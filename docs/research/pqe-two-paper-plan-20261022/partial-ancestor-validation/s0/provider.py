"""Actual accounted Pi callbacks with shared bounded JSON/DSML recovery."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
import secrets
import time
from common import *
from bfworld.agentlab.pqe20261024debt import adapter

runtime=DB.parents[2]
profile=load(runtime/'profile.json')
os.environ.update(BF_RUNTIME_ROOT=str(runtime),BF_RUNTIME_CONFIG=str(runtime/'runtime.json'),
    BF_HOME=profile['home'],BF_PI_ROOT=profile['pi_root'],BF_DEVELOPMENT_PROFILE=str(runtime/'profile.json'),
    PI_CODING_AGENT_DIR=str(Path(profile['home'])/'pi-config'),PYTHONDONTWRITEBYTECODE='1')
spec=importlib.util.spec_from_file_location('partial_existing_transport',BASE/'lc-service-learning/s0/runtime.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
p=transport.p
fmt_spec=importlib.util.spec_from_file_location('partial_saved_format',BASE/'codebt-zeroapi/s0/model_format.py')
formatter=importlib.util.module_from_spec(fmt_spec);fmt_spec.loader.exec_module(formatter)
LIMITS=dict(model_requests=12,tool_calls=24,numerical_inputs=18,candidates=6,wall_s=900,
    output_tokens=32768,generated_tokens=131072,usd=5,bytes=40_000_000)
p.OUT,p.PACKAGE,p.LIMITS,p.APP=OUT,PACKAGE,LIMITS,APP
p.SDK=Path(load(OUT/'shared/provider-binding.json')['sdk']['path'])
p.CELLS=[(key,) for key in load(OUT/'shared/provider-binding.json')['owners']]
p.TOTAL_CAPS=dict(requests=72,tool_calls=144,numerical_inputs=432,usd=30,retained_bytes=200_000_000)
p.callback_payload=transport.legacy.callback_payload


def normalize_response_text(text):
    return formatter.parse_model_output(text)


class PublicObjects(transport.legacy.PublicObjects):
    def register(self,value,*,path=None):
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        sha=hashlib.sha256(raw).hexdigest();ident='pub-'+sha
        if ident not in self.objects:
            target=self.folder/(ident+'.json.gz')
            if not target.exists():adapter._write_gzip(target,value)
            self.objects[ident]=dict(path=str(target),sha256=sha,serialized_bytes=len(raw))
            if isinstance(value,dict) and value.get('result_sha256') and 'facts' in value:
                self.results[value['result_sha256']]=ident
        return ident

    def _get(self,ident):
        if ident not in self.objects:raise ValueError('UNKNOWN_PUBLIC_OBJECT')
        item=self.objects[ident];value=load(item['path'])
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('PUBLIC_OBJECT_CHANGED')
        return value


class Episode(p.Episode):
    start_server=transport.LCEpisode.start_server

    def __init__(self,ident,family,initial):
        self.ident=ident;self.owner=load(OUT/'shared/provider-binding.json')['owners'][ident]
        self.token=secrets.token_urlsafe(32);self.access_token=secrets.token_urlsafe(32)
        self.limits=LIMITS;self.root=HERE/'episodes'/ident;self.root.mkdir(parents=True,exist_ok=False)
        self.started=time.monotonic();self.model_calls=self.tools=self.numerical=0
        self.candidates=set();self.actions=[];self.fatal=None;self.server=self.thread=None
        self.family=family;self.initial=initial;self.history=[];self.format_errors=0
        self.objects=PublicObjects(HERE/'public-objects')
        deadline=min(time.time()+900,load(HERE/'preflight.json')['absolute_deadline_epoch'])
        with connect() as db:
            assert not db.execute('SELECT 1 FROM research_model_owners WHERE owner=?',(self.owner,)).fetchone()
            assert not db.execute('SELECT 1 FROM model_requests WHERE owner=?',(self.owner,)).fetchone()
            db.execute('INSERT INTO principals VALUES(?,?,?)',(hashlib.sha256(self.token.encode()).hexdigest(),self.owner,'participant'))
            db.execute('INSERT INTO grants VALUES(?,?,?,?)',(self.owner,json.dumps([PACKAGE]),0,deadline))
            db.execute('INSERT INTO owner_model_caps VALUES(?,?)',(self.owner,5))
            db.execute('INSERT INTO settings VALUES(?,?)',('model_profile:'+self.owner,json.dumps(p.PROFILE)))
            db.execute('INSERT OR IGNORE INTO research_model_studies VALUES(?,?,?,?,?,?)',
                (PACKAGE,time.time(),load(HERE/'preflight.json')['absolute_deadline_epoch'],30.,'deepseek-flash',
                 'Direct human full-validation authority; frozen BFA099 original finite package and workorder10.'))
            db.execute('INSERT INTO research_model_owners VALUES(?,?,?)',(self.owner,PACKAGE,ident))
        accounting_gate(self.owner)
        save(self.root/'owner.json',dict(owner=self.owner,ident=ident,limits=LIMITS,activated_at=now(),expires=deadline))
        self.start_server()

    def ready(self,paid=False):
        require_capacity_and_time();protocol=load(OUT/'shared/protocol.json');require_sources(protocol)
        if protocol['status']!='FROZEN_FOR_COMPARISON':raise RuntimeError('METHOD_GATE_CLOSED')
        if self.fatal:raise RuntimeError(self.fatal)
        b=self.budget();accounting_gate(self.owner)
        if b['wall_s']>=900 or self.tools>24:raise RuntimeError('EPISODE_WALL_OR_TOOL_CAP')
        if sum(x.stat().st_blocks*512 for x in self.root.rglob('*') if x.is_file())>=40_000_000:
            raise RuntimeError('EPISODE_RETAINED_CAP')
        with connect() as db:
            rows=[dict(r) for r in db.execute('SELECT mr.* FROM model_requests mr JOIN research_model_owners ro ON mr.owner=ro.owner WHERE ro.protocol=?',(PACKAGE,))]
        held=sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows)
        if paid and (b['model_requests']>=12 or b['output_tokens']>=131072 or b['spent_usd']+.2>5
                     or len(rows)>=72 or held+.2>30):raise RuntimeError('FINITE_PAID_CAP')
        return b

    def paid_callback(self,request):
        result=transport.LCEpisode.paid_callback(self,request)
        folder=self.root/'callbacks'/f'{self.callback_index:02d}'
        if result.get('provider_status')=='COMPLETE' and result.get('usage',{}).get('status')=='KNOWN':
            records=[json.loads(line) for line in (folder/'pi-public.jsonl').read_text().splitlines() if line.strip()]
            answers=[row for row in records if row.get('type')=='assistant_public']
            if len(answers)==1:
                text=''.join(row['text'] for row in answers[0]['content'])
                normalized=normalize_response_text(text)
                result['payload']=normalized['payload'] if normalized['status']=='OK' else dict(status='FORMAT_ERROR',error=normalized.get('error'))
                result['normalization']=dict(status=normalized['status'],format=normalized.get('format'),
                    source_sha256=ref(BASE/'codebt-zeroapi/s0/model_format.py')['sha256'],raw_sha256=hashlib.sha256(text.encode()).hexdigest())
                save(folder/'callback-result.json',result)
        return result

    @staticmethod
    def public_result(value):
        row=deepcopy(value)
        for key in ('reused','new_full_wall_s','canonical_public_path','cache_origin'):row.pop(key,None)
        if 'results' in row:row['results']=[Episode.public_result(v) for v in row['results']]
        return row

    def query(self,controller,last=None):
        context=dict(site='strong_generic_joint_design',
            task_family=[p.public_task(t) for t in self.family],
            current_nodes=[dict(id=n.id,design=n.design,summary=n.summary) for n in controller.nodes.values()],
            initial_results=self.public_result(self.initial),
            own_evaluated_results=[self.public_result(v) for v in self.history],
            shared_components='component_contract contains source-bound static part facts; relationship_view contains observed facts; no private qualification is available.',
            site_contract=dict(outputs=[{'design':'complete legal design object','parent_id':'optional evaluated node id'},
                {'candidate_tool':{'parent_id':'optional evaluated node id'}},
                {'final_design':'explicit already evaluated full design object'},
                {'tool_calls':[{'name':'public_object','arguments':{'object_id':'pub-64hex','section':'RFC6901','offset':0}}]}],
                tools_budget=24,max_design_slots_including_initial=6,
                freedom='Any legal full joint design, direct jumps allowed; shared factory optional. Final result must be selected explicitly if no full PASS.',
                interpretation='Absent stages are UNKNOWN, not loss. Numeric seq is not globally unique. No code execution or private reference designs.'),
            remaining=dict(design_slots=6-controller.slots,requests=12-self.budget()['model_requests'],tools=24-self.tools),
            last_feedback=last)
        while True:
            self.ready(paid=True)
            request=self.objects.project(context)
            request['max_output_tokens']=p.output_allowance(self.budget()['output_tokens'],LIMITS)
            request['PUBLIC_TOOLS']=[dict(name='public_object',arguments={'object_id':'pub-...','section':'','offset':0})]
            result=self.paid_callback(request)
            if result.get('usage',{}).get('status')!='KNOWN':raise RuntimeError('PROVIDER_USAGE_NOT_SETTLED')
            payload=result['payload']
            calls=payload.get('tool_calls')
            if not calls:return payload
            if len(calls)>24-self.tools:raise RuntimeError('PUBLIC_TOOL_CAP')
            pages=[]
            for call in calls:
                self.tools+=1
                try:pages.append(self.objects.read(call['arguments']))
                except Exception as exc:pages.append(dict(error=type(exc).__name__+':'+str(exc)))
            context['last_public_tool_results']=pages

    def close(self):
        if self.server:self.server.shutdown();self.server.server_close()
        p.close_owner(self.owner,self.token)
        save(self.root/'closeout.json',dict(at=now(),budget=self.budget(),fatal=self.fatal,
            ledger=p.ledger(DB,self.owner),credentials_closed=True))
