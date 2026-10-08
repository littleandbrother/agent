"""D5 task-level constraints and public nominal event evaluation."""
from ..simulation_chain.contracts import digest
from .contracts import verify_design


def fields(design):
    value = {group + '.' + key: val for group in ('mechanical', 'circuit', 'firmware')
             for key, val in design['base_design'][group].items()}
    value.update({group + '.' + key: val for group in ('extraction', 'application')
                  for key, val in design[group].items()})
    value['gate'] = design['gate']
    value['gate_switch'] = design.get('gate_switch','BSS84')
    return value


def check_candidate(binding, parameters):
    task = binding['task']
    if digest(task) != binding['task_hash']:
        raise ValueError('SIMULATION_TASK_HASH_MISMATCH')
    if parameters.get('confirmation') is not True:
        raise ValueError('TASK_CONFIRMATION_REQUIRED')
    design = verify_design(parameters['candidate'])
    if design['base_design']['frozen'] != task['frozen']:
        raise ValueError('SELFPOWER_TASK_FROZEN_MISMATCH')
    baseline = fields(task['baseline'])
    for key, value in fields(design).items():
        rule = task['allowed_design_variables'].get(key)
        if rule is None and value != baseline[key]:
            raise ValueError('TASK_PROTECTED_FIELD:' + key)
        if rule and 'values' in rule and value not in rule['values']:
            raise ValueError('TASK_DESIGN_VALUE:' + key)
        if rule and 'range' in rule and not rule['range'][0] <= value <= rule['range'][1]:
            raise ValueError('TASK_DESIGN_RANGE:' + key)
    return design


def evaluate(binding, design, result, receiver):
    violations = []
    try: check_candidate(binding, {'candidate': design, 'confirmation': True})
    except (ValueError, KeyError, TypeError) as exc: violations.append(str(exc))
    task = binding['task']
    expected_rating=task.get('rating_protocol','legacy-series-proxy-v1')
    if result.get('rating_protocol','legacy-series-proxy-v1') != expected_rating:
        violations.append('SELFPOWER_RATING_PROTOCOL_MISMATCH')
    missing = [k for k in task['required_checks'] if result.get('checks', {}).get(k) is not True]
    completed = result.get('run_status') == 'completed' and result.get('source_stable') is True
    transmitted = {(e.get('capture_id'), e.get('time_s'), e.get('payload_hex'))
                   for e in receiver.get('transmitted', [])}
    valid = [e for e in receiver.get('delivered', [])
             if (e.get('capture_id'), e.get('time_s'), e.get('payload_hex')) in transmitted
             and type(e.get('time_s')) in (int, float)
             and 0 <= e['time_s'] <= task['service']['deadline_s']
             and e.get('payload_hex') == task['service']['expected_payload_hex']]
    eligible = not violations and completed and not missing
    satisfied = bool(valid) and result.get('metrics', {}).get('cold_start_reached') is True
    return {'schema_version': 'simulation-task-evaluation-v1', 'task_id': task['id'],
            'task_hash': binding['task_hash'], 'candidate_hash': digest(design),
            'input_violations': violations, 'run_status': result.get('run_status'),
            'diagnostic_only': False, 'pilot_observation_eligible': not violations,
            'nominal_prediction_eligible': eligible,
            'nominal_task_status': ('satisfied' if satisfied else 'unsatisfied') if eligible else 'not_evaluable',
            'prediction_comparison_scope': 'D5 declared nominal model only; not physically qualified ranking',
            'design_ranking_eligible': False, 'unpassed_numerical_checks': missing,
            'unpassed_physical_checks': ['full_rotating_FEM_domain', 'device_temperature_pulse_SOA', 'hardware_load_calibration'],
            'timely_correct_packets': len(valid), 'first_correct_packet_s': min((e['time_s'] for e in valid), default=None),
            'silence_groups': len(receiver.get('events', [])), 'exactly_once_semantics_qualified': False,
            'product_verified': False, 'hardware_calibrated': False, 'scope': task['claim_boundary']}
