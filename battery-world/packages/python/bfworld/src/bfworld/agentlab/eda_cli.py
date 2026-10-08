"""Owner/project-bound typed EasyEDA CLI. No arbitrary JS or shell execution.

Only an operator can bind an independently created project. Pi owns parameter
files and design operations; CLI receipts are preserved outside its write scope.
"""
import json
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path
from .store import canonical, identity
from .responsibility_review import local_file

SKILL = Path('/Users/depengsu/.codex/skills/easyeda-agent')
CLI = shutil.which('easyeda') or '/opt/homebrew/bin/easyeda'
DOMAINS = {'sch', 'pcb', 'board', 'doc', 'lib', 'bom', 'view', 'spec', 'api', 'apply', 'project', 'call', 'actions'}
DENIED = {'debug.exec_js', 'project.open', 'project.create', 'board.delete', 'system.page_reload'}
FILE_FLAGS = {'--from','--out','--board','--spec','--layout','--file','--input','--output','--dsn','--ses','--report','--plan','--request','--config','--netlist','--before','--playbook','--layout-page','--journal','--instance-map'}
ROUTE_FLAGS = {'--window','--project','--project-uuid','--host','--ports','--force-stale-read','--skip-version-check'}


def action_check(value):
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
    if argv in (['--help'], ['-h']): return argv
    if argv[0] not in DOMAINS:
        raise ValueError('EDA_COMMAND_DENIED: unsupported root command. Read argv=["--help"] or ["lib","--help"]; do not invent root commands. This is not a busy project or login failure.')
    if argv[0] == 'project' and len(argv) > 1 and argv[1] not in ('info','doc','export','export-source'):
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
    return result


def export_window(health, project):
    windows=health.get('found',{}).get('raw',{}).get('windows',[])
    matches=[w['windowId'] for w in windows if w.get('context',{}).get('projectUuid')==project and w.get('windowId')]
    if len(matches)!=1: raise ValueError('EDA_EXPORT_WINDOW_AMBIGUOUS_OR_MISSING')
    return matches[0]


def command_line(argv, project, window=None):
    command=[CLI,*argv]
    if argv[:2]==['pcb','autoroute'] and '--help' not in argv and '-h' not in argv:
        from .runtime_config import configured, RUNTIME_ROOT
        router=configured('EDA_ROUTER',RUNTIME_ROOT/'toolchains/freerouting-2.5.0/bf-freerouting')
        if not router.is_file():
            raise ValueError('EDA_ROUTER_UNAVAILABLE: no operator-configured local routing engine')
        command+=['--router',shlex.quote(str(router))+' {in} {out}']
    if argv[0] not in ('api','spec') and '--help' not in argv and '-h' not in argv:
        command+=['--project',project]
        if argv[:2]==['project','export']:
            if not window: raise ValueError('EDA_EXPORT_WINDOW_REQUIRED')
            command+=['--project-uuid',project,'--window',window]
    return command


class EdaCLI:
    def __init__(self, app):
        self.app=app; self.store=app.store; self.lock=threading.Lock()
        self.root=self.store.root.parent/'eda-cli'; self.root.mkdir(exist_ok=True)
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS eda_cli_bindings(owner TEXT PRIMARY KEY,project TEXT,authorization TEXT,created REAL,writable INTEGER DEFAULT 0);
              CREATE TABLE IF NOT EXISTS eda_cli_jobs(id TEXT PRIMARY KEY,owner TEXT,operation TEXT,request TEXT,status TEXT,result TEXT,created REAL,ended REAL,UNIQUE(owner,operation));''')
            db.execute("UPDATE eda_cli_jobs SET status='UNKNOWN' WHERE status='RUNNING'")

    def workspace(self, owner):
        self.app.conversations.get(owner)
        p=self.store.root.parent/'participants'/owner
        p.mkdir(exist_ok=True)
        return p

    def binding(self, owner):
        with self.store.connect() as db: row=db.execute('SELECT * FROM eda_cli_bindings WHERE owner=?',(owner,)).fetchone()
        return dict(row) if row else None

    def bind(self,owner,project,authorization,writable=False):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{10,80}',project or ''): raise ValueError('EDA_PROJECT_UUID_REQUIRED')
        old=self.binding(owner)
        if old and old['writable']: raise ValueError('EDA_OWNER_ALREADY_BOUND')
        with self.store.connect() as db:db.execute('INSERT OR REPLACE INTO eda_cli_bindings VALUES(?,?,?,?,?)',(owner,project,authorization,time.time(),int(writable)))
        return self.binding(owner)

    def get(self,owner,jid):
        with self.store.connect() as db:row=db.execute('SELECT * FROM eda_cli_jobs WHERE owner=? AND id=?',(owner,jid)).fetchone()
        if not row: raise ValueError('EDA_JOB_NOT_FOUND')
        d=dict(row);d['request']=json.loads(d['request']);d['result']=json.loads(d['result']) if d['result'] else None
        return d

    def action(self,owner,body,operator=False):
        if not operator:self.app.engineering.authorize(owner)
        root=self.workspace(owner);action=body.get('action','inspect')
        if action=='bind':
            if not operator:raise PermissionError('OPERATOR_REQUIRED')
            return self.bind(owner,body.get('project_uuid'),body.get('authorization','Explicit product engineering task'),body.get('writable') is True)
        if action=='inspect':
            return {'binding':self.binding(owner),'transport':'typed EasyEDA CLI 1.9',
                    'instructions':'Use skill then command argv (without easyeda); server pins project. File arguments are workspace-relative. Unknown CLI flags: use --help. command needs stable operation_id; job retrieves queued results. All same-window calls serialized. Do not use legacy jlceda for this binding.'}
        if action=='skill':
            name=body.get('path','SKILL.md');path=local_file(SKILL,name)
            if not path.is_file() or path.suffix not in ('.md','.json'):raise ValueError('EDA_SKILL_FILE_NOT_FOUND')
            text=path.read_text();offset=max(0,int(body.get('offset',0)));limit=min(18000,max(1,int(body.get('limit',12000))))
            return {'path':name,'text':text[offset:offset+limit],'next_offset':offset+limit if len(text)>offset+limit else None}
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
                return self.get(owner,old['id'])
            if db.execute("SELECT 1 FROM eda_cli_jobs WHERE status='RUNNING'").fetchone():raise ValueError('EDA_COMMAND_RUNNING_USE_JOB')
            db.execute('INSERT INTO eda_cli_jobs VALUES(?,?,?,?,?,?,?,?)',(jid,owner,operation,canonical(req),'RUNNING',None,time.time(),None))
        worker=threading.Thread(target=self.run,args=(owner,jid,argv,binding,root),daemon=True);worker.start();worker.join(15)
        return self.get(owner,jid)

    def run(self,owner,jid,argv,binding,workspace):
        started=time.time();status='FAILED';output={}
        try:
            with self.lock:
                window=None
                if argv[:2]==['project','export'] and '--help' not in argv:
                    health=subprocess.run([CLI,'health'],capture_output=True,text=True,timeout=15,check=True)
                    window=export_window(json.loads(health.stdout),binding['project'])
                command=command_line(argv,binding['project'],window)
                proc=subprocess.run(command,cwd=workspace,capture_output=True,text=True,timeout=540)
            output={'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr,'elapsed_s':time.time()-started}
            status='SUCCEEDED' if proc.returncode==0 else 'FAILED'
            try:
                native=json.loads(proc.stdout)
                if isinstance(native,dict) and native.get('ok') is False:status='FAILED'
            except (ValueError,TypeError):pass
        except subprocess.TimeoutExpired as exc:
            status='UNKNOWN';output={'error':'EDA_COMMAND_TIMEOUT_READ_BACK_BEFORE_RETRY','elapsed_s':time.time()-started,'stdout':str(exc.stdout or '')[-5000:]}
        except Exception as exc:output={'error':str(exc),'elapsed_s':time.time()-started}
        # The full command receipt is immutable to Pi; also expose a local copy.
        receipt={'schema_version':'bf-eda-cli-operation-v1','job_id':jid,'owner':owner,'project':binding['project'],'argv':argv,'status':status,**output}
        path=self.root/(jid+'.json');path.write_text(canonical(receipt))
        local=workspace/'eda-receipts';local.mkdir(exist_ok=True);(local/(jid+'.json')).write_text(canonical(receipt))
        summary={**output,'receipt_path':'eda-receipts/'+jid+'.json','receipt_sha256':identity(receipt)}
        if len(summary.get('stdout',''))>16000:summary['stdout']=summary['stdout'][:16000]+'\n[Full output in receipt_path]'
        with self.store.connect() as db:db.execute('UPDATE eda_cli_jobs SET status=?,result=?,ended=? WHERE id=?',(status,canonical(summary),time.time(),jid))
        self.app.conversations.event(owner,jid,{'type':'eda_cli_operation','job_id':jid,'project':binding['project'],'status':status,'argv':argv,'receipt_sha256':identity(receipt)})
