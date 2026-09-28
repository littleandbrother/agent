"""Independent scoped workflow use checks over sealed reference observations.

The routing program sees only public context and already-completed evidence.
The controller owns the full truth table. No world-model receipt is an input.
Replayed policy probes are NOT new experiments or measured Agent savings.
"""
from __future__ import annotations

import json
import math
import statistics
import time
from dataclasses import asdict
from pathlib import Path

from bfworld.kernel.canonical import canonical_hash, file_hash
from bfworld.coupled.profiled import VERSION as REFERENCE_VERSION, verify
from bfworld.coupled.profiled_artifacts import verify_bundle
from .compiler import context_errors
from .qualification import workflow_errors, route, receipt
from .repair import checked, seal, cpu_seconds
from .splits import validate_registry, launch_readiness
from .task_context import public_context, materialize

VERSION = 'workflow-use-qualification-v1'
CANDIDATE_VERSION = 'scoped-workflow-v1'
THRESHOLDS = {'min_median_probe_reduction', 'max_false_admissions', 'retain_all_solvable'}


def candidate_errors(candidate):
    if not isinstance(candidate, dict) or set(candidate) != {'schema_version', 'kind', 'scope', 'workflow'}:
        return ['exact scoped workflow envelope required']
    if candidate['schema_version'] != CANDIDATE_VERSION or candidate['kind'] != 'workflow':
        return ['scoped-workflow-v1 / workflow required']
    scope = candidate['scope']
    if not isinstance(scope, dict) or set(scope) != {'source_families', 'context_versions'}:
        return ['explicit source and context-version scope required']
    for values in scope.values():
        if (not isinstance(values, list) or not values or
                any(not isinstance(v, str) or not v for v in values) or len(values) != len(set(values))):
            return ['scope must use nonempty unique string lists']
    # The wrapper is strict, including the legacy policy envelope. Unknown fields
    # must not become covert authority to edit truth, tasks or thresholds.
    if not isinstance(candidate['workflow'], dict) or set(candidate['workflow']) != {'schema_version', 'kind', 'policy'}:
        return ['unexpected workflow envelope fields']
    return workflow_errors(candidate['workflow'])


def scoped_route(candidate, context, completed, verified):
    problems = candidate_errors(candidate)
    if problems:
        raise ValueError('; '.join(problems))
    scope = candidate['scope']
    if (context_errors(context) or context.get('schema_version') not in scope['context_versions'] or
            context.get('source_family') not in scope['source_families']):
        return {'action': 'abstain', 'reason': 'outside-declared-scope-or-invalid-context'}
    return route(candidate['workflow'], context['candidates'], completed, verified)


def implementation():
    here = Path(__file__).parent
    names = ('workflow_use.py', 'qualification.py', 'compiler.py', 'repair.py', 'splits.py', 'task_context.py')
    result = {name: file_hash(here/name) for name in names}
    result.update({name: file_hash(here.parent/'coupled'/name) for name in
                   ('engine.py', 'profiled.py', 'profiled_artifacts.py')})
    return result


def execution_pins(candidate, tasks, plan, evidence, acquisition):
    return {'candidate_hash': canonical_hash(candidate), 'task_manifest_hash': canonical_hash(tasks),
            'plan_hash': canonical_hash(plan), 'evidence_hash': canonical_hash(evidence),
            'acquisition_hash': canonical_hash(acquisition), 'implementation': implementation()}


def validate_plan(candidate, tasks, plan, evidence, acquisition, protocol=None):
    if candidate_errors(candidate):
        raise ValueError('mechanical workflow rejected before reference access')
    validate_registry(tasks, plan.get('exposed_environment_hashes', []))
    if plan.get('schema_version') != VERSION or plan.get('purpose') not in {'engineering-controls', 'formal-workflow-qualification'}:
        raise ValueError('explicit workflow qualification purpose required')
    if plan.get('task_manifest_hash') != canonical_hash(tasks) or plan.get('reference_version') != REFERENCE_VERSION:
        raise ValueError('workflow task/reference binding mismatch')
    thresholds = plan.get('thresholds')
    if not isinstance(thresholds, dict) or set(thresholds) != THRESHOLDS:
        raise ValueError('explicit workflow thresholds required')
    gain = thresholds['min_median_probe_reduction']
    if type(gain) not in (int, float) or not math.isfinite(gain) or gain < 0:
        raise ValueError('finite nonnegative probe threshold required')
    if thresholds['max_false_admissions'] != 0 or type(thresholds['max_false_admissions']) is not int or thresholds['retain_all_solvable'] is not True:
        raise ValueError('zero false admissions and retained solvability are mandatory')
    if candidate_errors(plan.get('baseline')):
        raise ValueError('valid predeclared scoped baseline required')
    ids = {t['task_id']: t for t in tasks}
    groups = [plan.get(k) for k in ('use_ids', 'regression_ids')]
    if any(not isinstance(g, list) or not g or any(not isinstance(k, str) for k in g) or
           len(g) != len(set(g)) or not set(g) <= ids.keys() for g in groups):
        raise ValueError('nonempty unique known workflow task groups required')
    if set(groups[0]) & set(groups[1]):
        raise ValueError('use and regression groups must be disjoint')
    if any(ids[k]['split'] not in {'development', 'qualification'} for k in groups[0]):
        raise ValueError('blind or confirmation tasks cannot enter workflow use qualification')
    if any(ids[k]['split'] != 'regression' for k in groups[1]):
        raise ValueError('explicit regression identity required')
    ceilings = plan.get('regression_probe_ceiling', {})
    if set(ceilings) != set(groups[1]) or any(type(v) is not int or v < 0 for v in ceilings.values()):
        raise ValueError('explicit per-regression probe ceilings required')
    if not isinstance(plan.get('oos_contexts'), list) or not plan['oos_contexts']:
        raise ValueError('explicit out-of-scope probes required')
    expected = {(k, c['id']) for g in groups for k in g for c in ids[k]['physics']['candidate_designs']}
    actual = [(row['task_id'], row['candidate_id']) for row in evidence]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError('complete unique task/design reference evidence required')
    if type(plan.get('max_reference_observations')) is not int or plan['max_reference_observations'] < len(expected):
        raise ValueError('insufficient declared reference observation budget')
    # Acquisition costs are kept, never reconstructed from a probe count.
    if (not isinstance(acquisition, dict) or set(acquisition) != {'complete', 'source_hash', 'scope'} or
            type(acquisition['complete']) is not bool or not isinstance(acquisition['source_hash'], str) or
            not acquisition['source_hash'].startswith('sha256:') or not acquisition['scope']):
        raise ValueError('explicit acquisition cost attribution required')
    if plan['purpose'] == 'formal-workflow-qualification':
        if protocol is None or not launch_readiness(protocol)['ready']:
            raise ValueError('formal workflow qualification requires owner-approved protocol')
        if protocol.get('workflow_qualification_execution') != execution_pins(candidate, tasks, plan, evidence, acquisition):
            raise ValueError('owner protocol must bind exact workflow, baseline, thresholds, tasks, evidence and costs')
        if any(ids[k]['split'] != 'qualification' or ids[k]['prior_exposure'] != 'never' for k in groups[0]):
            raise ValueError('formal workflow use requires unobserved qualification tasks')
        _window(protocol, current=False)
    return ids


def _window(protocol, *, current):
    window = protocol['shared_budget'].get('new_campaign_execution_window')
    if (not isinstance(window, dict) or set(window) != {'starts_unix_s', 'ends_unix_s'} or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in window.values())):
        raise ValueError('explicit finite workflow qualification window required')
    start, end = window['starts_unix_s'], window['ends_unix_s']
    if not 0 < end-start <= 3600 or (current and not start <= time.time() < end):
        raise ValueError('approved workflow qualification window expired')


def _observations(tasks, evidence, evidence_root):
    ids = {t['task_id']: t for t in tasks}
    base = Path(evidence_root).resolve()
    results = {}
    for row in evidence:
        bundle = (base/row['artifact']).resolve()
        if not bundle.is_relative_to(base):
            raise ValueError('reference evidence path escaped allowed root')
        verify_bundle(bundle)
        run = json.loads((bundle/'run.json').read_text())
        designs, ref, load = materialize(ids[row['task_id']])
        # Sealing reproduced the numerical run. Replay verifies identities and
        # conservation without silently charging/re-running a reference solver.
        verify(run, reproduce=False)
        if (run['content_hash'] != row['run_hash'] or run['design'] != asdict(designs[row['candidate_id']]) or
                run['reference'] != asdict(ref) or run['load_profile'] != asdict(load)):
            raise ValueError('reference evidence misbound to workflow task/design/load')
        results.setdefault(row['task_id'], {})[row['candidate_id']] = {
            'run_hash': row['run_hash'], 'physical_pass': run['physical_mission_pass']['value']}
    return results


def policy_use(candidate, context, observations):
    """Controller replay: private observations are never arguments to the route."""
    completed, verified, steps = [], [], []
    for _ in range(len(context['candidates']) + 1):
        action = scoped_route(candidate, context, completed, verified)
        if action['action'] == 'transient':
            cid = action['candidate_id']
            if cid in completed or cid not in observations:
                raise ValueError('duplicate or unbound workflow probe')
            completed.append(cid)
            facts = observations[cid]
            if facts['physical_pass']:
                verified.append(cid)
            steps.append({**action, **facts})
        elif action['action'] in {'submit', 'abstain'}:
            admitted = (action['action'] == 'submit' and action.get('candidate_id') in verified)
            false_admission = (action['action'] == 'submit' and not admitted)
            return {'success': admitted, 'probes': len(completed), 'steps': steps, 'terminal': action,
                    'false_admission': false_admission}
        else:
            raise ValueError('unsupported workflow action')
    raise ValueError('workflow did not terminate within finite catalogue budget')


def _evaluate(candidate, tasks, plan, observations):
    ids = {t['task_id']: t for t in tasks}
    errors = candidate_errors(candidate)
    rows = []
    if not errors:
        for group in ('use_ids', 'regression_ids'):
            for tid in plan[group]:
                ctx = public_context(ids[tid]); truth = observations[tid]
                baseline = policy_use(plan['baseline'], ctx, truth)
                used = policy_use(candidate, ctx, truth)
                solvable = any(r['physical_pass'] for r in truth.values())
                rows.append({'task_id': tid, 'task_hash': ids[tid]['content_hash'], 'group': group,
                             'solvable': solvable, 'baseline': baseline, 'workflow': used,
                             'baseline_retains_solvability': not solvable or baseline['success'],
                             'solvability_retained': not solvable or used['success'],
                             'probe_reduction': baseline['probes'] - used['probes'] if solvable and
                             baseline['success'] and used['success'] else None})
    scope = [{'context_hash': canonical_hash(ctx), 'abstained': not errors and
              scoped_route(candidate, ctx, [], [])['action'] == 'abstain'} for ctx in plan['oos_contexts']]
    use = [r for r in rows if r['group'] == 'use_ids']
    reg = [r for r in rows if r['group'] == 'regression_ids']
    gains = [r['probe_reduction'] for r in use if r['probe_reduction'] is not None]
    median = statistics.median(gains) if gains else None
    false_admissions = sum(r['workflow']['false_admission'] for r in rows)
    checks = {'mechanical': not errors,
              'baseline_retains_solvability': bool(rows) and all(r['baseline_retains_solvability'] for r in rows),
              'retains_solvability': bool(rows) and all(r['solvability_retained'] for r in rows),
              'use': bool(use) and median is not None and median >= plan['thresholds']['min_median_probe_reduction'],
              'regression': bool(reg) and all(r['solvability_retained'] and
                  r['workflow']['probes'] <= plan['regression_probe_ceiling'][r['task_id']] for r in reg),
              'scope': all(r['abstained'] for r in scope), 'no_false_admission': false_admissions == 0}
    return {'checks': checks, 'rows': rows, 'scope_tests': scope, 'errors': errors,
            'metrics': {'median_probe_reduction': median, 'false_admissions': false_admissions,
                        'lost_solvable_tasks': [r['task_id'] for r in rows if not r['solvability_retained']],
                        'baseline_policy_probes': sum(r['baseline']['probes'] for r in rows),
                        'candidate_policy_probes': sum(r['workflow']['probes'] for r in rows)}}


def execute_qualification(candidate, tasks, plan, evidence, acquisition, evidence_root, root, *, protocol=None):
    """Read existing evidence only. Does not generate tasks, reference runs or API calls."""
    validate_plan(candidate, tasks, plan, evidence, acquisition, protocol)
    identity = {**execution_pins(candidate, tasks, plan, evidence, acquisition),
                'protocol_hash': canonical_hash(protocol) if protocol else None}
    root = Path(root)
    if plan['purpose'] == 'formal-workflow-qualification':
        _window(protocol, current=not (root/'report.json').exists())
    root.mkdir(parents=True, exist_ok=True)
    # The directory is controller-owned; participant inputs have no path access.
    import fcntl
    with (root/'workflow.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        seal(root/'inputs.json', {'identity': identity, 'candidate': candidate, 'tasks': tasks,
             'plan': plan, 'evidence': evidence, 'acquisition': acquisition})
        start, cpu = time.perf_counter(), cpu_seconds()
        observations = _observations(tasks, evidence, evidence_root)
        facts = _evaluate(candidate, tasks, plan, observations)
        checks = {**facts['checks'], 'complete_acquisition_cost': acquisition['complete']}
        result = {'schema_version': VERSION, 'identity': identity, 'purpose': plan['purpose'],
                  'candidate_hash': canonical_hash(candidate), **facts, 'checks': checks,
                  'controls_pass': all(facts['checks'].values()),
                  'qualified': all(checks.values()) and plan['purpose'] == 'formal-workflow-qualification',
                  'world_receipt_dependency': None, 'blind_transfer': False, 'agent_use_benefit_measured': False,
                  'claim_boundary': 'Scoped finite-catalogue ordering on existing computational evidence. '
                  'Not an Agent, learned workflow, independent physics, factorial, transfer or RSI result.'}
        path = root/'report.json'
        if path.exists():
            cached = checked(json.loads(path.read_text()))
            if any(cached.get(k) != v for k, v in result.items()):
                raise ValueError('workflow report projection or identity changed')
            return cached
        return seal(path, {**result, 'cost': {'wall_s': time.perf_counter()-start, 'cpu_s': cpu_seconds()-cpu,
                    'imported_reference_observations': len(evidence), 'new_reference_runs': 0,
                    'provider_calls': 0, 'paid_cny': 0, 'acquisition': acquisition,
                    'total_campaign_cost_complete': False,
                    'scope': 'This evaluation only; historical acquisition and subsequent replay/audit costs are separate.'}})


def component_receipt(report, candidate):
    checked(report)
    if (report.get('schema_version') != VERSION or report['candidate_hash'] != canonical_hash(candidate) or
            report['identity']['candidate_hash'] != canonical_hash(candidate) or
            report['identity']['implementation'] != implementation()):
        raise ValueError('workflow receipt candidate or implementation mismatch')
    expected = all(report['checks'].values()) and report['purpose'] == 'formal-workflow-qualification'
    if report['qualified'] != expected or (expected and not report['identity']['protocol_hash']):
        raise ValueError('workflow qualification cannot be self-promoted')
    return receipt('workflow', candidate, expected, {'use_report_hash': report['content_hash'],
                   'checks': report['checks'], 'metrics': report['metrics'],
                   'protocol_hash': report['identity']['protocol_hash'], 'world_receipt_dependency': None,
                   'purpose': report['purpose'], 'claim_boundary': report['claim_boundary']})
