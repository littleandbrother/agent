"""Operator proof for separate paper EDA projects; no participant self-binding."""
import json
import re
import subprocess
import time
from pathlib import Path


def local_destination(record, creation):
    """An operator-selected persistent native file, never a participant path."""
    from .runtime_config import configured
    value=record.get('local_project')
    if not isinstance(value,str) or not value:raise ValueError('PAPER_EDA_LOCAL_PROJECT_REQUIRED')
    path=Path(value)
    allowed=configured('EDA_LOCAL_PROJECT_ROOT',Path.home()/'Documents/LCEDA-Pro/projects')
    if (not path.is_absolute() or path.suffix not in {'.eprj2','.eprj3'} or
        not path.resolve().is_relative_to(allowed.resolve()) or
        any(p.is_symlink() for p in [path,*path.parents]) or not path.is_file()):
        raise ValueError('PAPER_EDA_LOCAL_PROJECT_SCOPE')
    if path.suffix=='.eprj3' and json.loads(path.read_text()).get('name')!=creation['name']:
        raise ValueError('PAPER_EDA_LOCAL_PROJECT_NAME')
    return path


def open_local_destination(record, creation, project, policy, allow_open_missing=True):
    """Open an exact persisted destination only when it is not already open."""
    from .runtime_config import configured
    from .eda_cli import ready_window, read_health
    if policy.get('host')!='desktop' or policy.get('transport') not in {'native-cli-v1','easyeda-typed-v1'}:
        raise ValueError('PAPER_EDA_LOCAL_HOST_POLICY_REQUIRED')
    path=local_destination(record,creation)
    try:return ready_window(project,policy,0),None
    except ValueError as exc:
        if str(exc) not in {'EDA_NO_CONNECTED_WINDOW','EDA_BOUND_PROJECT_NOT_OPEN'}:raise
    # A live local desktop Connect needs no CLI headless session. It still
    # undergoes the same fresh project/native-document checks in configure_eda.
    # Never silently open a second backend or a Web destination for this policy.
    if policy.get('transport')=='easyeda-typed-v1':
        raise ValueError('PAPER_EDA_DESKTOP_CONNECT_PROJECT_NOT_OPEN')
    if not allow_open_missing:raise ValueError('PAPER_EDA_LOCAL_PROJECT_NOT_OPEN')
    cli=configured('EDA_NATIVE_CLI','/Applications/嘉立创EDA(专业版).app/Contents/MacOS/LCEDA-Pro')
    if not cli.is_file():raise ValueError('PAPER_EDA_NATIVE_CLI_UNAVAILABLE')
    listed=subprocess.run([str(cli),'session','list'],capture_output=True,text=True,timeout=10)
    sessions=json.loads(listed.stdout)
    if listed.returncode or sessions.get('ok') is not True:raise ValueError('PAPER_EDA_NATIVE_SESSION_LIST_FAILED')
    deadline=time.monotonic()+policy['wait_s']
    while True:
        try:return persisted_window(record,creation,policy,sessions,read_health()),None
        except ValueError as exc:
            if str(exc)=='PAPER_EDA_FILE_NOT_OPEN':break
            if str(exc) not in {'PAPER_EDA_FILE_WINDOW_NOT_READY','EDA_NO_CONNECTED_WINDOW','EDA_BOUND_PROJECT_NOT_OPEN'} or time.monotonic()>=deadline:raise
        time.sleep(.25)
    proc=subprocess.run([str(cli),'open','--path',str(path),'--headless'],capture_output=True,text=True,timeout=30)
    result=json.loads(proc.stdout)
    if proc.returncode or result.get('ok') is not True or not result.get('value',{}).get('sessionId'):
        raise ValueError('PAPER_EDA_LOCAL_OPEN_FAILED')
    deadline=time.monotonic()+policy['wait_s']
    opened_session={'ok':True,'value':[{'sessionId':result['value']['sessionId'],'status':'alive','origin':'cli','path':str(path)}]}
    while True:
        try:return persisted_window(record,creation,policy,opened_session,read_health()),result
        except ValueError as exc:
            if str(exc) not in {'EDA_NO_CONNECTED_WINDOW','EDA_BOUND_PROJECT_NOT_OPEN','PAPER_EDA_FILE_WINDOW_NOT_READY'} or time.monotonic()>=deadline:raise
        time.sleep(.25)


def persisted_window(record,creation,policy,sessions,health):
    """Runtime UUIDs may change; an exact official session/file is required."""
    from .eda_cli import select_window
    expected=Path(record['local_project']).resolve()
    candidates=[s for s in sessions.get('value',[]) if s.get('status')=='alive' and s.get('origin')=='cli' and
                isinstance(s.get('path'),str) and Path(s['path']).resolve()==expected]
    if not candidates:raise ValueError('PAPER_EDA_FILE_NOT_OPEN')
    if len(candidates)!=1:raise ValueError('PAPER_EDA_FILE_WINDOW_AMBIGUOUS')
    wanted='native-cli-'+candidates[0]['sessionId']
    windows=health.get('found',{}).get('raw',{}).get('windows',[])
    same=[w for w in windows if w.get('windowId')==wanted]
    if not same:raise ValueError('EDA_BOUND_PROJECT_NOT_OPEN')
    context=same[0].get('context',{});project=context.get('projectUuid')
    # A just-opened official file session can be alive before its project
    # context arrives. Missing identity is readiness, never permission to use
    # another window. A non-empty wrong identity remains a hard rejection.
    if not project or not context.get('projectName'):raise ValueError('PAPER_EDA_FILE_WINDOW_NOT_READY')
    if context.get('projectName')!=creation['name']:raise ValueError('PAPER_EDA_FILE_WINDOW_IDENTITY')
    window=select_window(health,project,policy)
    if window['windowId']!=wanted:raise ValueError('PAPER_EDA_FILE_WINDOW_IDENTITY')
    return window


def verify_native_documents(path,boards):
    """The opened session must expose the exact persisted native document IDs."""
    if path.suffix!='.eprj3':return
    profile=json.loads(path.read_text()).get('profile',{})
    rows=boards.get('result',{}).get('boards')
    if boards.get('ok') is not True or not isinstance(rows,list):raise ValueError('PAPER_EDA_FILE_DOCUMENT_READBACK')
    sch={r['schematicUuid'] for r in rows if r.get('schematicUuid')}
    pcb={r['pcbUuid'] for r in rows if r.get('pcbUuid')}
    if sch!=set(profile.get('schematics',{})) or pcb!=set(profile.get('pcbs',{})):
        raise ValueError('PAPER_EDA_FILE_DOCUMENT_MISMATCH')


def validate_binding(record, creation, opened, paper, owner, other_bindings=()):
    if (record.get('schema_version') != 'bf-paper-eda-binding-v1' or
        record.get('paper_id') != paper or record.get('owner') != owner or
        record.get('actor') != 'Codex environment preparation' or
        record.get('writable') is not True):
        raise ValueError('PAPER_EDA_OPERATOR_BINDING_REQUIRED')
    project = record.get('project_uuid')
    if not isinstance(project, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{10,80}', project):
        raise ValueError('PAPER_EDA_PROJECT_IDENTITY')
    if (creation.get('actor') != 'Codex environment preparation' or
        creation.get('created') is not True or creation.get('uuid') != project or
        not str(creation.get('name', '')).startswith('BF-Literature-'+paper+'-Native-') or
        creation.get('previous_current_project') == project):
        raise ValueError('PAPER_EDA_INDEPENDENT_CREATION_REQUIRED')
    response = opened.get('response', {})
    info = response.get('result', {})
    if (opened.get('actor') != 'Codex environment preparation' or
        response.get('ok') is not True or info.get('uuid') != project or
        info.get('friendlyName') != creation['name']):
        raise ValueError('PAPER_EDA_OPEN_READBACK_REQUIRED')
    if any(b.get('project') == project and b.get('owner') != owner for b in other_bindings):
        raise ValueError('PAPER_EDA_SHARED_PROJECT_DENIED')
    return project


def runtime_alias_project(root, paper, record, creation, prior):
    """Use an already-proved runtime UUID without opening the same file again.

    A native UUID is accepted only through the exact operator-file alias and
    binding revision hash. A matching name or an arbitrary connected window is
    insufficient. Fresh project and document readback still follows this step.
    """
    from .literature_campaign import read, digest
    project = record['project_uuid']
    if not record.get('local_project') or not prior or prior['project'] == project:
        return project
    record_path = root/'campaign/eda'/paper/'binding.json'
    alias_path = root/'campaign/eda'/paper/('runtime-file-binding-'+digest(record_path)[:20]+'-'+prior['project']+'.json')
    if not alias_path.exists():
        return project
    expected = {'schema_version': 'bf-paper-eda-file-alias-v1',
                'actor': 'Codex environment preparation', 'owner': record['owner'],
                'paper_id': paper, 'binding_record_sha256': digest(record_path),
                'created_project_uuid': project, 'runtime_project_uuid': prior['project'],
                'local_project': str(local_destination(record, creation)),
                'design_restore_claimed': False}
    if (alias_path.is_symlink() or read(alias_path) != expected or
            not prior.get('writable') or prior.get('owner') != record['owner'] or
            prior.get('proof') != digest(alias_path)):
        raise ValueError('PAPER_EDA_RUNTIME_ALIAS_INVALID')
    return prior['project']


def live_project_probe(cli, window, project, name):
    """Fresh bounded identity fact; failed transport is not a foreign design."""
    try:
        proc = subprocess.run([cli, 'project', 'info', '--window', window],
                              capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('PAPER_EDA_LIVE_PROJECT_PROBE_TIMEOUT_ACTION_NOT_SENT: readonly identity probe exceeded 20s; no design write dispatched') from exc
    try:
        live = json.loads(proc.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError('PAPER_EDA_LIVE_PROJECT_RESPONSE_INVALID_ACTION_NOT_SENT') from exc
    if proc.returncode != 0 or not isinstance(live, dict) or live.get('ok') is not True:
        public_error = live.get('error') if isinstance(live, dict) else None
        reason = json.dumps(public_error, ensure_ascii=False) if public_error else proc.stderr[:500]
        raise ValueError('PAPER_EDA_LIVE_PROJECT_UNAVAILABLE_ACTION_NOT_SENT: '+reason[:500])
    if (not isinstance(live.get('result'), dict) or live['result'].get('uuid') != project or
            live['result'].get('friendlyName') != name):
        raise ValueError('PAPER_EDA_LIVE_PROJECT_MISMATCH')
    return live


def configure_eda(app, root, paper, owner, target):
    """Read operator-only receipts, verify live identity, then bind original owner."""
    from .literature_campaign import read, digest, bound_file, put_once
    from .eda_cli import CLI, ready_window
    record_path = root/'campaign/eda'/paper/'binding.json'
    if record_path.is_symlink():
        raise ValueError('PAPER_EDA_BINDING_SYMLINK')
    record = read(record_path)
    proofs = []
    for key in ('creation', 'opened'):
        artifact = record.get(key, {})
        path = bound_file(root, artifact.get('path', ''), artifact.get('sha256'))
        if not path.resolve().is_relative_to((root/'campaign/eda'/paper).resolve()):
            raise ValueError('PAPER_EDA_FOREIGN_PROOF_DENIED')
        proofs.append(read(path))
    with app.store.connect() as db:
        bindings = [dict(row) for row in db.execute('SELECT owner,project FROM eda_cli_bindings UNION SELECT owner,project FROM eda_cli_binding_revisions')]
    created_project = validate_binding(record, *proofs, paper, owner, bindings)
    prior = app.eda_cli.binding(owner)
    project=runtime_alias_project(root,paper,record,proofs[0],prior)
    if record.get('local_project'):
        window,local_open=open_local_destination(record,proofs[0],project,app.eda_cli.policy)
        project=window['context']['projectUuid']
        if not isinstance(project,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{10,80}',project):raise ValueError('PAPER_EDA_PROJECT_IDENTITY')
    else:
        window=ready_window(project,app.eda_cli.policy,app.eda_cli.policy['wait_s']);local_open=None
    live = live_project_probe(CLI, window['windowId'], project, proofs[0]['name'])
    if any(b.get('project')==project and b.get('owner')!=owner for b in bindings):raise ValueError('PAPER_EDA_SHARED_PROJECT_DENIED')
    alias_path=None;boards=None
    if record.get('local_project'):
        proc=subprocess.run([CLI,'board','list','--window',window['windowId']],capture_output=True,text=True,timeout=20)
        if proc.returncode:raise ValueError('PAPER_EDA_FILE_DOCUMENT_READBACK')
        boards=json.loads(proc.stdout);verify_native_documents(local_destination(record,proofs[0]),boards)
        alias_path=root/'campaign/eda'/paper/('runtime-file-binding-'+digest(record_path)[:20]+'-'+project+'.json')
        alias={'schema_version':'bf-paper-eda-file-alias-v1','actor':'Codex environment preparation',
               'owner':owner,'paper_id':paper,'binding_record_sha256':digest(record_path),
               'created_project_uuid':created_project,'runtime_project_uuid':project,
               'local_project':record['local_project'],'design_restore_claimed':False}
        if alias_path.exists():
            if read(alias_path)!=alias:raise ValueError('PAPER_EDA_FILE_ALIAS_CHANGED')
        else:put_once(alias_path,alias)
    if prior and (prior['project'] != project or not prior['writable']):
        migration=record.get('migration') or {}
        previous=migration.get('previous_binding') or {}
        old_alias=root/'campaign/eda'/paper/('runtime-file-binding-'+digest(record_path)[:20]+'-'+prior['project']+'.json')
        native_prior=alias_path and (prior['project']==created_project or (old_alias.exists() and
                     read(old_alias)=={**alias,'runtime_project_uuid':prior['project']}))
        if not native_prior:
            old_path=bound_file(root,previous.get('path',''),previous.get('sha256'));old=read(old_path)
            if (migration.get('schema_version')!='bf-paper-eda-local-migration-v1' or
            migration.get('actor')!='Codex environment preparation' or
            migration.get('design_restore_claimed') is not False or
            not old_path.resolve().is_relative_to((root/'campaign/eda'/paper).resolve()) or
            old.get('owner')!=owner or old.get('paper_id')!=paper or
            old.get('project_uuid')!=prior['project'] or not prior['writable']):
                raise ValueError('PAPER_EDA_EXISTING_BINDING_CONFLICT')
        app.eda_cli.migrate_binding(owner,prior['project'],project,digest(alias_path or record_path),
                                   'Direct user same persisted local file; original cloud/runtime bindings retained as history',operator=True)
    if not prior:
        app.eda_cli.action(owner, {'action': 'bind', 'project_uuid': project,
                                 'authorization': 'Direct user per-paper engineering; independent project only',
                                 'writable': True}, operator=True)
    receipt = {'schema_version': 'bf-paper-eda-live-binding-v1', 'paper_id': paper,
               'owner': owner, 'project_uuid': project, 'actor': 'Codex environment preparation',
               'created_project_uuid':created_project,'native_file_documents':boards,
               'runtime_alias_proof':str(alias_path.relative_to(root)) if alias_path else None,
               'binding_record_sha256': digest(record_path), 'live_readback': live,
               'native_window_id':window['windowId'],'host_policy':app.eda_cli.policy,
               'local_project':record.get('local_project'),'local_open':local_open,
               'original_binding_retained':True,'migration':record.get('migration'),
               'native_design_accepted': False, 'paid_model_calls': 0}
    put_once(target/'eda-binding-readback.json', receipt)
    return receipt
