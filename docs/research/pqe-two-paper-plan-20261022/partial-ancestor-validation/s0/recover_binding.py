"""Reattach already-executed G results using explicit numeric representation equivalence.

This is host metadata recovery, never another evaluation or a model choice.
Original artifacts, errors, selected candidate, quotas and clocks stay unchanged.
"""
import sys
from common import *
from public_bridge import project
from run import B, tasks, factory
from bfworld.agentlab.pqe20261024debt import adapter


def equivalent(a,b):
    if isinstance(a,bool) or isinstance(b,bool):return type(a)==type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return a==b
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    return type(a)==type(b) and a==b


def main(ident):
    source=HERE/'continued-dispatch/trajectories'/ident
    original=load(source/'result.json')
    assert original['fatal']=='ValueError:MEMBER_DESIGN_BINDING'
    owner=load(HERE/'episodes'/ident/'owner.json')
    assert time.time()<owner['expires'], 'ORIGINAL_EPISODE_DEADLINE_NO_REOPEN'
    target=HERE/'binding-recovery'/ident;target.mkdir(parents=True,exist_ok=False)
    saved=load(source/'controller.json.gz');action=saved['pending'];assert action is not None
    family=tasks()[original['family']];f=factory(family);rows=[];bindings=[]
    ledger=load(HERE/'science-resource-ledger.json')
    for t in family:
        matches=[r for r in ledger['rows'] if r['status']=='COMPLETE' and r['task_id']==t['task_id'] and r['design_sha256']==digest(action['design'])]
        assert matches,'EXACT_REQUESTED_INPUT_REQUIRED'
        selected=matches[0];path=Path(selected['public_path']);public=load(path)
        assert equivalent(public['design'],action['design'])
        decision=load(path.parent/'decision.json');assert equivalent(decision['actual_design'],action['design'])
        bindings.append(dict(condition_id=t['condition_id'],original_public=ref(path),
            original_design=public['design'],requested_design=action['design'],
            original_design_sha256=digest(public['design']),requested_design_sha256=digest(action['design']),
            changed_representation_fields=[k for k in public['design'] if digest(public['design'][k])!=digest(action['design'][k])],
            exact_numeric_values_and_all_nonnumeric_fields_equal=True,source_result_sha256=public['result_sha256']))
        public.update(design=deepcopy(action['design']),condition_id=t['condition_id'])
        rows.append(project(public))
    initial=dict(design=f.initial_design,results=[])
    # Reconstruct only the frozen root initialization; no decisions are made.
    for n in saved['nodes']:
        if n['parent'] is None:
            for member in n['summary']['members']:
                initial['results'].append(dict(design=f.initial_design,condition_id=member['condition_id'],
                    execution_status=member['execution_status'],model_valid=member['model_valid'],public_check=member['public_check'],
                    result_sha256=member['result_sha256']))
    ctrl=B.FreeJointInterface(f,initial,scope=saved['scope'],seed=saved['seed'])
    for key in ['slots','archive','pending','termination','winner','expansions','raw_proposals','static_checks']:
        setattr(ctrl,key,deepcopy(saved[key]))
    ctrl.nodes={n['id']:B.Node(**n) for n in saved['nodes']};ctrl.by_semantic={n.semantic_key:n.id for n in ctrl.nodes.values()}
    ctrl.events=deepcopy(saved['events']);ctrl.round=sum(e['event'] in {'COMPLETE_CHILD_RESULT','SUBMISSION_STATIC_REJECTED'} for e in ctrl.events)
    result=dict(design=action['design'],request_id=action['request_id'],results=rows)
    update=ctrl.update(result);final=ctrl.stop()
    assert update['summary']['all_pass'] and final['all_condition_PASS'], 'NO_HOST_FALLBACK_OR_NEW_MODEL_CHOICE'
    save(target/'numeric-bindings.json',dict(at=now(),authority='Reviewer explicit same-owner numeric type equivalence recovery',
        original_failure=ref(source/'result.json'),original_controller=ref(source/'controller.json.gz'),bindings=bindings,
        original_deadline=owner['expires'],new_science=0,new_model_calls=0,new_software_items=0,
        consumer_controller_and_original_artifacts_unchanged=True))
    adapter._write_gzip(target/'controller.json.gz',ctrl.snapshot())
    save(target/'result.json',dict(id=ident,at=now(),status='RECOVERED_ALREADY_EXECUTED_ALL_PASS',
        final=final,original_failure=ref(source/'result.json'),bindings=ref(target/'numeric-bindings.json'),
        actual_new_full=0,actual_new_provider_requests=0,actual_new_slots=0,
        classification='Same model-selected whole design and actual main-family outcomes; automatic common all-PASS stop, no substituted selection.'))
    print(json.dumps(dict(event='BINDING_RECOVERY',id=ident,final=final),ensure_ascii=False),flush=True)


if __name__=='__main__':
    for ident in sys.argv[1:]:main(ident)
