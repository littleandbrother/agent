#!/usr/bin/env python3
"""Read-only full-row comparison against R0; never opens a Workbench."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time

APP = Path(__file__).resolve().parents[2]
OUT = APP / 'docs/agentlab/refactor-r0-r2-20261011'
baseline = json.loads((OUT / 'baseline.json').read_text())
def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
counts = []
for ledger in baseline['ledgers']:
    with sqlite3.connect('file:' + ledger['db_path'] + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        for key, digest in ledger['ledger_row_hashes'].items():
            row = db.execute('SELECT * FROM model_requests WHERE id=?', (key,)).fetchone()
            assert row is not None and identity(dict(row)) == digest, 'OLD_FEE_ROW_CHANGED:' + key
        for key, record in ledger['unknown'].items():
            row = db.execute('SELECT * FROM model_requests WHERE id=?', (key,)).fetchone()
            assert row is not None and identity(dict(row)) == record['row_sha256'], 'UNKNOWN_ROW_CHANGED:' + key
    counts.append({'db_path': ledger['db_path'], 'original_fee_rows_verified': len(ledger['ledger_row_hashes']),
                   'unknown_full_rows_verified': len(ledger['unknown'])})
for relative, digest in baseline['source_files'].items():
    assert sha(Path(baseline['original_code']) / relative) == digest, 'ORIGINAL_SOURCE_CHANGED:' + relative
index = baseline['session_index']
assert sha(index['path']) == index['sha256'], 'ORIGINAL_OWNER_INDEX_CHANGED'
environment = baseline['environment']
for name, digest in environment['files'].items():
    assert sha(Path(environment['root']) / name) == digest, 'D5_INPUT_CHANGED:' + name
receipt = {'schema_version': 'bf-original-state-preservation-v1', 'time': time.time(), 'passed': True,
           'ten_original_owners': baseline['original_owners'], 'ledgers': counts,
           'original_owner_fee_rows_verified': sum(c['original_fee_rows_verified'] for c in counts),
           'original_python_sources_verified': len(baseline['source_files']), 'original_index_unchanged': True,
           'frozen_D5_files_verified': len(environment['files']),
           'native_RAW_readback': 'R0 sealed full SHA readback retained; no new analog solve or redundant full RAW load.',
           'new_native_solver_calls': 0, 'database_access': 'mode=ro'}
path = OUT / ('preservation-final-' + str(time.time_ns()) + '.json')
path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
print(json.dumps({'passed': True, 'original_fee_rows_verified': receipt['original_owner_fee_rows_verified'],
                  'source_files_verified': receipt['original_python_sources_verified'], 'receipt': str(path)}))
