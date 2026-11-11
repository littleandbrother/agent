"""One first-stage experiment: shared full physics, five loops and one native Pi."""
import argparse
import concurrent.futures as cf
import copy
import http.server
import inspect
import json
import multiprocessing
import os
import random
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'funnel'
LOCK = threading.RLock()
HALT = threading.Event()
START = time.monotonic()
TALLY = dict(requests=0, settled=0, spent=0., conservative=0., reserved=0., jobs={})
CAP = 20.
PHYSICS = None
PORT = None
KEY = None
EPISODES = {}
RESUME = False


def saved_events(job):
    path = OUT/'runs'/job/'events.jsonl'
    return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []


def direct_messages(events, payload):
    messages=[dict(role='system',content=SYSTEM),dict(role='user',content=json.dumps(payload))]
    replies=[i for i,e in enumerate(events) if e['kind']=='response']
    for n,i in enumerate(replies):
        message=events[i]['response']['choices'][0]['message'];messages.append(message)
        after=events[i+1:replies[n+1] if n+1<len(replies) else len(events)]
        calls=message.get('tool_calls',[])
        if not calls:messages.append(dict(role='user',content='Use finish for your judgment, or a tool to continue.'))
        for call in calls:
            name=call['function']['name'];args=json.loads(call['function']['arguments'])
            found=next((e for e in after if e['kind']=='tool_result' and e['tool']==name and e['arguments']==args),None)
            invalid=next((e for e in after if e['kind']=='invalid_tool' and e['call']['id']==call['id']),None)
            result=found['result'] if found else dict(error=(invalid or {}).get('error') or 'TOOL_ERROR: execution interrupted; no physical verdict. This call is not repeated.')
            messages.append(dict(role='tool',tool_call_id=call['id'],content=json.dumps(result)))
    return messages


def emit(job, kind, **data):
    row = dict(kind=kind, job=job, time_s=time.monotonic()-START, **data)
    folder = OUT/'runs'/job
    folder.mkdir(parents=True, exist_ok=True)
    with LOCK, (folder/'events.jsonl').open('a') as f:
        f.write(json.dumps(row, ensure_ascii=False, default=lambda x:x.item())+'\n')


def upstream(body, job):
    body.update(model='deepseek-flash', thinking=dict(type='enabled'), reasoning_effort='high', stream=False)
    body.pop('stream_options', None)
    body['max_tokens'] = min(32768, int(body.pop('max_completion_tokens', body.get('max_tokens', 32768))))
    with LOCK:
        j = TALLY['jobs'].setdefault(job, dict(requests=0, responses=0, output=0, started=time.monotonic()))
        body['max_tokens'] = min(body['max_tokens'], 262144-j['output'])
    raw = json.dumps(body).encode()
    reserve = (len(raw)*.30 + max(0,body['max_tokens'])*1.20)/1e6
    while True:
        with LOCK:
            if HALT.is_set() or time.monotonic()-START > 14400 or time.monotonic()-j['started'] > 1800 or j['responses'] >= 64 or TALLY['requests'] >= 12288 or body['max_tokens'] <= 0 or TALLY['spent']+TALLY['reserved']+reserve > CAP:
                raise RuntimeError('LOCAL_LIMIT: no provider request sent')
            TALLY['requests'] += 1; j['requests'] += 1
            ident = TALLY['requests']; TALLY['reserved'] += reserve
        emit(job, 'request', id=ident, reservation_usd=reserve, input_bytes=len(raw),
             first_payload=body if j['requests']==1 else None)
        try:
            request = urllib.request.Request('https://api.deepseek.com/chat/completions', data=raw,
                headers={'Authorization':'Bearer '+KEY, 'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=600) as f:
                answer = json.load(f)
            usage = answer.get('usage', {})
            if not all(type(usage.get(k)) is int for k in ('prompt_tokens','completion_tokens','total_tokens')):
                raise RuntimeError('PROVIDER_USAGE_UNAVAILABLE')
            hit = usage.get('prompt_cache_hit_tokens', 0)
            cost = ((usage['prompt_tokens']-hit)*.30+hit*.006+usage['completion_tokens']*1.20)/1e6
            conservative = (usage['prompt_tokens']*.30+usage['completion_tokens']*1.20)/1e6
            with LOCK:
                TALLY['spent'] += cost; TALLY['conservative'] += conservative
                TALLY['reserved'] -= reserve; TALLY['settled'] += 1
                j['output'] += usage['completion_tokens']; j['responses'] += 1
            emit(job, 'response', id=ident, response=answer, estimated_usd=cost, conservative_usd=conservative)
            return answer
        except Exception as e:
            emit(job, 'UNKNOWN', id=ident, error=repr(e), reservation_usd=reserve)
            if isinstance(e, urllib.error.HTTPError) and e.code==500:
                continue  # Human-authorized retry; retain each original reservation.
            HALT.set()
            raise


class Proxy(http.server.BaseHTTPRequestHandler):
    """Only transport/accounting is shared; Pi still drives its own native loop."""
    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            job = self.path.split('/')[2]
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path.endswith('/science'):
                episode=EPISODES[job]
                if self.headers.get('X-Science-Key')!=episode.token:
                    raise ValueError('Use the scientific client in your own workspace')
                answer=episode.tool(body['tool'],body.get('args',{}))
                data=json.dumps(answer).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                return
            stream = body.get('stream', False)
            answer = upstream(body, job)
            if not stream:
                data = json.dumps(answer).encode()
                self.send_response(200); self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
                return
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.end_headers()
            choice = answer['choices'][0]
            message = copy.deepcopy(choice['message'])
            for i,c in enumerate(message.get('tool_calls', [])):
                c['index'] = i
            chunk = {k:answer[k] for k in ('id','model','created') if k in answer}
            chunk.update(object='chat.completion.chunk', choices=[dict(index=0, delta=message, finish_reason=None)])
            self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
            chunk.update(choices=[dict(index=0,delta={},finish_reason=choice['finish_reason'])],usage=answer['usage'])
            self.wfile.write(('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode()); self.wfile.flush()
        except Exception as e:
            data = json.dumps(dict(error=dict(message=str(e), type='local_limit' if str(e).startswith('LOCAL_LIMIT') else 'execution_error'))).encode()
            self.send_response(409); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data)))
            self.end_headers(); self.wfile.write(data)


def function(name, description, fields, required=()):
    return dict(type='function', function=dict(name=name, description=description,
        parameters=dict(type='object',properties=fields,required=list(required))))


def schemas(arm):
    string = dict(type='string')
    tools = [function('evaluate','Apply changes to the current design, then execute the actual full transient. Every call uses one of24 design evaluations, including cached/repeated designs.',
        dict(changes=dict(type='object'),reason=string), ('changes','reason')),
        function('calculate','Run arbitrary Python with numpy/scipy in your public workspace. These calculations are not measurements of the hidden physical instance. Actual full evaluations require evaluate.',dict(code=string),('code',)),
        function('finish','Give your final judgment. INFEASIBLE is a global claim over the entire declared legal space; UNKNOWN is allowed. No automatic correction of your judgment.',
            dict(status=dict(type='string',enum=['FEASIBLE','INFEASIBLE','UNKNOWN']),confidence=dict(type='number',minimum=0,maximum=1),reason=string),('status','confidence','reason'))]
    if arm in ('E','F'):
        tools += [function('inspect_diagnostics','Read actual amplitude/phase, event-window supply and program events from one of your evaluated designs.',dict(evaluation_id=string),('evaluation_id',)),
                  function('compute_bounds','Compute conservative necessary envelopes with explicit scope. A non-excluding bound does not prove a feasible solution exists.',{}),
                  function('trace','Read sampled actual voltage/displacement trace from one of your evaluations, with pagination.',
                           dict(evaluation_id=string,start_s=dict(type='number'),end_s=dict(type='number'),offset=dict(type='integer'),limit=dict(type='integer')),('evaluation_id',))]
    return tools


SYSTEM = '''Design this physical monitoring node to satisfy every stated service and safety condition, or judge infeasibility with a stated confidence and scope. You may change any declared variable or installed module. No module is a prescribed answer. Use measurements, physics and numerical code as useful. A failed search is not itself an exhaustive physical proof. Retain both possibility and uncertainty when warranted. All branches remain available; an untried branch is untried, not excluded. Give concise reasons through tool calls. You have24 full design evaluations,64 model responses and262144 total output tokens. Python/numerical work and diagnostic reads do not consume design slots. Read the remaining budgets returned by tools. Your first full initial result is shared and does not consume a design slot. @6/@12/@24 will be prefixes of this same24-slot strategy. End with finish.'''


def make_workspace(job, task, initial, arm):
    import funnel_physics as p
    from sim import beam
    workspace = Path('/tmp')/('bf-funnel-'+job)
    workspace.mkdir(exist_ok=True)
    view = p.feedback(task, task['initial'], initial, arm)
    payload = dict(task=p.public_task(task),initial_feedback=view,python_files=dict(nominal='nominal.py contains the nominal beam equations',science='from science import evaluate; evaluate(changes) runs full physics and consumes the same24 slots'),
        runtime='Native Pi coding Agent with read/write/edit/bash and shared physical tools' if arm=='F' else 'Tool-using model loop with arbitrary Python and shared physical tools')
    (workspace/'task.json').write_text(json.dumps(payload,indent=2))
    (workspace/'nominal.py').write_text('import numpy as np\n\n'+inspect.getsource(beam)+'\n')
    (workspace/'README.md').write_text('The task and current initial measurements are in task.json. nominal.py gives nominal beam equations and representative constants; actual mounting/manufacturing factors are unknown. All true-design evaluations must use evaluate. Python can compute nominal predictions and optimize your own models; it does not reveal the hidden instance.\n')
    (OUT/'profiles').mkdir(exist_ok=True)
    profile = OUT/'profiles'/(job+'.sb')
    generated = subprocess.run(['node',str(HERE/'funnel_pi.mjs'),'--profile',str(workspace)],capture_output=True,text=True,check=True)
    profile.write_text(generated.stdout)
    emit(job,'start',arm=arm,public_payload=payload,tools=schemas(arm),system=SYSTEM)
    return workspace,payload,profile


class Episode:
    def __init__(self, task, arm, initial):
        self.task,self.arm = task,arm
        self.job = arm+'-'+task['id']
        self.x = task['initial'].copy(); self.result = initial
        self.n = 0; self.done = None; self.error = None; self.history = []
        self.token=secrets.token_hex(16);self.eval_lock=threading.RLock()
        self.ids = {initial['evaluation_id']}; self.started = time.monotonic()
        self.previous=saved_events(self.job) if RESUME else []
        if self.previous:
            attempted=[e for e in self.previous if e['kind']=='evaluation_request']
            completed=[e for e in self.previous if e['kind']=='evaluation']
            self.n=max((e['step'] for e in attempted),default=0)
            if attempted:self.x=attempted[-1]['design']
            if completed:self.result=completed[-1]['result']
            self.history=[dict(step=e['step'],design=e['design'],result=e['result']) for e in completed]
            self.ids.update(e['result']['evaluation_id'] for e in completed)
            responses=[e for e in self.previous if e['kind']=='response']
            # Preserve model/evaluation/output/cost quotas; omit documented hosting downtime from the remaining execution clock.
            active=sum(e['time_s']-next(r['time_s'] for r in self.previous if r['kind']=='request' and r['id']==e['id']) for e in responses)
            active+=sum(e['result']['runtime_s'] for e in completed if not e['result']['reused'])
            self.started-=min(active,1800)
            TALLY['jobs'][self.job]=dict(requests=sum(e['kind']=='request' for e in self.previous),responses=len(responses),
                output=sum(e['response']['usage']['completion_tokens'] for e in responses),started=self.started)
        self.workspace,self.payload,self.profile = make_workspace(self.job,task,initial,arm)
        client='import json, urllib.request\nURL='+repr(f'http://127.0.0.1:{PORT}/job/{self.job}/science')+'\nKEY='+repr(self.token)+'\n'
        client += "def call(tool, **args):\n    req=urllib.request.Request(URL,data=json.dumps(dict(tool=tool,args=args)).encode(),headers={'Content-Type':'application/json','X-Science-Key':KEY})\n    with urllib.request.urlopen(req,timeout=1800) as f:return json.load(f)\n\ndef evaluate(changes, reason='Python numerical search'):\n    return call('evaluate',changes=changes,reason=reason)\n"
        (self.workspace/'science.py').write_text(client)
        with (self.workspace/'README.md').open('a') as f:f.write('Python can import science.evaluate(changes) to run full numerical searches. Each underlying call consumes the same24-evaluation counter. science.call exposes only tools permitted in this condition.\n')
        EPISODES[self.job]=self

    def tool(self,name,args):
        import funnel_physics as p
        if self.done is not None:
            return dict(stopped=True)
        if name=='finish':
            self.done=args
            result=dict(stopped=True)
        elif name=='evaluate':
            with self.eval_lock:
                if self.n>=24:
                    return dict(not_executed='24 design evaluations used; finish with your judgment')
                changes=args['changes']
                for k,v in changes.items():
                    domain=self.task['domain'].get(k)
                    if domain is None or (type(domain[0]) is bool and type(v) is not bool) or (type(domain[0]) is not bool and (type(v) not in (int,float) or not domain[0]<=v<=domain[1])):
                        raise ValueError('Outside declared domain: '+k)
                proposed=self.x|changes
                if proposed['rearm_V'] >= proposed['threshold_V']:
                    raise ValueError('Rearm voltage must be below wake threshold')
                self.x=proposed; self.n+=1
                emit(self.job,'evaluation_request',step=self.n,design=self.x,arguments=args)
                self.result=PHYSICS.submit(p.evaluate,self.task,self.x).result()
                self.ids.add(self.result['evaluation_id'])
                self.history.append(dict(step=self.n,design=self.x.copy(),result=self.result))
                result=p.feedback(self.task,self.x,self.result,self.arm)
                emit(self.job,'evaluation',step=self.n,design=self.x,result=self.result,arguments=args)
        elif name=='calculate':
            script=self.workspace/'calculation.py';script.write_text(args['code'])
            run=subprocess.run(['/usr/bin/sandbox-exec','-f',str(self.profile),sys.executable,'-B',str(script)],cwd=self.workspace,capture_output=True,text=True,timeout=max(1,1800-(time.monotonic()-self.started)),env=self.child_env())
            result=dict(stdout=run.stdout[-24000:],stderr=run.stderr[-4000:],exit_code=run.returncode)
        elif name=='compute_bounds' and self.arm in ('E','F'):
            result=p.compute_bounds(self.task,self.x)
        elif name in ('trace','inspect_diagnostics') and self.arm in ('E','F'):
            if args.get('evaluation_id') not in self.ids:
                raise ValueError('Read an evaluation made in this conversation')
            result=getattr(p,name)(**args)
        else:
            raise ValueError('Tool unavailable')
        result['remaining_design_evaluations']=24-self.n
        emit(self.job,'tool_result',tool=name,arguments=args,result=result)
        return result

    def child_env(self):
        return dict(PATH=os.environ['PATH'],HOME=str(self.workspace),LANG='en_US.UTF-8',
            TMPDIR=str(self.workspace),PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1')

    def direct(self):
        messages=direct_messages(self.previous,self.payload)
        for turn in range(sum(e['kind']=='response' for e in self.previous),64):
            if HALT.is_set() or time.monotonic()-self.started>1800:
                self.error='DEPENDENCY_OR_TIME_STOP';break
            req=urllib.request.Request(f'http://127.0.0.1:{PORT}/job/{self.job}/v1/chat/completions',
                data=json.dumps(dict(model='deepseek-flash',messages=messages,tools=schemas(self.arm),max_tokens=32768)).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=610) as f:
                answer=json.load(f)
            choice=answer['choices'][0];message=choice['message'];messages.append(message)
            calls=message.get('tool_calls',[])
            if not calls:
                messages.append(dict(role='user',content='Use finish for your judgment, or a tool to continue.'))
                continue
            for call in calls:
                try:
                    reply=self.tool(call['function']['name'],json.loads(call['function']['arguments']))
                except Exception as e:
                    reply=dict(error=str(e));emit(self.job,'invalid_tool',call=call,error=str(e))
                messages.append(dict(role='tool',tool_call_id=call['id'],content=json.dumps(reply)))
                if self.done is not None:
                    break
            if self.done is not None:
                break
        else:
            self.error='MODEL_RESPONSE_LIMIT'

    def pi(self):
        config=dict(cwd=str(self.workspace),prompt=SYSTEM+'\nRead task.json, then choose your tools and actions.',
            baseUrl=f'http://127.0.0.1:{PORT}/job/{self.job}/v1',model='deepseek-flash',schemas=[t['function'] for t in schemas('F')],
            output_dir=str(self.workspace/'pi-session'))
        if self.previous:
            config['resumeMessages']=[e['event']['message'] for e in self.previous if e['kind']=='pi_event' and e['event'].get('kind')=='message']
            for message in config['resumeMessages']:
                if message['role']=='toolResult' and any(c.get('type')=='text' and 'text' not in c for c in message.get('content',[])):
                    message['content']=[dict(type='text',text='TOOL_ERROR: interrupted execution returned no physical verdict.')]
                    message['isError']=True
            config['resumePrompt']='Execution resumed after a host interruption. Previous calls, observations and budgets remain. An interrupted evaluation has no physical verdict; do not infer failure from it. Continue with the same task.'
            config['wallSeconds']=max(1,1800-(time.monotonic()-self.started))
        process=subprocess.Popen(['/usr/bin/sandbox-exec','-f',str(self.profile),'node',str(HERE/'funnel_pi.mjs')],
            cwd=self.workspace,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(self.workspace/'pi.stderr').open('w'),text=True,
            env=self.child_env())
        try:
            process.stdin.write(json.dumps(config)+'\n');process.stdin.flush()
            for line in process.stdout:
                row=json.loads(line);emit(self.job,'pi_event',event=row)
                if row.get('kind')=='rpc':
                    try:
                        reply=self.tool(row['tool'],row.get('args',{}))
                        response=dict(id=row['id'],result=reply)
                    except Exception as e:
                        response=dict(id=row['id'],error=str(e) or type(e).__name__)
                    process.stdin.write(json.dumps(response)+'\n');process.stdin.flush()
                if row.get('kind')=='terminal':
                    if self.done is None:self.error=row.get('error') or 'PI_ENDED_WITHOUT_FINISH'
                    break
            process.wait(timeout=30)
            if process.returncode and not self.error:
                self.error='PI_PROCESS_'+str(process.returncode)+':'+(self.workspace/'pi.stderr').read_text()[-1000:]
        finally:
            if process.poll() is None:
                process.terminate();process.wait(timeout=10)

    def run(self):
        try:
            self.pi() if self.arm=='F' else self.direct()
        except Exception as e:
            self.error=repr(e)
        validated=not self.n or bool(self.history and self.history[-1]['design']==self.x)
        result=dict(task=self.task['id'],arm=self.arm,truth=self.task['subgroup'][0]!='4',subgroup=self.task['subgroup'],
            final=self.done,error=self.error,evaluations=self.n,actual_pass=self.result['pass_'] if validated else None,validated_design=validated,
            first_pass=0 if self.payload['initial_feedback']['pass_'] else next((h['step'] for h in self.history if h['result']['pass_']),None),
            runtime_s=time.monotonic()-self.started,design=self.x)
        emit(self.job,'terminal',**result)
        (OUT/'runs'/self.job/'terminal.json').write_text(json.dumps(result,indent=2))
        print(self.job,'PASS' if result['first_pass'] is not None else (self.done or {}).get('status',self.error),self.n,flush=True)
        # Only rebuildable public workspaces are removed; all decisions/tool facts remain above.
        shutil.rmtree(self.workspace)
        return result


def report():
    rows=[json.loads(p.read_text()) for p in sorted((OUT/'runs').glob('*/terminal.json'))]
    summary={}
    for arm in 'ABCDEF':
        values=[r for r in rows if r['arm']==arm]
        summary[arm]=dict(complete=len(values),feasible_count=sum(r['truth'] for r in values),
            pass_at={str(n):sum(r['truth'] and r['first_pass'] is not None and r['first_pass']<=n for r in values) for n in (6,12,24)},
            false_infeasible=sum(r['truth'] and (r['final'] or {}).get('status')=='INFEASIBLE' for r in values),
            true_infeasible=sum(not r['truth'] and (r['final'] or {}).get('status')=='INFEASIBLE' for r in values),
            errors=sum(r['error'] is not None for r in values))
    events=[json.loads(line) for p in (OUT/'runs').glob('*/events.jsonl') for line in p.read_text().splitlines()]
    responses=[r for r in events if r['kind']=='response'];unknown=[r for r in events if r['kind']=='UNKNOWN']
    science=[r['result'] for r in events if r['kind']=='evaluation']
    accounting=dict(requests=sum(r['kind']=='request' for r in events),settled=len(responses),unknown=unknown,
        usage={k:sum(r['response']['usage'].get(k,0) for r in responses) for k in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens')},
        estimated_usd=sum(r['estimated_usd'] for r in responses),conservative_usd=sum(r['conservative_usd'] for r in responses),
        retained_unknown_reservation_usd=sum(r['reservation_usd'] for r in unknown),rate_estimate_not_bill=True)
    common=json.loads((OUT/'initial.json').read_text()) if (OUT/'initial.json').exists() else {}
    data=dict(results=rows,arms=summary,accounting=accounting,science=dict(agent_attempts=sum(r['kind']=='evaluation_request' for r in events),logical_evaluations=len(science),agent_new_full=sum(r['cost']['full'] for r in science),agent_cached=sum(r['reused'] for r in science),shared_initials=dict(logical=len(common),new_full=sum(r['cost']['full'] for r in common.values()),cached=sum(r['reused'] for r in common.values())),qualification_file='qualification.json'),runtime_s=time.monotonic()-START)
    (OUT/'summary.json').write_text(json.dumps(data,indent=2))
    return data


def main():
    global PHYSICS,PORT,KEY,RESUME,START
    import funnel_physics as p
    from funnel_tasks import tasks
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--resume',action='store_true');parser.add_argument('--report',action='store_true');parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.report:
        print(json.dumps(report()['arms'],indent=2));return
    if not args.run:
        raise SystemExit('Choose --run or --report')
    RESUME=args.resume
    if list((OUT/'runs').glob('*/events.jsonl')) and not RESUME:
        raise SystemExit('Run already has evidence; use report, never silently replay')
    if RESUME:
        events=[e for folder in (OUT/'runs').iterdir() if folder.is_dir() for e in saved_events(folder.name)]
        responses=[e for e in events if e['kind']=='response'];unknown=[e for e in events if e['kind']=='UNKNOWN']
        request_ids={e['id'] for e in events if e['kind']=='request'}
        if request_ids-{e['id'] for e in responses+unknown}:raise RuntimeError('Unsettled provider request; do not replay')
        TALLY.update(requests=max(request_ids,default=0),settled=len(responses),spent=sum(e['estimated_usd'] for e in responses),
            conservative=sum(e['conservative_usd'] for e in responses),reserved=sum(e['reservation_usd'] for e in unknown))
        START-=max(e['time_s'] for e in events)
    frozen=tasks();qualification=json.loads((OUT/'qualification.json').read_text())
    if not qualification.get('all_qualified'):
        raise SystemExit('Task qualification incomplete; do not treat missing witnesses/proofs as truth')
    KEY=os.environ.get('DEEPSEEK_API_KEY') or (Path.home()/'.local/share/bf-campaign-20261019-s0/workbench/secrets/deepseek.key').read_text().strip()
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Proxy);PORT=server.server_port
    threading.Thread(target=server.serve_forever,daemon=True).start()
    protocol=dict(model='deepseek-flash',thinking='high',groups=dict(A='Base facts + Python + neutral untried-branch reminder',B='A + passive PA/EW/energy diagnostics',C='A + passive valid necessary envelopes',D='A + passive diagnostics/envelopes',E='A + active diagnostics/envelopes/trace',F='Native Pi persistent coding Agent, same active tools/information as E'),
        task_ids=[t['id'] for t in frozen],instances=32,trajectories=192,design_evaluations=24,model_responses=64,output_tokens=262144,request_output=32768,episode_wall_s=1800,batch_wall_s=14400,usd_cap=CAP,
        concurrency=dict(conversations=64,physical_processes=8),rates_per_million=dict(uncached_input=.30,cached_input=.006,output=1.20),rate_estimate_not_bill=True,
        interpretation='Single-model first-stage paired pilot. No claims of universal necessity/sufficiency, mathematical optimality of finite search, or predetermined method superiority. @6/12/24 are prefixes, not separately optimized budgets. F vs E compares native coding runtime at equal physical information access.',
        http500='Automatic retry approved; retain each UNKNOWN/reservation. Other missing usage halts paid dependencies.',qualification='Actual full-service feasible witnesses and analytical full-domain necessary exclusions before model results.',flagship='Not authorized in this stage; await user confirmation/new keys.')
    if RESUME:
        protocol['recovery']='Original tasks, scientific kernel, observations, messages, costs and quotas preserved. 64 conversations requested by user. Per-input worker timer replaces uncancelled wait timeout; documented host downtime excluded from remaining execution clock. Original operational terminations retained.'
        shutil.copy2(OUT/'protocol.json',OUT/'protocol-before-concurrency.json')
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    with cf.ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context('spawn')) as PHYSICS:
        if RESUME:initial=json.loads((OUT/'initial.json').read_text())
        else:
            initial={t['id']:f for t,f in ((t,PHYSICS.submit(p.evaluate,t,t['initial'])) for t in frozen)}
            initial={k:f.result(timeout=600) for k,f in initial.items()}
            (OUT/'initial.json').write_text(json.dumps(initial,separators=(',',':'))+'\n')
        jobs=[(t,a) for t in frozen for a in 'ABCDEF'];random.Random(20261111).shuffle(jobs)
        jobs=[(t,a) for t,a in jobs if not (OUT/'runs'/(a+'-'+t['id'])/'terminal.json').exists()]
        with cf.ThreadPoolExecutor(max_workers=64) as pool:
            futures=[pool.submit(lambda t=t,a=a:Episode(t,a,initial[t['id']]).run()) for t,a in jobs]
            for i,f in enumerate(cf.as_completed(futures),1):
                f.result()
                if i%8==0:report()
    server.shutdown();summary=report()
    print(json.dumps(summary['arms'],indent=2),flush=True)


if __name__=='__main__':
    main()
