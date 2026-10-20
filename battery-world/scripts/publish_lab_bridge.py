#!/usr/bin/env python3
"""Publish only the Lab view/bridge; preserve the original Studio runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

from bf_v2_environment import APP, SOURCE, environment

ORIGINAL=Path('/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011/battery-world')
RUNTIME=Path('/Users/depengsu/.local/share/bf-agent-runtime')
V2=Path('/Users/depengsu/.local/share/bf-agent-architecture-v2')
BASELINE=Path('/Users/depengsu/.local/share/bf-agent-baselines/bf-p01-demo-20261014')
PREFIX=Path('packages/python/bfworld/src/bfworld/agentlab')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protected_state():
    manifest=json.loads((BASELINE/'manifest.json').read_text())
    result={}
    for key,path in manifest['production']['database_paths'].items():
        db=sqlite3.connect('file:'+path+'?mode=ro',uri=True);db.execute('PRAGMA query_only=ON')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        record={}
        for table in ('model_requests','engineering_jobs','eda_cli_jobs','eda_cli_bindings',
                      'eda_cli_binding_revisions','design_snapshots','design_adoptions',
                      'research_usage_continuations','research_usage_carryforwards'):
            if table in tables:
                rows=db.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()
                record[table]={'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()}
        record['owners']=[r[0] for r in db.execute('SELECT id FROM conversations ORDER BY id')]
        record['busy']=db.execute("SELECT id,status FROM conversations WHERE status IN ('RUNNING','QUEUED','RECALLING')").fetchall()
        if 'engineering_jobs' in tables:record['busy_jobs']=db.execute("SELECT id,status FROM engineering_jobs WHERE status IN ('RUNNING','QUEUED')").fetchall()
        result[key]=record;db.close()
    native=Path(manifest['production']['native_project'])
    result['native']={str(p.relative_to(native)):sha(p) for p in sorted(native.rglob('*')) if p.is_file()}
    return result


def server_patch(text):
    a='    papers=paper_sessions or PaperSessions(workbench)\n'
    addition="""    from .lab_bridge import LabBridge, static_file as lab_static_file
    bridge_path=workbench.store.root/'lab-bridge.json'
    lab_bridge=LabBridge(bridge_path) if bridge_path.is_file() else None
"""
    if addition in text:return text
    if text.count(a)!=1:raise ValueError('ORIGINAL_SERVER_FACTORY_CHANGED')
    text=text.replace(a,a+addition)
    a='                path = urlparse(self.path).path\n'
    addition="""                if lab_bridge and (path in ('/lab','/lab/','/lab/v2','/lab/v2/') or path.startswith('/lab/v2/')):
                    file,kind=lab_static_file(UI,path)
                    self.bootstrap_cookie=file.name=='index.html'
                    return self.reply(200,file,kind)
"""
    # do_GET and do_POST each parse a path; modify only the first occurrence.
    text=text.replace(a,a+addition,1)
    a="                actor = self.principal(); owner = actor['owner']\n"
    addition="""                if lab_bridge and path.startswith('/api/design-repository'):
                    if actor['role']!='operator':raise PermissionError('OPERATOR_ONLY_LAB_VIEW')
                    return self.reply(*lab_bridge.get(self.path))
"""
    if a not in text:raise ValueError('ORIGINAL_GET_AUTH_CHANGED')
    return text.replace(a,a+addition,1)


def publish(output):
    output=Path(output).absolute();output.mkdir(parents=True,exist_ok=False)
    before=protected_state()
    if any(before[k]['busy'] or before[k].get('busy_jobs') for k in ('papers','demo')):raise ValueError('ORIGINAL_WRITER_ACTIVE')
    profile,env=environment(V2)
    from bfworld.agentlab.environment_profile import validate
    configuration_value=json.loads((V2/'runtime.json').read_text())
    profile=validate(configuration_value['development_profile'],configuration_value,env,SOURCE)
    registry=json.loads((V2/'p01-project.json').read_text())
    replacements={str(PREFIX/'server.py'):server_patch((ORIGINAL/PREFIX/'server.py').read_text()).encode(),
        str(PREFIX/'lab_bridge.py'):(APP/PREFIX/'lab_bridge.py').read_bytes(),
        'apps/agent-studio/studio.js':(APP/'apps/agent-studio/studio.js').read_bytes(),
        'apps/agent-studio/model-viewer.js':(APP/'apps/agent-studio/model-viewer.js').read_bytes()}
    for name in ('index.html','lab.js','lab.css'):
        replacements['apps/agent-studio/architecture-v2/'+name]=(APP/'apps/agent-studio/architecture-v2'/name).read_bytes()
    receipts={}
    for name,content in replacements.items():
        target=ORIGINAL/name
        if target.exists():
            backup=output/'before'/name;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
            before_hash=sha(target)
        else:before_hash=None
        staged=output/'staged'/name;staged.parent.mkdir(parents=True,exist_ok=True);staged.write_bytes(content)
        receipts[name]={'before':before_hash,'after':sha(staged)}
        if name.endswith('.py'):compile(content,name,'exec')
        if name.endswith('.js'):
            result=subprocess.run(['node','--check',str(staged)],capture_output=True,text=True)
            if result.returncode:raise ValueError(result.stderr)
    config={'schema_version':'bf-lab-read-bridge-v1','upstream':'http://127.0.0.1:8870',
        'operator_token':str(Path(profile['home'])/'state/operator.token'),
        'profile_sha256':profile['sha256'],'projects':[{'project':registry['project_id'],'owner':registry['owner']}],
        'publication':str(output),'read_only':True}
    configuration=RUNTIME/'workbench/state/lab-bridge.json'
    if configuration.exists():shutil.copy2(configuration,output/'before-bridge.json')
    (output/'before-state.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n')
    for name in replacements:
        target=ORIGINAL/name;target.parent.mkdir(parents=True,exist_ok=True)
        if receipts[name]['before'] != receipts[name]['after']:
            shutil.copyfile(output/'staged'/name,target)
    configuration.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n');configuration.chmod(0o600)
    after=protected_state()
    if before!=after:raise ValueError('PROTECTED_STATE_CHANGED')
    requires_restart=any(receipts[str(PREFIX/name)]['before'] != receipts[str(PREFIX/name)]['after']
                         for name in ('server.py','lab_bridge.py'))
    result={'schema_version':'bf-lab-publication-v1',
        'status':'PUBLISHED_PENDING_RESTART' if requires_restart else 'PUBLISHED_STATIC',
        'requires_restart':requires_restart,
        'files':receipts,'source_runtime':str(V2),'public_origin':'http://127.0.0.1:8768/lab',
        'protected_state_unchanged':True,'baseline':str(BASELINE),'model_requests_added':0,'simulations_rerun':0}
    (output/'publication.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args();result=publish(args.output)
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False))
