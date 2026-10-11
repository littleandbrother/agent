#!/usr/bin/env python3
"""Actual Pi A/B F0 design trials over a qualified synthetic environment.

The tool-only server has no Workbench or credential. Authority and fees use the
one production provider. Program changes and finite acceptance are real, while
mechanical calibration, converter topology and hardware are explicitly absent.
"""
import argparse
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request

APP=Path(__file__).resolve().parents[2]
os.environ.setdefault('BF_PI_ROOT',str(APP.parent/'pi-bf-aiot'))
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab import finite_cases as f
from bfworld.agentlab.design_lab.contracts import sha,sealed
from bfworld.agentlab.store import canonical,identity
from bfworld.agentlab import launcher
from bfworld.agentlab.runtime_config import NODE,PI

parser=argparse.ArgumentParser();parser.add_argument('--case',choices=('A','B'),required=True)
parser.add_argument('--run',action='store_true');parser.add_argument('--resume-owner');parser.add_argument('--resume-from',type=Path);args=parser.parse_args()
OUT=APP/'docs/agentlab/refactor-r3-r5-20261012'
env=f.manifest(args.case)
qualified=[p for p in sorted(OUT.glob('environment-*/qualification.json'))
    if json.loads(p.read_text())['model_domain_controls_passed'] and
    json.loads((p.parent/args.case/'environment.json').read_text())['environment_id']==env['environment_id']]
assert qualified, 'FINITE_CURRENT_ENV_UNQUALIFIED'
qualification=qualified[-1]
protocol={'schema_version':'bf-finite-pi-design-trial-v1','case':args.case,'contract':env,
          'model':'deepseek-flash','thinking':'high','model_profile':'engineering-reasoning-compact-v2',
          'qualification_sha256':sha(qualification),'executor_sha256':sha(__file__),
          'sdk_source_sha256':sha(PI/'packages/bf-agent/src/method-task.ts'),
          'resume_owner':args.resume_owner,'resume_from_sha256':sha(args.resume_from) if args.resume_from else None,
          'independent_variants':['fine-grid','permuted-signal-labels' if args.case=='A' else 'single-event-lower-energy'],
          'scope':'F0 synthetic source, actual compiled C, fixed stage current and virtual receive only',
          'old_paper_owners_replaced':False,'old_D5_native_solves':0}
protocol['task_id']='method-study-finite-'+args.case+'-'+identity(protocol)[:20]
root=OUT/protocol['task_id'];root.mkdir(parents=True,exist_ok=True)
sealed(root/'protocol.json',protocol)
if not args.run:
    print(canonical({'ready':True,'protocol':str(root/'protocol.json')}));raise SystemExit(0)
if (root/'attempt.json').exists():raise RuntimeError('EXISTING_ATTEMPT_INSPECT_BEFORE_RESUME')
home=Path('/Users/depengsu/.local/share/bf-agent-runtime/workbench')
dbpath=home/'state/workbench.sqlite'
service='http://127.0.0.1:8768'
operator=(home/'state/operator.token').read_text().strip()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def api(path,body):
    request=urllib.request.Request(service+path,data=canonical(body).encode(),
        headers={'Authorization':'Bearer '+operator,'Content-Type':'application/json'})
    with opener.open(request,timeout=60) as response:return json.load(response)
goal=('在已资格确认的合成连续供能源环境里，独立修订并采用实际 C 程序，完成外部四个请求的有效采样、二类波形判断及期限内虚拟接收。' if args.case=='A' else
      '在已资格确认的单次 Q–V–x 能量上界环境里，独立修订并采用实际 C 程序，零初始外部储能，单个事件在期限内正确虚拟接收，不依赖第二次动作。')
goal+='先 inspect 核对合同、接口和源码，再自行选择 check 和修订；submit 提交最终 program.c 与公开采用理由。核心验收不能由你自授通过，未支持的机械/电源拓扑/SoC/物理 RF 不作成功声明。'
if args.resume_owner:
    assert args.resume_from and args.resume_from.resolve().is_relative_to(OUT.resolve()), 'FINITE_RESUME_SOURCE_SCOPE'
    original=json.loads(args.resume_from.read_text())
    assert original['owner']==args.resume_owner and original['case']==args.case, 'FINITE_ORIGINAL_OWNER_REQUIRED'
    owner=args.resume_owner
    goal+='原任务继续；公共接口发布了严格参数规则，旧失败、SDK消息和费用全部保留。请读取 inspect 的 call_parameters。'
else:
    conversation=api('/api/conversations',{'text':goal,'operation_id':protocol['task_id'],'defer_dispatch':True})
    owner=conversation['id']
sealed(root/'owner.json',{'owner':owner,'task_id':protocol['task_id'],'role':'finite-case-designer','old_owner_replacement':False})
authority=api('/api/design-lab',{'action':'method_authorize','session_id':owner,
    'task_id':protocol['task_id'],'wall_authorization_text':'持续运行 不设置时间限制'})
token=authority.pop('participant_token')
workspace=home/'participants'/owner;workspace.mkdir(parents=True,exist_ok=True);(workspace/'.tmp').mkdir(exist_ok=True)
harness=root/'frozen-controller';harness.mkdir(exist_ok=True)
for rel in ('src/method-task.ts','dist/method-task.js'):
    source=PI/'packages/bf-agent'/rel;destination=harness/rel;destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,destination)
(harness/'node_modules').symlink_to(PI/'node_modules',target_is_directory=True)
shutil.copyfile(f.__file__,harness/'finite_cases.py')
shutil.copyfile(__file__,harness/'run_finite_design.py')
sealed(harness/'manifest.json',{'schema_version':'bf-finite-controller-v1',
    'files':{r:sha(harness/r) for r in ('src/method-task.ts','dist/method-task.js','finite_cases.py','run_finite_design.py')},
    'protocol_id':protocol['task_id'],'environment_id':env['environment_id']})
initial=(json.loads((args.resume_from.parent/'submitted-source.json').read_text())['program.c'] if args.resume_from else
         f.reference_source(args.case,wrong_class=args.case=='A',wrong_id=args.case=='B')['program.c'])
state={'source':initial,'checks':[],'submitted':False,'rationale':None}
tool_token=secrets.token_urlsafe(32)
def run_check(source,directory,**kwargs):
    sources={'program.c':source};build=f.build(env,sources,directory)
    execution=f.execute(env,sources,build,directory,**kwargs)
    numeric=f.native_energy_check(execution,directory)
    check=f.evaluate(env,build,execution,native=numeric)
    for name,value in (('build.json',build),('execution.json',execution),('numerical.json',numeric),('check.json',check)):
        sealed(directory/name,value)
    return {'build':build,'execution':execution,'check':check,'numeric':numeric}
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_POST(self):
        try:
            if self.headers.get('Authorization')!='Bearer '+tool_token:raise PermissionError('FINITE_TOOL_TOKEN')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<96_000:raise ValueError('FINITE_TOOL_BODY_BOUND')
            body=json.loads(self.rfile.read(length));action=body.get('action')
            if set(body)-{'action','source','rationale'}:raise ValueError('FINITE_FIELDS: inspect(action); check(action,source:string); submit(action,source:string,rationale:string). candidate is not a program input.')
            if action in ('check','submit') and not isinstance(body.get('source'),str):raise ValueError('FINITE_SOURCE_FIELD_REQUIRED: source is the exact program.c text')
            if action=='inspect':
                value={'contract':env,'source':state['source'],'submitted':state['submitted'],
                    'ABI':'void reset(void); int step(double dt_s,double supply_V,uint32_t request_id,int sample_available,double sample,uint32_t *tx_id,int *class); double current_A(void); int phase(void);',
                    'ABI_semantics':'phase 0=idle,1=boot,2=sample,3=TX; exact contract stage current. Output tx_id=0 means none. No truth label is supplied. sample_available is true only during sample phase. reset on rail <1.8V. Requests start at external contract times. step return is informational, outputs drive reception.',
                    'independent_checks':f.GATES,'last_check':state['checks'][-1]['check'] if state['checks'] else None}
                value['call_parameters']={'inspect':{'action':'inspect'},'check':{'action':'check','source':'exact program.c source text'},'submit':{'action':'submit','source':'exact program.c source text','rationale':'public adoption reason, at least 10 characters'}}
            elif action=='check':
                source=body.get('source',state['source'])
                if not isinstance(source,str) or len(source.encode())>64_000:raise ValueError('FINITE_SOURCE_BOUND')
                state['source']=source
                result=run_check(source,root/('public-check-'+str(len(state['checks']))))
                state['checks'].append(result)
                value={'source_sha256':identity({'program.c':source}),**result}
            elif action=='submit':
                if state['submitted']:raise ValueError('FINITE_ALREADY_SUBMITTED')
                source=body.get('source',state['source'])
                if not isinstance(source,str) or len(source.encode())>64_000:raise ValueError('FINITE_SOURCE_BOUND')
                rationale=body.get('rationale')
                if not isinstance(rationale,str) or len(rationale)<10:raise ValueError('FINITE_PUBLIC_REASON_REQUIRED')
                state.update(source=source,rationale=rationale,submitted=True)
                sealed(root/'submitted-source.json',{'program.c':source,'actor':'Pi','rationale':rationale})
                value={'submitted':True,'independent_acceptance_pending':True}
            else:raise ValueError('FINITE_ACTION_DENIED')
            self.send_response(200);self.end_headers();self.wfile.write(canonical(value).encode())
        except Exception as exc:
            self.send_response(400);self.end_headers();self.wfile.write(canonical({'error':str(exc)}).encode())
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
instruction='以当前合同和源码为准，自主选择验证与修订，记录采用理由和未支持范围。一次工具执行成功不等于功能验收。保持原始费用与作业历史。程序工具字段是 source:string；candidate 仅属于改进器接口，此任务不接受它。'
config={'workspace':str(workspace),'service':service,'token':token,'owner':owner,'goal':goal,
        'instruction':instruction,'toolService':f'http://127.0.0.1:{server.server_port}/tool','toolToken':tool_token,
        'methodId':'H-finite-design-000'}
profile=launcher.seatbelt(workspace,harness,server.server_port)+'\n(allow network-outbound (remote tcp "localhost:8768"))\n'
attempt={'owner':owner,'task_id':protocol['task_id'],'started':time.time(),'authority':authority,
         'harness_sha256':sha(harness/'manifest.json'),'sandbox_sha256':identity(profile)}
with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
    baseline_ids={r[0] for r in db.execute('SELECT id FROM model_requests WHERE owner=?',(owner,))}
attempt['prior_model_rows']=len(baseline_ids)
sealed(root/'attempt.json',attempt)
print(canonical({'phase':'START','case':args.case,'owner':owner}),flush=True)
try:
    with (root/'public-trace.jsonl').open('w') as stdout,(root/'stderr.log').open('w') as stderr:
        proc=subprocess.Popen(['/usr/bin/sandbox-exec','-p',profile,str(NODE),str(harness/'dist/method-task.js')],
            cwd=workspace,env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','TMPDIR':str(workspace/'.tmp'),'LANG':'en_US.UTF-8'},
            stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,start_new_session=True)
        proc.stdin.write((canonical(config)+'\n').encode());proc.stdin.close();proc.wait()
finally:
    server.shutdown();server.server_close();thread.join(timeout=2)
with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    rows=[dict(r) for r in db.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY created',(owner,))]
    wires=[json.loads(r['wire']) for r in db.execute('SELECT request_id,wire FROM model_request_evidence WHERE owner=? ORDER BY created',(owner,)) if r['request_id'] not in baseline_ids]
phase_rows=[r for r in rows if r['id'] not in baseline_ids]
valid=proc.returncode==0 and state['submitted'] and bool(phase_rows) and all(r['status']=='SETTLED' for r in phase_rows)
checks=[]
if valid:
    final=run_check(state['source'],root/'independent-final')
    checks.append(final)
    variant=run_check(state['source'],root/'independent-variant',dt=.00025,
        **({'truth_shift':1} if args.case=='A' else {'source_scale':.8}))
    checks.append(variant)
result={**attempt,'ended':time.time(),'case':args.case,'valid_execution':valid,'process_exit':proc.returncode,
    'public_checks':len(state['checks']),'submitted':state['submitted'],
    'design_id':'D-'+identity({'environment':env['environment_id'],'sources':{'program.c':state['source']}}),
    'actual_input_sha256':identity({'program.c':state['source']}),'adoption_actor':'Pi','adoption_rationale':state['rationale'],
    'scoped_passed':valid and all(c['check']['scoped_status']=='PASS' for c in checks),
    'checks':checks,'model_requests':len(phase_rows),'owner_model_requests':len(rows),'registered_charged_usd':sum(r['charged'] for r in phase_rows),
    'owner_registered_charged_usd':sum(r['charged'] for r in rows),
    'billing_rows':rows,'actual_profiles':[{k:w.get(k) for k in ('model','thinking','reasoning_effort','max_tokens')} for w in wires],
    'method_actual_loaded':bool(wires) and all(instruction in '\n'.join(str(x.get('content','')) for x in w['messages'] if x['role'] in ('system','developer')) for w in wires),
    'public_trace_sha256':sha(root/'public-trace.jsonl'),'Codex_participant_source_edits':0,
    'full_product_passed':False,'physical_verified':False,'physical_validation':'NOT_TESTED',
    'scope':protocol['scope'],'claim':'Finite program repair, actual execution and synthetic power/service feedback; not mechanical/circuit/PCB/target-MCU design or physical receive.'}
sealed(root/'result.json',result)
print(canonical({'case':args.case,'passed':result['scoped_passed'],'requests':len(rows),'registered_charged_usd':result['registered_charged_usd'],'result':str(root/'result.json')}))
if not result['scoped_passed']:raise SystemExit(1)
