"""Predeclared task progress, separate from illustration/file availability."""
import hashlib
import json
from pathlib import Path

SCHEMA='bf-paper-reproduction-task-v1'
STATES={'not_started','generated','executed','passed','failed','unknown','out_of_domain'}

def seal(plan):
    if plan.get('schema_version')!=SCHEMA or not plan.get('source_papers') or not plan.get('scope'):
        raise ValueError('REPRODUCTION_PLAN_SCHEMA')
    tasks=plan.get('tasks');ids=set()
    if not isinstance(tasks,list) or not 1<=len(tasks)<=80:raise ValueError('REPRODUCTION_TASK_BOUNDS')
    for task in tasks:
        if not isinstance(task,dict) or not task.get('id') or task['id'] in ids:raise ValueError('REPRODUCTION_TASK_ID')
        ids.add(task['id'])
        if task.get('tier') not in ('simulation','hardware') or not task.get('acceptance') or not task.get('source_locator'):
            raise ValueError('REPRODUCTION_TASK_CRITERIA_REQUIRED')
        if type(task.get('eligible')) is not bool:raise ValueError('REPRODUCTION_DENOMINATOR_REQUIRED')
    if not any(t['eligible'] for t in tasks):raise ValueError('REPRODUCTION_DENOMINATOR_EMPTY')
    return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def evaluate(plan, plan_hash, records, trusted_receipts=None):
    """Operator evaluator supplies hash-bound receipts, never participant flags.

    trusted_receipts maps digest to a file outside the participant workspace.
    With no trusted receipts, generated/executed records can be inspected but
    no pass or autonomy is accepted. This is not a cryptographic trust service.
    """
    if seal(plan)!=plan_hash:raise ValueError('REPRODUCTION_PLAN_SEAL_DRIFT')
    tasks={t['id']:t for t in plan['tasks']};seen=set();resolved=[]
    for record in records:
        tid=record.get('task_id');state=record.get('status')
        if tid not in tasks or tid in seen or state not in STATES:raise ValueError('REPRODUCTION_RECORD_INVALID')
        seen.add(tid);evidence=record.get('evidence',[])
        # PASS requires independently sealed execution facts. A PDF or prose
        # written by the participant, even when hashed, is not an evaluator.
        if record.get('actor') not in ('agent','operator','inherited'):raise ValueError('REPRODUCTION_ACTOR_REQUIRED')
        for e in evidence:
            p=Path(e['path'])
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=e['sha256']:raise ValueError('REPRODUCTION_EVIDENCE_HASH')
        qualified=False;autonomous=False
        if state=='passed':
            receipt_hash=record.get('executor_receipt_sha256')
            receipt_path=(trusted_receipts or {}).get(receipt_hash)
            if not receipt_path or not evidence:raise ValueError('REPRODUCTION_UNSUPPORTED_PASS')
            receipt_path=Path(receipt_path)
            if not receipt_path.is_file() or hashlib.sha256(receipt_path.read_bytes()).hexdigest()!=receipt_hash:
                raise ValueError('REPRODUCTION_RECEIPT_HASH')
            receipt=json.loads(receipt_path.read_text())
            if (receipt.get('plan_sha256')!=plan_hash or receipt.get('task_id')!=tid or
                    receipt.get('status')!='passed' or receipt.get('actor')!=record['actor'] or
                    receipt.get('evidence')!=evidence or not receipt.get('validator_id')):
                raise ValueError('REPRODUCTION_RECEIPT_BINDING')
            qualified=True
            trace=receipt.get('agent_trace')
            if record['actor']=='agent':
                if not trace or record.get('agent_trace_sha256')!=trace.get('sha256'):
                    raise ValueError('REPRODUCTION_AGENT_TRACE_REQUIRED')
                path=Path(trace['path'])
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=trace['sha256']:
                    raise ValueError('REPRODUCTION_AGENT_TRACE_HASH')
                autonomous=receipt.get('human_candidate_edits')==0 and record.get('human_candidate_edits')==0
        resolved.append({**record,'autonomous_qualified':autonomous,'independently_passed':bool(qualified)})
    by_id={r['task_id']:r for r in resolved}
    denominator=sum(t['eligible'] for t in tasks.values())
    numerator=sum(bool(t['eligible'] and by_id.get(tid,{}).get('autonomous_qualified')) for tid,t in tasks.items())
    passed=sum(bool(t['eligible'] and by_id.get(tid,{}).get('independently_passed')) for tid,t in tasks.items())
    return {'schema_version':'bf-paper-reproduction-progress-v1','plan_sha256':plan_hash,
            'predeclared_denominator':denominator,'agent_independent_passed':numerator,'all_actors_independent_passed':passed,
            'autonomous_fraction':numerator/denominator,'target_80_percent_reached':numerator/denominator>=.8,
            'tasks':[{'id':tid,**t,'record':by_id.get(tid,{'status':'not_started'})} for tid,t in tasks.items()],
            'claim_boundary':'Predeclared task completion in stated model tier; not source-figure coverage, image count, arbitrary paper reproducibility or physical acceptance.'}
