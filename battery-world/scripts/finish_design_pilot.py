#!/usr/bin/env python3
"""Supervise the already-authorized four-trial pilot. Never choose a design or erase an attempt."""
import json
import os
import sqlite3
import time
from pathlib import Path
import run_design_pilot as pilot

ROOT=pilot.DEFAULT_ROOT
PROTOCOL=pilot.prepare(ROOT)['protocol']
HOME=pilot.HOME_ROOT

def snapshot():
    db=sqlite3.connect((HOME/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    study=dict(db.execute('SELECT * FROM research_model_studies WHERE protocol=?',(PROTOCOL['id'],)).fetchone())
    result=[]
    for trial in PROTOCOL['pi_trials']:
        owner=db.execute('SELECT owner FROM research_model_owners WHERE protocol=? AND trial=?',(PROTOCOL['id'],trial['id'])).fetchone()
        row={'trial':trial,'owner':owner['owner'] if owner else None}
        if owner:
            owner=owner['owner'];row['conversation']=dict(db.execute('SELECT status,error FROM conversations WHERE id=?',(owner,)).fetchone())
            row['submitted']=bool(db.execute('SELECT 1 FROM simulation_task_submissions WHERE owner=?',(owner,)).fetchone())
            usage=list(db.execute('SELECT * FROM model_requests WHERE owner=?',(owner,)))
            row['active_provider']=any(r['status']=='DISPATCHED' for r in usage)
            row['cost_upper_usd']=sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in usage)
            cap=db.execute('SELECT max_usd FROM owner_model_caps WHERE owner=?',(owner,)).fetchone()
            row['owner_ceiling_usd']=cap['max_usd'] if cap else PROTOCOL['max_usd_per_trial']
            launch=HOME/'sessions'/owner/'receipt.json'
            receipt=json.loads(launch.read_text()) if launch.exists() else {}
            row['active_process']=False
            if receipt.get('status')=='RUNNING' and receipt.get('pid'):
                try:os.kill(receipt['pid'],0);row['active_process']=True
                except ProcessLookupError:pass
        result.append(row)
    db.close();return study,result


def main():
    import fcntl
    lock=(ROOT/'finish-supervisor.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    receipt=ROOT/'finish-supervisor.json'
    if receipt.exists():raise ValueError('SUPERVISOR_ALREADY_RECORDED')
    authority={'started':time.time(),'original_authorization_sha256':pilot.file_hash(ROOT/'continuation-authorization.json'),
               'scope':'Finish exactly four existing trajectories; no new designs supplied by operator; preserve each transport recovery.',
               'max_continuations_per_trial':6,'existing_cost_limits_retained':True}
    pilot.write_json(receipt,authority)
    terminal={};last=None
    while True:
        study,rows=snapshot()
        state=[(r['trial']['id'],r.get('conversation',{}).get('status','NOT_STARTED'),r.get('submitted',False),r.get('active_provider',False)) for r in rows]
        if state!=last:print(json.dumps(state),flush=True);last=state
        if time.time()>=study['expires']:break
        active=sum(r.get('conversation',{}).get('status') in ('STARTING','RUNNING','STOPPING') for r in rows)
        for row in rows:
            tid=row['trial']['id'];directory=ROOT/'trials'/tid
            if tid in terminal:continue
            if row.get('submitted'):
                if row['active_provider'] or row['active_process']:continue
                terminal[tid]='submitted';continue
            if row.get('active_provider') or row.get('active_process') or row.get('conversation',{}).get('status') in ('STARTING','RUNNING','STOPPING'):continue
            if not row['owner']:
                # The primary runner exclusively owns new trials and their
                # first receipts. This supervisor only resumes closed attempts.
                continue
            error=row['conversation'].get('error') or ''
            if 'USD_BUDGET' in error or row['cost_upper_usd']>=row['owner_ceiling_usd']-.005:
                terminal[tid]='authorized_cost_boundary';continue
            if not (directory/'receipt.json').exists():
                continue
            attempts=list(directory.glob('continuation-*/start.json'))
            if any(not (p.parent/'receipt.json').exists() for p in attempts):continue
            if len(attempts)>=6:terminal[tid]='transport_recoveries_exhausted';continue
            print('RECOVER_WITHOUT_NEW_PARAMETERS',tid,flush=True)
            try:pilot.recover_trial(ROOT,tid)
            except Exception as exc:
                terminal[tid]='supervisor_error:'+type(exc).__name__+':'+str(exc)
        if len(terminal)==len(rows):break
        time.sleep(10)
    study,rows=snapshot()
    summary={'started':authority['started'],'ended':time.time(),'terminal':terminal,'trials':rows,
             'all_submitted':all(r.get('submitted') for r in rows),'operator_selected_candidates':0}
    pilot.write_json(ROOT/'finish-summary.json',summary)
    print(json.dumps({'all_submitted':summary['all_submitted'],'terminal':terminal}),flush=True)

if __name__=='__main__':main()
