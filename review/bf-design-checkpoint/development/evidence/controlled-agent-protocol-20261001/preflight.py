#!/usr/bin/env python3
"""Offline contract/receipt checks. Never imports a provider or dispatches a run.

This is a trusted-operator validation layer, not receipt authentication, sandbox
qualification, statistical analysis, or a new participant execution framework.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

SCHEMA = 'bf-controlled-agent-protocol-v1'
DIMENSIONS = ('model_calls', 'input_tokens', 'output_tokens', 'solver_calls',
              'verifier_calls', 'candidate_branches', 'wall_seconds', 'local_cpu_seconds', 'money')
COST_PHASES = ('acquisition', 'generation', 'build_repair', 'qualification',
               'regression', 'transfer', 'rollback', 'solve')
FREEDOMS = {'architecture', 'mechanics', 'circuit', 'firmware', 'cross_domain',
            'candidate_models', 'in_task_tools'}
FAIR = ('model', 'facts_hash', 'history_hash', 'tools_hash', 'retrieval_hash',
        'clarifications_hash', 'edit_freedoms', 'budget', 'selection_rule', 'task_order_hash')
CONTROLS = {'no_op', 'build_failure', 'stale_build', 'pre_import_only',
            'hidden_feedback', 'evaluator_tamper', 'budget_overspend', 'missing_attempt',
            'external_manual_fix', 'rollback', 'removal', 'clean_session_transplant',
            'out_of_scope', 'generation_lineage_break'}
HEX = re.compile(r'^[a-f0-9]{64}$')

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def known(value):
    return isinstance(value, str) and bool(value.strip()) and value.lower() not in {
        'unknown', 'unavailable', 'tbd', 'pending', 'null', 'none'}

def hash_ok(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None

def finite(value, positive=False):
    return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)

def budget_errors(b, where):
    out = []
    if not isinstance(b, dict):
        return [where + ':BUDGET_UNKNOWN']
    for key in DIMENSIONS:
        if not finite(b.get(key), positive=True):
            out.append(where + ':BUDGET_UNKNOWN:' + key)
    for key in DIMENSIONS[:6]:
        if type(b.get(key)) is not int:
            out.append(where + ':INTEGER_LIMIT_REQUIRED:' + key)
    if not known(b.get('currency')): out.append(where + ':CURRENCY_UNKNOWN')
    return out

def model_errors(m):
    if not isinstance(m, dict): return ['MODEL_UNKNOWN']
    out = ['MODEL_UNKNOWN:' + k for k in ('provider', 'model_id', 'revision', 'fingerprint',
            'reasoning', 'seed_policy') if not known(m.get(k))]
    if type(m.get('context_tokens')) is not int or m['context_tokens'] <= 0: out.append('MODEL_CONTEXT_UNKNOWN')
    if type(m.get('vision')) is not bool: out.append('MODEL_VISION_UNKNOWN')
    if not finite(m.get('temperature')): out.append('MODEL_TEMPERATURE_UNKNOWN')
    return out

def outcome_errors(assigned, outcomes):
    """Intent-to-treat denominator: every assigned episode, all retries retained."""
    if not isinstance(assigned, list) or not assigned or len(set(assigned)) != len(assigned):
        return ['ASSIGNMENT_REGISTRY_INVALID']
    if not isinstance(outcomes, list): return ['OUTCOMES_MISSING']
    ids = [r.get('episode_id') for r in outcomes]
    out = []
    if len(ids) != len(set(ids)): out.append('DUPLICATE_EPISODE')
    if set(ids) != set(assigned): out.append('ALL_ATTEMPT_DENOMINATOR_MISMATCH')
    statuses = {'success', 'failure', 'invalid', 'budget_exhausted', 'crashed', 'not_started', 'no_submission', 'abstain'}
    all_attempts = [a for r in outcomes for a in (r.get('attempt_ids') or [])]
    if len(all_attempts) != len(set(all_attempts)): out.append('ATTEMPT_ID_REUSED')
    for r in outcomes:
        if r.get('status') not in statuses: out.append('OUTCOME_UNRESOLVED')
        if not isinstance(r.get('attempt_ids'), list) or not r['attempt_ids']: out.append('ATTEMPT_LINEAGE_MISSING')
        if r.get('cost_complete') is not True: out.append('COST_INCOMPLETE')
        if r.get('status') == 'success' and not hash_ok(r.get('independent_acceptance_hash')):
            out.append('SUCCESS_WITHOUT_ACCEPTANCE')
    return sorted(set(out))

def activation_errors(receipt, expected):
    """Check a trusted supervisor's post-import invocation receipt, not log labels."""
    out = []
    for k in ('harness_source_hash', 'harness_build_hash', 'controller_hash', 'nonce', 'entrypoint'):
        if receipt.get(k) != expected.get(k) or not known(expected.get(k)):
            out.append('ACTIVATION_BINDING:' + k)
    for k in ('fresh_process', 'clean_context', 'post_import', 'invoked'):
        if receipt.get(k) is not True: out.append('ACTIVATION_REQUIRED:' + k)
    if type(receipt.get('pid')) is not int or receipt.get('pid', 0) <= 0 or receipt.get('pid') == expected.get('author_pid'):
        out.append('FRESH_PID_REQUIRED')
    if type(receipt.get('exit_code')) is not int or receipt.get('exit_code') != 0: out.append('ACTIVATION_PROCESS_FAILED')
    if not hash_ok(receipt.get('invocation_output_hash')): out.append('INVOCATION_OUTPUT_UNBOUND')
    if receipt.get('loaded_modules') != expected.get('loaded_modules') or not expected.get('loaded_modules'):
        out.append('LOADED_MODULE_MISMATCH')
    return out

def lineage_errors(records, root_hash):
    seen = {root_hash: 0}
    out = []
    for r in records:
        parent = r.get('parent_hash'); child = r.get('child_hash')
        if parent not in seen or type(r.get('generation')) is not int or r.get('generation') != seen.get(parent, -2) + 1:
            out.append('GENERATION_LINEAGE_BREAK')
        if r.get('author_kind') != 'participant' or r.get('external_manual_edits') != []:
            out.append('NOT_PARTICIPANT_AUTHORED')
        if not hash_ok(child) or child == parent: out.append('NO_NEW_HARNESS')
        if child in seen: out.append('PREVIOUS_HARNESS_IS_ROLLBACK_NOT_GENERATION')
        if r.get('generator_loaded_harness_hash') != parent:
            out.append('GENERATOR_PARENT_NOT_LOADED')
        for key in ('participant_trace_hash', 'patch_hash', 'build_receipt_hash', 'load_receipt_hash', 'public_history_hash', 'generator_invocation_receipt_hash'):
            if not hash_ok(r.get(key)): out.append('LINEAGE_EVIDENCE_MISSING:' + key)
        changed = r.get('changed_paths')
        allowed = r.get('allowed_paths')
        if not isinstance(changed, list) or not changed or not isinstance(allowed, list) or not set(changed) <= set(allowed):
            out.append('HARNESS_EDIT_SCOPE_VIOLATION')
        if isinstance(child, str): seen[child] = r.get('generation', -1)
    return sorted(set(out))

def _checks(plan):
    out = []
    if plan.get('schema_version') != SCHEMA: out.append('SCHEMA_MISMATCH')
    if plan.get('status') != 'prospective-owner-frozen': out.append('PROTOCOL_NOT_FROZEN')
    out += model_errors(plan.get('model'))
    out += budget_errors(plan.get('per_episode_budget'), 'common')
    if not known(plan.get('global_budget_ledger_id')): out.append('GLOBAL_LEDGER_UNKNOWN')
    if not finite(plan.get('global_money_cap'), positive=True): out.append('GLOBAL_MONEY_CAP_UNKNOWN')
    per_episode = plan.get('per_episode_budget') or {}
    if finite(per_episode.get('money')) and finite(plan.get('global_money_cap')) and per_episode['money'] > plan['global_money_cap']:
        out.append('EPISODE_CAP_EXCEEDS_GLOBAL_CAP')
    if type(plan.get('unsettled_costs')) is not int or plan.get('unsettled_costs') != 0: out.append('UNSETTLED_OR_UNKNOWN_COSTS')
    if not isinstance(plan.get('assigned_episodes'), list) or not plan['assigned_episodes']:
        out.append('ASSIGNMENT_REGISTRY_UNFROZEN')
    if plan.get('denominator') != 'all_assigned_episodes_including_failures_and_retries':
        out.append('ALL_ATTEMPT_DENOMINATOR_REQUIRED')
    for k in ('task_manifest_hash', 'world_id', 'facts_hash', 'evaluator_hash',
              'holdout_manifest_hash', 'analysis_plan_hash', 'reuse_source_manifest_hash'):
        if not hash_ok(plan.get(k)): out.append('UNFROZEN_IDENTITY:' + k)
    freeze = plan.get('world_freeze_receipt') or {}
    if freeze.get('world_id') != plan.get('world_id') or not hash_ok(freeze.get('world_id')):
        out.append('WORLD_FREEZE_IDENTITY_MISMATCH')
    for k in ('requirements_owner_frozen', 'formal_trial_admitted'):
        if freeze.get(k) is not True: out.append('WORLD_GATE:' + k)
    reference = plan.get('no_agent_reference') or {}
    if reference.get('world_id') != plan.get('world_id') or reference.get('task_manifest_hash') != plan.get('task_manifest_hash'):
        out.append('REFERENCE_IDENTITY_MISMATCH')
    for k in ('sealed', 'independently_feasible', 'required_acceptance_gates_passed'):
        if reference.get(k) is not True: out.append('REFERENCE_UNKNOWN_OR_UNQUALIFIED:' + k)
    if not hash_ok(reference.get('receipt_hash')): out.append('REFERENCE_RECEIPT_MISSING')
    if reference.get('evidence_kind') != 'independent-computational-reference':
        out.append('REFERENCE_IS_NOT_QUALIFIED_COMPUTATIONAL_EVIDENCE')
    isolation = plan.get('runtime') or {}
    for k in ('runtime_id', 'platform', 'isolation_mechanism'):
        if not known(isolation.get(k)): out.append('RUNTIME_UNKNOWN:' + k)
    for k in ('implementation_hash', 'qualification_receipt_hash'):
        if not hash_ok(isolation.get(k)): out.append('RUNTIME_UNBOUND:' + k)
    for k in ('qualified_on_actual_host', 'private_read_denied', 'external_write_denied',
              'network_policy_verified', 'budget_authority_external', 'clean_process_load_verified'):
        if isolation.get(k) is not True: out.append('RUNTIME_UNQUALIFIED:' + k)
    isolation_scope = isolation.get('qualification_scope')
    if isolation_scope != 'participant-execution': out.append('FIXTURE_IS_NOT_RUNTIME_QUALIFICATION')
    independence = plan.get('independence') or {}
    for k in ('evaluator_immutable', 'holdout_inaccessible', 'separate_evaluator_authority',
              'confirmation_after_all_submissions_frozen', 'no_confirmation_feedback_to_generation',
              'parent_commission_split', 'known_development_evidence_excluded_from_holdout'):
        if independence.get(k) is not True: out.append('INDEPENDENCE_MISSING:' + k)
    if independence.get('participant_writable_objects') != ['design', 'candidate_model', 'declared_harness_sources']:
        out.append('AUTHORITY_BOUNDARY_CHANGED')
    d = plan.get('d_loop') or {}; arms = d.get('arms') or []
    if {a.get('id') for a in arms} != {'strong_generic', 'bf_design'} or len(arms) != 2:
        out.append('D_CORE_ARMS_MISSING')
    else:
        baseline, treatment = sorted(arms, key=lambda a: a['id'])
        for k in FAIR:
            if baseline.get(k) != treatment.get(k): out.append('D_FAIRNESS_MISMATCH:' + k)
            if baseline.get(k) is None: out.append('D_FAIRNESS_UNKNOWN:' + k)
        if set(baseline.get('edit_freedoms') or []) != FREEDOMS: out.append('STRONG_BASELINE_FREEDOM_RESTRICTED')
        if baseline.get('model') != plan.get('model'): out.append('D_MODEL_NOT_COMMON')
        if baseline.get('budget') != plan.get('per_episode_budget'): out.append('D_BUDGET_NOT_COMMON')
        if baseline.get('facts_hash') != plan.get('facts_hash'): out.append('D_FACTS_NOT_COMMON')
        for arm in arms:
            for k in ('facts_hash','history_hash','tools_hash','retrieval_hash','clarifications_hash','task_order_hash','harness_hash','intervention_hash'):
                if not hash_ok(arm.get(k)): out.append('D_UNFROZEN:' + arm['id'] + ':' + k)
            if arm.get('harness_frozen_during_episode') is not True: out.append('D_HARNESS_NOT_FROZEN')
    if d.get('primary_outcome') != 'independent_joint_acceptance_of_publicly_selected_final_design':
        out.append('D_PRIMARY_OUTCOME_UNFROZEN')
    h = plan.get('h_loop') or {}
    if h.get('enabled') is not True: out.append('H_LOOP_MISSING')
    for k in ('h0_hash', 'mutation_scope_hash', 'generation_plan_hash', 'rollback_policy_hash', 'cost_allocation_hash'):
        if not hash_ok(h.get(k)): out.append('H_UNFROZEN:' + k)
    if h.get('arms') != ['frozen_h0_total_budget_matched', 'participant_evolved_h']:
        out.append('H_FROZEN_CONTROL_MISSING')
    if h.get('author_kind') != 'participant' or h.get('external_manual_fixes_are_separate') is not True:
        out.append('H_AUTHORSHIP_NOT_SEPARATED')
    if h.get('later_generation_requires_actual_parent_load') is not True:
        out.append('H_LATER_GENERATION_LOAD_REQUIRED')
    if h.get('cost_phases') != list(COST_PHASES): out.append('H_TOTAL_COST_INCOMPLETE')
    total = h.get('total_budget_by_arm') or {}
    if not total or total.get('frozen_h0_total_budget_matched') != total.get('participant_evolved_h'):
        out.append('H_TOTAL_BUDGET_MISMATCH')
    for a in ('frozen_h0_total_budget_matched', 'participant_evolved_h'):
        out += budget_errors(total.get(a), 'H:' + a)
        arm_budget = total.get(a) or {}
        if finite(arm_budget.get('money')) and finite(plan.get('global_money_cap')) and arm_budget['money'] > plan['global_money_cap']:
            out.append('H_ARM_CAP_EXCEEDS_GLOBAL_CAP:' + a)
    if h.get('unused_budget_policy') != 'report_actual_cost_and_equal_opportunity_envelope_no_synthetic_spend':
        out.append('H_UNUSED_BUDGET_POLICY_MISSING')
    if set(h.get('required_negative_controls') or []) != CONTROLS: out.append('H_NEGATIVE_CONTROLS_INCOMPLETE')
    if h.get('promotion_authority') != 'independent_evaluator_after_frozen_confirmation':
        out.append('H_SELF_PROMOTION_FORBIDDEN')
    approval = plan.get('approval') or {}
    body = {k:v for k,v in plan.items() if k != 'approval'}
    if not known(approval.get('source_id')) or approval.get('protocol_hash') != digest(body):
        out.append('OWNER_APPROVAL_NOT_BOUND')
    return sorted(set(out))

def check_plan(plan):
    try:
        blockers = _checks(plan)
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        blockers = ['MALFORMED_CONTRACT:' + type(exc).__name__]
    return {'schema_version': 'bf-offline-preflight-receipt-v1',
            'contract_complete': not blockers, 'blockers': blockers,
            'live_launch_allowed': False, 'provider_calls': 0,
            'note': 'Offline checks only. No dispatch capability, authenticated authorization, runtime qualification, or scientific result is created.'}

def source_binding_errors(protocol_path, plan):
    """Read only declared non-hidden source/evidence under known task roots."""
    if not isinstance(plan, dict): return ['MALFORMED_CONTRACT:TOP_LEVEL']
    manifest_path = Path(protocol_path).resolve().parent / 'SOURCE-MANIFEST.json'
    if not manifest_path.is_file(): return ['SOURCE_MANIFEST_MISSING']
    if plan.get('reuse_source_manifest_hash') != file_digest(manifest_path):
        return ['SOURCE_MANIFEST_HASH_MISMATCH']
    allowed_roots = [Path('/workspace/shared/current-cache-integration-20261001'),
                     Path('/workspace/shared/bf-development-task-gates-20261001')]
    ledger = Path('/workspace/shared/bf-paper-experiment-protocol-ledger.json')
    out = []
    try:
        manifest = json.loads(manifest_path.read_text())
        for row in manifest['files']:
            path = Path(row['path']).resolve()
            if (any(x.startswith('.') for x in path.parts[1:]) or
                path.suffix not in {'.py', '.ts', '.json', '.md', '.yaml', '.sh'} or
                not (path == ledger or any(path.is_relative_to(r) for r in allowed_roots))):
                out.append('SOURCE_PATH_OUTSIDE_DECLARED_SCOPE'); continue
            if not path.is_file() or file_digest(path) != row['sha256']:
                out.append('SOURCE_BYTES_CHANGED:' + str(path))
    except (OSError, ValueError, KeyError, TypeError):
        out.append('SOURCE_MANIFEST_INVALID')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('protocol', type=Path); p.add_argument('--output', type=Path)
    args = p.parse_args()
    try:
        plan = json.loads(args.protocol.read_text())
        result = check_plan(plan)
        result['blockers'] = sorted(set(result['blockers'] + source_binding_errors(args.protocol, plan)))
        result['contract_complete'] = not result['blockers']
    except (OSError, json.JSONDecodeError) as exc:
        result = {'contract_complete': False, 'live_launch_allowed': False, 'blockers': ['INPUT_UNREADABLE:' + type(exc).__name__]}
    data = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        # Preserve sealed receipts. Regenerate to a new path, never replace one.
        with args.output.open('x') as f: f.write(data)
    print(data, end='')
    return 0 if result['contract_complete'] else 2

if __name__ == '__main__': raise SystemExit(main())
