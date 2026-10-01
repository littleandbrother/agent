#!/usr/bin/env python3
"""Read-only reanalysis of four retained, frozen conditional-passive trajectories.

No project imports, SciPy, provider calls, equilibrium solve, ODE integration,
network, extraction, model execution or threshold optimization. Requires NumPy.
Scientific tolerances come only from the byte-verified original PLAN.json.
"""
import argparse
import hashlib
import io
import json
import os
import platform
import sys
import tarfile
import zipfile
from pathlib import Path
import numpy as np
from numpy.polynomial import Polynomial

WRAPPER = 'BF_Conditional_Passive_20261001/'
NEW = 'passive-source-storage-jacobian-20261001/'
OLD = 'passive-source-storage-20261001/'
ARCHIVES = {
    'BF_Conditional_Passive_20261001_core.zip': 'e43d54c5289d7100c50a700429c2f08dfdc4a0531c5cbd0bb99097d3d1e497ec',
    'BF_Conditional_Passive_20261001_raw47.tar.xz': '83ff27440bf80cfa19b568a690bbfa8dfacf7d773ee30d66862146bdbfa6d19d',
    'BF_Conditional_Passive_20261001_raw10.tar.xz': '35b93a24df43518538492a35857f70f8ede441524533aed43bd4bc6fdd9ca089',
}
MANIFEST_SHA = 'b487357a066919aad8e32d96214553d2fa7f69d26e35a012f69414eafc1ccf6c'
NEW_PLAN_SHA = '0f8ae3b0b8d6d5d0d1accfa46fe4dc8f479f874be58cc30bc135567112ca3684'
ENERGIES = ['kinetic_J', 'elastic_J', 'piezo_J', 'storage_J', 'mutual_magnetic_J']
RATES = ['Dmechanical_J', 'Dresistor_J', 'Wdriver_translation_J', 'Wdriver_rotation_J']

def sha(data):
    return hashlib.sha256(data).hexdigest()

def require(ok, message):
    if not bool(ok):
        raise ValueError(message)

def maxabs(x):
    return float(np.max(np.abs(x)))

def same_numeric(a, b, name):
    """Floating re-evaluation consistency, NOT a scientific admission threshold."""
    a, b = np.asarray(a), np.asarray(b)
    require(a.shape == b.shape, 'shape mismatch: ' + name)
    if a.dtype == np.bool_ or b.dtype == np.bool_:
        require(np.array_equal(a, b), 'boolean readback mismatch: ' + name)
        return 0.
    # Dense evaluation and algebra reorder float64 operations by a few ulps.
    require(np.allclose(a, b, rtol=1e-11, atol=1e-13), 'algebra readback mismatch: ' + name)
    return maxabs(a - b)

def limits(coeff):
    p = Polynomial(coeff)
    roots = p.deriv().roots()
    x = [0., 1.] + [float(z.real) for z in roots if abs(z.imag) < 1e-9 and 0 < z.real < 1]
    y = p(x)
    return float(min(y)), float(max(y))

class Inputs:
    def __init__(self, directory, recovery):
        self.data, self.locations, self.used = {}, {}, set()
        self.archives = []
        for filename, expected in ARCHIVES.items():
            path = directory / filename
            payload = path.read_bytes()
            digest = sha(payload)
            require(digest == expected, 'archive SHA mismatch: ' + filename)
            self.archives.append({'filename': filename, 'sha256': digest, 'bytes': len(payload)})
            if filename.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(payload)) as z:
                    members = [(n, z.read(n)) for n in z.namelist() if not n.endswith('/')]
            else:
                with tarfile.open(fileobj=io.BytesIO(payload), mode='r:xz') as t:
                    members = [(m.name, t.extractfile(m).read()) for m in t.getmembers() if m.isfile()]
            for member, data in members:
                require(member.startswith(WRAPPER), 'unexpected wrapper: ' + member)
                rel = member[len(WRAPPER):]
                require(rel not in self.data, 'duplicate archive member: ' + rel)
                self.data[rel] = data
                self.locations[rel] = {'archive': filename, 'member': member, 'sha256': sha(data), 'bytes': len(data)}
        require(sha(self.data['PACKAGE-MANIFEST.json']) == MANIFEST_SHA, 'package manifest SHA mismatch')
        manifest = self.json('PACKAGE-MANIFEST.json')
        require(len(manifest['files']) == 268, 'unexpected package member count')
        require(set(self.data) == set(manifest['files']) | {'PACKAGE-MANIFEST.json'}, 'manifest member set mismatch')
        for name, expected in manifest['files'].items():
            require(sha(self.data[name]) == expected, 'member SHA mismatch: ' + name)
        self.manifest_count = len(manifest['files'])
        self.recovery = None
        if recovery is not None:
            payload = recovery.read_bytes()
            index = json.loads(payload)
            found = {Path(a['local_path']).name: a for a in index['archive_verification']}
            for name, expected in ARCHIVES.items():
                require(found[name]['expected_sha256'] == expected, 'recovery archive binding mismatch: ' + name)
                require(found[name]['actual_sha256'] == expected, 'recovery archive actual mismatch: ' + name)
            checked = 0
            for item in index['recoverable_inputs']:
                for member in item.get('members', []):
                    if Path(member['archive']).name in ARCHIVES:
                        rel = member['member'][len(WRAPPER):]
                        require(member['expected_sha256'] == sha(self.data[rel]), 'recovery member mismatch: ' + rel)
                        checked += 1
            self.recovery = {'filename': recovery.name, 'sha256': sha(payload), 'passive_member_bindings_checked': checked}

    def read(self, rel):
        self.used.add(rel)
        return self.data[rel]

    def json(self, rel):
        return json.loads(self.read(rel))

    def npz(self, rel):
        with np.load(io.BytesIO(self.read(rel)), allow_pickle=False) as data:
            return {k: data[k] for k in data.files}

    def bind(self, prefix, file, key):
        obj = self.json(prefix + file)
        for name, expected in obj[key].items():
            require(sha(self.data[prefix + name]) == expected, 'sealed binding mismatch: ' + prefix + name)
        return obj


def analyze_cell(inputs, plan, case, resolution):
    cid = case['id'] + '-' + resolution
    prefix = NEW + 'outputs/' + cid + '/'
    seal = inputs.bind(prefix, 'RUN-SEAL.json', 'files')
    started = inputs.json(prefix + 'STARTED.json')
    summary = inputs.json(prefix + 'SUMMARY.json')
    require(inputs.json(prefix + 'REJECTED-EVALUATION.json') is None, 'non-null rejection: ' + cid)
    identity = seal['identity']
    require(identity['case'] == case and identity['resolution_id'] == resolution, 'case identity mismatch')
    require(identity['version'] == plan['model_version'], 'version mismatch')
    require(identity['settings'] == plan['resolutions'][resolution] == summary['settings'], 'settings mismatch')
    require(identity['plan_seal_sha256'] == sha(inputs.data[NEW + 'PLAN-SEAL.json']), 'run plan-seal mismatch')
    require(identity['equilibrium_sha256'] == sha(inputs.data[NEW + 'outputs/EQUILIBRIUM-PREFLIGHT.json']), 'equilibrium binding mismatch')
    require(all(started[k] == v for k, v in identity.items()), 'STARTED identity mismatch')
    require(summary['status'] == 'TRAJECTORY_CHECKS_PASS' and summary['exception'] is None, 'incomplete historical trajectory')
    arrays = inputs.npz(prefix + 'raw.npz')
    require(all(np.isfinite(a).all() for a in arrays.values()), 'nonfinite raw values')
    sample, accepted, quad, ledger = [arrays[k] for k in ['sample', 'accepted', 'quadrature', 'ledger']]
    segments = inputs.json(prefix + 'DENSE-SEGMENTS.json')
    n = len(segments)
    t0 = np.array([s['t0'] for s in segments])
    t1 = np.array([s['t1'] for s in segments])
    y0 = np.array([s['y0'] for s in segments])
    coeff = np.array([s['polynomial_coefficients'] for s in segments])
    h = t1 - t0
    require(t0[0] == 0 and t1[-1] == 4 and np.array_equal(t1[:-1], t0[1:]) and np.all(h > 0), 'dense coverage mismatch')
    require(np.array_equal(sample[:, 0], np.linspace(0, 4, 4001)), 'common grid mismatch')
    require(accepted.shape == (n+1, 9) and quad.shape == (3*n, 38) and ledger.shape == (3*n, 12), 'array shape mismatch')
    require(accepted[-1, 0] == summary['last_accepted_t_s'] == 4, 'end time mismatch')
    require(np.array_equal(accepted[-1, 1:], summary['final_state']), 'final state mismatch')
    require(np.array_equal(accepted[:, 0], np.r_[0, t1]), 'accepted times mismatch')
    init = plan['initial_state']
    require(np.array_equal(accepted[0, 1:], [init['q0_m'], init['qdot0_m_s'], init['Q0_C'], init['Vstorage0_V'], 0, 0, 0, 0]), 'initial state mismatch')
    # Evaluate saved cubic coefficients; this is interpolation of recorded data, not time integration.
    xs = np.array([0, .5, 1.])
    states = (y0[:, None, :] + np.einsum('nsd,kd->nks', coeff, np.array([xs, xs**2, xs**3]).T)).reshape(-1, 8)
    times = np.column_stack((t0, t0 + h/2, t1)).ravel()
    same_numeric(times, quad[:, 0], 'quadrature timestamps')
    same_numeric(times, ledger[:, 0], 'ledger timestamps')
    same_numeric(states[::3], accepted[:-1, 1:], 'accepted left states')
    same_numeric(states[2::3], accepted[1:, 1:], 'accepted right states')
    idx = np.minimum(np.searchsorted(t1, sample[:, 0], side='left'), n-1)
    x = (sample[:, 0] - t0[idx]) / h[idx]
    sampled = y0[idx] + np.einsum('nsd,nd->ns', coeff[idx], np.column_stack((x, x*x, x*x*x)))
    sample_delta = same_numeric(sampled, sample[:, 1:], 'common-grid states')
    m = plan['mechanics']; mass, k, theta, cp = [m[f] for f in ['mass_kg', 'k_N_m', 'theta_C_m', 'Cp_ritz_F']]
    cin = case['cin_F']; R = plan['rectifier']['series_resistance_ohm']
    damping = 2 * plan['damping_ratio'] * np.sqrt(mass*k)
    q, qdot, charge, vs = states[:, :4].T
    vp = (charge - theta*q)/cp
    primitive_delta = same_numeric(np.column_stack((q, qdot, vp, vs)), quad[:, [1, 30, 31, 32]], 'saved kinematic/electrical primitives')
    current = np.maximum(np.abs(vp) - vs, 0)/R
    same_numeric(current, quad[:, 33], 'bridge current')
    ptrans = np.sum(quad[:, 8:11] * quad[:, 26:29], axis=1) * quad[:, 29]
    prot = -quad[:, 15] * quad[:, 29]
    powers = np.column_stack((damping*qdot*qdot, R*current*current, ptrans, prot))
    power_delta = same_numeric(powers, quad[:, [36,37,34,35]], 'power primitives')
    port_power_error = maxabs(vp*np.sign(vp)*current - vs*current - R*current*current)
    stored = np.column_stack((.5*mass*qdot*qdot, .5*k*q*q, .5*cp*vp*vp, .5*cin*vs*vs, quad[:, 4]))
    energy_delta = same_numeric(stored, ledger[:, 1:6], 'stored-energy decomposition')
    same_numeric(states[:, 4:], ledger[:, 6:10], 'recorded work/loss integrals')
    initial = stored[0]; final = stored[-1]
    # Use the frozen signed mutual potential, without an invented positive offset.
    balance = stored.sum(axis=1)-initial.sum()+states[:,4]+states[:,5]-states[:,6]-states[:,7]
    scale = np.maximum.reduce((np.full(len(states), initial[:4].sum()), np.abs(states[:,6]+states[:,7]), np.abs(stored[:,4]-initial[4]), np.full(len(states), 1e-9)))
    same_numeric(balance, ledger[:,10], 'energy balance')
    same_numeric(scale, ledger[:,11], 'energy normalization')
    gates = plan['gates']
    energy_threshold = gates['energy_abs_J'] + gates['energy_relative']*scale
    energy_pass = bool(np.all(np.abs(balance) <= energy_threshold))
    triples = powers.reshape(n, 3, 4)
    increments = h[:,None]*(triples[:,0] + 4*triples[:,1] + triples[:,2])/6
    simpson = increments.sum(axis=0)
    ode = accepted[-1, 5:9]
    simpson_threshold = gates['independent_ledger_abs_J'] + gates['independent_ledger_relative']*np.maximum(np.abs(simpson), 1e-9)
    simpson_pass = bool(np.all(np.abs(simpson-ode) <= simpson_threshold))
    cumulative = np.cumsum(increments, axis=0)
    independent_balance = stored[2::3].sum(axis=1)-initial.sum()+cumulative[:,0]+cumulative[:,1]-cumulative[:,2]-cumulative[:,3]
    # Original 6/10-order empirical refinement gates, using the saved evaluations only.
    qchecks = {}
    for name, a, b in [('force_N',2,3),('potential_J',4,5),('driver_derivative_J_per_rad',6,7)]:
        at, rt = gates['quadrature'][name]
        delta = np.abs(quad[:,a]-quad[:,b]); threshold = at+rt*np.abs(quad[:,b])
        qchecks[name] = {'max_abs_delta': float(delta.max()), 'max_delta_over_threshold': float(np.max(delta/threshold)), 'pass': bool(np.all(delta <= threshold))}
    # Dense extrema are necessary for the predeclared peak-Vs effect, not grid-only maxima.
    extrema = {'q_min_m': float('inf'), 'q_max_m': -float('inf'), 'Vp_min_V': float('inf'), 'Vp_max_V': -float('inf'), 'Vs_min_V': float('inf'), 'Vs_peak_V': -float('inf')}
    for y, c in zip(y0, coeff):
        for lo_name, hi_name, poly in [('q_min_m','q_max_m',np.r_[y[0],c[0]]), ('Vp_min_V','Vp_max_V',(np.r_[y[2],c[2]]-theta*np.r_[y[0],c[0]])/cp), ('Vs_min_V','Vs_peak_V',np.r_[y[3],c[3]])]:
            lo, hi = limits(poly); extrema[lo_name] = min(extrema[lo_name],lo); extrema[hi_name] = max(extrema[hi_name],hi)
    for name, value in summary['maxima'].items():
        same_numeric(extrema[name], value, 'dense extrema '+name)
    domain_pass = max(abs(extrema['q_min_m']),abs(extrema['q_max_m'])) <= gates['q_limit_m'] and extrema['Vs_min_V'] >= -gates['storage_negative_tolerance_V'] and max(abs(extrema['Vp_min_V']),abs(extrema['Vp_max_V']),extrema['Vs_peak_V']) <= gates['voltage_computational_guard_V']
    # Event-aware accumulation: exact 2 s split; never integrate a chord across its power jump.
    event = plan['driver_input']['opening_s']
    require(not np.any((t0 < event) & (t1 > event)), 'interval crosses driver event')
    left = np.flatnonzero(t1 == event); right = np.flatnonzero(t0 == event)
    require(len(left) == len(right) == 1, 'missing unique two-sided driver event')
    il, ir = int(left[0]), int(right[0])
    require(ir == il+1, 'noncontiguous driver event')
    left_row, right_row = 3*il+2, 3*ir
    event_state_delta = same_numeric(states[left_row], states[right_row], 'event continuous state')
    omega = plan['driver_input']['opening_angle_rad']/event
    require(np.all(quad.reshape(n,3,38)[t1 <= event,:,29] == omega), 'opening angular speed mismatch')
    require(np.all(quad.reshape(n,3,38)[t0 >= event,:,29] == 0), 'hold angular speed mismatch')
    event_report = {
        't_s': event, 'state_continuity_max_abs_delta': event_state_delta,
        'left_driver_power_W': powers[left_row,2:].tolist(), 'right_driver_power_W': powers[right_row,2:].tolist(),
        'opening_0_to_2s_simpson_J': dict(zip(RATES, increments[t1 <= event].sum(axis=0).tolist())),
        'hold_2_to_4s_simpson_J': dict(zip(RATES, increments[t0 >= event].sum(axis=0).tolist())),
        'storage_energy_at_2s_J': float(stored[left_row,3]), 'storage_gain_2_to_4s_J': float(final[3]-stored[left_row,3]),
        'integration_rule': 'Per accepted interval Simpson on its retained start/mid/end; distinct left/right powers retained at 2 s. No integration across the jump.',
    }
    jac = inputs.json(prefix+'JACOBIAN-CHECKS.json'); jac_ratio = 0.
    for record in jac:
        hq = record['h_m']; raw = record['raw']
        require(len(raw) == 4 and hq > 0, 'invalid Jacobian retained samples')
        vals = np.array([[v['Fq_N'],v['Ptranslation_W'],v['Protation_W']] for v in raw])
        d1, d2 = (vals[1]-vals[0])/(2*hq), (vals[3]-vals[2])/hq
        same_numeric(d1, record['derivative_h'], 'Jacobian h reconstruction')
        same_numeric(d2, record['derivative_half_h'], 'Jacobian h/2 reconstruction')
        j = plan['jacobian']; threshold = np.array([j['force_derivative_abs_N_m'],j['driver_power_derivative_abs_W_m'],j['driver_power_derivative_abs_W_m']])+j['relative_derivative_tolerance']*np.abs(d2)
        same_numeric(threshold, record['thresholds'], 'Jacobian thresholds')
        jac_ratio = max(jac_ratio, float(np.max(np.abs(d1-d2)/threshold)))
    budget = plan['budgets']
    cost = {key: summary[key] for key in ['accepted_steps','rhs_evaluations','force_evaluations','jacobian_evaluations','wall_s']}
    require(cost['accepted_steps'] == n and cost['jacobian_evaluations'] == len(jac), 'historical count mismatch')
    budget_pass = n <= budget['accepted_steps_per_trajectory'] and cost['rhs_evaluations'] <= budget['rhs_per_trajectory'] and cost['force_evaluations'] <= budget['force_evaluations_per_trajectory'] and cost['wall_s'] <= budget['wall_per_trajectory_s'] and len(jac) <= plan['jacobian']['maximum_jacobian_evaluations']
    checks_pass = energy_pass and simpson_pass and domain_pass and jac_ratio <= 1 and budget_pass and all(x['pass'] for x in qchecks.values())
    return {
        'case': case, 'resolution': resolution, 'role': '47 uF control' if case['id']=='cin47' else '10 uF conditional comparison candidate',
        'scoped_checks_pass': bool(checks_pass), 'end_time_s': float(accepted[-1,0]),
        'final_Vs_V': float(accepted[-1,4]), 'final_storage_J': float(.5*cin*accepted[-1,4]**2),
        'dense_extrema': extrema, 'initial_components_J': dict(zip(ENERGIES,initial.tolist())), 'final_components_J': dict(zip(ENERGIES,final.tolist())),
        'ode_work_and_losses_J': dict(zip(RATES,ode.tolist())),
        'energy_closure': {'formula':'E(t)-E(0)+Dmechanical+Dresistor-Wtranslation-Wrotation', 'maximum_abs_residual_J':maxabs(balance), 'final_residual_J':float(balance[-1]), 'max_residual_over_frozen_threshold':float(np.max(np.abs(balance)/energy_threshold)), 'frozen_gate_pass':energy_pass, 'initial_runtime_n6_minus_static_n10_U_J':float(initial[4]-init['initial_mutual_magnetic_J'])},
        'independent_saved_primitive_simpson': {'work_and_losses_J':dict(zip(RATES,simpson.tolist())), 'minus_ode_J':dict(zip(RATES,(simpson-ode).tolist())), 'frozen_threshold_J':dict(zip(RATES,simpson_threshold.tolist())), 'frozen_gate_pass':simpson_pass, 'final_balance_residual_J':float(independent_balance[-1]), 'max_endpoint_balance_residual_J_descriptive_only':maxabs(independent_balance)},
        'power_identity_max_abs_error_W':port_power_error, 'driver_power_min_W':powers[:,2:].min(axis=0).tolist(),
        'quadrature_refinement':qchecks, 'dense_voltage_and_q_guards_pass':bool(domain_pass),
        'jacobian_readback':{'records':len(jac),'max_delta_over_frozen_threshold':jac_ratio,'pass':jac_ratio <= 1},
        'event_2s':event_report, 'historical_execution_cost':cost, 'historical_budget_pass':bool(budget_pass),
        'recorded_minimum_clearance_lower_bound_m_not_recomputed':float(arrays['domain'][:,-1].min()),
        'readback_max_abs_deltas':{'sample':sample_delta,'kinematic_electrical_primitives':primitive_delta,'powers':power_delta,'stored_energy':energy_delta},
        'data_counts':{'accepted_intervals':n,'common_grid_points':len(sample),'primitive_rows':len(quad)},
    }, sample


def main(args):
    inputs = Inputs(args.archive_dir, args.recovery_index)
    plan = inputs.json(NEW+'PLAN.json')
    require(sha(inputs.data[NEW+'PLAN.json']) == NEW_PLAN_SHA, 'frozen plan SHA mismatch')
    inputs.bind(NEW, 'PLAN-SEAL.json', 'bindings')
    baseline = inputs.json(OLD+'PLAN.json')
    differences = sorted(k for k in set(plan)|set(baseline) if plan.get(k) != baseline.get(k))
    require(differences == ['authorization_status','implementation_revision','jacobian','model_version'], 'physical parameters or gates changed')
    old = inputs.json(OLD+'STOPPED-STUDY-RECEIPT.json')
    inputs.bind(OLD+'outputs/cin47-coarse/', 'RUN-SEAL.json', 'files')
    old_summary = inputs.json(OLD+'outputs/cin47-coarse/SUMMARY.json')
    old_raw = inputs.npz(OLD+'outputs/cin47-coarse/raw.npz')
    require(old_raw['accepted'][-1,0] == old_summary['last_accepted_t_s'] == old['last_accepted_t_s'], 'old stop-time mismatch')
    require(old['scientific_trajectories_attempted'] == 1 and old['scientific_trajectories_completed'] == 0 and len(old['unrun']) == 3, 'original cohort mismatch')
    require(all(not any(k.startswith(OLD+'outputs/'+c+'/') for k in inputs.data) for c in old['unrun']), 'fabricated original unrun outputs')
    cells, samples = {}, {}
    for case in plan['cases']:
        for res in ['coarse','fine']:
            cid=case['id']+'-'+res
            cells[cid],samples[cid] = analyze_cell(inputs, plan, case, res)
    convergence = {}
    for case in plan['cases']:
        cid=case['id']; a,b=samples[cid+'-coarse'],samples[cid+'-fine']; ca,cb=cells[cid+'-coarse'],cells[cid+'-fine']
        theta=plan['mechanics']['theta_C_m']; cp=plan['mechanics']['Cp_ritz_F']; checks={}
        for name,x,y in [('q_m',a[:,1],b[:,1]),('Vs_V',a[:,4],b[:,4]),('Vp_V',(a[:,3]-theta*a[:,1])/cp,(b[:,3]-theta*b[:,1])/cp)]:
            at,rt=plan['gates']['time_refinement'][name]; d=maxabs(x-y); threshold=at+rt*maxabs(y)
            checks[name]={'sup_abs_delta':d,'threshold':threshold,'pass':d <= threshold}
        values=[('final_storage_J',ca['final_storage_J'],cb['final_storage_J'],'energy_J'),('maxima.Vs_peak_V',ca['dense_extrema']['Vs_peak_V'],cb['dense_extrema']['Vs_peak_V'],'Vs_V')]
        values += [(f,ca['ode_work_and_losses_J'][f],cb['ode_work_and_losses_J'][f],'energy_J') for f in RATES]
        for name,x,y,gate in values:
            at,rt=plan['gates']['time_refinement'][gate]; d=abs(y-x); threshold=at+rt*abs(y)
            checks[name]={'abs_delta':d,'threshold':threshold,'pass':d <= threshold}
        convergence[cid]=checks
    published=inputs.json(NEW+'outputs/COMPARISON.json')
    for cid, checks in convergence.items():
        for name, item in checks.items():
            for key, value in item.items():
                same_numeric(value,published['gates'][cid][name][key],f'published convergence {cid}/{name}/{key}')
    convergence_pass=all(c['pass'] for row in convergence.values() for c in row.values())
    effects={}
    fine47,fine10=cells['cin47-fine'],cells['cin10-fine']
    for metric,v47,v10 in [('final_storage_J',fine47['final_storage_J'],fine10['final_storage_J']),('maxima.Vs_peak_V',fine47['dense_extrema']['Vs_peak_V'],fine10['dense_extrema']['Vs_peak_V'])]:
        effect=v10-v47; delta=sum(convergence[c][metric]['abs_delta'] for c in convergence)
        rule=abs(effect)>5*delta
        effects[metric]={'cin10_minus_cin47':effect,'coarse_fine_delta_sum':delta,'five_times_observed_delta':5*delta,'effect_exceeds_five_times_observed_resolution_delta':rule,'resolved_difference_admitted':bool(rule and convergence_pass and all(c['scoped_checks_pass'] for c in cells.values())),'empirical_only_not_error_bound':True}
        for k in ['cin10_minus_cin47','coarse_fine_delta_sum']:
            same_numeric(effects[metric][k],published['effects'][metric][k],'published effect '+metric+'/'+k)
    delta_work={k:fine10['ode_work_and_losses_J'][k]-fine47['ode_work_and_losses_J'][k] for k in RATES}
    delta_final={k:fine10['final_components_J'][k]-fine47['final_components_J'][k] for k in ENERGIES}
    source=inputs.json(NEW+'FINAL-RECEIPT.json')
    require(source['totals_across_versions'] == {'attempted':5,'completed':4,'stopped':1}, 'historical final receipt mismatch')
    cost={k:sum(c['historical_execution_cost'][k] for c in cells.values()) for k in ['accepted_steps','rhs_evaluations','force_evaluations','jacobian_evaluations','wall_s']}
    require(cost['wall_s'] <= plan['budgets']['total_wall_cap_s'], 'historical total wall exceeds frozen budget')
    result={
        'schema':'bf-retained-passive-reanalysis-v1',
        'status':'SCOPED_RETAINED_DATA_CHECKS_PASS' if convergence_pass and all(c['scoped_checks_pass'] for c in cells.values()) else 'SCOPED_RETAINED_DATA_CHECKS_FAIL',
        'analysis_kind':'Independent arithmetic reconstruction of previously retained data; no new trajectory or physical validation',
        'execution':{'new_trajectories':0,'new_equilibrium_solves':0,'new_force_or_provider_evaluations':0,'network_calls':0,'source_files_modified':0,'script_sha256':sha(Path(__file__).read_bytes()),'python':platform.python_version(),'numpy':np.__version__},
        'input_integrity':{'archives':inputs.archives,'package_manifest_sha256':MANIFEST_SHA,'all_manifest_entries_verified':inputs.manifest_count,'frozen_plan_sha256':NEW_PLAN_SHA,'plan_seal_sha256':sha(inputs.data[NEW+'PLAN-SEAL.json']),'recovery_index':inputs.recovery,'old_to_new_changed_top_level_fields':differences},
        'provenance':{'original_version':baseline['model_version'],'repaired_version':plan['model_version'],'original':{'attempted':1,'completed':0,'stopped':1,'unrun':old['unrun'],'last_accepted_t_s':old['last_accepted_t_s'],'exact_rejected_voltage':'not retained; unknown','comparison_admitted':False},'repaired':{'attempted':4,'completed':4,'stopped':0,'unrun':0},'totals':source['totals_across_versions'],'note':'The four repaired executions never replace the stopped original or populate its three unrun slots.'},
        'frozen_scientific_thresholds':plan['gates'],'frozen_effect_rule':plan['interpretation_rule'],
        'data_readback_tolerance':{'rtol':1e-11,'atol':1e-13,'scope':'Only floating arithmetic cross-checks; never a substituted scientific threshold'},
        'cells':cells,'time_refinement':convergence,'time_refinement_gate_count':sum(map(len,convergence.values())),'time_refinement_all_pass':convergence_pass,'effects':effects,
        'fine_comparison':{'final_Vs_ratio_10_over_47':fine10['final_Vs_V']/fine47['final_Vs_V'],'storage_ratio_10_over_47':fine10['final_storage_J']/fine47['final_storage_J'],'common_grid_q_sup_abs_difference_m':maxabs(samples['cin10-fine'][:,1]-samples['cin47-fine'][:,1]),'cin10_minus_cin47_work_and_loss_J':delta_work,'cin10_minus_cin47_final_energy_components_J':delta_final,'driver_total_work_difference_J':delta_work[RATES[2]]+delta_work[RATES[3]],'interpretation':'Same prescribed angle/time profile and initial state, but coupled dynamics change magnetic driver work and losses. The storage gain is an energy-partition result, not equal-input-work efficiency or energy creation.'},
        'historical_repaired_execution_cost_totals':cost,
        'scope_limits':['No magnetic source implementation imported or re-evaluated; n6/n10 evidence is same-source numerical refinement.', 'Magnet clearance column is integrity-verified and reported, not geometrically recomputed by this bounded script.', 'No new proof of material/tensor/ROM applicability, calibrated damping, omitted axial or modal physics, initialization/reset cost, PMIC startup, hardware feasibility or Agent benefit.', 'Simpson cumulative endpoint residual is descriptive; the frozen independent-ledger gate applies to final individual work/loss integrals.', '47 uF remains control; 10 uF is one conditional comparison candidate. No optimum, scan or threshold retuning.'],
        'conclusions_zh':['原归档和清单校验通过；四条修订轨迹的冻结能量、步长收敛和两项效果规则可由保存数据重算。','细步 10−47 µF 储能差为 +1.275079646 µJ；这是固定条件模型的储能电容敏感性，不是统计显著性或物理可行性。','2 s 驱动停止点保留左右单侧功率，逐接受区间积分；相同角度轨迹不等于相同外部磁驱动功。','原版 1 条中断和 3 个未运行槽位保持原身份，修订版 4 条完成，总实际尝试数仍为 5。'],
    }
    result['input_mapping']={name:inputs.locations[name] for name in sorted(inputs.used)}
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-dir',type=Path,required=True,help='Directory containing the three untouched original archives')
    parser.add_argument('--recovery-index',type=Path,help='Optional original RECOVERY-INDEX.json for an additional provenance cross-check')
    parser.add_argument('--out',type=Path,required=True,help='New JSON output path, never an original evidence file')
    args=parser.parse_args()
    if args.out.resolve().is_relative_to(args.archive_dir.resolve()) or (args.recovery_index and args.out.resolve() == args.recovery_index.resolve()):
        parser.error('Output must be outside the immutable archive directory and must not replace RECOVERY-INDEX.json')
    if os.path.lexists(args.out):
        parser.error('Output must be a new path; refusing an existing file, directory, symlink or hardlink')
    try:
        result=main(args)
    except Exception as exc:
        result={'schema':'bf-retained-passive-reanalysis-v1','status':'BLOCKED_OR_FAILED','error_type':type(exc).__name__,'error':str(exc),'claim':'No passing result is admitted; input or arithmetic evidence is missing/inconsistent.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    try:
        # Exclusive creation is the final safety check, including races after lexists.
        # Mode x refuses ordinary files, hardlinks and even dangling symlinks.
        with args.out.open('x', encoding='utf-8') as output:
            output.write(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    except FileExistsError:
        parser.error('Output appeared during analysis; refusing to overwrite any existing file or link')
    print(json.dumps({'status':result['status'],'output':str(args.out),'effects':result.get('effects',{})},ensure_ascii=False))
    sys.exit(0 if result['status']=='SCOPED_RETAINED_DATA_CHECKS_PASS' else 1)
