#!/usr/bin/env python3
"""Four finite fresh Pi episodes; no environments, retries or native dispatch."""
import argparse
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import threading
import time
import urllib.request

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[2]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.campaign20261019.phase2 import (
    BASELINE, CaseStore, VARIABLES, authoritative_consume, design,
)
from bfworld.agentlab.campaign20261019.phase1 import (
    BFPhaseGateway, digest, encoded, file_hash, ledger, output_bytes, seal, tool_definition,
)

OUT = Path('/Users/depengsu/.local/share/bf-phase2-20261020')
PLAN = ROOT / 'docs/research/phase-plan-20261019/phase2'
HIST = Path('/Users/depengsu/.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001')
PROFILE = Path('/Users/depengsu/.local/share/bf-campaign-20261019-s0/profile.json')
HARNESS = Path('/Users/depengsu/.local/share/bf-phase1-20261020/a/ar-service/pi-episode-001/harness')
EPISODES = {'p2-e5-001': (24, 1200, 1), 'p2-h-proposal-001': (12, 600, 1),
            'p2-h0-design-001': (24, 1200, 2), 'p2-hprime-design-001': (24, 1200, 2)}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def store():
    return CaseStore(APP, OUT / 'cases', HIST)


def module(kind):
    return __import__('bfworld.agentlab.campaign20261019.phase2_' + kind, fromlist=['*'])


class Host:
    def __init__(self, episode, root):
        self.episode, self.root = episode, Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = store()
        self.acquired = {}
        t = self.store.task('b-volatile-reset')
        self.current = {k: t['device'][k] for k in VARIABLES}

    def inspect(self):
        t = self.store.task('b-volatile-reset')
        data = {'baseline': BASELINE, 'partition': 'public-development',
            'service': {'event_time_s': t['event_s'], 'receive_deadline_s': t['deadline_s'],
                        'application_bytes': 8, 'unique_valid_frames': 1},
            'current_design': self.current, 'legal_design_ranges': VARIABLES,
            'sources': ['component_record', 'excitation_record', 'saved_activity'],
            'current_measurement': {'first_boot_s': .0027, 'received_frames': 0},
            'scope': 'Frozen ideal model only; physical calibration UNKNOWN'}
        if self.episode == 'p2-e5-001':
            data['proposal_tool_schema'] = module('discovery').tool_schema()
            data['consumer_policy_format'] = [{'equals': '<typed observed value>',
                                               'design': {'capacitance_f': '<number>', 'tx_not_before_s': '<number>'}}]
        elif self.episode == 'p2-h-proposal-001':
            data['proposal_tool_schema'] = module('methods').tool_schema()
            data['retained_failures'] = {
                'current_b_run': {'received_frames': 0, 'start_voltage_v': 0, 'deadline_s': .1},
                'ar_product': {'fixed_space': 'NO_GO', 'strict_FIFO': 'FAIL', 'product': 'NOT_ACCEPTED'},
                'history_scope': 'Public old failed BF cases, not heldout evaluation'}
        return data

    def __call__(self, body):
        action = body['action']
        if action in ('inspect', 'sources'):
            return self.inspect()
        if action == 'acquire':
            if body['source_id'] in self.acquired:
                return {k:v for k,v in self.acquired[body['source_id']].items() if k!='parent_path'}
            item = self.store.source(body['source_id'])
            self.acquired[body['source_id']] = item
            seal(self.root / 'acquisitions' / (body['source_id'] + '.json'), item)
            return {k:v for k,v in item.items() if k!='parent_path'}
        if self.episode == 'p2-e5-001' and action in ('propose', 'submit'):
            proposal = module('discovery').validate_proposal(body['spec'])
            # Domain, typed value and service are independently qualified after submit.
            if proposal['source_id'] not in self.acquired:
                raise ValueError('SOURCE_MUST_BE_ACTUALLY_ACQUIRED')
            policy = body['policy']
            from bfworld.agentlab.campaign20261019.phase2 import consume
            consume(None, policy, self.current)
            submission = {'proposal': proposal, 'policy': policy,
                'acquisition': self.acquired[proposal['source_id']], 'actor': 'actual-pi-participant'}
        elif self.episode == 'p2-h-proposal-001' and action in ('propose', 'submit'):
            proposal = module('methods').validate_method(body['proposal'])
            submission = {'proposal': proposal, 'raw_proposal':body['proposal'], 'actor': 'actual-pi-improver'}
        elif self.episode in ('p2-h0-design-001', 'p2-hprime-design-001') and action in ('check', 'submit'):
            candidate = design(body['candidate'])
            result = self.store.execute('b-volatile-reset', candidate)
            public = {'design': candidate, 'input_sha256': result['input_sha256'],
                'execution_key': result['execution_key'], 'full_feedback_response': True,
                'received_frames': result['reference']['received_frames'],
                'first_receive_s': result['reference']['first_receive_s'],
                'transient_failed_steps': result['reference']['transient_failed_steps'],
                'energy_debits_j': result['energy']['totals_j'],
                'physical_calibration': 'UNKNOWN', 'exact_input_cache_reused': result['reused']}
            seal(self.root / 'candidate-results' / (digest(candidate) + '.json'), {k:v for k,v in public.items() if k != 'exact_input_cache_reused'})
            if action == 'check':
                return public
            submission = {'candidate': candidate, 'execution_key': result['execution_key'],
                          'actor': 'actual-pi-designer'}
        else:
            raise ValueError('ACTION_NOT_AVAILABLE_IN_THIS_EPISODE')
        if action == 'submit':
            submission['reason'] = body.get('reason', '')
            seal(self.root / 'submission.json', submission)
        else:
            seal(self.root / 'proposal.json', submission)
        return {'proposal_sha256': digest(submission), 'saved': action,
                'qualification': 'REQUIRES_EXTERNAL_EVALUATION', 'service_pass': 'NOT_DECLARED'}


def definition(episode):
    if episode=='p2-e5-001':
        return tool_definition('bf_phase2', 'Read the fixed BF task with sources, acquire an actual source, then propose or submit one observation spec and conditional design policy. Selection and bounded AST construction are distinct modes. Final provenance, units, domain and service qualification are external.', module('discovery').tool_schema())
    props = {'action': {'enum': ['inspect', 'sources', 'acquire', 'propose', 'check', 'submit']},
             'source_id': {'type': 'string'}, 'reason': {'type': 'string', 'maxLength': 4000}}
    if episode in ('p2-e5-001', 'p2-h-proposal-001'):
        props['proposal'] = {'type': 'object'}
    if episode == 'p2-e5-001':
        props['policy'] = {'type': 'array', 'minItems': 1, 'maxItems': 3,
            'items': {'type': 'object', 'properties': {'equals': {}, 'design': {'type': 'object'}},
                      'required': ['equals', 'design'], 'additionalProperties': False}}
    if episode in ('p2-h0-design-001', 'p2-hprime-design-001'):
        props['candidate'] = {'type': 'object', 'properties': {k: {'type':'number', 'minimum':v[0], 'maximum':v[1]} for k,v in VARIABLES.items()},
                              'required': list(VARIABLES), 'additionalProperties': False}
    return tool_definition('bf_phase2', 'Read fixed BF task and source facts, acquire a source, and submit a bounded proposal or legal design. inspect returns the relevant proposal format. Tools return observations; final qualification is external.',
        {'type': 'object', 'properties': props, 'required': ['action'], 'additionalProperties': False})


def configure():
    profile = json.loads(PROFILE.read_text())
    for k,v in profile['paths'].items(): os.environ['BF_' + k] = v
    os.environ.update(BF_RUNTIME_ROOT=profile['runtime_root'], BF_RUNTIME_CONFIG=profile['configuration'],
        BF_DEVELOPMENT_PROFILE=str(PROFILE), PI_CODING_AGENT_DIR=str(Path(profile['home'])/'pi-config'),
        PYTHONDONTWRITEBYTECODE='1')
    return profile


def smoke(identity):
    """Real SDK/new host/source round trip, mock provider, no scientific run."""
    configure()
    root = OUT / identity
    if root.exists():
        raise FileExistsError('SOFTWARE_REHEARSAL_ALREADY_EXISTS')
    root.mkdir()
    dbpath = root/'fixture-ledger.sqlite'
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE model_requests(id TEXT,owner TEXT,created REAL,status TEXT,'
                   'reserved REAL,charged REAL,usage TEXT,response_hash TEXT,error TEXT)')
    requests = []
    tool = definition('p2-e5-001')
    call = {'action':'acquire','source_id':'component_record'}
    class Fake(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(payload);n=len(requests)
            usage={'prompt_tokens':2,'completion_tokens':1,'total_tokens':3,
                   'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':2}
            with sqlite3.connect(dbpath) as db:
                db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?)',
                    ('fixture-'+str(n),'fixture-phase2',time.time(),'SETTLED',0,0,json.dumps(usage),'mock',None))
            delta=({'role':'assistant','tool_calls':[{'index':0,'id':'fixture-source','type':'function',
                    'function':{'name':tool['name'],'arguments':encoded(call).decode()}}]} if n==1
                    else {'role':'assistant','content':'MOCK source receipt consumed; no paid experiment.'})
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            for item in [{'id':'fixture','model':'deepseek-flash','choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                         {'id':'fixture','model':'deepseek-flash','choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if n==1 else 'stop'}],'usage':usage}]:
                self.wfile.write(b'data: '+encoded(item)+b'\n\n')
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    mock=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fake)
    thread=threading.Thread(target=mock.serve_forever,daemon=True);thread.start()
    p={'id':'phase2-sdk-software-qualification','mode':'fixture','owner':'fixture-phase2','tool':tool,
       'provider_database':str(dbpath),'provider_service':'http://127.0.0.1:'+str(mock.server_port),
       'allowed_reported_models':['deepseek-flash'],'output_root':str(root),
       'bound_files':{str(Path(__file__)):file_hash(Path(__file__))},
       'candidate_fields':['proposal','policy'],'candidate_actions':['propose','submit'],
       'limits':{'model_requests':3,'candidates':1,'wall_seconds':60,'reserve_bytes':0,
                 'peak_remaining_bytes':0,'output_bytes':5_000_000,'tool_calls':5,
                 'tool_response_bytes':96_000,'model_request_bytes':2_000_000,
                 'model_response_bytes':64_000_000,'max_output_tokens':32768}}
    lease=root/'fixture-lease.json';seal(lease,{'status':'GRANTED','episode':p['id'],
        'expires':time.time()+60,'holders':['S0','Pi'],'other_executor_status':'idle'})
    gateway=BFPhaseGateway(p,root/'gateway',Host('p2-e5-001',root/'scientific'),
                           provider_token='fixture-only',lease_path=lease)
    runner=load('phase2_mock_existing_sdk',APP/'scripts/campaign_phase1.py')
    try:
        result=runner.invoke(root,HARNESS,{'workspace':str(root/'participant'),'service':gateway.start(),
            'token':gateway.token,'owner':p['owner'],'goal':'Exercise the new source tool once.',
            'instruction':'MOCK SOFTWARE QUALIFICATION ONLY. No research result.',
            'episodeId':p['id'],'tool':tool},timeout=45)
    finally:
        gateway.close();mock.shutdown();mock.server_close();thread.join(timeout=2)
    source=json.loads((root/'scientific/acquisitions/component_record.json').read_text())
    consumed=len(requests)==2 and source['source_sha256'] in json.dumps(requests[1])
    audit=runner.audit_participant(root,tool['name'])
    result.update(status='PASS' if result['exit_code']==0 and consumed and audit['executed_inputs']==1 else 'FAIL',
        real_sdk=True,mock_provider=True,source_consumed_in_next_request=consumed,trace_audit=audit,
        paid_model_requests=0,native_calls=0,new_scientific_executions=0)
    seal(root/'mock-requests.json',requests);seal(root/'result.json',result)
    print(json.dumps(result))
    return 0 if result['status']=='PASS' else 1


class GlobalGateway(BFPhaseGateway):
    def ready(self, *, paid=False):
        p = self.protocol
        start = json.loads((OUT / 'dispatch-baseline.json').read_text())
        if output_bytes(OUT) + max(0, output_bytes(Path(start['provider_home'])) - start['provider_home_bytes']) >= 500_000_000:
            self.stop('GLOBAL_STORAGE_GROWTH_CAP')
        if paid:
            accounts = [ledger(p['provider_database'], json.loads(f.read_text())['owner']) for f in OUT.glob('p2-*/owner.json')]
            if any(a['unknown_or_missing_usage'] for a in accounts):
                self.stop('GLOBAL_PROVIDER_USAGE_UNAVAILABLE')
            if sum(a['requests'] for a in accounts) >= 84:
                self.stop('GLOBAL_PROVIDER_REQUEST_CAP')
            if sum(a['settled_charge_upper_bound_usd'] for a in accounts) + .7 > 20:
                self.stop('GLOBAL_USD_UPPER_BOUND_CAP')
            elapsed = sum(json.loads(f.read_text()).get('wall_seconds_total', 0) for f in OUT.glob('p2-*/episode-result.json'))
            if elapsed + time.time() - self.started >= 4200:
                self.stop('GLOBAL_EPISODE_WALL_CAP')
        return super().ready(paid=paid)


def run(episode):
    if episode not in EPISODES:
        raise ValueError('UNREGISTERED_EPISODE')
    state=json.loads((PLAN.parent/'phase-state.json').read_text())
    if state['current_phase']!=2 or not state.get('paid_dispatch_allowed') or state.get('next_execution')!=episode:
        raise ValueError('THIS_FINITE_EPISODE_NOT_ENABLED_BY_COORDINATOR')
    if json.loads((OUT/'sdk-qualification-002/result.json').read_text())['status']!='PASS':
        raise ValueError('QUALIFIED_SDK_PATH_REQUIRED')
    target = OUT / episode
    if target.exists():
        raise FileExistsError('EXISTING_EPISODE_NO_AUTOMATIC_RETRY_OR_RESAMPLING')
    slots = json.loads((PLAN / 'idle-slots.json').read_text())
    active = [k for k in ('A','B') if slots[k]['status'] == 'active']
    if (time.time() - slots['observed_unix'] > 300 or len(active) > 1
            or any(slots[k]['status'] not in ('active','idle') for k in ('A','B'))
            or episode == 'p2-e5-001' and slots['B']['status'] != 'idle'
            or episode != 'p2-e5-001' and active):
        raise ValueError('FRESH_WORKER_IDLE_SNAPSHOT_REQUIRED')
    if shutil.disk_usage(OUT).free < 10_900_000_000:
        raise ValueError('WHOLE_PHASE_RESERVE_REQUIRED')
    profile = configure()
    database = Path(profile['home'])/'state/workbench.sqlite'
    with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory=sqlite3.Row
        prior={r['id']:digest(dict(r)) for r in db.execute('SELECT * FROM model_requests ORDER BY created,rowid')}
        unresolved=db.execute("SELECT count(*) FROM model_requests WHERE status NOT IN ('SETTLED','NOT_SENT')").fetchone()[0]
        if unresolved: raise ValueError('PRIOR_USAGE_UNRESOLVED')
    if not (OUT/'dispatch-baseline.json').exists():
        seal(OUT/'dispatch-baseline.json', {'provider_home':profile['home'],
            'provider_home_bytes':output_bytes(Path(profile['home'])), 'prior_ledger':prior,
            'maximum_charge_upper_bound_usd':20,'request_cap':84,'wall_cap_s':4200,
            'qualified_sdk':str(HARNESS/'manifest.json'), 'no_new_environment':True})
    goal = '用 sources 读取 BF 任务和来源，自行提出并提交一个有来源、单位、适用域的观察 spec，以及消费该观察的条件设计表 policy。条件表每项为 equals 和 design，design仅含两个合法设计变量。观察必须来自实际 acquire 的源。不要把人写表达式或自签资格当自主发现。最多一个不同观察提案；最终以 submit 保存 spec 和 policy。'
    if episode == 'p2-h-proposal-001':
        goal = '读取保留的 BF 失败和原始来源，提出并 submit 一个可从任务入口重新执行的通用 H 方法。你提出 method_text、hypothesis、falsifier 与 changed_artifact=H。不要把单个 D 参数修改当方法，也可提交合法 no-update。方法最终保留或拒绝由新的设计执行与外部服务决定。最多一个不同方法提案。'
    elif episode in ('p2-h0-design-001', 'p2-hprime-design-001'):
        goal = '从任务入口读取固定 BF 任务和所有可用来源，选择合法的两个 D 参数，实际 check，再 submit 最终 candidate 与简洁理由。目标是截止前一个有效8字节应用帧且无重复。最多两个不同候选；不能改供能、事件、初态、器件其他字段或判据。'
    instruction = '这是一个有限 public-development episode，使用 fresh session，禁止重试。inspect 读取任务与提案格式；acquire(source_id) 获取源内容。工具无 bash/文件/原生能力。资格与服务最终判据在外部。必须使用 submit；失败、未知、无更新均保留。不要宣称硬件、统计优势、迁移或 RSI。'
    if episode=='p2-e5-001':
        instruction=instruction.replace('inspect 读取任务与提案格式','sources 读取任务与提案格式')
    if episode == 'p2-hprime-design-001':
        method = json.loads((OUT/'p2-h-proposal-001/external/method.json').read_text())
        if method['status'] != 'ELIGIBLE_H_PROPOSAL': raise ValueError('NO_QUALIFIED_H_PRIME')
        instruction += '\n本条件使用的 H 方法（来自实际改进者，尚未证明有收益）：\n' + method['method_text']
    service='http://127.0.0.1:8980'
    operator=(Path(profile['home'])/'state/operator.token').read_text().strip()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api(path,body):
        req=urllib.request.Request(service+path,data=encoded(body),headers={'Authorization':'Bearer '+operator,'Content-Type':'application/json'})
        with opener.open(req,timeout=30) as response: return json.load(response)
    target.mkdir()
    owner=api('/api/conversations',{'text':goal,'operation_id':episode,'defer_dispatch':True})['id']
    seal(target/'owner.json',{'episode':episode,'owner':owner,'fresh_model_context':True,'old_owner_replacement':False})
    authority=api('/api/design-lab',{'action':'method_authorize','session_id':owner,'task_id':'method-study-'+episode,
        'wall_authorization_text':'持续运行 不设置时间限制','model_profile':'engineering-reasoning-compact-v2'})
    token=authority.pop('participant_token'); seal(target/'authority.json',authority)
    built=json.loads((HARNESS/'manifest.json').read_text())
    if file_hash(HARNESS/'dist/phase1/episode.js') != built['compiled_sha256']:
        raise ValueError('QUALIFIED_SDK_COMPILED_INPUT_DRIFT')
    paths=[Path(__file__),APP/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase2.py',
        APP/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase1.py',APP/'scripts/campaign_phase1.py',
        APP/'scripts/campaign_reference.py',APP/'configs/studies/phase2-20261020/shared/case-registry.json',
        APP/'configs/studies/phase2-20261020/shared/static-rich-baseline.json',
        PROFILE,HIST/'seal.json',HARNESS/'dist/phase1/episode.js',HARNESS/'src/phase1/episode.ts']
    paths += [APP/'packages/python/bfworld/src/bfworld/agentlab/provider.py',
              APP/'packages/python/bfworld/src/bfworld/agentlab/model_profile.py',
              APP.parent/'pi-bf-aiot/package-lock.json']
    paths += [APP/x for x in store().registry['frozen_scientific_files']]
    if episode in ('p2-e5-001','p2-h-proposal-001'):
        paths.append(APP/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019'/('phase2_discovery.py' if episode=='p2-e5-001' else 'phase2_methods.py'))
    if episode=='p2-hprime-design-001': paths.append(OUT/'p2-h-proposal-001/external/method.json')
    requests,wall,candidates=EPISODES[episode]
    p={'schema_version':'bf-phase2-finite-actual-episode-v1','id':episode,'mode':'public-development','baseline':BASELINE,
       'owner':owner,'goal':goal,'instruction':instruction,'tool':definition(episode),
       'harness':str(HARNESS),'output_root':str(target),'provider_service':service,'provider_database':str(database),
       'allowed_reported_models':['deepseek-flash'],'identity_scope':'Provider-reported alias; no independent weights pin',
       'bound_files':{**{str(x):file_hash(x) for x in paths},**built['sdk_runtime_files']},
       'candidate_fields':(['spec','policy'] if episode=='p2-e5-001' else ['proposal'] if episode=='p2-h-proposal-001' else ['candidate']),
       'candidate_actions':['propose','check','submit'],
       'limits':{'model_requests':requests,'wall_seconds':wall,'candidates':candidates,'reserve_bytes':10_000_000_000,
           'peak_remaining_bytes':900_000_000,'output_bytes':100_000_000,'tool_calls':40,'tool_response_bytes':96_000,
           'model_request_bytes':2_000_000,'model_response_bytes':64_000_000,'max_output_tokens':32768},
       'automatic_retry':False,'native_dispatches':0,'unpriced_nonzero_codex_assistance':True}
    protocol=target/'protocol.json';seal(protocol,p)
    lease=target/'slot-lease.json';seal(lease,{'status':'GRANTED','episode':episode,'expires':time.time()+wall,
        'holders':['S0',*active,'Pi'],'other_executor_status':'idle','worker_snapshot':slots})
    runner=load('phase2_existing_sdk_runner',APP/'scripts/campaign_phase1.py');runner.verify(protocol)
    started=time.monotonic();gateway=None
    result={'episode':episode,'owner':owner,'protocol_sha256':digest(p),'status':'START_FAILURE',
            'automatic_retry':False,'native_dispatches':0}
    try:
        gateway=GlobalGateway(p,target/'gateway',Host(episode,target/'scientific'),provider_token=token,lease_path=lease)
        result.update(runner.invoke(target,HARNESS,{'workspace':str(target/'participant'),'service':gateway.start(),
            'token':gateway.token,'owner':owner,'goal':goal,'instruction':instruction,'episodeId':episode,'tool':p['tool']},timeout=wall))
    except Exception as error:
        result['error']=type(error).__name__+': '+str(error)[:1500]
    finally:
        if gateway: gateway.close()
        token=None
        result['wall_seconds_total']=time.monotonic()-started
        account=ledger(database,owner);seal(target/'provider-costs.json',account)
        result['accounting']={k:v for k,v in account.items() if k!='rows'}
    try:
        result['trace_audit']=runner.audit_participant(target,p['tool']['name'])
        result['reported_models']=sorted(gateway.models_seen) if gateway else []
        result['status']='PARTICIPANT_SUBMITTED_REQUIRES_EXTERNAL_EVALUATION' if result.get('exit_code')==0 and (target/'scientific/submission.json').exists() and result['trace_audit']['model_submitted'] and not account['unknown_or_missing_usage'] and result['reported_models'] and not gateway.stopped else 'INCOMPLETE_OR_STOPPED'
    except Exception as error:
        result['trace_error']=str(error);result['status']='TRACE_AUDIT_FAILED'
    seal(target/'episode-result.json',result)
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        current={r['id']:digest(dict(r)) for r in db.execute('SELECT * FROM model_requests')}
    preserved=all(current.get(k)==v for k,v in prior.items())
    seal(target/'protected-ledger-readback.json',{'old_rows':len(prior),'old_unchanged':preserved,'new_rows':len(current)-len(prior)})
    if not preserved: raise ValueError('PROTECTED_BILLING_ROW_CHANGED')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status'].startswith('PARTICIPANT_SUBMITTED') else 1


def evaluate(episode):
    target=OUT/episode
    run_result=json.loads((target/'episode-result.json').read_text())
    if not run_result['status'].startswith('PARTICIPANT_SUBMITTED'):
        raise ValueError('NO_AUDITED_PARTICIPANT_SUBMISSION')
    value=json.loads((target/'scientific/submission.json').read_text())
    external=target/'external'
    trace = [json.loads(line) for line in (target/'pi-public-trace.jsonl').read_text().splitlines()]
    loaded = [x for x in trace if x.get('type')=='bf_episode_loaded']
    if len(loaded)!=1 or loaded[0].get('resume_messages')!=0:
        raise ValueError('FRESH_TASK_ENTRY_NOT_PROVEN')
    actual_run={'actor':'agent','episode':episode,'owner':run_result['owner'],
        'protocol_sha256':file_hash(target/'protocol.json'),
        'trace_sha256':file_hash(target/'pi-public-trace.jsonl'),
        'submission_sha256':file_hash(target/'scientific/submission.json'),
        'provider_usage':run_result['accounting'],'reported_models':run_result['reported_models'],
        'fresh_messages':loaded[0]['resume_messages'],'tool_sha256':loaded[0]['tool_sha256'],
        'assistance':'Codex apparatus and instruction preparation nonzero/unpriced'}
    seal(external/'agent-run.json',actual_run)
    if episode=='p2-e5-001':
        result=authoritative_consume(value['proposal'],value['policy'],value['acquisition'],
            module('discovery').evaluate_proposal,Host(episode,target/'scientific').current,store(),external)
        result['mode']=value['proposal']['mode']
    elif episode=='p2-h-proposal-001':
        method=value['proposal']
        if method.get('decision')=='no-update':
            result={'status':'NO_UPDATE','retained':False,'proposal':method}
        else:
            result={'status':'ELIGIBLE_H_PROPOSAL','method_text':method['method_text'],
            'method_sha256':digest(method),'proposal':method,'source_episode':episode,
            'impact_scope':module('methods').impact_scope(method),
            'advantage':'UNTESTED_PENDING_FRESH_DESIGNS'}
        seal(external/'method.json',result)
    else:
        execution=store().execute('b-volatile-reset',value['candidate'])
        result={'status':'INDEPENDENT_SERVICE_EVALUATED','candidate':value['candidate'],'execution':execution,
                'fresh_task_entry':True,'method_changed':episode=='p2-hprime-design-001'}
    result['agent_run_sha256']=file_hash(external/'agent-run.json')
    seal(external/'result.json',result)
    print(json.dumps({'episode':episode,'external_result':str(external/'result.json'),
        'status':result.get('status',result.get('selected_service'))},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='action',required=True)
    s=subs.add_parser('smoke');s.add_argument('--identity',choices=['sdk-qualification-001','sdk-qualification-002'],required=True)
    for name in ('run','evaluate'):
        s=subs.add_parser(name);s.add_argument('episode',choices=EPISODES)
    args=parser.parse_args()
    if args.action=='smoke': raise SystemExit(smoke(args.identity))
    if args.action=='run': raise SystemExit(run(args.episode))
    evaluate(args.episode)
