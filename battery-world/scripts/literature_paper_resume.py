#!/usr/bin/env python3
"""Separate paper task entry points; serialize the shared native apparatus."""
import argparse,fcntl,json,time,importlib
from pathlib import Path
from bfworld.agentlab.literature_campaign import DEFAULT_ROOT,read,digest
from bfworld.agentlab.literature_continuation import load_authority

def main():
    p=argparse.ArgumentParser();p.add_argument('paper',choices=[f'P{i:02}' for i in range(1,11)])
    p.add_argument('--phase',required=True,choices=['eda','firmware','engineering-repair','engineering-review','delivery'])
    p.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    p.add_argument('--message-file',type=Path);a=p.parse_args()
    message=None
    if a.message_file:
        file=a.message_file.resolve();queue=(a.root/'campaign/parallel-20261009/pi-queue').resolve()
        if file.parent!=queue or not file.is_file() or file.is_symlink():raise ValueError('OPERATOR_QUEUE_MESSAGE_REQUIRED')
        item=read(file)
        if item['paper']!=a.paper or item['phase']!=a.phase:raise ValueError('OPERATOR_QUEUE_SCOPE_MISMATCH')
        message=item.get('operator_text')
    ready=read(a.root/'campaign/parallel-20261009/READY.json')
    if ready['status']!='PASS' or ready['qualification_sha256']!=digest(a.root/'campaign/native-qualification.json'):
        raise ValueError('QUALIFIED_CONTINUATION_ENTRY_REQUIRED')
    if not load_authority(a.root):raise ValueError('CONTINUATION_USER_AUTHORITY_REQUIRED')
    slot=a.root/'campaign/parallel-20261009/native-apparatus-dispatch.lock'
    with slot.open('a') as lock:
        print(json.dumps({'paper':a.paper,'state':'WAITING_NATIVE_APPARATUS_SLOT','time':time.time()}),flush=True)
        fcntl.flock(lock,fcntl.LOCK_EX)
        ready=read(a.root/'campaign/parallel-20261009/READY.json')
        if ready['status']!='PASS' or ready['qualification_sha256']!=digest(a.root/'campaign/native-qualification.json'):
            raise ValueError('QUALIFIED_CONTINUATION_ENTRY_REQUIRED')
        load_authority(a.root)
        from bfworld.agentlab import literature_native
        importlib.reload(literature_native)
        print(json.dumps({'paper':a.paper,'state':'DISPATCHING_ORIGINAL_OWNER','phase':a.phase}),flush=True)
        result=literature_native.run_native_tasks(a.root,[a.paper],resume=True,phase=a.phase,operator_message=message)
        print(json.dumps({'paper':a.paper,'results':result},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
