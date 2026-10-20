#!/usr/bin/env python3
"""Fixed finite matched Pi pilot, using the existing V2 gateway and repository."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from bf_v2_environment import APP, environment
from v2_common import RUNTIME, action, create_pi

ROOT=RUNTIME/'continuous-design/pilot'
CONFIG=APP/'configs/studies/continuous-design-20261018'
PROTOCOL=CONFIG/'protocol.json'


def seal(path,value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_text()!=raw: raise ValueError('PILOT_RECEIPT_CHANGED:'+str(path))
    if not path.exists():path.write_text(raw)


def database():
    profile,_=environment(RUNTIME)
    db=sqlite3.connect((Path(profile['home'])/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    return db


def read_record(path):return json.loads(path.read_text())


def preflight_failure(value):
    m=value['metrics'];state=value['state'];error=state.get('error') or ''
    return (not any(m[k] for k in ('model_calls','actual_design_changes','candidate_evaluations','workers'))
        and state['status']=='FAILED' and ("git', 'rev-parse', 'HEAD" in error or
            ('ERR_INVALID_PACKAGE_CONFIG' in error and '/node_modules/' in error)))


def read_trial_final(folder):
    """Retain a zero-call file preflight failure when recovering the same trial."""
    original=read_record(folder/'final.json')
    recovered=folder/'recovery-final.json'
    if not recovered.exists():return original
    if not preflight_failure(original):raise ValueError('RECOVERY_REQUIRES_ZERO_CALL_PREFLIGHT_FAILURE')
    value=read_record(recovered)
    if value['entry']!=original['entry'] or value['preflight_recovery']['original_final_sha256']!=hashlib.sha256((folder/'final.json').read_bytes()).hexdigest():
        raise ValueError('PREFLIGHT_RECOVERY_REGISTRATION_CHANGED')
    return value


def prepare():
    protocol=read_record(PROTOCOL);digest=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    path=ROOT/'registry.json'
    if path.exists():
        old=read_record(path)
        if old['protocol_sha256']!=digest:raise ValueError('PILOT_PROTOCOL_CHANGED')
        return old
    base=read_record(CONFIG/'V2-cold-feedback.json')
    source_tasks=[
        {'id':'S1-current-timing','question':'核对节点的休眠、采样、发送电流与最短采样、发送时间。返回带单位、条件和来源的参数表。facts字段固定为 idle_a、sample_a、tx_a、minimum_sample_s、minimum_tx_s。',
         'oracle':{'idle_a':[.000008,'A'],'sample_a':[.001,'A'],'tx_a':[.008,'A'],'minimum_sample_s':[.01,'s'],'minimum_tx_s':[.004,'s']}},
        {'id':'S2-startup-validity','question':'核对节点的初始电压、启动、掉电、数据过期和收帧要求。facts字段固定为 initial_storage_v、initial_output_v、start_v、brownout_v、sample_validity_s、minimum_packets。保留单位、条件和来源。',
         'oracle':{'initial_storage_v':[0.,'V'],'initial_output_v':[0.,'V'],'start_v':[2.3,'V'],'brownout_v':[1.8,'V'],'sample_validity_s':[.1,'s'],'minimum_packets':[3,'frames']}},
    ]
    seal(ROOT/'source-protocol.json',{'schema_version':'scoped-source-pairs-v1','tasks':source_tasks,
        'arms':['single','temporary'],'replicates':1,'selection':protocol['adoption_rule'],
        'information':'same full candidate and task-definition; temporary arm must use one source worker; direct arm reads directly'})
    specs=[]
    for i,t in enumerate(source_tasks):
        for arm in (['single','temporary'] if i==0 else ['temporary','single']):
            specs.append({'key':t['id']+'--'+arm,'stage':'sources','case':t['id'],'organization':arm,
                'request':t['question'],'oracle':t['oracle'],'definition':base['definition'],'files':base['files']})
    names=['V1-local-capacitance','V2-cold-feedback','T1-fixed-power-scheduling','T2-short-validity']
    arms=list(protocol['conditions'])
    for i,name in enumerate(names):
        task=read_record(CONFIG/(name+'.json'))
        for arm in arms[i:]+arms[:i]:
            specs.append({'key':name+'--'+arm,'stage':'organizations','case':name,'organization':arm,
                'split':task['split'],'request':task['request'],'definition':task['definition'],'files':task['files']})
    entries=[]
    for spec in specs:
        entry_path=ROOT/'trials'/spec['key']/'registration.json'
        if entry_path.exists():entries.append(read_record(entry_path));continue
        owner=create_pi('BF fixed pilot · '+spec['key']+'\n'+spec['request'],'pilot-20261018-'+spec['key'])['id']
        made=action(owner,'repository_task_create',operation_id='pilot-create',definition=spec['definition'],
            title=spec['case'],files=spec['files'])
        policy=action(owner,'repository_work_configure',operation_id='pilot-work-policy',policy={
            'organization':spec['organization'],'kind':'source' if spec['stage']=='sources' else 'design',
            'limits':protocol['limits'],'protocol_sha256':digest})
        auth=action(owner,'authorize',wall_authorization_text='持续运行 不设置时间限制',model_profile=protocol['model_profile'])
        auth.pop('participant_token',None)
        entry={**{k:v for k,v in spec.items() if k not in ('definition','files')},'owner':owner,
            'project_id':made['project_id'],'initial_system':made['id'],'task_definition_id':made['task_definition']['id'],
            'input_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in spec['files'].items()},'policy':policy,'authority':auth}
        seal(entry_path,entry);entries.append(entry)
    # Arms differ only in work policy. Source/engineering inputs and tasks match.
    for case in {x['case'] for x in entries}:
        subset=[x for x in entries if x['case']==case]
        if len({x['task_definition_id'] for x in subset})!=1 or len({json.dumps(x['input_hashes'],sort_keys=True) for x in subset})!=1:
            raise ValueError('MATCHED_INPUT_CONFLICT')
    value={'schema_version':'organization-pilot-registry-v1','protocol_sha256':digest,'trials':entries,
        'automatic_resampling':False,'total_trials':len(entries)}
    seal(path,value);return value


def metrics(entry):
    db=database();pid=entry['project_id']
    workers=[r['owner'] for r in db.execute('SELECT owner FROM design_scoped_tasks WHERE project=?',(pid,))]
    owners=[entry['owner'],*workers];rows=[];events=[]
    for owner in owners:
        rows += [dict(r) for r in db.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY rowid',(owner,))]
        trace=RUNTIME/'workbench/sessions'/owner/'trace.jsonl'
        if trace.exists():events += [json.loads(line) for line in trace.read_text().splitlines() if line]
    usages=[json.loads(r['usage']) for r in rows if r.get('usage')]
    tokens=sum(u.get('total_tokens',u.get('prompt_tokens',0)+u.get('completion_tokens',0)) for u in usages)
    hit=sum(u.get('prompt_cache_hit_tokens',u.get('prompt_tokens_details',{}).get('cached_tokens',0)) for u in usages)
    facts=[e for e in events if e.get('type')=='repository_tool_fact']
    errors=[e for e in events if e.get('type')=='tool_execution_end' and e.get('isError')]
    executions=[json.loads(r[0]) for r in db.execute('SELECT value FROM design_task_executions WHERE project=?',(pid,))]
    results=[json.loads(r[0]) for r in db.execute('SELECT value FROM design_scoped_results WHERE project=? AND task IS NULL',(pid,))]
    worker_results=[json.loads(r[0]) for r in db.execute('SELECT value FROM design_scoped_results WHERE project=? AND task IS NOT NULL',(pid,))]
    view=action(entry['owner'],'repository_view');current=view['project']['submitted']
    system=next(s for s in view['systems'] if s['id']==current)
    q=system['current_qualification']
    source_correct=None
    if entry['stage']=='sources':
        got={f['field']:f for f in results[-1]['facts']} if results else {}
        def normalized(f,unit):
            scales={'A':{'A':1,'mA':.001,'uA':.000001,'µA':.000001,'μA':.000001},
                's':{'s':1,'ms':.001,'us':.000001,'µs':.000001},'V':{'V':1,'mV':.001},
                'frames':{'frames':1,'frame':1,'packets':1,'packet':1,'count':1,'1':1,'帧':1}}
            if f['unit'] not in scales[unit]:return None
            try:return float(f['value'])*scales[unit][f['unit']]
            except (ValueError,TypeError):return None
        source_correct=all(k in got and normalized(got[k],v[1]) is not None and abs(normalized(got[k],v[1])-v[0]) <= max(1e-12,abs(v[0])*1e-9)
            for k,v in entry['oracle'].items())
    actual_changes=[c for s in view['systems'] for c in s['design_changes'] if c['path'] in ('design.json','firmware/main.c')]
    releases=[r for r in view['releases'] if r['target']==current]
    consumed=[f for f in facts if f.get('action')=='work_result' and f.get('result',{}).get('result')]
    m={'key':entry['key'],'owner':entry['owner'],'workers':workers,'model_calls':len(rows),'total_tokens':tokens,
        'cache_hit_tokens':hit,'cost_upper_bound_usd':sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows),
        'unknown_requests':[r['id'] for r in rows if r['status']=='UNKNOWN'],'failed_tool_calls':len(errors),
        'coordination_calls':sum(f.get('action','').startswith('work_') for f in facts),
        'candidate_evaluations':len(executions),'reused_execution':sum(bool(f.get('result',{}).get('reused')) for f in facts if f.get('action')=='task_execute'),
        'native_dispatches':sum(len(e['metrics'].get('native_dispatches',[])) for e in executions),
        'valid_service':q['task_passed'],'qualification':q['status'],'current_system':current,
        'adopted_system':view['project']['adopted'],'source_correct':source_correct,'worker_results':len(worker_results),
        'parent_consumed_worker_results':len(consumed),'source_answers':len(results),'actual_design_changes':len(actual_changes),
        'same_version_releases':len(releases),'human_design_intervention':0,
        'false_adoption':bool(view['project']['adopted'] and view['project']['adopted']!=entry['initial_system'] and not next(s for s in view['systems'] if s['id']==view['project']['adopted'])['current_qualification']['task_passed'])}
    db.close();return m,view


def collect(entry,started=None):
    m,view=metrics(entry);state=action(entry['owner'],'repository_state')
    value={'entry':entry,'state':state,'metrics':m,'view':view,'finished':time.time()}
    if started:m['wall_seconds']=value['finished']-started
    seal(ROOT/'trials'/entry['key']/'final.json',value)
    if m['unknown_requests']:raise ValueError('PILOT_PROVIDER_UNKNOWN_STOP')
    return m


def run(stage):
    registry=read_record(ROOT/'registry.json')
    for entry in registry['trials']:
        if entry['stage']!=stage:continue
        folder=ROOT/'trials'/entry['key']
        if (folder/'final.json').exists():continue
        if (folder/'dispatch.json').exists():
            dispatch=read_record(folder/'dispatch.json')
        else:
            from continuous_design_ops import compact_artifacts
            storage=compact_artifacts()
            if storage['free_bytes']<1024**3:raise ValueError('PILOT_STORAGE_REQUIRED_BEFORE_DISPATCH')
            state=action(entry['owner'],'repository_state')
            if state['model_calls']:raise ValueError('UNRECORDED_PILOT_ATTEMPT_STOP')
            goal=entry['request']+(' 按组织配置核对来源并完成 work_answer。' if stage=='sources' else
                ' 自主分析并完成一项真实设计修订。读取 task_schema；执行、独立验收、设计决定、同版报告与交付、close。按固定组织策略工作，失败如实保存。最多4个执行输入，不做无限搜索；报告保留具体结果。')
            started=time.time();result=action(entry['owner'],'repository_start',goal=goal)
            dispatch={'started':started,'goal':goal,**result};seal(folder/'dispatch.json',dispatch)
            print(json.dumps({'event':'started','trial':entry['key'],'owner':entry['owner']},ensure_ascii=False),flush=True)
        while True:
            state=action(entry['owner'],'repository_state')
            if state['unknown_requests']:raise ValueError('PILOT_PROVIDER_UNKNOWN_STOP')
            if state['status'] not in ('RUNNING','STARTING','QUEUED'):break
            time.sleep(5)
        value=collect(entry,dispatch['started'])
        print(json.dumps({'event':'completed',**value},ensure_ascii=False),flush=True)
    return {'stage':stage,'status':'FINITE_LIST_FINISHED'}


def status():
    registry=read_record(ROOT/'registry.json');out=[]
    for entry in registry['trials']:
        folder=ROOT/'trials'/entry['key']
        if (folder/'recovery-dispatch.json').exists() and not (folder/'recovery-final.json').exists():
            out.append({'key':entry['key'],'zero_call_preflight_recovery':True,
                        **action(entry['owner'],'repository_state')})
        elif (folder/'final.json').exists():
            final=read_trial_final(folder)
            out.append({'status':final['state']['status'],**final['metrics']})
        elif (folder/'dispatch.json').exists():out.append({'key':entry['key'],**action(entry['owner'],'repository_state')})
        else:out.append({'key':entry['key'],'status':'PENDING'})
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','run','status']);parser.add_argument('--stage',choices=['sources','organizations'],default='sources')
    args=parser.parse_args()
    value=prepare() if args.mode=='prepare' else run(args.stage) if args.mode=='run' else status()
    print(json.dumps({'trials':value['total_trials']} if args.mode=='prepare' else value,ensure_ascii=False))
