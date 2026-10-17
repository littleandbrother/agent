#!/usr/bin/env python3
"""Scoped operator deployment and one new reference owner; original owners remain untouched."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.request

from bf_v2_environment import APP, environment
from v2_common import RUNTIME, action, create_pi, request, restart

ROOT = RUNTIME/'task-design'
EVIDENCE = APP/'docs/agentlab/architecture-v2/task-design-20261017/verification'


def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if path.exists() and path.read_text()!=text: raise ValueError('RECEIPT_ALREADY_EXISTS: '+str(path))
    if not path.exists():path.write_text(text)


def audit():
    from publish_lab_bridge import protected_state
    profile,_=environment(RUNTIME)
    db=sqlite3.connect((Path(profile['home'])/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
    active=[dict(r) for r in db.execute("SELECT id,status FROM conversations WHERE status IN ('RUNNING','STARTING','QUEUED')")]
    original=json.loads((RUNTIME/'p01-project.json').read_text())
    project=action(original['owner'],'repository_summary')
    protected={}
    for table,where in [('conversations','id'),('model_requests','owner')]:
        rows=[dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE {where}=? ORDER BY rowid',(original['owner'],))]
        protected[table]={'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}
    db.close()
    return {'active':active,'profile_id':profile['id'],'port':profile['port'],
        'original_runtime':protected_state(),'v2_p01':protected,
        'p01':{k:project[k] for k in ('project_id','owner','adopted','current_system','gates')},
        'capabilities':profile['capabilities']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['audit','publish','create','start','status','verify-preservation'])
    parser.add_argument('--cycle',type=int,default=1);a=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    if a.mode=='audit':
        before=audit();save(ROOT/'before.json',before);print(json.dumps({k:v for k,v in before.items() if k not in ('original_runtime','v2_p01')},ensure_ascii=False));return
    if a.mode=='publish':
        before=audit()
        if before['active']:raise ValueError('V2_CONTROLLERS_MUST_BE_IDLE')
        save(ROOT/'before.json',before)
        value=restart();save(ROOT/'publication.json',value);print(json.dumps(value));return
    if a.mode=='create':
        if (ROOT/'owner.json').exists():print((ROOT/'owner.json').read_text());return
        profile,_=environment(RUNTIME)
        key=Path(profile['paths']['PROVIDER_KEY_FILE']).read_text().strip()
        provider={}
        for label,url in [('balance','https://api.deepseek.com/user/balance'),('models','https://api.deepseek.com/models')]:
            req=urllib.request.Request(url,headers={'Authorization':'Bearer '+key})
            with urllib.request.urlopen(req,timeout=20) as response:provider[label]=json.load(response)
        save(ROOT/'provider-preflight.json',{'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**provider})
        if not provider['balance']['is_available'] or 'deepseek-flash' not in [m['id'] for m in provider['models']['data']]:raise ValueError('PROVIDER_NOT_READY')
        conversation=create_pi('常规压电节点 · 任务范式与连续设计','task-design-reference-20261017')
        owner=conversation['id'];fixture=APP/'configs/reference_cases/task-design'
        created=action(owner,'repository_task_create',operation_id='reference-task-create-v1',title='常规压电节点 · 名义参考链',
            definition=json.loads((fixture/'piezo-node-v1.json').read_text()),
            files={'design.json':(fixture/'design.json').read_text(),'firmware/main.c':(fixture/'main.c').read_text()})
        authority=action(owner,'authorize',wall_authorization_text='持续运行 不设置时间限制',model_profile='engineering-reasoning-efficient-v5')
        authority.pop('participant_token',None)
        save(ROOT/'authority.json',authority)
        identity={'owner':owner,'project_id':created['project_id'],'initial_system':created['id']}
        save(ROOT/'owner.json',identity);print(json.dumps(identity));return
    who=json.loads((ROOT/'owner.json').read_text());owner=who['owner']
    if a.mode=='start':
        goal=('在当前已确认的任务范围内，完成一轮实际候选设计和同版交付。先读取任务、源码和参考输入，选择一个值得验证的工程问题。'
              '至少修订一处设计参数或实际程序，让实际执行和独立检查支撑你的选择。验收要求、场景和模型固定。'
              '自行选择修改与实验，保留全部尝试，最终作出采用或审查保留决定，生成对应 PDF 和同版包并 close。') if a.cycle==1 else (
              '从上一轮当前候选继续第二轮小修订。自行选择一个有工程意义的改进，保留上一轮有效输入。'
              '实际提交、执行、独立验证并与父版本比较，再决定采用或保留；完成当前版本的报告、release 和 close。')
        result=action(owner,'repository_start',goal=goal)
        save(ROOT/f'cycle-{a.cycle}-dispatch.json',{'goal':goal,**result});print(json.dumps(result));return
    if a.mode=='status':
        status=action(owner,'repository_state');summary=action(owner,'repository_summary')
        print(json.dumps({'state':status,'gates':summary['gates'],'current_system':summary['current_system'],
            'releases':summary['releases']},ensure_ascii=False));return
    before=json.loads((ROOT/'before.json').read_text());after=audit()
    same=all(before[k]==after[k] for k in ('original_runtime','v2_p01','p01'))
    result={'status':'PASS' if same else 'FAIL','originals_unchanged':same,'before':before,'after':after}
    save(ROOT/'preservation.json',result);print(json.dumps({'status':result['status'],'originals_unchanged':same}))
    if not same:raise ValueError('PROTECTED_STATE_CHANGED')


if __name__=='__main__':main()
