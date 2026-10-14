#!/usr/bin/env python3
"""One idle, legitimate Workbench migration; queries never create another app.

Import metadata over existing Pi bytes and receipts. No source edits, candidate
engineering choice, native command, model call or historical row rewrite.
"""
import argparse
import fcntl
import json
from pathlib import Path
import sqlite3
import time

from bfworld.agentlab.design_lab.contracts import sealed, sha
from bfworld.agentlab.design_lab.paper_mainline import process_alive
from bfworld.agentlab.literature_campaign import DEFAULT_ROOT, read
from bfworld.agentlab.store import canonical, identity

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=DEFAULT_ROOT)
p.add_argument('--out',type=Path,required=True);p.add_argument('--desktop-proof',type=Path)
a=p.parse_args();root=a.root.resolve()
owner=next(s['owner'] for s in read(root/'campaign/parallel-20261009/pi-session-index.json')['sessions'] if s['paper_id']=='P01')
if owner!='pi-chat-b47a35e335bc68d4':raise ValueError('ORIGINAL_P01_OWNER_REQUIRED')
dbpath=root/'runtime/state/workbench.sqlite';queue=root/'campaign/parallel-20261009/pi-queue'

def records():
    with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        active=list(db.execute("SELECT id FROM conversations WHERE status IN ('RUNNING','STARTING','STOPPING')"))
        native=list(db.execute("SELECT id FROM engineering_jobs WHERE status IN ('RUNNING','QUEUED')"))
        eda=list(db.execute("SELECT id FROM eda_cli_jobs WHERE status IN ('RUNNING','QUEUED')"))
        if active or native or eda:raise ValueError('MIGRATION_REQUIRES_IDLE_NATIVE_AND_PI')
        old={table:{r['id']:identity(dict(r)) for r in db.execute('SELECT * FROM '+table)}
             for table in ('model_requests','engineering_jobs','eda_cli_jobs')}
        bound=db.execute('SELECT COUNT(*) FROM design_tasks WHERE owner=?',(owner,)).fetchone()[0]
        jobs={jid:json.loads(db.execute('SELECT request FROM engineering_jobs WHERE id=? AND owner=? AND status=\'SUCCEEDED\'',(jid,owner)).fetchone()[0])
              for jid in ('eng-d6b2ca501db8e7fa','eng-40c03b2d6cda1aa9','eng-9db41867521e453a','eng-dcbd2b0cbcc1140f','eng-6e2bc184592697d6')}
    return old,bound,jobs

before,bound,jobs=records()
if bound:raise ValueError('PAPER_ALREADY_BOUND_USE_READONLY_VIEW')
worker=read(queue/'worker.json')
if process_alive(worker.get('pid')):raise ValueError('MIGRATION_REQUIRES_DRAINED_WORKER')
a.out.mkdir(parents=True,exist_ok=False)
choice={'schema_version':'bf-paper-candidate-v1','files':['P01-R1-CANDIDATE-PLAN.md','contract.json'],
    'projects':sorted({j['parameters']['project_path'] for j in jobs.values()}),
    'selected_jobs':list(jobs),'eda_receipts':['eda-1603e9cff59789517bfa','eda-a669295e8a4851b45a93','eda-253707413fe24953016d'],
    'decision':'Import the existing Pi-authored R1 candidate and exact previous executions. The interrupted replacement is blocked, not accepted; no device or strategy is chosen by this metadata migration.'}
receipt=root/'runtime/participants'/owner/'eda-receipts/eda-a669295e8a4851b45a93.json'
fact={'operation_id':'import-ep-p01-r1-replace-d2-us1m-3','receipt_path':str(receipt.relative_to(root)),
      'receipt_sha256':sha(receipt)}
sealed(a.out/'migration-input.json',{'owner':owner,'selector':choice,'interrupted_write':fact,
    'historical_rows_sha256':identity(before),'original_index_sha256':sha(root/'campaign/parallel-20261009/pi-session-index.json')})
from bfworld.agentlab import literature_native
qualified=read(root/'campaign/native-qualification.json')
if qualified.get('status')!='PASS' or qualified['apparatus_identity']!=literature_native.apparatus_identity()[0]:
    raise ValueError('CURRENT_QUALIFIED_APPARATUS_REQUIRED')
from bfworld.agentlab.server import Workbench
with (queue/'worker.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    app=Workbench(root/'runtime/state')  # Intended migration writer, not a query instance.
    try:
        view=app.design_lab.handle(owner,{'action':'configure_paper','root':str(root),
            'sources':{'candidate.json':canonical(choice)},'interrupted_write':fact},operator=True)
        unknown_key=view['intent']['job_id']
        if a.desktop_proof:
            proof={'path':str(a.desktop_proof.resolve().relative_to(root)),'sha256':sha(a.desktop_proof)}
            restored=app.design_lab.handle(owner,{'action':'reconcile_native','job_id':unknown_key,'proof':proof},operator=True)
            sealed(a.out/'desktop-reconciliation.json',restored)
            view=app.design_lab.view(owner)
        check=app.design_lab.handle(owner,{'action':'check','operation_id':'migration-current-scope'})
        sealed(a.out/'view.json',view);sealed(a.out/'check.json',check)
    finally:
        app.design_lab.closing.set();app.design_lab.wake.set()
        app.stop.set();app.thread.join(3);app.lock.close()
after,bound,_=records()
if before!=after:raise ValueError('MIGRATION_CHANGED_HISTORICAL_ROWS')
result={'status':'PASS','created':time.time(),'owner':owner,'control_route':view['control_route'],
    'working_design':view['working_design'],'task_id':view['task_id'],'task_count':bound,
    'unknown_operation':unknown_key,'unknown_blocker_retained':not bool(a.desktop_proof),
    'interrupted_unknown_history_retained':True,
    'historical_records_preserved':{table:len(rows) for table,rows in before.items()},
    'view':{'path':str(a.out/'view.json'),'sha256':sha(a.out/'view.json')},
    'check':{'path':str(a.out/'check.json'),'sha256':sha(a.out/'check.json')},
    'model_calls':0,'new_solver_runs':0,'participant_engineering_edits':0,
    'full_product_passed':False,'physical':'NOT_TESTED','method_gain':'NOT_EVALUATED'}
sealed(a.out/'result.json',result);print(json.dumps(result,ensure_ascii=False))
