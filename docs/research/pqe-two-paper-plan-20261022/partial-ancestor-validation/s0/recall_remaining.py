"""Continue one existing G episode with its already-read pages and true remaining quota."""
import secrets
import hashlib
from datetime import datetime
from common import *
import run, provider
from apparatus import Apparatus, task_module
from public_bridge import project
from recover_binding import equivalent
from bfworld.agentlab.pqe20261024debt import adapter


def main():
    ident='mechanism-G-271828';root=HERE/'episodes'/ident;original=load(root/'owner.json')
    assert time.time()<original['expires'],'ORIGINAL_EPISODE_EXPIRED'
    target=HERE/'context-recall';target.mkdir(exist_ok=False);run.HERE=target
    close=load(root/'closeout.json');assert close['budget']['model_requests']==10 and close['budget']['tool_calls']==23
    saved=load(HERE/'continued-dispatch/trajectories'/ident/'controller.json.gz')
    family=run.tasks()['mechanism'];f=run.factory(family)
    manifests=load(OUT/'a/M2r/public-tasks-and-common-parent.json')['rows'];initial_rows=[]
    for t,meta in zip(family,manifests):
        val=load(ROOT/meta['canonical_public_result_ref']);val['condition_id']=t['condition_id'];initial_rows.append(project(val))
    initial=dict(design=f.initial_design,results=initial_rows)
    ctrl=run.B.FreeJointInterface(f,initial,scope=saved['scope'],seed=saved['seed'])
    for key in ['slots','archive','pending','termination','winner','expansions','raw_proposals','static_checks']:
        setattr(ctrl,key,deepcopy(saved[key]))
    ctrl.nodes={n['id']:run.B.Node(**n) for n in saved['nodes']};ctrl.by_semantic={n.semantic_key:n.id for n in ctrl.nodes.values()};ctrl.events=deepcopy(saved['events'])
    ep=provider.Episode.__new__(provider.Episode);ep.ident=ident;ep.owner=original['owner'];ep.root=root
    ep.token=secrets.token_urlsafe(32);ep.access_token=secrets.token_urlsafe(32);ep.limits=provider.LIMITS
    ep.started=time.monotonic()-(time.time()-datetime.fromisoformat(original['activated_at']).timestamp())
    ep.tools=23;ep.numerical=0;ep.candidates=set();ep.actions=[];ep.model_calls=10;ep.fatal=None;ep.server=ep.thread=None
    ep.family=family;ep.initial=initial;ep.history=[];ep.format_errors=0;ep.objects=provider.PublicObjects(HERE/'public-objects')
    observed={};old_inputs=sorted((root/'callbacks').glob('*/input-public.json'))
    for path in old_inputs:
        req=load(path)['request']
        for page in req.get('last_public_tool_results',[]):
            observed[digest(page)]=page
    request=deepcopy(load(old_inputs[-1])['request'])
    request['already_observed_public_pages']=list(observed.values())
    request['last_feedback']=dict(status='PUBLIC_TOOL_CAP',remaining_tool_calls=1,
        factual_context_recovery='Earlier supplied pages are retained here; no new observations or allowance. Remaining quotas below are actual.')
    app=Apparatus.__new__(Apparatus);app.cache={};app.ledger=load(HERE/'science-resource-ledger.json')
    app.original_static=task_module.static_geometry_facts;task_module.static_geometry_facts=app.static_geometry
    run.bind_cache(app,run.tasks())
    for row in app.ledger['rows']:
        if row['status']=='COMPLETE':
            inp=load(Path(row['path'])/'input.json');app.admit(inp['task'],inp['design'],row['public_path'],origin='SAME_PACKAGE_EXACT_PRIOR_RESULT')
    final=None;fatal=None;history=[]
    save(target/'ADMISSION.json',dict(at=now(),owner=ep.owner,original_deadline=original['expires'],
        original_closeout=ref(root/'closeout.json'),source=ref(Path(__file__)),already_observed_pages=len(observed),
        remaining_requests=2,remaining_tools=1,original_quota_unchanged=True,new_software_items=0,
        candidate_selection_after_other_DRA_holdout=True,holdout_results_visible_to_model=False,
        classification='Post-initial-exit interface recovery; not original all-finals-before-any-holdout execution.'))
    try:
        with run.runtime_scope():
            with connect() as db:
                db.execute('INSERT INTO principals VALUES(?,?,?)',(hashlib.sha256(ep.token.encode()).hexdigest(),ep.owner,'participant'))
                db.execute('UPDATE grants SET expires=? WHERE owner=?',(original['expires'],ep.owner))
                db.execute('UPDATE interactive_leases SET expires=? WHERE owner=?',(original['expires'],ep.owner))
                db.execute('UPDATE research_model_studies SET expires=? WHERE protocol=?',(load(HERE/'preflight.json')['absolute_deadline_epoch'],PACKAGE))
            ep.start_server()
            while ep.budget()['model_requests']<12:
                ep.ready(paid=True);budget=ep.budget()
                request['remaining']=dict(design_slots=6-ctrl.slots,requests=12-budget['model_requests'],tools=24-ep.tools)
                request['max_output_tokens']=provider.p.output_allowance(budget['output_tokens'],provider.LIMITS)
                request=ep.objects.project(request)
                answer=ep.paid_callback(request)
                assert answer['usage']['status']=='KNOWN'
                payload=answer['payload'];journal(target/'actions.jsonl',payload)
                if isinstance(payload.get('final_design'),dict):final=ctrl.finalize(payload['final_design']);break
                if payload.get('tool_calls'):
                    calls=payload['tool_calls'];assert len(calls)<=24-ep.tools,'ORIGINAL_TOOL_CAP'
                    pages=[]
                    for call in calls:
                        ep.tools+=1
                        try:pages.append(ep.objects.read(call['arguments']))
                        except Exception as exc:pages.append(dict(error=str(exc)))
                    request['last_public_tool_results']=pages
                    request['already_observed_public_pages']+=pages
                    continue
                assert isinstance(payload.get('design'),dict),'NO_HOST_CANDIDATE_FALLBACK'
                assert ep.tools<24,'ORIGINAL_TOOL_CAP'
                action=ctrl.submit(payload['design'],parent_id=payload.get('parent_id'));assert action['status']=='ACTION'
                ep.tools+=1
                result=app.evaluate(family,action['design'],group=ident,slot=action['slot'],request_id=action['request_id'])
                for member in result['results']:
                    assert equivalent(member['design'],action['design'])
                    member['design']=deepcopy(action['design']);member.update(project(member))
                update=ctrl.update(result);ep.history.append(result);history.append(result)
                save(target/'actual-selected-result.json',result)
                if update['summary']['all_pass']:final=ctrl.stop();break
                request['own_evaluated_results']=[ep.public_result(x) for x in ep.history]
                request['current_nodes']=[dict(id=n.id,design=n.design,summary=n.summary) for n in ctrl.nodes.values()]
                request['last_feedback']=update
            if final is None:final=ctrl.stop()
    except Exception as exc:
        fatal=type(exc).__name__+':'+str(exc);final=ctrl.stop()
    finally:
        if ep.server:ep.server.shutdown();ep.server.server_close()
        provider.p.close_owner(ep.owner,ep.token)
        adapter._write_gzip(target/'controller.json.gz',ctrl.snapshot())
        save(target/'result.json',dict(at=now(),id=ident,status='RECOVERED_SAME_EPISODE' if not fatal else 'OPERATIONAL_STOP',fatal=fatal,
            final=final,budget=ep.budget(),ledger=provider.p.ledger(DB,ep.owner),
            actual_new_full=sum(x['usage']['full_inputs'] for x in history),
            original_source_and_failed_exit_unchanged=True,post_initial_exit_interface_recovery=True))
    print(json.dumps(dict(event='SAME_EPISODE_CONTEXT_RECALL',final=final,fatal=fatal,budget=ep.budget())),flush=True)


if __name__=='__main__':main()
