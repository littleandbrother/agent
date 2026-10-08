"""Owner-bound method metadata. Actual jobs/artifacts remain the authority."""
import json
import time
from .simulation_chain.contracts import digest, file_hash
from .simulation_tasks import check_candidate

VERSION = 'bf-method-policy-v2-mainline'
PROFILES = {'strong_generic': (False, False), 'bf_design': (True, True),
            'representation_only': (True, False), 'revision_only': (False, True)}


def profile(name='strong_generic', opportunities=3):
    if name not in PROFILES or opportunities != 3:
        raise ValueError('METHOD_PROFILE_NOT_SUPPORTED')
    r, q = PROFILES[name]
    return {'schema': VERSION, 'method_id': name, 'R': r, 'Q': q,
            'candidate_opportunities': opportunities}


def capabilities(binding=None):
    if binding and binding['task'].get('engine')=='door-system':
        return {'id':'door-loading-release-configuration-v1','numeric_parameters':True,
                'structural_configuration':['mechanical.closed_dz_mm','mechanical.polarity'],
                'artifact_binding':['native CAD bracket pose','joint rotated magnetic force'],
                'architecture':False,'candidate_artifact_sources':False,
                'scope':'Bounded physical configuration, storage and timing; fixed beam/PMIC/application core, no topology synthesis or method superiority claim.'}
    return {'id': 'mainline-numeric-candidate-only-v2', 'numeric_parameters': True,
            'architecture': False, 'candidate_artifact_sources': False,
            'scope': 'Four R/Q policies are available; this pilot uses strong_generic only.'}


def record(engineering, owner, body):
    binding = engineering.tasks.binding(owner)
    if not binding:
        raise ValueError('METHOD_TASK_NOT_BOUND')
    kind = body.get('requested_kind')
    if kind not in ('parameter_refinement', 'architecture_recomposition'):
        raise ValueError('METHOD_REVISION_KIND')
    for key in ('rationale', 'falsifier'):
        if not isinstance(body.get(key), str) or not 1 <= len(body[key]) <= 4000:
            raise ValueError('METHOD_REASON_REQUIRED')
    after_id, before_id = body.get('job_id'), body.get('before_job_id')
    def snapshot(job_id):
        job = engineering.get(owner, job_id)  # cross-owner jobs rejected here
        if job['status'] not in ('SUCCEEDED', 'FAILED'):
            raise ValueError('METHOD_JOB_NOT_FINAL')
        if job.get('task_binding',{}).get('task_hash') != binding['task_hash']:
            raise ValueError('METHOD_JOB_TASK_MISMATCH')
        path = engineering.artifact(owner, job_id, 'design-spec.json')
        result = engineering.artifact(owner, job_id, 'result.json')
        candidate=json.loads(path.read_text())
        check_candidate(binding,{'candidate':candidate,'confirmation':True})
        observed=json.loads(result.read_text()).get('task_evaluation')
        if observed and observed.get('task_hash') != binding['task_hash']:
            raise ValueError('METHOD_RESULT_TASK_MISMATCH')
        return candidate, {'design-spec.json': file_hash(path),
            'result.json': file_hash(result)}, observed
    previous, before_hashes, _ = snapshot(before_id) if before_id else (
        binding['task']['baseline'], {'task-baseline': digest(binding['task']['baseline'])}, None)
    if after_id:
        current, after_hashes, evaluation = snapshot(after_id)
    elif kind == 'architecture_recomposition':
        current, after_hashes, evaluation = previous, before_hashes, None
    else:
        raise ValueError('METHOD_EXECUTED_JOB_REQUIRED')
    changed = [group+'.'+key for group, values in current.items() if isinstance(values, dict)
               for key, value in values.items() if previous[group][key] != value]
    unsupported = kind == 'architecture_recomposition'
    value = {'schema_version': 'method-capability-action-v1', 'owner': owner,
        'task_hash':binding['task_hash'],
        'method_profile': profile(), 'capabilities': capabilities(binding), 'before_job_id': before_id,
        'job_id': after_id, 'before_artifacts': before_hashes, 'after_artifacts': after_hashes,
        'actual_changed_fields': changed, 'requested_kind': kind,
        'rationale': body['rationale'], 'falsifier': body['falsifier'],
        'implementation_status': 'proposed_unsupported' if unsupported else 'executed_numeric_revision' if changed else 'no_op',
        'blocker': 'PROVIDER_ARCHITECTURE_NOT_IMPLEMENTED' if unsupported else None,
        'evaluation': evaluation, 'scientific_success': False, 'architecture_executed': False}
    value['record_id'] = digest(value)
    with engineering.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS method_revisions(id TEXT PRIMARY KEY, owner TEXT NOT NULL, receipt TEXT NOT NULL, created REAL NOT NULL)')
        db.execute('INSERT OR IGNORE INTO method_revisions VALUES(?,?,?,?)',
                   (value['record_id'], owner, json.dumps(value, sort_keys=True), time.time()))
    engineering.event(owner, after_id, 'method_revision', value)
    return value
