"""Typed collaboration and integration actions in the existing DesignLab journal."""
import json
from pathlib import Path
import time
import zipfile

from ..store import canonical, identity
from .contracts import sealed
from .repository_contracts import PREFIXES, domain_of, reuse_gates, check, VERSION, declaration_spec, declaration_examples


def object_save(repo, db, table, prefix, value, columns):
    value = {**value, 'id': prefix + '-' + identity(value)}
    db.execute('INSERT OR IGNORE INTO ' + table + ' VALUES(' + ','.join('?' for _ in range(len(columns)+2)) + ')',
               (value['id'], *(value[k] for k in columns), canonical(value)))
    sealed(repo.root/'objects'/value['id']/ 'record.json', value)
    return value


def scope(domain, path):
    return any(path.startswith(p) for p in PREFIXES[domain])


def task(repo, owner, db=None):
    if db is None:
        with repo.store.connect() as connection: return task(repo, owner, connection)
    row = db.execute('SELECT * FROM design_professional_tasks WHERE owner=?', (owner,)).fetchone()
    if not row: raise PermissionError('PROFESSIONAL_TASK_REQUIRED')
    return {**json.loads(row['value']), 'status': row['status']}


def workspace(repo, owner):
    value = task(repo, owner)
    path = repo.root/'workspaces'/value['id']
    if path.is_symlink(): raise PermissionError('WORKSPACE_SYMLINK')
    path.mkdir(parents=True, exist_ok=True)
    return path, value


def materialize(repo, value):
    base = repo.system(value['project_id'], value['base_system'])
    root = repo.root/'workspaces'/value['id']
    root.mkdir(parents=True, exist_ok=True)
    for name, ref in base['files'].items():
        dest = root/name
        if dest.exists(): continue  # Never overwrite an interrupted specialist's work.
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = repo.root/'blobs'/ref['sha256']
        from .repository import file_hash
        if file_hash(src) != ref['sha256']: raise ValueError('WORKSPACE_INPUT_TAMPER')
        dest.write_bytes(src.read_bytes())
        dest.chmod(0o600 if scope(value['role'], name) else 0o400)
    sealed(root/'task-history'/(identity(value)+'.json'),value)
    pointer=root/'CURRENT-TASK.json'
    if pointer.exists():pointer.chmod(0o600)
    pointer.write_text(canonical(value));pointer.chmod(0o400)
    return root


def assign(repo, owner, body, operator):
    p = repo.leader(body['project_id'], owner)
    domain = body['role']
    if domain not in ('power', 'firmware'): raise ValueError('PROFESSIONAL_ROLE_NOT_QUALIFIED')
    repo.system(p['id'], body['base_system'])
    for key in ('question', 'completion'):
        if not isinstance(body.get(key), str) or not 1 <= len(body[key]) <= 4000: raise ValueError('TASK_' + key.upper() + '_REQUIRED')
    contract_ids = body.get('contract_ids', [])
    with repo.store.connect() as db:
        for cid in contract_ids: repo._object(db, 'design_interface_contracts', cid, p['id'])
    # Create a real deferred Pi conversation before the repository transaction.
    # A retry uses the same creation identity; no generic chat worker is dispatched.
    conversation = repo.lab.app.conversations.create('P01 V2 · ' + domain + '\n' + body['question'],
        None, 'repo-task-' + identity({'lead': owner, 'operation': body['operation_id']}), defer_dispatch=True)
    professional = conversation['id']
    def apply(db):
        repo.leader(p['id'], owner, db)
        value = {'project_id': p['id'], 'owner': professional, 'lead': owner, 'role': domain,
                 'base_system': body['base_system'], 'question': body['question'], 'completion': body['completion'],
                 'contract_ids': contract_ids, 'branch': domain + '/' + professional,
                 'writable_prefixes': list(PREFIXES[domain]), 'source_author': 'Pi' if not operator else 'operator',
                 'created': time.time(), 'status': 'QUEUED', 'submission': None}
        value['id'] = 'PT-' + identity({k: v for k, v in value.items() if k != 'created'})
        db.execute('INSERT INTO design_professional_tasks VALUES(?,?,?,?,?,?)',
                   (value['id'], p['id'], professional, domain, 'QUEUED', canonical(value)))
        db.execute('INSERT INTO design_branch_heads VALUES(?,?,?,?,?)',
                   (p['id'], domain, value['branch'], None, 0))
        repo.lab.event(owner, 'professional_task_assigned', value, db)
        return value
    value = repo.mutate(owner, body, apply)
    materialize(repo, value)
    return value


def write(repo, owner, body):
    from .repository import name, file_hash
    root, value = workspace(repo, owner)
    logical = name(body['path'])
    if not scope(value['role'], logical): raise PermissionError('DOMAIN_WRITE_SCOPE')
    content = body['content']
    if not isinstance(content, str) or len(content.encode()) > 200000: raise ValueError('WORKSPACE_TEXT_LIMIT')
    path = root/logical
    if any(p.is_symlink() for p in [path, *path.parents] if p.is_relative_to(root)): raise PermissionError('WORKSPACE_SYMLINK')
    expected = body.get('expected_sha256')
    def apply(db):
        if (file_hash(path) if path.exists() else None) != expected: raise ValueError('WORKSPACE_REVISION_CONFLICT')
        # Material edits are exclusively Pi actions and recorded even before commit.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content); path.chmod(0o600)
        return {'project_id': value['project_id'], 'path': logical, 'sha256': file_hash(path), 'source_author': 'Pi'}
    return repo.mutate(owner, body, apply)


def commit(repo, owner, body, operator):
    from .repository import name, file_hash
    root, value = workspace(repo, owner)
    if value['status'] not in ('QUEUED', 'RUNNING', 'REVIEW_REQUIRED'): raise ValueError('PROFESSIONAL_TASK_CLOSED')
    paths = body.get('paths')
    if not isinstance(paths, list) or not paths: raise ValueError('DOMAIN_COMMIT_FILES_REQUIRED')
    for logical in paths:
        name(logical)
        if not scope(value['role'], logical): raise PermissionError('DOMAIN_COMMIT_SCOPE')
    if not isinstance(body.get('rationale'), str) or not body['rationale'].strip(): raise ValueError('DECISION_REASON_REQUIRED')
    def apply(db):
        row = db.execute('SELECT * FROM design_branch_heads WHERE project=? AND domain=? AND branch=?',
            (value['project_id'], value['role'], value['branch'])).fetchone()
        if row['revision'] != body['expected_revision']: raise ValueError('DOMAIN_BRANCH_REVISION_CONFLICT')
        base = repo.system(value['project_id'], value['base_system'], db)
        # A commit extends its branch head. Partial file lists must preserve all
        # earlier changes, including build sources not edited by this operation.
        previous = repo._object(db, 'design_domain_commits', row['head'], value['project_id']) if row['head'] else None
        files = dict(previous['files']) if previous else {k: v for k, v in base['files'].items() if scope(value['role'], k)}
        changes = []
        for logical in paths:
            path = root/logical
            if not path.is_file() or path.is_symlink(): raise ValueError('DOMAIN_FILE_NOT_FOUND')
            ref = repo.asset(db, path)
            if files.get(logical) != ref:
                changes.append({'path': logical, 'before': files.get(logical, {}).get('sha256'), 'after': ref['sha256']})
            files[logical] = ref
        # Changed build/model inputs cannot retain a prior job as qualified output.
        cumulative = [{'path': path, 'before': base['files'].get(path,{}).get('sha256'), 'after': ref['sha256']}
                      for path,ref in files.items() if base['files'].get(path,{}).get('sha256') != ref['sha256']]
        code_changed = any(c['path'].endswith(('.c', '.h', '.ld', 'Makefile', '.mk')) for c in cumulative)
        model_changed = any(c['path'].endswith(('.cir', '.sp', '.json')) and not c['path'].startswith('interfaces/') for c in cumulative)
        result = object_save(repo, db, 'design_domain_commits', 'DC', {
            'project_id': value['project_id'], 'domain': value['role'], 'branch': value['branch'], 'parent': row['head'],
            'base_system': base['id'], 'owner': owner, 'task_id': value['id'], 'files': files,
            'changes': changes, 'cumulative_changes': cumulative, 'rationale': body['rationale'], 'source_author': 'operator' if operator else 'Pi',
            'target_build': 'RECHECK_REQUIRED' if code_changed else 'UNCHANGED_REUSE',
            'model_execution': 'RECHECK_REQUIRED' if model_changed else 'UNCHANGED_REUSE',
            'new_device_design': code_changed or model_changed, 'revision': row['revision']+1},
            ['project_id', 'domain', 'branch', 'parent'])
        db.execute('UPDATE design_branch_heads SET head=?,revision=revision+1 WHERE project=? AND domain=? AND branch=?',
                   (result['id'], value['project_id'], value['role'], value['branch']))
        return result
    return repo.mutate(owner, body, apply)


def contract(repo, owner, body, operator):
    def apply(db):
        p = repo.leader(body['project_id'], owner, db)
        domain_ids = body['domain_commits']
        if set(domain_ids) != {'power', 'firmware'}: raise ValueError('POWER_FIRMWARE_DOMAINS_REQUIRED')
        commits = {k: repo._object(db, 'design_domain_commits', v, p['id']) for k, v in domain_ids.items()}
        if any(c['domain'] != d for d, c in commits.items()): raise ValueError('DOMAIN_IDENTITY_CONFLICT')
        if len({c['base_system'] for c in commits.values()}) != 1: raise ValueError('DOMAIN_BASE_CONFLICT')
        executions={}
        for domain,c in commits.items():
            if c['target_build']=='RECHECK_REQUIRED' or c['model_execution']=='RECHECK_REQUIRED':
                row=db.execute('SELECT value FROM design_domain_executions WHERE project=? AND domain_commit=? ORDER BY rowid DESC LIMIT 1',(p['id'],c['id'])).fetchone()
                if not row:raise ValueError('NEW_INPUT_EXECUTION_REQUIRED')
                execution=json.loads(row['value'])
                if execution['status']!='SUCCEEDED':raise ValueError('DOMAIN_EXECUTION_NOT_SUCCEEDED')
                from .repository_execution import input_project
                manifest='project-fw-s132/project.json' if domain=='firmware' else 'project-chain/project.json'
                if identity(input_project(repo,c,manifest))!=execution['project_sha256']:
                    raise ValueError('DOMAIN_EXECUTION_SOURCE_BINDING')
                executions[domain]=execution['id']
        parent = body.get('parent')
        if parent: repo._object(db, 'design_interface_contracts', parent, p['id'])
        return object_save(repo, db, 'design_interface_contracts', 'IC', {
            'project_id': p['id'], 'name': 'power-firmware', 'parent': parent,
            'domain_commits': domain_ids, 'executions':executions, 'base_system': next(iter(commits.values()))['base_system'],
            'schema_version': VERSION, 'units': 'SI', 'rationale': body['rationale'],
            'source_author': 'operator' if operator else 'Pi', 'revision': 1 if not parent else
                repo._object(db, 'design_interface_contracts', parent, p['id'])['revision']+1,
            'provides': ['power rail and initial state', 'actual radio and sampling timing'],
            'requires': ['source-bound load timing', 'manual admission boundary', 'current amplitude provenance'],
            'status': 'NOT_CHECKED'}, ['project_id', 'name', 'parent'])
    return repo.mutate(owner, body, apply)


def integrate(repo, owner, body, operator):
    def apply(db):
        p = repo.leader(body['project_id'], owner, db)
        if p['revision'] != body['expected_revision']: raise ValueError('PROJECT_REVISION_CONFLICT')
        base = repo.system(p['id'], body['base_system'], db)
        contracts = {k: repo._object(db, 'design_interface_contracts', cid, p['id']) for k, cid in body['contracts'].items()}
        if set(contracts) != {'power-firmware'}: raise ValueError('INTEGRATION_CONTRACT_REQUIRED')
        commits = {k: repo._object(db, 'design_domain_commits', cid, p['id']) for k, cid in body['domain_commits'].items()}
        if set(commits) != {'power', 'firmware'}: raise ValueError('INTEGRATION_DOMAINS_REQUIRED')
        if contracts['power-firmware']['domain_commits'] != body['domain_commits']: raise ValueError('CONTRACT_COMMIT_BINDING')
        if any(c['base_system'] != base['id'] or c['domain'] != k for k, c in commits.items()): raise ValueError('INTEGRATION_BASE_CONFLICT')
        files = dict(base['files']); changes = []
        for c in commits.values():
            files.update(c['files'])
        changes = [{'path': path, 'before': base['files'].get(path,{}).get('sha256'), 'after': ref['sha256']}
                   for path,ref in files.items() if base['files'].get(path,{}).get('sha256') != ref['sha256']]
        child = {k: v for k, v in base.items() if k not in ('id', 'validations', 'import_role')}
        child.update(parent=base['id'], origin_design_id=None, domain_commits=body['domain_commits'], contracts=body['contracts'],
                     files=files, design_changes=changes, provenance='Pi domain commits integrated by source-bound repository',
                     digital_status='REVIEW_REQUIRED', history_fabricated=False)
        child['jobs']=dict(base['jobs'])
        execution_ids=contracts['power-firmware'].get('executions',{})
        for domain,eid in execution_ids.items():
            execution=repo._object(db,'design_domain_executions',eid,p['id'])
            if execution['domain_commit']!=commits[domain]['id']:raise ValueError('EXECUTION_COMMIT_CONFLICT')
            from .repository_contracts import job_domain
            child['jobs']={j:r for j,r in child['jobs'].items() if job_domain(r)!=domain}
            child['jobs'][execution['job_id']]={'kind':execution['kind'],'artifacts':execution['artifacts'],
                'project_sha256':execution['project_sha256'],'origin_owner':execution.get('job_origin_owner',execution['owner']),
                'dispatched_in_v2':not execution.get('reused',False),'consumed_input':execution.get('consumed_input')}
        child['validations'] = reuse_gates(base, child)
        child = repo._save_system(db, owner, child)
        ir = object_save(repo, db, 'design_integration_requests', 'IR', {'project_id': p['id'], 'owner': owner,
            'base': base['id'], 'status': 'INTEGRATED', 'system_commit': child['id'],
            'domain_commits': body['domain_commits'], 'contracts': body['contracts'],
            'rationale': body['rationale'], 'source_author': 'operator' if operator else 'Pi'},
            ['project_id', 'owner', 'base', 'status'])
        db.execute('UPDATE design_projects SET revision=revision+1,submitted=? WHERE id=?', (child['id'], p['id']))
        repo.lab.event(owner, 'system_integrated', {'system_commit': child['id'], 'request': ir['id'],
            'reused_jobs': list(child['jobs']), 'new_native_jobs': len(execution_ids)}, db)
        return {'id': ir['id'], 'project_id': p['id'], 'system_commit': child['id'],
                'revision': p['revision']+1, 'validation_states': {k: v['status'] for k, v in child['validations'].items()}}
    return repo.mutate(owner, body, apply)


def validate(repo, owner, body):
    def apply(db):
        p = repo.leader(body['project_id'], owner, db)
        system = repo.system(p['id'], body['system_id'], db)
        from .repository import file_hash
        def read(path):
            ref = system['files'][path]; source = repo.root/'blobs'/ref['sha256']
            if file_hash(source) != ref['sha256']: raise ValueError('VALIDATION_INPUT_TAMPER')
            return source.read_text()
        declarations = {}
        for domain in ('power', 'firmware'):
            path = 'interfaces/' + domain + '.json'
            if path in system['files']: declarations[domain] = json.loads(read(path))
        if body.get('scope','system')=='interface':
            result = check(read, system['files'], declarations)
        elif body.get('scope','system')=='system':
            from .repository_validation import evaluate
            result=evaluate(repo,system)
            interface=result['interface']
            object_save(repo,db,'design_repository_validations','RV',{'project_id':p['id'],
                'target':system['id'],'kind':'power-firmware-interface','result':interface,
                'status':interface['status'],'scope':interface['scope'],'evaluator':interface['checker'],
                'immutable_input':system['id'],'physical':'NOT_TESTED'},['project_id','target','kind'])
        else:raise ValueError('VALIDATION_SCOPE_UNKNOWN')
        return object_save(repo, db, 'design_repository_validations', 'RV', {'project_id': p['id'],
            'target': system['id'], 'kind': 'power-firmware-interface' if body.get('scope')=='interface' else 'system-engineering', 'result': result,
            'status': result['status'], 'scope': result['scope'], 'evaluator': result['checker'],
            'immutable_input': system['id'], 'physical': 'NOT_TESTED'}, ['project_id', 'target', 'kind'])
    return repo.mutate(owner, body, apply)


def decide(repo, owner, body, operator):
    def apply(db):
        p = repo.leader(body['project_id'], owner, db)
        if body['expected_revision'] != p['revision']: raise ValueError('PROJECT_REVISION_CONFLICT')
        system = repo.system(p['id'], body['system_id'], db)
        if body['decision'] not in ('REVISE', 'REJECT', 'RETAIN_FOR_REVIEW', 'ADOPT_PASSED', 'RESTORE'):
            raise ValueError('SYSTEM_DECISION_INVALID')
        rows = [json.loads(r['value']) for r in db.execute('SELECT value FROM design_repository_validations WHERE project=? AND target=?', (p['id'], system['id']))]
        if not rows: raise ValueError('EXECUTED_VALIDATION_REQUIRED')
        if body['decision'] == 'ADOPT_PASSED':
            from .repository_validation import qualification
            if not qualification(repo,system,db)['product_passed']:
                raise ValueError('PRODUCT_GATES_NOT_PASSED')
        adopted = p['adopted']
        target = system
        if body['decision'] == 'RESTORE':
            # Restoration is a new immutable commit. Historical attempts remain.
            target = repo._save_system(db, owner, {**{k: v for k, v in system.items() if k != 'id'},
                'parent': p['submitted'], 'restored_from': system['id'], 'provenance': 'explicit design restoration'})
        if body['decision'] in ('ADOPT_PASSED', 'RESTORE'): adopted = target['id']
        decision = {'id': 'DA-' + identity({'body': body, 'owner': owner}), 'owner': owner,
                    'from_design': p['adopted'], 'to_design': target['id'], 'revision': p['revision']+1,
                    'decision': body['decision'], 'rationale': body['rationale'],
                    'source_author': 'operator' if operator else 'Pi', 'product_passed': body['decision'] == 'ADOPT_PASSED'}
        db.execute('INSERT INTO design_adoptions VALUES(?,?,?,?,?,?,?)', (decision['id'], owner, decision['from_design'],
            decision['to_design'], decision['revision'], canonical(decision), time.time()))
        db.execute('UPDATE design_projects SET adopted=?,revision=revision+1 WHERE id=?', (adopted, p['id']))
        repo.lab.event(owner, 'system_decision', decision, db)
        return {**decision, 'project_id': p['id']}
    return repo.mutate(owner, body, apply)


def finish(repo, owner, body):
    def apply(db):
        value = task(repo, owner, db)
        if body['status'] not in ('SUBMITTED', 'BLOCKED'): raise ValueError('PROFESSIONAL_FINISH_STATUS')
        commit_id = body.get('domain_commit')
        if body['status'] == 'SUBMITTED':
            commit = repo._object(db, 'design_domain_commits', commit_id, value['project_id'])
            if commit['owner'] != owner or commit['task_id'] != value['id']: raise PermissionError('TASK_SUBMISSION_IDENTITY')
        updated = {**value, 'status': body['status'], 'submission': commit_id, 'conclusion': body['conclusion']}
        db.execute('UPDATE design_professional_tasks SET status=?,value=? WHERE id=?',
                   (body['status'], canonical(updated), value['id']))
        repo.lab.event(value['lead'], 'professional_task_result', updated, db)
        return updated
    return repo.mutate(owner, body, apply)


def release(repo, owner, body):
    def apply(db):
        p = repo.leader(body['project_id'], owner, db)
        system = repo.system(p['id'], body['system_id'], db)
        validations = [json.loads(r['value']) for r in db.execute('SELECT value FROM design_repository_validations WHERE project=? AND target=?', (p['id'], system['id']))]
        if not validations: raise ValueError('RELEASE_REQUIRES_INDEPENDENT_VALIDATION')
        from .repository_reports import required_report
        report_folder, report_quality = required_report(repo, owner, system, body.get('report_id'))
        from .repository import file_hash
        all_refs=list(system['files'].values())+[ref for job in system['jobs'].values() for ref in job.get('artifacts',{}).values()]
        for ref in all_refs:
            if file_hash(repo.root/'blobs'/ref['sha256']) != ref['sha256']: raise ValueError('RELEASE_INPUT_TAMPER')
        from .repository_validation import qualification
        current=qualification(repo,system,db)
        manifest = {'schema_version': 'bf-system-review-release-v2', 'project_id': p['id'], 'target': system['id'],
                    'files': system['files'], 'validations': validations, 'jobs': system['jobs'],
                    'digital_status': current['status'], 'qualification':current, 'physical': system['physical'],
                    'kind': 'REVIEW_PACKAGE', 'rationale': body['rationale'], 'source_author': 'Pi',
                    'original_owner': system['origin_owner'], 'baseline': p['baseline'],
                    'required_engineering_report': report_quality}
        result = object_save(repo, db, 'design_repository_releases', 'REL', manifest, ['project_id', 'target'])
        archive = repo.root/'releases'/(result['id']+'.zip'); archive.parent.mkdir(exist_ok=True)
        if not archive.exists():
            with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifest.json', canonical(result))
                for path in report_quality['outputs']:
                    z.write(report_folder/path, 'reports/'+path)
                z.write(report_folder/'quality.json','reports/quality.json')
                for path, ref in system['files'].items(): z.write(repo.root/'blobs'/ref['sha256'], 'engineering/'+path)
                for job, record in system['jobs'].items():
                    for path, ref in record.get('artifacts', {}).items(): z.write(repo.root/'blobs'/ref['sha256'], 'jobs/'+job+'/'+path)
        sealed(repo.root/'releases'/(result['id']+'.seal.json'), {'release_id': result['id'], 'sha256': file_hash(archive),
               'bytes': archive.stat().st_size, 'target': system['id']})
        return result
    return repo.mutate(owner, body, apply)


def summary(repo, project, owner):
    view = repo.view(project, owner); p = view['project']
    current = repo.system(project, p['submitted'] or p['adopted'])
    from .repository_validation import qualification
    current_qualification=qualification(repo,current)
    return {'project_id': project, 'owner': owner, 'revision': p['revision'], 'adopted': p['adopted'],
            'current_system': current['id'], 'baseline': p['baseline'], 'requirements': p['requirements'],
            'files': [{'path': k, 'sha256': v['sha256'], 'bytes': v['bytes']} for k, v in current['files'].items()],
            'gates': {k: v['status'] for k, v in current_qualification['gates'].items()},
            'qualification':{k:v for k,v in current_qualification.items() if k!='gates'},
            'domains': [{k: c[k] for k in ('id', 'domain', 'owner', 'rationale', 'target_build', 'model_execution')} for c in view['domain_commits']],
            'contracts': [{k: c[k] for k in ('id', 'domain_commits', 'name', 'revision')} for c in view['contracts']],
            'tasks': view['professional_tasks'], 'branches': view['branches'],
            'validations': view['validations'], 'releases': [{k: c[k] for k in ('id', 'target', 'kind')} for c in view['releases']]}


def handle(repo, owner, body, operator=False):
    action = body['action']
    if action.startswith('repository_report_'):
        from .repository_reports import handle as reports
        return reports(repo, owner, body)
    if action == 'repository_schema': return declaration_spec()
    actions = {'repository_assign': lambda: assign(repo, owner, body, operator),
               'repository_write': lambda: write(repo, owner, body),
               'repository_commit': lambda: commit(repo, owner, body, operator),
               'repository_contract': lambda: contract(repo, owner, body, operator),
               'repository_integrate': lambda: integrate(repo, owner, body, operator),
               'repository_validate': lambda: validate(repo, owner, body),
               'repository_decide': lambda: decide(repo, owner, body, operator),
               'repository_finish': lambda: finish(repo, owner, body),
               'repository_release': lambda: release(repo, owner, body),
               'repository_summary': lambda: summary(repo, body['project_id'], owner),
               'repository_task': lambda: task(repo, owner)}
    if action in ('repository_execute','repository_execution'):
        from .repository_execution import handle as execution
        return execution(repo,owner,body)
    if action == 'repository_workspace_read':
        from .repository import name, file_hash
        root, value = workspace(repo, owner); path = root/name(body['path'])
        if path.is_symlink() or not path.is_file(): raise ValueError('WORKSPACE_FILE_NOT_FOUND')
        offset, limit = body.get('offset', 0), body.get('limit', 10000)
        if type(offset) != int or type(limit) != int or offset < 0 or not 1 <= limit <= 24000: raise ValueError('REPOSITORY_READ_RANGE')
        text = path.read_text(errors='replace')
        return {'path': body['path'], 'sha256': file_hash(path), 'content': text[offset:offset+limit],
                'next_offset': offset+limit if offset+limit < len(text) else None}
    if action=='repository_extract':
        s=repo.system(body['project_id'],body.get('system_id') or body.get('base_system') or repo.project(body['project_id'])['submitted'])
        files=dict(s['files'])
        with repo.store.connect() as db:
            for domain, key in body.get('domain_commits',{}).items():
                peer=repo._object(db,'design_domain_commits',key,body['project_id'])
                if peer['base_system']!=s['id'] or peer['domain']!=domain:raise ValueError('EXTRACTION_BASE_CONFLICT')
                files.update(peer['files'])
        from .repository import file_hash
        def read(path):
            ref=files[path];p=repo.root/'blobs'/ref['sha256']
            if file_hash(p)!=ref['sha256']:raise ValueError('EXTRACTION_INPUT_TAMPER')
            return p.read_text()
        result=check(read,files)
        return {'system_commit':s['id'],'checker':result['checker'],'status':result['status'],
                'facts':result.get('facts'),'source_hashes':result['source_hashes'],
                'declaration_schema':declaration_spec(), 'examples':declaration_examples(result),
                'domain_commits':body.get('domain_commits',{}),
                'issues':result.get('issues',[])}
    if action=='repository_rebase':return rebase(repo,owner,body)
    if action=='repository_reopen':
        def apply(db):
            p=repo.leader(body['project_id'],owner,db);v=task(repo,body['task_owner'],db)
            if v['project_id']!=p['id']:raise PermissionError('TASK_PROJECT_CONFLICT')
            v.update(status='QUEUED',question=body['question'],completion=body['completion'])
            db.execute('UPDATE design_professional_tasks SET status=?,value=? WHERE id=?',('QUEUED',canonical(v),v['id']))
            repo.lab.event(owner,'professional_task_reopened',v,db)
            return v
        return repo.mutate(owner,body,apply)
    if action in actions: return actions[action]()
    return None


def rebase(repo, owner, body):
    """Explicitly move an idle specialist to a new system; retain old tasks and workspaces."""
    from .repository import file_hash
    target_owner=body['task_owner']
    controller=getattr(repo.lab,'controllers',{}).get(target_owner)
    if controller and controller.is_alive():raise ValueError('REBASE_SPECIALIST_RUNNING')
    old=task(repo,target_owner)
    for key in ('question','completion'):
        if not isinstance(body.get(key),str) or not 1<=len(body[key])<=4000:raise ValueError('TASK_'+key.upper()+'_REQUIRED')
    def session_source(task_id):
        oldroot=repo.root/'workspaces'/task_id
        prior=oldroot/'.pi/repository-session-path'
        if not prior.exists():return None
        if prior.is_symlink():raise ValueError('REBASE_SESSION_SYMLINK')
        source=Path(prior.read_text().strip())
        allowed=oldroot/'.pi/repository-sessions'
        if not source.is_absolute() or not source.is_relative_to(allowed) or source.is_symlink() or not source.is_file():
            raise ValueError('REBASE_SESSION_PATH_CONFLICT')
        if any(p.is_symlink() for p in source.parents if p.is_relative_to(oldroot)):
            raise ValueError('REBASE_SESSION_SYMLINK')
        return source
    session_source(old['id'])
    def apply(db):
        p=repo.leader(body['project_id'],owner,db)
        current=task(repo,target_owner,db)
        if current!=old:raise ValueError('TASK_REBASE_CONFLICT')
        base=repo.system(p['id'],body['base_system'],db)
        if current['project_id']!=p['id']:raise PermissionError('TASK_PROJECT_CONFLICT')
        row=db.execute('SELECT * FROM design_branch_heads WHERE project=? AND domain=? AND branch=?',
            (p['id'],current['role'],current['branch'])).fetchone()
        if row['revision']!=body['expected_revision']:raise ValueError('DOMAIN_BRANCH_REVISION_CONFLICT')
        previous=repo._object(db,'design_domain_commits',row['head'],p['id']) if row['head'] else repo.system(p['id'],current['base_system'],db)
        root=repo.root/'workspaces'/current['id']
        dirty=[str(path.relative_to(root)) for path in root.rglob('*') if path.is_file()
               and scope(current['role'],str(path.relative_to(root)))
               and previous['files'].get(str(path.relative_to(root)),{}).get('sha256')!=file_hash(path)]
        if dirty:raise ValueError('REBASE_UNCOMMITTED_FILES: '+','.join(dirty))
        archived={**current,'branch_head':row['head'],'branch_revision':row['revision']}
        archive_id='TA-'+identity(archived)
        db.execute('INSERT OR IGNORE INTO design_professional_task_history VALUES(?,?,?,?)',
            (archive_id,p['id'],target_owner,canonical(archived)))
        sealed(repo.root/'task-history'/(archive_id+'.json'),archived)
        value={**current,'base_system':base['id'],'previous_task':current['id'],
               'question':body['question'],'completion':body['completion'],'status':'QUEUED',
               'submission':None,'created':time.time()}
        value.pop('conclusion',None)
        value['id']='PT-'+identity({k:v for k,v in value.items() if k not in ('id','created','branch')})
        value['branch']=current['role']+'/'+target_owner+'/'+value['id'][3:15]
        db.execute('UPDATE design_professional_tasks SET id=?,status=?,value=? WHERE owner=?',
                   (value['id'],'QUEUED',canonical(value),target_owner))
        db.execute('INSERT INTO design_branch_heads VALUES(?,?,?,?,?)',(p['id'],current['role'],value['branch'],None,0))
        repo.lab.event(owner,'professional_task_rebased',{'old_task':current['id'],'old_base':current['base_system'],
            'new_task':value['id'],'new_base':base['id'],'owner':target_owner,'archive':archive_id},db)
        return value
    value=repo.mutate(owner,body,apply)
    root=materialize(repo,value)
    pointer=root/'.pi/repository-session-path'
    if not pointer.exists():
        source=session_source(value['previous_task'])
        if source:
            # Preserve SDK session identity/history inside the new task sandbox.
            # The old workspace and its original session remain untouched.
            destination=root/'.pi/repository-sessions'/source.name
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists() and file_hash(destination)!=file_hash(source):
                raise ValueError('REBASE_SESSION_COPY_CONFLICT')
            destination.write_bytes(source.read_bytes());destination.chmod(0o600)
            pointer.write_text(str(destination));pointer.chmod(0o600)
            sealed(root/'.pi/rebase-session.json',{'source':str(source),'source_sha256':file_hash(source),
                'destination':str(destination),'previous_task':value['previous_task'],'owner':target_owner})
    return value
