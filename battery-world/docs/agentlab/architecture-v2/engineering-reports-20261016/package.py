#!/usr/bin/env python3
"""Package the reviewed template proof, sources and reproduction scripts."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
DESTINATION = Path.home()/'Downloads/BF_P01_Report_Templates_20261016'


def main():
    if DESTINATION.exists():
        raise ValueError('DELIVERY_DIRECTORY_ALREADY_EXISTS')
    allowed_files = ['collect.py','render.py','render_native_previews.mjs','verify.py','package.py',
                     'templates.json','report-facts.json','report-data.json','asset-inventory.json',
                     '来源索引.csv','P01_八页内容映射与补齐清单.md','REPORT.md','REPRODUCE.md']
    sources = [ROOT/name for name in allowed_files]
    for directory in ['input','output','skill-draft','verification']:
        sources.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and
                       p.name != 'repository-view.json' and '__pycache__' not in p.parts)
    receipts = []
    for source in sorted(sources):
        relative = source.relative_to(ROOT)
        raw = source.read_bytes()
        if source.suffix in ('.md','.json','.py','.mjs','.yaml','.csv','.txt'):
            if re.search(rb'(?:sk-[A-Za-z0-9]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',raw):
                raise ValueError('SECRET_PATTERN_FOUND:'+str(relative))
        target = DESTINATION/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        digest = hashlib.sha256(raw).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('COPY_HASH_MISMATCH:'+str(relative))
        receipts.append({'path':str(relative),'sha256':digest,'bytes':len(raw)})
    manifest={'files':receipts,'file_count':len(receipts),'bytes':sum(v['bytes'] for v in receipts)}
    (DESTINATION/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive=DESTINATION.with_suffix('.zip')
    if archive.exists():raise ValueError('DELIVERY_ARCHIVE_ALREADY_EXISTS')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(DESTINATION.rglob('*')):
            if source.is_file():bundle.write(source,str(Path(DESTINATION.name)/source.relative_to(DESTINATION)))
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip():raise ValueError('ZIP_CRC_FAILURE')
        for record in receipts:
            raw=bundle.read(str(Path(DESTINATION.name)/record['path']))
            if hashlib.sha256(raw).hexdigest()!=record['sha256']:
                raise ValueError('ZIP_HASH_MISMATCH:'+record['path'])
    result={'status':'PASS','directory':str(DESTINATION),'zip':str(archive),
            'files':len(receipts)+1,'archive_bytes':archive.stat().st_size,
            'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (ROOT/'verification/delivery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
