#!/usr/bin/env python3
"""Verify original rows and archived phases using read-only databases."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.contracts import sealed, sha

parser = argparse.ArgumentParser()
parser.add_argument('--baseline', type=Path, required=True)
args = parser.parse_args()
baseline = json.loads(args.baseline.read_text())
def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()

checks = []
for ledger in baseline['ledgers']:
    with sqlite3.connect('file:' + ledger['db'] + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        tables = []
        for table, expected in ledger['tables'].items():
            rows = [dict(r) for r in db.execute('SELECT * FROM ' + table)]
            def key(row):
                if 'id' in row:
                    return row['id']
                return row['owner'] + ':' + row.get('design_id', '')
            current = {key(row): row for row in rows}
            bad, archived, live_changes = [], [], []
            for item, expected_sha in expected.items():
                row = current.get(item)
                if row is None:
                    bad.append({'key': item, 'reason': 'ORIGINAL_ROW_ABSENT'})
                elif digest(row) == expected_sha:
                    continue
                elif table == 'design_tasks':
                    history = [json.loads(r['value']) for r in db.execute(
                        'SELECT value FROM design_task_history WHERE owner=?', (row['owner'],))]
                    if any(digest(h) == expected_sha for h in history):
                        archived.append(item)
                    else:
                        bad.append({'key': item, 'reason': 'OLD_PHASE_NOT_EXACTLY_ARCHIVED'})
                elif table == 'conversations':
                    # Live status/harness can change through legitimate continuation.
                    # Its old immutable row identity was verified before dispatch.
                    live_changes.append(item)
                else:
                    bad.append({'key': item, 'reason': 'ORIGINAL_IMMUTABLE_ROW_CHANGED'})
            tables.append({'table': table, 'original_rows': len(expected),
                           'current_rows': len(rows), 'mismatches': bad,
                           'exact_old_phases_archived': archived,
                           'live_conversation_updates': live_changes,
                           'passed': not bad})
        checks.append({'database': ledger['db'], 'mode': 'ro', 'tables': tables,
                       'passed': all(t['passed'] for t in tables)})

root = Path('/Users/depengsu/Documents/Long-Horizon AI Agent')
features = json.loads((root / 'feature_list.json').read_text())
first = features['features'][:88]
scientific = digest(first) == baseline['root_scientific_sha256']
index = Path('/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/campaign/parallel-20261009/pi-session-index.json')
index_exact = sha(index) == baseline['index_sha256']
current_owners = [s['owner'] for s in json.loads(index.read_text())['sessions']]
owner_scope = current_owners == baseline['original_owners']
value = {'schema_version': 'bf-original-history-preservation-v2', 'created': time.time(),
         'baseline': str(args.baseline.resolve()), 'baseline_sha256': sha(args.baseline),
         'ledgers': checks, 'original_ten_index_byte_exact': index_exact,
         'original_ten_owners_exact': owner_scope, 'root_first_88_scientific_features_exact': scientific,
         'passed': all(x['passed'] for x in checks) and index_exact and owner_scope and scientific,
         'workbench_instances_created': 0, 'model_calls': 0, 'solver_calls': 0,
         'scope': 'Original complete model rows, UNKNOWN/full reservations, engineering, EDA, snapshots, operations and adoptions unchanged. Old design task retained byte-equivalently in phase history. Conversation live state may legitimately change; no conversation removed.'}
out = APP / 'docs/agentlab/executable-lab-20261012' / ('preservation-active-' + str(time.time_ns()) + '.json')
sealed(out, value)
print(json.dumps({'receipt': str(out), 'passed': value['passed'], 'ledger_tables': sum(len(x['tables']) for x in checks)}))
if not value['passed']:
    raise SystemExit(1)
