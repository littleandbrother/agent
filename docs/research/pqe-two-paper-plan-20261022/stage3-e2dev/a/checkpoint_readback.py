"""Read the unique current D07 initial once; audit four completed D15 cells.

No new scientific execution, theory qualification, provider call, or raw copy.
The remaining cells are reviewed only after their final-output notification.
"""
import hashlib
import importlib.util
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
PLAN = STAGE.parent
ROOT = PLAN.parents[2]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'


def read(path):
    return json.loads(path.read_text())


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class OneRawRead:
    def __init__(self, path):
        self.path, self.reads, self.raw = path, 0, None

    def read_text(self):
        assert self.reads == 0
        self.reads += 1
        text = self.path.read_text()
        self.raw = json.loads(text)
        return text

    def __str__(self):
        return str(self.path)


def compact_review(review):
    """Keep verified facts and sampled timeline; original full raw is canonical."""
    state = dict(review['state'])
    for key in ('timeline', 'resets', 'same_record_retransmissions', 'different_record_sequence_reuse'):
        items = state.pop(key)
        state[key + '_count'] = len(items)
        state[key + '_canonical_identity'] = identity(items)
        state[key + '_sample'] = items if len(items) <= 8 else items[:4] + items[-4:]
    state['reset_mode_counts'] = dict(Counter(x['during'] for x in review['state']['resets']))
    result = {k: v for k, v in review.items() if k not in ('state', 'engineering_model')}
    result['state'] = state
    result['readback_scope'] = 'Independent stored-output readback; full raw read once and hashed in memory. Full replay reconstructed; only compact facts/samples retained here. No solver/evaluator or new integration.'
    return result


def main():
    initial_destination = HERE / 'A-D07-INITIAL-READBACK.json'
    d15_destination = HERE / 'A-D15-FOUR-READBACK.json'
    if initial_destination.exists() or d15_destination.exists():
        raise SystemExit('CHECKPOINT_ALREADY_RECORDED; do not reopen the initial raw')
    free = shutil.disk_usage(ROOT).free
    assert free >= 10_005_000_000
    prospective = read(HERE / 'A-PROSPECTIVE.json')
    tasks = read(CAN / 'studies/pqe20261022/shared/door-tasks.json')
    task = tasks['DOOR-DEV-D07-v1']
    directory = STAGE / 's0/initial-d07'
    public, decision, assessment = [read(directory / f) for f in ('public-result.json', 'decision.json', 'assessment.json')]
    helper_path = CAN / 'studies/pqe20261022/engineering/stage2/native/review_coupled.py'
    spec = importlib.util.spec_from_file_location('a_existing_readback', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    handle = OneRawRead(directory / 'raw.json')
    review = helper.review('e2dev-current-d07-initial', handle, task)
    raw = handle.raw
    science = prospective['current_five_scientific_sources']
    checks = {
        'raw_content_hash': identity({k: v for k, v in raw.items() if k != 'result_sha256'}) == raw['result_sha256'] == public['result_sha256'],
        'full_Task': identity(task) == prospective['task_bindings'][task['task_id']]['Task_sha256'] == raw['task_sha256'] == public['task_sha256'],
        'full_initial_Design': raw['design'] == task['initial_design'] == public['design'] == decision['actual_design'] and identity(raw['design']) == raw['design_sha256'],
        'initial_P': public['problem'] == task['initial_problem'] == decision['problem'],
        'dt': raw['dt_s'] == task['integration']['dt_s'],
        'five_sources': {k: decision['sources'].get(k) for k in science} == science == {k: public['sources'].get(k) for k in science},
        'engineering_model_hash': identity(raw['engineering_model']) == raw['engineering_model_sha256'] == public['engineering_model_sha256'],
        'model_valid_complete': raw['model_valid'] and not raw['domain_errors'] and raw['execution_status'] == 'COMPLETE',
        'service_verdict_matches_host': review['independent_service']['verdict'] == assessment['verdict'] and review['independent_service']['failures'] == assessment['failures'],
        'truth_and_missing_match_host': review['independent_service']['truth'] == assessment['truth'] and review['independent_service']['missing'] == assessment['missed_event_ids'],
        'energy_closure': review['energy']['within_tolerance'], 'force_limit': review['force']['within_limit'],
    }
    tx_brownouts = sum(x['during'] == 'TX' for x in review['state']['resets'])
    initial = {'schema_version': 'pqe-e2dev-a-d07-initial-readback-v1', 'package': prospective['package'],
               'owner': 'campaign-a', 'at_utc': datetime.now(timezone.utc).isoformat(),
               'status': 'INDEPENDENT_CURRENT_D07_INITIAL_REVIEW_COMPLETE' if all(checks.values()) else 'READBACK_MISMATCH_STOP',
               'checks': checks, 'review': compact_review(review),
               'raw_result_sha256': raw['result_sha256'], 'dt_s': raw['dt_s'], 'scientific_sources': science,
               'boot_count': raw['boot_count'], 'TX_brownout_count': tx_brownouts,
               'mechanism_admission': 'PRESENT_CURRENT_SOURCE_TX_BROWNOUT_AND_SERVICE_FAILURE' if tx_brownouts and review['independent_service']['verdict'] == 'FAIL' else 'ORIGINAL_MECHANISM_NOT_ESTABLISHED',
               'claim_boundary': 'Current D07 TX power-failure mechanism is present on this frozen initial; no claim that repair must be joint, that the Task is globally infeasible, or that repeated TX attempts are completed wire retransmissions.',
               'supply_readback_note': 'The stored full-step minimum TX terminal voltage is1.3000004036352033 V. Retained trace loaded-step minimum is1.6595906389877202 V; the trace is projected/sampled and need not retain the exact minimum. Both are below1.8 V brownout. The reported minimum is bound by the validated raw content; this readback does not reconstruct missing integration steps.',
               'resources': {'available_before_bytes': free, 'estimated_peak_additional_bytes': 5_000_000,
                             'retained_output_cap_bytes': 1_000_000, 'output_directory': str(HERE),
                             'A_raw_reads': handle.reads, 'A_raw_copies': 0, 'A_new_scientific_executions': 0,
                             'A_provider_requests': 0, 'A_new_qualifications': 0, 'A_native_solver_runs': 0,
                             'available_after_bytes': shutil.disk_usage(ROOT).free}}
    with initial_destination.open('x') as f:
        f.write(json.dumps(initial, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

    cache = read(HERE / 'INITIAL-CACHE-PROPOSAL.json')
    source = next(x for x in cache['exact_success_cache_entries'] if x['task_id'] == 'DOOR-DEV-D15-v2')
    previous = read(PLAN / 'stage2-d15/a/A-RECEIPT.json')
    source_service = previous['new_coupled_review']['independent_service']
    rows = []
    for i in range(4):
        d = STAGE / 's0/episodes' / ('d15-b' + str(i))
        e, t, reused, public = [read(d / f) for f in ('episode-result.json', 'method-transcript.json', 'actions/01/reused.json', 'actions/01/public-result.json')]
        costs = read(d / 'provider-costs.json')
        task = tasks[e['task_id']]
        action = e['actions'][0]
        key = identity({'task': task, 'design': e['last_design'], 'dt': task['integration']['dt_s'], 'scientific_source': science})
        bound = (reused['exact_key'] == key == source['exact_cache_key'] and reused['source'] == str(Path(source['raw_path']).parent)
                 and reused['source_result_sha256'] == source['source_result_sha256'] == public['result_sha256']
                 and public['task_sha256'] == identity(task) and public['design'] == e['last_design']
                 and {k: public['sources'].get(k) for k in science} == science)
        assert bound and not (d / 'actions/01/raw.json').exists()
        assert e['actual_tools'] == 1 and e['actual_new_numerical_inputs'] == 0
        assert action['actual_input'] == {'operation': 'edit', 'design_patch': {'persistent_queue': True}, 'problem_patch': {}}
        assert e['last_problem'] == task['initial_problem']
        assert all(x['status'] == 'SETTLED' and x['usage'] for x in costs['rows'])
        rows.append({'episode': e['episode'], 'condition': e['condition'],
                     'source_transcript': str(d / 'method-transcript.json'),
                     'termination': t['termination'], 'actual_input': action['actual_input'],
                     'Design_before': task['initial_design'], 'Design_after': e['last_design'],
                     'P_delta': {}, 'actual_P_consumption': 'NOT_OBSERVED_P_UNCHANGED',
                     'exact_cache_bound': bound, 'scientific_result_sha256': public['result_sha256'],
                     'independent_service_from_prior_exact_raw_review': source_service,
                     'model_self_assessment': t['model_conclusion'],
                     'pre_action_prediction': t['steps'][0]['select']['selected_candidate'].get('prediction_or_unknown'),
                     'hypotheses': t['steps'][0]['update'].get('hypotheses', []),
                     'explanation_assessment': 'Supported local committed-sequence continuity and service. No undelivered queue at reset or partial SAVE/ACK recovery is exercised.',
                     'timing_boundary': 'Capture-to-wire is about 8ms; independent external truth-to-receive latency is about56.7ms and also meets2s. These timing origins remain distinct.',
                     'provider_requests': costs['requests'], 'cost_estimate_usd': costs['cache_aware_rate_estimate_usd'],
                     'unknown_or_missing_usage': costs['unknown_or_missing_usage'],
                     'correction_feedback_count': len(t['contract_corrections']['feedback'])})
    d15 = {'schema_version': 'pqe-e2dev-a-d15-four-readback-v1', 'package': prospective['package'],
           'owner': 'campaign-a', 'at_utc': datetime.now(timezone.utc).isoformat(),
           'status': 'D15_FOUR_CELL_READBACK_COMPLETE_NOT_FINAL_TWELVE_CELL_RECEIPT',
           'rows': rows, 'new_raw_reads': 0, 'new_scientific_executions': 0,
           'prior_independent_raw_review': str(PLAN / 'stage2-d15/a/A-RECEIPT.json'),
           'interpretation': 'Four autonomous decisions select the same one-field repair and consume one pre-existing exact scientific result. Service ties do not establish H advantage or four independent numerical repeats.',
           'aggregate_requests': sum(x['provider_requests'] for x in rows),
           'aggregate_cost_estimate_usd': sum(x['cost_estimate_usd'] for x in rows),
           'pending': 'D07/M3 remaining cells; S0 final-input notification will trigger complete twelve-cell review.'}
    with d15_destination.open('x') as f:
        f.write(json.dumps(d15, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'d07_status': initial['status'], 'd07_boot': initial['boot_count'],
                      'd07_TX_brownout': tx_brownouts, 'd07_service': review['independent_service'],
                      'd07_state_counts': {k: v for k, v in initial['review']['state'].items() if k.endswith('_count') or k == 'reset_mode_counts'},
                      'd07_energy': review['energy'], 'd07_supply': review['supply'], 'd07_force': review['force'],
                      'd07_receipt_sha256': hashlib.sha256(initial_destination.read_bytes()).hexdigest(),
                      'd15_status': d15['status'], 'd15_cost': d15['aggregate_cost_estimate_usd'],
                      'd15_receipt_sha256': hashlib.sha256(d15_destination.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
