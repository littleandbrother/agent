"""Build only B-owned preformation artifacts from already-public M1-M4 files."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
from datetime import datetime, timezone
import ast
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / 'docs/research/pqe-two-paper-plan-20261022'
APP = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.pqe20261022.methods import digest, load_program
from bfworld.agentlab.pqe20261022.conditional_learning_methods import runtime_contract


def read(path):
    return json.loads(path.read_text())


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def bind(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}


catalog = {}


def source(key, relative, pointers=None):
    path = BASE / relative
    assert path.is_file(), path
    assert '/f1-conditional-learning/a/' not in str(path)
    assert path.name not in {'raw.json', 'assessment.json'}
    catalog[key] = {**bind(path), 'allowed_json_pointers': pointers or [''],
                    'visibility': 'PUBLIC_DEVELOPMENT', 'new_task_material': False}
    return key


def result_summary(result):
    facts = result.get('facts', {})
    counts = Counter(x.get('action', 'UNKNOWN') for x in facts.get('activity', []))
    return {k: deepcopy(result.get(k)) for k in ['execution_status', 'model_valid', 'task_id',
        'task_sha256', 'input_sha256', 'result_sha256', 'public_check']} | {
        'facts': {'observed_activity_row_counts': dict(counts),
            'activity_count_scope': 'Counts of saved public activity rows only; completeness is not assumed. Full facts and public summaries are source bound.',
            'receiver_records_count': len(facts.get('receiver_records', [])),
            'saved_records_count': len(facts.get('records', [])), 'wire_packets_count': len(facts.get('packets', [])),
            'minimum_tx_terminal_v': facts.get('minimum_tx_terminal_v'),
            'program_state': facts.get('program_state')},
        'full_public_result_in_catalog': True}


def compact_decision(decision, source_id, pointer=''):
    candidate = decision.get('selected_candidate', {})
    prediction = candidate.get('prediction_or_unknown', decision.get('expected_discrimination_or_gain', 'UNKNOWN'))
    if isinstance(prediction, dict):
        prediction = {k: deepcopy(prediction[k]) for k in ['verdict', 'service_verdict', 'scope', 'basis',
            'conditional_timely_records', 'conditional_ack_completed_windows', 'unknown_windows',
            'necessary_failures', 'conditions', 'unknowns', 'expected_information_gain', 'prediction_type'] if k in prediction}
    return {'selected_id': decision.get('selected_id'), 'selection_basis': decision.get('selection_basis'),
        'actual_input': deepcopy(decision.get('actual_input', {})),
        'saved_pre_action_prediction_excerpt': prediction,
        'full_saved_prediction_and_pool': {'source_id': source_id, 'json_pointer': pointer},
        'alternative_count': len(decision.get('alternatives', [])),
        'developer_annotation_is_not_agent_pre_action_prediction': True}


history = []


def incident(key, visible, decision, result, refs, annotation):
    history.append({'incident_id': key, 'allowed_for_learning': True, 'provenance': 'PUBLIC_EXECUTION',
        'record_ref': refs, 'visible_before': visible, 'decision': decision, 'result': result,
        'developer_annotation': {'author': 'DEVELOPER_RETROSPECTIVE', 'text': annotation,
            'not_an_autonomous_agent_discovery_or_original_prediction': True}})


# M1: real deterministic repair, public pre-action prediction and full service PASS.
m1 = 'dynamic-repair-m1/s0/attempts/01/'
m1_chain = source('m1-chain-public-sections', m1 + 'chain.json',
    ['/rows/0/state_before/task', '/rows/0/state_before/design', '/rows/0/state_before/problem',
     '/rows/0/generate', '/rows/0/select', '/rows/0/result', '/rows/0/state_after/strategy'])
m1_input = source('m1-action-input', m1 + 'actions/01-input.json', ['/design', '/problem', '/decision'])
m1_result = source('m1-public-result', m1 + 'actions/01/public-result.json')
v = read(BASE / (m1 + 'actions/01-input.json'))
incident('M1-DEVELOPER-METHOD-REPAIR-PASS', {'task_ref': {'source_id': m1_chain, 'json_pointer': '/rows/0/state_before/task'},
    'design': v['design'], 'problem': v['problem']}, compact_decision(v['decision'], m1_input, '/decision'),
    result_summary(read(BASE / (m1 + 'actions/01/public-result.json'))), [m1_chain, m1_input, m1_result],
    'Actual consumer full public PASS, received6. The deterministic developer method showed a usable repair capability; this was not automatic H formation or unseen-task transfer.')

# M2: preserve all three actual choices and corresponding results, including no-improvement repetition.
m2 = 'dynamic-decision-m2/s0/episodes/m2-02-u/'
m2_chain_path = BASE / (m2 + 'chain.json')
m2_rows = read(m2_chain_path)['rows']
allowed = []
for index in range(len(m2_rows)):
    allowed += [f'/rows/{index}/state_before/task', f'/rows/{index}/state_before/design',
                f'/rows/{index}/state_before/problem', f'/rows/{index}/generate', f'/rows/{index}/select',
                f'/rows/{index}/result', f'/rows/{index}/consequence']
m2_chain = source('m2-u-chain-public-sections', m2 + 'chain.json', allowed)
source('m2-public-task2', 'dynamic-decision-m2/a/public/task-02-input.json')
for index, row in enumerate(m2_rows):
    n = index + 1
    ref = source(f'm2-u-public-result-{n}', m2 + f'actions/{n:02d}/public-result.json')
    incident(f'M2-ORDINARY-FEEDBACK-CHOICE-{n}', {'task_ref': {'source_id': m2_chain, 'json_pointer': f'/rows/{index}/state_before/task'},
        'design': row['state_before']['design'], 'problem': row['state_before']['problem']},
        compact_decision(row['select'], m2_chain, f'/rows/{index}/select'), result_summary(row['result']), [m2_chain, ref],
        'M2 saved F/U pools, predictions and actions were identical; received3→5→5 and timely0→3→3 over this chain. Repetition added no service improvement. Empty phase-failure attribution and eight duplicate cheap calls do not establish a useful conditional method. Original full saved predictions remain available.')

# M3: actual no-improvement pools and full failures, no re-scoring of the old pools.
m3 = 'service-repair-m3/s0/'
for n in [1, 2, 3]:
    rel = m3 + f'episodes/m3-u/actions/{n:02d}-input.json'
    inp = read(BASE / rel)
    ref = source(f'm3-u-input-{n}', rel, ['/task_entry', '/design', '/problem', '/decision'])
    resrel = m3 + f'episodes/m3-u/actions/{n:02d}/public-result.json'
    resref = source(f'm3-u-public-result-{n}', resrel)
    incident(f'M3-ORDINARY-POOL-CHOICE-{n}', {'task_ref': {'source_id': ref, 'json_pointer': '/task_entry'},
        'design': inp['design'], 'problem': inp['problem']}, compact_decision(inp['decision'], ref, '/decision'),
        result_summary(read(BASE / resrel)), [ref, resref],
        'Original pools contain6,5,5 candidates. First6 and second5 had no predicted timely TX opportunity; a local electrical margin or raised gate did not establish full service. Actual selected execution remained valid FAIL with zero TX/received. No new predictor call is used to reinterpret the saved pool.')

predref = source('m3-isolated-retry-prediction', 'service-repair-m3/a/prediction-joint-spaced-retry.json')
engineeringref = source('m3-engineering-spaced-retry-result', m3 + 'engineering/02/public-result.json')
prediction = read(BASE / 'service-repair-m3/a/prediction-joint-spaced-retry.json')
engineering = read(BASE / (m3 + 'engineering/02/public-result.json'))
incident('M3-ISOLATED-PREDICTION-VS-CONTINUOUS-FAIL',
    {'task_ref': 'm2-public-task2', 'original_prediction_ref': predref},
    {'source': 'DEVELOPER_ENGINEERING_CHECK', 'prediction_ref': predref,
     'saved_pre_action_prediction_excerpt': prediction.get('service_prediction'), 'executed_design': engineering['design'],
     'not_autonomous_agent_decision': True}, result_summary(engineering), [predref, engineeringref],
    'The isolated conditional prediction reported six timely windows with explicit no inherited queue/prefix-interaction assumptions. The original continuous consumer instead received5 with3 timely,17TX and5ACK; this falsifies treating isolated-window predictions as complete service. This A engineering result is now common development history, not a hidden answer for the new tasks.')

toolref = source('m3-g-output-truncation-public', m3 + 'episodes/m3-g/callbacks/03/pi-public.jsonl')
# Public JSONL is a bounded stream source, not a JSON-pointer tree. It contains public output/usage only.
catalog[toolref]['format'] = 'PUBLIC_JSONL'
costref = source('m3-g-provider-costs', m3 + 'episodes/m3-g/provider-costs.json')
incident('M3-GENERIC-OUTPUT-TRUNCATED', {'task_ref': 'm2-public-task2', 'previous_complete_decisions': 2},
    {'selected_id': None, 'submitted_action': False, 'saved_pre_action_prediction_excerpt': 'NONE_OUTPUT_INCOMPLETE',
     'callback_number': 3, 'callback_public_ref': toolref},
    {'execution_status': 'TOOL_ERROR', 'model_valid': None, 'public_check': {'verdict': 'UNKNOWN'},
     'provider_stop_reason': 'length', 'public_action_content': [], 'new_scientific_inputs': 0,
     'reasoning_output_tokens_reported': 32768, 'cost_record_ref': costref}, [toolref, costref],
    'Output truncation before a legal action is a tool/output failure, not an engineering repair failure, candidate rejection, or domain FAIL. Original settled usage/cost remains in its ledger.')

# M4: success and the same candidate's failed regression remain separate incidents.
m4 = 'executable-select-m4/s0/'
for category, name in [('candidate', 'M4-UNKNOWN-EXPERIMENT-FULL-PASS'), ('regression', 'M4-REGRESSION-FAIL-ADOPTION-REJECTED')]:
    rel = m4 + category + '/01-input.json'
    inp = read(BASE / rel)
    inp_ref = source('m4-' + category + '-input', rel, ['/task_entry', '/design', '/problem', '/decision'])
    resrel = m4 + category + '/01/public-result.json'
    resref = source('m4-' + category + '-public-result', resrel)
    incident(name, {'task_ref': {'source_id': inp_ref, 'json_pointer': '/task_entry'},
        'design': inp['design'], 'problem': inp['problem']}, compact_decision(inp['decision'], inp_ref, '/decision'),
        result_summary(read(BASE / resrel)), [inp_ref, resref],
        ('The sole preregistered retry .65→.85 proposal was selected as an UNKNOWN discriminating experiment, not as predicted PASS. Original consumer full PASS6/6 timely,12TX,6ACK,empty queue. This constant is one old-task outcome, not a generic repair rule.' if category == 'candidate' else
         'The same candidate failed the original second-scope regression with zero TX/received and six saved records. The external adoption gate retained the parent method/design. Parent performance on that regression was not measured; no relative-parent causal degradation claim is supported. No second candidate or post-result rescue was run.'))

old_parent = APP / 'studies/pqe20261022/f1first/shared/parent-h0.json'
parent_wrapper = read(old_parent)
parent = parent_wrapper['program']
assert digest(parent) == 'e2dccf3a86540f4a17200ba670e97761cb09e3e6dc9af79d6ca31e10eeafb892'
load_program(parent)
save('parent-h0.json', {'program': parent, 'program_sha256': digest(parent), 'original_public_parent': bind(old_parent),
    'protocol': 'strong_generic', 'baseline': 'One exact fixed E2 strong_generic parent; model GEN/RANK and ordinary deterministic UPDATE.',
    'H0_extra_development_history': False, 'parent_authority': 'No per-task parent choice; H1 uses this same program with common history.'})

update_code = '''def h_update(ctx, ask):
    state = ctx["state"]
    result = ctx["result"]
    facts = result.get("facts", {})
    counts = facts.get("activity_counts", {})
    covered = isinstance(counts, dict) and bool(counts)
    if not covered:
        counts = {}
        activity = facts.get("activity", [])
        covered = False
        for row in activity:
            action = row.get("action", "UNKNOWN")
            counts[action] = counts.get(action, 0) + 1
    verdict = result.get("public_check", {}).get("verdict", "UNKNOWN")
    branch = "INSUFFICIENT_PUBLIC_EVIDENCE"
    status = result.get("execution_status", "UNKNOWN")
    if status not in ["OK", "COMPLETE", "COMPLETED", "SUCCESS"]:
        branch = "TOOL_OR_EXECUTION_ERROR"
    elif result.get("model_valid") is not True:
        branch = "DOMAIN_UNKNOWN"
    elif verdict == "PASS":
        branch = "ACTUAL_FULL_SERVICE_PASS"
    elif verdict == "FAIL":
        if covered and counts.get("boot", 0) == 0:
            branch = "STARTUP_OR_SOURCE"
        elif covered and counts.get("tx_begin", 0) > 0 and counts.get("wire_complete", 0) == 0:
            branch = "TX_ENERGY_RESET_OR_DELIVERY"
        elif counts.get("tx_begin", 0) > 0:
            branch = "DELIVERY_QUEUE_TIMING_OR_CROSS_EVENT_PREFIX"
        elif covered and counts.get("save_commit", 0) > 0:
            branch = "GATE_REACHABILITY_OR_TX_OPPORTUNITY"
        elif covered:
            branch = "CAPTURE_SAVE_OR_RESET"
    strategy = dict(state.get("strategy", {}))
    strategy["conditional_h3"] = {"branch": branch, "observed_activity_counts": counts,
        "counts_coverage_usable": covered, "public_verdict": verdict, "unique_cause": False,
        "scope": "current actual public execution only; branch is a hypothesis set, not a domain proof"}
    return {"strategy": strategy, "hypotheses": state.get("hypotheses", []),
        "invalidated": state.get("invalidated", []),
        "next_evidence": {"branch": branch, "require_original_complete_consumer": True}}
'''
gen_code = '''def h_gen(ctx, ask):
    branch = ctx["state"].get("strategy", {}).get("conditional_h3", {}).get("branch", "INSUFFICIENT_PUBLIC_EVIDENCE")
    if branch == "ACTUAL_FULL_SERVICE_PASS":
        return {"status": "STOPPED", "conclusion": {"verdict": "PASS", "basis": "actual model-valid full public consumer result", "scope": "this executed Task and Design only"}}
    request = dict(ctx)
    request["conditional_evidence"] = ctx["state"].get("strategy", {}).get("conditional_h3", {})
    return ask("H-GEN", request)
'''
rank_code = '''def h_rank(ctx, ask):
    request = dict(ctx)
    request["conditional_evidence"] = ctx["state"].get("strategy", {}).get("conditional_h3", {})
    return ask("H-RANK", request)
'''
stop_code = '''def h_stop(ctx, ask):
    result = ctx["state"].get("last_result", {})
    passed = result.get("execution_status") in ["OK", "COMPLETE", "COMPLETED", "SUCCESS"] and result.get("model_valid") is True and result.get("public_check", {}).get("verdict") == "PASS"
    return {"stop": passed, "reason": "actual complete public PASS" if passed else "continue within remaining quota", "scope": "current executed Task and Design only"}
'''
conditional_prompt = '''Use conditional_h3 as factual clues and competing hypotheses, never as a unique cause. For STARTUP_OR_SOURCE inspect public source/startup/capture necessary bounds; for TX_ENERGY_RESET_OR_DELIVERY compare TX energy, ESR, gate and actual reset/wire facts; for DELIVERY_QUEUE_TIMING_OR_CROSS_EVENT_PREFIX inspect actual wire/gateway/deadline/FIFO/ACK and inherited prefix interactions; for GATE_REACHABILITY_OR_TX_OPPORTUNITY check paired gate reachability and TX feasibility. WAIT voltage alone is not TX gain. For CAPTURE_SAVE_OR_RESET inspect capture/atomic-save/reset evidence. For insufficient evidence or tool/domain error preserve UNKNOWN and use identical public tools to read missing facts. Generate finite complete-schema alternatives with scoped predictions or UNKNOWN, information value, costs and explicit outcome branches; choose affordable discrimination or a defensible repair and retain a no-improvement/stop option. Never turn an isolated window into complete-service PASS, ban a domain from one candidate failure, repeat a no-gain pool blindly, or hard-code an old repair constant. Only the original complete consumer validates service; only the external two-task gate adopts a method. Return the original site schema.'''
h3 = deepcopy(parent)
h3.update(program_id='H3-fixed-conditional-public-history-v1', condition='H3', parent_program=parent['program_id'],
    origin='DEVELOPER_FIXED_CONDITIONAL_RULES', adoption='NOT_EVALUATED',
    code={'H-UPDATE': update_code, 'H-GEN': gen_code, 'H-RANK': rank_code, 'H-STOP': stop_code},
    prompts={'H-GEN': conditional_prompt, 'H-RANK': conditional_prompt},
    config={'H-UPDATE': {'rule_version': 'manual-preregistered-v1'}})
load_program(h3)  # capability/schema load only; the host owns the one isolated integration check.
assert all('0.85' not in code and 'DOOR-' not in code and 'LC-PV' not in code for code in h3['code'].values())
save('h3-fixed-rules.json', {'program': h3, 'program_sha256': digest(h3), 'parent_sha256': digest(parent),
    'history_incidents': [x['incident_id'] for x in history], 'preregistered_before_new_task_access': True,
    'new_task_materials_read': False, 'rule_scope': 'Manual conditional baseline from common public development history.',
    'all_six_editable_sites': h3['editable_sites'], 'unimplemented_sites_use_original_parent_defaults': ['H-EXP', 'H-REFORM'],
    'cost_boundary': 'Developer authored with coding-model assistance; authoring effort/cost unmeasured, not free. B experimental provider/science/cheap calls=0.'})
save('common-history.json', history)
save('public-source-catalog.json', {'schema': 'f1-public-source-catalog-v1',
    'sources': catalog, 'boundary': 'H1/H2/H3/H4 share exactly these eligible public development incidents and source IDs; H0 gets no extra development history. Only listed pointers are readable. No new F1 Task/initial state/label/reference or private evaluator material is included.',
    'paging': 'Host bounded reader only; full original public artifacts remain canonical, not copied. Every request/page and provider call is accounted.'})
save('runtime-contract.json', runtime_contract())
table = ['# Frozen common public development history', '',
    'Each row binds the original public input, saved pre-action prediction/action, and actual result through `public-source-catalog.json`. Developer interpretations are separate annotations; no old predictor or science run is repeated.', '',
    '| Incident | Actual public outcome | Interpretation boundary |', '|---|---|---|']
for row in history:
    outcome = row['result']
    table.append('| ' + row['incident_id'] + ' | ' + str(outcome.get('execution_status')) + '; model_valid=' + str(outcome.get('model_valid')) + '; ' + str(outcome.get('public_check', {}).get('verdict')) + ' | ' + row['developer_annotation']['text'].replace('|', '/') + ' |')
(HERE / 'HISTORY.md').write_text('\n'.join(table) + '\n')
module = APP / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022/conditional_learning_methods.py'
ast.parse(module.read_text())
papers = [APP / 'papers/pqe20261022' / name for name in ['paper1-stage3-decision-increment.md', 'paper2-stage3-decision-increment.md']]
save('PAPER-PREFIX-BASELINES.json', {'at': datetime.now(timezone.utc).isoformat(), 'papers': [bind(p) for p in papers],
    'requirement': 'Append one necessary core paragraph per paper only after actual finite outcomes; preserve every existing byte.'})
assert sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file()) < 4_000_000
print(json.dumps({'incidents': len(history), 'sources': len(catalog), 'parent_program_sha256': digest(parent),
    'h3_program_sha256': digest(h3), 'module': bind(module), 'B_new_science_cheap_provider_calls': 0,
    'new_F1_a_materials_read': False}, ensure_ascii=False))
