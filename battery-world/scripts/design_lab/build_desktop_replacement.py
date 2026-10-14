#!/usr/bin/env python3
"""Build a local connector repair; no native project or model is touched."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False);extension=a.repo/'extension';version='1.9.0-bf-desktop.4'
for name in ('package.json','package-lock.json','extension.json'):
    path=extension/name;(a.out/('before-'+name)).write_bytes(path.read_bytes())
    value=json.loads(path.read_text());value['version']=version
    if name=='package-lock.json':value['packages']['']['version']=version
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
codes={}
for stage in ('typecheck','test','build'):
    with (a.out/(stage+'.log')).open('w') as stream:
        code=subprocess.run(['npm','run',stage],cwd=extension,stdout=stream,stderr=subprocess.STDOUT).returncode
    codes[stage]=code
    if code:break
packages=list(extension.glob('**/*'+version+'*.eext'))
if all(v==0 for v in codes.values()) and len(codes)==3 and len(packages)==1:
    package=packages[0];target=Path('/Users/depengsu/Downloads')/package.name
    if target.exists() and target.read_bytes()!=package.read_bytes():raise ValueError('RELEASE_PACKAGE_CONFLICT')
    if not target.exists():shutil.copyfile(package,target)
    sealed=a.out/package.name;shutil.copyfile(package,sealed)
    artifact={'path':str(target),'immutable_copy':str(sealed),'bytes':target.stat().st_size,
              'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
else:artifact=None
result={'status':'PASS' if artifact else 'FAIL','created':time.time(),'version':version,'stages':codes,
        'package':artifact,'actions_sha256':hashlib.sha256((extension/'src/actions.ts').read_bytes()).hexdigest(),
        'tests_sha256':hashlib.sha256((extension/'src/actions.test.ts').read_bytes()).hexdigest(),
        'model_calls':0,'native_calls':0,'participant_engineering_edits':0,
        'scope':'Offline actual replacement-handler and complete connector regression; loaded desktop VM and real replacement remain unverified.'}
(a.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
raise SystemExit(0 if artifact else 1)
