"""Reversible storage of this turn's rejected D5 gzip waveforms.

The original gzip bytes must be reproducible exactly before relocation. Old
result, manifest and archive-receipt bytes are never edited. Qualified runs
are excluded; new native runs already use standard lossless XZ directly.
"""
import argparse
import gzip
import hashlib
import io
import json
import lzma
import re
from pathlib import Path


class DigestWriter(io.RawIOBase):
    def __init__(self):super().__init__();self.sha=hashlib.sha256();self.count=0
    def writable(self):return True
    def write(self,data):self.sha.update(data);self.count+=len(data);return len(data)


def file_identity(p):
    h=hashlib.sha256();count=0
    with Path(p).open('rb') as f:
        while chunk:=f.read(1<<20):h.update(chunk);count+=len(chunk)
    return h.hexdigest(),count


def gzip_to_file(source,destination):
    with lzma.open(source,'rb') as f:
        with gzip.GzipFile(filename='',fileobj=destination,mode='wb',compresslevel=3,mtime=0) as z:
            while chunk:=f.read(1<<20):z.write(chunk)


def repack(run):
    root=Path(run).resolve()
    if root.parent.name!='door-selfpower-v1' or not root.name.startswith(('full-','probe-sece-','probe-psshi-')):
        raise ValueError('ONLY_THIS_TURN_D5_RUNS')
    result=(root/'result.json').read_bytes();value=json.loads(result)
    if root.name.startswith('full-'):
        if value['run_status']=='running' or value['qualification']['nominal_status']=='satisfied':
            raise ValueError('REPACK_ONLY_REJECTED_FINISHED_RUNS')
    elif (value.get('status')!='completed' or value.get('model_calls')!=0
          or value.get('deck_sha256')!=file_identity(root/'system.cir')[0]
          or 'qualification' in value):
        raise ValueError('REPACK_ONLY_COMPLETED_CHARGING_PROBES')
    outputs=[]
    for old in sorted(root.rglob('system.raw.gz')):
        receipt=old.with_suffix('.archive.json')
        if not receipt.exists():continue
        identity=json.loads(receipt.read_text())
        if file_identity(old)!=(identity['archive_sha256'],identity['archive_bytes']):
            raise ValueError('OLD_GZIP_IDENTITY_CHANGED')
        new=old.with_suffix('.xz');record=old.with_suffix('.repacked.json')
        if new.exists() or record.exists():raise ValueError('REPACK_OUTPUT_EXISTS')
        with gzip.open(old,'rb') as f:header=f.read(32768).decode('utf-16-le',errors='replace')
        n=int(re.search(r'No. Variables:\s*(\d+)',header)[1]);stride=8+4*(n-1)
        if not 1<=stride<=256:raise ValueError('UNSUPPORTED_NATIVE_ROW_SIZE')
        temp=new.with_suffix('.xz.partial')
        filters=[{'id':lzma.FILTER_DELTA,'dist':stride},{'id':lzma.FILTER_LZMA2,'preset':1}]
        with gzip.open(old,'rb') as f,lzma.open(temp,'wb',filters=filters) as z:
            while chunk:=f.read(1<<20):z.write(chunk)
        raw_hash=hashlib.sha256();raw_count=0
        with lzma.open(temp,'rb') as f:
            while chunk:=f.read(1<<20):raw_hash.update(chunk);raw_count+=len(chunk)
        if (raw_hash.hexdigest(),raw_count)!=(identity['original_sha256'],identity['original_bytes']):
            raise ValueError('RAW_REPACK_READBACK_FAILED')
        digest=DigestWriter();gzip_to_file(temp,digest)
        if (digest.sha.hexdigest(),digest.count)!=(identity['archive_sha256'],identity['archive_bytes']):
            raise ValueError('ORIGINAL_GZIP_BYTES_NOT_REPRODUCIBLE')
        temp.replace(new);new_hash,new_bytes=file_identity(new)
        entry={'schema_version':'bf-d5-native-relocation-v1',**identity,
               'repacked_name':new.name,'repacked_sha256':new_hash,'repacked_bytes':new_bytes,
               'raw_readback_verified':True,'original_gzip_exactly_reproducible':True,
               'old_result_sha256':hashlib.sha256(result).hexdigest(),
               'restore_argv':['python3',str(Path(__file__).resolve()),'--restore',str(record)]}
        record.write_text(json.dumps(entry,indent=2)+'\n')
        if (root/'result.json').read_bytes()!=result:raise ValueError('RESULT_CHANGED_DURING_REPACK')
        old.unlink();outputs.append({'path':str(record),'saved_bytes':identity['archive_bytes']-new_bytes})
        print(json.dumps(outputs[-1]),flush=True)
    return outputs


def restore(record):
    p=Path(record).resolve();r=json.loads(p.read_text());source=p.parent/r['repacked_name']
    if file_identity(source)!=(r['repacked_sha256'],r['repacked_bytes']):raise ValueError('REPACK_IDENTITY_CHANGED')
    target=p.parent/r['archive_name']
    if target.exists():raise ValueError('RESTORE_OUTPUT_EXISTS')
    temp=target.with_suffix('.gz.partial')
    with temp.open('wb') as out:gzip_to_file(source,out)
    if file_identity(temp)!=(r['archive_sha256'],r['archive_bytes']):raise ValueError('GZIP_RESTORE_IDENTITY_FAILED')
    temp.replace(target);return {'restored':str(target),'exact_gzip_readback':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--run',type=Path);group.add_argument('--restore',type=Path);a=p.parse_args()
    print(json.dumps(repack(a.run) if a.run else restore(a.restore),indent=2))
