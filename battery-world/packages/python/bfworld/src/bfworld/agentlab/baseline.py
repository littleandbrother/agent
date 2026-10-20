"""Operator baseline snapshots. Production is opened read-only, never as a Workbench."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON')
    return db


def logical_state(path):
    """Small authoritative tables; full context/history is retained in the DB backup."""
    names = ['conversations', 'model_requests', 'model_limits', 'owner_model_caps',
             'interactive_leases', 'research_usage_continuations', 'research_usage_carryforwards',
             'engineering_jobs', 'eda_cli_jobs', 'eda_cli_bindings', 'eda_cli_binding_revisions',
             'design_tasks', 'design_snapshots', 'design_operations', 'design_events',
             'design_adoptions', 'design_task_history', 'assembly_revisions', 'delivery_bindings',
             'product_jobs', 'product_records', 'product_result_index', 'settings', 'grants']
    result = {}
    with readonly(path) as db:
        db.execute('BEGIN')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in names:
            if name not in tables:
                continue
            h, count = hashlib.sha256(), 0
            for row in db.execute('SELECT * FROM "' + name + '" ORDER BY rowid'):
                h.update(canonical(list(row)).encode() + b'\n')
                count += 1
            result[name] = {'rows': count, 'sha256': h.hexdigest()}
    return result


def database_summary(path, owners):
    with readonly(path) as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {'integrity': db.execute('PRAGMA quick_check').fetchone()[0]}
        if 'model_requests' in names:
            result['model_statuses'] = dict(db.execute('SELECT status,count(*) FROM model_requests GROUP BY status'))
            result['unknown'] = [dict(zip(['id', 'owner', 'reserved', 'charged', 'status'], row)) for row in
                db.execute("SELECT id,owner,reserved,charged,status FROM model_requests WHERE status='UNKNOWN' ORDER BY id")]
            result['owners'] = {o: dict(zip(['requests', 'reserved_usd', 'charged_usd'], db.execute(
                'SELECT count(*),coalesce(sum(reserved),0),coalesce(sum(charged),0) FROM model_requests WHERE owner=?', (o,)).fetchone())) for o in owners}
        if 'conversations' in names:
            result['conversations'] = [dict(zip(['id', 'status', 'error'], row)) for row in db.execute(
                'SELECT id,status,error FROM conversations WHERE id IN (' + ','.join('?' for _ in owners) + ') ORDER BY id', owners)]
        return result


def quiescent(path):
    with readonly(path) as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, statuses in [('conversations', ['STARTING', 'RUNNING']),
                                ('jobs', ['QUEUED', 'RUNNING']),
                                ('model_requests', ['RESERVED', 'DISPATCHED']),
                                ('engineering_jobs', ['QUEUED', 'RUNNING']),
                                ('eda_cli_jobs', ['RUNNING']),
                                ('design_operations', ['RUNNING', 'WAITING_NATIVE'])]:
            if table in names and db.execute('SELECT count(*) FROM ' + table + ' WHERE status IN (' +
                    ','.join('?' for _ in statuses) + ')', statuses).fetchone()[0]:
                raise ValueError('BASELINE_ACTIVE_WRITER:' + table)


def freeze(source, runtime, campaign, native_project, target, tag):
    source, runtime, campaign, native_project, target = map(lambda p: Path(p).resolve(),
        [source, runtime, campaign, native_project, target])
    if target.exists():
        raise ValueError('BASELINE_ALREADY_EXISTS')
    commit = subprocess.check_output(['git', 'rev-parse', tag + '^{commit}'], cwd=source, text=True).strip()
    if commit != subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip():
        raise ValueError('BASELINE_SOURCE_REF_MISMATCH')
    index = json.loads((campaign/'campaign/parallel-20261009/pi-session-index.json').read_text())
    owners = [s['owner'] for s in index['sessions']]
    owner = next(s['owner'] for s in index['sessions'] if s['paper_id'] == 'P01')
    dbs = {'papers': campaign/'runtime/state/workbench.sqlite',
           'demo': runtime/'workbench/state/workbench.sqlite'}
    target.mkdir(parents=True, mode=0o700)
    entries, exclusions, origins = {}, [], {}

    def copy_file(src, relative, expected=None):
        src = Path(src)
        if src.is_symlink() or not src.is_file():
            raise ValueError('BASELINE_FILE_INVALID:' + str(src))
        before = digest(src)
        if expected and expected != before:
            raise ValueError('BASELINE_INPUT_DRIFT:' + str(src))
        out = target/relative
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        if digest(out) != before or digest(src) != before:
            raise ValueError('BASELINE_COPY_DRIFT:' + str(src))
        entries[relative] = {'sha256': before, 'bytes': out.stat().st_size, 'origin': str(src)}
        origins[str(src)] = before

    def copy_tree(src, relative, excluded=()):
        src = Path(src)
        if not src.is_dir():
            raise ValueError('BASELINE_TREE_MISSING:' + str(src))
        for directory, dirs, files in os.walk(src, followlinks=False):
            base = Path(directory)
            for name in list(dirs):
                p = base/name
                if name in excluded or p.is_symlink():
                    exclusions.append({'path': str(p), 'reason': 'generated probe/cache' if name in excluded else 'external symlink',
                                       'target': os.readlink(p) if p.is_symlink() else None})
                    dirs.remove(name)
            for name in sorted(files):
                p = base/name
                if p.is_symlink():
                    exclusions.append({'path': str(p), 'reason': 'external symlink', 'target': os.readlink(p)})
                else:
                    copy_file(p, str(Path(relative)/p.relative_to(src)))

    with (runtime/'design-native.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = {}
        for name, path in dbs.items():
            quiescent(path)
            before[name] = logical_state(path)
            out = target/'private/databases'/f'{name}.sqlite'
            out.parent.mkdir(parents=True, exist_ok=True)
            with readonly(path) as inp, sqlite3.connect(out) as dest:
                inp.backup(dest, pages=4096)
            entries[str(out.relative_to(target))] = {'sha256': digest(out), 'bytes': out.stat().st_size,
                                                    'origin': str(path), 'method': 'SQLite online backup from mode=ro'}
            if logical_state(out) != before[name]:
                raise ValueError('BASELINE_DATABASE_CHANGED:' + name)
        with readonly(dbs['papers']) as db:
            row = db.execute('SELECT current_design,submission FROM design_tasks WHERE owner=?', (owner,)).fetchone()
            adopted, submission = row[0], json.loads(row[1])
            snapshot = json.loads(db.execute('SELECT value FROM design_snapshots WHERE owner=? AND design_id=?',
                                            (owner, submission['design_id'])).fetchone()[0])
        workspace = campaign/'runtime/participants'/owner
        for name, descriptor in snapshot['files'].items():
            if digest(workspace/name) != descriptor['sha256']:
                raise ValueError('BASELINE_CANDIDATE_SOURCE_CHANGED:' + name)
        copy_tree(workspace, 'p01/participant', excluded=('.local-probe', '__pycache__'))
        copy_tree(native_project, 'p01/native-project')
        for name in ['design-lab', 'design-previews', 'sessions']:
            copy_tree(campaign/'runtime'/name/owner, 'private/'+name+'/'+owner)
        for job in snapshot['selected_jobs']:
            copy_tree(campaign/'runtime/engineering'/job, 'p01/jobs/'+job)
        for s in index['sessions']:
            if s['owner'] != owner:
                copy_tree(campaign/'runtime/sessions'/s['owner'], 'private/sessions/'+s['owner'])
        for relative in ['CHECKPOINT.md', 'analysis.json', 'campaign/parallel-20261009/pi-session-index.json',
                         'campaign/acceptance/current.json']:
            copy_file(campaign/relative, 'campaign/'+relative)
        acceptance_index = json.loads((campaign/'campaign/acceptance/current.json').read_text())
        copy_file(campaign/acceptance_index['path'], 'campaign/'+acceptance_index['path'], acceptance_index['sha256'])
        for gate in submission['acceptance']['functional_gates']:
            ref = gate['evidence']; copy_file(campaign/ref['path'], 'campaign/'+ref['path'], ref['sha256'])
        configuration = json.loads((runtime/'runtime.json').read_text())
        copy_file(runtime/'runtime.json', 'operator/runtime.json')
        connector = configuration['eda']['connector_package']
        copy_file(connector['path'], 'environment/'+Path(connector['path']).name, connector['sha256'])
        for relative in subprocess.check_output(['git', 'diff', '--name-only', '-z'], cwd=source).decode().split('\0'):
            if relative:
                copy_file(source/relative, 'operator/preexisting-changes/'+relative)
        patch = subprocess.check_output(['git', 'diff', '--binary'], cwd=source)
        (target/'operator/preexisting.patch').write_bytes(patch)
        status = subprocess.check_output(['git', 'status', '--porcelain=v1'], cwd=source)
        (target/'operator/preexisting-git-status.txt').write_bytes(status)
        subprocess.run(['git', 'bundle', 'create', str(target/'source.bundle'), 'refs/tags/'+tag], cwd=source, check=True, capture_output=True)
        subprocess.run(['git', 'archive', '--format=tar', '--output='+str(target/'source.tar'), commit], cwd=source, check=True)
        after = {name: logical_state(path) for name, path in dbs.items()}
        if after != before:
            raise ValueError('BASELINE_PRODUCTION_STATE_CHANGED')
        for path, h in origins.items():
            if digest(path) != h:
                raise ValueError('BASELINE_ORIGIN_CHANGED:' + path)
        for file in target.rglob('*'):
            if file.is_file() and str(file.relative_to(target)) not in entries:
                entries[str(file.relative_to(target))] = {'sha256': digest(file), 'bytes': file.stat().st_size}
        value = {'schema_version': 'bf-baseline-manifest-v1', 'id': tag, 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'source': {'commit': commit, 'tag': tag, 'worktree': str(source)},
                 'production': {'runtime': str(runtime), 'campaign': str(campaign), 'native_project': str(native_project),
                                'demo_port': 8768, 'database_paths': {k: str(v) for k, v in dbs.items()}},
                 'p01': {'owner': owner, 'task_id': snapshot['task_id'], 'adopted_design': adopted,
                         'submitted_design': snapshot['design_id'], 'submission_id': submission['submission_id'],
                         'selected_jobs': snapshot['selected_jobs'], 'native_project_uuid': snapshot['eda_project'],
                         'gates': submission['acceptance']['functional_gates'], 'digital_status': submission['acceptance']['digital_engineering_status'],
                         'physical': 'NOT_TESTED'},
                 'original_owners': owners, 'database_fingerprints': before,
                 'databases': {name: database_summary(target/'private/databases'/f'{name}.sqlite', owners) for name in dbs},
                 'files': entries, 'exclusions': exclusions, 'new_model_requests': 0, 'new_solver_jobs': 0,
                 'visibility': 'operator-only; V2 participants receive only selected public inputs'}
        (target/'manifest.json').write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        for path in target.rglob('*'):
            if path.is_file():
                path.chmod(0o400)
        for path in sorted((p for p in target.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            path.chmod(0o500)
        target.chmod(0o500)
    return {'path': str(target), 'manifest_sha256': digest(target/'manifest.json'), 'files': len(entries),
            'bytes': sum(f['bytes'] for f in entries.values()), 'original_owners': len(owners)}


def verify(target, origins=False):
    target = Path(target).resolve()
    value = json.loads((target/'manifest.json').read_text())
    if value.get('schema_version') != 'bf-baseline-manifest-v1':
        raise ValueError('BASELINE_SCHEMA_INVALID')
    for name, ref in value['files'].items():
        p = target/name
        if not p.resolve().is_relative_to(target) or p.is_symlink() or digest(p) != ref['sha256']:
            raise ValueError('BASELINE_FILE_CHANGED:' + name)
        if origins and ref.get('origin') and ref.get('method') is None and digest(ref['origin']) != ref['sha256']:
            raise ValueError('BASELINE_ORIGIN_CHANGED:' + name)
    for name, fingerprint in value['database_fingerprints'].items():
        db = target/'private/databases'/f'{name}.sqlite'
        if logical_state(db) != fingerprint:
            raise ValueError('BASELINE_DATABASE_CHANGED:' + name)
        if origins and logical_state(value['production']['database_paths'][name]) != fingerprint:
            raise ValueError('PRODUCTION_DATABASE_CHANGED:' + name)
    return {'status': 'PASS', 'files': len(value['files']), 'bytes': sum(f['bytes'] for f in value['files'].values()),
            'manifest_sha256': digest(target/'manifest.json'), 'production_checked': origins}
