"""Restore registered case bytes to a local archive, without changing claims.

Only resident legacy files or explicitly supplied ZIPs are read. ZIP members
are selected by registered size and SHA256, never extracted by their paths.
The old cloud-backed store and database publication remain untouched.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from contextlib import ExitStack
from pathlib import Path

from bfworld.agentlab.store import identity


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()


def recover(state,owner,case,version,root,archives,receipt,activate=False):
    state,root,receipt=map(lambda x:Path(x).resolve(),(state,root,receipt))
    with sqlite3.connect((state/'workbench.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT payload FROM engineering_case_releases WHERE owner=? AND id=? AND version=?',
                       (owner,case,version)).fetchone()
    if row is None:raise ValueError('CASE_RELEASE_NOT_FOUND')
    manifest=json.loads(row[0]);files={(f['sha256'],f['name']):f for g in manifest['groups'] for f in g['files']}
    legacy=state/'engineering-case-files'/identity(owner)
    actions=[];sources={};zip_index={}
    with ExitStack() as stack:
        for archive in archives:
            path=Path(archive).resolve()
            if path.stat().st_flags&0x40000000:raise ValueError('RECOVERY_ARCHIVE_NOT_RESIDENT')
            z=stack.enter_context(zipfile.ZipFile(path));sources[str(path)]=digest(path)
            for member in z.infolist():
                if not member.is_dir():zip_index.setdefault((Path(member.filename).name,member.file_size),[]).append((path,z,member))
        for (sha,name),meta in files.items():
            if Path(name).name!=name or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValueError('CASE_ARCHIVE_PATH_INVALID')
            dest=root/identity(owner)/sha/name
            item={'name':name,'sha256':sha,'bytes':meta['bytes']};actions.append(item)
            if dest.exists():
                if dest.is_symlink() or digest(dest)!=sha:raise ValueError('LOCAL_CASE_ARCHIVE_CORRUPT')
                item['source']='already verified local archive';continue
            old=legacy/sha/name;data=None
            if old.is_file() and not old.is_symlink() and not old.stat().st_flags&0x40000000:
                if digest(old)!=sha:raise ValueError('LEGACY_CASE_ARCHIVE_CORRUPT')
                data=old.read_bytes();item['source']=str(old)
            if data is None:
                for path,z,member in zip_index.get((Path(meta['path']).name,meta['bytes']),[]):
                    candidate=z.read(member)
                    if hashlib.sha256(candidate).hexdigest()==sha:
                        data=candidate;item['source']={'archive':str(path),'member':member.filename};break
            if data is None:
                item['error']='No resident byte-identical source';continue
            if len(data)!=meta['bytes'] or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('RECOVERY_READBACK_MISMATCH')
            dest.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=dest.parent,delete=False) as tmp:
                tmp.write(data);temporary=Path(tmp.name)
            if digest(temporary)!=sha:raise ValueError('RECOVERY_DESTINATION_MISMATCH')
            os.replace(temporary,dest);item['readback_verified']=True
    missing=[x for x in actions if x.get('error')]
    result={'schema_version':'bf-case-storage-recovery-v1','owner':owner,'case':case,'version':version,
            'manifest_sha256':hashlib.sha256(row[0].encode()).hexdigest(),'local_root':str(root),
            'source_archives':sources,'files':len(files),'missing':len(missing),'passed':not missing,
            'actions':actions,'scope':'Original registered bytes and claims retained; no evidence re-generation.'}
    receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if activate:
        if missing:raise ValueError('INCOMPLETE_RECOVERY_NOT_ACTIVATED')
        config=state/'engineering-case-storage.json'
        value={'schema_version':'bf-engineering-case-storage-v1','root':str(root)}
        if config.exists() and json.loads(config.read_text())!=value:raise ValueError('DIFFERENT_LOCAL_ARCHIVE_ALREADY_CONFIGURED')
        config.write_text(json.dumps(value,indent=2)+'\n')
    return {k:v for k,v in result.items() if k not in ('actions','source_archives')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('state','root','receipt'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('owner','case','version'):p.add_argument('--'+name,required=True)
    p.add_argument('--archive',type=Path,action='append',default=[])
    p.add_argument('--activate',action='store_true')
    a=p.parse_args();print(json.dumps(recover(a.state,a.owner,a.case,a.version,a.root,a.archive,a.receipt,a.activate),ensure_ascii=False))
