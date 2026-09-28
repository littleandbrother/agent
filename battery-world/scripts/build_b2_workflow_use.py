#!/usr/bin/env python3
"""Replay fixed workflow controls on already-public sealed v2 evidence only."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'packages/python/bfworld/src'))
from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json
from bfworld.campaign.repair import checked, seal
from bfworld.campaign.splits import task_record
from bfworld.campaign.task_context import public_context
from bfworld.campaign.workflow_use import VERSION, CANDIDATE_VERSION, implementation, execute_qualification
from bfworld.coupled.profiled import VERSION as REFERENCE_VERSION


def policy(order_by='capacitance_f', descending=False):
    return {'schema_version': CANDIDATE_VERSION, 'kind': 'workflow',
            'scope': {'source_families': ['rotary'], 'context_versions': ['profiled-predictor-context-v2']},
            'workflow': {'schema_version': 'harness-patch-v1', 'kind': 'workflow', 'policy': {
                'order_by': order_by, 'descending': descending,
                'require_transient_before_submit': True, 'stop_after_verified': True}}}


def build(repo=REPO):
    source_report = checked(json.loads((repo/'docs/b2-development/profiled-report.json').read_text()))
    source = {'profiled_report_hash': source_report['content_hash'],
              'builder_hash': file_hash(Path(__file__)), 'implementation': implementation()}
    root = repo/'.bfworld/workflow-use-controls'/canonical_hash(source).split(':')[1]
    root.mkdir(parents=True, exist_ok=True)
    tasks = list(source_report['registry']['tasks']); evidence = []
    use_ids = [t['task_id'] for t in tasks if t['task_id'].startswith('public-')]
    regression_ids = []
    for t in list(tasks):
        if t['task_id'].startswith('observed-'):
            r = task_record('regression-'+t['task_id'], 'regression', t['physics'],
                            prior_exposure='observed-final', regression_of=t['task_id'])
            tasks.append(r); regression_ids.append(r['task_id'])
    for row in source_report['runs']:
        tid = row['task_id']
        if tid.startswith('observed-'): tid = 'regression-'+tid
        evidence.append({'task_id': tid, 'candidate_id': row['candidate_id'],
                         'artifact': row['artifact'], 'run_hash': row['run_hash']})
    oos = public_context(tasks[0]); oos['source_family'] = 'solar'
    plan = {'schema_version': VERSION, 'purpose': 'engineering-controls',
            'task_manifest_hash': canonical_hash(tasks), 'reference_version': REFERENCE_VERSION,
            'use_ids': use_ids, 'regression_ids': regression_ids, 'baseline': policy(),
            'thresholds': {'min_median_probe_reduction': 1, 'max_false_admissions': 0, 'retain_all_solvable': True},
            'regression_probe_ceiling': {regression_ids[0]: 4, regression_ids[1]: 5, regression_ids[2]: 1},
            'oos_contexts': [oos, {}, None], 'max_reference_observations': len(evidence)}
    variants = [['no-change', policy()], ['capacitance-descending', policy(descending=True)],
                ['esr-ascending', policy(order_by='esr_ohm')]]
    acquisition = {'complete': False, 'source_hash': source_report['content_hash'],
                   'scope': 'Reused public computational observations. Historical acquisition and maintenance cost incomplete.'}
    seal(root/'control-manifest.json', {'source': source, 'tasks': tasks, 'plan': plan,
         'variants': variants, 'acquisition': acquisition})
    reports = []
    for name, candidate in variants:
        r = execute_qualification(candidate, tasks, plan, evidence, acquisition, repo, root/name)
        reports.append({'name': name, 'artifact': str((root/name/'report.json').relative_to(repo)), 'report': r})
    result = {'schema_version': 'public-workflow-use-controls-v1', 'source': source,
              'artifact_root': str(root.relative_to(repo)), 'variants': reports,
              'source_reference_observations': len(evidence), 'new_reference_runs': 0,
              'actual_provider_calls': 0, 'actual_paid_cny': 0,
              'world_receipt_dependency': None, 'agent_generated': False, 'transfer_validated': False,
              'claim_boundary': 'Coordinator-declared public ordering controls, including all negative outcomes; no learned workflow or formal qualification.'}
    result['content_hash'] = canonical_hash(result)
    validate(result, repo)
    write_canonical_json(repo/'docs/b2-development/workflow-use-controls.json', result)
    print(json.dumps({'status': 'pass', 'report_hash': result['content_hash'],
                      'variants': [{**{'name': r['name']}, **r['report']['metrics'],
                                    'controls_pass': r['report']['controls_pass'], 'qualified': r['report']['qualified']}
                                   for r in reports], 'actual_provider_calls': 0}))
    return result


def validate(result, repo=REPO):
    checked(result)
    if (result['source']['implementation'] != implementation() or result['source']['builder_hash'] != file_hash(Path(__file__)) or
            result['source']['profiled_report_hash'] != checked(json.loads((repo/'docs/b2-development/profiled-report.json').read_text()))['content_hash']):
        raise ValueError('stale workflow control source')
    for entry in result['variants']:
        path = (repo/entry['artifact']).resolve()
        if not path.is_relative_to((repo/'.bfworld/workflow-use-controls').resolve()):
            raise ValueError('workflow control artifact path escaped')
        if checked(json.loads(path.read_text())) != entry['report']:
            raise ValueError('workflow control projection mismatch')
        inputs = checked(json.loads(path.with_name('inputs.json').read_text()))
        replay = execute_qualification(inputs['candidate'], inputs['tasks'], inputs['plan'],
            inputs['evidence'], inputs['acquisition'], repo, path.parent)
        if replay != entry['report'] or replay['purpose'] != 'engineering-controls' or replay['qualified']:
            raise ValueError('workflow engineering control was changed or promoted')
    return result


if __name__ == '__main__': build()
