"""Host-only source-bound group aggregation; no new model or physical run."""
from pathlib import Path
import copy
import json
import sys

ROOT=Path(__file__).resolve().parents[4]
APP=ROOT/'workbench/bf-campaign-s0-20261019/battery-world'
PLAN=Path(__file__).parent
OUT=Path.home()/'.local/share/bf-phase3-20261020'
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.campaign20261019.common import digest,file_hash,seal


def read(p): return json.loads(Path(p).read_text())


def groups(stage=None):
    protocol=read(PLAN/'protocol.json');records={}
    for spec in protocol['episodes']:
        if stage and spec['stage']!=stage:continue
        path=OUT/'episodes'/spec['id']/'episode-result.json'
        if not path.exists():continue
        record=read(path);key=spec['group']
        group=records.setdefault(key,{'id':key,'stage':spec['stage'],'world':spec['world'],
            'condition':spec['condition'],'replicate':spec['replicate'],'episodes':[],
            'requests':0,'settled_upper_usd':0,'cache_aware_estimate_usd':0,'wall_s':0,
            'unknown_usage':[],'complete_service':'INCOMPLETE','status':'INCOMPLETE'})
        group['episodes'].append({'id':spec['id'],'kind':spec['kind'],'status':record['status'],
                                  'result_path':str(path),'result_sha256':file_hash(path)})
        cost=record['accounting'];group['requests']+=cost['requests']
        group['settled_upper_usd']+=cost['settled_charge_upper_bound_usd']
        group['cache_aware_estimate_usd']+=cost['cache_aware_rate_estimate_usd']
        group['wall_s']+=record['wall_seconds_total'];group['unknown_usage']+=cost['unknown_or_missing_usage']
        if spec['kind']=='H':
            group['H_proposal_status']=record['status']
            group['H_proposal']=record.get('external_result',{}).get('method')
            continue
        group['status']=record['status'];group['final_episode']=spec['id']
        group['initial_cache_sha256']=record['initial_cache_sha256']
        group['fresh_task_entry']=record.get('fresh_task_entry',False)
        group['reported_models']=record.get('reported_models',[])
        ep_protocol=read(path.parent/'protocol.json');group['tool_sha256']=ep_protocol['tool']['sha256']
        packet=path.parent/'scientific/information-packet.json'
        if packet.exists():group['information_sha256']=read(packet)['decoded_packet_sha256']
        execution=record.get('external_result',{}).get('execution')
        if execution:
            group.update(complete_service=execution['complete_service'],design=execution['design'],
                         first_receive_s=execution['reference']['first_receive_s'],
                         ordered_event_state=execution['ordered_event_state'],execution=execution,
                         prospective_E5=record['external_result'].get('prospective_E5_consumer',False))
    return records


def matched_methods(records):
    paired=[]
    for row in records.values():
        if row['condition'] not in ('ordinary_reflection','proposed_method') or 'final_episode' not in row:continue
        fixed=next((x for x in records.values() if (x['stage'],x['world'],x['replicate'],x['condition'])==
                    (row['stage'],row['world'],row['replicate'],'complete-raw')),None)
        if not fixed or 'final_episode' not in fixed:continue
        parity={k:row.get(k)==fixed.get(k) and row.get(k) is not None for k in
                ('initial_cache_sha256','information_sha256','tool_sha256','reported_models')}
        parity['fresh_task_entries']=row['fresh_task_entry'] and fixed['fresh_task_entry']
        parity['same_registered_total_budget']=row['requests']<=24 and fixed['requests']<=24 and row['wall_s']<=1200 and fixed['wall_s']<=1200
        proposed=(row.get('H_proposal') or {}).get('decision')=='propose'
        ready=all(parity.values()) and not row['unknown_usage'] and not fixed['unknown_usage']
        better=row['complete_service']=='PASS' and fixed['complete_service']!='PASS'
        decision=('RETAIN_AS_FINITE_EXPERIMENTAL_CANDIDATE' if proposed and ready and better else 'REJECT_PROMOTION')
        paired.append({'world':row['world'],'stage':row['stage'],'replicate':row['replicate'],
            'condition':row['condition'],'fixed_group':fixed['id'],'method_group':row['id'],'parity':parity,
            'fixed_service':fixed['complete_service'],'method_service':row['complete_service'],
            'fixed_requests':fixed['requests'],'method_total_requests':row['requests'],
            'H_reexecution_controls':{'frozen_old_decisions':('INELIGIBLE_AFTER_TASK_LOCAL_H_CHANGE' if proposed else 'UNCHANGED_H_CONTROL_WITH_REGISTERED_FRESH_D'),
                'dependency_recompute':'TASK_ENTRY','scope_recompute':'TASK_ENTRY','full':'TASK_ENTRY',
                'actual_fresh_context_receipt':str(OUT/'episodes'/row['final_episode']/'episode-result.json'),
                'physical_exact_input_reuse':'Allowed independently of the mandatory fresh Agent decisions'},
            'decision':decision,'reason':('New complete-service success under matched cap; still no statistical/general claim' if decision.startswith('RETAIN') else
                'No new complete-service success, no valid H, or a parity/usage gate failed. Costs of all proposal stages retained.'),
            'default_H_changed':False})
    return paired


def deterministic_controls(records):
    registry=read(APP/'configs/studies/phase3-20261020/shared/tasks.json');rows=[]
    hist=Path.home()/'.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001'
    for group in records.values():
        execution=group.get('execution')
        if not execution:continue
        world=group['world'];entry=registry['tasks'][world]
        if 'derived_assets' in entry:
            original=Path(entry['derived_assets']['input.json']['path']);baseline=Path(entry['derived_assets']['result.json']['path'])
        else:original=hist/'cases'/world/'input.json';baseline=original.parent/'result.json'
        task=read(original);changed=copy.deepcopy(task);changed['device'].update(group['design'])
        correct=digest(changed)==execution['input_sha256']
        if not correct:raise ValueError('ACTUAL_CONSUMED_INPUT_HASH_MISMATCH:'+group['id'])
        differs=task!=changed
        old_result=read(baseline)
        old_service=old_result.get('complete_service')
        if old_service is None:
            old_service='PASS' if all(old_result['reference']['verdicts'][k]=='PASS' for k in
                ('independent_energy','independent_receiver','event_receive','deduplication','transient_voltage')) else 'FAIL'
        strategies=[{'strategy':'frozen-trajectory','eligible':not differs,
                     'disposition':'INVALID_FOR_CHANGED_INPUT' if differs else 'EXACT_UNCHANGED_INPUT_CONTROL',
                     'retained_baseline_path':str(baseline),'baseline_sha256':file_hash(baseline),
                     'historical_service_label':old_service,
                     'stale_label_disagrees_with_actual_full_feedback':old_service!=execution['complete_service']}]
        for strategy in ('dependency-recompute','scope-recompute','full-feedback'):
            strategies.append({'strategy':strategy,'eligible':True,'scope':'full-feedback-response',
                'actual_execution_key':execution['execution_key'],'consumed_input_sha256':execution['input_sha256'],
                'service':execution['complete_service'],'exact_response_reused':execution['reused'],
                'scope_policy':'Coupled input conservatively expands to full response; no claimed speedup'})
        rows.append({'group':group['id'],'changed_D':differs,'strategies':strategies,
                     'new_scientific_executions_for_comparison':0,'source_bound_identity':'PASS'})
    return rows


def snapshot(name,stage=None):
    records=groups(stage)
    value={'schema_version':'bf-phase3-actual-comparison-v1','groups':records,
           'matched_methods':matched_methods(records),'deterministic_controls':deterministic_controls(records),
           'accounting':{'requests':sum(x['requests'] for x in records.values()),
                        'settled_upper_usd':sum(x['settled_upper_usd'] for x in records.values()),
                        'wall_s':sum(x['wall_s'] for x in records.values()),
                        'unknown_usage':[y for x in records.values() for y in x['unknown_usage']]},
           'claim_boundary':'Public development digital trials; task and run counts separate. No invoice, hardware, transfer, RSI or significance claim.'}
    seal(PLAN/name,value);return value


def freeze_formal():
    records=groups('pilot');plan=read(PLAN/'protocol.json')
    expected={x['id'] for x in plan['episodes'] if x['stage']=='pilot'}
    observed={y['id'] for x in records.values() for y in x['episodes']}
    if expected!=observed:raise ValueError('TWO_COMPLETE_FINITE_PILOT_REPLICATES_REQUIRED')
    signatures={}
    for x in records.values():
        signatures.setdefault(x['condition'],[]).append(digest({'status':x['status'],'service':x['complete_service'],'design':x.get('design')}))
    stable=all(len(v)==2 and len(set(v))==1 for v in signatures.values())
    value={'schema_version':'bf-phase3-formal-repeat-freeze-v1','formal_repetitions':2 if stable else 3,
           'stable_across_two_pilots':stable,'pilot_signatures':signatures,
           'rule_sha256':digest(plan['formal_repetitions_rule']),'repeat_selection_events':1,
           'adapt_after_this_freeze':False,'no_original_failure_replaced':True}
    seal(PLAN/'formal-repeat-freeze.json',value);return value


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='freeze':print(json.dumps(freeze_formal()))
    else:print(json.dumps(snapshot(sys.argv[1] if len(sys.argv)>1 else 'actual-comparison.json')['accounting']))
