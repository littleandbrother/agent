#!/usr/bin/env python3
"""Read-only audit of the four actual design attempts and generate bound data."""
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3

RUNTIME=Path.home()/'.local/share/bf-campaign-20261019-s0'
HERE=Path(__file__).resolve().parent
APP=HERE.parents[3]


def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()


def strings(v):
    if isinstance(v,str):yield v
    elif isinstance(v,list):
        for x in v:yield from strings(x)
    elif isinstance(v,dict):
        for x in v.values():yield from strings(x)


def audit():
    registry=load(RUNTIME/'registry.json')
    protocol=load(APP/'configs/studies/parallel-20261019/methods/protocol.json')
    con=sqlite3.connect((RUNTIME/'workbench/state/workbench.sqlite').as_uri()+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    rows=[];cores=[];harnesses=[];earlier_new=set()
    warm={p.name for p in (RUNTIME/'cache-start').iterdir() if (p/'completed.json').is_file()}
    historical=Path.home()/'.local/share/bf-agent-architecture-v2/workbench/design-lab/repository/feedback-native-cache'
    historical_keys={p.name for p in historical.iterdir() if (p/'completed.json').is_file()}
    all_owners={e['owner'] for e in registry['trials']}
    observed_owners={r[0] for r in con.execute('SELECT DISTINCT owner FROM model_requests')}
    assert observed_owners<=all_owners, 'UNREGISTERED_MODEL_OWNER'
    assert len(all_owners)==4, 'OWNERS_NOT_FRESH'
    for e in registry['trials']:
        trial=RUNTIME/'trials'/e['key']
        final=load(trial/'final.json')
        stop=load(trial/'stop.json') if (trial/'stop.json').exists() else None
        dispatch=load(trial/'dispatch.json')
        view=load(trial/'view.json')
        current=next(s for s in view['systems'] if s['id']==final['current_system'])
        initial=next(s for s in view['systems'] if s['id']==e['initial_system'])
        events=[json.loads(l) for l in (RUNTIME/'workbench/sessions'/e['owner']/'trace.jsonl').read_text().splitlines() if l]
        loaded=next(v for v in events if v.get('type')=='repository_controller_loaded')
        assert loaded['resume_message_count']==0, 'PRIOR_TRAJECTORY_CONTEXT'
        assert loaded['model']=='deepseek-flash', 'BACKEND_MISMATCH'
        assert dispatch['cache_start_sha256']==protocol['cache_start'], 'CACHE_START_MISMATCH'
        assert e['goal']==protocol['prompts'][e['arm']], 'PROMPT_CHANGED'
        assert e['goal_sha256']==digest(e['goal'])==final['goal_sha256'], 'PROMPT_HASH_MISMATCH'
        wire=con.execute('SELECT wire FROM model_request_evidence WHERE owner=? ORDER BY rowid LIMIT 1',(e['owner'],)).fetchone()
        first=load(trial/'ledger.json')[0]
        assert wire is not None and e['goal'] in '\n'.join(strings(json.loads(wire[0]))), 'ACTUAL_GOAL_NOT_CONSUMED'
        assert initial['files']['firmware/main.c']['sha256']==e['input_hashes']['firmware/main.c'], 'INITIAL_INPUT_MISMATCH'
        final_fw=current['files']['firmware/main.c']['sha256']
        changed=final_fw!=e['input_hashes']['firmware/main.c']
        assert changed, 'OLD_DEVICE_ONLY_RESCORED'
        assert not final['unknown_or_missing_usage'] and final['reserved_unsettled_usd']==0, 'USAGE_UNRESOLVED'
        executions=load(trial/'executions.json')
        native=sum(len(x['metrics'].get('native_dispatches',[])) for x in executions)
        cache_keys={p.name for p in (trial/'cache-after').iterdir() if (p/'completed.json').is_file()}
        new=cache_keys-warm
        repeated=new&(earlier_new|historical_keys)
        assert not repeated, 'REPEATED_ALREADY_SUCCESSFUL_NATIVE_INPUT'
        earlier_new|=new
        # Administrative owner/project/policy identifiers do not alter task facts.
        core=re.sub(r'(?:PR|WP|SC|TD)-[0-9a-f]{64}', '<ADMIN-ID>', loaded['prompt'])
        core=re.sub(r'pi-chat-[0-9a-f]+','<OWNER-ID>',core)
        cores.append(digest(core));harnesses.append(loaded['harness_id'])
        start=dispatch['started_epoch']
        facts=[v for v in events if v.get('type')=='repository_tool_fact']
        qualification=final['qualification']
        received=qualification.get('gates',{}).get('receiver_service',{}).get('findings',{}).get('received_sequences')
        if stop:
            assert final.get('resource_censored') and final['stop_reason']==stop['reason'], 'STOP_RECORD_OMITTED'
            assert abs(final['decision_wall_s']-(stop['epoch']-start))<1e-6, 'STOP_TIME_MISMATCH'
        row={'attempt':e['key'],'owner':e['owner'],'arm':e['arm'],
            'fresh_context_messages':loaded['resume_message_count'],
            'actual_goal_consumed':True,'goal_sha256':e['goal_sha256'],
            'task_definition_id':e['task_definition_id'],'initial_inputs':e['input_hashes'],
            'final_firmware_sha256':final_fw,'firmware_changed':changed,
            'harness_id':loaded['harness_id'],'core_prompt_sha256':loaded['prompt_sha256'],
            'normalized_core_sha256':cores[-1],
            'requests':final['requests'],'tokens':final['tokens'],
            'cost_upper_bound_usd':final['settled_cost_upper_bound_usd'],
            'cache_aware_estimate_usd':final['cache_aware_estimate_usd'],
            'decision_wall_s':final['decision_wall_s'],
            'setup_wall_s':loaded['time']-start,
            'after_loaded_wall_s':final['decision_wall_s']-(loaded['time']-start),
            'candidate_evaluations':len(executions),'native_dispatches':native,
            'new_native_cache_keys':sorted(new),'repeated_successful_native_inputs':sorted(repeated),
            'tool_fact_calls':len(facts),
            'failed_tool_calls':sum(v.get('type')=='tool_execution_end' and bool(v.get('isError')) for v in events),
            'delivered':final['delivered'],'task_passed':qualification['task_passed'],
            'qualification_status':qualification['status'],
            'resource_censored':bool(stop),'stop_reason':stop['reason'] if stop else None,
            'received_frames':len(received) if received is not None else None,
            'physical':qualification['physical'],
            'result_sha256':sha(trial/'final.json'),'ledger_sha256':sha(trial/'ledger.json'),
            'view_sha256':sha(trial/'view.json'),'executions_sha256':sha(trial/'executions.json'),
            'first_request_id':first['id'],
            'stop_receipt_sha256':sha(trial/'stop.json') if stop else None}
        assert row['requests']<=80 and len(executions)<=4 and row['decision_wall_s']<=1200, 'FINITE_CAP_EXCEEDED'
        rows.append(row)
    assert len(set(harnesses))==1, 'HARNESS_DRIFT'
    assert len({r['task_definition_id'] for r in rows})==1, 'TASK_DRIFT'
    assert len({canonical(r['initial_inputs']) for r in rows})==1, 'STARTING_DEVICE_DRIFT'
    # Compare actual normalized prompts explicitly; never hide extra differences.
    normalized_core_match=len(set(cores))==1
    arms={}
    for arm in ('H0','H1'):
        rs=[r for r in rows if r['arm']==arm]
        arms[arm]={'attempts':len(rs),'delivered':sum(r['delivered'] and r['task_passed'] for r in rs),
                   'completed_without_resource_stop':sum(not r['resource_censored'] for r in rs),
                   'resource_censored':sum(r['resource_censored'] for r in rs),
                   'requests':sum(r['requests'] for r in rs),
                   'cost_upper_bound_usd':sum(r['cost_upper_bound_usd'] for r in rs),
                   'cache_aware_estimate_usd':sum(r['cache_aware_estimate_usd'] for r in rs)
                      if all(r['cache_aware_estimate_usd'] is not None for r in rs) else None,
                   'candidate_evaluations':sum(r['candidate_evaluations'] for r in rs),
                   'native_dispatches':sum(r['native_dispatches'] for r in rs)}
    censored=any(r['resource_censored'] for r in rows)
    eligible=not censored and normalized_core_match and arms['H1']['delivered']==2 and arms['H1']['delivered']>=arms['H0']['delivered']
    result={'schema_version':'campaign-method-confirmation-audit-v1','status':'PASS',
            'protocol_sha256':registry['protocol_sha256'],'rows':rows,'arms':arms,
            'same_harness':True,'normalized_core_match':normalized_core_match,
            'retention':('NO_PROMOTION_RESOURCE_CENSORED' if censored else
                         'RETAIN_DEVELOPMENT_CANDIDATE_ONLY' if eligible else 'REJECT_DEVELOPMENT_UPDATE'),
            'resource_censored_attempts':[r['attempt'] for r in rows if r['resource_censored']],
            'default_method_changed':False,'autonomous_G':'NOT_RUN','transfer':'NOT_TESTED',
            'interpretation':'A true operator-proposed H change was consumed in four fresh design attempts. '
                             'Three delivered; H0-r2 hit the frozen disk gate after execution and before validation. '
                             'It was not resampled. Resource censoring prevents a completed arm comparison; '
                             'no method advantage, promotion, or recursive improvement is established.',
            'cache_boundary':'Identical physical cache start; provider and OS caches uncontrolled. '
                             'No native cache key newly solved here duplicates an earlier successful input.',
            'billing_boundary':'Charge is a conservative upper bound; cache-aware estimate is not an invoice.'}
    result['cost_scope']={
        'included':'All parent requests, including the stopped attempt, within these four BF owners; no children.',
        'historical_cache_construction_bill':'UNKNOWN; 16 pre-existing entries reused, not assigned zero cost.',
        'operator_proposal_cost':'UNPRICED; H1 was operator-authored, not autonomous G.',
        'codex_supervision_executor_and_writing_cost':'NOT_AVAILABLE_IN_BF_LEDGER',
        'efficiency_claim':'NOT_SUPPORTED by attempt charges alone.'}
    (HERE/'paid-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    fields=['attempt','requests','cost_upper_bound_usd','cache_aware_estimate_usd','candidate_evaluations',
            'native_dispatches','setup_wall_s','after_loaded_wall_s','received_frames','delivered','task_passed',
            'qualification_status','resource_censored','stop_reason']
    with (HERE/'paid-results.csv').open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
        for row in rows:w.writerow({k:row[k] for k in fields})
    print(json.dumps({'status':result['status'],'arms':arms,'normalized_core_match':normalized_core_match,
                      'retention':result['retention']}))
    return result


if __name__=='__main__':audit()
