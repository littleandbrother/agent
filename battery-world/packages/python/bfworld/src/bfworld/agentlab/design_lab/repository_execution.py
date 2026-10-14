"""Domain execution adapter to the existing fixed engineering worker."""
import json
from pathlib import PurePosixPath
from .. import engineering_projects
from .repository import name,file_hash
from .repository_actions import task,object_save,scope


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
                return {'status':'SUCCEEDED','job_id':jid,'reused':True,'domain_commit':commit['id']}
        if commit['target_build']=='UNCHANGED_REUSE' and commit['model_execution']=='UNCHANGED_REUSE':
            return {'status':'SUCCEEDED','reused':True,'domain_commit':commit['id'],'jobs':list(base['jobs'])}
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
    if job['status']!='SUCCEEDED':return {'status':job['status'],'job_id':jid,'error':job.get('error')}
    with repo.store.connect() as db:
        artifacts={}
        for ref in job['result']['artifacts']:
            path=engineering.artifact(commit['owner'],jid,ref['name'])
            artifacts[ref['name']]=repo.asset(db,path,ref['sha256'])
        value=object_save(repo,db,'design_domain_executions','EX',{'project_id':pid,'domain_commit':commit['id'],
            'owner':commit['owner'],'job_id':jid,'status':'SUCCEEDED','kind':project['manifest']['kind'],
            'project_sha256':signature,'artifacts':artifacts,'executor_sha256':job['template_sha256'],
            'independent_readback':job['result']['independent_readback'],'source_author':'Pi'},['project_id','domain_commit','owner'])
    return value
