"""Explicit physics identities, not integer modulo aliases.

This module creates no blind tasks and contains no reference outcomes. Formal
split selection remains an owner decision. Near-duplicate thresholds likewise
need a protocol; exact-physics rejection alone is not independence proof.
"""
from __future__ import annotations
import math
from bfworld.kernel.canonical import canonical_hash

SPLITS = {'development', 'qualification', 'blind-transfer', 'regression', 'out-of-scope'}
PHYSICS_FIELDS = {'source', 'initial_state', 'load_profile', 'receiver', 'model_card',
                  'label', 'deadline_s', 'candidate_designs', 'reference_version'}
IDENTITY_FIELDS = {'id','task_id','session','device_session','split','name','description','model_id','source_id','reference_version'}


def finite_tree(value):
    if isinstance(value, dict):
        return all(isinstance(k,str) and finite_tree(v) for k,v in value.items())
    if isinstance(value, list):
        return all(finite_tree(v) for v in value)
    return value is None or isinstance(value,(str,bool)) or (type(value) in (int,float) and math.isfinite(value))


def environment_hash(physics):
    if not isinstance(physics, dict) or set(physics) != PHYSICS_FIELDS or not finite_tree(physics):
        raise ValueError('explicit, finite physics fields required; identity/session fields cannot substitute for physics')
    if any(not isinstance(physics[k],dict) or not physics[k] for k in ('source','initial_state','load_profile','receiver','model_card')):
        raise ValueError('empty physical component')
    if type(physics['deadline_s']) not in (int,float) or physics['deadline_s'] <= 0:
        raise ValueError('positive deadline required')
    if not isinstance(physics['label'],str) or not isinstance(physics['reference_version'],str):
        raise ValueError('label and reference version required')
    designs = physics['candidate_designs']
    if not isinstance(designs,list) or not designs:
        raise ValueError('explicit nonempty candidate designs required')
    normalized = []
    for design in designs:
        if not isinstance(design,dict) or not {'capacitance_f','esr_ohm'} <= design.keys():
            raise ValueError('candidate C / ESR required')
        if (type(design['capacitance_f']) not in (int,float) or design['capacitance_f'] <= 0
                or type(design['esr_ohm']) not in (int,float) or design['esr_ohm'] < 0):
            raise ValueError('positive C and nonnegative ESR required')
        normalized.append({k:v for k,v in design.items() if k != 'id'})
    # Candidate IDs and order never make a new physical task.
    def physical_only(value):
        if isinstance(value,dict):
            return {k:physical_only(v) for k,v in value.items() if k not in IDENTITY_FIELDS}
        if isinstance(value,list):
            return [physical_only(v) for v in value]
        if type(value) in (int,float):
            return float(value)
        return value
    normalized = [physical_only(d) for d in normalized]
    if len({canonical_hash(d) for d in normalized}) != len(normalized):
        raise ValueError('duplicate physical candidate designs')
    return canonical_hash(physical_only({**physics, 'candidate_designs': sorted(normalized,key=canonical_hash)}))


def task_record(task_id, split, physics, *, prior_exposure='never', regression_of=None):
    if not isinstance(task_id,str) or not task_id or split not in SPLITS:
        raise ValueError('explicit task_id and split required')
    if prior_exposure not in {'never','public','observed-final'}:
        raise ValueError('exposure identity required')
    if split in {'qualification','blind-transfer'} and prior_exposure != 'never':
        raise ValueError('observed tasks cannot become new qualification or blind tasks')
    obj = {'schema_version':'explicit-scientific-task-v1','task_id':task_id,'split':split,
           'physics':physics,'environment_hash':environment_hash(physics),
           'prior_exposure':prior_exposure,'regression_of':regression_of}
    obj['content_hash'] = canonical_hash(obj)
    return obj


def validate_registry(tasks, exposed_hashes=()):
    ids, environments = {}, {}
    for t in tasks:
        if t['content_hash'] != canonical_hash({k:v for k,v in t.items() if k!='content_hash'}):
            raise ValueError('task hash mismatch')
        expected = task_record(t['task_id'],t['split'],t['physics'],prior_exposure=t['prior_exposure'],regression_of=t['regression_of'])
        if expected != t or t['task_id'] in ids:
            raise ValueError('duplicate or inconsistent task identity')
        if t['split'] in {'qualification','blind-transfer'} and t['environment_hash'] in exposed_hashes:
            raise ValueError('previously exposed physics reused for hidden testing')
        ids[t['task_id']] = t
        environments.setdefault(t['environment_hash'],[]).append(t)
    for t in tasks:
        if t['regression_of'] is not None:
            parent=ids.get(t['regression_of'])
            if t['split']!='regression' or parent is None or parent['environment_hash']!=t['environment_hash']:
                raise ValueError('regression lineage missing or physics differs')
    for group in environments.values():
        if len(group) > 1:
            originals = [t for t in group if t['split'] != 'regression']
            if len(originals) != 1 or originals[0]['split'] not in {'development','out-of-scope'}:
                raise ValueError('different task IDs share physical specification')
            if any(t['regression_of'] != originals[0]['task_id'] for t in group if t['split']=='regression'):
                raise ValueError('repeated physics requires explicit regression lineage')
    return {'status':'pass','tasks':len(tasks),'unique_environments':len(environments),
            'independence_claim':'exact identity audit only; near-duplicate and physical independence unestablished'}


def learning_feedback(record, facts):
    if record['content_hash'] != canonical_hash({k:v for k,v in record.items() if k!='content_hash'}):
        raise ValueError('feedback task identity was modified')
    if record['split'] not in {'development','qualification'}:
        raise ValueError('blind, regression and out-of-scope confirmation cannot enter candidate generation')
    return {'task_id':record['task_id'],'environment_hash':record['environment_hash'],
            'split':record['split'],'facts':facts}


def launch_readiness(protocol):
    """Fail closed on missing human decisions; never synthesize authorization."""
    required = ('owner_approval', 'task_manifest_hash', 'thresholds', 'baselines', 'model_identity',
                'shared_budget', 'success_metric', 'statistical_unit', 'candidate_order_rule')
    missing = [k for k in required if not protocol.get(k)]
    if protocol.get('status') != 'owner-approved':
        missing.append('owner-approved status')
    if protocol.get('paid_dispatch_enabled') is not True:
        missing.append('explicit new-protocol paid dispatch authorization')
    budget = protocol.get('shared_budget',{})
    if not isinstance(budget,dict) or not budget.get('new_campaign_execution_window'):
        missing.append('owner-approved execution window without resetting the original ledger')
    approval = protocol.get('owner_approval')
    expected_hash = canonical_hash({k:v for k,v in protocol.items() if k!='owner_approval'})
    if not isinstance(approval,dict) or approval.get('protocol_hash') != expected_hash or not approval.get('approval_id'):
        missing.append('owner approval receipt bound to exact protocol hash')
    return {'ready':not missing,'missing':missing,'paid_dispatch_allowed':not missing}
