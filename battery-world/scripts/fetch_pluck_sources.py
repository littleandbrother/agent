#!/usr/bin/env python3
"""Fetch the authors' public copies and verify pinned content before use.

Existing PDFs are checked, never overwritten. Publisher HTML is not a PDF.
No institutional login, credentials, or access-control bypass is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
URLS={
 'vipsn':'https://metal.shanghaitech.edu.cn/publication/J40.pdf',
 'unified':'https://sms-lab.github.io/publications/J99_Tang%20et%20al_2025_10.10881361-665xadd8d4.pdf',
 'cross-domain':'https://sms-lab.github.io/publications/J125_Tang%20et%20al_2026_10.11151.4071279.pdf',
 'ltc3588':'https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf',
}

def verify(data, sha256):
    if not data.startswith(b'%PDF-'):raise ValueError('SOURCE_IS_NOT_PDF')
    if hashlib.sha256(data).hexdigest()!=sha256:raise ValueError('SOURCE_HASH_MISMATCH')

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);a=p.parse_args()
    case=json.loads((ROOT/'configs/reference_cases/pluck-v1/case.json').read_text())
    output=a.home/'sources';output.mkdir(parents=True,exist_ok=True);receipt=[]
    auxiliary={'id':'ltc3588','file':'ltc3588-1.pdf','sha256':'f1e52b155e35b2b5fe70ee05f5cdf130a577488df648703054bf2f57395c7c1d'}
    for source in case['sources']+[auxiliary]:
        path=output/source['file'];cached=path.exists();url=URLS[source['id']]
        if cached:data=path.read_bytes()
        else:
            request=urllib.request.Request(url,headers={'User-Agent':'BF-reference-case/1.0'})
            with urllib.request.urlopen(request,timeout=45) as response:data=response.read(30*1024*1024+1)
            if len(data)>30*1024*1024:raise ValueError('SOURCE_SIZE_LIMIT')
        verify(data,source['sha256'])
        if not cached:
            with path.open('xb') as stream:stream.write(data)
        receipt.append({'id':source['id'],'url':url,'path':str(path),'sha256':source['sha256'],'bytes':len(data),'verified':True,'already_cached':cached})
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
