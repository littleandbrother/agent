#!/usr/bin/env python3
"""Seal or verify a local integration delta without creating a Git commit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT/'workbench/bf-campaign-s0-20261019'
OUT = HERE/'integrated-v1'


def load(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def describe(base, rel):
    p = base/rel
    raw = os.readlink(p).encode() if p.is_symlink() else p.read_bytes()
    return {'path':rel,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
            'kind':'symlink' if p.is_symlink() else 'file','executable':bool(p.lstat().st_mode & 0o111)}


def same(a, b):
    return all(a[k]==b[k] for k in ('sha256','bytes','kind','executable'))


def roots():
    values = set()
    for n in ('BFA-045-ar-b-reference.json','BFA-046-interface-interventions.json','BFA-047-method-reexecution.json'):
        for rel in load(HERE/n)['owned_paths']:
            if rel.startswith(('../','/')):
                continue
            values.add('battery-world/'+rel.rstrip('/'))
    return sorted(values)


def copy_entry(source, target, entry):
    src, dst = source/entry['path'], target/entry['path']
    dst.parent.mkdir(parents=True,exist_ok=True)
    assert same(describe(source,entry['path']),entry), str(src)
    if src.is_symlink():
        dst.symlink_to(os.readlink(src))
    elif sys.platform=='darwin':
        subprocess.run(['/bin/cp','-cp',str(src),str(dst)],check=True)
    else:
        shutil.copy2(src,dst)
    assert same(describe(target,entry['path']),entry), str(dst)


def capture():
    if OUT.exists():
        raise ValueError('INTEGRATION_VERSION_ALREADY_EXISTS')
    baseline = load(HERE/'baseline-v1/manifest.json')
    base = {e['path']:e for e in baseline['entries']}
    selected = set(base)
    owned = roots()
    for rel in owned:
        p = SOURCE/rel
        for f in p.rglob('*') if p.is_dir() else [p]:
            if f.exists() and (f.is_file() or f.is_symlink()) and '__pycache__' not in f.parts and f.suffix!='.pyc':
                selected.add(str(f.relative_to(SOURCE)))
    entries = []
    delta = []
    for rel in sorted(selected):
        e = describe(SOURCE,rel)
        entries.append(e)
        if rel not in base or not same(e,base[rel]):
            assert any(rel==r or rel.startswith(r+'/') for r in owned), 'OUT_OF_SCOPE_CHANGE:'+rel
            delta.append(e)
    OUT.mkdir()
    for e in delta:
        copy_entry(SOURCE,OUT/'overlay',e)
    identity = {'base':baseline['id'],'entries':entries}
    value = {'schema_version':'bf-local-integration-baseline-v1','id':'IB-'+digest(identity),
             'base':baseline['id'],'head':baseline['head'],'source':str(SOURCE),
             'owned_roots':owned,'entries':entries,'delta_paths':[e['path'] for e in delta],
             'files':len(entries),'delta_files':len(delta),'delta_bytes':sum(e['bytes'] for e in delta),
             'no_commit_or_push':True,
             'boundary':'Local content seal, not a Git commit. Original experimental inputs remain on CB baseline. '
                        'Host runtime/profile, installed SDK symlink and generated binaries are environment bindings, '
                        'not new scientific semantics. Raw runs stay in their sealed external runtime.'}
    (OUT/'manifest.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return verify(SOURCE)


def verify(source):
    value = load(OUT/'manifest.json')
    assert value['id']=='IB-'+digest({'base':value['base'],'entries':value['entries']})
    delta = set(value['delta_paths'])
    for e in value['entries']:
        assert same(describe(source,e['path']),e), e['path']
        if e['path'] in delta:
            assert same(describe(OUT/'overlay',e['path']),e), 'OVERLAY:'+e['path']
    result = {'status':'PASS','id':value['id'],'source':str(source),'files':value['files'],
              'delta_files':value['delta_files'],'delta_bytes':value['delta_bytes']}
    print(json.dumps(result))
    return result


def restore(destination, base):
    if destination.exists():
        raise ValueError('RESTORE_DESTINATION_MUST_NOT_EXIST')
    value = load(OUT/'manifest.json')
    delta = set(value['delta_paths'])
    destination.mkdir(parents=True)
    for e in value['entries']:
        copy_entry(OUT/'overlay' if e['path'] in delta else base,destination,e)
    return verify(destination)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode',choices=['capture','verify','restore'])
    p.add_argument('--source',type=Path,default=SOURCE)
    p.add_argument('--destination',type=Path)
    p.add_argument('--base',type=Path)
    a = p.parse_args()
    if a.mode=='capture':
        capture()
    elif a.mode=='verify':
        verify(a.source)
    else:
        if a.destination is None or a.base is None:
            p.error('restore requires --destination and --base')
        restore(a.destination.absolute(),a.base.absolute())


if __name__=='__main__':
    main()
