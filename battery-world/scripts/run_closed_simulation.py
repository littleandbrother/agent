#!/usr/bin/env python3
"""Reproduce candidate or six bounded native acceptance controls (no model API calls)."""
import argparse
import copy
import json
from pathlib import Path
import time
import numpy as np
from bfworld.agentlab.simulation_chain.pipeline import submit_candidate,implementation
from bfworld.agentlab.simulation_chain.contracts import DEFAULT,digest,file_hash,write_json
from bfworld.agentlab.simulation_chain import solver
from bfworld.agentlab.simulation_chain.cache import Cache
from bfworld.agentlab.runtime_config import HOME_ROOT

def acceptance(root):
    root.mkdir(parents=True,exist_ok=True);cache=root/'cache';impl=implementation();cases={}
    started=time.time()
    def run(name,spec,confirm=False,interrupt=None):
        print('CASE',name,flush=True);out=root/name
        if (out/'result.json').exists():
            result=json.loads((out/'result.json').read_text())
            if result['implementation']!=impl:raise RuntimeError('Acceptance source changed; use a new output directory')
        else:
            if time.time()-started>10800:raise RuntimeError('Acceptance wall cap')
            result=submit_candidate(spec,out,cache,confirm=confirm,interrupt_after=interrupt,
              event=lambda kind,data:print(kind,data.get('stage',''),flush=True))
        cases[name]={'run_status':result['run_status'],'error':result.get('error'),'physics_hash':result.get('physics_hash'),
                     'metrics':result.get('metrics'),'result_sha256':file_hash(out/'result.json')}
        write_json(root/'cases.json',cases);return result
    baseline=run('baseline',{},True)
    mechanical=run('mechanical-gap-50',{'mechanical':{'gap_mm':50}})
    circuit=run('circuit-cin-22',{'circuit':{'cin_uF':22}})
    positive=run('positive-module',{'circuit':{'diagnostic_input_A':.001}},True)
    strategy=run('firmware-interval-200',{'circuit':{'diagnostic_input_A':.001},'firmware':{'interval_ms':200}})
    interrupted=run('checkpoint-interrupted',{},interrupt='firmware')
    resumed=run('checkpoint-resumed',{})
    camera=run('camera-only',{'presentation':{'camera_deg':-35}})
    no_motion=run('no-motion',{'mechanical':{'opening_s':0}})
    outside=run('outside-rom',{'mechanical':{'gap_mm':28}})
    # A bounded tool-startup retry is a NEW run; the failed attempt remains.
    if outside['run_status']=='tool_fail':outside=run('outside-rom-retry',{'mechanical':{'gap_mm':28}})
    def key(r,s):return r.get('stages',{}).get(s,{}).get('key')
    def eq(a,b,stages):return all(key(a,s) and key(a,s)==key(b,s) for s in stages)
    checks={
      '1_clean_baseline_repeatable_failure':baseline['run_status']=='completed' and not baseline['metrics']['cold_start_reached'] and eq(baseline,resumed,['joint']) and baseline['metrics']==resumed.get('metrics'),
      '2_mechanical_change_propagates':mechanical['run_status']=='completed' and all(key(baseline,s)!=key(mechanical,s) for s in ['cad','force','joint']) and eq(baseline,mechanical,['beam','firmware']),
      '3_circuit_change_recouples':circuit['run_status']=='completed' and eq(baseline,circuit,['cad','beam','force','firmware']) and key(circuit,'joint')!=key(baseline,'joint') and baseline['metrics']['peak_storage_V']!=circuit['metrics']['peak_storage_V'],
      '4_firmware_build_load_and_packet_change':strategy['run_status']=='completed' and eq(positive,strategy,['cad','beam','force']) and all(key(positive,s)!=key(strategy,s) for s in ['firmware','joint']) and positive['metrics']['tx_completed']>strategy['metrics']['tx_completed']>0,
      '5_camera_and_interruption_recovery':interrupted['run_status']=='tool_fail' and resumed['run_status']=='completed' and camera['run_status']=='completed' and baseline['physics_hash']==resumed['physics_hash']==camera['physics_hash'] and eq(baseline,camera,['cad','beam','force','firmware','joint']) and all(s['cache_hit'] for s in resumed['stages'].values()),
      '6_positive_module_power_program_receiver':positive['run_status']=='completed' and positive.get('module_diagnostic_passed',False) and positive['product_verified'] is False,
      'no_motion_no_harvest_or_packet':no_motion['run_status']=='completed' and no_motion['metrics']['tx_completed']==0 and abs(no_motion['energy_ledger']['pmic_port_energy_J'])<1e-9,
      'model_domain_is_not_design_failure':outside['run_status']=='out_of_domain' and outside['design_status']=='insufficient_evidence' and outside.get('predicted_design_status') is None,
    }
    # Native passive-load comparison against independently integrated ODE; this
    # catches sign errors, duplicate Cp and a disconnected electrical back-action.
    checkpoint_root=Cache(cache).root
    beam=checkpoint_root/'beam'/key(baseline,'beam');force=checkpoint_root/'force'/key(baseline,'force');fw=checkpoint_root/'firmware'/key(baseline,'firmware')
    rom=json.loads((beam/'rom.json').read_text());passive={};max_errors={}
    from scipy.integrate import solve_ivp
    from scipy.interpolate import RegularGridInterpolator
    table=np.load(force/'force-table.npz');interpolate=RegularGridInterpolator((table['angles'],table['qs']),table['values'],bounds_error=True)
    for resistance in (100000,1000000):
        out=root/('passive-'+str(resistance));out.mkdir(exist_ok=True)
        if not (out/'solve.json').exists():solver.solve(out,DEFAULT,rom,force/'force-table.npz',fw,resistor=resistance)
        value=json.loads((out/'solve.json').read_text());raw=np.genfromtxt(out/'waveform.csv',delimiter=',',names=True);passive[resistance]=raw
        damp=2*DEFAULT['mechanical']['damping_ratio']*np.sqrt(rom['k']*rom['mass'])
        def rhs(t,y):
            q,u,v=y;a=min(t/2,1)*np.deg2rad(65);f=float(interpolate([[a,q]])[0])
            return [u,(f-rom['k']*q-damp*u-rom['theta']*v)/rom['mass'],(rom['theta']*u-v/resistance)/rom['cp']]
        ref=solve_ivp(rhs,[0,4],[value['q0_m'],0,0],t_eval=raw['time_s'],method='Radau',rtol=1e-8,atol=1e-11,max_step=.0001)
        max_errors[str(resistance)]={'tip':float(max(abs(raw['tip_m']-ref.y[0]))/max(abs(ref.y[0]))),'voltage':float(max(abs(raw['piezo_V']-ref.y[2]))/max(abs(ref.y[2])))}
    checks['passive_ODE_reference']=max(x for r in max_errors.values() for x in r.values())<.01
    checks['electrical_back_action']=float(max(abs(passive[100000]['tip_m']-passive[1000000]['tip_m'])))>1e-6
    # Bounded deterministic range study, not a probabilistic Monte Carlo claim.
    uncertainty=[]
    for name,m in [('damping-low',{'damping_ratio':.01}),('damping-high',{'damping_ratio':.08}),
                   ('remanence-low',{'remanence_T':1.}),('remanence-high',{'remanence_T':1.4})]:
        r=run('range-'+name,{'mechanical':m})
        uncertainty.append({'condition':m,'run_status':r['run_status'],'predicted':r.get('predicted_design_status'),'metrics':r.get('metrics')})
    write_json(root/'uncertainty.json',{'scope':'one-factor bounded sensitivity, no distributions, Sobol indices or probability-of-success claim','runs':uncertainty})
    receipt={'schema_version':'closed-simulation-acceptance-v1','checks':checks,'six_acceptance_passed':all(checks[k] for k in list(checks)[:6]),
      'all_controls_passed':all(checks.values()),'passive_reference_relative_errors':max_errors,'cases':cases,
      'product_accepted':False,'model_calls':0,'model_sufficiency':baseline.get('applicability'),
      'numerical_checks':baseline.get('checks'),'elapsed_s':time.time()-started,'implementation':impl}
    receipt['runner_sha256']=file_hash(Path(__file__))
    write_json(root/'receipt.json',receipt)
    print(json.dumps({k:receipt[k] for k in ('checks','six_acceptance_passed','all_controls_passed','elapsed_s')},ensure_ascii=False,indent=2),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--acceptance',action='store_true');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--spec',type=Path);p.add_argument('--cache',type=Path,default=HOME_ROOT/'simulation-chain/cache');p.add_argument('--explore',action='store_true')
    a=p.parse_args()
    if a.acceptance:acceptance(a.output)
    else:
        r=submit_candidate(json.loads(a.spec.read_text()) if a.spec else {},a.output,a.cache,confirm=not a.explore)
        print(json.dumps(r,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
