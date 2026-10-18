"""Apply transparent APFS compression to sealed CSV blobs; preserve logical bytes."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

ROOT=Path.home()/'.local/share/bf-agent-architecture-v2'
REPO=ROOT/'workbench/design-lab/repository'
OUT=ROOT/'continuous-design/storage'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'compaction.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        targets={}
        for receipt in (REPO/'task-executions').glob('*/*/completed.json'):
            value=json.loads(receipt.read_text())
            if value.get('status')!='SUCCEEDED':continue
            for name,ref in value.get('outputs',{}).items():
                if name.endswith('.csv'):targets[ref['sha256']]=REPO/'blobs'/ref['sha256']
        stamp=str(time.time_ns());before=shutil.disk_usage(ROOT).free;done=[]
        for sha,path in targets.items():
            if not path.is_file() or path.is_symlink():continue
            original=path.stat()
            if original.st_size<1024**2 or original.st_flags&getattr(stat,'UF_COMPRESSED',0x20):continue
            if digest(path)!=sha:raise ValueError('SEALED_CSV_CHANGED')
            temporary=path.with_name(path.name+'.csv-compress-'+stamp)
            subprocess.run(['/usr/bin/ditto','--noclone','--hfsCompression',str(path),str(temporary)],check=True,timeout=30)
            copied=temporary.stat()
            if digest(temporary)!=sha:raise ValueError('CSV_COMPRESSION_CHANGED_BYTES')
            current=path.stat()
            if (current.st_ino,current.st_size,current.st_mtime_ns)!=(original.st_ino,original.st_size,original.st_mtime_ns):
                temporary.unlink();continue
            if copied.st_blocks>=original.st_blocks:
                temporary.unlink();continue
            os.replace(temporary,path)
            if digest(path)!=sha:raise ValueError('CSV_READBACK_CHANGED')
            done.append({'path':str(path),'sha256':sha,'logical_bytes':original.st_size,
                'source_blocks_bytes':original.st_blocks*512,'compressed_blocks_bytes':copied.st_blocks*512})
        result={'before_free':before,'after_free':shutil.disk_usage(ROOT).free,
            'logical_bytes_preserved':True,'compressed':done}
        (OUT/('csv-compression-'+stamp+'.json')).write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'compressed':len(done),'free_bytes':result['after_free']}))


if __name__=='__main__':main()
