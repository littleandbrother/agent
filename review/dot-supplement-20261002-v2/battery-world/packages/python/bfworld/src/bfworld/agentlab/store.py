"""Persistent operator/participant identity and serial experiment jobs."""
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def identity(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'workbench.sqlite'
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS principals(token_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, role TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, operation TEXT NOT NULL,
              request_hash TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL,
              updated REAL NOT NULL, result TEXT, error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
              UNIQUE(owner,operation));
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL,
              job_id TEXT NOT NULL, time REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS grants(owner TEXT PRIMARY KEY, task_ids TEXT NOT NULL, max_jobs INTEGER NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS uploads(owner TEXT NOT NULL, snapshot_id TEXT NOT NULL, PRIMARY KEY(owner,snapshot_id));
            CREATE TABLE IF NOT EXISTS submissions(owner TEXT PRIMARY KEY, job_id TEXT NOT NULL, run_id TEXT NOT NULL, snapshot_id TEXT NOT NULL, created REAL NOT NULL);
            ''')
        self.db.chmod(0o600)
        token_file = self.root / 'operator.token'
        if not token_file.exists():
            token_file.write_text(self.issue('operator', 'operator'))
            token_file.chmod(0o600)
        self.grant('operator', ['rotary-reference']+[f'dev-{i:02}' for i in range(1,9)], 200, time.time()+86400)

    def grant(self, owner, task_ids, max_jobs, expires):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO grants VALUES (?,?,?,?)',(owner,canonical(task_ids),max_jobs,expires))

    def upload(self, owner, snapshot_id):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO uploads VALUES (?,?)',(owner,snapshot_id))

    def authorize(self, owner, request):
        with self.connect() as db:
            grant=db.execute('SELECT * FROM grants WHERE owner=?',(owner,)).fetchone()
            if not grant or time.time()>grant['expires'] or request['task_id'] not in json.loads(grant['task_ids']):
                raise PermissionError('TASK_GRANT_DENIED_OR_EXPIRED')
            if request.get('snapshot_id') and not db.execute('SELECT 1 FROM uploads WHERE owner=? AND snapshot_id=?',(owner,request['snapshot_id'])).fetchone():
                raise PermissionError('SNAPSHOT_NOT_OWNED')
        return dict(grant)

    def connect(self):
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        return db

    def issue(self, owner, role='participant'):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO principals VALUES (?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), owner, role))
        return token

    def authenticate(self, token):
        with self.connect() as db:
            row = db.execute('SELECT owner,role FROM principals WHERE token_hash=?',
                             (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:
            raise PermissionError('AUTH_REQUIRED')
        return dict(row)

    def event(self, owner, job, kind, data):
        with self.connect() as db:
            db.execute('INSERT INTO events(owner,job_id,time,kind,data) VALUES (?,?,?,?,?)',
                       (owner, job, time.time(), kind, canonical(data)))

    def enqueue(self, owner, operation, request):
        if not isinstance(operation, str) or not 1 <= len(operation) <= 100:
            raise ValueError('OPERATION_ID_REQUIRED')
        digest = identity(request)
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE owner=? AND operation=?', (owner, operation)).fetchone()
            if row:
                if row['request_hash'] != digest:
                    raise ValueError('OPERATION_CONFLICT')
                return self.project(row)
            grant=self.authorize(owner,request)
            count = db.execute('SELECT COUNT(*) FROM jobs WHERE owner=?', (owner,)).fetchone()[0]
            if count >= grant['max_jobs']:
                raise ValueError('EXPERIMENT_BUDGET_EXHAUSTED')
            job = 'job-' + secrets.token_hex(8)
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (job, owner, operation, digest, canonical(request), 'QUEUED', now, now, None, None, 0))
        self.event(owner, job, 'queued', {'task_id': request['task_id'], 'request_hash': digest})
        return self.get(owner, job)

    @staticmethod
    def project(row):
        value = dict(row)
        for key in ['request', 'result']:
            if value[key] is not None:
                value[key] = json.loads(value[key])
        return value

    def get(self, owner, job):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (job, owner)).fetchone()
        if not row:
            raise PermissionError('JOB_NOT_FOUND')
        return self.project(row)

    def jobs(self, owner):
        with self.connect() as db:
            return [self.project(r) for r in db.execute('SELECT * FROM jobs WHERE owner=? ORDER BY created DESC', (owner,))]

    def events(self, owner, job):
        self.get(owner, job)
        with self.connect() as db:
            return [{**dict(r), 'data': json.loads(r['data'])} for r in
                    db.execute('SELECT * FROM events WHERE owner=? AND job_id=? ORDER BY seq', (owner, job))]

    def update(self, owner, job, status, result=None, error=None):
        self.get(owner, job)
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?,updated=?,result=?,error=? WHERE id=? AND owner=?',
                       (status, time.time(), canonical(result) if result is not None else None, error, job, owner))

    def cancel(self, owner, job):
        value=self.get(owner, job)
        if value['status'] not in ('QUEUED','RUNNING','UNKNOWN'):
            return {'job_id':job,'cancellation_requested':False,'terminal_confirmed':True,'status':value['status']}
        with self.connect() as db:
            db.execute('UPDATE jobs SET cancel_requested=1 WHERE owner=? AND id=?', (owner, job))
        self.event(owner, job, 'cancel_requested', {})
        return {'job_id': job, 'cancellation_requested': True, 'terminal_confirmed': False}

    def submit(self,owner,job_id,snapshot_id):
        job=self.get(owner,job_id)
        if job['status']!='SUCCEEDED' or job['result']['snapshot_id']!=snapshot_id:
            raise ValueError('SUBMISSION_REQUIRES_COMPLETED_MATCHING_RUN')
        result=job['result']
        with self.connect() as db:
            old=db.execute('SELECT * FROM submissions WHERE owner=?',(owner,)).fetchone()
            if old and (old['job_id']!=job_id or old['snapshot_id']!=snapshot_id):
                raise ValueError('SUBMISSION_ALREADY_SEALED')
            db.execute('INSERT OR IGNORE INTO submissions VALUES (?,?,?,?,?)',(owner,job_id,result['run_id'],snapshot_id,time.time()))
        self.event(owner,job_id,'submitted',{'run_id':result['run_id'],'snapshot_id':snapshot_id,'design_status':result['design_status']})
        return {'run_id':result['run_id'],'snapshot_id':snapshot_id,'design_status':result['design_status'],'sealed':True}

    def reconcile(self):
        with self.connect() as db:
            rows = list(db.execute("SELECT id,owner FROM jobs WHERE status='RUNNING'"))
        for row in rows:
            self.update(row['owner'], row['id'], 'UNKNOWN', error='Worker interrupted; no automatic re-dispatch.')
            self.event(row['owner'], row['id'], 'reconciliation_required', {'status': 'UNKNOWN'})
