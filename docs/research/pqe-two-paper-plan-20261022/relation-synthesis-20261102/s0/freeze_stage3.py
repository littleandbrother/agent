"""One direct core closure readback, then immutable comparison admission."""
from common import *
from apparatus import Apparatus,door,lc_adapter
from bfworld.agentlab.pqe20261024debt.facts import design_facts
from bfworld.agentlab.pqe20261024debt.obligations import semantic_checks


def run():
    if (HERE/'core-closure-gate.json').exists():
        raise RuntimeError('CORE_GATE_ALREADY_RECORDED')
    app=Apparatus(resume=True)
    freeze=load(OUT/'b/closure-v2/freeze-receipt.json')
    for path,sha in freeze['source_manifest'].items():
        assert ref(path)['sha256']==sha
    bindings=[]
    original=load(OUT/'b/frozen-prefixes/candidates.json')['cells']
    for cell in freeze['cells']:
        assert ref(cell['path'])['sha256']==cell['sha256']
        old=next(c for c in original if c['prefix_id']==cell['prefix_id'] and c['switch']==cell['switch'])
        assert cell['design']==old['design'] and cell['same_as_v1_selected_design']
        decision=load(cell['path'])
        if cell['switch']=='on':
            assert not decision['selected']['selection']['coverage_satisfied']
            assert decision['generation']['closure_chains']
        outcome=next(r for r in load(HERE/'stage2-result.json')['cells']
            if r['prefix_id']==cell['prefix_id'] and r['switch']==cell['switch'])
        assert load(outcome['result']['path'])['design']==cell['design']
        bindings.append(dict(prefix_id=cell['prefix_id'],switch=cell['switch'],
            independently_generated_v2_decision=ref(cell['path']),retained_v1_consequence=outcome['result'],
            exact_same_consumer_input=True,new_logical_or_numerical_execution=0,
            causality='New decision provenance bound to a retained exact-input consequence; v1 execution is not reattributed to v2.'))
    example=load(OUT/'b/closure-v2/identity-progress-on.json.gz')
    prefix=load(OUT/'shared/prefixes/identity-progress.json.gz')
    chain=next(c for c in example['generation']['closure_chains'] if c['intent']['kind']=='INTRODUCE_PUBLIC_PRODUCER')
    summaries=[]
    for node in chain['nodes']:
        saved=node['inspection'];design=saved['design']
        actual=design_facts(design,prefix['public_contract']['tasks'][0])
        assert actual==saved['actual_design_facts']
        assert semantic_checks(actual)==saved['actual_semantic_checks']
        assert saved['full_service']=='UNKNOWN'
        summaries.append(dict(id=node['id'],parent_id=node['parent_id'],design=design,
            transition=node['transition'],unmet=[o['check']['kind'] for o in saved['obligations'] if o['status']=='UNMET_STATIC_COMPANION'],
            unknown=[o['check']['kind'] for o in saved['obligations'] if o['status'].startswith('UNKNOWN')],
            source_facts_sha256=digest(actual)))
    root=summaries[0]
    assert root['unmet']==['CONSUMPTION']
    reader=next(n for n in summaries if n['parent_id']==root['id'] and n['design']['read_source']=='holding_then_contact')
    assert 'CONSUMPTION' not in reader['unmet']
    assert reader['transition']['kind']=='COMPANION_FROM_ACTUAL_UNMET_CHECK'
    assert reader['transition']['source_fact_ids']==['holder.production','program.read']
    early=next(n for n in summaries if n['design']['clear_after']=='early')
    assert 'RELIABLE_HANDOFF' in early['unmet']
    for value in ('save','ack'):
        branch=next(n for n in summaries if n['design']['clear_after']==value)
        assert not branch['unmet'] and branch['unknown']
    gate=dict(at=now(),status='PASS',software_checks=1,new_provider_requests=0,new_full_inputs=0,
        source_freeze=ref(OUT/'b/closure-v2/freeze-receipt.json'),actual_source_fact_readback=summaries,
        exact_decision_consequence_bindings=bindings,
        scope='Actual producer->unmet consumption->read companion generation exists. early is an unmet sibling; save/ack are two supported siblings, not a logged early->save edge. All service/dynamic obligations UNKNOWN.',
        selected_component_closure_executed_in_stage2=False,
        stage3_admission='Mechanism implementation and prospective decision chain only, not evidence of efficacy.')
    save(HERE/'core-closure-gate.json',gate)
    journal(HERE/'software-checks.jsonl',dict(index=7,name='actual_source_candidate_duty_closure_and_exact_v2_decision_binding',status='PASS',at=now()))
    # Capture the actual final source tree after pre-comparison direct fixes.
    files=[HERE/x for x in ['common.py','apparatus.py','provider.py','run_stage3.py','freeze_stage3.py']]
    files += [OUT/'b/semantic_search.py',OUT/'b/semantic_closure.py',
        BASE/'partial-ancestor-validation/s0/public_bridge.py',
        BASE/'lc-service-learning/s0/runtime.py',BASE/'codebt-zeroapi/s0/model_format.py',
        LAB/'bfworld/agentlab/historical_usage.py',APP/'scripts/pqe_pi_callback.mjs',
        ROOT/'workbench/bf-architecture-v2/pi-bf-aiot/packages/coding-agent/dist/bundle/index.js']
    protocol=dict(package=PACKAGE,status='FROZEN_FOR_COMPARISON',at=now(),
        method_entry=str(OUT/'b/semantic_closure.py'),candidate_duty_closure_gate='PASS',
        source_hashes={str(p):ref(p)['sha256'] for p in files},
        consumer_sources={'DOOR':door.source_identity(),'LC':lc_adapter.source_identity()},
        task_manifest=ref(OUT/'a/stage3-host/MANIFEST.json'),
        budgets=load(OUT/'shared/registration.json')['cost_cap'],
        six_new_designs_exclude_common_initial=True,
        execution_order='DOOR then LC; seed314159 then271828; G,D,R. No result-based changes.',
        exact_cache_counted_in_logical_comparison=True,
        provider_identity='deepseek/deepseek-flash;profile=engineering-reasoning-active-context-v4;thinking=enabled/high;upstream-weights=unreported',
        lc_candidate_facts='Existing public numeric contracts; holder companion engine unavailable for LC and receives no closure credit.',
        old_packages_remain_paused=True)
    save(OUT/'shared/stage3-protocol.json',protocol)
    save(OUT/'shared/protocol.json',protocol)
    state=load(HERE/'execution-state.json')
    state.update(status='STAGE3_FROZEN_READY_FOR_COMMON_INITIALS_AND_FINITE_GDR')
    state['execution_gate'].update(provider_ready=True,new_full_dispatch='STAGE3_INITIAL6_COMPARISON216_MAX',candidate_duty_closure='PASS_IMPLEMENTATION_ONLY')
    save(HERE/'execution-state.json',state);save(BASE/'execution-state.json',state)
    print(dict(core_gate='PASS',same_four_decisions=True,component_chain_nodes=len(summaries),
        actual_full_consequences_of_new_component_chain='NOT_YET_TESTED',storage=capacity()))


if __name__=='__main__':run()
