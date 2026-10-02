"""Delivery inventory over existing assembly files/jobs, never a new truth ledger.

Participants bind immutable file/job identities. They cannot submit PASS. Native
execution, numerical validity, literature agreement and hardware remain separate.
"""
import hashlib
import json
from pathlib import Path
import time
import zipfile
import os
import tempfile

from .store import canonical, identity
from .design_review import native_checks, cards
from .product_authority import binding_inputs, profile, PLUCK_ONLY, verdict

ROOT = Path(__file__).resolve().parents[6]
CONTRACT = ROOT / 'configs/reference_cases/engineering-delivery-v1.json'


def contract():
    return json.loads(CONTRACT.read_text())


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def missing_roles(requirements, files):
    """One file cannot satisfy several separately requested artifacts."""
    assigned = {}
    def fit(role, visited):
        for index, meta in enumerate(files):
            if index in visited or not any(meta['name'].lower().endswith(e) for e in requirements[role]['extensions']):
                continue
            visited.add(index)
            if index not in assigned or fit(assigned[index], visited):
                assigned[index] = role
                return True
        return False
    return [role for i, role in enumerate(requirements) if not fit(i, set())]


def dependent_ids(changed, tasks=None):
    tasks = tasks or contract()['tasks']
    affected = set(changed)
    while True:
        new = {t['id'] for t in tasks if set(t['depends_on']) & affected}
        if new <= affected:
            return sorted(affected)
        affected |= new


class Deliverables:
    def __init__(self, app):
        self.app = app
        self.store = app.store
        with self.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS delivery_bindings(
                owner TEXT, operation TEXT, task TEXT, revision INTEGER,
                payload TEXT, created REAL, PRIMARY KEY(owner,operation))''')
            db.execute('''CREATE TABLE IF NOT EXISTS product_stage_contracts(
                owner TEXT, revision INTEGER, payload TEXT, created REAL,
                PRIMARY KEY(owner,revision))''')

    def stage_contract(self, owner):
        with self.store.connect() as db:
            row=db.execute('SELECT payload FROM product_stage_contracts WHERE owner=? ORDER BY revision DESC LIMIT 1',(owner,)).fetchone()
        return json.loads(row['payload']) if row else None

    def configure_stage(self, owner, body):
        """Operator-only HTTP route. Stage changes never edit scientific checks."""
        from .product_authority import STAGES
        self.app.products.require(owner)
        if set(body)-{'session_id'} != {'action','expected_revision','target_stage','max_continuations','reason'}:
            raise ValueError('STAGE_CONTRACT_SCHEMA')
        if body['target_stage'] not in STAGES or type(body['expected_revision']) is not int or type(body['max_continuations']) is not int or not 0<=body['max_continuations']<=12:
            raise ValueError('STAGE_CONTRACT_INVALID')
        if not isinstance(body['reason'],str) or not 1<=len(body['reason'])<=1000:raise ValueError('STAGE_CONTRACT_REASON_REQUIRED')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            last=db.execute('SELECT MAX(revision) FROM product_stage_contracts WHERE owner=?',(owner,)).fetchone()[0] or 0
            if last!=body['expected_revision']:raise ValueError('STAGE_CONTRACT_CONFLICT')
            value=dict(revision=last+1,target_stage=body['target_stage'],max_continuations=body['max_continuations'],reason=body['reason'],source='operator',owner=owner)
            db.execute('INSERT INTO product_stage_contracts VALUES(?,?,?,?)',(owner,last+1,canonical(value),time.time()))
        self.app.conversations.event(owner,'stage-contract-'+identity(value),{'type':'product_stage_contract','contract':value})
        return self.inspect(owner)

    def bind(self, owner, body):
        required = {'action', 'operation_id', 'task_id', 'revision', 'files', 'jobs'}
        if set(body) - {'session_id'} != required:
            raise ValueError('DELIVERY_BINDING_SCHEMA: no participant verdicts accepted')
        from .assembly import ID
        if not isinstance(body['operation_id'], str) or not ID.fullmatch(body['operation_id']):
            raise ValueError('DELIVERY_OPERATION_ID')
        tasks = {t['id']: t for t in contract()['tasks']}
        if body['task_id'] not in tasks:
            raise ValueError('DELIVERY_TASK_UNKNOWN')
        if any(not isinstance(body[k], list) or len(body[k]) > 100 or
               any(not isinstance(x, str) for x in body[k]) for k in ('files', 'jobs')):
            raise ValueError('DELIVERY_REFERENCE_SCHEMA')
        if any(len(body[k]) != len(set(body[k])) for k in ('files', 'jobs')) or type(body['revision']) is not int:
            raise ValueError('DELIVERY_REFERENCE_SCHEMA')
        current = self.app.assemblies.get(owner)
        if body['revision'] != current['revision'] or not current['source_valid']:
            raise ValueError('DELIVERY_REVISION_STALE')
        files = []
        for key in body['files']:
            path, record = self.app.assemblies.file(owner, key)
            if record['revision'] != current['revision']:
                raise ValueError('DELIVERY_FILE_REVISION_STALE')
            files.append({k: record[k] for k in ('id', 'name', 'digest', 'source', 'bytes')})
        jobs = []
        for key in body['jobs']:
            job = self.app.engineering.get(owner, key)
            if job['status'] in ('RUNNING', 'QUEUED'):
                raise ValueError('DELIVERY_JOB_NOT_FINAL')
            for artifact in (job.get('result') or {}).get('artifacts', []):
                self.app.engineering.artifact(owner, key, artifact['name'])
            jobs.append({'id': key, 'status': job['status'], 'engine': job['engine'], 'snapshot_sha256': identity(job)})
        payload = dict(task_id=body['task_id'], revision=current['revision'],
                       physical_hash=current['hashes']['physical_hash'],
                       input_dimensions=binding_inputs(body['task_id'], current),
                       files=files, jobs=jobs, contract_sha256=file_digest(CONTRACT))
        # Snapshot all direct dependency bindings. Future edits are discovered
        # from actual identities, without letting the participant waive them.
        old = self._bindings(owner)
        payload['dependencies'] = {key: identity(old.get(key)) for key in tasks[body['task_id']]['depends_on']}
        with self.store.connect() as db:
            previous = db.execute('SELECT payload FROM delivery_bindings WHERE owner=? AND operation=?',
                                  (owner, body['operation_id'])).fetchone()
            if previous and previous['payload'] != canonical(payload):
                raise ValueError('DELIVERY_OPERATION_CONFLICT')
            db.execute('INSERT OR IGNORE INTO delivery_bindings VALUES(?,?,?,?,?,?)',
                       (owner, body['operation_id'], body['task_id'], current['revision'], canonical(payload), time.time()))
        self.app.conversations.event(owner, 'delivery-binding-' + body['operation_id'],
                                     {'type': 'delivery_binding', **payload})
        return self.inspect(owner)

    def _bindings(self, owner):
        self.app.products.require(owner)
        with self.store.connect() as db:
            rows = db.execute('SELECT payload FROM delivery_bindings WHERE owner=? ORDER BY created,rowid', (owner,)).fetchall()
        return {v['task_id']: v for row in rows for v in [json.loads(row['payload'])]}

    def inspect(self, owner):
        spec = contract()
        bindings = self._bindings(owner)
        try:
            current = self.app.assemblies.get(owner)
        except ValueError as exc:
            if str(exc) != 'ASSEMBLY_NOT_FOUND':
                raise
            current = None
        changed = set()
        for key, value in bindings.items():
            if not current or not current['source_valid'] or (value.get('input_dimensions') != binding_inputs(key, current) if 'input_dimensions' in value else value['physical_hash'] != current['hashes']['physical_hash']) or value['contract_sha256'] != file_digest(CONTRACT):
                changed.add(key)
            if any(identity(bindings.get(dep)) != digest for dep, digest in value['dependencies'].items()):
                changed.add(key)
            for meta in value.get('files', []):
                try:
                    self.app.assemblies.file(owner, meta['id'])
                except (ValueError, PermissionError, OSError):
                    changed.add(key)
            for ref in value.get('jobs', []):
                try:
                    job = self.app.engineering.get(owner, ref['id'])
                    if identity(job) != ref['snapshot_sha256']:
                        changed.add(key)
                    for meta in (job.get('result') or {}).get('artifacts', []):
                        self.app.engineering.artifact(owner, job['id'], meta['name'])
                except (ValueError, PermissionError, OSError):
                    changed.add(key)
        stale = set(dependent_ids(changed, spec['tasks']))
        family, profile_reason = profile(current)
        tasks = []
        for task in spec['tasks']:
            binding = bindings.get(task['id'])
            files = []; errors = []
            for meta in (binding or {}).get('files', []):
                try:
                    self.app.assemblies.file(owner, meta['id'])
                    files.append(meta)
                except (ValueError, PermissionError, OSError) as exc:
                    errors.append(str(exc))
            missing = missing_roles(task['files'], files)
            # Generic documentation is an inventory entry, never a semantic PASS.
            status = 'missing' if not files else 'partial' if missing else 'present'
            if task['id'] in stale:
                status = 'stale'
            if errors:
                status = 'invalid'
            executions = []
            for ref in (binding or {}).get('jobs', []):
                try:
                    job = self.app.engineering.get(owner, ref['id'])
                    for a in (job.get('result') or {}).get('artifacts', []):
                        self.app.engineering.artifact(owner, job['id'], a['name'])
                    executions.append({'id': job['id'], 'engine': job['engine'], 'status': job['status'],
                        'current_assembly': (job.get('assembly') or {}).get('hashes', {}).get('physical_hash') == (current or {}).get('hashes', {}).get('physical_hash')})
                except (ValueError, PermissionError, OSError) as exc:
                    errors.append(str(exc))
            if errors:
                status = 'invalid'
            tasks.append({**task, 'checks': native_checks(self.app,owner,task['id'],binding,current), 'applicability': 'not_applicable' if family == 'solar' and task['id'] in PLUCK_ONLY else 'required', 'binding': binding, 'delivery_status': status,
                          'validation_status': 'stale' if status == 'stale' else 'failed' if errors else 'not_run',
                          'validation_reason': 'Requires scope-specific independent acceptance; file presence and successful tool execution do not certify this task.',
                          'missing_files': missing, 'integrity_errors': errors, 'executions': executions})
        result = {'schema_version': 'bf-engineering-delivery-snapshot-v1', 'owner': owner,
                'revision': current['revision'] if current else None, 'contract': spec,
                'profile': family, 'profile_reason': profile_reason, 'tasks': tasks, 'changed_tasks': sorted(changed), 'stale_tasks': sorted(stale),
                'complete': False, 'hardware_verified': False,
                'scope': 'Source-bound inventory and freshness; no self-certification or reference answers.'}
        result['research_cards'] = cards(result, current)
        result['verdict'] = verdict(self.app, owner, result)
        result['complete'] = result['verdict']['full_engineering_passed']
        return result

    def package(self, owner, expected_snapshot=None, revision=None):
        snapshot = self.inspect(owner)
        if snapshot['revision'] is None:
            raise ValueError('DELIVERY_ASSEMBLY_REQUIRED')
        catalog = self.app.results.inspect(owner, revision)
        if expected_snapshot and expected_snapshot != catalog['snapshot_sha256']:
            raise ValueError('RESULTS_CHANGED_REFRESH_BEFORE_EXPORT')
        if any(not f['integrity'] for f in catalog['files']):
            raise ValueError('RESULTS_CONTAIN_INVALID_FILES')
        key = identity({'delivery':snapshot,'results':catalog})[:24]
        root = self.store.root / 'product-assemblies' / owner / 'delivery-packages'
        root.mkdir(parents=True, exist_ok=True)
        dest = root / (key + '.zip')
        if not dest.exists():
            fd, temporary = tempfile.mkstemp(dir=root, suffix='.zip.partial')
            os.close(fd)
            try:
                with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.writestr('版本清单与验收报告/验收.json', canonical(snapshot))
                    z.writestr('版本清单与验收报告/交付标准.json', canonical(snapshot['contract']))
                    for folder in snapshot['contract']['directories']:
                        z.writestr(folder + '/', '')
                    z.writestr('成果清单.json', canonical(catalog))
                    for ref in catalog['files']:
                        path, name = self.app.results.file(owner,ref['id'])
                        z.write(path, ref['archive_path'])
                    if self.app.results.inspect(owner,revision)['snapshot_sha256'] != catalog['snapshot_sha256']:
                        raise ValueError('RESULTS_CHANGED_DURING_PACKAGE')
                if canonical(self.inspect(owner)) != canonical(snapshot):
                    raise ValueError('DELIVERY_CHANGED_DURING_PACKAGE')
                os.replace(temporary, dest)
            finally:
                Path(temporary).unlink(missing_ok=True)
        with zipfile.ZipFile(dest) as z:
            if z.testzip() or z.read('版本清单与验收报告/验收.json').decode() != canonical(snapshot) or z.read('成果清单.json').decode() != canonical(catalog):
                raise ValueError('DELIVERY_ZIP_CORRUPT')
            expected={f['archive_path'] for f in catalog['files']}
            if {n for n in z.namelist() if n.startswith('成果/')} != expected:
                raise ValueError('DELIVERY_ZIP_INVENTORY_MISMATCH')
            for f in catalog['files']:
                h=hashlib.sha256()
                with z.open(f['archive_path']) as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
                if h.hexdigest()!=f['sha256']:raise ValueError('DELIVERY_ZIP_HASH_MISMATCH')
        # Use the existing publication/download/Trace path for the archive.
        import shutil
        relative = 'delivery-packages/' + dest.name
        workspace = self.store.root.parent / 'participants' / owner
        target = workspace / relative
        if workspace.is_symlink() or target.is_symlink() or not target.resolve().is_relative_to(workspace.resolve()):
            raise PermissionError('DELIVERY_PACKAGE_PATH_DENIED')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and file_digest(target) != file_digest(dest):
            raise ValueError('DELIVERY_PACKAGE_CONFLICT')
        try:
            with target.open('xb') as output, dest.open('rb') as source:
                shutil.copyfileobj(source, output)
        except FileExistsError:
            if target.is_symlink() or file_digest(target) != file_digest(dest):
                raise ValueError('DELIVERY_PACKAGE_CONFLICT')
        result = self.app.assemblies.register(owner, {'revision': snapshot['revision'], 'path': relative, 'kind': 'document'})
        return {**result, 'complete': snapshot['complete'], 'verdict': snapshot['verdict'], 'scope': snapshot['scope'], 'tasks': len(snapshot['tasks'])}
