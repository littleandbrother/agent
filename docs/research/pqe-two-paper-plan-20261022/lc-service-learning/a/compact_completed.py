"""Compress only completed resident A artifacts; verify complete byte identity."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,plistlib,shutil,stat,subprocess,time
A=Path(__file__).resolve().parent
ROOT=A.parents[4]
BIN=Path('/Users/depengsu/.local/share/bf-agent-runtime/maintenance-tools/applesauce-v0.5.30/applesauce')
EXPECTED='930a613509fa1db336f3810a59c7c1747d2241630ebac8629bef651896ff0a8b'
DATALESS=getattr(stat,'SF_DATALESS',0x40000000)
COMPRESSED=getattr(stat,'UF_COMPRESSED',0x20)

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while chunk:=f.read(1024*1024):h.update(chunk)
 return h.hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def state(p):
 s=p.lstat();return {'logical_bytes':s.st_size,'allocated_bytes':s.st_blocks*512,'flags':s.st_flags,
   'inode':s.st_ino,'device':s.st_dev,'nlink':s.st_nlink,'mtime_ns':s.st_mtime_ns,'mode':s.st_mode}
def usage(p):
 files=[q for q in p.rglob('*') if q.is_file()]
 return {'logical_bytes':sum(q.stat().st_size for q in files),'allocated_bytes':sum(q.stat().st_blocks*512 for q in files),'files':len(files)}
def idle(p):
 r=subprocess.run(['/usr/sbin/lsof','-nP','-F','p','--',str(p)],capture_output=True,text=True,timeout=15)
 return r.returncode==1 and not r.stdout.strip() and not r.stderr.strip(),{'returncode':r.returncode,'stdout':r.stdout[:1000],'stderr':r.stderr[:1000]}
def save(p,value):
 with p.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
assert sha(BIN)==EXPECTED,'UNTRUSTED_BINARY'
device=subprocess.run(['/bin/df','-P',str(A)],check=True,capture_output=True,text=True).stdout.splitlines()[-1].split()[0]
info=plistlib.loads(subprocess.run(['/usr/sbin/diskutil','info','-plist',device],check=True,capture_output=True).stdout)
assert info.get('FilesystemType','').lower()=='apfs',info.get('FilesystemType')
ledger=[json.loads(s) for s in (A/'DISPATCH.jsonl').read_text().splitlines()]
completed={Path(r['output']).resolve() for r in ledger if r['state']=='FINISHED'}
reserved={r['id'] for r in ledger if r['state']=='RESERVED'}
assert reserved=={r['id'] for r in ledger if r['state']=='FINISHED'},'A_BATCH_INCOMPLETE'
refs={r['path']:r for r in json.loads((A/'A-FILE-INVENTORY.json').read_text())['files']}
free_before=shutil.disk_usage(A).free
assert free_before>=11_000_000_000
before_tree=usage(A);entries=[]
for p in sorted(A.rglob('*.json')):
 if p.name not in ('raw.json','public-result.json'):continue
 pre=state(p)
 if pre['logical_bytes']<=1_000_000:continue
 entry={'path':str(p),'before':pre,'started_at_utc':now()}
 reason=None
 if p.parent.resolve() not in completed:reason='PARENT_NOT_COMPLETED_DISPATCH'
 elif not p.is_relative_to(A) or p.is_symlink() or p.resolve()!=p:reason='PATH_OR_SYMLINK'
 elif not stat.S_ISREG(pre['mode']) or pre['nlink']!=1:reason='NOT_SINGLE_LINK_REGULAR'
 elif pre['flags']&DATALESS or pre['allocated_bytes']==0:reason='DATALESS_OR_NONRESIDENT'
 elif pre['flags']&COMPRESSED:reason='ALREADY_COMPRESSED'
 elif any('fileprovider' in x.lower() or 'ubiquity' in x.lower() for x in subprocess.run(['/usr/bin/xattr',str(p)],check=True,capture_output=True,text=True).stdout.splitlines()):reason='CLOUD_PROVIDER_XATTR'
 if reason:entry.update(status='SKIPPED',reason=reason);entries.append(entry);continue
 ok,opened=idle(p);entry['lsof_before']=opened
 if not ok:entry.update(status='SKIPPED',reason='OPEN_HANDLE_OR_LSOF_UNCERTAIN');entries.append(entry);continue
 digest=sha(p);entry['sha256_before']=digest
 assert digest==refs[str(p)]['sha256'] and pre['logical_bytes']==refs[str(p)]['bytes'],'SEALED_FILE_MISMATCH'
 assert state(p)==pre,'CHANGED_DURING_PRE_READBACK'
 ok,opened=idle(p);entry['lsof_immediately_before']=opened
 if not ok:entry.update(status='SKIPPED',reason='OPENED_DURING_PRE_READBACK');entries.append(entry);continue
 begin=time.monotonic()
 proc=subprocess.run([str(BIN),'compress','--verify','--quiet',str(p)],capture_output=True,text=True,timeout=60)
 after=state(p);post_digest=sha(p)
 entry.update(after=after,sha256_after=post_digest,full_content_identity=digest==post_digest,
    exit_code=proc.returncode,stdout=proc.stdout[-1000:],stderr=proc.stderr[-1000:],wall_s=time.monotonic()-begin,
    completed_at_utc=now(),allocated_reduction_bytes=pre['allocated_bytes']-after['allocated_bytes'])
 assert proc.returncode==0,entry
 assert digest==post_digest and pre['logical_bytes']==after['logical_bytes'],'CONTENT_CHANGED'
 assert after['nlink']==1 and after['flags']&COMPRESSED,'NOT_COMPRESSED_SINGLE_LINK'
 entry['status']='COMPRESSED_VERIFIED';entries.append(entry)
 # Flush a compact journal so partial completion is not lost on interruption.
 with (A/'COMPACTION-JOURNAL.jsonl').open('a') as f:
  f.write(json.dumps(entry,ensure_ascii=False,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
 print(json.dumps({'file':str(p.relative_to(A)),'saved_allocated_bytes':entry['allocated_reduction_bytes'],'sha256_unchanged':True}),flush=True)
after_tree=usage(A);free_after=shutil.disk_usage(A).free
save(A/'COMPACTION-RECEIPT.json',{'package':'BF-PQE-LC-SERVICE-LEARNING-20261024-001','at_utc':now(),
 'scope':'Only A-owned completed >1MB resident regular single-link raw/public JSON; original scientific input/source and prior-package artifacts untouched.',
 'binary':{'path':str(BIN),'sha256':EXPECTED},'command':['compress','--verify','--quiet'],
 'filesystem':info.get('FilesystemType'),'entries':entries,
 'compressed_verified':sum(e['status']=='COMPRESSED_VERIFIED' for e in entries),
 'skipped':sum(e['status']=='SKIPPED' for e in entries),
 'allocated_reduction_selected_files_bytes':sum(e.get('allocated_reduction_bytes',0) for e in entries),
 'tree_before':before_tree,'tree_after_before_receipt':after_tree,
 'free_before_bytes':free_before,'free_after_bytes':free_after,
 'free_space_interpretation':'Concurrent filesystem free-space samples only; do not attribute total-volume delta to this operation. Selected-file st_blocks reductions are reported separately and are not a physical reclaim guarantee.',
 'full_content_readback':'SHA256 of every selected file before and after; original sealed SHA matched; applesauce internal verify also enabled.',
 'new_backups_environments_worktrees':0,'new_scientific_inputs':0,'model_calls':0,
 'storage_maintenance_operations':sum(e['status']=='COMPRESSED_VERIFIED' for e in entries),
 'new_scientific_cheap_checks':0})
print(json.dumps({'receipt':str(A/'COMPACTION-RECEIPT.json'),'sha256':sha(A/'COMPACTION-RECEIPT.json'),
 'selected_allocated_reduction_bytes':sum(e.get('allocated_reduction_bytes',0) for e in entries),
 'tree_after':usage(A),'free_after':free_after}))
