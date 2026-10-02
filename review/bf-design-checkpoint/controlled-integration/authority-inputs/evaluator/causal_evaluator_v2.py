"""Prospective causal validation, independently versioned from apparatus/old gates."""
import bisect
import math
from event_apparatus_v2 import integrate
EVALUATOR_VERSION='bf-causal-evaluator-v2-postactivation'

def interpolate(rows, grid, key='displacement_m'):
    times=[r['time_s'] for r in rows]
    if grid[0]<times[0] or grid[-1]>times[-1]:
        raise ValueError('OBSERVATION_WINDOW_UNCOVERED')
    vals=[]
    for t in grid:
        i=bisect.bisect_left(times,t)
        if times[i]==t: vals.append(rows[i][key]); continue
        a,b=rows[i-1],rows[i]
        vals.append(a[key]+(b[key]-a[key])*(t-a['time_s'])/(b['time_s']-a['time_s']))
    return vals

def maxdiff(a,b):
    if len(a)!=len(b) or not a: raise ValueError('GRID_MISMATCH')
    if any(not math.isfinite(x) for x in [*a,*b]): raise ValueError('NONFINITE_METRIC')
    return max(abs(x-y) for x,y in zip(a,b))

def energy_ledger(spec,rows):
    m,s,p=spec['mechanics'],spec['storage'],spec['power']
    times=[r['time_s'] for r in rows]
    integral=lambda key: integrate(times,[key(r) for r in rows])
    first,last=rows[0],rows[-1]
    mechanical=lambda r:.5*m['mass_kg']*r['velocity_m_s']**2+.5*m['stiffness_n_m']*r['displacement_m']**2
    piezo=lambda r:.5*m['piezo_capacitance_f']*r['piezo_v']**2
    storage=lambda r:.5*s['capacitance_f']*r['storage_v']**2
    drive=integral(lambda r:r['force_n']*r['velocity_m_s'])
    damping=integral(lambda r:m['damping_ns_m']*r['velocity_m_s']**2)
    generated=integral(lambda r:m['coupling_n_v']*r['piezo_v']*r['velocity_m_s'])
    reaction=generated if spec['control']['feedback_mode']=='reciprocal' else 0.
    bridge_in=integral(lambda r:r['piezo_v']*r['piezo_to_bridge_a'])
    rectified=integral(lambda r:r['storage_v']*r['rectifier_a'])
    load=integral(lambda r:r['storage_v']*r['load_a'])
    quiescent=integral(lambda r:r['storage_v']*r['quiescent_a'])
    dm,dp,ds=mechanical(last)-mechanical(first),piezo(last)-piezo(first),storage(last)-storage(first)
    bridge_absorbed=bridge_in-rectified
    external=generated-reaction
    # All balances use exactly the first-to-last exported interval.
    # Bridge absorbed work includes diode losses/change in stored junction energy
    # and the 1e12-ohm numerical reference path, not inferred pure dissipation.
    return {'units':'J','integration_start_s':times[0],'integration_end_s':times[-1],
        'mechanical_drive_work':drive,'mechanical_damping':damping,
        'mechanical_reaction_work':reaction,'electrical_generated_work':generated,
        'artificial_external_electrical_work':external,'piezo_to_bridge_work':bridge_in,
        'rectifier_to_storage_work':rectified,'load_input_work':load,
        'ideal_regulated_output_work':p['efficiency']*load,
        'ideal_converter_loss':(1-p['efficiency'])*load,
        'quiescent_and_leakage_work':quiescent,'bridge_net_absorbed_work':bridge_absorbed,
        'reference_resistor_work':integral(lambda r:r['negative_rail_v']**2/1e12),
        'mechanical_energy_change':dm,'piezo_energy_change':dp,'storage_energy_change':ds,
        'mechanical_balance_residual':drive-damping-dm-reaction,
        'piezo_balance_residual':generated-dp-bridge_in,
        'storage_balance_residual':rectified-load-quiescent-ds,
        'total_balance_residual':drive+external-damping-dm-dp-ds-bridge_absorbed-load-quiescent,
        'initial_exported_mechanical_energy':mechanical(first),
        'initial_exported_piezo_energy':piezo(first),'initial_exported_storage_energy':storage(first)}

def evaluate(plan,cases):
    expected={f'{mode}-{load}-{i}' for mode in plan['feedback_modes'] for load in plan['idle_current_a'] for i in range(3)}
    if set(cases)!=expected: raise ValueError('EXACT_CASE_MATRIX_REQUIRED')
    start,end=plan['observation_window_s']; count=plan['observation_points']
    grid=[start+(end-start)*i/(count-1) for i in range(count)]
    criteria=plan['criteria']; floor=criteria['displacement_floor_m']; traces={}; activations={}; energies={}
    for name,case in cases.items():
        rows,spec=case['rows'],case['spec']
        if abs(rows[-1]['time_s']-plan['duration_s'])>1e-12: raise ValueError('TRANSIENT_INCOMPLETE')
        trace=interpolate(rows,grid); traces[name]=trace
        enabled=[r for r in rows if r['enabled']>.5 and r['load_a']>0]
        idle_end=sum(s['duration_s'] for s in spec['workload']['stages'])
        idle=[r for r in rows if r['enabled']>.5 and r['stage_time_s']>=idle_end and r['load_a']>0 and start<=r['time_s']<=end]
        activations[name]={'first_positive_load_time_s':enabled[0]['time_s'] if enabled else None,
            'idle_rows_in_window':len(idle),'passed':bool(enabled and enabled[0]['time_s']<start and idle)}
        energies[name]=energy_ledger(spec,rows)
    refinements={}; convergence={}
    for mode in plan['feedback_modes']:
        for load in plan['idle_current_a']:
            key=f'{mode}-{load}'; a,b,c=[traces[f'{key}-{i}'] for i in range(3)]
            e0,e1=maxdiff(a,b),maxdiff(b,c); scale=max(max(abs(x) for x in c),floor)
            refinements[key]={'coarse_halfstep_m':e0,'finest_halfstep_m':e1,'finest_trace_scale_m':scale,
                'ratio_fine_over_coarse':e1/e0 if e0 else None}
            convergence[key]=e1<=criteria['max_finest_relative_trajectory_change']*scale
    rb,rt='reciprocal-baseline','reciprocal-treatment'; nb,nt='no-feedback-baseline','no-feedback-treatment'
    effects={mode:maxdiff(traces[f'{mode}-baseline-2'],traces[f'{mode}-treatment-2']) for mode in plan['feedback_modes']}
    error=lambda name:refinements[name]['finest_halfstep_m']
    null_budget=criteria['negative_control_refinement_multiplier']*(error(nb)+error(nt))+floor
    causal_uncertainty=error(rb)+error(rt)+effects['no-feedback']+floor
    margin=criteria['causal_separation_multiplier']*causal_uncertainty
    energy_checks={}
    for name,e in energies.items():
        if not name.endswith('-2') or not name.startswith('reciprocal-'): continue
        for residual,work in [('mechanical_balance_residual','mechanical_drive_work'),('piezo_balance_residual','electrical_generated_work'),('storage_balance_residual','rectifier_to_storage_work')]:
            budget=max(criteria['energy_absolute_floor_j'],criteria['energy_relative_tolerance']*abs(e[work]))
            energy_checks[name+':'+residual]={'passed':abs(e[residual])<=budget,'residual_j':e[residual],'budget_j':budget}
        budget=max(criteria['energy_absolute_floor_j'],criteria['energy_relative_tolerance']*abs(e['piezo_to_bridge_work']))
        energy_checks[name+':bridge_nonnegative']={'passed':e['bridge_net_absorbed_work']>=-budget,'absorbed_j':e['bridge_net_absorbed_work'],'budget_j':budget}
    checks={'finite_positive_activation':all(a['passed'] for a in activations.values()),
        'time_convergence':all(convergence.values()),'no_feedback_negative_control':effects['no-feedback']<=null_budget,
        'postactivation_causal_separation':effects['reciprocal']>margin,
        'reciprocal_energy_ports':all(e['passed'] for e in energy_checks.values())}
    return {'schema_version':EVALUATOR_VERSION,'checks':checks,'diagnostic_passed':all(checks.values()),
        'effects_m':effects,'causal_uncertainty_envelope_m':causal_uncertainty,'causal_required_margin_m':margin,
        'negative_control_budget_m':null_budget,'refinements':refinements,'convergence_checks':convergence,
        'activations':activations,'energy_checks':energy_checks,'energy_ledgers':energies,
        'global_peak_is_not_causal_gate':True,'hardware_verified':False,'ltc3588_qualified':False,
        'uncertainty_status':'empirical finite-refinement envelope, not certified continuum error bound',
        'integrated_authoritative_world_applicable':False}
