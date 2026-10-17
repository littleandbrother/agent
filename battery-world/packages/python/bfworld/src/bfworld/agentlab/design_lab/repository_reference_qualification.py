"""Admission of the fixed no-Agent apparatus before a participant can run it."""
import json
from pathlib import Path

from ..store import identity
from .repository import file_hash
from .repository_reference_node import environment


def require(repo, system):
    if system.get('task_definition', {}).get('case_adapter') != 'piezo-reference-v1': return None
    pointer = repo.store.root.parent.parent/'task-design/reference-qualification/current.json'
    if not pointer.is_file(): raise ValueError('REFERENCE_QUALIFICATION_REQUIRED')
    pin = json.loads(pointer.read_text()); path = Path(pin['path'])
    if file_hash(path) != pin['sha256']: raise ValueError('REFERENCE_QUALIFICATION_CHANGED')
    value = json.loads(path.read_text())
    if value['status'] != 'PASS' or value['protocol_id'] != identity(value['protocol']):
        raise ValueError('REFERENCE_QUALIFICATION_FAILED')
    if value['environment'] != environment(): raise ValueError('REFERENCE_ENVIRONMENT_REQUALIFY')
    from .repository_task_checks import evaluator_identity
    if value['protocol']['checker'] != evaluator_identity(system): raise ValueError('REFERENCE_CHECKER_REQUALIFY')
    for filename, digest in value['protocol']['sources'].items():
        if file_hash(Path(__file__).with_name(filename)) != digest: raise ValueError('REFERENCE_CHECKER_REQUALIFY')
    for filename, digest in value['evidence'].items():
        if file_hash(path.parent/filename) != digest: raise ValueError('REFERENCE_EVIDENCE_CHANGED')
    if set(value['checks']) != {'nominal','bad-frame','no-energy','changed-firmware-source-reuse'} or not all(value['checks'].values()):
        raise ValueError('REFERENCE_CONTROLS_REQUIRED')
    return {'protocol_id':value['protocol_id'], 'sha256':pin['sha256'], 'scope':'nominal-reference-chain',
            'record':value, 'path':str(path)}


def reference_cache(repo, system):
    pointer = repo.store.root.parent.parent/'task-design/reference-qualification/current.json'
    if not pointer.is_file(): return None
    qualification = require(repo,system)
    if not qualification: return None
    value=qualification['record']; root=Path(qualification['path']).parent
    execution=json.loads((root/'nominal-run.json').read_text())
    if execution['id'] != value['nominal_execution']:raise ValueError('REFERENCE_EXECUTION_IDENTITY')
    blobs=Path(value['artifact_root'])
    for ref in execution['artifacts'].values():
        if file_hash(blobs/ref['sha256']) != ref['sha256']:raise ValueError('REFERENCE_RAW_CHANGED')
    return {'execution':execution,'blobs':blobs}
