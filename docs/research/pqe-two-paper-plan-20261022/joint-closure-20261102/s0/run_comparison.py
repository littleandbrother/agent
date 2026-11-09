"""Twelve actual same-backend agents; optional J/C proposals never decide."""
from common import *
from apparatus import Apparatus
from inputs import inputs, contract, admit_prior, Facts
from provider import Episode, runtime_scope, finite_service
from bfworld.agentlab.pqe20261024debt.search import DomainSpace


def complexity(initial,design):
    edits={k:dict(before=initial.get(k),after=v) for k,v in design.items() if initial.get(k)!=v}
    return dict(changes=edits,changed_field_count=len(edits),
        added_components=([design['holding_component']] if initial.get('holding_component')=='off' and design.get('holding_component') not in {None,'off'} else []),
        capacitance_f=design['capacitance_f'],pv_area_cm2=design.get('area_cm2'),
        scope='Actual unweighted fields/components; no synthetic aggregate burden score.')


def normalize(space,raw):
    design=space.validate(deepcopy(raw))
    if design.get('holding_component')=='off':
        for k,v in dict(holding_capacity=2,holding_overflow='drop_new',read_source='contact_only',clear_after='never').items():
            if k in design:design[k]=v
    return design


def trajectory(app,facts,B,name,family,contexts,condition,repeat,initial,shared_history,initial_facts):
    ident=f'{name}-{condition}-{repeat}'
    folder=HERE/'trajectories'/ident;folder.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();before={k:app.ledger[k] for k in ('full_attempts','full_wall_s','logical_inputs','cache_reuses','cheap_numeric')}
    ctr=contract(name,family,initial);space=DomainSpace(ctr,initial['design'])
    strategy=B.Strategy(ctr,initial['design'],initial,fact_fn=facts.facts,calc_fn=facts.calculate,
        recursive=condition=='G+J+C',seed=repeat) if condition!='G' else None
    nodes=[dict(id='initial',slot=0,parent_id=None,design=initial['design'],statuses=[r['public_check']['verdict'] for r in initial['results']])]
    evaluated={digest(normalize(space,initial['design'])):initial}
    history=[];last=None;episode=None;fatal=None;termination=None;final=None
    method_bundle=None;bundle_parent=None;offers={}
    try:
        episode=Episode(ident,family,initial,condition=condition,
            tools=lambda tool,args: tool_answer(app,facts,ctr,family,evaluated,tool,args),
            shared_history=shared_history,initial_facts=initial_facts)
        while len(history)<6:
            app.ready()
            if strategy and strategy.current_parent_id!=bundle_parent:
                method_bundle=strategy.propose();bundle_parent=strategy.current_parent_id
                save(folder/f'proposals-{len(history)}.json.gz',method_bundle)
                offers={c['id']:c for c in method_bundle['candidates']}
            try:
                payload=episode.query(nodes=nodes,evaluated_slots=len(history),last=last,method_bundle=method_bundle)
            except RuntimeError as exc:
                if str(exc) in {'FINITE_PAID_CAP','EPISODE_WALL_OR_TOOL_CAP','NONREAD_ACTION_CAP','PUBLIC_READ_CAP'}:
                    termination='FINITE_EPISODE_RESOURCE_EXHAUSTED';last=dict(reason=str(exc));break
                raise
            journal(folder/'model-actions.jsonl',payload)
            if isinstance(payload.get('final_design'),dict):
                try:
                    selected=normalize(space,payload['final_design']);final=evaluated[digest(selected)]
                    termination='MODEL_EXPLICIT_EVALUATED_FINAL';break
                except (ValueError,KeyError,TypeError) as exc:
                    last=dict(status='FINAL_REJECTED',reason=str(exc));journal(folder/'rejections.jsonl',last);continue
            offered=offers.get(payload.get('candidate_id'))
            raw=payload.get('design',offered['design'] if offered else None)
            if not isinstance(raw,dict):
                last=dict(status='FORMAT_REJECTED',required='design, offered candidate_id, or evaluated final_design',original=payload)
                journal(folder/'rejections.jsonl',last);continue
            try:
                design=normalize(space,raw);app.validate(family[0],design)
                key=digest(design)
                if key in evaluated:raise ValueError('ALREADY_EVALUATED_DESIGN_NO_NEW_SLOT')
            except (ValueError,KeyError,TypeError) as exc:
                last=dict(status='STATIC_REJECTED',reason=str(exc),submitted=raw,no_full_consumer_executed=True)
                journal(folder/'rejections.jsonl',last);continue
            slot=len(history)+1
            adoption=next((c for c in offers.values() if c['design']==design),None)
            parent_id=adoption['parent_id'] if adoption else payload.get('parent_id',nodes[-1]['id'])
            result=app.evaluate(family,design,group=ident,slot=slot,phase='comparison',contexts=contexts)
            result_path=folder/f'candidate-{slot}.json.gz';save(result_path,result)
            entry=dict(slot=slot,parent_id=parent_id,design=design,raw_proposal=raw,result=ref(result_path),
                statuses=[r['public_check']['verdict'] for r in result['results']],
                public_check=result['public_check'],model_valid=result['model_valid'],usage=result['usage'],
                selected_method_candidate_id=adoption['id'] if adoption else None,
                origin=adoption['origin'] if adoption else 'FREE_OR_MODIFIED_MODEL_PROPOSAL',
                closure_chain=adoption.get('closure_chain',[]) if adoption else [],
                derivations=adoption.get('derivations',[]) if adoption else [],
                complexity=complexity(initial['design'],design))
            history.append(entry);evaluated[key]=result
            nodes.append(dict(id='node-'+key[:24],slot=slot,parent_id=parent_id,design=design,statuses=entry['statuses']))
            episode.history.append(result);episode.candidates.add(key);episode.numerical+=result['usage']['logical_inputs']
            if strategy:last=strategy.update(result);save(folder/'strategy-state.json.gz',strategy.snapshot())
            else:last=dict(status='EVALUATED',slot=slot,statuses=entry['statuses'],public_check=result['public_check'])
            save(folder/'history.json',history);save(HERE/'fact-tool-cost.json',facts.cost)
            if result['execution_status']!='COMPLETE' or not result['model_valid']:
                raise RuntimeError('FULL_TOOL_OR_MODEL_DOMAIN_INCOMPLETE')
            if result['public_check']['verdict']=='PASS':final=result;termination='FIRST_WHOLE_SERVICE_PASS';break
        if termination is None:termination='SIX_DISTINCT_DESIGN_BUDGET_EXHAUSTED'
    except Exception as exc:
        fatal=type(exc).__name__+':'+str(exc);termination='OPERATIONALLY_INCOMPLETE'
    finally:
        if episode:episode.close()
    if strategy:save(folder/'strategy-state.json.gz',strategy.snapshot())
    first=next((h['slot'] for h in history if h['model_valid'] and h['public_check']['verdict']=='PASS'),None)
    outcome=dict(schema='joint-closure-real-model-trajectory-v1',ident=ident,family=name,condition=condition,
        repeat_identifier=repeat,backend_seed_supported=False,status='COMPLETE' if fatal is None else 'OPERATIONALLY_INCOMPLETE',
        termination=termination,fatal=fatal,last_feedback=last,first_all_service_PASS_design_slot=first,
        first_all_service_PASS_logical_inputs=3*first if first is not None else None,
        logical_evaluated_designs=len(history),history=history,
        final=(dict(design=final['design'],public_check=final['public_check']) if final else None),
        new_resources={k:app.ledger[k]-before[k] for k in before},wall_s=time.monotonic()-start,
        method_strategy_cost=strategy.cost if strategy else None,
        model_ledger=load(episode.root/'closeout.json')['ledger'] if episode else None,
        method_identity='actual accounted deepseek/deepseek-flash Pi model; thinking high; underlying weights unreported')
    save(folder/'result.json',outcome)
    print(json.dumps(dict(event='TRAJECTORY',ident=ident,status=outcome['status'],first_PASS=first,fatal=fatal)),flush=True)
    return outcome


def tool_answer(app,facts,ctr,family,evaluated,tool,args):
    raw=args.get('design')
    if not isinstance(raw,dict):raise ValueError('COMPLETE_LEGAL_DESIGN_REQUIRED')
    space=DomainSpace(ctr,ctr['initial_design']);design=normalize(space,raw);app.validate(family[0],design)
    observed=evaluated.get(digest(design))
    if tool=='candidate_facts':return facts.facts(ctr,design,observed)
    operation=args.get('operation','all')
    if operation not in facts.a.OPERATIONS:raise ValueError('UNSUPPORTED_OPERATION:'+str(operation))
    return facts.calculate(ctr,design,operation,public_result=observed)


def run():
    protocol=load(OUT/'shared/protocol.json');require_sources(protocol)
    assert protocol['status']=='FROZEN_FOR_COMPARISON' and protocol['core_chain_gate']=='PASS'
    if (HERE/'comparison-started.json').exists():raise RuntimeError('NO_AUTOMATIC_RETRY_OR_RESUME')
    save(HERE/'comparison-started.json',dict(at=now(),protocol=ref(OUT/'shared/protocol.json')))
    app=Apparatus(resume=True);families,contexts,initials=inputs();admit_prior(app,families,contexts)
    facts=Facts(app);B=module(OUT/'b/joint_strategy.py','joint_frozen_strategy')
    shared_history=load(OUT/'shared/common-history.json.gz')
    initial_facts={name:facts.facts(contract(name,tasks,initials[name]),initials[name]['design'],initials[name]) for name,tasks in families.items()}
    rows=[]
    try:
        with finite_service(),runtime_scope():
            for name,family in families.items():
                for repeat in REPEATS:
                    for condition in ('G','G+J','G+J+C'):
                        result=trajectory(app,facts,B,name,family,contexts,condition,repeat,initials[name],shared_history,initial_facts[name])
                        rows.append(result);save(HERE/'comparison-partial.json',dict(at=now(),trajectories=rows))
                        accounting_gate();ready()
                        if result['fatal']:raise RuntimeError('FORMAL_OPERATIONAL_STOP:'+result['ident']+':'+result['fatal'])
    finally:
        save(HERE/'fact-tool-cost.json',facts.cost)
        save(HERE/'comparison-result.json',dict(at=now(),planned_trajectories=12,trajectories=rows,
            completed=sum(r['status']=='COMPLETE' for r in rows),operational_incomplete=sum(r['status']!='COMPLETE' for r in rows),
            unrun_trajectories=12-len(rows),metric='One design passes all three original conditions; exact reuse counts logical slots equally.',
            scope='Previously exposed development diagnosis, no blind transfer or statistical advantage claim.'))


if __name__=='__main__':run()
