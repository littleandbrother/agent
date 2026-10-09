"""Operator proof for separate paper EDA projects; no participant self-binding."""
import json
import re
import subprocess


def validate_binding(record, creation, opened, paper, owner, other_bindings=()):
    if (record.get('schema_version') != 'bf-paper-eda-binding-v1' or
        record.get('paper_id') != paper or record.get('owner') != owner or
        record.get('actor') != 'Codex environment preparation' or
        record.get('writable') is not True):
        raise ValueError('PAPER_EDA_OPERATOR_BINDING_REQUIRED')
    project = record.get('project_uuid')
    if not isinstance(project, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{10,80}', project):
        raise ValueError('PAPER_EDA_PROJECT_IDENTITY')
    if (creation.get('actor') != 'Codex environment preparation' or
        creation.get('created') is not True or creation.get('uuid') != project or
        not str(creation.get('name', '')).startswith('BF-Literature-'+paper+'-Native-') or
        creation.get('previous_current_project') == project):
        raise ValueError('PAPER_EDA_INDEPENDENT_CREATION_REQUIRED')
    response = opened.get('response', {})
    info = response.get('result', {})
    if (opened.get('actor') != 'Codex environment preparation' or
        response.get('ok') is not True or info.get('uuid') != project or
        info.get('friendlyName') != creation['name']):
        raise ValueError('PAPER_EDA_OPEN_READBACK_REQUIRED')
    if any(b.get('project') == project and b.get('owner') != owner for b in other_bindings):
        raise ValueError('PAPER_EDA_SHARED_PROJECT_DENIED')
    return project


def configure_eda(app, root, paper, owner, target):
    """Read operator-only receipts, verify live identity, then bind original owner."""
    from .literature_campaign import read, digest, bound_file, put_once
    from .eda_cli import CLI
    record_path = root/'campaign/eda'/paper/'binding.json'
    if record_path.is_symlink():
        raise ValueError('PAPER_EDA_BINDING_SYMLINK')
    record = read(record_path)
    proofs = []
    for key in ('creation', 'opened'):
        artifact = record.get(key, {})
        path = bound_file(root, artifact.get('path', ''), artifact.get('sha256'))
        if not path.resolve().is_relative_to((root/'campaign/eda'/paper).resolve()):
            raise ValueError('PAPER_EDA_FOREIGN_PROOF_DENIED')
        proofs.append(read(path))
    with app.store.connect() as db:
        bindings = [dict(row) for row in db.execute('SELECT owner,project FROM eda_cli_bindings')]
    project = validate_binding(record, *proofs, paper, owner, bindings)
    proc = subprocess.run([CLI, 'project', 'info', '--project', project],
                          capture_output=True, text=True, timeout=20)
    if proc.returncode != 0:
        raise ValueError('PAPER_EDA_LIVE_PROJECT_UNAVAILABLE')
    live = json.loads(proc.stdout)
    if (live.get('ok') is not True or live.get('result', {}).get('uuid') != project or
        live['result'].get('friendlyName') != proofs[0]['name']):
        raise ValueError('PAPER_EDA_LIVE_PROJECT_MISMATCH')
    prior = app.eda_cli.binding(owner)
    if prior and (prior['project'] != project or not prior['writable']):
        raise ValueError('PAPER_EDA_EXISTING_BINDING_CONFLICT')
    if not prior:
        app.eda_cli.action(owner, {'action': 'bind', 'project_uuid': project,
                                 'authorization': 'Direct user per-paper engineering; independent project only',
                                 'writable': True}, operator=True)
    receipt = {'schema_version': 'bf-paper-eda-live-binding-v1', 'paper_id': paper,
               'owner': owner, 'project_uuid': project, 'actor': 'Codex environment preparation',
               'binding_record_sha256': digest(record_path), 'live_readback': live,
               'native_design_accepted': False, 'paid_model_calls': 0}
    put_once(target/'eda-binding-readback.json', receipt)
    return receipt
