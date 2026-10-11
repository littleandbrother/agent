#!/usr/bin/env python3
"""Current-version read-only audit; no Workbench, provider or native execution.

Old prose and pointer snapshots are compared with latest immutable attempts,
actual live sources and original ledgers. Output is confined to this slice.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import statistics
from collections import Counter

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.contracts import sha, sealed
from bfworld.agentlab import literature_acceptance

ROOT = Path('/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008')
OUT = APP / 'docs/agentlab/refactor-r3-r5-20261012' / ('system-audit-' + str(time.time_ns()))
OUT.mkdir(parents=True)
index_path = ROOT / 'campaign/parallel-20261009/pi-session-index.json'
index = json.loads(index_path.read_text())
pointer_path = ROOT / 'campaign/acceptance/current.json'
pointer = json.loads(pointer_path.read_text())
snapshot_path = ROOT / pointer['path']
assert sha(snapshot_path) == pointer['sha256'], 'ACCEPTANCE_POINTER_HASH'
snapshot = json.loads(snapshot_path.read_text())
old = {p['paper']: p for p in snapshot['papers']}
owners = {s['paper_id']: s['owner'] for s in index['sessions']}
assert len(owners) == 10 and len(set(owners.values())) == 10
attempts = {p: [] for p in owners}
for path in (ROOT / 'campaign/native-runs').rglob('attempt.json'):
    value = json.loads(path.read_text())
    paper = value.get('paper')
    if paper in owners and value.get('owner') == owners[paper]:
        attempts[paper].append((value['started'], path))

dbpath = ROOT / 'runtime/state/workbench.sqlite'
with sqlite3.connect('file:' + str(dbpath) + '?mode=ro', uri=True) as db:
    db.row_factory = sqlite3.Row
    status = {r['id']: dict(r) for r in db.execute('SELECT id,status,error,updated FROM conversations')}
    assembly = {o: db.execute('SELECT revision,hashes FROM assembly_revisions WHERE owner=? ORDER BY revision DESC LIMIT 1', (o,)).fetchone() for o in owners.values()}
    jobs = [dict(r) for r in db.execute('SELECT id,owner,status,created,ended,error FROM engineering_jobs ORDER BY created') if r['owner'] in owners.values()]
    requests = [dict(r) for r in db.execute('SELECT id,owner,status,reserved,charged,usage FROM model_requests ORDER BY created') if r['owner'] in owners.values()]
    contexts = [json.loads(r['projection']) for r in db.execute('SELECT owner,projection FROM model_request_context') if r['owner'] in owners.values()]
    settings = []
    # Only redacted configuration facts. No credentials, tokens or full grants.
    for row in db.execute('SELECT key,value FROM settings'):
        if any(x in row['key'].lower() for x in ('budget', 'unbounded', 'model_profile', 'context', 'authority', 'window')):
            try:
                body = json.loads(row['value'])
            except ValueError:
                body = None
            if isinstance(body, dict):
                settings.append({'key': row['key'], 'value_sha256': hashlib.sha256(row['value'].encode()).hexdigest(),
                    'facts': {k: body.get(k) for k in ('schema_version','scope','expires','expires_at','expires_utc','max_usd','max_tokens','max_requests','cumulative_usd_cap','cumulative_token_cap','request_count_cap','wall_seconds','wall_unbounded','unbounded','model_profile') if k in body}})

current_papers = []
for paper in sorted(owners):
    entries = sorted(attempts[paper])
    started, attempt_path = entries[-1]
    result_path = attempt_path.parent / 'result.json'
    if not result_path.is_file():
        current_papers.append({'paper': paper, 'owner': owners[paper], 'latest_attempt': str(attempt_path.relative_to(ROOT)), 'receipt_missing': True})
        continue
    current = json.loads(result_path.read_text())
    current.update(result_path=str(result_path.relative_to(ROOT)), result_sha256=sha(result_path))
    native = json.loads((result_path.parent / 'native-report.json').read_text())
    row = assembly[owners[paper]]
    current['live_assembly_matches'] = bool(row) and row['revision'] == native.get('assembly_revision') and json.loads(row['hashes']).get('physical_hash') == native.get('assembly_physical_hash')
    current['execution'] = status.get(owners[paper], {'status': 'UNAVAILABLE'})
    verified, bad = [], []
    for item in current.get('delivery_integrity', {}).get('verified_files', []):
        path = result_path.parent / 'participant-files' / item['path']
        valid = not path.is_symlink() and path.resolve().is_relative_to(result_path.parent.resolve()) and path.is_file() and sha(path) == item['sha256']
        (verified if valid else bad).append(item)
    if bad:
        current['delivery_integrity'] = {**current['delivery_integrity'], 'status': 'FAIL'}
    evidence = []
    for path in sorted((ROOT / 'campaign/reviews' / paper / 'digital-gates').glob('*.json')):
        value = json.loads(path.read_text())
        value['artifact'] = {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}
        evidence.append(value)
    scope_path = ROOT / 'campaign/acceptance' / paper / 'scope-v1.json'
    accepted = literature_acceptance.evaluate(ROOT, json.loads(scope_path.read_text()), current, evidence, old[paper].get('issues', []))
    selected_ids = set(accepted['selected_bindings'])
    req = [r for r in requests if r['owner'] == owners[paper]]
    settled = [r for r in req if r['status'] == 'SETTLED']
    unknown = [r for r in req if r['status'] == 'UNKNOWN']
    accepted.update(latest_attempt={'path': str(attempt_path.relative_to(ROOT)), 'sha256': sha(attempt_path), 'started': started},
                    latest_native_result_changed_from_pointer=accepted['source_result'] != old[paper]['source_result'],
                    delivery_readback={'sha_records_checked': len(verified) + len(bad), 'verified': len(verified), 'mismatches': bad},
                    actual_native_jobs=[r for r in jobs if r['id'] in selected_ids],
                    all_native_job_counts={s: sum(j['status'] == s and j['owner'] == owners[paper] for j in jobs) for s in sorted(set(j['status'] for j in jobs))},
                    ledger={'requests': len(req), 'settled': len(settled), 'unknown': len(unknown), 'registered_charged_usd': sum(r['charged'] for r in req), 'unknown_reserved_usd': sum(r['reserved'] for r in unknown)},
                    actual_native_gaps=native.get('gaps', []),
                    required_checks_missing=[g['id'] for g in accepted['functional_gates'] if g['status'] != 'PASS'])
    sealed(OUT / (paper + '.json'), accepted)
    current_papers.append(accepted)

usage = [json.loads(r['usage']) for r in requests if r['status']=='SETTLED' and r['usage']]
totals = {k: sum(u.get(k, 0) for u in usage) for k in ('prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')}
def stats(values):
    values = sorted(values)
    return {'count':len(values),'median':statistics.median(values) if values else None,
            'p95':values[int((len(values)-1)*.95)] if values else None,'maximum':max(values) if values else None}
cost_diagnostic = {'settled_usage_records':len(usage),'tokens':totals,
    'prompt_tokens_per_request':stats([u['prompt_tokens'] for u in usage]),
    'output_tokens_per_request':stats([u['completion_tokens'] for u in usage]),
    'context_projection_records':len(contexts),'source_bytes':stats([c['source_bytes'] for c in contexts]),
    'projected_bytes':stats([c['projected_bytes'] for c in contexts]),
    'fits_false':sum(c.get('fits') is False for c in contexts),
    'profile_counts':dict(Counter(c.get('model_profile',{}).get('version','UNRECORDED') for c in contexts)),
    'interpretation':'Token and projection observations only. Historical models/rates/conditions may differ; no supplier repricing or causal compression benefit.'}
report = {'schema_version': 'bf-system-current-readonly-audit-v1', 'created': time.time(),
          'database_mode': 'ro', 'workbench_instances_created': 0, 'models_dispatched': 0, 'native_jobs_dispatched': 0,
          'input_index': {'path': str(index_path), 'sha256': sha(index_path)},
          'old_acceptance_pointer': pointer, 'old_pointer_stage_pass_count': snapshot['stage_deliveries_passed'],
          'latest_papers': current_papers,
          'stage_delivery_passed': sum(p.get('stage_delivery_passed', False) for p in current_papers),
          'full_digital_products_passed': sum(p.get('full_product_passed', False) for p in current_papers),
          'frozen_delivery_sha_records': sum(p.get('delivery_readback', {}).get('sha_records_checked', 0) for p in current_papers),
          'live_input_or_file_problems': sum(not p.get('current_sources_valid', False) or p.get('delivery_readback', {}).get('mismatches', []) != [] for p in current_papers),
          'registered_charged_usd_original_ten': sum(r['charged'] for r in requests),
          'model_requests_original_ten': len(requests),
          'unknown_rows_original_ten': sum(r['status'] == 'UNKNOWN' for r in requests),
          'unknown_reserved_original_ten_usd': sum(r['reserved'] for r in requests if r['status'] == 'UNKNOWN'),
          'active_original_native_jobs': [j for j in jobs if j['status'] in ('RUNNING','QUEUED')],
          'settings_facts': settings, 'physical_validation': 'NOT_TESTED',
          'actual_cost_context_diagnostic':cost_diagnostic,
          'claim': 'Current declared paper scopes, live source bindings and file readback. No model dispatch, physical or generalization claim; original campaign not overwritten.'}
sealed(OUT / 'report.json', report)
print(json.dumps({k: report[k] for k in ('stage_delivery_passed','full_digital_products_passed','frozen_delivery_sha_records','live_input_or_file_problems','model_requests_original_ten','registered_charged_usd_original_ten','unknown_rows_original_ten')}, ensure_ascii=False))
print(json.dumps({'report': str(OUT / 'report.json')}))
