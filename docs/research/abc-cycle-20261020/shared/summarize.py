#!/usr/bin/env python3
"""Read only canonical ABC results and settled receipts; rewrite one derived index."""
import hashlib
import json
from pathlib import Path

SHARED = Path(__file__).resolve().parent
OUT = Path.home()/'.local/share/bf-abc-20261020'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize():
    registrations = {}
    for filename in ('protocol-entry-fix-v1.1.json','protocol-B-v1.json','protocol-A-v1.json'):
        plan = read(SHARED/filename)
        for ident, registration in plan['episodes'].items():
            if ident in registrations: raise ValueError('DUPLICATE_EPISODE_ID')
            registrations[ident] = {**registration,'protocol':str(SHARED/filename)}
    rows, request_ids = [], set()
    for ident, registration in sorted(registrations.items()):
        spec = read(registration['template'])
        path = OUT/'episodes'/ident/'episode-result.json'
        row = {'episode_id':ident,'package':registration['package'],'stage':spec.get('stage'),
            'arm':spec.get('arm',spec.get('condition')),'task_id':spec.get('task_id',spec.get('case')),
            'status':'RUNNING' if (path.parent/'attempt.json').exists() else 'NOT_RUN'}
        if path.exists():
            value = read(path)
            result = value.get('independent_result') or {}
            row.update(result_path=str(path),result_sha256=sha(path),status=value['status'],
                independent_status=result.get('status','NOT_EVALUATED'),wall_s=value['wall_seconds_total'],
                requests=value['accounting']['requests'],charge_upper_usd=value['accounting']['settled_charge_upper_bound_usd'],
                unknown_usage=value['accounting']['unknown_or_missing_usage'],
                tool_calls=value.get('trace_audit',{}).get('model_tool_calls'),
                error=value.get('error'),audit_or_check_error=value.get('audit_or_check_error'))
            account = read(path.parent/'provider-costs.json')
            tokens = {'input':0,'output':0,'reasoning':0,'cached_input':0}
            for request in account['rows']:
                if request['id'] in request_ids: raise ValueError('DOUBLE_COUNTED_PROVIDER_REQUEST')
                request_ids.add(request['id'])
                if request['status'] != 'SETTLED': raise ValueError('UNSETTLED_FINAL_RECEIPT')
                usage = request['usage']
                if isinstance(usage,str): usage=json.loads(usage)
                tokens['input'] += usage['prompt_tokens']
                tokens['output'] += usage['completion_tokens']
                tokens['reasoning'] += (usage.get('completion_tokens_details') or {}).get('reasoning_tokens',0)
                tokens['cached_input'] += usage.get('prompt_cache_hit_tokens',(usage.get('prompt_tokens_details') or {}).get('cached_tokens',0))
            row['tokens'] = tokens
            artifact = (path.parent/'host/submission.json' if registration['package']=='interfaces' else
                path.parent/'product/submission.json' if registration['package']=='product' else
                path.parent/'methods'/('method-submission.json' if spec.get('stage')=='formation' else 'submission.json'))
            row['actual_artifact_submitted']=artifact.exists()
            row['artifact_sha256']=sha(artifact) if artifact.exists() else None
            row['gateway_stopped']=value.get('gateway_stopped')
            row['sdk_exit_code']=value.get('exit_code')
            row['context_payload_bytes']=(path.parent/'participant-payload.json').stat().st_size
            events=[json.loads(s) for s in (path.parent/'gateway/gateway-events.jsonl').read_text().splitlines()]
            row['gateway_tool_failures']=sum(v['kind']=='tool_failed' for v in events)
            row['gateway_tool_wall_s']=sum(v['data'].get('wall_seconds',0) for v in events if v['kind'] in ('tool_completed','tool_failed'))
            if registration['package']=='methods':
                row.update({k:result.get(k) for k in ('event_matching','timely_receive','timestamp_accuracy','wrong_service_judgment','consumed_method_sha256','submitted_candidate')})
                row['scientific_executions']=len(list(path.parent.glob('methods/executions/*/response.json')))
                row['executed_samples']=sum(read(p)['sample_count'] for p in path.parent.glob('methods/executions/*/response.json'))
                row['method_checks_semantic_proof']=False
                submitted=[v['data']['output'].get('relations') for v in events if v['kind']=='tool_completed' and v['data'].get('output',{}).get('recorded')=='submit']
                if submitted and submitted[-1] is not None:
                    relations=submitted[-1]
                    if relations['method_sha256']!=result['consumed_method_sha256']:raise ValueError('FROZEN_RELATION_BINDING')
                    row['frozen_method_relations']=relations['rows']
                    row['failed_frozen_relation_on_passed_design']=result['status']=='PASS' and any(v['result'] is False for v in relations['rows'])
            elif registration['package']=='interfaces':
                row.update({k:result.get(k) for k in ('truth','coverage','prediction_correct','decision_correct','selected_service','wrong_adoption','wrong_rejection','real_typed_consumer','interface_decision_success','execution_keys','costs')})
                executions=[read(p) for p in path.parent.glob('host/executions/*.json')]
                for execution in executions:
                    if sha(execution['raw_path']) != execution['raw_sha256']:
                        raise ValueError('B_CANONICAL_RAW_HASH_CHANGED')
                row['scientific_executions']=sum(not v['reused'] for v in executions)
                row['exact_input_cache_reuses']=sum(v['reused'] for v in executions)
                row['evaluated_input_count']=len(executions)
                row['host_evaluation_timing']='Included in total episode wall time; no separately recorded host-only duration.'
            else:
                row.update(execution_integrity=result.get('execution_integrity'),engineering_acceptance=result.get('engineering_acceptance'))
        rows.append(row)
    def arm_table(package):
        formal=[r for r in rows if r['package']==package and r['stage']=='formal']
        arms={}
        for row in formal:
            arm=arms.setdefault(row['arm'],{'planned':0,'finished':0,'submitted':0,'service_pass':0,'judgment_errors':0,'requests':0,'charge_upper_usd':0.,'input_tokens':0,'output_tokens':0,'reasoning_tokens':0,'tools':0,'scientific_executions':0,'exact_input_cache_reuses':0,'executed_samples':0,'failed_frozen_relation_on_passed_design':0})
            arm['planned']+=1
            if 'result_path' not in row:continue
            arm['finished']+=1
            arm['submitted']+=row['status']=='ACTUAL_SUBMITTED'
            service_pass=(row.get('independent_status')=='PASS' if package=='methods' else row.get('selected_service')=='PASS')
            arm['service_pass']+=service_pass
            arm['actual_artifact_submissions']=arm.get('actual_artifact_submissions',0)+row['actual_artifact_submitted']
            arm['within_budget_service_pass']=arm.get('within_budget_service_pass',0)+(service_pass and row['status']=='ACTUAL_SUBMITTED')
            arm['stopped_or_incomplete']=arm.get('stopped_or_incomplete',0)+(row['status']!='ACTUAL_SUBMITTED')
            arm['judgment_errors']+=(row.get('wrong_service_judgment') is True if package=='methods' else row.get('prediction_correct') is False)
            arm['requests']+=row['requests'];arm['charge_upper_usd']+=row['charge_upper_usd'];arm['tools']+=row.get('tool_calls') or 0
            for key in ('scientific_executions','exact_input_cache_reuses','executed_samples','failed_frozen_relation_on_passed_design'):arm[key]+=row.get(key) or 0
            for name in ('input','output','reasoning'):arm[name+'_tokens']+=row['tokens'][name]
            if package=='interfaces':
                for key in ('coverage','prediction_correct','decision_correct','wrong_adoption','wrong_rejection','real_typed_consumer','interface_decision_success'):
                    arm[key]=arm.get(key,0)+(row.get(key) is True)
                for key in ('acquisition_read_bytes','preflight_calls','rejected_actions','tool_wall_s'):
                    arm[key]=arm.get(key,0)+(row.get('costs',{}).get(key) or 0)
                arm['evaluated_input_count']=arm.get('evaluated_input_count',0)+row.get('evaluated_input_count',0)
            else:
                for key in ('event_matching','timely_receive','timestamp_accuracy'):
                    arm[key+'_pass']=arm.get(key+'_pass',0)+(row.get(key)=='PASS')
        return arms
    completed=[r for r in rows if 'result_path' in r]
    value={'schema_version':'bf-abc-canonical-result-index-v1','rows':rows,'formal_methods':arm_table('methods'),
        'formal_interfaces':arm_table('interfaces'),'planned_model_episodes':len(rows),'finished_model_episodes':len(completed),
        'running':[r['episode_id'] for r in rows if r['status']=='RUNNING'],
        'completed_accounting_only':{'requests':sum(r['requests'] for r in completed),'charge_upper_usd':sum(r['charge_upper_usd'] for r in completed),
            'unknown_usage':[x for r in completed for x in r['unknown_usage']]},
        'scope':'Partial while episodes remain; usage from sealed completed receipts only. Fixed-rate estimates are not invoices; Codex preparation cost UNKNOWN. Format, scientific judgment, service, acquisition/execution and hardware claims stay separate.',
        'boundaries':['Physical NOT_CALIBRATED; original failures and billing retained.','C is an ideal continuously powered time-semantics component, no energy/RF/keepalive acceptance.','H structural admission is not semantic proof; both raw methods carried unchanged.','A is a finite nominal component projection, original service FAIL; not global A/R impossibility.','B development legal consumption is researcher-specified, excluded from18 formal attempts.','No RSI, G expansion or new publication claim.']}
    target=SHARED.parent/'RESULT-INDEX.json'
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:value[k] for k in ('finished_model_episodes','planned_model_episodes','running','formal_methods','formal_interfaces','completed_accounting_only')},ensure_ascii=False))
    return value


if __name__=='__main__':summarize()
