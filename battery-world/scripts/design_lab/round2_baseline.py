"""Freeze P01 efficiency baseline using read-only SQLite and source files."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def capture(repo, runtime, output, owner):
    output.mkdir(parents=True, exist_ok=False)
    module = repo / 'packages/python/bfworld/src/bfworld/agentlab'
    paths = [module / name for name in ('context.py', 'continuation_context.py', 'provider.py',
        'model_profile.py', 'eda_cli.py', 'tool_responses.py', 'skill_resources.py',
        'literature_package.py', 'literature_acceptance.py', 'design_lab/paper_candidate.py')]
    pi = repo.parent / 'pi-bf-aiot'
    paths += [pi / 'packages/bf-agent/src' / name for name in ('chat-product.ts',
        'skill-resources.ts', 'bounded-bash.ts', 'paper-candidate.ts')]
    paths += [p for p in (pi / 'packages/bf-harness/resources').rglob('*') if p.is_file()]
    code = {}
    for p in paths:
        data = p.read_bytes()
        code[str(p)] = digest(data)
        target = output / 'source-baseline' / ('pi' if p.is_relative_to(pi) else 'app') / p.relative_to(pi if p.is_relative_to(pi) else repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    with sqlite3.connect('file:' + str(runtime / 'runtime/state/workbench.sqlite') + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        tables = ['model_requests', 'engineering_jobs', 'eda_cli_jobs', 'design_tasks',
                  'design_operations', 'chat_messages', 'skill_activations', 'settings', 'grants']
        rows = {}
        for name in tables:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone():
                rows[name] = [dict(r) for r in db.execute('SELECT * FROM ' + name)]
        active = [r for r in rows.get('engineering_jobs', []) if r['status'] in ('RUNNING', 'QUEUED')]
        dispatched = [r for r in rows['model_requests'] if r['status'] == 'DISPATCHED']
        if active or dispatched:
            raise RuntimeError('BASELINE_REQUIRES_IDLE_NATIVE_AND_MODEL')
        request = db.execute('SELECT wire FROM model_request_evidence WHERE owner=? ORDER BY created DESC LIMIT 1', (owner,)).fetchone()
        wire = json.loads(request['wire'])
        # Public observable messages only. Reasoning is excluded from all review artifacts.
        for m in wire.get('messages', []):
            m.pop('reasoning_content', None)
        (output / 'last-public-wire.json').write_bytes(encoded(wire))
    ledger = rows['model_requests']
    (output / 'baseline-rows.json').write_bytes(encoded(rows))
    participant = runtime / 'runtime/participants' / owner
    source_hashes = {}
    for p in participant.rglob('*'):
        if p.is_file() and not p.is_symlink() and not any(x in p.relative_to(participant).parts for x in ('.pi', '.tmp', 'context-records', 'tool-records')):
            source_hashes[str(p.relative_to(participant))] = digest(p.read_bytes())
    baseline = {'schema_version': 'bf-p01-efficiency-baseline-v1', 'created': time.time(),
        'owner': owner, 'source': code, 'participant_files': source_hashes,
        'row_hashes': {k: digest(encoded(v)) for k, v in rows.items()},
        'request_count': len(ledger), 'unknown_count': sum(r['status'] == 'UNKNOWN' for r in ledger),
        'settled_usd': sum(r['charged'] for r in ledger if r['status'] == 'SETTLED'),
        'active_jobs': len(active), 'dispatched_requests': len(dispatched)}
    (output / 'baseline.json').write_bytes(encoded(baseline))
    print(json.dumps({k: baseline[k] for k in ('owner', 'request_count', 'unknown_count', 'settled_usd', 'active_jobs')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--owner', required=True)
    a = parser.parse_args()
    capture(a.repo.resolve(), a.runtime.resolve(), a.output.resolve(), a.owner)
