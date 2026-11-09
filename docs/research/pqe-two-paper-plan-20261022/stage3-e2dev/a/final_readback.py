"""Offline A readback of the frozen twelve-cell E2 development package.

No solver/evaluator, scientific apparatus, provider, or native-tool imports.
Each of the thirteen new episode raws is read once. Compact ledgers permit a
metadata-only resume without reopening any raw. The prior initial/cache raws
are never opened. This script writes only campaign-a's owned directory.
"""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
PLAN = STAGE.parent
ROOT = PLAN.parents[2]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
SRC = CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022'
OUTPUT = HERE / 'A-EPISODE-READBACK.json'


def read(path):
    return json.loads(path.read_text())


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def literal(path, name):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Missing literal ' + name)


class OneRawRead:
    def __init__(self, path):
        self.path, self.reads, self.raw, self.byte_sha256 = path, 0, None, None

    def read_text(self):
        assert self.reads == 0, 'RAW_ALREADY_READ'
        self.reads += 1
        data = self.path.read_bytes()
        self.byte_sha256 = hashlib.sha256(data).hexdigest()
        text = data.decode('utf-8')
        self.raw = json.loads(text)
        return text

    def __str__(self):
        return str(self.path)


def model_binding(raw, task, defaults, topology, program_version, model_version, nodes, domain):
    d = raw['design']
    comp = task['components']
    m = {**defaults, **d['mechanism']}
    values = {
        'G1': {'generator_constant_vs_per_m': m['generator_constant_vs_per_m']},
        'Rcoil': {'resistance_ohm': m['coil_resistance_ohm']},
        'BR1': {'drop_v': m['rectifier_drop_v']},
        'Cstore': {'capacitance_f': d['capacitance_f']},
        'Rleak': {'resistance_ohm': comp['leakage_ohm']},
        'CLAMP': {'maximum_v': comp['max_v']},
        'Rbranch': {'resistance_ohm': d['esr_ohm']},
        'PROGRAM': {'version': program_version,
                    'loads': {k: comp[k] for k in ('boot_a', 'boot_s', 'write_a', 'write_s', 'tx_a', 'tx_s', 'idle_a')},
                    'parameters': {k: d[k] for k in ('debounce_s', 'persistent_queue', 'retry_s')}},
        'SUPERVISOR': {k: d[k] for k in ('startup_v', 'brownout_v', 'tx_gate_v')},
    }
    model = raw['engineering_model']
    expected_elements = [{'id': key, 'kind': kind, 'nodes': ns, 'parameters': values[key]}
                         for key, (kind, ns) in topology.items()]
    return {
        'model_content_hash': identity(model) == raw['engineering_model_sha256'],
        'model_full_Task_Design_identity': model['task_sha256'] == identity(task) == raw['task_sha256']
                                          and model['design_sha256'] == identity(d) == raw['design_sha256'],
        'all_connected_elements_and_numerical_parameters': model['elements'] == expected_elements,
        'actual_mechanism_parameters': model['mechanical'] == {k: m[k] for k in
            ('stroke_m', 'cam_base_radius_m', 'follower_coulomb_n', 'follower_viscous_n_s_per_m')},
        'model_nodes_version_domain': model['nodes'] == nodes and model['schema_version'] == model_version
                                      and model['domain'] == domain,
        'program_version_and_load_provenance': raw['program_version'] == program_version
                                              and model.get('load_provenance') == comp.get('provenance'),
    }


def legal_edit(task, before_d, before_p, actual):
    p = {**deepcopy(before_p), **deepcopy(actual.get('problem_patch', {}))}
    patch = actual.get('design_patch', {})
    d = {**deepcopy(before_d), **deepcopy(patch)}
    legal = set(task['design_domain'])
    active = set(p['active_variables'])
    checks = {
        'Task_and_service_not_editable': set(actual) <= {'operation', 'design_patch', 'problem_patch', 'dt_s'}
            and set(actual.get('problem_patch', {})) <= {'active_variables', 'groups', 'fixed_choices', 'assumptions', 'local_objective'},
        'legal_scope_groups': active <= legal and all(set(g) <= active for g in p['groups']),
        'edit_inside_resulting_scope': set(patch) <= active,
        'resulting_fixed_choices_agree': all(k in legal and d[k] == v for k, v in p['fixed_choices'].items()),
        'read_actions_have_no_design_edit': actual['operation'] not in {'observe', 'verify', 'report', 'select'} or not patch,
        'full_design_field_set': set(d) == legal,
        'legal_dt': actual.get('dt_s', task['integration']['dt_s']) in task['integration']['allowed_dt_s'],
    }
    values_legal = True
    for k, spec in task['design_domain'].items():
        v = d[k]
        if spec['kind'] == 'number':
            values_legal &= type(v) in (float, int) and math.isfinite(v) and spec['min'] <= v <= spec['max']
        elif spec['kind'] == 'boolean':
            values_legal &= type(v) is bool
        elif spec['kind'] == 'mechanism':
            values_legal &= isinstance(v, dict) and set(v) <= set(spec['editable'])
            values_legal &= all(type(n) in (float, int) and math.isfinite(n) and spec['editable'][name][0] <= n <= spec['editable'][name][1]
                                for name, n in v.items())
    checks['declared_design_domain'] = bool(values_legal)
    checks['power_thresholds'] = d['brownout_v'] < d['startup_v'] <= task['components']['max_v']
    changed = sorted(k for k in legal if d[k] != before_d[k])
    added = sorted(active - set(before_p['active_variables']))
    released = sorted(k for k, v in before_p['fixed_choices'].items() if k not in p['fixed_choices'] or p['fixed_choices'][k] != v)
    exercised = sorted(set(changed) & (set(added) | set(released)))
    effect = {'Design_changed_fields': changed, 'active_variables_added': added,
              'fixed_choices_released': released, 'groups_changed': p['groups'] != before_p['groups'],
              'effective_scope_changed': bool(added or released), 'actual_new_scope_exercised': exercised}
    return d, p, checks, effect


def collect():
    assert not OUTPUT.exists(), 'DOSSIER_ALREADY_RECORDED; use its compact facts'
    free_before = shutil.disk_usage(ROOT).free
    assert free_before >= 10_005_000_000
    prospective = read(HERE / 'A-PROSPECTIVE.json')
    science = prospective['current_five_scientific_sources']
    assert {k: file_hash(SRC / k) for k in science} == science, 'FROZEN_SCIENCE_CHANGED'
    helper = module('e2_readback_helper', CAN / 'studies/pqe20261022/engineering/stage2/native/review_coupled.py')
    compact = module('e2_checkpoint_helpers', HERE / 'checkpoint_readback.py').compact_review
    constants = [literal(SRC / 'door_model.py', 'DEFAULT_MECHANISM'), literal(SRC / 'engineering.py', 'TOPOLOGY'),
                 literal(SRC / 'door_program.py', 'PROGRAM_VERSION'), literal(SRC / 'engineering.py', 'MODEL_VERSION'),
                 literal(SRC / 'engineering.py', 'NODES'), literal(SRC / 'door_model.py', 'DOMAIN')]
    tasks = read(CAN / 'studies/pqe20261022/shared/door-tasks.json')
    public_materials = read(CAN / 'studies/pqe20261022/shared/e2dev-public-materials.json')
    results = read(STAGE / 's0/RESULTS.json')
    batch = read(STAGE / 's0/batch-result.json')
    assert results['batch_result_sha256'] == file_hash(STAGE / 's0/batch-result.json')
    assert len(results['episodes']) == 12
    checkpoint_hashes = {'A-D07-INITIAL-READBACK.json': '00498d20e66e13195f251c6ab00d09ae4c2e318af834ca0b517ba176fd6820f4',
                         'A-D15-FOUR-READBACK.json': '47e07668073286079429b0ab3062482b374022514c1c5c279f0c2b1e62e7d183'}
    assert all(file_hash(HERE / k) == v for k, v in checkpoint_hashes.items())
    cache = read(HERE / 'INITIAL-CACHE-PROPOSAL.json')
    prior_d15 = read(HERE / 'A-D15-FOUR-READBACK.json')
    previous_rows = {r['episode']: r for r in prior_d15['rows']}
    ledger_dir = HERE / 'raw-readback'
    ledger_dir.mkdir(exist_ok=True)
    cells = []
    fresh_raw_reads = 0
    for record in results['episodes']:
        cell = record['episode']
        directory = STAGE / 's0/episodes' / cell
        ep = read(directory / 'episode-result.json')
        trans = read(directory / 'method-transcript.json')
        costs = read(directory / 'provider-costs.json')
        task = tasks[ep['task_id']]
        steps = [s for s in trans['steps'] if s.get('result') is not None]
        checks = {
            'full_Task_frozen': identity(task) == prospective['task_bindings'][ep['task_id']]['Task_sha256'],
            'model_public_Task_matches_frozen_materials': trans['initial_state']['task'] == public_materials[ep['task_id']],
            'initial_Design_P_frozen': trans['initial_state']['design'] == task['initial_design']
                and trans['initial_state']['problem'] == task['initial_problem'],
            'complete_finite_attempt': ep['status'] == 'COMPLETED_FINITE_ATTEMPT' and not ep['error'] and not ep['fatal'],
            'action_count_matches': len(ep['actions']) == len(steps) == ep['actual_tools'] == trans['counts']['tool_calls'],
            'provider_usage_available': not costs['unknown_or_missing_usage'] and costs['unsettled_reserved_usd'] == 0
                and all(r['status'] == 'SETTLED' and r['usage'] and not r['error'] for r in costs['rows']),
            'request_count_matches': costs['requests'] == len(costs['rows']) == len(trans['callback_records']) == trans['counts']['callback_attempts'],
            'no_native_or_hardware': ep['native_calls'] == ep['hardware_runs'] == 0,
            'limits_observed': costs['requests'] <= trans['limits']['provider_requests']
                and ep['actual_tools'] <= trans['limits']['tool_calls']
                and ep['actual_new_numerical_inputs'] <= trans['limits']['new_numerical_inputs']
                and ep['wall_s'] <= trans['limits']['wall_s'],
        }
        before_d, before_p = deepcopy(task['initial_design']), deepcopy(task['initial_problem'])
        action_rows = []
        for action, step in zip(ep['actions'], steps):
            n = action['number']
            q = directory / 'actions' / f'{n:02d}'
            pub = read(q / 'public-result.json')
            actual = action['actual_input']
            d, p, legal, effect = legal_edit(task, before_d, before_p, actual)
            binding = {
                'selected_action_matches': step['select']['actual_input'] == actual == step['select']['selected_candidate']['actual_input'],
                'state_before_matches': step['state_before']['design'] == before_d and step['state_before']['problem'] == before_p,
                'public_actual_Design_P_match': pub['design'] == d and pub['problem'] == p,
                'compact_step_Design_P_match': step['result']['design'] == d and step['result']['problem'] == p,
                'decision_before_execution_hash': step['decision_sha256_before_execution'] == identity(step['select']),
                'compact_result_hash': step['result_sha256'] == identity(step['result']),
                'public_service_matches_step': pub['public_check'] == step['result']['public_check'] == action['public_check'],
            }
            row = {'number': n, 'operation': actual['operation'], 'actual_input': actual,
                   'Design_before': before_d, 'Design_after': d, 'scope_effect_independent': effect,
                   'scope_effect_host': step.get('scope_effect'), 'legality_checks': legal, 'binding_checks': binding,
                   'execution_status': pub['execution_status'], 'public_check': pub['public_check'],
                   'scientific_result_sha256': pub.get('result_sha256'),
                   'compact_public_result_sha256': step['result_sha256'],
                   'selected_pre_action_prediction': step['select']['selected_candidate'].get('prediction_or_unknown'),
                   'unselected_ids': step.get('unselected_ids', []), 'hypotheses': step['update'].get('hypotheses', []),
                   'metadata_byte_hashes': {name: file_hash(q / name) for name in ('public-result.json', 'public-compact.json') if (q / name).exists()}}
            if (q / 'decision.json').exists():
                dec = read(q / 'decision.json')
                binding.update({'pre_execution_receipt': dec['phase'] == 'BEFORE_EXECUTION'
                                and dec['task_sha256'] == identity(task) and dec['parent_design_sha256'] == identity(before_d)
                                and dec['actual_design'] == d and dec['problem'] == p and dec['decision'] == step['select']})
                row['metadata_byte_hashes']['decision.json'] = file_hash(q / 'decision.json')
            if pub['execution_status'] == 'NO_EXECUTION':
                binding['no_scientific_execution_or_raw'] = not (q / 'raw.json').exists() and pub['usage']['numerical_inputs'] == 0
                row['scientific_applicability'] = 'NO_NEW_ASSESSMENT; prior applicable science retained'
            elif (q / 'reused.json').exists():
                reused = read(q / 'reused.json')
                source = next(x for x in cache['exact_success_cache_entries'] if x['task_id'] == ep['task_id'])
                exact_key = identity({'task': task, 'design': d, 'dt': task['integration']['dt_s'], 'scientific_source': science})
                binding['exact_cache_full_binding'] = exact_key == reused['exact_key'] == source['exact_cache_key']
                binding['original_cache_result'] = reused['source_result_sha256'] == source['source_result_sha256'] == pub['result_sha256']
                binding['cache_source_path'] = reused['source'] == str(Path(source['raw_path']).parent)
                binding['cache_has_no_new_raw'] = not (q / 'raw.json').exists()
                row['independent_service'] = previous_rows[cell]['independent_service_from_prior_exact_raw_review']
                row['scientific_applicability'] = 'EXACT_CACHE_PRIOR_INDEPENDENT_RAW_READBACK'
                row['cache_key'] = exact_key
                row['prior_review'] = prior_d15['prior_independent_raw_review']
            else:
                ledger_path = ledger_dir / f'{cell}-{n:02d}.json'
                if ledger_path.exists():
                    ledger = read(ledger_path)
                    assert ledger['status'] == 'COMPLETE', 'STOP_PREVIOUS_RAW_READBACK_ERROR'
                    assert ledger['raw_path'] == str(q / 'raw.json')
                    assert ledger['scientific_result_sha256'] == pub['result_sha256']
                    assert all(ledger['checks'].values()), 'STOP_PREVIOUS_RAW_AUDIT_MISMATCH'
                else:
                    handle = OneRawRead(q / 'raw.json')
                    try:
                        review = helper.review(f'{cell}-{n:02d}', handle, task)
                        raw = handle.raw
                        raw_checks = model_binding(raw, task, *constants)
                        raw_checks.update({
                            'raw_content_identity': identity({k: v for k, v in raw.items() if k != 'result_sha256'}) == raw['result_sha256'] == pub['result_sha256'],
                            'Task_Design_dt': raw['task_sha256'] == identity(task) and raw['design'] == d and raw['dt_s'] == task['integration']['dt_s'],
                            'five_scientific_sources': {k: pub['sources'].get(k) for k in science} == science,
                            'public_engineering_model': pub['engineering_model_sha256'] == raw['engineering_model_sha256'],
                            'public_model_valid_status': pub['model_valid'] == raw['model_valid'] and pub['domain_errors'] == raw['domain_errors']
                                and pub['execution_status'] == raw['execution_status'],
                            'public_core_facts': all(pub['facts'][k] == raw[k] for k in ('packets', 'energy', 'peak_handle_force_n', 'minimum_tx_terminal_v', 'program_state')),
                            'energy_closure': review['energy']['within_tolerance'], 'force_limit': review['force']['within_limit'],
                        })
                        assessment = read(q / 'assessment.json')
                        service = review['independent_service']
                        raw_checks['independent_service_matches_host'] = service['verdict'] == assessment['verdict'] == pub['public_check']['verdict'] \
                            and service['failures'] == assessment['failures'] == pub['public_check']['failures'] \
                            and service['unknown'] == assessment['unknown'] == pub['public_check']['unknown']
                        raw_checks['independent_truth_matches_receiver_and_deadlines'] = service['truth'] == assessment['truth'] \
                            and service['matches'] == assessment['matches'] and service['missing'] == assessment['missed_event_ids'] \
                            and review['receiver']['accepted'] == assessment['receiver_records']
                        compacted = compact(review)
                        voltages = [x['terminal_v'] for x in raw['trace']]
                        compacted['stored_trace_terminal_v_range'] = [min(voltages), max(voltages)]
                        compacted['boot_count'] = raw['boot_count']
                        compacted['first_boot_s'] = next((x['time_s'] for x in raw['activity'] if x['action'] == 'boot'), None)
                        compacted['first_capture_s'] = next((x['time_s'] for x in raw['activity'] if x['action'] == 'capture'), None)
                        ledger = {'schema': 'pqe-e2dev-a-once-only-raw-ledger-v1', 'status': 'COMPLETE',
                                  'raw_path': str(q / 'raw.json'), 'raw_file_bytes': (q / 'raw.json').stat().st_size,
                                  'raw_byte_sha256': handle.byte_sha256, 'raw_reads': handle.reads,
                                  'scientific_result_sha256': raw['result_sha256'], 'checks': raw_checks,
                                  'model_valid': raw['model_valid'], 'domain_errors': raw['domain_errors'],
                                  'review': compacted, 'new_scientific_executions': 0}
                        save_new(ledger_path, ledger)
                        fresh_raw_reads += handle.reads
                    except Exception as error:
                        if not ledger_path.exists():
                            save_new(ledger_path, {'schema': 'pqe-e2dev-a-once-only-raw-ledger-v1', 'status': 'READBACK_ERROR_STOP',
                                'raw_path': str(q / 'raw.json'), 'raw_reads': handle.reads, 'raw_byte_sha256': handle.byte_sha256,
                                'scientific_result_sha256': handle.raw.get('result_sha256') if handle.raw else None,
                                'error': type(error).__name__ + ': ' + str(error), 'do_not_reopen_raw': True})
                        raise
                row['raw_ledger'] = {'path': str(ledger_path), 'sha256': file_hash(ledger_path)}
                row['independent_service'] = ledger['review']['independent_service']
                row['scientific_applicability'] = 'ADMISSIBLE_COMPLETE_MODEL' if ledger['model_valid'] else 'MODEL_DOMAIN_UNKNOWN_ONLY_DIAGNOSTIC_FRAMES'
                row['domain_errors'] = ledger['domain_errors']
                binding['raw_ledger_all_checks'] = all(ledger['checks'].values())
                row['mechanism_startup_actually_consumed'] = bool(effect['actual_new_scope_exercised']) and ledger['checks']['actual_mechanism_parameters'] \
                    and ledger['checks']['all_connected_elements_and_numerical_parameters']
            if pub['execution_status'] != 'NO_EXECUTION':
                binding['full_Task_Design_in_public'] = pub['task_sha256'] == identity(task) and pub['input_sha256'] == identity(d)
                binding['five_sources_in_public_and_compact'] = {k: pub['sources'].get(k) for k in science} == science \
                    == {k: step['result']['sources'].get(k) for k in science}
                binding['compact_scientific_source_identity'] = step['result']['result_sha256'] == pub['result_sha256'] \
                    == step['result']['public_projection']['source_result_sha256']
            action_rows.append(row)
            before_d, before_p = deepcopy(d), deepcopy(p)
        checks['final_actual_Design_P'] = before_d == ep['last_design'] == trans['final_state']['design'] \
            and before_p == ep['last_problem'] == trans['final_state']['problem']
        checks['all_legal_actions'] = all(all(a['legality_checks'].values()) for a in action_rows)
        checks['all_action_bindings'] = all(all(a['binding_checks'].values()) for a in action_rows)
        billing = []
        for c in costs['rows']:
            usage = json.loads(c['usage']) if isinstance(c['usage'], str) else c['usage']
            billing.append({'id': c['id'], 'status': c['status'], 'reserved_usd': c['reserved'], 'charged_estimate_usd': c['charged'],
                            'usage': usage, 'response_sha256': c['response_hash'], 'error': c['error']})
        checks['accounting_sum'] = math.isclose(sum(c['charged_estimate_usd'] for c in billing), costs['cache_aware_rate_estimate_usd'], abs_tol=1e-10)
        applicable = [a for a in action_rows if a['execution_status'] != 'NO_EXECUTION'][-1]
        corrections = [{'kind': c['kind'], 'execution_status': c['execution_status'], 'scientific_result': c['scientific_result'],
                        'numerical_inputs': c['numerical_inputs'], 'source_callback_index': c['source_callback_index'],
                        'source_request_sha256': c['source_request_sha256'], 'original_payload_sha256': c['original_payload_sha256'],
                        'errors': c['errors']} for c in trans['contract_corrections']['feedback']]
        cells.append({'episode': cell, 'task_id': ep['task_id'], 'condition': ep['condition'], 'status': ep['status'],
            'checks': checks, 'model_identity': trans['model_identity'], 'frozen_methods_sha256': trans['frozen_methods_sha256'],
            'termination': trans['termination'], 'actual_tools': ep['actual_tools'], 'new_numerical_inputs': ep['actual_new_numerical_inputs'],
            'actions': action_rows, 'last_control_result': ep['last_public_service'],
            'last_applicable_scientific_result': {'action': applicable['number'], 'scientific_result_sha256': applicable['scientific_result_sha256'],
                'independent_service': applicable['independent_service']},
            'actual_P_scope_consumed': any(a.get('mechanism_startup_actually_consumed') for a in action_rows),
            'model_self_assessment': ep['method_conclusion'], 'contract_corrections': corrections,
            'h_g_formation': trans['h_g_formation'], 'generated_code_loaded': trans['generated_code_loaded'],
            'requests': costs['requests'], 'cost_estimate_usd': costs['cache_aware_rate_estimate_usd'], 'billing': billing,
            'source_byte_hashes': {n: file_hash(directory / n) for n in ('episode-result.json', 'method-transcript.json', 'provider-costs.json')}})
    totals = {'cells': len(cells), 'requests': sum(x['requests'] for x in cells), 'tools': sum(x['actual_tools'] for x in cells),
              'episode_new_numerical_inputs': sum(x['new_numerical_inputs'] for x in cells),
              'exact_cache_hits': sum(a['scientific_applicability'] == 'EXACT_CACHE_PRIOR_INDEPENDENT_RAW_READBACK' for c in cells for a in c['actions']),
              'model_domain_unknown_actions': sum(a.get('domain_errors', []) != [] for c in cells for a in c['actions']),
              'no_execution_actions': sum(a['execution_status'] == 'NO_EXECUTION' for c in cells for a in c['actions']),
              'correction_feedback_count': sum(len(c['contract_corrections']) for c in cells),
              'estimated_usd': sum(x['cost_estimate_usd'] for x in cells),
              'scope_consumed_episodes': [x['episode'] for x in cells if x['actual_P_scope_consumed']],
              'final_applicable_service': {v: sum(x['last_applicable_scientific_result']['independent_service']['verdict'] == v for x in cells) for v in ('PASS', 'FAIL', 'UNKNOWN')}}
    aggregate_checks = {
        'twelve_complete_finite_cells': totals['cells'] == 12 and all(c['status'] == 'COMPLETED_FINITE_ATTEMPT' for c in cells),
        'all_cell_checks': all(all(c['checks'].values()) for c in cells),
        'requests_tools_numerical_cache_corrections_match_S0': all(totals[k] == results['totals'][k] for k in
            ('cells', 'requests', 'tools', 'episode_new_numerical_inputs', 'exact_cache_hits', 'correction_feedback_count')),
        'estimated_cost_matches': math.isclose(totals['estimated_usd'], results['totals']['estimated_usd'], abs_tol=1e-10),
        'domain_unknown_count_matches': totals['model_domain_unknown_actions'] == results['totals']['domain_unknown_actions'],
        'P_consumption_matches': totals['scope_consumed_episodes'] == results['totals']['scope_permission_change_episodes'],
        'frozen_method_same_all_conditions': len({x['frozen_methods_sha256'] for x in cells}) == 1,
        'same_reported_backend_profile': len({x['model_identity'] for x in cells}) == 1,
        'new_raw_ledger_count': len(list(ledger_dir.glob('*.json'))) == 13,
    }
    dossier = {'schema': 'pqe-e2dev-a-twelve-cell-dossier-v1', 'package': prospective['package'], 'owner': 'campaign-a',
               'at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'INDEPENDENT_READBACK_COMPLETE' if all(aggregate_checks.values()) else 'AUDIT_MISMATCH_STOP',
               'checks': aggregate_checks, 'totals': totals, 'cells': cells, 'scientific_sources': science,
               'prior_checkpoint_byte_hashes': checkpoint_hashes,
               'S0_results_byte_sha256': file_hash(STAGE / 's0/RESULTS.json'),
               'S0_batch_result_byte_sha256': file_hash(STAGE / 's0/batch-result.json'),
               'resources': {'available_before_bytes': free_before, 'estimated_peak_additional_bytes': 5_000_000,
                   'output_directory': str(HERE), 'retained_output_cap_bytes': 1_000_000,
                   'A_episode_raw_reads_this_invocation': fresh_raw_reads, 'A_episode_raw_reads_total': 13,
                   'A_current_initial_raw_reads_from_prior_checkpoint': 1, 'A_prior_cache_raw_reads': 0,
                   'A_raw_copies': 0, 'A_new_scientific_executions': 0, 'A_provider_requests': 0,
                   'A_native_runs': 0, 'A_qualification_reruns': 0, 'A_parameter_scans': 0,
                   'A_new_environments': 0, 'A_new_backups': 0, 'A_workers': 0,
                   'available_after_bytes': shutil.disk_usage(ROOT).free}}
    save_new(OUTPUT, dossier)
    assert sum(f.stat().st_size for f in HERE.rglob('*') if f.is_file()) < 1_000_000, 'A_OUTPUT_CAP_EXCEEDED'
    print(json.dumps({'status': dossier['status'], 'checks': aggregate_checks, 'totals': totals, 'dossier_sha256': file_hash(OUTPUT),
                      'failed_cell_checks': {c['episode']: [k for k, v in c['checks'].items() if not v] for c in cells if not all(c['checks'].values())}}, indent=2))
    for c in cells:
        for a in c['actions']:
            if 'raw_ledger' in a:
                ledger = read(Path(a['raw_ledger']['path'])); r = ledger['review']
                print(json.dumps({'case': c['episode'] + '-' + str(a['number']), 'checks': all(ledger['checks'].values()),
                    'verdict': r['independent_service']['verdict'], 'domain_errors': ledger['domain_errors'],
                    'received': r['unique_received_count'], 'boots': r['boot_count'], 'first_boot': r['first_boot_s'],
                    'activity': r['activity_counts'], 'reset_modes': r['state']['reset_mode_counts'],
                    'minimum_tx_v': r['supply']['reported_min_TX_v'], 'trace_v_range': r['stored_trace_terminal_v_range']}))


if __name__ == '__main__':
    collect()
