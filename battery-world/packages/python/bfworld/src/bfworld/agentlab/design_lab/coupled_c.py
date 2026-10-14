"""Prospective C phase: actual candidate C ↔ native D5 circuit/ROM.

The old fixed-envelope phase and its receipts remain unchanged. Each trial
starts a fresh isolated program instance. Only converged final events enter
receiver validation; provisional transmissions never become deliveries.
"""
import copy
import csv
import json
from pathlib import Path
import re
import shutil
import numpy as np
from . import builder, case_c, contracts as lab, native_solver, native_witness, model_catalog
from ..store import identity
from ..door_selfpower import contracts as d5, solver, pipeline
from ..simulation_chain.contracts import ChainError

VERSION = 'bf-native-coupled-C-v2'
SCOPE = 'C-F1-native-D5-candidate-program-circuit-v2'


def validation_id():
    paths = [Path(__file__), Path(builder.__file__), Path(case_c.__file__),
             Path(solver.__file__), Path(pipeline.__file__), Path(lab.__file__),
             Path(native_solver.__file__), Path(native_witness.__file__), Path(model_catalog.__file__)]
    return 'Venv-' + identity({'version': VERSION,
                              'code': {str(p.name): lab.sha(p) for p in paths},
                              'D5_executor': d5.template_hash()})


def environment(reference):
    from .baseline import environment as baseline_environment
    base = baseline_environment(reference)
    root = Path(base['root'])
    manifest = json.loads((root / 'system-manifest.json').read_text())
    source_stage = next(s for s in manifest['stages'] if s['stage'] == 'cad/force')
    # D5 already contains the exact reused force assets. Its historical source
    # directory may be archived; use these bound copies, never rebuild them.
    force = root / 'force/force-table.npz'
    domain = root / 'force/force-domain.json'
    if lab.sha(force) != source_stage['force_sha256']:
        raise ValueError('C_MAGNETIC_FORCE_IDENTITY_DRIFT')
    if not json.loads(domain.read_text())['interpolation_passed']:
        raise ValueError('C_MAGNETIC_FORCE_NOT_QUALIFIED')
    for path, digest in manifest['source_dependencies'].items():
        if lab.sha(path) != digest:
            raise ValueError('C_NATIVE_DEPENDENCY_DRIFT:' + path)
    physical = json.loads((root / 'design-spec.json').read_text())
    d5.verify_design(physical)
    value = {**base, 'schema_version': VERSION, 'mode': 'native-coupled-C',
             'parent_environment_id': base['environment_id'],
             'native_model': {'physical_design': physical,
                 'rom': {'path': str(root / 'rom.json'), 'sha256': lab.sha(root / 'rom.json')},
                 'force': {'path': str(force), 'sha256': lab.sha(force)},
                 'force_domain': {'path': str(domain), 'sha256': lab.sha(domain)},
                 'source_dependencies': manifest['source_dependencies']},
             'solver_version': d5.template_hash(), 'builder_version': builder.VERSION,
             'supported': 'Candidate C/H and supported D5 circuit choices, actual cold native circuit/program waveform fixed point with finer-step confirmation.',
             'unqualified': ['arbitrary target ELF/HEX peripheral execution', 'physical RF',
                 'new beam/material geometry', 'uncalibrated target activity-current mapping',
                 'unqualified vendor model/backend migration', 'full A/B physical models'],
             'calibration': 'COMSOL-derived ROM and nominal vendor circuit; hardware NOT_TESTED'}
    value.pop('environment_id')
    return {**value, 'environment_id': 'E-' + identity(value)}


def verify_environment(value):
    if value.get('schema_version') != VERSION or value.get('mode') != 'native-coupled-C':
        raise ValueError('C_COUPLED_ENVIRONMENT_REQUIRED')
    if value['environment_id'] != 'E-' + identity({k: v for k, v in value.items() if k != 'environment_id'}):
        raise ValueError('C_COUPLED_ENVIRONMENT_TAMPER')
    if value['solver_version'] != d5.template_hash():
        raise ValueError('C_COUPLED_EXECUTOR_CHANGED')
    model = value['native_model']
    for key in ('rom', 'force', 'force_domain'):
        if lab.sha(model[key]['path']) != model[key]['sha256']:
            raise ValueError('C_MODEL_ASSET_DRIFT:' + key)
    for path, digest in model['source_dependencies'].items():
        if lab.sha(path) != digest:
            raise ValueError('C_NATIVE_DEPENDENCY_DRIFT:' + path)
    d5.verify_design(model['physical_design'])
    return value


def contract(env):
    value = lab.contract(env['environment_id'], validation_id())
    value.pop('task_id')
    value.update(schema_version=VERSION, scope=SCOPE,
                 supported_actions=[*value['supported_actions'],
                     'edit device.json: D5 circuit, extraction, gate, gate_switch'],
                 fixed=['D5 beam/ROM/magnetic motion and initial state', '100us firmware clock',
                        'declared stage-current envelope', 'virtual sensor and packet receiver'],
                 load_policy='Exact unchanged native witness is reused. Changed stage timing or supported circuit choices invoke new native supply/program iteration and finer-step confirmation.',
                 execution_level='Native reciprocal ROM and vendor circuit + isolated compiled application C. ARM object is build evidence only; target peripherals/current calibration/RF remain unqualified.')
    return {**value, 'task_id': 'task-C-' + identity(value)[:20]}


def physical_design(sources, env):
    base = env['native_model']['physical_design']
    candidate = {k: copy.deepcopy(base['base_design'][k]) for k in ('mechanical', 'circuit', 'firmware')}
    candidate.update({k: copy.deepcopy(base[k]) for k in ('extraction', 'gate', 'application')})
    if 'gate_switch' in base:
        candidate['gate_switch'] = base['gate_switch']
    try:
        changed = json.loads(sources.get('device.json', '{}'))
    except (ValueError, TypeError) as exc:
        raise ValueError('C_DEVICE_JSON_INVALID') from exc
    if not isinstance(changed, dict) or set(changed) - {'circuit', 'extraction', 'gate', 'gate_switch'}:
        raise ValueError('C_DEVICE_ACTION_NOT_SUPPORTED')
    candidate.update(changed)
    return d5.normalize(candidate)


def snapshot(task, sources, env, parent=None):
    if not isinstance(sources, dict) or 'program.c' not in sources or not 1 <= len(sources) <= 17:
        raise ValueError('DESIGN_SOURCE_REQUIRED')
    for name, text in sources.items():
        if (name != 'device.json' and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*\.(c|h)', name)) or not isinstance(text, str):
            raise ValueError('DESIGN_SOURCE_PATH_DENIED')
    if sum(len(t.encode()) for t in sources.values()) > 128000:
        raise ValueError('DESIGN_SOURCE_SIZE')
    physical = physical_design(sources, env)
    value = {'schema_version': VERSION, 'task_id': task['task_id'],
             'environment_id': task['environment_id'], 'scope': task['scope'],
             'parent': parent, 'sources': sources,
             'dimensions': {'application': identity({n: t for n, t in sources.items() if n != 'device.json'}),
                            'physical': physical['design_id']}}
    return {**value, 'design_id': 'D-' + identity(value)}


def build(design, directory, env):
    verify_environment(env)
    receipt = case_c.build(design, directory)
    directory = Path(directory)
    physical = physical_design(design['sources'], env)
    candidate = builder.candidate({
        'geometry': {'reference': env['files']['assembly.step']},
        'physical_bindings': {'rom': env['native_model']['rom']['sha256'],
                              'force': env['native_model']['force']['sha256']},
        'circuit': {'design': physical['design_id']},
        'firmware': {'sources': design['dimensions']['application']},
        'algorithm': {'implementation': 'included in candidate C/H'},
        'hardware': {'target': receipt['compiler']['target'], 'load_model': case_c.CURRENT},
        'scenario': {'motion': physical['base_design']['frozen']['task']}}, env['environment_id'])
    plan = builder.plan(candidate, {n: env['solver_version'] if n != 'target_build' else receipt['compiler']
                                   for n in builder.DEPENDENCIES})
    lab.sealed(directory / 'candidate-components.json', candidate)
    lab.sealed(directory / 'candidate-build-plan.json', plan)
    lab.sealed(directory / 'candidate-device.json', physical)
    receipt['files'].update({n: lab.sha(directory / n) for n in
                            ('candidate-components.json', 'candidate-build-plan.json', 'candidate-device.json')})
    if 'device.json' in design['sources']:
        receipt['files']['device.json'] = lab.sha(directory / 'device.json')
    receipt.update(schema_version=VERSION, candidate_id=candidate['candidate_id'], build_plan_id=plan['plan_id'])
    receipt.pop('build_id')
    return {**receipt, 'build_id': 'B-' + identity(receipt)}


def run_program(directory, grid, supply, good, event, label):
    """Pure participant logic runs in a fresh restricted process each trial."""
    source = directory / (label + '-input.csv')
    with source.open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['time_s', 'supply_V', 'pgood_V', 'state', 'current_A'])
        writer.writerows(zip(grid, supply, good, np.zeros(len(grid)), np.zeros(len(grid))))
    trace, packets = directory / (label + '.csv'), directory / (label + '-tx.csv')
    case_c.command([directory / 'application', source, trace, packets,
                    str(event['time_s']), str(event['event_id']), str(event['kind'])], directory, [])
    with trace.open() as stream:
        rows = list(csv.DictReader(stream))
    with packets.open() as stream:
        events = [{'time_s': float(r['time_s']), 'payload_hex': r['payload_hex']} for r in csv.DictReader(stream)]
    if len(rows) != len(grid) or [float(r['time_s']) for r in rows] != list(grid):
        raise ValueError('C_EXECUTION_TIME_MISMATCH')
    states = np.array([int(r['state']) for r in rows])
    current = np.array([float(r['current_A']) for r in rows])
    if not all(0 <= state < len(case_c.CURRENT) for state in states):
        raise ValueError('C_STATE_INVALID')
    if not np.allclose(current, np.array(case_c.CURRENT)[states], rtol=0, atol=1e-14):
        raise ValueError('C_UNQUALIFIED_CURRENT_MODEL')
    if np.any((np.asarray(supply) < 1.8) & (states != 0)):
        raise ValueError('C_BROWNOUT_RESET_INVALID')
    return current, states, events


def virtual_receive(_directory, events, link):
    # The actual wire format, receiver delivery and application de-dup remain
    # independently checked by case_c.evaluate after convergence.
    if link.get('loss_probability', 0) != 0:
        return {'events': [], 'delivered': []}
    valid = [e for e in events if case_c.decode(e['payload_hex']) is not None]
    return {'events': valid, 'delivered': valid, 'scope': 'virtual packet link; physical RF NOT_CHECKED'}


def ensure_stable(task, env, version):
    verify_environment(env)
    if task['validation_id'] != version or validation_id() != version:
        raise ValueError('C_EXECUTOR_DRIFT_RECHECK_REQUIRED')


def execute(task, design, receipt, directory, env, *, native_solve=None, trusted_witness=None):
    version=validation_id()
    ensure_stable(task,env,version)
    if task['environment_id']!=env['environment_id'] or design['task_id']!=task['task_id']:
        raise ValueError('C_TASK_ENVIRONMENT_BINDING')
    verify_environment(env)
    directory = Path(directory)
    case_c.verify_build(design, receipt, directory)
    physical = physical_design(design['sources'], env)
    replay = case_c.execute(task, design, receipt, directory, env)
    unchanged = physical == env['native_model']['physical_design']
    if replay['power_fixed_point'] and unchanged:
        replay.update(schema_version=VERSION, scope=SCOPE,
                      native_solve='REUSED_EXACT_LOAD_WITNESS', native_checks={'unchanged_native_witness': True})
        replay.pop('execution_id')
        ensure_stable(task,env,version)
        return {**replay, 'execution_id': 'X-' + identity(replay)}
    reused=native_witness.reuse(trusted_witness,task,design,receipt,directory,env,physical)
    if reused is not None:
        ensure_stable(task,env,version)
        return reused
    storage = pipeline.storage_observation(directory)
    if not storage['ready']:
        raise ValueError('C_NATIVE_STORAGE_UNAVAILABLE')
    rom = json.loads(Path(env['native_model']['rom']['path']).read_text())
    force = Path(env['native_model']['force']['path'])
    solve = native_solve or native_solver.solve  # Injection reserved to offline tests.
    counts = []
    for name, scale in [('joint', 1.), ('time-step', .5)]:
        target = directory / name
        target.mkdir()
        count = [0]
        def execute_candidate(_firmware, grid, supply, good):
            label = name + '-trial-' + str(count[0])
            count[0] += 1
            return run_program(directory, grid, supply, good, task['event'], label)
        try:
            summary = solve(target, physical, rom, force, directory, max_step_scale=scale,
                            program_executor=execute_candidate, receiver_executor=virtual_receive)
        except Exception as error:
            # Failed native calls need not reach a program callback. Preserve
            # actual logs and partial accounting rather than reporting zero.
            lab.sealed(directory/'native-execution-failure.json',{
                'task_id':task['task_id'],'design_id':design['design_id'],'phase':name,
                'error':type(error).__name__+': '+str(error),
                'completed_program_trials':counts+[count[0]],
                'new_native_solver_calls':None,
                'accounting':'Use retained per-iteration native process logs; callback count alone cannot count failed backend runs.',
                'retained_files':{str(p.relative_to(directory)):lab.sha(p)
                    for p in target.rglob('*') if p.is_file() and p.suffix in ('.log','.json','.cir')},
                'physical_verified':False})
            raise
        counts.append(count[0])
        if name == 'joint':
            coarse = summary
        else:
            fine = summary
    step = pipeline.confirmation_check(coarse, fine)
    lab.sealed(directory / 'native-time-step-check.json', step)
    shutil.copyfile(directory / 'joint/program.csv', directory / 'coupled-program.csv')
    witness = {**env, 'root': str(directory), 'files': {'program.csv': lab.sha(directory / 'coupled-program.csv')}}
    # case_c's runner consumes the exact converged grid. Preserve it separately
    # from the baseline program.csv; no native reference file is written.
    shutil.copyfile(directory / 'coupled-program.csv', directory / 'program.csv')
    final = case_c.execute(task, design, receipt, directory, witness)
    checks = {'rom_domain': coarse['peak_tip_mm'] <= 8.,
              'energy_balance': coarse['numerical_energy_passed'],
              'drive_balance': coarse['drive_ledger']['numerical_passed'],
              'electrical_energy_lower_bound': coarse['energy_ledger']['energy_lower_bound_passed'],
              'component_ratings': coarse['ratings']['passed'],
              'program_power_fixed_point': coarse['coupling_converged'], 'time_step': step['passed']}
    final.update(schema_version=VERSION, power_fixed_point=final['power_fixed_point'] and all(checks.values()),
                 native_solve='NEW_NATIVE_COUPLED_FIXED_POINT', new_native_solver_calls=sum(counts),
                 native_checks=checks, scope=SCOPE, solver_input_design_id=physical['design_id'],
                 provisional_events_committed=False, coupling_iteration_count=counts,
                 native_metrics={'coarse': coarse, 'fine': fine},
                 native_dependencies=[])
    for name in ('joint', 'time-step'):
        for path in sorted((directory / name).rglob('*')):
            if path.is_file() and path.suffix not in ('.gz', '.xz', '.raw'):
                final['observations'][str(path.relative_to(directory))] = lab.sha(path)
        for path in sorted((directory / name).rglob('*.archive.json')):
            archive = json.loads(path.read_text())
            final['native_dependencies'].append({'path': str(path.parent / archive['archive_name']),
                'sha256': archive['archive_sha256'], 'original_sha256': archive['original_sha256'],
                'readback_verified': archive['readback_verified']})
    final['observations'].update({n: lab.sha(directory / n) for n in
                                 ('native-time-step-check.json', 'coupled-program.csv')})
    final.pop('execution_id')
    ensure_stable(task,env,version)
    return {**final, 'execution_id': 'X-' + identity(final)}


def probe(task, design, receipt, directory, env, execution, event, stem):
    directory = Path(directory)
    witness = env
    if execution['native_solve'] in ('NEW_NATIVE_COUPLED_FIXED_POINT','REUSED_QUALIFIED_NATIVE_WITNESS'):
        witness = {**env, 'root': str(directory), 'files': {'program.csv': lab.sha(directory / 'program.csv')}}
    return case_c.execute(task, design, receipt, directory, witness, event=event, stem=stem)


def evaluate(task, design, receipt, execution, env):
    if execution['execution_id'] != 'X-' + identity({k: v for k, v in execution.items() if k != 'execution_id'}):
        raise ValueError('C_EXECUTION_RECEIPT_TAMPER')
    value = case_c.evaluate(task, design, receipt, execution, env)
    value['public_reason'] = 'Actual candidate source/build, current/supply fixed point, native numerical and rating scope, and virtual receiver identity/deadline independently checked.'
    value['native_checks'] = execution.get('native_checks', {})
    value['check_id'] = 'V-' + identity({k: v for k, v in value.items() if k != 'check_id'})
    return value
