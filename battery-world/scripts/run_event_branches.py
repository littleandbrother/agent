#!/usr/bin/env python3
"""Four matched computational branches for a declared pair of design patches.

This measures interaction of these patches, not Agent efficacy or global
optimality. All variants rerun the full solver; no unqualified cache reuse.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time

from bfworld.agentlab.server import Workbench
from bfworld.agentlab import event_design
from bfworld.agentlab.store import identity


def patched(base, patch):
    if set(patch) != {'rationale','changes','provenance'} or not patch['rationale'] or not patch['provenance']:
        raise ValueError('BRANCH_PATCH_DECLARATION_REQUIRED')
    result=copy.deepcopy(base)
    for key,value in patch['changes'].items():
        parts=key.split('.')
        if len(parts)!=2 or parts[0] not in ('mechanics','drive','storage','power','diode','workload') or parts[1] not in result[parts[0]]:
            raise ValueError('BRANCH_DESIGN_PATH_INVALID:'+key)
        if key in ('storage.initial_v','drive.trajectory','drive.kind','workload.origin','workload.firmware_sha256','workload.measurement_sha256'):
            raise ValueError('BRANCH_FROZEN_CONDITION:'+key)
        result[parts[0]][parts[1]]=value
    result['provenance']+=patch['provenance']
    return event_design.validate(result)


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--patch-a',type=Path,required=True);p.add_argument('--patch-b',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();base=event_design.validate(json.loads(a.base.read_text()));pa=json.loads(a.patch_a.read_text());pb=json.loads(a.patch_b.read_text())
    if base['workload']['origin']=='measured':
        raise ValueError('BRANCH_MEASURED_PROFILE_REQUIRES_NEW_OPERATOR_BINDING; use immutable per-design measured runs')
    if set(pa['changes']) & set(pb['changes']):raise ValueError('BRANCH_PATCHES_OVERLAP')
    variants={'D':base,'D+a':patched(base,pa),'D+b':patched(base,pb),'D+a+b':patched(patched(base,pa),pb)}
    a.output.mkdir(parents=True,exist_ok=False)
    protocol={'schema_version':'bf-event-branches-v1','created':time.time(),'variants':{k:identity(v) for k,v in variants.items()},
              'patch_a':pa,'patch_b':pb,'base_sha256':hashlib.sha256(a.base.read_bytes()).hexdigest(),
              'fixed':['requirements','simulation','drive trajectory','initial storage'],
              'scope':'four exact design patches, full recomputation, computational only','model_calls':0,'wall_seconds':720}
    (a.output/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
    results={};deadline=time.monotonic()+720
    with tempfile.TemporaryDirectory(prefix='bf-event-branches-') as tmp:
        home=Path(tmp);(home/'paid-window-closed.json').write_text('{}');app=Workbench(home/'state')
        try:
            for name,spec in variants.items():
                out=a.output/name;out.mkdir()
                try:
                    report=event_design.run(app.engineering,{'id':name,'owner':'branch-validation','event_spec':spec,'event_spec_sha256':identity(spec)},out,min(deadline,time.monotonic()+180))
                    results[name]={'checks':report['checks'],'event':report['fine']['receiver'],'passed':report['computational_checks_passed']}
                except Exception as error:
                    results[name]={'passed':False,'execution_error':str(error)}
                (a.output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
        finally:app.stop.set();app.thread.join(3);app.lock.close()
    print(json.dumps({'output':str(a.output),'results':results,'hardware_verified':False},ensure_ascii=False))


if __name__=='__main__':main()
