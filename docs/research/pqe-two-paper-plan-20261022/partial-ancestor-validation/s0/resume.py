"""Explicit same-package recovery after proven local pre-provider rejection.

No frozen algorithm, task, evaluator, prompt, quota or deadline is changed.
Completed cells/inputs are read, not rerun. Interrupted work remains charged.
"""
import secrets
import hashlib
from datetime import datetime
from common import *
import run
import provider
from apparatus import Apparatus, task_module
from bfworld.agentlab.pqe20261024debt import adapter

CONT=HERE/'continued-dispatch'


def align_finite_lease(owner,deadline):
    with connect() as db:
        old=[dict(x) for x in db.execute('SELECT * FROM interactive_leases WHERE owner=?',(owner,))]
        db.execute('UPDATE interactive_leases SET expires=? WHERE owner=?',(deadline,owner))
    journal(CONT/'lease-alignment.jsonl',dict(at=now(),owner=owner,original=old,
        finite_episode_deadline=deadline,quota_changed=False,reason='Deferred UI lease predates finite scientific activation; original same-episode deadline only.'))


class SameEpisode(provider.Episode):
    def __init__(self,ident,family,initial):
        root=HERE/'episodes'/ident
        self.first_recovered_payload=None
        if not root.exists():
            super().__init__(ident,family,initial)
            align_finite_lease(self.owner,load(root/'owner.json')['expires'])
            return
        assert ident in {'known-local-G-314159','mechanism-G-314159'}
        original=load(root/'owner.json')
        assert time.time()<original['expires']
        with connect() as db:assert db.execute('SELECT count(*) FROM model_requests WHERE owner=?',(original['owner'],)).fetchone()[0]==0
        self.ident=ident;self.owner=original['owner'];self.root=root
        self.token=secrets.token_urlsafe(32);self.access_token=secrets.token_urlsafe(32)
        self.limits=provider.LIMITS
        began=datetime.fromisoformat(original['activated_at']).timestamp()
        self.started=time.monotonic()-(time.time()-began)
        self.model_calls=self.tools=self.numerical=0;self.candidates=set();self.actions=[]
        self.fatal=None;self.server=self.thread=None
        self.family=family;self.initial=initial;self.history=[];self.format_errors=0
        self.objects=provider.PublicObjects(HERE/'public-objects')
        self.first_recovered_payload=load(root/'callbacks/01/input-public.json')
        # Admit only the original prompt's referenced public objects.
        def refs(v):
            if isinstance(v,dict):
                for k,x in v.items():
                    if k in {'object_id','public_object_ref'} and isinstance(x,str) and x.startswith('pub-'):
                        target=HERE/'public-objects'/(x+'.json.gz');value=load(target)
                        raw=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
                        assert hashlib.sha256(raw).hexdigest()==x[4:]
                        self.objects.objects[x]=dict(path=str(target),sha256=x[4:],serialized_bytes=len(raw))
                    refs(x)
            elif isinstance(v,list):
                for x in v:refs(x)
        refs(self.first_recovered_payload)
        with connect() as db:
            db.execute('INSERT INTO principals VALUES(?,?,?)',(hashlib.sha256(self.token.encode()).hexdigest(),self.owner,'participant'))
            db.execute('UPDATE grants SET expires=? WHERE owner=?',(original['expires'],self.owner))
        align_finite_lease(self.owner,original['expires'])
        save(root/'local-recovery.json',dict(at=now(),authority='Reviewer original-package explicit transport recovery',
            original_owner=original['owner'],original_started_at=original['activated_at'],original_deadline=original['expires'],
            original_rejection=ref(root/'callbacks/01/callback-result.json'),new_owner=False,new_quota=False))
        self.start_server()

    def paid_callback(self,request):
        if self.first_recovered_payload is not None:
            original=self.first_recovered_payload
            assert request['max_output_tokens']==original['max_output_tokens']
            request=deepcopy(original['request'])
            assert provider.p.callback_payload(request,request['max_output_tokens'])==original
            self.first_recovered_payload=None
        return super().paid_callback(request)


def restore_controller(snapshot,factory,initial):
    ctor=run.B.DeterministicController
    ctrl=ctor(snapshot['condition'],factory,initial,scope=snapshot['scope'],seed=snapshot['seed'])
    for key in ['slots','archive','pending','termination','winner','expansions','raw_proposals','static_checks']:
        setattr(ctrl,key,deepcopy(snapshot[key]))
    ctrl.nodes={n['id']:run.B.Node(**n) for n in snapshot['nodes']}
    ctrl.by_semantic={n.semantic_key:n.id for n in ctrl.nodes.values()}
    ctrl.events=deepcopy(snapshot['events'])
    ctrl.round=sum(e['event'] in {'COMPLETE_CHILD_RESULT','SUBMISSION_STATIC_REJECTED'} for e in ctrl.events)
    return ctrl


def main():
    assert load(HERE/'local-rejection-forensics.json')['status']=='PROVEN_LOCAL_PRE_PROVIDER_REJECTION'
    protocol=load(OUT/'shared/protocol.json');require_sources(protocol);require_capacity_and_time()
    CONT.mkdir(exist_ok=False);run.HERE=CONT;run.Episode=SameEpisode
    app=Apparatus.__new__(Apparatus);app.cache={};app.ledger=load(HERE/'science-resource-ledger.json')
    app.original_static=task_module.static_geometry_facts;task_module.static_geometry_facts=app.static_geometry
    families=run.tasks();run.bind_cache(app,families)
    for row in app.ledger['rows']:
        if row['status']=='COMPLETE':
            inp=load(Path(row['path'])/'input.json');app.admit(inp['task'],inp['design'],row['public_path'],origin='SAME_PACKAGE_COMPLETED_EXACT_INPUT')
    initials={name:app.evaluate(ts,ts[0]['initial_design'],group='RESUME_SHARED_INITIAL:'+name,slot=1) for name,ts in families.items()}
    first=load(HERE/'comparison-result.json');(HERE/'comparison-result.json').rename(HERE/'comparison-first-exit.json')
    rejected=[r for r in first['rows'] if r['condition']=='G'];rows=[r for r in first['rows'] if r['condition']!='G']
    completed={r['id'] for r in rows};holdouts=[];stop=None
    save(OUT/'shared/transport-recovery-002.json',dict(at=now(),authority='Reviewer explicit same-package recovery after local pre-provider proof',
        forensics=ref(HERE/'local-rejection-forensics.json'),source=ref(Path(__file__)),
        original_protocol=ref(OUT/'shared/protocol.json'),completed_cells_not_repeated=sorted(completed),
        prior_transport_exits_preserved=ref(HERE/'comparison-first-exit.json'),
        source_changes_to_frozen_algorithms_physics_prompt_budget_deadline=False,global_full_already_spent=89,
        interrupted_input=29,interrupted_input_charged=True,new_software_items=0))
    # Original G windows keep running; resume these before independent remaining cells.
    recovery=[c for c in protocol['trajectory_order'] if f"{c['family']}-{c['condition']}-{c['seed']}" in {r['id'] for r in rejected}]
    order=recovery+[c for c in protocol['trajectory_order'] if f"{c['family']}-{c['condition']}-{c['seed']}" not in completed|{r['id'] for r in rejected}]
    try:
        with run.runtime_scope():
            with connect() as db:db.execute('UPDATE research_model_studies SET expires=? WHERE protocol=?',(load(HERE/'preflight.json')['absolute_deadline_epoch'],PACKAGE))
            for cell in order:
                ident=f"{cell['family']}-{cell['condition']}-{cell['seed']}"
                try:
                    require_capacity_and_time()
                    prefix=None;ctor=run.B.DeterministicController
                    if ident=='known-local-R-271828':
                        saved=load(HERE/'trajectories'/ident/'controller.json.gz')
                        ctrl=restore_controller(saved,run.factory(families[cell['family']]),initials[cell['family']])
                        action=ctrl.pending;before=deepcopy(app.ledger)
                        result=app.evaluate(families[cell['family']],action['design'],group=ident,slot=action['slot'],request_id=action['request_id'])
                        ctrl.update(result);save(CONT/'interrupted-pending-result.json',result)
                        prefix=dict(previous_interrupted_full=29,previous_receipt=ref(HERE/'science/029/receipt.json'),
                            new_full=app.ledger['full_attempts']-before['full_attempts'],new_wall_s=app.ledger['full_wall_s']-before['full_wall_s'],
                            full_reused=app.ledger['reused']-before['reused'],result=ref(CONT/'interrupted-pending-result.json'))
                        run.B.DeterministicController=lambda *args,**kwargs:ctrl
                    try:row=run.trajectory(app,cell['family'],families[cell['family']],cell['condition'],cell['seed'],initials[cell['family']])
                    finally:run.B.DeterministicController=ctor
                    if prefix:
                        row['resumed_prefix']=prefix;row['actual_new_full']+=prefix['new_full'];row['actual_full_wall_s']+=prefix['new_wall_s'];row['reused_full']+=prefix['full_reused']
                        save(CONT/'trajectories'/ident/'result.json',row)
                    rows.append(row);completed.add(ident)
                    save(HERE/'comparison-result.json',dict(at=now(),rows=rows,initial_local_rejections=rejected,holdouts=holdouts,status='RUNNING_RECOVERED_SAME_PACKAGE'))
                    accounting_gate()
                except Exception as exc:
                    stop=type(exc).__name__+':'+str(exc);break
            save(HERE/'FINALS-FROZEN-BEFORE-HOLDOUT.json',dict(at=now(),finals=[dict(id=r['id'],final=r['final']) for r in rows if r['family']=='mechanism'],feedback_to_method=False))
            if not stop:
                isolated=load(OUT/'a/M2r/tasks-private.json')['isolated_holdouts']
                for row in rows:
                    if row['family']!='mechanism':continue
                    if not row['final'].get('eligible_for_holdout') or row['fatal']:
                        holdouts.append(dict(id=row['id'],status='NOT_RUN_NO_ELIGIBLE_VALID_FINAL'));continue
                    try:
                        result=app.evaluate(isolated,row['final']['final_design'],group=row['id'],slot='FROZEN_FINAL',phase='holdout')
                        save(CONT/'trajectories'/row['id']/'isolated-result.json',result)
                        holdouts.append(dict(id=row['id'],status='COMPLETE',verdict=result['public_check']['verdict'],
                            members=[dict(condition_id=x['condition_id'],model_valid=x['model_valid'],execution_status=x['execution_status'],public_check=x['public_check'],canonical_public_path=x.get('canonical_public_path')) for x in result['results']],usage=result['usage']))
                    except Exception as exc:stop=type(exc).__name__+':'+str(exc);break
    finally:
        missing=[dict(**c,id=f"{c['family']}-{c['condition']}-{c['seed']}",status='NOT_RUN_RESOURCE_OR_DEPENDENCY_STOP') for c in protocol['trajectory_order'] if f"{c['family']}-{c['condition']}-{c['seed']}" not in completed]
        save(HERE/'comparison-result.json',dict(at=now(),rows=rows,unrun=missing,holdouts=holdouts,initial_local_rejections=rejected,
            status='FINITE_MATRIX_COMPLETE' if not stop and len(rows)==24 else 'FINITE_EXIT_INCOMPLETE',stop=stop,
            interrupted_full_counted=29,science_ledger=ref(HERE/'science-resource-ledger.json')))
        save(HERE/'method-postflight.json',dict(**capacity(),reclaimed_bytes=0,new_backups_environments_worktrees=0))


if __name__=='__main__':main()
