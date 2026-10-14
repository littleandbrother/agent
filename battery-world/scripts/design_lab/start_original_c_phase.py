#!/usr/bin/env python3
"""Bind a qualified new phase to the original Pi C source and conversation.

Read-only DB inventory; mutations go through the one live original Workbench.
No participant source is authored here, and no inference occurs without --apply.
"""
import argparse
import fcntl
import hashlib
import http.cookiejar
import json
from pathlib import Path
import sqlite3
import sys
import time
import urllib.request

APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab import coupled_c
from bfworld.agentlab.design_lab.contracts import sealed,sha
from bfworld.agentlab.store import identity
from bfworld.agentlab.runtime_config import RUNTIME_ROOT

parser=argparse.ArgumentParser();parser.add_argument('--release',type=Path,required=True)
parser.add_argument('--apply',action='store_true');args=parser.parse_args()
release=args.release.resolve();q=json.loads((release/'qualification.json').read_text())
env=json.loads((release/'environment.json').read_text());contract=coupled_c.contract(env)
if not q['passed'] or q['environment_id']!=env['environment_id'] or q['validation_id']!=contract['validation_id']:
    raise ValueError('CURRENT_NATIVE_QUALIFIED_RELEASE_REQUIRED')
coupled_c.verify_environment(env)
owner='pi-chat-3faf3eb798e76401'
state=RUNTIME_ROOT/'workbench/state';dbpath=state/'workbench.sqlite'
with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    old=dict(db.execute('SELECT * FROM design_tasks WHERE owner=?',(owner,)).fetchone())
    design=json.loads(db.execute('SELECT value FROM design_snapshots WHERE owner=? AND design_id=?',
                                (owner,old['current_design'])).fetchone()['value'])
    fee={r['id']:identity(dict(r)) for r in db.execute('SELECT * FROM model_requests')}
    profile=json.loads(db.execute('SELECT value FROM settings WHERE key=?',('model_profile:'+owner,)).fetchone()['value'])
    if db.execute("SELECT 1 FROM conversations WHERE status IN ('STARTING','RUNNING')").fetchone():
        raise ValueError('PHASE_RELEASE_REQUIRES_DRAINED_MAIN_CONTROLLER')
out=APP/'docs/agentlab/executable-lab-20261012'/('original-C-phase-'+str(time.time_ns()))
out.mkdir(parents=True)
goal=('继续原 C 案例。公共原生执行器已通过新版本无 Agent 资格；旧阶段、你此前编写的源码、'
      '费用与交付已保留。先读取当前合同/environment、已有设计与操作，审查自己的实现及接口，'
      '由你决定保留或修改设计，并选择能区分问题的实际检查。输入未变且通过的物理结果必须复用；'
      '实际电路或电流/时序变化必须满足本环境的联合执行要求，不能用旧波形证明新负载。'
      '按实际独立结果选择和采用设计，再提交同版工程与回执。保持任务和物理参考；'
      '不修改检查器、技能、费用或原授权历史。未支持目标外设、物理 RF 和硬件仍明确说明。'
      '不要把公共装置测试计为你的自主设计，也不要据此宣称 RSI。')
plan={'created':time.time(),'owner':owner,'previous_task':old['task_id'],
      'previous_design':design['design_id'],'source_origin':'Exact original Pi-authored snapshot',
      'source_hashes':{n:hashlib.sha256(t.encode()).hexdigest() for n,t in design['sources'].items()},
      'new_task_id':contract['task_id'],'environment_id':env['environment_id'],
      'validation_id':contract['validation_id'],'qualification_sha256':sha(release/'qualification.json'),
      'model_profile_preserved':profile,'old_fee_rows':len(fee),'goal':goal,
      'participant_engineering_authored_by_Codex':False,'new_physics_requested_by_operator':False}
sealed(out/'plan.json',plan)
if not args.apply:
    print(json.dumps({'ready':True,'owner':owner,'plan':str(out/'plan.json'),'paid_calls':0}));raise SystemExit(0)
slot=(RUNTIME_ROOT/'design-native.lock').open('a');fcntl.flock(slot,fcntl.LOCK_EX|fcntl.LOCK_NB)
destination=RUNTIME_ROOT/'workbench/design-lab/qualifications'/contract['validation_id']/'qualification.json'
sealed(destination,q)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
with opener.open('http://127.0.0.1:8768/',timeout=10) as response:response.read()
def api(path,body):
    request=urllib.request.Request('http://127.0.0.1:8768'+path,
        data=json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with opener.open(request,timeout=30) as response:return json.load(response)
if old['task_id']==contract['task_id']:raise ValueError('PHASE_ALREADY_BOUND_USE_EXISTING_RECEIPT')
view=api('/api/design-lab',{'session_id':owner,'action':'configure','environment':env,
                        'sources':design['sources'],'new_phase':True})
authority=api('/api/design-lab',{'session_id':owner,'action':'authorize',
    'wall_authorization_text':'持续运行 不设置时间限制','model_profile':profile})
fcntl.flock(slot,fcntl.LOCK_UN);slot.close()
message=api('/api/conversations/'+owner+'/messages',{'operation_id':'native-C-phase-'+contract['task_id'], 'text':goal})
with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    preserved=all((r:=db.execute('SELECT * FROM model_requests WHERE id=?',(key,)).fetchone()) is not None
                  and identity(dict(r))==digest for key,digest in fee.items())
    archived=db.execute('SELECT value FROM design_task_history WHERE owner=? AND task_id=?',
                         (owner,old['task_id'])).fetchone()
    exact_history=archived is not None and json.loads(archived['value'])==old
if not preserved or not exact_history:raise ValueError('ORIGINAL_HISTORY_OR_FEE_DRIFT')
receipt={**plan,'dispatch_message_id':message['id'],'authority_id':authority['authority_id'],
         'initial_new_design':view['current_design'],'original_fee_rows_verified':preserved,
         'exact_old_task_archived':exact_history,'new_native_solves_by_this_script':0,
         'state':'DISPATCHED_ORIGINAL_PI_C','physical_verified':False,'full_product_passed':False}
sealed(out/'dispatch.json',receipt)
print(json.dumps({'owner':owner,'state':receipt['state'],'receipt':str(out/'dispatch.json')}))
