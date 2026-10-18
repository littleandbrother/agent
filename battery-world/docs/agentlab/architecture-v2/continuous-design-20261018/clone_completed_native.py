"""Share completed native artifacts with APFS COW; preserve paths and bytes."""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

ROOT=Path('/Users/depengsu/.local/share/bf-agent-architecture-v2')
REPO=ROOT/'workbench/design-lab/repository'
OUT=ROOT/'continuous-design/storage'
lib=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True)
lib.clonefile.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int]
lib.clonefile.restype=ctypes.c_int

def clone(source,target):
    if lib.clonefile(os.fsencode(source),os.fsencode(target),0):
        raise OSError(ctypes.get_errno(),os.strerror(ctypes.get_errno()))

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def signature(path):
    s=path.stat();return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns

def compact():
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'compaction.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _compact_locked()

def _compact_locked():
    stamp=str(time.time_ns());probe=OUT/('probe-'+stamp);probe.mkdir(parents=True)
    source=probe/'source';copy=probe/'copy';source.write_bytes(b'cow-source-kept')
    clone(source,copy)
    if os.path.samefile(source,copy):raise ValueError('COW_INODE_NOT_INDEPENDENT')
    copy.write_bytes(b'changed-copy')
    if source.read_bytes()!=b'cow-source-kept':raise ValueError('COW_SOURCE_CHANGED')
    sources={}
    for receipt in (REPO/'feedback-native-cache').glob('*/completed.json'):
        value=json.loads(receipt.read_text())
        if value['status']!='SUCCEEDED':continue
        wave=receipt.parent/'system.raw.zlib';sha=value['outputs']['system.raw.zlib']
        if digest(wave)!=sha:raise ValueError('NATIVE_CACHE_CHANGED')
        sources.setdefault(wave.stat().st_size,{})[sha]=wave
    plan=[];targets=set()
    for receipt in (REPO/'task-executions').glob('*/*/completed.json'):
        value=json.loads(receipt.read_text())
        if value.get('status')!='SUCCEEDED':continue
        targets.update(receipt.parent.glob('**/system.raw.zlib'))
        for name,ref in value.get('outputs',{}).items():
            blob=REPO/'blobs'/ref['sha256']
            if not blob.is_file() or blob.stat().st_size<1024**2:continue
            if digest(blob)!=ref['sha256']:raise ValueError('SEALED_ARTIFACT_CHANGED')
            sources.setdefault(blob.stat().st_size,{}).setdefault(ref['sha256'],blob)
            targets.add(receipt.parent/name)
        for path in receipt.parent.rglob('*'):
            if path.name=='readback.raw' or '.cow-' in path.name or path.name.endswith('.bf-dedup-tmp'):continue
            try:
                if path.is_file() and path.stat().st_size>=1024**2:targets.add(path)
            except FileNotFoundError:continue
    # Content-addressed blobs are immutable copies of the same sealed waves.
    for matches in sources.values():
        targets.update(REPO/'blobs'/sha for sha in matches if (REPO/'blobs'/sha).is_file())
    for target in sorted(targets):
        if target.is_symlink():continue
        try:
            before=signature(target);candidates=sources.get(before[2],{})
            if not candidates:continue
            sha=digest(target);canonical=candidates.get(sha)
            if canonical is None or os.path.samefile(target,canonical):continue
            if signature(target)!=before:continue
        except FileNotFoundError:
            continue
        plan.append({'target':str(target),'source':str(canonical),'sha256':sha,'signature':before})
    (OUT/('clone-'+stamp+'-plan.json')).write_text(json.dumps(plan,indent=2)+'\n')
    before_free=shutil.disk_usage(ROOT).free;done=[]
    for entry in plan:
        target=Path(entry['target']);source=Path(entry['source'])
        if list(signature(target))!=list(entry['signature']):continue
        temporary=target.with_name(target.name+'.cow-'+stamp)
        clone(source,temporary)
        if digest(temporary)!=entry['sha256']:raise ValueError('CLONE_READBACK_CHANGED')
        if list(signature(target))!=list(entry['signature']):
            temporary.unlink();continue
        os.utime(temporary,ns=(target.stat().st_atime_ns,target.stat().st_mtime_ns))
        os.replace(temporary,target)
        if digest(target)!=entry['sha256'] or os.path.samefile(source,target):
            raise ValueError('COW_REPLACEMENT_CHANGED')
        done.append(entry)
    result={'probe':'PASS','before_free':before_free,'after_free':shutil.disk_usage(ROOT).free,
        'cloned':done,'content_and_paths_preserved':True,'independent_inodes':True}
    (OUT/('clone-'+stamp+'-receipt.json')).write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    result=compact()
    print(json.dumps({'cloned':len(result['cloned']),'before_free':result['before_free'],
        'after_free':result['after_free']}))

if __name__=='__main__':main()
