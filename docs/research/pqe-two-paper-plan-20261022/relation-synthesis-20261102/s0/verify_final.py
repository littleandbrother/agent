"""One finite-package readback, with no simulation, model or old-package retry."""
from collections import Counter
from common import *
from apparatus import door, lc_adapter


def stable_hash(rows, *, ascii=True):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=ascii,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def verify_ref(value):
    path=Path(value['path'])
    if not path.is_absolute():
        path=ROOT/path
    assert ref(path)['sha256']==value['sha256'], str(path)


def forbidden_paths(value, prefix=''):
    found=[]
    if isinstance(value,dict):
        for key,item in value.items():
            path=prefix+'/'+key
            if key in {'observer_epoch','observer_event_id','hidden_truth','event_truth','truth_event_id'}:
                found.append(path)
            found.extend(forbidden_paths(item,path))
    elif isinstance(value,list):
        for i,item in enumerate(value):
            found.extend(forbidden_paths(item,prefix+'/'+str(i)))
    return found


def run():
    assert not (HERE/'verification.json').exists(), 'NO_DUPLICATE_FINAL_CHECK'
    pre=load(HERE/'preflight.json')
    protocol=load(OUT/'shared/protocol.json')
    require_sources(protocol)
    assert protocol['consumer_sources']==dict(DOOR=door.source_identity(),LC=lc_adapter.source_identity())
    verify_ref(protocol['task_manifest'])
    matrix=load(HERE/'stage3-result.json')
    assert len(matrix['trajectories'])==matrix['planned_trajectories']==12
    expected={(family,method,seed) for family in ('DOOR','LC') for method in ('G','D','R') for seed in SEEDS}
    assert {(r['family'],r['condition'],r['seed']) for r in matrix['trajectories']}==expected
    ledger=load(HERE/'science-resource-ledger.json')
    original_a=load(OUT/'a/RESOURCE-TOTAL.json')
    original_b=load(OUT/'b/HANDOFF-CLOSURE-V2.json')
    assert ledger['full_attempts']==len(ledger['rows'])
    logical=[json.loads(x) for x in (HERE/'logical-inputs.jsonl').read_text().splitlines() if x.strip()]
    assert len(logical)==ledger['logical_inputs']
    assert sum(bool(r['reused']) for r in logical)==ledger['cache_reuses']
    assert ledger['full_attempts']+ledger['cache_reuses']==ledger['logical_inputs']
    phases=Counter(r['phase'] for r in ledger['rows'])
    assert phases['initial']==6 and phases['stage2']==9 and phases['comparison']<=216
    checked_refs=0
    gzip_readback=0
    for r in ledger['rows']:
        folder=Path(r['path'])
        assert load(folder/'receipt.json')==r
        inp=load(folder/'input.json')
        assert digest(inp['design'])==r['design_sha256']
        if r['status']=='COMPLETE':
            public=load(r['public_path'])
            decision=load(folder/'result/decision.json')
            assert public['design']==inp['design'] and public['task_id']==inp['task']['task_id']
            assert decision['task_sha256']==digest(inp['task'])
            assert decision['sources']==protocol['consumer_sources']['LC' if 'area_cm2' in inp['design'] else 'DOOR']
            assert public['model_valid']==r['model_valid'] and public['public_check']['verdict']==r['verdict']
            for name in ('raw','assessment','public-result'):
                f=folder/'result'/f'{name}.json.gz'
                with gzip.open(f,'rb') as stream:
                    while stream.read(1024*1024):
                        pass
                gzip_readback+=1
    for row in logical:
        if row['reused']:
            verify_ref(row['source']);checked_refs+=1
    trajectory_rows=[]
    for r in matrix['trajectories']:
        assert len(r['history'])==r['logical_evaluated_designs']<=6
        assert r['new_resources']['logical_inputs']==3*len(r['history'])
        first=next((h['slot'] for h in r['history'] if h['model_valid'] and h['public_check']['verdict']=='PASS'),None)
        initial=load(HERE/'initial'/f'{r["family"]}.json.gz')
        if initial['public_check']['verdict']=='PASS':
            first=0
        assert first==r['first_all_service_PASS_design_slot']
        for h in r['history']:
            verify_ref(h['result']);checked_refs+=1
            saved=load(h['result']['path'])
            assert saved['design']==h['design']
            assert [x['public_check']['verdict'] for x in saved['results']]==h['statuses']
            assert len(saved['results'])==3
        if r['final']:
            assert any(r['final']['design']==h['design'] for h in r['history']) or r['final']['design']==initial['design']
        trajectory_rows.append({k:r[k] for k in ('ident','family','condition','seed','status','fatal',
            'first_all_service_PASS_design_slot','first_all_service_PASS_logical_inputs','logical_evaluated_designs','new_resources','final_complexity')})
    # Only immutable row identities and compact current billing facts are retained.
    with connect() as db:
        old=[dict(r) for r in db.execute('SELECT * FROM model_requests WHERE created<? ORDER BY id',(pre['wall_start_epoch'],))]
        auth=[dict(r) for r in db.execute('SELECT * FROM historical_usage_exceptions ORDER BY id')]
        assert len(old)==pre['billing_baseline']['model_requests_count']==1995
        assert stable_hash(old)==pre['billing_baseline']['model_requests_rows_sha256']
        assert stable_hash(auth,ascii=False)==pre['billing_baseline']['authorizations_rows_sha256']
        for original in pre['billing_baseline']['original_unknown_rows']:
            assert dict(db.execute('SELECT * FROM model_requests WHERE id=?',(original['id'],)).fetchone())==original
        owners=[dict(r) for r in db.execute('SELECT * FROM research_model_owners WHERE protocol=? ORDER BY trial',(PACKAGE,))]
        new=[dict(r) for r in db.execute('SELECT mr.* FROM model_requests mr JOIN research_model_owners ro ON mr.owner=ro.owner WHERE ro.protocol=? ORDER BY mr.created,mr.id',(PACKAGE,))]
        assert len(owners)==4 and len(new)<=48
        assert all(r['status']=='SETTLED' and r['usage'] is not None for r in new)
        assert not db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone()
        for owner in owners:
            assert not db.execute('SELECT 1 FROM principals WHERE owner=?',(owner['owner'],)).fetchone()
            assert not db.execute('SELECT 1 FROM grants WHERE owner=? AND expires>?',(owner['owner'],time.time())).fetchone()
        assert db.execute('SELECT expires FROM research_model_studies WHERE protocol=?',(PACKAGE,)).fetchone()[0]<=time.time()
        prior=load(HERE/'runtime-open.json')['prior_scope']
        scope=db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        assert (scope[0] if scope else None)==prior
    assert accounting_gate()['new_missing_usage']==0
    token=Counter()
    charged=0.
    ids=[]
    for r in new:
        u=json.loads(r['usage']) if isinstance(r['usage'],str) else r['usage']
        for key in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'):
            token[key]+=u.get(key,0)
        token['reasoning_tokens']+=u.get('completion_tokens_details',{}).get('reasoning_tokens',0)
        charged+=r['charged']
        ids.append(dict(id=r['id'],owner=r['owner'],row_sha256=stable_hash(r),charged_usd=r['charged']))
    episodes=[]
    for owner in owners:
        folder=HERE/'episodes'/owner['trial']
        close=load(folder/'closeout.json')
        budget=close['budget']
        assert close['credentials_closed'] and not close['ledger']['unknown_or_missing_usage']
        assert budget['model_requests']<=12 and budget['tool_calls']<=64 and budget['candidates']<=6
        assert budget['numerical_inputs']<=18 and budget['output_tokens']<=131072 and budget['spent_usd']<=5
        own=[r for r in new if r['owner']==owner['owner']]
        assert len(own)==budget['model_requests']
        callbacks=sorted((folder/'callbacks').iterdir())
        assert len(callbacks)==len(own)
        prior_pages=[]
        for index,callback in enumerate(callbacks):
            request=load(callback/'input-public.json')['request']
            assert not forbidden_paths(request), forbidden_paths(request)[:3]
            assert request['public_page_history'][:len(prior_pages)]==prior_pages
            prior_pages=request['public_page_history']
            remaining=request['remaining']
            assert remaining['provider_requests']==12-index
            assert remaining['public_reads']==64-len(prior_pages)
            assert remaining['design_slots']>=0 and remaining['logical_condition_evaluations']>=0
            wire=load(callback/'wire-public.json')
            sent=[]
            for message in wire['messages']:
                if message['role']!='user':
                    continue
                content=message.get('content')
                text=content if isinstance(content,str) else ''.join(x.get('text','') for x in content)
                sent.append(json.loads(text))
            assert request in sent, 'Actual provider payload differs from the saved public request.'
            assert all(not forbidden_paths(item) for item in sent)
        episodes.append(dict(ident=owner['trial'],budget=budget,callback_count=len(callbacks),
            persisted_pages=close['preserved_read_pages'],source=ref(folder/'closeout.json')))
    assert load(HERE/'finite-service-close.json')['package_process_stopped'] is True
    failure=load(HERE/'failure-log-readback.json')
    assert failure['status']=='BYTE_IDENTICAL_FAILURE_LOG_RESTORED'
    assert ref(failure['original_path'])['sha256']==failure['sha256']
    software=[json.loads(x) for x in (HERE/'software-checks.jsonl').read_text().splitlines() if x.strip()]
    assert len(software)==7, 'Software count must be amended explicitly for any new case.'
    resources=dict(new_full_inputs=original_a['full_attempts']+ledger['full_attempts'],
        new_full_wall_s=original_a['full_wall_s']+ledger['full_wall_s'],
        logical_inputs_including_stage1=original_a['full_attempts']+ledger['logical_inputs'],
        exact_reused_inputs=ledger['cache_reuses'],
        cheap_numeric=original_a['cheap_numeric']+original_b['B_cheap_geometry_miss_total']+ledger['cheap_numeric'],
        software_checks=original_a['software_checks']+original_b['B_software_total']+len(software)+1,
        software_original_B_failures=3,software_S0=len(software)+1,
        provider_episodes=len(owners),provider_requests=len(new),provider_tokens=dict(token),
        cache_aware_rate_estimate_usd=charged,unsettled_reserved_usd=0.,new_unknown=0,
        original_unknown_reserved_usd=sum(x['reserved'] for x in pre['billing_baseline']['original_unknown_rows']),
        scientific_phase_new_inputs=dict(stage1=original_a['full_attempts'],**dict(phases)))
    assert resources['new_full_inputs']<=240 and resources['new_full_wall_s']<=3600
    assert resources['cheap_numeric']<=96 and ledger['cheap_numeric']<=48
    assert resources['software_checks']<=24 and resources['software_S0']<=10 and charged<=20
    costs=dict(at=now(),package=PACKAGE,resources=resources,episodes=episodes,
        row_identities=ids,rate_scope='Pinned cache-aware rate estimate, not an invoice.',
        baseline_rows_unchanged=len(old),baseline_authorizations_unchanged=len(auth))
    save(HERE/'cost-closeout.json',costs)
    save(HERE/'result.json',dict(at=now(),status='FINITE_PACKAGE_EXECUTED',package=PACKAGE,
        stage1=ref(OUT/'a/STAGE1-RESULT.json'),stage2=ref(HERE/'stage2-result.json'),
        component_closure_implementation=ref(HERE/'core-closure-gate.json'),
        comparison=ref(HERE/'stage3-result.json'),trajectories=trajectory_rows,
        resources=resources,cost_closeout=ref(HERE/'cost-closeout.json')))
    journal(HERE/'software-checks.jsonl',dict(index=8,name='finite_artifact_source_host_scope_and_billing_readback',
        status='PASS',at=now(),new_science=0,new_provider=0))
    save(HERE/'verification.json',dict(at=now(),status='PASS',new_science=0,new_provider=0,
        one_necessary_combined_software_check=True,checked_candidate_and_reuse_refs=checked_refs,
        gzip_full_readback_files=gzip_readback,old_billing_rows_unchanged=1995,
        original_unknown_rows_and_reserves_unchanged=True,actual_sent_prompt_private_fields=0,
        public_pages_persist_in_actual_wire=True,accurate_request_and_read_balances=True,
        frozen_sources_and_tasks_unchanged=True,all_six_common_initials_once=True,
        credentials_closed=True,scope_restored=True,package_service_stopped=True,
        resources=resources,storage=capacity(),script=ref(Path(__file__))))
    print(json.dumps(dict(status='PASS',resources=resources),ensure_ascii=False))


if __name__=='__main__':
    run()
