"""Source-bound interface checks and exact dependency fingerprints.

Checks report observations; choosing a device strategy remains the Agent's job.
The first calibrated extractor is nRF5/S132 with the declared P01 load schema.
Other extractors must register their own source and unit contracts.
"""
import math
import re

from ..store import identity

VERSION = 'power-firmware-source-contract-v2'
PREFIXES = {'mechanical': ('project-cad/', 'mechanical/'),
            'power': ('project-chain/', 'project-spice/', 'circuit/', 'interfaces/power.json'),
            'firmware': ('project-fw-s132/', 'project-firmware/', 'receiver/', 'interfaces/firmware.json'),
            'assembly': ('assembly/', 'interfaces/assembly.json')}
GATES = {'source_domain': ('mechanical', 'power'), 'schematic_bom_pins': ('power',),
         'pcb_connectivity_drc': ('power', 'assembly'), 'geometry_fit': ('mechanical', 'assembly'),
         'board_firmware_interfaces': ('power', 'firmware', 'assembly'),
         'firmware_event_logic': ('firmware',), 'power_load_chain': ('mechanical', 'power', 'firmware'),
         'delivery_version': ('mechanical', 'power', 'firmware', 'assembly')}
CONTRACT_GATES = ('board_firmware_interfaces', 'power_load_chain', 'delivery_version')


def domain_of(path):
    for domain, prefixes in PREFIXES.items():
        if any(path.startswith(p) for p in prefixes): return domain
    return 'shared'


def fingerprint(system, gate):
    domains = GATES.get(gate, tuple(PREFIXES))
    value = {'files': {p: r['sha256'] for p, r in system['files'].items()
                       if domain_of(p) in domains or domain_of(p) == 'shared'},
             'jobs': {j: {k: v for k, v in r.items() if k not in ('dispatched_in_v2', 'origin_owner')}
                      for j, r in system.get('jobs', {}).items()
                      if job_domain(r) in domains or job_domain(r) == 'shared'},
             'contracts': system.get('contracts', {}) if gate in CONTRACT_GATES else {}}
    # Interface declarations do not change the bytes compiled by a firmware job.
    if gate not in CONTRACT_GATES:
        value['files'] = {p: s for p, s in value['files'].items() if not p.startswith('interfaces/')}
    return identity(value)


def job_domain(ref):
    text = str(ref.get('kind', ref.get('executor', ref.get('label', '')))).lower()
    if 'cad' in text: return 'mechanical'
    if 'firmware' in text: return 'firmware'
    if 'spice' in text: return 'power'
    artifacts = ref.get('artifacts', {})
    if any(p.endswith('.elf') for p in artifacts): return 'firmware'
    if any(p.endswith('.raw') for p in artifacts): return 'power'
    if any(p.endswith('.step') for p in artifacts): return 'mechanical'
    return 'shared'


def reuse_gates(parent, child):
    records = {}
    for key, old in parent.get('validations', {}).items():
        same = fingerprint(parent, key) == fingerprint(child, key)
        records[key] = {**old, 'status': old['status'] if same else 'RECHECK_REQUIRED',
                        'prior_status': old['status'], 'reused_from': parent['id'] if same else None,
                        'input_fingerprint': fingerprint(child, key),
                        'dependency_binding': 'exact-source-contract-job-fingerprint',
                        'invalidated_by': None if same else 'relevant input or contract changed'}
    return records


def timing(source):
    def number(pattern):
        found = re.search(pattern, source)
        return float(found[1]) if found else None
    return {'advertising_ms': number(r'#define\s+APP_ADV_INTERVAL\s+(\d+)'),
            'connection_min_ms': number(r'#define\s+MIN_CONN_INTERVAL\s+MSEC_TO_UNITS\((\d+(?:\.\d+)?),'),
            'connection_max_ms': number(r'#define\s+MAX_CONN_INTERVAL\s+MSEC_TO_UNITS\((\d+(?:\.\d+)?),'),
            'sample_ms': number(r'\.sample_period_ms\s*=\s*(\d+)'),
            'policy_advertising_ms': number(r'\.adv_period_ms\s*=\s*(\d+)')}


def check(read, files, declarations=None):
    """read(logical) consumes verified immutable bytes, never working files."""
    import json
    from pathlib import Path
    from .repository import file_hash
    result = {'checker': VERSION, 'checker_sha256': file_hash(Path(__file__)), 'checks': [],
              'source_hashes': {}, 'scope': 'source timing and declared load/power interface',
              'native_jobs_dispatched': 0, 'physical': 'NOT_TESTED'}
    def load(path, structured=False):
        if path not in files: raise ValueError('SOURCE_NOT_PRESENT: ' + path)
        result['source_hashes'][path] = files[path]['sha256']
        raw = read(path)
        return json.loads(raw) if structured else raw
    def record(key, actual, expected, compatible, locator):
        result['checks'].append({'id': key, 'status': 'PASS' if compatible else 'FAIL',
                                 'actual': actual, 'expected': expected, 'source': locator})
    try:
        source = timing(load('project-fw-s132/main.c'))
        if any(source[k] is None for k in ('advertising_ms', 'connection_min_ms', 'connection_max_ms', 'sample_ms')):
            raise ValueError('UNSUPPORTED_FIRMWARE_TIMING_EXPRESSION')
        source['advertising_ms'] *= .625
        model = load('project-chain/load-timeline.json', True)
        interface = load('project-chain/interface-params.json', True)
        radio = model['actual_radio_timing']
        comparisons = [('advertising_ms', radio['advertising_period_ms'], 'APP_ADV_INTERVAL'),
                       ('connection_min_ms', radio['connection_period_range_ms'][0], 'MIN_CONN_INTERVAL'),
                       ('connection_max_ms', radio['connection_period_range_ms'][1], 'MAX_CONN_INTERVAL'),
                       ('sample_ms', radio['sample_period_ms'], 'm_cfg.sample_period_ms')]
        for key, expected, locator in comparisons:
            record(key, source[key], expected, math.isclose(source[key], expected, abs_tol=1e-9), locator)
        used = radio['connection_period_ms_used']
        record('connection_bound', used, [source['connection_min_ms'], source['connection_max_ms']],
               source['connection_min_ms'] <= used <= source['connection_max_ms'], 'load-timeline actual_radio_timing')
        load_timing = interface['load_timing']
        record('model_interface_advertising', load_timing['actual_advertising_period_ms'], source['advertising_ms'],
               math.isclose(load_timing['actual_advertising_period_ms'], source['advertising_ms']), 'interface-params load_timing')
        record('manual_admission_energy', interface['manual_action']['manual_action_energy'], 0,
               interface['manual_action']['manual_action_energy'] == 0, 'interface-params manual_action')
        result['facts'] = {'firmware': source, 'rail_v': interface['regulator']['v_out_v'],
                           'storage_initial_v': interface['storage']['initial_v'],
                           'manual_admission': True, 'sece_resolved': interface['sece']['resolved'],
                           'current_amplitudes_origin': load_timing['current_amplitudes_origin']}
        result['issues'] = []
        if source['policy_advertising_ms'] != source['advertising_ms']:
            result['issues'].append({'id': 'policy-radio-duty', 'status': 'OPEN',
              'category': 'design_configuration', 'policy_ms': source['policy_advertising_ms'],
              'radio_ms': source['advertising_ms'], 'source': 'project-fw-s132/main.c'})
        if not interface['sece']['resolved']:
            result['issues'].append({'id': 'sece-envelope', 'status': 'OPEN', 'category': 'model_applicability',
                                     'unresolved': interface['sece']['unresolved']})
        # Agent declarations must agree with source extraction. They cannot grade themselves.
        for domain, declaration in (declarations or {}).items():
            if not isinstance(declaration, dict): raise ValueError('DECLARATION_OBJECT_REQUIRED')
            declared = declaration.get('interface', {})
            allowed = source if domain == 'firmware' else {k: result['facts'][k] for k in
                ('rail_v', 'storage_initial_v', 'manual_admission', 'sece_resolved')}
            for key, expected in allowed.items():
                if key not in declared: raise ValueError('CONTRACT_INTERFACE_FIELD_REQUIRED: ' + domain + '.' + key)
                record(domain + '_declaration_' + key, declared[key], expected, declared[key] == expected,
                       'interfaces/' + domain + '.json → immutable source')
            sources = declaration.get('sources', [])
            if not sources: raise ValueError('DECLARATION_SOURCE_REFS_REQUIRED')
            for ref in sources:
                path = ref.get('path')
                if path not in files: raise ValueError('DECLARATION_SOURCE_NOT_PRESENT: ' + str(path))
                record(domain + '_source_' + path, ref.get('sha256'), files[path]['sha256'],
                       ref.get('sha256') == files[path]['sha256'], ref.get('locator'))
        result['status'] = 'FAIL' if any(c['status'] == 'FAIL' for c in result['checks']) else 'PASS'
    except (ValueError, KeyError, TypeError) as error:
        result.update(status='UNEVALUABLE', error=str(error))
    result['input_fingerprint'] = identity(result['source_hashes'])
    return result
