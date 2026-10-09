"""Operator projection of original paper Pi sessions, without a second writer.

The existing paper runtime retains conversations, projects, costs and execution.
Only sidebar metadata and explicit continuation requests live in the Studio.
Opening this view never constructs a Workbench or restores a running process.
"""
import contextlib
import hashlib
import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from .store import Store, canonical, identity
from .literature_campaign import DEFAULT_ROOT, read, digest
from .literature_continuation import validate_authority, load_authority
from . import budget_policy

REGISTRATION = 'paper-sessions.json'


class ReadOnlyStore(Store):
    def __init__(self, root):
        self.root=Path(root).resolve();self.db=self.root/'workbench.sqlite';self.readonly=True
        if not self.db.is_file():raise ValueError('PAPER_RUNTIME_NOT_FOUND')

    @contextlib.contextmanager
    def connect(self):
        db=sqlite3.connect(self.db.as_uri()+'?mode=ro',uri=True,timeout=5)
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
        try:yield db
        finally:db.close()


def reader(cls, app, **fields):
    """Allocate read adapters without their migration/recovery constructors."""
    value=cls.__new__(cls);value.app=app;value.store=app.store
    for key,item in fields.items():setattr(value,key,item)
    return value


class PaperSessions:
    def __init__(self, production, study_root=DEFAULT_ROOT):
        self.production=production;self.root=Path(study_root).resolve();self.registration=None
        self.lock=threading.RLock();self._view=None
        path=production.store.root/REGISTRATION
        if not path.is_file():return
        value=read(path)
        if value.get('schema_version')!='bf-paper-session-registration-v1' or Path(value.get('study_root','')).resolve()!=self.root:
            raise ValueError('PAPER_SESSION_REGISTRATION_INVALID')
        authorization=self.root/'campaign/parallel-20261009/authorization.json'
        if value.get('authorization_sha256')!=digest(authorization):raise ValueError('PAPER_SESSION_AUTHORITY_CHANGED')
        scope=read(authorization)
        # Historical sessions remain readable after the execution window closes.
        validate_authority(scope,scope['created'])
        allowed={row['paper_id']:row['owner'] for row in scope['owners']}
        papers=value.get('papers',[])
        if len(papers)!=10 or {r.get('paper'):r.get('owner') for r in papers}!=allowed:
            raise ValueError('PAPER_SESSION_OWNER_SCOPE')
        production.organization.folder(value['folder_id'])
        self.registration=value;self.papers={r['owner']:r for r in papers}
        self.queue=self.root/'campaign/parallel-20261009/pi-queue';self.queue.mkdir(exist_ok=True)
        source=ReadOnlyStore(self.root/'runtime/state')
        with source.connect() as db:
            for row in papers:
                if not db.execute('SELECT 1 FROM conversations WHERE id=?',(row['owner'],)).fetchone():raise ValueError('ORIGINAL_PI_SESSION_MISSING')

    def has(self, owner):return bool(self.registration and owner in self.papers)

    def requests(self, owner):
        if not self.has(owner):raise PermissionError('PAPER_SESSION_NOT_REGISTERED')
        return [value for p in sorted(self.queue.glob(owner+'-*.json')) if (value:=read(p)).get('schema_version')=='bf-paper-continuation-queue-v1']

    def queue_state(self, owner):
        rows=self.requests(owner)
        return max(rows,key=lambda r:r['created']) if rows else None

    def view(self):
        if not self.registration:return None
        with self.lock:
            if self._view:return self._view
            from .chat import Conversations
            from .product import Products
            from .assembly import Assemblies
            from .deliverables import Deliverables
            from .engineering import Engineering
            from .jlceda import JLCEDA
            from .simulation_tasks import SimulationTasks
            from .eda_cli import EdaCLI
            from .references import References
            from .product_results import ProductResults
            from .result_sources import ResultSources
            from .engineering_cases import EngineeringCases
            from .eda_results import EdaResults
            app=SimpleNamespace(store=ReadOnlyStore(self.root/'runtime/state'))
            state=app.store.root;home=state.parent
            app.organization=self.production.organization
            app.products=reader(Products,app,root=state/'products')
            app.assemblies=reader(Assemblies,app,root=state/'product-assemblies')
            app.deliverables=reader(Deliverables,app)
            app.engineering=reader(Engineering,app,root=home/'engineering')
            app.engineering.eda=JLCEDA.__new__(JLCEDA)
            app.engineering.eda.e=app.engineering;app.engineering.eda.store=app.store;app.engineering.eda.latest={'status':'not_probed'}
            app.engineering.tasks=SimulationTasks.__new__(SimulationTasks);app.engineering.tasks.store=app.store
            app.eda_cli=reader(EdaCLI,app,root=home/'eda-cli')
            app.references=reader(References,app,root=home/'references')
            app.results=reader(ProductResults,app,_checked={})
            app.results.sources=ResultSources(app.results)
            # Derived view files belong to the operator cache, outside paper data.
            app.results.sources.root=self.production.store.root/'paper-view-cache'
            cases=EngineeringCases.__new__(EngineeringCases);cases.catalog=app.results;cases.store=app.store
            cases.legacy_root=state/'engineering-case-files';cases.root=cases.legacy_root
            config=state/'engineering-case-storage.json'
            if config.is_file():
                storage=read(config)
                if storage.get('schema_version')!='bf-engineering-case-storage-v1' or not Path(storage.get('root','')).is_absolute():raise ValueError('CASE_STORAGE_CONFIG_INVALID')
                cases.root=Path(storage['root']).resolve()
            app.results.cases=cases;app.results.eda=EdaResults(app.results)
            app.conversations=reader(Conversations,app,home=home)
            from .skill_resources import SkillResources
            app.skills=reader(SkillResources,app)
            self._view=app;return app

    def list(self):
        if not self.registration:return []
        app=self.view();out=[]
        for owner,paper in sorted(self.papers.items(),key=lambda item:item[1]['paper']):
            raw=app.conversations.get(owner);queue=self.queue_state(owner)
            meta=self.production.organization.metadata(owner)
            if meta['deleted']:continue
            status='QUEUED' if queue and queue['status']=='QUEUED' and raw['status']!='RUNNING' else raw['status']
            out.append({**raw,**meta,'title':meta['title'] or paper['title'],
                'folder_id':meta['folder_id'] or self.registration['folder_id'],
                'paper':paper['paper'],'status':status,'source_status':raw['status'],
                'paper_session':True,'legacy':False,'execution_queue':queue})
        return out

    def readiness(self, owner):
        reasons=[];authority=None
        try:
            authority=load_authority(self.root)
            if not authority:reasons.append('PAPER_CONTINUATION_WINDOW_CLOSED')
        except (ValueError,OSError):reasons.append('PAPER_CONTINUATION_WINDOW_CLOSED')
        ready=self.root/'campaign/parallel-20261009/READY.json'
        if not ready.is_file() or read(ready).get('status')!='PASS':reasons.append('PAPER_CONTINUATION_RELEASE_PENDING')
        with self.view().store.connect() as db:
            unbounded=bool(budget_policy.for_owner(db,owner))
        return {'ready':not reasons,'reasons':reasons,'owner':owner,'model':'DeepSeek',
                'unbounded':unbounded,'limit_usd':None if unbounded else 30,'token_limit':None if unbounded else 175000000,
                'usage_deferral_explicitly_authorized':True}

    def detail(self, owner):
        if not self.has(owner):raise PermissionError('PAPER_SESSION_NOT_REGISTERED')
        app=self.view();conv=app.conversations.get(owner)
        with app.store.connect() as db:
            messages=[dict(r) for r in db.execute('SELECT * FROM chat_messages WHERE conversation=? ORDER BY created',(owner,))]
            costs=[dict(r) for r in db.execute('SELECT status,charged,reserved FROM model_requests WHERE owner=?',(owner,))]
            recalls=[dict(r) for r in db.execute('SELECT * FROM chat_recalls WHERE conversation=? ORDER BY rowid',(owner,))]
        events,cursor=app.conversations.snapshot_events(owner)
        meta=self.production.organization.metadata(owner);paper=self.papers[owner];queue=self.queue_state(owner)
        pending=queue and queue['status']=='QUEUED' and conv['status']!='RUNNING'
        return {**conv,**meta,'title':meta['title'] or paper['title'],'folder_id':meta['folder_id'] or self.registration['folder_id'],
            'status':'QUEUED' if pending else conv['status'],'error':None if pending else conv['error'],'source_status':conv['status'],'source_error':conv['error'],
            'paper':paper['paper'],'paper_session':True,'execution_queue':queue,'recalls':recalls,
            'shared_context':{'folder_id':self.registration['folder_id'],'folder_name':self.registration['folder_name'],'source':'Operator organization only; original frozen Pi method remains loaded.'},
            'messages':messages,'events':events,'event_cursor':cursor,'execution':None,'jobs':app.store.jobs(owner),
            'product':app.products.projection(owner),'readiness':self.readiness(owner),
            'cost':{'cap_usd':self.readiness(owner)['limit_usd'],'unbounded':self.readiness(owner)['unbounded'],
                    'model_calls':len(costs),'liability_usd':sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in costs),'fees_reset':False},
            'scope':'Original Pi conversation and engineering records; engineering acceptance, attribution and physical validation are separate.'}

    def events(self, owner, after=0):
        if not self.has(owner):raise PermissionError('PAPER_SESSION_NOT_REGISTERED')
        return self.view().conversations.events(owner,after)

    def target(self, path, query, body=None):
        if not self.registration:return None
        parts=path.strip('/').split('/')
        if len(parts)>=3 and parts[:2] in (['api','conversations'],['api','sidebar']):
            return parts[2] if self.has(parts[2]) else None
        owner=(body or {}).get('session_id') or query.get('session',[None])[0]
        if self.has(owner):return owner
        if len(parts)>=4 and parts[:3]==['api','engineering','jobs']:
            with self.view().store.connect() as db:r=db.execute('SELECT owner FROM engineering_jobs WHERE id=?',(parts[3],)).fetchone()
            if r and self.has(r['owner']):return r['owner']
        return None

    def enqueue(self, owner, operation, text=None):
        if not self.has(owner):raise PermissionError('PAPER_SESSION_NOT_REGISTERED')
        if not isinstance(operation,str) or not 1<=len(operation)<=100:raise ValueError('OPERATION_REQUIRED')
        if text is not None and (not isinstance(text,str) or not 1<=len(text.strip())<=12000):raise ValueError('MESSAGE_REQUIRED_MAX_12000')
        scope=load_authority(self.root)
        if not scope:raise ValueError('CONTINUATION_USER_AUTHORITY_REQUIRED')
        key=owner+'-'+identity(operation)[:20];path=self.queue/(key+'.json')
        with self.lock:
            if path.exists():
                old=read(path)
                if old.get('operator_text')!=text:raise ValueError('OPERATION_CONFLICT')
                return old
            # Do not launch another Pi process while this original owner is active.
            active=self.view().conversations.get(owner)['status']=='RUNNING'
            ready=read(self.root/'campaign/parallel-20261009/READY.json')
            phase=ready['commands'][self.papers[owner]['paper']]['phase']
            value={'schema_version':'bf-paper-continuation-queue-v1','id':key,'paper':self.papers[owner]['paper'],
                'owner':owner,'operation':operation,'phase':phase,'operator_text':text,
                'created':time.time(),'status':'OBSERVING_EXISTING_RUN' if active and text is None else 'QUEUED',
                'authorization_sha256':scope['authority_sha256'],'fees_reset':False}
            tmp=path.with_suffix('.tmp');tmp.write_text(canonical(value));tmp.replace(path)
            return value

    def change_entry(self, owner, body):
        if not self.has(owner):raise PermissionError('PAPER_SESSION_NOT_REGISTERED')
        if body.get('action') not in ('rename','move','delete','restore'):raise ValueError('SIDEBAR_ACTION_INVALID')
        # Deletion here hides the recoverable shortcut; it cannot delete source data.
        meta=self.production.organization.metadata(owner)
        if body['action']=='rename':meta['title']=self.production.organization.name(body['name'])
        elif body['action']=='move':
            fid=body.get('folder_id')
            if fid:self.production.organization.folder(fid)
            meta['folder_id']=fid
        else:meta['deleted']=int(body['action']=='delete')
        with self.production.store.connect() as db:db.execute('INSERT OR REPLACE INTO sidebar_entries VALUES(?,?,?,?,?)',(owner,meta['title'],meta['folder_id'],meta['deleted'],time.time()))
        return meta

    def cancel_pending(self, owner):
        if not self.has(owner):raise PermissionError('PAPER_SESSION_NOT_REGISTERED')
        cancelled=[]
        with self.lock:
            for item in self.requests(owner):
                if item['status']=='QUEUED':
                    item.update(status='CANCELLED',ended=time.time())
                    (self.queue/(item['id']+'.json')).write_text(canonical(item));cancelled.append(item['id'])
        active=self.view().conversations.get(owner)['status']=='RUNNING'
        if active:
            stop=self.queue/(owner+'-stop.json')
            stop.write_text(canonical({'owner':owner,'requested':time.time(),'action':'stop_before_next_model_call'}))
        return {'owner':owner,'cancelled':cancelled,'status':'STOP_REQUESTED' if active else 'IDLE','source_records_preserved':True}
