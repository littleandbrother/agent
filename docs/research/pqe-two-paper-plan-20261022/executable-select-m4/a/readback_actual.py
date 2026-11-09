"""Independent saved-artifact readback only: zero solver/model/score dispatch."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('/Users/depengsu/Documents/Long-Horizon AI Agent')
BASE = ROOT/'docs/research/pqe-two-paper-plan-20261022/executable-select-m4'
A = BASE/'a'
SRC = ROOT/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src/bfworld/agentlab/pqe20261022'

def read(path):
    return json.loads(Path(path).read_text())

def bind(path):
    b = Path(path).read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)}

def checked(ref):
    assert bind(ref['path']) == ref, ('binding', ref['path'])
    return read(ref['path'])

def save(path, value):
    with Path(path).open('x') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')

interface = read(A/'INTERFACE-RECEIPT.json')
for name in ('source', 'frozen_factual_dependency', 'candidate', 'fixed_parent', 'verification', 'condition_calculation', 'cheap_ledger'):
    checked(interface[name]) if name != 'source' and name != 'frozen_factual_dependency' else None
    assert bind(interface[name]['path']) == interface[name]
from bfworld.agentlab.pqe20261022.trajectory_service_facts import extract_trajectory_facts
from bfworld.agentlab.pqe20261022.service_relations import model_identity

protocol = read(BASE/'shared/protocol.json')
freeze = read(BASE/'s0/participant-freeze.json')
for path, digest in freeze['source_bindings'].items():
    assert bind(path)['sha256'] == digest, ('frozen source changed', path)
assert freeze['development_proposal'] == interface['candidate']
parent = checked(interface['fixed_parent'])
proposal = checked(interface['candidate'])
expected = deepcopy(parent['design'])
expected['retry_s'] = proposal['proposal']['actual_input']['design_patch']['retry_s']
assert expected['retry_s'] == 0.85
result = read(BASE/'s0/result.json')
ledger = checked(result['ledger'])
assert ledger['full_dynamic_inputs'] == 2 and ledger['full_dynamic_wall_s'] <= 240
assert result['paid_models'] == result['new_model_episodes'] == result['post_result_revisions'] == 0
assert ledger['provider_requests'] == ledger['provider_usd'] == 0
chain = checked(result['chain'])
for name, ref in chain.items():
    if isinstance(ref, dict) and {'path','sha256','bytes'} <= ref.keys():
        checked(ref)
final_state = checked(chain['final_state'])
assert final_state['design'] == parent['design']
assert result['adoption']['adoption_status'] == 'RETAIN_PARENT_REGRESSION_NOT_PASSED'
rows = []
for role in ('candidate', 'regression'):
    folder = BASE/'s0'/role/'01'
    receipt = read(folder/'readback.json')
    public = checked(receipt['public_result'])
    raw = checked(receipt['raw'])
    assessment = checked(receipt['assessment'])
    decision = read(folder/'decision.json')
    entry = next(t for t in protocol['tasks'] if t['task_id'] == public['task_id'])
    packet = checked(entry['public_input'])
    public_task = packet['task']
    assert public['task_sha256'] == raw['task_sha256'] == entry['task_canonical_sha256']
    assert public['design'] == raw['design'] == decision['actual_design'] == expected
    assert public['sources'] == decision['sources'] == protocol['apparatus_source']
    assert model_identity({k: v for k, v in raw.items() if k != 'result_sha256'}) == raw['result_sha256'] == public['result_sha256']
    assert model_identity(raw['design']) == raw['design_sha256'] == public['input_sha256'] == receipt['design_sha256']
    assert public['execution_status'] == raw['execution_status'] == 'COMPLETE'
    assert public['model_valid'] is True and raw['model_valid'] is True and not public['domain_errors']
    for field in ('activity', 'records', 'packets', 'trace', 'energy', 'program_state'):
        assert public['facts'][field] == raw[field], ('public raw mismatch', role, field)
    assert public['facts']['receiver_records'] == assessment['receiver_records']
    assert public['public_check']['verdict'] == assessment['verdict']
    assert abs(assessment['mechanical_residual_j']) <= assessment['energy_tolerance_j']
    assert abs(assessment['storage_residual_j']) <= assessment['energy_tolerance_j']
    facts = extract_trajectory_facts(public_task, public['design'], public)
    assert facts['status'] == 'PUBLIC_TRAJECTORY_FACTS'
    assert facts['summary']['complete_public_event_lists'] is True
    assert facts['scope']['task_sha256'] == model_identity(public_task)
    assert facts['summary']['timely_public_window_records'] == len(assessment['matches']) == receipt['timely_matches']
    counts = dict(Counter(x['action'] for x in raw['activity']))
    assert counts == receipt['activity_counts']
    assert facts['summary']['tx_count'] == counts.get('tx_begin', 0)
    assert facts['summary']['ack_commit_count'] == counts.get('ack_commit', 0)
    assert len(raw['records']) == 6 and len({x['seq'] for x in raw['records']}) == 6
    assert [x['seq'] for x in raw['records']] == [1,2,3,4,5,6]
    assert facts['queue_summary']['length'] == len(raw['remaining_queue'])
    actual_pass = (assessment['verdict'] == 'PASS' and len(assessment['matches']) == 6 and
                   facts['summary']['timely_public_window_records'] == 6 and counts.get('ack_commit',0) == 6 and
                   facts['queue_summary']['length'] == 0)
    assert actual_pass == (role == 'candidate')
    if role == 'candidate':
        assert counts['tx_begin'] == 12 and counts['ack_commit'] == 6
        assert all(len(r['wire_attempts']) == 2 and len(r['ack_commits']) == 1 for r in facts['records'])
        assert not facts['service_failures']
    else:
        assert counts.get('tx_begin',0) == counts.get('ack_commit',0) == 0
        assert facts['queue_summary']['length'] == 6
        assert facts['summary']['original_minimum_tx_terminal_v'] is None
    fact_path = A/('actual-'+role+'-facts.json')
    save(fact_path, facts)
    event_rows=[]
    for rec, obs in zip(facts['records'], facts['source_gateway_observations']):
        event_rows.append({'seq':rec['seq'],'direction':rec['direction'],'saved_s':rec['saved_s'],
            'wire_times_s':[x['time_s'] for x in rec['wire_attempts']],
            'receiver_times_s':[x['time_s'] for x in rec['receiver_observations']],
            'ack_commit_times_s':[x['time_s'] for x in rec['ack_commits']],
            'public_deadline_s':rec['deadline_s'],'delivery_status':rec['delivery_status'],
            'actual_first_tx_v':obs['tx_begins'][0]['capacitor_v'] if obs['tx_begins'] else None})
    rows.append({'role':role,'original_receipt':bind(folder/'readback.json'),'source_artifacts':{k:receipt[k] for k in ('public_result','raw','assessment')},
        'public_task':entry['public_input'],'full_task_sha256':public['task_sha256'],
        'public_task_sha256':facts['scope']['task_sha256'],'design_sha256':receipt['design_sha256'],
        'execution_status':'COMPLETE','model_valid':True,'domain_errors':[],
        'assessment_verdict':assessment['verdict'],'assessment_failures':assessment['failures'],
        'saved_records':6,'tx_count':counts.get('tx_begin',0),'received_count':len(assessment['receiver_records']),
        'timely_count':len(assessment['matches']),'ack_commit_count':counts.get('ack_commit',0),
        'remaining_queue_length':facts['queue_summary']['length'],
        'minimum_tx_terminal_v':raw['minimum_tx_terminal_v'],
        'peak_handle_force_n':raw['peak_handle_force_n'],
        'energy':{'mechanical_residual_j':assessment['mechanical_residual_j'],'storage_residual_j':assessment['storage_residual_j'],'tolerance_j':assessment['energy_tolerance_j']},
        'actual_full_service_pass':actual_pass,'events':event_rows,'facts':bind(fact_path),
        'physical_qualification':assessment['physical_qualification'],'loss_rate_statistical_claim':assessment['loss_rate_statistical_claim']})
review={'schema':'m4-A-final-independent-service-review-v1','package':result['package'],'at_utc':datetime.now(timezone.utc).isoformat(),
    'status':'A_DONE_CANDIDATE_PASS6_REGRESSION_FAIL0_RETAIN_PARENT','source':interface['source'],'proposal':interface['candidate'],
    'fixed_parent':{'public_result':interface['fixed_parent'],'timely_count':3,'received_count':5,'tx_count':17,'ack_commit_count':5,'remaining_queue_length':1},
    'actual_executions':rows,'adoption':{'eligible':False,'parent_retained':True,'reason':'Original task2 candidate PASS6; identical design original task1 regression FAIL0. Prespecified joint gate not met.','method_status':result['adoption']['adoption_status']},
    's0_result':bind(BASE/'s0/result.json'),'chain':result['chain'],'resource_ledger':result['ledger'],
    'A_resources':{'cheap_calls':1,'cheap_cap':4,'full_dynamic_inputs':0,'model_provider_native_hardware_calls':0,'saved_artifact_readback_new_science_calls':0,'implementation_revisions':0,'post_result_source_candidate_revisions':0},
    'whole_package_observed_resources':{'new_full_dynamic_inputs':ledger['full_dynamic_inputs'],'full_dynamic_wall_s':ledger['full_dynamic_wall_s'],'new_cheap_relations':ledger['cheap_scores'],'model_provider_calls':0,'post_result_revisions':0},
    'claim_boundary':['One explicitly seen-development fixed retry intervention produced a complete nominal task2 service repair in the original consumer.','The original task1 regression fails; cross-task adoption, transfer, learned H, H effectiveness comparisons and RSI are not established.','Public trace is sampled; original ledger and checks do not establish hardware or population loss probability.','No candidate/algorithm replacement, new numerical action, retry, blind search or whole-domain infeasibility claim follows this readback.'],
    'next_handoff':'S0 root closure and reviewer. Stop manual tuning of this DOOR mechanism; preserve both original outcomes and parent authority.'}
save(A/'FINAL-REVIEW.json',review)
print(json.dumps({'status':review['status'],'candidate':{k:rows[0][k] for k in ('saved_records','tx_count','received_count','timely_count','ack_commit_count','remaining_queue_length','minimum_tx_terminal_v')},'regression':{k:rows[1][k] for k in ('saved_records','tx_count','received_count','timely_count','ack_commit_count','remaining_queue_length','minimum_tx_terminal_v')},'eligible_to_adopt':False,'new_science_or_model_for_readback':0,'resource_ledger':review['whole_package_observed_resources']}))
