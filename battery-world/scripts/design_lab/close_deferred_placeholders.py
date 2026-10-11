#!/usr/bin/env python3
"""Withdraw only this turn's deferred UI launch stubs, retain completed runs.

The standalone Pi experiments already ran through the existing provider. Their
QUEUED UI placeholders were not delivered by the ordinary chat controller.
Leaving them queued would allow an accidental generic retry of completed work.
Use the one server's append-only recall API, never a direct database mutation.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import urllib.request

APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.contracts import sealed
from bfworld.agentlab.store import identity
OUT=APP/'docs/agentlab/refactor-r3-r5-20261012'
dbpath=Path('/Users/depengsu/.local/share/bf-agent-runtime/workbench/state/workbench.sqlite')
originals=set(json.loads((APP/'docs/agentlab/refactor-r0-r2-20261011/baseline.json').read_text())['original_owners'])
owners=sorted({json.loads(p.read_text())['owner'] for p in OUT.rglob('owner.json')})
assert not originals.intersection(owners), 'ORIGINAL_OWNER_DENIED'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
token=(dbpath.parent/'operator.token').read_text().strip()
def query():
    with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        fees={r['id']:identity(dict(r)) for r in db.execute('SELECT * FROM model_requests') if r['owner'] in owners}
        pending=[dict(r) for r in db.execute("SELECT id,conversation,operation,status,text FROM chat_messages WHERE status='QUEUED'") if r['conversation'] in owners]
    return fees,pending
before,pending=query();changes=[]
for message in pending:
    assert message['operation'].startswith(('method-study-','method-followup-')), 'UNOWNED_OPERATION_DENIED'
    request=urllib.request.Request('http://127.0.0.1:8768/api/conversations/'+message['conversation']+'/recall',
        data=json.dumps({'message_id':message['id']}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with opener.open(request,timeout=20) as response:reply=json.load(response)
    # Wait for local zero-model context branching; no provider request or job.
    until=time.monotonic()+25
    while True:
        with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
            row=db.execute('SELECT status,error FROM chat_recalls WHERE id=?',(reply['id'],)).fetchone()
        if row[0]=='COMPLETE':break
        if row[0]=='FAILED':raise RuntimeError('PLACEHOLDER_RECALL_FAILED:'+str(row[1]))
        if time.monotonic()>until:raise RuntimeError('PLACEHOLDER_RECALL_PENDING')
        time.sleep(.1)
    changes.append({'owner':message['conversation'],'message_id':message['id'],
        'original_text_sha256':hashlib.sha256(message['text'].encode()).hexdigest(),'recall_id':reply['id'],
        'terminal_status':'WITHDRAWN','completed_external_trial_retained':True})
after,remaining=query();assert before==after, 'MODEL_LEDGER_CHANGED';assert not remaining, 'PLACEHOLDER_STILL_QUEUED'
receipt={'schema_version':'bf-external-pi-launch-stub-closeout-v1','time':time.time(),'changed':changes,
    'database_reads':'mode=ro','mutations':'Existing operator recall API only','new_models':0,'new_native_jobs':0,
    'fee_rows_verified_unchanged':len(before),'original_ten_owners_changed':False,
    'private_method_sdk_sessions_and_completed_engineering_unchanged':True,
    'reason':'Retire undelivered generic launch stubs for this turn; completed external Pi trials remain in immutable receipts. This is not cancellation or deletion of the completed design.'}
path=OUT/('deferred-placeholders-'+str(time.time_ns())+'.json');sealed(path,receipt)
print(json.dumps({'closed_stubs':len(changes),'fee_rows_unchanged':len(before),'receipt':str(path)}))
