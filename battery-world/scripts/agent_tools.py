#!/usr/bin/env python3
"""One JSON request per line, suitable for a thin DSH/Codex tool subprocess.

Input: {"id":...,"method":"experiment","params":{...}}.
Public methods: describe, experiment, read, status, recover, submit.
No model credentials, hidden task files or arbitrary code execution are exposed.
"""
import argparse
import json
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.control.broker import Broker,RANGES

def dispatch(broker,method,params):
    if method=='describe':return {'methods':['experiment','read','status','recover','submit'],'design_domain':RANGES,'profiles':['nominal','surge','no-receiver'],'external_model_calls':0,'scope':'local computational reference; not a participant sandbox'}
    if method=='experiment':return broker.request(params)
    if method=='read':return broker.read(params['experiment_id'])
    if method=='status':return broker.status()
    if method=='recover':return broker.recover()
    if method=='submit':return broker.submit(params['experiment_id'],params['content_hash'])
    raise ValueError('unknown method')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state',type=Path,default=REPO/'.bfworld/agent-control');parser.add_argument('--budget',type=int,default=100)
    args=parser.parse_args();broker=Broker(args.state,args.budget)
    for line in sys.stdin:
        request={}
        try:
            if len(line)>65536:raise ValueError('request too large')
            request=json.loads(line);answer={'id':request.get('id'),'result':dispatch(broker,request['method'],request.get('params',{}))}
        except (ValueError,KeyError,TypeError) as exc:answer={'id':request.get('id'),'error':{'message':str(exc)}}
        print(json.dumps(answer,allow_nan=False),flush=True)
