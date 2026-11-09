"""Two remaining direct software checks. No science/provider dispatch."""
from bisect import bisect_right
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from common import *
from public_bridge import project, PRIVATE_FIELDS
from run import B, tasks, factory
import provider


def no_private(value):
    if isinstance(value,dict):return not (set(value)&PRIVATE_FIELDS) and all(no_private(v) for v in value.values())
    return not isinstance(value,list) or all(no_private(v) for v in value)


def initial(family,paths):
    rows=[]
    for t,path in zip(family,paths):
        row=load(path);row['condition_id']=t['condition_id'];rows.append(project(row))
    return dict(design=family[0]['initial_design'],results=rows)


def public_v2():
    old=OUT/'a/runs/01-M0-parent-capture-recover/result/public-result.json'
    original=ref(old);public=load(old);view=project(public)
    activity=public['facts']['activity'];reset_times=sorted(e['time_s'] for e in activity if e.get('action')=='brownout')
    receives=[e for e in view['relationship_graph']['events'] if e['stage']=='recv']
    assert receives and all(e['observed_mcu_resets']==bisect_right(reset_times,e['time_s']) for e in receives)
    assert no_private(view) and ref(old)==original
    # Entire nested copy is scrubbed; input bytes and raw dictionaries remain unchanged.
    contaminated=deepcopy(public);contaminated['facts']['nested']=[{'observer_epoch':999}]
    assert no_private(project(contaminated)) and contaminated['facts']['nested'][0]['observer_epoch']==999
    # Same live holder capture across a MCU reset is a replay, never a conflict.
    fixture=dict(task_id='SOFTWARE_ONLY',design=public['design'],facts=dict(receiver_records=[],activity=[
        dict(action='holding_capture_commit',time_s=0,record=dict(token=1,direction=1)),
        dict(action='holding_read_commit',time_s=1,record=dict(token=1,direction=1,assigned_seq=1)),
        dict(action='capture',time_s=1,direction=1,source='paid_holder_read'),
        dict(action='save_commit',time_s=1,record=dict(seq=1,direction=1)),
        dict(action='brownout',time_s=2),
        dict(action='holding_read_commit',time_s=3,record=dict(token=1,direction=1,assigned_seq=1)),
        dict(action='capture',time_s=3,direction=1,source='paid_holder_read'),
        dict(action='save_commit',time_s=3,record=dict(seq=1,direction=1))]))
    replay=project(fixture)
    assert not any(x['stage']=='identity' and x['holds'] is False for x in replay['relationship_view']['relations'])
    return dict(status='PASS',old_canonical=original,receive_reset_counts=[x['observed_mcu_resets'] for x in receives],
        full_shared_object_private_key_scan='PASS',same_holder_replay_negative_control='PASS',original_bytes_unchanged=True)


def common_chain():
    families=tasks();family=families['known-local']
    paths=[BASE/f'codebt-idea/s0/science/{i:02d}-initial-{t["condition_id"]}/result/public-result.json.gz' for i,t in enumerate(family,1)]
    shared=initial(family,paths);f=factory(family)
    summary=B.summarize(shared,f.initial_design,[t['condition_id'] for t in family],f)
    assert summary['complete_valid'] and summary['relationships'] and B.targets(summary)
    pools=[f.generate(f.initial_design,seed=seed,round_index=0,relationships=summary['relationships']) for seed in SEEDS]
    assert all(0<x['raw_proposals']<=32 for x in pools)
    assert len({digest(x['generation_records']) for x in pools})==3
    scope=dict(conditions=[t['condition_id'] for t in family],family_id=family[0]['family_id'])
    g=B.FreeJointInterface(f,shared,scope=scope,seed=SEEDS[0])
    joint={**f.initial_design,'capacitance_f':.00043,'esr_ohm':1.234,'persistent_queue':True}
    action=g.submit(joint)
    assert action['status']=='ACTION' and action['design']==f.normalize(joint)['design']
    # Exercise the real frozen A parent gate on actual saved model-valid partial results.
    new=families['mechanism'];manifest=load(OUT/'a/M2r/public-tasks-and-common-parent.json')['rows']
    new_initial=initial(new,[ROOT/x['canonical_public_result_ref'] for x in manifest])
    partial=[]
    for row in load(OUT/'a/M2r/mechanism-qualification.json')['rows']:
        if row['design_name']=='identity-only':
            val=load(OUT/'a/M2r'/row['folder']/'result/public-result.json');val['condition_id']=row['condition_id'];partial.append(project(val))
    assert len(partial)==3
    nf=factory(new);nscope=dict(conditions=[t['condition_id'] for t in new],family_id=new[0]['family_id'])
    consumed=[]
    for cond in ['R','A']:
        ctrl=B.DeterministicController(cond,nf,new_initial,scope=nscope,seed=SEEDS[0])
        act=ctrl._submit(partial[0]['design'],ctrl.nodes[ctrl.root_id],{'kind':'SOFTWARE_SAVED_PARTIAL_CHECK'})
        reply=ctrl.update(dict(request_id=act['request_id'],design=partial[0]['design'],results=partial))
        node=ctrl.nodes[reply['node_id']]
        assert node.low_score and ctrl._eligible(node)==(cond=='R')
        ctrl.step()
        eligibility=[e for e in ctrl.events if e['event']=='PARENT_ELIGIBILITY'][-1]
        assert (node.id in eligibility['forbidden'])==(cond=='A')
        consumed.append(dict(condition=cond,low_score=node.low_score,eligible=ctrl._eligible(node),
            relationships=len(node.summary['relationships']),selected_parent=ctrl.pending and ctrl.pending['parent_id']))
    # Run the actual new callback normalization method with the original saved DSML response.
    saved=BASE/'codebt-idea/s0/episodes/generic_agent/callbacks/03/pi-public.jsonl'
    with tempfile.TemporaryDirectory(prefix='.compat-',dir=HERE) as tmp:
        temp=Path(tmp);folder=temp/'callbacks/01';folder.mkdir(parents=True)
        (folder/'pi-public.jsonl').symlink_to(saved)
        stub=provider.Episode.__new__(provider.Episode);stub.root=temp;stub.callback_index=1
        with patch.object(provider.transport.LCEpisode,'paid_callback',return_value=dict(provider_status='COMPLETE',usage=dict(status='KNOWN'),payload=dict(status='JSON_SYNTAX_ERROR'))):
            reply=provider.Episode.paid_callback(stub,{})
        assert reply['normalization']['status']=='OK' and reply['payload']['tool_calls']
        objects=provider.PublicObjects(temp/'public')
        obj=objects.register(Episode_public(shared));page=objects.read(dict(object_id=obj,section='',offset=0))
        assert no_private(page)
        stub.owner=next(iter(load(OUT/'shared/provider-binding.json')['owners'].values()))
        stub.tools=stub.numerical=0;stub.candidates=set();stub.started=time.monotonic()
        budget=provider.p.Episode.budget(stub)
        assert budget['model_requests']==0 and budget['spent_usd']==0
        allowance=provider.p.output_allowance(budget['output_tokens'],provider.LIMITS)
        wire=provider.p.validate_wire(dict(model='deepseek-flash',stream=True,max_tokens=allowance,
            messages=[dict(role='user',content='SOFTWARE_ONLY_NO_DISPATCH')]),allowance)
        assert wire['max_tokens']==32768
        payload=provider.p.callback_payload(objects.project(dict(site='strong_generic_joint_design',initial_results=Episode_public(shared))),allowance)
        assert no_private(payload)
        normalization=reply['normalization']
    accounting_gate()
    return dict(status='PASS',actual_public_summary=dict(statuses=summary['statuses'],relations=len(summary['relationships']),targets=len(B.targets(summary))),
        public_payload_private_key_scan='PASS',pool_counts=[x['raw_proposals'] for x in pools],seeded_generation_distinct=True,
        G_arbitrary_joint_submission='PASS',actual_partial_parent_gates=consumed,
        saved_DSML_actual_callback_normalization=normalization,saved_DSML_source=ref(saved),
        actual_public_object_paging='PASS',actual_prepared_owner_budget=budget,actual_wire_cap=wire['max_tokens'],
        qualification_used_only_for_software_check_not_method_or_model_history=True,
        provider_requests=0,full_inputs=0,cheap_numeric=0)


def Episode_public(value):return provider.Episode.public_result(value)


def main():
    counter=load(HERE/'counter.json');assert counter['software_cases']==2
    for name,fn in [('public_v2_full_copy_and_idempotent_replay',public_v2),('real_common_host_saved_DSML_relations_and_budgets',common_chain)]:
        counter['software_cases']+=1
        try:result=fn()
        except Exception as exc:
            result=dict(status='FAIL',error=type(exc).__name__+':'+str(exc));save(HERE/(name+'.json'),result)
            counter['software_rows'].append(dict(case=name,**result));save(HERE/'counter.json',counter);raise
        save(HERE/(name+'.json'),result);counter['software_rows'].append(dict(case=name,status='PASS',receipt=str(HERE/(name+'.json'))))
        save(HERE/'counter.json',counter)
    print(json.dumps(dict(status='PASS',S0_software_cases=4,total_package_software_cases=12,new_science=0,new_API=0)),flush=True)


if __name__=='__main__':main()
