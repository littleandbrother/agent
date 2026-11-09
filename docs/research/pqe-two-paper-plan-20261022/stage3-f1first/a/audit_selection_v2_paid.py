"""Independent stored consumer and scope audit for the three paid-restored cells."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
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


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    scope_path = HERE / 'selection-scope-review-v2-paid.json'
    consumer_path = HERE / 'selection-consumer-readback-v2-paid.json'
    assert not scope_path.exists(), 'PRESERVE_SEALED_SCOPE_REVIEW'
    prospective = read(HERE / 'A-PROSPECTIVE-v2-paid.json')
    for ref in prospective['preserved_evidence']:
        assert digest(ref['path']) == ref['sha256']
    protocol = read(SHARED / 'f1first-protocol-v3.json')
    registry = read(PRIVATE / 'registry.json')
    role = registry['roles']['selection']
    assert digest(role['task_path']) == role['task_file_sha256']
    task = read(role['task_path'])[role['task_json_key']]
    assert identity(task) == role['task_sha256']
    assert all(digest(SRC / name) == value for name, value in registry['scientific_sources'].items())
    assert all(digest(path) == values['after'] for path, values in protocol['changed_source_bindings'].items())
    assert all(digest(ref['path']) == ref['sha256'] for ref in protocol['shared_bindings'].values())
    assert all(digest(ref['path']) == ref['sha256'] for ref in protocol['original_attempt_bindings'])
    free_before = shutil.disk_usage(ROOT).free
    assert free_before >= 10_025_000_000
    episodes, transcripts = {}, {}
    for condition in ('H1', 'H2', 'H4'):
        ident = 'select-v2-paid-' + condition.lower()
        assert protocol['parent_attempts'][ident] == 'select-v2-' + condition.lower()
        episodes[condition] = read(S0 / 'episodes' / ident / 'episode-result.json')
        transcripts[condition] = read(S0 / 'episodes' / ident / 'method-transcript.json')
    qualifier = module_at('a_paid_usage_gate', HERE / 'qualify_inputs.py')
    gate_before = qualifier.usage_gate()
    if consumer_path.exists():
        consumer = read(consumer_path)
    else:
        marker = HERE / 'selection-consumer-readback-v2-paid-start.json'
        assert not marker.exists(), 'CANONICAL_RAW_ALREADY_READ_NO_REPEAT'
        action = episodes['H1']['actions'][0]
        directory = Path(action['path'])
        public_path = directory / 'public-result.json'
        public = read(public_path)
        decision_path = directory / 'decision.json'
        decision = read(decision_path)
        expected = {**task['initial_design'], **action['actual_input']['design_patch']}
        assert action['usage']['numerical_inputs'] == 1
        assert expected == {**task['initial_design'], 'persistent_queue': True}
        raw_path = directory / 'raw.json'
        save(marker, {'at_utc': datetime.now(timezone.utc).isoformat(), 'raw_path': str(raw_path),
                      'canonical_raw_reads_authorized': 1, 'new_execution': 0, 'initial_or_bridge_raw_reads': 0})
        data = raw_path.read_bytes()  # The sole filesystem content read of this new raw.
        raw = json.loads(data)
        helper_path = CAN / 'studies/pqe20261022/engineering/stage2/native/review_coupled.py'
        helper = module_at('a_paid_stored_output_helper', helper_path)
        bridge_tool = module_at('a_paid_memory_raw_wrapper', HERE / 'review_bridge_v2.py')
        independent = helper.review('select-v2-paid-h1', bridge_tool.MemoryRaw(raw), task)
        independent['raw_path'] = str(raw_path)
        assessment_path = directory / 'assessment.json'
        assessment = read(assessment_path)
        service = independent['independent_service']
        checks = {
            'raw_object_identity': identity({k: v for k, v in raw.items() if k != 'result_sha256'}) == raw['result_sha256'],
            'frozen_Task_identity': raw['task_sha256'] == public['task_sha256'] == decision['task_sha256'] == role['task_sha256'],
            'actual_Design_is_model_selected_patch': raw['design'] == public['design'] == decision['actual_design'] == expected,
            'selected_decision_binding': decision['decision'] == transcripts['H1']['steps'][0]['select'],
            'Design_object_identity': identity(expected) == raw['design_sha256'] == public['input_sha256'],
            'engineering_model_identity': identity(raw['engineering_model']) == raw['engineering_model_sha256'] == public['engineering_model_sha256'],
            'complete_valid_execution': raw['execution_status'] == public['execution_status'] == 'COMPLETE' and raw['model_valid'] and not raw['domain_errors'],
            'public_raw_result_identity': public['result_sha256'] == raw['result_sha256'],
            'public_factual_fields': all(public['facts'][key] == raw[key] for key in ('activity', 'packets', 'energy', 'peak_handle_force_n', 'minimum_tx_terminal_v', 'program_state')),
            'independent_verdict': service['verdict'] == assessment['verdict'] == public['public_check']['verdict'],
            'independent_failures_unknown': service['failures'] == assessment['failures'] == public['public_check']['failures'] and service['unknown'] == assessment['unknown'] == public['public_check']['unknown'],
            'independent_truth_matches': service['truth'] == assessment['truth'] and service['matches'] == assessment['matches'] and service['missing'] == assessment['missed_event_ids'],
            'independent_receiver': independent['receiver']['accepted'] == assessment['receiver_records'] == public['facts']['receiver_records'] and independent['unique_received_count'] == public['public_check']['received_count'],
            'CRC_commits_RAM_NVM': not independent['receiver']['invalid'] and independent['state']['all_commit_and_duration_checks'] and independent['state']['final_RAM_NVM_reconstructed'],
            'energy_and_force': independent['energy']['within_tolerance'] and independent['force']['within_limit'],
            'same_scientific_sources': all(public['sources'][name] == value for name, value in registry['scientific_sources'].items()),
        }
        consumer = {'schema': 'pqe-f1first-a-selection-consumer-v2-paid', 'package': protocol['package'],
                    'at_utc': datetime.now(timezone.utc).isoformat(), 'visibility': 'HOST_PRIVATE_NOT_G',
                    'status': 'PASS_STORED_CONSUMER_READBACK' if all(checks.values()) else 'FAIL_STOP',
                    'checks': checks, 'raw_file': {'path': str(raw_path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)},
                    'raw_result_sha256': raw['result_sha256'], 'public_result': binding(public_path),
                    'decision': binding(decision_path), 'assessment': binding(assessment_path),
                    'helper': binding(helper_path), 'independent_readback': independent,
                    'counts': {'new_canonical_raw_reads': 1, 'initial_raw_rereads': 0, 'bridge_raw_rereads': 0,
                               'new_scientific_provider_native_inputs_by_A': 0, 'raw_copies': 0}}
        save(consumer_path, consumer)
    assert consumer['status'] == 'PASS_STORED_CONSUMER_READBACK', 'INDEPENDENT_CONSUMER_AUDIT_STOP'
    source_directory = Path(consumer['public_result']['path']).parent
    original_public = read(source_directory / 'public-result.json')
    cache_key = identity({'task': task, 'design': original_public['design'], 'dt': task['integration']['dt_s'],
                          'scientific_source': registry['scientific_sources']})
    conditions = {}
    with sqlite3.connect(Path(gate_before['database']).as_uri() + '?mode=ro', uri=True) as database:
        database.row_factory = sqlite3.Row
        database.execute('PRAGMA query_only=ON')
        for condition in ('H1', 'H2', 'H4'):
            episode, transcript = episodes[condition], transcripts[condition]
            directory = S0 / 'episodes' / episode['episode']
            account = read(directory / 'provider-costs.json')
            rows = [dict(row) for row in database.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY created,id', (episode['owner'],))]
            usage_ids = [ident for item in transcript['usage_ledger'] for ident in item['usage']['request_ids']]
            action = episode['actions'][0]
            action_directory = Path(action['path'])
            public = read(action_directory / 'public-result.json')
            reused = read(action_directory / 'reused.json') if (action_directory / 'reused.json').exists() else None
            cache_checks = {'exact_key': reused['exact_key'] == cache_key,
                            'canonical_source': Path(reused['source']) == source_directory,
                            'raw_result_identity': reused['source_result_sha256'] == consumer['raw_result_sha256'] == public['result_sha256'],
                            'same_actual_input': reused['actual_design'] == public['design'] == original_public['design'],
                            'same_complete_service': public['public_check'] == original_public['public_check'],
                            'no_extra_raw_or_science': not (action_directory / 'raw.json').exists() and public['usage']['numerical_inputs'] == 0 and public['usage']['reused']} if reused else {'new_canonical_consumer': action_directory == source_directory and public['usage']['numerical_inputs'] == 1}
            prior_task = read(S0 / 'episodes' / ('select-' + condition.lower()) / 'method-transcript.json')['initial_state']['task']
            checks = {
                'episode_and_driver_completed': episode['error'] is None and episode['fatal'] is None and episode['termination']['reason'] == transcript['termination']['reason'] == 'MODEL_STOPPED',
                'same_initial_role_Task_projection': transcript['initial_state']['task'] == prior_task,
                'same_initial_Design_Problem': transcript['initial_state']['design'] == task['initial_design'] and transcript['initial_state']['problem'] == task['initial_problem'],
                'only_original_initial_evidence': transcript['initial_state']['last_result']['result_sha256'] == role['raw_result_sha256'],
                'all_usage_known_and_SETTLED': len(rows) == account['requests'] == 3 and all(row['status'] == 'SETTLED' and row['usage'] is not None for row in rows) and all(item['usage']['status'] == 'KNOWN' for item in transcript['usage_ledger']) and not account['unknown_or_missing_usage'],
                'request_ids_match_account': set(usage_ids) == {row['id'] for row in rows},
                'one_legal_local_edit': len(episode['actions']) == episode['actual_tools'] == 1 and action['actual_input'] == {'operation': 'edit', 'design_patch': {'persistent_queue': True}, 'problem_patch': {}},
                'consumer_or_exact_cache_binding': all(cache_checks.values()),
                'full_service_not_inherited_initial': episode['candidate_service'] == episode['last_public_service'] == public['public_check'] and episode['last_public_service_origin'] == 'LAST_CONSUMER_RESULT',
                'accepted_actual_design_and_problem': episode['last_design'] == public['design'] and episode['last_problem'] == public['problem'],
                'model_local_PASS_supported': episode['model_conclusion']['verdict'] == transcript['model_conclusion']['verdict'] == consumer['independent_readback']['independent_service']['verdict'] == 'PASS',
            }
            assert all(checks.values()), (condition, checks)
            step = transcript['steps'][0]
            conditions[condition] = {
                'episode_result': binding(directory / 'episode-result.json'), 'unsupported_global_exclusions': 0, 'erroneous_adoptions': 0,
                'assessment': 'OBSERVED_LOCAL_DECISIONS_SOUND; COMPLETE_CONSUMER_OR_EXACT_REUSE_PASS',
                'notes': ['The only edit enables persistence at ESR5 and capacitance300uF; all other Design/Problem fields remain unchanged.',
                          'The local prediction/UNKNOWN and contingency branches do not exclude the entire legal design domain.',
                          'Final PASS is expressly limited to this supplied finite24h scenario and disclaims population loss/hardware inference.',
                          'This selected action equals the baselines; changed H4 prompt consumption alone does not show distinct engineering action or transfer advantage.'],
                'evidence': {'transcript': binding(directory / 'method-transcript.json'), 'provider_costs': binding(directory / 'provider-costs.json'),
                             'model_payloads': [item['response']['payload'] for item in transcript['callback_records']],
                             'selected_basis_quote': step['select']['selection_basis'], 'conclusion_quote': episode['model_conclusion'],
                             'program_id': episode['program'], 'program_sha256': episode['program_sha256'], 'program_status': episode['program_status'],
                             'prepared_and_delivered_site_calls': [call for call in step['site_calls'] if call['site'] in ('H-GEN', 'H-RANK')],
                             'common_history_sha256': transcript['common_history_sha256'],
                             'parent_attempt': protocol['parent_attempts'][episode['episode']],
                             'actual_action': action, 'public_result': binding(action_directory / 'public-result.json'),
                             'reused_source': binding(action_directory / 'reused.json') if reused else None,
                             'consumer_readback': binding(consumer_path)},
                'checks': checks, 'cache_checks': cache_checks,
                'service_boundary': {'initial_only': read(role['initial_public_result_path'])['public_check'],
                                     'candidate_service': public['public_check'], 'scope': 'This frozen Task only; not population, hardware or domain-wide necessity.'},
                'counter_boundary': {'attempted_reserved_numerical': episode['reserved_or_attempted_numerical_inputs'],
                                     'completed_new_numerical': episode['actual_new_numerical_inputs'], 'exact_cache_reuses': int(bool(reused)), 'tools': 1},
                'accounting': {'owner': episode['owner'], 'requests': len(rows), 'request_ids': usage_ids,
                               'all_SETTLED': True, 'new_missing_usage': [], 'estimated_usd': account['cache_aware_rate_estimate_usd'],
                               'rate_scope': account['rate_scope']},
            }
    assert len({row['evidence']['common_history_sha256'] for row in conditions.values()}) == 1
    criteria = read(HERE / 'A-SELECTION-REVIEW-PROTOCOL.json')
    gate_after = qualifier.usage_gate()
    value = {'schema': 'pqe-f1first-a-selection-scope-review-v2-paid', 'package': protocol['package'], 'owner': 'campaign-a',
             'at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'COMPLETE_FOR_THREE_PAID_RESTORED_SELECTIONS',
             'visibility': 'HOST_PRIVATE; not G or formation/history', 'conditions': conditions,
             'totals': {'unsupported_global_exclusions': 0, 'erroneous_adoptions': 0, 'provider_requests': 9,
                        'new_selection_coupled_inputs': 1, 'exact_cache_reuses': 2, 'tools': 3,
                        'estimated_model_usd': str(sum((Decimal(str(row['accounting']['estimated_usd'])) for row in conditions.values()), Decimal(0))),
                        'canonical_raw_reads': 1, 'initial_raw_rereads': 0, 'bridge_raw_rereads': 0, 'confirmation_outcome_reads': 0,
                        'new_scientific_provider_native_executions_by_A': 0},
             'common_history_same_sha256': next(iter(conditions.values()))['evidence']['common_history_sha256'],
             'initial_source': binding(HERE / 'A-INITIAL-RECEIPT.json'), 'consumer_diagnostic': binding(consumer_path),
             'method_boundary': 'H2 used retained parent; H4 consumed original formed H-GEN prompt, but all chose the same edit and accepted the same complete service. No comparative efficacy advantage is shown.',
             'adoption_boundary': 'A scope gates have zero observed errors. S0 must still apply original full service/no-regression/cost gates, including original failed-selection costs; no confirmation outcomes were read.',
             'criteria': {key: criteria[key] for key in ('counting_unit', 'unsupported_global_exclusions', 'erroneous_adoptions', 'important_boundaries')},
             'prospective': binding(HERE / 'A-PROSPECTIVE-v2-paid.json'), 'execution_protocol': binding(SHARED / 'f1first-protocol-v3.json'),
             'new_UNKNOWN_usage_gate_before': gate_before, 'new_UNKNOWN_usage_gate_after': gate_after,
             'resources': {'available_before_bytes': free_before, 'available_after_bytes': shutil.disk_usage(ROOT).free, 'raw_copies': 0},
             'limitations': ['One selected joint block and shared exact cache do not provide independent physical replications.',
                             'Finite persistence intervention supports this input; it does not prove persistence is necessary over every legal power/timing design.',
                             'No formal E2/E3, stable transfer, population loss guarantee or physical qualification.']}
    save(scope_path, value)
    print(json.dumps({'scope_review': binding(scope_path), 'consumer_readback': binding(consumer_path), 'totals': value['totals']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
