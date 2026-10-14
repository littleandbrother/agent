"""Frozen Pi-native controller transport; no Codex design planner or retries."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time
from .. import launcher, budget_policy
from ..runtime_config import PI, NODE
from ..model_profile import for_owner as model_profile
from ..store import canonical, identity
from .contracts import sha, sealed


def freeze(lab,native=False):
    from .resources import bundle
    from ..skill_resources import freeze_resources
    resources=bundle(native=native)
    source=PI/'packages/bf-agent'
    result=subprocess.run([str(PI/'node_modules/.bin/tsgo'),'-p',str(source/'tsconfig.json')],
                          capture_output=True,text=True,timeout=60)
    if result.returncode:raise ValueError('DESIGN_APP_BUILD_FAILED:'+result.stdout[-2000:]+result.stderr[-2000:])
    modules=('design-task','extensions/bf-design')
    code={folder+'/'+name+'.'+suffix:sha(source/folder/(name+'.'+suffix))
          for folder,suffix in [('src','ts'),('dist','js')] for name in modules}
    apparatus=Path(__file__).resolve().parent
    manifest={'schema_version':'bf-design-controller-v1','controller':'pi-native-loop',
              'files':code,'pi_lock_sha256':sha(PI/'package-lock.json'),
              'python_bindings':{p.name:sha(p) for p in sorted(apparatus.glob('*.py'))},
              'context_bindings':{n:sha(apparatus.parent/n) for n in
                    ('provider.py','context.py','model_profile.py','budget_policy.py','recovery.py','skill_resources.py','engineering.py','runtime_config.py')},
              'tools':['bf_design'],'skills':'versioned-on-demand-design-lab-resources',
              'resource_manifest':resources[0],
              'outer_controller':'durable-intent-and-fact-events-only',
              'wall_limit_seconds':None,'fee_ledger':'preserved'}
    manifest['harness_id']='H-'+identity(manifest)
    destination=lab.root/'harnesses'/manifest['harness_id']
    for folder,suffix in [('src','ts'),('dist','js')]:
        for name in modules:
            path=destination/folder/(name+'.'+suffix);path.parent.mkdir(parents=True,exist_ok=True)
            original=source/folder/(name+'.'+suffix)
            if path.exists() and sha(path)!=sha(original):raise ValueError('DESIGN_CONTROLLER_FROZEN_TAMPER')
            if not path.exists():shutil.copyfile(original,path)
    if not (destination/'node_modules').exists():(destination/'node_modules').symlink_to(PI/'node_modules',target_is_directory=True)
    if not (destination/'resources/manifest.json').exists():freeze_resources(destination/'resources',resources)
    sealed(destination/'manifest.json',manifest)
    return destination,manifest


def start(lab,owner,dry_run=False):
    task=lab.task(owner)
    if task['submission'] and not dry_run:return lab.view(owner)
    if owner in lab.controllers and lab.controllers[owner].is_alive():raise ValueError('DESIGN_CONTROLLER_ALREADY_RUNNING')
    with lab.store.connect() as db:
        authority=budget_policy.unbounded_time(db,owner)
        if not authority:raise ValueError('EXPLICIT_CONTINUATION_AUTHORITY_REQUIRED')
        grant=db.execute('SELECT * FROM grants WHERE owner=?',(owner,)).fetchone()
        limits=db.execute('SELECT * FROM model_limits WHERE id=1').fetchone()
        lab.app.provider.recovery.check_window(db,owner,grant,limits)
        if lab.app.provider.recovery.unknown_blockers(db,owner):raise ValueError('PROVIDER_USAGE_UNKNOWN_STOP')
    if not dry_run:
        from .qualification import validation_id
        from .coupled_c import validation_id as native_validation_id
        actual_validation=native_validation_id() if task['environment'].get('mode')=='native-coupled-C' else validation_id()
        if actual_validation!=task['contract']['validation_id']:raise ValueError('EXECUTOR_VALIDATION_CHANGED_RECHECK_REQUIRED')
        path=lab.root/'qualifications'/task['contract']['validation_id']/'qualification.json'
        qualification=json.loads(path.read_text())
        if (qualification['environment_id']!=task['environment']['environment_id'] or not qualification['passed']
            or qualification['validation_id']!=task['contract']['validation_id']):raise ValueError('DESIGN_ENVIRONMENT_NOT_QUALIFIED')
    thread=threading.Thread(target=run,args=(lab,owner,dry_run),daemon=True)
    lab.controllers[owner]=thread;thread.start()
    return {'owner':owner,'controller':'pi-native-loop','dispatch':'STARTING','dry_run':dry_run}


def run(lab,owner,dry_run):
    try:
        _run(lab,owner,dry_run)
    except Exception as exc:
        # Lock acquisition and controller freezing can fail before _run creates
        # its normal attempt. Preserve those environment failures too.
        output=lab.store.root.parent/'sessions'/owner
        attempt=output/'design-attempts'/('startup-failure-'+str(time.time_ns()))
        receipt={'schema_version':'bf-design-session-v1','owner':owner,
                 'task_id':lab.task(owner)['task_id'],'started':time.time(),
                 'status':'FAILED','dry_run':dry_run,'ended':time.time(),
                 'error':type(exc).__name__+': '+str(exc)[:2000],
                 'failure_scope':'controller-startup','fee_ledger_preserved':True}
        sealed(attempt/'receipt.json',receipt)
        launcher.write_session_receipt(output/'receipt.json',receipt)
        lab.app.conversations.state(owner,'FAILED',receipt['error'])
        lab.event(owner,'controller_finished',{'status':'FAILED',
            'receipt_path':str(attempt/'receipt.json'),'receipt_sha256':sha(attempt/'receipt.json'),
            'submitted':False,'failure_scope':'controller-startup'})


def _run(lab,owner,dry_run):
    app=lab.app;home=lab.store.root.parent
    from ..chat import conversation_slot
    with conversation_slot(home,owner):
        task=lab.task(owner);harness,manifest=freeze(lab,native=task['environment'].get('mode')=='native-coupled-C')
        workspace=home/'participants'/owner
        workspace.mkdir(parents=True,exist_ok=True);(workspace/'.tmp').mkdir(exist_ok=True)
        output=home/'sessions'/owner;output.mkdir(parents=True,exist_ok=True)
        attempt=output/'design-attempts'/('attempt-'+str(time.time_ns()));attempt.mkdir(parents=True)
        receipt={'schema_version':'bf-design-session-v1','owner':owner,'task_id':task['task_id'],
                 'harness':manifest,'environment_id':task['environment']['environment_id'],
                 'validation_id':task['contract']['validation_id'],'started':time.time(),
                 'wall_seconds':None,'dry_run':dry_run,'status':'STARTING','fee_ledger_preserved':True}
        try:
            finished=None;watcher=None;process=None
            checks=launcher.preflight(workspace,harness);receipt['sandbox']=checks
            with lab.store.connect() as db:
                db.execute('UPDATE conversations SET harness=? WHERE id=?',(str(harness),owner))
                profile=model_profile(db,owner)
                # A service restart marks SENT messages UNKNOWN. Their original
                # goal remains authoritative context, never an automatic retry
                # of an UNKNOWN provider request (checked by start separately).
                message=db.execute("SELECT * FROM chat_messages WHERE conversation=? AND status IN ('QUEUED','ACCEPTED','SENT','UNKNOWN') ORDER BY created DESC LIMIT 1",(owner,)).fetchone()
                if not message:raise ValueError('DESIGN_REQUIRES_USER_GOAL')
                db.execute("UPDATE chat_messages SET status='SENT' WHERE id=? AND status='QUEUED'",(message['id'],))
            receipt['model_profile']=profile
            token=lab.store.issue(owner)
            configuration={'workspace':str(workspace),'service':f'http://127.0.0.1:{app.conversations.port}',
                           'token':token,'owner':owner,'goal':message['text'],'messageId':message['id'],
                           'harnessIdentity':manifest['harness_id'],'modelProfile':profile,'dryRun':dry_run}
            command=['/usr/bin/sandbox-exec','-p',launcher.seatbelt(workspace,harness,app.conversations.port),
                     str(NODE),str(harness/'dist/design-task.js')]
            app.conversations.state(owner,'STARTING')
            finished=threading.Event()
            def watch():
                while not finished.wait(.15):app.conversations.ingest(owner,execution_state=False)
                app.conversations.ingest(owner,execution_state=False)
            watcher=threading.Thread(target=watch,daemon=True);watcher.start()
            with (output/'trace.jsonl').open('a') as stdout,(attempt/'stderr.log').open('w') as stderr:
                process=subprocess.Popen(command,cwd=workspace,env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin',
                         'TMPDIR':str(workspace/'.tmp'),'LANG':'en_US.UTF-8'},stdin=subprocess.PIPE,
                         stdout=stdout,stderr=stderr,start_new_session=True)
                receipt.update(pid=process.pid,status='RUNNING')
                sealed(attempt/'dispatch.json',receipt)
                app.conversations.processes[owner]=process;app.conversations.starting.add(owner)
                app.conversations.state(owner,'RUNNING')
                process.stdin.write((canonical(configuration)+'\n').encode());process.stdin.flush()
                while process.poll() is None:
                    # Revocation is explicit; process age never renews authority.
                    with lab.store.connect() as db:authority=budget_policy.unbounded_time(db,owner)
                    if not authority:
                        os.killpg(process.pid,signal.SIGTERM);receipt['authority_revoked']=True
                    try:process.wait(timeout=1)
                    except subprocess.TimeoutExpired:pass
                process.stdin.close()
            finished.set();watcher.join(timeout=2)
            receipt.update(exit_code=process.returncode,status='COMPLETED' if process.returncode==0 else 'FAILED',
                           submission=lab.task(owner)['submission'],trace_sha256=sha(output/'trace.jsonl'))
            app.conversations.state(owner,'IDLE' if process.returncode==0 else 'FAILED',
                                    None if process.returncode==0 else (attempt/'stderr.log').read_text()[-2000:])
        except Exception as exc:
            receipt.update(status='FAILED',error=type(exc).__name__+': '+str(exc)[:2000])
            app.conversations.state(owner,'FAILED',receipt['error'])
        finally:
            if finished is not None:finished.set()
            if watcher is not None:watcher.join(timeout=2)
            if process is not None and process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                process.wait(timeout=5)
            trace=output/'trace.jsonl'
            if trace.is_file():
                shutil.copyfile(trace,attempt/'trace-sealed.jsonl')
                receipt['trace_path']=str(attempt/'trace-sealed.jsonl')
                receipt['trace_sha256']=sha(attempt/'trace-sealed.jsonl')
            receipt['ended']=time.time();sealed(attempt/'receipt.json',receipt)
            # This mutable pointer is deliberately distinguished from sealed attempts.
            launcher.write_session_receipt(output/'receipt.json',receipt)
            app.conversations.processes.pop(owner,None);app.conversations.starting.discard(owner)
            lab.event(owner,'controller_finished',{'status':receipt['status'],'receipt_path':str(attempt/'receipt.json'),
                      'receipt_sha256':sha(attempt/'receipt.json'),'submitted':bool(receipt.get('submission'))})

