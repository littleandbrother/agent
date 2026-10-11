#!/usr/bin/env python3
"""Pi-improver and paired Pi solvers against the one live provider ledger.

The tool-only loopback server below is not a Workbench, has no credential or
database writer, and exposes no hidden evaluation. Each new owner represents
a new registered experiment, never a replacement paper task or fee bypass.
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
from bfworld.agentlab.design_lab import method_study as m
from bfworld.agentlab.design_lab.contracts import sha,sealed
from bfworld.agentlab.store import canonical,identity
from bfworld.agentlab import launcher
from bfworld.agentlab.runtime_config import NODE,PI

parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');args=parser.parse_args()
OUT=APP/'docs/agentlab/refactor-r3-r5-20261012'
home=Path('/Users/depengsu/.local/share/bf-agent-runtime/workbench');dbpath=home/'state/workbench.sqlite'
service='http://127.0.0.1:8768'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
operator=(home/'state/operator.token').read_text().strip()
def api(path,body):
    request=urllib.request.Request(service+path,data=canonical(body).encode(),
        headers={'Authorization':'Bearer '+operator,'Content-Type':'application/json'})
    with opener.open(request,timeout=60) as response:return json.load(response)
def read_rows(owner):
    with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        return [dict(r) for r in db.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY created',(owner,))]
def wire_proof(owner,instruction):
    with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        result=[]
        for row in db.execute('SELECT request_id,wire,receipt FROM model_request_evidence WHERE owner=? ORDER BY created',(owner,)):
            wire=json.loads(row['wire']);content='\n'.join(str(x.get('content','')) for x in wire['messages'] if x['role'] in ('system','developer'))
            result.append({'request_id':row['request_id'],'wire_sha256':identity(wire),
                           'instruction_present':instruction in content,'wire_bytes':len(row['wire'].encode())})
        return result

protocol={'schema_version':'bf-method-study-protocol-v1','model':'deepseek-flash','thinking':'high',
          'model_profile':'engineering-reasoning-compact-v2','base_method':'H-method-000',
          'source_episode_ids':['C-F0-actual-frame-repair-20261012'],
          'pairs':list(m.cases()),'order':'parent,child interleaved by fixed case order',
          'adoption_rule':'all child PASS, no correctness regression; one gain with child+acquisition <=1.5*parent, or >=15% cost reduction including acquisition',
          'unbounded_authorization':'Direct user: no cumulative fee/token/request/wall-clock cap',
          'model_semantics':sha(m.__file__),'sdk_source':sha(PI/'packages/bf-agent/src/method-task.ts'),
          'runner_sha256':sha(__file__),'variant_evaluation':'each pair uses its named new sequence; synchronous control begins with an already correct public core',
          'old_owners_replaced':False,'hidden_evaluation_visible':False,
          'claim':'Finite callback variants, not independent-paper generalization; failures and rejects retained'}
protocol['protocol_id']='method-study-'+identity(protocol)[:24]
root=OUT/protocol['protocol_id'];root.mkdir(parents=True,exist_ok=True)
sealed(root/'protocol.json',protocol)

# Independent no-Agent compiled positive and unmodified failing starter must
# establish that this apparatus can both pass and reject before Pi is connected.
ref=r'''#include <stdint.h>
static uint32_t c,o;static int p,d,connected;
void reset(void){c=o=0;p=d=connected=0;}
void handle(int k,uint32_t x,uint32_t y){
 if(k==1){c=x;connected=1;p=0;o=0;}
 else if(k==2&&connected&&x==c){connected=0;p=0;o=0;}
 else if(k==3&&connected&&x==c){o=y;p=1;}
 else if(k==5&&connected&&p&&x==c&&y==o){d++;p=0;o=0;}
 else if(k==6&&connected&&p&&x==c&&y==o){p=0;o=0;}
}
int pending(void){return p;}uint32_t connection(void){return c;}
uint32_t operation(void){return o;}int deliveries(void){return d;}
'''
if not (root/'no-agent-qualification.json').exists():
    positive=m.evaluate(ref,root/'no-agent-positive',m.cases())
    negative=m.evaluate(m.STARTER,root/'no-agent-negative',m.cases())
    sealed(root/'no-agent-qualification.json',{'positive':positive,'negative':negative,
        'passed':positive['passed'] and not negative['passed'],'paid_calls':0})
q=json.loads((root/'no-agent-qualification.json').read_text())
if not q['passed']:raise RuntimeError('METHOD_ENVIRONMENT_UNQUALIFIED')
if not args.run:
    print(canonical({'ready':True,'protocol':str(root/'protocol.json'),'no_agent_passed':True}));raise SystemExit(0)

harness=root/'frozen-controller';harness.mkdir(exist_ok=True)
for rel in ['src/method-task.ts','dist/method-task.js']:
    source=PI/'packages/bf-agent'/rel;destination=harness/rel;destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists() and sha(source)!=sha(destination):raise RuntimeError('METHOD_EXECUTOR_DRIFT')
    if not destination.exists():shutil.copyfile(source,destination)
if not (harness/'node_modules').exists():(harness/'node_modules').symlink_to(PI/'node_modules',target_is_directory=True)
sealed(harness/'manifest.json',{'schema_version':'bf-method-controller-v1',
    'files':{rel:sha(harness/rel) for rel in ['src/method-task.ts','dist/method-task.js']},
    'protocol_id':protocol['protocol_id'],'python_semantics':sha(m.__file__),'model_profile':protocol['model_profile']})

def run_one(label,kind,instruction,method_id,visible):
    folder=root/'trials'/label;folder.mkdir(parents=True,exist_ok=True)
    result_file=folder/'result.json'
    if result_file.exists():return json.loads(result_file.read_text())
    if (folder/'attempt.json').exists():raise RuntimeError('EXISTING_INCOMPLETE_ATTEMPT_INSPECT_BEFORE_RETRY:'+label)
    goal=('独立生成一个条件化 Skill 补丁，根据提供的真实经历与父方法。不要写当前工程答案。用 inspect 读经历，提交 candidate 六字段：instruction、hypothesis、falsifier、applicability、negative_scope、evidence_episodes。可拒绝改进，但不能自授通过。' if kind=='improver' else
          '独立修订当前异步事件 C 核心，让它符合冻结 ABI。先 inspect，自行选择检查、修改与验证；submit 提交最终 program.c。公开检查只是局部，独立验收另运行。')
    conversation=api('/api/conversations',{'text':goal,'operation_id':protocol['protocol_id']+'-'+label,
                    'defer_dispatch':True})
    owner=conversation['id']
    sealed(folder/'owner.json',{'owner':owner,'task_id':protocol['protocol_id'],'role':kind,'old_paper_owner_replacement':False})
    authority=api('/api/design-lab',{'action':'method_authorize','session_id':owner,
                  'task_id':protocol['protocol_id'],'wall_authorization_text':'持续运行 不设置时间限制'})
    token=authority.pop('participant_token')
    workspace=home/'participants'/owner;workspace.mkdir(parents=True,exist_ok=True);(workspace/'.tmp').mkdir(exist_ok=True)
    variant=label.rsplit('-',1)[0] if kind=='solver' else None
    initial=ref if variant=='synchronous-negative-scope' else m.STARTER
    state={'kind':kind,'source':initial,'submitted':False,'checks':[],'candidate':None}
    tool_token=secrets.token_urlsafe(32)
    public={'basic-operation':[(1,7,0),(3,7,2),(4,7,2),(5,7,2),(5,7,2)]}
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            try:
                if self.headers.get('Authorization')!='Bearer '+tool_token:raise PermissionError('METHOD_TOKEN')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<96_000:raise ValueError('METHOD_BODY_BOUND')
                body=json.loads(self.rfile.read(length));action=body.get('action')
                if action=='inspect':
                    value={'kind':kind,'task_variant':variant,'abi':m.ABI,'source':state['source'] if kind=='solver' else None,
                           'visible_episodes':visible,'parent_method_id':method_id,'submitted':state['submitted'],
                           'public_sequences':public if kind=='solver' else None,
                           'candidate_fields':['instruction','hypothesis','falsifier','applicability','negative_scope','evidence_episodes']}
                elif action=='check' and kind=='solver':
                    source=body.get('source',state['source']);state['source']=source
                    value=m.evaluate(source,folder/('public-check-'+str(len(state['checks']))),public)
                    state['checks'].append(value)
                elif action=='submit':
                    if state['submitted']:raise ValueError('METHOD_ALREADY_SUBMITTED')
                    if kind=='solver':
                        source=body.get('source',state['source'])
                        if not isinstance(source,str) or len(source.encode())>32_000:raise ValueError('METHOD_SOURCE_SIZE')
                        state['source']=source;sealed(folder/'submitted-source.json',{'program.c':source,'actor':'Pi','rationale':body.get('rationale')})
                    else:
                        state['candidate']=m.candidate(body['candidate'],method_id,protocol['source_episode_ids'])
                        sealed(folder/'candidate.json',state['candidate'])
                        text='---\nname: bf-callback-identity\nversion: '+state['candidate']['method_id']+'\n---\n'+state['candidate']['instruction']+'\n'
                        path=folder/'SKILL.md'
                        with path.open('x') as stream:stream.write(text)
                    state['submitted']=True;value={'submitted':True,'independent_adoption':False}
                else:raise ValueError('METHOD_ACTION_DENIED')
                self.send_response(200);self.end_headers();self.wfile.write(canonical(value).encode())
            except Exception as exc:
                self.send_response(400);self.end_headers();self.wfile.write(canonical({'error':str(exc)}).encode())
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    config={'workspace':str(workspace),'service':service,'token':token,'owner':owner,'goal':goal,
            'instruction':instruction,'toolService':f'http://127.0.0.1:{server.server_port}/tool',
            'toolToken':tool_token,'methodId':method_id}
    profile=launcher.seatbelt(workspace,harness,server.server_port)
    # The exact finite extension talks to its tool loopback and the one provider
    # port. Default deny still covers files outside its frozen/workspace roots.
    profile += '\n(allow network-outbound (remote tcp "localhost:8768"))\n'
    attempt={'owner':owner,'label':label,'kind':kind,'method_id':method_id,'started':time.time(),
             'authority':authority,'harness_sha256':sha(harness/'manifest.json'),'sandbox_sha256':identity(profile)}
    sealed(folder/'attempt.json',attempt)
    print(canonical({'phase':'START','label':label,'owner':owner}),flush=True)
    try:
        with (folder/'public-trace.jsonl').open('w') as stdout,(folder/'stderr.log').open('w') as stderr:
            proc=subprocess.Popen(['/usr/bin/sandbox-exec','-p',profile,str(NODE),str(harness/'dist/method-task.js')],
                cwd=workspace,env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','TMPDIR':str(workspace/'.tmp'),'LANG':'en_US.UTF-8'},
                stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,start_new_session=True)
            proc.stdin.write((canonical(config)+'\n').encode());proc.stdin.close()
            # No cumulative wall budget. Eventual model/provider or explicit
            # operation containment failures stay visible rather than retrying.
            proc.wait()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    rows=read_rows(owner);usage=[json.loads(r['usage']) for r in rows if r['usage']]
    proof=wire_proof(owner,instruction)
    observed_profile=[]
    with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
        for (wire,) in db.execute('SELECT wire FROM model_request_evidence WHERE owner=?',(owner,)):
            body=json.loads(wire);observed_profile.append({k:body.get(k) for k in ('model','thinking','reasoning_effort','max_tokens')})
    valid=proc.returncode==0 and state['submitted'] and bool(rows) and all(r['status']=='SETTLED' for r in rows)
    final=None
    if valid and kind=='solver':final=m.evaluate(state['source'],folder/'independent-final',{variant:m.cases()[variant]})
    value={**attempt,'ended':time.time(),'process_exit':proc.returncode,'submitted':state['submitted'],
           'valid_execution':valid,'model_requests':len(rows),'cost_usd':sum(r['charged'] for r in rows),
           'cache_tariff_estimate_usd':sum((u.get('prompt_cache_hit_tokens',0)*.006+
            u.get('prompt_cache_miss_tokens',u['prompt_tokens']-u.get('prompt_cache_hit_tokens',0))*.3+u['completion_tokens']*1.2)/1e6 for u in usage),
           'billing_rows':rows,'method_wire':proof,'actual_profiles':observed_profile,
           'public_checks':len(state['checks']),'passed':valid and (final['passed'] if final else True),
           'independent_check':final,'candidate':state['candidate'],
           'public_trace_sha256':sha(folder/'public-trace.jsonl'),'Codex_participant_edits':0}
    sealed(result_file,value)
    print(canonical({'phase':'RESULT','label':label,'valid':valid,'passed':value['passed'],'cost_usd':value['cost_usd']}),flush=True)
    if not valid:raise RuntimeError('PI_METHOD_EXECUTION_FAILED:'+label+': '+(folder/'stderr.log').read_text()[-1000:])
    return value

episode_path=APP/'docs/agentlab/refactor-r0-r2-20261011/trial/independent-review.json'
episode=json.loads(episode_path.read_text())
trace_path=APP/'docs/agentlab/refactor-r0-r2-20261011/trial/pi-public-trace.jsonl'
public=[]
for line in trace_path.read_text().splitlines():
    v=json.loads(line)
    if v.get('type') in ('design_tool_fact','assistant_public','text_delta'):
        public.append(v)
visible=[{'episode_id':protocol['source_episode_ids'][0],'scope':episode.get('scope'),
          'facts':'Actual Pi C core initially sent wrong frame/event identity, independent gates failed; Pi revised protocol and uint32 latch/dedup, re-executed and submitted; 17 settled requests. No operator participant edits.',
          'review_sha256':sha(episode_path),'public_trace_sha256':sha(trace_path),'public_trace_excerpt':public[:12],
          'boundaries':'Host core/fixed D5, not real SoC/RF. Only public events, no hidden reasoning.'}]
base='先核对当前合同、输入身份和源码，使用实际编译检查与独立结果支持提交。保留适用范围与未检查项，不用文件存在代替功能通过。'
improver=run_one('improver','improver',base,'H-method-000',visible)
c=improver['candidate'];sealed(root/'candidate.json',c)
pairs=[]
for index,name in enumerate(protocol['pairs']):
    parent=run_one(name+'-parent','solver',base,'H-method-000',visible)
    child=run_one(name+'-child','solver',base+'\n条件化方法 Skill：\n'+c['instruction'],c['method_id'],visible)
    pairs.append({'task_variant':name,'parent':parent,'child':child})
verdict=m.decision(pairs,improver['cost_usd']);verdict['candidate_id']=c['method_id']
verdict['actual_patch_sha256']=sha(root/'trials/improver/SKILL.md')
verdict['all_actual_loaded']=all(all(r['instruction_present'] for r in p['child']['method_wire']) for p in pairs)
if not verdict['all_actual_loaded']:verdict.update(adopted=False,decision='REJECT_LOAD_FAILURE')
sealed(root/'comparison.json',{'protocol_id':protocol['protocol_id'],'pairs':pairs,'improver':improver,'decision':verdict})
sealed(root/'adoption.json',verdict)
sealed(root/'lineage.json',{'parent':'H-method-000','candidate':c['method_id'],'decision':verdict['decision'],
      'adopted_descendant':c['method_id'] if verdict['adopted'] else None,
      'R5_next_generation':'READY_FOR_SEPARATE_NEW_EVALUATION' if verdict['adopted'] else 'BLOCKED_BY_NO_ADOPTION',
      'RSI':False,'physical':'NOT_TESTED'})
print(canonical({'protocol':str(root/'protocol.json'),'adoption':verdict}),flush=True)
