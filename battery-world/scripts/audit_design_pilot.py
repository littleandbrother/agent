#!/usr/bin/env python3
"""Read-only independent checks for the real Pi pilot; no provider or solver calls."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from bfworld.agentlab.simulation_tasks import evaluate, check_candidate
from bfworld.agentlab.simulation_chain.contracts import file_hash


def audit(home, study):
    seal=json.loads((study/'seal.json').read_text());protocol=seal['protocol'];binding=seal['task']
    amendment=study/'completion-allocation-amendment.json'
    allocation=json.loads(amendment.read_text()) if amendment.exists() else None
    owner_ceiling=allocation['new_owner_ceiling_usd'] if allocation else protocol['max_usd_per_trial']
    if allocation and allocation['study_max_usd']!=protocol['requested_paid_allocation_usd']:
        raise ValueError('STUDY_ALLOCATION_DRIFT')
    db=sqlite3.connect((home/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    rows=[];errors=[];seen=set()
    for trial in protocol['pi_trials']:
        owner=db.execute('SELECT owner FROM research_model_owners WHERE protocol=? AND trial=?',(protocol['id'],trial['id'])).fetchone()
        item={'trial':trial['id'],'started':bool(owner),'candidates':[],'submitted':False}
        if owner:
            owner=owner['owner'];item['owner']=owner
            jobs=list(db.execute('SELECT * FROM engineering_jobs WHERE owner=? ORDER BY created',(owner,)))
            if len(jobs)>protocol['pi_max_candidates_per_trial']:errors.append(trial['id']+': quota reset')
            for job in jobs:
                req=json.loads(job['request']);check_candidate(binding,req['parameters'])
                directory=home/'engineering'/job['id']
                result=json.loads(job['result']) if job['result'] else {}
                if not result:
                    item['candidates'].append({'id':job['id'],'status':job['status']});continue
                manifest={x['name']:x for x in result['artifacts']}
                verified=[]
                for name in ('result.json','design-spec.json','task-evaluation.json','receiver.json','energy.json','coupling-iterations.json'):
                    if name in manifest:
                        if file_hash(directory/name)!=manifest[name]['sha256']:errors.append(job['id']+': artifact '+name)
                        verified.append(name)
                data=json.loads((directory/'result.json').read_text())
                spec=json.loads((directory/'design-spec.json').read_text())
                receiver=json.loads((directory/'receiver.json').read_text()) if (directory/'receiver.json').exists() else {}
                independent=evaluate(binding,spec,data,receiver)
                if independent!=data['task_evaluation']:errors.append(job['id']+': independent verdict mismatch')
                item['candidates'].append({'id':job['id'],'run_status':data['run_status'],'evaluation':independent,'verified_artifacts':verified})
                seen.add(job['id'])
            submission=db.execute('SELECT receipt FROM simulation_task_submissions WHERE owner=?',(owner,)).fetchone()
            if submission:
                r=json.loads(submission['receipt']);item['submitted']=True;item['selection']=r
                if r['job_id'] not in {j['id'] for j in jobs}:errors.append(trial['id']+': selection ownership')
                if r['task_hash']!=binding['task_hash'] or r['result_sha256']!=file_hash(home/'engineering'/r['job_id']/'result.json'):errors.append(trial['id']+': selection identity')
            usage=[dict(r) for r in db.execute('SELECT id,status,charged,reserved,usage,error FROM model_requests WHERE owner=?',(owner,))]
            item['calls']=len(usage);item['cost_upper_usd']=sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in usage)
            item['locally_settled_usd']=sum(r['charged'] for r in usage if r['status']=='SETTLED')
            item['original_trial_limit_usd']=protocol['max_usd_per_trial']
            item['original_trial_limit_exceeded']=item['cost_upper_usd']>=protocol['max_usd_per_trial']
            item['unsettled']=sum(r['status']!='SETTLED' for r in usage)
            if item['cost_upper_usd']>=owner_ceiling:errors.append(trial['id']+': owner cost cap')
            item['transport_continuations']=len(list((study/'trials'/trial['id']).glob('continuation-*/start.json')))
        rows.append(item)
    usage=list(db.execute('SELECT m.* FROM model_requests m JOIN research_model_owners o ON o.owner=m.owner WHERE o.protocol=?',(protocol['id'],)))
    total=sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in usage)
    if total>=protocol['requested_paid_allocation_usd']:errors.append('study cost cap')
    a=study/'continuation-authorization.json'
    if a.exists():
        v=json.loads(a.read_text())
        if file_hash(study/'agent-runtime-seal.json')!=v['original_runtime_sha256']:errors.append('original runtime seal changed')
        if file_hash(study/'trials/baseline-r1/receipt.json')!=v['original_failed_receipt_sha256']:errors.append('original failure overwritten')
    db.close()
    return {'schema_version':'independent-pi-audit-v2','task_hash':binding['task_hash'],'trials':rows,
        'submitted':sum(r['submitted'] for r in rows),'actual_candidates':len(seen),'study_model_requests':len(usage),
        'study_cost_upper_usd':total,'errors':errors,'integrity_passed':not errors,
        'pooled_completion_allocation':bool(allocation),'owner_ceiling_usd':owner_ceiling,
        'submitted_execution_trajectories':sum(r['submitted'] and bool(r['candidates']) for r in rows),
        'feedback_linkage_status':'not_established_by_submission_or_this_audit',
        'original_trial_allocation_deviations':[r['trial'] for r in rows if r.get('original_trial_limit_exceeded')],
        'allocation_authority':'Agent interpretation of general user continuation instruction; no separate explicit numerical per-trial amendment' if allocation else 'frozen_original_limits',
        'claim':'Execution and nominal-model audit only; no physical qualification, architecture synthesis or method superiority.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve original audit')
    result=audit(a.home,a.study);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='trials'},ensure_ascii=False))
