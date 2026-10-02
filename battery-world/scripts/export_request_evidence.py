#!/usr/bin/env python3
"""Read-only request-presence audit; never exports private prompt bodies."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


def audit(db, owners):
    db.row_factory = sqlite3.Row
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    output, errors = [], []
    for owner in owners:
        requests = db.execute('SELECT id,request_hash,status FROM model_requests WHERE owner=? ORDER BY created,id', (owner,))
        for request in requests:
            row = db.execute('SELECT * FROM model_request_evidence WHERE owner=? AND request_id=?', (owner, request['id'])).fetchone() if 'model_request_evidence' in tables else None
            item = {'owner': owner, 'request_id': request['id'], 'request_sha256': request['request_hash'],
                    'ledger_status': request['status'], 'method': {'status': 'unknown'}, 'feedback': [],
                    'feedback_linkage_status': 'unknown', 'reason': 'missing_post_projection_wire_receipt'}
            if row:
                receipt = json.loads(row['receipt'])
                digest = hashlib.sha256(row['wire'].encode()).hexdigest()
                anchors = [json.loads(r['data']).get('request_evidence_sha256') for r in db.execute(
                    "SELECT data FROM events WHERE owner=? AND kind='model_dispatched' AND json_extract(data,'$.request_id')=?", (owner, request['id']))]
                if (digest != request['request_hash'] or digest != receipt.get('wire_sha256')
                        or receipt.get('owner') != owner or receipt.get('request_id') != request['id']
                        or hashlib.sha256(row['receipt'].encode()).hexdigest() not in anchors):
                    errors.append({'request_id': request['id'], 'error': 'WIRE_IDENTITY_MISMATCH'})
                    item['reason'] = 'invalid_wire_receipt'
                else:
                    item.update(method=receipt['method'], feedback=receipt['feedback'],
                        feedback_linkage_status='recorded_post_projection_presence', reason=None)
            output.append(item)
    return {'schema': 'bf-request-presence-audit-v1', 'owners': owners, 'requests': output,
            'integrity_errors': errors, 'counts': {'requests': len(output),
                'with_wire_receipt': sum(r['feedback_linkage_status'] != 'unknown' for r in output),
                'historical_unknown': sum(r['reason'] == 'missing_post_projection_wire_receipt' for r in output)},
            'scope': 'Request presence only. Historical configuration and tool execution do not establish instruction delivery or feedback use; persisted submissions remain separate facts.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--owner', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        result = audit(db, args.owner)
    with args.output.open('x') as target:
        json.dump(result, target, ensure_ascii=False, indent=2)
        target.write('\n')
    print(json.dumps(result['counts']))
    if result['integrity_errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
