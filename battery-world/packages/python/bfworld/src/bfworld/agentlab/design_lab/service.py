"""Authoritative task/control/adoption ledger within the existing Workbench.

Only this service writes CheckReceipts. Participant source and rationale are
never promoted to verdicts. Operations are idempotent and UNKNOWN is not retried.
"""
import csv
import fcntl
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import zipfile
from ..store import canonical, identity
from ..runtime_config import RUNTIME_ROOT
from . import case_c, coupled_c
from .contracts import owner as valid_owner, contract, snapshot, check_snapshot, acceptance, sha, sealed


class DesignLab:
    def __init__(self, app, start_worker=True):
        self.app,self.store=app,app.store
        self.root=self.store.root.parent/'design-lab'
        self.root.mkdir(exist_ok=True)
        self.wake=threading.Event()
        self.closing=threading.Event()
        self.controllers={}
        with self.store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS design_tasks(owner TEXT PRIMARY KEY,task_id TEXT NOT NULL,
              contract TEXT NOT NULL,environment TEXT NOT NULL,current_design TEXT NOT NULL,
              revision INTEGER NOT NULL,intent TEXT NOT NULL,plan TEXT NOT NULL,status TEXT NOT NULL,
              cursor INTEGER NOT NULL DEFAULT 0,submission TEXT);
            CREATE TABLE IF NOT EXISTS design_snapshots(owner TEXT NOT NULL,design_id TEXT NOT NULL,
              value TEXT NOT NULL,PRIMARY KEY(owner,design_id));
            CREATE TABLE IF NOT EXISTS design_operations(id TEXT PRIMARY KEY,owner TEXT NOT NULL,
              operation TEXT NOT NULL,request_hash TEXT NOT NULL,request TEXT NOT NULL,status TEXT NOT NULL,
              result TEXT,error TEXT,created REAL NOT NULL,UNIQUE(owner,operation));
            CREATE TABLE IF NOT EXISTS design_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
              owner TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS design_adoptions(id TEXT PRIMARY KEY,owner TEXT NOT NULL,
              from_design TEXT NOT NULL,to_design TEXT NOT NULL,revision INTEGER NOT NULL,
              rationale TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS design_task_history(owner TEXT NOT NULL,task_id TEXT NOT NULL,
              value TEXT NOT NULL,PRIMARY KEY(owner,task_id));
            ''')
            interrupted=list(db.execute("SELECT id,owner FROM design_operations WHERE status='RUNNING'"))
            db.execute("UPDATE design_operations SET status='UNKNOWN',error='Service interrupted; inspect immutable files before resolving, no automatic re-dispatch.' WHERE status='RUNNING'")
        for row in interrupted:self.event(row['owner'],'operation_unknown',{'operation_id':row['id']})
        from .repository import Repository
        self.repository=Repository(self)
        if start_worker:threading.Thread(target=self.worker,daemon=True).start()

    def event(self,owner,kind,data,db=None):
        if db is None:
            with self.store.connect() as connection:return self.event(owner,kind,data,connection)
        return db.execute('INSERT INTO design_events(owner,kind,data,created) VALUES(?,?,?,?)',
                          (owner,kind,canonical(data),time.time())).lastrowid

    def task(self,owner):
        with self.store.connect() as db:row=db.execute('SELECT * FROM design_tasks WHERE owner=?',(valid_owner(owner),)).fetchone()
        if not row:raise ValueError('DESIGN_TASK_NOT_FOUND')
        value=dict(row)
        for key in ('contract','environment','intent','plan','submission'):
            if value[key] is not None:value[key]=json.loads(value[key])
        return value

    def configure(self,owner,env,source,new_phase=False):
        valid_owner(owner)
        if owner in self.controllers and self.controllers[owner].is_alive():
            raise ValueError('DESIGN_PHASE_REQUIRES_IDLE_CONTROLLER')
        from .baseline import environment
        native=env.get('mode')=='native-coupled-C'
        from . import paper_candidate
        paper=env.get('mode')==paper_candidate.MODE
        if paper:
            if env!=paper_candidate.environment(self,owner,env['root']):raise ValueError('PAPER_ENVIRONMENT_TAMPER')
            task=paper_candidate.contract(env)
            design=paper_candidate.capture(self,owner,task,env,source)
        elif native:
            coupled_c.verify_environment(env)
            task=coupled_c.contract(env)
            design=coupled_c.snapshot(task,source,env)
        else:
            if env!=environment(env['root']):raise ValueError('ENVIRONMENT_MANIFEST_TAMPER')
            from .qualification import validation_id
            task=contract(env['environment_id'],validation_id())
            design=snapshot(task,source)
        if paper:self.persist_snapshot(owner,design)
        with self.store.connect() as db:
            if not db.execute('SELECT 1 FROM conversations WHERE id=?',(owner,)).fetchone():
                raise ValueError('DESIGN_REQUIRES_EXISTING_PI_CONVERSATION')
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM design_tasks WHERE owner=?',(owner,)).fetchone()
            if old:
                if not new_phase:raise ValueError('DESIGN_TASK_ALREADY_BOUND')
                if old['task_id']==task['task_id']:raise ValueError('DESIGN_PHASE_ALREADY_BOUND')
                if db.execute("SELECT 1 FROM design_operations WHERE owner=? AND status IN ('QUEUED','RUNNING','UNKNOWN')",(owner,)).fetchone():
                    raise ValueError('DESIGN_PHASE_REQUIRES_DRAINED_KNOWN_OPERATIONS')
                db.execute('INSERT INTO design_task_history VALUES(?,?,?)',(owner,old['task_id'],canonical(dict(old))))
                db.execute('DELETE FROM design_tasks WHERE owner=?',(owner,))
            db.execute('INSERT INTO design_snapshots VALUES(?,?,?)',(owner,design['design_id'],canonical(design)))
            db.execute('INSERT INTO design_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (owner,task['task_id'],canonical(task),canonical(env),design['design_id'],1,
                        canonical({'kind':'CONTINUE'}),canonical([]),'ACTIVE',0,None))
            self.event(owner,'phase_bound' if old else 'task_bound',{'task_id':task['task_id'],'design_id':design['design_id'],
                       'previous_task_id':old['task_id'] if old else None,'original_owner_preserved':True},db)
            if old:
                previous=json.loads(db.execute('SELECT value FROM design_snapshots WHERE owner=? AND design_id=?',
                                               (owner,old['current_design'])).fetchone()['value'])
                retained=previous['sources']==source
                authors=[json.loads(r['data']) for r in db.execute(
                    "SELECT data FROM design_events WHERE owner=? AND kind='design_frozen' ORDER BY seq",(owner,))]
                inherited=[v['source_author'] for v in authors if v['design_id']==previous['design_id']]
                author=(inherited[-1] if inherited else 'Codex public starter/reference') if retained else 'Codex operator phase source'
                self.event(owner,'design_frozen',{'design_id':design['design_id'],'parent':None,
                    'source_author':author,'phase_binding_actor':'Codex operator',
                    'source_provenance':{'previous_design':previous['design_id'],
                                         'previous_task':old['task_id'],'byte_exact_sources_retained':retained}},db)
                if not retained:
                    self.event(owner,'external_intervention',{'action':'operator_phase_source_change',
                        'design_id':design['design_id'],'previous_design':previous['design_id']},db)
        if not paper:self.persist_snapshot(owner,design)
        destination=self.root/owner/('phases/'+task['task_id'] if old else '')
        sealed(destination/'task-contract.json',task)
        sealed(destination/'environment.json',env)
        return self.view(owner)

    def task_version(self,owner,task_id):
        current=self.task(owner)
        if current['task_id']==task_id:return current
        with self.store.connect() as db:
            row=db.execute('SELECT value FROM design_task_history WHERE owner=? AND task_id=?',(owner,task_id)).fetchone()
        if not row:raise ValueError('DESIGN_TASK_VERSION_NOT_FOUND')
        value=json.loads(row['value'])
        for key in ('contract','environment','intent','plan','submission'):
            if value[key] is not None:value[key]=json.loads(value[key])
        return value

    def persist_snapshot(self,owner,design):
        if design.get('schema_version')=='bf-paper-design-snapshot-v1':
            from .paper_candidate import persist
            return persist(self,owner,design)
        directory=self.root/owner/'designs'/design['design_id'];directory.mkdir(parents=True,exist_ok=True)
        sealed(directory/'snapshot.json',design)
        for name,text in design['sources'].items():
            path=directory/name
            if path.exists() and path.read_text()!=text:raise ValueError('DESIGN_FROZEN_SOURCE_TAMPER')
            path.write_text(text)

    def design(self,owner,design_id):
        with self.store.connect() as db:row=db.execute('SELECT value FROM design_snapshots WHERE owner=? AND design_id=?',(owner,design_id)).fetchone()
        if not row:raise PermissionError('DESIGN_NOT_OWNED')
        stored=json.loads(row['value'])
        if stored.get('schema_version')=='bf-system-commit-v2':
            return self.repository.system(stored['project_id'],design_id)
        task=self.task_version(owner,stored['task_id'])
        if task['environment'].get('mode')=='paper-native-P01':
            from .paper_candidate import verify
            return verify(self,owner,stored)
        if task['environment'].get('mode')=='native-coupled-C':
            value=coupled_c.snapshot(task['contract'],stored['sources'],task['environment'],stored.get('parent'))
            if value!=stored:raise ValueError('DESIGN_SNAPSHOT_TAMPER')
        else:value=check_snapshot(task['contract'],stored)
        path=self.root/owner/'designs'/design_id/'snapshot.json'
        if path.is_file() and json.loads(path.read_text())!=value:raise ValueError('DESIGN_FROZEN_SOURCE_TAMPER')
        for name,text in value['sources'].items():
            if not (path.parent/name).is_file() or (path.parent/name).read_text()!=text:raise ValueError('DESIGN_FROZEN_SOURCE_TAMPER')
        return value

    def freeze(self,owner,sources,parent,actor='internal-reference'):
        task=self.task(owner)
        previous=self.design(owner,parent)
        if previous['task_id']!=task['task_id']:raise ValueError('DESIGN_PARENT_FROM_ANOTHER_PHASE')
        if task['environment'].get('mode')=='paper-native-P01':
            from .paper_candidate import capture
            value=capture(self,owner,task['contract'],task['environment'],sources,parent)
        else:
            value=(coupled_c.snapshot(task['contract'],sources,task['environment'],parent)
                   if task['environment'].get('mode')=='native-coupled-C' else snapshot(task['contract'],sources,parent))
        self.persist_snapshot(owner,value)
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO design_snapshots VALUES(?,?,?)',(owner,value['design_id'],canonical(value)))
            self.event(owner,'design_frozen',{'design_id':value['design_id'],'parent':parent,'source_author':actor},db)
        return value

    def operation(self,owner,key):
        with self.store.connect() as db:row=db.execute('SELECT * FROM design_operations WHERE id=? AND owner=?',(key,owner)).fetchone()
        if not row:raise PermissionError('DESIGN_OPERATION_NOT_OWNED')
        value=dict(row)
        for k in ('request','result'):
            if value[k] is not None:value[k]=json.loads(value[k])
        return value

    def run(self,owner,operation_id,design_id):
        from ..runtime_config import require_capability
        require_capability('native')
        if self.task(owner)['environment'].get('mode')=='paper-native-P01':
            raise ValueError('PAPER_CANDIDATE_NATIVE_ENTRY_REQUIRED')
        design=self.design(owner,design_id)
        if design['task_id']!=self.task(owner)['task_id']:raise ValueError('DESIGN_RUN_FROM_ANOTHER_PHASE')
        if not isinstance(operation_id,str) or not 1<=len(operation_id)<=100:raise ValueError('OPERATION_ID_REQUIRED')
        request={'design_id':design_id,'task_id':self.task(owner)['task_id']};digest=identity(request)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM design_operations WHERE owner=? AND operation=?',(owner,operation_id)).fetchone()
            if row:
                if row['request_hash']!=digest:raise ValueError('OPERATION_CONFLICT')
                return self.operation(owner,row['id'])
            cached=db.execute("SELECT * FROM design_operations WHERE owner=? AND request_hash=? AND status IN ('SUCCEEDED','QUEUED','RUNNING','UNKNOWN') ORDER BY created DESC LIMIT 1",(owner,digest)).fetchone()
            if cached:return self.operation(owner,cached['id'])
            key='design-job-'+secrets.token_hex(8)
            db.execute('INSERT INTO design_operations VALUES(?,?,?,?,?,?,NULL,NULL,?)',
                       (key,owner,operation_id,digest,canonical(request),'QUEUED',time.time()))
            self.event(owner,'operation_queued',{'operation_id':key,'request_hash':digest},db)
        self.wake.set()
        return self.operation(owner,key)

    def worker(self):
        while not self.closing.is_set():
            self.wake.wait(1);self.wake.clear()
            # Teardown must not reconnect to, or recreate, a removed Store.
            # Other database failures remain visible rather than being retried.
            if self.closing.is_set() or not self.store.db.is_file():return
            try:
                with self.store.connect() as db:
                    row=db.execute("SELECT id,owner FROM design_operations WHERE status='QUEUED' ORDER BY created LIMIT 1").fetchone()
            except sqlite3.OperationalError:
                if not self.store.db.is_file():return
                raise
            if row:
                try:self.execute(row['owner'],row['id'])
                except Exception as exc:
                    with self.store.connect() as db:
                        db.execute("UPDATE design_operations SET status='FAILED',error=? WHERE id=?",(type(exc).__name__+': '+str(exc)[:3000],row['id']))
                    self.event(row['owner'],'operation_failed',{'operation_id':row['id'],'error':str(exc)[:2000]})

    def execute(self,owner,key):
        if self.task(owner)['environment'].get('mode')=='paper-native-P01':
            raise ValueError('PAPER_CANDIDATE_C_EXECUTOR_DENIED')
        # Same in-process engineering lock; cross-process advisory lock also
        # covers the paper runtime. All workers must be drained before rollout.
        from .native_slot import native_slot
        with self.app.engineering.lock,native_slot():
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute("SELECT * FROM design_operations WHERE id=? AND owner=? AND status='QUEUED'",(key,owner)).fetchone()
                if not row:return
                db.execute("UPDATE design_operations SET status='RUNNING' WHERE id=?",(key,))
            task=self.task(owner);design=self.design(owner,json.loads(row['request'])['design_id'])
            from .qualification import validation_id
            native=task['environment'].get('mode')=='native-coupled-C'
            actual_validation=coupled_c.validation_id() if native else validation_id()
            if actual_validation!=task['contract']['validation_id']:raise ValueError('EXECUTOR_VALIDATION_CHANGED_RECHECK_REQUIRED')
            directory=self.root/owner/'operations'/key
            witness=None
            if native:
                qualification_path=self.root/'qualifications'/task['contract']['validation_id']/'qualification.json'
                qualification=json.loads(qualification_path.read_text())
                if (not qualification['passed'] or qualification['environment_id']!=task['environment']['environment_id']
                    or qualification['validation_id']!=actual_validation):
                    raise ValueError('DESIGN_ENVIRONMENT_NOT_QUALIFIED')
                # Only an operator-published qualification can supply this
                # cache. It is not an argument accepted from participant tools.
                witness=qualification.get('native_witness')
            receipt=coupled_c.build(design,directory,task['environment']) if native else case_c.build(design,directory)
            sealed(directory/'build.json',receipt)
            execution=(coupled_c.execute(task['contract'],design,receipt,directory,task['environment'],trusted_witness=witness) if native
                       else case_c.execute(task['contract'],design,receipt,directory,task['environment']))
            sealed(directory/'execution.json',execution)
            check=(coupled_c.evaluate(task['contract'],design,receipt,execution,task['environment']) if native
                   else case_c.evaluate(task['contract'],design,receipt,execution,task['environment']))
            ports=[]
            for stem,event in [('port-id',{'time_s':2.5,'event_id':65591,'kind':1}),
                               ('port-kind',{'time_s':2.5,'event_id':4294967239,'kind':2})]:
                probe=(coupled_c.probe(task['contract'],design,receipt,directory,task['environment'],execution,event,stem) if native
                       else case_c.execute(task['contract'],design,receipt,directory,task['environment'],event=event,stem=stem))
                verified=case_c.evaluate(task['contract'],design,receipt,probe,task['environment'],event_truth=event)
                ports.append({'scope':'modeled port conformance; not a second real motion',
                              'execution':probe,'check':verified})
                sealed(directory/(stem+'.json'),{'execution':probe,'check':verified})
            if any(p['check']['gates']['event_identity']!='PASS' for p in ports):
                check['gates']['event_identity']='FAIL'
                check['gates']['deadline_receive']='FAIL'
            check['port_conformance']=[{'execution_id':p['execution']['execution_id'],'event_identity':p['check']['gates']['event_identity']} for p in ports]
            check['check_id']='V-'+identity({k:v for k,v in check.items() if k!='check_id'})
            sealed(directory/'check.json',check)
            result={'build':receipt,'execution':execution,'check':check,
                    'receipt_sha256':{name:sha(directory/name) for name in ('build.json','execution.json','check.json')}}
            sealed(directory/'result.json',result)
            with self.store.connect() as db:
                db.execute("UPDATE design_operations SET status='SUCCEEDED',result=? WHERE id=?",(canonical(result),key))
                self.event(owner,'operation_completed',{'operation_id':key,'design_id':design['design_id'],
                           'check_id':check['check_id'],'gates':check['gates']},db)

    def verified_result(self,owner,key):
        op=self.operation(owner,key)
        if op['status']!='SUCCEEDED':raise ValueError('CHECK_REQUIRES_SUCCESSFUL_EXECUTION')
        directory=self.root/owner/'operations'/key
        result=op['result']
        for name,digest in result['receipt_sha256'].items():
            if sha(directory/name)!=digest:raise ValueError('CHECK_ARTIFACT_TAMPER')
        if json.loads((directory/'result.json').read_text())!=result:raise ValueError('CHECK_ARTIFACT_TAMPER')
        design=self.design(owner,result['build']['design_id'])
        case_c.verify_build(design,result['build'],directory)
        for name,digest in result['execution']['observations'].items():
            if sha(directory/name)!=digest:raise ValueError('EXECUTION_OBSERVATION_TAMPER')
        if result['execution'].get('native_dependencies'):
            from .native_witness import verify_archives
            verify_archives(result['execution']['native_dependencies'])
        for stem in ('port-id','port-kind'):
            value=json.loads((directory/(stem+'.json')).read_text())
            if value['execution']['execution_id'] not in [v['execution_id'] for v in result['check']['port_conformance']]:raise ValueError('PORT_CHECK_TAMPER')
            for name,digest in value['execution']['observations'].items():
                if sha(directory/name)!=digest:raise ValueError('PORT_OBSERVATION_TAMPER')
        return result

    def adopt(self,owner,design_id,expected_revision,rationale,operator=False):
        if self.design(owner,design_id)['task_id']!=self.task(owner)['task_id']:raise ValueError('DESIGN_ADOPTION_FROM_ANOTHER_PHASE')
        if not isinstance(rationale,str) or not rationale.strip() or len(rationale)>4000:raise ValueError('ADOPTION_RATIONALE_REQUIRED')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if operator:
                live=db.execute('SELECT status FROM conversations WHERE id=?',(owner,)).fetchone()
                busy=db.execute("SELECT 1 FROM design_operations WHERE owner=? AND status IN ('QUEUED','RUNNING','UNKNOWN') LIMIT 1",(owner,)).fetchone()
                if not live or live['status'] in ('RUNNING','STARTING','STOPPING','QUEUED') or busy:
                    raise ValueError('DESIGN_OPERATOR_RESTORE_REQUIRES_IDLE')
            old=db.execute('SELECT * FROM design_tasks WHERE owner=?',(owner,)).fetchone()
            if old['revision']!=expected_revision:raise ValueError('ADOPTION_STALE_REVISION')
            if old['submission']:raise ValueError('DESIGN_TASK_ALREADY_SUBMITTED')
            key='A-'+identity({'owner':owner,'from':old['current_design'],'to':design_id,'revision':expected_revision+1,'rationale':rationale})
            db.execute('INSERT INTO design_adoptions VALUES(?,?,?,?,?,?,?)',
                       (key,owner,old['current_design'],design_id,expected_revision+1,rationale,time.time()))
            db.execute('UPDATE design_tasks SET current_design=?,revision=? WHERE owner=?',
                       (design_id,expected_revision+1,owner))
            self.event(owner,'design_adopted',{'adoption_id':key,'design_id':design_id,'revision':expected_revision+1,
                       'affected':['application','build','execution','event_checks'],'retained':['physical_reference'],'rationale':rationale},db)
        return {'adoption_id':key,**self.view(owner)}

    def set_intent(self,owner,kind,job_id=None,plan=None):
        task=self.task(owner)
        if kind not in ('CONTINUE','WAIT','BLOCKED'):raise ValueError('TASK_INTENT_INVALID')
        if kind=='WAIT':
            job=self.operation(owner,job_id)
            if job['status'] not in ('QUEUED','RUNNING','UNKNOWN'):raise ValueError('WAIT_REQUIRES_PENDING_JOB')
        elif job_id is not None:raise ValueError('JOB_ONLY_FOR_WAIT')
        if plan is not None and (not isinstance(plan,list) or len(canonical(plan))>12000):raise ValueError('TASK_PLAN_INVALID')
        value={'kind':kind,'job_id':job_id}
        with self.store.connect() as db:
            db.execute('UPDATE design_tasks SET intent=?,plan=?,status=? WHERE owner=?',
                       (canonical(value),canonical(plan if plan is not None else task['plan']),kind,owner))
            self.event(owner,'intent_recorded',value,db)
        return self.view(owner)

    def events(self,owner,after=0):
        self.task(owner)
        if type(after) is not int or after<0:raise ValueError('EVENT_CURSOR_INVALID')
        with self.store.connect() as db:
            values=[{**dict(r),'data':json.loads(r['data'])} for r in db.execute(
                'SELECT * FROM design_events WHERE owner=? AND seq>? ORDER BY seq LIMIT 100',(owner,after))]
        return {'events':values,'next_cursor':values[-1]['seq'] if values else after}

    def acknowledge(self,owner,cursor):
        task=self.task(owner);events=self.events(owner,task['cursor'])['events']
        if type(cursor)is not int or cursor<task['cursor'] or cursor not in [task['cursor'],*(v['seq'] for v in events)]:
            raise ValueError('EVENT_CURSOR_NOT_DELIVERED')
        with self.store.connect() as db:db.execute('UPDATE design_tasks SET cursor=? WHERE owner=?',(cursor,owner))
        return {'cursor':cursor}

    def view(self,owner):
        task=self.task(owner)
        if task['environment'].get('mode')=='design-repository-v2':
            return self.repository.view(task['environment']['project_id'],owner)
        if task['environment'].get('mode')=='paper-native-P01':
            from .paper_candidate import frozen_view
            return frozen_view(self,owner)
        with self.store.connect() as db:
            operations=[dict(r) for r in db.execute('SELECT id,status,request,error FROM design_operations WHERE owner=? ORDER BY created DESC',(owner,))
                        if json.loads(r['request'])['task_id']==task['task_id']][:8]
            design_count=db.execute('SELECT COUNT(*) FROM design_snapshots WHERE owner=?',(owner,)).fetchone()[0]
        for op in operations:op['request']=json.loads(op['request'])
        from .resources import bundle
        methods=bundle(native=task['environment'].get('mode')=='native-coupled-C')[0]
        return {k:task[k] for k in ('owner','task_id','contract','current_design','revision','intent','plan','status','cursor','submission')}|{
            'operations':operations,'design_count':design_count,'original_owner_preserved':True,
            'environment_id':task['environment']['environment_id'],
            'environment_mode':task['environment'].get('mode','fixed-envelope-C'),
            'available_skills':[{k:x[k] for k in ('id','version','description','sha256')} for x in methods['skills']],
            'observations': 'job/check/observe provide actual frozen results; no suggested next step.'}

    def environment_view(self,owner):
        task=self.task(owner);env=task['environment']
        if env.get('mode')=='design-repository-v2':
            return {'environment':env,'baseline':self.repository.profile['baseline'],
                    'project':self.repository.project(env['project_id'],owner)}
        native=env.get('mode')=='native-coupled-C'
        if native:coupled_c.verify_environment(env)
        from .builder import DEPENDENCIES, VERSION
        assets=None
        if native:
            from .model_catalog import catalogue
            q=self.root/'qualifications'/task['contract']['validation_id']/'qualification.json'
            assets=catalogue(env['root'],q if q.is_file() else None,
                             expected_environment=env['environment_id'],
                             expected_validation=task['contract']['validation_id'])
        return {'environment':env,'supported_actions':task['contract']['supported_actions'],
                'candidate_builder':{'version':VERSION,'dependencies':DEPENDENCIES},
                'model_catalogue':assets,
                'qualification_scope':task['contract']['scope'],
                'physical':'NOT_TESTED','full_product_passed':False}

    def inspect_check(self,owner,key):
        result=self.verified_result(owner,key)
        task=self.task_version(owner,result['check']['task_id'])
        return {'operation_id':key,'check':result['check'],
                'acceptance':acceptance(task['contract'],result['build']['design_id'],result['check'],task['current_design']),
                'execution':result['execution'],'build':result['build']}

    def observe(self,owner,key,start=0,end=6.5,offset=0,limit=100):
        self.verified_result(owner,key)
        if type(offset)is not int or offset<0 or type(limit)is not int or not 1<=limit<=200:raise ValueError('OBSERVATION_PAGE_INVALID')
        if not 0<=start<=end<=6.5:raise ValueError('OBSERVATION_WINDOW_INVALID')
        p=self.root/owner/'operations'/key/'execution.csv'
        with p.open() as stream:values=[r for r in csv.DictReader(stream) if start<=float(r['time_s'])<=end]
        rows=values[offset:offset+limit]
        return {'source_sha256':sha(p),'units':{'time_s':'s','supply_V':'V','pgood_V':'V','current_A':'A','state':'enumeration'},
                'total_rows':len(values),'rows':rows,'next_offset':offset+limit if offset+limit<len(values) else None}

    def submit(self,owner,key,rationale):
        if not isinstance(rationale,str) or not rationale.strip():raise ValueError('SUBMISSION_RATIONALE_REQUIRED')
        task=self.task(owner);result=self.verified_result(owner,key)
        design_id=result['build']['design_id']
        if design_id!=task['current_design']:raise ValueError('SUBMISSION_REQUIRES_ADOPTED_DESIGN')
        verdict=acceptance(task['contract'],design_id,result['check'],task['current_design'])
        with self.store.connect() as db:
            events=[json.loads(r['data']) for r in db.execute("SELECT data FROM design_events WHERE owner=? AND kind='design_frozen'",(owner,))]
            teacher=db.execute("SELECT COUNT(*) FROM design_events WHERE owner=? AND kind='external_intervention'",(owner,)).fetchone()[0]
        authors=[v['source_author'] for v in events if v['design_id']==design_id]
        receipt={'schema_version':'bf-design-submission-v1','owner':owner,'task_id':task['task_id'],
                 'design_id':design_id,'operation_id':key,'revision':task['revision'],
                 'acceptance':verdict,'rationale':rationale,
                 'attribution':{'application_source':authors[-1] if authors else 'Codex public starter/reference',
                                'operator_design_actions':teacher,'design_decisions':'public trace; actor recorded per action',
                                'environment_and_checker':'Codex','physical':'NOT_TESTED','method_improvement':'NOT_EVALUATED'}}
        receipt['submission_id']='S-'+identity(receipt)
        if task['submission'] and task['submission']!=receipt:raise ValueError('SUBMISSION_ALREADY_SEALED')
        package=self.root/owner/'deliveries'/receipt['submission_id'];package.mkdir(parents=True,exist_ok=True)
        sealed(package/'submission.json',receipt)
        sealed(package/'task-contract.json',task['contract'])
        sealed(package/'environment.json',task['environment'])
        sealed(package/'snapshot.json',self.design(owner,design_id))
        source=self.root/owner/'operations'/key
        for name in ['build.json','execution.json','check.json','execution.csv','execution-tx.csv',
                     'port-id.json','port-id.csv','port-id-tx.csv','port-kind.json','port-kind.csv','port-kind-tx.csv',
                     *result['build']['files']]:
            dest=package/name;data=(source/name).read_bytes()
            if dest.exists() and dest.read_bytes()!=data:raise ValueError('DELIVERY_IMMUTABLE_CONFLICT')
            dest.write_bytes(data)
        # Native results carry current-candidate evidence, separate from the
        # retained reference. Large RAW archives remain immutable dependencies.
        if task['environment'].get('mode')=='native-coupled-C':
            for name in result['execution']['observations']:
                original=source/name;dest=package/'candidate'/name
                dest.parent.mkdir(parents=True,exist_ok=True)
                if dest.exists() and dest.read_bytes()!=original.read_bytes():raise ValueError('DELIVERY_IMMUTABLE_CONFLICT')
                dest.write_bytes(original.read_bytes())
        # CAD/electrical model/ratings are carried by exact source references;
        # copy editable small artifacts, retain RAW by immutable dependency hash.
        ref=Path(task['environment']['root'])
        for name in ('assembly.step','installation.step','design-spec.json','system.cir','rom.json','rating-check.json','energy.json','drive-ledger.json','time-step-check.json'):
            (package/('reference-'+name)).write_bytes((ref/name).read_bytes())
        sealed(package/'delivery-manifest.json',{'schema_version':'bf-design-delivery-v1','design_id':design_id,
            'files':{str(p.relative_to(package)):sha(p) for p in sorted(package.rglob('*')) if p.is_file() and p.name!='delivery-manifest.json' and p.suffix!='.zip'},
            'external_native_dependencies':task['environment']['native_dependencies']+result['execution'].get('native_dependencies',[]),
            'scope':task['contract']['scope'],'full_product_passed':False})
        zip_path=package/'C-digital-design.zip'
        if not zip_path.exists():
            with zipfile.ZipFile(zip_path,'x',zipfile.ZIP_DEFLATED) as archive:
                for p in sorted(package.rglob('*')):
                    if p.is_file() and p!=zip_path:
                        info=zipfile.ZipInfo(str(p.relative_to(package)),date_time=(2026,10,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                        archive.writestr(info,p.read_bytes())
        with zipfile.ZipFile(zip_path) as archive:
            if archive.testzip() is not None:raise ValueError('DELIVERY_ZIP_CORRUPT')
            manifest=json.loads(archive.read('delivery-manifest.json'))
            import hashlib
            if any(hashlib.sha256(archive.read(n)).hexdigest()!=h for n,h in manifest['files'].items()):raise ValueError('DELIVERY_READBACK_FAILED')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT current_design,revision FROM design_tasks WHERE owner=?',(owner,)).fetchone()
            if current['current_design']!=design_id or current['revision']!=task['revision']:raise ValueError('SUBMISSION_STALE_REVISION')
            db.execute("UPDATE design_tasks SET submission=?,status='SUBMITTED',intent=? WHERE owner=?",
                       (canonical(receipt),canonical({'kind':'SUBMIT','operation_id':key}),owner))
            self.event(owner,'task_submitted',{'submission_id':receipt['submission_id'],'scoped_status':verdict['scoped_status'],'zip_sha256':sha(zip_path)},db)
        return {**receipt,'package_path':str(zip_path),'zip_sha256':sha(zip_path)}

    def delivery(self,owner):
        task=self.task(owner)
        if task['environment'].get('mode')=='paper-native-P01':
            from .paper_delivery import delivery
            return delivery(self,owner)
        receipt=task['submission']
        if not receipt:raise ValueError('DESIGN_NOT_SUBMITTED')
        result=self.verified_result(owner,receipt['operation_id'])
        actual=acceptance(task['contract'],result['build']['design_id'],result['check'],task['current_design'])
        if actual!=receipt['acceptance'] or task['revision']!=receipt['revision']:
            raise ValueError('DELIVERY_STALE_REVISION')
        directory=self.root/owner/'deliveries'/receipt['submission_id']
        package=directory/'C-digital-design.zip'
        with self.store.connect() as db:
            event=db.execute("SELECT data FROM design_events WHERE owner=? AND kind='task_submitted' ORDER BY seq DESC LIMIT 1",(owner,)).fetchone()
        if not event or json.loads(event['data'])['zip_sha256']!=sha(package):
            raise ValueError('DELIVERY_ZIP_TAMPER')
        with zipfile.ZipFile(package) as archive:
            if archive.testzip() is not None:raise ValueError('DELIVERY_ZIP_CORRUPT')
            if json.loads(archive.read('submission.json'))!=receipt:raise ValueError('DELIVERY_RECEIPT_TAMPER')
            manifest=json.loads(archive.read('delivery-manifest.json'))
            if manifest['design_id']!=task['current_design']:raise ValueError('DELIVERY_DESIGN_MISMATCH')
            import hashlib
            for name,digest in manifest['files'].items():
                if hashlib.sha256(archive.read(name)).hexdigest()!=digest or sha(directory/name)!=digest:
                    raise ValueError('DELIVERY_READBACK_FAILED')
        return package

    def handle(self,owner,body,operator=False):
        action=body.get('action')
        if isinstance(action,str) and action.startswith('repository_'):
            return self.repository.handle(owner,body,operator)
        if self.repository.bound(owner) and action in ('configure','configure_paper','freeze','run','adopt','submit','start'):
            raise ValueError('REPOSITORY_REQUIRES_TYPED_ACTION')
        from . import paper_candidate
        if action=='configure_paper':
            if not operator:raise PermissionError('OPERATOR_REQUIRED')
            env=paper_candidate.environment(self,owner,body['root'])
            value=self.configure(owner,env,body['sources'])
            self.event(owner,'design_frozen',{'design_id':value['current_design'],'parent':None,
                'source_author':'existing Pi source; Codex migration metadata',
                'engineering_source_changed':False})
            if body.get('interrupted_write'):
                fact=body['interrupted_write']
                paper_candidate.record_blocker(self,owner,fact['operation_id'],fact)
            return self.view(owner)
        if paper_candidate.bound(self,owner):
            result=paper_candidate.handle(self,owner,body,operator)
            if result is not None:return result
        required={'freeze':('sources','parent'),'run':('operation_id','design_id'),
                  'job':('job_id',),'check':('job_id',),'observe':('job_id',),
                  'adopt':('design_id','expected_revision','rationale'),'intent':('kind',),
                  'ack':('cursor',),'submit':('job_id','rationale'),'skill':('skill_id',)}
        missing=[key for key in required.get(action,()) if body.get(key) is None]
        if missing:raise ValueError('DESIGN_ARGUMENTS_REQUIRED: '+str(action)+' requires '+','.join(missing))
        if operator and action in ('freeze','run','adopt','intent','submit'):
            self.event(owner,'external_intervention',{'actor':'operator','action':action,'input_sha256':identity(body)})
        if action=='configure':
            if not operator:raise PermissionError('OPERATOR_REQUIRED')
            return self.configure(owner,body['environment'],body['sources'],body.get('new_phase',False))
        if action in ('authorize','method_authorize'):
            if not operator:raise PermissionError('OPERATOR_REQUIRED')
            from .. import budget_policy
            from ..model_profile import named
            if action=='method_authorize':
                self.app.conversations.get(owner)
                task_id=body.get('task_id','')
                if not isinstance(task_id,str) or not task_id.startswith('method-study-') or len(task_id)>150:
                    raise ValueError('METHOD_TASK_ID_INVALID')
                task={'task_id':task_id}
            else:
                task=self.task(owner)
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                previous=budget_policy.configured(db)
                new=dict(previous or {'mode':'unbounded','scope':'owners','owners':[owner],
                    'authorized_by':'direct-user','direct_user_authorization':'费用、累计 token 和请求数不设上限',
                    'cumulative_usd_cap':None,'cumulative_token_cap':None,'request_count_cap':None,
                    'request_usd_cap':None,'fees_reset':False,'unknown_reservations_preserved':True})
                if new['scope']=='owners' and owner not in new['owners']:new['owners']=[*new['owners'],owner]
                carried={r['id']:identity(dict(r)) for r in db.execute("SELECT * FROM model_requests WHERE status='UNKNOWN'")}
                new.update(schema_version='bf-model-unbounded-policy-v2',wall_seconds=None,wall_authorized_by='direct-user',
                    wall_authorization_text=body['wall_authorization_text'],wall_unbounded=True,
                    wall_owners=list(dict.fromkeys([*new.get('wall_owners',[]),owner])),unknown_carryforward=carried,
                    wall_window_changed=True)
                profile=body.get('model_profile','engineering-reasoning-compact-v2');named(profile)
                budget_policy.validate(new)
                authority={'schema_version':'bf-design-continuation-v1','owner':owner,'previous':previous,'effective':new,
                           'issued':time.time(),'actor':'authenticated-operator','model_profile':profile,
                           'original_grants_and_billing_unchanged':True,
                           'legacy_expiry_storage':'New task grant records issuance time; explicit v2 wall authority determines effective expiry=None.'}
                authority_id='AUTH-'+identity(authority)
                sealed(self.root/owner/'authorizations'/(authority_id+'.json'),authority)
                budget_policy.install(db,new)
                # Conversation creation is deferred before its execution mode is
                # known. Bind a new C grant here; never overwrite any old grant.
                db.execute('INSERT OR IGNORE INTO grants VALUES(?,?,?,?)',
                           (owner,canonical([task['task_id']]),0,authority['issued']))
                db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                           ('model_profile:'+owner,canonical(profile)))
                self.event(owner,'authority_installed',{'authority_id':authority_id,'wall_seconds':None,'ledger_preserved':True},db)
            result={'authority_id':authority_id,'owner':owner,'wall_seconds':None,'model_profile':profile}
            if action=='method_authorize':result['participant_token']=self.store.issue(owner)
            return result
        if action=='inspect':return self.view(owner)
        if action=='environment':return self.environment_view(owner)
        if action=='skill':
            return self.app.skills.action(owner,{'action':'activate','skill_id':body.get('skill_id')})
        if action=='start':
            if not operator:raise PermissionError('OPERATOR_REQUIRED')
            from .controller import start
            return start(self,owner,body.get('dry_run',False))
        if action=='qualify':
            if not operator:raise PermissionError('OPERATOR_REQUIRED')
            from .qualification import qualify
            task=self.task(owner)
            path=self.root/'qualifications'/task['contract']['validation_id'];path.mkdir(parents=True,exist_ok=True)
            if (path/'qualification.json').is_file():return json.loads((path/'qualification.json').read_text())
            if task['environment'].get('mode')=='native-coupled-C':
                raise ValueError('NATIVE_QUALIFICATION_REQUIRES_SEALED_NO_AGENT_RELEASE')
            report=qualify(task['environment'],path/('attempt-'+str(time.time_ns())))
            if report['passed']:sealed(path/'qualification.json',report)
            return report
        if action=='source':return self.design(owner,body.get('design_id') or self.task(owner)['current_design'])
        if action=='freeze':return self.freeze(owner,body['sources'],body['parent'],'operator' if operator else 'Pi')
        if action=='run':return self.run(owner,body['operation_id'],body['design_id'])
        if action=='job':return self.operation(owner,body['job_id'])
        if action=='check':return self.inspect_check(owner,body['job_id'])
        if action=='observe':return self.observe(owner,body['job_id'],body.get('start',0),body.get('end',6.5),body.get('offset',0),body.get('limit',100))
        if action=='adopt':return self.adopt(owner,body['design_id'],body['expected_revision'],body['rationale'],operator=operator)
        if action=='intent':return self.set_intent(owner,body['kind'],body.get('job_id'),body.get('plan'))
        if action=='events':return self.events(owner,body.get('after',0))
        if action=='ack':return self.acknowledge(owner,body['cursor'])
        if action=='submit':return self.submit(owner,body['job_id'],body['rationale'])
        raise ValueError('DESIGN_ACTION_INVALID')

