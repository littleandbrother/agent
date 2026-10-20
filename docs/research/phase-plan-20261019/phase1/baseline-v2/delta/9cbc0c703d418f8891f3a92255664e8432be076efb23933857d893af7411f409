#!/usr/bin/env python3
"""APFS-share identical completed pilot waves; retain every path and byte.

Only a finalized NEW campaign trial is eligible. No original runtime, database,
ledger, trace, live execution, or release archive is rewritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

RUNTIME=Path.home()/'.local/share/bf-campaign-20261019-s0'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(trial):
    registry=json.loads((RUNTIME/'registry.json').read_text())
    entry=next(e for e in registry['trials'] if e['key']==trial)
    folder=RUNTIME/'trials'/trial
    final=json.loads((folder/'final.json').read_text())
    if final['owner']!=entry['owner'] or final['status'] in ('RUNNING','STARTING','STOPPING'):
        raise ValueError('COMPLETED_TRIAL_REQUIRED')
    receipt=folder/'apfs-sharing.json'
    if receipt.exists():
        return json.loads(receipt.read_text())
    execution=RUNTIME/'workbench/design-lab/repository/task-executions'/entry['project_id']
    eligible=[folder/'cache-after',execution]
    # Seed only from our new, frozen cache; protected originals are never targets.
    groups={}
    for p in sorted((RUNTIME/'cache-start').rglob('system.raw.zlib')):
        groups[(p.stat().st_size,sha(p))]=p
    before=shutil.disk_usage(RUNTIME).free
    records=[]
    for root in eligible:
        for p in sorted(root.rglob('system.raw.zlib')):
            if p.is_symlink() or not p.resolve().is_relative_to(RUNTIME):
                raise ValueError('CLONE_SCOPE')
            stat=p.stat();digest=sha(p);key=(stat.st_size,digest)
            source=groups.get(key)
            if source is None:
                groups[key]=p
                continue
            tmp=p.with_name(p.name+'.clone-'+str(os.getpid()))
            if tmp.exists():raise ValueError('CLONE_TEMP_EXISTS')
            subprocess.run(['/bin/cp','-cp',str(source),str(tmp)],check=True)
            if sha(source)!=digest or sha(tmp)!=digest or tmp.stat().st_ino==source.stat().st_ino:
                raise ValueError('CLONE_PRE_REPLACE_READBACK')
            os.chmod(tmp,stat.st_mode & 0o7777)
            os.utime(tmp,ns=(stat.st_atime_ns,stat.st_mtime_ns))
            os.replace(tmp,p)
            if sha(p)!=digest or p.stat().st_size!=stat.st_size:
                raise ValueError('CLONE_POST_REPLACE_READBACK')
            records.append({'path':str(p.relative_to(RUNTIME)),
                            'shared_source':str(source.relative_to(RUNTIME)),
                            'bytes':stat.st_size,'sha256':digest,
                            'original_mtime_ns':stat.st_mtime_ns,
                            'distinct_inode':p.stat().st_ino!=source.stat().st_ino,
                            'preserved_mtime_ns':p.stat().st_mtime_ns==stat.st_mtime_ns})
    result={'trial':trial,'status':'PASS','files':records,'free_bytes_before':before,
            'free_bytes_after':shutil.disk_usage(RUNTIME).free,'epoch':time.time(),
            'concurrent_other_trial_may_write':True,
            'boundary':'All completed artifact paths and bytes preserved; free-space net change includes concurrent work.'}
    receipt.write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('trial');r=compact(p.parse_args().trial)
    print(json.dumps({'trial':r['trial'],'status':r['status'],'shared_files':len(r['files']),
                      'free_bytes_before':r['free_bytes_before'],'free_bytes_after':r['free_bytes_after']}))
