#!/usr/bin/env python3
"""Read-only linkage of existing native jobs and raw bytes in a sealed export."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile


def export(home, study, bundle):
    db = sqlite3.connect((home / 'state/workbench.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    records = []
    with db, zipfile.ZipFile(bundle) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP_CRC_MISMATCH')
        owners = db.execute('SELECT owner,trial FROM research_model_owners WHERE protocol=? ORDER BY trial', (study,)).fetchall()
        declared_trials = {t['id'] for t in json.loads(archive.read('protocol.json'))['pi_trials']}
        for actor in owners:
            if actor['trial'] not in declared_trials:
                continue  # transport-only diagnostic owner is not a Pi design trajectory
            actions = json.loads(archive.read(actor['trial'] + '-actions.json'))
            events = {r['seq']: json.loads(r['data']) for r in db.execute('SELECT seq,data FROM chat_events WHERE conversation=?', (actor['owner'],))}
            submission = db.execute('SELECT receipt FROM simulation_task_submissions WHERE owner=?', (actor['owner'],)).fetchone()
            selected = json.loads(submission['receipt']) if submission else None
            for row in db.execute('SELECT * FROM engineering_jobs WHERE owner=? ORDER BY created', (actor['owner'],)):
                request = json.loads(row['request'])
                identity_payload=json.dumps({k:v for k,v in request.items() if k!='turn_id'},sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
                if hashlib.sha256(identity_payload.encode()).hexdigest() != row['request_hash']:
                    raise ValueError('REQUEST_HASH_MISMATCH')
                starts = [a for a in actions if a['tool'] == 'bf_engineering' and a['args'].get('action') == 'run' and a['args'].get('operation_id') == row['operation']]
                for action in starts:
                    if events.get(action['seq'], {}).get('args') != action['args']:
                        raise ValueError('ACTION_SOURCE_MISMATCH')
                result_path = f"candidates/{row['id']}/result.json"
                original = (home / 'engineering' / row['id'] / 'result.json').read_bytes()
                if archive.read(result_path) != original:
                    raise ValueError('RAW_RESULT_MISMATCH')
                digest = hashlib.sha256(original).hexdigest()
                manifest = json.loads(row['result'])['artifacts']
                if next(a['sha256'] for a in manifest if a['name'] == 'result.json') != digest:
                    raise ValueError('RESULT_MANIFEST_MISMATCH')
                seals = [a for a in actions if a['tool'] == 'bf_engineering' and a['args'].get('action') == 'submit' and a['args'].get('job_id') == row['id']]
                for action in seals:
                    if events.get(action['seq'], {}).get('args') != action['args']:
                        raise ValueError('SUBMISSION_ACTION_MISMATCH')
                is_selected = bool(selected and selected['job_id'] == row['id'])
                if is_selected and (not seals or selected['result_sha256'] != digest):
                    raise ValueError('SUBMISSION_RESULT_MISMATCH')
                if not starts:
                    raise ValueError('NO_SOURCE_BOUND_RUN_ACTION')
                records.append({'trial': actor['trial'], 'owner': actor['owner'], 'job_id': row['id'],
                    'operation_id': row['operation'], 'request': request, 'request_sha256': row['request_hash'],
                    'status': row['status'], 'created': row['created'], 'ended': row['ended'],
                    'actions': starts, 'result': {'zip_path': result_path, 'bytes': len(original), 'sha256': digest},
                    'artifacts': manifest, 'submission': selected if is_selected else None, 'submit_actions': seals,
                    'instruction_delivery': 'unknown', 'feedback_reading': 'unknown'})
    db.close()
    return {'schema': 'native-job-source-links-v1', 'study': study,
        'bundle': {'name': bundle.name, 'sha256': hashlib.sha256(bundle.read_bytes()).hexdigest()},
        'jobs': records, 'counts': {'unique_jobs': len({r['job_id'] for r in records}),
            'submissions': sum(bool(r['submission']) for r in records)},
        'scope': 'Existing actual actions, terminal results and submissions only; no rerun or inference about model feedback use.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, required=True)
    p.add_argument('--study', required=True)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    value = export(a.home, a.study, a.bundle)
    with a.output.open('x') as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write('\n')
    print(json.dumps(value['counts']))
