#!/usr/bin/env python3
"""Dispatch queued original Pi owners; never combine papers into one session."""
import argparse
import fcntl
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from bfworld.agentlab.literature_campaign import DEFAULT_ROOT, read, digest
from bfworld.agentlab.literature_continuation import load_authority
from bfworld.agentlab.store import canonical
from bfworld.agentlab.design_lab.paper_mainline import selected_paper
from bfworld.agentlab.design_lab.paper_candidate import readonly_bound

REPO=Path(__file__).resolve().parents[1]


def save(path, value):
    temporary=path.with_suffix('.next');temporary.write_text(canonical(value));temporary.replace(path)


def live_queue_item(path,item):
    return (item.get('schema_version')=='bf-paper-continuation-queue-v1' and
            item.get('status')=='QUEUED' and path.name==str(item.get('owner'))+'.json')


def upstream_blocker(root,owner,since):
    """Fresh actual provider evidence only; never rewrite UNKNOWN or old fees."""
    path=Path(root)/'runtime/state/workbench.sqlite'
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT id,status,error,created FROM model_requests WHERE owner=? '
                       'AND created>=? ORDER BY created DESC LIMIT 1',(owner,since)).fetchone()
    if not row or row['status'] not in ('FAILED','UNKNOWN') or not row['error']:return None
    match=re.search(r'HTTP(?: Error)?\s+(401|402)\b',row['error'])
    if not match:return None
    return {'request_id':row['id'],'status':row['status'],'http_status':int(match[1]),
            'created':row['created'],'error':row['error'],
            'unknown_and_reservation_preserved':True,'automatic_retries':0}


def candidate_outcome(result):
    """A previous intent cannot turn this attempt's failure into continuation."""
    candidate=result.get('candidate_lifecycle') if result.get('control_route')=='candidate-lifecycle' else None
    if not candidate:return None,None
    if (result.get('execution') or {}).get('status')=='FAILED':return 'RUN_FAILED',None
    decision=result.get('candidate_decision_current_attempt')
    if not decision:return 'CANDIDATE_REVIEW_REQUIRED',None
    kind=decision.get('kind')
    if candidate.get('status')=='REVIEW_SUBMITTED':return 'CANDIDATE_REVIEW_SUBMITTED',decision
    return ('CANDIDATE_'+kind,decision) if kind in ('BLOCKED','REJECT','CONTINUE') else ('CANDIDATE_REVIEW_REQUIRED',None)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--watch',action='store_true')
    parser.add_argument('--paper',action='append',choices=[f'P{i:02}' for i in range(1,11)],
                        help='Only these original paper owners; other queue records stay untouched')
    args=parser.parse_args();root=args.root;selected=set(args.paper) if args.paper else None
    queue=root/'campaign/parallel-20261009/pi-queue';queue.mkdir(exist_ok=True)
    with (queue/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        save(queue/'worker.json',{'pid':os.getpid(),'started':time.time(),'status':'RUNNING',
            'mode':'selected-original-Pi-owners' if selected else 'ten-original-independent-Pi-owners',
            'selected_papers':sorted(selected) if selected else None})
        while True:
            try:scope=load_authority(root)
            except (ValueError,OSError) as exc:
                save(queue/'worker.json',{'pid':os.getpid(),'status':'WINDOW_CLOSED','error':str(exc),'ended':time.time()});return
            ready=read(root/'campaign/parallel-20261009/READY.json')
            if ready.get('status')!='PASS' or ready.get('qualification_sha256')!=digest(root/'campaign/native-qualification.json'):
                save(queue/'worker.json',{'pid':os.getpid(),'status':'WAITING_QUALIFIED_RELEASE','updated':time.time()})
                if not args.watch:return
                time.sleep(2);continue
            if not scope:raise ValueError('CONTINUATION_USER_AUTHORITY_REQUIRED')
            allowed={p['owner']:p['paper_id'] for p in scope['owners']}
            candidates=[]
            for path in queue.glob('pi-chat-*.json'):
                item=read(path)
                # Historical backups and stop receipts can share this glob.
                # Only the canonical original-owner file is a live queue item.
                if not live_queue_item(path,item):continue
                if not selected_paper(item,selected):continue
                if allowed.get(item.get('owner'))!=item.get('paper') or item.get('authorization_sha256')!=scope['authority_sha256']:
                    item.update(status='REJECTED',error='ORIGINAL_PI_SCOPE_CHANGED');save(path,item);continue
                candidates.append((item['created'],item['paper'],path,item))
            if not candidates:
                save(queue/'worker.json',{'pid':os.getpid(),'status':'IDLE' if args.watch else 'DRAINED',
                    'selected_papers':sorted(selected) if selected else None,'updated':time.time()})
                if not args.watch:return
                time.sleep(2);continue
            _,paper,path,item=min(candidates)
            stop=queue/(item['owner']+'-stop.json')
            if stop.exists():
                # A later explicit message resumes this owner; preserve the stop receipt.
                if stop.stat().st_mtime>item['created']:
                    item.update(status='CANCELLED',ended=time.time());save(path,item);continue
                stop.rename(queue/(item['owner']+'-stop-'+str(time.time_ns())+'.receipt'))
            log=queue/(item['id']+'.log')
            command=[sys.executable,str(REPO/'scripts/literature_paper_resume.py'),paper,'--phase',item['phase'],'--root',str(root),'--message-file',str(path)]
            if readonly_bound(root,item['owner']):command.append('--candidate')
            item.update(status='RUNNING',started=time.time(),log=log.name);save(path,item)
            save(queue/'worker.json',{'pid':os.getpid(),'status':'RUNNING','paper':paper,'owner':item['owner'],'updated':time.time()})
            print(canonical({'paper':paper,'owner':item['owner'],'phase':item['phase'],'state':'DISPATCHING_ORIGINAL_PI_SESSION'}),flush=True)
            with log.open('a') as output:
                proc=subprocess.Popen(command,cwd=REPO,env=os.environ,stdout=output,stderr=subprocess.STDOUT)
                item['pid']=proc.pid;save(path,item);code=proc.wait()
            current=read(path);current.update(exit_code=code,ended=time.time())
            records=[]
            for line in log.read_text().splitlines():
                try:value=json.loads(line)
                except ValueError:continue
                if value.get('paper')==paper and 'results' in value:records=value['results']
            if records:
                result=records[-1];evaluation=result.get('evaluation',{})
                candidate=result.get('candidate_lifecycle') if result.get('control_route')=='candidate-lifecycle' else None
                status,decision=candidate_outcome(result)
                if not candidate:status='FILE_CHECKS_COMPLETE' if evaluation.get('status')=='PASS' else 'REPAIR_REQUIRED'
                current.update(status=status,
                    evaluation_status=evaluation.get('status'),execution=result.get('execution'),new_model_calls=result.get('new_model_calls'),
                    full_product_passed=False,physical_verified=False,digital_core_status='INDEPENDENT_REVIEW_REQUIRED')
                if candidate:current.update(control_route='candidate-lifecycle',working_design=candidate['working_design'],candidate_decision=decision,historical_candidate_intent=candidate['intent'])
            else:current.update(status='DISPATCH_FAILED',error=log.read_text()[-1600:])
            save(path,current)
            print(canonical({'paper':paper,'owner':item['owner'],'state':current['status'],'new_model_calls':current.get('new_model_calls')}),flush=True)
            block=upstream_blocker(root,item['owner'],item['started'])
            if block:
                save(queue/'worker.json',{'pid':os.getpid(),'status':'PROVIDER_BLOCKED',
                    'paper':paper,'owner':item['owner'],'evidence':block,'ended':time.time(),
                    'remaining_queue_preserved':True})
                print(canonical({'state':'PROVIDER_BLOCKED','paper':paper,'http_status':block['http_status']}),flush=True)
                return


if __name__=='__main__':main()
