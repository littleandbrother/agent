"""Export the original paper candidate and its already completed check.

No solver, design adoption, or acceptance decision is performed here.
"""
import hashlib
import json
from pathlib import Path
import zipfile

from ..store import canonical, identity
from .contracts import sealed, sha
from . import paper_candidate as pc


def public_evidence(lab, owner, check):
    """Collect the checked public receipts so an exported ZIP is self-contained."""
    task = lab.task(owner)
    root = Path(task['environment']['root'])
    files, references = {}, []
    check_dir = lab.root / owner / 'checks' / check['check_id']

    def include(ref, kind):
        if not ref:
            return None
        source = pc.safe_file(root, ref['path'])
        allowed = (source.suffix == '.json' and (
            source.resolve().is_relative_to((root / 'campaign/reviews/P01').resolve()) or
            (kind == 'source-review' and source.resolve().is_relative_to((root / 'deployment').resolve())) or
            (kind == 'current-input' and source == check_dir / 'current-input.json') or
            (kind == 'scope' and source == root / task['environment']['scope']['path'])))
        if not allowed:
            raise ValueError('PAPER_DELIVERY_PUBLIC_REVIEW_REQUIRED')
        if sha(source) != ref.get('sha256'):
            raise ValueError('PAPER_DELIVERY_REVIEW_HASH_CHANGED')
        name = 'evidence/artifacts/' + ref['path']
        if source.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('PAPER_DELIVERY_REVIEW_SIZE')
        files[name] = source
        references.append({'kind': kind, 'original_path': ref['path'],
                           'package_path': name, 'sha256': ref['sha256']})
        return json.loads(source.read_text())

    include(task['environment'].get('scope'), 'scope')
    acceptance = check['acceptance']
    include(acceptance.get('source_result'), 'current-input')
    for gate in acceptance.get('functional_gates', []):
        body = include(gate.get('evidence'), 'gate')
        if body is not None:
            if (body.get('owner') != owner or body.get('paper') != 'P01' or
                    body.get('actor') != 'independent-checker' or body.get('gate_id') != gate['id']):
                raise ValueError('PAPER_DELIVERY_REVIEW_IDENTITY')
            include(body.get('source_review'), 'source-review')
    for issue in acceptance.get('issues', []):
        include(issue.get('artifact'), 'issue')
        include(issue.get('closure_evidence'), 'closure')
    if len(files) > 512 or sum(p.stat().st_size for p in files.values()) > 64 * 1024 * 1024:
        raise ValueError('PAPER_DELIVERY_REVIEW_SIZE')
    return files, {'schema_version': 'bf-public-delivery-evidence-index-v1',
                   'owner': owner, 'check_id': check['check_id'], 'references': references,
                   'physical': 'NOT_TESTED'}


def checked(lab, owner, check_id):
    if (not isinstance(check_id, str) or not check_id.startswith('check-') or
            len(check_id) != 26 or any(c not in '0123456789abcdef' for c in check_id[6:])):
        raise ValueError('PAPER_CHECK_ID_REQUIRED')
    path = lab.root / owner / 'checks' / check_id / 'check.json'
    if not path.is_file() or path.is_symlink():
        raise ValueError('PAPER_COMPLETED_CHECK_REQUIRED')
    value = json.loads(path.read_text())
    task = lab.task(owner)
    if (value.get('schema_version') != 'bf-paper-candidate-check-v1' or
            value.get('task_id') != task['task_id'] or value.get('check_id') != check_id or
            value.get('design_id') != pc.working(lab, owner)):
        raise ValueError('PAPER_CHECK_CURRENT_CANDIDATE_REQUIRED')
    if value.get('pending_operations'):
        raise ValueError('PAPER_PENDING_OPERATION_READ_BEFORE_RETRY')
    if (value.get('scope_source_sha256') != task['environment']['scope']['sha256'] or
            value.get('evaluator_sha256') != task['contract']['validation_id']):
        raise ValueError('PAPER_CHECK_ENVIRONMENT_MISMATCH')
    # The check receipt is independently recorded, not a participant file.
    with lab.store.connect() as db:
        events = [json.loads(r[0]) for r in db.execute(
            "SELECT data FROM design_events WHERE owner=? AND kind='candidate_checked'", (owner,))]
    if not any(e.get('check_id') == check_id and e.get('design_id') == value['design_id'] and
               e.get('receipt_sha256') == sha(path) for e in events):
        raise ValueError('PAPER_CHECK_RECEIPT_NOT_RECORDED')
    return path, value


def submit(lab, owner, check_id, rationale, operator=False):
    if operator:
        raise PermissionError('PAPER_SUBMISSION_PI_REQUIRED')
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 4000:
        raise ValueError('SUBMISSION_RATIONALE_REQUIRED')
    task = lab.task(owner)
    design = lab.design(owner, pc.working(lab, owner))
    pc.verify(lab, owner, design, live=True)
    check_path, check = checked(lab, owner, check_id)
    with lab.store.connect() as db:
        if db.execute("SELECT 1 FROM design_operations WHERE owner=? AND status IN ('RUNNING','UNKNOWN','WAITING_NATIVE')", (owner,)).fetchone():
            raise ValueError('PAPER_PENDING_OPERATION_READ_BEFORE_RETRY')
        authors = [json.loads(r[0]) for r in db.execute(
            "SELECT data FROM design_events WHERE owner=? AND kind='design_frozen'", (owner,))]
    receipt = {'schema_version': 'bf-paper-design-submission-v1', 'owner': owner,
        'paper': 'P01', 'task_id': task['task_id'], 'design_id': design['design_id'],
        'revision': task['revision'], 'check_id': check_id, 'check_sha256': sha(check_path),
        'rationale': rationale, 'acceptance': check['acceptance'],
        'scope': 'same-version digital engineering review', 'physical': 'NOT_TESTED',
        'attribution': {'design_source': next((e['source_author'] for e in reversed(authors)
            if e.get('design_id') == design['design_id']), 'recorded original source'),
            'engineering_jobs': 'original-owner native receipts',
            'environment_and_checker': 'Codex', 'method_gain': 'NOT_EVALUATED'}}
    receipt['submission_id'] = 'S-' + identity(receipt)
    directory = lab.root / owner / 'deliveries' / receipt['submission_id']
    directory.mkdir(parents=True, exist_ok=True)
    sealed(directory / 'submission.json', receipt)
    sealed(directory / 'task-contract.json', task['contract'])
    sealed(directory / 'environment.json', task['environment'])
    sealed(directory / 'snapshot.json', design)
    sealed(directory / 'check.json', check)
    inputs = lab.root / owner / 'designs' / design['design_id'] / 'inputs'
    def copy_file(source, relative):
        data = source.read_bytes()
        dest = directory / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.read_bytes() != data:
            raise ValueError('DELIVERY_IMMUTABLE_CONFLICT')
        if not dest.exists():
            dest.write_bytes(data)
    for name in design['files']:
        copy_file(pc.safe_file(inputs, name), 'candidate/' + name)
    evidence_files, evidence_index = public_evidence(lab, owner, check)
    for name, source in evidence_files.items():
        copy_file(source, name)
    sealed(directory / 'evidence/index.json', evidence_index)
    for jid, binding in design['selected_jobs'].items():
        job = lab.app.engineering.get(owner, jid)
        if (job['status'] != 'SUCCEEDED' or identity(job.get('result')) != binding['result_sha256'] or
                job.get('project_sha256') != binding['project_sha256']):
            raise ValueError('PAPER_DELIVERY_JOB_BINDING_CHANGED')
        selected_path = job.get('parameters', {}).get('project_path')
        if (selected_path not in design['projects'] or
                design['projects'][selected_path]['project_sha256'] != job['project_sha256']):
            raise ValueError('PAPER_DELIVERY_JOB_SOURCE_MISMATCH: ' + jid)
        sealed(directory / 'jobs' / jid / 'receipt.json', job)
        outputs = (job.get('result') or {}).get('outputs', [])
        if not outputs:
            raise ValueError('PAPER_DELIVERY_JOB_OUTPUT_REQUIRED')
        for item in outputs:
            source = pc.safe_file(lab.store.root.parent / 'engineering' / jid, item['name'])
            if sha(source) != item['sha256']:
                raise ValueError('PAPER_DELIVERY_JOB_OUTPUT_CHANGED')
            copy_file(source, 'jobs/' + jid + '/outputs/' + item['name'])
    manifest = {'schema_version': 'bf-paper-candidate-delivery-v1',
        'owner': owner, 'design_id': design['design_id'], 'check_id': check_id,
        'files': {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*'))
            if p.is_file() and p.name not in ('delivery-manifest.json', 'P01-digital-review.zip')},
        'acceptance': check['acceptance'], 'physical': 'NOT_TESTED'}
    sealed(directory / 'delivery-manifest.json', manifest)
    package = directory / 'P01-digital-review.zip'
    if not package.exists():
        with zipfile.ZipFile(package, 'x', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted([*manifest['files'], 'delivery-manifest.json']):
                info = zipfile.ZipInfo(name, date_time=(2026, 10, 14, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, (directory / name).read_bytes())
    verify_package(directory, receipt)
    pc.verify(lab, owner, design, live=True)
    with lab.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT revision,intent,submission FROM design_tasks WHERE owner=?', (owner,)).fetchone()
        if current['revision'] != task['revision'] or json.loads(current['intent']).get('working_design', task['current_design']) != design['design_id']:
            raise ValueError('SUBMISSION_STALE_REVISION')
        if not current['submission'] or json.loads(current['submission']) != receipt:
            intent = {'kind': 'CONTINUE', 'working_design': design['design_id'], 'rationale': rationale}
            db.execute("UPDATE design_tasks SET submission=?,status='REVIEW_SUBMITTED',intent=? WHERE owner=?",
                (canonical(receipt), canonical(intent), owner))
            lab.event(owner, 'task_submitted', {'submission_id': receipt['submission_id'],
                'design_id': design['design_id'], 'check_id': check_id, 'zip_sha256': sha(package),
                'scoped_status': check['acceptance']['digital_engineering_status']}, db)
            lab.event(owner, 'candidate_decision', intent, db)
    return {**receipt, 'package_path': str(package), 'zip_sha256': sha(package),
            'file_count': len(manifest['files']), 'workflow_status': 'REVIEW_SUBMITTED'}


def verify_package(directory, receipt):
    package = directory / 'P01-digital-review.zip'
    if not package.is_file() or package.is_symlink():
        raise ValueError('DELIVERY_ZIP_MISSING')
    with zipfile.ZipFile(package) as archive:
        if archive.testzip() is not None:
            raise ValueError('DELIVERY_ZIP_CORRUPT')
        if json.loads(archive.read('submission.json')) != receipt:
            raise ValueError('DELIVERY_RECEIPT_TAMPER')
        manifest = json.loads(archive.read('delivery-manifest.json'))
        if manifest['design_id'] != receipt['design_id'] or manifest['check_id'] != receipt['check_id']:
            raise ValueError('DELIVERY_DESIGN_MISMATCH')
        if len(archive.namelist()) != len(set(archive.namelist())) or set(archive.namelist()) != set(manifest['files']) | {'delivery-manifest.json'}:
            raise ValueError('DELIVERY_FILE_SET_MISMATCH')
        for name, digest in manifest['files'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest or sha(pc.safe_file(directory, name)) != digest:
                raise ValueError('DELIVERY_READBACK_FAILED')
    return package


def delivery(lab, owner):
    task = lab.task(owner)
    receipt = task['submission']
    if not receipt or receipt.get('schema_version') != 'bf-paper-design-submission-v1':
        raise ValueError('DESIGN_NOT_SUBMITTED')
    if receipt['design_id'] != pc.working(lab, owner) or receipt['revision'] != task['revision']:
        raise ValueError('DELIVERY_STALE_REVISION')
    check_path, check = checked(lab, owner, receipt['check_id'])
    if sha(check_path) != receipt['check_sha256'] or check['acceptance'] != receipt['acceptance']:
        raise ValueError('DELIVERY_CHECK_TAMPER')
    directory = lab.root / owner / 'deliveries' / receipt['submission_id']
    package = verify_package(directory, receipt)
    with lab.store.connect() as db:
        events = [json.loads(r[0]) for r in db.execute(
            "SELECT data FROM design_events WHERE owner=? AND kind='task_submitted'", (owner,))]
    if not any(e.get('submission_id') == receipt['submission_id'] and e.get('zip_sha256') == sha(package) for e in events):
        raise ValueError('DELIVERY_ZIP_TAMPER')
    return package
