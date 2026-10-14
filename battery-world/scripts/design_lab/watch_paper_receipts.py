#!/usr/bin/env python3
"""Passive finite-batch observer: no Workbench, dispatch, or scheduled messages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.contracts import sealed, sha
ROOT = Path('/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008')
TERMINAL_QUEUE_STATES = frozenset({'FILE_CHECKS_COMPLETE', 'CHECKS_COMPLETE', 'REPAIR_REQUIRED',
    'DISPATCH_FAILED', 'CANCELLED', 'REJECTED', 'FAILED', 'BLOCKED'})


def phase_ended(status):
    # Held/waiting/unknown states have not executed or ended a phase.
    return status in TERMINAL_QUEUE_STATES


class IdentityDrift(ValueError):
    pass


def database_busy(exc):
    code = getattr(exc, 'sqlite_errorcode', None)
    return ((code is not None and (code & 255) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED))
            or str(exc).lower() in ('database is locked', 'database table is locked'))


def live(pid):
    try:
        r = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and 'scripts/literature_pi_queue.py' in r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def read_snapshot(root, owners, initial, index_sha, attempts=4, backoff=.1):
    """All-or-nothing bounded RO snapshot; never seals partial terminal facts."""
    queue = root / 'campaign/parallel-20261009/pi-queue'
    if sha(root / 'campaign/parallel-20261009/pi-session-index.json') != index_sha:
        raise IdentityDrift('ORIGINAL_INDEX_CHANGED')
    worker = json.loads((queue / 'worker.json').read_text())
    items = []
    for owner, paper in owners.items():
        raw = (queue / (owner + '.json')).read_bytes()
        item = json.loads(raw)
        if item['id'] != initial[owner] or item['owner'] != owner or item['paper'] != paper:
            raise IdentityDrift('ORIGINAL_QUEUE_REPLACED:' + paper)
        items.append((owner, paper, item, hashlib.sha256(raw).hexdigest()))
    for attempt in range(attempts):
        try:
            with sqlite3.connect('file:' + str(root / 'runtime/state/workbench.sqlite') + '?mode=ro', uri=True, timeout=.1) as db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
                rows = []
                for owner, paper, item, item_sha in items:
                    requests = list(db.execute('SELECT status,charged,reserved FROM model_requests WHERE owner=? AND created>=?',
                                               (owner, item.get('started', time.time() + 1))))
                    rows.append({'owner': owner, 'paper': paper, 'queue_id': item['id'], 'queue_status': item['status'],
                        'queue_sha256': item_sha, 'execution': item.get('execution'), 'new_model_calls': item.get('new_model_calls'),
                        'observed_requests': len(requests), 'registered_charged_usd': sum(r['charged'] for r in requests),
                        'unknown_full_reserved_usd': sum(r['reserved'] for r in requests if r['status'] == 'UNKNOWN'),
                        'full_product_passed': False, 'physical_verified': False, 'core_review': 'INDEPENDENT_REVIEW_REQUIRED'})
            return {'created': time.time(), 'pid': os.getpid(), 'worker': worker, 'papers': rows,
                'original_index_sha256': index_sha, 'database_mode': 'ro', 'fresh': True,
                'database_retry_count': attempt, 'workbench_instances_created': 0, 'models_dispatched': 0,
                'native_jobs_dispatched': 0, 'scheduled_chat_automations': 0, 'participant_edits': 0, 'Pi_feedback_edits': 0}
        except sqlite3.OperationalError as exc:
            if not database_busy(exc) or attempt + 1 == attempts:
                raise
            time.sleep(backoff)


def status_sample(root, owners, initial, index_sha, last_healthy=None):
    """Busy reads expose no stale paper rows. Other failures are terminal."""
    try:
        return read_snapshot(root, owners, initial, index_sha)
    except (sqlite3.OperationalError, IdentityDrift, OSError, ValueError, KeyError) as exc:
        busy = isinstance(exc, sqlite3.OperationalError) and database_busy(exc)
        return {'created': time.time(), 'pid': os.getpid(), 'fresh': False, 'papers': [], 'error': str(exc),
            'last_healthy_at': last_healthy, 'database_mode': 'ro', 'workbench_instances_created': 0,
            'models_dispatched': 0, 'native_jobs_dispatched': 0, 'scheduled_chat_automations': 0,
            'status': 'DEGRADED_DATABASE_BUSY' if busy else 'OBSERVER_IDENTITY_ERROR' if isinstance(exc, IdentityDrift) else 'OBSERVER_READ_ERROR'}


def write_status(out, value):
    p = out / 'status.next'
    p.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n')
    p.replace(out / 'status.json')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--interval', type=float, default=5)
    args = parser.parse_args(argv)
    if args.interval < .05:
        parser.error('interval must be at least .05 seconds')
    root = args.root.resolve()
    index = root / 'campaign/parallel-20261009/pi-session-index.json'
    index_sha = sha(index)
    owners = {s['owner']: s['paper_id'] for s in json.loads(index.read_text())['sessions']}
    if len(owners) != 10:
        raise IdentityDrift('TEN_ORIGINAL_OWNERS_REQUIRED')
    queue = root / 'campaign/parallel-20261009/pi-queue'
    initial = {o: json.loads((queue / (o + '.json')).read_text())['id'] for o in owners}
    out = APP / 'docs/agentlab/executable-lab-20261012' / ('receipt-observer-' + str(time.time_ns()))
    out.mkdir()
    stopped = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda number, frame: stopped.append(number))
    sealed(out / 'plan.json', {'schema_version': 'bf-paper-receipt-observer-v2', 'created': time.time(),
        'actor': 'Codex passive receipt observer', 'original_queue_ids': initial, 'original_index_sha256': index_sha,
        'hypothesis': 'Bounded RO reads recover from contention without changing Pi inputs or history.',
        'falsifier': 'Observer mutates DB/queue/Pi, reports stale facts as current, or hides non-lock errors.',
        'stop': 'Original batch ends, worker disappears, identity drifts, non-lock error or operator signal; no restart.'})
    print(json.dumps({'observer': str(out), 'pid': os.getpid(), 'state': 'PASSIVE_ORIGINAL_BATCH_OBSERVATION'}), flush=True)
    seen, last_healthy, busy_count = set(), None, 0
    while True:
        state = status_sample(root, owners, initial, index_sha, last_healthy)
        ending = 'OPERATOR_SIGNAL' if stopped else None
        if not state['fresh']:
            if state['status'] != 'DEGRADED_DATABASE_BUSY':
                ending = ending or state['status']
            else:
                busy_count += 1
                state['consecutive_degraded_samples'] = busy_count
                if busy_count == 1:
                    sealed(out / ('database-busy-' + str(time.time_ns()) + '.json'), state)
                try:
                    worker = json.loads((queue / 'worker.json').read_text())
                    if worker['status'] != 'RUNNING' or not live(worker['pid']):
                        ending = ending or 'WORKER_ENDED_WHILE_DATABASE_UNAVAILABLE'
                except (OSError, ValueError, KeyError) as exc:
                    ending, state['error'] = 'OBSERVER_READ_ERROR', str(exc)
        else:
            if busy_count:
                sealed(out / ('database-recovered-' + str(time.time_ns()) + '.json'),
                       {'created': time.time(), 'consecutive_degraded_samples': busy_count, 'fresh': True})
            busy_count = 0
            last_healthy = state['created']
            state['last_healthy_at'] = last_healthy
            for row in state['papers']:
                if phase_ended(row['queue_status']) and row['owner'] not in seen:
                    sealed(out / (row['paper'] + '-phase-end.json'), {'created': time.time(), **row,
                        'scope': 'Queue/file-stage facts only; no core/product/physical/RSI promotion.'})
                    seen.add(row['owner'])
            worker = state['worker']
            if all(phase_ended(p['queue_status']) for p in state['papers']):
                ending = ending or 'ORIGINAL_BATCH_PHASES_ENDED'
            elif worker['status'] != 'RUNNING' or not live(worker['pid']):
                ending = ending or 'ORIGINAL_WORKER_ABSENT_OR_ENDED'
        state['status'] = ending or state.get('status', 'OBSERVING')
        write_status(out, state)
        if ending:
            sealed(out / 'end.json', {**state, 'products_complete_claimed': False})
            for name, command in [
                ('final-audit', [sys.executable, 'scripts/design_lab/audit_system.py']),
                ('final-preservation', [sys.executable, 'scripts/design_lab/verify_original_history.py', '--baseline', str(args.baseline.resolve())]),
            ]:
                try:
                    r = subprocess.run(command, cwd=APP, capture_output=True, text=True, timeout=60)
                    value = {'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
                except (OSError, subprocess.TimeoutExpired) as exc:
                    value = {'exit_code': None, 'error': str(exc), 'status': 'AUDIT_NOT_COMPLETED'}
                sealed(out / (name + '.json'), {'created': time.time(), **value, 'model_calls': 0, 'native_jobs': 0, 'workbench_instances': 0})
            print(json.dumps({'observer': str(out), 'state': ending, 'products_complete_claimed': False}), flush=True)
            return 0 if ending in ('ORIGINAL_BATCH_PHASES_ENDED', 'OPERATOR_SIGNAL') else 1
        time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
