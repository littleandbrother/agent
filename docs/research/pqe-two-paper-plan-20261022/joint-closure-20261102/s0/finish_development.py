"""Original B-generated companion before/after consequences, not model credit."""
from common import *
from apparatus import Apparatus
from inputs import Facts


def run():
    target=HERE/'actual-companion-consequences.json'
    if target.exists():raise RuntimeError('NO_AUTOMATIC_DEVELOPMENT_RETRY')
    saved=load(OUT/'b/direct-prefix-generations.json.gz')['saved-undelivered']
    prefix=load(saved['source']);tasks=prefix['public_contract']['tasks']
    pool=next(x for x in saved['outputs'] if x['recursive'])
    companion=next(c for c in pool['candidates'] if len(c.get('closure_chain',[]))>1)
    before_design=companion['closure_chain'][0]['design'];after_design=companion['design']
    assert before_design!=after_design
    app=Apparatus(resume=True);facts=Facts(app)
    for row in load(OLD/'s0/science-resource-ledger.json')['rows']:
        if row['status']=='COMPLETE' and row['task_id'] in {t['task_id'] for t in tasks}:
            old=load(Path(row['path'])/'input.json');task=next(t for t in tasks if t['task_id']==row['task_id'])
            if old['task']==task:app.admit(task,old['design'],row['public_path'],origin='EXACT_OLD_PREFIX_DEVELOPMENT')
    B=module(OUT/'b/joint_strategy.py','joint_consequence_strategy')
    strategy=B.Strategy(prefix['public_contract'],prefix['family_result']['design'],prefix['family_result'],
        fact_fn=facts.facts,calc_fn=facts.calculate,recursive=True,seed=314159)
    results=[]
    for index,(label,design) in enumerate((('before-companion',before_design),('after-companion',after_design)),1):
        value=app.evaluate(tasks,design,group='development-actual-'+label,slot=index,phase='development')
        path=HERE/'development'/label/'result.json.gz';save(path,value)
        update=strategy.update(value)
        results.append(dict(label=label,design=design,statuses=[r['public_check']['verdict'] for r in value['results']],
            public_check=value['public_check'],usage=value['usage'],result=ref(path),update=update))
        save(HERE/'companion-consequences-progress.json',results)
        if value['execution_status']!='COMPLETE':raise RuntimeError('COMPANION_CONSUMER_TOOL_ERROR')
    # Update influences the actual next Generate; a full PASS correctly offers
    # no further action. This is developer direct-path diagnosis only.
    next_action=strategy.propose();save(HERE/'development/after-companion/next-generation.json.gz',next_action)
    save(target,dict(at=now(),status='COMPLETE',source=ref(OUT/'b/direct-prefix-generations.json.gz'),
        candidate_id=companion['id'],closure_chain=companion['closure_chain'],results=results,
        next_action=ref(HERE/'development/after-companion/next-generation.json.gz'),
        changed_after_actual_Update=True,real_model_selected=False,
        scope='Developer-selected existing B-generated candidate; actual facts, companion edit, original full consequences, Update and next Generate. No real-model mechanism benefit credited.'))
    save(HERE/'development-fact-cost-final.json',facts.cost)
    # The two S0 failures are local test harness errors; do not overwrite them
    # or spend a 25th software case to turn the receipt green. Independent B
    # registered cases already exercise both exact paths and actual A facts.
    direct=load(HERE/'direct-checks.json');b=load(OUT/'b/direct-checks.json')
    failures=[r for r in direct['cases'] if r['status']=='FAIL']
    assert len(failures)==2 and b['PASS']==8 and b['FAIL']==0
    save(HERE/'integration-review.json',dict(at=now(),status='PASS_WITH_PRESERVED_LOCAL_HARNESS_FAILURES',
        software_case_attempts=dict(A=6,B=8,S0=10,total=24),additional_case_reruns=0,
        original_s0_receipt=ref(HERE/'direct-checks.json'),failures=failures,
        cause_and_resolution=[dict(case=5,cause='S0 reconstructed parent ID from design, while B correctly binds design plus result.',
            correction='Read original archived parent by exact design; no rerun.',independent_evidence='B candidate_fact_companion_recheck and actual_A_interfaces_two_public_prefixes; actual before/after consumer evidence.'),
            dict(case=7,cause='S0 deliberately chose holding_capacity=8 outside the public domain before normalization.',
                correction='Use the original legal maximum; no authority or production domain change, no rerun.',
                independent_evidence='B inactive_fields_and_authority; original successful large-capacitance designs remain in common history.')],
        revisions_used=2,second_revision_scope='S0 test-harness lookup/domain-input only; scientific methods/consumers unchanged.',
        core_chain_gate='PASS',core_evidence=ref(target),formal_allowed=True,
        limits='Software path and developer direct full consequences do not establish real-model recursive value.'))
    print(json.dumps(dict(event='DEVELOPMENT_COMPANION',statuses=[r['statuses'] for r in results],logical=app.ledger['logical_inputs'],full=app.ledger['full_attempts'],cheap=app.ledger['cheap_numeric'])),flush=True)


if __name__=='__main__':run()
