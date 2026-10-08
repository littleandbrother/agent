"""D5 native reciprocal mechanics/extractor/PMIC/gate and shared-C fixed point.

No precharged storage, clock-driven extractor, independent controller supply or
reduced application workload. Any incomplete native run/fixed point is rejected.
"""
import shutil
import os
import re
import json
import subprocess
from pathlib import Path
import numpy as np
from scipy.integrate import cumulative_trapezoid
from ..door_system import solver as d4, native, model
from ..simulation_chain.contracts import ChainError, write_json
from ..simulation_chain.native import command
from . import contracts, extraction, ratings as terminal_ratings
from .archive import archive_raw
from .native_process import contain_timeout


def deck(directory,design,rom,force,grid,current,max_step_scale=1.,iq_scale=1.):
    original=design['base_design'];spec=native.solver_spec(original)
    spec['solver']['max_step_s']*=max_step_scale
    q0,damping=d4.deck(directory,spec,rom,force,grid,current)
    gate=contracts.GATES[design['gate']]
    if gate:gate={**gate,'iq_A':1.5e-6*iq_scale,'load_switch':design.get('gate_switch','BSS84')}
    text=extraction.replace_power((directory/'system.cir').read_text(),spec,
          design['extraction']['topology'],ce=design['extraction']['envelope_pF']*1e-12,
          inductance=design['parts']['coil']['L_H'],dcr=design['parts']['coil']['dcr_ohm_max'],
          profile={'BAT46WJ':'schottky','BAT46WJ-3P':'schottky-parallel','BAS21HY':'rated-sece'}[design['extraction']['diodes']],gate=gate)
    if gate is None:text=text.replace('.tran ', 'Vmcu mcu out 0\n.tran ',1)
    names='V(mcu) V(cap) V(vin2) V(port) V(pz2) I(L1)'
    if gate:names+=' V(gate) V(ctl_delay) V(hth) V(lth) I(Bmonitor) I(Rmon1) I(Smonitor) I(Smonitor_high)'
    top=design['extraction']['topology']
    if top=='sece':names+=' V(rect) V(env) V(base) V(nb) V(lx) V(collector) I(Lextract) '+terminal_ratings.saved_channels(design)
    elif top=='psshi':names+=' V(envp) V(envn) V(lc) I(Lp)'
    text=text.replace('I(Bload)','I(Bload) '+names)
    (directory/'system.cir').write_text(text)
    return q0,damping,spec


def evaluate_program(firmware,t,v):
    return d4.execute_program(firmware,t,v[:,0],v[:,1])


def gate_observation(t,v,design):
    """Read-only facts: an unpowered VIN peak is not an enable opportunity."""
    gate=contracts.GATES[design['gate']]
    if gate is None:return {'bypassed':True}
    powered=v['v(out)']>=1.5
    enabled=powered & (v['v(gate)']<=.1*v['v(out)'])
    def first(mask):return float(t[np.flatnonzero(mask)[0]]) if np.any(mask) else None
    return {'schema_version':'bf-reserve-gate-observation-v1','bypassed':False,
            'monitor_supply_min_V':1.5,'enable_threshold_V':gate['high_V'],'disable_threshold_V':gate['low_V'],
            'overall_VIN_peak_V':float(max(v['v(vin)'])),
            'powered_VIN_peak_V':float(max(v['v(vin)'][powered])) if np.any(powered) else None,
            'powered_control_peak_V':float(max(v['v(ctl_delay)'][powered])) if np.any(powered) else None,
            'first_monitor_powered_s':first(powered),'first_gate_enabled_s':first(enabled),
            'scope':'Observed native voltages in the declared behavioral monitor; not a hardware threshold or tolerance qualification.'}


def native_solve(directory,duration):
    # Prospective D5 execution budget only. D4's frozen numerical tolerances and
    # prior240s timeout failure are retained; waveform acceptance is unchanged.
    try:
        command([d4.WINE,'--enable-alt-loader=macdrv','--bottle','default','--no-gui','--workdir',
                 'C:/Program Files/ADI/LTspice','LTspice.exe','-b',directory/'system.cir'],directory,'launcher',600)
    except ChainError as exc:
        if isinstance(exc.__cause__,subprocess.TimeoutExpired):contain_timeout(directory)
        raise
    log=(directory/'system.log').read_text(errors='replace')
    if 'Total elapsed time:' not in log or 'Fatal' in log:raise ChainError('numerical_fail','D5 native transient incomplete')
    if 'tolerance relaxed' in log.lower():raise ChainError('numerical_fail','D5 native solver relaxed requested tolerance')
    t,v=d4.read_raw(directory/'system.raw',duration)
    for key,var in [('storage_peak','v(vin)'),('output_peak','v(out)')]:
        match=re.search(r'^'+key+r':.*?=\s*([-+\d.eE]+)',log,re.M)
        if not match or not np.isclose(float(match[1]),max(v[var]),rtol=5e-4,atol=1e-7):
            raise ChainError('numerical_fail','D5 native .meas/RAW mismatch:'+key)
    return t,v


def solve(directory,design,rom,force,firmware,*,max_step_scale=1.,iq_scale=1.):
    contracts.verify_design(design)
    task=design['base_design']['frozen']['task']; frozen=design['base_design']['frozen']
    duration=task['deadline_s'];dt=frozen['numerics']['firmware_step_s']
    grid=np.linspace(0,duration,round(duration/dt)+1)
    current=np.full(len(grid),frozen['model']['reset_uA']*1e-6)
    previous=None;iterations=[];converged=False
    for n in range(frozen['numerics']['max_coupling_iterations']):
        path=directory/f'iteration-{n:02}';path.mkdir()
        q0,damping,spec=deck(path,design,rom,force,grid,current,max_step_scale,iq_scale)
        t,v=native_solve(path,duration)
        gate_facts=gate_observation(t,v,design)
        write_json(path/'gate-observation.json',gate_facts)
        if t[0]==0 and abs(v['v(q)'][0]-q0)>1e-9 and t[1]<1e-7 and abs(v['v(q)'][1]-q0)<1e-7:
            v['v(q)'][0]=q0;v['v(force)'][0]=rom['k']*q0
            # The UIC t=0 display row may contain arbitrary L currents. These
            # declared zero-energy states alone are restored in derived arrays.
            for key in ('i(lextract)','i(lp)','i(l1)'):
                if key in v:v[key][0]=0.
        if max(abs(v['v(q)']))>frozen['model']['beam_limit_m']+1e-8:
            write_json(directory/'provisional-solve.json',{'fixed_point':False,'not_task_acceptance':True,
                'peak_tip_mm':float(max(abs(v['v(q)']))*1000),'domain_limit_mm':8.,'iteration':n})
            archive_raw(path/'system.raw')
            raise ChainError('out_of_domain','D5 ROM domain exceeded; no extrapolated verdict')
        supply=d4.conservative_sample(t,v['v(mcu)'],grid)
        good=d4.conservative_sample(t,v['v(pgood)'],grid)
        nxt,states,events=d4.execute_program(firmware,grid,supply,good)
        diff=float(np.max(abs(nxt-current)))
        dv=float(np.max(abs(supply-previous))) if previous is not None else None
        iterations.append({'iteration':n,'max_current_difference_A':diff,
                           'max_supply_difference_V':dv,'complete_TX':len(events),
                           'first_mismatch_s':float(grid[np.flatnonzero(abs(nxt-current)>1e-12)[0]]) if diff>1e-12 else None,
                           'peak_storage_V':float(max(v['v(vin)'])),'peak_mcu_V':float(max(supply)),
                           'gate_observation':gate_facts,
                           'program_states':sorted(set(states.tolist()))})
        write_json(directory/'coupling-iterations.json',iterations)
        np.savetxt(path/'program.csv',np.column_stack([grid,supply,good,states,nxt]),delimiter=',',
                   header='time_s,mcu_supply_V,pgood_V,state,current_A',comments='')
        write_json(path/'provisional-TX.json',{'events':events,'fixed_point':False,'not_task_acceptance':True})
        write_json(directory/'provisional-solve.json',{'fixed_point':False,'not_task_acceptance':True,
            'iteration':n,'observations':iterations[-1],
            'first_TX_brownout_s':float(grid[1:][np.flatnonzero((states[:-1]==4)&(states[1:]==0)&(supply[1:]<1.8))[0]])
                 if np.any((states[:-1]==4)&(states[1:]==0)&(supply[1:]<1.8)) else None,
            'minimum_active_supply_V':float(min(supply[states>0])) if np.any(states>0) else None})
        shutil.copy2(path/'program.csv',directory/'provisional-program.csv')
        sample=np.linspace(0,duration,13001)
        columns=['v(q)','v(u)','v(pz1,pz2)','v(vin)','v(out)','v(mcu)','v(pgood)']
        columns+=['v(ctl_delay)','v(gate)']
        np.savetxt(directory/'provisional-waveform.csv',np.column_stack([sample]+[np.interp(sample,t,(v[k] if k in v else np.zeros_like(t))) for k in columns]),delimiter=',',
                   header='time_s,tip_m,velocity_m_s,piezo_V,storage_V,regulated_V,mcu_V,pgood_V,gate_control_V,load_switch_gate_V',comments='')
        archive_raw(path/'system.raw')
        if diff<1e-12 and (previous is None or dv<.001):converged=True;break
        current=nxt;previous=supply
    if not converged:raise ChainError('numerical_fail','D5 power/program waveform fixed point not reached')
    receiver=d4.receive(firmware,events,spec['link']);write_json(directory/'receiver.json',receiver)
    np.savetxt(directory/'program.csv',np.column_stack([grid,supply,good,states,nxt]),delimiter=',',
               header='time_s,mcu_supply_V,pgood_V,state,current_A',comments='')
    q,u,pz,F=[v[k] for k in ('v(q)','v(u)','v(pz1,pz2)','v(force)')]
    stored=.5*rom['mass']*u*u+.5*rom['k']*q*q+.5*rom['cp']*pz*pz
    port=cumulative_trapezoid(pz*v['i(vsense)'],t,initial=0)
    loss=cumulative_trapezoid(damping*u*u,t,initial=0)
    work=cumulative_trapezoid(F*u,t,initial=0)
    residual=stored-stored[0]+port+loss-work
    scale=max(np.max(abs(work)),stored[0],np.max(abs(port)),1e-12)
    top=design['extraction']['topology'];c=design['base_design']['circuit']
    load_energy=float(np.trapezoid(v['v(mcu)' if design['gate']!='off' else 'v(out)']*v['i(bload)'],t))
    monitor_energy=float(np.trapezoid(v['v(out)']*v['i(bmonitor)'],t)) if design['gate']!='off' else 0.
    divider_energy=float(np.trapezoid(v['v(vin)']*v['i(rmon1)'],t)) if design['gate']!='off' else 0.
    # The push-pull L output has no N-version pull-up resistor. Its actual
    # powered output-switch dissipation is retained, rather than zeroing all
    # controller output losses when the obsolete resistor is removed.
    pullup_loss=0.
    output_stage_loss=float(np.trapezoid(v['v(gate)']*v['i(smonitor)']
           +(v['v(gate)']-v['v(out)'])*v['i(smonitor_high)'],t)) if design['gate']!='off' else 0.
    Lkey={'sece':'i(lextract)','psshi':'i(lp)'}.get(top)
    coil_loss=float(design['parts']['coil']['dcr_ohm_max']*np.trapezoid(v[Lkey]**2,t)) if Lkey else 0.
    estore=.5*c['cin_uF']*1e-6*v['v(vin)']**2+.5*c['cout_uF']*1e-6*v['v(out)']**2
    estore+=.5*4.7e-6*v['v(vin2)']**2+.5*1e-6*(v['v(vin)']-v['v(cap)'])**2+.5*10e-6*v['i(l1)']**2
    ce=design['extraction']['envelope_pF']*1e-12
    if top=='sece':estore+=.5*ce*v['v(env)']**2
    if top=='psshi':estore+=.5*ce*(v['v(envp)']**2+v['v(envn)']**2)
    if Lkey:estore+=.5*design['parts']['coil']['L_H']*v[Lkey]**2
    if design['gate']!='off':estore+=.5*100e-9*v['v(mcu)']**2
    # Lower bound only: encrypted PMIC losses and BJT junction storage are not
    # exposed. This cannot be labeled a full electrical energy residual.
    known=estore[-1]+load_energy+monitor_energy+divider_energy+pullup_loss+output_stage_loss+coil_loss
    ledger={'initial_electric_J':0.,'independent_control_source_J':0.,'diagnostic_source_J':0.,
        'mechanical_piezo_relative_residual':float(max(abs(residual))/scale),
        'piezo_port_J':float(port[-1]),'application_J':load_energy,'monitor_IQ_J':monitor_energy,
        'divider_J':divider_energy,'pullup_loss_J':pullup_loss,'gate_output_stage_loss_J':output_stage_loss,
        'extractor_coil_loss_J':coil_loss,
        'final_observable_storage_J':float(estore[-1]),'known_electrical_energy_J':float(known),
        'unresolved_electronics_J':float(port[-1]-known),
        'energy_lower_bound_passed':bool(port[-1]+1e-6>=known),
        'boundary':'MIC841 logic is behavioral with powered IQ/divider/PMOS; encrypted PMIC + junction/core/ESR losses not fully certified.'}
    write_json(directory/'energy.json',ledger)
    pzt_peak=float(max(abs(pz[t>1e-7])))
    ratings=terminal_ratings.check(t,v,design)
    write_json(directory/'rating-check.json',ratings)
    sample=np.linspace(0,duration,13001)
    columns=['v(q)','v(u)','v(pz1,pz2)','v(vin)','v(out)','v(mcu)','v(pgood)']
    columns+=['v(ctl_delay)','v(gate)']
    np.savetxt(directory/'waveform.csv',np.column_stack([sample]+[np.interp(sample,t,(v[k] if k in v else np.zeros_like(t))) for k in columns]),delimiter=',',
               header='time_s,tip_m,velocity_m_s,piezo_V,storage_V,regulated_V,mcu_V,pgood_V,gate_control_V,load_switch_gate_V',comments='')
    write_json(directory/'gate-observation.json',gate_facts)
    for name in ('system.cir','system.log','load.pwl','system.raw.archive.json'):shutil.copy2(path/name,directory/name)
    archive=json.loads((path/'system.raw.archive.json').read_text())
    os.link(path/archive['archive_name'],directory/archive['archive_name'])
    summary={'design_id':design['design_id'],'coupling_converged':True,'iterations':iterations,'energy_ledger':ledger,
        'peak_tip_mm':float(max(abs(q))*1000),'peak_piezo_V':pzt_peak,'peak_storage_V':float(max(v['v(vin)'])),
        'peak_supply_V':float(max(v['v(mcu)'])),'tx_completed':len(events),'received_events':len(receiver['events']),
        'cold_start_reached':bool(max(v['v(mcu)'])>=3.2),'program_states_reached':sorted(set(states.tolist())),
        'numerical_energy_passed':ledger['mechanical_piezo_relative_residual']<.01,
        'ratings':ratings,'diagnostic_only':False,'q0_m':q0,
        'first_TX_s':events[0]['time_s'] if events else None,
        'first_RX_s':receiver['delivered'][0]['time_s'] if receiver['delivered'] else None}
    summary['gate_observation']=gate_facts
    summary['drive_ledger']=model.drive_ledger(directory,design['base_design'],rom,t,q,u,pz,port,loss)
    write_json(directory/'solve.json',summary)
    return summary
