"""Independent task-profile checks over sealed raw execution, without dispatch."""
import csv
import io
import json
import math
from pathlib import Path

from ..store import identity
from .repository import file_hash
from .repository_profiles import system_profile, task_requirements

VERSION = 'task-profile-review-v1'


def evaluator_identity(system):
    cfg = system_profile(system)
    files = [Path(__file__), Path(__file__).with_name('repository_profiles.py'),
             Path(__file__).with_name('repository_task_standards.py')]
    if cfg['adapter'] == 'p01-existing':
        files += [Path(__file__).with_name('repository_validation.py'),
                  Path(__file__).with_name('repository_contracts.py'), Path(__file__).with_name('repository_load.py')]
    elif cfg['adapter'] == 'piezo-reference-v1':
        files += [Path(__file__).with_name('repository_reference_node.py')]
    return {'version': VERSION, 'adapter': cfg['adapter'], 'sources': {f.name: file_hash(f) for f in files}}


def read(repo, system, path):
    ref = system['files'].get(path)
    if not ref: raise ValueError('TASK_INPUT_MISSING: ' + path)
    p = repo.root/'blobs'/ref['sha256']
    if file_hash(p) != ref['sha256']: raise ValueError('TASK_INPUT_CHANGED')
    return p.read_text()


def curve_rows(raw):
    reader = csv.DictReader(io.StringIO(raw))
    if reader.fieldnames != ['x', 'y']: raise ValueError('CURVE_COLUMNS_X_Y_REQUIRED')
    rows = [[float(r['x']), float(r['y'])] for r in reader]
    if len(rows) < 2 or not all(math.isfinite(v) for r in rows for v in r): raise ValueError('CURVE_FINITE_SAMPLES_REQUIRED')
    if any(a[0] >= b[0] for a, b in zip(rows, rows[1:])): raise ValueError('CURVE_AXIS_NOT_INCREASING')
    return rows


def qualification(repo, system, db):
    from .repository_contracts import fingerprint
    required = task_requirements(repo, system, db)['required_gates']
    gates = {}
    execution_id = None
    if system_profile(system)['adapter'] in ('tabulated-curve-v1','piezo-reference-v1'):
        from .repository_task_execution import current_execution
        execution = current_execution(repo, system, db)
        execution_id = execution['id'] if execution else None
    for key, val in system.get('validations', {}).items():
        # Only correctly bound carried records can remain current.
        if val.get('input_fingerprint') == fingerprint(system, key) and val.get('execution_id') == execution_id: gates[key] = dict(val)
    for row in db.execute('SELECT value FROM design_repository_validations WHERE project=? ORDER BY rowid', (system['project_id'],)):
        record = json.loads(row['value'])
        for key, val in record.get('result', {}).get('gates', {}).items():
            if key in required and val.get('input_fingerprint') == fingerprint(system, key) and val.get('execution_id') == execution_id:
                gates[key] = {**val, 'validation_id': record['id'], 'evidence_target': record['target']}
    for key in required: gates.setdefault(key, {'status': 'NOT_CHECKED', 'input_fingerprint': fingerprint(system, key)})
    passed = bool(required) and all(gates[k]['status'] == 'PASS' for k in required)
    return {'schema_version': 'bf-system-qualification-v1', 'system_commit': system['id'],
            'status': 'PASS' if passed else 'REPAIR_REQUIRED' if any(gates[k]['status'] == 'FAIL' for k in required) else 'CHECKS_PENDING',
            'scope': system['task_definition']['scope'], 'task_definition': system['task_definition']['id'],
            'gates': {k: gates[k] for k in required}, 'task_passed': passed,
            'product_passed': passed and system['task_definition']['scope'] == 'digital-product', 'physical': 'NOT_TESTED'}


def evaluate(repo, system):
    from .repository_contracts import fingerprint
    cfg = system_profile(system); task = task_requirements(repo, system); gates = {}
    execution = None
    def record(key, status, result):
        gates[key] = {'status': status, 'findings': result, 'scope': task['scope'], 'input_fingerprint': fingerprint(system, key),
                      'execution_id': execution['id'] if execution else None}
    if cfg['adapter'] == 'p01-existing':
        from .repository_validation import evaluate as p01_evaluate, native_review_reuse
        if task['profile'] == 'p01-digital-v1':
            return p01_evaluate(repo, system)
        # PCB task consumes the native audit only; firmware/energy are unrelated gates.
        for key in task['required_gates']:
            if key == 'delivery_version': continue
            try:
                origin = system.get('inherited_from')
                original = repo.system(origin['project_id'], origin['system_id']) if origin else None
                value = native_review_reuse(repo, system, key, original)
                record(key, value['status'] if value else 'NOT_CHECKED', value or {'missing': 'native audit for these PCB inputs'})
            except (ValueError, KeyError) as e: record(key, 'UNEVALUABLE', {'error': str(e)})
    else:
        from .repository_task_execution import current_execution
        execution = current_execution(repo, system)
        if not execution:
            for key in task['required_gates']:
                if key != 'delivery_version': record(key, 'NOT_CHECKED', {'missing': 'current input execution'})
        elif execution['status'] != 'SUCCEEDED':
            for key in task['required_gates']:
                if key != 'delivery_version': record(key, 'UNEVALUABLE', {'execution': execution['id'], 'error': execution['metrics']})
        elif cfg['adapter'] == 'tabulated-curve-v1':
            # Parse the immutable input independently of the execution metrics.
            reference = curve_rows(read(repo, system, 'reference.csv'))
            observation = curve_rows(read(repo, system, 'observation.csv'))
            aligned = [r[0] for r in reference] == [r[0] for r in observation]
            record('curve_binding', 'PASS' if aligned else 'FAIL', {'samples': [len(reference), len(observation)],
                'axis_units': task['scenario']['axis_units'], 'execution': execution['id']})
            error = max(abs(a[1]-b[1]) for a, b in zip(reference, observation)) if aligned else None
            limit = task['acceptance']['curve_accuracy']['max_abs_error']
            record('curve_accuracy', 'PASS' if error is not None and error <= limit else 'FAIL',
                   {'max_abs_error': error, 'limit': limit, 'execution': execution['id']})
        elif cfg['adapter'] == 'piezo-reference-v1':
            from .repository_reference_node import independent_check
            for key, value in independent_check(repo, system, execution).items(): record(key, value['status'], value)
    for path in system['files']: read(repo, system, path)
    record('delivery_version', 'PASS', {'files': len(system['files']), 'task_definition': task['id']})
    return {'checker': evaluator_identity(system), 'target': system['id'], 'gates': gates,
            'scope': task['scope'], 'status': 'PASS' if all(v['status'] == 'PASS' for v in gates.values()) else 'FAIL',
            'native_jobs_dispatched': 0, 'physical': 'NOT_TESTED'}
