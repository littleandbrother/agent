#!/usr/bin/env python3
"""Copy a completed executor's declared paths into S0, with source readback."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = json.loads((HERE/'baseline-v1/manifest.json').read_text())
DEST = ROOT/'workbench/bf-campaign-s0-20261019/battery-world'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integrate(role):
    assert role in ('a','b')
    feature = 'BFA-045-ar-b-reference' if role=='a' else 'BFA-046-interface-interventions'
    contract = json.loads((HERE/(feature+'.json')).read_text())
    source = ROOT/f'workbench/bf-campaign-{role}-20261019/battery-world'
    handoff = source/'docs/research/parallel-20261019'/('reference' if role=='a' else 'interfaces')/'HANDOFF.md'
    if not handoff.is_file():
        raise ValueError('EXECUTOR_HANDOFF_REQUIRED')
    allowed = contract['owned_paths']
    def owns(name):
        return any(name==p or (p.endswith('/') and name.startswith(p)) for p in allowed)
    baseline_changes = []
    for e in BASE['entries']:
        name=e['path']
        if not name.startswith('battery-world/'):
            continue
        relative=name.removeprefix('battery-world/')
        path=source/relative
        if e['kind']=='file' and sha(path)!=e['sha256']:
            if relative!='PROJECT.yaml' and not owns(relative):
                raise ValueError('OUT_OF_SCOPE_BASELINE_CHANGE:'+relative)
            baseline_changes.append(relative)
    files = set()
    for name in allowed:
        path = source/name
        if path.is_dir():
            files.update(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        elif path.is_file():
            files.add(path)
    copied=[]
    for src in sorted(files):
        name=str(src.relative_to(source))
        if not owns(name):
            raise ValueError('COPY_OUT_OF_SCOPE')
        dst=DEST/name
        expected=sha(src)
        if dst.exists() and sha(dst)!=expected:
            raise ValueError('INTEGRATION_CONFLICT:'+name)
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)
        if sha(dst)!=expected or sha(src)!=expected:
            raise ValueError('COPY_READBACK_CHANGED:'+name)
        copied.append({'path':name,'sha256':expected,'bytes':dst.stat().st_size})
    value={'baseline':BASE['id'],'owner':contract['owner'],'source':str(source),
           'destination':str(DEST),'handoff_sha256':sha(handoff),
           'baseline_changes':baseline_changes,'files':copied,
           'status':'COPIED_AND_READBACK_VERIFIED','shared_state_imported':False}
    out=HERE/f'integration-{role}.json'
    if out.exists():
        raise ValueError('INTEGRATION_RECEIPT_EXISTS')
    out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return {'owner':contract['owner'],'files':len(copied),'bytes':sum(x['bytes'] for x in copied)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('role',choices=['a','b'])
    print(json.dumps(integrate(p.parse_args().role)))
