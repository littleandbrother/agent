"""Trusted fresh-process launcher. Participant code never receives provider keys."""
import hashlib
import fcntl
import json
import os
import secrets
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from .store import Store,canonical,identity
from .experiments import task,BASELINE_DESIGN,BASELINE_POLICY
from .recovery import Recovery, INTERACTIVE_WALL_SECONDS
from .model_profile import for_owner as model_profile
from . import budget_policy
from .skill_resources import source_bundle, freeze_resources, verify as verify_resources

from .runtime_config import PI, HOME_ROOT, NODE as NODE_PATH, readonly_runtime
NODE = str(NODE_PATH)
INTERACTIVE_SHUTDOWN_GRACE_SECONDS=10

def filehash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_session_receipt(path, receipt):
    """Publish the mutable pointer without exposing a half-written receipt."""
    data=canonical(receipt)
    path=Path(path)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                         prefix='.'+path.name+'.',delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)

# Capture the loaded controller revision once. A file edit while a serial batch
# holds this Python module must not relabel that already-loaded implementation.
CONTROLLER_SOURCE_HASH=filehash(__file__)

def world_binding():
    base=Path(__file__).resolve().parent
    paths=[base/name for name in ['programmed.py','experiments.py','store.py','provider.py','model_profile.py','recovery.py','references.py','reference_checks.py','event_design.py','event_measurement.py']]
    paths += [base.parent/'coupled'/name for name in ['engine.py','profiled.py']]
    return {str(p):filehash(p) for p in paths}


def delivery_binding():
    # Product delivery capability is outside the frozen scientific apparatus.
    base=Path(__file__).resolve().parent
    paths=[base/'eda_cli.py',base/'responsibility_review.py',base/'deliverables.py', base/'product_authority.py', base/'runtime_config.py', base/'engineering_projects.py', base/'beam_event.py', base/'design_review.py', base/'assembly.py', base/'tool_responses.py', base/'request_evidence.py', base/'engineering.py', base.parents[5]/'configs/reference_cases/engineering-delivery-v1.json']
    paths += [PI/'packages/bf-agent'/folder/('engineering-wait.'+ext) for folder,ext in [('src','ts'),('dist','js')]]
    paths += [base/name for name in ('firmware_targets.py','nordic_sdk.py','stm32_l432.py','spice_observation.py','assembly_contract.py')]
    paths += [base/name for name in ('skill_resources.py','native_outcome.py','context.py','product_dependencies.py')]
    paths += [PI/'packages/bf-agent'/folder/('skill-resources.'+ext) for folder,ext in [('src','ts'),('dist','js')]]
    paths += [PI/'packages/bf-agent'/folder/('bounded-bash.'+ext) for folder,ext in [('src','ts'),('dist','js')]]
    return {str(p):filehash(p) for p in paths}

def freeze(source=PI/'packages/bf-harness',label='H0',home_root=HOME_ROOT,app_entry='main.js'):
    # Concurrent conversations may freeze the same new revision. Serialize its
    # build/publication so no caller observes a partially written manifest.
    Path(home_root).mkdir(parents=True,exist_ok=True)
    with (Path(home_root)/'harness-freeze.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _freeze_locked(source,label,home_root,app_entry)


def _freeze_locked(source,label,home_root,app_entry):
    if app_entry not in ('main.js','chat.js','chat-v2.js','chat-product.js'):raise ValueError('APP_ENTRY_INVALID')
    if app_entry=='chat-product.js':
        # A source hash beside stale dist output is not an executable revision.
        build=subprocess.run([str(PI/'node_modules/.bin/tsgo'),'-p',str(PI/'packages/bf-agent/tsconfig.json')],capture_output=True,text=True,timeout=30)
        if build.returncode:raise ValueError('PRODUCT_APP_BUILD_FAILED: '+build.stdout[-1000:]+build.stderr[-1000:])
    files={str(p.relative_to(source)):p.read_text() for p in sorted((source/'src').glob('*.ts'))}
    if app_entry=='chat-product.js' and 'src/product.ts' not in files:
        files['src/product.ts']=(PI/'packages/bf-harness/src/product.ts').read_text()
    digest=identity(files)
    bindings={'source':digest,'app':filehash(PI/'packages/bf-agent/dist'/app_entry),'lock':filehash(PI/'package-lock.json'),'world':world_binding()}
    if app_entry=='chat-product.js':
        bindings['delivery']=delivery_binding()
        resources=source_bundle()
        bindings['resources']=resources[0]['sha256']
        bindings['research_method']={kind:filehash(PI/('packages/bf-agent/'+folder+'/research-method.'+suffix)) for kind,folder,suffix in [('source_sha256','src','ts'),('build_sha256','dist','js')]}
        # Freeze pinned metadata; only an actual qualified caller requires the
        # full content audit before using it. Unrelated owners receive no grant.
        bindings['readonly_runtime']=readonly_runtime(verify_contents=False)
    binding=identity(bindings)
    dest=Path(home_root)/'harnesses'/(label+'-'+binding[:12])
    if (dest/'manifest.json').exists():
        manifest=json.loads((dest/'manifest.json').read_text())
        for name,value in manifest['source_files'].items():
            if filehash(dest/name)!=value:raise ValueError('FROZEN_SOURCE_TAMPER')
        for name,value in manifest['loaded_modules'].items():
            if filehash(dest/'dist'/(name+'.js'))!=value:raise ValueError('FROZEN_BUILD_TAMPER')
        for name,value in manifest.get('loaded_files',{}).items():
            if filehash(dest/'dist'/name)!=value:raise ValueError('FROZEN_BUILD_TAMPER')
        if manifest.get('resource_manifest'):
            verify_resources(dest/'resources',manifest['resource_manifest']['sha256'])
        return dest
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'src').mkdir(exist_ok=True)
    for name,value in files.items():(dest/name).write_text(value)
    for name in ['package.json','tsconfig.json']:shutil.copyfile(PI/'packages/bf-harness'/name,dest/name)
    if not (dest/'node_modules').exists():(dest/'node_modules').symlink_to(PI/'node_modules',target_is_directory=True)
    build=subprocess.run([str(PI/'node_modules/.bin/tsgo'),'-p',str(dest/'tsconfig.json')],capture_output=True,text=True,timeout=30)
    (dest/'build.log').write_text(build.stdout+build.stderr)
    if build.returncode:raise ValueError('CANDIDATE_BUILD_FAILED: '+build.stdout[-1000:]+build.stderr[-1000:])
    manifest={'schema_version':'bf-agent-harness-v1','label':label,'source_hash':digest,
      'source_files':{name:filehash(dest/name) for name in files},
      'loaded_modules':{name:filehash(dest/'dist'/(name+'.js')) for name in (['solver','improver','product'] if 'src/product.ts' in files else ['solver','improver'])},
      'loaded_files':{p.name:filehash(p) for p in sorted((dest/'dist').glob('*.js'))},
      'pi_git_revision':'7140838fdd5ee1ff21dbe50955a8801617b065ef',
      'pi_lock_hash':filehash(PI/'package-lock.json'),'app_build_hash':filehash(PI/'packages/bf-agent/dist'/app_entry),
      'app_entry':app_entry,'app_source_hash':filehash(PI/'packages/bf-agent/src'/app_entry.replace('.js','.ts')),'world_binding':world_binding(),
       'thinking':'owner-bound' if app_entry=='chat-product.js' else 'off','session_caps':{'experiments':6,'model_requests':128 if app_entry=='chat-product.js' else 24,'wall_seconds':INTERACTIVE_WALL_SECONDS if app_entry in ('chat.js','chat-v2.js','chat-product.js') else 600},
      'resource_hashes':{str(p.relative_to(PI)):filehash(p) for p in sorted((PI/'packages/ai/src/providers/data').rglob('*.json'))},
      'tools':['read','edit','write','bash','bf_experiment','bf_job','bf_inspect_run','bf_submit']+(['bf_product','bf_eda'] if app_entry=='chat-product.js' else [])+(['bf_engineering','bf_reference'] if app_entry in ('chat-product.js','chat-v2.js') else []),
      'model':'deepseek-flash','resources':'explicit-empty-no-ancestry','world':'coupled-programmed-reference-v3'}
    if app_entry=='chat-product.js':
        freeze_resources(dest/'resources',resources)
        manifest['resource_manifest']=resources[0]
        manifest['resources']='frozen-project-catalog-v1'
        manifest['tools'].append('bf_skill')
        manifest['delivery_binding']=delivery_binding()
        manifest['research_method']=bindings['research_method']
        manifest['readonly_runtime']=bindings['readonly_runtime']
    manifest['identity']=identity(manifest)
    (dest/'manifest.json').write_text(canonical(manifest))
    return dest


def seatbelt(workspace,harness,port=8768,mutable=None):
    def q(p):return str(Path(p).resolve()).replace('\\','\\\\').replace('"','\\"')
    # An installed Pi checkout may share node_modules with the deployment
    # checkout. macOS authorizes resolved paths, so allowing only PI makes ESM
    # package manifests unreadable and produces a misleading missing index.js.
    # Allow the actual vendor dependency root and installed Pi workspace
    # packages, never the deployment home, provider credentials or evaluator.
    dependencies=[PI/'node_modules']
    scope=PI/'node_modules/@earendil-works'
    if scope.is_dir():
        for path in sorted(scope.iterdir()):
            target=path.resolve()
            if target.is_dir() and target.parent.name=='packages':
                manifest=target/'package.json'
                if manifest.is_file() and json.loads(manifest.read_text()).get('name')=='@earendil-works/'+path.name:
                    dependencies.append(target)
    runtime=readonly_runtime(workspace)
    public_runtime=[Path(p['path']) for p in runtime['roots']] if runtime else []
    reads=' '.join(f'(subpath "{p}")' for p in sorted({q(p) for p in [workspace,harness,PI,*dependencies,*public_runtime]}))
    source_guards=''
    if mutable is not None:
        source_guards=' '.join(f'(deny file-write* (literal "{q(workspace / "harness" / name)}"))'
                              for name in ['solver.ts','improver.ts'] if name not in mutable)
    return f'''(version 1)(allow default)
      (deny network*) (allow network-outbound (remote ip "localhost:{port}"))
      (deny file-read* (require-all
        (require-any (subpath "/Users") (subpath "/private") (subpath "/Volumes") (subpath "/Applications") (subpath "/Library/Keychains"))
        (require-not (require-any {reads}))))
      (allow file-read-metadata)
      (deny file-write* (require-not (require-any (subpath "{q(workspace)}") (subpath "/dev"))))
      {source_guards}
    '''


def preflight(workspace,harness):
    source="""const fs=require('fs'),net=require('net'),cp=require('child_process');
const checks={};
try{fs.readFileSync(SECRET_PATH);checks.secret=false}catch(e){checks.secret=e.code==='EPERM'||e.code==='EACCES'}
try{fs.writeFileSync(WRITE_PATH,'x');checks.write=false}catch(e){checks.write=e.code==='EPERM'||e.code==='EACCES'}
try{fs.readFileSync(EVALUATOR_PATH);checks.evaluator=false}catch(e){checks.evaluator=e.code==='EPERM'||e.code==='EACCES'}
checks.shell=cp.spawnSync('/bin/sh',['-c','echo safe']).stdout.toString().trim()==='safe';
const socket=net.connect({host:'1.1.1.1',port:443});socket.on('error',e=>{checks.network=e.code==='EPERM'||e.code==='EACCES';console.log(JSON.stringify(checks));});
setTimeout(()=>{socket.destroy();if(checks.network===undefined){checks.network=false;console.log(JSON.stringify(checks))}},500);
"""
    from .runtime_config import KEY_PATH
    source=source.replace("SECRET_PATH", json.dumps(str(KEY_PATH))).replace("WRITE_PATH", json.dumps(str(HOME_ROOT/"forbidden"))).replace("EVALUATOR_PATH", json.dumps(str(Path(__file__).with_name("experiments.py"))))
    proc=subprocess.run(['/usr/bin/sandbox-exec','-p',seatbelt(workspace,harness),NODE,'-e',source],cwd=workspace,
        env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','TMPDIR':str(workspace)},capture_output=True,text=True,timeout=5)
    if proc.returncode:raise ValueError('PI_SANDBOX_FAILED: '+proc.stderr[-1200:])
    checks=json.loads(proc.stdout)
    if not all(checks.values()):raise ValueError('PI_SANDBOX_PREFLIGHT_FAILED: '+canonical(checks))
    runtime=readonly_runtime(workspace)
    if runtime:
        # Run the dependency test through the identical caller profile. A host
        # import cannot prove that the original Pi can execute this runtime.
        source="import json,tkinter; from bleak import BleakClient; import inspect; print(json.dumps({'tk':bool(tkinter.Tcl().eval('info patchlevel')),'bleak':'disconnected_callback' in inspect.signature(BleakClient).parameters}))"
        probe=subprocess.run(['/usr/bin/sandbox-exec','-p',seatbelt(workspace,harness),
            runtime['interpreter'],'-B','-c',source],cwd=workspace,
            env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','TMPDIR':str(Path(workspace)/'.tmp'),'LANG':'en_US.UTF-8'},
            capture_output=True,text=True,timeout=10)
        try:usable=probe.returncode==0 and all(json.loads(probe.stdout).values())
        except (ValueError,TypeError):usable=False
        if not usable:raise ValueError('PI_RECEIVER_RUNTIME_PREFLIGHT_FAILED: '+probe.stderr[-1000:])
        checks['receiver_runtime']=True
    return checks


def wait_interactive(proc,store,owner,on_expire=None):
    """Follow the current user lease; process age and tool polling never renew it."""
    recovery=Recovery(store)
    while proc.poll() is None:
        with store.connect() as db:lease=recovery.lease(db,owner)
        remaining=lease['expires']-time.time() if lease and lease['expires'] is not None else float('inf') if lease else 0
        if remaining>0:
            try:proc.wait(timeout=min(1,remaining))
            except subprocess.TimeoutExpired:pass
            continue
        # Conversations serializes this decision with send()/recall(). A new
        # user message racing this check keeps its lease, not the old deadline.
        if on_expire and not on_expire(proc):continue
        observation={'error':'CHAT_TURN_WALL_BUDGET' if lease else 'CHAT_TURN_AUTH_REQUIRED',
                     'message_id':lease['message_id'] if lease else None,
                     'expires':lease['expires'] if lease else None,
                     'observed_at':time.time(),'grace_seconds':INTERACTIVE_SHUTDOWN_GRACE_SECONDS,
                     'forced_kill':False}
        store.event(owner,owner,'interactive_deadline_reached',observation)
        try:
            proc.stdin.write(b'{"type":"close"}\n');proc.stdin.flush()
        except (BrokenPipeError,ValueError,OSError):pass
        try:proc.wait(timeout=INTERACTIVE_SHUTDOWN_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait();observation['forced_kill']=True
        return observation
    return None


def prepare_workspace(workspace, resume=False, staged=False):
    """An operator-staged first launch may already have immutable task inputs."""
    if workspace.is_symlink():raise ValueError('WORKSPACE_SYMLINK_DENIED')
    if workspace.exists() and not resume:
        if not staged or any((workspace/p).exists() for p in ('.pi','.tmp','task.json','design.json','policy.py')):
            raise ValueError('WORKSPACE_ALREADY_INITIALIZED')
    workspace.mkdir(parents=True,exist_ok=resume or staged)
    (workspace/'.pi').mkdir(exist_ok=resume);(workspace/'.tmp').mkdir(exist_ok=resume)


def previous_attempt_summary(previous):
    """Keep missing terminal evidence explicit after an unclean process exit.

    The session lock is acquired before resume; a leftover RUNNING receipt is
    evidence of interrupted bookkeeping, not a still-live execution or success.
    The complete original receipt is archived separately for chat upgrades.
    """
    summary = {k: previous.get(k) for k in ('started', 'ended', 'status', 'trace_hash')}
    if previous.get('status') == 'RUNNING' or previous.get('ended') is None:
        summary.update(status='INTERRUPTED', recorded_status=previous.get('status'),
                       terminal_receipt_missing=True)
    return summary


def launch(harness,task_id='dev-01',mode='solve',experience=None,label=None,store_root=None,dry_run=False,resume=False,interrupt_after_job=False,mutable=('solver.ts','improver.ts'),feedback=None,public_history=None,memory_in_prompt=False,process_lock=None,service_port=8768,on_process=None,home_root=None,shared_context=None,chat_upgrade=False,product=False,on_expire=None):
    home_root=Path(home_root or HOME_ROOT)
    session_lock=process_lock or (home_root/'pi-session.lock').open('a')
    try:
        fcntl.flock(session_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        store=Store(store_root or home_root/'state')
        with store.connect() as db:time_authority=budget_policy.unbounded_time(db,label)
        if not dry_run and (home_root/'paid-window-closed.json').exists() and not time_authority:raise ValueError('PAID_WINDOW_CLOSED')
        manifest=json.loads((Path(harness)/'manifest.json').read_text())
        app_entry=manifest.get('app_entry','main.js')
        if identity({k:v for k,v in manifest.items() if k!='identity'})!=manifest['identity']:raise ValueError('HARNESS_MANIFEST_TAMPER')
        for name,digest in manifest['source_files'].items():
            if filehash(Path(harness)/name)!=digest:raise ValueError('HARNESS_SOURCE_TAMPER')
        for name,digest in manifest['loaded_modules'].items():
            if filehash(Path(harness)/'dist'/(name+'.js'))!=digest:raise ValueError('HARNESS_ACTIVATION_HASH_MISMATCH')
        for name,digest in manifest.get('loaded_files',{}).items():
            if filehash(Path(harness)/'dist'/name)!=digest:raise ValueError('HARNESS_ACTIVATION_HASH_MISMATCH')
        if filehash(PI/'packages/bf-agent/dist'/app_entry)!=manifest['app_build_hash']:raise ValueError('APP_BUILD_CHANGED_SINCE_FREEZE')
        if filehash(PI/'package-lock.json')!=manifest['pi_lock_hash']:raise ValueError('LOCK_CHANGED_SINCE_FREEZE')
        if manifest.get('world_binding',world_binding())!=world_binding():raise ValueError('WORLD_CHANGED_SINCE_FREEZE')
        if 'delivery_binding' in manifest and manifest['delivery_binding']!=delivery_binding():raise ValueError('DELIVERY_CHANGED_SINCE_FREEZE')
        if product and manifest.get('readonly_runtime')!=readonly_runtime(verify_contents=False):raise ValueError('READONLY_RUNTIME_CHANGED_SINCE_FREEZE')
        if manifest.get('resource_manifest'):
            verify_resources(Path(harness)/'resources',manifest['resource_manifest']['sha256'])
        owner=label or ('pi-'+mode+'-'+secrets.token_hex(5))
        staged=False
        if product and on_process and not resume:
            with store.connect() as db:
                staged=bool(db.execute("SELECT 1 FROM chat_events WHERE conversation=? AND json_extract(data,'$.type')='conversation_staged'",(owner,)).fetchone())
        workspace=home_root/'participants'/owner
        prepare_workspace(workspace,resume=resume,staged=staged)
        store.grant(owner,[] if product else [task_id],6,time.time()+620)
        if on_process:Recovery(store).refresh_grant(owner)
        token=store.issue(owner)
        if mode=='solve' and not resume:
            task_input={'mode':'product-discovery','task_id':None,'assumptions':'explicit-revisable','capability':'unbound'} if product else task(task_id)
            if public_history is not None:
                (workspace/'public-history.json').write_text(canonical(public_history))
                if memory_in_prompt:
                    task_input={**task_input,'public_development_memory':public_history}
            (workspace/'task.json').write_text(canonical(task_input))
            (workspace/'design.json').write_text(canonical({} if product else task(task_id)['baseline_design']))
            (workspace/'policy.py').write_text(BASELINE_POLICY)
        elif mode!='solve' and not resume:
            (workspace/'harness').mkdir()
            for name in ['solver.ts','improver.ts']:shutil.copyfile(Path(harness)/'src'/name,workspace/'harness'/name)
            (workspace/'experience').mkdir()
            index=[]
            for i,item in enumerate(experience or []):
                entry={k:v for k,v in item.items() if k!='public_trace'}
                trace_name=f'experience/trial-{i:02}.json'
                (workspace/trace_name).write_text(json.dumps(item.get('public_trace',[]),ensure_ascii=False,indent=2))
                entry['public_trace_file']=trace_name;index.append(entry)
            (workspace/'experience.json').write_text(json.dumps(index,ensure_ascii=False,indent=2))
            (workspace/'node_modules').symlink_to(PI/'node_modules',target_is_directory=True)
            config={'compilerOptions':{'target':'ES2022','module':'NodeNext','moduleResolution':'NodeNext','strict':True,'skipLibCheck':True,'outDir':'build'},'include':['harness/*.ts']}
            (workspace/'tsconfig.json').write_text(canonical(config))
            (workspace/'package.json').write_text(canonical({'type':'module','scripts':{'build':str(PI/'node_modules/.bin/tsgo')+' -p tsconfig.json'}}))
        checks=preflight(workspace,harness)
        if mode=='solve' and resume:
            if (workspace/'public-history.json').exists():public_history=json.loads((workspace/'public-history.json').read_text())
            memory_in_prompt='public_development_memory' in json.loads((workspace/'task.json').read_text())
        with store.connect() as db:profile=model_profile(db,owner)
        cfg={'workspace':str(workspace),'service':f'http://127.0.0.1:{service_port}','token':token,'taskId':task_id,'mode':mode,'dryRun':dry_run,'modelProfile':profile,
          'resourceRoot':str(Path(harness)/'resources') if manifest.get('resource_manifest') else None,
          'productModule':str(Path(harness)/'dist/product.js'),'product':product,'sharedContext':shared_context,'solverModule':str(Path(harness)/'dist/solver.js'),'improverModule':str(Path(harness)/'dist/improver.js'),
          'sourceManifest':manifest,'improvementContext':{'parent':manifest,'allowed_paths':['harness/'+p for p in mutable],'experience_file':'experience.json','trace_files':'experience/*.json','reading':'The index and complete public traces are local files. Page or summarize large files instead of dumping all traces into context.','continuation_feedback':feedback}}
        command=['/usr/bin/sandbox-exec','-p',seatbelt(workspace,harness,port=service_port,mutable=mutable if mode=='improve' else None),NODE,str(PI/'packages/bf-agent/dist'/app_entry),'-']
        receipt={'owner':owner,'mode':mode,'dry_run':dry_run,'task_id':task_id,'harness_path':str(harness),'harness':manifest,'sandbox':checks,'started':time.time(),'status':'RUNNING','workspace':str(workspace),
          'controller_hash':CONTROLLER_SOURCE_HASH,'model_profile':profile,'public_history_hash':identity(public_history) if public_history is not None else None,'memory_in_prompt':memory_in_prompt,
          'task_input_hash':filehash(workspace/'task.json') if mode=='solve' else None}
        if on_process:receipt['wall_policy']={'scope':'latest-valid-user-message','seconds':INTERACTIVE_WALL_SECONDS,'grace_seconds':INTERACTIVE_SHUTDOWN_GRACE_SECONDS}
        output=home_root/'sessions'/owner;output.mkdir(parents=True,exist_ok=resume)
        if resume:
            previous=json.loads((output/'receipt.json').read_text())
            if previous['harness']['identity']!=manifest['identity'] and not (chat_upgrade and ((app_entry=='chat-v2.js' and previous['harness'].get('app_entry') in ('chat.js','chat-v2.js')) or (app_entry=='chat-product.js' and previous['harness'].get('app_entry')=='chat-product.js'))):raise ValueError('RESUME_REQUIRES_SAME_FROZEN_HARNESS')
            if chat_upgrade:
                from .developer import write_once
                archive=output/'attempts'/(identity(previous)+'.json')
                if not archive.exists():write_once(archive,previous)
                receipt['previous_harness_identity']=previous['harness']['identity']
                receipt['shared_context']=shared_context
            receipt['previous_attempts']=previous.get('previous_attempts',[])+[previous_attempt_summary(previous)]
        write_session_receipt(output/'receipt.json',receipt)
        store.event(owner,owner,'session_started',{'mode':mode,'harness_id':manifest['identity'],'task_id':task_id})
        with (output/'trace.jsonl').open('a' if resume else 'w') as stdout,(output/'stderr.log').open('a' if resume else 'w') as stderr:
            proc=subprocess.Popen(command,cwd=workspace,env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','TMPDIR':str(workspace/'.tmp'),'LANG':'en_US.UTF-8'},stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,start_new_session=True)
            receipt['pid']=proc.pid;write_session_receipt(output/'receipt.json',receipt)
            proc.stdin.write((canonical(cfg)+'\n').encode());proc.stdin.flush()
            if on_process:on_process(proc)
            else:proc.stdin.close()
            try:
                if interrupt_after_job:
                    end=time.monotonic()+600
                    while proc.poll() is None and time.monotonic()<end:
                        if store.jobs(owner):
                            os.killpg(proc.pid,signal.SIGKILL);proc.wait();receipt['injected_interruption']=True;break
                        time.sleep(.005)
                    if proc.poll() is None:raise subprocess.TimeoutExpired(command,600)
                elif on_process:
                    deadline=wait_interactive(proc,store,owner,on_expire)
                    if deadline:receipt.update(error=deadline['error'],deadline_shutdown=deadline)
                else:proc.wait(timeout=600)
                if on_process:proc.stdin.close()
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait();receipt['error']='SESSION_WALL_LIMIT'
        receipt.update({'ended':time.time(),'exit_code':proc.returncode,'status':'COMPLETED' if proc.returncode==0 else 'FAILED',
                        'trace_hash':filehash(output/'trace.jsonl')})
        with store.connect() as db:
            submission=db.execute('SELECT * FROM submissions WHERE owner=?',(owner,)).fetchone()
        receipt['submission']=dict(submission) if submission else None
        if receipt.get('injected_interruption'):receipt['status']='INTERRUPTED'
        if receipt.get('deadline_shutdown'):receipt['status']='PAUSED'
        write_session_receipt(output/'receipt.json',receipt)
        store.event(owner,owner,'session_finished',{'status':receipt['status'],'submitted':bool(submission)})
        return receipt
    finally:
        if process_lock is None:session_lock.close()


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--harness',type=Path);parser.add_argument('--task',default='dev-01');parser.add_argument('--label');parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args();harness=args.harness or freeze()
    if args.freeze_only:print(harness);return
    print(canonical(launch(harness,args.task,label=args.label)))

if __name__=='__main__':main()
