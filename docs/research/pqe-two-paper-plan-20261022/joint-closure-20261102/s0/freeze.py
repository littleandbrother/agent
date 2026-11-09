"""One common pre-formal source/prompt/tool/task/budget freeze."""
from common import *
from apparatus import door,lc_adapter
from inputs import inputs
from provider import p,base


def run():
    path=OUT/'shared/protocol.json'
    if path.exists():raise RuntimeError('ONE_FORMAL_FREEZE_ONLY')
    review=load(HERE/'integration-review.json');assert review['formal_allowed'] and review['core_chain_gate']=='PASS'
    families,contexts,initials=inputs();old=load(OLD/'shared/protocol.json')
    consumers=dict(DOOR=door.source_identity(),LC=lc_adapter.source_identity())
    assert consumers==old['consumer_sources']
    for owner in ('a','b'):
        h=load(OUT/owner/'HANDOFF.json');assert ref(h['entry']['path'])['sha256']==h['entry']['sha256']
    source_paths=set((HERE).glob('*.py'))|{OUT/'a/shared_facts.py',OUT/'b/joint_strategy.py',
        p.SDK,p.APP/'scripts/pqe_pi_callback.mjs',LAB/'bfworld/agentlab/historical_usage.py',
        LAB/'bfworld/agentlab/provider.py',LAB/'bfworld/agentlab/server.py'}
    for m in list(sys.modules.values()):
        f=getattr(m,'__file__',None)
        if f:
            f=Path(f).resolve()
            if f.suffix=='.py' and f.is_relative_to(ROOT):source_paths.add(f)
    source_paths.update(Path(x) for x in old['source_hashes'])
    source_paths.update((OUT/'shared/common-history.json.gz',OUT/'shared/registration.json',OUT/'shared/API.json',HERE/'DIRECT-CHECKS.md'))
    model_identity=dict(api_identity=p.MODEL_IDENTITY,profile=p.PROFILE,thinking='high',
        upstream_weight_identity='unreported',backend_seed_supported=False,
        inherited_prior_identity=old['provider_identity'],sdk_entry=str(p.SDK),
        same_actual_transport_all_conditions=True,paid_format_probes=0)
    save(path,dict(package=PACKAGE,status='FROZEN_FOR_COMPARISON',at=now(),core_chain_gate='PASS',
        integration_review=ref(HERE/'integration-review.json'),source_hashes={str(f):ref(f)['sha256'] for f in sorted(source_paths)},
        consumer_sources=consumers,model_identity=model_identity,
        tasks=ref(OLD/'a/stage3-host/MANIFEST.json'),initials={k:ref(OLD/'s0/initial'/f'{k}.json.gz') for k in initials},
        common_history=ref(OUT/'shared/common-history.json.gz'),budgets=load(OUT/'shared/registration.json')['cost_cap'],
        fixed_order=dict(families=['DOOR','LC'],repeats=list(REPEATS),conditions=['G','G+J','G+J+C']),
        shared_tools=['public_object','candidate_facts','calculate'],
        shared_instruction='Same actual Pi callback payload; no new results from another condition; every legal whole design remains available.',
        method_difference='Optional J strategy; only recursive boolean differs between G+J and G+J+C. Actual model decides in all3.',
        stop='First one whole design PASS all3 conditions; otherwise six distinct designs or declared finite resource stop.',
        exact_cache_uses_equal_logical_slots=True,no_after_PASS_optimization=True,
        scope='Previously exposed development tasks/history, no blind transfer, statistical advantage or optimality claim.',
        retained_failures=dict(A=4,B_pre_case_parse=1,S0_harness=2),old_packages_remain_paused=True))
    state=load(HERE/'execution-state.json');state.update(status='FROZEN_READY_FOR_REAL_MODEL_MATRIX',
        execution_gate=dict(provider_ready=True,development_full='COMPLETE_18_LOGICAL_12_NEW',comparison='CORE_CHAIN_PASS'),
        protocol=ref(path));save(HERE/'execution-state.json',state);save(BASE/'execution-state.json',state)
    print(json.dumps(dict(event='FROZEN',sources=len(source_paths),model=model_identity['api_identity'],capacity=capacity())),flush=True)


if __name__=='__main__':run()
