"""Task-scoped, read-only acceptance. No participant-supplied verdict is trusted.

The legacy assembly goal is a bounded digital milestone, never full engineering
acceptance. This projection supplies the same verdict to Pi and all four views.
"""
from .store import identity

STAGES = ('concept', 'digital-model', 'engineering-package', 'computational-verification', 'hardware')
PLUCK_ONLY = {'magnetics', 'fem', 'convergence', 'mapping', 'direction'}


def fingerprints(current):
    if not current:
        return {}
    p = current['payload']
    return {**current['hashes'],
            'requirements': identity({k: p.get(k) for k in ('requirements', 'assumptions', 'required_roles')}),
            'interfaces': identity({'interfaces': p.get('interfaces'), 'contacts': p.get('allowed_contacts', [])}),
            'presentation': identity({'view': p.get('presentation'), 'appearance': [{k:x.get(k) for k in ('id','name','color')} for x in p['parts']]})}


def dimensions(task):
    # Unknown tasks conservatively depend on the complete physical definition.
    return {'requirements': ['requirements'], 'references': ['requirements'],
            'interfaces': ['requirements', 'interfaces'],
            'cad': ['geometry_hash', 'interfaces'], 'drawings': ['geometry_hash'],
            'presentation': ['geometry_hash', 'presentation'],
            'clearance': ['geometry_hash', 'interfaces'],
            'firmware': ['interfaces', 'energy_hash'],
            'firmware-resources': ['interfaces', 'energy_hash']}.get(task, ['physical_hash'])


def binding_inputs(task, current):
    h = fingerprints(current)
    return {k: h.get(k) for k in dimensions(task)}


def profile(current):
    if current and 'pv_power_mw' in current['payload'].get('energy', {}):
        return 'solar', '由当前供能字段推定；未替用户批准产品要求'
    return 'unclassified', '尚未确定采能类型；专用拨动采能条目保留为适用性待确认'


def verdict(app, owner, snapshot, assembly=None):
    a = assembly if assembly is not None else app.assemblies.projection(owner, include_delivery=False)
    current = a.get('current')
    legacy = app.assemblies.observe_delivery(owner, a)
    checks = {x['id']: x for x in a.get('checks', [])}
    # Independently verify every output, even when a database says SUCCEEDED.
    valid_model = False
    for j in a.get('jobs', []):
        if j.get('stale') or j['status'] != 'SUCCEEDED' or not (j.get('result') or {}).get('digital_checks_passed'):
            continue
        try:
            for f in j['result'].get('artifacts', []):
                app.engineering.artifact(owner, j['id'], f['name'])
            valid_model = bool(j['result'].get('artifacts'))
        except (ValueError, OSError, PermissionError):
            continue
        if valid_model:
            break
    roles_ok = checks.get('required-parts', {}).get('passed', False)
    native_ok = valid_model and roles_ok
    task_rows = snapshot['tasks']
    applicable = [t for t in task_rows if t.get('applicability') != 'not_applicable']
    package_missing = [t['id'] for t in applicable if t['delivery_status'] != 'present']
    verification_missing = [t['id'] for t in applicable if t['validation_status'] != 'passed']
    records = [
        dict(id='concept', label='需求与方案', passed=bool(current and current['source_valid']), missing=[] if current else ['assembly']),
        dict(id='digital-model', label='原生数字模型', passed=native_ok, missing=[] if native_ok else ['current-native-model']),
        dict(id='engineering-package', label='工程文件齐套', passed=bool(applicable) and not package_missing, missing=package_missing),
        dict(id='computational-verification', label='计算与工程验收', passed=bool(applicable) and not verification_missing, missing=verification_missing),
        dict(id='hardware', label='实物验收', passed=False, missing=['physical-measurements'], status='not_measured'),
    ]
    # Legacy goals remain explicit bounded milestones for historical tasks.
    target = 'digital-model' if legacy else 'computational-verification'
    missing = list(legacy['missing']) if legacy else verification_missing
    if legacy and not native_ok and 'current_native_checks_not_passed' not in missing:
        missing.append('current_native_checks_not_passed')
    passed = not missing and (native_ok if legacy else bool(applicable))
    explicit = app.deliverables.stage_contract(owner)
    if explicit:
        target = explicit['target_stage']
        stage = next(x for x in records if x['id']==target)
        missing = list(stage['missing']); passed = stage['passed']
    value = dict(schema_version='bf-product-authority-v1', owner=owner,
                 assembly_revision=current['revision'] if current else None,
                 contract_sha256=identity(snapshot['contract']), profile=snapshot['profile'],
                 target_stage=target, target_source='operator-stage-contract' if explicit else 'operator-legacy-digital-goal' if legacy else 'engineering-default',
                 stage_contract=explicit,
                 passed=passed, missing=missing, stages=records,
                 max_continuations=explicit['max_continuations'] if explicit else legacy['max_continuations'] if legacy else 0, auto_continue=bool(explicit or legacy),
                 goal=legacy.get('goal') if legacy else {},
                 full_engineering_passed=records[3]['passed'], hardware_verified=False,
                 scope='当前目标阶段判定；阶段完成不代表整机、制造或实物完成。')
    value['verdict_sha256'] = identity(value)
    return value


def context_packet(app, owner):
    d = app.deliverables.inspect(owner)
    try:
        a = app.assemblies.get(owner)
    except ValueError as exc:
        if str(exc) != 'ASSEMBLY_NOT_FOUND':
            raise
        a = None
    jobs = app.engineering.jobs(owner)
    packet = dict(schema_version='bf-product-context-v1', owner=owner,
                  revision=a['revision'] if a else None, hashes=a['hashes'] if a else {},
                  requirements=a['payload'].get('requirements', []) if a else [],
                  assumptions=a['payload'].get('assumptions', []) if a else [],
                  interfaces=a['payload'].get('interfaces', []) if a else [],
                  delivery=d['verdict'], stale_tasks=d['stale_tasks'],
                  pending=[{'id': j['id'], 'engine': j['engine'], 'status': j['status']} for j in jobs if j['status'] in ('RUNNING', 'QUEUED', 'UNKNOWN')],
                  failures=[{'id': j['id'], 'engine': j['engine'], 'error': j.get('error')} for j in jobs if j['status']=='FAILED'][:5],
                  evidence=[{'task': t['id'], 'status': t['validation_status'], 'files': [f['id'] for f in (t['binding'] or {}).get('files', [])]} for t in d['tasks'] if t['binding']],
                  memory_authority='Shared notes are unverified; this packet contains current task facts, not hidden evaluation.')
    packet['sha256'] = identity(packet)
    return packet
