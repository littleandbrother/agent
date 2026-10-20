"""Operator-sealed reference admission for the new feedback adapter only."""
import json
from pathlib import Path

from ..store import identity
from .repository import file_hash

CONTROLS = {'nominal','delayed-start','no-energy','bad-frame','expired-sample','brownout',
            'nonconvergence','raw-binding','requirements-reuse','unknown-dispatch','same-version-delivery'}


def require(repo, system):
    if system.get('task_definition',{}).get('case_adapter')!='piezo-feedback-v1': return None
    pointer = repo.root/'feedback-qualification/current.json'
    if not pointer.is_file(): raise ValueError('FEEDBACK_REFERENCE_QUALIFICATION_REQUIRED')
    pin=json.loads(pointer.read_text()); path=Path(pin['path'])
    if file_hash(path)!=pin['sha256']: raise ValueError('FEEDBACK_REFERENCE_QUALIFICATION_CHANGED')
    value=json.loads(path.read_text())
    if value['id']!='FQ-'+identity({k:v for k,v in value.items() if k!='id'}) or value['status']!='PASS':
        raise ValueError('FEEDBACK_REFERENCE_QUALIFICATION_FAILED')
    from .repository_feedback_node import environment
    from .repository_task_checks import evaluator_identity
    if value['environment']!=environment() or value['checker']!=evaluator_identity(system):
        raise ValueError('FEEDBACK_REFERENCE_REQUALIFY')
    if set(value['controls'])!=CONTROLS or not all(v is True for v in value['controls'].values()):
        raise ValueError('FEEDBACK_REFERENCE_CONTROLS_REQUIRED')
    for filename,digest in value['evidence'].items():
        if file_hash(path.parent/filename)!=digest: raise ValueError('FEEDBACK_REFERENCE_EVIDENCE_CHANGED')
    return {'qualification_id':value['id'],'protocol':value['protocol'],'path':str(path),'sha256':pin['sha256']}
