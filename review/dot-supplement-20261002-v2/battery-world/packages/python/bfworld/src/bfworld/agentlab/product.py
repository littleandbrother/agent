"""Product conversation records. Assumptions are proposals, never user authority.

Engineering jobs remain in the fixed apparatus. This module binds, rather than
recomputes, its results to a specific proposal version.
"""
import hashlib
import json
import time
from pathlib import Path
from .store import canonical, identity
from . import experiments

CAPABILITIES = [
    {'id': 'rotary-f1', 'name': '旋转能量源 · F1 计算实验', 'status': 'available',
     'tasks': [f'dev-{i:02}' for i in range(1, 9)],
     'scope': '固定旋转能量源模型下的储能、电源、采样、计算与交付检查；不验证机械 CAD、FEM 或实物。'},
    {'id': 'cad', 'name': '尺寸 CAD', 'status': 'not_connected',
     'scope': '等待安装；Blender 展示模型不代替制造 CAD。'},
    {'id': 'field-acceptance', 'name': '安装与现场验收', 'status': 'not_connected',
     'scope': '需要实物、安装条件与测量记录；不能由计算通过替代。'},
]


class Products:
    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.root = self.store.root / 'products'
        with self.store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS product_sessions(owner TEXT PRIMARY KEY,created REAL);
            CREATE TABLE IF NOT EXISTS product_creation(owner TEXT PRIMARY KEY,input_hash TEXT);
            CREATE TABLE IF NOT EXISTS product_records(owner TEXT,revision INTEGER,kind TEXT,payload TEXT,source_message TEXT,operation TEXT,created REAL,PRIMARY KEY(owner,revision),UNIQUE(owner,operation));
            CREATE TABLE IF NOT EXISTS product_approvals(owner TEXT,revision INTEGER,message_id TEXT,PRIMARY KEY(owner,revision));
            CREATE TABLE IF NOT EXISTS product_approval_actions(owner TEXT,revision INTEGER,message_id TEXT,PRIMARY KEY(owner,revision,message_id));
            INSERT OR IGNORE INTO product_approval_actions SELECT * FROM product_approvals;
            CREATE TABLE IF NOT EXISTS product_bindings(owner TEXT,revision INTEGER,task_id TEXT,rationale TEXT,PRIMARY KEY(owner,revision));
            CREATE TABLE IF NOT EXISTS product_jobs(owner TEXT,job_id TEXT,revision INTEGER,PRIMARY KEY(owner,job_id));
            CREATE TABLE IF NOT EXISTS product_attachments(owner TEXT,id TEXT,name TEXT,digest TEXT,created REAL,PRIMARY KEY(owner,id));
            ''')

    def exists(self, owner):
        with self.store.connect() as db:
            return bool(db.execute('SELECT 1 FROM product_sessions WHERE owner=?', (owner,)).fetchone())

    def create(self, owner, attachments=None):
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO product_sessions VALUES(?,?)', (owner, time.time()))
            db.execute('INSERT OR IGNORE INTO product_creation VALUES(?,?)', (owner, identity(attachments or [])))
        for attachment in attachments or []:
            self.attach(owner, attachment)

    def check_creation(self, owner, attachments):
        with self.store.connect() as db:
            old = db.execute('SELECT input_hash FROM product_creation WHERE owner=?', (owner,)).fetchone()
        if old and old['input_hash'] != identity(attachments or []):
            raise ValueError('OPERATION_CONFLICT')

    def validate_attachments(self, attachments):
        if not isinstance(attachments, list) or len(attachments) > 3:
            raise ValueError('PRODUCT_ATTACHMENT_LIMIT')
        for body in attachments:
            name = self.text(body['name'], 100)
            if Path(name).name != name or Path(name).suffix.lower() not in ('.txt', '.md', '.json'):
                raise ValueError('PRODUCT_ATTACHMENT_TEXT_ONLY')
            self.text(body['content'], 16000)

    def require(self, owner):
        if not self.exists(owner):
            raise PermissionError('PRODUCT_SESSION_REQUIRED')
        if self.app.organization.metadata(owner)['deleted']:
            raise PermissionError('CONVERSATION_DELETED')

    def message(self, owner, mid):
        with self.store.connect() as db:
            r = db.execute('SELECT * FROM chat_messages WHERE id=? AND conversation=?', (mid, owner)).fetchone()
        if not r or r['status'] in ('WITHDRAWN', 'RECALLING', 'CANCELLED'):
            raise ValueError('PRODUCT_SOURCE_MESSAGE_INVALID')
        return dict(r)

    @staticmethod
    def text(value, maximum=2000):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError('PRODUCT_TEXT_INVALID')
        return value.strip()

    def records(self, owner):
        with self.store.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM product_records WHERE owner=? ORDER BY revision', (owner,))]
            recalls = [dict(r) for r in db.execute("SELECT from_seq,to_seq FROM chat_recalls WHERE conversation=? AND status='COMPLETE'", (owner,))]
            events = {r['source']: r['seq'] for r in db.execute('SELECT source,seq FROM chat_events WHERE conversation=?', (owner,))}
        for r in rows:
            r['payload'] = json.loads(r['payload'])
            seq = events.get('product-' + str(r['revision']))
            try:
                self.message(owner, r['source_message'])
                r['stale'] = any(seq is not None and c['from_seq'] <= seq <= c['to_seq'] for c in recalls)
            except ValueError:
                r['stale'] = True
        return rows

    def current(self, owner):
        return next((r for r in reversed(self.records(owner)) if r['kind'] == 'proposal' and not r['stale']), None)

    def write(self, owner, body):
        self.require(owner)
        kind = body.get('kind')
        if kind not in ('proposal', 'question'):
            raise ValueError('PRODUCT_RECORD_KIND')
        source = body['source_message_id']
        self.message(owner, source)
        operation = self.text(body['operation_id'], 100)
        p = body['payload']
        if not isinstance(p, dict):
            raise ValueError('PRODUCT_PAYLOAD_INVALID')
        if kind == 'proposal':
            keys = {'title', 'purpose', 'form', 'service', 'installation', 'energy', 'assumptions', 'acceptance', 'limits'}
            if set(p) != keys:
                raise ValueError('PRODUCT_PROPOSAL_FIELDS')
            for k in ('title', 'purpose', 'form', 'service', 'installation', 'energy'):
                self.text(p[k])
            for k in ('assumptions', 'acceptance', 'limits'):
                if not isinstance(p[k], list) or not 1 <= len(p[k]) <= 12:
                    raise ValueError('PRODUCT_LIST_REQUIRED')
                for item in p[k]:
                    self.text(item)
        else:
            if set(p) != {'question', 'options', 'reason'}:
                raise ValueError('PRODUCT_QUESTION_FIELDS')
            self.text(p['question']); self.text(p['reason'])
            if not isinstance(p['options'], list) or not 2 <= len(p['options']) <= 3:
                raise ValueError('PRODUCT_QUESTION_OPTIONS')
            for option in p['options']:
                self.text(option, 200)
        with self.app.conversations.lock:
            self.message(owner, source)
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                old = db.execute('SELECT * FROM product_records WHERE owner=? AND operation=?', (owner, operation)).fetchone()
                if old:
                    if old['payload'] != canonical(p) or old['kind'] != kind or old['source_message'] != source:
                        raise ValueError('OPERATION_CONFLICT')
                    return next(r for r in self.records(owner) if r['revision'] == old['revision'])
                revision = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM product_records WHERE owner=?', (owner,)).fetchone()[0]
                db.execute('INSERT INTO product_records VALUES(?,?,?,?,?,?,?)', (owner, revision, kind, canonical(p), source, operation, time.time()))
                if kind == 'proposal':
                    db.execute("UPDATE grants SET task_ids='[]' WHERE owner=?", (owner,))
            self.app.conversations.event(owner, 'product-' + str(revision), {'type': 'product_record', 'revision': revision, 'kind': kind})
            if kind == 'proposal':
                self.save_file(owner, f'proposal-v{revision}.json', canonical({'schema_version': 'bf-product-proposal-v1', 'revision': revision, 'source_message_id': source, 'authority': 'agent_proposal', **p}))
            return next(r for r in self.records(owner) if r['revision'] == revision)

    def approve(self, owner, revision):
        self.require(owner)
        with self.app.conversations.lock:
            proposal = self.current(owner)
            if not proposal or proposal['revision'] != revision:
                raise ValueError('PRODUCT_REVISION_STALE')
            if self.approved(owner, revision):
                return self.projection(owner)
            prefix = 'approve-product-' + str(revision) + '-'
            with self.store.connect() as db:
                attempt = db.execute('SELECT COUNT(*) FROM chat_messages WHERE conversation=? AND operation LIKE ?', (owner, prefix + '%')).fetchone()[0]
            # A user-facing durable message is the authority. Pi has no approval route.
            message = self.app.conversations.send(owner, f'按产品方案 v{revision} 继续。保留其中标明的假设；若发现不成立，请更新方案说明影响。', prefix + str(attempt))
            self.message(owner, message['id'])
            with self.store.connect() as db:
                db.execute('INSERT OR IGNORE INTO product_approval_actions VALUES(?,?,?)', (owner, revision, message['id']))
        return self.projection(owner)

    def approved(self, owner, revision):
        with self.store.connect() as db:
            rows = db.execute('SELECT message_id FROM product_approval_actions WHERE owner=? AND revision=?', (owner, revision)).fetchall()
        for row in rows:
            try:
                self.message(owner, row['message_id'])
                return True
            except ValueError:
                pass
        return False

    def binding(self, owner):
        proposal = self.current(owner)
        if not proposal:
            return None
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM product_bindings WHERE owner=? AND revision=?', (owner, proposal['revision'])).fetchone()
        return dict(row) if row else None

    def bind(self, owner, body):
        self.require(owner)
        task_id = body['task_id']
        if body.get('adapter') != 'rotary-f1' or task_id not in CAPABILITIES[0]['tasks']:
            raise ValueError('PRODUCT_CAPABILITY_UNAVAILABLE')
        rationale = self.text(body['rationale'])
        with self.app.conversations.lock:
            proposal = self.current(owner)
            if not proposal or proposal['revision'] != body['revision']:
                raise ValueError('PRODUCT_REVISION_STALE')
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                grant = db.execute('SELECT * FROM grants WHERE owner=?', (owner,)).fetchone()
                if not grant or time.time() > grant['expires']:
                    raise ValueError('MODEL_OWNER_GRANT_EXPIRED')
                old = db.execute('SELECT * FROM product_bindings WHERE owner=? AND revision=?', (owner, proposal['revision'])).fetchone()
                if old and old['task_id'] != task_id:
                    raise ValueError('PRODUCT_BINDING_IMMUTABLE_NEW_REVISION_REQUIRED')
                db.execute('INSERT OR IGNORE INTO product_bindings VALUES(?,?,?,?)', (owner, proposal['revision'], task_id, rationale))
                # Preserve expiry, experiment cap and all existing receipts.
                db.execute('UPDATE grants SET task_ids=? WHERE owner=?', (canonical([task_id]), owner))
        return {'binding': self.binding(owner), 'task': experiments.task(task_id), 'scope': CAPABILITIES[0]['scope'],
                'authority': 'provisional-computational-exploration', 'product_accepted': False}

    def check_job(self, owner, task_id):
        if not self.exists(owner):
            return
        binding = self.binding(owner)
        if not binding or binding['task_id'] != task_id:
            raise ValueError('PRODUCT_ADAPTER_BINDING_REQUIRED')

    def bind_job(self, owner, job):
        if self.exists(owner):
            binding = self.binding(owner)
            with self.store.connect() as db:
                db.execute('INSERT OR IGNORE INTO product_jobs VALUES(?,?,?)', (owner, job['id'], binding['revision']))

    def check_submit(self, owner, jid):
        if not self.exists(owner):
            return
        binding = self.binding(owner)
        with self.store.connect() as db:
            row = db.execute('SELECT revision FROM product_jobs WHERE owner=? AND job_id=?', (owner, jid)).fetchone()
        if not binding or not row or row['revision'] != binding['revision']:
            raise ValueError('PRODUCT_EVIDENCE_STALE')

    def save_file(self, owner, name, text):
        root = self.root / owner
        root.mkdir(parents=True, exist_ok=True)
        dest = root / name
        if dest.exists():
            if dest.read_text() != text:
                raise ValueError('PRODUCT_FILE_IMMUTABLE')
        else:
            with dest.open('x') as f:
                f.write(text)
        return hashlib.sha256(text.encode()).hexdigest()

    def attach(self, owner, body):
        self.require(owner)
        self.validate_attachments([body])
        name = self.text(body['name'], 100)
        if Path(name).name != name or Path(name).suffix.lower() not in ('.txt', '.md', '.json'):
            raise ValueError('PRODUCT_ATTACHMENT_TEXT_ONLY')
        content = self.text(body['content'], 16000)
        key = 'input-' + identity({'name': name, 'content': content})[:20]
        digest = self.save_file(owner, key + '.txt', content)
        with self.store.connect() as db:
            if db.execute('SELECT COUNT(*) FROM product_attachments WHERE owner=?', (owner,)).fetchone()[0] >= 20:
                raise ValueError('PRODUCT_ATTACHMENT_LIMIT')
            db.execute('INSERT OR IGNORE INTO product_attachments VALUES(?,?,?,?,?)', (owner, key, name, digest, time.time()))
        return {'id': key, 'name': name, 'sha256': digest}

    def files(self, owner):
        files = []
        if self.exists(owner):
            for r in self.records(owner):
                if r['kind'] == 'proposal':
                    name = f"proposal-v{r['revision']}.json"
                    if (self.root / owner / name).exists():
                        files.append({'id': name, 'name': name, 'group': '方案', 'revision': r['revision'], 'stale': r['stale']})
            with self.store.connect() as db:
                for r in db.execute('SELECT * FROM product_attachments WHERE owner=?', (owner,)):
                    files.append({'id': r['id'] + '.txt', 'name': r['name'], 'group': '用户资料', 'sha256': r['digest']})
        for job in self.store.jobs(owner):
            if not job.get('result'):
                continue
            for name in job['result'].get('artifacts', []):
                files.append({'id': job['id'] + '/' + name, 'name': name, 'group': '算法与固件' if name == 'policy.py' else '计算与验收', 'job_id': job['id'], 'run_id': job['result']['run_id'], 'status': job['result']['design_status']})
        return files

    def file(self, owner, key):
        item = next((f for f in self.files(owner) if f['id'] == key), None)
        if not item:
            raise PermissionError('PRODUCT_FILE_DENIED')
        if item.get('job_id'):
            job = self.store.get(owner, item['job_id'])
            root = self.store.root / 'runs' / job['result']['run_id']
            p = root / item['name']
        else:
            root = self.root / owner
            p = root / key
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or not p.is_file():
            raise PermissionError('PRODUCT_FILE_DENIED')
        if p.stat().st_size > 500000:
            raise ValueError('PRODUCT_PREVIEW_TOO_LARGE')
        content = p.read_bytes()
        return {**item, 'sha256': hashlib.sha256(content).hexdigest(), 'content': content.decode('utf-8')}

    def projection(self, owner):
        records = self.records(owner) if self.exists(owner) else []
        proposal = self.current(owner) if records else None
        approved = bool(proposal and self.approved(owner, proposal['revision']))
        binding = self.binding(owner) if proposal else None
        with self.store.connect() as db:
            evidence = [dict(r) for r in db.execute('SELECT job_id,revision FROM product_jobs WHERE owner=?', (owner,))]
        for e in evidence:
            job = self.store.get(owner, e['job_id'])
            e.update({'stale': not proposal or e['revision'] != proposal['revision'], 'status': job['status'], 'design_status': (job['result'] or {}).get('design_status'), 'snapshot_id': job['request'].get('snapshot_id')})
        engineering=[{**j,'stale':j['design_revision'] is not None and (not proposal or j['design_revision']!=proposal['revision'])} for j in self.app.engineering.jobs(owner)] if hasattr(self.app,'engineering') else []
        return {'enabled': self.exists(owner), 'records': records, 'proposal': proposal, 'approved': approved, 'binding': binding, 'engineering':engineering,
                'assembly': self.app.assemblies.projection(owner) if hasattr(self.app,'assemblies') and self.exists(owner) else None, 'evidence': evidence, 'capabilities': CAPABILITIES + ([{'id':x['id'],'name':x['id'].title()+' 工程模板','status':'available' if x['installed'] else 'not_connected','scope':x['scope']} for x in self.app.engineering.catalog()['engines']] if hasattr(self.app,'engineering') else []), 'files': self.files(owner), 'hardware_verified': False}

    def context(self, owner):
        self.require(owner)
        with self.store.connect() as db:
            messages = [dict(r) for r in db.execute("SELECT id,text,status FROM chat_messages WHERE conversation=? AND status NOT IN ('WITHDRAWN','RECALLING','CANCELLED') ORDER BY created", (owner,))]
        return {**self.projection(owner), 'messages': messages,
                'attachments': [self.file(owner, f['id']) for f in self.files(owner) if f['group'] == '用户资料']}
