"""Pi SDK sessions for repository lead and specialists; no product planner here."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

from .. import budget_policy, launcher
from ..model_profile import for_owner
from ..runtime_config import PI, NODE, require_capability, DEVELOPMENT_PROFILE
from ..store import canonical, identity
from .contracts import sealed, sha
from .repository_actions import task, materialize


def freeze(lab):
    from .resources import bundle
    from ..skill_resources import freeze_resources, source_bundle
    source = PI/'packages/bf-agent'
    proc = subprocess.run([str(PI/'node_modules/.bin/tsgo'), '-p', str(source/'tsconfig.json')],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode: raise ValueError('REPOSITORY_PI_BUILD_FAILED:' + proc.stdout[-2000:] + proc.stderr[-1000:])
    modules = ('repository-task', 'extensions/bf-repository', 'extensions/bf-design')
    professional, professional_files = source_bundle()
    design, design_files = bundle(native=True)
    if set(professional_files) & set(design_files): raise ValueError('RESOURCE_PATH_COLLISION')
    merged = {**professional, 'skills': professional['skills'] + design['skills'],
              'plugins': professional['plugins'] + design['plugins'],
              'files': {**professional['files'], **design['files']}}
    merged.pop('sha256', None)
    if len({x['id'] for x in merged['skills']}) != len(merged['skills']): raise ValueError('RESOURCE_SKILL_COLLISION')
    merged['sha256'] = identity(merged)
    resources = merged, {**professional_files, **design_files}
    manifest = {'schema_version': 'bf-repository-controller-v2', 'controller': 'pi-sdk-repository',
       'files': {folder+'/'+n+'.'+suffix: sha(source/folder/(n+'.'+suffix)) for folder, suffix in [('src','ts'),('dist','js')] for n in modules},
       'python_bindings': {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))
                           if p.name.startswith(('repository', 'report_', 'feedback_'))},
       'review_fixtures': {p.name:sha(p) for p in sorted(Path(__file__).parent.glob('repository-review-*.json'))},
       'context_bindings': {n: sha(Path(__file__).parent.parent/n) for n in
                           ('provider.py','context.py','model_profile.py','budget_policy.py','recovery.py','skill_resources.py')},
       'pi_lock_sha256': sha(PI/'package-lock.json'), 'tools': ['bf_repository'],
       'resource_manifest': resources[0],
       'engineering_bindings': {n:sha(Path(__file__).parent.parent/n) for n in ('engineering.py','engineering_projects.py','nordic_sdk.py')}, 'development_profile_sha256': DEVELOPMENT_PROFILE['sha256'],
       'baseline': DEVELOPMENT_PROFILE['baseline'], 'device_decision_actor': 'Pi',
       'source_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=PI,text=True).strip(),
       'baseline_source_commit': DEVELOPMENT_PROFILE['base_commit'],
       'native_dispatch': DEVELOPMENT_PROFILE['capabilities']['native']}
    manifest['harness_id'] = 'H-' + identity(manifest)
    dest = lab.root/'harnesses'/manifest['harness_id']
    for folder, suffix in [('src','ts'),('dist','js')]:
        for n in modules:
            file = dest/folder/(n+'.'+suffix); file.parent.mkdir(parents=True,exist_ok=True)
            if file.exists() and sha(file) != sha(source/folder/(n+'.'+suffix)): raise ValueError('HARNESS_TAMPER')
            if not file.exists(): shutil.copyfile(source/folder/(n+'.'+suffix),file)
    if not (dest/'node_modules').exists(): (dest/'node_modules').symlink_to(PI/'node_modules',target_is_directory=True)
    if not (dest/'resources/manifest.json').exists(): freeze_resources(dest/'resources', resources)
    sealed(dest/'manifest.json',manifest)
    return dest,manifest


def state(repo, owner, target=None):
    pid = repo.bound(owner); p = repo.project(pid,owner)
    target = target or owner
    if target != owner:
        repo.leader(pid,owner)
        t = task(repo,target)
        if t['project_id'] != pid: raise PermissionError('SPECIALIST_PROJECT_CONFLICT')
    else:
        t = None if p['owner'] == owner else task(repo,owner)
    with repo.store.connect() as db:
        conversation = db.execute('SELECT status,error FROM conversations WHERE id=?',(target,)).fetchone()
        rows = [dict(r) for r in db.execute('SELECT id,status,charged,reserved,usage FROM model_requests WHERE owner=?',(target,))]
        branch = None if t is None else dict(db.execute('SELECT * FROM design_branch_heads WHERE project=? AND domain=? AND branch=?',
            (pid,t['role'],t['branch'])).fetchone())
    running = repo.lab.controllers.get(target)
    status = 'RUNNING' if running and running.is_alive() else ('FAILED' if conversation['status']=='FAILED' else (t['status'] if t else conversation['status']))
    return {'owner':target,'project_id':pid,'status':status,'revision':p['revision'], 'adopted':p['adopted'],
            'current_system':p['submitted'], 'task':t, 'branch':branch,'error':conversation['error'],
            'model_calls':len(rows),'unknown_requests':[r['id'] for r in rows if r['status']=='UNKNOWN'],
            'cost_upper_bound_usd':sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows)}


def start(repo, owner, goal=None, dry_run=False, purpose='design'):
    require_capability('agent')
    require_capability('model')
    project = repo.project(repo.bound(owner),owner)
    from .repository_reference_qualification import require as require_reference
    system = repo.system(project['id'],project['submitted'])
    require_reference(repo, system)
    from .repository_feedback_qualification import require as require_feedback
    require_feedback(repo, system)
    if owner in repo.lab.controllers and repo.lab.controllers[owner].is_alive(): raise ValueError('REPOSITORY_CONTROLLER_ALREADY_RUNNING')
    with repo.store.connect() as db:
        if not budget_policy.unbounded_time(db,owner): raise ValueError('EXPLICIT_CONTINUATION_AUTHORITY_REQUIRED')
        if repo.lab.app.provider.recovery.unknown_blockers(db,owner): raise ValueError('PROVIDER_USAGE_UNKNOWN_STOP')
    if purpose not in ('design','report'): raise ValueError('REPOSITORY_RUN_PURPOSE')
    thread=threading.Thread(target=run,args=(repo,owner,goal,dry_run,purpose),daemon=True)
    repo.lab.controllers[owner]=thread;thread.start()
    return {'owner':owner,'project_id':repo.bound(owner),'status':'STARTING','controller':'pi-sdk-repository'}


def run(repo,owner,goal,dry_run,purpose='design'):
    lab=repo.lab; app=lab.app; home=lab.store.root.parent
    output=home/'sessions'/owner;output.mkdir(parents=True,exist_ok=True)
    attempt=output/'repository-attempts'/('attempt-'+str(time.time_ns()));attempt.mkdir(parents=True)
    receipt={'schema_version':'bf-repository-pi-run-v2','owner':owner,'project_id':repo.bound(owner),
             'started':time.time(),'status':'STARTING','dry_run':dry_run,'purpose':purpose,'fee_ledger_preserved':True}
    proc=None
    try:
        harness,manifest=freeze(lab);receipt['harness']=manifest
        p=repo.project(repo.bound(owner),owner)
        professional = p['owner'] != owner
        if professional:
            t=task(repo,owner); workspace=materialize(repo,t)
            if goal is None: goal=canonical({'professional_task':t,'goal':'Complete the assigned question, submit an actual Domain Commit and finish.'})
            if purpose == 'design':
                with repo.store.connect() as db: db.execute("UPDATE design_professional_tasks SET status='RUNNING' WHERE owner=?",(owner,))
        else:
            workspace=repo.root/'lead'/owner;workspace.mkdir(parents=True,exist_ok=True)
            if goal is None:
                with repo.store.connect() as db:
                    row=db.execute('SELECT text FROM chat_messages WHERE conversation=? ORDER BY created DESC LIMIT 1',(owner,)).fetchone()
                    goal=row['text']
        (workspace/'.tmp').mkdir(exist_ok=True)
        receipt['sandbox']=launcher.preflight(workspace,harness)
        with lab.store.connect() as db:
            profile=for_owner(db,owner)
            db.execute('UPDATE conversations SET harness=? WHERE id=?',(str(harness),owner))
            db.execute("UPDATE chat_messages SET status='SENT' WHERE conversation=? AND status='QUEUED'",(owner,))
        token=lab.store.issue(owner)
        config={'workspace':str(workspace),'service':f'http://127.0.0.1:{app.conversations.port}',
                'token':token,'owner':owner,'goal':goal,'messageId':attempt.name,
                'harnessIdentity':manifest['harness_id'],'modelProfile':profile,'dryRun':dry_run,'purpose':purpose}
        receipt.update(model_profile=profile,harness_id=manifest['harness_id'])
        app.conversations.state(owner,'RUNNING')
        with (output/'trace.jsonl').open('a') as stdout, (attempt/'stderr.log').open('w') as stderr:
            proc=subprocess.Popen(['/usr/bin/sandbox-exec','-p',launcher.seatbelt(workspace,harness,app.conversations.port),
                str(NODE),str(harness/'dist/repository-task.js')],cwd=workspace,
                env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','TMPDIR':str(workspace/'.tmp'),'LANG':'en_US.UTF-8'},
                stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,start_new_session=True)
            app.conversations.processes[owner]=proc;app.conversations.starting.add(owner)
            receipt.update(pid=proc.pid,status='RUNNING');sealed(attempt/'dispatch.json',receipt)
            proc.stdin.write((canonical(config)+'\n').encode());proc.stdin.flush()
            while proc.poll() is None:
                with lab.store.connect() as db:
                    if not budget_policy.unbounded_time(db,owner): os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
                app.conversations.ingest(owner,execution_state=False)
            proc.stdin.close()
        receipt.update(exit_code=proc.returncode,status='COMPLETED' if proc.returncode==0 else 'FAILED')
        if professional and purpose == 'design':
            current=task(repo,owner)
            if current['status']=='RUNNING':
                with lab.store.connect() as db:db.execute("UPDATE design_professional_tasks SET status='REVIEW_REQUIRED' WHERE owner=?",(owner,))
        app.conversations.state(owner,'IDLE' if proc.returncode==0 else 'FAILED',
            None if proc.returncode==0 else (attempt/'stderr.log').read_text()[-1800:])
    except Exception as error:
        receipt.update(status='FAILED',error=type(error).__name__+': '+str(error)[:1600])
        app.conversations.state(owner,'FAILED',receipt['error'])
        if purpose == 'design':
            with lab.store.connect() as db:db.execute("UPDATE design_professional_tasks SET status='BLOCKED' WHERE owner=? AND status IN ('QUEUED','RUNNING')",(owner,))
    finally:
        if proc and proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=5)
        app.conversations.ingest(owner,execution_state=False)
        trace=output/'trace.jsonl'
        if trace.exists():shutil.copyfile(trace,attempt/'trace-sealed.jsonl');receipt['trace_sha256']=sha(attempt/'trace-sealed.jsonl')
        receipt['ended']=time.time();sealed(attempt/'receipt.json',receipt)
        launcher.write_session_receipt(output/'receipt.json',receipt)
        app.conversations.processes.pop(owner,None);app.conversations.starting.discard(owner)
        lab.event(owner,'repository_controller_finished',{'status':receipt['status'],'receipt_sha256':sha(attempt/'receipt.json'),
                   'receipt_path':str(attempt/'receipt.json'),'harness_id':receipt.get('harness_id')})


def handle(repo,owner,body,operator):
    action=body['action']
    if action=='repository_state':return state(repo,owner,body.get('task_owner'))
    if action=='repository_start':
        if not operator:raise PermissionError('OPERATOR_REQUIRED')
        return start(repo,owner,body.get('goal'),body.get('dry_run',False),body.get('purpose','design'))
    if action=='repository_run_task':
        p=repo.leader(body['project_id'],owner); target=body['task_owner']; t=task(repo,target)
        if t['project_id']!=p['id']:raise PermissionError('SPECIALIST_PROJECT_CONFLICT')
        with repo.store.connect() as db:
            if not budget_policy.unbounded_time(db,owner):raise ValueError('LEAD_AUTHORITY_REQUIRED')
        if t['status']=='SUBMITTED':return state(repo,owner,target)
        repo.lab.handle(target,{'action':'method_authorize','task_id':'method-study-repository-'+t['id'],
              'wall_authorization_text':'持续运行 不设置时间限制','model_profile':'engineering-reasoning-efficient-v5'},True)
        return start(repo,target)
    if action=='repository_close':
        def apply(db):
            p=repo.leader(body['project_id'],owner,db)
            from .repository_reports import required_report
            required_report(repo, owner, repo.system(p['id'],p['submitted'],db))
            if not db.execute('SELECT 1 FROM design_repository_releases WHERE project=? AND target=?',(p['id'],p['submitted'])).fetchone():
                raise ValueError('SAME_VERSION_RELEASE_REQUIRED')
            value={'project_id':p['id'],'status':'REVIEW_DELIVERED','conclusion':body['conclusion'],'system_commit':p['submitted']}
            repo.lab.event(owner,'repository_cycle_closed',value,db)
            return value
        return repo.mutate(owner,body,apply)
    if action in ('repository_skill_catalog','repository_skill','repository_skill_resource'):
        translated={'repository_skill_catalog':'catalog','repository_skill':'activate','repository_skill_resource':'resource'}[action]
        keys=('skill_id',) if translated=='activate' else ('path','offset','limit') if translated=='resource' else ()
        return repo.lab.app.skills.action(owner,{'action':translated,**{k:body[k] for k in keys if k in body}})
    return None
