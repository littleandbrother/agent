#!/usr/bin/env python3
"""Check real SDK restoration with zero model calls and no engineering replay."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import urllib.request

APP = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, default=Path('/Users/depengsu/.local/share/bf-agent-runtime'))
parser.add_argument('--port', type=int, default=8768)
parser.add_argument('--session-id')
args = parser.parse_args()
out = APP / 'docs/agentlab/refactor-r0-r2-20261011/trial'
home = args.runtime / 'workbench'
owner = args.session_id or json.loads((out / 'owner.json').read_text())['owner']
def inventory():
    with sqlite3.connect('file:' + str(home / 'state/workbench.sqlite') + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        result = {}
        for table in ('model_requests', 'design_operations'):
            rows = [dict(x) for x in db.execute('SELECT * FROM ' + table + ' ORDER BY id')]
            result[table] = {'count': len(rows), 'sha256': hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
        task = dict(db.execute('SELECT current_design,revision,submission FROM design_tasks WHERE owner=?', (owner,)).fetchone())
        result['task'] = task
    return result
before = inventory()
pointer = home / 'sessions' / owner / 'receipt.json'
previous = pointer.read_bytes()
request = urllib.request.Request('http://127.0.0.1:' + str(args.port) + '/api/design-lab',
    data=json.dumps({'action': 'start', 'session_id': owner, 'dry_run': True}).encode(),
    headers={'Authorization': 'Bearer ' + (home / 'state/operator.token').read_text().strip(), 'Content-Type': 'application/json'})
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(request, timeout=20) as response:
    dispatched = json.load(response)
for _ in range(240):
    if pointer.read_bytes() != previous:
        receipt = json.loads(pointer.read_text())
        if receipt['status'] in ('COMPLETED', 'FAILED'):
            break
    time.sleep(.25)
else:
    raise TimeoutError('DRY_VERIFY_RECEIPT_NOT_FOUND')
assert receipt['status'] == 'COMPLETED' and receipt['dry_run'] is True, receipt.get('error')
trace = Path(receipt['trace_path'])
assert trace.name == 'trace-sealed.jsonl' and hashlib.sha256(trace.read_bytes()).hexdigest() == receipt['trace_sha256']
# Only export the public scalar restoration facts. Private reasoning stays local.
resume = [json.loads(line).get('resume_message_count') for line in trace.read_text().splitlines() if '"resume_message_count"' in line]
assert resume and resume[-1] > 0
after = inventory()
assert before == after
identifier = str(time.time_ns())
receipt_path = out / ('zero-model-recovery-controller-' + identifier + '.json')
receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
record = {'schema_version': 'bf-final-dry-recovery-v1', 'owner': owner, 'time': time.time(),
          'harness_id': receipt['harness']['harness_id'], 'status': receipt['status'],
          'immutable_attempt_trace_verified': True, 'trace_path': str(trace), 'trace_sha256': receipt['trace_sha256'],
          'fee_operation_and_adopted_task_unchanged': before == after, 'before': before, 'after': after,
          'resume_message_count': resume[-1], 'new_model_requests': 0, 'new_native_solver_calls': 0,
          'controller_receipt': receipt_path.name,
          'paid_run_harness_id': json.loads((out / 'pi-controller-receipt.json').read_text())['harness']['harness_id'],
          'qualification_boundary': 'Post-run recovery and trace sealing only; not a new paid solving trial.'}
path = out / ('zero-model-recovery-' + identifier + '.json')
path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(json.dumps({'status': 'PASS', 'resume_message_count': resume[-1], 'harness_id': record['harness_id'],
                  'new_model_calls': 0, 'new_engineering_operations': 0, 'report': str(path)}))
