"""Seal fact review of the three completed pre-provider v2 local aborts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

HERE = Path(__file__).resolve().parent
PLAN = HERE.parents[1]
ROOT = PLAN.parents[2]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
PRIVATE = CAN / 'studies/pqe20261022/f1first/private'
SHARED = PRIVATE.parent / 'shared'
SRC = CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022'
S0 = HERE.parent / 's0'
DATABASE = Path('/Users/depengsu/.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite')


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def binding(path):
    return {'path': str(path), 'sha256': digest(path)}


def save(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    path.chmod(0o444)


def main():
    output = HERE / 'selection-scope-review-v2.json'
    assert not output.exists(), 'PRESERVE_SEALED_REVIEW'
    prospective = read(HERE / 'A-PROSPECTIVE-v2.json')
    for ref in prospective['preserved_originals']:
        assert digest(ref['path']) == ref['sha256']
    protocol = read(SHARED / 'f1first-protocol-v2.json')
    registry = read(PRIVATE / 'registry.json')
    role = registry['roles']['selection']
    assert digest(role['task_path']) == role['task_file_sha256']
    task = read(role['task_path'])[role['task_json_key']]
    initial = read(role['initial_public_result_path'])
    bridge = read(HERE / 'bridge-readback-v2.json')
    assert bridge['status'] == 'PASS_STORED_CONSUMER_READBACK'
    free_before = shutil.disk_usage(ROOT).free
    assert free_before >= 10_025_000_000
    conditions = {}
    with sqlite3.connect(DATABASE.as_uri() + '?mode=ro', uri=True) as database:
        database.execute('PRAGMA query_only=ON')
        for condition in ('H1', 'H2', 'H4'):
            directory = S0 / 'episodes' / ('select-v2-' + condition.lower())
            episode_path = directory / 'episode-result.json'
            transcript_path = directory / 'method-transcript.json'
            cost_path = directory / 'provider-costs.json'
            episode, transcript, cost = read(episode_path), read(transcript_path), read(cost_path)
            prior_transcript_path = S0 / 'episodes' / ('select-' + condition.lower()) / 'method-transcript.json'
            prior_public_task = read(prior_transcript_path)['initial_state']['task']
            public_task = transcript['initial_state']['task']
            callback = transcript['callback_records'][0]
            provider_count = database.execute('SELECT count(*) FROM model_requests WHERE owner=?', (episode['owner'],)).fetchone()[0]
            calls = transcript['steps'][0]['site_calls']
            gen = next(call for call in calls if call['site'] == 'H-GEN')
            checks = {
                'host_frozen_Task_identity': identity(task) == role['task_sha256'],
                'same_public_Task_projection_as_v1': public_task == prior_public_task,
                'all_public_Task_shared_fields_frozen': all(public_task[key] == task[key] for key in public_task if key in task),
                'explicit_public_Task_projection_fields': set(task) - set(public_task) == {'exposure', 'family_id', 'initial_design', 'initial_problem', 'qualification_claim'} and set(public_task) - set(task) == {'public_inputs'},
                'unchanged_initial_design_problem': episode['last_design'] == task['initial_design'] == transcript['initial_state']['design'] and episode['last_problem'] == task['initial_problem'],
                'initial_result_identity': transcript['initial_state']['last_result']['result_sha256'] == role['raw_result_sha256'],
                'no_selected_or_executed_action': not episode['actions'] and episode['actual_tools'] == 0 and all(step.get('select') is None and step.get('result') is None and step.get('update') is None for step in transcript['steps']),
                'no_model_conclusion_or_adoption': episode['model_conclusion'] is None and transcript['model_conclusion'] is None,
                'specific_local_signature_error': callback['error'] == {'type': 'TypeError', 'message': "F1Episode.ready() got an unexpected keyword argument 'paid'"},
                'driver_stopped_missing_usage': episode['termination']['reason'] == transcript['termination']['reason'] == 'MISSING_USAGE',
                'no_provider_request_or_charge': provider_count == episode['accounting']['requests'] == cost['requests'] == 0 and cost['rows'] == [] and cost['cache_aware_rate_estimate_usd'] == cost['unsettled_reserved_usd'] == 0,
                'preserved_synthetic_UNKNOWN': callback['response']['usage']['status'] == 'UNKNOWN' and transcript['usage_ledger'][0]['usage']['status'] == 'UNKNOWN' and callback['consumed_payload']['status'] == 'INVALID_OUTPUT_USAGE',
                'no_callback_or_action_artifacts': not (directory / 'callbacks').exists() and not (directory / 'actions').exists(),
                'zero_actual_and_attempted_science': episode['actual_new_numerical_inputs'] == episode['reserved_or_attempted_numerical_inputs'] == transcript['counts']['new_numerical_inputs'] == 0,
                'inherited_FAIL_is_initial_only': episode['last_public_service'] == episode['candidate_service'] == initial['public_check'],
            }
            assert all(checks.values()), (condition, checks)
            conditions[condition] = {
                'episode_result': binding(episode_path),
                'unsupported_global_exclusions': 0,
                'erroneous_adoptions': 0,
                'assessment': 'NO_VISIBLE_MODEL_DECISIONS; PRE_PROVIDER_LOCAL_CALLBACK_ABORT; NO_CANDIDATE_SCIENCE',
                'notes': [
                    'No candidate, selection, update or conclusion exists. Zero observed scope errors does not establish a sound method comparison or selection pass.',
                    'The prepared H-GEN callback failed at the local ready(paid=True) entry before provider dispatch. Driver UNKNOWN is preserved separately from the empty provider request ledger.',
                    'Recorded last_public_service and candidate_service FAIL/received2 are the inherited initial result, not an executed candidate outcome.',
                    'No new model cost or simulation can serve as a cost-tie winner or evidence for adopting the formed child.'
                ],
                'evidence': {
                    'method_transcript': binding(transcript_path), 'provider_costs': binding(cost_path),
                    'callback_pointer': 'callback_records[0]', 'callback_request_sha256': callback['request_sha256'],
                    'exact_error': callback['error'], 'driver_response': callback['response'],
                    'consumed_payload': callback['consumed_payload'], 'termination': transcript['termination'],
                    'usage_ledger': transcript['usage_ledger'], 'counts': transcript['counts'],
                    'program_id': episode['program'], 'program_sha256': episode['program_sha256'],
                    'program_status': episode['program_status'], 'prepared_H_GEN': gen,
                    'prompt_delivery_boundary': 'Prepared locally; no provider request exists and no model consumed this v2 request.',
                    'common_history_sha256': transcript['common_history_sha256'],
                    'public_Task_projection_sha256': identity(public_task),
                    'same_projection_prior_transcript': binding(prior_transcript_path),
                    'callbacks_directory_exists': (directory / 'callbacks').exists(),
                    'actions_directory_exists': (directory / 'actions').exists(),
                },
                'checks': checks,
                'service_boundary': {
                    'initial_service_only': initial['public_check'],
                    'recorded_candidate_service_field': episode['candidate_service'],
                    'actual_candidate_service': None, 'candidate_service_status': 'NOT_EVALUATED',
                    'actual_model_outcome': None,
                },
                'counter_boundary': {'local_callback_attempts': 1, 'provider_requests': provider_count,
                                     'tools': 0, 'reserved_or_attempted_numerical_inputs': 0,
                                     'started_scientific_consumers': 0, 'completed_scientific_consumers': 0,
                                     'exact_cache_reuses': 0},
                'accounting': {'provider_database': str(DATABASE), 'owner': episode['owner'],
                               'verified_model_request_rows': provider_count, 'provider_ledger': cost,
                               'driver_synthetic_UNKNOWN_records': 1,
                               'driver_callback_reserve_as_recorded_usd': transcript['usage_ledger'][0]['reserve'],
                               'scope': 'No provider-request row exists. This does not erase the original driver UNKNOWN record or change historical R11.'},
            }
    assert len({row['evidence']['common_history_sha256'] for row in conditions.values()}) == 1
    criteria = read(HERE / 'A-SELECTION-REVIEW-PROTOCOL.json')
    value = {
        'schema': 'pqe-f1first-a-selection-scope-review-v2', 'package': protocol['package'],
        'owner': 'campaign-a', 'at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'COMPLETE_FOR_THREE_V2_PRE_PROVIDER_CALLBACK_ABORTS; NO_CANDIDATE_SCIENCE',
        'visibility': 'HOST_PRIVATE; never inject into G/formation/history',
        'conditions': conditions,
        'totals': {'unsupported_global_exclusions': 0, 'erroneous_adoptions': 0,
                   'local_callback_attempts': 3, 'driver_synthetic_UNKNOWN_records': 3,
                   'provider_requests': 0, 'provider_estimated_usd': 0, 'tools': 0,
                   'new_selection_scientific_inputs': 0, 'selection_cache_reuses': 0,
                   'new_scientific_executions_by_A': 0, 'selection_candidate_raw_reads': 0,
                   'initial_raw_rereads': 0, 'confirmation_result_reads': 0},
        'common_history_same_sha256': next(iter(conditions.values()))['evidence']['common_history_sha256'],
        'initial_source': {'registry': binding(PRIVATE / 'registry.json'),
                           'initial_public_result': {'path': role['initial_public_result_path'], 'sha256': role['initial_public_result_sha256']},
                           'sealed_initial_receipt': binding(HERE / 'A-INITIAL-RECEIPT.json')},
        'consumer_diagnostic': {
            'bridge_readback': binding(HERE / 'bridge-readback-v2.json'),
            'bridge_status': bridge['status'], 'bridge_is_method_selection_result': False,
            'planner_callsite': {'path': str(SRC / 'pilot.py'), 'sha256': digest(SRC / 'pilot.py'), 'line': 304, 'text': 'budget=self.ready(paid=True);before=ledger(DATABASE,self.owner)'},
            'incompatible_override': {'path': str(SRC / 'f1first.py'), 'sha256': digest(SRC / 'f1first.py'), 'line': 173, 'text': 'def ready(self):'},
            'stop': 'S0 confirmed no adoption/confirmation dispatch and no automatic fourth implementation revision.',
        },
        'method_boundary': 'Frozen H2 parent retention and H4 formed child identity remain. A prepared H4 prompt differs, but this v2 request never reached a model and no engineering use-test occurred.',
        'adoption_boundary': 'No effective v2 selection scientific evidence exists. Do not adopt from inherited initial FAIL or zero provider cost. S0 owns any disposition; no new revision/rerun is authorized by this review.',
        'criteria': {key: criteria[key] for key in ('counting_unit', 'unsupported_global_exclusions', 'erroneous_adoptions', 'important_boundaries')},
        'prospective': binding(HERE / 'A-PROSPECTIVE-v2.json'),
        'original_review_preserved': binding(HERE / 'selection-scope-review.json'),
        'protocol_v2': binding(SHARED / 'f1first-protocol-v2.json'),
        'resources': {'available_before_bytes': free_before, 'available_after_bytes': shutil.disk_usage(ROOT).free,
                      'retained_A_and_private_bytes_before_this_review': sum(path.stat().st_size for folder in (HERE, PRIVATE) for path in folder.rglob('*') if path.is_file()),
                      'raw_copies': 0, 'new_environments': 0, 'workers': 0},
        'limitations': ['Only the observed finite local aborts are reviewed; zero scope errors is not successful method behavior.',
                        'Bridge PASS is apparatus recovery evidence. The ten confirmation cells remain unexecuted and are not scientific FAIL.',
                        'No stable transfer, formal E2/E3, general loss guarantee, or physical/hardware qualification follows.'],
    }
    save(output, value)
    print(json.dumps({'path': str(output), 'sha256': digest(output), 'status': value['status'],
                      'totals': value['totals']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
