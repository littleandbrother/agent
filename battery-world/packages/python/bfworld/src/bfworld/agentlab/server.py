"""Loopback workbench; UI projects persisted execution facts only."""
import argparse
import fcntl
import hashlib
import json
import os
import re
from http.cookies import SimpleCookie
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs

from .store import Store, canonical
from . import experiments
from .provider import Provider

REPO = Path(__file__).resolve().parents[6]
UI = REPO / 'apps/agent-studio'
from .runtime_config import HOME_ROOT
DEFAULT_ROOT = HOME_ROOT / 'state'
STEPS = ['版本基线', '设计实验', '受控服务', 'Pi 求解', '状态与恢复', '冻结与对照', '自主补丁', '递归与迁移']


def ui_build():
    """Content identity, so the same files share one build across process restarts."""
    digest = hashlib.sha256()
    for path in sorted(UI.rglob('*')):
        if path.is_file() and path.suffix in {'.html', '.js', '.css'}:
            digest.update(str(path.relative_to(UI)).encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()[:16]


def ui_index():
    build = ui_build()
    page = (UI / 'index.html').read_text()
    page = page.replace('<head>', '<head><meta name="bf-ui-build" content="' + build + '">', 1)
    return re.sub(r'((?:href|src)="/[^"?]+\.(?:css|js))"',
                  lambda m: m[1] + '?v=' + build + '"', page).encode()


class Workbench:
    def __init__(self, root):
        self.store = Store(root)
        self.lock = (self.store.root / 'service.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.provider=Provider(self.store)
        from .developer import Developer
        self.developer=Developer(self)
        from .organization import Organization
        self.organization=Organization(self)
        from .chat import Conversations
        self.conversations=Conversations(self)
        from .product import Products
        self.products=Products(self)
        from .assembly import Assemblies
        self.assemblies=Assemblies(self)
        from .deliverables import Deliverables
        self.deliverables=Deliverables(self)
        from .engineering import Engineering
        self.engineering=Engineering(self)
        from .references import References
        self.references=References(self)
        from .panorama import Panorama
        self.panorama=Panorama(self.store.root)
        self.conversations.reconcile_blocks()
        self.agent_lock=threading.Lock()
        self.store.reconcile()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.work, daemon=True)
        self.thread.start()

    def state(self, owner):
        jobs=self.store.jobs(owner)
        if owner=='operator':
            with self.store.connect() as db:jobs=[self.store.project(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC')]
            for path in sorted((self.store.root.parent/'sessions').glob('*/receipt.json')):
                receipt=json.loads(path.read_text())
                if not receipt.get('dry_run') and 'preflight' not in receipt['owner']:
                    jobs.append({'id':receipt['owner'],'owner':receipt['owner'],'agent':True,
                                 'status':{'COMPLETED':'SUCCEEDED'}.get(receipt['status'],receipt['status']),
                                 'created':receipt['started'],'request':{'task_id':receipt['task_id']}})
            jobs.sort(key=lambda j:j['created'],reverse=True)
        jobs=[{k:j.get(k) for k in ['id','owner','agent','status','created','request']} for j in jobs]
        progress=self.store.root.parent/'progress.json'
        statuses=json.loads(progress.read_text()) if progress.exists() else {}
        model=self.provider.status()
        requests=model.pop('requests')
        model['unknown_usage']=any(r['status']=='UNKNOWN' for r in requests)
        model['used_tokens']=sum(json.loads(r['usage'])['total_tokens'] for r in requests if r['usage'])
        closed=self.store.root.parent/'paid-window-closed.json'
        model['closed']=json.loads(closed.read_text()) if closed.exists() else None
        return {'jobs': jobs, 'steps': [
            {'index': i, 'name': name, 'status': statuses.get(str(i),'pending')} for i, name in enumerate(STEPS)],
            'model': model, 'study':self.study_summary() if owner=='operator' else None,
            'reference': {'name': 'Rotary-TENG · A reference', 'fidelity': 'F1-simplified', 'model_calls': 0}}

    def study_summary(self):
        root=self.store.root.parent/'studies';out={'development':None,'recursive':None,'candidates':[],'lineage':[]}
        path=root/'dev-v1/h0-vs-h1.json'
        if path.exists():
            value=json.loads(path.read_text())
            out['development']={k:value[k] for k in ['parent_pass','child_pass','parent_total','child_total','complete_pairs','promotion']}
        path=root/'recursive-v1/report.json'
        if path.exists():
            value=json.loads(path.read_text())
            out['recursive']={'complete':value['completed_all_declared_trials'],
              'blocked':any(v.get('global_budget_interruptions',0) for v in value['arms'].values()),
              'arms':{k:{f:v[f] for f in ['trials','passed','failed','not_evaluated']} for k,v in value['arms'].items()}}
        for path in sorted((root/'dev-v1/candidates').glob('*/candidate.json')):
            value=json.loads(path.read_text())
            out['candidates'].append({k:value.get(k) for k in ['label','status','parent','identity','changed_files','improver_process']})
        path=root/'recursive-v1/lineage.json'
        if path.exists():
            lineage=json.loads(path.read_text())
            for key,title,parent in [('h0','H0 · 初始程序',None),('h1','H1 · 改变求解程序 P','h0'),
                                     ('joint','Ug · 改变改进程序 U','h1'),('meta_u0_child','U0 生成的后代','h1'),
                                     ('meta_ug_child','Ug 生成的后代','joint')]:
                if not lineage.get(key):continue
                folder=Path(lineage[key]).resolve()
                if folder.parent!=(self.store.root.parent/'harnesses').resolve():continue
                manifest=json.loads((folder/'manifest.json').read_text())
                candidate=next((c for c in out['candidates'] if c.get('identity')==manifest['identity']),None)
                out['lineage'].append({'key':key,'title':title,'parent':parent,'label':manifest['label'],
                    'modules':manifest['loaded_modules'],'process':candidate['improver_process'] if candidate else None})
        return out

    def session_detail(self,owner,include_events=True):
        if not owner.startswith('pi-') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in owner):
            raise PermissionError('SESSION_NOT_FOUND')
        directory=self.store.root.parent/'sessions'/owner
        receipt=json.loads((directory/'receipt.json').read_text())
        status={'COMPLETED':'SUCCEEDED'}.get(receipt['status'],receipt['status'])
        with self.store.connect() as db:
            model_rows=[dict(r) for r in db.execute('SELECT status,charged,reserved FROM model_requests WHERE owner=?',(owner,))]
        if receipt['mode']=='solve' and receipt['harness'].get('app_entry') not in ('chat.js','chat-v2.js','chat-product.js') and status=='SUCCEEDED' and not receipt.get('submission'):status='FAILED'
        result={'receipt':receipt,'model_calls':len(model_rows),'cost_upper_bound_usd':sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in model_rows)}
        if receipt['mode']=='improve':
            result['candidates']=[c for c in self.study_summary()['candidates'] if c['improver_process']==owner]
        if receipt.get('submission'):
            result['verified']=self.store.get(owner,receipt['submission']['job_id'])['result']
        value={'id':owner,'owner':owner,'agent':True,'status':status,'created':receipt['started'],'request':{'task_id':receipt['task_id']},'result':result,'error':receipt.get('error')}
        if include_events:
            value['events']=[]
            for seq,line in enumerate((directory/'trace.jsonl').read_text().splitlines()):
                try:data=json.loads(line)
                except json.JSONDecodeError:continue
                value['events'].append({'seq':seq,'kind':'pi_trace','data':data,'time':data.get('time',receipt['started'])})
            if (directory/'stderr.log').stat().st_size:
                kind='prior_execution_error' if receipt.get('previous_attempts') and receipt['status']=='COMPLETED' else 'execution_failed'
                value['events'].append({'kind':kind,'data':{'message':(directory/'stderr.log').read_text()[-1500:]},'time':receipt.get('ended',receipt['started'])})
        return value

    def work(self):
        while not self.stop.wait(.2):
            with self.store.connect() as db:
                row = db.execute("SELECT * FROM jobs WHERE status='QUEUED' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                continue
            job = self.store.project(row)
            owner, jid = job['owner'], job['id']
            if job['cancel_requested']:
                self.store.update(owner, jid, 'CANCELLED')
                self.store.event(owner, jid, 'cancelled', {'before_dispatch': True})
                continue
            self.store.update(owner, jid, 'RUNNING')
            self.store.event(owner, jid, 'started', {'executor': 'bfworld.application.rotary.run_rotary_mission' if job['request']['task_id']=='rotary-reference' else 'bfworld.agentlab.programmed.execute'})
            try:
                result = self.baseline(owner, jid) if job['request']['task_id']=='rotary-reference' else self.experiment(owner,jid,job['request'])
                self.store.update(owner, jid, 'SUCCEEDED', result)
                self.store.event(owner, jid, 'completed', {'run_id': result['run_id'], 'design_status': result['design_status']})
            except InterruptedError:
                self.store.update(owner, jid, 'CANCELLED')
                self.store.event(owner, jid, 'cancelled', {'process_stopped': True})
            except Exception as exc:
                self.store.update(owner, jid, 'FAILED', error=str(exc)[:1200])
                self.store.event(owner, jid, 'execution_failed', {'error_type': type(exc).__name__, 'message': str(exc)[:1200]})

    def experiment(self,owner,jid,request):
        root=self.store.root/'jobs'/jid;root.mkdir(parents=True,exist_ok=True)
        env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(REPO/'packages/python/bfworld/src'),'PYTHONDONTWRITEBYTECODE':'1','LANG':'en_US.UTF-8'}
        command=[str(REPO/'.venv/bin/python'),'-m','bfworld.agentlab.experiments',str(self.store.root),request['task_id'],request['snapshot_id']]
        with (root/'worker.log').open('w') as log:
            process=subprocess.Popen(command,cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            started=time.monotonic()
            while process.poll() is None:
                cancelled=self.store.get(owner,jid)['cancel_requested']
                if cancelled or time.monotonic()-started>60:
                    import signal
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                    if cancelled:raise InterruptedError()
                    raise TimeoutError('EXPERIMENT_WALL_LIMIT')
                time.sleep(.05)
        if process.returncode:raise RuntimeError((root/'worker.log').read_text()[-1000:])
        result=json.loads((root/'worker.log').read_text())
        self.store.event(owner,jid,'experiment_result', {k:result[k] for k in ['run_id','snapshot_id','design_status','checks','summary']})
        return result

    def baseline(self, owner, jid):
        root = self.store.root / 'jobs' / jid
        root.mkdir(parents=True, exist_ok=False)
        env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(REPO / 'packages/python/bfworld/src'),
               'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'en_US.UTF-8'}
        command = [str(REPO / '.venv/bin/python'), '-m', 'bfworld', 'run', '--mission',
                   str(REPO / 'configs/missions/rotary-overvoltage-v1.json'), '--workspace', str(root / 'live'),
                   '--output', str(root / 'bundle')]
        with (root / 'execution.log').open('w') as log:
            process = subprocess.Popen(command, env=env, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
            started = time.monotonic()
            while process.poll() is None:
                if self.store.get(owner, jid)['cancel_requested']:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
                    raise InterruptedError()
                if time.monotonic() - started > 60:
                    process.kill(); process.wait(); raise TimeoutError('REFERENCE_TIME_BUDGET')
                time.sleep(.05)
        if process.returncode:
            raise RuntimeError((root / 'execution.log').read_text()[-1200:])
        receipt = json.loads((root / 'execution.log').read_text())
        verify = subprocess.run([str(REPO / '.venv/bin/python'), '-m', 'bfworld', 'verify', '--bundle', str(root / 'bundle')],
                                env=env, cwd=REPO, capture_output=True, text=True, timeout=15)
        if verify.returncode:
            raise RuntimeError('BUNDLE_VERIFICATION_FAILED')
        phases = []
        for phase in ['baseline', 'revised', 'fine_validation']:
            files = list((root / 'live').rglob(phase + '-summary.json'))
            summary = json.loads(files[0].read_text())
            phases.append(summary)
            self.store.event(owner, jid, 'experiment_phase', summary)
        import pyarrow.parquet as pq
        rows = pq.read_table(root / 'bundle/channels.parquet').to_pylist()
        return {'task_id': 'rotary-reference', 'run_id': receipt['run_id'], 'execution_status': 'SUCCEEDED',
                'design_status': 'PASS' if phases[-1]['passed'] else 'FAIL', 'phases': phases,
                'bundle_hash': receipt['bundle_hash'], 'fidelity': 'F1-simplified',
                'model_calls': 0, 'hardware_result': False, 'agent_result': False,
                'description': '既有参考程序执行预设基准、修订和细步长复核。',
                'channels': rows[::max(1, len(rows)//450)],
                'artifacts': ['bundle/evidence.json', 'bundle/run-manifest.json', 'bundle/events.jsonl', 'bundle/world.ir.json']}


def handler(workbench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value, kind='application/json; charset=utf-8'):
            content = canonical(value).encode() if not isinstance(value, bytes) else value
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors " + ("'self'" if urlparse(self.path).path=='/model-viewer.html' else "'none'"))
            if getattr(self,'bootstrap_cookie',False):
                token=(workbench.store.root/'operator.token').read_text().strip()
                self.send_header('Set-Cookie','bf_operator='+token+'; Path=/; HttpOnly; SameSite=Strict')
            self.end_headers()
            try:self.wfile.write(content)
            except (BrokenPipeError,ConnectionResetError):pass

        def principal(self):
            authorization=self.headers.get('Authorization','').removeprefix('Bearer ').strip()
            if authorization:return workbench.store.authenticate(authorization)
            cookie=SimpleCookie(self.headers.get('Cookie',''))
            return workbench.store.authenticate(cookie['bf_operator'].value if 'bf_operator' in cookie else '')

        def local_host(self):
            if self.headers.get('Host') not in ('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)):
                raise PermissionError('HOST_DENIED')

        def conversation_stream(self,cid,after):
            workbench.conversations.get(cid)
            self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
            deadline=time.monotonic()+25
            try:
                while time.monotonic()<deadline:
                    rows=workbench.conversations.events(cid,after)
                    for row in rows:
                        self.wfile.write((canonical(row)+'\n').encode());after=row['seq']
                    if not rows:self.wfile.write(b'{"heartbeat":true}\n')
                    self.wfile.flush();time.sleep(.3)
            except (BrokenPipeError,ConnectionResetError):pass

        def provider_stream(self,owner,body):
            started=False
            def chunk(value):
                nonlocal started
                if not started:
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-store');self.end_headers();started=True
                self.wfile.write(('data: '+canonical(value)+'\n\n').encode());self.wfile.flush()
            try:
                workbench.provider.complete(owner,body,on_chunk=chunk)
                if started:self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
            except Exception as exc:
                if not started:raise
                try:
                    self.wfile.write(('data: '+canonical({'error':{'message':str(exc)}})+'\n\ndata: [DONE]\n\n').encode());self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):pass

        def do_GET(self):
            try:
                self.local_host()
                path = urlparse(self.path).path
                static = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                          '/conversation.js': ('conversation.js', 'text/javascript'), '/conversation.css': ('conversation.css', 'text/css'), '/version.js': ('version.js', 'text/javascript'),
                          '/style.css': ('style.css', 'text/css'), '/tokens.css': ('tokens.css', 'text/css'),
                          '/delivery.js': ('delivery.js','text/javascript'), '/trace.js': ('trace.js', 'text/javascript'), '/references.js': ('references.js','text/javascript'), '/engineering.js': ('engineering.js', 'text/javascript'), '/eda.js': ('eda.js', 'text/javascript'), '/trace.css': ('trace.css', 'text/css'), '/developer.js': ('developer.js', 'text/javascript'), '/developer.css': ('developer.css', 'text/css'), '/chat.css':('chat.css','text/css'), '/organization.js':('organization.js','text/javascript'), '/organization.css':('organization.css','text/css'), '/cases.js':('cases.js','text/javascript'), '/product.js':('product.js','text/javascript'), '/product.css':('product.css','text/css')}
                if path in static:
                    name, kind = static[path]
                    self.bootstrap_cookie=path=='/'
                    return self.reply(200, ui_index() if path=='/' else (UI / name).read_bytes(), kind + '; charset=utf-8')
                if path in ('/model-viewer.html','/model-viewer.js','/model-viewer.css'):
                    return self.reply(200,(UI/path[1:]).read_bytes(),('text/html' if path.endswith('.html') else 'text/css' if path.endswith('.css') else 'text/javascript')+'; charset=utf-8')
                if path.startswith('/vendor/three/'):
                    allowed={'build/three.module.js','build/three.core.js','examples/jsm/loaders/GLTFLoader.js','examples/jsm/controls/OrbitControls.js','examples/jsm/utils/BufferGeometryUtils.js'}
                    rel=path.removeprefix('/vendor/three/')
                    if rel not in allowed:return self.reply(404,{'error':'NOT_FOUND'})
                    return self.reply(200,(UI/'vendor/three'/rel).read_bytes(),'text/javascript; charset=utf-8')
                if path in ('/panorama.js','/panorama.css','/console.css','/research.js','/research.css','/product-graph.js','/product-deliverables.js','/product-deliverables-view.js','/product-workspace.js','/product-workspace.css','/reference-case.js'):
                    return self.reply(200,(UI/path[1:]).read_bytes(),('text/javascript' if path.endswith('.js') else 'text/css')+'; charset=utf-8')
                actor = self.principal(); owner = actor['owner']
                if path in ('/api/reference-case','/api/reference-case/artifact'):
                    if actor['role']!='operator':raise PermissionError('OPERATOR_ONLY_REFERENCE_CASE')
                    from .pluck_case import projection, digest
                    home=workbench.store.root.parent
                    data=projection(home)
                    if path.endswith('/artifact'):
                        name=parse_qs(urlparse(self.path).query).get('name',[''])[0]
                        record=next((a for a in data.get('artifacts',[]) if a['path']==name),None)
                        if not record:raise ValueError('CASE_ARTIFACT_NOT_LISTED')
                        root=(home/'reference-cases'/'pluck-v1').resolve();file=(root/name).resolve()
                        if not file.is_relative_to(root) or digest(file)!=record['sha256']:raise ValueError('CASE_ARTIFACT_INTEGRITY')
                        kind={'.pdf':'application/pdf','.png':'image/png','.json':'application/json','.csv':'text/csv','.md':'text/plain','.svg':'image/svg+xml'}.get(file.suffix,'application/octet-stream')
                        return self.reply(200,file.read_bytes(),kind)
                    return self.reply(200,data)
                if path in ('/api/references','/api/references/source'):
                    query=parse_qs(urlparse(self.path).query)
                    target=query.get('session',[owner])[0] if actor['role']=='operator' else owner
                    if actor['role']!='operator':workbench.references.authorize(owner)
                    if path.endswith('/source'):
                        record=workbench.references.get(target,query.get('id',[''])[0])
                        if record['kind']!='source':raise ValueError('REFERENCE_SOURCE_REQUIRED')
                        return self.reply(200,workbench.references.blob(record['raw_sha256']).read_bytes(),'application/octet-stream')
                    return self.reply(200,workbench.references.projection(target))
                if path=='/api/product-context':
                    from .product_authority import context_packet
                    query=parse_qs(urlparse(self.path).query)
                    target=query.get('session',[owner])[0] if actor['role']=='operator' else owner
                    return self.reply(200,context_packet(workbench,target))
                if path=='/api/progress':
                    from .progress import project
                    query=parse_qs(urlparse(self.path).query)
                    target=query.get('session',[owner])[0] if actor['role']=='operator' else owner
                    return self.reply(200,project(workbench,target))
                if path.startswith('/api/engineering'):
                    query=parse_qs(urlparse(self.path).query)
                    operator=actor['role']=='operator'
                    target=query.get('session',[owner])[0] if operator else owner
                    if not operator:workbench.engineering.authorize(owner)
                    if path=='/api/engineering':return self.reply(200,{**workbench.engineering.catalog(target),'jobs':workbench.engineering.jobs(target if target!='operator' else None)})
                    parts=path.strip('/').split('/')
                    if len(parts)==4 and parts[2]=='jobs':return self.reply(200,workbench.engineering.get(owner,parts[3],operator))
                    if len(parts)==5 and parts[2]=='jobs' and parts[4]=='artifact':
                        file=workbench.engineering.artifact(owner,parts[3],query.get('name',[''])[0],operator)
                        kind={'.png':'image/png','.json':'application/json','.glb':'model/gltf-binary','.csv':'text/csv','.log':'text/plain'}.get(file.suffix,'application/octet-stream')
                        return self.reply(200,file.read_bytes(),kind)
                    return self.reply(404,{'error':'NOT_FOUND'})
                if path=='/api/ui-version':
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    return self.reply(200,{'schema_version':'bf-ui-build-v1','build':ui_build()})
                if path in ('/api/assembly','/api/assembly/file'):
                    query=parse_qs(urlparse(self.path).query)
                    target=query.get('session',[owner])[0] if actor['role']=='operator' else owner
                    if path.endswith('/file'):
                        file,meta=workbench.assemblies.file(target,query.get('id',[''])[0])
                        import mimetypes
                        return self.reply(200,file.read_bytes(),mimetypes.guess_type(meta['name'])[0] or 'application/octet-stream')
                    return self.reply(200,workbench.assemblies.projection(target))
                if path=='/api/deliverables':
                    query=parse_qs(urlparse(self.path).query)
                    target=query.get('session',[owner])[0] if actor['role']=='operator' else owner
                    return self.reply(200,workbench.deliverables.inspect(target))
                if path=='/api/product':return self.reply(200,workbench.products.context(owner))
                if path=='/api/health':
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    return self.reply(200,workbench.conversations.readiness())
                if path=='/api/folder-memory':return self.reply(200,workbench.organization.memory(owner))
                if path=='/api/organization':
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    return self.reply(200,{'folders':workbench.organization.folders(),'trash':workbench.conversations.list(True),'deleted_folders':workbench.organization.folders(True),'tools':__import__('bfworld.agentlab.organization',fromlist=['TOOLS']).TOOLS})
                if path.startswith('/api/conversations'):
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    parts=path.strip('/').split('/')
                    if len(parts)==2:return self.reply(200,{'sessions':workbench.conversations.list(),'folders':workbench.organization.folders()})
                    if len(parts)==4 and parts[3]=='events':
                        after=int(parse_qs(urlparse(self.path).query).get('after',['0'])[0])
                        return self.conversation_stream(parts[2],after)
                    if len(parts)==4 and parts[3]=='file':
                        workbench.conversations.get(parts[2])
                        key=parse_qs(urlparse(self.path).query).get('id',[''])[0]
                        return self.reply(200,workbench.products.file(parts[2],key))
                    if len(parts)==3:return self.reply(200,workbench.conversations.detail(parts[2]))
                    return self.reply(404,{'error':'NOT_FOUND'})
                if path.startswith('/api/developer'):
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    query=parse_qs(urlparse(self.path).query)
                    if path in ('/api/developer/research','/api/developer/research/export','/api/developer/research/record'):
                        from .research import Research
                        research=Research(workbench.store.root.parent)
                        if path.endswith('/export'):
                            return self.reply(200,research.export())
                        if path.endswith('/record'):
                            return self.reply(200,research.get(query.get('kind',[''])[0],query.get('id',[''])[0]))
                        return self.reply(200,research.project())
                    if path=='/api/developer/panorama':
                        return self.reply(200,workbench.panorama.projection(query.get('snapshot',[None])[0],query.get('baseline',[None])[0]))
                    if path=='/api/developer/panorama/file':
                        return self.reply(200,workbench.panorama.file(query.get('snapshot',[''])[0],query.get('file',[''])[0],query.get('baseline',[None])[0]))
                    if path=='/api/developer/panorama/check':
                        return self.reply(200,workbench.panorama.check_log(query.get('id',[''])[0]))
                    if path=='/api/developer/trace':
                        from .trace_review import TraceReview
                        return self.reply(200,TraceReview(workbench).snapshot(query.get('session',[None])[0]))
                    if path in ('/api/developer/trace-analysis','/api/developer/trace-compare'):
                        from .trace_review import TraceReview
                        from .trace_analysis import analyze,compare
                        def projection(cid):
                            return analyze(TraceReview(workbench).snapshot(cid))
                        current=projection(query.get('session',[None])[0])
                        return self.reply(200,compare(projection(query.get('baseline',[None])[0]),current) if path.endswith('compare') else current)
                    if path=='/api/developer':
                        return self.reply(200,workbench.developer.projection(query.get('session',[None])[0]))
                    if path=='/api/developer/seed':
                        return self.reply(200,workbench.developer.seed(query.get('session',[None])[0],query.get('revision',[None])[0]))
                    if path=='/api/developer/revision':
                        key=query.get('id',[''])[0]
                        return self.reply(200,{'record':workbench.developer.revision(key),'diff':workbench.developer.diff(key)})
                    if path=='/api/developer/harness':
                        return self.reply(200,workbench.developer.harness_detail(query.get('id',[''])[0]))
                    return self.reply(404,{'error':'NOT_FOUND'})
                if path == '/api/state':
                    return self.reply(200, workbench.state(owner))
                if path=='/api/budget':
                    with workbench.store.connect() as db:
                        grant=dict(db.execute('SELECT * FROM grants WHERE owner=?',(owner,)).fetchone())
                        count=db.execute('SELECT COUNT(*) FROM jobs WHERE owner=?',(owner,)).fetchone()[0]
                        usage=[dict(r) for r in db.execute('SELECT id,status,charged,reserved,usage FROM model_requests WHERE owner=?',(owner,))]
                    return self.reply(200,{'authority':'external-sqlite-ledger','owner':owner,'remaining_experiments':max(0,grant['max_jobs']-count),
                        'requests':usage,'expires':grant['expires'],'receipt_ref':'ledger:'+owner})
                if path.startswith('/api/operations/'):
                    from urllib.parse import unquote
                    operation=unquote(path.removeprefix('/api/operations/'))
                    with workbench.store.connect() as db:
                        row=db.execute('SELECT * FROM jobs WHERE owner=? AND operation=?',(owner,operation)).fetchone()
                    return self.reply(200,workbench.store.project(row) if row else {'status':'NOT_SUBMITTED','operation':operation})
                if path.startswith('/api/tasks/'):
                    task_id=path.removeprefix('/api/tasks/')
                    workbench.store.authorize(owner,{'task_id':task_id})
                    return self.reply(200,experiments.task(task_id))
                parts = path.strip('/').split('/')
                if len(parts)==4 and parts[:2]==['api','jobs'] and parts[3]=='artifact':
                    if actor['role']=='operator':
                        with workbench.store.connect() as db:
                            row=db.execute('SELECT owner FROM jobs WHERE id=?',(parts[2],)).fetchone()
                            if row:owner=row['owner']
                    job=workbench.store.get(owner,parts[2]);result=job['result']
                    name=parse_qs(urlparse(self.path).query).get('name',[''])[0]
                    if not result or name not in result['artifacts']:raise PermissionError('ARTIFACT_DENIED')
                    root=workbench.store.root/'jobs'/job['id'] if job['request']['task_id']=='rotary-reference' else workbench.store.root/'runs'/result['run_id']
                    return self.reply(200,(root/name).read_bytes(),'application/octet-stream')
                if len(parts) == 3 and parts[:2] == ['api', 'jobs']:
                    if parts[2].startswith('pi-') and actor['role']=='operator':
                        return self.reply(200,workbench.session_detail(parts[2]))
                    if actor['role']=='operator':
                        with workbench.store.connect() as db:
                            row=db.execute('SELECT owner FROM jobs WHERE id=?',(parts[2],)).fetchone()
                            if row:owner=row['owner']
                    job = workbench.store.get(owner, parts[2])
                    return self.reply(200, {**job, 'events': workbench.store.events(owner, parts[2])})
                self.reply(404, {'error': 'NOT_FOUND'})
            except PermissionError as exc:
                self.reply(403, {'error': str(exc)})
            except Exception as exc:
                self.reply(400, {'error': str(exc)[:500]})

        def do_POST(self):
            try:
                self.local_host()
                if self.headers.get('Sec-Fetch-Site')=='cross-site':raise PermissionError('ORIGIN_DENIED')
                origin = self.headers.get('Origin')
                if origin and origin != 'http://' + self.headers['Host']:
                    raise PermissionError('ORIGIN_DENIED')
                actor = self.principal(); owner = actor['owner']
                path = urlparse(self.path).path
                length = int(self.headers.get('Content-Length', '0'))
                # Pi sends its preserved history. The provider projects completed
                # interactive tool exchanges before enforcing the 128 KB wire cap.
                incoming_limit = 2 * 1024 * 1024 if path == '/v1/chat/completions' else 128000
                if not 0 < length <= incoming_limit:
                    raise ValueError('REQUEST_SIZE')
                body = json.loads(self.rfile.read(length))
                if path=='/api/measurements/import':
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    target=body.get('session_id')
                    workbench.conversations.get(target)
                    from .event_measurement import import_capture
                    return self.reply(201,import_capture(workbench,target,body))
                if path=='/api/references':
                    target=body.get('session_id',owner) if actor['role']=='operator' else owner
                    if actor['role']!='operator':workbench.references.authorize(owner)
                    elif target!='operator':workbench.conversations.get(target)
                    return self.reply(200,workbench.references.action(target,body))
                if path=='/api/engineering':
                    operator=actor['role']=='operator'
                    if not operator:workbench.engineering.authorize(owner)
                    target=body.get('session_id',owner) if operator else owner
                    if operator and target!='operator':workbench.conversations.get(target)
                    action=body.get('action','run')
                    if action=='eda_probe':return self.reply(200,workbench.engineering.eda.probe(target))
                    if action in ('eda_context','eda_bind'):
                        if not operator:raise PermissionError('OPERATOR_REQUIRED')
                        if action=='eda_context':return self.reply(200,workbench.engineering.eda.context(body.get('window_id')))
                        return self.reply(200,workbench.engineering.eda.bind(target,body.get('window_id'),body.get('project_uuid'),body.get('board_uuid')))
                    if action=='skill':return self.reply(200,workbench.engineering.skill(target,body.get('skill_id'),actor['role']))
                    if action=='run':return self.reply(202,workbench.engineering.submit(target,body,actor['role']))
                    raise ValueError('ENGINEERING_ACTION_INVALID')
                if path=='/api/assembly':
                    target=body.get('session_id',owner) if actor['role']=='operator' else owner
                    action=body.get('action','write')
                    if action=='write':return self.reply(201,workbench.assemblies.write(target,body))
                    if action=='register':return self.reply(201,workbench.assemblies.register(target,body))
                    if action=='verify':
                        if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                        from .product_evidence import verify
                        return self.reply(201,verify(workbench.assemblies,target,body))
                    if action=='goal':
                        if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                        return self.reply(201,workbench.assemblies.set_goal(target,body))
                    raise ValueError('ASSEMBLY_ACTION_INVALID')
                if path=='/api/deliverables':
                    target=body.get('session_id',owner) if actor['role']=='operator' else owner
                    if body.get('action')=='configure_stage':
                        if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                        return self.reply(201,workbench.deliverables.configure_stage(target,body))
                    if body.get('action')=='bind':return self.reply(201,workbench.deliverables.bind(target,body))
                    if body.get('action')=='package':return self.reply(201,workbench.deliverables.package(target))
                    raise ValueError('DELIVERY_ACTION_INVALID')
                if path=='/api/product':
                    target=body.get('session_id',owner) if actor['role']=='operator' else owner
                    return self.reply(201,workbench.products.write(target,body))
                if path=='/api/product/bind':return self.reply(200,workbench.products.bind(owner,body))
                if path=='/api/folder-memory':return self.reply(200,workbench.organization.memory(owner,body))
                if path=='/api/folders' or path.startswith('/api/folders/') or path.startswith('/api/sidebar/'):
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    if path=='/api/folders':return self.reply(201,workbench.organization.create_folder(body['name']))
                    key=path.strip('/').split('/')[-1]
                    if path.startswith('/api/folders/'):return self.reply(200,workbench.organization.mutate_folder(key,body))
                    return self.reply(200,workbench.organization.change_entry(key,body))
                if path.startswith('/api/conversations'):
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    parts=path.strip('/').split('/')
                    if len(parts)==2:return self.reply(201,workbench.conversations.create(body['text'],body.get('task_id'),body['operation_id'],body.get('folder_id'),body.get('attachments'),body.get('model_cap_usd')))
                    if len(parts)==4 and parts[3]=='approve':return self.reply(200,workbench.products.approve(parts[2],body['revision']))
                    if len(parts)==4 and parts[3]=='attachments':return self.reply(201,workbench.products.attach(parts[2],body))
                    if len(parts)==4 and parts[3]=='messages':return self.reply(202,workbench.conversations.send(parts[2],body['text'],body['operation_id']))
                    if len(parts)==4 and parts[3]=='retry':return self.reply(202,workbench.conversations.retry(parts[2]))
                    if len(parts)==4 and parts[3]=='recall':return self.reply(202,workbench.conversations.recalls.request(parts[2],body['message_id']))
                    if len(parts)==4 and parts[3]=='stop':return self.reply(202,workbench.conversations.stop(parts[2]))
                    return self.reply(404,{'error':'NOT_FOUND'})
                if path.startswith('/api/developer/'):
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    if path=='/api/developer/panorama/scan':
                        snapshot=workbench.panorama.scan()
                        return self.reply(200,{'snapshot':snapshot['id']})
                    if path=='/api/developer/revisions':
                        return self.reply(201,workbench.developer.save(body))
                    if path=='/api/developer/validate':
                        return self.reply(200,workbench.developer.validate(body['revision']))
                    if path=='/api/developer/activate':
                        return self.reply(200,workbench.developer.activate(body.get('revision'),body['expected_generation']))
                    return self.reply(404,{'error':'NOT_FOUND'})
                if path=='/api/solve':
                    if actor['role']!='operator':raise PermissionError('OPERATOR_REQUIRED')
                    if (workbench.store.root.parent/'paid-window-closed.json').exists():raise ValueError('PAID_WINDOW_CLOSED')
                    experiments.task(body['task_id'])
                    if body['task_id'].startswith('transfer'):raise PermissionError('TRANSFER_RESERVED')
                    active_revision=workbench.developer.active()['revision']
                    active_harness=workbench.developer.resolve(active_revision) if active_revision else None
                    # Fail synchronously while the serial study owns the process
                    # slot, instead of returning a session that cannot start.
                    session_lock=(workbench.store.root.parent/'pi-session.lock').open('a')
                    try:fcntl.flock(session_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:
                        session_lock.close();raise ValueError('PI_SESSION_ALREADY_RUNNING')
                    if not workbench.agent_lock.acquire(blocking=False):
                        session_lock.close();raise ValueError('PI_SESSION_ALREADY_RUNNING')
                    import secrets
                    session_id='pi-ui-'+secrets.token_hex(6)
                    def solve():
                        try:
                            from .launcher import freeze,launch
                            launch(active_harness or freeze(label='UI'),body['task_id'],label=session_id,store_root=workbench.store.root,process_lock=session_lock)
                        finally:
                            session_lock.close();workbench.agent_lock.release()
                    threading.Thread(target=solve,daemon=True).start()
                    return self.reply(202,{'id':session_id})
                if path=='/v1/chat/completions':
                    if body.get('stream'):return self.provider_stream(owner,body)
                    result=workbench.provider.complete(owner,body)
                    if not body.get('stream'):return self.reply(200,result)
                    chunks=[]
                    common={k:result[k] for k in ['id','model','created']}
                    for choice in result['choices']:
                        message={k:v for k,v in choice['message'].items() if k in ('role','content','tool_calls')}
                        if message.get('tool_calls'):
                            message['tool_calls']=[dict(call,index=i) for i,call in enumerate(message['tool_calls'])]
                        chunks.append({**common,'object':'chat.completion.chunk','choices':[{'index':choice['index'],'delta':message,'finish_reason':choice['finish_reason']}]})
                    chunks.append({**common,'object':'chat.completion.chunk','choices':[],'usage':result['usage']})
                    stream=''.join('data: '+canonical(chunk)+'\n\n' for chunk in chunks)+'data: [DONE]\n\n'
                    return self.reply(200,stream.encode(),'text/event-stream')
                if path == '/api/jobs':
                    request={'task_id':body['task_id']}
                    if body['task_id']!='rotary-reference':
                        experiments.task(body['task_id']);request['snapshot_id']=body['snapshot_id']
                    elif actor['role']!='operator':raise PermissionError('TASK_DENIED')
                    with workbench.conversations.lock:
                        workbench.products.check_job(owner,request['task_id'])
                        job = workbench.store.enqueue(owner, body['operation_id'], request)
                        workbench.products.bind_job(owner,job)
                    return self.reply(202, job)
                if path=='/api/snapshots':
                    sid=experiments.snapshot(workbench.store.root,body['files'])
                    workbench.store.upload(owner,sid)
                    return self.reply(201,{'snapshot_id':sid})
                if path=='/api/submit':
                    with workbench.conversations.lock:
                        workbench.products.check_submit(owner,body['job_id'])
                        return self.reply(200,workbench.store.submit(owner,body['job_id'],body['snapshot_id']))
                parts = path.strip('/').split('/')
                if len(parts) == 4 and parts[:2] == ['api', 'jobs'] and parts[3] == 'cancel':
                    return self.reply(202, workbench.store.cancel(owner, parts[2]))
                self.reply(404, {'error': 'NOT_FOUND'})
            except PermissionError as exc:
                self.reply(403, {'error': str(exc)})
            except Exception as exc:
                self.reply(400, {'error': str(exc)[:500]})
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--port', type=int, default=8768)
    args = parser.parse_args()
    workbench = Workbench(args.root)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(workbench))
    workbench.conversations.port=server.server_port
    link = f'http://127.0.0.1:{args.port}/#access=' + (workbench.store.root / 'operator.token').read_text()
    (workbench.store.root / 'launch-url.txt').write_text(link)
    (workbench.store.root / 'launch-url.txt').chmod(0o600)
    print(f'BF Agent workbench listening on 127.0.0.1:{args.port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
