"""Task configuration shared by Repository, Pi and report consumers.

Historical P01 commits retain their original payloads and qualification keys.
New task contracts are immutable members of System Commits.
"""
from copy import deepcopy
import math

from ..store import identity

VERSION = 'bf-design-task-definition-v2'
INTENTS = ('audit', 'reproduce', 'reconstruct', 'complete', 'optimize', 'new_design')
PREFIXES = {'mechanical': ('project-cad/', 'mechanical/'),
            'power': ('project-chain/', 'project-spice/', 'circuit/', 'interfaces/power.json'),
            'firmware': ('project-fw-s132/', 'project-firmware/', 'receiver/', 'interfaces/firmware.json'),
            'assembly': ('assembly/', 'interfaces/assembly.json')}
P01_GATES = {'source_domain': ('mechanical', 'power'), 'schematic_bom_pins': ('power',),
             'pcb_connectivity_drc': ('power', 'assembly'), 'geometry_fit': ('mechanical', 'assembly'),
             'board_firmware_interfaces': ('power', 'firmware', 'assembly'),
             'firmware_event_logic': ('firmware',), 'power_load_chain': ('mechanical', 'power', 'firmware'),
             'delivery_version': ('mechanical', 'power', 'firmware', 'assembly')}
P01 = {'id': 'p01-digital-v1', 'adapter': 'p01-existing', 'scope': 'digital-product',
       'gates': list(P01_GATES), 'report': 'node-eight-page-v1',
       'manifests': {'firmware': 'project-fw-s132/project.json', 'power': 'project-chain/project.json'},
       'executors': {'firmware': 'firmware-nrf52832-s132', 'power': 'spice'},
       'source_paths': {'firmware': 'project-fw-s132/main.c', 'load': 'project-chain/load-timeline.json',
                        'power': 'project-chain/interface-params.json'},
       'roles': ['power', 'firmware']}
PROFILES = {
    P01['id']: P01,
    'curve-reproduction-v1': {'id': 'curve-reproduction-v1', 'adapter': 'tabulated-curve-v1',
        'scope': 'curve-reproduction', 'gates': ['curve_binding', 'curve_accuracy', 'delivery_version'],
        'report': 'curve-three-section-v1', 'roles': [], 'manifests': {}, 'executors': {}},
    'pcb-completion-v1': {'id': 'pcb-completion-v1', 'adapter': 'p01-existing',
        'scope': 'pcb-engineering', 'gates': ['schematic_bom_pins', 'pcb_connectivity_drc', 'delivery_version'],
        'report': 'pcb-four-section-v1', 'roles': [], 'review_only': True, 'manifests': {}, 'executors': {}},
    'node-reference-v1': {'id': 'node-reference-v1', 'adapter': 'piezo-reference-v1',
        'scope': 'nominal-reference-chain', 'gates': ['source_model', 'load_binding', 'power_service',
            'receiver_service', 'delivery_version'], 'report': 'reference-five-section-v1',
        'roles': [], 'manifests': {}, 'executors': {}}
}
REPORTS = {
    'node-eight-page-v1': ['overview', 'dimensions', 'assembly', 'pcb', 'schematic', 'firmware_sequence', 'energy', 'acceptance'],
    'curve-three-section-v1': ['target_and_conditions', 'curves_and_error', 'conclusion_and_files'],
    'pcb-four-section-v1': ['scope_and_design', 'schematic_and_pcb', 'connectivity_and_drc', 'conclusion_and_files'],
    'reference-five-section-v1': ['task_and_model', 'mechanics_and_source', 'firmware_and_receiver', 'energy_and_service', 'conclusion_and_files']
}
# Each link names the executable consumer and checker, not only its producers.
INTERFACES = {
    'p01-existing': [
        {'id': 'firmware-load', 'producer': 'firmware', 'consumer': 'power',
         'executor': 'spice', 'checker': 'power-firmware-source-contract-v3',
         'input_paths': ['project-fw-s132/main.c', 'project-chain/load-timeline.json', 'project-chain/interface-params.json'],
         'affected_gates': ['board_firmware_interfaces', 'power_load_chain'],
         'units': {'period': 'ms', 'current': 'A', 'voltage': 'V'}, 'initial_state': 'declared storage voltage',
         'model_scope': 'nRF5 S132 timing with declared current amplitudes and manual admission'}],
    'tabulated-curve-v1': [
        {'id': 'reference-observation', 'producer': 'reference', 'consumer': 'curve-comparison-v1',
         'executor': 'tabulated-data-readback', 'checker': 'curve-comparison-v1',
         'input_paths': ['reference.csv', 'observation.csv'], 'affected_gates': ['curve_binding', 'curve_accuracy'],
         'units': 'task scenario axis_units', 'initial_state': 'task scenario', 'model_scope': 'matching sampled abscissae'}],
    'piezo-reference-v1': [
        {'id': 'mechanics-source', 'producer': 'mechanical', 'consumer': 'ngspice-piezo-v1',
         'executor': 'ngspice-piezo-v1', 'checker': 'piezo-source-v1', 'input_paths': ['design.json'],
         'affected_gates': ['source_model', 'power_service'], 'units': 'SI', 'initial_state': 'scenario',
         'model_scope': 'linear lumped piezo harvester'},
        {'id': 'firmware-load-receiver', 'producer': 'host-firmware-v1', 'consumer': 'ngspice-piezo-v1',
         'executor': 'host-firmware-v1', 'checker': 'node-service-v1', 'input_paths': ['firmware/main.c', 'design.json'],
         'affected_gates': ['load_binding', 'power_service', 'receiver_service'], 'units': 's,A,V',
         'initial_state': 'scenario', 'model_scope': 'compiled host event trace and digital receiver'}]
}


def profile(key):
    if key not in PROFILES: raise ValueError('TASK_PROFILE_UNKNOWN: ' + str(key))
    return deepcopy(PROFILES[key])


def schema():
    from .repository_task_standards import catalogue
    return {'schema_version': VERSION, 'intents': list(INTENTS), 'profiles': deepcopy(PROFILES),
            'reports': deepcopy(REPORTS), 'parameter_sources': ['user', 'literature', 'measurement', 'agent', 'reference'],
            'parameter_roles': ['constraint', 'design_choice', 'assumption'],
            'required_fields': ['profile', 'intent', 'goal', 'scenario', 'parameters', 'acceptance'],
            'standards': catalogue(),
            'description': 'Task intent, scenario, parameters with independent source/role, acceptance and report scope. '
            'Requirements are operator-owned; Pi changes only declared design files. task_schema returns profiles and required gates.'}


def runtime_spec(task):
    cfg = profile(task['profile'])
    result = {'profile':cfg, 'report_sections':REPORTS[cfg['report']],
              'report_content':{'conclusion':'string','sections':{k:{'text':'string','sources':['candidate path or gate ID']} for k in REPORTS[cfg['report']]}},
              'intent':task['intent'], 'requirements_owner':'operator'}
    operations = ['task_definition', 'task_schema', 'task_state', 'summary', 'read', 'validate', 'decide', 'release', 'close']
    if cfg['report'] != 'node-eight-page-v1': operations.append('task_report')
    if cfg['adapter'] in ('piezo-reference-v1', 'tabulated-curve-v1'):
        operations += ['task_execute', 'task_result']
        if task['intent'] != 'audit': operations.append('task_commit')
    elif cfg['roles'] and task['intent'] != 'audit':
        operations += ['assign', 'task', 'write', 'commit', 'execute', 'extract', 'contract', 'integrate', 'rebase', 'finish']
    result['qualified_operations'] = operations
    if cfg['adapter'] == 'piezo-reference-v1':
        result.update(write_paths=['design.json','firmware/main.c','notes/'],
            design_fields={'length_m':[.02,.1],'width_m':[.002,.03],'substrate_m':[.00005,.001],
                'piezo_m':[.00005,.001],'tip_mass_kg':[0,.02],'storage_f':[.000001,.02]},
            program={'language':'C11 host executable; stdio available', 'output_columns':['t_s','duration_s','state','seq','value','crc'],
                'states':['sample','tx','idle'],'duration_s':[0,1], 'time':'strictly ordered nonoverlapping events with >1e-7 s gaps, inside scenario.duration_s',
                'checksum':'(seq ^ value ^ 0xA5) & 255', 'receiver':'matching sample before tx, sensor_value and minimum durations from scenario',
                'supply':'actual sample and tx windows must meet scenario.minimum_storage_v',
                'execution':'sandboxed compile and host execution; events drive fixed state-current waveform and storage solver'})
    elif cfg['adapter']=='tabulated-curve-v1':
        result.update(write_paths=['observation.csv','notes/'],data_columns=['x','y'],comparison='same increasing x coordinates, finite values, maximum absolute y error')
    if task.get('standards'):
        result['standards'] = task['standards']
        result['write_paths'] = task['standards']['design_space']['editable_files']
        result['design_fields'] = task['standards']['design_space']['fields']
        result['fixed_parameters'] = task['standards']['fixed_parameters']
    return result


def definition(raw):
    """Validate and seal an operator-approved task; no Agent-selected acceptance."""
    if not isinstance(raw, dict): raise ValueError('TASK_DEFINITION_OBJECT_REQUIRED')
    allowed = set(schema()['required_fields']) | {'phase', 'report', 'functions', 'components', 'assignments', 'design_space', 'service'}
    if set(raw) - allowed: raise ValueError('TASK_DEFINITION_UNKNOWN_FIELD')
    if not set(schema()['required_fields']) <= set(raw): raise ValueError('TASK_DEFINITION_FIELDS_REQUIRED')
    cfg = profile(raw['profile'])
    if raw['intent'] not in INTENTS: raise ValueError('TASK_INTENT_UNKNOWN')
    if not isinstance(raw['goal'], str) or not 1 <= len(raw['goal'].strip()) <= 4000: raise ValueError('TASK_GOAL_REQUIRED')
    if not isinstance(raw['scenario'], dict) or not raw['scenario']: raise ValueError('TASK_SCENARIO_REQUIRED')
    if not isinstance(raw['parameters'], list): raise ValueError('TASK_PARAMETERS_REQUIRED')
    if 'phase' in raw and (not isinstance(raw['phase'], str) or not 1 <= len(raw['phase']) <= 128): raise ValueError('TASK_PHASE_REQUIRED')
    seen = set()
    for parameter in raw['parameters']:
        if not isinstance(parameter, dict) or not {'name', 'value', 'unit', 'source', 'role'} <= parameter.keys():
            raise ValueError('TASK_PARAMETER_FIELDS_REQUIRED')
        if not isinstance(parameter['name'], str) or not parameter['name'] or parameter['name'] in seen:
            raise ValueError('TASK_PARAMETER_IDENTITY')
        seen.add(parameter['name'])
        if parameter['source'] not in schema()['parameter_sources'] or parameter['role'] not in schema()['parameter_roles']:
            raise ValueError('TASK_PARAMETER_SOURCE_ROLE')
        if parameter['source'] in ('literature', 'measurement') and not parameter.get('locator'):
            raise ValueError('TASK_PARAMETER_SOURCE_LOCATOR')
        if parameter['role'] == 'constraint' and parameter['name'] in raw['scenario'] and parameter['value'] != raw['scenario'][parameter['name']]:
            raise ValueError('TASK_PARAMETER_SCENARIO_CONFLICT')
    criteria = raw['acceptance']
    if not isinstance(criteria, dict) or set(criteria) != set(cfg['gates']): raise ValueError('TASK_ACCEPTANCE_GATES_MISMATCH')
    for key, criterion in criteria.items():
        if not isinstance(criterion, dict) or not isinstance(criterion.get('condition'), str) or not criterion['condition'].strip():
            raise ValueError('TASK_ACCEPTANCE_CONDITION_REQUIRED: ' + key)
    if cfg['adapter'] == 'tabulated-curve-v1':
        limit = criteria['curve_accuracy'].get('max_abs_error')
        if type(limit) not in (float, int) or not math.isfinite(limit) or limit < 0:
            raise ValueError('CURVE_ERROR_LIMIT_REQUIRED')
        if not isinstance(raw['scenario'].get('axis_units'), dict) or set(raw['scenario']['axis_units']) != {'x', 'y'}:
            raise ValueError('CURVE_AXIS_UNITS_REQUIRED')
    if cfg['adapter'] == 'piezo-reference-v1':
        scenario = raw['scenario']
        positive = ('frequency_hz', 'electrical_load_ohm', 'damping_ratio', 'conversion_efficiency',
                    'duration_s', 'rail_v', 'storage_max_v', 'minimum_storage_v', 'minimum_sample_s', 'minimum_tx_s')
        for key in positive:
            if type(scenario.get(key)) not in (int, float) or not math.isfinite(scenario[key]) or scenario[key] <= 0:
                raise ValueError('REFERENCE_SCENARIO_REQUIRED: ' + key)
        if not (scenario['conversion_efficiency'] <= 1 and scenario['duration_s'] <= 600 and
                1 <= scenario['frequency_hz'] <= 1000 and .001 <= scenario['damping_ratio'] <= .2):
            raise ValueError('REFERENCE_SCENARIO_DOMAIN')
        for key in ('initial_storage_v', 'acceleration_peak_m_s2'):
            if type(scenario.get(key)) not in (int, float) or not math.isfinite(scenario[key]) or scenario[key] < 0:
                raise ValueError('REFERENCE_SCENARIO_REQUIRED: ' + key)
        if not scenario['initial_storage_v'] <= scenario['storage_max_v'] or not scenario['minimum_storage_v'] <= scenario['storage_max_v']:
            raise ValueError('REFERENCE_STORAGE_LIMITS')
        if not isinstance(scenario.get('state_currents_a'), dict) or set(scenario['state_currents_a']) != {'idle', 'sample', 'tx'}:
            raise ValueError('REFERENCE_CURRENT_ENVELOPE_REQUIRED')
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= .1 for v in scenario['state_currents_a'].values()):
            raise ValueError('REFERENCE_CURRENT_ENVELOPE_DOMAIN')
        if type(criteria['receiver_service'].get('minimum_packets')) is not int or criteria['receiver_service']['minimum_packets'] < 1:
            raise ValueError('REFERENCE_RECEIVER_REQUIREMENT')
        if type(scenario.get('sensor_value')) is not int or not 0 <= scenario['sensor_value'] <= 65535:
            raise ValueError('REFERENCE_SENSOR_VALUE_REQUIRED')
        material = scenario.get('material', {})
        if not isinstance(material, dict) or set(material) != {'substrate_E_pa', 'piezo_E_pa', 'substrate_density', 'piezo_density', 'relative_permittivity', 'd31_m_v'}:
            raise ValueError('REFERENCE_MATERIAL_FIELDS')
        for key in ('substrate_E_pa', 'piezo_E_pa', 'substrate_density', 'piezo_density', 'relative_permittivity'):
            if type(material.get(key)) not in (int, float) or not math.isfinite(material[key]) or material[key] <= 0:
                raise ValueError('REFERENCE_MATERIAL_REQUIRED: ' + key)
        if type(material.get('d31_m_v')) not in (int, float) or not math.isfinite(material['d31_m_v']):
            raise ValueError('REFERENCE_MATERIAL_REQUIRED: d31_m_v')
    report = raw.get('report', cfg['report'])
    if report != cfg['report']: raise ValueError('TASK_REPORT_PROFILE_MISMATCH')
    value = {**deepcopy(raw), 'schema_version': VERSION, 'phase': raw.get('phase', raw['intent']),
             'report': report, 'scope': cfg['scope'], 'case_adapter': cfg['adapter'],
             'required_gates': cfg['gates'], 'interfaces': deepcopy(INTERFACES[cfg['adapter']])}
    for key in ('functions', 'components', 'assignments'):
        if not isinstance(value.get(key, []), list): raise ValueError('TASK_MAPPING_LIST_REQUIRED')
        value.setdefault(key, [])
    # Shared physical components are represented once. Functions may reference the same component.
    if not all(isinstance(c, dict) for c in value['components']+value['functions']+value['assignments']):
        raise ValueError('TASK_MAPPING_OBJECT_REQUIRED')
    for obj in value['functions'] + value['assignments']:
        for key in ('components', 'functions'):
            refs = obj.get(key, [])
            if not isinstance(refs, list) or any(not isinstance(v, str) for v in refs) or len(refs) != len(set(refs)):
                raise ValueError('TASK_MAPPING_REFERENCE_LIST')
    component_ids = [c.get('id') for c in value['components']]
    if any(not isinstance(i, str) or not i for i in component_ids) or len(component_ids) != len(set(component_ids)):
        raise ValueError('TASK_COMPONENT_IDENTITY')
    for f in value['functions']:
        if not set(f.get('components', [])) <= set(component_ids): raise ValueError('TASK_FUNCTION_COMPONENT_UNKNOWN')
    function_ids = [f.get('id') for f in value['functions']]
    if any(not isinstance(i,str) or not i for i in function_ids) or len(set(function_ids)) != len(function_ids):
        raise ValueError('TASK_FUNCTION_IDENTITY')
    for assignment in value['assignments']:
        if not set(assignment.get('functions', [])) <= set(function_ids): raise ValueError('TASK_ASSIGNMENT_FUNCTION_UNKNOWN')
    from .repository_task_standards import compile_standard
    value['standards'] = compile_standard(raw, cfg)
    value['id'] = 'TD-' + identity(value)
    return value


def system_definition(repo, system, db=None):
    value = system.get('task_definition')
    if value:
        if value['id'] != 'TD-' + identity({k: v for k, v in value.items() if k != 'id'}):
            raise ValueError('TASK_DEFINITION_TAMPER')
        return value
    return None


def system_profile(system):
    return profile(system.get('task_definition', {}).get('profile', P01['id']))


def execution_identity(system, executor, environment, paths=None):
    selected = sorted(system['files'] if paths is None else paths)
    if not selected or any(p not in system['files'] for p in selected): raise ValueError('EXECUTION_INPUT_FILES_REQUIRED')
    task = system.get('task_definition', {})
    from .repository_task_standards import execution_scenario
    payload = {'schema_version': 'bf-execution-identity-v1', 'executor': executor,
        'environment': environment, 'scenario': execution_scenario(task),
        'inputs': {p: system['files'][p]['sha256'] for p in selected}}
    return {'id': 'EX-' + identity(payload), **payload}


def acceptance_identity(system, gate, raw_key, checker):
    task = system.get('task_definition')
    if not task: return raw_key  # Sealed historical P01 identity.
    return identity({'schema_version': 'bf-acceptance-identity-v1', 'execution': raw_key,
        'gate': gate, 'scope': task['scope'], 'criterion': task['acceptance'].get(gate),
        'checker': checker, 'profile': task['profile']})


def task_requirements(repo, system, db=None):
    value = system_definition(repo, system, db)
    return value or repo.project(system['project_id'], db=db)['requirements']
