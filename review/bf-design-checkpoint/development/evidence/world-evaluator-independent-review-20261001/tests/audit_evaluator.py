"""Independent saved-channel readback; no producer imports and no solver invocation."""
import copy, datetime, hashlib, json
from pathlib import Path
import numpy as np
ROOT=Path('/workspace/shared/causal-evaluator-repair-20261001')
OUT=Path('/workspace/shared/world-evaluator-independent-review-20261001/reports/evaluator-independent-readback.json')
load=lambda p:json.loads((ROOT/p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
plan=load('contracts/prospective-plan-v2.json');base=load('contracts/base-fixture-v2.json');receipt=load('DIAGNOSTIC-RESULT.json');reported=load('EVALUATION-RESULT.json')
checks={}; hashes={}
for seal_name in ['PLAN-SEAL.json','RUNNER-SEAL.json']:
 seal=load(seal_name)
 for p,h in seal['files'].items():
  actual=sha(ROOT/p);assert actual==h,(p,actual,h);hashes[p]=actual
assert sha(ROOT/'EVALUATION-RESULT.json')==receipt['evaluation_sha256']
assert sha(ROOT/'PLAN-SEAL.json')==receipt['plan_seal_sha256']
assert sha(ROOT/'RUNNER-SEAL.json')==receipt['runner_seal_sha256']
assert datetime.datetime.fromisoformat(load('PLAN-SEAL.json')['created_utc'])<datetime.datetime.fromisoformat(receipt['created_utc'])
assert receipt['scientific_runs_started']==receipt['scientific_runs_completed']==plan['maximum_scientific_solves']==12
assert receipt['complete'] is True
assert set(receipt['cases'])=={f'{m}-{l}-{i}' for m in plan['feedback_modes'] for l in plan['idle_current_a'] for i in range(3)}
for p,h in load('source-binding.json')['source_files'].items():assert sha(p)==h,p
assert sha(receipt['solver_path'])==receipt['solver_sha256']
grid=np.linspace(*plan['observation_window_s'],plan['observation_points']);traces={};results={};maxerr=0.
for name,c in receipt['cases'].items():
 folder=ROOT/'runs'/name;s=json.loads((folder/'input.json').read_text())
 for p,key in [('input.json','input_sha256'),('input.cir','deck_sha256'),('out.tsv','output_sha256')]:assert sha(folder/p)==c[key],(name,p)
 m,load_name,index=name.rsplit('-',2);index=int(index)
 expected=copy.deepcopy(base);expected['control']['feedback_mode']=m;expected['workload']['idle_current_a']=plan['idle_current_a'][load_name]
 assert s==expected,name
 assert c['max_step_s']==plan['max_steps_s'][index]
 deck=(folder/'input.cir').read_text()
 assert f"tran {c['max_step_s']:.12g} " in deck
 assert f"-v(timer)/{base['control']['timer_reset_tau_s']:.12g}" in deck
 assert ('Bpiezo_force u 0 I=0*v(p)' in deck)==(m=='no-feedback')
 d=np.loadtxt(folder/'out.tsv',skiprows=1);assert d.shape==(c['row_count'],15)
 assert np.isfinite(d).all() and np.all(np.diff(d[:,0])>0)
 t,drive,q,u,v,vs,enabled,timer,force,ir,il,diode,iq,ib,vneg=d.T
 assert abs(t[-1]-plan['duration_s'])<1e-12 and t[0]<=grid[0] and t[-1]>=grid[-1]
 traces[name]=np.interp(grid,t,q)
 mech,store,power=s['mechanics'],s['storage'],s['power'];theta=mech['coupling_n_v']
 integ=lambda y:float(np.trapezoid(y,t))
 dm=float((.5*mech['mass_kg']*u*u+.5*mech['stiffness_n_m']*q*q)[-1]-(.5*mech['mass_kg']*u*u+.5*mech['stiffness_n_m']*q*q)[0])
 dp=float(.5*mech['piezo_capacitance_f']*(v[-1]**2-v[0]**2));ds=float(.5*store['capacitance_f']*(vs[-1]**2-vs[0]**2))
 wf,wd,wg,wb,wr,wl,wq=[integ(x) for x in (force*u,mech['damping_ns_m']*u*u,theta*v*u,v*ib,vs*ir,vs*il,vs*iq)]
 react=wg if m=='reciprocal' else 0.;external=wg-react;absorb=wb-wr
 e={'mechanical_drive_work':wf,'mechanical_damping':wd,'mechanical_reaction_work':react,'electrical_generated_work':wg,'artificial_external_electrical_work':external,'piezo_to_bridge_work':wb,'rectifier_to_storage_work':wr,'load_input_work':wl,'ideal_regulated_output_work':power['efficiency']*wl,'ideal_converter_loss':(1-power['efficiency'])*wl,'quiescent_and_leakage_work':wq,'bridge_net_absorbed_work':absorb,'reference_resistor_work':integ(vneg*vneg/1e12),'mechanical_energy_change':dm,'piezo_energy_change':dp,'storage_energy_change':ds,'mechanical_balance_residual':wf-wd-dm-react,'piezo_balance_residual':wg-dp-wb,'storage_balance_residual':wr-wl-wq-ds,'total_balance_residual':wf+external-wd-dm-dp-ds-absorb-wl-wq}
 for k,value in e.items():
  delta=abs(value-reported['energy_ledgers'][name][k]);maxerr=max(maxerr,delta)
  assert np.isclose(value,reported['energy_ledgers'][name][k],rtol=1e-10,atol=1e-14),(name,k,value,reported['energy_ledgers'][name][k])
 active=np.flatnonzero((enabled>.5)&(il>0));idle=(enabled>.5)&(timer>=sum(x['duration_s'] for x in s['workload']['stages']))&(il>0)&(t>=grid[0])&(t<=grid[-1])
 activation=bool(len(active) and t[active[0]]<grid[0] and np.any(idle))
 assert activation==reported['activations'][name]['passed']
 assert int(idle.sum())==reported['activations'][name]['idle_rows_in_window']
 results[name]={'rows':len(t),'activation':activation,'energy_j':e,'input_sha256':c['input_sha256'],'output_sha256':c['output_sha256']}
ref={};conv={};criteria=plan['criteria'];floor=criteria['displacement_floor_m']
for m in plan['feedback_modes']:
 for l in plan['idle_current_a']:
  k=f'{m}-{l}';a,b,c=[traces[f'{k}-{i}'] for i in range(3)]
  coarse=float(np.max(np.abs(a-b)));fine=float(np.max(np.abs(b-c)));scale=max(float(np.max(np.abs(c))),floor)
  ref[k]={'coarse_halfstep_m':coarse,'finest_halfstep_m':fine,'finest_trace_scale_m':scale};conv[k]=fine<=criteria['max_finest_relative_trajectory_change']*scale
  for key,v in ref[k].items():assert np.isclose(v,reported['refinements'][k][key],rtol=1e-9,atol=1e-14),(k,key)
effect={m:float(np.max(np.abs(traces[f'{m}-baseline-2']-traces[f'{m}-treatment-2']))) for m in plan['feedback_modes']}
err=lambda k:ref[k]['finest_halfstep_m']
null=criteria['negative_control_refinement_multiplier']*(err('no-feedback-baseline')+err('no-feedback-treatment'))+floor
uncertainty=err('reciprocal-baseline')+err('reciprocal-treatment')+effect['no-feedback']+floor
margin=criteria['causal_separation_multiplier']*uncertainty
energies=[]
for name,r in results.items():
 if not name.startswith('reciprocal-') or not name.endswith('-2'):continue
 e=r['energy_j']
 for residual,work in [('mechanical_balance_residual','mechanical_drive_work'),('piezo_balance_residual','electrical_generated_work'),('storage_balance_residual','rectifier_to_storage_work')]:energies.append(abs(e[residual])<=max(criteria['energy_absolute_floor_j'],criteria['energy_relative_tolerance']*abs(e[work])))
 energies.append(e['bridge_net_absorbed_work']>=-max(criteria['energy_absolute_floor_j'],criteria['energy_relative_tolerance']*abs(e['piezo_to_bridge_work'])))
checks={'finite_positive_activation':all(r['activation'] for r in results.values()),'time_convergence':all(conv.values()),'no_feedback_negative_control':effect['no-feedback']<=null,'postactivation_causal_separation':effect['reciprocal']>margin,'reciprocal_energy_ports':all(energies)}
assert checks==reported['checks'];assert all(checks.values())==reported['diagnostic_passed']
for key,value in [('causal_required_margin_m',margin),('negative_control_budget_m',null)]:assert np.isclose(value,reported[key],rtol=1e-9,atol=1e-14)
assert reported['hardware_verified'] is False and reported['ltc3588_qualified'] is False and reported['integrated_authoritative_world_applicable'] is False
out={'schema':'bf-independent-evaluator-readback-v1','status':'pass_with_declared_scope','new_solver_runs':0,'producer_imports':0,'paid_calls':0,'case_count':12,'checks':checks,'effects_m':effect,'causal_required_margin_m':margin,'negative_control_budget_m':null,'maximum_energy_reconstruction_difference_j':maxerr,'refinements':ref,'verified_frozen_files':hashes,'cases':results,'scope':'Generic fixed-assumption diagnostic only; saved-channel quadrature and finite-refinement screen, not door-world, vendor, hardware or continuum error qualification'}
OUT.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('cases','verified_frozen_files','refinements')},indent=2))
