#!/usr/bin/env python3
"""Finite prospectively registered BF groups; use the existing SDK and provider."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import urllib.request

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[2]
PLAN = ROOT/'docs/research/phase-plan-20261019/phase3'
OUT = Path.home()/'.local/share/bf-phase3-20261020'
HIST = Path.home()/'.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001'
HARNESS = Path.home()/'.local/share/bf-phase1-20261020/a/ar-service/pi-episode-001/harness'
PROFILE = Path.home()/'.local/share/bf-campaign-20261019-s0/profile.json'
sys.path.insert(0, str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.campaign20261019.phase1 import BFPhaseGateway, encoded, digest, file_hash, ledger, output_bytes, seal, tool_definition
from bfworld.agentlab.campaign20261019.phase2 import VARIABLES, design
from bfworld.agentlab.campaign20261019.phase3 import ComparisonStore, ProspectiveHost, checked_design
from jsonschema import ValidationError


def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text())


def configure():
    profile=read(PROFILE)
    for key,value in profile['paths'].items():os.environ['BF_'+key]=value
    os.environ.update(BF_RUNTIME_ROOT=profile['runtime_root'],BF_RUNTIME_CONFIG=profile['configuration'],
                      BF_DEVELOPMENT_PROFILE=str(PROFILE),PI_CODING_AGENT_DIR=str(Path(profile['home'])/'pi-config'),
                      PYTHONDONTWRITEBYTECODE='1')
    return profile


class Gateway(BFPhaseGateway):
    """Wire v2 validation/counters before any valid-proposal budget is charged."""
    def tool(self, body):
        with self.lock:
            self.ready()
            if self.tool_calls >= self.protocol['limits']['tool_calls']:
                raise ValueError('EPISODE_TOOL_LIMIT')
            self.tool_calls += 1
            self.event('tool_started',{'number':self.tool_calls,'input':body})
            try:
                self.validator.validate(body)
                if self.handler.kind=='D' and body['action'] in ('check','submit'):
                    key=digest(checked_design(body['candidate'],self.handler.store.legal(self.handler.world)))
                    if key not in self.candidates and len(self.candidates)>=2:
                        raise ValueError('VALID_D_PROPOSAL_CAP')
                    self.candidates.add(key)
                value=self.handler(body)
                if len(encoded(value))>self.protocol['limits']['tool_response_bytes']:
                    raise ValueError('TOOL_RESPONSE_BOUND')
                self.event('tool_completed',{'number':self.tool_calls,'output':value})
                return value
            except Exception as error:
                syntax=isinstance(error,ValidationError) or str(error)=='V2_ACTION_TYPE_OR_SYNTAX_REJECTED'
                if syntax:
                    self.syntax_rejections=getattr(self,'syntax_rejections',0)+1
                    if self.syntax_rejections>2:
                        self.stop('V3_SYNTAX_REJECTION_CAP')
                self.event('tool_failed',{'number':self.tool_calls,'error':type(error).__name__+': '+str(error)[:1200]})
                raise

    def ready(self, *, paid=False):
        if paid:
            plan=read(PLAN/'protocol.json');db=self.protocol['provider_database']
            all_cost=[ledger(db,read(f)['owner']) for f in (OUT/'episodes').glob('*/owner.json')]
            group=self.protocol['group']
            group_cost=[ledger(db,read(f)['owner']) for f in (OUT/'episodes').glob('*/owner.json')
                        if read(f)['group']==group]
            if any(x['unknown_or_missing_usage'] for x in all_cost):self.stop('GLOBAL_UNKNOWN_USAGE')
            if sum(x['requests'] for x in all_cost)>=plan['maximum_provider_requests']:self.stop('GLOBAL_REQUEST_CAP')
            if sum(x['settled_charge_upper_bound_usd'] for x in all_cost)+.7>plan['maximum_settled_upper_usd']:self.stop('GLOBAL_COST_CAP')
            if sum(x['requests'] for x in group_cost)>=24:self.stop('GROUP_TOTAL_REQUEST_CAP')
            previous=sum(read(f).get('wall_seconds_total',0) for f in (OUT/'episodes').glob('*/episode-result.json')
                         if read(f)['group']==group)
            if previous+time.time()-self.started>=1200:self.stop('GROUP_TOTAL_WALL_CAP')
            all_wall=sum(read(f).get('wall_seconds_total',0) for f in (OUT/'episodes').glob('*/episode-result.json'))
            if all_wall+time.time()-self.started>=plan['maximum_total_episode_wall_s']:self.stop('GLOBAL_WALL_CAP')
            if output_bytes(OUT)>=500_000_000:self.stop('PHASE_OUTPUT_CAP')
            if output_bytes(Path(self.protocol['provider_database']).parents[1])-plan['provider_home_initial_bytes']>=plan['maximum_provider_home_growth_bytes']:
                self.stop('PROVIDER_HOME_GROWTH_CAP')
        return super().ready(paid=paid)


def definition(kind, adapter, limits):
    if kind in ('E5','H'):
        params=adapter.schema(kind)
    else:
        params={'type':'object','additionalProperties':False,'required':['action'],
                'properties':{'action':{'enum':['inspect','sources','acquire','check','submit']},
                              'source_id':{'type':'string'},'reason':{'type':'string','maxLength':4000},
                              'candidate':{'type':'object','additionalProperties':False,
                                  'required':list(VARIABLES),
                                   'properties':{k:{'type':'number','minimum':v[0],'maximum':v[1]} for k,v in limits.items()}}},
                'allOf':[{'if':{'properties':{'action':{'enum':['check','submit']}}},'then':{'required':['candidate']}},
                         {'if':{'properties':{'action':{'const':'acquire'}}},'then':{'required':['source_id']}}]}
    return tool_definition('bf_phase3','Read the registered BF task and source facts; propose only the permitted artifact. Tools return observed facts. Submit once. Qualification and final independent service remain host-side.',params)


def run_episode(spec):
    started=time.monotonic()
    state=read(PLAN.parent/'phase-state.json')
    if state['current_phase']!=3 or not state.get('paid_dispatch_allowed'):
        raise ValueError('PHASE3_NOT_ENABLED')
    slots=read(PLAN/'idle-slots.json')
    if time.time()-slots['observed_unix']>3600 or any(slots[x]!='idle' for x in ('A','B')):
        raise ValueError('WORKER_IDLE_LEASE_REQUIRED')
    if shutil.disk_usage(ROOT).free<10_900_000_000:raise ValueError('STORAGE_RESERVE')
    profile=configure();database=Path(profile['home'])/'state/workbench.sqlite'
    root=OUT/'episodes'/spec['id']
    if root.exists():raise FileExistsError('SEALED_ATTEMPT_NO_AUTOMATIC_RETRY')
    plan=read(PLAN/'protocol.json')
    if spec not in plan['episodes']:raise ValueError('UNREGISTERED_EPISODE')
    if spec['stage']=='formal':
        selection=read(PLAN/'formal-repeat-freeze.json')
        if spec['replicate']>selection['formal_repetitions']:raise ValueError('FORMAL_REPLICATE_NOT_ENABLED')
    prior_group=[read(f) for f in (OUT/'episodes').glob('*/episode-result.json') if read(f)['group']==spec['group']]
    requests=24-sum(x['accounting']['requests'] for x in prior_group)
    wall=1200-sum(x['wall_seconds_total'] for x in prior_group)
    if spec['kind']=='H':requests=min(requests,8);wall=min(wall,400)
    prior_tools=sum(1 for f in (OUT/'episodes').glob('*/owner.json') if read(f)['group']==spec['group']
                    for line in ((f.parent/'gateway/gateway-events.jsonl').read_text().splitlines()
                                 if (f.parent/'gateway/gateway-events.jsonl').exists() else [])
                    if json.loads(line)['kind']=='tool_started')
    if prior_tools>=40:raise ValueError('GROUP_TOOL_BUDGET_EXHAUSTED')
    if requests<1 or wall<=0:raise ValueError('GROUP_BUDGET_EXHAUSTED')
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        prior={row['id']:digest(dict(row)) for row in db.execute('SELECT * FROM model_requests')}
        if db.execute("SELECT count(*) FROM model_requests WHERE status NOT IN ('SETTLED','NOT_SENT')").fetchone()[0]:
            raise ValueError('PRIOR_USAGE_UNRESOLVED')
    adapter=load_module('registered_v2_adapter',PLAN.parent/'phase2/dispatch_adapter_v2.py')
    task_registry=read(APP/'configs/studies/phase3-20261020/shared/tasks.json')
    tool=definition(spec['kind'],adapter,task_registry['tasks'][spec['world']]['legal_design_ranges'])
    goal=('用sources读取任务和提案schema，实际acquire来源，自行提出并submit一个有来源/单位/适用域的观察spec及typed条件design policy。selection或construction均可，禁止研究者预填答案。路径使用JSON Pointer，例如/field_name。最多一个有效观察提案，语法错误单列最多2。真实资格和消费者在本实时调用执行。'
          if spec['kind']=='E5' else
          '用inspect和实际acquire的BF来源，从保留的失败提出并submit一个changed_artifact=H的可重新执行方法、假设及反证；可合法no-update。本H接口没有D check，不能把D修改当H。最多一个有效H提案，语法错误单列最多2。'
          if spec['kind']=='H' else
          '从inspect的固定BF任务入口，实际取得来源，选择两个合法D字段，使用check并submit最终candidate。目标是截止前一个有效8字节帧且无重复。最多两个不同设计，所有检查含最终确认计入同组总预算。不得改变供能、状态、初态或判据。')
    instruction='有限public-development前瞻试验，fresh session，最终必须submit。无bash/文件/原生权限。无自动重试；未知/失败/no-update保留。不得声称硬件、统计优势、迁移或RSI。'
    method_source=None
    if spec.get('method_episode'):
        method_source=OUT/'episodes'/spec['method_episode']/'scientific/submission.json'
        if not method_source.exists():
            method_source=OUT/'episodes'/spec['method_episode']/'episode-result.json'
            if not method_source.exists():raise ValueError('H_EPISODE_NOT_COMPLETED')
            proposed={'decision':'no-update'}
        else:proposed=read(method_source)['proposal']
        instruction+='\n实际改进者的方法（尚未证明收益）：\n'+proposed.get('method_text','NO_UPDATE: use the fixed baseline procedure.')
    condition_instructions=read(APP/'configs/studies/phase3-20261020/shared/instructions.json')
    instruction+='\n'+condition_instructions[spec['condition']]['proposal' if spec['kind']=='H' else 'design']
    service='http://127.0.0.1:8980'
    operator=(Path(profile['home'])/'state/operator.token').read_text().strip()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api(path,body):
        req=urllib.request.Request(service+path,data=encoded(body),headers={'Authorization':'Bearer '+operator,'Content-Type':'application/json'})
        with opener.open(req,timeout=30) as response:return json.load(response)
    root.mkdir(parents=True)
    owner=api('/api/conversations',{'text':goal,'operation_id':spec['id'],'defer_dispatch':True})['id']
    seal(root/'owner.json',{'episode':spec['id'],'owner':owner,'group':spec['group'],'fresh_model_context':True})
    authority=api('/api/design-lab',{'action':'method_authorize','session_id':owner,'task_id':'method-study-'+spec['id'],
                                  'wall_authorization_text':'持续运行 不设置时间限制','model_profile':'engineering-reasoning-compact-v2'})
    token=authority.pop('participant_token');seal(root/'authority.json',authority)
    built=read(HARNESS/'manifest.json')
    if file_hash(HARNESS/'dist/phase1/episode.js')!=built['compiled_sha256']:raise ValueError('SDK_IDENTITY_DRIFT')
    paths=[Path(__file__),APP/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase3.py',
           APP/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase1.py',
           APP/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase2.py',
           APP/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase2_discovery.py',
           APP/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase2_methods.py',
           APP/'scripts/campaign_phase1.py',APP/'scripts/campaign_reference.py',
           PLAN.parent/'phase2/dispatch_adapter_v2.py',PLAN/'protocol.json',OUT/'initial-cache.json',
           APP/'configs/studies/phase3-20261020/shared/tasks.json',
           APP/'configs/studies/phase3-20261020/shared/instructions.json',PROFILE,HIST/'seal.json',
           HARNESS/'manifest.json',HARNESS/'dist/phase1/episode.js']
    paths.extend([APP/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase3_interfaces.py',
                  APP/'configs/studies/phase3-20261020/methods/conditions.json',
                  APP/'configs/studies/phase3-20261020/interfaces/conditions.json',
                  APP/'configs/studies/phase3-20261020/interfaces/derived-case.json'])
    paths.extend(APP/f for f in read(APP/'configs/studies/phase2-20261020/shared/case-registry.json')['frozen_scientific_files'])
    if method_source:paths.append(method_source)
    p={'schema_version':'bf-phase3-prospective-episode-v1','id':spec['id'],'group':spec['group'],
       'mode':'public-development','baseline':plan['id'],'owner':owner,'spec':spec,'goal':goal,'instruction':instruction,
       'tool':tool,'harness':str(HARNESS),'output_root':str(root),'provider_service':service,'provider_database':str(database),
       'allowed_reported_models':['deepseek-flash'],'identity_scope':'Provider alias only; independent weights version UNKNOWN',
       'initial_cache_sha256':file_hash(OUT/'initial-cache.json'),
       'bound_files':{str(f):file_hash(f) for f in paths},'candidate_fields':[], 'candidate_actions':[],
       'limits':{'model_requests':requests,'wall_seconds':wall,'candidates':2,'reserve_bytes':10_000_000_000,
                  'peak_remaining_bytes':900_000_000,'output_bytes':100_000_000,'tool_calls':40-prior_tools,
                 'tool_response_bytes':96_000,'model_request_bytes':2_000_000,'model_response_bytes':64_000_000,
                 'max_output_tokens':32768},'automatic_retry':False,'native_dispatches':0}
    seal(root/'protocol.json',p)
    lease=root/'slot-lease.json';seal(lease,{'status':'GRANTED','episode':spec['id'],'expires':time.time()+wall,
                                          'holders':['S0','Pi'],'other_executor_status':'idle'})
    runner=load_module('phase3_existing_sdk',APP/'scripts/campaign_phase1.py')
    store=ComparisonStore(APP,OUT,HIST,OUT/'initial-cache.json',spec['group'])
    gateway=None
    result={'episode':spec['id'],'group':spec['group'],'spec':spec,'owner':owner,'status':'START_FAILURE',
            'initial_cache_sha256':p['initial_cache_sha256'],'protocol_sha256':digest(p)}
    try:
        host=ProspectiveHost(root/'scientific',store,spec['world'],spec['kind'],adapter,
                             condition=spec['condition'],tool=tool)
        gateway=Gateway(p,root/'gateway',host,provider_token=token,lease_path=lease)
        result.update(runner.invoke(root,HARNESS,{'workspace':str(root/'participant'),'service':gateway.start(),
                      'token':gateway.token,'owner':owner,'goal':goal,'instruction':instruction,
                      'episodeId':spec['id'],'tool':tool},timeout=wall))
    except Exception as error:
        result['error']=type(error).__name__+': '+str(error)[:1500]
    finally:
        if gateway:gateway.close()
        token=None
        result['wall_seconds_total']=time.monotonic()-started
        account=ledger(database,owner);seal(root/'provider-costs.json',account)
        result['accounting']={k:v for k,v in account.items() if k!='rows'}
    try:
        result['trace_audit']=runner.audit_participant(root,tool['name'])
        loaded=[json.loads(line) for line in (root/'pi-public-trace.jsonl').read_text().splitlines()]
        loaded=[x for x in loaded if x.get('type')=='bf_episode_loaded']
        result['fresh_task_entry']=len(loaded)==1 and loaded[0].get('resume_messages')==0
        result['reported_models']=sorted(gateway.models_seen) if gateway else []
        accepted=(result.get('exit_code')==0 and (root/'scientific/submission.json').exists()
                  and result['trace_audit']['model_submitted'] and result['fresh_task_entry']
                  and not account['unknown_or_missing_usage'] and result['reported_models'] and not gateway.stopped)
        result['status']='ACTUAL_PROSPECTIVE_SUBMITTED' if accepted else 'INCOMPLETE_OR_STOPPED'
        if accepted:
            value=read(root/'scientific/submission.json')
            result['external_result']=({'method':value['proposal'],'retained':'PENDING_FRESH_DESIGN'} if spec['kind']=='H'
                                      else {'execution':value['execution'],'prospective_E5_consumer':spec['kind']=='E5'})
    except Exception as error:
        result['status']='TRACE_AUDIT_FAILED';result['trace_error']=str(error)
    seal(root/'episode-result.json',result)
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;current={row['id']:digest(dict(row)) for row in db.execute('SELECT * FROM model_requests')}
    preserved=all(current.get(k)==v for k,v in prior.items())
    seal(root/'protected-ledger-readback.json',{'old_rows':len(prior),'old_unchanged':preserved,'new_rows':len(current)-len(prior)})
    if not preserved or account['unknown_or_missing_usage']:raise ValueError('PRESERVATION_OR_ACCOUNTING_GATE')
    print(json.dumps({'episode':spec['id'],'status':result['status'],'requests':account['requests'],
                      'service':result.get('external_result',{}).get('execution',{}).get('complete_service'),
                      'wall_s':result['wall_seconds_total']},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode',help='Exact registered prospective episode ID')
    args=parser.parse_args();specs=read(PLAN/'protocol.json')['episodes']
    run_episode(next(x for x in specs if x['id']==args.episode))
