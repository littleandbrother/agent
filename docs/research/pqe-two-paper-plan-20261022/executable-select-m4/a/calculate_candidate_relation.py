"""ONE registered conditional engineering relation, not a new trajectory."""
import json, math
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path("/Users/depengsu/Documents/Long-Horizon AI Agent")
PLAN=ROOT/'docs/research/pqe-two-paper-plan-20261022'
A=PLAN/'executable-select-m4/a'
ledger_path=A/'cheap-ledger.json'
ledger=json.loads(ledger_path.read_text())
if ledger['total_calls'] or ledger['calls']: raise RuntimeError('RELATION_ALREADY_CONSUMED')
call={'id':'one-fixed-retry-development-relation','status':'STARTED','started_utc':datetime.now(timezone.utc).isoformat(),'scope':'Conditional timing/no-source charge bounds using saved parent; no candidate voltage trajectory or original consumer.'}
ledger['calls'].append(call);ledger['total_calls']+=1
ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
parent=json.loads((PLAN/'service-repair-m3/s0/engineering/02/public-result.json').read_text())
task=json.loads((PLAN/'dynamic-decision-m2/a/host/tasks.json').read_text())[parent['task_id']]
facts=json.loads((A/'saved-trajectory-02.json').read_text())
design=parent['design'];c=task['components']; retry=0.85
cap=design['capacitance_f'];leak=c['max_v']/c['leakage_ohm']
rows=[]
for record in facts['source_gateway_observations']:
    tx=record['tx_begins'][0]; wire=record['first_wire_s']; recovery=record['first_available_gateway_at_or_after_query_s'];deadline=record['deadline_s']
    second_wire=wire+retry+c['tx_s']
    before_second=(c['tx_a']+leak)*c['tx_s']+(c['idle_a']+leak)*retry
    through_second=before_second+(c['tx_a']+leak)*c['tx_s']
    through_ack=through_second+(c['write_a']+leak)*c['write_s']
    rows.append({'seq':record['seq'],'direction':record['direction'],'original_first_tx_s':tx['time_s'],'original_first_tx_v':tx['capacitor_v'],'original_first_wire_s':wire,'public_gateway_recovery_s':recovery,'public_deadline_s':deadline,'fixed_first_wire_second_completion_hypothesis_s':second_wire,'retry_timing_interval_s':[max(0,recovery-wire-c['tx_s']),deadline-wire-c['tx_s']],'hypothetical_second_wire_inside_gateway_and_deadline':any(a<=second_wire<=b for a,b in task['gateway_windows']) and second_wire<=deadline,'conditional_second_start_v_lower':tx['capacitor_v']-before_second/cap,'conditional_second_tx_min_terminal_v_lower':tx['capacitor_v']-through_second/cap-c['tx_a']*design['esr_ohm'],'conditional_ack_end_terminal_v_lower':tx['capacitor_v']-through_ack/cap-c['write_a']*design['esr_ohm'],'entry_condition':'These are bounds IF the new run reaches this observed parent first-TX entry (or higher), stays powered, and has no competing capture. Old V is never supplied as an initial state or asserted as a new candidate voltage.'})
interval=[max(r['retry_timing_interval_s'][0] for r in rows),min(task['design_domain']['retry_s']['max'],min(r['retry_timing_interval_s'][1] for r in rows))]
result={'schema':'m4-A-one-conditional-relation-v1','cheap_calls':1,'candidate_retry_s':retry,'all_six_records':rows,'intersection_with_legal_retry_domain_s':interval,'conditions':['First-wire times and voltages are saved-parent factual anchors, not predicted new-design observations.','No source after first TX is credited; leakage bounded by original max_v/Rleak; nominal constant phase loads and original retry semantics only.','Cross-event changes, later cold startup, source feedback and queue interactions require the full original consumer from original initial state.'],'no_candidate_simulation':True,'no_old_voltage_initialization':True,'service_verdict':'UNKNOWN'}
assert interval[0]<=retry<=interval[1]
assert all(r['hypothetical_second_wire_inside_gateway_and_deadline'] and r['conditional_second_start_v_lower']>=design['tx_gate_v'] and r['conditional_second_tx_min_terminal_v_lower']>=design['brownout_v'] and r['conditional_ack_end_terminal_v_lower']>=design['brownout_v'] for r in rows)
(A/'candidate-condition-calculation.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
call.update(status='COMPLETE',candidate_retry_s=retry,output_path=str(A/'candidate-condition-calculation.json'),service_verdict='UNKNOWN')
ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
print(json.dumps({'retry_s':retry,'interval':interval,'second_start_min_lower_v':min(r['conditional_second_start_v_lower'] for r in rows),'second_tx_min_lower_v':min(r['conditional_second_tx_min_terminal_v_lower'] for r in rows),'ack_end_min_lower_v':min(r['conditional_ack_end_terminal_v_lower'] for r in rows),'total_calls':ledger['total_calls'],'service_verdict':'UNKNOWN'}))
