"""Bounded public progress projection. Never constructs or restores a Workbench.

The tree groups existing scoped gates for reading; it creates no acceptance.
An assembly revision sequence is not design ancestry or an adoption record.
"""
import hashlib
import json
import time
from pathlib import Path

from .literature_acceptance import evaluate
from .literature_campaign import bound_file, read


def artifact(root, record):
    if not isinstance(record, dict) or not record.get('path') or not record.get('sha256'):
        return None
    try:
        bound_file(root, record['path'], record['sha256'])
    except (OSError, ValueError, KeyError):
        return None
    return {'path': record['path'], 'sha256': record['sha256']}


def paper_acceptance(root, owner, paper, assembly):
    """Recheck the original seal, live sources, assembly and independent evidence.

    No new checks/solvers or files are generated. A changed input invalidates the
    corresponding existing conclusion through the established evaluator.
    """
    pointer = read(root / 'campaign/acceptance/current.json')
    sealed = read(bound_file(root, pointer['path'], pointer['sha256']))
    previous = next((p for p in sealed.get('papers', [])
                     if p.get('owner') == owner and p.get('paper') == paper), None)
    if not previous:
        return None
    source = previous['source_result']
    current = read(bound_file(root, source['path'], source['sha256']))
    scope = read(root / 'campaign/acceptance' / paper / 'scope-v1.json')
    if scope.get('owner') != owner or scope.get('paper') != paper:
        raise ValueError('PROGRESS_ACCEPTANCE_OWNER_MISMATCH')
    live_assembly = assembly.get('current') or {}
    physical = live_assembly.get('hashes', {}).get('physical_hash')
    native_checks = current.get('evaluation', {}).get('native_checks', [])
    report_artifact = next((a for a in current.get('artifacts', [])
                            if a.get('path', '').endswith('/native-report.json')), None)
    native_report = read(bound_file(root, report_artifact['path'], report_artifact['sha256'])) if report_artifact else {}
    # The accepted packet must be reproduced from the exact original selected
    # native checks; every live source is checked by evaluate().
    current = {**current, 'result_path': source['path'], 'result_sha256': source['sha256'],
               'live_assembly_matches': bool(physical) and
                   native_report.get('assembly_revision') == live_assembly.get('revision') and
                   native_report.get('assembly_physical_hash') == physical}
    workspace = root / 'runtime/participants' / owner
    verified_files = current.get('delivery_integrity', {}).get('verified_files', [])
    if not verified_files or any(not artifact(workspace, f) for f in verified_files):
        current['delivery_integrity'] = {**current.get('delivery_integrity', {}), 'status': 'STALE'}
    evidence = []
    for path in sorted((root / 'campaign/reviews' / paper / 'digital-gates').glob('*.json')):
        row = read(path)
        if isinstance(row, dict) and row.get('schema_version') in (
                'bf-paper-digital-gate-review-v1', 'bf-paper-digital-gate-review-v2'):
            evidence.append({**row, 'artifact': {
                'path': str(path.relative_to(root)),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}})
    return evaluate(root, scope, current, evidence, previous.get('issues', []))


def slim_revisions(assembly):
    rows = {r['revision']: r for r in assembly.get('revisions', [])}
    current = assembly.get('current') or {}
    if current.get('revision') is not None:
        rows[current['revision']] = current
    ordered = sorted(rows.values(), key=lambda r: r['revision'])
    return [{'id': 'assembly-' + str(r['revision']), 'revision': r['revision'],
             'kind': 'assembly', 'parent_id': None,
             'timeline_predecessor': 'assembly-' + str(ordered[i - 1]['revision']) if i else None,
             'title': '装配 v' + str(r['revision']), 'created': r.get('created'),
             'summary': r.get('payload', {}).get('summary') or r.get('operation') or '',
             'hashes': r.get('hashes', {}), 'current': r['revision'] == current.get('revision'),
             'actor': 'Pi' if str(r.get('operation', '')).startswith('pi-') else '来源见操作记录',
             'rollback_supported': False} for i, r in enumerate(ordered)]


def snapshot(workbench, papers, owner):
    """Only original-owner public facts; no all-campaign trace/history load."""
    is_paper = papers.has(owner)
    app = papers.view() if is_paper else workbench
    with app.store.connect() as db:
        conversation = db.execute('SELECT id,status,error,updated FROM conversations WHERE id=?', (owner,)).fetchone()
    if conversation is None:
        raise ValueError('PROGRESS_SESSION_NOT_FOUND')
    revisions = app.assemblies.revisions(owner)
    assembly = {'revisions': revisions,
                'current': next((r for r in reversed(revisions) if r.get('source_valid')), None)}
    value = {'schema_version': 'bf-execution-progress-v1', 'owner': owner,
             'checked_at': time.time(), 'execution': dict(conversation),
             'assembly_revision': (assembly.get('current') or {}).get('revision'),
             'versions': slim_revisions(assembly), 'ancestry_available': False,
             'acceptance': None, 'phase': None, 'public_artifacts': [],
             'physical_validation': 'NOT_TESTED', 'design_lab': None}
    if is_paper:
        root, paper = papers.root, papers.papers[owner]['paper']
        value['paper'] = paper
        acceptance = paper_acceptance(root, owner, paper, assembly)
        value['acceptance'] = acceptance
        if acceptance:
            value['public_artifacts'] = [r for x in acceptance['functional_gates']
                                         if (r := artifact(root, x.get('evidence')))]
            for issue in acceptance['issues']:
                for key in ('artifact', 'closure_evidence'):
                    if (r := artifact(root, issue.get(key))) and r not in value['public_artifacts']:
                        value['public_artifacts'].append(r)
        queue_file = papers.queue / (owner + '.json')
        queue = read(queue_file) if queue_file.is_file() else {}
        if queue.get('owner') not in (None, owner) or queue.get('paper') not in (None, paper):
            raise ValueError('PROGRESS_QUEUE_OWNER_MISMATCH')
        phase = queue.get('phase') or 'engineering-review'
        phase_file = root / 'campaign/recovery' / paper / 'phases' / (phase + '.json')
        # Phase names are operator-owned; reject traversal even if a queue is bad.
        if not phase_file.resolve().is_relative_to((root / 'campaign/recovery' / paper / 'phases').resolve()):
            raise ValueError('PROGRESS_PHASE_SCOPE')
        record = read(phase_file) if phase_file.is_file() else {}
        value['phase'] = {k: record.get(k) for k in (
            'title', 'goal', 'objective', 'scope', 'required_project_kinds', 'acceptance', 'stop_condition')}
        value['phase'].update({'id': phase, 'queue_status': queue.get('status'),
                               'queue_id': queue.get('id'), 'started': queue.get('started')})
        value['native_restore_supported'] = False
    else:
        try:
            lab = workbench.design_lab.view(owner)
        except (ValueError, KeyError):
            lab = None
        if lab and lab.get('task_id'):
            value['design_lab'] = lab
            with app.store.connect() as db:
                rows = list(db.execute('SELECT value FROM design_snapshots WHERE owner=?', (owner,)))
                decisions = [dict(r) for r in db.execute(
                    "SELECT kind,data,created FROM design_events WHERE owner=? AND kind IN ('design_frozen','design_adopted') ORDER BY seq DESC LIMIT 200", (owner,))]
            designs = [json.loads(r['value']) for r in rows]
            designs = [d for d in designs if d.get('task_id') == lab['task_id']]
            value['design_events'] = [{**r, 'data': json.loads(r['data'])} for r in reversed(decisions)]
            events = value['design_events']
            frozen = {e['data']['design_id']: e for e in events if e['kind'] == 'design_frozen'}
            value['versions'] = [{'id': d['design_id'], 'parent_id': d.get('parent'),
                                  'kind': 'design', 'current': d['design_id'] == lab['current_design'],
                                  'title': d['design_id'][:14],
                                  'created': frozen.get(d['design_id'], {}).get('created'), 'task_id': d.get('task_id'),
                                  'actor': frozen.get(d['design_id'], {}).get('data', {}).get('source_author', '来源见冻结记录'),
                                  'hashes': {n: hashlib.sha256(s.encode()).hexdigest() for n, s in d.get('sources', {}).items()},
                                  'rollback_supported': lab['status'] != 'SUBMITTED'} for d in designs]
            value['versions'].sort(key=lambda v: v.get('created') or 0)
            value['ancestry_available'] = any(d.get('parent') for d in designs)
    return value


def public_artifact(workbench, papers, owner, name):
    if not papers.has(owner):
        raise PermissionError('PROGRESS_ARTIFACT_PAPER_SCOPE_REQUIRED')
    data = snapshot(workbench, papers, owner)
    row = next((r for r in data['public_artifacts'] if r['path'] == name), None)
    if row is None:
        raise PermissionError('PROGRESS_ARTIFACT_NOT_PUBLIC')
    return bound_file(papers.root, name, row['sha256'])
