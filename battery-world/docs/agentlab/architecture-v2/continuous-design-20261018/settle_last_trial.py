#!/usr/bin/env python3
"""Append the last trial's late execution accounting; never restart a job."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'scripts'))
from v2_common import RUNTIME, action
from run_organization_pilot import seal


def read(path):return json.loads(path.read_text())


def main():
    trial=RUNTIME/'continuous-design/pilot/trials/T2-short-validity--fixed'
    original=read(trial/'final.json');entry=original['entry']
    state=action(entry['owner'],'repository_state')
    if state['status']!='FAILED' or state['model_calls']!=28 or state['unknown_requests']:
        raise ValueError('TRIAL_NOT_QUIESCENT')
    view=action(entry['owner'],'repository_view')
    known={e['id'] for e in original['view']['task_executions']}
    late=[e for e in view['task_executions'] if e['id'] not in known]
    if len(late)!=1 or late[0]['status']!='FAILED':raise ValueError('UNEXPECTED_LATE_EXECUTION')
    execution=late[0]
    if execution['target']!=original['metrics']['current_system']:raise ValueError('LATE_INPUT_CHANGED')
    repo=RUNTIME/'workbench/design-lab/repository';blobs=repo/'blobs'
    failure=read(blobs/execution['artifacts']['failure.json']['sha256'])
    if failure['error']!='FEEDBACK_FIXED_POINT_NOT_REACHED':raise ValueError('UNEXPECTED_FAILURE')
    iterations=read(blobs/execution['artifacts']['coarse/iterations.json']['sha256'])
    keys=[i['native']['key'] for i in iterations if not i['native']['reused']]
    for ref in execution['artifacts'].values():
        if hashlib.sha256((blobs/ref['sha256']).read_bytes()).hexdigest()!=ref['sha256']:
            raise ValueError('LATE_ARTIFACT_CHANGED')
    for key in keys:
        folder=repo/'feedback-native-cache'/key;completed=read(folder/'completed.json')
        if completed['key']!=key or completed['status']!='SUCCEEDED':raise ValueError('NATIVE_NOT_COMPLETED')
        for name,digest in completed['outputs'].items():
            if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:raise ValueError('NATIVE_OUTPUT_CHANGED')
    db=sqlite3.connect((RUNTIME/'workbench/state/workbench.sqlite').as_uri()+'?mode=ro',uri=True)
    owners=[entry['owner'],*original['metrics']['workers']]
    calls=sum(db.execute('SELECT count(*) FROM model_requests WHERE owner=?',(o,)).fetchone()[0] for o in owners)
    db.close()
    if calls!=original['metrics']['model_calls']:raise ValueError('TRIAL_RESAMPLED')
    value={'schema_version':'pilot-post-trial-settlement-v1','key':entry['key'],
        'original_final_sha256':hashlib.sha256((trial/'final.json').read_bytes()).hexdigest(),
        'original_model_calls':calls,'new_model_requests':0,'new_native_solves':0,
        'late_executions':late,'unreported_native_dispatches':keys,
        'failure':failure,'reason':'Controller request guard ended before the in-flight execution receipt was registered',
        'original_final_preserved':True}
    seal(trial/'post-trial-settlement.json',value)
    out=Path(__file__).parent/'results/last-trial-settlement.json'
    seal(out,value)
    print(json.dumps({'status':'PASS','late_executions':len(late),'native_dispatches':len(keys),'new_model_requests':0,'new_native_solves':0}))


if __name__=='__main__':main()
