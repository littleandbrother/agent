"""Prospective candidate-program kernel, isolated from frozen historical D5.

Deck, native circuit reader and voltage/gate observations reuse the unchanged
historical D5 helpers. This new module owns candidate-program/receiver callbacks.
No participant can select or modify these trusted functions.
"""
import shutil
import os
import json
import numpy as np
from scipy.integrate import cumulative_trapezoid
from ..door_system import solver as d4, model
from ..simulation_chain.contracts import ChainError, write_json
from ..door_selfpower import contracts, ratings as terminal_ratings
from ..door_selfpower.archive import archive_raw
from ..door_selfpower.solver import deck, native_solve, gate_observation

def solve(directory,design,rom,force,firmware,*,max_step_scale=1.,iq_scale=1.,
          program_executor=None,receiver_executor=None):
    # The legacy execution path remains the default. A prospective apparatus
    # version may supply a trusted, isolated application executor. Participants
    # never provide these callables or select validation/solver implementations.
    execute = program_executor or d4.execute_program
    receive = receiver_executor or d4.receive
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
        nxt,states,events=execute(firmware,grid,supply,good)
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
    receiver=receive(firmware,events,spec['link']);write_json(directory/'receiver.json',receiver)
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
