#!/usr/bin/env python3
"""Summarize the frozen finite pilot without model or solver calls."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'scripts'))
from run_organization_pilot import read_trial_final


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path,
        default=Path.home()/'.local/share/bf-agent-architecture-v2')
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent/'results')
    args = parser.parse_args()
    root = args.runtime/'continuous-design'
    registry = read(root/'pilot/registry.json')
    incident=read(root/'reconciliation/result.json')
    trials = []
    for entry in registry['trials']:
        path = root/'pilot/trials'/entry['key']/'final.json'
        if not path.exists():
            raise ValueError('FINITE_TRIAL_PENDING:'+entry['key'])
        final = read_trial_final(path.parent)
        metrics = dict(final['metrics'])
        settlement_path=path.parent/'post-trial-settlement.json'
        settlement=read(settlement_path) if settlement_path.exists() else None
        late=settlement['late_executions'] if settlement else []
        metrics['candidate_evaluations']+=len(late)
        late_native=settlement['unreported_native_dispatches'] if settlement else []
        partial=(incident['proof']['retained_partial_native_dispatches']
            if incident['registered_execution']['project_id']==entry['project_id'] else [])
        current = next(s for s in final['view']['systems'] if s['id']==metrics['current_system'])
        gates = current['current_qualification'].get('gates',{})
        owners = [entry['owner'], *metrics['workers']]
        errors = collections.Counter()
        harnesses = set()
        lead_facts = []
        for owner in owners:
            folder = args.runtime/'workbench/sessions'/owner
            trace = folder/'trace.jsonl'
            if trace.exists():
                for line in trace.read_text().splitlines():
                    event = json.loads(line)
                    if owner==entry['owner'] and event.get('type')=='repository_tool_fact':
                        lead_facts.append(event)
                    if event.get('type') == 'tool_execution_end' and event.get('isError'):
                        texts = [b.get('text','') for b in event.get('result',{}).get('content',[]) if b.get('type')=='text']
                        errors.update([' '.join(texts)[:500]])
            for receipt in folder.glob('repository-attempts/*/receipt.json'):
                value=read(receipt)
                if value.get('harness_id'):harnesses.add(value['harness_id'])
        if metrics['unknown_requests']:
            raise ValueError('UNRECONCILED_PROVIDER_REQUEST')
        closures = [e['result'] for e in lead_facts if e.get('action')=='close' and
            e.get('result',{}).get('system_commit')==metrics['current_system']]
        decisions = [e['result'] for e in lead_facts if e.get('action')=='decide']
        completed_loop = bool(metrics['actual_design_changes'] and metrics['same_version_releases'] and closures)
        trials.append({**metrics, 'stage':entry['stage'], 'case':entry['case'],
            'organization':entry['organization'], 'controller_status':final['state']['status'],
            'controller_error':final['state']['error'], 'harnesses':sorted(harnesses),
            'preflight_recovery':final.get('preflight_recovery'),
            'partial_native_dispatches':len(partial),
            'late_native_dispatches':len(late_native),
            'total_native_dispatches':metrics['native_dispatches']+len(partial)+len(late_native),
            'interrupted_execution_inputs':int(bool(partial)),
            'post_trial_reconciliation':incident if partial else None,
            'post_trial_settlement':settlement,
            'request_limit_reached':metrics['model_calls']>=entry['policy']['limits']['requests_per_trial'],
            'evaluation_limit_reached':metrics['candidate_evaluations']>=entry['policy']['limits']['candidate_evaluations_per_trial'],
            'gate_status':{key:value['status'] for key,value in gates.items()},
            'power_result':gates.get('power_service',{}).get('findings'),
            'receiver_result':gates.get('receiver_service',{}).get('findings'),
            'execution_ids':[e['id'] for e in final['view']['task_executions']+late],
            'release_ids':[r['id'] for r in final['view']['releases']],
            'completed_candidate_loop':completed_loop,
            'end_to_end_service':bool(completed_loop and metrics['valid_service']),
            'decisions':[{k:r.get(k) for k in ('id','decision','to_design')} for r in decisions],
            'tool_errors':dict(errors), 'receipt_sha256':hashlib.sha256((path.parent/'recovery-final.json'
                if final.get('preflight_recovery') else path).read_bytes()).hexdigest()})
    pairs = []
    for case in sorted({t['case'] for t in trials if t['stage']=='sources'}):
        arms = {t['organization']:t for t in trials if t['case']==case}
        direct, worker = arms['single'], arms['temporary']
        pairs.append({'case':case, 'direct_correct':direct['source_correct'],
            'worker_correct':worker['source_correct'],
            'parent_consumed':bool(worker['parent_consumed_worker_results']),
            'direct_cost_usd':direct['cost_upper_bound_usd'],
            'worker_cost_usd':worker['cost_upper_bound_usd'],
            'cost_ratio':worker['cost_upper_bound_usd']/direct['cost_upper_bound_usd'],
            'direct_errors':direct['failed_tool_calls'], 'worker_errors':worker['failed_tool_calls'],
            'meets_pair_adoption_rule':bool(worker['source_correct'] and worker['parent_consumed_worker_results'] and
                (worker['cost_upper_bound_usd']<direct['cost_upper_bound_usd'] or
                 worker['failed_tool_calls']<direct['failed_tool_calls']))})
    organizations = []
    for arm in ('single','temporary','fixed','joint'):
        rows = [t for t in trials if t['stage']=='organizations' and t['organization']==arm]
        feasible = [t for t in rows if t['case']!='T2-short-validity']
        organizations.append({'organization':arm, 'trials':len(rows),
            'valid_service':sum(t['valid_service'] for t in rows),
            'completed_candidate_loops':sum(t['completed_candidate_loop'] for t in rows),
            'end_to_end_service':sum(t['end_to_end_service'] for t in rows),
            'feasible_task_service':sum(t['valid_service'] for t in feasible),
            'feasible_tasks':len(feasible),
            'feasible_deliveries':sum(bool(t['same_version_releases']) for t in feasible),
            'feasible_workers':sum(len(t['workers']) for t in feasible),
            'feasible_model_calls':sum(t['model_calls'] for t in feasible),
            'feasible_cost_usd':sum(t['cost_upper_bound_usd'] for t in feasible),
            'feasible_tool_errors':sum(t['failed_tool_calls'] for t in feasible),
            'workers':sum(len(t['workers']) for t in rows),
            'trials_with_workers':sum(bool(t['workers']) for t in rows),
            'same_version_deliveries':sum(bool(t['same_version_releases']) for t in rows),
            'actual_design_changes':sum(t['actual_design_changes'] for t in rows),
            'model_calls':sum(t['model_calls'] for t in rows),
            'tokens':sum(t['total_tokens'] for t in rows),
            'cost_usd':sum(t['cost_upper_bound_usd'] for t in rows),
            'tool_errors':sum(t['failed_tool_calls'] for t in rows),
            'native_dispatches':sum(t['total_native_dispatches'] for t in rows),
            'false_adoption':sum(t['false_adoption'] for t in rows)})
    old = read(root/'original-owner-state.json')
    owner = read(args.runtime/'task-design/owner.json')['owner']
    db = sqlite3.connect((args.runtime/'workbench/state/workbench.sqlite').as_uri()+'?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY rowid',(owner,))][old['model_calls']:]
    db.close()
    original = {'owner':owner, 'new_model_calls':len(rows),
        'cost_upper_bound_usd':sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows),
        'request_states':dict(collections.Counter(r['status'] for r in rows))}
    view=read(root/'cycle-2-view.json');base=read(root/'transition.json')['id']
    systems={s['id']:s for s in view['systems']};executions=[]
    for execution in view['task_executions']:
        source=systems[execution['target']]
        while source['id']!=base and source.get('parent') in systems:
            source=systems[source['parent']]
        if source['id']==base:executions.append(execution)
    original.update({'current_system':view['project']['submitted'],
        'adopted_system':view['project']['adopted'],
        'candidate_evaluations':len(executions),
        'native_dispatches':sum(len(e['metrics'].get('native_dispatches',[])) for e in executions)})
    output = {'protocol_sha256':registry['protocol_sha256'], 'original':original,
        'trials':trials, 'source_pairs':pairs, 'organizations':organizations,
        'total_pilot_calls':sum(t['model_calls'] for t in trials),
        'total_pilot_cost_usd':sum(t['cost_upper_bound_usd'] for t in trials),
        'total_pilot_native_dispatches':sum(t['total_native_dispatches'] for t in trials),
        'late_native_dispatches':sum(t['late_native_dispatches'] for t in trials),
        'zero_call_preflight_recoveries':sum(bool(t['preflight_recovery']) for t in trials),
        'storage_reconciliation':{'trial':'T2-short-validity--joint','status':'FAILED',
            'partial_native_dispatches':len(incident['proof']['retained_partial_native_dispatches']),
            'new_model_requests':incident['new_model_requests'],'new_native_solves':incident['new_native_solves']},
        'scope':'finite descriptive pilot; one replicate per task/arm; model and numerical apparatus fixed'}
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'summary.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    columns = ['case','organization','stage','source_correct','valid_service','same_version_releases',
        'actual_design_changes','model_calls','total_tokens','cost_upper_bound_usd','failed_tool_calls',
        'candidate_evaluations','native_dispatches','partial_native_dispatches','late_native_dispatches','total_native_dispatches',
        'interrupted_execution_inputs','false_adoption','wall_seconds','owner','current_system']
    with (args.out/'trials.csv').open('w',newline='') as handle:
        writer = csv.DictWriter(handle,columns,extrasaction='ignore',lineterminator='\n')
        writer.writeheader();writer.writerows(trials)
    print(json.dumps({k:v for k,v in output.items() if k!='trials'},ensure_ascii=False))


if __name__=='__main__':
    main()
