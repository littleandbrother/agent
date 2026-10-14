"""Independent digital acceptance over explicitly scoped, version-bound evidence.

Execution and file checks are inputs, never substitutes for functional gates.
This module has no Workbench, database writer, provider or solver dependency.
"""
import hashlib
import json
from pathlib import Path


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(root, artifact):
    try:
        path = root / artifact['path']
        return (not path.is_symlink() and path.resolve().is_relative_to(root.resolve())
                and path.is_file() and _digest(path) == artifact['sha256'])
    except (KeyError, TypeError, ValueError, OSError):
        return False


def evaluate(root, scope, current, evidence=(), issues=()):
    """Facts only. A scope is preregistered; evidence comes from independent checks.

    Evidence must contain gate_id, owner, paper, status, artifact and bindings.
    A binding contains job_id and project_sha256 from the selected native result.
    Every required binding must match. Unchecked, stale and failed are distinct.
    Participant-authored reports are deliberately not accepted as evidence.
    """
    root = Path(root)
    owner, paper = scope['owner'], scope['paper']
    if current.get('owner') != owner or current.get('paper') != paper:
        raise ValueError('ACCEPTANCE_ORIGINAL_OWNER_MISMATCH')
    gates = scope['required_gates']
    ids = [g['id'] for g in gates]
    if not gates or len(ids) != len(set(ids)):
        raise ValueError('ACCEPTANCE_SCOPE_INVALID')
    selected = {c['job_id']: c.get('project_sha256')
                for c in current.get('evaluation', {}).get('native_checks', [])}
    current_seal = {'path': current.get('result_path'), 'sha256': current.get('result_sha256')}
    seal_valid = _bound(root, current_seal)
    live_sources_valid = True
    live_job_valid = {}
    workspace = root / 'runtime/participants' / owner
    for check in current.get('evaluation', {}).get('native_checks', []):
        job_valid = True
        for name, expected in check.get('project_source_sha256', {}).items():
            if not _bound(workspace, {'path': name, 'sha256': expected}):
                job_valid = False
        if check.get('participant_project_path') and check.get('project_manifest'):
            try:
                job_valid &= json.loads((workspace / check['participant_project_path']).read_text()) == check['project_manifest']
            except (OSError, ValueError):
                job_valid = False
        live_job_valid[check['job_id']] = bool(job_valid)
        live_sources_valid &= job_valid
    valid_current = seal_valid and live_sources_valid and current.get('live_assembly_matches') is True
    accepted, rejected = [], []
    v2 = False
    for e in evidence:
        reason = None
        if e.get('owner') != owner or e.get('paper') != paper:
            reason = 'WRONG_ORIGINAL_OWNER'
        elif e.get('actor') != 'independent-checker' or e.get('gate_id') not in ids:
            reason = 'NOT_INDEPENDENT_OR_WRONG_SCOPE'
        elif not _bound(root, e.get('artifact', {})):
            reason = 'EVIDENCE_HASH_MISMATCH'
        elif not any((root / e['artifact']['path']).resolve().is_relative_to((root / prefix).resolve())
                     for prefix in scope.get('review_roots', [])):
            reason = 'UNTRUSTED_REVIEW_LOCATION'
        elif e.get('source_review') and not _bound(root, e['source_review']):
            reason = 'SOURCE_REVIEW_HASH_MISMATCH'
        elif not e.get('bindings') or not all(
                b.get('job_id') in selected and selected[b['job_id']] == b.get('project_sha256')
                for b in e['bindings']):
            reason = 'STALE_NATIVE_BINDING'
        elif any(not _bound(workspace, src) for src in e.get('supporting_sources', [])):
            reason = 'STALE_REVIEW_INPUT'
        elif e.get('status') not in ('PASS', 'FAIL', 'UNEVALUABLE'):
            reason = 'EVIDENCE_STATUS_INVALID'
        else:
            try:
                body = json.loads((root / e['artifact']['path']).read_text())
            except (OSError, ValueError, UnicodeError):
                body = None
            fields = ('paper', 'owner', 'actor', 'gate_id', 'status', 'created', 'bindings', 'resolves', 'supporting_sources', 'source_review')
            if not isinstance(body, dict) or body.get('schema_version') not in ('bf-paper-digital-gate-review-v1','bf-paper-digital-gate-review-v2') or any(
                    body.get(k) != e.get(k) for k in fields):
                reason = 'EVIDENCE_CONTENT_MISMATCH'
            elif body.get('schema_version') == 'bf-paper-digital-gate-review-v2':
                resolutions=body.get('resolved_findings',[])
                if (resolutions!=e.get('resolved_findings',[]) or not isinstance(resolutions,list) or
                    any(not isinstance(r,dict) or r.get('scope')!='identified-defect-only' or
                        r.get('status')!='PASS' or r.get('id') not in body.get('resolves',[]) for r in resolutions)):
                    reason='EVIDENCE_RESOLUTION_SCOPE_INVALID'
            elif e.get('resolved_findings'):
                reason='EVIDENCE_RESOLUTION_VERSION_REQUIRED'
        if reason:
            rejected.append({'gate_id': e.get('gate_id'), 'reason': reason, 'artifact': e.get('artifact')})
        else:
            eligible=body.get('resolved_findings',[]) if body['schema_version']=='bf-paper-digital-gate-review-v2' else []
            accepted.append({**e,'_defect_resolutions':{r['id'] for r in eligible}})
            v2 |= body['schema_version']=='bf-paper-digital-gate-review-v2'
    results = []
    for gate in gates:
        matching = sorted((e for e in accepted if e['gate_id'] == gate['id']), key=lambda x: x.get('created', 0))
        # A later independent recheck may supersede an older failure, with exact bindings.
        latest = matching[-1] if matching else None
        latest_valid = bool(latest) and seal_valid and all(live_job_valid.get(b['job_id']) for b in latest['bindings'])
        status = latest['status'] if latest_valid else 'STALE' if latest else 'NOT_CHECKED'
        results.append({**gate, 'status': status, 'evidence': latest.get('artifact') if latest else None})
    issue_states = []
    for issue in issues:
        if issue.get('owner') != owner or issue.get('paper') != paper:
            raise ValueError('ISSUE_ORIGINAL_OWNER_MISMATCH')
        if not _bound(root, issue.get('artifact', {})):
            raise ValueError('ISSUE_EVIDENCE_HASH_MISMATCH')
        # Changing an input makes a finding require a recheck, never silently closes it.
        bindings = issue.get('bindings', [])
        matches = bool(bindings) and all(selected.get(b.get('job_id')) == b.get('project_sha256')
                                         and b.get('job_id') in selected for b in bindings)
        rechecks = sorted((e for e in accepted if e['gate_id'] == issue['gate_id']),
                          key=lambda e: e.get('created', 0))
        latest_recheck = rechecks[-1] if rechecks else None
        resolved_defect=bool(latest_recheck and issue['id'] in latest_recheck['_defect_resolutions'])
        closures = [latest_recheck] if (latest_recheck and (latest_recheck['status'] == 'PASS' or resolved_defect)
                    and issue['id'] in latest_recheck.get('resolves', [])
                    and latest_recheck.get('created', 0) > issue.get('created', 0)
                    and seal_valid and all(live_job_valid.get(b['job_id']) for b in latest_recheck['bindings'])) else []
        matching_live = matches and seal_valid and all(live_job_valid.get(b['job_id']) for b in bindings)
        state = 'CLOSED' if closures else 'OPEN' if matching_live else 'RECHECK_REQUIRED'
        issue_states.append({**issue, 'state': state, 'closure_evidence': closures[-1]['artifact'] if state == 'CLOSED' else None})
    file_status = current.get('delivery_integrity', {}).get('status', 'NOT_CHECKED')
    if not valid_current:
        file_status = 'STALE'
    unresolved = [i for i in issue_states if i['state'] != 'CLOSED']
    statuses = {g['status'] for g in results}
    full_pass = valid_current and file_status == 'PASS' and statuses == {'PASS'} and not unresolved
    digital_status = ('PASS' if full_pass else 'REPAIR_REQUIRED' if 'FAIL' in statuses or any(
        i['state'] == 'OPEN' and i.get('finding_status') == 'FAIL' for i in unresolved)
        else 'RECHECK_REQUIRED' if not valid_current or any(i['state'] == 'RECHECK_REQUIRED' for i in unresolved)
        else 'CHECKS_PENDING')
    return {'schema_version': 'bf-paper-digital-acceptance-v2' if v2 else 'bf-paper-digital-acceptance-v1', 'paper': paper, 'owner': owner,
            'scope': scope['scope'], 'scope_sha256': hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest(),
            'source_result': current_seal, 'selected_bindings': selected, 'current_sources_valid': valid_current,
            'execution': current.get('execution', {}), 'file_integrity': file_status,
            'functional_gates': results, 'issues': issue_states, 'rejected_evidence': rejected,
            'digital_engineering_status': digital_status, 'full_product_passed': full_pass,
            'stage_delivery_passed': valid_current and file_status == 'PASS',
            'physical_validation': 'NOT_TESTED', 'physical_verified': False,
            'contribution': current.get('contribution', {}), 'agent_improvement_proven': False}
