"""Executable task semantics: bounds, consumers, identities and phase transitions.

Definitions are frozen inside existing System Commits. Historical v1 definitions
retain their original execution descriptors; no second controller is introduced.
"""
from copy import deepcopy
import json
import math

VERSION = 'bf-task-semantics-v1'
REFERENCE_RULES = {'source_relative_error_lt': .01, 'tip_displacement_length_ratio_max': .05,
    'charge_absolute_tolerance_c': 1e-10, 'charge_relative_tolerance': 1e-5,
    'energy_absolute_tolerance_j': 1e-6, 'energy_relative_tolerance': .01, 'negative_voltage_tolerance_v': 1e-6}
DESIGN_FIELDS = {
    'length_m': ('m', .02, .1), 'width_m': ('m', .002, .03),
    'substrate_m': ('m', .00005, .001), 'piezo_m': ('m', .00005, .001),
    'tip_mass_kg': ('kg', 0, .02), 'storage_f': ('F', .000001, .02)}
SCENARIO_UNITS = {'frequency_hz': 'Hz', 'initial_storage_v': 'V', 'rail_v': 'V',
    'storage_max_v': 'V', 'minimum_storage_v': 'V', 'duration_s': 's',
    'minimum_sample_s': 's', 'minimum_tx_s': 's', 'electrical_load_ohm': 'ohm',
    'acceleration_peak_m_s2': 'm/s2', 'damping_ratio': '1', 'conversion_efficiency': '1',
    'sensor_value': '1', 'state_currents_a': 'A', 'material': 'SI'}
CHECK_ONLY = {'minimum_storage_v', 'minimum_sample_s', 'minimum_tx_s', 'sensor_value'}
DISPLAY_ONLY = {'boundary', 'parameter_basis'}
FUNCTIONS = {'H': 'harvesting', 'P': 'power', 'S': 'sensing', 'C': 'compute',
             'R': 'radio', 'G': 'receiver', 'M': 'mechanical', 'B': 'board'}
INTERFACE_FAMILIES = {
    'mechanics-source': ['input_motion', 'mechanical_boundary', 'electrical_port', 'validity'],
    'source-power': ['voltage_current_relation', 'polarity', 'load_domain', 'initial_state'],
    'power-runtime': ['rail', 'startup', 'brownout', 'load_events', 'current_provenance'],
    'sensing-data': ['measurand', 'sampling', 'calibration', 'error'],
    'board-firmware': ['device_identity', 'pins', 'voltage', 'bus', 'reset'],
    'radio-service': ['frame', 'sequence', 'receiver', 'deadline', 'success'],
    'board-package': ['outline', 'coordinate_frame', 'units', 'holes', 'height', 'keepouts']}


def finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value): raise ValueError('TASK_NONFINITE_VALUE')
    if isinstance(value, dict):
        for v in value.values(): finite_tree(v)
    elif isinstance(value, list):
        for v in value: finite_tree(v)


def catalogue():
    return {'version': VERSION, 'functions': FUNCTIONS, 'interface_families': INTERFACE_FAMILIES,
        'parameter_binding': {'target': 'scenario|design|artifact', 'path': 'exact field or logical artifact'},
        'design_space': {'fields': 'subset of adapter fields with unit/min/max',
                         'editable_files': 'subset of adapter writable paths'},
        'acceptance': 'condition is explanatory text; registered predicates and typed fields execute the requirement',
        'phase_change': 'operator-owned, explicit rationale when intent/profile changes, compatible inputs required',
        'interface_levels': ['format', 'source_consistency', 'engineering_compatibility']}


def compile_standard(raw, cfg):
    finite_tree(raw)
    adapter = cfg['adapter']; scenario = raw['scenario']
    from .repository_feedback_contract import FIELDS as FEEDBACK_FIELDS, UNITS as FEEDBACK_UNITS, spec as feedback_spec
    design_fields = FEEDBACK_FIELDS if adapter=='piezo-feedback-v1' else DESIGN_FIELDS
    scenario_units = FEEDBACK_UNITS if adapter=='piezo-feedback-v1' else SCENARIO_UNITS
    piezo = adapter in ('piezo-reference-v1','piezo-feedback-v1')
    for key in ('functions', 'assignments'):
        for obj in raw.get(key, []):
            for refs in ('components', 'functions'):
                if refs in obj and (not isinstance(obj[refs], list) or any(not isinstance(v, str) for v in obj[refs]) or len(set(obj[refs])) != len(obj[refs])):
                    raise ValueError('TASK_MAPPING_REFERENCE_LIST')
    physical = [c['physical_instance'] for c in raw.get('components', []) if 'physical_instance' in c]
    if any(not isinstance(p, str) or not p for p in physical) or len(set(physical)) != len(physical):
        raise ValueError('TASK_PHYSICAL_INSTANCE_DUPLICATE')
    if adapter == 'piezo-reference-v1' and set(scenario) - set(SCENARIO_UNITS) - DISPLAY_ONLY:
        raise ValueError('TASK_SCENARIO_UNSUPPORTED_FIELD')
    criteria_fields = {'curve_accuracy': {'max_abs_error'}, 'receiver_service': {'minimum_packets'}}
    for gate, criterion in raw['acceptance'].items():
        if set(criterion) - {'condition'} - criteria_fields.get(gate, set()):
            raise ValueError('TASK_CRITERION_UNSUPPORTED_FIELD: ' + gate)
    fixed = []; bindings = []
    for p in raw['parameters']:
        if set(p) - {'name', 'value', 'unit', 'source', 'role', 'locator', 'binding'}:
            raise ValueError('TASK_PARAMETER_UNKNOWN_FIELD')
        if not isinstance(p['unit'], str) or not p['unit']: raise ValueError('TASK_PARAMETER_UNIT_REQUIRED')
        bind = p.get('binding')
        if bind is None and p['name'] in scenario and p['value'] == scenario[p['name']]:
            bind = {'target': 'scenario', 'path': p['name']}
        if bind is None and piezo and p['name'] in design_fields:
            bind = {'target': 'design', 'path': p['name']}
        if bind is None:
            if p['role'] == 'constraint': raise ValueError('TASK_CONSTRAINT_BINDING_REQUIRED: ' + p['name'])
            bindings.append({'parameter': p['name'], 'binding': None, 'status': 'DESCRIPTIVE'})
            continue
        if not isinstance(bind, dict) or set(bind) != {'target', 'path'}: raise ValueError('TASK_PARAMETER_BINDING')
        target, path = bind['target'], bind['path']
        if target == 'scenario':
            if path not in scenario or p['value'] != scenario[path]: raise ValueError('TASK_PARAMETER_SCENARIO_CONFLICT')
            if piezo and p['unit'] != scenario_units.get(path): raise ValueError('TASK_PARAMETER_UNIT_MISMATCH')
            if p['role'] == 'design_choice': raise ValueError('TASK_SCENARIO_IS_FIXED')
        elif target == 'design':
            if not piezo or path not in design_fields: raise ValueError('TASK_DESIGN_BINDING_UNSUPPORTED')
            unit, lo, hi = design_fields[path]
            if p['unit'] != unit: raise ValueError('TASK_PARAMETER_UNIT_MISMATCH')
            if type(p['value']) not in (int, float) or not lo <= p['value'] <= hi: raise ValueError('TASK_DESIGN_VALUE_DOMAIN')
        elif target == 'artifact':
            from .repository import name
            name(path)
            if p['role'] == 'constraint' and (not isinstance(p['value'], str) or len(p['value']) != 64 or any(c not in '0123456789abcdef' for c in p['value'])):
                raise ValueError('TASK_ARTIFACT_CONSTRAINT_SHA_REQUIRED')
        else: raise ValueError('TASK_PARAMETER_BINDING_TARGET')
        entry = {'parameter': p['name'], 'binding': bind, 'value': p['value'], 'role': p['role'], 'unit': p['unit']}
        bindings.append(entry)
        if p['role'] == 'constraint': fixed.append(entry)
    from .repository_profiles import PREFIXES
    defaults = {
        'piezo-feedback-v1': {'fields':{k:{'unit':u,'min':lo,'max':hi} for k,(u,lo,hi) in FEEDBACK_FIELDS.items()},
                              'editable_files':['design.json','firmware/main.c','notes/']},
        'piezo-reference-v1': {'fields': {k: {'unit': u, 'min': lo, 'max': hi} for k, (u, lo, hi) in DESIGN_FIELDS.items()},
                              'editable_files': ['design.json', 'firmware/main.c', 'notes/']},
        'tabulated-curve-v1': {'fields': {}, 'editable_files': ['observation.csv', 'notes/']},
        'p01-existing': {'fields': {}, 'editable_files': sorted({p for role in cfg['roles'] for p in PREFIXES[role]})}}
    space = deepcopy(raw.get('design_space', defaults[adapter]))
    if not isinstance(space, dict) or set(space) != {'fields', 'editable_files'}: raise ValueError('TASK_DESIGN_SPACE_SCHEMA')
    if not isinstance(space['fields'], dict) or not isinstance(space['editable_files'], list): raise ValueError('TASK_DESIGN_SPACE_SCHEMA')
    if any(not isinstance(p, str) or not p for p in space['editable_files']): raise ValueError('TASK_DESIGN_SPACE_PATH')
    from .repository import name
    for path in space['editable_files']: name(path.rstrip('/'))
    if len(space['editable_files']) != len(set(space['editable_files'])) or not all(path_allowed(p, defaults[adapter]['editable_files']) for p in space['editable_files']):
        raise ValueError('TASK_DESIGN_SPACE_PATH')
    for key, bounds in space['fields'].items():
        if key not in defaults[adapter]['fields'] or not isinstance(bounds, dict) or set(bounds) != {'unit', 'min', 'max'}: raise ValueError('TASK_DESIGN_SPACE_FIELD')
        original = defaults[adapter]['fields'][key]
        if bounds['unit'] != original['unit'] or any(type(bounds[k]) not in (int, float) for k in ('min', 'max')) or not original['min'] <= bounds['min'] <= bounds['max'] <= original['max']:
            raise ValueError('TASK_DESIGN_SPACE_BOUNDS')
    for item in fixed:
        if item['binding']['target'] == 'design':
            key = item['binding']['path']
            if 'design_space' in raw and key in space['fields']: raise ValueError('TASK_FIXED_VARIABLE_CONFLICT')
            space['fields'].pop(key, None)
    service = {'observable': cfg['scope']}
    if piezo:
        service = {'observable': 'valid-digital-frames', 'startup': 'declared-initial-storage',
            'deadline_s': scenario['duration_s'], 'minimum_results': raw['acceptance']['receiver_service']['minimum_packets']}
    elif adapter == 'tabulated-curve-v1': service = {'observable': 'paired-sample-error'}
    if 'service' in raw and raw['service'] != service: raise ValueError('TASK_SERVICE_UNSUPPORTED_OR_CONFLICTING')
    for a in raw.get('assignments', []):
        if a.get('role') not in ['lead'] + cfg['roles']: raise ValueError('TASK_ASSIGNMENT_ROLE_UNSUPPORTED')
        if 'components' in a and (not isinstance(a['components'], list) or not set(a['components']) <= {c['id'] for c in raw.get('components', [])}):
            raise ValueError('TASK_ASSIGNMENT_COMPONENT_UNKNOWN')
    return {'version': VERSION, 'service': service, 'design_space': space, 'bindings': bindings,
        'fixed_parameters': fixed, 'interface_levels': ['format', 'source_consistency', 'engineering_compatibility'],
        'execution_policy': feedback_spec() if adapter=='piezo-feedback-v1' else {'coupling': 'average source power to storage; host events drive fixed-current load; supply checked afterward',
            'source_step_s': 1/scenario['frequency_hz']/160, 'source_cycles': 120, 'source_evaluation_last_cycles': 20,
            'storage_max_step_s': .01, 'event_edges_s': 1e-7, 'event_order': 'ordered and non-overlapping',
            'feedback_iteration': 'not implemented; automatic startup and voltage-driven firmware require another adapter'} if adapter == 'piezo-reference-v1' else {'adapter': adapter},
        'acceptance_predicates': acceptance_predicates(raw, cfg),
        'reference_rules': deepcopy(REFERENCE_RULES) if adapter == 'piezo-reference-v1' else {},
        'interface_consumers': interface_consumers(adapter)}


def acceptance_predicates(raw, cfg):
    """Effective machine conditions shown by the same schema that drives checks."""
    result = {g: {'checker': 'repository_task_checks.evaluate',
                  'parameters': {k: v for k, v in c.items() if k != 'condition'}} for g, c in raw['acceptance'].items()}
    if cfg['adapter'] == 'piezo-reference-v1':
        s = raw['scenario']
        values = {
            'source_model': {'relative_error_lt': REFERENCE_RULES['source_relative_error_lt'],
                             'tip_displacement_length_ratio_max': REFERENCE_RULES['tip_displacement_length_ratio_max']},
            'load_binding': {'charge_absolute_tolerance_c': REFERENCE_RULES['charge_absolute_tolerance_c'],
                             'charge_relative_tolerance': REFERENCE_RULES['charge_relative_tolerance']},
            'power_service': {'all_transmissions_supplied': True, 'minimum_sample_and_tx_storage_v': s['minimum_storage_v'],
                'energy_absolute_tolerance_j': REFERENCE_RULES['energy_absolute_tolerance_j'],
                'energy_relative_tolerance': REFERENCE_RULES['energy_relative_tolerance'],
                'negative_voltage_tolerance_v': REFERENCE_RULES['negative_voltage_tolerance_v']},
            'receiver_service': {'minimum_packets': raw['acceptance']['receiver_service']['minimum_packets'],
                'sample_before_tx': True, 'unique_sequence': True, 'checksum': '(seq ^ value ^ 0xA5) & 255',
                'sensor_value': s['sensor_value'], 'minimum_sample_s': s['minimum_sample_s'], 'minimum_tx_s': s['minimum_tx_s'],
                'deadline_s': s['duration_s'], 'minimum_sample_and_tx_storage_v': s['minimum_storage_v']}}
        for gate, parameters in values.items():
            result[gate] = {'checker': 'repository_reference_node.independent_check', 'parameters': parameters}
    elif cfg['adapter'] == 'piezo-feedback-v1':
        from .repository_feedback_contract import NUMERICS, CHECK_ONLY
        for value in result.values():
            value['checker']='repository_feedback_validation.independent_check'
            value['rules']=NUMERICS
            value['service_conditions']={k:v for k,v in raw['scenario'].items() if k in CHECK_ONLY}
    elif cfg['adapter'] == 'p01-existing':
        for value in result.values(): value['checker'] = 'repository_validation.evaluate / native_review_reuse'
    return result


def interface_consumers(adapter):
    """Expose the actual consuming path; unimplemented families stay explicit."""
    result = {k: {'status': 'NOT_IMPLEMENTED'} for k in INTERFACE_FAMILIES}
    if adapter == 'piezo-reference-v1':
        paths = {
            'mechanics-source': ('design.json + scenario.material', 'modal → source.cir → ngspice', ['source_model'], ['source_model']),
            'source-power': ('source.dat + conversion_efficiency', 'available_power → storage.cir', ['source_model'], ['power_service']),
            'power-runtime': ('compiled events.csv + state_currents_a', 'load.json → storage.cir → service windows', ['load_binding'], ['power_service']),
            'radio-service': ('sample/tx events.csv', 'independent_check digital receiver', ['load_binding'], ['receiver_service'])}
        for key, (producer, consumer, sources, engineering) in paths.items():
            result[key] = {'status': 'IMPLEMENTED', 'producer': producer, 'consumer': consumer,
                'checker': 'repository_reference_node.independent_check', 'scope': 'nominal-reference-chain',
                'source_gates': sources, 'engineering_gates': engineering, 'affected_gates': sorted(set(sources+engineering))}
    elif adapter == 'piezo-feedback-v1':
        for key,producer,consumer,gates in [
                ('mechanics-source','design + fixed excitation/material','reciprocal modal source',['source_model','coupling_numerics']),
                ('source-power','piezo electrical port','vendor LTC3588-1 bridge/buck',['source_model','power_service']),
                ('power-runtime','MCU VDD + PGOOD','sandboxed compiled C → state-current load → native solver',['load_binding','power_service','coupling_numerics']),
                ('radio-service','completed sample/TX in one powered boot','independent digital receiver',['receiver_service'])]:
            result[key]={'status':'IMPLEMENTED','producer':producer,'consumer':consumer,
                'checker':'repository_feedback_validation.independent_check','scope':'vendor-PMIC-program-feedback',
                'source_gates':gates,'engineering_gates':gates,'affected_gates':gates}
    elif adapter == 'p01-existing':
        result['power-runtime'] = {'status': 'IMPLEMENTED', 'producer': 'nRF5/S132 source + load-timeline.json',
            'consumer': 'repository_load + spice', 'checker': 'repository_contracts.check + repository_validation.evaluate',
            'scope': 'P01 calibrated adapter', 'source_gates': ['board_firmware_interfaces'],
            'engineering_gates': ['power_load_chain'], 'affected_gates': ['board_firmware_interfaces', 'power_load_chain']}
    return result


def execution_scenario(task):
    scenario = task.get('scenario', {})
    if task.get('standards', {}).get('version') != VERSION: return scenario
    if task['case_adapter'] == 'piezo-reference-v1':
        return {k: v for k, v in scenario.items() if k not in CHECK_ONLY | DISPLAY_ONLY}
    if task['case_adapter'] == 'piezo-feedback-v1':
        from .repository_feedback_contract import CHECK_ONLY as FEEDBACK_CHECK_ONLY
        return {k:v for k,v in scenario.items() if k not in FEEDBACK_CHECK_ONLY | DISPLAY_ONLY}
    return scenario


def acceptance_scenario(task):
    if task.get('standards', {}).get('version') == VERSION and task['case_adapter'] in ('piezo-reference-v1','piezo-feedback-v1'):
        return {k: v for k, v in task['scenario'].items() if k not in DISPLAY_ONLY}
    return task['scenario']


def check_files(task, files, read, previous=None, changed=None):
    standard = task.get('standards')
    if not standard: return
    space = standard['design_space']
    if changed is not None:
        for path in changed:
            if not path_allowed(path, space['editable_files']): raise PermissionError('TASK_DESIGN_SCOPE')
    design = None
    if task['case_adapter'] in ('piezo-reference-v1','piezo-feedback-v1'):
        from .repository_feedback_contract import FIELDS as FEEDBACK_FIELDS
        fields = FEEDBACK_FIELDS if task['case_adapter']=='piezo-feedback-v1' else DESIGN_FIELDS
        if not {'design.json', 'firmware/main.c'} <= set(files): raise ValueError('TASK_TRANSITION_INPUT_MISSING')
        design = json.loads(read('design.json')); finite_tree(design)
        if not isinstance(design, dict) or set(design) != set(fields): raise ValueError('TASK_DESIGN_FIELDS')
        for key, (unit, lo, hi) in fields.items():
            val = design[key]
            if type(val) not in (int, float) or not lo <= val <= hi: raise ValueError('TASK_DESIGN_VALUE_DOMAIN')
            if key in space['fields']:
                b = space['fields'][key]
                if not b['min'] <= val <= b['max']: raise PermissionError('TASK_DESIGN_SPACE_BOUNDS')
            elif previous is not None and val != previous[key]: raise PermissionError('TASK_UNDECLARED_DESIGN_VARIABLE: ' + key)
    elif task['case_adapter'] == 'tabulated-curve-v1' and not {'reference.csv', 'observation.csv'} <= set(files):
        raise ValueError('TASK_TRANSITION_INPUT_MISSING')
    for p in standard['fixed_parameters']:
        target, path = p['binding']['target'], p['binding']['path']
        if target == 'design' and design[path] != p['value']: raise PermissionError('TASK_FIXED_PARAMETER_CHANGED: ' + p['parameter'])
        if target == 'artifact' and files.get(path, {}).get('sha256') != p['value']: raise PermissionError('TASK_FIXED_ARTIFACT_CHANGED: ' + path)


def transition(parent, child, rationale):
    changed = [key for key in ('intent', 'profile', 'phase') if parent.get(key) != child.get(key)]
    if changed and (not isinstance(rationale, str) or not rationale.strip()): raise ValueError('TASK_PHASE_TRANSITION_REASON_REQUIRED')
    return {'from_definition': parent.get('id'), 'to_definition': child['id'], 'changed': changed,
            'reason': rationale or 'operator revises task requirements', 'old_conclusions': 'retained with original requirements'}


def path_allowed(path, paths):
    return any(path.startswith(a) if a.endswith('/') else path == a for a in paths)
