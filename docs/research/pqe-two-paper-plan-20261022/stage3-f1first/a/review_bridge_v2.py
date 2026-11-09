"""Read one existing bridge raw once; no solver, model, or native execution."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
PLAN = HERE.parents[1]
ROOT = PLAN.parents[2]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
PRIVATE = CAN / 'studies/pqe20261022/f1first/private'
SHARED = PRIVATE.parent / 'shared'
SRC = CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022'
S0 = HERE.parent / 's0'


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def binding(path):
    return {'path': str(path), 'sha256': digest(path)}


def save(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    path.chmod(0o444)


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MemoryRaw:
    def __init__(self, raw):
        self.raw, self.reads = raw, 0

    def read_text(self):
        self.reads += 1
        assert self.reads == 1
        return json.dumps(self.raw, allow_nan=False)

    def __str__(self):
        return 'in-memory-existing-bridge-raw; canonical path bound separately'


def main():
    output = HERE / 'bridge-readback-v2.json'
    marker = HERE / 'bridge-readback-v2-start.json'
    assert not output.exists() and not marker.exists(), 'NO_SECOND_CANONICAL_RAW_READ'
    free_before = shutil.disk_usage(ROOT).free
    assert free_before >= 10_025_000_000
    protocol = read(SHARED / 'f1first-protocol-v2.json')
    registry = read(PRIVATE / 'registry.json')
    freeze = read(PRIVATE / 'freeze.json')
    role = registry['roles']['selection']
    assert digest(role['task_path']) == role['task_file_sha256']
    task = read(role['task_path'])[role['task_json_key']]
    assert identity(task) == role['task_sha256']
    receipt_path = Path(protocol['bridge_validation']['path'])
    assert digest(receipt_path) == protocol['bridge_validation']['sha256']
    receipt = read(receipt_path)
    raw_path = Path(receipt['raw_result']['path'])
    assert str(raw_path) not in {v['raw_path'] for v in registry['roles'].values()}
    public_path = Path(receipt['public_result']['path'])
    assert digest(public_path) == receipt['public_result']['sha256']
    public = read(public_path)
    decision_path = raw_path.parent / 'decision.json'
    decision = read(decision_path)
    original_path = Path(receipt['original_action']['path'])
    assert digest(original_path) == receipt['original_action']['sha256']
    original = read(original_path)['decision']
    qualifier = module_at('a_f1_qualifier_readonly', HERE / 'qualify_inputs.py')
    gate_before = qualifier.usage_gate()
    helper_path = CAN / 'studies/pqe20261022/engineering/stage2/native/review_coupled.py'
    helper = module_at('a_bridge_stored_readback', helper_path)
    save(marker, {'at_utc': datetime.now(timezone.utc).isoformat(),
                  'raw_path': str(raw_path), 'authorized_canonical_raw_reads': 1,
                  'new_execution': 0, 'initial_raw_reads': 0})
    # Exactly one filesystem content read of this canonical raw.
    data = raw_path.read_bytes()
    raw = json.loads(data)
    review = helper.review('f1-task-bridge-validation', MemoryRaw(raw), task)
    review['raw_path'] = str(raw_path)
    assessment_path = raw_path.parent / 'assessment.json'
    assessment = read(assessment_path)
    independent = review['independent_service']
    expected_design = {**task['initial_design'], **original['actual_input']['design_patch']}
    checks = {
        'raw_file_sha256_matches_receipt': hashlib.sha256(data).hexdigest() == receipt['raw_result']['sha256'],
        'raw_object_identity': identity({k: v for k, v in raw.items() if k != 'result_sha256'}) == raw['result_sha256'],
        'original_autonomous_decision_unchanged': decision['decision'] == original,
        'actual_design_is_original_proposal': raw['design'] == decision['actual_design'] == receipt['actual_design'] == expected_design,
        'frozen_Task_identity': raw['task_sha256'] == public['task_sha256'] == role['task_sha256'] == decision['task_sha256'],
        'design_identity': raw['design_sha256'] == public['input_sha256'] == identity(expected_design),
        'engineering_model_identity': identity(raw['engineering_model']) == raw['engineering_model_sha256'] == public['engineering_model_sha256'],
        'complete_valid_model': raw['execution_status'] == public['execution_status'] == 'COMPLETE' and raw['model_valid'] and not raw['domain_errors'],
        'public_raw_result_identity': public['result_sha256'] == raw['result_sha256'],
        'public_factual_fields': all(public['facts'][key] == raw[key] for key in ('activity', 'packets', 'energy', 'peak_handle_force_n', 'minimum_tx_terminal_v', 'program_state')),
        'independent_verdict': independent['verdict'] == assessment['verdict'] == public['public_check']['verdict'],
        'independent_failures_unknown': independent['failures'] == assessment['failures'] == public['public_check']['failures'] and independent['unknown'] == assessment['unknown'] == public['public_check']['unknown'],
        'independent_truth_matches': independent['truth'] == assessment['truth'] and independent['matches'] == assessment['matches'] and independent['missing'] == assessment['missed_event_ids'],
        'independent_receiver': review['receiver']['accepted'] == assessment['receiver_records'] == public['facts']['receiver_records'] and review['unique_received_count'] == public['public_check']['received_count'],
        'independent_commit_RAM_NVM': review['state']['all_commit_and_duration_checks'] and review['state']['final_RAM_NVM_reconstructed'],
        'independent_energy_force': review['energy']['within_tolerance'] and review['force']['within_limit'],
        'same_five_scientific_sources': all(digest(SRC / name) == value == public['sources'][name] for name, value in registry['scientific_sources'].items()),
        'old_catalog_and_split_unchanged': digest(CAN / 'studies/pqe20261022/shared/door-tasks.json') == freeze['source_catalog_unchanged_byte_sha256'] and digest(CAN / 'studies/pqe20261022/shared/split-rules.json') == freeze['old_split_rules_unchanged_byte_sha256'],
        'same_bound_H_history_and_roles': all(digest(ref['path']) == ref['sha256'] for ref in protocol['shared_bindings'].values()),
        'limited_changed_sources_match_protocol': all(digest(path) == values['after'] for path, values in protocol['changed_source_bindings'].items()),
        'original_attempts_preserved': all(digest(ref['path']) == ref['sha256'] for ref in protocol['original_attempt_bindings']),
        'one_science_no_provider_native': receipt['new_numerical_inputs'] == public['usage']['numerical_inputs'] == 1 and receipt['provider_requests'] == receipt['native'] == 0,
    }
    gate_after = qualifier.usage_gate()
    value = {
        'schema': 'pqe-f1first-a-bridge-readback-v2',
        'package': protocol['package'], 'owner': 'campaign-a',
        'visibility': 'HOST_PRIVATE; not for G or selection/formation history',
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'PASS_STORED_CONSUMER_READBACK' if all(checks.values()) else 'FAIL_READBACK_STOP',
        'checks': checks, 'bridge_receipt': binding(receipt_path),
        'raw_file': {'path': str(raw_path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)},
        'raw_result_sha256': raw['result_sha256'], 'public_result': binding(public_path),
        'decision': binding(decision_path), 'assessment': binding(assessment_path),
        'original_action': receipt['original_action'], 'readback_helper': binding(helper_path),
        'independent_readback': review,
        'new_UNKNOWN_usage_gate_before': gate_before, 'new_UNKNOWN_usage_gate_after': gate_after,
        'counts': {'canonical_bridge_raw_reads': 1, 'initial_raw_reads': 0,
                   'new_scientific_executions_by_A': 0, 'provider_requests_by_A': 0,
                   'native_by_A': 0, 'raw_copies': 0},
        'claim_boundary': 'Only the stored original autonomous proposal traversed host/adapter/dynamic consumer. It is apparatus recovery evidence, not a v2 model choice, method selection result, adopted H, transfer result or hardware qualification.',
        'resources': {'available_before_bytes': free_before, 'available_after_bytes': shutil.disk_usage(ROOT).free},
    }
    save(output, value)
    print(json.dumps({'path': str(output), 'sha256': digest(output), 'status': value['status'],
                      'checks': checks, 'service': independent['verdict'],
                      'matched': len(independent['matches']), 'new_executions': 0}, indent=2))


if __name__ == '__main__':
    main()
