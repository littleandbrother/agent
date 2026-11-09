"""Finite Pi callback/consumer bridge. Only trusted code executes BF actions."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import subprocess
import threading
import time
import urllib.request

from . import adapter
from .executor import identity
from .methods import common_contract_check, public_state
from .public_projection import (project_result, project_embedded_results,
    scientific_source_identity, is_public_result, PROJECTION_VERSION)
from ..campaign20261019.phase1 import ledger, output_bytes
from ..historical_usage import new_batch_usage_blockers

APP = adapter.APP
ROOT = APP.parents[2]
BASE = ROOT / 'docs/research/pqe-two-paper-plan-20261022'
OUT = BASE / 'stage2-pilot1'
RUNTIME = Path.home() / '.local/share/bf-campaign-20261019-s0'
RUNTIME_HOME = RUNTIME / 'workbench'
DATABASE = RUNTIME_HOME / 'state/workbench.sqlite'
SERVICE = 'http://127.0.0.1:8980'
SDK = (Path.home() / '.local/share/bf-abc-20261020/harness/node_modules/@earendil-works/pi-coding-agent/dist/bundle/index.js').resolve()
PROFILE = 'engineering-reasoning-active-context-v4'
MODEL_IDENTITY = 'deepseek/deepseek-flash;profile='+PROFILE+';thinking=enabled/high;upstream-weights=unreported'
PACKAGE = 'BF-PQE-S2-PILOT1-20261022-001'
LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=6, candidates=6,
              wall_s=900, output_tokens=4096, generated_tokens=49152, usd=4, bytes=20_000_000)
PROTOCOL_PATH = APP/'studies/pqe20261022/shared/pilot-protocol.json'
PUBLIC_MATERIALS_PATH=APP/'studies/pqe20261022/shared/public-materials.json'
INITIAL_ACTION=None
CONTRACT_CORRECTIONS=0
TOTAL_CAPS = {'requests':48,'tool_calls':96,'numerical_inputs':24,'usd':16,'retained_bytes':80000000}
CELLS = [('d04-generic','DOOR-DEV-D04-v1','strong_generic'),
         ('d04-full-h','DOOR-DEV-D04-v1','full_h'),
         ('d07-generic','DOOR-DEV-D07-v1','strong_generic'),
         ('d07-full-h','DOOR-DEV-D07-v1','full_h')]


def configure(protocol_path):
    """Select one registered prospective profile; legacy protocol files stay immutable."""
    global OUT, PACKAGE, LIMITS, CELLS, PROTOCOL_PATH, TOTAL_CAPS
    global PUBLIC_MATERIALS_PATH, INITIAL_ACTION, CONTRACT_CORRECTIONS
    requested=Path(protocol_path).resolve()
    if requested == PROTOCOL_PATH.resolve():return
    profiles={
      'pilot2-protocol.json':('stage2-pilot2','BF-PQE-S2-PILOT2-20261022-001','d04','DOOR-DEV-D04-v1',40000000),
      'pilot3-protocol.json':('stage2-pilot3','BF-PQE-S2-PILOT3-20261022-001','d10','DOOR-DEV-D10-v1',50000000),
      'd15-protocol.json':('stage2-d15','BF-PQE-S2-D15-20261022-001','d15','DOOR-DEV-D15-v2',50000000),
      'm3-protocol.json':('stage2-m3','BF-PQE-S2-M3-20261023-001','m3','DOOR-DEV-D02-M3-v2',50000000),
      'e2dev-protocol.json':('stage3-e2dev','BF-PQE-S3-E2DEV-20261023-001','e2dev',None,150000000)}
    if requested.parent != (APP/'studies/pqe20261022/shared').resolve() or requested.name not in profiles:
        raise ValueError('UNREGISTERED_PILOT_PROTOCOL')
    folder,PACKAGE,label,task_id,cap=profiles[requested.name]
    PROTOCOL_PATH=requested;OUT=BASE/folder
    LIMITS={**LIMITS,'output_tokens':32768,'generated_tokens':131072}
    CELLS=[(label+'-generic',task_id,'strong_generic'),(label+'-full-h',task_id,'full_h')]
    TOTAL_CAPS={'requests':24,'tool_calls':48,'numerical_inputs':12,'usd':8,'retained_bytes':cap}
    if folder=='stage2-pilot3':
        INITIAL_ACTION=OUT/'a/initial';CONTRACT_CORRECTIONS=2
        PUBLIC_MATERIALS_PATH=APP/'studies/pqe20261022/shared/pilot3-public-materials.json'
        TOTAL_CAPS.update(numerical_inputs=14,initial_numerical_inputs=2,episode_numerical_inputs=12)
    elif folder=='stage2-d15':
        LIMITS.update(numerical_inputs=3,candidates=3,bytes=24000000)
        INITIAL_ACTION=OUT/'s0/initial';CONTRACT_CORRECTIONS=2
        PUBLIC_MATERIALS_PATH=APP/'studies/pqe20261022/shared/d15-public-materials.json'
        TOTAL_CAPS.update(numerical_inputs=6,initial_numerical_inputs=0,episode_numerical_inputs=6)
    elif folder=='stage2-m3':
        LIMITS.update(numerical_inputs=6,candidates=6,bytes=24000000)
        INITIAL_ACTION=OUT/'s0/initial';CONTRACT_CORRECTIONS=2
        PUBLIC_MATERIALS_PATH=APP/'studies/pqe20261022/shared/m3-public-materials.json'
        TOTAL_CAPS.update(numerical_inputs=13,initial_numerical_inputs=1,episode_numerical_inputs=12)
    elif folder=='stage3-e2dev':
        LIMITS.update(numerical_inputs=6,candidates=6,bytes=12000000)
        INITIAL_ACTION=None;CONTRACT_CORRECTIONS=2
        PUBLIC_MATERIALS_PATH=APP/'studies/pqe20261022/shared/e2dev-public-materials.json'
        order=[('d15','DOOR-DEV-D15-v2',['strong_generic','fixed_sequence','ordinary_feedback','full_h']),
               ('d07','DOOR-DEV-D07-v1',['fixed_sequence','ordinary_feedback','full_h','strong_generic']),
               ('m3','DOOR-DEV-D02-M3-v2',['ordinary_feedback','full_h','strong_generic','fixed_sequence'])]
        labels={'strong_generic':'b0','fixed_sequence':'b1','ordinary_feedback':'b2','full_h':'b3'}
        CELLS=[(task+'-'+labels[condition],task_id,condition) for task,task_id,conditions in order for condition in conditions]
        TOTAL_CAPS.update(requests=144,tool_calls=288,numerical_inputs=75,initial_numerical_inputs=3,
                          episode_numerical_inputs=72,usd=48)


def output_allowance(used, limits):
    if type(used) is not int or used<0:raise ValueError('INVALID_OUTPUT_USAGE')
    left=limits['generated_tokens']-used
    if left<=0:raise ValueError('EPISODE_OUTPUT_CAP')
    return min(limits['output_tokens'],left)

def encoded(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def dbconnect():
    c=sqlite3.connect(DATABASE,timeout=30);c.row_factory=sqlite3.Row
    return c

def api(path,value):
    token=(RUNTIME_HOME/'state/operator.token').read_text().strip()
    req=urllib.request.Request(SERVICE+path,data=encoded(value),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=20) as response:
        return json.load(response)

def register_owner(episode):
    owner=api('/api/conversations',{'text':'PQE finite development episode '+episode,
        'operation_id':PACKAGE+'-'+episode,'defer_dispatch':True})['id']
    token=secrets.token_urlsafe(32);now=time.time()
    with dbconnect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM model_requests WHERE owner=?',(owner,)).fetchone():
            raise ValueError('OWNER_ALREADY_EXECUTED_NO_RETRY')
        if new_batch_usage_blockers(db,owner):raise ValueError('NEW_USAGE_UNKNOWN_STOP')
        db.execute('INSERT INTO principals VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),owner,'participant'))
        db.execute('INSERT INTO grants VALUES(?,?,?,?)',(owner,json.dumps([PACKAGE]),0,now+LIMITS['wall_s']))
        db.execute('INSERT INTO owner_model_caps VALUES(?,?)',(owner,LIMITS['usd']))
        db.execute('INSERT INTO settings VALUES(?,?)',('model_profile:'+owner,json.dumps(PROFILE)))
        db.execute('INSERT OR IGNORE INTO research_model_studies VALUES(?,?,?,?,?,?)',
            (PACKAGE,now,now+len(CELLS)*LIMITS['wall_s']+300,float(TOTAL_CAPS['usd']),'deepseek-flash','Direct user all-stage authority; '+PACKAGE+' finite resource profile.'))
        db.execute('INSERT INTO research_model_owners VALUES(?,?,?)',(owner,PACKAGE,episode))
    return owner,token

def close_owner(owner,token):
    with dbconnect() as db:
        db.execute('UPDATE grants SET expires=? WHERE owner=?',(time.time(),owner))
        db.execute('DELETE FROM principals WHERE token_hash=? AND owner=?',(hashlib.sha256(token.encode()).hexdigest(),owner))
        db.execute("UPDATE conversations SET status='IDLE',updated=? WHERE id=?",(time.time(),owner))

def public_task(task):
    t=public_state({'task':task})['task']
    # Host sizing provenance can name a prior baseline; it is not a repair hint.
    t.get('material_sources',{}).pop('initial_storage_choice',None)
    t['public_inputs']={**t.get('public_inputs',{}),
        'source_model':{'kind':'constructed continuous cam and reciprocal electromagnetic generator',
          'equations':['x=L/2*(1-cos(2*theta))','u=L*sin(2*theta)*omega',
                       'e=K*u','i=max((abs(e)-Vbus-Vrect)/Rcoil,0)',
                       'Pmechanical=Vbus*i+Rcoil*i*i+Vrect*i+friction_power'],
          'defaults':{'K_Vs_per_m':500,'coil_ohm':1500,'rectifier_v':.3,'stroke_m':.008,
                      'base_radius_m':.007,'coulomb_n':.05,'viscous_n_s_m':.2},
          'scope':'Prescribed angle; reaction checked as force constraint, no load-to-angle feedback.'},
        'supply_scope':'esr_ohm is simplified series load-branch supply impedance, not full net capacitor-current ESR.',
        'gateway_scope':'Ideal link inside listed windows; sequence, direction, CRC and deadlines checked.',
        'program':'Powered contact debounce -> persistent queue SAVE -> TX -> independent gateway ACK. Brownout resets volatile state. Saved event IDs persist when persistent_queue is true. No free unpowered absolute clock.',
        'feedback_access':'Compact factual summaries; observe candidate target detail:<list>:<offset> returns 64 rows from trace/activity/records/packets/receiver_records of current result. Same legal actions and observation access in both conditions.'}
    t['public_inputs']['program_state_semantics']={
        'committed_image':['seq','last_direction','queue of seq/direction records'],
        'persistent_queue_false':'Completed SAVE/ACK updates volatile RAM. Reset clears this image; BOOT starts from seq=0, last_direction=0, queue=[].',
        'persistent_queue_true':'Completed SAVE/ACK atomically updates NVM. Reset clears RAM but retains the last committed NVM image; BOOT reloads that image.',
        'commit_rules':'SAVE commits the new sequence, last direction and queued record only after the full write_s at write_a. ACK deletes its queued record only after the same write interval. Incomplete operations leave the previous committed image intact.',
        'costs':'Both state options use the same declared BOOT/SAVE/ACK/TX/IDLE loads in Task.components. Interrupted intervals still consume current for their elapsed time; energy uses the coupled supply voltage.',
        'clock_rules':'Reset clears pending work, debounce sample/time, powered uptime and retry deadline. The device does not retain unpowered absolute time or unavailable contact-edge history.'}
    return t

def compact_result(result,target=''):
    projected=project_result(result);p=deepcopy(projected)
    facts=p.get('facts',{});catalog={}
    for name in ['trace','activity','records','packets','receiver_records']:
        values=facts.get(name,[])
        if not isinstance(values,list):continue
        catalog[name]={'count':len(values),'page_size':64,'target':'detail:'+name+':<offset>'}
        if len(values)>48:
            indices=set(range(8))|set(range(len(values)-8,len(values)))|{round(i*(len(values)-1)/23) for i in range(24)}
            facts[name]=[values[i] for i in sorted(indices)]
        if name=='activity':
            facts['activity_counts']=dict(Counter((v.get('action','?')+(':'+str(v.get('during')) if v.get('during') else '')) for v in values))
    facts['detail_catalog']=catalog
    facts['projection']='Lists with more than 48 rows are sampled; exact counts and public detail pages remain available via observe.'
    if target.startswith('detail:'):
        match=re.fullmatch(r'detail:(trace|activity|records|packets|receiver_records):(\d+)',target)
        if not match:raise ValueError('PUBLIC_DETAIL_TARGET_INVALID')
        name,offset=match.group(1),int(match.group(2));full=projected.get('facts',{}).get(name,[])
        if offset>len(full):raise ValueError('PUBLIC_DETAIL_OFFSET')
        facts['requested_detail']={'list':name,'offset':offset,'rows':full[offset:offset+64],'total':len(full)}
    return p

def deduplicate_public_results(request):
    registry={}
    def visit(v):
        if isinstance(v,dict):
            if is_public_result(v):
                key=identity(v);registry[key]=v;return {'public_result_ref':key}
            return {k:visit(x) for k,x in v.items()}
        if isinstance(v,list):return [visit(x) for x in v]
        return v
    out=visit(project_embedded_results(request));out['public_result_registry']=registry
    return out


def callback_payload(request,max_output_tokens):
    """The exact public object serialized by the real Pi callback path."""
    formation = PACKAGE == 'BF-PQE-S3-F1FIRST-20261023-001' and request.get('site', '').startswith('G-')
    formation_instruction = ('You are a real method-forming model callback. Return exactly one JSON object following the supplied site contract. No Markdown. You may propose restricted H source as strings only inside the declared patch.code fields. The host validates and separately executes it; you have no filesystem, network, tools, private targets, evaluation answers or credentials. Only the authorized public history and fixed parent in this request are available. No update and rejection are valid. Do not change scientific consumers, evaluator, accounting, authorization or adoption rules.')
    return {
      'instruction':formation_instruction if formation else 'You are the real BF Pi model callback for a fixed trusted decision program. Return exactly one JSON object following the supplied site format. No Markdown. Keep output concise. You have no tools, filesystem, shell, imports, private evaluator or reference solutions. Only public evidence in this request may support claims. Do not claim hardware or learning results. The host executes validated JSON actions; never output executable code. Repeated public_result_ref objects resolve in public_result_registry.',
      'request':deduplicate_public_results(request),'max_output_tokens':max_output_tokens}


def execution_cache_key(task,design,dt,sources):
    return identity({'task':task,'design':design,'dt':dt,
                     'scientific_source':scientific_source_identity(sources)})


def require_public_release():
    path=OUT/'s0/PUBLIC-RELEASE.json';gate=json.loads(path.read_text())
    if gate['status']!='PASS':raise ValueError('PUBLIC_BOUNDARY_NOT_RELEASED')
    review=Path(gate['B_review_path'])
    if hashlib.sha256(review.read_bytes()).hexdigest()!=gate['B_review_sha256']:
        raise ValueError('INDEPENDENT_BOUNDARY_REVIEW_CHANGED')
    for p,h in gate['source_sha256'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:
            raise ValueError('PUBLIC_BOUNDARY_CODE_CHANGED_AFTER_REVIEW')
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def validate_wire(body, output_cap=4096):
    if body.get('model')!='deepseek-flash' or body.get('stream') is not True:raise ValueError('PINNED_MODEL_STREAM_REQUIRED')
    if body.get('tools') or body.get('tool_choice') not in (None,'none','auto'):raise ValueError('NO_MODEL_TOOLS_ALLOWED')
    if any(m.get('role')=='tool' or m.get('tool_calls') for m in body.get('messages',[])):raise ValueError('NO_TOOL_HISTORY_ALLOWED')
    if 'max_tokens' in body and 'max_completion_tokens' in body and body['max_tokens']!=body['max_completion_tokens']:raise ValueError('AMBIGUOUS_OUTPUT_CAP')
    output=body.get('max_tokens',body.get('max_completion_tokens'))
    if type(output_cap) is not int or not 1<=output_cap<=32768:raise ValueError('INVALID_OUTPUT_GRANT')
    if type(output) is not int or not 1<=output<=output_cap:raise ValueError('OUTPUT_CAP')
    if len(encoded(body))>400_000:raise ValueError('PUBLIC_REQUEST_BYTES_CAP')
    return {k:v for k,v in {**body,'temperature':.2,'max_tokens':output}.items() if k!='max_completion_tokens'}

class Episode:
    def __init__(self,ident,task_id,condition,protocol,cache,*,task_resolver=None):
        self.ident,self.condition,self.protocol,self.cache=ident,condition,protocol,cache
        self.root=OUT/'s0/episodes'/ident;self.root.mkdir(parents=True,exist_ok=False)
        self.started=time.monotonic();self.owner,self.token=register_owner(ident)
        self.task_resolver=task_resolver
        self.task=(task_resolver or adapter.load_task)(task_id);self.design=deepcopy(self.task['initial_design']);self.problem=deepcopy(self.task['initial_problem'])
        self.model_calls=0;self.tools=0;self.numerical=0;self.candidates=set();self.last_full=None;self.actions=[]
        self.fatal=None;self.server=None;self.thread=None;self.callback_cap=1;self.call_relays=0
        self.access_token=secrets.token_urlsafe(32)
        save(self.root/'owner.json',{'owner':self.owner,'episode':ident,'finite_usd':4,'grant_wall_s':900,'no_unbounded_authorization':True})

    def budget(self):
        a=ledger(DATABASE,self.owner)
        return {'model_requests':a['requests'],'tool_calls':self.tools,'numerical_inputs':self.numerical,
                'candidates':len(self.candidates),'spent_usd':a['settled_charge_upper_bound_usd']+a['unsettled_reserved_usd'],
                'output_tokens':sum(json.loads(r['usage'])['completion_tokens'] for r in a['rows'] if r['usage']),
                'wall_s':time.monotonic()-self.started}

    def ready(self,paid=False):
        if self.fatal:raise ValueError(self.fatal)
        b=self.budget()
        if b['wall_s']>=LIMITS['wall_s']:raise ValueError('EPISODE_WALL_CAP')
        if output_bytes(self.root)>=LIMITS['bytes'] or output_bytes(OUT)>=TOTAL_CAPS['retained_bytes']:raise ValueError('OUTPUT_STORAGE_CAP')
        with dbconnect() as db:
            if new_batch_usage_blockers(db,self.owner):
                self.fatal='NEW_USAGE_UNKNOWN_STOP';raise ValueError(self.fatal)
        if paid and (b['model_requests']>=12 or b['output_tokens']>=LIMITS['generated_tokens'] or b['spent_usd']+.19>4):raise ValueError('EPISODE_MODEL_CAP')
        return b

    def start_server(self):
        host=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                try:
                    if self.path!='/v1/chat/completions' or self.headers.get('Authorization')!='Bearer '+host.access_token:
                        raise ValueError('BROKER_ROUTE_OR_AUTH_DENIED')
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=400000:raise ValueError('BODY_CAP')
                    budget=host.ready(paid=True)
                    grant=min(host.callback_output_cap,output_allowance(budget['output_tokens'],LIMITS))
                    body=validate_wire(json.loads(self.rfile.read(length)),grant)
                    if body['max_tokens']!=host.callback_output_cap:raise ValueError('SDK_OUTPUT_GRANT_MISMATCH')
                    if host.call_relays>=1:raise ValueError('ONE_PROVIDER_CALL_PER_PI_CALLBACK')
                    host.call_relays+=1;host.model_calls+=1
                    save(host.root/'callbacks'/f'{host.callback_index:02d}'/'wire-public.json',body)
                    request=urllib.request.Request(SERVICE+self.path,data=encoded(body),headers={'Authorization':'Bearer '+host.token,'Content-Type':'application/json'})
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=min(310,max(1,900-(time.monotonic()-host.started)))) as response:
                        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                        for line in response:
                            if line.startswith(b'data:') and line.strip()!=b'data: [DONE]':
                                data=json.loads(line[5:])
                                if data.get('model') and data['model']!='deepseek-flash':
                                    host.fatal='RESPONSE_MODEL_MISMATCH';raise ValueError(host.fatal)
                            self.wfile.write(line);self.wfile.flush()
                except Exception as e:
                    host.relay_error=type(e).__name__+':'+str(e)[:400]
                    try:self.send_error(400,host.relay_error)
                    except OSError:pass
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def planner(self,request):
        budget=self.ready(paid=True);before=ledger(DATABASE,self.owner)
        requested=request.get('max_output_tokens')
        allowance=output_allowance(budget['output_tokens'],LIMITS)
        if type(requested) is not int or not 1<=requested<=allowance:raise ValueError('CALLBACK_OUTPUT_GRANT_INVALID')
        self.callback_output_cap=requested
        self.callback_index=1+len(list((self.root/'callbacks').glob('*'))) if (self.root/'callbacks').exists() else 1
        folder=self.root/'callbacks'/f'{self.callback_index:02d}';folder.mkdir(parents=True)
        self.call_relays=0;self.relay_error=None
        payload=callback_payload(request,self.callback_output_cap)
        config={'sdk_entry':str(SDK),'workspace':str(folder/'participant'),
          'service':'http://127.0.0.1:'+str(self.server.server_port),'token':self.access_token,
          **payload}
        save(folder/'input-public.json',payload)
        with (folder/'pi-public.jsonl').open('w') as stdout,(folder/'stderr.log').open('w') as stderr:
            proc=subprocess.Popen(['/opt/homebrew/bin/node',str(APP/'scripts/pqe_pi_callback.mjs')],
                cwd=folder,env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','LANG':'en_US.UTF-8'},stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,start_new_session=True)
            try:proc.communicate(encoded(config)+b'\n',timeout=max(1,900-(time.monotonic()-self.started)))
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                self.fatal='EPISODE_WALL_CAP'
        after=ledger(DATABASE,self.owner);old={r['id'] for r in before['rows']};rows=[r for r in after['rows'] if r['id'] not in old]
        usage={'status':'UNKNOWN','model_identity':MODEL_IDENTITY,'request_ids':[r['id'] for r in rows]}
        if len(rows)==1 and rows[0]['status']=='SETTLED' and rows[0]['usage']:
            raw_usage=json.loads(rows[0]['usage']);usage.update(status='KNOWN',cost=rows[0]['charged'],input_tokens=raw_usage['prompt_tokens'],output_tokens=raw_usage['completion_tokens'])
            if usage['output_tokens']>self.callback_output_cap or budget['output_tokens']+usage['output_tokens']>LIMITS['generated_tokens']:
                self.fatal='PROVIDER_OUTPUT_CAP_EXCEEDED'
            if rows[0]['error'] and rows[0]['error'].startswith(('PROVIDER_RESERVATION','PROVIDER_TOKEN')):
                self.fatal=rows[0]['error']
        else:self.fatal='PROVIDER_USAGE_NOT_SETTLED'
        records=[json.loads(l) for l in (folder/'pi-public.jsonl').read_text().splitlines() if l.strip()]
        loaded=[v for v in records if v.get('type')=='pqe_pi_loaded'];answers=[v for v in records if v.get('type')=='assistant_public']
        payload={'status':'INVALID_PLANNER_OUTPUT'};error=self.relay_error
        provider_status='PARSE_OR_TRANSPORT_ERROR' if error else 'COMPLETE'
        try:
            if proc.returncode:raise ValueError('PI_PROCESS_EXIT:'+str(proc.returncode))
            if len(loaded)!=1 or loaded[0]['tools'] or loaded[0]['history_messages']:raise ValueError('PI_CONTEXT_OR_TOOL_BOUNDARY')
            if len(answers)!=1 or answers[0].get('stopReason')!='stop':raise ValueError('PI_STOP_REASON:'+str(answers[-1].get('stopReason') if answers else None))
            if any(v['type']!='text' for v in answers[0]['content']):raise ValueError('MODEL_TOOL_OUTPUT_DENIED')
            answer_text=''.join(v['text'] for v in answers[0]['content'])
            try:payload=json.loads(answer_text)
            except json.JSONDecodeError as exc:
                if (PACKAGE not in {'BF-PQE-S3-E2DEV-20261023-001', 'BF-PQE-S3-F1FIRST-20261023-001', 'BF-PQE-S3-E2MAIN-20261023-001', 'BF-PQE-S3-E3LC-20261023-001'} or error or self.fatal or
                        usage['status']!='KNOWN' or len(rows)!=1 or rows[0]['error']):
                    raise
                # Complete normal-stop output only. The original text stays in
                # pi-public/session evidence; no candidate is extracted or fixed.
                payload={'status':'JSON_SYNTAX_ERROR','syntax_error':{
                    'kind':'JSONDecodeError','line':exc.lineno,'column':exc.colno,'position':exc.pos},
                    'original_output_sha256':hashlib.sha256(answer_text.encode()).hexdigest()}
                error=str(exc);provider_status='COMPLETE'
            if not isinstance(payload,dict):raise ValueError('JSON_OBJECT_REQUIRED')
        except (ValueError,KeyError) as e:
            error=str(e);provider_status='PARSE_OR_TRANSPORT_ERROR'
        result={'payload':payload,'usage':usage,'request_ids':[r['id'] for r in rows],
                'provider_status':provider_status,'error':error,
                'granted_max_output_tokens':self.callback_output_cap,'output_budget_before':budget['output_tokens'],
                'output_budget_after':self.budget()['output_tokens']}
        save(folder/'callback-result.json',result)
        print(json.dumps({'episode':self.ident,'callback':self.callback_index,'site':request.get('site'),
                          'usage':usage['status'],'error':error}),flush=True)
        return result

    def consume(self,decision):
        self.ready();self.tools+=1
        if self.tools>24:raise ValueError('EPISODE_TOOL_CAP')
        submitted=decision['actual_input']
        if submitted.get('operation') not in {'report','select'}:
            candidate_key=identity({**self.design,**submitted.get('design_patch',{})})
            if candidate_key not in self.candidates and len(self.candidates)>=LIMITS['candidates']:raise ValueError('EPISODE_CANDIDATE_CAP')
            self.candidates.add(candidate_key)
        actual=common_contract_check({'task':self.task,'design':self.design,'problem':self.problem},submitted,{'remaining_actions':25-self.tools})
        design={**self.design,**actual.get('design_patch',{})};problem={**self.problem,**actual.get('problem_patch',{})}
        adapter.validate_design(self.task,design)
        dt=actual.get('dt_s',self.task['integration']['dt_s'])
        key=execution_cache_key(self.task,design,dt,self.protocol['apparatus_source']) if self.protocol.get('scientific_source') else identity({'task':self.task,'design':design,'dt':dt,'source':self.protocol['apparatus_source']})
        target=decision.get('selected_candidate',{}).get('target','');op=actual['operation'];output=self.root/'actions'/f'{self.tools:02d}'
        if op in {'report','select'}:
            public=adapter.execute(self.task,self.design,self.problem,decision,output,
                                   task_resolver=getattr(self,'task_resolver',None))
        elif key in self.cache:
            previous=self.cache[key];public=project_result(json.loads((previous/'public-result.json').read_text()));public['problem']=problem
            public['usage']={'paid_model_requests':0,'numerical_inputs':0,'reused':True,'wall_s':0}
            output.mkdir(parents=True);save(output/'reused.json',{'source':str(previous),'exact_key':key,'decision':decision,'actual_design':design,'problem':problem,'source_result_sha256':public.get('result_sha256'),'public_projection_version':PROJECTION_VERSION})
            save(output/'public-result.json',public)
        else:
            if self.numerical>=LIMITS['numerical_inputs']:raise ValueError('EPISODE_NUMERICAL_CAP')
            self.numerical+=1
            public=adapter.execute(self.task,self.design,self.problem,decision,output,
                                   task_resolver=getattr(self,'task_resolver',None));self.cache[key]=output
        self.last_full=public if public['execution_status']!='NO_EXECUTION' else self.last_full
        if public['execution_status']!='NO_EXECUTION':self.design,self.problem=design,problem
        compact=compact_result(public,target);save(output/'public-compact.json',compact)
        self.actions.append({'number':self.tools,'operation':op,'selected_id':decision.get('selected_id'),
            'target':target,'candidate_evaluation':op not in {'report','select'} and not target.startswith('detail:'),
            'actual_input':actual,'path':str(output),'public_check':compact['public_check'],'usage':compact['usage']})
        return compact

    def close(self):
        if self.server:self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        close_owner(self.owner,self.token)

def initial_observation(protocol,task_id=None,*,task_resolver=None):
    binding=protocol.get('initial_observation')
    if protocol.get('initial_observations'):
        if task_id is None:raise ValueError('MULTI_TASK_INITIAL_REQUIRES_TASK_ID')
        binding=protocol['initial_observations'].get(task_id)
    if not binding:return None
    path=Path(binding['public_result_path'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=binding['public_result_sha256']:
        raise ValueError('FROZEN_INITIAL_PUBLIC_RESULT_CHANGED')
    result=json.loads(path.read_text())
    source_matches=(scientific_source_identity(result['sources'])==protocol['scientific_source']) if protocol.get('scientific_source') else result['sources']==protocol['apparatus_source']
    if not source_matches or result['task_sha256']!=identity((task_resolver or adapter.load_task)(result['task_id'])):
        raise ValueError('INITIAL_RESULT_SOURCE_OR_TASK_MISMATCH')
    return project_result(result)

def episode_initial_state(task,design,problem,initial=None):
    state={'task':public_task(task),'design':deepcopy(design),'problem':deepcopy(problem),'history':[],'evidence':[]}
    if initial is not None:
        if initial['design']!=design or initial['problem']!=problem or initial['task_id']!=task['task_id']:
            raise ValueError('INITIAL_OBSERVATION_INPUT_MISMATCH')
        compact=compact_result(initial)
        record={'origin':'DEVELOPER_PROVIDED_INITIAL_OBSERVATION','agent_selected':False,
                'charged_to':'shared initial-mechanism budget; not this episode tool/numerical quota',
                'result':compact}
        state.update(last_result=compact,history=[deepcopy(record)],evidence=[deepcopy(record)])
    return state


def freeze():
    path=PROTOCOL_PATH
    if path.exists():raise ValueError('PROTOCOL_ALREADY_FROZEN')
    verification=json.loads((BASE/'s0/verification.json').read_text())
    files=['packages/python/bfworld/src/bfworld/agentlab/pqe20261022/pilot.py',
           'packages/python/bfworld/src/bfworld/agentlab/pqe20261022/episode_methods.py',
           'scripts/pqe_pi_callback.mjs','scripts/pqe_pilot.py']
    protocol={'package':PACKAGE,'frozen_at':datetime.now(timezone.utc).isoformat(),
      'cells':CELLS,'limits_per_episode':LIMITS,'total_caps':TOTAL_CAPS,
      'same_backend':{'provider':'deepseek','request_and_response_model':'deepseek-flash','profile':PROFILE,
        'thinking':'enabled','reasoning_effort':'high','temperature':.2,'max_tokens':LIMITS['output_tokens'],
        'identity_scope':'Provider alias and version naming; exact upstream immutable weights not supplied'},
      'provider_service':SERVICE,'provider_database':str(DATABASE),'sdk_entry':str(SDK),
      'new_source_bindings':{str(APP/p):hashlib.sha256((APP/p).read_bytes()).hexdigest() for p in files},
      'apparatus_source':{Path(k).name:v for k,v in verification['source_hashes'].items() if Path(k).name in ['door_model.py','executor.py','evaluator.py','adapter.py']},
      'apparatus_evidence_reused':str(BASE/'s0/verification.json'),
      'participant_tools':[],'host_broker_operations':sorted(adapter.OPERATIONS),
      'model_input':'Clean callback request plus public-only result registry; no developer conversation, private assessment/reference files or source access.',
      'callback_context':'Fresh Pi SDK session per method callback; complete method-supplied public state/history, common deterministic list projection and public page access.',
      'scope':str(len(CELLS))+' development cells, fixed trusted H, no H/G formation; no forced restructuring, no statistical or hardware claim.',
      'authority':'BF-PQE-20261022-001 direct user all-stage approval; reviewer dispatch '+PACKAGE,
      'old_unknown':'Only exact unchanged historical exception; no new missing-usage carryforward.',
      'resource_reuse':'Existing SDK/environment/service; new finite owner grants, no unbounded method_authorize.',
      'no_rerun':'Each cell once; failed/unrun cells retained; no replacements or quota transfer.'}
    protocol['contract_correction_limit']=CONTRACT_CORRECTIONS
    if PACKAGE in {'BF-PQE-S2-D15-20261022-001','BF-PQE-S2-M3-20261023-001','BF-PQE-S3-E2DEV-20261023-001'}:
        protocol['apparatus_source']=adapter.source_identity()
        protocol['scientific_source']=scientific_source_identity(protocol['apparatus_source'])
        protocol['apparatus_evidence_reused']=str(BASE/'stage2-engineering/s0/RESULTS.json')
        for name in ['public_projection.py','adapter.py','methods.py']:
            source=Path(adapter.__file__).with_name(name)
            protocol['new_source_bindings'][str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
        protocol['public_projection_version']=PROJECTION_VERSION
        protocol['public_boundary_release']=require_public_release()
        if PACKAGE=='BF-PQE-S3-E2DEV-20261023-001':
            registry=OUT/'s0/input-registry.json';binding=json.loads(registry.read_text())
            protocol['initial_observations']=binding['initial_observations']
            protocol['scientific_cache']=binding.get('scientific_cache',[])
            protocol['task_exclusions']=binding.get('task_exclusions',{})
            count=sum(v['actual_initial_numerical_inputs'] for v in protocol['initial_observations'].values())
            if type(count) is not int or not 0<=count<=3:raise ValueError('E2DEV_SHARED_INITIAL_CAP')
            protocol['input_registry']={'path':str(registry),'sha256':hashlib.sha256(registry.read_bytes()).hexdigest()}
            conditions=APP/'studies/pqe20261022/shared/e2dev-conditions.json'
            protocol['condition_definitions']=json.loads(conditions.read_text())
            protocol['new_source_bindings'][str(conditions)]=hashlib.sha256(conditions.read_bytes()).hexdigest()
            protocol['output_feedback_protocol']='pqe-complete-output-shared-corrections-v2'
            protocol['exposure']='Previously exposed development Tasks; new common protocol, separate from old pilot data; not unseen transfer.'
            for task_id in protocol['initial_observations']:initial_observation(protocol,task_id)
        else:
            binding=json.loads((OUT/'s0/initial-projection.json').read_text())
            protocol['initial_observation']=binding['initial_observation']
            count=protocol['initial_observation']['actual_initial_numerical_inputs']
            if PACKAGE=='BF-PQE-S2-D15-20261022-001' and count!=0:raise ValueError('D15_INITIAL_MUST_REUSE')
        if PACKAGE=='BF-PQE-S2-M3-20261023-001':
            if type(count) is not int or count!=1:raise ValueError('M3_INITIAL_MUST_BE_ONE')
            qualification=OUT/'a/A-QUALIFICATION.json'
            if json.loads(qualification.read_text())['status']!='QUALIFIED_CURRENT_P_EXCLUDED_GLOBAL_UNKNOWN':
                raise ValueError('M3_ANALYTIC_QUALIFICATION_REQUIRED')
            protocol['analytic_qualification']={'path':str(qualification),
                'sha256':hashlib.sha256(qualification.read_bytes()).hexdigest()}
        if protocol.get('initial_observation'):initial_observation(protocol)
    elif INITIAL_ACTION is not None:
        classification=json.loads((OUT/'a/initial-classification.json').read_text())
        if not classification['eligible_for_paid_pair']:raise ValueError('INITIAL_MECHANISM_NOT_ESTABLISHED_NO_PAID_PAIR')
        count=classification['actual_initial_numerical_inputs']
        if type(count) is not int or not 1<=count<=2:raise ValueError('INITIAL_NUMERICAL_CAP')
        result_path=INITIAL_ACTION/'public-result.json'
        protocol['initial_observation']={'public_result_path':str(result_path),
            'public_result_sha256':hashlib.sha256(result_path.read_bytes()).hexdigest(),
            'origin':'DEVELOPER_PROVIDED_INITIAL_OBSERVATION','actual_initial_numerical_inputs':count,
            'classification_receipt':str(OUT/'a/initial-classification.json')}
        initial_observation(protocol)
    materials=PUBLIC_MATERIALS_PATH
    if materials.exists():
        frozen=json.loads(materials.read_text())
        for _,task_id,_ in CELLS:
            if public_task(adapter.load_task(task_id))!=frozen[task_id]:raise ValueError('PUBLIC_MATERIALS_CHANGED')
    else:save(materials,{task_id:public_task(adapter.load_task(task_id)) for _,task_id,_ in CELLS})
    save(path,protocol)
    return protocol

def run_cell(cell,protocol,cache,*,task_resolver=None,driver_factory=None,
             episode_factory=None,initial_state_factory=None,initial_observation_factory=None):
    from .episode_methods import EpisodeDriver
    ident,task_id,condition=cell
    ep=(episode_factory or Episode)(ident,task_id,condition,protocol,cache,task_resolver=task_resolver);driver=None;error=None
    try:
        ep.start_server()
        initial=(initial_observation_factory or initial_observation)(protocol,task_id,task_resolver=task_resolver)
        state=(initial_state_factory or episode_initial_state)(ep.task,ep.design,ep.problem,initial)
        if initial is not None:ep.last_full=initial
        driver=(driver_factory or EpisodeDriver)(condition,ep.planner,episode_id=ident,initial_state=state,
                             model_identity=MODEL_IDENTITY,request_reserve_usd=.19,
                              expected_methods_sha256=protocol.get('source_bindings',{}).get(str(Path(__file__).with_name('methods.py'))),
                             limits={'output_tokens_per_request':LIMITS['output_tokens'],'output_tokens_total':LIMITS['generated_tokens'],
                                     'new_numerical_inputs':LIMITS['numerical_inputs']},
                             max_contract_corrections=protocol.get('contract_correction_limit',0))
        while True:
            evaluation_cap=protocol.get('max_candidate_evaluations')
            if evaluation_cap is not None and sum(a.get('candidate_evaluation',False) for a in ep.actions)>=evaluation_cap:
                driver.finish('CANDIDATE_EVALUATION_CAP');break
            b=ep.ready();snapshot={'provider_requests_remaining':12-b['model_requests'],
                'tool_calls_remaining':24-b['tool_calls'],'new_numerical_inputs_remaining':LIMITS['numerical_inputs']-b['numerical_inputs'],
                'reserve_usd_remaining':4-b['spent_usd'],'wall_s_remaining':900-b['wall_s'],
                'output_tokens_remaining':LIMITS['generated_tokens']-b['output_tokens']}
            action=driver.next(snapshot)
            save(ep.root/'method-transcript.json',driver.transcript())
            if action['status']!='ACTION':break
            try:result=ep.consume(action['decision'])
            except (ValueError,KeyError,TypeError) as exc:
                result={'schema_version':'pqe-public-result-v1','execution_status':'TOOL_ERROR',
                    'task_id':task_id,'design':ep.design,'problem':ep.problem,'model_valid':None,
                    'facts':{'tool_error':str(exc)},'public_check':{'verdict':'UNKNOWN','failures':[],
                    'unknown':['TOOL_ERROR']},'usage':{'numerical_inputs':0,'paid_model_requests':0}}
                save(ep.root/'tool-errors'/f'{ep.tools:02d}.json',{'decision':action['decision'],'result':result})
            driver.update(result)
            save(ep.root/'method-transcript.json',driver.transcript())
    except Exception as exc:
        error=type(exc).__name__+':'+str(exc)
        if driver:driver.finish(error)
    finally:
        ep.close()
    account=ledger(DATABASE,ep.owner);save(ep.root/'provider-costs.json',account)
    transcript=driver.transcript() if driver else None
    if transcript:save(ep.root/'method-transcript.json',transcript)
    result={'episode':ident,'task_id':task_id,'condition':condition,'owner':ep.owner,
       'status':'COMPLETED_FINITE_ATTEMPT' if not error else 'STOPPED_WITH_ERROR','error':error,'fatal':ep.fatal,
       'wall_s':time.monotonic()-ep.started,'actions':ep.actions,'actual_tools':ep.tools,
       'actual_new_numerical_inputs':ep.numerical,'distinct_attempted_designs':len(ep.candidates),
       'last_design':ep.design,'last_problem':ep.problem,'last_public_service':ep.last_full['public_check'] if ep.last_full else None,
       'accounting':{k:v for k,v in account.items() if k!='rows'},'method_conclusion':transcript.get('model_conclusion') if transcript else None,
       'initial_observation_origin':'DEVELOPER_PROVIDED_INITIAL_OBSERVATION' if protocol.get('initial_observation') or protocol.get('initial_observations') else None,
       'interpretation':'Actual Pi fixed-method development attempt, not H learning or method efficacy.',
        'termination':transcript.get('termination') if transcript else None,
       'native_calls':0,'hardware_runs':0}
    save(ep.root/'episode-result.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

def run_all():
    protocol=json.loads(PROTOCOL_PATH.read_text())
    if protocol['package']!=PACKAGE or protocol['limits_per_episode']!=LIMITS or protocol['cells']!=[list(c) for c in CELLS]:raise ValueError('PROTOCOL_RESOURCE_MISMATCH')
    if PACKAGE in {'BF-PQE-S2-D15-20261022-001','BF-PQE-S2-M3-20261023-001','BF-PQE-S3-E2DEV-20261023-001'} and require_public_release()!=protocol['public_boundary_release']:
        raise ValueError('PUBLIC_BOUNDARY_RELEASE_CHANGED')
    if PACKAGE=='BF-PQE-S2-M3-20261023-001':
        qualification=protocol['analytic_qualification']
        if hashlib.sha256(Path(qualification['path']).read_bytes()).hexdigest()!=qualification['sha256']:
            raise ValueError('M3_ANALYTIC_QUALIFICATION_CHANGED')
    if PACKAGE=='BF-PQE-S3-E2DEV-20261023-001':
        binding=protocol['input_registry']
        if hashlib.sha256(Path(binding['path']).read_bytes()).hexdigest()!=binding['sha256']:
            raise ValueError('E2DEV_INPUT_REGISTRY_CHANGED')
    # New integration bindings only; prior qualification is reused without a rerun.
    for p,h in protocol['new_source_bindings'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('FROZEN_PILOT_CODE_CHANGED')
    receipts=[];cache={};prior=None;installed=False
    if PACKAGE=='BF-PQE-S2-PILOT2-20261022-001':
        previous=BASE/'stage2-pilot1/s0/episodes/d04-full-h/actions/01'
        public=json.loads((previous/'public-result.json').read_text());raw=json.loads((previous/'raw.json').read_text())
        task=adapter.load_task('DOOR-DEV-D04-v1')
        if public['sources']!=protocol['apparatus_source'] or public['task_sha256']!=identity(task) or raw['design']!=task['initial_design']:raise ValueError('CACHE_EXACT_BINDING_MISMATCH')
        key=identity({'task':task,'design':raw['design'],'dt':raw['dt_s'],'source':public['sources']})
        cache[key]=previous
    initials=protocol.get('initial_observations',{})
    if protocol.get('initial_observation'):
        single=protocol['initial_observation'];public=json.loads(Path(single['public_result_path']).read_text())
        initials={public['task_id']:single}
    cache_bindings=[(task_id,binding) for task_id,binding in initials.items()]
    cache_bindings.extend((binding['task_id'],binding) for binding in protocol.get('scientific_cache',[]))
    for task_id,binding in cache_bindings:
        result_path=Path(binding['public_result_path'])
        if hashlib.sha256(result_path.read_bytes()).hexdigest()!=binding['public_result_sha256']:
            raise ValueError('FROZEN_SHARED_CACHE_RESULT_CHANGED')
        public=project_result(json.loads(result_path.read_text()));task=adapter.load_task(task_id)
        if public['task_id']!=task_id or public['task_sha256']!=identity(task):raise ValueError('SHARED_CACHE_TASK_CHANGED')
        if protocol.get('scientific_source') and scientific_source_identity(public['sources'])!=protocol['scientific_source']:
            raise ValueError('SHARED_CACHE_SCIENCE_CHANGED')
        previous=result_path.parent
        raw_path=Path(binding.get('source_raw_path',str(previous/'raw.json')))
        raw=json.loads(raw_path.read_text())
        if raw['result_sha256']!=public['result_sha256'] or raw['design']!=public['design']:
            raise ValueError('INITIAL_RAW_BINDING_MISMATCH')
        key=execution_cache_key(task,public['design'],raw['dt_s'],public['sources']) if protocol.get('scientific_source') else identity({'task':task,'design':public['design'],'dt':raw['dt_s'],'source':public['sources']})
        cache[key]=previous
    lock=OUT/'s0/active.lock'
    with lock.open('x') as f:f.write(str(os.getpid()))
    try:
        free=os.statvfs(OUT).f_bavail*os.statvfs(OUT).f_frsize
        minimum_free=11_000_000_000 if PACKAGE=='BF-PQE-S3-E2DEV-20261023-001' else (10_500_000_000 if PACKAGE=='BF-PQE-S2-M3-20261023-001' else 10_300_000_000)
        if free<minimum_free:raise ValueError('BATCH_STORAGE_RESERVE')
        with dbconnect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():raise ValueError('OTHER_PROVIDER_REQUEST_ACTIVE')
            row=db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone();prior=row['value'] if row else None
            db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps('per-owner'),))
            installed=True
        save(OUT/'s0/runtime-registration.json',{'at':datetime.now(timezone.utc).isoformat(),
          'budget_scope_before':prior,'temporary_budget_scope':'per-owner','finite_owner_cap_usd':4,'finite_study_cap_usd':TOTAL_CAPS['usd'],
          'unbounded_policy_changed':False,'old_model_rows_changed':False,'free_before_bytes':free})
        for cell in CELLS:
            if receipts and (receipts[-1].get('fatal') or receipts[-1].get('accounting',{}).get('unknown_or_missing_usage')):break
            if cell[1] in protocol.get('task_exclusions',{}):
                receipts.append({'episode':cell[0],'task_id':cell[1],'condition':cell[2],
                    'status':'NOT_RUN_TASK_INITIAL_NOT_QUALIFIED','reason':protocol['task_exclusions'][cell[1]]})
                continue
            receipts.append(run_cell(cell,protocol,cache))
    finally:
        if installed:
            with dbconnect() as db:
                current=db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
                if current and current['value']==json.dumps('per-owner'):
                    if prior is None:db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
                    else:db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'",(prior,))
                db.execute('UPDATE research_model_studies SET expires=? WHERE protocol=?',(time.time(),PACKAGE))
        lock.unlink()
        missing=[{'episode':c[0],'status':'NOT_RUN_DEPENDENT_DISPATCH_STOP'} for c in CELLS if c[0] not in {x['episode'] for x in receipts}]
        save(OUT/'s0/batch-result.json',{'package':PACKAGE,'episodes':receipts+missing,
             'completed_at':datetime.now(timezone.utc).isoformat(),'budget_scope_restored':installed,
             'actual_requests':sum(x.get('accounting',{}).get('requests',0) for x in receipts),
             'actual_new_numerical_inputs':sum(x.get('actual_new_numerical_inputs',0) for x in receipts),
             'shared_initial_numerical_inputs':sum(v['actual_initial_numerical_inputs'] for v in initials.values()),
             'retained_bytes':output_bytes(OUT),'free_after_bytes':os.statvfs(OUT).f_bavail*os.statvfs(OUT).f_frsize})
    return receipts
