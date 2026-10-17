#!/usr/bin/env python3
"""Package report evidence with an explicit allowlist and a content manifest."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

APP=Path(__file__).resolve().parents[2]
DOC=APP/'docs/agentlab/architecture-v2/task-evaluation-20261017'
ROOT=Path('/Users/depengsu/.local/share/bf-agent-architecture-v2/task-evaluation')
OUTPUT=Path('/Users/depengsu/Downloads/BF_Task_Study_20261017')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def copy(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,dest)


def main():
    OUTPUT.mkdir(exist_ok=True)
    for source in DOC.rglob('*'):
        if source.is_file() and source.name not in ['.DS_Store'] and '__pycache__' not in source.parts:
            copy(source,OUTPUT/source.relative_to(DOC))
    for source in Path(__file__).parent.glob('*.py'):copy(source,OUTPUT/'scripts'/source.name)
    source_root=APP/'packages/python/bfworld/src/bfworld/agentlab/design_lab'
    for name in ['repository_task_intake.py','repository.py','repository_profiles.py','repository_task_standards.py',
                 'repository_task_actions.py','repository_task_execution.py','repository_task_checks.py','repository_task_state.py',
                 'repository_reference_node.py','repository_reference_qualification.py']:
        copy(source_root/name,OUTPUT/'source/design_lab'/name)
    copy(APP.parent/'pi-bf-aiot/packages/bf-agent/src/extensions/bf-repository.ts',OUTPUT/'source/pi/bf-repository.ts')
    copy(APP/'docs/agentlab/architecture-v2/task-design-20261017/STANDARD-DEFINITIONS.md',OUTPUT/'source/STANDARD-DEFINITIONS.md')
    copy(APP/'project/features/BFA-039-task-intake-and-contract-experiments/feature.yaml',OUTPUT/'source/feature.yaml')
    # These folders contain only local numerical inputs and results, not provider messages.
    for folder in ['mechanisms/runs','mechanisms/replay','mechanisms-controls']:
        for source in (ROOT/folder).rglob('*'):
            if source.is_file() and source.suffix in ['.json','.raw','.csv','.cir','.log','.txt']:
                copy(source,OUTPUT/'raw'/folder/source.relative_to(ROOT/folder))
    for name in ['system.raw','events.json']:
        copy(ROOT/'default/vendor-probe'/name,OUTPUT/'raw/default-vendor'/name)
    p08=json.loads((DOC/'data/p08/readback.json').read_text())
    source=Path(p08['raw_path'])
    if sha(source)!=p08['raw_sha256']:raise ValueError('P08_SOURCE_DRIFT')
    copy(source,OUTPUT/'raw/p08/project-trace.raw')
    for name in ['tests-task-final.log','publication.json']:
        copy(ROOT/name,OUTPUT/'verification'/name)
    for source in (ROOT/'final-verification').glob('*'):
        if source.is_file():copy(source,OUTPUT/'verification/lab'/source.name)
    # No credentials, private reasoning, or proprietary model installation files.
    forbidden=[]
    for source in OUTPUT.rglob('*'):
        if not source.is_file():continue
        if source.name=='provider.token' or source.suffix=='.sub':forbidden.append(str(source.relative_to(OUTPUT)))
        if source.suffix in ['.json','.txt','.md','.yaml','.log','.py','.ts']:
            text=source.read_text(errors='replace')
            if re.search(r'\bsk-[A-Za-z0-9]{24,}\b',text):forbidden.append(str(source.relative_to(OUTPUT)))
            if '"reasoning_content"' in text and source.suffix=='.json':forbidden.append(str(source.relative_to(OUTPUT)))
    if forbidden:raise ValueError('PACKAGE_EXCLUSIONS_FAILED:'+','.join(forbidden))
    rows=[{'path':str(p.relative_to(OUTPUT)),'bytes':p.stat().st_size,'sha256':sha(p)}
          for p in sorted(OUTPUT.rglob('*')) if p.is_file() and p.name!='MANIFEST.json']
    manifest={'version':'bf-task-study-package-v1','git_base':'9bcdbad0c275e2af019f3c9645bf5c40ebf38411',
              'source_state':'uncommitted V2 working changes; source hashes included',
              'files':rows,'excluded':['provider credentials','private reasoning text','vendor model installation']}
    (OUTPUT/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    subprocess.run([sys.executable,str(OUTPUT/'scripts/verify_results.py'),str(OUTPUT)],check=True)
    archive=OUTPUT.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for source in sorted(OUTPUT.rglob('*')):
            if source.is_file():z.write(source,Path(OUTPUT.name)/source.relative_to(OUTPUT))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP_CRC_FAILED')
        for r in rows:
            if hashlib.sha256(z.read(OUTPUT.name+'/'+r['path'])).hexdigest()!=r['sha256']:raise ValueError('ZIP_CONTENT_DRIFT')
    receipt={'status':'PASS','archive':str(archive),'sha256':sha(archive),'bytes':archive.stat().st_size,
             'files':len(rows),'exclusion_check':'PASS','manifest_check':'PASS','zip_readback':'PASS'}
    (ROOT/'package-result.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    archive.with_suffix('.zip.sha256').write_text(receipt['sha256']+'  '+archive.name+'\n')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
