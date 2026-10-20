#!/usr/bin/env python3
"""Read back saved phase-two evidence and billing; never execute an experiment."""
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
APP = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
LOCAL = Path.home() / '.local/share'
OUT = LOCAL / 'bf-phase2-20261020'
EPISODES = ('p2-e5-001', 'p2-h-proposal-001', 'p2-h0-design-001',
            'p2-hprime-design-001')


def load(path):
    return json.loads(path.read_text())


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    actual = load(OUT / 'actual-results.json')
    baseline = load(OUT / 'dispatch-baseline.json')
    bindings = {}
    for episode in EPISODES:
        protocol = load(OUT / episode / 'protocol.json')
        result = load(OUT / episode / 'episode-result.json')
        assert hashlib.sha256(encoded(protocol)).hexdigest() == result['protocol_sha256'], episode
        assert not result['trace_audit']['unmatched_executed_inputs'], episode
        assert not result['accounting']['unknown_or_missing_usage'], episode
        assert load(OUT / episode / 'protected-ledger-readback.json')['old_unchanged'], episode
        for name, expected in protocol['bound_files'].items():
            assert name not in bindings or bindings[name] == expected, name
            bindings[name] = expected
    for name, expected in bindings.items():
        assert sha(Path(name)) == expected, name

    cache = load(OUT / 'cases/index.json')
    entries = cache
    assert entries, 'Missing saved case registry'
    cache_files = {}
    for entry in entries.values():
        for name, expected in entry['artifacts'].items():
            assert name not in cache_files or cache_files[name] == expected, name
            cache_files[name] = expected
    for name, expected in cache_files.items():
        assert sha(Path(name)) == expected, name
    origins = Counter(entry['origin'] for entry in entries.values())
    assert origins['new-full-feedback-response'] == actual['new_scientific_executions'] == 7
    assert origins['sealed-historical-exact-input'] == 5

    for rel, expected in load(HERE / 'baseline.json')['frozen_scientific_files'].items():
        assert sha(APP / rel) == expected, rel
    old_assets = {
        'papers/method-reexecution-20261019/main.pdf':
            '6da2fa74902d1776eaf5f19379bb6ff12d28c8c0ef0746fdf141713dadb54b7c',
        'papers/interface-sufficiency-20261019/interface-sufficiency-phase1.pdf':
            'aa4d29d003d0caf7d3b15cca424cf2ec315d0b178375a123eaf127937832c785',
        'papers/shared/hkustgz-paper.sty':
            '473994c5eb69167576ae0427ed4696e6542d5aadd10497868e38304e7c850872',
        'papers/shared/assets/hkustgz-english.pdf':
            '25f016add579c729d3447b4fca72b66fa98bd309cc82a9a4971bd61d8837f12e',
        'papers/shared/assets/hkustgz-english.svg':
            '69a0e1030a05cc50d11d38c16f24e3ad092e4760e043638f87943f29d4271e7c',
    }
    for rel, expected in old_assets.items():
        assert sha(APP / rel) == expected, rel

    protected_before = load(ROOT / 'docs/storage-deep-clean-20261020/protected-before.json')
    databases = {
        'production': LOCAL / 'bf-agent-runtime/workbench/state/workbench.sqlite',
        'v2': LOCAL / 'bf-agent-architecture-v2/workbench/state/workbench.sqlite',
        'historical': LOCAL / 'bf-agent-runtime/reference-cases/literature-rsi-20261008/runtime/state/workbench.sqlite',
        'campaign': LOCAL / 'bf-campaign-20261019-s0/workbench/state/workbench.sqlite',
    }
    protected = {}
    for label, path in databases.items():
        tables = {}
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            for table, old in protected_before[label].items():
                if table == 'status_counts':
                    continue
                assert table in ('conversations', 'model_requests', 'design_projects')
                h = hashlib.sha256()
                count = 0
                for row in db.execute('SELECT * FROM ' + table + ' ORDER BY rowid LIMIT ?', (old['rows'],)):
                    h.update(encoded(dict(row)))
                    h.update(b'\n')
                    count += 1
                assert count == old['rows'] and h.hexdigest() == old['sha256'], (label, table)
                tables[table] = {'original_rows': count, 'sha256': h.hexdigest()}
            tables['status_counts'] = [list(row) for row in db.execute(
                'SELECT status,count(*) FROM model_requests GROUP BY status')]
            if label != 'campaign':
                assert tables['status_counts'] == protected_before[label]['status_counts'], label
            else:
                rows = {row['id']: dict(row) for row in db.execute('SELECT * FROM model_requests')}
                assert all(hashlib.sha256(encoded(rows[key])).hexdigest() == value
                           for key, value in baseline['prior_ledger'].items()), 'Original phase-two billing prefix'
                added = [row for key, row in rows.items() if key not in baseline['prior_ledger']]
                assert len(added) == actual['provider_requests'] == 25
                assert all(row['status'] == 'SETTLED' and row['charged'] is not None for row in added)
                charges = sum((Decimal(str(row['charged'])) for row in added), Decimal(0))
                reported = Decimal(str(actual['settled_charge_upper_bound_usd']))
                # SQLite REAL and the original accounting helper use binary floats.
                # Compare at a trillionth of a dollar and expose the raw difference.
                assert charges.quantize(Decimal('0.000000000001')) == reported.quantize(Decimal('0.000000000001'))
                tables['phase2_baseline_rows_unchanged'] = len(baseline['prior_ledger'])
                tables['phase2_added_requests'] = len(added)
                tables['phase2_settled_upper_usd'] = str(charges)
                tables['binary_float_sum_difference_usd'] = str(charges - reported)
        protected[label] = tables

    retention = load(OUT / 'method-retain-or-reject.json')
    assert retention['status'] == 'REJECT_PROMOTION_KEEP_EXPERIMENTAL_ARTIFACT'
    assert not retention['retained'] and not retention['default_H_changed']
    assert retention['gate']['failures'] == ['PARITY_INITIAL_CACHE_SHA256']
    for episode in EPISODES[:2]:
        assert actual['actual_episodes'][episode]['status'] == 'INCOMPLETE_OR_STOPPED'
    for episode in EPISODES[2:]:
        result = load(OUT / episode / 'external/result.json')
        assert result['fresh_task_entry'] and result['execution']['complete_service'] == 'PASS'
    e5 = load(OUT / 'p2-e5-001/posthoc-adapter-001/result.json')
    assert e5['label'] == 'POSTHOC_HOST_ADAPTER_REEVALUATION' and not e5['original_live_E5_success']
    assert (e5['original_service'], e5['selected_service'], e5['static_complete_service']) == ('FAIL', 'PASS', 'PASS')
    print(json.dumps({
        'status': 'PASS', 'protocols': len(EPISODES), 'unique_bound_files': len(bindings),
        'saved_case_files': len(cache_files), 'case_origins': dict(origins),
        'protected': protected, 'old_UNKNOWN_preserved': True,
        'phase1_pdfs_shared_style_and_logo_unchanged': True,
        'new_provider_requests_during_verification': 0, 'new_scientific_executions_during_verification': 0,
        'no_method_promotion': True, 'original_failures_preserved': True,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
