"""Four frozen paired-prefix candidates through their original three conditions."""
import importlib.util
from common import *
from apparatus import Apparatus


def run():
    target = HERE / 'stage2-result.json'
    if target.exists():
        raise RuntimeError('STAGE2_ALREADY_COMPLETE_NO_RERUN')
    freeze = load(OUT / 'b/frozen-prefixes/freeze-receipt.json')
    for path, sha in freeze['source_manifest'].items():
        assert ref(path)['sha256'] == sha
    protocol = dict(package=PACKAGE, status='STAGE2_FROZEN',
        source_hashes={str(p): ref(p)['sha256'] for p in [
            HERE/'common.py', HERE/'apparatus.py', HERE/'run_stage2.py',
            OUT/'b/semantic_search.py', BASE/'partial-ancestor-validation/s0/public_bridge.py',
            LAB/'bfworld/agentlab/historical_usage.py']},
        semantic_freeze=ref(OUT/'b/frozen-prefixes/freeze-receipt.json'),
        allocation=load(OUT/'shared/registration.json')['allocation'],
        task_selection='A tasks frozen before outcomes; not exposed to B during stage2 formation.')
    save(OUT/'shared/stage2-protocol.json', protocol)
    save(OUT/'shared/protocol.json', protocol)
    spec = importlib.util.spec_from_file_location('stage2_frozen_semantics', OUT/'b/semantic_search.py')
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
    cells = load(OUT/'b/frozen-prefixes/candidates.json')['cells']
    paired = []
    for label in ('identity-progress', 'saved-undelivered'):
        prefix = load(OUT/'shared/prefixes'/f'{label}.json.gz')
        state = B.build_state(prefix['family_result'], prefix['prior_result'], prefix['public_contract'])
        if label == 'identity-progress':
            prior = B.build_state(prefix['prior_result'], public_contract=prefix['public_contract'])
            assert all(state['stage_counts'][k] <= prior['stage_counts'][k] for k in state['stage_counts'])
            assert len([r for r in state['progress'] if r['kind']=='prior_conflict_no_longer_observed']) == 3
            factory = B.SemanticFactory(prefix['public_contract'], state['design'])
            rules = factory._rules(factory.initial_design, state)
            assert {r['patch']['clear_after'] for r in rules if r['rule'].startswith('powered_capture_handoff_')} == {'save', 'ack'}
        group = [load(c['cell_path']) for c in cells if c['prefix_id']==label]
        assert len(group) == 2
        # Inspect frozen concrete records; do not generate a new candidate pool.
        paired.append(dict(prefix_id=label, state=state, cell_refs=[ref(c['cell_path']) for c in cells if c['prefix_id']==label]))
    journal(HERE/'software-checks.jsonl',dict(index=4,name='corrected_identity_progress_on_actual_public_prefix',status='PASS',at=now()))
    journal(HERE/'software-checks.jsonl',dict(index=5,name='durable_SAVE_and_ACK_conditional_handoff_alternatives',status='PASS',at=now()))
    # The B receipt explicitly records equal common pools/facts/RNG and real
    # changed selected designs, not a host-rescored diagnostic pool.
    for label in ('identity-progress', 'saved-undelivered'):
        a, b = [c for c in cells if c['prefix_id']==label]
        assert a['design'] != b['design']
        assert ref(a['prefix_source_path'])['sha256'] == a['prefix_source_sha256'] == b['prefix_source_sha256']
        assert all(ref(c['cell_path'])['sha256'] == c['cell_sha256'] for c in (a,b))
    journal(HERE/'software-checks.jsonl',dict(index=6,name='frozen_actual_prefix_consumption_cut_and_candidate_binding',status='PASS',at=now()))
    app = Apparatus(resume=True)
    old_rows = load(BASE/'partial-ancestor-validation/s0/science-resource-ledger.json')['rows']
    answers = []
    for cell in cells:
        ready()
        assert ref(cell['cell_path'])['sha256'] == cell['cell_sha256']
        prefix = load(cell['prefix_source_path'])
        family = prefix['public_contract']['tasks']
        for task in family:
            # A prior result is reused only for this exact requested input.
            old = next((r for r in old_rows if r.get('status')=='COMPLETE'
                and r['task_id']==task['task_id'] and r['design_sha256']==digest(cell['design'])), None)
            if old:
                app.admit(task,cell['design'],old['public_path'],origin='BFA099_EXACT_REQUESTED_INPUT')
        ident = cell['prefix_id']+'-'+cell['switch']
        result = app.evaluate(family,cell['design'],group=ident,slot=1,phase='stage2')
        path = HERE/'stage2'/f'{ident}.json.gz'
        save(path,result)
        answers.append(dict(prefix_id=cell['prefix_id'],switch=cell['switch'],seed=cell['seed'],
            design=cell['design'],design_patch=cell['design_patch'],
            before=ref(cell['prefix_source_path']), frozen_candidate=ref(cell['cell_path']),
            result=ref(path),public_check=result['public_check'],model_valid=result['model_valid'],
            statuses=[r['public_check']['verdict'] for r in result['results']],usage=result['usage']))
        save(HERE/'stage2-partial.json',dict(completed=answers))
        if result['execution_status']!='COMPLETE':
            raise RuntimeError('STAGE2_COMPLETE_CONSUMER_TOOL_ERROR')
    result = dict(schema='relation-synthesis-paired-prefix-result-v1',at=now(),
        status='COMPLETE',cells=answers,paired_prefixes=paired,
        stage3_gate='PASS_SEMANTIC_TO_DESIGN_CONTENT_CHANGE_BOTH_PREFIXES',
        gate_scope='Mechanism activation on seen diagnostics, not held-out efficacy or method superiority.',
        logical_inputs=sum(r['usage']['logical_inputs'] for r in answers),
        new_full_inputs=sum(r['usage']['full_inputs'] for r in answers),
        cache_reuses=sum(r['usage']['cache_reuses'] for r in answers),
        new_full_wall_s=sum(r['usage']['full_wall_s'] for r in answers),
        old_test_receipt='B original 7PASS/3FAIL retained; S0 corrected three direct assertions independently passed.',
        new_provider_requests=0)
    save(target,result)
    print({k:v for k,v in result.items() if k not in {'cells','paired_prefixes'}})


if __name__=='__main__':
    run()
