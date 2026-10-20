"""Read sealed episodes into task/run tables; never alter an episode verdict."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import statistics
import sys

PLAN=Path(__file__).parent
spec=importlib.util.spec_from_file_location('phase3_sealed_comparison',PLAN/'compare.py')
comparison=importlib.util.module_from_spec(spec);spec.loader.exec_module(comparison)
ROOT,APP,OUT=comparison.ROOT,comparison.APP,comparison.OUT
read,seal,digest,file_hash=comparison.read,comparison.seal,comparison.digest,comparison.file_hash


def tables(records,stage):
    chosen=[x for x in records.values() if x['stage']==stage]
    rows=[]
    for condition in read(PLAN/'protocol.json')['conditions']:
        subset=[x for x in chosen if x['condition']==condition]
        by_task={task:dict(Counter(x['complete_service'] for x in subset if x['world']==task))
                 for task in read(PLAN/'protocol.json')['tasks'] if any(x['world']==task for x in subset)}
        rows.append({'condition':condition,'task_count':len(by_task),'run_count':len(subset),
            'service_counts':dict(Counter(x['complete_service'] for x in subset)),
            'ordered_event_counts':dict(Counter(x.get('ordered_event_state',{}).get('classification','NO_ADMITTED_EXECUTION') for x in subset)),
            'per_task_counts':by_task,'requests':sum(x['requests'] for x in subset),
            'mean_group_requests':statistics.mean(x['requests'] for x in subset) if subset else None,
            'wall_s':sum(x['wall_s'] for x in subset),
            'settled_upper_usd':sum(x['settled_upper_usd'] for x in subset),
            'H_proposal_counts':dict(Counter((x.get('H_proposal') or {}).get('decision','incomplete')
                for x in subset if condition in ('proposed_method','ordinary_reflection')))})
    return rows


def e5_audit(records):
    rows=[]
    for group in records.values():
        if group['condition']!='live-e5':continue
        root=OUT/'episodes'/group['final_episode'];submit=root/'scientific/submission.json'
        failed=[]
        for line in (root/'gateway/gateway-events.jsonl').read_text().splitlines():
            event=json.loads(line)
            if event['kind']=='tool_failed':failed.append(event['data']['error'])
        value={'group':group['id'],'stage':group['stage'],'world':group['world'],
               'operational_status':group['status'],'complete_service':group['complete_service'],
               'failed_actions':failed,'new_physical_measurement':False}
        if submit.exists():
            submission=read(submit)
            entry=read(APP/'configs/studies/phase3-20261020/shared/tasks.json')['tasks'][group['world']]
            parent=(Path(entry['derived_assets']['input.json']['path']) if 'derived_assets' in entry else
                    Path.home()/'.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001/cases'/group['world']/'input.json')
            current={k:read(parent)['device'][k] for k in ('capacitance_f','tx_not_before_s')}
            value.update(mode=submission['spec']['mode'],source_id=submission['spec']['source_id'],
                         qualification=submission['qualification'],units=submission['observation']['units'],
                         typed_observation_consumed=submission['consumer']['used_observation'],
                         design_changed=submission['execution']['design']!=current,
                         spec_sha256=digest(submission['spec']))
        rows.append(value)
    return rows


def final():
    protocol=read(PLAN/'protocol.json');n=read(PLAN/'formal-repeat-freeze.json')['formal_repetitions']
    expected={x['id'] for x in protocol['episodes'] if x['stage']=='pilot' or x['replicate']<=n}
    actual={p.parent.name for p in (OUT/'episodes').glob('*/episode-result.json')}
    if actual!=expected:raise ValueError('FINITE_MATRIX_NOT_COMPLETE:'+str(len(actual))+'/'+str(len(expected)))
    snapshot=comparison.snapshot('actual-comparison.json');records=snapshot['groups']
    if snapshot['accounting']['unknown_usage']:raise ValueError('UNKNOWN_PROVIDER_USAGE')
    formal=tables(records,'formal');pilot=tables(records,'pilot');index={x['condition']:x for x in formal}
    e4=[]
    for left in records.values():
        if left['condition']!='rich-static':continue
        right=next(x for x in records.values() if (x['stage'],x['world'],x['replicate'],x['condition'])==
                   (left['stage'],left['world'],left['replicate'],'e4-rich-static-table'))
        e4.append({'stage':left['stage'],'world':left['world'],'replicate':left['replicate'],
                   'identical_decoded_initial_packet':left.get('information_sha256')==right.get('information_sha256') and bool(left.get('information_sha256')),
                   'identical_tool':left['tool_sha256']==right['tool_sha256'],
                   'json_service':left['complete_service'],'table_service':right['complete_service'],
                   'json_requests':left['requests'],'table_requests':right['requests']})
    proposal=index['proposed_method'];controls=[index['complete-raw'],index['ordinary_reflection']]
    task_ids=protocol['tasks']
    vector=lambda row:[row['per_task_counts'][t].get('PASS',0) for t in task_ids]
    p=vector(proposal)
    dominates=all(all(a>=b for a,b in zip(p,vector(c))) and any(a>b for a,b in zip(p,vector(c))) for c in controls)
    cost_ok=all(proposal['mean_group_requests']<=c['mean_group_requests'] for c in controls)
    # Counts within each task stay a vector; 12 repeats are never 12 new tasks.
    selection={'registered_rule':protocol['stage4_selection_rule'],'task_order':task_ids,
        'task_success_vectors':{x['condition']:vector(x) for x in [proposal,*controls]},
        'strict_task_vector_dominance_without_a_lost_task':dominates,'mean_group_requests_not_higher':cost_ok,
        'condition_decision':'ELIGIBLE_FOR_SEPARATE_HELDOUT_ADMISSION' if dominates and cost_ok else 'KEEP_UNCHANGED_BASE_H',
        'default_H_changed':False,'global_transferable_H_proven':False,
        'scope':'Phase3 H instantiations are task-local. This selection cannot establish a globally transferred H or a recursively improved G.'}
    data={'schema_version':'bf-phase3-main-tables-v1','formal':formal,'pilot':pilot,
          'e4_pairs':e4,'e5_audit':e5_audit(records),'selection':selection,
          'accounting':snapshot['accounting'],'group_count':len(records),'actual_episode_count':len(actual),
          'formal_task_count':len(task_ids),'formal_repetitions_per_task':n,
          'all_formal_groups_expected':len(task_ids)*n*len(protocol['conditions']),
          'data_dictionary':{'task_count':'Distinct fixed task IDs; not repetitions or method-proposal owners',
             'run_count':'One fixed task/condition/replicate group, including all H-parent costs where present',
             'INCOMPLETE':'No admitted final execution; retained in the denominator, never replaced',
             'E4':'Only initial complete packet serialization differs; later source acquisition responses are common JSON',
             'rich-static_and_complete-raw':'Both contain every supplied record and the full model definition; raw physical traces remain host-side for audit',
             'executable-response':'Candidate-specific public energy ledger, activity and packets; full coupled raw trace retained host-side',
             'cost':'Provider-reported settled conservative estimate; no invoice audit. Codex assistance/full end-to-end cost UNKNOWN',
             'science':'Fixed ideal digital B apparatus and a synthetic DC single-query derivative; hardware and RF qualification UNKNOWN'},
          'source_bindings':{'protocol':file_hash(PLAN/'protocol.json'),'comparison':file_hash(PLAN/'actual-comparison.json'),
                             'comparison_code':file_hash(PLAN/'compare.py'),
                             'analysis_code':file_hash(Path(__file__))}}
    seal(PLAN/'main-tables.json',data)
    print(json.dumps({'formal_groups':data['all_formal_groups_expected'],'episodes':len(actual),'selection':selection['condition_decision'],'requests':snapshot['accounting']['requests']}))
    return data


if __name__=='__main__':final()
