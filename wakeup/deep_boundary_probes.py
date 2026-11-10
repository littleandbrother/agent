"""Six small scientific probes. Run --run, then --report; no old harness."""
import argparse
import concurrent.futures
import importlib.util
import http.client
import json
import os
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/'deep'
MODULES={}
for name in ('semantic_alias','trap_cascade','numerics_fidelity'):
    spec=importlib.util.spec_from_file_location(name,OUT/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    for t in m.tasks(): MODULES[t['id']]=(m,t)
ARMS=('Raw','Text','Decoupled')
RATES={'input':.30,'output':1.20,'cache':.006}
SCIENCE=threading.Lock()


def scientific(m,t,x,fidelity='full',observation=None):
    with SCIENCE: return m.evaluate(t,x,fidelity,observation)


def run(continuation=False, auto500=False):
    path=OUT/'agents.jsonl';old=[json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    sent={r['id'] for r in old if r['kind']=='request'};settled={r['id'] for r in old if r['kind']=='response'}
    allowed={r['id'] for r in old if r['kind']=='UNKNOWN' and (r['error'].startswith('HTTP Error 500:') or r['error'].startswith('IncompleteRead('))} if auto500 else ({44} if continuation else set())
    if sent-settled != allowed:raise SystemExit('Unsettled non-HTTP500 request; no retry.')
    paid_jobs={r['job'] for r in old if r['kind']=='request'}
    last={r['job']:r for r in old if r['kind']=='terminal'}
    done={j for j,r in last.items() if r['error'] is None or r['pass_']} if auto500 else {r['job'] for r in old if r['kind']=='terminal' and (not continuation or r['job'] in paid_jobs)}
    lock=threading.Lock();halt=threading.Event();start=time.monotonic()
    tally=dict(requests=len(sent),spent=sum(r['estimated_usd'] for r in old if r['kind']=='response'),reserved=sum(r['reservation_usd'] for r in old if r['kind']=='UNKNOWN'))
    key=os.environ.get('DEEPSEEK_API_KEY') or (Path.home()/'.local/share/bf-campaign-20261019-s0/workbench/secrets/deepseek.key').read_text().strip()
    protocol=dict(model='deepseek-flash',thinking='high',output_per_request=32768,usd_cap=3.,max_requests=300,wall_s=7200,
        design_actions=6,full_design_actions=3,observations=3,numeric_calls_per_optimizer=50,
        groups='Raw/Text/Decoupled share tools; axis5 instead Raw/Raw+Numeric/Decoupled isolates the numerical tool.',
        interpretation='50 local calculations are not a theoretical optimum. No hard topology lock. P3-peek and P6-impact-transfer have no full feasible witness; diagnostic-only, not a cognitive-failure race.',
        tasks=[{k:v for k,v in t.items() if not k.startswith('_') and k!='diagnostic'} for m,t in MODULES.values()],rates=RATES)
    if continuation or auto500:
        protocol=json.loads((OUT/'protocol.json').read_text())
        if auto500:protocol['http500_policy']=dict(human_approved=True,automatic_retry=True,retain_each_original_unknown_and_reserve=True,other_missing_usage_stops=True,budget_usd=3,transport_scope='HTTP500 and incomplete response-body reads; original reservations retained',scope='Resume original conversations and remaining cells; no duplicated scientific prefix')
        else:protocol['accounting_amendment']=dict(request=44,job='P2_unit_v/Text',human_approved=True,reservation_usd=.0404316,retain_unknown=True,retry=False,scope='Only jobs without ANY earlier provider request; all costs and reservation share originalUSD3')
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    def emit(r):
        r['phase']='automatic-http500' if auto500 else 'continuation-1' if continuation else 'initial'
        with lock:
            with path.open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    initial={r['task']:r['result'] for r in old if r['kind']=='common_initial'}
    for tid,(m,t) in MODULES.items():
        if tid in initial:continue
        fidelity='fast' if t['axis'] in (5,6) else 'full'
        initial[tid]=scientific(m,t,t['initial'],fidelity)
        emit(dict(kind='common_initial',task=tid,design=t['initial'],result=initial[tid]))
    def episode(job):
        tid,arm=job;jid=tid+'/'+arm
        if jid in done:return
        m,t=MODULES[tid];x=t['initial'].copy();current=initial[tid];n=full=obs=cheap=0;error=None;diagnosis=None;history=[]
        full_seen={json.dumps(x,sort_keys=True)} if current['fidelity'].startswith('full') else set()
        public={k:v for k,v in t.items() if not k.startswith('_') and k!='diagnostic'}
        policy='Freely diagnose and redesign. Choose interventions or observations; do not assume the examples in descriptions are unique solutions.'
        if arm=='Text':policy+=' Diagnostic note: '+t['diagnostic']
        if arm=='Decoupled':policy+=' Keep explicit competing structural hypotheses. A failed numerical point is not a refuted topology. Use bounded numerical search when available; preserve supported improvements while investigating residual failures. Reverse a choice if evidence warrants it; nothing is administratively locked. State numerical uncertainty.'
        messages=[dict(role='system',content='Design and repair this physical monitoring node. Use tools and concise reasons; avoid lengthy hand arithmetic. Only full-service success counts except explicitly harmonic-only tasks. Available actions have no prescribed winner.\n'+policy),dict(role='user',content=json.dumps(dict(task=public,initial_feedback=current,budget=dict(design_actions=6,full_design_actions=3,observations=3,numeric_calls_per_optimizer=50))))]
        tools=[dict(type='function',function=dict(name='evaluate',description='Apply changes to CURRENT design. Choose full or fast; fast success is not full success.',parameters=dict(type='object',properties=dict(changes=dict(type='object'),fidelity=dict(type='string',enum=['full','fast']),reason=dict(type='string')),required=['changes','fidelity','reason']))),
            dict(type='function',function=dict(name='observe',description='Measure current design power/trigger/program. Same measured state, no hidden diagnosis label.',parameters=dict(type='object',properties=dict(kind=dict(type='string',enum=['power','trigger','program'])),required=['kind']))),
            dict(type='function',function=dict(name='finish',description='Stop with scope, diagnosis and remaining uncertainty.',parameters=dict(type='object',properties=dict(reason=dict(type='string')),required=['reason'])))]
        optimizer=hasattr(m,'optimize') and not (t['axis']==5 and arm=='Raw')
        if optimizer:tools.append(dict(type='function',function=dict(name='optimize',description='Apply changes, then at most50 HARMONIC calculations. Does not optimize full rearming, classification or displacement. Returns best FOUND point, NOT optimality/infeasibility proof. Counts one design action.',parameters=dict(type='object',properties=dict(changes=dict(type='object'),variables=dict(type='array',items=dict(type='string',enum=list(m.DOMAIN))),reason=dict(type='string')),required=['changes','variables','reason']))))
        prior=[r for r in old if r.get('job')==jid]
        pending_ids={r['id'] for r in prior if r['kind']=='pending_response'}-{r['id'] for r in prior if r['kind']=='resumed_response'}
        pending=[r for r in prior if r['kind']=='response' and r['id'] in pending_ids]
        responses=[r for r in prior if r['kind']=='response' and r['id'] not in pending_ids]
        if auto500 and responses:
            messages=next(r['messages'] for r in reversed(prior) if r['kind']=='start')
            events=[r for r in prior if r['kind'] in ('evaluation','observation','invalid_action')]
            for rr in responses:
                msg=rr['response']['choices'][0]['message'];messages.append(msg)
                for call in msg.get('tool_calls',[]):
                    name=call['function']['name'];a=json.loads(call['function']['arguments'])
                    if events and events[0]['kind']=='invalid_action':reply=dict(error=events.pop(0)['error'])
                    elif name=='finish':diagnosis=a;reply=dict(stopped=True)
                    elif name=='observe' and obs>=3:reply=dict(not_executed='Observation budget used')
                    elif name=='evaluate' and a['fidelity']=='fast' and t['axis'] not in (5,6):reply=dict(not_executed='No qualified fast evaluator; request full')
                    elif name=='evaluate' and a['fidelity']=='full' and t['axis']!=5 and full>=3:reply=dict(not_executed='Three full design evaluations used; cached observations remain available')
                    elif name!='observe' and n>=6:reply=dict(not_executed='Design budget used')
                    else:
                        e=events.pop(0);x=e['design'].copy();current=e['result'];state=json.dumps(x,sort_keys=True)
                        if name=='observe':
                            obs+=1
                            if current['fidelity'].startswith('full') and state not in full_seen:full+=1;full_seen.add(state)
                            reply=current
                        else:
                            n=e['step'];cheap+=current['cost']['numeric']
                            if current['fidelity'].startswith('full'):full+=1;full_seen.add(state)
                            reply=current if name!='optimize' else dict(design=x,result=current,evaluations=current['cost']['numeric'],proves_infeasibility=False,explanation='Best observed point in a bounded local search, not a theoretical limit or a certified empty subspace.')
                    messages.append(dict(role='tool',tool_call_id=call['id'],content=json.dumps(reply|dict(remaining_designs=6-n,remaining_full_designs=3-full,remaining_observations=3-obs))))
            emit(dict(kind='resume',job=jid,restored_responses=len(responses),actions=n,full_design_actions=full,observations=obs))
        else:emit(dict(kind='start',job=jid,task=tid,axis=t['axis'],arm=arm,messages=messages,tools=tools))
        for turn in range(len(responses),10):
            if halt.is_set():error='DEPENDENCY_STOP';break
            if time.monotonic()-start>7200:halt.set();error='WALL_LIMIT';break
            if pending:
                saved=pending.pop(0);answer=saved['response'];rid=saved['id']
            else:
                body=dict(model='deepseek-flash',messages=messages,tools=tools,thinking=dict(type='enabled'),reasoning_effort='high',max_tokens=32768,stream=False)
                raw=json.dumps(body).encode();reserve=(len(raw)*.30+32768*1.20)/1e6
                while True:
                    with lock:
                        if tally['spent']+tally['reserved']+reserve>3 or tally['requests']>=300:halt.set();error='BUDGET_LIMIT';break
                        tally['reserved']+=reserve;tally['requests']+=1;rid=tally['requests']
                    emit(dict(kind='request',job=jid,id=rid,reservation_usd=reserve))
                    try:
                        req=urllib.request.Request('https://api.deepseek.com/chat/completions',data=raw,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
                        with urllib.request.urlopen(req,timeout=600) as f:answer=json.load(f)
                        u=answer.get('usage',{})
                        if not all(type(u.get(k)) is int for k in ('prompt_tokens','completion_tokens','total_tokens')):raise RuntimeError('usage unavailable')
                        cost=(u['prompt_tokens']*.30+u['completion_tokens']*1.20)/1e6
                        with lock:tally['spent']+=cost;tally['reserved']-=reserve
                        emit(dict(kind='response',job=jid,id=rid,response=answer,estimated_usd=cost));break
                    except Exception as e:
                        error=str(e);emit(dict(kind='UNKNOWN',job=jid,id=rid,error=error,reservation_usd=reserve))
                        if auto500 and (isinstance(e,http.client.IncompleteRead) or isinstance(e,urllib.error.HTTPError) and e.code==500):time.sleep(2);error=None;continue
                        halt.set();break
                if error is not None:break
            choice=answer['choices'][0];msg=choice['message'];messages.append(msg)
            if not msg.get('tool_calls'):error='OUTPUT_LENGTH' if choice['finish_reason']=='length' else 'TEXT_WITHOUT_ACTION';break
            for call in msg['tool_calls']:
                name=call['function']['name']
                try:
                    a=json.loads(call['function']['arguments'])
                    if name=='finish':diagnosis=a;reply=dict(stopped=True)
                    elif name=='observe':
                        if obs>=3:reply=dict(not_executed='Observation budget used')
                        else:
                            state=json.dumps(x,sort_keys=True)
                            if t['axis']!=5 and full>=3 and state not in full_seen:reply=dict(not_executed='Full evaluation budget used for new measurement state')
                            else:
                                obs+=1;reply=scientific(m,t,x,'full',a['kind']);current=reply
                                if current['fidelity'].startswith('full') and state not in full_seen:full+=1;full_seen.add(state)
                                emit(dict(kind='observation',job=jid,design=x.copy(),observation=a['kind'],result=reply))
                    else:
                        if n>=6:reply=dict(not_executed='Design budget used')
                        else:
                            changes=a.get('changes',{})
                            for k,v in changes.items():
                                d=t['domain'].get(k)
                                if d is None or (type(d[0]) is bool and type(v) is not bool) or (type(d[0]) is str and v not in d) or (type(d[0]) not in (str,bool) and (type(v) not in (int,float) or not d[0]<=v<=d[1])):raise ValueError('Outside public domain: '+k)
                            proposed=x|changes
                            if name=='optimize' and optimizer:
                                if any(k not in m.DOMAIN for k in a['variables']):raise ValueError('Optimizer supports declared harmonic variables only')
                                with SCIENCE:z=m.optimize(t,proposed,a['variables'],50)
                                x=z['design'];current=z['result'];cheap+=z['evaluations'];reply=z;n+=1
                            elif name=='evaluate':
                                fidelity=a['fidelity']
                                if fidelity=='fast' and t['axis'] not in (5,6):reply=dict(not_executed='No qualified fast evaluator; request full')
                                elif fidelity=='full' and t['axis']!=5 and full>=3:reply=dict(not_executed='Three full design evaluations used; cached observations remain available')
                                else:
                                    current=scientific(m,t,proposed,fidelity);x=proposed;n+=1;cheap+=current['cost']['numeric'];reply=current
                                    if current['fidelity'].startswith('full'):full+=1;full_seen.add(json.dumps(x,sort_keys=True))
                            else:raise ValueError('Tool unavailable')
                            if 'not_executed' not in reply:
                                h=dict(kind='evaluation',job=jid,step=n,tool=name,arguments=a,design=x.copy(),result=current);history.append(h);emit(h)
                    messages.append(dict(role='tool',tool_call_id=call['id'],content=json.dumps(reply|dict(remaining_designs=6-n,remaining_full_designs=3-full,remaining_observations=3-obs))))
                except (KeyError,ValueError,TypeError) as e:
                    emit(dict(kind='invalid_action',job=jid,error=str(e)))
                    messages.append(dict(role='tool',tool_call_id=call['id'],content=json.dumps(dict(error=str(e)))))
            if rid in pending_ids:emit(dict(kind='resumed_response',job=jid,id=rid))
            valid_success=current['pass_'] and (t['axis']==5 or current['fidelity'].startswith('full'))
            if valid_success or diagnosis is not None or n>=6:break
        else:error='REQUEST_LIMIT'
        ok=current['pass_'] and (t['axis']==5 or current['fidelity'].startswith('full'))
        emit(dict(kind='terminal',job=jid,task=tid,axis=t['axis'],arm=arm,pass_=ok,design=x,result=current,actions=n,full_design_actions=full,observations=obs,numeric_evaluations=cheap,diagnosis=diagnosis,error=error))
        print(jid,'PASS' if ok else error or 'NO_PASS',n,full,obs,flush=True)
    jobs=[(tid,arm) for tid,(m,t) in MODULES.items() for arm in (('Raw','Raw+Numeric','Decoupled') if t['axis']==5 else ARMS)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(episode,jobs))
    emit(dict(kind='batch_end',accounting=tally,runtime_s=time.monotonic()-start));print(json.dumps(tally),flush=True)
    report()


def report():
    r=[json.loads(s) for s in (OUT/'agents.jsonl').read_text().splitlines()];responses=[x for x in r if x['kind']=='response'];u={k:sum(x['response']['usage'].get(k,0) for x in responses) for k in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens')}
    u['reasoning_tokens']=sum(x['response']['usage'].get('completion_tokens_details',{}).get('reasoning_tokens',0) for x in responses)
    cost=sum(x['estimated_usd'] for x in responses)
    result=dict(results=list({x['job']:x for x in r if x['kind']=='terminal'}.values()),requests=sum(x['kind']=='request' for x in r),settled=len(responses),unknown=[x for x in r if x['kind']=='UNKNOWN'],usage=u,conservative_estimated_usd=cost,cache_aware_estimated_usd=cost-u['prompt_cache_hit_tokens']*.294/1e6,actions=sum(x['kind']=='evaluation' for x in r),observations=sum(x['kind']=='observation' for x in r),invalid_actions=sum(x['kind']=='invalid_action' for x in r))
    for t in result['results']:
        calls=sum(x['kind']=='request' and x.get('job')==t['job'] for x in r)
        t['status']='PASS' if t['pass_'] else 'NOT_EXECUTED' if calls==0 else 'VALID_NO_PASS' if t['error'] is None else 'PROVIDER_UNKNOWN' if any(x['job']==t['job'] for x in result['unknown']) else 'INTERRUPTED'
    result['status_counts']={k:sum(t['status']==k for t in result['results']) for k in ('PASS','VALID_NO_PASS','PROVIDER_UNKNOWN','INTERRUPTED','NOT_EXECUTED')}
    facts=[x['result'] for x in r if x['kind'] in ('common_initial','evaluation','observation')]
    result['scientific_costs']=dict(new_full_executions=sum(x['cost']['full'] for x in facts),numeric_evaluations=sum(x['cost']['numeric'] for x in facts),full_result_reuses=sum(x['fidelity'].startswith('full') and x['cost']['full']==0 for x in facts),optimizer_internal_evaluations=sum(x['result']['cost']['numeric'] for x in r if x['kind']=='evaluation' and x['tool']=='optimize'),scope='Recorded model experiment and common initial states; developer qualification and incident diagnosis separate')
    result['unknown_reservation_usd']=sum(x['reservation_usd'] for x in result['unknown'])
    result['inflight_requests']=sorted({x['id'] for x in r if x['kind']=='request'}-{x['id'] for x in r if x['kind'] in ('response','UNKNOWN')})
    (OUT/'summary.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--report',action='store_true');p.add_argument('--continue-unstarted',action='store_true');p.add_argument('--auto-http500',action='store_true');a=p.parse_args()
    if a.run or a.continue_unstarted or a.auto_http500:run(a.continue_unstarted,a.auto_http500 or a.run)
    if a.report:report()
