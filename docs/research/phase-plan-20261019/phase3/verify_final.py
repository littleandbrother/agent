"""Read back sealed evidence and billing; never dispatch a model or simulation."""
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
APP = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
LOCAL = Path.home() / '.local/share'
OUT = LOCAL / 'bf-phase3-20261020'
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.campaign20261019.phase1 import ledger, encoded
from bfworld.agentlab.campaign20261019.common import digest, file_hash, seal


def read(path):
    return json.loads(Path(path).read_text())


def check_files(entries):
    for path, value in entries.items():
        expected = value if isinstance(value, str) else value['sha256']
        assert file_hash(path) == expected, path


def verify():
    plan = read(HERE / 'protocol.json')
    repeat = read(HERE / 'formal-repeat-freeze.json')
    assert repeat['formal_repetitions'] == 3 and repeat['repeat_selection_events'] == 1
    expected = {x['id'] for x in plan['episodes']
                if x['stage'] == 'pilot' or x['replicate'] <= 3}
    observed = {p.name for p in (OUT / 'episodes').iterdir() if p.is_dir()}
    assert expected == observed and len(expected) == 140
    records, bindings, chain = [], {}, []
    for name in sorted(expected):
        root = OUT / 'episodes' / name
        protocol = read(root / 'protocol.json')
        result = read(root / 'episode-result.json')
        assert digest(protocol) == result['protocol_sha256'], name
        assert result['status'] in ('ACTUAL_PROSPECTIVE_SUBMITTED', 'INCOMPLETE_OR_STOPPED'), name
        assert result['fresh_task_entry'] and result['reported_models'] == ['deepseek-flash'], name
        assert not result['trace_audit']['unmatched_executed_inputs'], name
        assert not result['accounting']['unknown_or_missing_usage'], name
        assert read(root / 'provider-costs.json')['unsettled_reserved_usd'] == 0, name
        assert protocol['native_dispatches'] == 0
        receipt = read(root / 'protected-ledger-readback.json')
        assert receipt['old_unchanged'] and receipt['new_rows'] == result['accounting']['requests'], name
        chain.append((receipt['old_rows'], receipt['new_rows']))
        for path, sha in protocol['bound_files'].items():
            assert path not in bindings or bindings[path] == sha, path
            bindings[path] = sha
        records.append(result)
    check_files(bindings)
    p2 = read(LOCAL / 'bf-phase2-20261020/dispatch-baseline.json')
    old_prefix = len(p2['prior_ledger']) + 25
    assert old_prefix == 100
    cursor = old_prefix
    for old, added in sorted(chain):
        assert old == cursor, (old, cursor)
        cursor += added
    owners = [x['owner'] for x in records]
    account = read(HERE / 'main-tables.json')['accounting']
    assert cursor == old_prefix + account['requests']

    # Old records are checked in place rather than copied to another database.
    before = read(ROOT / 'docs/storage-deep-clean-20261020/protected-before.json')
    databases = {
        'production': LOCAL / 'bf-agent-runtime/workbench/state/workbench.sqlite',
        'v2': LOCAL / 'bf-agent-architecture-v2/workbench/state/workbench.sqlite',
        'historical': LOCAL / 'bf-agent-runtime/reference-cases/literature-rsi-20261008/runtime/state/workbench.sqlite',
        'campaign': LOCAL / 'bf-campaign-20261019-s0/workbench/state/workbench.sqlite',
    }
    protected = {}
    for label, path in databases.items():
        summary = {}
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            for table, old in before[label].items():
                if table == 'status_counts':
                    continue
                assert table in ('conversations', 'model_requests', 'design_projects')
                h = hashlib.sha256()
                count = 0
                for row in db.execute('SELECT * FROM ' + table + ' ORDER BY rowid LIMIT ?', (old['rows'],)):
                    h.update(encoded(dict(row)) + b'\n')
                    count += 1
                assert count == old['rows'] and h.hexdigest() == old['sha256'], (label, table)
                summary[table] = {'original_rows': count, 'sha256': h.hexdigest()}
            if label == 'campaign':
                rows = {row['id']: dict(row) for row in db.execute('SELECT * FROM model_requests')}
                assert all(digest(rows[key]) == sha for key, sha in p2['prior_ledger'].items())
                actual = [row for row in rows.values() if row['owner'] in owners]
                assert len(actual) == account['requests'] == 771
                assert all(row['status'] == 'SETTLED' and row['charged'] is not None for row in actual)
                charges = sum((Decimal(str(row['charged'])) for row in actual), Decimal(0))
                reported = Decimal(str(account['settled_upper_usd']))
                assert charges.quantize(Decimal('0.000000000001')) == reported.quantize(Decimal('0.000000000001'))
                h = hashlib.sha256()
                for row in db.execute('SELECT * FROM model_requests ORDER BY rowid LIMIT ?', (cursor,)):
                    h.update(encoded(dict(row)) + b'\n')
                summary.update(phase3_sealed_prefix_rows=cursor, phase3_sealed_prefix_sha256=h.hexdigest(),
                               phase3_requests=len(actual), phase3_settled_upper_usd=str(charges),
                               binary_float_sum_difference_usd=str(charges - reported))
            summary['old_status_counts'] = before[label]['status_counts']
        protected[label] = summary
    for episode in ('p2-e5-001', 'p2-h-proposal-001', 'p2-h0-design-001', 'p2-hprime-design-001'):
        root = LOCAL / 'bf-phase2-20261020' / episode
        old = read(root / 'provider-costs.json')
        assert ledger(databases['campaign'], read(root / 'episode-result.json')['owner'])['rows'] == old['rows']
    check_files(read(HERE.parent / 'phase2/source-manifest.json')['entries'])

    initial = read(OUT / 'initial-cache.json')
    physical = read(OUT / 'physical-cache/index.json')
    artifacts = {}
    for entry in physical.values():
        assert entry.get('status') != 'STARTED'
        for path, sha in entry['artifacts'].items():
            assert path not in artifacts or artifacts[path] == sha
            artifacts[path] = sha
    check_files(artifacts)
    new_comparison = len(set(physical) - set(initial))
    assert new_comparison + 1 <= plan['maximum_new_scientific_executions']
    jobs = [read(p) for p in (OUT / 'groups').glob('*/job-overlay.json')]
    assert len(jobs) == 112
    assert all(j['initial_cache_sha256'] == file_hash(OUT / 'initial-cache.json')
               and len(j['executed']) <= 2 for j in jobs)
    future = read(HERE / 'stage4-selection-freeze.json')
    for task in future['new_unexposed_tasks']:
        assert file_hash(task['input_path']) == task['input_sha256']
        assert file_hash(task['parent']) == task['parent_sha256']
        assert task['id'] not in plan['tasks']
        assert not task['participant_exposures'] and not task['scientific_executions']
    witness = read(HERE / 'ordered-selected-witnesses.json')
    assert witness['selected_groups'] == 4 and witness['distinct_physical_execution_keys'] == 1
    for row in witness['witnesses']:
        assert file_hash(row['raw_path']) == row['raw_sha256']
        order = row['ordered_state']
        assert order['pending_event_retained_across_reset'] and row['service'] == 'PASS'
        assert row['capture_last_s'] < order['resets_before_first_delivery'][0]['time_s'] < order['first_valid_receive_s']
    value = {'status': 'PASS', 'actual_episodes': 140, 'formal_groups': 96, 'pilot_groups': 16,
             'unique_bound_files': len(bindings), 'cached_response_files': len(artifacts),
             'phase2_manifest_files': read(HERE.parent / 'phase2/source-manifest.json')['entry_count'],
             'protected': protected, 'historical_UNKNOWN_records_preserved': 24,
             'phase3_UNKNOWN_records': 0, 'new_comparison_scientific_executions': new_comparison,
             'derived_baseline_scientific_executions': 1, 'total_new_scientific_executions': new_comparison + 1,
             'group_job_overlays': len(jobs), 'logical_D_evaluations': sum(len(j['executed']) for j in jobs),
             'exact_initial_cache_and_private_two_D_limits': 'PASS',
             'no_new_model_or_scientific_execution_for_verification': True,
             'ordered_selected_groups': 4, 'ordered_distinct_cached_physical_points': 1,
             'new_unexposed_phase4_inputs': 2, 'default_H_changed': False,
             'verification_code_sha256': file_hash(Path(__file__))}
    seal(HERE / 'preservation-final.json', value)
    print(json.dumps({k: v for k, v in value.items() if k != 'protected'}, indent=2))
    return value


if __name__ == '__main__':
    verify()
