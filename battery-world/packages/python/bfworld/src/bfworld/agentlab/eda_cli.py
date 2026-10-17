"""Owner/project-bound typed EasyEDA CLI. No arbitrary JS or shell execution.

Only an operator can bind an independently created project. Pi owns parameter
files and design operations; CLI receipts are preserved outside its write scope.
"""
import json
import hashlib
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path
from .store import canonical, identity
from .responsibility_review import local_file
from .native_outcome import summarize
from .runtime_config import configured, eda_policy

SKILL = Path('/Users/depengsu/.codex/skills/easyeda-agent')
CLI = str(configured('EDA_CLI', shutil.which('easyeda') or '/opt/homebrew/bin/easyeda'))
DOMAINS = {'sch', 'pcb', 'board', 'doc', 'lib', 'bom', 'view', 'spec', 'api', 'apply', 'project', 'call', 'actions'}
DENIED = {'debug.exec_js', 'project.open', 'project.create', 'board.delete', 'system.page_reload'}
FILE_FLAGS = {'--from','--out','--board','--spec','--layout','--file','--input','--output','--dsn','--ses','--report','--plan','--request','--config','--netlist','--before','--playbook','--layout-page','--journal','--instance-map'}
ROUTE_FLAGS = {'--window','--project','--project-uuid','--host','--ports','--force-stale-read','--skip-version-check'}


def uncertain_replace(argv, native, command_entered):
    """A daemon timeout reply does not prove an entered replacement did nothing.

    Preserve known validation failures and read failures as FAILED. This changes
    future classification only; historical native/financial rows remain intact.
    """
    if not command_entered or argv[:2] != ['sch','replace'] or not isinstance(native,dict):return False
    error=native.get('error') or {}
    if not isinstance(error,dict) or error.get('code')!='DISPATCH_FAILED':return False
    text=canonical(error).lower()
    return 'context deadline exceeded' in text or 'connector did not respond' in text


def action_check(value):
    if value in ('system.environment', 'document.current'): return
    if not isinstance(value, str) or not value.startswith(('sch.','schematic.','pcb.','board.','doc.','lib.','bom.','view.','project.')) or value in DENIED or (value.startswith('project.') and value not in ('project.current','project.export','project.export_source')) or (value.startswith('lib.') and value.split('.')[1] not in ('search','get','resolve','device','footprint')):
        raise ValueError('EDA_TYPED_ACTION_DENIED')


def check_payload(node, workspace, project=None):
    """Typed payloads cannot override routing or read arbitrary local files."""
    if isinstance(node, dict):
        if 'run' in node:
            if not isinstance(node['run'],str) or '${' in node['run']:raise ValueError('EDA_PLAYBOOK_RUN_SCHEMA')
            args=shlex.split(node['run'])
            if not args or args[0]=='apply' or args[:2]==['sch','apply']:raise ValueError('EDA_NESTED_APPLY_DENIED')
            if not isinstance(node.get('args',[]),list) or not isinstance(node.get('flags',{}),dict):raise ValueError('EDA_PLAYBOOK_RUN_SCHEMA')
            args+=node.get('args',[])
            for flag,value in node.get('flags',{}).items():
                if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9-]*',flag):raise ValueError('EDA_PLAYBOOK_FLAG_SCHEMA')
                if value is False:continue
                for item in value if isinstance(value,list) else [value]:
                    args.append('--'+flag)
                    if item is not True:args.append(str(item))
            validate_argv(args,workspace,project)
        for key, value in node.items():
            if key == 'action': action_check(value)
            if key in ('code','command','shell','script'):
                raise ValueError('EDA_EXECUTABLE_PLAYBOOK_DENIED')
            if key.lower().replace('_','') in ('project','projectuuid','projectid','window','windowid','host','ports'):
                if key.lower().replace('_','') not in ('project','projectuuid','projectid') or project is None or value != project:
                    raise ValueError('EDA_ROUTE_SERVER_OWNED')
            if key.lower() in ('path','filepath','inputpath','outputpath','file','from') and isinstance(value,str):
                local_file(workspace,value)
            check_payload(value,workspace,project)
    elif isinstance(node, list):
        for value in node: check_payload(value,workspace,project)


def validate_argv(argv, workspace, project=None):
    if not isinstance(argv, list) or not 1 <= len(argv) <= 80 or any(not isinstance(x, str) or len(x) > 131072 or '\x00' in x for x in argv):
        raise ValueError('EDA_ARGV_SCHEMA')
    if argv in (['--help'], ['-h'], ['call', '--help'], ['call', '-h']): return argv
    if argv[0] not in DOMAINS:
        raise ValueError('EDA_COMMAND_DENIED: unsupported root command. Read argv=["--help"] or ["lib","--help"]; do not invent root commands. This is not a busy project or login failure.')
    if argv[0] == 'project' and len(argv) > 1 and argv[1] not in ('info','doc','export','export-source','--help','-h'):
        raise ValueError('EDA_PROJECT_OPERATION_DENIED')
    if argv[:2] in (['board','delete'], ['board','rebind'], ['doc','close']):
        raise ValueError('EDA_SCOPE_OPERATION_DENIED')
    if argv[0] == 'call':
        if len(argv) < 2: raise ValueError('EDA_ACTION_REQUIRED')
        action_check(argv[1])
    if argv[0] == 'lib' and len(argv)>1 and argv[1] in ('create','delete','update','import'):
        raise ValueError('EDA_LIBRARY_WRITE_DENIED')
    # Project selection is server-owned. Accept an exact redundant binding,
    # which official CLI examples include, but never permit a foreign route.
    cleaned=[];i=0
    while i<len(argv):
        arg=argv[i];flag=arg.split('=',1)[0]
        if flag in ('--project','--project-uuid'):
            value=arg.split('=',1)[1] if '=' in arg else (argv[i+1] if i+1<len(argv) else None)
            if not project or value!=project:raise ValueError('EDA_PROJECT_IDENTITY_MISMATCH: use the bound project from inspect')
            i+=1 if '=' in arg else 2;continue
        cleaned.append(arg);i+=1
    argv=cleaned
    is_apply=argv[0]=='apply' or argv[:2]==['sch','apply']
    # In apply, --from is a step selector, not a filesystem path.
    file_flags=FILE_FLAGS-{'--from'} if is_apply else FILE_FLAGS
    positional=1 if argv[0]=='apply' else 2 if argv[:2] in (['sch','apply'],['sch','materialize']) else None
    result = list(argv)
    for i, arg in enumerate(argv):
        flag = arg.split('=', 1)[0]
        if flag == '--router':
            raise ValueError('EDA_ROUTER_SERVER_OWNED: use pcb autoroute; the operator-configured engine is injected by the backend')
        if flag in ROUTE_FLAGS: raise ValueError('EDA_ROUTE_SERVER_OWNED: omit route flags; the backend already selects the bound project. This is not a busy project or login failure.')
        if flag == '--payload':
            if '=' in arg or i+1 == len(argv): raise ValueError('EDA_PAYLOAD_SEPARATE_REQUIRED')
            check_payload(json.loads(argv[i+1]),workspace,project)
        if flag in ('--payload','--project-uuid') and i+1==len(argv):raise ValueError('EDA_FLAG_VALUE_REQUIRED')
        if flag in file_flags and '--help' not in argv:
            if '=' in arg: raise ValueError('EDA_FILE_FLAG_SEPARATE_REQUIRED')
            if i+1 == len(argv): raise ValueError('EDA_FILE_VALUE_REQUIRED')
            if '${' in argv[i+1]:raise ValueError('EDA_DYNAMIC_FILE_PATH_DENIED')
            result[i+1] = str(local_file(workspace, argv[i+1]))
        if arg.startswith(('/', '~')) and i and argv[i-1] not in file_flags and i!=positional:
            raise ValueError('EDA_ABSOLUTE_ARGUMENT_DENIED')
    if positional is not None and '--help' not in argv and '-h' not in argv:
        if len(argv)<=positional or argv[positional].startswith('-'):raise ValueError('EDA_POSITIONAL_FILE_REQUIRED')
        result[positional]=str(local_file(workspace,argv[positional]))
    # Apply reads only declarative typed steps, never executable commands.
    if is_apply and '--help' not in argv and '-h' not in argv:
        p=Path(result[positional])
        if not p.is_file():raise ValueError('EDA_APPLY_FILE_NOT_FOUND')
        check_payload(json.loads(p.read_text()),workspace,project)
    # Import the current schematic, rather than enrich PCB attributes from a
    # different library snapshot. P01 desktop readback reproduced a native
    # Netlist Error after that enrichment despite all 172 pin nets matching.
    # Keep the effective flag in the operation receipt, not just subprocess argv.
    if result[:2]==['pcb','import-changes'] and '--help' not in result and '-h' not in result:
        flags=[x for x in result if x.split('=',1)[0]=='--no-sync-attrs']
        if any(x not in ('--no-sync-attrs','--no-sync-attrs=true') for x in flags):
            raise ValueError('EDA_IMPORT_LIBRARY_BACKFILL_DENIED: schematic is the authoritative import source')
        if not flags:result.append('--no-sync-attrs')
    return result


def select_window(health, project, policy=None):
    """One exact project, one compatible host. Never fall back to another window."""
    policy = policy or {'host': 'any', 'modes': []}
    windows=health.get('found',{}).get('raw',{}).get('windows',[])
    if not windows: raise ValueError('EDA_NO_CONNECTED_WINDOW')
    matches=[w for w in windows if w.get('context',{}).get('projectUuid')==project and w.get('windowId')]
    if not matches: raise ValueError('EDA_BOUND_PROJECT_NOT_OPEN')
    allowed=[]
    for window in matches:
        if policy.get('transport') == 'native-cli-v1' and 'native-cli.v1' not in window.get('capabilities', []): continue
        if policy.get('connector_version') and window.get('connectorVersion') != policy['connector_version']: continue
        environment=window.get('context',{}).get('environment',{})
        if policy['host']!='any' and environment.get('host')!=policy['host']: continue
        if policy.get('modes') and environment.get('mode') not in policy['modes']: continue
        allowed.append(window)
    if not allowed:
        if policy.get('connector_version') and not any(w.get('connectorVersion') == policy['connector_version'] for w in matches):
            raise ValueError('EDA_CONNECTOR_VERSION_MISMATCH')
        if any(w.get('context',{}).get('environment',{}).get('host', 'unknown')=='unknown' for w in matches):
            raise ValueError('EDA_HOST_IDENTITY_UNKNOWN')
        raise ValueError('EDA_HOST_POLICY_MISMATCH')
    if len(allowed)!=1: raise ValueError('EDA_WINDOW_AMBIGUOUS')
    return allowed[0]


def export_window(health, project):
    # Legacy callers keep their error contract; new operations use select_window.
    try: return select_window(health,project)['windowId']
    except ValueError as exc: raise ValueError('EDA_EXPORT_WINDOW_AMBIGUOUS_OR_MISSING') from exc


def offline_command(argv):
    return argv[0] in ('api','spec','actions') or '--help' in argv or '-h' in argv


def identity_diagnostic(argv):
    # These fixed reads are themselves the recovery observation. Requiring a
    # project.current probe before document.current would hide the only safe
    # way to distinguish an unavailable FIFO from a foreign project.
    return argv[:2] in (['project','info'], ['project','doc'], ['call','document.current'])


def verified_identity_response(proc, project, diagnostic=False, argv=None):
    try:
        wire=json.loads(proc.stdout)
    except (ValueError,TypeError):
        raise ValueError('EDA_PROJECT_IDENTITY_READ_INVALID_RESPONSE')
    if not isinstance(wire,dict):raise ValueError('EDA_PROJECT_IDENTITY_READ_INVALID_RESPONSE')
    if proc.returncode or wire.get('ok') is not True:
        error=wire.get('error') or {}
        code=error.get('code','NATIVE_READ_FAILED') if isinstance(error,dict) else 'NATIVE_READ_FAILED'
        raise ValueError('EDA_PROJECT_PROBE_FAILED:'+str(code))
    result=wire.get('result') or {};context=wire.get('context') or {}
    if not isinstance(result,dict) or not isinstance(context,dict):
        raise ValueError('EDA_PROJECT_IDENTITY_READ_INVALID_RESPONSE')
    if not diagnostic or argv[:2]==['project','info']:
        uuids=[result.get('uuid'),context.get('projectUuid')]
    else:
        uuids=[context.get('projectUuid'),result.get('parentProjectUuid')]
    known=[v for v in uuids if isinstance(v,str) and v]
    if not known:raise ValueError('EDA_FRESH_PROJECT_IDENTITY_UNKNOWN')
    if any(v!=project for v in known):raise ValueError('EDA_FRESH_PROJECT_IDENTITY_MISMATCH')
    if not diagnostic and result.get('uuid')!=project:
        raise ValueError('EDA_FRESH_PROJECT_IDENTITY_UNKNOWN')
    return wire


def read_health():
    proc=subprocess.run([CLI,'health'],capture_output=True,text=True,timeout=5,check=True)
    return json.loads(proc.stdout)


def ready_window(project, policy, wait_s=0):
    """Bounded observation only: no daemon/client restarts or authentication."""
    deadline=time.monotonic()+wait_s
    while True:
        try: return select_window(read_health(),project,policy)
        except ValueError as exc:
            if str(exc) not in ('EDA_NO_CONNECTED_WINDOW','EDA_BOUND_PROJECT_NOT_OPEN') or time.monotonic()>=deadline: raise
        time.sleep(min(0.5,max(0,deadline-time.monotonic())))


def command_line(argv, project, window=None):
    command=[CLI,*argv]
    if argv[:2]==['pcb','autoroute'] and '--help' not in argv and '-h' not in argv:
        from .runtime_config import configured, RUNTIME_ROOT
        router=configured('EDA_ROUTER',RUNTIME_ROOT/'toolchains/freerouting-2.5.0/bf-freerouting')
        if not router.is_file():
            raise ValueError('EDA_ROUTER_UNAVAILABLE: no operator-configured local routing engine')
        command+=['--router',shlex.quote(str(router))+' {in} {out}']
    if not offline_command(argv):
        command+=['--project',project]
        if argv[:2]==['project','export']:
            if not window: raise ValueError('EDA_EXPORT_WINDOW_REQUIRED')
            command+=['--project-uuid',project]
        if window: command+=['--window',window]
    return command


class EdaCLI:
    def __init__(self, app):
        self.app=app; self.store=app.store; self.lock=threading.Lock(); self.policy=eda_policy()
        self.root=self.store.root.parent/'eda-cli'; self.root.mkdir(exist_ok=True)
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS eda_cli_bindings(owner TEXT PRIMARY KEY,project TEXT,authorization TEXT,created REAL,writable INTEGER DEFAULT 0);
              CREATE TABLE IF NOT EXISTS eda_cli_binding_revisions(id TEXT PRIMARY KEY,owner TEXT,previous_project TEXT,project TEXT,authorization TEXT,created REAL,writable INTEGER,proof TEXT);
              CREATE TABLE IF NOT EXISTS eda_cli_jobs(id TEXT PRIMARY KEY,owner TEXT,operation TEXT,request TEXT,status TEXT,result TEXT,created REAL,ended REAL,UNIQUE(owner,operation));''')
            db.execute("UPDATE eda_cli_jobs SET status='UNKNOWN' WHERE status='RUNNING'")

    def workspace(self, owner):
        self.app.conversations.get(owner)
        p=self.store.root.parent/'participants'/owner
        p.mkdir(exist_ok=True)
        return p

    def binding(self, owner):
        with self.store.connect() as db:
            revision=db.execute('SELECT * FROM eda_cli_binding_revisions WHERE owner=? ORDER BY created DESC,rowid DESC LIMIT 1',(owner,)).fetchone()
            row=revision or db.execute('SELECT * FROM eda_cli_bindings WHERE owner=?',(owner,)).fetchone()
        return dict(row) if row else None

    def migrate_binding(self, owner, previous_project, project, proof, authorization, *, operator=False):
        """Append an operator-proved destination; never rewrite the original row."""
        if not operator:raise PermissionError('OPERATOR_REQUIRED')
        if (not re.fullmatch(r'[a-zA-Z0-9_-]{10,80}',project or '') or project==previous_project or
            not isinstance(proof,str) or not re.fullmatch(r'[a-f0-9]{64}',proof)):
            raise ValueError('EDA_MIGRATION_IDENTITY_REQUIRED')
        old=self.binding(owner)
        if old and old['project']==project and old.get('proof')==proof:return old
        if not old or old['project']!=previous_project or not old['writable']:
            raise ValueError('EDA_MIGRATION_PREVIOUS_BINDING_REQUIRED')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            foreign=db.execute('SELECT owner FROM eda_cli_bindings WHERE project=? AND owner!=? UNION SELECT owner FROM eda_cli_binding_revisions WHERE project=? AND owner!=?',(project,owner,project,owner)).fetchone()
            if foreign:raise ValueError('EDA_MIGRATION_FOREIGN_PROJECT')
            db.execute('INSERT INTO eda_cli_binding_revisions VALUES(?,?,?,?,?,?,?,?)',
                       ('eda-binding-'+identity([owner,previous_project,project,proof])[:24],owner,previous_project,project,authorization,time.time(),1,proof))
        return self.binding(owner)

    def bind(self,owner,project,authorization,writable=False):
        from .runtime_config import validate_native_project
        validate_native_project(project)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{10,80}',project or ''): raise ValueError('EDA_PROJECT_UUID_REQUIRED')
        old=self.binding(owner)
        if old and old['writable']: raise ValueError('EDA_OWNER_ALREADY_BOUND')
        with self.store.connect() as db:db.execute('INSERT OR REPLACE INTO eda_cli_bindings VALUES(?,?,?,?,?)',(owner,project,authorization,time.time(),int(writable)))
        return self.binding(owner)

    def get(self,owner,jid,origin='job_lookup'):
        with self.store.connect() as db:row=db.execute('SELECT * FROM eda_cli_jobs WHERE owner=? AND id=?',(owner,jid)).fetchone()
        if not row: raise ValueError('EDA_JOB_NOT_FOUND')
        d=dict(row);d['request']=json.loads(d['request']);d['result']=json.loads(d['result']) if d['result'] else None
        # This is a projection, never an update to the immutable original receipt.
        # Reusing an operation ID retrieves history; it does not revalidate the
        # current design or execute the native command again.
        d['observation']={'origin':origin,'dispatch_requested_in_this_call':origin=='submitted_operation',
                          'current_design_revalidated':False,'original_receipt_unchanged':True}
        return d

    def public_history(self, owner, project):
        """Bounded recovery pointers, not new SDK observations or acceptance."""
        workspace = self.workspace(owner)
        predicates = "owner=? AND json_extract(request,'$.project')=?"
        with self.store.connect() as db:
            rows = list(db.execute('SELECT * FROM eda_cli_jobs WHERE '+predicates+
                                   ' ORDER BY created DESC,id DESC LIMIT 8', (owner,project)))
            latest = {}
            for group, action in [('sch','read'),('sch','save'),('pcb','dump'),('pcb','drc'),('pcb','list')]:
                latest[group+'.'+action] = db.execute('SELECT * FROM eda_cli_jobs WHERE '+predicates+
                    " AND json_extract(request,'$.argv[0]')=? AND json_extract(request,'$.argv[1]')=?"
                    ' ORDER BY created DESC,id DESC LIMIT 1', (owner,project,group,action)).fetchone()
        def brief(row):
            if row is None:return None
            row=dict(row);result=json.loads(row['result']) if row['result'] else {}
            expected='eda-receipts/'+row['id']+'.json';path=workspace/expected
            value={'id':row['id'],'operation':row['operation'],'status':row['status'],
                   'argv':json.loads(row['request'])['argv'],'created':row['created'],'ended':row['ended'],
                   'observation_origin':'immutable historical operation',
                   'current_design_revalidated':False,'receipt_status':'PENDING' if row['status']=='RUNNING' else 'UNAVAILABLE'}
            if (result.get('receipt_path')==expected and not (workspace/'eda-receipts').is_symlink() and
                    not path.is_symlink() and path.is_file()):
                raw=path.read_bytes()
                if len(raw)<=8*1024*1024 and hashlib.sha256(raw).hexdigest()==result.get('receipt_sha256'):
                    receipt=json.loads(raw)
                    if (receipt.get('job_id')==row['id'] and receipt.get('owner')==owner and
                            receipt.get('project')==project and receipt.get('status')==row['status']):
                        value.update(receipt_status='HASH_BOUND',receipt={'path':expected,'sha256':result['receipt_sha256']})
                    else:value['receipt_status']='IDENTITY_MISMATCH'
                else:value['receipt_status']='HASH_MISMATCH'
            return value
        return {'schema_version':'bf-original-owner-eda-observations-v1','owner':owner,'project':project,
                'recent_operations':[brief(row) for row in rows],
                'latest_by_action':{name:brief(row) for name,row in latest.items()},
                'new_native_calls':0,'full_product_passed':False,'physical_verified':False}

    def action(self,owner,body,operator=False):
        if body.get('action') in ('command', 'bind'):
            from .runtime_config import require_capability
            require_capability('native')
        if not operator:self.app.engineering.authorize(owner)
        root=self.workspace(owner);action=body.get('action','inspect')
        fields = {'inspect': set(), 'bind': {'project_uuid','authorization','writable'},
                  'skill': {'path','offset','limit'}, 'job': {'job_id','wait_for_completion'},
                  'command': {'argv','operation_id','wait_for_completion'}}
        if action not in fields: raise ValueError('EDA_ACTION_INVALID')
        unknown = set(body) - fields[action] - {'action','session_id'}
        if unknown: raise ValueError('EDA_UNEXPECTED_FIELDS: '+','.join(sorted(unknown)))
        if action=='bind':
            if not operator:raise PermissionError('OPERATOR_REQUIRED')
            return self.bind(owner,body.get('project_uuid'),body.get('authorization','Explicit product engineering task'),body.get('writable') is True)
        if action=='inspect':
            binding=self.binding(owner); readiness={'ready':False,'reason':'EDA_INDEPENDENT_PROJECT_BINDING_REQUIRED'}
            if binding:
                try:
                    window=ready_window(binding['project'],self.policy)
                    readiness={'ready':True,'window_id':window['windowId'],
                               'environment':window.get('context',{}).get('environment'),
                               'connector_version':window.get('connectorVersion'),'project_uuid':binding['project']}
                except Exception as exc: readiness={'ready':False,'reason':str(exc)}
            return {'binding':binding,'adapter':'easyeda-typed-v1',
                    'transport':self.policy.get('transport','easyeda-typed-v1'),
                    'host_policy':self.policy,'readiness':readiness,
                    'import_changes_policy':{'attribute_source':'schematic',
                                             'automatic_library_backfill':False,
                                             'effective_flags':['--no-sync-attrs']},
                    'instructions':'Use skill then command argv (without easyeda); server pins project. File arguments are workspace-relative. Unknown CLI flags: use --help. command needs stable operation_id; job retrieves queued results. All same-window calls serialized. Do not use legacy jlceda for this binding.'}
        if action=='skill':
            name=body.get('path')
            if isinstance(name,str) and name.startswith('references/'):
                value=self.app.skills.action(owner,{'action':'resource','path':'vendor/easyeda-typed/'+name,
                    'offset':body.get('offset',0),'limit':body.get('limit',12000),'offset_unit':'characters'})
                return {**value,'requested_path':name,'text':value['content']}
            aliases={'SKILL.md':'easyeda-agent','easyeda-agent':'easyeda-agent',
                     'easyeda-pcb-routing':'easyeda-pcb-routing'}
            if name not in aliases:
                raise ValueError('EDA_SKILL_NOT_FOUND: use path=easyeda-agent or easyeda-pcb-routing; use bf_skill resource for frozen references')
            value=self.app.skills.action(owner,{'action':'activate','skill_id':aliases[name]})
            return {**value,'requested_path':name,'text':value['content'],'next_offset':None}
        if action=='job':return self.get(owner,body.get('job_id'))
        if action!='command':raise ValueError('EDA_ACTION_INVALID')
        binding=self.binding(owner)
        if not binding:raise ValueError('EDA_INDEPENDENT_PROJECT_BINDING_REQUIRED')
        argv=validate_argv(body.get('argv'),root,binding['project'])
        if not binding['writable'] and '--help' not in argv and argv[0] not in ('api','spec') and argv[:2] not in (["project","info"],["project","doc"],["lib","search"],["lib","get"],["lib","resolve"],["lib","device"],["lib","footprint"]):
            raise ValueError('EDA_REFERENCE_READ_ONLY_NEW_PROJECT_REQUIRED')
        if '--project-uuid' in argv and argv[argv.index('--project-uuid')+1]!=binding['project']:
            raise ValueError('EDA_PROJECT_IDENTITY_MISMATCH')
        operation=body.get('operation_id')
        if not isinstance(operation,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',operation):raise ValueError('EDA_OPERATION_ID_REQUIRED')
        req={'argv':body['argv'],'project':binding['project']};jid='eda-'+identity([owner,operation])[:20]
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM eda_cli_jobs WHERE owner=? AND operation=?',(owner,operation)).fetchone()
            if old:
                if old['request']!=canonical(req):raise ValueError('EDA_OPERATION_CONFLICT: this operation_id already identifies different arguments; use a new ID for a changed command. This is not a busy project.')
                return self.get(owner,old['id'],'existing_operation')
            if db.execute("SELECT 1 FROM eda_cli_jobs WHERE status='RUNNING'").fetchone():raise ValueError('EDA_COMMAND_RUNNING_USE_JOB')
            db.execute('INSERT INTO eda_cli_jobs VALUES(?,?,?,?,?,?,?,?)',(jid,owner,operation,canonical(req),'RUNNING',None,time.time(),None))
        worker=threading.Thread(target=self.run,args=(owner,jid,argv,binding,root),daemon=True);worker.start();worker.join(15)
        return self.get(owner,jid,'submitted_operation')

    def run(self,owner,jid,argv,binding,workspace):
        started=time.time();status='FAILED';output={};host={};command_entered=False;probe_record=None
        try:
            with self.lock:
                window=None
                if not offline_command(argv):
                    selected=ready_window(binding['project'],self.policy,self.policy['wait_s'])
                    window=selected['windowId']
                    # A cached health context cannot prove the active project.
                    if not identity_diagnostic(argv):
                        probe_args=[CLI,'project','info','--window',window]
                        probe_record={'argv':probe_args,'readonly':True,'design_command_sent':False}
                        probe=subprocess.run(probe_args,capture_output=True,text=True,timeout=15)
                        probe_record.update(exit_code=probe.returncode,stdout=probe.stdout,stderr=probe.stderr)
                        fresh=verified_identity_response(probe,binding['project'])
                        current={**selected,'context':{'projectUuid':binding['project'],
                            'environment':fresh.get('result',{}).get('environment') or fresh.get('context',{}).get('environment',{})}}
                        select_window({'found':{'raw':{'windows':[current]}}},binding['project'],self.policy)
                    else:current=selected
                    host={'window_id':window,'environment':current['context']['environment'],
                          'connector_version':selected.get('connectorVersion'),'project_uuid':binding['project']}
                command=command_line(argv,binding['project'],window)
                command_entered=True
                help_key = identity({'argv': argv, 'cli_sha256': hashlib.sha256(Path(CLI).read_bytes()).hexdigest(),
                                     'policy': self.policy}) if '--help' in argv or '-h' in argv else None
                cache = self.root/'help-cache'/(help_key+'.json') if help_key else None
                cached = json.loads(cache.read_text()) if cache and cache.is_file() else None
                if cached:
                    proc = subprocess.CompletedProcess(command, cached['exit_code'], cached['stdout'], cached['stderr'])
                else:
                    proc=subprocess.run(command,cwd=workspace,capture_output=True,text=True,timeout=540)
                    if cache and proc.returncode == 0:
                        cache.parent.mkdir(exist_ok=True)
                        cache.write_text(canonical({'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr}))
            output={'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr,'elapsed_s':time.time()-started}
            if help_key: output['help_cache']={'key':help_key,'hit':bool(cached),'path':str(cache)}
            if identity_diagnostic(argv) and not offline_command(argv):
                fresh=verified_identity_response(proc,binding['project'],True,argv)
                verified={**selected,'context':{'projectUuid':binding['project'],
                    'environment':fresh.get('result',{}).get('environment') or fresh.get('context',{}).get('environment',{})}}
                select_window({'found':{'raw':{'windows':[verified]}}},binding['project'],self.policy)
                host['environment']=verified['context']['environment']
            status='SUCCEEDED' if proc.returncode==0 else 'FAILED'
            try:
                native=json.loads(proc.stdout)
                if isinstance(native,dict) and native.get('ok') is False:status='FAILED'
                if uncertain_replace(argv,native,command_entered):status='UNKNOWN'
            except (ValueError,TypeError):pass
        except subprocess.TimeoutExpired as exc:
            status='UNKNOWN' if command_entered else 'FAILED'
            output={'error':'EDA_COMMAND_TIMEOUT_READ_BACK_BEFORE_RETRY' if command_entered else 'EDA_PROJECT_PROBE_TIMEOUT_ACTION_NOT_SENT',
                    'elapsed_s':time.time()-started,'stdout':str(exc.stdout or '')[-5000:]}
            if not command_entered and probe_record is not None:probe_record['timed_out']=True
        except Exception as exc:output.update(error=str(exc),elapsed_s=time.time()-started)
        output['command_entered']=command_entered
        if probe_record is not None:output['project_probe']=probe_record
        # The full command receipt is immutable to Pi; also expose a local copy.
        receipt={'schema_version':'bf-eda-cli-operation-v1','job_id':jid,'owner':owner,'project':binding['project'],'argv':argv,
                 'host_policy':self.policy,'native_host':host,'status':status,**output}
        path=self.root/(jid+'.json');path.write_text(canonical(receipt))
        local=workspace/'eda-receipts';local.mkdir(exist_ok=True);(local/(jid+'.json')).write_text(canonical(receipt))
        outcome=summarize(receipt)
        summary={**output,'native_host':host,'outcome':outcome,'receipt_path':'eda-receipts/'+jid+'.json','receipt_sha256':identity(receipt)}
        if len(summary.get('stdout',''))>16000:summary['stdout']=summary['stdout'][:16000]+'\n[Full output in receipt_path]'
        with self.store.connect() as db:db.execute('UPDATE eda_cli_jobs SET status=?,result=?,ended=? WHERE id=?',(status,canonical(summary),time.time(),jid))
        self.app.conversations.event(owner,jid,{'type':'eda_cli_operation','job_id':jid,'project':binding['project'],'status':status,'argv':argv,'outcome':outcome,'receipt_sha256':identity(receipt)})
