"""Read one new D15 raw; independently review facts without executing apparatus.

Uses the previously qualified stdlib-only A readback helper, never a simulator.
Only writes A-RECEIPT.json. Existing initial evidence comes from its A receipt.
"""
import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
PLAN = STAGE.parent
ROOT = PLAN.parents[2]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
HELPER = CAN / 'studies/pqe20261022/engineering/stage2/native/review_coupled.py'
SCIENCE = ('door_model.py', 'door_program.py', 'engineering.py', 'executor.py', 'evaluator.py')


def read(path):
    return json.loads(path.read_text())


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class OneRawRead:
    """Expose one filesystem read to the helper and retain the parsed input."""
    def __init__(self, path):
        self.path, self.reads, self.value = path, 0, None

    def read_text(self):
        assert self.reads == 0, 'New raw may be read only once in this review'
        self.reads += 1
        text = self.path.read_text()
        self.value = json.loads(text)
        return text

    def __str__(self):
        return str(self.path)


def main():
    free_before = shutil.disk_usage(ROOT).free
    peak, retained_cap = 5_000_000, 1_000_000
    assert free_before >= 10_000_000_000 + peak
    prospective = read(HERE / 'A-PROSPECTIVE.json')
    tasks = read(CAN / 'studies/pqe20261022/shared/door-tasks.json')
    task = tasks['DOOR-DEV-D15-v2']
    materials = read(CAN / 'studies/pqe20261022/shared/d15-public-materials.json')
    prior_receipt_path = PLAN / 'stage2-engineering/a/A-RECEIPT.json'
    initial = next(x for x in read(prior_receipt_path)['coupled_review'] if x['case'] == 'd15-initial')
    batch = read(STAGE / 's0/batch-result.json')
    episodes = {}
    for name in ('generic', 'full-h'):
        d = STAGE / 's0/episodes' / ('d15-' + name)
        episodes[name] = {
            'path': d, 'episode': read(d / 'episode-result.json'),
            'transcript': read(d / 'method-transcript.json'),
            'costs': read(d / 'provider-costs.json'),
            'public': read(d / 'actions/01/public-result.json'),
        }
    g, h = episodes['generic'], episodes['full-h']
    gd = read(g['path'] / 'actions/01/decision.json')
    reused = read(h['path'] / 'actions/01/reused.json')
    assert not (h['path'] / 'actions/01/raw.json').exists()
    assert g['transcript']['initial_state'] == h['transcript']['initial_state']
    assert g['transcript']['initial_state']['task'] == materials[task['task_id']]
    assert g['transcript']['initial_state']['problem'] == prospective['initial']['P']
    assert g['transcript']['initial_state']['design'] == task['initial_design']
    assert identity(task) == prospective['initial']['task_sha256'] == gd['task_sha256']
    assert gd['actual_design'] == reused['actual_design'] == g['public']['design'] == h['public']['design']
    assert gd['actual_design'] == {**task['initial_design'], 'persistent_queue': True}
    sources = {k: gd['sources'][k] for k in SCIENCE}
    assert sources == prospective['scientific_sources']['recorded']
    assert sources == {k: g['public']['sources'][k] for k in SCIENCE} == {k: h['public']['sources'][k] for k in SCIENCE}
    assert reused['source'] == str(g['path'] / 'actions/01')
    assert reused['source_result_sha256'] == g['public']['result_sha256'] == h['public']['result_sha256']
    assert g['public']['facts'] == h['public']['facts']
    for row in episodes.values():
        e, t = row['episode'], row['transcript']
        assert e['actual_tools'] == e['distinct_attempted_designs'] == 1
        assert len(t['steps'][0]['generate']['candidates']) == 1
        assert e['actions'][0]['actual_input'] == {'operation': 'edit', 'design_patch': {'persistent_queue': True}, 'problem_patch': {}}
        assert e['last_problem'] == t['initial_state']['problem']
        assert t['termination']['reason'] == 'MODEL_STOPPED'
        assert not t['contract_corrections']['feedback']
        assert t['steps'][0]['result_sha256'] == identity(t['steps'][0]['result'])
        assert not t['h_g_formation'] and not t['generated_code_loaded']
        assert all(x['status'] == 'SETTLED' and x['usage'] is not None for x in row['costs']['rows'])
        assert not row['costs']['unknown_or_missing_usage']
    spec = importlib.util.spec_from_file_location('a_existing_readback', HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    raw_handle = OneRawRead(g['path'] / 'actions/01/raw.json')
    review = helper.review('d15-persistent-queue-new', raw_handle, task)
    review['readback_scope'] = ('Independent CRC, truth spans, receiver dedup, commit replay and energy algebra. '
                              'The wrapper additionally validates the new raw/model content hashes in memory, '
                              'without rereading the raw. No solver/evaluator import, integration or new execution.')
    raw = raw_handle.value
    key_payload = {'task': task, 'design': raw['design'], 'dt': raw['dt_s'], 'scientific_source': sources}
    exact_key = identity(key_payload)
    bindings = {
        'full_task': raw['task_sha256'] == identity(task) == g['public']['task_sha256'] == h['public']['task_sha256'],
        'full_design': raw['design'] == gd['actual_design'] and raw['design_sha256'] == identity(gd['actual_design']),
        'dt': raw['dt_s'] == task['integration']['dt_s'],
        'five_scientific_sources': sources == prospective['scientific_sources']['recorded'],
        'exact_cache_key': exact_key == reused['exact_key'],
        'raw_result_binding': raw['result_sha256'] == reused['source_result_sha256'],
        'new_raw_content_hash': identity({k: v for k, v in raw.items() if k != 'result_sha256'}) == raw['result_sha256'],
        'engineering_model_content': identity(raw['engineering_model']) == raw['engineering_model_sha256'],
        'single_new_raw_read': raw_handle.reads == 1,
        'full_h_no_raw': not (h['path'] / 'actions/01/raw.json').exists(),
        'both_public_facts_equal': g['public']['facts'] == h['public']['facts'],
        'full_h_reused_zero_new_inputs': h['public']['usage'].get('reused') is True and h['public']['usage']['numerical_inputs'] == 0,
    }
    assessment = read(g['path'] / 'actions/01/assessment.json')
    service = review['independent_service']
    assessment_matches = (
        service['verdict'] == assessment['verdict']
        and service['failures'] == assessment['failures']
        and service['truth'] == assessment['truth']
        and service['matches'] == assessment['matches']
        and review['receiver']['accepted'] == assessment['receiver_records'])
    energy_compare = {k: review['energy'][k] == v for k, v in initial['energy'].items() if k in review['energy'] and isinstance(v, (int, float)) and not isinstance(v, bool)}
    tx_compare = [r['TX'] for r in review['state']['timeline']] == [r['TX'] for r in initial['state']['timeline']]
    reset_compare = [(r['time_s'], r['during']) for r in review['state']['resets']] == [(r['time_s'], r['during']) for r in initial['state']['resets']]
    cost_rows = [{**r, 'usage': json.loads(r['usage'])} for x in episodes.values() for r in x['costs']['rows']]
    behavior = {}
    for name, row in episodes.items():
        e, t = row['episode'], row['transcript']
        first = t['steps'][0]
        behavior[name] = {
            'condition': t['condition'], 'source_transcript': str(row['path'] / 'method-transcript.json'),
            'model_identity': t['model_identity'], 'frozen_methods_sha256': t['frozen_methods_sha256'],
            'initial_observation_origin': e['initial_observation_origin'],
            'initial_observation_selected_by_agent': False,
            'proposal_count': len(first['generate']['candidates']),
            'unselected_distinct_candidates': first['unselected_ids'],
            'selected_id': first['select']['selected_id'],
            'actual_input': e['actions'][0]['actual_input'],
            'selection_basis': first['select']['selection_basis'],
            'expected_discrimination_or_gain': first['select']['expected_discrimination_or_gain'],
            'expected_state_change': first['select']['selected_candidate']['expected_state_change'],
            'structured_prediction': first['select']['selected_candidate']['prediction_or_unknown'],
            'scope_effect': first['scope_effect'], 'P_proposals': 0, 'P_executions': 0,
            'update_hypotheses': first['update']['hypotheses'],
            'termination': t['termination'], 'model_self_assessment': e['method_conclusion'],
            'public_result_object_hash': first['result_sha256'],
            'scientific_source_result_hash': first['result']['result_sha256'],
            'public_object_hash_verified': identity(first['result']) == first['result_sha256'],
            'contract_corrections': len(t['contract_corrections']['feedback']),
            'provider_requests': e['accounting']['requests'], 'tools': e['actual_tools'],
            'new_scientific_executions': e['actual_new_numerical_inputs'],
            'distinct_attempted_designs': e['distinct_attempted_designs'],
            'wall_s': e['wall_s'], 'cost_estimate_usd': e['accounting']['cache_aware_rate_estimate_usd'],
            'independent_service_verdict': service['verdict'],
            'explanation_verdict': 'SUPPORTED_LOCAL_IDENTITY_MECHANISM' if service['verdict'] == 'PASS' else 'REQUIRES_REVIEW',
            'explanation_scope': 'Committed sequence survives empty-queue IDLE brownout and BOOT reload; does not demonstrate an undelivered queued record surviving reset or interrupted SAVE/ACK recovery in this trajectory.',
            'structured_prediction_assessment': 'UNKNOWN field; qualitative pre-action sequence/count prediction is consistent.' if name == 'generic' else 'Received-count >=4 prediction met on exact reused evidence; CONSISTENT with unique_cause=false is appropriately local.',
            'h_g_formation': t['h_g_formation'], 'generated_code_loaded': t['generated_code_loaded'],
        }
    result = {
        'schema_version': 'pqe-d15-a-receipt-v1', 'package': prospective['package'],
        'feature': prospective['feature'], 'owner': 'campaign-a',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'INDEPENDENT_READBACK_COMPLETE' if all(bindings.values()) and assessment_matches else 'READBACK_MISMATCH_STOP',
        'audience': 'HOST_ONLY; not participant material',
        'prospective_path': str(HERE / 'A-PROSPECTIVE.json'),
        'readback_command': 'rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B ' + "'" + str(Path(__file__).resolve()) + "'",
        'readback_helper': str(HELPER),
        'initial_evidence': {
            'classification': 'DEVELOPER_PROVIDED_INITIAL_OBSERVATION',
            'independent_review_source': str(prior_receipt_path),
            'source_result_sha256': prospective['initial']['source_result_sha256'],
            'initial_service': initial['independent_service'],
            'initial_unique_received_count': initial['unique_received_count'],
            'initial_same_record_retransmissions': initial['state']['same_record_retransmissions'],
            'initial_different_saved_record_sequence_reuse': initial['state']['different_record_sequence_reuse'],
            'old_raw_reads_this_final_review': 0,
            'old_qualification_reruns': 0,
        },
        'shared_inputs': {
            'initial_state_equal': True, 'public_task_matches_shared_materials': True,
            'full_initial_P_unchanged': True, 'components_and_service_unchanged': True,
            'private_field_check_scope': 'A checks equal actual State/materials only; B owns participant-boundary release and wire audit.',
        },
        'new_coupled_review': review,
        'host_assessment_matches_independent_review': assessment_matches,
        'reuse_review': {
            'source': reused['source'], 'reuse_path': str(h['path'] / 'actions/01/reused.json'),
            'source_result_sha256': raw['result_sha256'], 'actual_design_sha256': raw['design_sha256'],
            'full_task_sha256': raw['task_sha256'], 'dt_s': raw['dt_s'],
            'scientific_sources': sources, 'exact_key_recomputed': exact_key,
            'checks': bindings, 'public_projection_version': reused['public_projection_version'],
            'interpretation': 'One new D15 execution in generic. Full_h independently selected the same edit and consumed that exact result; it is not a second simulation or independent scientific replicate. No old D04/D07 cross-Task reuse.',
        },
        'before_after': {
            'initial_unique_received': initial['unique_received_count'],
            'new_unique_received': review['unique_received_count'],
            'initial_saved_sequence': [r['record']['seq'] for r in initial['state']['timeline']],
            'new_saved_sequence': [r['record']['seq'] for r in review['state']['timeline']],
            'new_received_sequence': [r['seq'] for r in review['receiver']['accepted']],
            'new_same_record_retransmissions': review['state']['same_record_retransmissions'],
            'new_different_saved_record_sequence_reuse': review['state']['different_record_sequence_reuse'],
            'energy_fields_equal_to_prior_A_receipt': energy_compare,
            'TX_timing_equal_to_prior_A_receipt': tx_compare,
            'brownout_times_modes_equal_to_prior_A_receipt': reset_compare,
            'supply_equal_to_prior_A_receipt': review['supply'] == initial['supply'],
            'force_equal_to_prior_A_receipt': review['force'] == initial['force'],
            'comparison_scope': 'Uses already-audited initial receipt; no reread of old raw. Equal conservative write costs in both modes are the declared model semantics, not measured NVM costs.',
        },
        'agent_behavior_and_explanation': behavior,
        'billing': {
            'scope': 'This D15 batch only; old UNKNOWN/reservations remain untouched.',
            'actual_provider_requests': len(cost_rows),
            'all_six_SETTLED_with_provider_usage': all(r['status'] == 'SETTLED' and r['usage'] for r in cost_rows),
            'request_ids': [r['id'] for r in cost_rows],
            'prompt_tokens': sum(r['usage']['prompt_tokens'] for r in cost_rows),
            'completion_tokens': sum(r['usage']['completion_tokens'] for r in cost_rows),
            'cache_aware_rate_estimate_usd': sum(r['charged'] for r in cost_rows),
            'rate_scope': g['costs']['rate_scope'],
            'unknown_or_missing_usage': [], 'unsettled_reserved_usd': sum(x['costs']['unsettled_reserved_usd'] for x in episodes.values()),
        },
        'claim_boundary': [
            'PASS for all four prescribed events in this frozen 24-hour nominal Task only; no hardware acceptance, population loss-rate or global feasibility claim.',
            'The local explanation is supported by committed-state/reset/BOOT evidence and a one-field intervention; no unique-cause claim or optimal-repair search.',
            'The observed repair concerns sequence continuity. Last direction is also retained, but its separate causal contribution is not isolated because both pre-reset states are closed.',
            'No queued-record-at-reset or interrupted SAVE/ACK recovery is exercised by this new trajectory; prior engineering qualification is separate.',
            'Two model decision episodes, one new scientific execution, zero new initial executions; shared reused evidence is not statistical replication.',
            'No P restructuring, H/G learning, generated code, method superiority or broad agent autonomy is established.',
            'Both episodes begin with an equal developer-provided real failing initial observation. Subsequent repair selection and stopping are model decisions.',
        ],
        'resources': {
            'available_before_bytes': free_before, 'estimated_peak_additional_bytes': peak,
            'output_directory': str(HERE), 'retained_output_cap_bytes': retained_cap,
            'A_new_raw_reads': raw_handle.reads, 'A_old_raw_reads_this_final_review': 0,
            'A_provider_requests': 0, 'A_scientific_executions': 0, 'A_native_solver_runs': 0,
            'A_tests_run': 0, 'A_new_environments': 0, 'A_new_backups': 0, 'A_workers': 0,
            'batch_new_scientific_executions': batch['actual_new_numerical_inputs'],
            'batch_new_initial_executions': batch['shared_initial_numerical_inputs'],
            'batch_retained_bytes_reported': batch['retained_bytes'],
            'available_after_bytes': shutil.disk_usage(ROOT).free,
        },
        'handoff': 'A final readback complete. S0 owns integration, feature/progress/session state and final reporting; B owns public-boundary audit. A returns idle without further dispatch.',
    }
    destination = HERE / 'A-RECEIPT.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    result['resources']['A_retained_bytes'] = sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())
    result['resources']['available_after_bytes'] = shutil.disk_usage(ROOT).free
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    assert result['resources']['A_retained_bytes'] < retained_cap
    print(json.dumps({'receipt': str(destination), 'status': result['status'], 'service': service,
                      'reuse_checks': bindings, 'before_after': result['before_after'],
                      'state': review['state'], 'energy': review['energy'], 'supply': review['supply'],
                      'force': review['force'], 'billing': result['billing']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
