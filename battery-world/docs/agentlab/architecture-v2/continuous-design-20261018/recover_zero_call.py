"""Recover one zero-call file preflight; never resample an Agent output."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

APP=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(APP/'scripts'))
from run_organization_pilot import ROOT, metrics, preflight_failure, read_record, seal
from v2_common import RUNTIME, action


def main():
    parser=argparse.ArgumentParser();parser.add_argument('key');args=parser.parse_args()
    folder=ROOT/'trials'/args.key
    if (folder/'recovery-final.json').exists():raise ValueError('RECOVERY_ALREADY_FINISHED')
    old=read_record(folder/'final.json');entry=old['entry'];m=old['metrics']
    if not preflight_failure(old):raise ValueError('ONLY_ZERO_CALL_FILE_PREFLIGHT_RECOVERY_ALLOWED')
    dispatch_path=folder/'recovery-dispatch.json'
    if dispatch_path.exists():dispatch=read_record(dispatch_path)
    else:
        frozen=read_record(Path(__file__).parent/'results/frozen-harness.json')
        package=APP.parent/'pi-bf-aiot/packages/bf-agent'
        lab=APP/'packages/python/bfworld/src/bfworld/agentlab'
        for group,root in (('files',package),('python_bindings',lab/'design_lab'),
                           ('context_bindings',lab),('engineering_bindings',lab)):
            for name,digest in frozen[group].items():
                if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
                    raise ValueError('FROZEN_HARNESS_CHANGED:'+name)
        protocol=APP/'configs/studies/continuous-design-20261018/protocol.json'
        if hashlib.sha256(protocol.read_bytes()).hexdigest()!=entry['policy']['protocol_sha256']:
            raise ValueError('FROZEN_PROTOCOL_CHANGED')
        state=action(entry['owner'],'repository_state')
        if state['model_calls'] or state['current_system']!=entry['initial_system']:
            raise ValueError('ORIGINAL_TRIAL_HAS_CHANGED')
        original=read_record(folder/'dispatch.json')
        started=time.time()
        result=action(entry['owner'],'repository_start',goal=original['goal'])
        dispatch={'started':started,'original_final_sha256':hashlib.sha256((folder/'final.json').read_bytes()).hexdigest(),
            'same_owner':entry['owner'],'same_goal':original['goal'],**result}
        seal(dispatch_path,dispatch)
    while True:
        state=action(entry['owner'],'repository_state')
        if state['unknown_requests']:raise ValueError('PROVIDER_UNKNOWN_STOP')
        if state['status'] not in ('RUNNING','STARTING','QUEUED'):break
        time.sleep(5)
    m,view=metrics(entry)
    m['wall_seconds']=time.time()-read_record(folder/'dispatch.json')['started']
    value={'entry':entry,'state':state,'metrics':m,'view':view,'finished':time.time(),
        'preflight_recovery':{'original_final_sha256':dispatch['original_final_sha256'],
            'same_owner_and_goal':True,'model_calls_before_recovery':0,'recovery_started':dispatch['started']}}
    seal(folder/'recovery-final.json',value)
    print(json.dumps(m,ensure_ascii=False))


if __name__=='__main__':main()
