#!/usr/bin/env python3
import json
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.control.broker import Broker
from bfworld.kernel.canonical import write_canonical_json,file_hash

def main():
    broker=Broker(REPO/'.bfworld/reference-control',budget=100)
    version=file_hash(REPO/'packages/python/bfworld/src/bfworld/coupled/engine.py').split(':')[1][:12]
    experiment=broker.request({'idempotency_key':'reference-pass-'+version,'design':{},'prediction':{'actor':'developer reference driver','expected':'physical pass only; not an Agent trial'}})
    submission=broker.submit(experiment['experiment_id'],experiment['run']['content_hash'])
    report={'status':'pass','interface':'JSONL and loopback HTTP','reference_submission':submission,
            'cost':broker.status(),'formal_agent_pilot':False,'agent_identity':None,
            'security_boundary':'API rejects hidden mutation; local filesystem is not a participant sandbox',
            'recovery_tests':'tests/control/test_broker.py real subprocess death after reservation and artifact seal'}
    write_canonical_json(REPO/'docs/control/validation.json',report)
    print(json.dumps({'status':'pass','reference_submission':submission['status'],'external_model_calls':0}))
if __name__=='__main__':main()
