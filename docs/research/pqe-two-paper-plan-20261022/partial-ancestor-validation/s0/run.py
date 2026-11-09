"""Frozen finite comparison; all evaluations use the one original consumer."""
from contextlib import contextmanager
import importlib.util
import sys
import time
from common import *
from apparatus import Apparatus
from provider import Episode, p

spec=importlib.util.spec_from_file_location('partial_frozen_controllers',OUT/'b/controllers.py')
B=importlib.util.module_from_spec(spec);sys.modules[spec.name]=B;spec.loader.exec_module(B)


def tasks():
    local=load(BASE/'codebt-idea/a/TASKS.json')['conditions']
    new=[row['task'] for row in load(OUT/'a/M2r/public-tasks-and-common-parent.json')['rows']]
    return {'known-local':local,'mechanism':new}


def factory(family):
    first=family[0]
    return B.CandidateFactory(dict(design_domain=first['design_domain'],
        active_variables=first['initial_problem']['active_variables']),first['initial_design'])


def bind_cache(app,families):
    for i,t in enumerate(families['known-local'],1):
        app.admit(t,t['initial_design'],BASE/f'codebt-idea/s0/science/{i:02d}-initial-{t["condition_id"]}/result/public-result.json.gz',origin='OLD_SHARED_INITIAL_EXACT_OFF_ROUTE')
        path=BASE/f'codebt-zeroapi/a/{i:02d}-P1-{t["condition_id"]}/result/public-result.json'
        app.admit(t,load(path)['design'],path,origin='SEEN_P1_EXACT_OFF_ROUTE')
    for row in load(OUT/'a/M2r/mechanism-qualification.json')['rows']:
        inp=load(ROOT/row['input_ref'])
        app.admit(inp['task'],inp['design'],OUT/'a/M2r'/row['folder']/'result/public-result.json',
                  origin='COORDINATOR_PRIVATE_EXACT_CACHE_NOT_EXPOSED_UNTIL_REQUESTED')
    app.persist()


@contextmanager
def runtime_scope():
    with connect() as db:
        if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
            raise RuntimeError('OTHER_PROVIDER_REQUEST_ACTIVE')
        prior=db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        prior=prior['value'] if prior else None
        db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps('per-owner'),))
    save(HERE/'runtime-open.json',dict(at=now(),prior_scope=prior,finite_package=PACKAGE))
    try:yield
    finally:
        with connect() as db:
            current=db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            if not current or current['value']!=json.dumps('per-owner'):
                raise RuntimeError('CONCURRENT_BUDGET_SCOPE_CHANGE')
            if prior is None:db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
            else:db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'",(prior,))
            owners=[x[0] for x in db.execute('SELECT owner FROM research_model_owners WHERE protocol=?',(PACKAGE,))]
            for owner in owners:
                db.execute('UPDATE grants SET expires=? WHERE owner=?',(time.time(),owner))
                db.execute('DELETE FROM principals WHERE owner=?',(owner,))
                db.execute("UPDATE conversations SET status='IDLE',updated=? WHERE id=?",(time.time(),owner))
            db.execute('UPDATE research_model_studies SET expires=? WHERE protocol=?',(time.time(),PACKAGE))
        save(HERE/'runtime-closeout.json',dict(at=now(),prior_scope_restored=prior,owners=owners,history_rows_deleted=0))


def trajectory(app,name,family,condition,seed,initial):
    ident=f'{name}-{condition}-{seed}';folder=HERE/'trajectories'/ident;folder.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();before=deepcopy({k:app.ledger[k] for k in ['full_attempts','full_wall_s','reused']})
    scope=dict(conditions=[t['condition_id'] for t in family],family_id=family[0]['family_id'])
    f=factory(family)
    ctrl=(B.FreeJointInterface(f,initial,scope=scope,seed=seed) if condition=='G' else
          B.DeterministicController(condition,f,initial,scope=scope,seed=seed))
    ep=None;fatal=None;last=None;final=None;history=[]
    try:
        if condition=='G':ep=Episode(ident,family,initial)
        while not ctrl.termination:
            app.ready()
            if ep:
                payload=ep.query(ctrl,last)
                journal(folder/'model-actions.jsonl',payload)
                if payload.get('candidate_tool') is not None:
                    ep.tools+=1;ep.ready()
                    args=payload['candidate_tool'];last={'candidate_tool_result':ctrl.candidate_tool(**args)}
                    continue
                if isinstance(payload.get('final_design'),dict):
                    final=ctrl.finalize(payload['final_design']);break
                if not isinstance(payload.get('design'),dict):
                    ep.format_errors+=1
                    last=dict(status='FORMAT_ERROR',error='Exactly one complete design, candidate_tool or explicit evaluated final_design is required.',original=payload)
                    if ep.format_errors>=2:raise RuntimeError('BOUNDED_FORMAT_RECOVERY_EXHAUSTED')
                    continue
                if ctrl.slots>=6:
                    ep.format_errors+=1;last=dict(status='SLOT_CAP',required='Select an already evaluated final_design.')
                    if ep.format_errors>=2:raise RuntimeError('FINAL_SELECTION_NOT_SUBMITTED')
                    continue
                ep.tools+=1;ep.ready()
                action=ctrl.submit(payload['design'],parent_id=payload.get('parent_id'))
            else:action=ctrl.step()
            if action['status']=='STATIC_REJECTED':
                last=action;continue
            if action['status']!='ACTION':break
            result=app.evaluate(family,action['design'],group=ident,slot=action['slot'],request_id=action['request_id'])
            history.append(dict(slot=action['slot'],request_id=action['request_id'],design=result['design'],
                public_check=result['public_check'],usage=result['usage'],
                members=[{k:v for k,v in row.items() if k not in {'facts','relationship_graph','relationship_view','component_contract'}} for row in result['results']]))
            last=ctrl.update(result)
            if ep:
                ep.numerical+=result['usage']['full_inputs'];ep.candidates.add(f.semantic_key(result['design']))
                ep.history.append(result)
                if ctrl.slots>=6 and not ctrl.termination:
                    # Same episode and remaining requests; the model selects its own final.
                    last={**last,'required':'No design slots remain; explicitly select an evaluated final_design.'}
                    while True:
                        payload=ep.query(ctrl,last);journal(folder/'model-actions.jsonl',payload)
                        if isinstance(payload.get('final_design'),dict):
                            final=ctrl.finalize(payload['final_design']);break
                        ep.format_errors+=1;last=dict(status='FINAL_SELECTION_REQUIRED',required='Return final_design from an evaluated node.')
                        if ep.format_errors>=2:raise RuntimeError('FINAL_SELECTION_NOT_SUBMITTED')
                    break
        if final is None:final=ctrl.stop()
    except Exception as exc:
        fatal=type(exc).__name__+':'+str(exc)
        final=ctrl.stop()
        print(json.dumps(dict(event='TRAJECTORY_STOP',id=ident,error=fatal)),flush=True)
    finally:
        if ep:
            ep.fatal=fatal or ep.fatal;ep.close()
        from bfworld.agentlab.pqe20261024debt import adapter
        adapter._write_gzip(folder/'controller.json.gz',ctrl.snapshot())
    row=dict(id=ident,family=name,condition=condition,seed=seed,status='OPERATIONAL_STOP' if fatal else 'COMPLETE',
        fatal=fatal,final=final,history=history,wall_s=time.monotonic()-started,
        actual_new_full=app.ledger['full_attempts']-before['full_attempts'],
        actual_full_wall_s=app.ledger['full_wall_s']-before['full_wall_s'],
        reused_full=app.ledger['reused']-before['reused'],snapshot=ref(folder/'controller.json.gz'),
        model_accounting=p.ledger(DB,ep.owner) if ep else None)
    save(folder/'result.json',row)
    print(json.dumps(dict(event='TRAJECTORY',id=ident,status=row['status'],final=final,
                         actual_new_full=row['actual_new_full'],wall_s=row['wall_s'])),flush=True)
    return row


def main():
    protocol=load(OUT/'shared/protocol.json');require_sources(protocol)
    assert protocol['status']=='FROZEN_FOR_COMPARISON'
    app=Apparatus();families=tasks();bind_cache(app,families)
    initials={name:app.evaluate(ts,ts[0]['initial_design'],group='SHARED_INITIAL:'+name,slot=1) for name,ts in families.items()}
    rows=[];holdouts=[];stop=None
    try:
        with runtime_scope():
            for cell in protocol['trajectory_order']:
                ident=f"{cell['family']}-{cell['condition']}-{cell['seed']}"
                try:
                    require_capacity_and_time()
                    row=trajectory(app,cell['family'],families[cell['family']],cell['condition'],cell['seed'],initials[cell['family']])
                    rows.append(row);save(HERE/'comparison-result.json',dict(at=now(),rows=rows,holdouts=holdouts,status='RUNNING'))
                    accounting_gate()
                except Exception as exc:
                    stop=type(exc).__name__+':'+str(exc);break
            finals=[dict(id=row['id'],final=row['final']) for row in rows if row['family']=='mechanism']
            save(HERE/'FINALS-FROZEN-BEFORE-HOLDOUT.json',dict(at=now(),finals=finals,controller_policy_unchanged=True))
            isolated=load(OUT/'a/M2r/tasks-private.json')['isolated_holdouts']
            if not stop:
                for row in rows:
                    if row['family']!='mechanism':continue
                    if not row['final'].get('eligible_for_holdout') or row['fatal']:
                        holdouts.append(dict(id=row['id'],status='NOT_RUN_NO_ELIGIBLE_VALID_FINAL'));continue
                    try:
                        result=app.evaluate(isolated,row['final']['final_design'],group=row['id'],slot='FROZEN_FINAL',phase='holdout')
                        # These results never return to a controller or model.
                        save(HERE/'trajectories'/row['id']/'isolated-result.json',result)
                        holdouts.append(dict(id=row['id'],status='COMPLETE',verdict=result['public_check']['verdict'],
                            members=[dict(condition_id=x['condition_id'],model_valid=x['model_valid'],
                                execution_status=x['execution_status'],public_check=x['public_check'],
                                canonical_public_path=x.get('canonical_public_path')) for x in result['results']],usage=result['usage']))
                    except Exception as exc:
                        stop=type(exc).__name__+':'+str(exc);break
    finally:
        done={r['id'] for r in rows}
        unrun=[dict(**c,id=f"{c['family']}-{c['condition']}-{c['seed']}",status='NOT_RUN_RESOURCE_OR_DEPENDENCY_STOP')
            for c in protocol['trajectory_order'] if f"{c['family']}-{c['condition']}-{c['seed']}" not in done]
        save(HERE/'comparison-result.json',dict(at=now(),rows=rows,unrun=unrun,holdouts=holdouts,
            status='FINITE_MATRIX_COMPLETE' if not stop and len(rows)==24 else 'FINITE_EXIT_INCOMPLETE',
            stop=stop,science_ledger=ref(HERE/'science-resource-ledger.json')))
        save(HERE/'method-postflight.json',dict(**capacity(),reclaimed_bytes=0,new_backups_environments_worktrees=0))


if __name__=='__main__':main()
