#!/usr/bin/env python3
"""Predeclare explicit public development conditions, then execute every one."""
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.kernel.canonical import canonical_hash,file_hash,write_canonical_json
from bfworld.coupled.engine import Design,Reference
from bfworld.coupled.profiled import LoadProfile
from bfworld.coupled.profiled_artifacts import seal_run,verify_bundle
from bfworld.campaign.splits import task_record,validate_registry
from bfworld.campaign.task_context import physics_for,execute_candidate,materialize
from bfworld.campaign.semantic_development import variants,evaluate_variant,diagnostic_context,use_control
from bfworld.campaign.study import task as observed_legacy_task,design_of
from bfworld.campaign.repair import checked,seal,cpu_seconds

def build(repo=REPO):
    modules=['coupled/profiled.py','coupled/profiled_artifacts.py','campaign/task_context.py','campaign/semantic_development.py','campaign/compiler.py','campaign/sandbox.py','campaign/splits.py']
    inputs={'builder_hash':file_hash(Path(__file__)),'pilot_file_hash':file_hash(repo/'docs/campaign/report.json'),
        'implementation':{p:file_hash(repo/'packages/python/bfworld/src/bfworld'/p) for p in modules},
        'frozen_reference_hash':file_hash(repo/'packages/python/bfworld/src/bfworld/coupled/engine.py')}
    root=repo/'.bfworld/b2-profiled'/canonical_hash(inputs).split(':')[1]
    if (root/'report.json').exists():report=checked(json.loads((root/'report.json').read_text()))
    else:
        root.mkdir(parents=True,exist_ok=True);start=time.perf_counter();cpu=cpu_seconds()
        pilot=json.loads((repo/'docs/campaign/report.json').read_text());tasks=[]
        for index in (6,7,8):
            old=observed_legacy_task(index,'qualification')
            # Match the frozen pilot's stable ascending-C use-test order. Input
            # JSON order is not its baseline order; do not conflate the two.
            designs={c['id']:design_of(old,c['id']) for c in sorted(old['public']['candidates'],key=lambda c:c['capacitance_f'])}
            physics=physics_for(designs,Reference(**old['reference']),LoadProfile())
            tasks.append(task_record('observed-qualification-'+str(index),'development',physics,prior_exposure='observed-final'))
        # Fixed engineering variations. Public BEFORE execution; never promoted
        # to independent qualification/blind sets merely by renaming a task.
        designs={'small':replace(Design(),capacitance_f=.00033,esr_ohm=18),
                 'medium':Design(),'large':replace(Design(),capacitance_f=.0047)}
        specs=[('long-tx',Reference(),replace(LoadProfile(),tx_duration_s=.2)),
               ('long-sense',Reference(),replace(LoadProfile(),sense_duration_s=.16)),
               ('tight-deadline',replace(Reference(),deadline_s=.4),LoadProfile()),
               ('shifted-source',replace(Reference(),source_phase_rad=1.5707963267948966),LoadProfile())]
        for name,ref,load in specs:
            tasks.append(task_record('public-'+name,'development',physics_for(designs,ref,load),prior_exposure='public'))
        registry={'schema_version':'public-profiled-development-v1','tasks':tasks,'identity_audit':validate_registry(tasks),
            'protocol_status':'engineering manifest, NOT formal study protocol',
            'selection':'three observed historical conditions plus four fixed explicit public variations; retain all outcomes',
            'baseline_order':'stable ascending capacitance, as in frozen pilot use tests; same order and observations for every program',
            'authorship':'coordinator-defined development checks; no new Agent generation',
            'qualification':False,'blind':False}
        registry=seal(root/'task-manifest.json',registry) # before reference execution
        programs=variants(pilot['knowledge'][2]['candidate']['code'])
        seal(root/'candidate-manifest.json',{'variants':programs,'task_manifest_hash':registry['content_hash']})
        observations={};runs=[]
        for task in tasks:
            observations[task['task_id']]={}
            for candidate in task['physics']['candidate_designs']:
                cid=candidate['id'];run=execute_candidate(task,cid);bundle=seal_run(root/'runs',run)
                observations[task['task_id']][cid]={'run_hash':run['content_hash'],'physical_pass':run['physical_mission_pass']['value']}
                runs.append({'task_id':task['task_id'],'candidate_id':cid,'artifact':str(bundle.relative_to(repo)),
                    'run_hash':run['content_hash'],'summary':run['summary'],'physical':run['physical_mission_pass'],
                    'load_profile':run['load_profile'],'reference':run['reference'],'design':run['design'],
                    'trace':run['rows'],'events':run['events']})
        results=[evaluate_variant(p,tasks,observations,root/'programs'/p['id']) for p in programs]
        # Adapter must preserve original decisions on the identical observed tasks.
        expected={(r['task'],r['candidate']):r['predicted'] for r in pilot['qualifications'][2]['checks']}
        for t in results[0]['tasks'][:3]:
            for r in t['rows']:
                if (r['prediction']=='feasible')!=expected[(t['task_id'].removeprefix('observed-'),r['candidate_id'])]:
                    raise ValueError('interface adapter changed original G2 decision')
            old_use=next(u for u in pilot['qualifications'][2]['use_tests'] if u['task']==t['task_id'].removeprefix('observed-'))
            if (t['raw']['probes'] if t['raw']['success'] else None)!=old_use['baseline_probes'] or (t['program']['probes'] if t['program']['success'] else None)!=old_use['learned_probes']:
                raise ValueError('interface-only use control changed from frozen pilot')
        report=seal(root/'report.json',{'schema_version':'b2-profiled-development-v1','inputs':inputs,'registry':registry,
            'variants':results,'runs':runs,'cost':{'provider_calls':0,'paid_cny':0,'reference_runs':len(runs),
                'wall_s':time.perf_counter()-start,'cpu_s':cpu_seconds()-cpu},
            'scientific_status':{'agent_generated_g3':False,'world_qualified':False,'blind_transfer':False,'agent_transplant':False,'hardware':False},
            'claim_boundary':'Explicit computational task and mechanical portability controls only; engineer-written patches evaluated on public conditions, not learned transfer.'})
    validate(report,repo)
    write_canonical_json(repo/'docs/b2-development/profiled-report.json',report)
    print(json.dumps({'status':'built','profiled_hash':report['content_hash'],'reference_runs':len(report['runs']),
        'variants':[{k:r[k] for k in ('id','false_rejects','false_feasible_predictions','physical_successes')} for r in report['variants']],'provider_calls':0}))
    return report

def validate(report,repo=REPO):
    checked(report);checked(report['registry']);validate_registry(report['registry']['tasks'])
    tasks={t['task_id']:t for t in report['registry']['tasks']}
    expected={(t['task_id'],c['id']) for t in tasks.values() for c in t['physics']['candidate_designs']}
    actual=[(r['task_id'],r['candidate_id']) for r in report['runs']]
    if len(actual)!=len(expected) or set(actual)!=expected:raise ValueError('incomplete/duplicate reference catalogue')
    observations={t:{} for t in tasks}
    for row in report['runs']:
        root=(repo/row['artifact']).resolve()
        if not root.is_relative_to((repo/'.bfworld/b2-profiled').resolve()):raise ValueError('profiled source outside evidence root')
        verify_bundle(root)
        run=json.loads((root/'run.json').read_text())
        designs,ref,load=materialize(tasks[row['task_id']])
        from dataclasses import asdict
        if run['design']!=asdict(designs[row['candidate_id']]) or run['reference']!=asdict(ref) or run['load_profile']!=asdict(load):
            raise ValueError('reference run belongs to another explicit task')
        for k,v in [('run_hash','content_hash'),('summary','summary'),('physical','physical_mission_pass'),('trace','rows'),('events','events'),('load_profile','load_profile'),('reference','reference'),('design','design')]:
            if row[k]!=run[v]:raise ValueError('profiled projection misbound: '+k)
        observations[row['task_id']][row['candidate_id']]={'run_hash':run['content_hash'],'physical_pass':run['physical_mission_pass']['value']}
    pilot=json.loads((repo/'docs/campaign/report.json').read_text())
    proposed=variants(pilot['knowledge'][2]['candidate']['code'])
    if len(proposed)!=len(report['variants']):raise ValueError('variant count mismatch')
    for variant,source in zip(report['variants'],proposed):
        if any(variant[k]!=v for k,v in source.items()):raise ValueError('diagnostic patch changed')
        checked(variant['mechanical'])
        if variant['mechanical']['candidate_hash']!=canonical_hash(variant['candidate']) or not variant['mechanical']['passed']:
            raise ValueError('mechanical receipt misbound')
        if [t['task_id'] for t in variant['tasks']]!=list(tasks):raise ValueError('variant task selection mismatch')
        for t in variant['tasks']:
            record=tasks[t['task_id']];ctx=diagnostic_context(record);facts=observations[t['task_id']]
            if t['task_hash']!=record['content_hash'] or t['context_hash']!=canonical_hash(ctx):raise ValueError('diagnostic context misbound')
            if [r['candidate_id'] for r in t['rows']]!=[c['id'] for c in ctx['candidates']]:raise ValueError('candidate order changed')
            output={'scope_ok':True,'predictions':{r['candidate_id']:{'verdict':r['prediction']} for r in t['rows']}}
            for r in t['rows']:
                f=facts[r['candidate_id']]
                if r['observed']!=f['physical_pass'] or r['run_hash']!=f['run_hash'] or r['false_reject']!=(r['prediction']=='infeasible' and f['physical_pass']) or r['false_feasible_prediction']!=(r['prediction']=='feasible' and not f['physical_pass']):
                    raise ValueError('semantic error row misbound')
            raw=use_control(ctx,None,facts);used=use_control(ctx,output,facts)
            if t['raw']!=raw or t['removed']!=raw or t['program']!=used or t['detached']!=used or t['detached_output_equal'] is not True:
                raise ValueError('use/removal/transplant control mismatch')
        expected_counts={'false_rejects':sum(r['false_reject'] for t in variant['tasks'] for r in t['rows']),
            'false_feasible_predictions':sum(r['false_feasible_prediction'] for t in variant['tasks'] for r in t['rows']),
            'physical_successes':sum(t['program']['success'] for t in variant['tasks']),'qualified':False,'promoted':False}
        if any(variant[k]!=v for k,v in expected_counts.items()):raise ValueError('semantic aggregate or qualification mismatch')
    return {'status':'pass','runs':len(report['runs'])}

if __name__=='__main__':build()
