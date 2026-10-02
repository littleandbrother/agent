"""Pinned allowlist and inert evidence checks. No imports of collected code."""
import hashlib
import json
import math
import re

VERSION = "1.0.0"
SCHEMA = "native-evidence-bundle-v1"
EVIDENCE_REL = "verification/closed-simulation-20260930"
SOURCE_COMMIT = '338d60384d5805abf1e02252a4513860066a2c39'
EXPECTED_IMPLEMENTATION = {'solver.py': 'c6e09edd277f8014fc6c410df70ec967c71863108fcc4e1fe12362bb49784782', 'native.py': 'a2e2937aa9aa0b5aecf6a98ea29f37185f6355c315c5560d08df1c3125903c07', 'pipeline.py': '47a848f2216fdd9acda7de5c01ab4505770903f27b73a52a44830a6072e5c2d5', 'contracts.py': '00d7ffea6447f22515cc95a5a816a67ea3823bec533f87a2146a682370f638d5', 'cache.py': '82eb4b01dbe1e47fa737059bdde62116108fe0562f9cf9618a72423e3c594ea5', 'cli.py': 'ecca226de3817009ff3aa9c00e23fa21755b88ba3f7b1c6eb53225e5134f6371', '__init__.py': '07b306e3cca8e02b2c307b6347cd17ecb20455335e45bfefa08af07af419e46a', 'program.c': '9fe95cfc2f66235963f9c49d1d15f4bd46185513203a7b9766b88134aff35baf'}
EXPECTED_RUNNER = 'af223c3f1929f808f5792d5254b7f66797af5f8807393be9af475606d1452912'
DEFAULT_SPEC = {'schema_version': 'closed-simulation-spec-v1', 'mechanical': {'gap_mm': 48.0, 'opening_s': 2.0, 'angle_deg': 65.0, 'remanence_T': 1.25, 'damping_ratio': 0.02}, 'circuit': {'cin_uF': 47.0, 'cout_uF': 100.0, 'initial_vin_V': 0.0, 'diagnostic_input_A': 0.0}, 'firmware': {'interval_ms': 100.0, 'boot_ms': 53.8, 'init_ms': 13.0, 'tx_ms': 5.0, 'boot_mA': 0.41, 'init_mA': 1.596, 'tx_mA': 3.659, 'sleep_uA': 2.0, 'reset_uA': 0.3}, 'link': {'loss_probability': 0.0, 'seed': 17, 'scan_duty': 1.0}, 'solver': {'max_step_s': 5e-05, 'firmware_step_s': 0.0001, 'reltol': 0.0001, 'max_coupling_iterations': 8}, 'presentation': {'camera_deg': 35.0}}
TOP_FILES = ['final-receipt.json', 'acceptance-v2/receipt.json', 'acceptance-v2/cases.json', 'acceptance-v2/uncertainty.json', 'acceptance-v2/schema-validation.json']
CASES = ['baseline', 'positive-module']
CASE_FILES = ['result.json', 'design-spec.json', 'convergence.json', 'coupling-iterations.json', 'energy.json', 'receiver.json', 'program.csv', 'waveform.csv', 'system.cir', 'trace.jsonl', 'policy.h', 'program.c', 'magnetic-confirmation.json']
STAGE_FILES = {'beam': ['checkpoint.json', 'rom.json', 'DoorBeam.java', 'solve.log', 'solver.log'], 'force': ['checkpoint.json', 'force-table.npz', 'force-domain.json'], 'firmware': ['checkpoint.json', 'build-receipt.json', 'program.c', 'policy.h', 'receiver.py', 'host-build.log', 'arm-build.log', 'compiler.log'], 'magnetic-confirmation': ['checkpoint.json', 'magnetic-confirmation.json', 'DoorMagnetic.java', 'solve.log', 'solver.log'], 'joint': ['checkpoint.json', 'solve.json', 'coupling-iterations.json', 'energy.json', 'program.csv', 'receiver.json', 'system.cir', 'system.log', 'load.pwl'], 'numerical': ['checkpoint.json', 'solve.json', 'coupling-iterations.json', 'energy.json', 'program.csv', 'receiver.json', 'system.cir', 'system.log', 'load.pwl']}
PASSIVE_FILES = ["solve.json", "waveform.csv", "system.cir", "system.log"]
PASSIVE_CASES = ["passive-100000", "passive-1000000"]
KEY_RE = re.compile(r"[0-9a-f]{64}\Z")

def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def valid_path(value):
    return (isinstance(value, str) and len(value) <= 512 and not value.startswith('/')
            and all(re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', p) and p not in ('.', '..')
                    for p in value.split('/')))


def load_json(data):
    """Strict data-only JSON, rejecting duplicate keys and non-finite constants."""
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('Duplicate JSON key')
            result[k] = v
        return result
    def bad_constant(s):
        raise ValueError('Non-finite JSON constant: ' + s)
    def finite_float(s):
        value = float(s)
        if not math.isfinite(value):
            raise ValueError('Non-finite JSON number')
        return value
    return json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad_constant, parse_float=finite_float)


def selected_paths(json_objects, raw='none', passive=False, passive_raw=False, model_interface=False):
    """Never follow paths supplied by evidence; only validated stage keys expand this list."""
    paths = set(TOP_FILES)
    if model_interface:
        paths.add('native-model-interface.json')
    unresolved = []
    for case in CASES:
        base = 'acceptance-v2/' + case
        paths.update(base + '/' + n for n in CASE_FILES)
        r = json_objects.get(base + '/result.json')
        stages = r.get('stages', {}) if isinstance(r, dict) else {}
        for stage, names in STAGE_FILES.items():
            record = stages.get(stage) if isinstance(stages, dict) else None
            key = record.get('key') if isinstance(record, dict) else None
            if not isinstance(key, str) or not KEY_RE.fullmatch(key):
                unresolved.append({'case': case, 'stage': stage, 'reason': 'missing_or_invalid_stage_key'})
                continue
            prefix = 'acceptance-v2/cache/' + stage + '/' + key + '/'
            paths.update(prefix + n for n in names)
            if stage in ('joint', 'numerical') and (raw == 'all' or raw == case):
                paths.add(prefix + 'system.raw')
    if passive:
        for case in PASSIVE_CASES:
            paths.update('acceptance-v2/' + case + '/' + n for n in PASSIVE_FILES)
            if passive_raw:
                paths.add('acceptance-v2/' + case + '/system.raw')
    return sorted(paths), unresolved


def validate_evidence(objects, records, expected_results=None, model_interface=False):
    """Consistency checks, not solver execution, attestation or scientific acceptance."""
    checks = []
    def add(name, state, detail=None):
        row = {'check': name, 'status': state}
        if detail is not None:
            row['detail'] = detail
        checks.append(row)
    def eq(name, a, b):
        add(name, 'pass' if json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False) else 'fail')
    def get_obj(path):
        value = objects.get(path)
        if not isinstance(value, dict):
            add(path, 'missing' if path not in records else 'fail', 'JSON object unavailable')
            return None
        return value
    def artifact_list(prefix, listed):
        if not isinstance(listed, list) or len(listed) > 10000:
            add(prefix + ':artifact_manifest', 'fail', 'Invalid artifact list')
            return
        seen = set()
        for f in listed:
            name = f.get('path', f.get('name')) if isinstance(f, dict) else None
            if not valid_path(name) or name in seen:
                add(prefix + ':artifact_manifest', 'fail', 'Unsafe or duplicate artifact path; never followed')
                continue
            seen.add(name)
            row = records.get(prefix + '/' + name)
            if row is not None:
                eq(prefix + '/' + name + ':upstream_hash', row['sha256'], f.get('sha256'))
                eq(prefix + '/' + name + ':upstream_bytes', row['bytes'], f.get('bytes'))
        for name in records:
            if name.startswith(prefix + '/'):
                suffix = name[len(prefix) + 1:]
                if suffix not in ('checkpoint.json', 'result.json') and suffix not in seen:
                    add(name + ':upstream_listing', 'fail', 'Collected artifact is not listed upstream')
    interface_report = {'status': 'not_requested', 'model_authenticity': 'not_independently_verified'}
    interface = None
    if model_interface:
        interface = get_obj('native-model-interface.json')
        if interface is None:
            interface_report['status'] = 'missing'
        else:
            from model_interface import validate_interface
            try:
                interface_report = validate_interface(interface)
                add('model_interface:declaration_structure', 'pass')
            except (ValueError, TypeError, KeyError):
                interface_report['status'] = 'invalid'
                add('model_interface:declaration_structure', 'fail')
                interface = None
    acceptance = get_obj('acceptance-v2/receipt.json')
    cases = get_obj('acceptance-v2/cases.json')
    if acceptance is not None:
        eq('acceptance:implementation', acceptance.get('implementation'), EXPECTED_IMPLEMENTATION)
        eq('acceptance:runner_sha256', acceptance.get('runner_sha256'), EXPECTED_RUNNER)
        eq('acceptance:schema', acceptance.get('schema_version'), 'closed-simulation-acceptance-v1')
    # final-receipt has no published machine-readable schema here: do not invent fields.
    add('final-receipt:interpretation', 'not_performed',
        'Collected as data only; its schema is not established by the reviewed source')
    for case in CASES:
        prefix = 'acceptance-v2/' + case
        r = get_obj(prefix + '/result.json')
        spec = get_obj(prefix + '/design-spec.json')
        if r is None:
            continue
        eq(case + ':schema', r.get('schema_version'), 'closed-simulation-result-v1')
        eq(case + ':model_version', r.get('model_version'), 'door-closed-simulation-v1')
        eq(case + ':implementation', r.get('implementation'), EXPECTED_IMPLEMENTATION)
        if interface is not None:
            tool_hash = r.get('tools', {}).get('pmic_model') if isinstance(r.get('tools'), dict) else None
            if tool_hash is None:
                add(case + ':declared_model_hash_to_result', 'missing')
            else:
                eq(case + ':declared_model_hash_to_result', interface.get('model_sha256'), tool_hash)
        eq(case + ':product_verified', r.get('product_verified'), False)
        if expected_results and case in expected_results:
            eq(case + ':operator_expected_result_sha256', records[prefix + '/result.json']['sha256'], expected_results[case])
        else:
            add(case + ':external_run_anchor', 'not_supplied',
                'No independent run ID/hash was supplied; case path and in-bundle hash links are checked')
        for name, listing in [('cases.json', cases), ('receipt.json', acceptance.get('cases') if acceptance else None)]:
            item = listing.get(case) if isinstance(listing, dict) else None
            if not isinstance(item, dict):
                add(case + ':' + name + ':result_link', 'missing')
            else:
                eq(case + ':' + name + ':result_sha256', item.get('result_sha256'), records[prefix + '/result.json']['sha256'])
                for key in ('run_status', 'physics_hash', 'metrics'):
                    eq(case + ':' + name + ':' + key, item.get(key), r.get(key))
        artifact_list(prefix, r.get('artifacts'))
        if spec is not None:
            expected_spec = load_json(json.dumps(DEFAULT_SPEC).encode())
            if case == 'positive-module':
                expected_spec['circuit']['diagnostic_input_A'] = .001
            eq(case + ':input_contract', spec, expected_spec)
            try:
                eq(case + ':physics_hash', r.get('physics_hash'), digest({
                    'spec': {k: v for k, v in spec.items() if k != 'presentation'},
                    'implementation': r.get('implementation'), 'tools': r.get('tools')}))
                eq(case + ':presentation_hash', r.get('presentation_hash'), digest(spec.get('presentation')))
            except (ValueError, TypeError, RecursionError):
                add(case + ':identity_digest', 'fail')
        stages = r.get('stages')
        model_versions = r.get('model_versions')
        if not isinstance(stages, dict) or not isinstance(model_versions, dict):
            add(case + ':stage_structure', 'fail')
            continue
        for stage in STAGE_FILES:
            row = stages.get(stage)
            key = row.get('key') if isinstance(row, dict) else None
            if not isinstance(key, str) or not KEY_RE.fullmatch(key):
                add(case + ':' + stage + ':key', 'missing' if row is None else 'fail')
                continue
            eq(case + ':' + stage + ':model_versions', model_versions.get(stage), key)
            sp = 'acceptance-v2/cache/' + stage + '/' + key
            cp = get_obj(sp + '/checkpoint.json')
            if cp is None:
                continue
            eq(case + ':' + stage + ':checkpoint_key', cp.get('key'), key)
            eq(case + ':' + stage + ':checkpoint_stage', cp.get('stage'), stage)
            eq(case + ':' + stage + ':checkpoint_schema', cp.get('schema_version'), 'simulation-checkpoint-v1')
            try:
                eq(case + ':' + stage + ':inputs_digest', digest({'stage': stage, 'inputs': cp.get('inputs')}), key)
            except (ValueError, TypeError, RecursionError):
                add(case + ':' + stage + ':inputs_digest', 'fail')
            artifact_list(sp, cp.get('files'))
            inputs = cp.get('inputs')
            if not isinstance(inputs, dict):
                add(case + ':' + stage + ':inputs_structure', 'fail')
                continue
            if spec is not None:
                if stage == 'joint':
                    eq(case + ':joint:input_spec', inputs.get('spec'), {k: v for k, v in spec.items() if k != 'presentation'})
                    eq(case + ':joint:dependencies', inputs.get('dependencies'),
                       {s: model_versions.get(s) for s in ('cad', 'beam', 'force', 'firmware')})
                    eq(case + ':joint:solver', inputs.get('solver'), EXPECTED_IMPLEMENTATION['solver.py'])
                elif stage == 'numerical':
                    eq(case + ':numerical:parent_joint', inputs.get('joint'), model_versions.get('joint'))
                    eq(case + ':numerical:solver', inputs.get('solver'), EXPECTED_IMPLEMENTATION['solver.py'])
                    settings = dict(spec['solver']) if isinstance(spec.get('solver'), dict) else {}
                    if all(type(settings.get(k)) in (int, float) for k in ('max_step_s', 'firmware_step_s', 'reltol')):
                        for k in ('max_step_s', 'firmware_step_s', 'reltol'):
                            settings[k] /= 2
                        eq(case + ':numerical:settings', inputs.get('settings'), settings)
                    else:
                        add(case + ':numerical:settings', 'fail')
                elif stage == 'firmware':
                    eq(case + ':firmware:config', inputs.get('config'), spec.get('firmware'))
                    eq(case + ':firmware:program', inputs.get('program'), EXPECTED_IMPLEMENTATION['program.c'])
                elif stage == 'force':
                    mechanical = spec.get('mechanical', {})
                    if isinstance(mechanical, dict):
                        eq(case + ':force:mechanical', inputs.get('mechanical'), {k: mechanical.get(k) for k in ('gap_mm', 'remanence_T')})
                elif stage == 'magnetic-confirmation':
                    mechanical = spec.get('mechanical', {})
                    if isinstance(mechanical, dict):
                        eq(case + ':magnetic:gap', inputs.get('gap_mm'), mechanical.get('gap_mm'))
                        eq(case + ':magnetic:remanence', inputs.get('br'), mechanical.get('remanence_T'))
                if stage in ('beam', 'force', 'firmware', 'magnetic-confirmation'):
                    eq(case + ':' + stage + ':builder', inputs.get('builder'), EXPECTED_IMPLEMENTATION['native.py'])
            authoritative = {'beam': 'rom.json', 'force': 'force-domain.json', 'firmware': 'build-receipt.json',
                             'joint': 'solve.json', 'numerical': 'solve.json',
                             'magnetic-confirmation': 'magnetic-confirmation.json'}[stage]
            native_value = get_obj(sp + '/' + authoritative)
            if native_value is not None:
                eq(case + ':' + stage + ':duplicate_value_consistency', cp.get('value'), native_value)
                if stage == 'joint':
                    eq(case + ':joint_metrics', r.get('metrics'), native_value)
                if stage in ('joint', 'numerical'):
                    energy = get_obj(sp + '/energy.json')
                    if energy is not None:
                        eq(case + ':' + stage + ':energy_ledger', native_value.get('energy_ledger'), energy)
            # The exact copied case files must match their producing stage bytes.
            copies = {'joint': ['waveform.csv', 'program.csv', 'receiver.json', 'energy.json', 'system.cir', 'coupling-iterations.json'],
                      'firmware': ['program.c', 'policy.h'],
                      'magnetic-confirmation': ['magnetic-confirmation.json']}.get(stage, [])
            for name in copies:
                a, b = records.get(prefix + '/' + name), records.get(sp + '/' + name)
                if a and b:
                    eq(case + ':' + stage + ':' + name + ':copy_hash', a['sha256'], b['sha256'])
        ledger = objects.get(prefix + '/energy.json')
        if isinstance(ledger, dict):
            eq(case + ':energy_ledger_copy', r.get('energy_ledger'), ledger)
    return {
        'source_binding': 'fail' if any(c['status'] == 'fail' for c in checks)
                          else 'incomplete' if any(c['status'] == 'missing' for c in checks) else 'pass',
        'scientific_validation': 'not_performed',
        'model_interface': interface_report,
        'authentication': 'not_provided',
        'checks': checks,
        'limitations': [
            'Hashes prove byte identity and internal consistency, not authenticity or that a solver ran.',
            'The source commit is a pinned comparison target, not a native execution attestation.',
            'No collected code, NPZ contents, licensed model or solver is executed.',
            'CSV/JSON/log checks do not independently recompute RAW extrema, transient energy or sub-grid brownouts.',
            'RAW presence does not mean RAW parsing, physical qualification, COMSOL convergence or a native rerun passed.',
            'The pinned deck .save omits V(vin2), V(cap), V(vin,cap), I(Ccap), I(Cvin2) and auxiliary-rail currents. Existing RAW cannot establish auxiliary-rail startup or charge/discharge timing; a NEW versioned observation fixture is required.',
            'Bounded credential-marker scans reduce accidental sharing but cannot prove arbitrary content is secret-free.',
            'The two case names, result hashes and physics hashes provide run association; no nonexistent task_id/run_id is invented.'
        ]
    }
