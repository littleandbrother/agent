"""Old, unchanged phase2 instances: circuit × domain × runtime × real budget."""
import concurrent.futures as cf
import copy
import http.server
import inspect
import itertools
import json
import multiprocessing
import random
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import funnel_run as host
import attribution_physics as physics
from sim import beam

HERE = Path(__file__).resolve().parent
OUT = HERE / 'attribution'
SYSTEM = '''Repair this monitoring node under the declared hardware and parameter domain. Meet every original full-transient service and safety condition. Hidden manufacturing factors are fixed within a task. Use only your own measurements; a failed search or a measured maximum is not a full-domain proof. No diagnostics or calibration truth are provided. All legal variables can be changed together. Your physical-evaluation budget is stated in task.json; it is a hard independent budget, not a prefix of another run. The common initial result is free. Numerical work, when available, does not spend physical evaluations; every call to science.evaluate does. After finding a passing design you may finish immediately; further improvement is optional. Finish with status/confidence/reason and an evaluated evaluation_id selecting your final design (empty for no selection).'''
TOOLS = copy.deepcopy(host.schemas('A'))
TOOLS[0]['function']['description'] = 'Apply a joint design change and run full transient physics. One call spends one of the task-specific physical evaluation slots, including cache hits.'
TOOLS[2]['function']['parameters']['properties']['evaluation_id'] = dict(type='string')
TOOLS[2]['function']['parameters']['required'].append('evaluation_id')


def schemas(arm):
    return [t for t in TOOLS if arm != 'L' or t['function']['name'] != 'calculate']


class Episode(host.Episode):
    def __init__(self, task, arm, budget, initial):
        self.task, self.arm, self.budget = task, arm, budget
        self.job = f"{arm}-{task['branch']}-{task['width']}-b{budget}-{task['selection_id']}"
        self.x, self.result = task['initial'].copy(), initial
        self.n, self.done, self.error, self.history, self.previous = 0, None, None, [], []
        self.token, self.eval_lock, self.started = secrets.token_hex(16), threading.RLock(), time.monotonic()
        self.workspace = Path('/tmp') / ('bf-attribution-' + self.job)
        self.workspace.mkdir()
        self.payload = dict(task=physics.public_task(task), initial_feedback=physics.feedback(task,self.x,initial),
            resources=dict(physical_evaluations=budget,model_responses=64,output_tokens=262144,wall_s=1800),
            computing='Python/numpy/scipy and nominal.py are available.' if arm!='L' else 'No Python tool or nominal equation source is supplied in this control.',
            runtime='Native Pi coding Agent' if arm=='F' else 'Persistent model tool loop')
        (self.workspace/'task.json').write_text(json.dumps(self.payload,indent=2))
        if arm!='L':
            (self.workspace/'nominal.py').write_text('import numpy as np\n\n'+inspect.getsource(beam)+'\n')
            client='import json, urllib.request\nURL='+repr(f'http://127.0.0.1:{host.PORT}/job/{self.job}/science')+'\nKEY='+repr(self.token)+'\n'
            client+="def call(tool, **args):\n    req=urllib.request.Request(URL,data=json.dumps(dict(tool=tool,args=args)).encode(),headers={'Content-Type':'application/json','X-Science-Key':KEY})\n    with urllib.request.urlopen(req,timeout=1800) as f:return json.load(f)\n\ndef evaluate(changes,reason='Python design search'):\n    return call('evaluate',changes=changes,reason=reason)\n"
            (self.workspace/'science.py').write_text(client)
        (self.workspace/'README.md').write_text('task.json contains all public task information. No hidden factors or historical successful designs are available. nominal.py, when present, is nominal, not a calibrated model. All true physical evaluations must use evaluate and share the declared budget. No extra diagnostic/bounds/trace tools.\n')
        self.profile=OUT/'profiles'/(self.job+'.sb')
        self.profile.parent.mkdir(exist_ok=True)
        profile=subprocess.run(['node',str(HERE/'funnel_pi.mjs'),'--profile',str(self.workspace)],capture_output=True,text=True,check=True)
        self.profile.write_text(profile.stdout)
        host.EPISODES[self.job]=self
        host.emit(self.job,'start',arm=arm,budget=budget,task_id=task['id'],branch=task['branch'],width=task['width'],
                  public_payload=self.payload,system=SYSTEM,tools=schemas(arm))

    def tool(self,name,args):
        if self.done is not None:return dict(stopped=True)
        if name not in {t['function']['name'] for t in schemas(self.arm)}:
            raise ValueError('Tool unavailable in this condition')
        if name=='finish':
            self.done=args;result=dict(stopped=True)
        elif name=='evaluate':
            with self.eval_lock:
                if self.n>=self.budget:return dict(not_executed='Physical evaluation budget exhausted; finish with available evidence.',remaining_design_evaluations=0)
                for key,value in args['changes'].items():
                    domain=self.task['domain'].get(key)
                    if domain is None or (type(domain[0]) is bool and type(value) is not bool) or (type(domain[0]) is not bool and (type(value) not in (int,float) or not domain[0]<=value<=domain[1])):
                        raise ValueError('Outside declared domain: '+key)
                proposed=self.x|args['changes']
                if 'rearm_V' in proposed and proposed['rearm_V']>=proposed['threshold_V']:
                    raise ValueError('Rearm voltage must be below wake voltage')
                self.x=proposed;self.n+=1
                host.emit(self.job,'evaluation_request',step=self.n,design=self.x,arguments=args)
                result=host.PHYSICS.submit(physics.evaluate,self.task,self.x).result()
                self.result=result
                self.history.append(dict(step=self.n,design=self.x.copy(),result=result))
                host.emit(self.job,'evaluation',step=self.n,design=self.x,result=result,arguments=args)
                result=physics.feedback(self.task,self.x,result)
        else:
            script=self.workspace/'calculation.py';script.write_text(args['code'])
            run=subprocess.run(['/usr/bin/sandbox-exec','-f',str(self.profile),sys.executable,'-B',str(script)],cwd=self.workspace,capture_output=True,text=True,
                timeout=max(1,1800-(time.monotonic()-self.started)),env=self.child_env())
            result=dict(stdout=run.stdout[-24000:],stderr=run.stderr[-4000:],exit_code=run.returncode)
        result['remaining_design_evaluations']=self.budget-self.n
        host.emit(self.job,'tool_result',tool=name,arguments=args,result=result)
        return result

    def pi(self):
        config=dict(cwd=str(self.workspace),prompt=json.dumps(self.payload),systemPrompt=SYSTEM,
            baseUrl=f'http://127.0.0.1:{host.PORT}/job/{self.job}/v1',model='deepseek-flash',
            schemas=[t['function'] for t in schemas('F')],wallSeconds=1800)
        process=subprocess.Popen(['/usr/bin/sandbox-exec','-f',str(self.profile),'node',str(HERE/'funnel_pi.mjs')],
            cwd=self.workspace,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(self.workspace/'pi.stderr').open('w'),text=True,env=self.child_env())
        try:
            process.stdin.write(json.dumps(config)+'\n');process.stdin.flush()
            for line in process.stdout:
                event=json.loads(line);host.emit(self.job,'pi_event',event=event)
                if event.get('kind')=='rpc':
                    try:reply=dict(id=event['id'],result=self.tool(event['tool'],event.get('args',{})))
                    except Exception as error:reply=dict(id=event['id'],error=str(error) or type(error).__name__)
                    process.stdin.write(json.dumps(reply)+'\n');process.stdin.flush()
                if event.get('kind')=='terminal':
                    if self.done is None:self.error=event.get('error') or 'PI_ENDED_WITHOUT_FINISH'
                    break
            process.wait(timeout=30)
            if process.returncode and not self.error:self.error='PI_PROCESS_'+str(process.returncode)
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)

    def run(self):
        try:self.pi() if self.arm=='F' else self.direct()
        except Exception as error:self.error=str(error) or type(error).__name__
        selection=(self.done or {}).get('evaluation_id')
        candidates=[dict(step=0,design=self.task['initial'],result=self.payload['initial_feedback'])]+self.history
        selected=next((h for h in candidates if h['result']['evaluation_id']==selection),None)
        row=dict(job=self.job,task=self.task['id'],selection_id=self.task['selection_id'],arm=self.arm,budget=self.budget,
            branch=self.task['branch'],width=self.task['width'],evaluations=self.n,final=self.done,error=self.error,
            first_pass=next((h['step'] for h in candidates if h['result']['pass_']),None),
            selected_pass=bool(self.done and self.done['status']=='FEASIBLE' and selected and selected['result']['pass_']),
            last_working_pass=self.result['pass_'] if (not self.n or self.history and self.history[-1]['design']==self.x) else None,
            selected_design=selected['design'] if selected else None,design=self.x,runtime_s=time.monotonic()-self.started)
        host.emit(self.job,'terminal',**{k:v for k,v in row.items() if k!='job'})
        (OUT/'runs'/self.job/'terminal.json').write_text(json.dumps(row,indent=2))
        print(self.job,'FOUND' if row['first_pass'] is not None else (self.done or {}).get('status',self.error),self.n,flush=True)
        shutil.rmtree(self.workspace)
        return row


def report():
    rows=[json.loads(p.read_text()) for p in sorted((OUT/'runs').glob('*/terminal.json'))]
    cells={}
    for arm,branch,width,budget in itertools.product('LAF',('direct','converter'),('narrow','wide'),(6,24)):
        q=[r for r in rows if (r['arm'],r['branch'],r['width'],r['budget'])==(arm,branch,width,budget)]
        if q:cells[f'{arm}-{branch}-{width}-b{budget}']=dict(complete=len(q),found=sum(r['first_pass'] is not None for r in q),selected_pass=sum(r['selected_pass'] for r in q),errors=sum(bool(r['error']) for r in q))
    events=[json.loads(line) for p in (OUT/'runs').glob('*/events.jsonl') for line in p.read_text().splitlines()]
    responses=[e for e in events if e['kind']=='response'];unknown=[e for e in events if e['kind']=='UNKNOWN']
    science=[e['result'] for e in events if e['kind']=='evaluation']
    data=dict(rows=rows,cells=cells,accounting=dict(requests=sum(e['kind']=='request' for e in events),settled=len(responses),unknown=unknown,
        usage={k:sum(e['response']['usage'].get(k,0) for e in responses) for k in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens')},
        estimated_usd=sum(e['estimated_usd'] for e in responses),retained_reservation_usd=sum(e['reservation_usd'] for e in unknown)),
        science=dict(attempts=sum(e['kind']=='evaluation_request' for e in events),completed=len(science),new_full=sum(e['cost']['full'] for e in science),reused=sum(e['reused'] for e in science)))
    (OUT/'summary.json').write_text(json.dumps(data,indent=2));return data


def main():
    if '--report' in sys.argv:print(json.dumps(report()['cells'],indent=2));return
    if '--run' not in sys.argv:raise SystemExit('Use --run or --report')
    if list((OUT/'runs').glob('*/events.jsonl')):raise SystemExit('Existing evidence: do not silently rerun')
    host.OUT,host.SYSTEM,host.schemas,host.CAP=OUT,SYSTEM,schemas,20.
    host.KEY=(Path.home()/'.local/share/bf-campaign-20261019-s0/workbench/secrets/deepseek.key').read_text().strip()
    selection=json.loads((OUT/'legacy-selection.json').read_text())
    tasks=[physics.make_task(p['selection_id'],b,w) for p in selection['selected_pairs'] for b,w in itertools.product(('direct','converter'),('narrow','wide'))]
    (OUT/'tasks.json').write_text(json.dumps(tasks,indent=2))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),host.Proxy);host.PORT=server.server_port
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with cf.ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context('spawn')) as host.PHYSICS:
        initial={t['selection_id']+'-'+t['branch']+'-'+t['width']:host.PHYSICS.submit(physics.evaluate,t,t['initial']) for t in tasks}
        initial={k:v.result() for k,v in initial.items()}
        (OUT/'initial.json').write_text(json.dumps(initial,indent=2))
        jobs=[(t,a,n) for t in tasks for a,n in itertools.product('AF',(6,24))]
        jobs += [(t,'L',n) for t in tasks if t['branch']=='direct' and t['width']=='narrow' for n in (6,24)]
        random.Random(20261111).shuffle(jobs)
        with cf.ThreadPoolExecutor(max_workers=64) as pool:
            futures=[pool.submit(lambda t=t,a=a,n=n:Episode(t,a,n,initial[t['selection_id']+'-'+t['branch']+'-'+t['width']]).run()) for t,a,n in jobs]
            for i,future in enumerate(cf.as_completed(futures),1):
                future.result()
                if i%8==0:report()
    server.shutdown();print(json.dumps(report()['cells'],indent=2))


if __name__=='__main__':main()
