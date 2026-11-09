"""One append-only transport attempt in the original two logical episodes."""
from copy import deepcopy
from datetime import datetime
import gzip,hashlib,json,secrets,time,subprocess
import science as s
h=s.host
HERE,ROOT,DB,PACKAGE=s.HERE,s.ROOT,s.DB,s.PACKAGE

def read(p):return json.loads(p.read_text())
def compressed(p):
    with gzip.open(p,'rt') as f:return json.load(f)
def main():
    marker=HERE/'transport-continuation-start.json'
    if marker.exists():raise RuntimeError('ONE_CONTINUATION_ONLY')
    protocol=read(s.PROTOCOL)
    assert protocol['sources']==s.adapter.source_identity()
    assert all(s.ref(ROOT/p)['sha256']==v for p,v in protocol['method_sources'].items())
    ledger=read(HERE/'science-resource-ledger.json')
    owners=protocol['actual_provider_binding']['owners']
    originals={g:read(HERE/'episodes'/g/'owner.json') for g in owners}
    deadlines={g:datetime.fromisoformat(o['activated_at']).timestamp()+900 for g,o in originals.items()}
    assert all(time.time()<v for v in deadlines.values()),'ORIGINAL_DEADLINE_EXPIRED'
    old_refs={str(p.relative_to(ROOT)):s.ref(p) for g in owners for p in (HERE/'episodes'/g/'closeout.json',HERE/'groups'/g/'snapshot.json.gz')}
    with s.p.dbconnect() as db:
        assert not db.execute('SELECT 1 FROM model_requests mr JOIN research_model_owners ro ON ro.owner=mr.owner WHERE ro.protocol=?',(PACKAGE,)).fetchone()
        prior=db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        prior=prior['value'] if prior else None
        db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps('per-owner'),))
        db.execute('UPDATE research_model_studies SET expires=? WHERE protocol=?',(max(deadlines.values()),PACKAGE))
    s.save(marker,dict(at=s.now(),attempt='TRANSPORT_CAP_CONTINUATION',same_owners=owners,original_deadlines_utc={g:datetime.fromtimestamp(v,s.timezone.utc).isoformat() for g,v in deadlines.items()},original_refs=old_refs,per_request_cap=32768,episode_output_cap=131072,new_episode_count=0,new_owner_count=0,new_scientific_initials=0,authority='Reviewer explicit 2026-10-24T11:09 UTC append-only continuation of the original USD10 batch; preserve original terminal snapshots and absolute deadlines.'))
    family=json.loads(s.Path(protocol['family_ref']['path']).read_text())['conditions']
    contract=read(s.Path(protocol['contract_ref']['path']))
    initial=deepcopy(family[0]['initial_design'])
    original_public=[compressed(s.Path(x['public_result']['path'])) for x in ledger['members'] if x['group']=='initial' and x.get('status')=='COMPLETE']
    if len(original_public)!=3:
        original_public=[compressed(p) for p in sorted((HERE/'science').glob('0[123]-*/result/public-result.json.gz'))]
    initial_result=dict(design=initial,results=original_public)
    scope=dict(family_id=family[0]['family_id'],conditions=protocol['conditions'],task_sha256=[h.digest(t) for t in family],model_identity=s.p.MODEL_IDENTITY,fixed_service=True,certificate=None)
    facts_fn=lambda d:s.facts.design_facts(d,family[0])
    common=dict(scope=scope,initial_result=initial_result,active_variables=family[0]['initial_problem']['active_variables'],validate_fn=lambda d:s.task.validate_design(family[0],d))
    ep=None
    summaries={}
    current={}
    def member(t,design,action):
        if ep.budget_view()['remaining_wall_s']<120:raise RuntimeError('ORIGINAL_DEADLINE_INSUFFICIENT_FOR_FULL_INPUT')
        assert ledger['new_full_inputs']<63 and ledger['full_wall_s']+120<=7560
        ordinal=ledger['new_full_inputs']+1
        folder=HERE/'science'/f'{ordinal:02d}-{current["group"]}-{t["condition_id"]}'
        ledger['new_full_inputs']+=1;s.save(HERE/'science-resource-ledger.json',ledger)
        row=dict(index=ordinal,group=current['group'],candidate_ordinal=current['ordinal'],condition_id=t['condition_id'],attempt='TRANSPORT_CAP_CONTINUATION',task_sha256=h.digest(t),design_sha256=h.digest(design))
        s.journal('scientific-claims.jsonl',dict(**row,at=s.now(),input_path=str(folder/'input.json')))
        start=time.monotonic()
        try:
            result=h.scientific_member(t,design,action,folder)
            row.update(status='COMPLETE',public_result=s.ref(folder/'result/public-result.json.gz'),public_check=result['public_check'],result_sha256=result['result_sha256'])
            return result
        except Exception as exc:
            row.update(status='TOOL_ERROR',error=type(exc).__name__+':'+str(exc));raise
        finally:
            row['wall_s']=time.monotonic()-start;ledger['full_wall_s']+=row['wall_s'];ledger['members'].append(row)
            s.journal('scientific-members.jsonl',row);s.save(HERE/'science-resource-ledger.json',ledger)
    broker=h.FamilyBroker(family,member,sources=protocol['sources'])
    broker.full_inputs=ledger['new_full_inputs'];broker.full_wall_s=ledger['full_wall_s']
    for t,pub in zip(family,original_public):broker.cache[h.digest(dict(task=t,design=initial,sources=protocol['sources']))]=pub
    try:
        for group,owner in owners.items():
            if time.time()>=deadlines[group]:
                summaries[group]=dict(status='ORIGINAL_DEADLINE_EXPIRED_BEFORE_CONTINUATION');continue
            token=secrets.token_urlsafe(32)
            ep=object.__new__(s.ScienceEpisode)
            ep.ident,ep.owner,ep.token=group,owner,token
            ep.limits,ep.protocol,ep.condition=s.LIMITS,protocol,group
            ep.root=HERE/'episodes'/group
            ep.started=time.monotonic()-(time.time()-(deadlines[group]-900))
            old=read(ep.root/'closeout.json')['budget']
            ep.model_calls=old['model_requests'];ep.tools=old['tool_calls'];ep.numerical=old['numerical_inputs'];ep.candidates=set();ep.actions=[]
            ep.fatal=ep.server=ep.thread=None;ep.access_token=secrets.token_urlsafe(32)
            ep.objects=s.PublicObjects(ep.root/'public-objects')
            idx=read(ep.root/'public-objects/index.json');ep.objects.objects=idx['objects'];ep.objects.results=idx['result_objects']
            ep.common_results=original_public;ep.family=family;ep.public_history=[]
            with s.p.dbconnect() as db:
                assert not db.execute('SELECT 1 FROM model_requests WHERE owner=?',(owner,)).fetchone()
                assert not s.historical_usage.new_batch_usage_blockers(db,owner)
                db.execute('INSERT INTO principals VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),owner,'participant'))
                db.execute('UPDATE grants SET expires=? WHERE owner=?',(deadlines[group],owner))
            ep.start_server()
            planner=h.FinitePlanner(ep.callback,ep.budget_view,model_identity=s.p.MODEL_IDENTITY,settlement_check=ep.settled)
            ctrl=(s.GenericJointAgent(initial,contract,planner,facts_fn=facts_fn,model_identity=s.p.MODEL_IDENTITY,max_evaluated_designs=6,**common) if group=='generic_agent' else s.DebtSearch(initial,contract,facts_fn,planner,model_identity=s.p.MODEL_IDENTITY,seed=20261024,**common))
            # New execution-attempt view, linked to immutable original terminal.
            # The rejected callback still consumes the original controller count.
            ctrl.model_requests=1
            current.update(group=group,ordinal=0)
            rows=[];error=None
            try:
                while True:
                    action=ctrl.step(ep.budget_view())
                    s.journal('transport-continuation-journal.jsonl',dict(at=s.now(),group=group,event='ACTION_OR_STOP',action=action))
                    if action.get('status')!='ACTION':break
                    current['ordinal']+=1;ep.tools+=1;ep.candidates.add(h.digest(action['design']))
                    result=broker.evaluate(group,action)
                    service=s.family_result(result,action['design'],protocol['conditions'])
                    update=ctrl.update(result);rows.append(dict(ordinal=current['ordinal'],action=action,service=service,update=update))
                    ep.numerical+=result['usage']['full_inputs'];ep.public_history.extend(result['results'])
                    s.journal('transport-continuation-journal.jsonl',dict(at=s.now(),group=group,event='RESULT',result=rows[-1]))
                    print(json.dumps(dict(event='CONTINUATION_CANDIDATE',group=group,service=service)),flush=True)
            except Exception as exc:error=type(exc).__name__+':'+str(exc)
            finally:
                s.adapter._write_gzip(ep.root/'continuation-snapshot.json.gz',ctrl.snapshot())
                summaries[group]=dict(status='APPEND_ATTEMPT_CLOSED',owner=owner,original_deadline=deadlines[group],error=error,termination=ctrl.termination,candidates=rows,ledger=s.p.ledger(DB,owner),budget=ep.budget())
                s.save(ep.root/'continuation-closeout.json',summaries[group]);s.p.close_owner(owner,token)
                if ep.server:ep.server.shutdown();ep.server.server_close()
                ep=None
                s.save(HERE/'transport-continuation-summary.json',summaries)
    finally:
        if ep:
            s.p.close_owner(ep.owner,ep.token)
            if ep.server:ep.server.shutdown();ep.server.server_close()
        with s.p.dbconnect() as db:
            for owner in owners.values():
                db.execute('UPDATE grants SET expires=? WHERE owner=?',(time.time(),owner));db.execute('DELETE FROM principals WHERE owner=?',(owner,))
            db.execute('UPDATE research_model_studies SET expires=? WHERE protocol=?',(time.time(),PACKAGE))
            if prior is None:db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
            else:db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'",(prior,))
        s.save(HERE/'transport-continuation-summary.json',summaries)
        ledger['transport_continuation']=summaries;ledger['provider']={g:s.p.ledger(DB,o) for g,o in owners.items()};s.save(HERE/'science-resource-ledger.json',ledger)
        assert all(s.ref(ROOT/p)['sha256']==v['sha256'] for p,v in old_refs.items()),'ORIGINAL_TERMINAL_CHANGED'
        print(json.dumps(dict(event='TRANSPORT_CONTINUATION_CLOSED',groups=list(summaries))),flush=True)
if __name__=='__main__':main()
