#!/usr/bin/env python3
"""Dispatch queued original Pi owners; never combine papers into one session."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from bfworld.agentlab.literature_campaign import DEFAULT_ROOT, read, digest
from bfworld.agentlab.literature_continuation import load_authority
from bfworld.agentlab.store import canonical

REPO=Path(__file__).resolve().parents[1]


def save(path, value):
    temporary=path.with_suffix('.next');temporary.write_text(canonical(value));temporary.replace(path)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--watch',action='store_true');args=parser.parse_args();root=args.root
    queue=root/'campaign/parallel-20261009/pi-queue';queue.mkdir(exist_ok=True)
    with (queue/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        save(queue/'worker.json',{'pid':os.getpid(),'started':time.time(),'status':'RUNNING','mode':'ten-original-independent-Pi-owners'})
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
                if item.get('schema_version')!='bf-paper-continuation-queue-v1' or item.get('status')!='QUEUED':continue
                if allowed.get(item.get('owner'))!=item.get('paper') or item.get('authorization_sha256')!=scope['authority_sha256']:
                    item.update(status='REJECTED',error='ORIGINAL_PI_SCOPE_CHANGED');save(path,item);continue
                candidates.append((item['created'],item['paper'],path,item))
            if not candidates:
                save(queue/'worker.json',{'pid':os.getpid(),'status':'IDLE','updated':time.time()})
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
                current.update(status='CHECKS_COMPLETE' if evaluation.get('status')=='PASS' else 'REPAIR_REQUIRED',
                    evaluation_status=evaluation.get('status'),execution=result.get('execution'),new_model_calls=result.get('new_model_calls'),
                    full_product_passed=False,physical_verified=False)
            else:current.update(status='DISPATCH_FAILED',error=log.read_text()[-1600:])
            save(path,current)
            print(canonical({'paper':paper,'owner':item['owner'],'state':current['status'],'new_model_calls':current.get('new_model_calls')}),flush=True)


if __name__=='__main__':main()
