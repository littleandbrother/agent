"""Design Repository records owned by the existing DesignLab and its journal.

The repository adds immutable design objects; it does not dispatch an Agent or
own another task controller. All mutations use design_operations/design_events.
"""
import hashlib
import json
import mimetypes
from pathlib import Path, PurePosixPath
import re
import time
import zipfile

from ..store import canonical, identity
from .contracts import sealed

MODE = 'design-repository-v2'
DOMAINS = ('mechanical', 'power', 'firmware', 'assembly')
STATUSES = ('PASS', 'FAIL', 'UNEVALUABLE', 'NOT_CHECKED', 'RECHECK_REQUIRED')


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1024*1024), b''):
            h.update(part)
    return h.hexdigest()


def name(value):
    if not isinstance(value, str) or not 1<=len(value)<=240 or '\\' in value or any(ord(c)<32 for c in value):
        raise ValueError('REPOSITORY_NAME_INVALID')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or str(p) != value:
        raise ValueError('REPOSITORY_PATH_INVALID')
    return value


class Repository:
    def __init__(self, lab, profile=None):
        self.lab, self.store = lab, lab.store
        if profile is None:
            from ..runtime_config import DEVELOPMENT_PROFILE
            profile = DEVELOPMENT_PROFILE
        self.profile = profile
        self.root = lab.root/'repository'
        self.root.mkdir(exist_ok=True)
        with self.store.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS design_projects(id TEXT PRIMARY KEY,owner TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,revision INTEGER NOT NULL,adopted TEXT NOT NULL,submitted TEXT,
                baseline TEXT NOT NULL,requirements TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_system_commits(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                parent TEXT,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_domain_commits(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                domain TEXT NOT NULL,branch TEXT NOT NULL,parent TEXT,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_interface_contracts(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                name TEXT NOT NULL,parent TEXT,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_branch_heads(project TEXT NOT NULL,domain TEXT NOT NULL,
                branch TEXT NOT NULL,head TEXT,revision INTEGER NOT NULL,
                PRIMARY KEY(project,domain,branch));
              CREATE TABLE IF NOT EXISTS design_integration_requests(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                owner TEXT NOT NULL,base TEXT NOT NULL,status TEXT NOT NULL,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_repository_validations(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                target TEXT NOT NULL,kind TEXT NOT NULL,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_professional_tasks(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                owner TEXT UNIQUE NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_professional_task_history(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                owner TEXT NOT NULL,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_repository_assets(id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,
                bytes INTEGER NOT NULL,media_type TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_repository_releases(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                target TEXT NOT NULL,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_domain_executions(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                domain_commit TEXT NOT NULL,owner TEXT NOT NULL,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_method_experiments(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                status TEXT NOT NULL,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS design_task_executions(id TEXT PRIMARY KEY,project TEXT NOT NULL,
                target TEXT NOT NULL,value TEXT NOT NULL);
            ''')
            from .repository_work import install
            install(db)

    def bound(self, owner):
        with self.store.connect() as db:
            row = db.execute('SELECT id FROM design_projects WHERE owner=?',(owner,)).fetchone()
            if row: return row['id']
            row = db.execute('SELECT project FROM design_professional_tasks WHERE owner=?',(owner,)).fetchone()
            if not row: row = db.execute('SELECT project FROM design_scoped_tasks WHERE owner=?',(owner,)).fetchone()
            return row['project'] if row else None

    def project(self, project, owner=None, db=None):
        if db is None:
            with self.store.connect() as connection: return self.project(project,owner,connection)
        row = db.execute('SELECT * FROM design_projects WHERE id=?',(project,)).fetchone()
        if not row: raise ValueError('DESIGN_PROJECT_NOT_FOUND')
        if owner is not None and owner != row['owner'] and not db.execute(
                'SELECT 1 FROM design_professional_tasks WHERE project=? AND owner=?',(project,owner)).fetchone() and not db.execute(
                'SELECT 1 FROM design_scoped_tasks WHERE project=? AND owner=?',(project,owner)).fetchone():
            raise PermissionError('DESIGN_PROJECT_NOT_OWNED')
        value = dict(row)
        for k in ('baseline','requirements'): value[k]=json.loads(value[k])
        return value

    def leader(self, project, owner, db=None):
        value=self.project(project,owner,db)
        if value['owner']!=owner: raise PermissionError('DESIGN_LEAD_REQUIRED')
        return value

    def mutate(self, owner, body, callback):
        key=body.get('operation_id')
        if not isinstance(key,str) or not 1<=len(key)<=100: raise ValueError('OPERATION_ID_REQUIRED')
        request={**body,'repository':True,'task_id':'repository:'+str(body.get('project_id','baseline-import'))}
        request_hash=identity(request)
        op_id='R-'+identity({'owner':owner,'operation':key})
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM design_operations WHERE owner=? AND operation=?',(owner,key)).fetchone()
            if old:
                if old['request_hash']!=request_hash: raise ValueError('REPOSITORY_OPERATION_CONFLICT')
                if old['status']!='SUCCEEDED': raise ValueError('REPOSITORY_OPERATION_STATE_UNKNOWN')
                return json.loads(old['result'])
            db.execute('INSERT INTO design_operations VALUES(?,?,?,?,?,?,?,?,?)',
                       (op_id,owner,key,request_hash,canonical(request),'RUNNING',None,None,time.time()))
            value=callback(db)
            db.execute("UPDATE design_operations SET status='SUCCEEDED',result=? WHERE id=?",(canonical(value),op_id))
            self.lab.event(owner,'repository_operation',{'id':op_id,'action':body['action'],
                'project_id':value.get('project_id',body.get('project_id')),'result_id':value.get('id')},db)
            return value

    def _baseline(self):
        if not self.profile: raise PermissionError('ISOLATED_V2_PROFILE_REQUIRED')
        ref=self.profile['baseline'];root=Path(ref['path'])
        if file_hash(root/'manifest.json')!=ref['manifest_sha256']: raise ValueError('BASELINE_MANIFEST_CHANGED')
        return root,json.loads((root/'manifest.json').read_text())

    def baseline_file(self, logical):
        root,manifest=self._baseline();name(logical)
        ref=manifest['files'].get(logical)
        if not ref: raise ValueError('BASELINE_ASSET_NOT_FROZEN')
        path=root/logical
        if path.is_symlink() or not path.is_file() or file_hash(path)!=ref['sha256']:
            raise ValueError('BASELINE_ASSET_CHANGED')
        return path,ref

    def asset(self, db, path, expected=None):
        path=Path(path);digest=file_hash(path)
        if expected and digest!=expected: raise ValueError('ASSET_SOURCE_CHANGED')
        key='B-'+digest;dest=self.root/'blobs'/digest
        dest.parent.mkdir(exist_ok=True)
        if not dest.exists():
            with dest.open('xb') as f: f.write(path.read_bytes())
            dest.chmod(0o400)
        elif file_hash(dest)!=digest: raise ValueError('REPOSITORY_BLOB_CHANGED')
        media=mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
        db.execute('INSERT OR IGNORE INTO design_repository_assets VALUES(?,?,?,?)',
                   (key,digest,path.stat().st_size,media))
        return {'asset_id':key,'sha256':digest,'bytes':path.stat().st_size,'media_type':media}

    def _object(self, db, table, key, project):
        row=db.execute('SELECT value,project FROM '+table+' WHERE id=?',(key,)).fetchone()
        if not row or row['project']!=project: raise PermissionError('REPOSITORY_OBJECT_NOT_OWNED')
        value=json.loads(row['value'])
        # All object IDs include their immutable payload; time lives in events.
        if key!=value['id'] or key.split('-',1)[1]!=identity({k:v for k,v in value.items() if k!='id'}):
            raise ValueError('REPOSITORY_OBJECT_TAMPER')
        return value

    def system(self, project, key, db=None):
        if db is None:
            with self.store.connect() as connection: return self.system(project,key,connection)
        return self._object(db,'design_system_commits',key,project)

    def _save_system(self, db, owner, value):
        if value.get('task_definition'):
            from .repository_task_standards import check_files
            check_files(value['task_definition'], value['files'],
                        lambda path: (self.root/'blobs'/value['files'][path]['sha256']).read_text())
        value={**value,'id':'SC-'+identity(value)}
        db.execute('INSERT OR IGNORE INTO design_system_commits VALUES(?,?,?,?)',
                   (value['id'],value['project_id'],value.get('parent'),canonical(value)))
        db.execute('INSERT OR IGNORE INTO design_snapshots VALUES(?,?,?)',(owner,value['id'],canonical(value)))
        sealed(self.root/'systems'/value['id']/'snapshot.json',value)
        return value

    def import_baseline(self, owner, body, operator):
        if not operator: raise PermissionError('OPERATOR_REQUIRED')
        root,manifest=self._baseline();p01=manifest['p01'];original=p01['owner']
        if owner in self.profile.get('protected_owners',[]): raise PermissionError('ORIGINAL_OWNER_PROTECTED')
        project='PR-'+identity({'baseline':self.profile['baseline'],'paper':'P01','owner':owner})
        def apply(db):
            if db.execute('SELECT 1 FROM design_projects WHERE owner=?',(owner,)).fetchone():
                raise ValueError('DESIGN_PROJECT_ALREADY_EXISTS')
            if not db.execute('SELECT 1 FROM conversations WHERE id=?',(owner,)).fetchone():
                raise ValueError('DESIGN_REQUIRES_EXISTING_PI_CONVERSATION')
            systems={}
            for role in ('adopted_design','submitted_design'):
                old_id=p01[role];prefix=f'private/design-lab/{original}/designs/{old_id}/'
                snapshot_path,_=self.baseline_file(prefix+'snapshot.json')
                snapshot=json.loads(snapshot_path.read_text());files={}
                for logical,ref in snapshot['files'].items():
                    path,_=self.baseline_file(prefix+'inputs/'+logical)
                    files[logical]=self.asset(db,path,ref['sha256'])
                jobs={}
                for job,ref in snapshot['selected_jobs'].items():
                    outputs={}
                    job_prefix=f'p01/jobs/{job}/'
                    for logical in manifest['files']:
                        if logical.startswith(job_prefix):
                            path,pin=self.baseline_file(logical)
                            outputs[logical[len(job_prefix):]]=self.asset(db,path,pin['sha256'])
                    jobs[job]={**ref,'artifacts':outputs,'origin_owner':original,'dispatched_in_v2':False}
                gates={}
                if role=='submitted_design':
                    for gate in p01['gates']:
                        logical='campaign/'+gate['evidence']['path']
                        path,_=self.baseline_file(logical)
                        gates[gate['id']]={'status':gate['status'],'label':gate['label'],
                            'evidence':self.asset(db,path,gate['evidence']['sha256']),
                            'dependency_binding':'original-submitted-candidate','origin_design_id':old_id}
                systems[role]=self._save_system(db,owner,{'schema_version':'bf-system-commit-v2',
                    'project_id':project,'parent':None,'origin_design_id':old_id,'origin_owner':original,
                    'import_role':role,'baseline':self.profile['baseline'],'domain_commits':{},'contracts':{},
                    'files':files,'jobs':jobs,'validations':gates,'physical':p01['physical'],
                    'digital_status':p01['digital_status'] if gates else 'NOT_CHECKED',
                    'provenance':'byte-exact existing Pi candidate; Codex metadata import',
                    'design_changes':[],'history_fabricated':False})
            task_id='task-'+project
            requirements={'goal':'P01 full digital engineering under the frozen first-version use case',
                'scope_source':self.profile['baseline'],'required_gates':[g['id'] for g in p01['gates']],
                'manual_mcu_admission':True,'physical':'NOT_TESTED'}
            db.execute('INSERT INTO design_projects VALUES(?,?,?,?,?,?,?,?)',
                (project,owner,'P01 TENG Wireless Sensing Node',1,systems['adopted_design']['id'],
                 systems['submitted_design']['id'],canonical(self.profile['baseline']),canonical(requirements)))
            db.execute('INSERT INTO design_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (owner,task_id,canonical({'task_id':task_id,**requirements}),
                 canonical({'mode':MODE,'environment_id':self.profile['id'],'project_id':project}),
                 systems['adopted_design']['id'],1,canonical({'kind':'CONTINUE'}),canonical([]),'IDLE',0,
                 canonical({'origin_submission':p01['submission_id'],'system_commit':systems['submitted_design']['id']})))
            self.lab.event(owner,'baseline_project_imported',{'project_id':project,
                'adopted':systems['adopted_design']['id'],'submitted':systems['submitted_design']['id'],
                'original_adopted':p01['adopted_design'],'original_submitted':p01['submitted_design'],
                'original_owner':original,'engineering_changed':False},db)
            return {'project_id':project,'id':systems['submitted_design']['id'],
                'adopted':systems['adopted_design']['id'],'submitted':systems['submitted_design']['id'],
                'files':len(systems['submitted_design']['files']),'gate_statuses':{k:v['status'] for k,v in systems['submitted_design']['validations'].items()}}
        return self.mutate(owner,body,apply)

    def view(self, project, owner):
        with self.store.connect() as db:
            p=self.project(project,owner,db)
            systems=[json.loads(r['value']) for r in db.execute('SELECT value FROM design_system_commits WHERE project=? ORDER BY rowid',(project,))]
            from .repository_validation import qualification
            for system in systems:
                system['current_qualification']=qualification(self,system,db)
            def rows(table): return [json.loads(r['value']) for r in db.execute('SELECT value FROM '+table+' WHERE project=? ORDER BY rowid',(project,))]
            return {'schema_version':'bf-design-project-view-v2','project':p,'systems':systems,
                'domain_commits':rows('design_domain_commits'),'contracts':rows('design_interface_contracts'),
                'integration_requests':rows('design_integration_requests'),'validations':rows('design_repository_validations'),
                'professional_tasks':[{**json.loads(r['value']),'status':r['status']} for r in db.execute('SELECT value,status FROM design_professional_tasks WHERE project=? ORDER BY rowid',(project,))],'releases':rows('design_repository_releases'),
                'executions':rows('design_domain_executions'),'experiments':rows('design_method_experiments'),
                'task_executions': rows('design_task_executions'),
                'scoped_tasks': [{**json.loads(r['value']), 'status': r['status']} for r in db.execute(
                    'SELECT value,status FROM design_scoped_tasks WHERE project=? ORDER BY rowid',(project,))],
                'scoped_results': rows('design_scoped_results'), 'work_policies': rows('design_work_policies'),
                'professional_task_history':rows('design_professional_task_history'),
                'branches':[dict(r) for r in db.execute('SELECT * FROM design_branch_heads WHERE project=?',(project,))]}

    def artifact(self, project, owner, system_id, logical):
        self.project(project,owner);name(logical)
        system=self.system(project,system_id)
        ref=system['files'].get(logical)
        if not ref: raise ValueError('REPOSITORY_ARTIFACT_NOT_IN_SYSTEM')
        path=self.root/'blobs'/ref['sha256']
        if file_hash(path)!=ref['sha256']: raise ValueError('REPOSITORY_BLOB_CHANGED')
        return path,ref

    def handle(self, owner, body, operator=False):
        action=body.get('action')
        from .repository_work import task as scoped_task, guard as work_guard, handle as work_actions
        assigned=scoped_task(self,owner)
        if assigned:
            project=body.get('project_id') or assigned['project_id']
            if project!=assigned['project_id']: raise PermissionError('SCOPED_WORK_PROJECT_CONFLICT')
            work_guard(self,owner,{**body,'project_id':project},operator)
            body={**body,'system_id':body.get('system_id',assigned['base_system'])}
        if action in ('repository_task_assessment_schema', 'repository_task_assess'):
            from .repository_task_intake import schema, validate
            if action == 'repository_task_assessment_schema': return schema()
            value = body.get('assessment')
            if isinstance(value, str): value = json.loads(value)
            return validate(body.get('request'), value)
        if action=='repository_import': return self.import_baseline(owner,body,operator)
        from .repository_task_actions import handle as task_actions
        if action in ('repository_task_schema', 'repository_task_create'):
            return task_actions(self, owner, body, operator)
        project=body.get('project_id') or self.bound(owner)
        if not project: raise ValueError('DESIGN_PROJECT_NOT_BOUND')
        self.project(project,owner)
        work_guard(self,owner,{**body,'project_id':project},operator)
        work_value=work_actions(self,owner,{**body,'project_id':project},operator)
        if work_value is not None: return work_value
        task_value = task_actions(self, owner, {**body, 'project_id': project}, operator)
        if task_value is not None: return task_value
        if (action == 'repository_archive_read' or
                action in ('repository_read', 'repository_workspace_read') and
                str(body.get('path', '')).startswith('context-records/')):
            from ..context import ContextArchive
            return ContextArchive(self.store.root.parent, owner).read(
                body['path'], body.get('offset', 0), body.get('limit', 8000), body.get('pointer'))
        if action=='repository_view': return self.view(project,owner)
        if action=='repository_system': return self.system(project,body['system_id'])
        if action=='repository_read':
            if body.get('domain_commit'):
                with self.store.connect() as db:
                    commit=self._object(db,'design_domain_commits',body['domain_commit'],project)
                system=self.system(project,commit['base_system'])
                ref={**system['files'],**commit['files']}.get(name(body['path']))
                if not ref:raise ValueError('REPOSITORY_ARTIFACT_NOT_IN_COMMIT')
                path=self.root/'blobs'/ref['sha256']
                if file_hash(path)!=ref['sha256']:raise ValueError('REPOSITORY_BLOB_CHANGED')
            else:
                path,ref=self.artifact(project,owner,body['system_id'],body['path'])
            offset=body.get('offset',0);limit=body.get('limit',12000)
            if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=24000: raise ValueError('REPOSITORY_READ_RANGE')
            text=path.read_text(errors='replace')
            return {**ref,'path':body['path'],'offset':offset,'total_chars':len(text),'content':text[offset:offset+limit],
                'next_offset':offset+limit if offset+limit<len(text) else None}
        from .repository_controller import handle as controller
        value=controller(self,owner,{**body,'project_id':project},operator)
        if value is not None:return value
        from .repository_experiments import handle as experiment
        value=experiment(self,owner,{**body,'project_id':project},operator)
        if value is not None:return value
        from .repository_actions import handle
        value=handle(self,owner,{**body,'project_id':project},operator)
        if value is not None:return value
        raise ValueError('REPOSITORY_ACTION_UNKNOWN')
