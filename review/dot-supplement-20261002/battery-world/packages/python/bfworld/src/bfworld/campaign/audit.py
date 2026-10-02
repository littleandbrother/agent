"""Read-only report audit. Never launches providers, programs or new experiments."""
from bfworld.kernel.canonical import canonical_hash

def check_hash(obj):
    if canonical_hash({k:v for k,v in obj.items() if k!='content_hash'})!=obj['content_hash']:raise ValueError('campaign identity mismatch')

def audit(report):
    check_hash(report);check_hash(report['protocol'])
    if report['protocol_hash']!=report['protocol']['content_hash']:raise ValueError('protocol binding mismatch')
    trials=report['trials'];outcomes=report['outcomes'];budget=report['budget'];receipts=budget['receipts']
    if len({t['id'] for t in trials})!=len(trials) or len(trials)!=len(outcomes):raise ValueError('trial identity/count mismatch')
    if len({r['id'] for r in receipts})!=len(receipts):raise ValueError('duplicate paid receipt')
    if budget['calls']!=len(receipts) or budget['unsettled']!=sum(r['state']!='settled' for r in receipts):raise ValueError('cost ledger count mismatch')
    upper=sum(r['charged_upper_micro_cny'] if r['charged_upper_micro_cny'] is not None else r['reserved_micro_cny'] for r in receipts)/1e6
    if upper!=budget['accounted_upper_bound_cny'] or upper>=20 or upper>budget['cap_cny']:raise ValueError('total cost mismatch/overrun')
    by_trial={}
    for r in receipts:by_trial[r['trial']]=by_trial.get(r['trial'],0)+(r['charged_upper_micro_cny'] if r['charged_upper_micro_cny'] is not None else r['reserved_micro_cny'])
    if any(v>2e6 for v in by_trial.values()):raise ValueError('per-trial cost overrun')
    if sum(r['tokens'] or 0 for r in receipts)!=budget['usage_tokens']:raise ValueError('token count mismatch')
    knowledge={k['content_hash']:k for k in report['knowledge']};qual={q['candidate_hash']:q for q in report['qualifications']}
    for k in knowledge.values():
        check_hash(k)
        if canonical_hash(k['candidate'].get('code',''))!=k['program_hash']:raise ValueError('program identity mismatch')
    for q in qual.values():
        check_hash(q)
        if q['candidate_hash'] not in knowledge or q['program_hash']!=knowledge[q['candidate_hash']]['program_hash']:raise ValueError('qualification binding mismatch')
        if q['accuracy']!=sum(c['correct'] for c in q['checks'])/len(q['checks']) or q['false_safe']!=sum(c['false_safe'] for c in q['checks']):raise ValueError('qualification counters changed')
        if (q['status']=='qualified-for-pilot')!=(q['explanation_pass'] and q['use_pass']):raise ValueError('self/false promotion')
    for trial,outcome in zip(trials,outcomes):
        check_hash(trial)
        if trial['id']!=outcome['trial_id']:raise ValueError('trial outcome mismatch')
        if trial['program_used'] and trial['arm']!='joint-without-qualification' and qual[trial['candidate_hash']]['status']!='qualified-for-pilot':raise ValueError('rejected knowledge used by guarded arm')
        submission=trial['submission'];obs=[s['observation'] for s in trial['steps']]
        admitted=bool(submission and submission['claim_pass'] and any(o.get('candidate_id')==submission['candidate_id'] and o.get('physical',{}).get('value') and o.get('energy_residual',1)<1e-7 for o in obs))
        final=outcome['final'];passed=bool(final and final['physical']['value'] and final['energy_residual']<1e-5)
        if (outcome['admitted'],outcome['heldout_physical_pass'],outcome['false_admission'],outcome['computational_verified_success'])!=(admitted,passed,admitted and not passed,admitted and passed):raise ValueError('admission was not derived from bound evidence')
        if final and final['candidate_id']!=submission['candidate_id']:raise ValueError('submitted design changed during final confirmation')
        if trial['verifier_probes']!=sum('physical' in o for o in obs):raise ValueError('probe count mismatch')
        if trial['history_hash']!=knowledge[trial['candidate_hash']]['history_hash']:raise ValueError('unequal prior history')
    return {'status':'pass','trials':len(trials),'model_calls':budget['calls'],'usage_tokens':budget['usage_tokens'],'cost_upper_cny':upper,
      'computational_verified_success':sum(o['computational_verified_success'] for o in outcomes),'false_admissions':sum(o['false_admission'] for o in outcomes),
      'qualified_candidates':sum(q['status']=='qualified-for-pilot' for q in qual.values()),'report_hash':report['content_hash'],
      'scope':'hashes, derived verdicts, guarded treatment activation and usage-based budget; not an independent physical calibration'}
