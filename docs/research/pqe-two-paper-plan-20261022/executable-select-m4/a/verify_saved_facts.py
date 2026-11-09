"""Saved-trajectory readback only: no predictions or original consumer."""
import json, hashlib
from pathlib import Path
from copy import deepcopy
import bfworld.agentlab.pqe20261022.service_relations as old
from bfworld.agentlab.pqe20261022.trajectory_service_facts import extract_trajectory_facts
ROOT=Path("/Users/depengsu/Documents/Long-Horizon AI Agent")
PLAN=ROOT/'docs/research/pqe-two-paper-plan-20261022'
A=PLAN/'executable-select-m4/a'
tasks=json.loads((PLAN/'dynamic-decision-m2/a/host/tasks.json').read_text())
task=tasks['DOOR-M2-GATE-RECOVER-20261023-v1']
checks={}
outputs=[]
def forbidden(*args,**kwargs): raise AssertionError('PREDICTOR_FORBIDDEN')
old.predict_candidate=forbidden
for ordinal in (1,2):
    source=PLAN/f'service-repair-m3/s0/engineering/{ordinal:02d}/public-result.json'
    data=source.read_bytes(); result=json.loads(data)
    fact=extract_trajectory_facts(task,result['design'],result)
    checks[f'parent{ordinal}_full_chain']=fact['status']=='PUBLIC_TRAJECTORY_FACTS' and len(fact['records'])==6 and fact['summary']['tx_count']==17 and fact['summary']['ack_commit_count']==5 and fact['queue_summary']['length']==1
    checks[f'parent{ordinal}_service']=fact['summary']['timely_public_window_records']==3 and fact['summary']['late_public_window_records']==2 and fact['summary']['unreceived_records']==1
    checks[f'parent{ordinal}_original_timeline']=fact['timeline']==result['facts']['activity'] and len(fact['power_epochs'])==3
    close=next(x for x in fact['source_gateway_observations'] if x['seq']==2)
    checks[f'parent{ordinal}_close_recovery']=close['actual_wires_before_gateway']==2 and all(x['sampled_gate_margin_v']<0 for x in (close['recovery_samples']['at_or_before'],close['recovery_samples']['at_or_after']))
    private=deepcopy(result); private['assessment']={'truth':[{'DO_NOT_USE':1}]}
    checks[f'parent{ordinal}_private_ignored']=extract_trajectory_facts(task,result['design'],private)==fact
    bad=deepcopy(result); bad['design']['retry_s']=0.22
    checks[f'parent{ordinal}_design_bound']=extract_trajectory_facts(task,result['design'],bad)['status']=='UNBOUND_DESIGN'
    payload=(json.dumps(fact,indent=2,allow_nan=False)+'\n').encode()
    target=A/f'saved-trajectory-{ordinal:02d}.json'
    with target.open('xb') as f:f.write(payload)
    outputs.append({'source':{'path':str(source),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)},'output':{'path':str(target),'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}})
zero=json.loads((PLAN/'service-repair-m3/s0/episodes/m3-u/actions/01/public-result.json').read_text())
z=extract_trajectory_facts(task,zero['design'],zero)
checks['no_tx_no_fabricated_tx_margin']=z['summary']['tx_count']==0 and z['summary']['original_minimum_tx_terminal_v'] is None
sparse=deepcopy(zero); sparse['facts']['activity']=sparse['facts']['activity'][:4]; sparse['facts']['detail_catalog']={'activity':{'count':len(zero['facts']['activity'])}}
s=extract_trajectory_facts(task,zero['design'],sparse)
checks['incomplete_activity_not_complete_chain']=s['summary']['complete_public_event_lists'] is False
report={'schema':'m4-A-saved-fact-verification-v1','passed':all(checks.values()),'checks':checks,'outputs':outputs,'cheap_calls':0,'full_science_calls':0,'model_calls':0}
(A/'saved-fact-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'checks':checks,'output_bytes':sum(x['output']['bytes'] for x in outputs)}))
assert report['passed']
