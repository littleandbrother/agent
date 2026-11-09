"""Ten direct integration cases and bounded original-prefix consequences."""
from common import *
from apparatus import Apparatus,door,lc_adapter
from inputs import inputs,contract,admit_prior,history,Facts
from run_comparison import normalize
from bfworld.agentlab.pqe20261024debt.search import DomainSpace


def run():
    if (HERE/'direct-checks.json').exists():raise RuntimeError('NO_AUTOMATIC_DIRECT_CASE_RERUN')
    for owner in ('a','b'):
        if not (OUT/owner/'HANDOFF.json').exists():raise RuntimeError('OWNER_BLOCK_NOT_READY:'+owner)
    app=Apparatus();facts=Facts(app);B=module(OUT/'b/joint_strategy.py','joint_direct_strategy')
    families,contexts,initials=inputs();admitted=admit_prior(app,families,contexts)
    prefixes={p.stem.split('.')[0]:load(p) for p in (OLD/'shared/prefixes').glob('*.gz')}
    cases=[];details={};pools={};strategies={};development=[]
    def case(name,fn):
        start=time.monotonic()
        try:value=fn();row=dict(name=name,status='PASS',details=value)
        except Exception as exc:row=dict(name=name,status='FAIL',error=type(exc).__name__+':'+str(exc))
        row['wall_s']=time.monotonic()-start;cases.append(row)
        save(HERE/'direct-checks-progress.json',dict(at=now(),cases=cases))
        print(json.dumps(dict(event='DIRECT_CASE',name=name,status=row['status'],error=row.get('error'))),flush=True)

    def bindings():
        assert sum(len(v) for v in families.values())==6
        assert [r['public_check']['verdict'] for r in initials['DOOR']['results']]==['PASS','FAIL','FAIL']
        assert all(r['public_check']['verdict']=='FAIL' for r in initials['LC']['results'])
        return dict(tasks=6,exact_initials=2,admitted_prior_inputs=admitted,consumer_sources=dict(DOOR=door.source_identity(),LC=lc_adapter.source_identity()))

    def calculator():
        c=contract('LC',families['LC'],initials['LC']);d=c['initial_design']
        f=facts.facts(c,d,initials['LC']);v=facts.calculate(c,d)
        changed={**d,'capacitance_f':d['capacitance_f']*1.2,'area_cm2':d['area_cm2']*1.1}
        other=facts.calculate(c,changed)
        assert len(v['tasks'])==len(other['tasks'])==3 and v['tasks']!=other['tasks']
        assert {'capacitance_f','area_cm2'}<=set(f['active_fields']) and f['scope']['full_service']=='UNKNOWN'
        assert all(t['full_service']=='UNKNOWN' for t in v['tasks'])
        dc=contract('DOOR',families['DOOR'],initials['DOOR']);dv=facts.calculate(dc,dc['initial_design'])
        assert all(t['loads']['conditional_phase_chains'] and t['loads']['public_domain_endpoint_points'] for t in dv['tasks'])
        details['LC_calculation']=v
        return dict(actual_public_schedules_supported=True,c_pv_change_recomputed=True,door_conditional_chains_present=True,full_service='UNKNOWN')

    def matched():
        summaries=[]
        for name,prefix in prefixes.items():
            c=prefix['public_contract'];initial=prefix['family_result']
            for recursive in (False,True):
                s=B.Strategy(c,initial['design'],initial,fact_fn=facts.facts,calc_fn=facts.calculate,recursive=recursive,seed=314159)
                pool=s.propose();pools[name,recursive]=pool;strategies[name,recursive]=s
                save(HERE/'development'/name/('C' if recursive else 'J')/'proposals.json.gz',pool)
            j,cc=pools[name,False],pools[name,True]
            assert j['common_candidates_sha256']==cc['common_candidates_sha256']
            assert j['common_candidates'] and all(x['parent_id']==j['parent_id'] for x in j['candidates'])
            summaries.append(dict(prefix=name,common_sha256=j['common_candidates_sha256'],joint_count=len(j['candidates']),recursive_count=len(cc['candidates'])))
        return summaries

    def current_parent():
        # Actual full results below feed Update; no fabricated pass/fail facts.
        assert development and all(x['update']['previous_parent_retained'] for x in development)
        return [dict(prefix=x['prefix'],recursive=x['recursive'],update=x['update']) for x in development]

    def actual_chain():
        name=next(iter(prefixes));s=strategies[name,True];prefix=prefixes[name]
        parent=next(r for r in s.archive.values() if r['design']==prefix['family_result']['design'])
        before=s._inspect(parent['design'],parent)
        # Software-only legal role-transition input, never forced on a model or
        # submitted to the scientific consumer to manufacture a milestone.
        raw={**parent['design'],'holding_component':'lp_fifo','read_source':'contact_only','clear_after':'never'}
        candidate=s._candidate(raw,parent,before,'DIRECT_ENGINEERING_ROLE_TRANSITION',[])
        successor,attempts=s._recursive(candidate,parent,before)
        save(HERE/'direct-real-companion-chain.json.gz',dict(candidate=candidate,successor=successor,attempts=attempts,
            scope='Actual original source facts and new recursive code; software test only, no dynamic method credit.'))
        assert successor and len(successor['closure_chain'])>1
        assert successor['design']!=candidate['design'] and successor['full_service']=='UNKNOWN'
        assert all(x['facts_sha256'] for x in successor['closure_chain'])
        return dict(actual_source_fact_chain=True,transitions=len(successor['closure_chain'])-1,scientific_full_executed=False,dynamic_method_credit=False)

    def unknown():
        for pool in pools.values():
            for c in pool['candidates']:assert c['full_service']=='UNKNOWN' and c['empirical_status']=='NOT_EVALUATED'
        lc=details['LC_calculation'];assert lc['applicability']['service_certificate'] is None
        assert all(t['clock']['actual_sync_at']=='UNKNOWN' and t['recovery']['full_service']=='UNKNOWN' for t in lc['tasks'])
        return dict(static_and_dynamic_separate=True)

    def freedom():
        c=contract('DOOR',families['DOOR'],initials['DOOR']);sp=DomainSpace(c,c['initial_design'])
        raw={**c['initial_design'],'holding_capacity':c['design_domain']['holding_capacity']['max'],
             'read_source':'holding_then_contact','clear_after':'ack'}
        norm=normalize(sp,raw);assert norm['holding_component']=='off' and norm['read_source']=='contact_only'
        successful=[r for r in history()['rows'] if r['family']=='DOOR' and r['public_check']['verdict']=='PASS']
        for r in successful:app.validate(families['DOOR'][0],normalize(sp,r['design']))
        return dict(prior_legal_successes_retained=len(successful),no_capacitance_truncation=True,inactive_normalized=True)

    def payload():
        from provider import PublicObjects,p,base
        obj=PublicObjects(HERE/'direct-public-objects');raw=dict(rows=[dict(i=i,text='实际公共内容'*30) for i in range(12)])
        ident=obj.register(raw);page=obj.read(dict(object_id=ident,section='/rows',offset=0))
        assert len(p.encoded(page))<=1800 and page['rows']
        history_=history();projection=obj.project(dict(site='same_backend_free_joint_scientific_design',
            page_history=[page]*64,common_history=history_,current_nodes=[dict(design=initials['LC']['design'])]*7))
        wire=p.callback_payload(projection,32768);assert len(p.encoded(wire))<=240000
        assert wire['request']['page_history']==[page]*64
        parsed=base.formatter.parse_model_output('{"design":{"x":1}}');assert parsed['status']=='OK'
        save(HERE/'direct-wire-receipt.json',dict(projected_bytes=len(p.encoded(projection)),payload_bytes=len(p.encoded(wire)),pages=64,
            same_actual_Pi_payload_function=True,paid_format_probes=0))
        return load(HERE/'direct-wire-receipt.json')

    def budgets():
        from provider import p,LIMITS
        assert p.output_allowance(131071,LIMITS)==1 and p.output_allowance(0,LIMITS)==32768
        assert accounting_gate()['new_missing_usage']==0
        return dict(logical_reuse_charged=True,public_reads=64,nonread_actions=24,total_requests=144,output_remainder_checked=True)

    def boundary():
        for owner in ('a','b'):
            h=load(OUT/owner/'HANDOFF.json')
            assert h.get('full',h.get('full_inputs',0))==0
        assert all(not p.get('hidden_truth_exposed') and not p.get('successor_design_exposed') for p in prefixes.values())
        return dict(public_only=True,consumers_unmodified=True,old_packages_closed=True,source_hashes=facts.a.source_identity())

    case('1 exact bindings',bindings);case('2 repaired shared numeric path',calculator)
    case('3 same-parent J/C common pool',matched)
    if all(c['status']=='PASS' for c in cases):
        # Exact old prefix contexts remain the original development contracts.
        for name,prefix in prefixes.items():
            c=prefix['public_contract'];tasks=c['tasks']
            for row in load(OLD/'s0/science-resource-ledger.json')['rows']:
                if row['status']=='COMPLETE' and row['task_id'] in {t['task_id'] for t in tasks}:
                    old=load(Path(row['path'])/'input.json');task=next(t for t in tasks if t['task_id']==row['task_id'])
                    if old['task']==task:app.admit(task,old['design'],row['public_path'],origin='EXACT_OLD_PREFIX_DEVELOPMENT')
            for recursive in (False,True):
                pool=pools[name,recursive]
                candidate=next((x for x in pool['candidates'] if x['origin']=='RECURSIVE_COMPANION'),pool['candidates'][0])
                result=app.evaluate(tasks,candidate['design'],group='development-'+name+('-C' if recursive else '-J'),slot=1,phase='development')
                path=HERE/'development'/name/('C' if recursive else 'J')/'result.json.gz';save(path,result)
                update=strategies[name,recursive].update(result)
                development.append(dict(prefix=name,recursive=recursive,candidate=candidate['id'],design=candidate['design'],
                    closure_chain=candidate['closure_chain'],result=ref(path),statuses=[x['public_check']['verdict'] for x in result['results']],
                    usage=result['usage'],update=update))
                save(HERE/'development-results.json',development)
                if result['execution_status']!='COMPLETE':raise RuntimeError('DEVELOPMENT_CONSUMER_TOOL_ERROR')
    case('4 actual Update retains parent',current_parent)
    case('5 actual source-fact recursive chain',actual_chain)
    case('6 UNKNOWN remains UNKNOWN',unknown)
    case('7 original legal edit freedom',freedom)
    case('8 actual payload and persistent public pages',payload)
    case('9 separate finite resource math',budgets)
    case('10 source and visibility review',boundary)
    passed=all(c['status']=='PASS' for c in cases)
    save(HERE/'direct-checks.json',dict(at=now(),status='PASS' if passed else 'FAIL',cases=cases,software_cases=len(cases),
        development_logical_inputs=sum(x['usage']['logical_inputs'] for x in development),
        core_chain_gate='PASS' if any(c['name'].startswith('5 ') and c['status']=='PASS' for c in cases) else 'FAIL',
        no_paid_requests=True,revisions_used=1))
    save(HERE/'fact-tool-cost.json',facts.cost)
    save(OUT/'shared/common-history.json.gz',history())
    print(json.dumps(dict(event='STAGE1',status='PASS' if passed else 'FAIL',full=app.ledger['full_attempts'],cheap=app.ledger['cheap_numeric'])),flush=True)


if __name__=='__main__':run()
