"""Task-contract actions on the existing Repository journal and System Commits."""
import json
from pathlib import Path
import tempfile

from ..store import canonical, identity
from .repository import MODE, file_hash, name
from .repository_profiles import definition, profile, schema, system_definition, REPORTS, runtime_spec
from .repository_contracts import reuse_gates
from .repository_task_standards import check_files, transition


def file_inputs(repo, db, values):
    if not isinstance(values, dict) or len(values) > 100: raise ValueError('TASK_FILES_LIMIT')
    result = {}
    with tempfile.TemporaryDirectory(prefix='bf-task-input-') as folder:
        for logical, content in values.items():
            name(logical)
            if not isinstance(content, str) or len(content.encode()) > 500000: raise ValueError('TASK_TEXT_FILE_LIMIT')
            path = Path(folder)/logical
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
            result[logical] = repo.asset(db, path)
    return result


def create(repo, owner, body, operator):
    if not operator: raise PermissionError('OPERATOR_REQUIRED')
    if not repo.profile: raise PermissionError('ISOLATED_V2_PROFILE_REQUIRED')
    if owner in repo.profile.get('protected_owners', []): raise PermissionError('ORIGINAL_OWNER_PROTECTED')
    contract = definition(body['definition'])
    def apply(db):
        if not db.execute('SELECT 1 FROM conversations WHERE id=?', (owner,)).fetchone():
            raise ValueError('DESIGN_REQUIRES_EXISTING_PI_CONVERSATION')
        if db.execute('SELECT 1 FROM design_projects WHERE owner=?', (owner,)).fetchone():
            raise ValueError('DESIGN_PROJECT_ALREADY_EXISTS')
        files = {}; origin = None; jobs = {}; validations = {}
        if body.get('source_system'):
            source = repo.system(body['source_project'], body['source_system'], db)
            files.update(source['files'])
            origin = {'project_id': source['project_id'], 'system_id': source['id']}
            jobs = source['jobs']
            validations = source['validations']
        files.update(file_inputs(repo, db, body.get('files', {})))
        if not files: raise ValueError('TASK_INITIAL_FILES_REQUIRED')
        check_files(contract, files, lambda path: (repo.root/'blobs'/files[path]['sha256']).read_text())
        pid = 'PR-' + identity({'owner': owner, 'operation': body['operation_id']})
        system = repo._save_system(db, owner, {'schema_version': 'bf-system-commit-v2', 'project_id': pid,
            'parent': None, 'origin_design_id': None, 'origin_owner': owner, 'baseline': repo.profile['baseline'],
            'task_definition': contract, 'domain_commits': {}, 'contracts': {}, 'files': files,
            'jobs': jobs, 'validations': validations, 'physical': 'NOT_TESTED', 'digital_status': 'NOT_CHECKED',
            'provenance': 'operator-approved task and initial assets', 'inherited_from': origin,
            'design_changes': [], 'history_fabricated': False})
        db.execute('INSERT INTO design_projects VALUES(?,?,?,?,?,?,?,?)',
            (pid, owner, body.get('title') or contract['goal'][:120], 1, system['id'], system['id'],
             canonical(repo.profile['baseline']), canonical(contract)))
        db.execute('INSERT INTO design_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (owner, 'task-'+pid, canonical({'task_id': 'task-'+pid, **contract}),
             canonical({'mode': MODE, 'environment_id': repo.profile['id'], 'project_id': pid}),
             system['id'], 1, canonical({'kind': 'CONTINUE'}), '[]', 'IDLE', 0, '{}'))
        return {'id': system['id'], 'system_id': system['id'], 'project_id': pid, 'task_definition': contract,
                'revision': 1, 'native_jobs_dispatched': 0}
    return repo.mutate(owner, body, apply)


def revise_definition(repo, owner, body, operator):
    if not operator: raise PermissionError('TASK_REQUIREMENTS_OPERATOR_ONLY')
    if any(thread.is_alive() for thread in repo.lab.controllers.values()): raise ValueError('TASK_REVISION_REQUIRES_IDLE_CONTROLLERS')
    contract = definition(body['definition'])
    def apply(db):
        p = repo.leader(body['project_id'], owner, db)
        if p['revision'] != body['expected_revision']: raise ValueError('PROJECT_REVISION_CONFLICT')
        parent = repo.system(p['id'], p['submitted'], db)
        phase_change = transition(parent.get('task_definition', {}), contract, body.get('rationale'))
        files = {**parent['files'], **file_inputs(repo, db, body.get('files', {}))}
        check_files(contract, files, lambda path: (repo.root/'blobs'/files[path]['sha256']).read_text())
        child = {k: v for k, v in parent.items() if k not in ('id', 'validations')}
        changes = [{'path': k, 'before': parent['files'].get(k, {}).get('sha256'), 'after': v['sha256']}
                   for k, v in files.items() if parent['files'].get(k) != v]
        if parent.get('task_definition', {}).get('id') == contract['id'] and not changes: raise ValueError('TASK_DEFINITION_UNCHANGED')
        child.update(parent=parent['id'], task_definition=contract, design_changes=changes,
                     files=files, task_transition=phase_change,
                     provenance='operator-approved task phase revision')
        child['validations'] = reuse_gates(parent, child)
        child = repo._save_system(db, owner, child)
        db.execute('UPDATE design_projects SET requirements=?,submitted=?,revision=revision+1 WHERE id=?',
            (canonical(contract), child['id'], p['id']))
        db.execute('UPDATE design_tasks SET contract=? WHERE owner=?', (canonical({'task_id': 'task-'+p['id'], **contract}), owner))
        return {'id': child['id'], 'project_id': p['id'], 'revision': p['revision']+1,
                'task_definition': contract, 'native_jobs_dispatched': 0}
    return repo.mutate(owner, body, apply)


def commit(repo, owner, body, operator):
    """Single-Agent task revisions use the same immutable System Commit and journal."""
    def apply(db):
        p = repo.leader(body['project_id'], owner, db)
        if p['revision'] != body['expected_revision']: raise ValueError('PROJECT_REVISION_CONFLICT')
        if body['base_system'] != p['submitted']: raise ValueError('TASK_BASE_CONFLICT')
        parent = repo.system(p['id'], body['base_system'], db)
        contract = system_definition(repo, parent, db)
        if not contract: raise ValueError('EXPLICIT_TASK_DEFINITION_REQUIRED')
        if contract['intent'] == 'audit': raise PermissionError('AUDIT_TASK_READ_ONLY_DESIGN')
        cfg = profile(contract['profile'])
        allowed = {'tabulated-curve-v1': ('observation.csv', 'notes/'),
                   'piezo-reference-v1': ('design.json', 'firmware/main.c', 'notes/')}.get(cfg['adapter'])
        if allowed is None: raise ValueError('PROFESSIONAL_COMMIT_PATH_REQUIRED')
        if not isinstance(body.get('rationale'), str) or not body['rationale'].strip(): raise ValueError('DECISION_REASON_REQUIRED')
        if not body.get('files'): raise ValueError('TASK_COMMIT_FILES_REQUIRED')
        for path in body['files']:
            if not any(path.startswith(a) if a.endswith('/') else path == a for a in allowed):
                raise PermissionError('TASK_DESIGN_SCOPE')
        files = {**parent['files'], **file_inputs(repo, db, body['files'])}
        previous = json.loads((repo.root/'blobs'/parent['files']['design.json']['sha256']).read_text()) if cfg['adapter'] == 'piezo-reference-v1' else None
        check_files(contract, files, lambda path: (repo.root/'blobs'/files[path]['sha256']).read_text(), previous, body['files'])
        changes = [{'path': k, 'before': parent['files'].get(k, {}).get('sha256'), 'after': v['sha256']}
                   for k, v in files.items() if parent['files'].get(k) != v]
        if not changes: raise ValueError('TASK_COMMIT_UNCHANGED')
        child = {k: v for k, v in parent.items() if k not in ('id', 'validations')}
        child.update(parent=parent['id'], files=files, design_changes=changes,
                     rationale=body['rationale'], source_author='operator' if operator else 'Pi')
        child['validations'] = reuse_gates(parent, child)
        child = repo._save_system(db, owner, child)
        db.execute('UPDATE design_projects SET submitted=?,revision=revision+1 WHERE id=?', (child['id'], p['id']))
        return {'id': child['id'], 'project_id': p['id'], 'revision': p['revision']+1, 'changes': changes}
    return repo.mutate(owner, body, apply)


def handle(repo, owner, body, operator=False):
    action = body['action']
    if action == 'repository_task_schema':
        project = repo.bound(owner)
        if project:
            p=repo.project(project,owner); s=repo.system(project,p['submitted']); task=system_definition(repo,s)
            if task: return runtime_spec(task)
        return schema()
    if action == 'repository_task_create': return create(repo, owner, body, operator)
    if action == 'repository_task_define': return revise_definition(repo, owner, body, operator)
    if action == 'repository_task_commit': return commit(repo, owner, body, operator)
    if action == 'repository_task_definition':
        p = repo.project(body['project_id'], owner)
        s = repo.system(p['id'], body.get('system_id') or p['submitted'])
        d = system_definition(repo, s)
        cfg = profile(d['profile'] if d else 'p01-digital-v1')
        return {'system_id': s['id'], 'definition': d, 'profile': cfg, 'report_sections': REPORTS[cfg['report']]}
    if action == 'repository_task_state':
        from .repository_task_state import state
        return state(repo, owner, body)
    if action == 'repository_task_execute':
        from .repository_task_execution import execute
        return execute(repo, owner, body, operator)
    if action == 'repository_task_result':
        from .repository_task_result import read
        return read(repo, owner, body)
    if action == 'repository_task_report':
        from .repository_task_reports import prepare
        return prepare(repo, owner, body, operator)
    return None
