"""Separate controller-owned world and workflow receipts; no shared promotion bit.

Qualification here is component-scoped. It never asserts blind-transfer benefit,
hardware confirmation or automatic permission to launch a formal campaign.
"""
from __future__ import annotations
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash, file_hash
from .compiler import VERSION
from .repair import checked


def receipt(kind, candidate, passed, facts):
    obj = {'schema_version': 'component-qualification-v1', 'kind': kind,
           'candidate_hash': canonical_hash(candidate), 'passed': passed,
           'facts': facts, 'transfer_validated': False, 'authority': 'trusted-controller'}
    obj['content_hash'] = canonical_hash(obj)
    return obj


def qualify_world(candidate, mechanical, evaluator):
    """The evaluator is inaccessible until exact candidate compilation passes."""
    checked(mechanical)
    if mechanical.get('schema_version')!=VERSION or mechanical.get('compiler_hash')!=file_hash(Path(__file__).with_name('compiler.py')):
        raise ValueError('stale or unknown mechanical compiler identity')
    if mechanical['candidate_hash'] != canonical_hash(candidate):
        raise ValueError('mechanical receipt belongs to another candidate')
    if not mechanical['passed']:
        return receipt('world-model', candidate, False, {'stage': 'mechanical-rejected', 'scientific_probes': 0})
    facts = evaluator(candidate)
    required = {'explanation_pass', 'use_pass', 'scope_pass', 'regression_pass', 'protocol_hash'}
    if not required <= facts.keys() or any(type(facts[k]) is not bool for k in required-{'protocol_hash'}):
        raise ValueError('separate science, scope, regression and protocol bindings required')
    if not isinstance(facts['protocol_hash'], str) or not facts['protocol_hash'].startswith('sha256:'):
        raise ValueError('science protocol identity required')
    return receipt('world-model', candidate, all(facts[k] for k in required-{'protocol_hash'}), facts)


def workflow_errors(patch):
    if not isinstance(patch, dict) or patch.get('schema_version') != 'harness-patch-v1' or patch.get('kind') != 'workflow':
        return ['harness-patch-v1 / workflow required']
    policy = patch.get('policy')
    fields = {'order_by', 'descending', 'require_transient_before_submit', 'stop_after_verified'}
    if not isinstance(policy, dict) or set(policy) != fields:
        return ['unexpected or missing workflow fields; reference/qualification edits not allowed']
    if policy['order_by'] not in {'capacitance_f', 'esr_ohm'} or type(policy['descending']) is not bool:
        return ['invalid candidate ordering policy']
    if policy['require_transient_before_submit'] is not True or policy['stop_after_verified'] is not True:
        return ['workflow cannot disable evidence or verified-stop safety invariants']
    return []


def route(patch, candidates, completed, verified):
    problems = workflow_errors(patch)
    if problems:
        raise ValueError('; '.join(problems))
    ids = {c['id'] for c in candidates}
    if not set(completed) <= ids or not set(verified) <= set(completed):
        raise ValueError('verified evidence must bind a completed candidate')
    if verified:
        return {'action': 'submit', 'candidate_id': sorted(verified)[0]}
    field = patch['policy']['order_by']
    ordered = sorted(candidates, key=lambda c: (c[field], c['id']), reverse=patch['policy']['descending'])
    remaining = [c for c in ordered if c['id'] not in completed]
    return {'action': 'transient', 'candidate_id': remaining[0]['id']} if remaining else {'action': 'abstain', 'reason': 'catalogue exhausted without verified evidence'}


def qualify_workflow(patch):
    problems = workflow_errors(patch)
    checks = []
    if not problems:
        candidates = [{'id':'a','capacitance_f':.001,'esr_ohm':10}, {'id':'b','capacitance_f':.002,'esr_ohm':4}]
        checks = [route(patch,candidates,[],[])['action']=='transient',
                  route(patch,candidates,['a'],['a'])=={'action':'submit','candidate_id':'a'},
                  route(patch,candidates,['a'],[])['candidate_id']=='b',
                  route(patch,candidates,['a','b'],[])['action']=='abstain']
    return receipt('workflow', patch, not problems and all(checks), {
        'errors': problems, 'safety_route_checks': checks,
        'scope': 'declarative finite-catalogue routing and evidence safety, not design benefit',
        'world_receipt_dependency': None})


def activated_components(world, world_receipt, workflow, workflow_receipt):
    for candidate, qualification, kind in ((world,world_receipt,'world-model'),(workflow,workflow_receipt,'workflow')):
        checked(qualification)
        if qualification['kind'] != kind or qualification['candidate_hash'] != canonical_hash(candidate):
            raise ValueError('component receipt misbound')
    return {'world-model': world if world_receipt['passed'] else None,
            'workflow': workflow if workflow_receipt['passed'] else None}
