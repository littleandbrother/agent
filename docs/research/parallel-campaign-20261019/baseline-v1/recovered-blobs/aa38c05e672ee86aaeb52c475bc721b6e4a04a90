"""Read-only lifecycle facts derived from the existing candidate and journal."""
import json

from .repository_profiles import system_definition, system_profile
from .repository_task_standards import check_files


def state(repo, owner, body):
    p = repo.project(body['project_id'], owner)
    s = repo.system(p['id'], body.get('system_id') or p['submitted'])
    task = system_definition(repo, s)
    if not task: raise ValueError('EXPLICIT_TASK_DEFINITION_REQUIRED')
    cfg = system_profile(s)
    result = {'project_id': p['id'], 'system_id': s['id'], 'task_definition': task['id'],
        'phase': task['phase'], 'intent': task['intent'], 'scope': task['scope'],
        'current': s['id'] == p['submitted'], 'adopted': s['id'] == p['adopted'],
        'task_transition': s.get('task_transition'), 'native_jobs_dispatched': 0}
    try:
        check_files(task, s['files'], lambda path: (repo.root/'blobs'/s['files'][path]['sha256']).read_text())
    except (ValueError, PermissionError, KeyError) as error:
        return {**result, 'stage': 'INPUT_BLOCKED', 'reason': str(error), 'allowed_actions': ['task_definition', 'read']}
    execution = None
    if cfg['adapter'] in ('tabulated-curve-v1', 'piezo-reference-v1','piezo-feedback-v1'):
        from .repository_task_execution import current_execution, pending_execution
        root = pending_execution(repo, s)
        execution = current_execution(repo, s)
        if not execution and root:
            completed = (root/'completed.json').exists()
            return {**result, 'stage': 'RECOVERY_REQUIRED', 'operation_state': 'COMPLETED_NOT_REGISTERED' if completed else 'UNKNOWN',
                    'allowed_actions': ['task_execute', 'task_result'] if completed else ['state', 'task_state'],
                    'recovery_action': 'register_completed_result' if completed else 'operator_reconcile', 'dispatch_allowed': False}
        if not execution:
            return {**result, 'stage': 'READY_TO_EXECUTE', 'allowed_actions': ['task_execute', 'read'], 'dispatch_allowed': True}
    from .repository_validation import qualification
    q = qualification(repo, s)
    gates = q['gates']; statuses = {v['status'] for v in gates.values()}
    if statuses & {'NOT_CHECKED', 'RECHECK_REQUIRED'}: stage = 'READY_TO_VALIDATE'
    elif execution and execution['status'] != 'SUCCEEDED': stage = 'EXECUTION_BLOCKED'
    elif statuses & {'UNEVALUABLE'}: stage = 'EVALUATION_BLOCKED'
    else: stage = 'DECISION_REQUIRED'
    report = None; release = None
    if cfg['report'] != 'node-eight-page-v1':
        from .repository_task_reports import required
        try:
            folder, quality = required(repo, owner, s); report = folder.name
            with repo.store.connect() as db:
                for row in db.execute('SELECT value FROM design_repository_releases WHERE project=? AND target=? ORDER BY rowid DESC', (p['id'], s['id'])):
                    item = json.loads(row['value'])
                    if item.get('qualification') == q and item.get('required_engineering_report') == quality and (repo.root/'releases'/(item['id']+'.zip')).is_file():
                        release = item['id']; break
        except ValueError as error:
            result['report_status'] = str(error)
    if release: stage = 'DELIVERED'
    elif report: stage = 'READY_TO_DELIVER'
    interfaces = {}
    def combined(keys):
        values = [gates.get(k, {}).get('status', 'NOT_CHECKED') for k in keys]
        if all(v == 'PASS' for v in values) and values: return 'PASS'
        for status in ('FAIL', 'UNEVALUABLE', 'RECHECK_REQUIRED', 'NOT_CHECKED'):
            if status in values: return status
        return 'NOT_CHECKED'
    for key, spec in task.get('standards', {}).get('interface_consumers', {}).items():
        interfaces[key] = {'format': 'PASS', 'source_consistency': combined(spec['source_gates']),
            'engineering_compatibility': combined(spec['engineering_gates']), 'scope': spec['scope']} if spec['status'] == 'IMPLEMENTED' else {'status': spec['status']}
    actions = ['task_result', 'read', 'validate', 'decide', 'task_report', 'release']
    if cfg.get('review_only'): actions = ['read', 'validate', 'decide', 'task_report', 'release']
    elif task['intent'] != 'audit': actions += ['assign'] if cfg['roles'] else ['task_commit']
    return {**result, 'stage': stage, 'execution_id': execution['id'] if execution else None,
        'execution_status': execution['status'] if execution else 'NATIVE_DOMAIN_PATH',
        'qualification': q, 'interfaces': interfaces, 'report_id': report, 'release_id': release,
        'allowed_actions': actions, 'dispatch_allowed': False}
