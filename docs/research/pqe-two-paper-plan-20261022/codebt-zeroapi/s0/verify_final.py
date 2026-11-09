"""Read saved evidence only. No controller, numerical kernel, provider or tools."""
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import json
import os
import sqlite3
import time

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
OUT = HERE.parent
OLD = OUT.parent / 'codebt-idea'
APP = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
LAB = APP / 'packages/python/bfworld/src/bfworld/agentlab'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    path = Path(path)
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def verify():
    pre = load(HERE / 'preflight.json')
    a = load(OUT / 'a/EXIT-READBACK.json')
    counter = load(OUT / 'a/counter.json')
    family = load(OLD / 'a/TASKS.json')['conditions']
    tasks = {t['condition_id']: t for t in family}
    debt = load(OLD / 's0/science/05-debt_agent-short-cold/input.json')['design']
    checked = []
    for row in a['audit']:
        label = row['label']
        if label.startswith(('P1-', 'P2-')):
            for entry in row['files']:
                path = OUT / 'a' / entry['name']
                assert path.stat().st_size == entry['bytes']
                assert sha(path) == entry['sha256'], str(path)
                load(path)
                checked.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path)})
            folder = next(p for p in (OUT / 'a').iterdir()
                          if p.is_dir() and p.name.endswith(label))
            inp = load(folder / 'input.json')
            task = inp['task']
            assert task == tasks[task['condition_id']]
            public = load(folder / 'result/public-result.json')
            assert public['task_id'] == task['task_id']
            assert public['task_sha256'] == digest(task)
            if label.startswith('P1-'):
                assert inp['decision']['actual_input']['design_patch'] == {'persistent_queue': True}
                design = {**task['initial_design'], 'persistent_queue': True}
            else:
                design = debt
            assert public['design'] == design
            assert public['model_valid'] is True
            assert public['execution_status'] == 'COMPLETE'
            assert public['public_check']['verdict'] == ('PASS' if label.startswith('P1-') else 'FAIL')
        else:
            folder = next(p for p in (OUT / 'a').iterdir()
                          if p.is_dir() and p.name.endswith(label))
            assert sha(folder / 'stderr') == row['stderr_sha256']
            assert sha(folder / 'input.json') == row['input_sha256']
            if row.get('error_sha256'):
                assert sha(folder / 'error.json') == row['error_sha256']
                assert load(folder / 'error.json')['status'] == 'TOOL_ERROR'
    assert counter['full_attempts'] == 8 and len(counter['rows']) == 8
    assert sum(r['status'] == 'COMPLETE' for r in counter['rows']) == 6
    assert abs(sum(r['elapsed_s'] for r in counter['rows']) - counter['full_wall_s']) < 1e-6
    assert counter['full_wall_s'] <= 1920

    # Compare the frozen source bytes, never import or execute those kernels.
    decisions = [load(p) for p in (OUT / 'a').glob('0[123]-P1-*/result/decision.json')]
    decisions += [load(p) for p in (OUT / 'a').glob('0[678]-P2-*/result/decision.json')]
    assert len(decisions) == 6
    frozen = {}
    for name in ['door_model.py', 'door_program.py', 'engineering.py', 'executor.py',
                 'evaluator.py', 'adapter.py', 'public_projection.py']:
        value = sha(LAB / 'pqe20261022' / name)
        assert all(d['sources'][name] == value for d in decisions), name
        frozen[name] = value
    for name in ['consumer.py', 'firmware.py']:
        value = sha(LAB / 'pqe20261023bold' / name)
        assert all(d['sources']['bold/' + name] == value for d in decisions), name
        frozen['bold/' + name] = value
    cache = load(OUT / 'a/STATIC-GEOMETRY-CACHE-PATCH.json')
    assert sha(ROOT / cache['source']) == cache['new_sha256']
    current_a = load(OUT / 'a/SOURCE-EXIT.json')['current']
    assert current_a['task.py'] == cache['old_sha256']
    for name, value in current_a.items():
        if name != 'task.py':
            assert sha(LAB / 'pqe20261024debt' / name) == value

    dsml = load(HERE / 'model-format-readback.json')
    assert dsml['software_cases'] == dsml['passed'] == 3
    assert sha(dsml['source_path']) == dsml['source_sha256']
    for row in dsml['checks']:
        assert row['status'] == 'PASS'
        if 'source_path' in row:
            assert sha(row['source_path']) == row['source_sha256']
    b = load(OUT / 'b/case-budget.json')
    assert len(b['attempts']) == 7 and {r['case'] for r in b['attempts']} == set(range(1, 8))
    for row in b['attempts']:
        assert row['status'] == 'PASS'
        detail = load(OUT / 'b' / ('case-%02d.json' % row['case']))
        assert detail['status'] == 'PASS'
        assert detail['provider_calls'] == detail['model_episodes'] == detail['full_inputs'] == 0
    cheap_b = sum(r['cheap_numeric'] for r in b['attempts'])
    cheap = counter['cheap_numeric'] + cheap_b
    software = counter['software_cases'] + dsml['software_cases'] + len(b['attempts'])
    assert cheap == 7 <= 8 and software == 12
    assert load(OUT / 'a/MECHANISM-II-QUALIFICATION.json')['new_full_executions'] == 0

    db = sqlite3.connect('file:/Users/depengsu/.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    billing = {}
    for table, key in [('model_requests', 'id'), ('historical_usage_exceptions', 'id'),
                       ('research_model_owners', 'owner'), ('research_model_studies', 'protocol'),
                       ('principals', 'token_hash'), ('grants', 'owner')]:
        rows = [dict(r) for r in db.execute('SELECT * FROM ' + table + ' ORDER BY ' + key)]
        value = {'count': len(rows), 'sha256': digest(rows)}
        assert value == pre['billing_baseline'][table], table
        billing[table] = value
    db.close()
    files = [p for p in OUT.rglob('*') if p.is_file()]
    logical = sum(p.stat().st_size for p in files)
    allocated = sum(p.stat().st_blocks * 512 for p in files)
    available = os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize
    elapsed = time.time() - pre['wall_start_epoch']
    completed_epochs = [r['started_epoch'] + r['elapsed_s'] for r in counter['rows']]
    completed_epochs += [datetime.fromisoformat(r['completed_at']).timestamp() for r in b['attempts']]
    completed_epochs.append(datetime.fromisoformat(dsml['at']).timestamp())
    execution_elapsed = max(completed_epochs) - pre['wall_start_epoch']
    assert allocated < pre['retained_output_cap_bytes'] and available >= 10400000000
    # A later readback does not reopen execution or consume its expired budget.
    assert 0 <= execution_elapsed < pre['wall_cap_s']
    return {'schema': 'codebt-zeroapi-s0-exit-readback-v1', 'status': 'PASS',
        'at': datetime.now(timezone.utc).isoformat(), 'scope': 'Saved bytes, bindings, verdicts, counters and ledger only; no rerun.',
        'canonical_result_files': checked, 'tasks_and_designs_exact': True,
        'all_six_model_valid': True, 'P1_pass': 3, 'P2_fail': 3,
        'frozen_original_kernels': frozen, 'post_P2_cache_patch_separate': True,
        'new_full_attempts': 8, 'full_complete': 6, 'full_tool_errors': 2,
        'full_child_wall_s': counter['full_wall_s'], 'cheap_numeric': cheap,
        'B_geometry_actual_evaluations': cheap_b,
        'B_geometry_cache_hits': sum(r['geometry_cache_reuses'] for r in b['attempts']),
        'software_cases': software, 'software_pass': software,
        'new_provider_requests': 0, 'new_model_episodes': 0, 'api_usd': 0,
        'billing_all_six_tables_unchanged': billing,
        'storage': {'available_bytes': available, 'logical_bytes': logical,
                    'allocated_bytes': allocated, 'retained_cap_bytes': 40000000,
                    'active_reclaimed_bytes': 0, 'new_backups': 0},
        'package_wall_elapsed_s': elapsed, 'execution_wall_elapsed_s': execution_elapsed,
        'wall_cap_s': 2400, 'readback_does_not_reopen_execution': True,
        'broad_suite_or_init': False, 'repository_health_claim': False,
        'integration_boundary': 'Public bridge is exercised in saved-result B controller cases. DSML is saved-payload normalization only. Original closed FamilyBroker and paid planner transport have not loaded these new helpers.'}


if __name__ == '__main__':
    result = verify()
    (HERE / 'final-readback.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['canonical_result_files', 'frozen_original_kernels', 'billing_all_six_tables_unchanged']}, ensure_ascii=False))
