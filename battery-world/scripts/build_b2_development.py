#!/usr/bin/env python3
"""Build a zero-provider development dossier; never start a new model study."""
import json
import sys
import time
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json
from bfworld.campaign.compiler import compile_candidate
from bfworld.campaign.diagnostics import g2_residuals, canonical_interventions
from bfworld.campaign.repair import seal, checked, cpu_seconds, run_repair
from bfworld.campaign.splits import launch_readiness
from bfworld.campaign.study import task


def build(repo=REPO):
    source = repo/'docs/campaign/report.json'
    before = file_hash(source)
    report = json.loads(source.read_text())
    draft = json.loads((repo/'studies/b2-003/protocol-draft.json').read_text())
    modules = ['compiler.py','repair.py','diagnostics.py','qualification.py','splits.py']
    inputs = {'pilot_file_hash':before,'draft_hash':canonical_hash(draft),
        'implementation':{n:file_hash(repo/'packages/python/bfworld/src/bfworld/campaign'/n) for n in modules},
        'builder_hash':file_hash(Path(__file__)),
        'reference_implementation_hash':file_hash(repo/'packages/python/bfworld/src/bfworld/coupled/engine.py')}
    root = repo/'.bfworld/b2-development'/canonical_hash(inputs).split(':')[1]
    path = root/'report.json'
    if path.exists():
        dossier = checked(json.loads(path.read_text()))
        if dossier['inputs'] != inputs:
            raise ValueError('development dossier identity mismatch')
    else:
        root.mkdir(parents=True,exist_ok=True)
        start, cpu = time.perf_counter(), cpu_seconds()
        contexts = [task(0,'learning')['public']]
        # Explicit envelope migration for static/smoke triage, not a candidate
        # program edit or a claim that the original provider produced v1 schema.
        mechanical = []
        for capsule in report['knowledge']:
            legacy = capsule['candidate']
            wrapped = {'schema_version':'world-model-patch-v1','kind':'world-model',
                'scope':{'source_families':['rotary']}, 'code':legacy.get('code','')}
            mechanical.append({'generation':capsule['generation'],'original_candidate_hash':capsule['content_hash'],
                'adaptation':'envelope only; legacy pass boolean output is intentionally not a v1 ternary verdict',
                'receipt':compile_candidate(wrapped,contexts,root/'sandbox')})
        broken = {'schema_version':'world-model-patch-v1','kind':'world-model',
            'scope':{'source_families':['rotary']},'code':'def plan(ctx):\n    pass = True'}
        control = {**broken,'code':"def plan(ctx):\n    return {'scope_ok': False, 'predictions': {}}"}
        def scripted_replacement(feedback):
            return {'candidate':control,'cost_receipt':{'wall_s':0,'cpu_s':0,'provider_calls':0,'paid_cny':0},
                'proposer':'hand-authored mechanical negative control; not an Agent learning result'}
        repair_control = run_repair(broken,contexts,root/'mechanical-control',scripted_replacement)
        residuals = g2_residuals(report,repo,root/'runs')
        episode = canonical_interventions(repo,root/'runs')
        if file_hash(source) != before:
            raise ValueError('frozen pilot changed during development')
        dossier = seal(path, {'schema_version':'b2-development-dossier-v1','inputs':inputs,
            'status':'engineering-development; not qualified transfer',
            'compiler_triage':mechanical,'mechanical_control':repair_control,'g2':residuals,'episode':episode,
            'protocol_readiness':launch_readiness(draft),
            'cost':{'wall_s':time.perf_counter()-start,'cpu_s':cpu_seconds()-cpu,
                'provider_calls':0,'paid_cny':0,'historical_reproductions':24,
                'canonical_reference_runs':5,'new_scientific_qualification_runs':0,
                'scope':'this local dossier only; historical cost not retroactively estimated'},
            'scientific_status':{'world_model_qualified':False,'blind_transfer':False,'removal':False,
                'transplant':False,'hardware':False,'rsi':False},
            'paid_pilot_file_hash_after':file_hash(source)})
    write_canonical_json(repo/'docs/b2-development/report.json',dossier)
    print(json.dumps({'status':'built','dossier_hash':dossier['content_hash'],
        'false_rejects':len(dossier['g2']['residuals']['false_reject_region']),
        'lost_solvable_tasks':len(dossier['g2']['residuals']['lost_solvable_task']),
        'provider_calls':0,'formal_launch_ready':dossier['protocol_readiness']['ready']}))
    return dossier


if __name__ == '__main__':
    build()
