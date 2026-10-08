"""Persistent product analysis; participant statements never become verdicts."""
import hashlib
import json
from pathlib import Path
from .store import canonical, identity


def contract(app, owner):
    path = app.store.root / 'responsibility-contracts' / (owner + '.json')
    return json.loads(path.read_text()) if path.is_file() else None


def bind_contract(app, owner, body):
    """Operator freezes the task inventory, not the participant's engineering answer."""
    app.conversations.get(owner)
    allowed = {'action','session_id','source_revision','required_ids','max_continuations','reason','sources'}
    if set(body)-allowed or not isinstance(body.get('source_revision'),str) or not body['source_revision']:
        raise ValueError('REVIEW_CONTRACT_SCHEMA')
    ids = body.get('required_ids')
    if not isinstance(ids,list) or not ids or any(not isinstance(x,str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('REVIEW_CONTRACT_IDS')
    if type(body.get('max_continuations')) is not int or not 0 <= body['max_continuations'] <= 4 or not body.get('reason'):
        raise ValueError('REVIEW_CONTRACT_CONTINUATIONS')
    root = app.store.root.parent / 'participants' / owner
    sources = body.get('sources')
    if not isinstance(sources,list) or not sources: raise ValueError('REVIEW_CONTRACT_SOURCES')
    for item in sources:
        path = local_file(root,item.get('path'))
        if not path.is_file() or digest(path) != item.get('sha256'): raise ValueError('REVIEW_CONTRACT_SOURCE_MISMATCH')
    value = {k:body[k] for k in ('source_revision','required_ids','max_continuations','reason','sources')}
    value.update(schema_version='bf-responsibility-contract-v1',owner=owner,authority='operator')
    value['sha256'] = identity(value)
    old = contract(app,owner)
    if old:
        if old != value: raise ValueError('REVIEW_CONTRACT_ALREADY_FROZEN')
        return old
    folder = app.store.root/'responsibility-contracts'; folder.mkdir(exist_ok=True)
    with (folder/(owner+'.json')).open('x') as stream: stream.write(canonical(value))
    app.conversations.event(owner,'responsibility-contract-'+value['sha256'],{'type':'responsibility_contract','contract':value})
    return value


def local_file(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('REVIEW_RELATIVE_PATH_REQUIRED')
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('REVIEW_PATH_DENIED')
    return path


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def inspect(root, expected=None):
    root = Path(root)
    path = local_file(root, 'analysis.json')
    if not path.is_file():
        return {'schema_version': 'bf-responsibility-review-v1', 'status': 'missing',
                'missing': ['analysis.json'], 'engineering_passed': False,
                'instruction': 'Write analysis.json with source_revision, sources[{path,sha256}], responsibilities[{id,requirement,status,artifacts:[{path,source_revision,reference_only}]}], assumptions, decisions, issues. Public reasons only. Then inspect again.'}
    if path.stat().st_size > 262144:
        raise ValueError('REVIEW_TOO_LARGE')
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or any(not isinstance(data.get(k), list) for k in ('sources', 'responsibilities', 'assumptions', 'decisions', 'issues')) or not isinstance(data.get('source_revision'), str):
        raise ValueError('REVIEW_SCHEMA')
    if not data['sources'] or not data['responsibilities']:
        raise ValueError('REVIEW_SOURCES_AND_RESPONSIBILITIES_REQUIRED')
    errors = []; missing = []; artifacts = []; ids = set(); actionable = []; blocked = []
    if expected:
        if data['source_revision'] != expected['source_revision']: errors.append('task_revision_mismatch')
        for source in expected['sources']:
            p = local_file(root,source['path'])
            if not p.is_file() or digest(p) != source['sha256']: errors.append('frozen_source_changed:' + source['path'])
    for source in data['sources']:
        p = local_file(root, source.get('path'))
        if not p.is_file() or digest(p) != source.get('sha256'):
            errors.append('source_changed_or_missing:' + source['path'])
    for item in data['responsibilities']:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or item['id'] in ids or not item.get('requirement') or item.get('status') not in ('planned','working','evidence_ready','blocked'):
            raise ValueError('REVIEW_RESPONSIBILITY_SCHEMA')
        ids.add(item['id'])
        refs = item.get('artifacts', [])
        if not refs: missing.append(item['id'])
        for ref in refs:
            p = local_file(root, ref.get('path'))
            valid = p.is_file() and p.stat().st_size > 0
            current = ref.get('source_revision') == data['source_revision'] and ref.get('reference_only') is False
            if not valid: missing.append(item['id'] + ':' + ref['path'])
            if not current: errors.append('reference_or_revision_mismatch:' + ref['path'])
            artifacts.append({'responsibility': item['id'], 'path': ref['path'], 'exists': valid,
                              'current_declared_revision': current, 'sha256': digest(p) if valid else None})
        if item['status'] != 'evidence_ready': missing.append(item['id'] + ':' + item['status'])
        if item['status'] == 'blocked': blocked.append(item['id'])
        elif item['status'] != 'evidence_ready' or not refs: actionable.append(item['id'])
        elif any(x == item['id'] or x.startswith(item['id']+':') for x in missing): actionable.append(item['id'])
    if expected:
        for key in expected['required_ids']:
            if key not in ids: missing.append(key); actionable.append(key)
    if errors: actionable.append('source_or_revision_integrity')
    return {'schema_version': 'bf-responsibility-review-v1', 'status': 'incomplete' if missing or errors else 'inventory_ready',
            'source_revision': data['source_revision'], 'analysis_sha256': digest(path),
            'errors': errors, 'missing': missing, 'actionable': actionable, 'blocked': blocked, 'artifacts': artifacts, 'issues': data['issues'],
            'engineering_passed': False, 'agent_autonomy_proven': False,
            'scope': 'Checks existence, source bytes and declared current revision only. Native checks, circuit equivalence and responsibility attribution require independent evidence; a filled checklist is not acceptance.'}


def submit(app, owner, body):
    """Record a bounded stopping point. This is never engineering acceptance."""
    expected = contract(app, owner)
    if not expected: raise ValueError('REVIEW_CONTRACT_REQUIRED')
    root = app.eda_cli.workspace(owner)
    report = local_file(root, body.get('file_path'))
    if not report.is_file() or report.stat().st_size < 40: raise ValueError('REVIEW_REPORT_REQUIRED')
    review = inspect(root, expected)
    if review.get('errors') or review.get('actionable') or review['status'] == 'missing':
        return {'submitted': False, 'review': review, 'reason': 'Actionable or integrity gaps remain; continue executing.'}
    data = json.loads((root/'analysis.json').read_text())
    for item in data['responsibilities']:
        if item['status'] == 'blocked' and (not item.get('blocker_reason') or not item.get('artifacts') or any(not a['exists'] for a in review['artifacts'] if a['responsibility'] == item['id'])):
            return {'submitted': False, 'review': review, 'reason': 'Blocked responsibilities need blocker_reason and actual evidence artifacts.'}
    receipt = {'schema_version':'bf-responsibility-submission-v1', 'owner':owner,
               'status':'submitted_with_gaps' if review.get('blocked') else 'inventory_submitted',
               'submitted':True, 'review':review, 'report':{'path':body['file_path'],'sha256':digest(report)},
               'contract_sha256':expected['sha256'], 'engineering_passed':False, 'agent_autonomy_proven':False}
    receipt['sha256'] = identity(receipt)
    folder = app.store.root/'responsibility-submissions'/owner; folder.mkdir(parents=True,exist_ok=True)
    path = folder/(receipt['sha256']+'.json')
    if not path.exists(): path.write_text(canonical(receipt))
    app.conversations.event(owner,'responsibility-submission-'+receipt['sha256'],{'type':'responsibility_submission','receipt':receipt})
    # One catalogue serves the task and product/delivery pages. A submission
    # may expose evidence and gaps; it cannot promote an engineering verdict.
    publication = publish_submission(app.results, owner, root, data, receipt)
    return {**receipt, 'publication':publication}


def publish_submission(catalog, owner, root, data, receipt):
    groups=[];total=0
    responsibilities=data['responsibilities']
    if len(responsibilities)>31: raise ValueError('REVIEW_PUBLICATION_GROUP_LIMIT')
    for index,item in enumerate(responsibilities):
        files=[]
        for ref in item.get('artifacts',[]):
            p=local_file(root,ref['path']);total+=p.stat().st_size
            if total>32*1024*1024: raise ValueError('REVIEW_PUBLICATION_SIZE_LIMIT')
            sha=digest(p)
            files.append({'path':ref['path'],'sha256':sha,
                          'name':sha[:10]+'-'+p.name,'sections':['documents']})
        if files:
            domain=item.get('domain','system')
            if domain not in ('mechanical','circuit','firmware','system'): domain='system'
            groups.append({'id':'responsibility-'+str(index+1),'domain':domain,
                           'kind':'analysis-evidence','title':str(item['requirement'])[:160],
                           'scope':'Agent 提交的候选证据；'+str(item['status'])+'；尚未经独立工程验收',
                           'design_status':'insufficient_evidence','files':list({f['path']:f for f in files}.values())})
    report=receipt['report']
    groups.append({'id':'submission','domain':'system','kind':'analysis-report',
                   'title':'分析与交付检查','scope':'清单提交不等于工程通过；以报告中缺项为准',
                   'design_status':'insufficient_evidence',
                   'files':[{'path':report['path'],'sha256':report['sha256'],'sections':['documents']}]})
    manifest={'schema_version':'bf-engineering-case-v1','id':'analysis-'+receipt['contract_sha256'][:12],
              'version':'review-'+receipt['sha256'][:12],'title':'任务分析与候选交付',
              'authority':'operator-assisted','hardware_verified':False,'autonomous_agent_verified':False,
              'design_sha256':receipt['review']['analysis_sha256'],'groups':groups}
    saved=catalog.cases.publish(owner,root,manifest)
    return {'id':saved['id'],'version':saved['version'],'groups':len(groups),
            'engineering_passed':False,'agent_autonomy_proven':False}
