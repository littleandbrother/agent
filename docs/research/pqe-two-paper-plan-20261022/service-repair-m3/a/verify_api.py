"""One offline service-fact check; prediction calls are separately ledgered."""
import json
from pathlib import Path
from copy import deepcopy
from bfworld.agentlab.pqe20261022.service_relations import extract_service_facts

ROOT = Path("/Users/depengsu/Documents/Long-Horizon AI Agent")
BASE = ROOT / 'docs/research/pqe-two-paper-plan-20261022'
A = BASE / 'service-repair-m3/a'
TASKS = json.loads((BASE / 'dynamic-decision-m2/a/host/tasks.json').read_text())
RESULT = json.loads((BASE / 'dynamic-decision-m2/s0/episodes/m2-02-f/actions/01/public-result.json').read_text())
TASK = TASKS[RESULT['task_id']]
DESIGN = RESULT['design']
facts = extract_service_facts(TASK, DESIGN, RESULT)
checks = {}
checks['six_saves_three_late_three_unreceived'] = (facts['summary']['saved_records_observed'] == 6 and facts['summary']['late_public_window_records'] == 3 and facts['summary']['unreceived_records'] == 3)
checks['no_observed_sequence_reuse'] = facts['summary']['different_record_sequence_reuse']['status'] == 'NOT_OBSERVED_COMPLETE_SAVES'
checks['ack_not_wire_removal'] = all((len(r['ack_commits']) == 1) == (r['seq'] <= 3) for r in facts['records'])
checks['retained_fifo_backlog'] = facts['queue_summary']['length'] == 3 and facts['queue_summary']['head']['seq'] == 4 and bool(facts['queue_summary']['observed_head_blocking'])
checks['public_failures_independent_of_phase_label'] = facts['summary']['service_failure_observed'] and 'failed_phases' not in facts
bad = deepcopy(RESULT)
bad['design']['retry_s'] = 0.23
checks['design_binding'] = extract_service_facts(TASK, DESIGN, bad)['status'] == 'UNBOUND_DESIGN'
private = deepcopy(RESULT)
private['assessment'] = {'private_truth': 'DO_NOT_CONSUME', 'pass': True}
private['ground_truth'] = [{'seq': 999}]
checks['private_material_ignored'] = extract_service_facts(TASK, DESIGN, private) == facts
sparse = deepcopy(RESULT)
sparse['facts']['receiver_records'] = sparse['facts']['receiver_records'][:1]
sparse['facts']['detail_catalog'] = {'receiver_records': {'count': 3}}
sf = extract_service_facts(TASK, DESIGN, sparse)
checks['sparse_receive_absence_stays_unknown'] = sf['summary']['unreceived_records'] == 0 and any(r['delivery_status'] == 'UNKNOWN' for r in sf['records'])
retry = deepcopy(RESULT)
w = next(e for e in retry['facts']['activity'] if e['action'] == 'wire_complete')
retry['facts']['activity'].append({**w, 'time_s': w['time_s'] + 0.001})
rf = extract_service_facts(TASK, DESIGN, retry)
checks['same_record_retransmission_not_sequence_reuse'] = rf['summary']['same_record_retransmissions_observed'] == 1 and rf['summary']['different_record_sequence_reuse']['status'] == 'NOT_OBSERVED_COMPLETE_SAVES'
reuse = deepcopy(RESULT)
reuse['facts']['records'].append({'seq': 1, 'direction': 1, 'committed_s': 70.0, 'durable': True})
uf = extract_service_facts(TASK, DESIGN, reuse)
checks['different_save_reuse_separate_and_ambiguous'] = uf['summary']['different_record_sequence_reuse']['status'] == 'OBSERVED' and all(r['delivery_status'] == 'UNKNOWN_AMBIGUOUS_SEQUENCE_REUSE' for r in uf['records'] if r['seq'] == 1)
checks['finite_json'] = bool(json.dumps(facts, allow_nan=False))
report = {'schema': 'm3-A-offline-checks-v1', 'checks': checks, 'passed': all(checks.values()), 'cheap_calls': 0, 'full_dynamic_calls': 0, 'model_calls': 0}
(A / 'offline-checks.json').write_text(json.dumps(report, indent=2) + '\n')
(A / 'initial-service-facts.json').write_text(json.dumps(facts, indent=2, allow_nan=False) + '\n')
print(json.dumps(report))
assert report['passed']
