"""Losslessly compact completed unqualified D5 runs; exact old XZ restore.

Result/manifest/old archive-receipt bytes are unchanged. A relocation receipt
retains both the original RAW identity and the original compressed identity.
Qualified positives are never relocated by this maintenance command.
"""
import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path


class HashSink(io.RawIOBase):
    def __init__(self):super().__init__();self.sha=hashlib.sha256();self.count=0
    def writable(self):return True
    def write(self,data):self.sha.update(data);self.count+=len(data);return len(data)


def stream_identity(path,raw=False):
    h=hashlib.sha256();count=0
    with (lzma.open(path,'rb') if raw else Path(path).open('rb')) as f:
        while b:=f.read(1<<20):h.update(b);count+=len(b)
    return h.hexdigest(),count


def encode(source,target,stride,preset):
    filters=[{'id':lzma.FILTER_DELTA,'dist':stride},{'id':lzma.FILTER_LZMA2,'preset':preset}]
    with lzma.open(source,'rb') as f,lzma.LZMAFile(target,'wb',filters=filters) as z:
        while b:=f.read(1<<20):z.write(b)


def compact(run):
    root=Path(run).resolve()
    if root.parent.name!='door-selfpower-v1' or not root.name.startswith('full-'):raise ValueError('D5_RUN_REQUIRED')
    original=(root/'result.json').read_bytes();result=json.loads(original)
    if result['qualification']['nominal_prediction_eligible'] or result['run_status']=='running':
        raise ValueError('ONLY_COMPLETED_UNQUALIFIED_RUNS')
    for p in sorted(root.glob('joint/iteration-*/system.raw.xz')):
        r=json.loads(p.with_name('system.raw.archive.json').read_text())
        stride=r['row_stride_bytes'];new=p.with_suffix('.refined.xz');receipt=p.with_suffix('.refined.json')
        if receipt.exists():continue
        if stream_identity(p)!=(r['archive_sha256'],r['archive_bytes']):raise ValueError('OLD_ARCHIVE_DRIFT')
        partial=new.with_suffix('.xz.partial');encode(p,partial,stride,6)
        if stream_identity(partial,True)!=(r['original_sha256'],r['original_bytes']):raise ValueError('RAW_READBACK_FAILED')
        sink=HashSink();encode(partial,sink,stride,1)
        if (sink.sha.hexdigest(),sink.count)!=(r['archive_sha256'],r['archive_bytes']):
            raise ValueError('ORIGINAL_XZ_NOT_EXACTLY_REPRODUCIBLE')
        nh,nb=stream_identity(partial)
        if nb>=r['archive_bytes']:partial.unlink();continue
        partial.replace(new)
        entry={'schema_version':'bf-d5-refined-relocation-v1',**r,'refined_name':new.name,
               'refined_sha256':nh,'refined_bytes':nb,'old_xz_exactly_reproducible':True,
               'raw_readback_verified':True,'old_result_sha256':hashlib.sha256(original).hexdigest(),
               'restore_argv':['python3',str(Path(__file__).resolve()),'--restore',str(receipt)]}
        receipt.write_text(json.dumps(entry,indent=2)+'\n')
        if (root/'result.json').read_bytes()!=original:raise ValueError('RUN_CHANGED_DURING_COMPACTION')
        p.unlink();print(json.dumps({'receipt':str(receipt),'saved_bytes':r['archive_bytes']-nb}),flush=True)


def restore(receipt):
    p=Path(receipt).resolve();r=json.loads(p.read_text());source=p.parent/r['refined_name'];target=p.parent/r['archive_name']
    if stream_identity(source)!=(r['refined_sha256'],r['refined_bytes']):raise ValueError('REFINED_DRIFT')
    if target.exists():raise ValueError('RESTORE_TARGET_EXISTS')
    partial=target.with_suffix('.xz.partial');encode(source,partial,r['row_stride_bytes'],1)
    if stream_identity(partial)!=(r['archive_sha256'],r['archive_bytes']):raise ValueError('RESTORE_READBACK_FAILED')
    partial.replace(target);print(json.dumps({'restored':str(target),'exact_old_xz':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();g=parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--run',type=Path);g.add_argument('--restore',type=Path);a=parser.parse_args()
    compact(a.run) if a.run else restore(a.restore)
