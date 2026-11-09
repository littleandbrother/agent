"""One prospective analytic qualification; no apparatus import or execution.

Read the frozen Task/prospective inputs, derive passive source-voltage bounds,
and write A-QUALIFICATION.json once. This does not find a service solution.
"""
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def main():
    destination = HERE / 'A-QUALIFICATION.json'
    if destination.exists():
        raise SystemExit('QUALIFICATION_ALREADY_RECORDED; do not reevaluate or retune')
    available_before = shutil.disk_usage(HERE).free
    assert available_before >= 10_005_000_000
    task_path = HERE / 'Task-proposal.json'
    prospective_path = HERE / 'A-PROSPECTIVE.json'
    task = json.loads(task_path.read_text())
    prospective = json.loads(prospective_path.read_text())
    assert identity(task) == prospective['task_proposal_identity']
    assert identity(task['initial_design']) == prospective['initial_design_sha256']
    assert identity(task['initial_problem']) == prospective['initial_problem_sha256']
    assert identity(task['motion']) == prospective['motion_sha256']
    default = prospective['source_model_constants']['DEFAULT_MECHANISM']
    domain = prospective['source_model_constants']['DOMAIN']
    design = task['initial_design']
    problem = task['initial_problem']
    assert problem['fixed_choices'] == {'mechanism': {}, 'startup_v': 2.2}
    assert design['mechanism'] == {}
    assert set(problem['active_variables']) == set(task['design_domain']) - {'mechanism', 'startup_v'}
    assert task['initial']['mechanical_stored_j'] == task['initial']['capacitor_v'] == 0

    # All four linear segments span 0..90 degrees, including the exact peak.
    # No-motion intervals have omega=0; there is no additional source maximum.
    segments = []
    for segment in task['motion']:
        lo, hi = sorted((segment['start_deg'], segment['end_deg']))
        assert lo == 0 and hi == 90
        omega_deg = (segment['end_deg'] - segment['start_deg']) / (segment['end_s'] - segment['start_s'])
        assert abs(omega_deg) <= domain['maximum_speed_deg_s']
        omega = math.radians(omega_deg)
        peak_time = segment['start_s'] + (45 - segment['start_deg']) / omega_deg
        segments.append({**segment, 'omega_deg_per_s': omega_deg,
                         'omega_rad_per_s': omega, 'max_abs_sin_2theta': 1.0,
                         'peak_theta_rad': math.pi / 4, 'peak_time_s': peak_time})
    omega_peak = max(abs(s['omega_rad_per_s']) for s in segments)
    k = default['generator_constant_vs_per_m']
    rectifier = default['rectifier_drop_v']
    initial_v = task['initial']['capacitor_v']
    current_emf = k * default['stroke_m'] * omega_peak
    current_u = max(initial_v, 0.0, current_emf - rectifier)
    startup = problem['fixed_choices']['startup_v']
    guard = prospective['rule']['numeric_comparison_guard_v']
    current_margin = startup - current_u

    # Intersect the hard Task permission box with every geometry inequality.
    # The 2 mm radial rim contributes to r+L <= W/2 - 0.002.
    l_min, l_max = task['design_domain']['mechanism']['editable']['stroke_m']
    r_min, r_max = task['design_domain']['mechanism']['editable']['cam_base_radius_m']
    rim = 0.002
    radius_budget = domain['envelope_width_m'] / 2 - rim
    pressure_tan = math.tan(math.radians(domain['maximum_pressure_angle_deg']))
    a = (math.sqrt(1 + 4 / pressure_tan**2) - 1) / 2
    # Pressure condition: L/sqrt(r(r+L))<=tan(40deg) iff r>=a*L.
    upper_stroke_constraints = {
        'hard_Task_stroke_max_m': l_max,
        'minimum_base_and_width_m': radius_budget - r_min,
        'pressure_and_maximum_base_m': r_max / a,
        'pressure_and_width_m': radius_budget / (1 + a),
        'generator_travel_envelope_m': domain['envelope_length_m'] - 0.044,
        'broad_source_coefficient_stroke_max_m': 0.020,
    }
    l_sup = min(upper_stroke_constraints.values())
    assert l_sup >= l_min
    base_interval = [max(r_min, a * l_sup), min(r_max, radius_budget - l_sup)]
    assert base_interval[0] <= base_interval[1]
    # Analytic geometric support point only; not a coupled or service candidate.
    # Use the existing default base when within the supported interval.
    support_base = min(max(default['cam_base_radius_m'], base_interval[0]), base_interval[1])
    support_geometry = {
        'stroke_m': l_sup, 'cam_base_radius_m': support_base,
        'cam_diameter_m': 2 * (support_base + l_sup + rim),
        'generator_travel_envelope_m': [0.044 + l_sup, 0.028, 0.014],
        'assembly_depth_m': 0.003 + 0.001 + 0.014 + 0.002,
        'maximum_pressure_angle_deg': math.degrees(math.atan(l_sup / math.sqrt(support_base * (support_base + l_sup)))),
    }
    geometry_valid = (support_geometry['cam_diameter_m'] <= domain['envelope_width_m'] + 1e-12
                      and support_geometry['generator_travel_envelope_m'][0] <= domain['envelope_length_m'] + 1e-12
                      and support_geometry['assembly_depth_m'] <= domain['envelope_depth_m'] + 1e-12
                      and support_geometry['maximum_pressure_angle_deg'] <= domain['maximum_pressure_angle_deg'])
    assert geometry_valid
    global_emf = k * l_sup * omega_peak
    global_u = max(initial_v, 0.0, global_emf - rectifier)
    minimum_startup = task['design_domain']['startup_v']['min']
    assert task['design_domain']['brownout_v']['min'] < minimum_startup <= task['components']['max_v']
    global_margin = global_u - minimum_startup
    if current_margin <= guard:
        status = 'STOP_CURRENT_P_NOT_EXCLUDED'
    elif global_margin < -guard:
        status = 'STOP_GLOBAL_STARTUP_NO_GO'
    elif global_margin > guard:
        status = 'QUALIFIED_CURRENT_P_EXCLUDED_GLOBAL_UNKNOWN'
    else:
        status = 'STOP_BOUNDARY_UNRESOLVED'

    binding = {
        'task_id': task['task_id'], 'frozen_proposal_sha256': identity(task),
        'initial_design_sha256': identity(design), 'initial_problem_sha256': identity(problem),
        'motion_sha256': identity(task['motion']),
        'binding_scope': 'Frozen initial Design/P and prescribed trajectory; not a recomputed bound for later edited inputs.',
    }
    assumptions = prospective['assumptions']
    public_facts = {
        'schema_version': 'pqe-source-envelope-facts-v1',
        'origin': 'DEVELOPER_PROVIDED_ANALYTIC_NECESSARY_BOUND_BEFORE_DYNAMIC_RESULTS',
        'binding': binding,
        'formula': 'U=max(V_initial,0,sup_t abs(K*L*sin(2*theta(t))*omega(t))-V_rect)',
        'units': {'theta': 'rad', 'omega': 'rad/s', 'L': 'm', 'K': 'V*s/m', 'U': 'V'},
        'assumptions': assumptions,
        'passive_barrier_argument': 'For Vcap above this envelope, the blocking rectifier supplies zero current. C*dVcap/dt equals source current minus nonnegative leakage/load, so positive capacitance cannot cross the envelope from below. Clamps and passive branch losses cannot raise it.',
        'motion_coverage': {'linear_segments': 4, 'all_segments_include_theta_pi_over_4': True,
                            'maximum_absolute_omega_rad_per_s': omega_peak,
                            'complete_linear_segment_peak_rule': 'abs(sin(2*theta))<=1 with equality at theta=pi/4 in each segment; omega=0 in every remaining interval.'},
        'current_problem_bound': {
            'fixed_choices': problem['fixed_choices'],
            'resolved_source_parameters': default,
            'source_emf_sup_v': current_emf, 'capacitor_upper_bound_v': current_u,
            'fixed_startup_v': startup, 'startup_minus_upper_bound_v': current_margin,
            'classification': 'CURRENT_P_FIRST_STARTUP_EXCLUDED' if current_margin > guard else 'NOT_EXCLUDED',
            'scope': 'Current fixed mechanism and startup threshold, same motion and initial state, all legal active passive storage/load/program choices.',
        },
        'complete_legal_domain_optimistic_bound': {
            'mechanism_permissions': task['design_domain']['mechanism'],
            'geometry_constraints': ['0.006<=L<=0.0085 m; 0.006<=r<=0.008 m',
                                     '2*(r+L+0.002)<=0.035 m', '0.044+L<=0.060 m',
                                     'assembly_depth=0.020 m<=0.020 m',
                                     'atan(L/sqrt(r*(r+L)))<=40 deg'],
            'maximum_geometrically_admissible_stroke_m': l_sup,
            'source_emf_optimistic_upper_bound_v': global_emf,
            'capacitor_optimistic_upper_bound_v': global_u,
            'minimum_legal_startup_v': minimum_startup,
            'upper_bound_minus_minimum_startup_v': global_margin,
            'complete_service_feasibility': 'UNKNOWN',
            'interpretation': 'Failure of this optimistic bound to exclude startup does not establish charge time, powered boot, loaded TX, retained state, deadlines, or complete service feasibility.',
        },
        'numerical_comparison_guard_v': guard,
        'guard_scope': prospective['rule']['guard_scope'],
    }
    result = {
        'schema_version': 'pqe-m3-a-qualification-v1', 'package': prospective['package'],
        'feature': prospective['feature'], 'owner': 'campaign-a',
        'evaluated_at_utc': datetime.now(timezone.utc).isoformat(), 'status': status,
        'task_proposal_path': str(task_path), 'prospective_path': str(prospective_path),
        'binding': binding, 'complete_service_feasibility': 'UNKNOWN',
        'qualification_evaluations': 1, 'trajectory': segments,
        'current_P': public_facts['current_problem_bound'],
        'full_legal_geometry_derivation': {
            'rim_m': rim, 'radius_budget_after_rim_m': radius_budget,
            'pressure_base_per_stroke_lower_bound': a,
            'admissible_base_interval_formula': 'max(r_min,a*L)<=r<=min(r_max,0.035/2-0.002-L)',
            'stroke_upper_constraints_m': upper_stroke_constraints,
            'maximum_admissible_stroke_m': l_sup,
            'admissible_base_interval_at_maximum_stroke_m': base_interval,
            'geometric_support_point': support_geometry,
            'geometric_support_valid': geometry_valid,
            'support_scope': 'Host-only support for the geometric supremum, not a complete Design, service solution, or evaluated candidate.',
            'invalid_box_corner_excluded': {'stroke_m': l_max, 'base_radius_m': r_max,
                                             'cam_diameter_m': 2 * (r_max + l_max + rim),
                                             'width_limit_m': domain['envelope_width_m']},
            'geometry_tolerance_note': 'Uses exact declared envelope inequalities. The source accepts a 1e-12 m envelope slack; hard Task L_max remains the controlling stroke bound, so this slack cannot increase the reported supremum.',
        },
        'global_optimistic': public_facts['complete_legal_domain_optimistic_bound'],
        'public_inputs_append': {'source_envelope': public_facts},
        'registration_contract': 'S0 may append exactly public_inputs_append before registering Task. Frozen physical, motion, service, hard design domain and initial Design/P remain identical; this changes prospective metadata identity only. No post-result input selection is authorized.',
        'claim_boundary': [
            'Current-P first startup is excluded within the declared passive model, independently of capacitance tuning; this is a voltage-envelope argument, not average energy.',
            'Full legal geometric domain is not excluded by the optimistic source-voltage bound. Complete service remains UNKNOWN; no coupled repair was found or executed.',
            'Task-editable coefficients are only stroke and base radius; the broad source implementation coefficient box is not a permission to change K, Rcoil or rectifier.',
            'Source-envelope facts are prospectively given common public information. Their later use must not be described as Agent discovery of the bound.',
        ],
        'resources': {'available_before_bytes': available_before,
                      'estimated_peak_additional_bytes': 5_000_000, 'retained_output_cap_bytes': 1_000_000,
                      'output_directory': str(HERE), 'analytic_qualifications': 1,
                      'dynamic_executions': 0, 'provider_requests': 0, 'native_solver_runs': 0,
                      'parameter_scans': 0, 'complete_repair_candidates_solved': 0,
                      'new_environments': 0, 'new_backups': 0, 'workers': 0,
                      'available_after_bytes': shutil.disk_usage(HERE).free},
        'reproducible_command': "rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B '" + str(Path(__file__).resolve()) + "'",
        'rerun_policy': 'The command refuses to overwrite an existing qualification. Do not rerun during this package.',
        'handoff': 'S0 verifies qualification, appends the common public facts and registers Task, then owns at most one shared initial execution. A is idle until Task registration/materials or actual output readback is assigned.',
    }
    with destination.open('x') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': status, 'current_U_v': current_u, 'current_startup_v': startup,
                      'current_exclusion_margin_v': current_margin, 'global_U_v': global_u,
                      'minimum_legal_startup_v': minimum_startup, 'global_nonexclusion_margin_v': global_margin,
                      'geometrically_admissible_base_at_Lmax_m': base_interval,
                      'support_geometry': support_geometry, 'receipt': str(destination),
                      'receipt_sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
