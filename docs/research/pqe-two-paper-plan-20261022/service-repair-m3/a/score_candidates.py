"""Counted private A approximation calls; never execute scientific consumer."""
import json, time, hashlib
from pathlib import Path
from datetime import datetime, timezone
from bfworld.agentlab.pqe20261022.service_relations import predict_candidate
ROOT = Path("/Users/depengsu/Documents/Long-Horizon AI Agent")
A = ROOT/'docs/research/pqe-two-paper-plan-20261022/service-repair-m3/a'
BASE = A.parent.parent/'dynamic-decision-m2'
tasks = json.loads((BASE/'a/host/tasks.json').read_text())
facts = json.loads((A/'initial-service-facts.json').read_text())
plans = json.loads((A/'prediction-plans.json').read_text())
ledger_path = A/'cheap-ledger.json'
ledger = json.loads(ledger_path.read_text())
for plan in plans['candidates']:
    if any(c['id'] == plan['id'] for c in ledger['calls']):
        continue
    if ledger['total_calls'] >= ledger['cap']:
        raise RuntimeError('A_CHEAP_CAP')
    call = {'id':plan['id'], 'status':'STARTED', 'started_utc':datetime.now(timezone.utc).isoformat(), 'design':plan['design'], 'purpose':plan['purpose']}
    ledger['calls'].append(call)
    ledger['total_calls'] += 1
    ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
    begin = time.perf_counter()
    try:
        prediction = predict_candidate(tasks['DOOR-M2-GATE-RECOVER-20261023-v1'],plan['design'],facts)
        payload = (json.dumps(prediction,indent=2,allow_nan=False)+'\n').encode()
        target = A/('prediction-'+plan['id']+'.json')
        with target.open('xb') as f: f.write(payload)
        call.update(status='COMPLETE',wall_s=time.perf_counter()-begin,output_path=str(target),sha256=hashlib.sha256(payload).hexdigest(),prediction_status=prediction['prediction_status'],selection_metrics=prediction['selection_metrics'])
        print(json.dumps({'id':plan['id'],'metrics':prediction['selection_metrics'],'necessary_failures':prediction['necessary_failures'],'windows':[{'i':w['window'],'status':w['status'],'timely':w['timely'],'attempts':len(w.get('attempts',[])),'receive':w.get('first_receive_s'),'margin':w.get('minimum_terminal_margin_v')} for w in prediction['service_prediction']['windows']]}))
    except Exception as exc:
        call.update(status='ERROR_RETAINED',error=repr(exc),wall_s=time.perf_counter()-begin)
        ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
        raise
    ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
