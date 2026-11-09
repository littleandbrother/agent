"""Read saved BFA099 facts and the read-only ledger; never dispatch an experiment."""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = OUT.parents[3]
PACKAGE = 'BF-PQE-PARTIAL-ANCESTOR-VALIDATION-20261026-001'
DB = Path('/Users/depengsu/.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite')
PRIVATE_KEYS = {'observer_epoch', 'observer_event_id', 'hidden_truth', 'event_truth', 'truth_event_id'}


def load(path):
    path = Path(path)
    with gzip.open(path, 'rt') if path.suffix == '.gz' else path.open() as stream:
        return json.load(stream)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value, ascii=True):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=ascii, allow_nan=False).encode()).hexdigest()


def numeric_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(numeric_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(numeric_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def private_keys(value):
    found = set()
    if isinstance(value, dict):
        found.update(set(value) & PRIVATE_KEYS)
        for child in value.values():
            found.update(private_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(private_keys(child))
    elif isinstance(value, str):
        # Actual serialized public payloads, not plain instructions naming fields.
        try:
            child = json.loads(value)
        except (ValueError, TypeError):
            return found
        if isinstance(child, (dict, list)):
            found.update(private_keys(child))
    return found


def verify():
    protocol = load(OUT / 'shared/protocol.json')
    for name, expected in protocol['source_hashes'].items():
        assert sha(ROOT / name) == expected, ('FROZEN_SOURCE', name)
    amendment = load(OUT / 'shared/M2-expression-amendment-admission.json')
    for name, expected in amendment['old_immutable_refs'].items():
        assert sha(ROOT / name) == expected, ('ORIGINAL_QUALIFICATION', name)
    for item in amendment['frozen_inputs']:
        assert sha(ROOT / item['path']) == item['sha256']
    htask = protocol['holdout']['task_hash']
    assert sha(htask['path']) == htask['sha256']
    old = load(OUT / 'a/mechanism-qualification.json')
    revised = load(OUT / 'a/M2r/mechanism-qualification.json')
    assert old['status'] == 'NOT_ESTABLISHED' and revised['status'] == 'QUALIFIED'
    assert Counter((r['model_valid'], r['verdict']) for r in old['results']) == {
        (True, 'PASS'): 12, (True, 'FAIL'): 18, (False, 'UNKNOWN'): 15}
    a0, a1 = load(OUT / 'a/counter.json'), load(OUT / 'a/M2r/counter.json')
    assert a0['full_attempts'] == 45 and a1['full_attempts'] == 15
    qualification_files = 0
    for path, base in [(OUT / 'a/independent-readback.json', OUT / 'a'),
                       (OUT / 'a/M2r/independent-readback.json', ROOT)]:
        for row in load(path)['checks']:
            for artifact in row['files']:
                assert sha(base / artifact['ref']) == artifact['sha256']
                qualification_files += 1
    for name, artifact in load(OUT / 'b/SOURCE-FROZEN.json')['files'].items():
        assert sha(OUT / 'b' / name) == artifact['sha256']

    index = load(HERE / 'evidence-index.json')
    for key in ['original_comparison', 'current_canonical_science_ledger', 'current_method_summary']:
        assert sha(index[key]['path']) == index[key]['sha256']
    assert index['original_comparison_modified'] is False
    ledger = load(HERE / 'science-resource-ledger.json')
    assert ledger['full_attempts'] == len(ledger['rows']) == 65
    assert abs(ledger['full_wall_s'] - sum(r['full_wall_s'] for r in ledger['rows'])) < 1e-8
    completed, interrupted = [], []
    for row in ledger['rows']:
        folder = Path(row['path'])
        assert load(folder / 'receipt.json') == row
        inp = load(folder / 'input.json')
        assert digest(inp['design']) == row['design_sha256']
        if row['status'] != 'COMPLETE':
            assert row['index'] == 29 and row['status'] == 'STARTED'
            assert not (folder / 'result/public-result.json.gz').exists()
            interrupted.append(row['index'])
            continue
        public = load(row['public_path'])
        raw = load(folder / 'result/raw.json.gz')
        decision = load(folder / 'result/decision.json')
        assessment = load(folder / 'result/assessment.json.gz')
        assert digest(inp['task']) == raw['task_sha256'] == public['task_sha256'] == decision['task_sha256']
        assert digest(raw['design']) == raw['design_sha256'] == public['input_sha256']
        assert numeric_equal(inp['design'], raw['design']) and numeric_equal(public['design'], raw['design'])
        assert digest({k: v for k, v in raw.items() if k != 'result_sha256'}) == raw['result_sha256']
        assert public['result_sha256'] == raw['result_sha256']
        assert assessment['verdict'] == public['public_check']['verdict'] == row['verdict']
        assert raw['model_valid'] is True and public['model_valid'] is True
        assert assessment['physical_qualification'] == 'UNKNOWN'
        completed.append(row)
    assert len(completed) == 64 and interrupted == [29]
    assert Counter((r['phase'], r['verdict']) for r in completed) == {
        ('main', 'FAIL'): 30, ('main', 'PASS'): 24, ('holdout', 'PASS'): 10}
    for item in ledger['off_route_reuse_bindings']:
        for kind in ['raw', 'decision']:
            assert sha(item[kind]['path']) == item[kind]['sha256']

    summary = load(HERE / 'method-summary.json')
    original = load(HERE / 'comparison-result.json')
    assert len(original['rows']) == len(summary['rows']) == 24 and original['unrun'] == []
    for row in summary['rows']:
        assert sha(row['snapshot']['path']) == row['snapshot']['sha256']
        assert load(row['snapshot']['path'])['slots'] == row['slots_including_initial'] <= 6
    for seed in [271828, 161803]:
        recovery = load(HERE / f'binding-recovery/known-local-G-{seed}/result.json')
        assert recovery['actual_new_full'] == recovery['actual_new_provider_requests'] == recovery['actual_new_slots'] == 0
        assert recovery['final']['all_condition_PASS'] is True
        bindings = load(HERE / f'binding-recovery/known-local-G-{seed}/numeric-bindings.json')
        for item in bindings['bindings']:
            assert numeric_equal(item['original_design'], item['requested_design'])
            assert sha(item['original_public']['path']) == item['original_public']['sha256']
    recall = load(HERE / 'context-recall/result.json')
    assert recall['actual_new_full'] == 0 and recall['final']['eligible_for_holdout'] is False
    assert recall['budget']['model_requests'] == 12 and recall['budget']['tool_calls'] == 24
    yes = [r for r in original['holdouts'] if r['status'] == 'COMPLETE']
    no = [r for r in original['holdouts'] if r['status'] != 'COMPLETE']
    assert len(yes) == len(no) == 6
    assert all(r['verdict'] == 'PASS' and len(r['members']) == 2 for r in yes)
    for row in yes:
        for member in row['members']:
            assert load(member['canonical_public_path'])['public_check']['verdict'] == member['public_check']['verdict'] == 'PASS'
    rs = [r for r in summary['rows'] if r['family'] == 'mechanism' and r['condition'] == 'R' and r['all_main_PASS']]
    assert len(rs) == 3 and all(r['current_final']['final_design']['holding_component'] == 'off' for r in rs)

    owners = load(OUT / 'shared/provider-binding.json')['owners']
    preflight = load(HERE / 'preflight.json')
    with sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=30) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute('SELECT * FROM model_requests ORDER BY id')]
        old_rows = [r for r in rows if r['owner'] not in owners.values()]
        new_rows = [r for r in rows if r['owner'] in owners.values()]
        assert len(old_rows) == 1966 and digest(old_rows, False) == preflight['billing_baseline']['model_requests']['sha256']
        policies = [dict(row) for row in db.execute('SELECT * FROM historical_usage_exceptions ORDER BY id')]
        assert digest(policies, False) == load(OUT / 'shared/accounting-scope.json')['original_authorizations_sha256']
        unknown = [r for r in old_rows if r['status'] == 'UNKNOWN']
        assert {r['id']: r for r in unknown} == {r['id']: r for r in preflight['historical_unknown_original_rows']}
        assert len(new_rows) == 29 and all(r['status'] == 'SETTLED' and r['usage'] for r in new_rows)
        for row in new_rows:
            usage = json.loads(row['usage'])
            assert all(isinstance(usage[k], int) and usage[k] >= 0 for k in ['prompt_tokens', 'completion_tokens'])
            assert row['response_hash'] and row['error'] is None
        for owner in owners.values():
            assert db.execute('SELECT count(*) FROM principals WHERE owner=?', (owner,)).fetchone()[0] == 0
            assert all(r['expires'] < time.time() and r['max_jobs'] == 0 for r in db.execute('SELECT expires,max_jobs FROM grants WHERE owner=?', (owner,)))
            assert db.execute('SELECT status FROM conversations WHERE id=?', (owner,)).fetchone()[0] == 'IDLE'
        assert db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone() is None
        studies = list(db.execute('SELECT expires FROM research_model_studies WHERE protocol=?', (PACKAGE,)))
        assert len(studies) == 1 and studies[0]['expires'] < time.time()
    public_files = sorted((HERE / 'public-objects').glob('*.json.gz'))
    wire_files = sorted((HERE / 'episodes').rglob('wire-public.json'))
    for path in public_files + wire_files:
        assert not private_keys(load(path)), ('PRIVATE_PUBLIC_KEY', str(path))
    active_callbacks = []
    for line in subprocess.check_output(['ps', '-axo', 'pid=,comm=,args='], text=True, errors='replace').splitlines():
        pieces = line.split(None, 2)
        if len(pieces) == 3 and Path(pieces[1]).name == 'node' and 'pqe_pi_callback.mjs' in pieces[2] and str(OUT) in pieces[2]:
            active_callbacks.append(int(pieces[0]))
    assert not active_callbacks
    state = load(HERE / 'execution-state.json')
    assert state['execution_gate']['provider_ready'] is False and state['execution_gate']['new_full_dispatch'] is False
    assert state['old_cleanup_writing_automation_remain_paused'] is True
    a_exit = load(OUT / 'a/METHOD-INDEPENDENT-READBACK.json')
    b_exit = load(OUT / 'b/METHOD-INDEPENDENT-EXIT.json')
    assert a_exit['status'].startswith('PASS') and a_exit['service_and_energy_review'] == 'PASS_FOR_EXACT_RETAINED_SCOPE'
    assert b_exit['status'] == 'METHOD_READBACK_COMPLETE_NO_ROBUST_ANCESTOR_BENEFIT_ESTABLISHED'
    assert b_exit['source_and_trace_binding']['controller_frozen_unchanged'] is True
    assert b_exit['source_and_trace_binding']['snapshot_hashes_all_match'] is True
    manifest = load(HERE / 'integrity-manifest.json')
    for item in manifest['files']:
        assert sha(OUT / item['path']) == item['sha256'], ('SAVED_ARTIFACT', item['path'])
    fs = os.statvfs(ROOT)
    available = fs.f_bavail * fs.f_frsize
    allocated = sum(p.stat().st_blocks * 512 for p in OUT.rglob('*') if p.is_file())
    assert available >= 11_500_000_000 and allocated < 200_000_000
    full_count = a0['full_attempts'] + a1['full_attempts'] + ledger['full_attempts']
    full_wall = a0['full_wall_s'] + a1['full_wall_s'] + ledger['full_wall_s']
    assert full_count == 125 and full_count <= 512 and full_wall <= 3600
    charge = sum(r['charged'] for r in new_rows)
    assert abs(charge - summary['usage']['provider_charge_upper_usd']) < 1e-12
    return {'status': 'PASS_FOR_SAVED_FINITE_EXIT_WITH_SCIENTIFIC_LIMITATIONS',
        'at': datetime.now(timezone.utc).isoformat(), 'package': PACKAGE,
        'frozen_sources_checked': len(protocol['source_hashes']),
        'qualification_canonical_files_checked': qualification_files,
        'manifest_files_checked': len(manifest['files']),
        'full_attempts': full_count, 'full_completed': 124, 'full_wall_s': full_wall,
        'original_domain_unknown_qualification_inputs': 15, 'interrupted_attempts_retained': interrupted,
        'method_new_complete': 54, 'holdout_new_complete': 10,
        'holdout_eligible_designs': 6, 'holdout_logical_PASS_members': 12, 'holdout_NE_trajectories': 6,
        'provider_requests': len(new_rows), 'provider_statuses': dict(Counter(r['status'] for r in new_rows)),
        'provider_charge_upper_estimate_usd': charge, 'provider_invoice_verified': False,
        'original_model_rows_preserved': len(old_rows), 'original_UNKNOWNs_preserved': len(unknown),
        'original_UNKNOWN_reserve_usd': sum(r['reserved'] for r in unknown),
        'original_authorizations_unchanged': True, 'new_missing_usage': 0,
        'new_active_principals': 0, 'unexpired_package_grants': 0, 'budget_scope': 'ABSENT',
        'public_objects_checked': len(public_files), 'public_wire_payloads_checked': len(wire_files),
        'private_key_leaks': 0, 'active_package_callbacks': active_callbacks,
        'available_bytes': available, 'allocated_output_upper_bytes': allocated,
        'new_scientific_or_model_executions_in_this_readback': 0,
        'new_software_cases_or_suite_reruns': 0, 'reclaimed_bytes': 0,
        'new_backups_environments_worktrees': 0, 'cleanup_resumed': False,
        'claim_boundary': 'Finite package closed. Strong-G comparison and causal useful-failed-ancestor advantage remain unestablished; global holder necessity has counterexamples. No hardware or whole-repository-health claim.'}


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
