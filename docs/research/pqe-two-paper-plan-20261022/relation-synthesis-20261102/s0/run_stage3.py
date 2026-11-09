"""Gated 2-family x 3-method x 2-seed comparison, no automatic retry."""
from collections import Counter
import importlib.util
from types import SimpleNamespace
from common import *
from apparatus import Apparatus, is_lc
from provider import Episode, runtime_scope, finite_service


def load_method():
    protocol = load(OUT/'shared/protocol.json')
    require_sources(protocol)
    if protocol['status'] != 'FROZEN_FOR_COMPARISON':
        raise RuntimeError('STAGE3_NOT_FROZEN')
    if protocol.get('candidate_duty_closure_gate') != 'PASS':
        raise RuntimeError('CORE_CANDIDATE_CLOSURE_NOT_PASSED')
    sys.path.insert(0,str(OUT/'b'))
    path=Path(protocol['method_entry'])
    spec=importlib.util.spec_from_file_location('frozen_relation_comparison',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import semantic_search as base
    return SimpleNamespace(SemanticFactory=module.ClosureFactory,
        FreeJointInterface=base.FreeJointInterface,
        DeterministicController=base.DeterministicController)


def tasks_and_contexts():
    manifest=load(OUT/'a/stage3-host/MANIFEST.json')
    families={'DOOR':[],'LC':[]}
    contexts={}
    for e in manifest['entries']:
        for key in ('task','initial_design','initial_problem','lc_public','lc_host_task'):
            if key in e and ref(e[key]['path']) != e[key]:
                raise RuntimeError('FROZEN_TASK_BINDING:'+key)
        task=load(e['task']['path'])
        families[e['family']].append(task)
        if e['family']=='LC':
            contexts[task['task_id']]=dict(public=load(e['lc_public']['path']),
                                         host_task=load(e['lc_host_task']['path']))
    for family in families.values():
        assert len(family)==3 and all(t['initial_design']==family[0]['initial_design'] for t in family)
    return families,contexts


def contract_for(name,family,initial):
    return dict(family_id=name,world_kind='LC-PV' if name=='LC' else 'DOOR',
        design_domain=family[0]['design_domain'],
        active_variables=family[0]['initial_problem']['active_variables'],tasks=family,
        component_contract=initial['results'][0].get('component_contract'))


def public_node(node):
    state=node['state']
    return dict(id=node['id'],design=node['design'],parent_id=node['parent_id'],
        slot=node['slot'],observations=dict(statuses=state['statuses'],
        stage_counts=state['stage_counts'],received_count=state['received_count'],
        model_valid=state['complete_valid']))


def complexity(initial,design,raw=None):
    changes={k:dict(before=initial.get(k),after=v) for k,v in design.items() if initial.get(k)!=v}
    inactive=[]
    if raw is not None:
        inactive=[k for k in raw if raw.get(k)!=design.get(k)]
    components=[]
    if initial.get('holding_component')=='off' and design.get('holding_component') not in {None,'off'}:
        components.append('holder:'+design['holding_component'])
    return dict(changed_fields=list(changes),changes=changes,changed_field_count=len(changes),
        added_components=components,inactive_fields_normalized=inactive,
        pv_area_delta_cm2=design.get('area_cm2',0)-initial.get('area_cm2',0),
        capacitance_delta_f=design['capacitance_f']-initial['capacitance_f'],
        scope='Unweighted real changes; no synthetic aggregate complexity score.')


def trajectory(app,B,name,family,contexts,condition,seed,initial):
    ident=f'{name}-{condition}-{seed}'
    folder=HERE/'trajectories'/ident
    folder.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    before={k:app.ledger[k] for k in ('full_attempts','full_wall_s','logical_inputs','cache_reuses','cheap_numeric')}
    factory=B.SemanticFactory(contract_for(name,family,initial),family[0]['initial_design'],
        validate_fn=lambda design:app.validate(family[0],design))
    ctrl=(B.FreeJointInterface(factory,initial,seed=seed) if condition=='G' else
          B.DeterministicController(condition,factory,initial,seed=seed))
    episode=None
    history=[]
    fatal=None
    final=None
    last=None
    proposals=0
    try:
        if condition=='G' and not ctrl.termination:
            episode=Episode(ident,family,initial)
        while not ctrl.termination:
            app.ready()
            if episode:
                payload=episode.query(nodes=[public_node(n) for n in ctrl.nodes.values()],
                                      evaluated_slots=ctrl.slots,last=last)
                journal(folder/'model-actions.jsonl',payload)
                proposals+=1
                if isinstance(payload.get('final_design'),dict):
                    final=ctrl.finalize(payload['final_design'])
                    ctrl.termination='MODEL_EXPLICIT_FINAL'
                    break
                if not isinstance(payload.get('design'),dict):
                    last=dict(status='FORMAT_REJECTED',reason='SCHEMA_REQUIRES_DESIGN_OR_EVALUATED_FINAL',original=payload)
                    if proposals>=12:
                        raise RuntimeError('MODEL_REQUEST_BUDGET_NO_VALID_FINAL')
                    continue
                try:
                    action=ctrl.submit(payload['design'],parent_id=payload.get('parent_id'))
                except (ValueError,KeyError) as exc:
                    last=dict(status='STATIC_REJECTED',reason=type(exc).__name__+':'+str(exc),
                              no_full_consumer_executed=True,submitted_design=payload['design'])
                    journal(folder/'local-rejections.jsonl',last)
                    continue
            else:
                action=ctrl.step()
                if action is None:
                    break
            result=app.evaluate(family,action['design'],group=ident,slot=action['slot'],
                                phase='comparison',contexts=contexts)
            result_path=folder/f'candidate-{action["slot"]}.json.gz'
            save(result_path,result)
            entry=dict(slot=action['slot'],parent_id=action['parent_id'],request_id=action['request_id'],
                design=action['design'],raw_proposal=action.get('raw_proposal'),
                result=ref(result_path),statuses=[r['public_check']['verdict'] for r in result['results']],
                model_valid=result['model_valid'],public_check=result['public_check'],usage=result['usage'],
                selection=action.get('selection'),derivations=action.get('derivations',[]),
                closure_derivations=action.get('closure_derivations',[]),
                complexity=complexity(family[0]['initial_design'],action['design'],action.get('raw_proposal')))
            history.append(entry)
            save(folder/'history.json',history)
            if result['execution_status']=='STATIC_REJECTED':
                raise RuntimeError('SHARED_VALIDATOR_DISAGREEMENT')
            last=ctrl.update(result)
            if episode:
                episode.numerical+=result['usage']['logical_inputs']
                episode.candidates.add(factory.semantic_key(result['design']))
                episode.history.append(result)
            save(folder/'controller.json.gz',ctrl.snapshot())
        if condition=='G' and episode and final is None and not ctrl.winner:
            # A spent read quota does not block explicit final selection.
            payload=episode.query(nodes=[public_node(n) for n in ctrl.nodes.values()],
                evaluated_slots=ctrl.slots,last=dict(status=ctrl.termination,final_selection_required=True))
            journal(folder/'model-actions.jsonl',payload)
            if not isinstance(payload.get('final_design'),dict):
                raise RuntimeError('EXPLICIT_FINAL_NOT_SUBMITTED')
            final=ctrl.finalize(payload['final_design'])
        if final is None:
            final=ctrl.stop()
    except Exception as exc:
        fatal=type(exc).__name__+':'+str(exc)
    finally:
        if episode:
            episode.close()
    save(folder/'controller.json.gz',ctrl.snapshot())
    first=0 if initial['public_check']['verdict']=='PASS' else next(
        (r['slot'] for r in history if r['model_valid'] and r['public_check']['verdict']=='PASS'),None)
    complete=(fatal is None and (ctrl.winner is not None or ctrl.termination in {
        'NEW_CANDIDATE_BUDGET_EXHAUSTED','NO_UNSEEN_LEGAL_CANDIDATE','MODEL_EXPLICIT_FINAL'}))
    final_complexity=complexity(family[0]['initial_design'],final['design']) if final else None
    result=dict(schema='relation-synthesis-comparison-trajectory-v1',ident=ident,family=name,
        condition=condition,seed=seed,status='COMPLETE' if complete else 'OPERATIONALLY_INCOMPLETE',
        fatal=fatal,termination=ctrl.termination,first_all_service_PASS_design_slot=first,
        first_all_service_PASS_logical_inputs=3*first if first is not None else None,
        initial_excluded_from_six_candidate_slots=True,logical_evaluated_designs=ctrl.slots,
        history=history,final=final,final_complexity=final_complexity,
        new_resources={k:app.ledger[k]-before[k] for k in before},wall_s=time.monotonic()-start,
        model_ledger=(load(episode.root/'closeout.json')['ledger'] if episode else None),
        method_identity='actual accounted deepseek/deepseek-flash Pi model' if condition=='G' else 'deterministic developer algorithm; zero model calls')
    save(folder/'result.json',result)
    print(json.dumps(dict(event='TRAJECTORY',ident=ident,status=result['status'],first_PASS=first,fatal=fatal)),flush=True)
    return result


def run():
    local_preflight_continuation='--matrix-only-after-local-runtime-root-fix' in sys.argv
    if (HERE/'stage3-running.json').exists() and not local_preflight_continuation:
        raise RuntimeError('NO_AUTOMATIC_STAGE3_RESUME_OR_RETRY')
    B=load_method()
    if local_preflight_continuation:
        with connect() as db:
            assert not db.execute('SELECT 1 FROM research_model_owners WHERE protocol=?',(PACKAGE,)).fetchone()
        assert not (HERE/'trajectories').exists()
        assert not (HERE/'stage3-result.json').exists()
        assert (HERE/'local-runtime-binding-amendment.json').exists()
    else:
        save(HERE/'stage3-running.json',dict(at=now(),finite=True,automatic_resume=False))
    app=Apparatus(resume=True)
    families,contexts=tasks_and_contexts()
    initials={}
    for name,family in families.items():
        if local_preflight_continuation:
            result=load(HERE/'initial'/f'{name}.json.gz')
            assert result['design']==family[0]['initial_design']
            assert len(result['results'])==3 and result['model_valid'] is True
        else:
            result=app.evaluate(family,family[0]['initial_design'],group=name+'-initial',slot=0,
                                phase='initial',contexts=contexts)
            save(HERE/'initial'/f'{name}.json.gz',result)
        initials[name]=result
        if result['execution_status']!='COMPLETE':
            raise RuntimeError('SHARED_INITIAL_INTERFACE_OR_TOOL_ERROR:'+name)
    results=[]
    # Logical comparisons use identical slots; execution order affects only
    # resource reuse. No result-driven order, reseeding or quota transfer.
    with finite_service(), runtime_scope():
        for name,family in families.items():
            for seed in SEEDS:
                for condition in ('G','D','R'):
                    results.append(trajectory(app,B,name,family,contexts,condition,seed,initials[name]))
                    save(HERE/'stage3-partial.json',dict(at=now(),trajectories=results))
                    accounting_gate()
    save(HERE/'stage3-result.json',dict(at=now(),status='FINITE_MATRIX_TERMINATED',
        trajectories=results,planned_trajectories=12,completed=sum(r['status']=='COMPLETE' for r in results),
        operational_incomplete=sum(r['status']!='COMPLETE' for r in results),
        denominators=dict(families=2,methods=3,seeds=2,per_family_method=2),
        metric='First one candidate PASS all three original gates; logical cached inputs counted equally.',
        no_statistical_significance_claim=True))


if __name__=='__main__':
    run()
