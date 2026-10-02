"""Credential-holding DeepSeek proxy with durable, fail-closed USD reservations."""
import hashlib
import json
import math
import secrets
import time
import urllib.request
from pathlib import Path
from .store import canonical
from .recovery import Recovery, ObservedHTTPSHandler, is_not_sent
from .context import ContextArchive, REQUEST_BYTES, project_interactive
from .request_evidence import describe as describe_request

MODEL='deepseek-flash'
RATE={'input_usd_per_million':.30,'output_usd_per_million':1.20,'cache_hit_usd_per_million':.006}
from .runtime_config import KEY_PATH
PRICING_SOURCE='https://api-docs.deepseek.com/quick_start/pricing/'
STREAM_SECONDS=300
STREAM_BYTES=2000000

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('PROVIDER_REDIRECT_DENIED')


class Provider:
    def __init__(self,store):
        self.store=store
        self.recovery=Recovery(store)
        with store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS model_limits(id INTEGER PRIMARY KEY CHECK(id=1), total_usd REAL NOT NULL,
              request_usd REAL NOT NULL, max_tokens INTEGER NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS model_requests(id TEXT PRIMARY KEY, owner TEXT NOT NULL, created REAL NOT NULL,
              request_hash TEXT NOT NULL, reserved REAL NOT NULL, charged REAL NOT NULL, status TEXT NOT NULL,
              usage TEXT, response_hash TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS model_request_context(request_id TEXT PRIMARY KEY,owner TEXT NOT NULL,
              message_id TEXT NOT NULL,created REAL NOT NULL,projection TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS model_request_evidence(request_id TEXT PRIMARY KEY,owner TEXT NOT NULL,
              created REAL NOT NULL,wire TEXT NOT NULL,receipt TEXT NOT NULL);
            ''')
            # Conservative engineering caps inside the user's <$0.20 / <$3 bounds.
            db.execute('INSERT OR IGNORE INTO model_limits VALUES (1,2.90,.19,9000000,?)',(time.time()+6*3600,))
            db.execute("UPDATE model_requests SET status='UNKNOWN' WHERE status='DISPATCHED'")

    @staticmethod
    def owner_cap(db, owner):
        explicit=db.execute('SELECT max_usd FROM owner_model_caps WHERE owner=?',(owner,)).fetchone()
        if explicit:return explicit['max_usd']
        if not owner.startswith('pi-chat-'):return None
        configured=db.execute("SELECT value FROM settings WHERE key='interactive_default_owner_usd'").fetchone()
        if not configured:return None
        cap=json.loads(configured['value'])
        if type(cap) not in (int,float) or not math.isfinite(cap) or cap<=0:raise ValueError('MODEL_CAP_INVALID')
        return cap

    def status(self):
        with self.store.connect() as db:
            limits=dict(db.execute('SELECT * FROM model_limits WHERE id=1').fetchone())
            resolved=self.recovery.resolved(db)
            rows=[dict(r) for r in db.execute('SELECT id,owner,created,reserved,charged,status,usage,error FROM model_requests ORDER BY created')]
            for row in rows:
                if row['id'] in resolved:row.update(source_status=row['status'],status='NOT_SENT',resolution='verified_pre_send_failure_reservation_retained')
        return {'provider':'deepseek','model_id':MODEL,'version':'DeepSeek-V4.1-Flash','status':'CONFIGURED' if KEY_PATH.exists() else 'NOT_CONFIGURED',
                'limits':limits,'upper_bound_usd':sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows),
                'calls':len(rows),'rates':RATE,'pricing_source':PRICING_SOURCE,'requests':rows}

    def complete(self,owner,payload,on_chunk=None):
        if (self.store.root.parent/"paid-window-closed.json").exists():raise ValueError("PAID_WINDOW_CLOSED")
        if payload.get('model')!=MODEL:raise ValueError('MODEL_ID_MISMATCH')
        with self.store.connect() as db:
            interactive=db.execute('SELECT 1 FROM interactive_leases WHERE owner=?',(owner,)).fetchone()
        projection=None
        if interactive:
            payload,projection=project_interactive(payload, ContextArchive(self.store.root.parent, owner))
        if len(canonical(payload).encode())>REQUEST_BYTES:
            self.store.event(owner, owner, 'model_context_rejected', projection or {
                'projected_bytes':len(canonical(payload).encode()), 'limit_bytes':REQUEST_BYTES})
            raise ValueError('MODEL_CONTEXT_BYTE_LIMIT')
        output=min(int(payload.get('max_tokens') or payload.get('max_completion_tokens') or 4096),8192)
        if output<1:raise ValueError('OUTPUT_LIMIT')
        if interactive and output<1024:raise ValueError('MODEL_OUTPUT_BUDGET_TOO_SMALL')
        body={k:payload[k] for k in ('model','messages','tools','tool_choice','temperature') if k in payload}
        body.update({'max_tokens':output,'stream':bool(on_chunk),'thinking':{'type':'disabled'}})
        if on_chunk:body['stream_options']={'include_usage':True}
        raw=canonical(body).encode()
        input_bound=len(raw)+4096
        reservation=(input_bound*.30+output*1.20)/1000000
        request_id='llm-'+secrets.token_hex(10)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            limit=db.execute('SELECT * FROM model_limits WHERE id=1').fetchone()
            grant=db.execute('SELECT * FROM grants WHERE owner=?',(owner,)).fetchone()
            self.recovery.check_window(db,owner,grant,limit)
            rows=list(db.execute('SELECT * FROM model_requests'))
            resolved=self.recovery.resolved(db)
            if self.recovery.unknown_blockers(db,owner):raise ValueError('PROVIDER_USAGE_UNKNOWN_STOP')
            if any(r['error']=='PROVIDER_RESERVATION_EXCEEDED' for r in rows):raise ValueError('PROVIDER_RESERVATION_EXCEEDED')
            held=sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows)
            used_tokens=sum(json.loads(r['usage'])['total_tokens'] if r['usage'] else 0 for r in rows)
            pending_tokens=sum(128000+4096+8192 for r in rows if r['status']=='DISPATCHED')
            lease=self.recovery.lease(db,owner)
            if lease:
                bindings={r['request_id']:r['message_id'] for r in db.execute('SELECT request_id,message_id FROM model_request_context WHERE owner=?',(owner,))}
                count=sum(r['owner']==owner and (bindings.get(r['id'])==lease['message_id'] or
                          r['id'] not in bindings and r['created']>=lease['created']) for r in rows)
                if count>=128:raise ValueError('CHAT_TURN_REQUEST_CAP')
            elif sum(r['owner']==owner for r in rows)>=24:raise ValueError('SESSION_REQUEST_CAP')
            owner_cap=self.owner_cap(db,owner)
            owner_held=sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows if r['owner']==owner)
            if owner_cap is not None and owner_held+reservation>=owner_cap:raise ValueError('MODEL_OWNER_USD_BUDGET')
            study=db.execute('SELECT s.* FROM research_model_studies s JOIN research_model_owners o ON o.protocol=s.protocol WHERE o.owner=?',(owner,)).fetchone()
            if study:
                if study['model'] != MODEL:raise ValueError('RESEARCH_MODEL_ID_MISMATCH')
                study_owners={r['owner'] for r in db.execute('SELECT owner FROM research_model_owners WHERE protocol=?',(study['protocol'],))}
                study_held=sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows if r['owner'] in study_owners)
                if study_held+reservation>=study['max_usd']:raise ValueError('RESEARCH_MODEL_USD_BUDGET')
            if reservation>=limit['request_usd'] or held+reservation>=limit['total_usd']:
                raise ValueError('MODEL_USD_BUDGET')
            if used_tokens+pending_tokens+input_bound+output>limit['max_tokens']:raise ValueError('MODEL_TOKEN_BUDGET')
            db.execute('INSERT INTO model_requests VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL)',
                       (request_id,owner,time.time(),hashlib.sha256(raw).hexdigest(),reservation,0.,'DISPATCHED'))
            evidence=describe_request(db,owner,body,raw)
            evidence['request_id']=request_id
            db.execute('INSERT INTO model_request_evidence VALUES(?,?,?,?,?)',
                       (request_id,owner,time.time(),raw.decode(),canonical(evidence)))
            if lease:
                db.execute('INSERT INTO model_request_context VALUES(?,?,?,?,?)',
                           (request_id,owner,lease['message_id'],time.time(),canonical({**projection,'max_output_tokens':output,'wire_sha256':hashlib.sha256(raw).hexdigest()})))
        self.store.event(owner,owner,'model_dispatched',{'request_id':request_id,'reserved_usd':reservation,'model_id':MODEL,
            'request_evidence_sha256':hashlib.sha256(canonical(evidence).encode()).hexdigest()})
        req=urllib.request.Request('https://api.deepseek.com/chat/completions',data=raw,
            headers={'Authorization':'Bearer '+KEY_PATH.read_text().strip(),'Content-Type':'application/json'})
        with self.store.connect() as db:
            continuation=self.recovery.usage_continuation(db,owner=owner)
        stream_seconds=min(1200,max(1,continuation['expires']-time.time())) if continuation else STREAM_SECONDS
        settled=False;observed_final_usage=None;chunks=[]
        transport={'request_id':request_id,'provider_request_id':None,'bytes':0,
                   'time_limit_s':stream_seconds,'byte_limit':STREAM_BYTES}
        def settle_usage(usage,data,output_error=None):
            nonlocal settled
            if not isinstance(usage,dict) or any(type(usage.get(k)) is not int or usage[k]<0 for k in ['prompt_tokens','completion_tokens','total_tokens']):
                raise ValueError('PROVIDER_USAGE_MISSING')
            if usage['prompt_tokens']+usage['completion_tokens']!=usage['total_tokens']:
                raise ValueError('PROVIDER_USAGE_INCONSISTENT')
            charge=(usage['prompt_tokens']*.30+usage['completion_tokens']*1.20)/1000000
            violation='PROVIDER_RESERVATION_EXCEEDED' if charge>reservation else 'PROVIDER_TOKEN_BOUND_VIOLATION' if usage['prompt_tokens']>input_bound or usage['completion_tokens']>output else None
            with self.store.connect() as db:
                db.execute("UPDATE model_requests SET status='SETTLED',charged=?,usage=?,response_hash=?,error=? WHERE id=?",
                           (charge,canonical(usage),hashlib.sha256(data).hexdigest(),violation or output_error,request_id))
            settled=True
            self.store.event(owner,owner,'model_settled',{'request_id':request_id,'upper_bound_usd':charge,'usage':usage,'output_error':violation or output_error})
            return violation
        try:
            with urllib.request.build_opener(NoRedirect(),ObservedHTTPSHandler()).open(req,timeout=90) as response:
                if on_chunk:
                    size=0;started=time.monotonic();usage=None;done=False
                    for line in response:
                        size+=len(line)
                        transport.update(bytes=size,elapsed_s=time.monotonic()-started)
                        if size>STREAM_BYTES or transport['elapsed_s']>stream_seconds:raise ValueError('PROVIDER_STREAM_LIMIT')
                        if line.startswith(b':'):
                            try:on_chunk(None)  # SSE keepalive, never model content or usage
                            except (BrokenPipeError,ConnectionResetError):pass
                        if not line.startswith(b'data:'):continue
                        raw_chunk=line[5:].strip()
                        if raw_chunk==b'[DONE]':done=True;break
                        chunk=json.loads(raw_chunk)
                        if chunk.get('error'):raise ValueError('PROVIDER_STREAM_ERROR')
                        if chunk.get('model')!=MODEL:raise ValueError('RESPONSE_MODEL_ID_MISMATCH')
                        if transport['provider_request_id'] is None and chunk.get('id'):
                            transport['provider_request_id']=chunk['id']
                            self.store.event(owner,owner,'provider_transport_started',dict(transport))
                        chunks.append(chunk)
                        if chunk.get('usage'):
                            usage=chunk['usage']
                            choices=chunk.get('choices',[])
                            if not choices or any(c.get('finish_reason') for c in choices):
                                observed_final_usage=usage
                                self.store.event(owner,owner,'provider_terminal_usage',
                                    {**transport,'usage':usage})
                        # A disconnected browser/SDK does not cancel usage settlement.
                        try:on_chunk(chunk)
                        except (BrokenPipeError,ConnectionResetError):pass
                    if not done:raise ValueError('PROVIDER_STREAM_TRUNCATED')
                    result={'model':MODEL,'usage':usage,'choices':[]}
                    data=canonical(chunks).encode()
                else:
                    data=response.read(2000000)
                    result=json.loads(data)
            usage=result.get('usage')
            if result.get('model')!=MODEL:raise ValueError('RESPONSE_MODEL_ID_MISMATCH')
            # A rejected output can still have known billing. Settle observed
            # usage first instead of converting it to an UNKNOWN global block.
            violation=settle_usage(usage,data)
            self.store.event(owner,owner,'provider_transport_completed',{**transport,'settled':True})
            if violation:raise ValueError(violation)
            return result
        except Exception as exc:
            # A final provider usage chunk followed by a missing DONE marker is
            # known billing with failed output. It is not a successful answer.
            if not settled and observed_final_usage is not None:
                try:settle_usage(observed_final_usage,canonical(chunks).encode(),str(exc)[:200])
                except ValueError:pass  # invalid usage still retains UNKNOWN
            # Unknown billing stays reserved; only an explicit study amendment permits continuation.
            if not settled:
                with self.store.connect() as db:
                    status='NOT_SENT' if is_not_sent(exc) else 'UNKNOWN'
                    db.execute("UPDATE model_requests SET status=?,error=? WHERE id=?",(status,type(exc).__name__+': '+str(exc)[:200],request_id))
            self.store.event(owner,owner,'provider_transport_failed',
                {**transport,'settled':settled,'error':type(exc).__name__+': '+str(exc)[:200],
                 'automatic_retry':False})
            raise
