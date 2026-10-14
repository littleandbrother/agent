"""Domain execution adapter to the existing fixed engineering worker."""
import json
import hashlib
import zipfile
from pathlib import PurePosixPath
from .. import engineering_projects
from ..store import identity
from .repository import name,file_hash
from .repository_actions import task,object_save,scope


def consumed_input(repo, artifacts, project):
    """Prove the worker's complete source snapshot is the selected commit input."""
    ref=artifacts.get('input.json')
    if not ref:raise ValueError('EXECUTION_INPUT_RECEIPT_REQUIRED')
    path=repo.root/'blobs'/ref['sha256']
    if file_hash(path)!=ref['sha256']:raise ValueError('EXECUTION_INPUT_TAMPER')
    actual=json.loads(path.read_text())
    from ..store import identity
    if actual.get('project_sha256')!=identity(project) or actual.get('project')!=project:
        raise ValueError('EXECUTION_CONSUMED_SOURCE_CONFLICT')
    source_archive=artifacts.get('project-source.zip')
    if source_archive:
        archive=repo.root/'blobs'/source_archive['sha256']
        if file_hash(archive)!=source_archive['sha256']:raise ValueError('EXECUTION_SOURCE_ARCHIVE_TAMPER')
        with zipfile.ZipFile(archive) as z:
            for path,source in project['sources'].items():
                if z.read(path)!=source.encode():raise ValueError('EXECUTION_SOURCE_ARCHIVE_CONFLICT: '+path)
    return {'manifest':project['manifest'], 'sources':{p:hashlib.sha256(s.encode()).hexdigest()
        for p,s in project['sources'].items()},'project_sha256':identity(project),
        'input_receipt_sha256':ref['sha256']}


def reused_execution(repo, db, commit, project, job_id, record, origin):
    consumed=consumed_input(repo,record['artifacts'],project)
    result_path=repo.root/'blobs'/record['artifacts']['result.json']['sha256']
    if file_hash(result_path)!=record['artifacts']['result.json']['sha256']:raise ValueError('EXECUTION_RESULT_TAMPER')
    result=json.loads(result_path.read_text())
    if not result.get('readback_passed') or result['project_sha256']!=consumed['project_sha256']:
        raise ValueError('REUSED_EXECUTION_NOT_VALID')
    return object_save(repo,db,'design_domain_executions','EX',{'project_id':commit['project_id'],
        'domain_commit':commit['id'],'owner':commit['owner'],'job_id':job_id,'status':'SUCCEEDED',
        'kind':project['manifest']['kind'],'project_sha256':consumed['project_sha256'],
        'artifacts':record['artifacts'],'executor_sha256':record.get('executor_sha256'),
        'independent_readback':result['independent_readback'],'consumed_input':consumed,
        'source_author':'Pi','reused':True,'reused_from':origin,
        'job_origin_owner':record.get('job_origin_owner',record.get('origin_owner',record.get('owner')))},
        ['project_id','domain_commit','owner'])


def input_project(repo,commit,manifest_path):
    name(manifest_path)
    if not scope(commit['domain'],manifest_path):raise PermissionError('DOMAIN_PROJECT_SCOPE')
    def source(logical):
        ref=commit['files'].get(logical)
        if not ref:raise ValueError('DOMAIN_SOURCE_NOT_COMMITTED')
        path=repo.root/'blobs'/ref['sha256']
        if file_hash(path)!=ref['sha256']:raise ValueError('DOMAIN_EXECUTION_INPUT_TAMPER')
        return path
    spec=json.loads(source(manifest_path).read_text())
    permitted={'firmware':('firmware-nrf52832-s132',),'power':('spice',)}
    if spec.get('kind') not in permitted.get(commit['domain'],()):raise PermissionError('DOMAIN_EXECUTOR_NOT_QUALIFIED')
    prefix=str(PurePosixPath(manifest_path).parent)
    project=engineering_projects.snapshot(spec,lambda p:source(name(prefix+'/'+p)))
    return project


def failed_execution(repo, engineering, commit, project, job, body):
    """Return the real failed worker input and compiler/solver feedback to Pi."""
    artifacts={}
    with repo.store.connect() as db:
        for ref in (job.get('result') or {}).get('artifacts',[]):
            path=engineering.artifact(commit['owner'],job['id'],ref['name'])
            artifacts[ref['name']]=repo.asset(db,path,ref['sha256'])
        consumed=consumed_input(repo,artifacts,project) if 'input.json' in artifacts else None
        value=object_save(repo,db,'design_domain_executions','EX',{
            'project_id':commit['project_id'],'domain_commit':commit['id'],
            'owner':commit['owner'],'job_id':job['id'],'status':job['status'],
            'error':job.get('error'),'kind':project['manifest']['kind'],
            'project_sha256':identity(project),
            'executor_sha256':job.get('template_sha256'),'artifacts':artifacts,
            'consumed_input':consumed,'reused':False,'source_author':'Pi'},
            ['project_id','domain_commit','owner'])
    diagnostics={}
    for name in ('process.log','solver.log'):
        ref=artifacts.get(name)
        if not ref:continue
        path=repo.root/'blobs'/ref['sha256']
        if file_hash(path)!=ref['sha256']:raise ValueError('EXECUTION_DIAGNOSTIC_TAMPER')
        content=path.read_text(errors='replace');offset=body.get('offset',max(0,len(content)-16000))
        limit=body.get('limit',16000)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=20000:
            raise ValueError('EXECUTION_DIAGNOSTIC_RANGE_INVALID')
        diagnostics[name]={'sha256':ref['sha256'],'bytes':ref['bytes'],
            'content':content[offset:offset+limit],'offset':offset,'total_chars':len(content),
            'next_offset':offset+limit if offset+limit<len(content) else None}
    return {**value,'diagnostics':diagnostics,'diagnostic_missing':not bool(diagnostics)}


def handle(repo,owner,body):
    pid=body['project_id'];repo.project(pid,owner)
    with repo.store.connect() as db:
        commit=repo._object(db,'design_domain_commits',body['domain_commit'],pid)
    if owner!=commit['owner']:
        repo.leader(pid,owner)
        if body['action']=='repository_execute':raise PermissionError('SPECIALIST_EXECUTION_REQUIRED')
    project=input_project(repo,commit,body.get('path') or ('project-fw-s132/project.json' if commit['domain']=='firmware' else 'project-chain/project.json'))
    from ..store import identity
    signature=identity(project)
    engineering=repo.lab.app.engineering
    if body['action']=='repository_execute':
        # Exact unchanged inputs already have a frozen successful job. Return it;
        # never dispatch a solver just to exercise a new architecture.
        base=repo.system(pid,commit['base_system'])
        for jid,ref in base['jobs'].items():
            if ref.get('project_sha256')==signature:
                return repo.mutate(owner,body,lambda db:reused_execution(repo,db,commit,project,jid,ref,base['id']))
        with repo.store.connect() as db:
            previous=[json.loads(r['value']) for r in db.execute('SELECT value FROM design_domain_executions WHERE project=? ORDER BY rowid DESC',(pid,))]
        for ref in previous:
            if ref['status']=='SUCCEEDED' and ref['project_sha256']==signature and ref.get('executor_sha256')==file_hash(engineering_projects.__file__):
                return repo.mutate(owner,body,lambda db:reused_execution(repo,db,commit,project,ref['job_id'],ref,ref['id']))
        def apply(db):
            job=engineering.submit_repository(owner,'repo-exec-'+identity({'commit':commit['id'],'input':signature}),project,
                {'project_id':pid,'domain_commit':commit['id'],'manifest':body['path']},db=db)
            return {'project_id':pid,'domain_commit':commit['id'],'job_id':job['id'],'status':job['status'],'reused':False}
        result=repo.mutate(owner,body,apply)
        engineering.dispatch_repository(owner,result['job_id'])
        return result
    # Completion is observed from the engineering ledger, not Agent prose.
    jid=body.get('job_id')
    if not jid:raise ValueError('DOMAIN_EXECUTION_JOB_REQUIRED')
    job=engineering.get(commit['owner'],jid)
    binding=job.get('repository_binding',{})
    if binding.get('domain_commit')!=commit['id'] or job.get('project_sha256')!=signature:raise ValueError('DOMAIN_EXECUTION_IDENTITY_CONFLICT')
    if job['status'] in ('FAILED','CANCELLED'):
        return failed_execution(repo,engineering,commit,project,job,body)
    if job['status']!='SUCCEEDED':return {'status':job['status'],'job_id':jid,'error':job.get('error')}
    with repo.store.connect() as db:
        artifacts={}
        for ref in job['result']['artifacts']:
            path=engineering.artifact(commit['owner'],jid,ref['name'])
            artifacts[ref['name']]=repo.asset(db,path,ref['sha256'])
        value=object_save(repo,db,'design_domain_executions','EX',{'project_id':pid,'domain_commit':commit['id'],
            'owner':commit['owner'],'job_id':jid,'status':'SUCCEEDED','kind':project['manifest']['kind'],
            'project_sha256':signature,'artifacts':artifacts,'executor_sha256':job['template_sha256'],
            'independent_readback':job['result']['independent_readback'],'consumed_input':consumed_input(repo,artifacts,project),
            'reused':False,'job_origin_owner':commit['owner'],'source_author':'Pi'},['project_id','domain_commit','owner'])
    return value
