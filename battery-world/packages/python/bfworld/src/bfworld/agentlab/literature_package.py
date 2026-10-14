"""Public metadata utility. Pi selects designs; this code never designs or grades.

The same standalone file is frozen into the participant apparatus references.
No database, Workbench, solver, provider or protected-evaluator access is needed.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import time


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def local_file(root, name):
    if not isinstance(name, str):
        raise ValueError('PACKAGE_RELATIVE_FILE_REQUIRED')
    rel = PurePosixPath(name)
    if not rel.parts or rel.is_absolute() or '..' in rel.parts:
        raise ValueError('PACKAGE_RELATIVE_FILE_REQUIRED')
    path = root / name
    if (any((root / Path(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts) + 1)) or
            not path.resolve().is_relative_to(root.resolve()) or not path.is_file()):
        raise ValueError('PACKAGE_FILE_UNAVAILABLE_OR_SYMLINK:' + name)
    return path


def job_index(owner, jobs, assembly, eda_project=None):
    """Projection of actual native jobs; excludes model requests and decisions."""
    entries = []
    for job in jobs:
        if job.get('owner') != owner or job.get('engine') != 'engineering-project':
            continue
        result, project = job.get('result') or {}, job.get('project') or {}
        source_path = job.get('parameters', {}).get('project_path')
        base = PurePosixPath(source_path).parent if source_path else None
        entries.append({'id': job['id'], 'owner': owner, 'status': job.get('status'),
            'kind': result.get('kind'), 'readback_passed': result.get('readback_passed'),
            'project_sha256': job.get('project_sha256'),
            'project_identity_valid': bool(project) and sha(encoded(project)) == job.get('project_sha256') == result.get('project_sha256'),
            'project_path': source_path, 'manifest': project.get('manifest'),
            'source_sha256': {str(base / name): sha(text.encode()) for name, text in project.get('sources', {}).items()} if base else {},
            'assembly_revision': job.get('assembly', {}).get('revision'),
            'assembly_physical_hash': job.get('assembly_hashes', {}).get('physical_hash'),
            'functional_passed': False})
    return {'schema_version': 'bf-public-package-job-index-v1', 'owner': owner,
        'assembly_revision': assembly['revision'], 'assembly_physical_hash': assembly['hashes']['physical_hash'],
        'eda_project': eda_project, 'jobs': entries, 'full_product_passed': False, 'physical_verified': False}


def prepare(root, index, recipe, report, contract, created=None):
    root = Path(root).resolve()
    owner = index.get('owner')
    if index.get('schema_version') != 'bf-public-package-job-index-v1' or root.name != owner:
        raise ValueError('PACKAGE_ORIGINAL_WORKSPACE_REQUIRED')
    if (report.get('paper_id') != contract['paper_id'] or report.get('source_identity') != contract['source_identity'] or
            report.get('assembly_revision') != index['assembly_revision'] or
            report.get('assembly_physical_hash') != index['assembly_physical_hash']):
        raise ValueError('PACKAGE_CURRENT_IDENTITY_REQUIRED')
    selected = recipe.get('engineering_jobs')
    unresolved = recipe.get('unresolved_gates')
    if (not isinstance(selected, list) or not selected or any(not isinstance(j, str) for j in selected) or
            len(set(selected)) != len(selected) or not isinstance(unresolved, list) or not unresolved):
        raise ValueError('PACKAGE_EXPLICIT_SELECTION_AND_UNRESOLVED_SCOPE_REQUIRED')
    jobs = {j['id']: j for j in index['jobs']}
    if len(jobs) != len(index['jobs']):
        raise ValueError('PACKAGE_DUPLICATE_INDEX_JOB')
    file_names = recipe.get('files', [])
    eda_names = recipe.get('eda_receipts', [])
    if (not isinstance(file_names, list) or not isinstance(eda_names, list) or
            any(not isinstance(n, str) for n in file_names + eda_names) or
            any(not isinstance(g, str) or not g.strip() for g in unresolved)):
        raise ValueError('PACKAGE_EXPLICIT_FILES_AND_SCOPE_REQUIRED')
    names = set(file_names)
    names.update(['native-report.json', 'delivery/UNVERIFIED.md'])
    bindings = []
    for jid in selected:
        job = jobs.get(jid)
        if (not job or job.get('owner') != owner or job.get('status') != 'SUCCEEDED' or
                job.get('readback_passed') is not True or not job.get('project_identity_valid') or
                not job.get('kind') or not job.get('source_sha256') or
                job.get('assembly_revision') != index['assembly_revision'] or
                job.get('assembly_physical_hash') != index['assembly_physical_hash']):
            raise ValueError('PACKAGE_SELECTED_NATIVE_JOB_UNAVAILABLE:' + jid)
        manifest = local_file(root, job['project_path'])
        if json.loads(manifest.read_text()) != job['manifest']:
            raise ValueError('PACKAGE_SELECTED_MANIFEST_CHANGED:' + jid)
        for name, expected in job['source_sha256'].items():
            if sha(local_file(root, name).read_text().encode()) != expected:
                raise ValueError('PACKAGE_SELECTED_SOURCE_CHANGED:' + name)
        names.add(job['project_path'])
        names.update(job['source_sha256'])
        bindings.append({'job_id': jid, 'kind': job['kind'], 'project_sha256': job['project_sha256']})
    eda = []
    for name in eda_names:
        path = local_file(root, name)
        receipt = json.loads(path.read_text())
        if (receipt.get('owner') != owner or receipt.get('project') != index.get('eda_project') or
                receipt.get('status') != 'SUCCEEDED' or not str(receipt.get('job_id', '')).startswith('eda-')):
            raise ValueError('PACKAGE_EDA_RECEIPT_NOT_CURRENT_OWNER_SUCCESS:' + name)
        eda.append({'job_id': receipt['job_id'], 'path': name, 'sha256': sha(path.read_bytes()),
            'scope': 'Native operation receipt; separate from solver/build jobs and core acceptance'})
        names.add(name)
    if 'delivery/manifest.json' in names or not 1 <= len(names) <= 512:
        raise ValueError('PACKAGE_FILE_SELECTION_INVALID')
    updated = {**report, 'schema_version': 'bf-paper-native-report-v1',
        'jobs': [{'job_id': b['job_id'], 'kind': b['kind']} for b in bindings],
        'eda_jobs': eda, 'gaps': unresolved, 'full_product_passed': False, 'physical_verified': False,
        'metadata_preparation': {'actor': 'frozen common metadata utility', 'selection_actor': 'Pi',
            'created': time.time() if created is None else created, 'engineering_source_edits': 0}}
    report_bytes = encoded(updated)
    files = []
    for name in sorted(names):
        data = report_bytes if name == 'native-report.json' else local_file(root, name).read_bytes()
        files.append({'path': name, 'sha256': sha(data)})
    manifest = {'schema_version': 'bf-paper-native-delivery-v1', 'paper_id': contract['paper_id'],
        'source_identity': contract['source_identity'], 'assembly_revision': index['assembly_revision'],
        'assembly_physical_hash': index['assembly_physical_hash'], 'files': files,
        'trusted_jobs': [{'job_id': b['job_id'], 'project_sha256': b['project_sha256']} for b in bindings],
        'eda_receipts': eda, 'unresolved_gates': unresolved,
        'metadata_preparation': updated['metadata_preparation']}
    return report_bytes, encoded(manifest)


def install(root, operation, report_bytes, manifest_bytes, recovery_inputs=None):
    root = Path(root).resolve()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', operation or ''):
        raise ValueError('PACKAGE_METADATA_OPERATION_REQUIRED')
    # Resolve destination ancestry before any write. Metadata is the only writable
    # output; no engineer-selected source/project/output can be overwritten.
    for name in ['native-report.json', 'delivery/manifest.json', 'delivery/metadata-history', 'delivery/metadata-receipts']:
        rel = PurePosixPath(name)
        if any((root / Path(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts) + 1)):
            raise ValueError('PACKAGE_METADATA_DESTINATION_SYMLINK')
    receipt_dir = root / 'delivery/metadata-receipts'
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / (operation + '.json')
    outputs = {'native-report.json': report_bytes, 'delivery/manifest.json': manifest_bytes}
    if receipt_path.exists():
        if recovery_inputs is None:
            raise ValueError('PACKAGE_METADATA_OPERATION_ALREADY_RECORDED')
        existing = json.loads(receipt_path.read_text())
        if existing['outputs'] != [{'path': name, 'sha256': sha(data)} for name, data in outputs.items()]:
            raise ValueError('PACKAGE_METADATA_OPERATION_CONFLICT')
        for name, data in outputs.items():
            if local_file(root, name).read_bytes() != data:
                raise ValueError('PACKAGE_PREPARED_OUTPUT_CHANGED:' + name)
        return existing
    if recovery_inputs is not None:
        for name, data in outputs.items():
            current = sha((root / name).read_bytes()) if (root / name).is_file() else None
            if current not in {recovery_inputs[name], sha(data)}:
                raise ValueError('PACKAGE_METADATA_RECOVERY_CONFLICT:' + name)
    history = root / 'delivery/metadata-history'
    history.mkdir(parents=True, exist_ok=True)
    previous = []
    for name in outputs:
        target = root / name
        if target.exists():
            old = target.read_bytes()
            saved = history / (sha(old) + '-' + target.name)
            if saved.exists() and saved.read_bytes() != old:
                raise ValueError('PACKAGE_METADATA_HISTORY_CHANGED')
            if not saved.exists():
                saved.write_bytes(old)
            if recovery_inputs is None or sha(old) == recovery_inputs[name]:
                previous.append({'path': str(saved.relative_to(root)), 'sha256': sha(old)})
    if recovery_inputs is not None:
        previous = []
        for name, expected in recovery_inputs.items():
            if expected is None: continue
            saved = history / (expected + '-' + Path(name).name)
            if not saved.is_file() or sha(saved.read_bytes()) != expected:
                raise ValueError('PACKAGE_METADATA_RECOVERY_HISTORY_CHANGED:' + name)
            previous.append({'path': str(saved.relative_to(root)), 'sha256': expected})
    for name, data in outputs.items():
        target = root / name
        tmp = target.with_suffix('.metadata-next')
        if tmp.is_symlink():
            raise ValueError('PACKAGE_METADATA_DESTINATION_SYMLINK')
        tmp.write_bytes(data)
        tmp.replace(target)
    receipt = {'schema_version': 'bf-common-package-metadata-receipt-v1', 'operation': operation,
        'previous': previous, 'outputs': [{'path': name, 'sha256': sha(data)} for name, data in outputs.items()],
        'engineering_source_edits': 0, 'full_product_passed': False, 'physical_verified': False}
    receipt_path.write_bytes(encoded(receipt))
    return receipt


def prepare_candidate(lab, owner, body):
    import fcntl
    directory = lab.root/owner/'metadata-preparations'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _prepare_candidate(lab, owner, body)


def _prepare_candidate(lab, owner, body):
    """Use Pi's frozen selection; explicit overrides remain available."""
    from .design_lab import paper_candidate as pc
    fields = {'action', 'session_id', 'operation_id', 'design_id', 'engineering_jobs',
              'files', 'eda_receipts', 'report_path', 'unresolved_gates'}
    if set(body) - fields:
        raise ValueError('PACKAGE_UNEXPECTED_FIELDS:' + ','.join(sorted(set(body) - fields)))
    operation = body.get('operation_id')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', operation or ''):
        raise ValueError('PACKAGE_METADATA_OPERATION_REQUIRED')
    design = lab.design(owner, pc.working(lab, owner))
    if body.get('design_id') != design['design_id']:
        raise ValueError('PACKAGE_CURRENT_DESIGN_REQUIRED')
    with lab.store.connect() as db:
        if db.execute("SELECT 1 FROM design_operations WHERE owner=? AND status IN ('UNKNOWN','QUEUED','RUNNING','WAITING_NATIVE')", (owner,)).fetchone():
            raise ValueError('PACKAGE_PENDING_OPERATION_REQUIRED_RECONCILIATION')
    assembly = lab.app.assemblies.get(owner)
    workspace = lab.store.root.parent / 'participants' / owner
    defaults = {'engineering_jobs': list(design['selected_jobs']),
                'files': [name for name in design['files'] if name != 'delivery/manifest.json'],
                'eda_receipts': [item['path'] for item in design['native_receipts'].values()]}
    recipe = {key: body.get(key, defaults.get(key, []))
              for key in ('engineering_jobs', 'files', 'eda_receipts', 'unresolved_gates')}
    if any(not isinstance(items, list) or any(not isinstance(item, str) for item in items)
           for items in recipe.values()):
        raise ValueError('PACKAGE_SELECTION_LISTS_REQUIRED')
    if any(j not in design['selected_jobs'] for j in recipe['engineering_jobs']):
        raise ValueError('PACKAGE_JOB_NOT_IN_CURRENT_CANDIDATE')
    for name in recipe['files'] + recipe['eda_receipts']:
        if name not in design['files']:
            raise ValueError('PACKAGE_FILE_NOT_IN_CURRENT_CANDIDATE:' + name)
    report_path = body.get('report_path', 'native-report.json')
    if report_path not in design['files']:
        raise ValueError('PACKAGE_REPORT_NOT_IN_CURRENT_CANDIDATE')
    request_hash = sha(encoded({k:v for k,v in body.items() if k != 'session_id'}))
    target = lab.root / owner / 'metadata-preparations' / (operation + '.json')
    if target.is_file():
        previous = json.loads(target.read_text())
        if previous['request_sha256'] != request_hash:
            raise ValueError('PACKAGE_OPERATION_CONFLICT')
        if previous['assembly_physical_hash'] != assembly['hashes']['physical_hash'] or previous['assembly_revision'] != assembly['revision']:
            raise ValueError('PACKAGE_ASSEMBLY_CHANGED')
        for item in previous['outputs']:
            if sha(local_file(workspace, item['path']).read_bytes()) != item['sha256']:
                raise ValueError('PACKAGE_PREPARED_OUTPUT_CHANGED:' + item['path'])
        # Inputs outside the two metadata outputs remain exact even on retry.
        for name, item in design['files'].items():
            if name not in {'native-report.json', 'delivery/manifest.json'} and sha(pc.safe_file(workspace, name).read_bytes()) != item['sha256']:
                raise ValueError('PACKAGE_INPUT_CHANGED:' + name)
        return previous
    from .design_lab.contracts import sealed
    intent_path = target.with_name(operation + '.intent.json')
    if intent_path.is_file():
        intent = json.loads(intent_path.read_text())
        if intent['request_sha256'] != request_hash or intent['design_id'] != design['design_id']:
            raise ValueError('PACKAGE_OPERATION_CONFLICT')
        if intent['assembly_revision'] != assembly['revision'] or intent['assembly_physical_hash'] != assembly['hashes']['physical_hash']:
            raise ValueError('PACKAGE_ASSEMBLY_CHANGED')
        for name, expected in intent['inputs'].items():
            if sha(pc.safe_file(workspace, name).read_bytes()) != expected:
                raise ValueError('PACKAGE_INPUT_CHANGED:' + name)
        report_bytes, manifest_bytes = intent['report'].encode(), intent['manifest'].encode()
    else:
        pc.verify(lab, owner, design, live=True)
        jobs = [lab.app.engineering.get(owner, j) for j in recipe['engineering_jobs']]
        index = job_index(owner, jobs, assembly, design['eda_project'])
        report = json.loads(local_file(workspace, report_path).read_text())
        contract = json.loads(local_file(workspace, 'contract.json').read_text())
        report_bytes, manifest_bytes = prepare(workspace, index, recipe, report, contract)
        pc.verify(lab, owner, design, live=True)
        intent = {'design_id': design['design_id'], 'request_sha256': request_hash,
            'assembly_revision': assembly['revision'], 'assembly_physical_hash': assembly['hashes']['physical_hash'],
            'inputs': {name: item['sha256'] for name, item in design['files'].items()
                       if name not in {'native-report.json', 'delivery/manifest.json'}},
            'metadata_before': {name: sha((workspace/name).read_bytes()) if (workspace/name).is_file() else None
                                for name in ('native-report.json', 'delivery/manifest.json')},
            'report': report_bytes.decode(), 'manifest': manifest_bytes.decode()}
        sealed(intent_path, intent)
    now = lab.app.assemblies.get(owner)
    if now['revision'] != assembly['revision'] or now['hashes'] != assembly['hashes']:
        raise ValueError('PACKAGE_ASSEMBLY_CHANGED')
    result = install(workspace, operation, report_bytes, manifest_bytes, recovery_inputs=intent['metadata_before'])
    value = {**result, 'schema_version': 'bf-candidate-metadata-preparation-v1',
             'design_id': design['design_id'], 'request_sha256': request_hash,
             'assembly_revision': assembly['revision'], 'assembly_physical_hash': assembly['hashes']['physical_hash'],
             'selected_jobs': recipe['engineering_jobs'], 'next_action': 'freeze metadata outputs',
             'receipt': str(target)}
    sealed(target, value)
    lab.event(owner, 'candidate_metadata_prepared', {'design_id': design['design_id'],
              'operation_id': operation, 'receipt_path': str(target), 'receipt_sha256': pc.sha(target)})
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True)
    parser.add_argument('--recipe', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path.cwd().resolve()
    index = json.loads(local_file(root, args.index).read_text())
    recipe = json.loads(local_file(root, args.recipe).read_text())
    report = json.loads(local_file(root, 'native-report.json').read_text())
    contract = json.loads(local_file(root, 'contract.json').read_text())
    report_bytes, manifest_bytes = prepare(root, index, recipe, report, contract)
    value = install(root, recipe.get('operation_id'), report_bytes, manifest_bytes) if args.apply else {
        'preview': True, 'report_sha256': sha(report_bytes), 'manifest': json.loads(manifest_bytes)}
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
