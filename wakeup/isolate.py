"""Finite competing-explanation probes. One direct model loop, no old harness."""
import argparse
import concurrent.futures
import http.client
import importlib.util
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/'isolation'
REGISTRY={}
for name in ('faults','resonance'):
    spec=importlib.util.spec_from_file_location(name,OUT/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    for t in m.tasks():REGISTRY[t['id']]=(m,t)
SCIENCE=threading.Lock()


def run():
    journal=OUT/'agents.jsonl'
    old=[json.loads(l) for l in journal.read_text().splitlines()] if journal.exists() else []
    done={r['job'] for r in old if r['kind']=='terminal'}
    unfinished={r['job'] for r in old if r['kind']=='request'}-done
    if unfinished:raise SystemExit('Saved partial conversations exist; use their recorded replies, do not restart them: '+str(unfinished))
    lock=threading.Lock();halt=threading.Event();started=time.monotonic()
    tally=dict(requests=sum(r['kind']=='request' for r in old),spent=sum(r.get('estimated_usd',0) for r in old),reserved=sum(r.get('reservation_usd',0) for r in old if r['kind']=='UNKNOWN'))
    key=os.environ.get('DEEPSEEK_API_KEY') or (Path.home()/'.local/share/bf-campaign-20261019-s0/workbench/secrets/deepseek.key').read_text().strip()
    jobs=[(tid,c,0) for tid in REGISTRY for c in ('C0','C1','C2','C3')]
    numeric=next(k for k in REGISTRY if k.startswith('T4b'))
    jobs.append((numeric,'C4',0))
    for tid,conditions in [('T1a',('C0','C1')),('T2',('C1','C2')),('T3',('C2','C3')),(numeric,('C3','C4'))]:
        jobs.extend((tid,c,1) for c in conditions)
    protocol=dict(model='deepseek-flash',thinking='high',max_output=32768,usd_cap=3,max_requests=300,wall_s=7200,
        full_designs=3,math_designs=6,observations=3,successful_requests_per_job=12,optimize_internal_calls=50,
        conditions=dict(C0='Original wording and delta-only feedback; 3 freely timed single-view observations.',C1='C0 plus component-level voltage definitions and current full design/diff echo. A combined interface intervention.',C2='C1; replace freely timed observations with power/trigger/program after edits1/2/3. Same three single views; timing and scheduling both change.',C3='C2 plus at most one component group per edit; a diagnostic restriction, not a proposed method.',C4='T4b only: C3 plus bounded within-component numerical search; best found, not global extreme/proof.'),
        jobs=[dict(task=a,condition=b,replicate=c) for a,b,c in jobs],
        repeats='Four fixed adjacent pairs, once each, regardless of direction or sign. No post-result task selection.',
        interpretation='Finite elimination study. No assumed baseline failure, no unique-cause or intrinsic-LLM conclusion from residual failures.',
        rates=dict(miss=.30,hit=.006,output=1.20),http500='Automatic retry; original UNKNOWN and full reservation retained. Incomplete response reads treated as transport recovery; other missing usage stops.')
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    def emit(row):
        with lock:
            with journal.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    def measure(m,t,x):
        with SCIENCE:return m.evaluate(t,x)
    initial={r['task']:r['result'] for r in old if r['kind']=='initial'}
    for tid,(m,t) in REGISTRY.items():
        if tid not in initial:
            initial[tid]=measure(m,t,t['initial']);emit(dict(kind='initial',task=tid,design=t['initial'],result=initial[tid]))
    def episode(job):
        tid,c,rep=job;jid=f'{tid}/{c}/r{rep}'
        if jid in done:return
        m,t=REGISTRY[tid];x=t['initial'].copy();result=initial[tid];steps=observations=0;error=diagnosis=None
        limit=6 if result['fidelity'].startswith('harmonic') else 3
        notes='Use actual tools to repair the complete declared service. A failed design does not by itself identify its failed component. No answer is prescribed.'
        if c in ('C2','C3','C4'):notes+=' Three observations are automatically attached after accepted edits, in fixed task-independent order: power, trigger, program; no separate initial measurement. This is the observation-timing condition.'
        if c in ('C3','C4'):notes+=' Each edit must affect at most ONE declared component group. You may combine fields within that group. This restriction is experimental, not a claim about good general design.'
        public=dict(id=tid,description=t['description'],initial=t['initial'],domain=t['domain'],spec=t['spec'] if c=='C0' else t['clean_spec'])
        if c in ('C3','C4'):public['groups']=t['groups']
        def feedback(r,view=None):
            z=dict(pass_=r['pass_'],terminal=r['terminal'],slack=r['slack'],fidelity=r['fidelity'])
            if view:z['observation']=dict(kind=view,values=r[view])
            if c!='C0':z.update(current_design=x.copy(),diff_from_initial={k:v for k,v in x.items() if v!=t['initial'].get(k)})
            return z|dict(remaining_designs=limit-steps,remaining_observations=3-observations)
        messages=[dict(role='system',content=notes),dict(role='user',content=json.dumps(dict(task=public,initial_feedback=feedback(result),budget=dict(design_evaluations=limit,observations=3,model_turns=12))))]
        tools=[dict(type='function',function=dict(name='evaluate',description='Apply changes to CURRENT design and run the actual declared evaluator.',parameters=dict(type='object',properties=dict(changes=dict(type='object'),reason=dict(type='string')),required=['changes','reason']))),dict(type='function',function=dict(name='finish',description='Stop and state what the measurements support.',parameters=dict(type='object',properties=dict(reason=dict(type='string')),required=['reason'])))]
        if c in ('C0','C1'):tools.append(dict(type='function',function=dict(name='observe',description='Read one actual current-state measurement; total3, timing is your choice.',parameters=dict(type='object',properties=dict(kind=dict(type='string',enum=['power','trigger','program'])),required=['kind']))))
        if c=='C4':tools.append(dict(type='function',function=dict(name='optimize',description='Apply a within-component change, then <=50 harmonic calculations in ONE component. Returns best FOUND point, never a theoretical extreme. Counts one design action; all internal calculations logged.',parameters=dict(type='object',properties=dict(changes=dict(type='object'),variables=dict(type='array',items=dict(type='string',enum=list(t['domain']))),reason=dict(type='string')),required=['changes','variables','reason']))))
        emit(dict(kind='start',job=jid,task=tid,condition=c,replicate=rep,messages=messages,tools=tools))
        for turn in range(12):
            if halt.is_set():error='DEPENDENCY_STOP';break
            if time.monotonic()-started>7200:halt.set();error='WALL_LIMIT';break
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
                    emit(dict(kind='UNKNOWN',job=jid,id=rid,error=str(e),reservation_usd=reserve))
                    if isinstance(e,http.client.IncompleteRead) or isinstance(e,urllib.error.HTTPError) and e.code==500:time.sleep(2);continue
                    halt.set();error=str(e);break
            if error is not None:break
            msg=answer['choices'][0]['message'];messages.append(msg)
            if not msg.get('tool_calls'):error='OUTPUT_LENGTH' if answer['choices'][0]['finish_reason']=='length' else 'TEXT_WITHOUT_ACTION';break
            for call in msg['tool_calls']:
                name=call['function']['name']
                try:
                    a=json.loads(call['function']['arguments'])
                    if name=='finish':diagnosis=a['reason'];reply=dict(stopped=True)
                    elif name=='observe' and c in ('C0','C1'):
                        if observations>=3:reply=dict(not_executed='Observation budget used')
                        else:
                            observations+=1;reply=feedback(result,a['kind']);emit(dict(kind='observation',job=jid,kind_observed=a['kind'],design=x.copy(),values=result[a['kind']]))
                    elif name in ('evaluate','optimize'):
                        if steps>=limit:reply=dict(not_executed='Design budget used')
                        else:
                            changes=a.get('changes',{})
                            for k,v in changes.items():
                                d=t['domain'].get(k)
                                if d is None or (type(d[0]) is bool and type(v) is not bool) or (type(d[0]) is not bool and (type(v) not in (int,float) or not d[0]<=v<=d[1])):raise ValueError('Outside public domain: '+k)
                            affected={t['groups'][k] for k,v in changes.items() if x.get(k)!=v}
                            if name=='optimize':affected|={t['groups'][k] for k in a['variables']}
                            if c in ('C3','C4') and len(affected)>1:raise ValueError('This condition permits one component group per edit: '+str(sorted(affected)))
                            before=x.copy();proposed=x|changes
                            if name=='optimize' and c=='C4':
                                with SCIENCE:z=m.optimize(t,proposed,a['variables'],50)
                                x=z['design'];result=z['result']
                            elif name=='evaluate':x=proposed;result=measure(m,t,x)
                            else:raise ValueError('Tool not provided in this condition')
                            steps+=1;view=None
                            if c in ('C2','C3','C4') and observations<3:
                                view=('power','trigger','program')[observations];observations+=1
                            reply=feedback(result,view)
                            emit(dict(kind='evaluation',job=jid,step=steps,tool=name,arguments=a,before=before,design=x.copy(),result=result,automatic_view=view))
                    else:raise ValueError('Tool not provided')
                    messages.append(dict(role='tool',tool_call_id=call['id'],content=json.dumps(reply)))
                except (KeyError,ValueError,TypeError) as e:
                    emit(dict(kind='invalid_action',job=jid,error=str(e)))
                    messages.append(dict(role='tool',tool_call_id=call['id'],content=json.dumps(dict(error=str(e)))))
            if result['pass_'] or diagnosis is not None or steps>=limit:break
        else:error='MODEL_TURN_LIMIT'
        emit(dict(kind='terminal',job=jid,task=tid,condition=c,replicate=rep,pass_=result['pass_'],steps=steps,observations=observations,design=x,result=result,diagnosis=diagnosis,error=error))
        print(jid,'PASS' if result['pass_'] else error or 'NO_PASS',steps,flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(episode,jobs))
    emit(dict(kind='batch_end',runtime_s=time.monotonic()-started,accounting=tally));report()


def report():
    r=[json.loads(l) for l in (OUT/'agents.jsonl').read_text().splitlines()];resp=[x for x in r if x['kind']=='response'];u={k:sum(x['response']['usage'].get(k,0) for x in resp) for k in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens')}
    u['reasoning_tokens']=sum(x['response']['usage'].get('completion_tokens_details',{}).get('reasoning_tokens',0) for x in resp)
    terms=list({x['job']:x for x in r if x['kind']=='terminal'}.values());facts=[x['result'] for x in r if x['kind'] in ('initial','evaluation')]
    s=dict(results=terms,requests=sum(x['kind']=='request' for x in r),settled=len(resp),unknown=[x for x in r if x['kind']=='UNKNOWN'],usage=u,conservative_estimated_usd=sum(x['estimated_usd'] for x in resp),new_full_executions=sum(x['cost']['full'] for x in facts),numeric_evaluations=sum(x['cost']['numeric'] for x in facts),invalid_actions=sum(x['kind']=='invalid_action' for x in r))
    s['cache_aware_estimated_usd']=s['conservative_estimated_usd']-u['prompt_cache_hit_tokens']*.294/1e6;s['unknown_reservation_usd']=sum(x['reservation_usd'] for x in s['unknown'])
    s['inflight']=sorted({x['id'] for x in r if x['kind']=='request'}-{x['id'] for x in r if x['kind'] in ('response','UNKNOWN')})
    s['postrun_diagnostics']=[x for x in r if x['kind']=='postrun_rejected_proposal_counterfactual']
    s['all_new_numeric_evaluations']=s['numeric_evaluations']+sum(x['result']['cost']['numeric'] for x in s['postrun_diagnostics'])
    (OUT/'summary.json').write_text(json.dumps(s,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--report',action='store_true');a=p.parse_args()
    if a.run:run()
    if a.report:report()
