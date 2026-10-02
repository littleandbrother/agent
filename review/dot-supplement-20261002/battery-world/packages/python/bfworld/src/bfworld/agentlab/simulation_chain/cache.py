"""Content-addressed checkpoints. Incomplete or altered artifacts never count as hits."""
import os
import json
import time
import secrets
from pathlib import Path
from .contracts import digest,file_hash,write_json,ChainError

class Cache:
    def __init__(self,root,event=lambda *args:None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.event=event

    def stage(self,name,inputs,producer):
        key=digest({'stage':name,'inputs':inputs});dest=self.root/name/key
        manifest=dest/'checkpoint.json'
        if manifest.is_file():
            m=json.loads(manifest.read_text())
            if m.get('key')!=key or not m.get('files'):
                raise ChainError('tool_fail','Invalid checkpoint '+name)
            for f in m['files']:
                path=dest/f['path']
                if path.is_symlink() or not path.is_file() or file_hash(path)!=f['sha256']:
                    raise ChainError('tool_fail','Checkpoint hash mismatch: '+name+'/'+f['path'])
            self.event('stage_cached',{'stage':name,'key':key})
            return dest,m['value'],key,True
        dest.parent.mkdir(parents=True,exist_ok=True)
        temp=dest.parent/(key+'.partial-'+secrets.token_hex(4));temp.mkdir()
        self.event('stage_started',{'stage':name,'key':key})
        started=time.time()
        try:
            value=producer(temp)
            files=[{'path':str(p.relative_to(temp)),'bytes':p.stat().st_size,'sha256':file_hash(p)}
                   for p in sorted(temp.rglob('*')) if p.is_file() and not p.is_symlink()]
            m={'schema_version':'simulation-checkpoint-v1','key':key,'stage':name,
               'inputs':inputs,'value':value,'files':files,'elapsed_s':time.time()-started}
            write_json(temp/'checkpoint.json',m)
            # Match a resumed checkpoint exactly, including JSON scalar/container
            # types (native producers can return NumPy float scalars or tuples).
            value=json.loads((temp/'checkpoint.json').read_text())['value']
            # Callers hold a cache lock; rename is the commit point.
            os.rename(temp,dest)
            self.event('stage_completed',{'stage':name,'key':key,'files':len(files)})
            return dest,value,key,False
        except Exception as exc:
            write_json(temp/'failure.json',{'error':str(exc),'elapsed_s':time.time()-started})
            self.event('stage_failed',{'stage':name,'key':key,'error':str(exc)})
            raise
