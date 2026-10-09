"""A separately declared, small engineering-method round over closed episodes.

The actor sees public development facts, never its eventual paired verdicts.
These are workflow/C host fixtures, not completed paper devices or hardware.
"""
import json
import shutil
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .store import canonical, identity
from .literature_campaign import DEFAULT_ROOT, digest, read, put_once, owner_budget
from .literature_rsi import comparison, qualify_candidate, verify_method

BASE = '''你是 BF Agent Design 的 Pi。执行本会话单独的局部工程任务。先读 TASK.md、task-input.json、experience.json 和所需专业技能；已有事实与接口定义必须对账。只编辑本工作目录产物，保留只读输入。实际生成可检查文件，失败按事实诊断，产物/方法/物理结论分开。不能读取评价器源码、参考答案或其他会话文件，不能自行宣告验收。工具仅用于本局部任务，不派发原生求解或编辑任何旧工程。完成时写 report.md，说明实际修改及限制。'''

HEADER = '''#ifndef POLICY_H
#define POLICY_H
#include <stdint.h>
enum { NONE=0, REQUEST_SAMPLE=1, SEND_SAMPLE=2 };
typedef struct { unsigned started, connected, pending, queued, epoch, sample_epoch, delivered; int last_error; } policy_t;
void reset(policy_t *p);
void enable_energy(policy_t *p);
void connected(policy_t *p);
void disconnected(policy_t *p);
unsigned next_action(policy_t *p);
void sample_done(policy_t *p, unsigned epoch, int success);
void send_done(policy_t *p, int success);
#endif
'''
BROKEN = '''#include "policy.h"
#include <string.h>
void reset(policy_t *p){memset(p,0,sizeof(*p));}
void enable_energy(policy_t *p){p->started=1;}
void connected(policy_t *p){p->connected=1;}
void disconnected(policy_t *p){p->connected=0;}
unsigned next_action(policy_t *p){if(p->queued){p->delivered++;return SEND_SAMPLE;}if(p->started && p->connected){p->pending=1;p->sample_epoch=p->epoch;return REQUEST_SAMPLE;}return NONE;}
void sample_done(policy_t *p,unsigned epoch,int success){(void)epoch;p->pending=0;p->queued=success;}
void send_done(policy_t *p,int success){p->queued=0;p->last_error=success?0:-1;}
'''
REFERENCE = '''#include "policy.h"
#include <string.h>
void reset(policy_t *p){memset(p,0,sizeof(*p));}
void enable_energy(policy_t *p){p->started=1;}
void connected(policy_t *p){p->epoch++;p->connected=1;p->pending=p->queued=0;}
void disconnected(policy_t *p){p->epoch++;p->connected=0;p->pending=p->queued=0;}
unsigned next_action(policy_t *p){if(!p->started || !p->connected)return NONE;if(p->queued)return SEND_SAMPLE;if(p->pending)return NONE;p->pending=1;p->sample_epoch=p->epoch;return REQUEST_SAMPLE;}
void sample_done(policy_t *p,unsigned epoch,int success){if(!p->started || !p->connected || !p->pending || epoch!=p->epoch || epoch!=p->sample_epoch)return;p->pending=0;p->queued=success?1:0;}
void send_done(policy_t *p,int success){if(!p->started || !p->connected || !p->queued)return;if(success){p->delivered++;p->last_error=0;}else p->last_error=-1;p->queued=0;}
'''
# Independently specified event orders; assertions never call the reference.
HOST_CHECK = '''#include "policy.h"
#include <stdio.h>
static void linked(policy_t *p){reset(p);enable_energy(p);connected(p);}
int main(void){policy_t p;unsigned e;int a,b,c,d,f,g,h;
 reset(&p);sample_done(&p,p.epoch,1);a=next_action(&p)==NONE && p.queued==0;
 linked(&p);next_action(&p);e=p.sample_epoch;disconnected(&p);sample_done(&p,e,1);b=next_action(&p)==NONE && p.queued==0;
 linked(&p);next_action(&p);e=p.sample_epoch;sample_done(&p,e,1);next_action(&p);send_done(&p,0);c=p.delivered==0 && p.last_error!=0;
 linked(&p);d=next_action(&p)==REQUEST_SAMPLE && next_action(&p)==NONE;
 linked(&p);next_action(&p);e=p.sample_epoch;disconnected(&p);connected(&p);next_action(&p);sample_done(&p,e,1);f=p.pending==1 && p.queued==0;
 linked(&p);next_action(&p);e=p.sample_epoch;sample_done(&p,e,1);g=next_action(&p)==SEND_SAMPLE && p.delivered==0;send_done(&p,1);g=g && p.delivered==1;send_done(&p,1);g=g && p.delivered==1;
 linked(&p);next_action(&p);e=p.sample_epoch;sample_done(&p,e,0);h=next_action(&p)==REQUEST_SAMPLE && p.delivered==0;
 printf("{\\"before_enable\\":%s,\\"late_after_disconnect\\":%s,\\"rejected_send\\":%s,\\"one_pending_sample\\":%s,\\"old_connection_epoch\\":%s,\\"successful_send_once\\":%s,\\"failed_sample_retry\\":%s}\\n",a?"true":"false",b?"true":"false",c?"true":"false",d?"true":"false",f?"true":"false",g?"true":"false",h?"true":"false");return 0;}
'''


def check_output(kind, public, workspace, output):
    public=Path(public);workspace=Path(workspace);output=Path(output)
    output.mkdir(parents=True,exist_ok=True);problems=[];checks={}
    try:
        task=read(public/'task-input.json')
        if kind=='manifest':
            body=read(workspace/'manifest.json');files=body.get('files',[])
            names=[x['path'] for x in files]
            checks['paths_unique']=len(names)==len(set(names))
            checks['complete_scope']=set(names)==set(task['required_files'])
            checks['actual_hashes']=all(x['path'] in task['required_files'] and
                x['sha256']==digest(workspace/x['path']) for x in files)
            checks['actual_job_binding']=body.get('trusted_jobs')==task['trusted_jobs']
            checks['claim_boundary']=body.get('physical_verified') is False and body.get('full_product_passed') is False
        elif kind=='geometry':
            from .assembly import validate
            value=validate(read(workspace/'assembly.json'));note=read(workspace/'sizing-note.json')
            part=value['parts'][0];actual=read(public/'cad-parameters.json')['film_thickness_mm']
            checks['part_identity']=len(value['parts'])==1 and part['id']=='film' and part['role']=='input'
            checks['source_dimension_preserved']=digest(workspace/'cad-parameters.json')==digest(public/'cad-parameters.json')
            checks['approximation_explicit']=(note.get('envelope_only') is True and
                note.get('actual_thickness_mm')==actual and note.get('envelope_thickness_mm')==part['geometry']['size_mm'][2] and
                note.get('physical_verified') is False and part['source']['basis']=='design-assumption')
            checks['actual_in_plane_dimensions']=part['geometry']['size_mm'][:2]==[24,16]
        elif kind=='firmware':
            for n in ('policy.c','policy.h'):shutil.copyfile(workspace/n,output/n)
            (output/'independent-events.c').write_text(HOST_CHECK)
            build=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','policy.c','independent-events.c','-o','replay'],cwd=output,capture_output=True,text=True,timeout=20)
            (output/'build.log').write_text(build.stdout+build.stderr)
            if build.returncode:raise ValueError('HOST_BUILD_FAILED')
            run=subprocess.run([str(output/'replay')],capture_output=True,text=True,timeout=5)
            (output/'run.log').write_text(run.stdout+run.stderr);checks=json.loads(run.stdout)
        else:raise ValueError('UNKNOWN_LOCAL_TASK')
        problems.extend(k for k,v in checks.items() if v is not True)
        for name in task['readonly_files']:
            if digest(public/name)!=digest(workspace/name):problems.append('INPUT_CHANGED:'+name)
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        problems.append(type(exc).__name__+':'+str(exc))
    return {'status':'PASS' if not problems else 'FAIL','problems':problems,'checks':checks,
            'scope':'Local workflow validation / C host event replay only','full_product_passed':False,'physical_verified':False}


def make_tasks(root):
    """Construct fixed, declared fixtures and calibrate both controls before Pi."""
    root=Path(root);out=[]
    for kind,split,paper in [('manifest','development','P01'),('geometry','new-variant','P03'),('firmware','cross-paper','P04')]:
        folder=root/'public-tasks'/kind;folder.mkdir(parents=True,exist_ok=False)
        readonly=['task-input.json','TASK.md']
        if kind=='manifest':
            for n,b in [('network.txt','P01 source-bound network draft\n'),('limits.txt','No radio / physical validation\n')]:
                (folder/n).write_text(b);readonly.append(n)
            jobs=[{'job_id':'development-job-fixture','project_sha256':'a'*64}]
            files=[{'path':n,'sha256':digest(folder/n)} for n in ('network.txt','limits.txt')]
            broken={'files':files+[files[0]],'trusted_jobs':jobs,'physical_verified':False,'full_product_passed':False}
            (folder/'manifest.json').write_text(json.dumps(broken,indent=2)+'\n')
            instruction='修复 manifest.json 的重复文件记录。只包含 network.txt 与 limits.txt 两个真实文件，各出现一次，计算实际SHA256，保留task-input中的可信job绑定。physical_verified与full_product_passed均保持false。该job是公开开发夹具，不是实际工程通过。'
            extra={'required_files':['network.txt','limits.txt'],'trusted_jobs':jobs}
            reference={**broken,'files':files}
        elif kind=='geometry':
            body={'title':'P03 thin-film representation variant','units':'mm','parts':[{'id':'film','name':'thin film','role':'input','geometry':{'kind':'box','size_mm':[24,16,.03]},'source':{'basis':'design-assumption','note':'Paper dimension retained separately; workspace envelope is a representation.'}}],
                'required_roles':['input'],'requirements':[],'assumptions':[],'interfaces':[],'energy':{},'presentation':{'camera_deg':35}}
            (folder/'assembly.json').write_text(json.dumps(body,indent=2)+'\n')
            (folder/'cad-parameters.json').write_text(json.dumps({'film_thickness_mm':.03,'units':'mm'},indent=2)+'\n');readonly.append('cad-parameters.json')
            (folder/'contract-schema.md').write_text('当前装配验证器：parts内id唯一；role可取input；source.basis可取design-assumption，并需note。box的size_mm三轴均在[0.05,500]，center_mm三轴在[-1000,1000]。顶层units=mm，title非空；required_roles/requirements/assumptions/interfaces为列表，energy为对象。这是工作区表示约束，不改变真实CAD物理尺寸。\n');readonly.append('contract-schema.md')
            instruction='现有assembly.json中的真实薄膜厚度小于工作区表示下限。修复工作区装配表示，保持id、role、面内尺寸。禁止改变cad-parameters.json中的真实厚度。写sizing-note.json明确envelope_only=true、actual_thickness_mm、envelope_thickness_mm及physical_verified=false；装配source需说明近似。这里只验表示与来源一致性，不验制造。'
            extra={};reference=json.loads(json.dumps(body));reference['parts'][0]['geometry']['size_mm'][2]=.05
        else:
            (folder/'policy.h').write_text(HEADER);(folder/'policy.c').write_text(BROKEN);readonly.append('policy.h')
            instruction='修复policy.c中的异步事件与发送确认逻辑，保持policy.h不变。enable_energy后且已连接才可请求采样；同一连接epoch仅能有一个pending采样；断连/重连使旧采样失效；无请求的回调不可排队。next_action只能提议发送，成功send_done才增加delivered，失败保留错误并清理发送，重复确认不得重复计数；失败采样可重试。connected与disconnected需推进epoch。P04的BLE/高速采样场景提供任务入口，这份独立声明的C工作流夹具并非作者固件，主机回放不等于目标无线验证。'
            extra={};reference=REFERENCE
        (folder/'TASK.md').write_text(instruction+'\n完成后写report.md记录实际修改与边界。\n')
        task={'id':kind,'kind':kind,'split':split,'paper':paper,'readonly_files':readonly,**extra}
        put_once(folder/'task-input.json',task)
        for arm in ('negative','reference'):
            workspace=root/'no-agent'/kind/arm/'workspace';shutil.copytree(folder,workspace)
            if arm=='reference':
                if kind=='manifest':(workspace/'manifest.json').write_text(json.dumps(reference)+'\n')
                elif kind=='geometry':
                    (workspace/'assembly.json').write_text(json.dumps(reference)+'\n');(workspace/'sizing-note.json').write_text(json.dumps({'envelope_only':True,'actual_thickness_mm':.03,'envelope_thickness_mm':.05,'physical_verified':False})+'\n')
                else:(workspace/'policy.c').write_text(reference)
            result=check_output(kind,folder,workspace,workspace.parent/'check')
            put_once(workspace.parent/'result.json',result)
            if result['status']!=('PASS' if arm=='reference' else 'FAIL'):raise ValueError('LOCAL_REFERENCE_CALIBRATION_FAILED:'+kind+':'+arm)
        out.append(task)
    return out


def prepare(root=DEFAULT_ROOT):
    from . import launcher
    study=Path(root);root=study/'learning/native-generation-v1'
    if (root/'prepared.json').exists():return audit(root)
    root.mkdir(parents=True,exist_ok=True)
    evidence=[]
    for eid,name in [('E01','fault-check-001/result.json'),('E02','delivery-duplicates-review.json')]:
        p=study/'campaign/reviews/P01'/name
        evidence.append({'id':eid,'paper':'P01','source':str(p.relative_to(study)),'sha256':digest(p),'public_facts':read(p)})
    # Locate one known closed owner's interface observations, not all history.
    owner='pi-chat-23f915b7ee4e9fe6';trace=study/'runtime/sessions'/owner/'trace.jsonl'
    observed=[];count=0
    with trace.open() as f:
        for line in f:
            row=json.loads(line)
            if row.get('type')=='tool_execution_start' and row.get('toolName')=='bf_product':count+=1
            if row.get('type')=='tool_execution_end' and row.get('toolName')=='bf_product' and row.get('isError'):
                observed.append({'time':row.get('time'),'tool':'bf_product','observation':str(row.get('result'))[:700]})
    evidence.append({'id':'E03','paper':'P03','source_owner':owner,'trace_sha256':digest(trace),'tool_calls':count,
                     'public_observations':observed[-12:],'scope':'Observed interface failures, no private model reasoning'})
    put_once(root/'experience.json',{'episodes':evidence,'permitted_trials':[e['id'] for e in evidence],
        'preparation_actor':'Codex','facts_actor':'Pi execution / independent checker','candidate_answer_provided':False})
    tasks=make_tasks(root);now=time.time()
    protocol={'schema_version':'bf-native-learning-protocol-v1','id':'native-learning-round2-20261009','model':'deepseek-flash',
        'tasks':tasks,'max_solver_traces':6,'max_candidates':1,'budget_scope':'per-session/task','usd_per_owner':30,
        'started':now,'expires':now+21600,'order':['improver']+[t['id']+'-M0' for t in tasks]+[t['id']+'-M2' for t in tasks],
        'comparison':'Same task, same public historical information, same tools/model/evaluator; independent pass recovery with no regressions required',
        'adoption_boundary':'Local engineering-method fixtures only. No production adoption or statistical/recursive claim.'}
    put_once(root/'protocol.json',protocol)
    harness=launcher.freeze(label='LRSI-native-learning-M0-20261009',home_root=study/'harness-home',app_entry='chat-product.js')
    manifest=verify_method(harness)
    files={str(p.relative_to(root)):digest(p) for p in root.rglob('*') if p.is_file() and p.suffix in {'.json','.md','.c','.h','.txt'}}
    prepared={'schema_version':'bf-native-learning-prepared-v1','harness':str(harness),'harness_identity':manifest['identity'],
        'controller_sha256':digest(__file__),'files':files,'no_agent_reference':'3 references PASS; 3 negative controls FAIL',
        'claim':'New declared local engineering-method round; first round and original paper sessions unchanged'}
    put_once(root/'prepared.json',prepared);return prepared


def audit(root):
    root=Path(root);value=read(root/'prepared.json')
    if digest(__file__)!=value['controller_sha256']:raise ValueError('METHOD_CONTROLLER_CHANGED')
    for path,sha in value['files'].items():
        if digest(root/path)!=sha:raise ValueError('METHOD_INPUT_CHANGED:'+path)
    verify_method(Path(value['harness']));return value


def run(root=DEFAULT_ROOT):
    from . import launcher,provider
    from .server import Workbench,handler
    from .model_profile import ENGINEERING
    study=Path(root);root=study/'learning/native-generation-v1';record=audit(root);protocol=read(root/'protocol.json')
    if time.time()>=protocol['expires']:raise ValueError('METHOD_ROUND_EXPIRED')
    if list((root/'trials').glob('*/attempt.json')):raise ValueError('NO_AUTOMATIC_METHOD_REPLAY')
    runtime=root/'runtime';app=Workbench(runtime/'state');harness=Path(record['harness'])
    with app.store.connect() as db:
        if db.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0]:raise ValueError('METHOD_REQUIRES_NEW_LEDGER')
        db.execute('UPDATE model_limits SET total_usd=210,max_tokens=175000000,expires=? WHERE id=1',(protocol['expires'],))
        db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('model_budget_scope',canonical('per-owner')))
        db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('interactive_default_owner_usd',canonical(30)))
        db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',(protocol['id'],time.time(),protocol['expires'],210,'deepseek-flash',canonical(protocol)))
    original=app.provider.complete
    def guarded(*args,**kwargs):
        audit(root)
        if time.time()>=protocol['expires']:raise ValueError('METHOD_ROUND_EXPIRED')
        with app.store.connect() as db:
            if db.execute("SELECT COUNT(*) FROM model_requests WHERE status='UNKNOWN'").fetchone()[0]:raise ValueError('NEW_UNKNOWN_USAGE_STOP')
        return original(*args,**kwargs)
    app.provider.complete=guarded;base=handler(app)
    class MethodHandler(base):
        def do_POST(self):
            path=urlparse(self.path).path
            if path not in {'/v1/chat/completions','/api/skills','/api/engineering'}:return self.reply(403,{'error':'LOCAL_METHOD_MUTATION_DENIED'})
            if path=='/api/engineering':
                import io
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=64000:return self.reply(400,{'error':'LOCAL_METHOD_SIZE'})
                wire=self.rfile.read(n);body=json.loads(wire)
                if body.get('action')!='skill':return self.reply(403,{'error':'LOCAL_METHOD_SKILL_ONLY'})
                self.rfile=io.BytesIO(wire)
            super().do_POST()
    server=ThreadingHTTPServer(('127.0.0.1',0),MethodHandler)
    threading.Thread(target=server.serve_forever,daemon=True).start();app.conversations.port=server.server_port
    environment=identity({'harness':record['harness_identity'],'controller':digest(__file__),'provider':digest(provider.__file__),
        'profile':ENGINEERING,'protocol':digest(root/'protocol.json'),'guard':'local-native-method-v1'})
    results={};overlay=''
    try:
        for tid in protocol['order']:
            audit(root);task=next((t for t in protocol['tasks'] if tid.startswith(t['id']+'-')),None)
            if tid!='improver' and tid.endswith('-M2') and not overlay:continue
            is_improver=task is None
            text=('读取experience.json和TASK.md，生成一个通用方法候选及report.md。' if is_improver else '实际完成TASK.md指定文件修改，写report.md。')
            prompt=BASE+('\n实际加载的候选方法：\n'+overlay if tid.endswith('-M2') else '')
            def stage(cid):
                workspace=runtime/'participants'/cid;workspace.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/'experience.json',workspace/'experience.json')
                if task:shutil.copytree(root/'public-tasks'/task['id'],workspace,dirs_exist_ok=True)
                else:
                    (workspace/'TASK.md').write_text('你是独立Pi-Improver。依据experience.json中的真实公开故障事实，提出一个可被推翻的通用流程改进。只写candidate.json和report.md。candidate恰含target、instruction、hypothesis、falsifier、applies_to、evidence_trials；target=literature_method_overlay，instruction<=6000字，evidence_trials只可用E01/E02/E03。方法应适用于未知器件/尺寸/接口，不复制本案例答案。不能改模型、工具、评分、预算、原始结果或当前工程，不能自行采用。无合理改进则candidate.json写status=NO_OP与reason。本轮未提供后续对照任务与结果。\n')
                with app.store.connect() as db:
                    db.execute('UPDATE conversations SET harness=?,title=? WHERE id=?',(str(harness),'方法改进 · '+tid,cid))
                    db.execute('INSERT INTO research_model_owners VALUES(?,?,?)',(cid,protocol['id'],tid))
                    db.execute('INSERT INTO owner_model_caps VALUES(?,30)',(cid,))
                    db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('model_profile:'+cid,canonical(ENGINEERING['version'])))
            c=app.conversations.create(text,None,'native-method-'+tid,preflight=stage,defer_dispatch=True);owner=c['id']
            context={'folder_id':protocol['id'],'folder_name':'独立工程方法开发','revision':0,'memory':'','prompt':prompt,
                'tools':['read','write','edit','bash','bf_engineering'],'harness_revision':None}
            app.organization.bind(owner,context);target=root/'trials'/tid
            put_once(target/'attempt.json',{'trial':tid,'owner':owner,'started':time.time(),'kind':'improver' if is_improver else 'solver',
                'task':task,'method_identity':identity({'harness':record['harness_identity'],'base':BASE,'overlay':overlay if tid.endswith('-M2') else ''})})
            done=threading.Event();watch=None
            def ready(proc):
                nonlocal watch
                app.conversations.processes[owner]=proc;app.conversations.state(owner,'RUNNING');app.conversations.drain(owner,proc)
                def observe():
                    while not done.wait(.2):app.conversations.ingest(owner)
                watch=threading.Thread(target=observe,daemon=True);watch.start()
            try:receipt=launcher.launch(harness,None,label=owner,store_root=app.store.root,service_port=server.server_port,home_root=runtime,
                shared_context=context,product=True,on_process=ready)
            finally:
                done.set()
                if watch:watch.join()
                app.conversations.processes.pop(owner,None)
            app.conversations.ingest(owner,execution_state=False)
            if app.conversations.get(owner)['status']=='RUNNING':app.conversations.state(owner,'IDLE' if not receipt.get('exit_code') else 'FAILED')
            workspace=runtime/'participants'/owner;trace=runtime/'sessions'/owner/'trace.jsonl'
            with app.store.connect() as db:
                bills=[dict(x) for x in db.execute('SELECT * FROM model_requests WHERE owner=?',(owner,))]
                wires=[json.loads(x['wire']) for x in db.execute('SELECT wire FROM model_request_evidence WHERE owner=?',(owner,))]
            activated=any(prompt in str(m.get('content','')) for w in wires for m in w.get('messages',[]))
            result={'trial':tid,'kind':'improver' if is_improver else 'solver','owner':owner,'model_calls':len(bills),'budget':owner_budget(bills,owner),
                'method_in_actual_request':activated,'environment_sha256':environment,'process_status':receipt['status'],
                'execution':{k:app.conversations.get(owner).get(k) for k in ('status','error')},
                'trace':str(trace.relative_to(study)),'trace_sha256':digest(trace),'source_files_edited_by_Codex':0,'physical_verified':False}
            if is_improver:
                body=read(workspace/'candidate.json')
                if body.get('status')=='NO_OP':result['candidate_status']='NO_OP'
                else:
                    qualified=qualify_candidate(body,['E01','E02','E03']);overlay=body['instruction']
                    put_once(root/'candidate-02.json',{**qualified,'parent_method':'M0','child_method':'M2','actor':'Pi','owner':owner,
                        'source_sha256':digest(workspace/'candidate.json'),'body':body})
                    result['candidate_status']=qualified['status']
            else:
                result['task_sha256']=identity({p.name:digest(p) for p in (root/'public-tasks'/task['id']).iterdir() if p.is_file()})
                result['evaluation']=check_output(task['kind'],root/'public-tasks'/task['id'],workspace,target/'independent-check')
                if not (workspace/'report.md').is_file():result['evaluation']['problems'].append('REPORT_MISSING')
                if not activated or not bills or any(b['status']!='SETTLED' for b in bills) or result['execution']['status']!='IDLE':
                    result['evaluation']['problems'].append('EXECUTION_OR_USAGE_UNVERIFIED')
                if result['evaluation']['problems']:result['evaluation']['status']='FAIL'
                results[tid]=result
            for name in ('report.md','candidate.json','manifest.json','assembly.json','sizing-note.json','policy.c','policy.h'):
                if (workspace/name).is_file():shutil.copyfile(workspace/name,target/name)
            put_once(target/'result.json',result)
            print(json.dumps({'trial':tid,'evaluation':result.get('evaluation',{}).get('status'),'calls':len(bills),'usd':result['budget']['liability_usd']},ensure_ascii=False),flush=True)
            if not bills or any(b['status']!='SETTLED' for b in bills):raise ValueError('METHOD_USAGE_UNAVAILABLE_STOP')
        if overlay:
            pairs=[{'task':t['id'],'split':t['split'],'parent':results[t['id']+'-M0'],'child':results[t['id']+'-M2']} for t in protocol['tasks']]
            verdict=comparison(pairs);verdict.update(parent_method='M0',candidate_method='M2',paired_tasks=pairs,
                scope='Small public development workflow/C host fixtures only',public_history_equal=True)
        else:verdict={'status':'NO_OP','production_adopted':False,'recursive_self_improvement_claim':False}
        put_once(root/'comparison.json',verdict);return verdict
    finally:
        server.shutdown();server.server_close();app.stop.set();app.thread.join(timeout=3);app.lock.close()
