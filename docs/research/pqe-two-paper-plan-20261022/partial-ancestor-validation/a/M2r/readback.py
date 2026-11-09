"""One canonical artifact readback; no consumer, evaluator, or model call."""
import gzip
import hashlib
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

M = Path(__file__).resolve().parent
R = M.parents[5]
P = M.parent.parent
AL = R / 'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src/bfworld/agentlab'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def source_path(alias):
    if alias.startswith('codebt/'):
        return AL / 'pqe20261024debt' / alias.split('/', 1)[1]
    if alias.startswith('bold/'):
        return AL / 'pqe20261023bold' / alias.split('/', 1)[1]
    return AL / 'pqe20261022' / alias


def main():
    if (M / 'independent-readback.json').exists():
        raise RuntimeError('CANONICAL_READBACK_ALREADY_EXISTS_NO_REPEAT')
    errors = []

    def check(label, value):
        if not value:
            errors.append(label)
        return bool(value)

    freeze = read(M / 'INPUTS-FROZEN.json')
    gate = read(P / 'shared/M2-expression-amendment-admission.json')
    used = read(M / 'admission-used.json')
    counter = read(M / 'counter.json')
    result = read(M / 'mechanism-qualification.json')
    check('freeze_bound', sha(M / 'INPUTS-FROZEN.json') == used['freeze_sha256'] == counter['freeze_sha256'] == gate['freeze']['sha256'])
    check('gate_bound', sha(P / 'shared/M2-expression-amendment-admission.json') == used['gate_sha256'])
    check('runner_bound', sha(M / 'run.py') == used['runner_sha256'])
    check('corrector_bound', sha(R / freeze['corrector_ref']) == freeze['corrector_sha256'])
    check('private_tasks_bound', sha(R / freeze['tasks_private_ref']) == freeze['tasks_private_sha256'])
    check('admitted_inputs_exact', freeze['new_frozen_inputs'] == gate['frozen_inputs'])
    old_checks = {path: sha(R / path) == expected for path, expected in freeze['old_records_preserved'].items()}
    check('original_protected_files_unchanged', all(old_checks.values()))
    source_checks = {alias: sha(source_path(alias)) == expected for alias, expected in used['sources'].items()}
    check('all_current_sources_unchanged', all(source_checks.values()))
    check('all_frozen_path_sources_unchanged', all(sha(R / path) == expected for path, expected in freeze['sources_at_freeze'].items()))
    check('rows_match_result', counter['rows'] == result['rows'])
    check('exact_fifteen_complete', len(counter['rows']) == counter['full_attempts'] == 15 and all(row['status'] == 'COMPLETE' for row in counter['rows']))
    check('unique_order_and_folder', len({row['order'] for row in counter['rows']}) == len({row['folder'] for row in counter['rows']}) == 15)

    checks, evidence = [], []
    for item, row in zip(freeze['new_frozen_inputs'], counter['rows']):
        label = f"{item['order']:02d}-{item['design_name']}-{item['condition_id']}"
        folder = M / row['folder']
        output = folder / 'result'
        inp = read(R / item['path'])
        original = read(R / inp['original_input_ref'])
        reference = read(folder / 'input-reference.json')
        decision = read(output / 'decision.json')
        with gzip.open(output / 'raw.json.gz', 'rt') as stream:
            raw = json.load(stream)
        with gzip.open(output / 'assessment.json.gz', 'rt') as stream:
            assessment = json.load(stream)
        public = read(output / 'public-result.json')
        local = {}

        def local_check(key, value):
            local[key] = check(label + ':' + key, value)

        local_check('exact_frozen_input', sha(R / item['path']) == item['sha256'] == row['input_sha256'] == reference['sha256'] and reference['path'] == item['path'])
        local_check('same_original_design', sha(R / inp['original_input_ref']) == inp['original_input_sha256'] and inp['design'] == original['design'] and digest(inp['design']) == inp['original_frozen_design_sha256'])
        local_check('task_binding', raw['task_sha256'] == decision['task_sha256'] == public['task_sha256'] == digest(inp['task']))
        local_check('design_binding', raw['design'] == decision['actual_design'] == public['design'] == inp['design'] and raw['design_sha256'] == digest(inp['design']))
        local_check('parent_decision_binding', decision['parent_design_sha256'] == digest(inp['parent_design']) and decision['decision'] == inp['decision'])
        local_check('source_binding', decision['sources'] == public['sources'] == reference['sources'] == used['sources'])
        local_check('raw_content_binding', raw['result_sha256'] == digest({k: v for k, v in raw.items() if k != 'result_sha256'}) == public['result_sha256'])
        local_check('engineering_model_binding', raw['engineering_model_sha256'] == digest(raw['engineering_model']) == public['engineering_model_sha256'])
        local_check('gzip_hash_binding', sha(output / 'raw.json.gz') == row['raw_sha256'] and sha(output / 'assessment.json.gz') == row['assessment_sha256'])
        local_check('model_valid_complete', raw['model_valid'] is True and raw['domain_errors'] == [] and raw['execution_status'] == 'COMPLETE')
        local_check('verdict_binding', public['public_check']['verdict'] == assessment['verdict'] == row['verdict'] and public['public_check']['failures'] == assessment['failures'] == row['failures'] and assessment['unknown'] == row['unknown'] == [])
        local_check('count_binding', len(assessment['receiver_records']) == row['received'] == public['public_check']['received_count'] and len(assessment['truth']) == row['truth_events_private'] and len(assessment['missed_event_ids']) == row['missed_private'])
        local_check('activity_energy_binding', dict(Counter(e['action'] for e in raw['activity'])) == row['activity_counts'] and raw['energy'] == row['energy'] and raw['holding_loads'] == row['holding_loads'])
        local_check('physical_qualification_unknown', raw['physical_qualification'] == assessment['physical_qualification'] == 'UNKNOWN')
        local_check('no_paid_calls', public['usage']['paid_model_requests'] == 0 and public['usage']['numerical_inputs'] == 1)
        local_check('within_original_time_caps', 0 < row['elapsed_s'] < row['wall_cap_s'] <= 120 and row['started_epoch'] + row['elapsed_s'] < used['absolute_deadline_epoch'])
        local_check('energy_residual_within_tolerance', abs(assessment['mechanical_residual_j']) <= assessment['energy_tolerance_j'] and abs(assessment['storage_residual_j']) <= assessment['energy_tolerance_j'])
        file_rows = []
        for path in [R / item['path'], folder / 'input-reference.json', output / 'decision.json', output / 'raw.json.gz', output / 'assessment.json.gz', output / 'public-result.json', folder / 'summary-private.json']:
            file_rows.append({'ref': str(path.relative_to(R)), 'sha256': sha(path), 'bytes': path.stat().st_size})
        checks.append({'label': label, 'checks': local, 'files': file_rows})
        # These are source-bound event excerpts, not inferred per-boot RAM/NVM snapshots.
        cold_window = []
        for i, event in enumerate(raw['activity']):
            if 1180 <= event.get('time_s', -1) <= 1210:
                cold_window.append({'raw_pointer': f'#/activity/{i}', 'time_s': event.get('time_s'), 'action': event['action'], **{k: event[k] for k in ['record', 'direction', 'source', 'seq', 'token', 'durable', 'placement', 'boot'] if k in event}})
        evidence.append({'label': label, 'raw_ref': str((output / 'raw.json.gz').relative_to(R)), 'raw_sha256': row['raw_sha256'], 'verdict': row['verdict'], 'failures': row['failures'], 'received': row['received'], 'truth_events_private': row['truth_events_private'], 'missed_private': row['missed_private'], 'sequence_reuse_private': row['sequence_reuse_private'], 'activity_counts': row['activity_counts'], 'energy': row['energy'], 'holding_loads': row['holding_loads'], 'cold_window_event_excerpts_private': cold_window})

    wall = sum(row['elapsed_s'] for row in counter['rows'])
    misses = sum(row['static_geometry_real_misses'] for row in counter['rows'])
    check('actual_wall_sum', math.isclose(wall, counter['full_wall_s'], abs_tol=1e-9))
    check('cheap_accounting', misses == 1 and counter['cheap_numeric'] == 5 + misses and 10 + counter['cheap_numeric'] <= 32)
    check('no_new_cases_or_api', counter['software_cases'] == counter['api_requests'] == 0)
    check('pre_execution_rejection_one', counter['pre_execution_rejections'] == 1 and (M / 'pre-execution-rejection.json').exists())
    check('A_wall_cap', 45 + counter['full_attempts'] == 60 <= gate['qualification_full_cap'] and counter['prior_actual_full_wall_s'] + wall < gate['A_cumulative_full_wall_cap_s'])
    check('holdouts_unexecuted', result['holdouts_executed'] == 0 and all('holdout' not in row['condition_id'] for row in counter['rows']))
    groups = {name: [row for row in counter['rows'] if row['design_name'] == name] for name in freeze['five_design_order']}
    check('finite_gate_recomputed_from_retained_verdicts', all(row['verdict'] == 'PASS' for row in groups['complete-reference']) and all(any(row['verdict'] == 'FAIL' for row in groups[name]) for name in ['parent', 'identity-only', 'holder-only', 'clear-never-neighbor']) and result['status'] == 'QUALIFIED')
    check('distinct_reuse_breakpoint', groups['clear-never-neighbor'][1]['activity_counts'].get('holding_overflow_drop_new') == 4 and all('SPURIOUS_OR_DUPLICATE_EVENT_ID' in row['failures'] for row in groups['clear-never-neighbor']))
    paths = [path for path in M.rglob('*') if path.is_file()]
    available = os.statvfs(R).f_bavail * os.statvfs(R).f_frsize
    inventory = {'files': len(paths), 'logical_bytes': sum(path.stat().st_size for path in paths), 'allocated_bytes': sum(path.stat().st_blocks * 512 for path in paths), 'available_bytes': available, 'retained_cap_bytes': 200_000_000, 'estimated_peak_additional_bytes_at_admission': 1_500_000_000, 'admission_available_bytes': gate['resources']['available_bytes'], 'no_scratch_or_environment_created': True}
    check('storage_cap_and_free_reserve', inventory['allocated_bytes'] < inventory['retained_cap_bytes'] and available > 10_000_000_000)
    report = {'schema': 'M2r-canonical-readback-v1', 'classification': 'PRIVATE_DEVELOPER_REFERENCE', 'at': datetime.now(timezone.utc).isoformat(), 'status': 'PASS_FOR_RETAINED_CANONICAL_RESULTS' if not errors else 'BLOCKED', 'errors': errors, 'full_inputs_read': 15, 'new_consumer_or_evaluator_executions': 0, 'new_software_cases': 0, 'new_cheap_numeric': 0, 'api_requests': 0, 'original_protected_hash_checks': old_checks, 'source_hash_checks': source_checks, 'checks': checks, 'new_actual_cost': result['new_cost'], 'cumulative_A': result['cumulative_A'], 'pre_execution_rejections': 1, 'binding_only_corrections': 1, 'world_numerical_corrections_in_M2r': 0, 'holdouts_executed': 0, 'storage': inventory, 'public_projection_v2_canonical_regression_owner': 'S0; not rerun by A', 'claim_boundary': result['claim_boundary'], 'next_handoff': 'S0 sequentially continues the already-authorized four method conditions and fixed-design final holdouts; reference values and deletion outcomes remain private from B/controllers.'}
    write(M / 'mechanism-evidence-private.json', {'schema': 'M2r-mechanism-retained-evidence-v1', 'classification': 'PRIVATE_DEVELOPER_REFERENCE', 'no_new_execution': True, 'rows': evidence, 'limitations': ['Finite constructed exploratory interaction only.', 'identity-only changes the persistent state bundle, not a seq-only mechanism.', 'holder-only keeps contact_only and cannot isolate persistence while holding read/clear fixed.', 'No complete-reference persistence-off controlled deletion was authorized or run.', 'No experimental attribution among seq, last_direction and queue.', 'Per-boot RAM/NVM snapshots were not logged; event excerpts must not be described as snapshots.', 'No method or ancestor-value claim; final holdouts remain unexecuted by A.']})
    write(M / 'independent-readback.json', report)
    table = ['| Frozen design | Verdicts, capture/reuse/radio | Received |', '|---|---|---|']
    for name in freeze['five_design_order']:
        table.append('| ' + name + ' | ' + '/'.join(row['verdict'] for row in groups[name]) + ' | ' + '/'.join(str(row['received']) for row in groups[name]) + ' |')
    text = '\n'.join(['# M2r private qualification and readback', '', 'PRIVATE: A/S0 only. Do not expose reference values or deletion results to B/controllers.', '', 'M2r is QUALIFIED in the finite frozen three-task family. Canonical artifact readback: ' + report['status'] + '.', '', *table, '', 'All 15 new executions were complete and model valid. New full wall: ' + repr(wall) + ' s. A cumulative: 60 full, ' + repr(result['cumulative_A']['full_wall_s']) + ' s; cheap 16; software cases 3; API 0.', '', 'The pre-execution admission rejection count is 1; the binding-only runner correction count is 1. It occurred before a consumer call. No M2r world numerical correction occurred.', '', 'The complete reference preserves both cold events before MCU recovery, reads and saves the two held records, clears them after SAVE, and delivers all records. The persistent-only bundle has no holder capture of those cold events. Holder-only pays for capture but retains contact_only, so it does not consume the held events through the complete reference route. Clear-never prevents the second cold held record from draining before expiry; reuse-train additionally has four explicit overflow drops. These are source-bound event observations, not inferred logged boot snapshots.', '', 'This establishes a finite exploratory interaction in the declared neighbors. It does not establish global component necessity, seq-only/persistence-only necessity, method benefit, failed-ancestor value, physical qualification, or a valid original preregistered M2 outcome. Original 45 executions, 15 MODEL_DOMAIN UNKNOWN results, NOT_ESTABLISHED conclusion and original exit/counter bytes remain unchanged.', '', 'No new full, cheap numeric, software case or evaluator replay was used by this readback. S0 owns the reserved public-v2 regression and final package ledger. S0 should continue the already-authorized method comparison and final fixed-design holdouts in order.', ''])
    (M / 'READBACK.md').write_text(text)
    write(M / 'FINAL-EXIT.json', {'schema': 'M2r-A-final-exit-v1', 'classification': 'PRIVATE_DEVELOPER_REFERENCE', 'status': 'QUALIFIED_A_SLICE_COMPLETE' if not errors else 'BLOCKED', 'mechanism_qualification_ref': 'mechanism-qualification.json', 'mechanism_qualification_sha256': sha(M / 'mechanism-qualification.json'), 'readback_ref': 'independent-readback.json', 'readback_sha256': sha(M / 'independent-readback.json'), 'evidence_ref': 'mechanism-evidence-private.json', 'evidence_sha256': sha(M / 'mechanism-evidence-private.json'), 'counter_sha256': sha(M / 'counter.json'), 'new_actual_cost': result['new_cost'], 'cumulative_A': result['cumulative_A'], 'pre_execution_rejections': 1, 'binding_only_corrections': 1, 'original_A_exit_unchanged': old_checks, 'holdouts_executed': 0, 'no_further_A_dispatch': True, 'next_owner': 'S0', 'next_authorized_work': report['next_handoff'], 'claim_boundary': report['claim_boundary'], 'errors': errors})
    print(json.dumps({'status': report['status'], 'errors': errors, 'new_full': 15, 'new_full_wall_s': wall, 'cumulative_A': result['cumulative_A'], 'pre_execution_rejections': 1, 'binding_only_corrections': 1, 'storage': inventory, 'readback_sha256': sha(M / 'independent-readback.json'), 'final_exit_sha256': sha(M / 'FINAL-EXIT.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
