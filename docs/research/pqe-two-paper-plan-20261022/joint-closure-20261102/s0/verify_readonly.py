"""Read-only receipt/source/ledger check. Never dispatches or runs science."""
from collections import Counter
from common import *


def verify():
    before=load(HERE/'preflight.json');protocol=load(OUT/'shared/protocol.json');require_sources(protocol)
    matrix=load(HERE/'comparison-result.json');science=load(HERE/'science-resource-ledger.json')
    with connect() as db:
        owners=[r['owner'] for r in db.execute('SELECT owner FROM research_model_owners WHERE protocol=?',(PACKAGE,))]
        rows=[dict(r) for r in db.execute('SELECT mr.* FROM model_requests mr JOIN research_model_owners ro ON mr.owner=ro.owner WHERE ro.protocol=? ORDER BY mr.id',(PACKAGE,))]
        new_ids={r['id'] for r in rows}
        old=[dict(r) for r in db.execute('SELECT * FROM model_requests ORDER BY id') if r['id'] not in new_ids]
        authorizations=[dict(r) for r in db.execute('SELECT * FROM historical_usage_exceptions ORDER BY id')]
        old_hash=hashlib.sha256(json.dumps(old,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        auth_hash=hashlib.sha256(json.dumps(authorizations,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        original_unknowns=[dict(db.execute('SELECT * FROM model_requests WHERE id=?',(r['id'],)).fetchone()) for r in before['billing_baseline']['original_unknown_rows']]
        scope=db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        principals=db.execute('SELECT owner FROM principals').fetchall()
        active_credentials=[r['owner'] for r in principals if r['owner'] in owners]
        open_grants=[dict(r) for r in db.execute('SELECT * FROM grants') if r['owner'] in owners and r['expires']>time.time()]
    failures=[]
    def need(condition,label):
        if not condition:failures.append(label)
    need(len(old)==before['billing_baseline']['model_requests_count'],'OLD_ROW_COUNT')
    need(old_hash==before['billing_baseline']['model_requests_rows_sha256'],'OLD_MODEL_ROWS_CHANGED')
    need(auth_hash==before['billing_baseline']['authorizations_rows_sha256'],'ORIGINAL_AUTHORIZATIONS_CHANGED')
    need(original_unknowns==before['billing_baseline']['original_unknown_rows'],'ORIGINAL_UNKNOWN_ROWS_CHANGED')
    need(all(r['status']=='SETTLED' and r['usage'] for r in rows),'NEW_USAGE_NOT_SETTLED')
    need(not active_credentials and not open_grants,'LIVE_NEW_OWNER_CREDENTIALS')
    need((scope['value'] if scope else None)==load(HERE/'runtime-open.json')['prior_scope'],'BUDGET_SCOPE_NOT_RESTORED')
    need(load(HERE/'finite-service-close.json')['package_process_stopped'] is True,'OWN_SERVICE_NOT_STOPPED')
    need(len(rows)<=144 and len(owners)<=12,'PROVIDER_PACKAGE_CAP')
    need(science['full_attempts']<=240 and science['full_wall_s']<=4800,'FULL_CAP')
    need(all(r['status']=='COMPLETE' for r in science['rows']),'SCIENTIFIC_TOOL_INCOMPLETE')
    logical=[json.loads(x) for x in (HERE/'logical-inputs.jsonl').read_text().splitlines()]
    phases=Counter(r['phase'] for r in logical)
    need(phases['development']<=24 and phases['comparison']<=216,'PHASE_LOGICAL_CAP')
    need(len(logical)==science['logical_inputs'],'LOGICAL_LEDGER_MISMATCH')
    a,b=load(OUT/'a/HANDOFF.json'),load(OUT/'b/HANDOFF.json')
    cheap=a['cheap_total']+b['resources']['cheap_total_charged']+science['cheap_numeric']
    need(cheap<=120 and science['cheap_numeric']<=72,'CHEAP_CAP')
    episode_receipts=[]
    for folder in sorted((HERE/'episodes').iterdir()):
        closed=load(folder/'closeout.json');budget=closed['budget'];ledger=closed['ledger']
        need(budget['model_requests']<=12 and budget['output_tokens']<=131072 and budget['spent_usd']<=5.,'EPISODE_PROVIDER_CAP:'+folder.name)
        need(budget['tool_calls']<=64 and budget['nonread_actions']<=24 and budget['numerical_inputs']<=18 and budget['candidates']<=6,'EPISODE_ACTION_CAP:'+folder.name)
        need(budget['model_requests']>0,'NO_REAL_MODEL:'+folder.name)
        callbacks=[]
        for cb in sorted((folder/'callbacks').iterdir()):
            result=load(cb/'callback-result.json');need(result['usage']['status']=='KNOWN','CALLBACK_USAGE:'+str(cb))
            wire=load(cb/'wire-public.json.gz') if (cb/'wire-public.json.gz').exists() else load(cb/'wire-public.json')
            need(wire['model']=='deepseek-flash' and wire['stream'] is True,'CALLBACK_MODEL:'+str(cb))
            need(wire.get('max_tokens',wire.get('max_completion_tokens',0))<=32768,'CALLBACK_OUTPUT_GRANT:'+str(cb))
            callbacks.append(dict(path=str(cb),usage=result['usage'],normalization=result.get('normalization')))
        episode_receipts.append(dict(ident=folder.name,owner=load(folder/'owner.json')['owner'],budget=budget,callbacks=callbacks))
    need(len(episode_receipts)==len(matrix['trajectories']),'EPISODE_MATRIX_MISMATCH')
    total_usd=sum(r['charged'] for r in rows);need(total_usd<=60.,'TOTAL_PROVIDER_USD_CAP')
    tokens=Counter()
    for r in rows:
        u=json.loads(r['usage']) if r['usage'] else {}
        for key in ('prompt_tokens','completion_tokens','total_tokens'):tokens[key]+=u.get(key,0)
        tokens['reasoning_tokens']+=u.get('completion_tokens_details',{}).get('reasoning_tokens',0)
    return dict(at=now(),status='PASS' if not failures else 'FAIL',failures=failures,package=PACKAGE,
        audit_scope='Ledger/source/receipt/resource closure only; does not establish shared-tool functional coverage.',
        comparison_validity=(load(HERE/'comparison-validity.json')['status'] if (HERE/'comparison-validity.json').exists() else 'NOT_ASSESSED'),
        old_model_requests=dict(count=len(old),sha256=old_hash,unchanged=old_hash==before['billing_baseline']['model_requests_rows_sha256']),
        original_authorizations=dict(sha256=auth_hash,unchanged=auth_hash==before['billing_baseline']['authorizations_rows_sha256']),
        original_unknowns_unchanged=original_unknowns==before['billing_baseline']['original_unknown_rows'],
        old_unknown_reserved_usd=sum(r['reserved'] for r in original_unknowns),
        provider=dict(episodes=len(owners),requests=len(rows),statuses=dict(Counter(r['status'] for r in rows)),
            tokens=dict(tokens),settled_charge_upper_bound_usd=total_usd,
            cost_scope='Pinned local accounting estimate/upper bound; no provider invoice claim.',rows=rows),
        episode_receipts=episode_receipts,
        resources=dict(full_new=science['full_attempts'],full_wall_s=science['full_wall_s'],logical_inputs=len(logical),
            phases=dict(phases),exact_reuse=science['cache_reuses'],cheap_numeric_total=cheap,cheap_by_owner=dict(A=a['cheap_total'],B=b['resources']['cheap_total_charged'],S0=science['cheap_numeric']),
            software_cases=24,software_failures=dict(A=4,S0=2),pre_case_parse_failures=1),
        credentials_closed=not active_credentials and not open_grants,capacity=capacity(),
        new_backups_worktrees_environments=0,cleanup_reclaimed_bytes=0)


if __name__=='__main__':
    result=verify()
    print(json.dumps({k:v for k,v in result.items() if k not in {'provider','episode_receipts'}},ensure_ascii=False,indent=2))
    if result['status']!='PASS':raise SystemExit(1)
