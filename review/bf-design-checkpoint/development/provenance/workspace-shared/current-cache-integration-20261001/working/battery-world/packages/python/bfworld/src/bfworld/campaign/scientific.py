"""Controller-owned explanation/use/regression/scope execution for B2.

No default scientific thresholds. A plan and complete task identities are sealed
before execution. Public engineering controls can exercise all paths but can never
produce a qualified knowledge receipt. Blind transfer is not run by this module.
"""
from __future__ import annotations
import json
import fcntl
import math
import statistics
import time
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash,file_hash
from bfworld.coupled.profiled import VERSION as REFERENCE_VERSION
from bfworld.coupled.profiled_artifacts import seal_run,verify_bundle
from .compiler import VERSION as COMPILER_VERSION,output_errors
from .repair import checked,seal,cpu_seconds
from .sandbox import execute as sandbox_execute
from .task_context import public_context,execute_candidate
from .semantic_development import use_control
from .splits import validate_registry,learning_feedback,launch_readiness

VERSION='scientific-qualification-execution-v1'
THRESHOLDS={'min_agreement','min_coverage','max_false_feasible','min_median_probe_reduction','retain_all_solvable'}

def validate_plan(plan,tasks,protocol=None):
    ids={t['task_id']:t for t in tasks}
    validate_registry(tasks,plan.get('exposed_environment_hashes',[]))
    if plan.get('schema_version')!=VERSION or plan.get('purpose') not in {'engineering-controls','formal-qualification'}:
        raise ValueError('explicit qualification plan purpose required')
    if plan.get('task_manifest_hash')!=canonical_hash(tasks) or plan.get('reference_version')!=REFERENCE_VERSION:
        raise ValueError('plan task/reference binding mismatch')
    thresholds=plan.get('thresholds')
    if not isinstance(thresholds,dict) or set(thresholds)!=THRESHOLDS:raise ValueError('all scientific thresholds must be explicit')
    for k in ('min_agreement','min_coverage'):
        if type(thresholds[k]) not in (int,float) or not math.isfinite(thresholds[k]) or not 0<=thresholds[k]<=1:raise ValueError('invalid probability threshold')
    if type(thresholds['max_false_feasible']) is not int or thresholds['max_false_feasible']<0 or thresholds['retain_all_solvable'] is not True:
        raise ValueError('nonnegative false-feasible cap and retained solvability required')
    if type(thresholds['min_median_probe_reduction']) not in (int,float) or not math.isfinite(thresholds['min_median_probe_reduction']) or thresholds['min_median_probe_reduction']<0:
        raise ValueError('explicit nonnegative use threshold required')
    groups=[plan.get(k) for k in ('explanation_ids','use_ids','regression_ids')]
    if any(not isinstance(g,list) or not g or len(g)!=len(set(g)) or not set(g)<=ids.keys() for g in groups):raise ValueError('nonempty unique known task groups required')
    if any(set(a)&set(b) for i,a in enumerate(groups) for b in groups[i+1:]):raise ValueError('explanation/use/regression task groups must be disjoint')
    selected=set(sum(groups,[]))
    if any(ids[k]['split']=='blind-transfer' for k in selected):raise ValueError('blind tasks cannot enter qualification')
    for k in groups[2]:
        if ids[k]['split']!='regression':raise ValueError('regression identity required')
    if plan.get('candidate_order_rule')!='stable-capacitance-ascending':raise ValueError('unsupported candidate ordering; no silent replacement')
    ceiling=plan.get('regression_probe_ceiling',{})
    if set(ceiling)!=set(groups[2]) or any(type(v) is not int or v<0 for v in ceiling.values()):raise ValueError('predeclared per-regression probe ceilings required')
    if not isinstance(plan.get('oos_contexts'),list) or not plan['oos_contexts']:raise ValueError('explicit out-of-scope probes required')
    needed=sum(len(ids[k]['physics']['candidate_designs']) for k in selected)
    if type(plan.get('max_reference_runs')) is not int or plan['max_reference_runs']<needed:raise ValueError('insufficient predeclared reference budget')
    if type(plan.get('max_predictor_calls')) is not int or plan['max_predictor_calls']<len(selected)+len(plan['oos_contexts']):raise ValueError('insufficient predeclared predictor budget')
    if plan['purpose']=='formal-qualification':
        if protocol is None or not launch_readiness(protocol)['ready']:raise ValueError('formal qualification requires owner-approved protocol')
        if protocol.get('qualification_plan_hash')!=canonical_hash(plan) or protocol.get('task_manifest_hash')!=canonical_hash(tasks) or protocol.get('thresholds')!=thresholds or protocol.get('candidate_order_rule')!=plan['candidate_order_rule']:
            raise ValueError('formal protocol does not bind exact scientific decisions')
        if any(ids[k]['split']!='qualification' or ids[k]['prior_exposure']!='never' for k in groups[0]+groups[1]):raise ValueError('formal explanation/use tasks must be previously unobserved qualification conditions')
    elif any(ids[k]['split'] not in {'development','qualification'} for k in groups[0]+groups[1]):
        raise ValueError('invalid engineering explanation/use split')
    return ids

def execute_qualification(candidate,mechanical,tasks,plan,root,*,protocol=None,acquisition_cost_complete=False,observer=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with (root/'qualification.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:return _execute(candidate,mechanical,tasks,plan,root,protocol,acquisition_cost_complete,observer)
        finally:fcntl.flock(lock,fcntl.LOCK_UN)

def _execute(candidate,mechanical,tasks,plan,root,protocol,acquisition_cost_complete,observer):
    root=Path(root);ids=validate_plan(plan,tasks,protocol)
    checked(mechanical)
    if mechanical['candidate_hash']!=canonical_hash(candidate) or mechanical['compiler_hash']!=file_hash(Path(__file__).with_name('compiler.py')) or mechanical['schema_version']!=COMPILER_VERSION:
        raise ValueError('mechanical candidate or compiler identity mismatch')
    implementation={name:file_hash(Path(__file__).with_name(name)) for name in ('scientific.py','compiler.py','task_context.py','semantic_development.py','splits.py','sandbox.py')}
    physical=Path(__file__).parents[1]/'coupled'
    implementation.update({name:file_hash(physical/name) for name in ('profiled.py','profiled_artifacts.py','engine.py')})
    identity={'candidate_hash':canonical_hash(candidate),'mechanical_hash':mechanical['content_hash'],'plan_hash':canonical_hash(plan),
              'protocol_hash':canonical_hash(protocol) if protocol else None,'implementation':implementation,'acquisition_cost_complete':acquisition_cost_complete}
    root.mkdir(parents=True,exist_ok=True);seal(root/'identity.json',identity);seal(root/'plan.json',plan)
    if (root/'report.json').exists():
        result=checked(json.loads((root/'report.json').read_text()))
        if result['identity']!=identity:raise ValueError('qualification result identity mismatch')
        for row in result['rows']:
            bundle=(root/row['artifact']).resolve()
            if not bundle.is_relative_to((root/'runs').resolve()):raise ValueError('reference path escaped qualification')
            verify_bundle(bundle)
            run=json.loads((bundle/'run.json').read_text())
            if row['run_hash']!=run['content_hash'] or row['observed']!=run['physical_mission_pass']['value']:
                raise ValueError('qualification observation misbound')
        return result
    if (root/'execution-start.json').exists():
        # Lock is now held, so an earlier execution cannot still own this path.
        # Its unmeasured crash interval must not disappear from total-cost claims.
        raise RuntimeError('interrupted qualification has incomplete local cost; no automatic rerun or promotion')
    seal(root/'execution-start.json',{'identity_hash':canonical_hash(identity),'started_unix_s':time.time()})
    start,cpu=time.perf_counter(),cpu_seconds();rows=[];uses=[];regressions=[];scope=[];probes=pred_calls=0
    early=[]
    if not mechanical['passed']:early.append('mechanical-rejected')
    if acquisition_cost_complete is not True:early.append('acquisition-cost-incomplete')
    if not early:
        for group in ('explanation_ids','use_ids','regression_ids'):
            for tid in plan[group]:
                task=ids[tid];ctx=public_context(task)
                ctx['candidates']=sorted(ctx['candidates'],key=lambda c:c['capacitance_f'])
                pred_calls+=1
                try:
                    output=sandbox_execute(candidate['code'],ctx,root/'sandbox')
                    errors=output_errors(output,ctx)
                except Exception as exc:output={'scope_ok':False,'predictions':{}};errors=['predictor execution failed: '+type(exc).__name__]
                if errors:early.append('predictor-schema-or-runtime-failure')
                # Malformed output is retained as a failed program, never allowed
                # to become success just because raw fallback can solve a task.
                selection=output if not errors else {'scope_ok':False,'predictions':{}}
                observations={}
                for c in ctx['candidates']:
                    run=execute_candidate(task,c['id']);bundle=seal_run(root/'runs',run);probes+=1
                    if observer:observer({'task_id':tid,'candidate_id':c['id'],'run_hash':run['content_hash']})
                    truth=run['physical_mission_pass']['value']
                    pred=selection['predictions'][c['id']]['verdict'] if selection['scope_ok'] else 'abstain'
                    row={'task_id':tid,'split':task['split'],'group':group,'candidate_id':c['id'],'task_hash':task['content_hash'],
                        'prediction':pred,'observed':truth,'run_hash':run['content_hash'],'artifact':str(bundle.relative_to(root)),
                        'correct':pred!='abstain' and (pred=='feasible')==truth,
                        'false_feasible':pred=='feasible' and not truth,'false_reject':pred=='infeasible' and truth,'errors':errors}
                    rows.append(row);observations[c['id']]={'run_hash':run['content_hash'],'physical_pass':truth}
                raw=use_control(ctx,None,observations);used=use_control(ctx,selection,observations)
                comparison={'task_id':tid,'split':task['split'],'raw':raw,'program':used,
                    'solvability_retained':not raw['success'] or used['success'],
                    'probe_reduction':raw['probes']-used['probes'] if raw['success'] and used['success'] else None}
                if group=='use_ids':uses.append(comparison)
                if group=='regression_ids':regressions.append({**comparison,'ceiling':plan['regression_probe_ceiling'][tid],
                    'passed':comparison['solvability_retained'] and used['probes']<=plan['regression_probe_ceiling'][tid]})
        for i,ctx in enumerate(plan['oos_contexts']):
            pred_calls+=1
            try:out=sandbox_execute(candidate['code'],ctx,root/'sandbox');passed=out=={'scope_ok':False,'predictions':{}}
            except Exception:out=None;passed=False
            scope.append({'probe':i,'context_hash':canonical_hash(ctx),'abstained':passed})
    explanation=[r for r in rows if r['group']=='explanation_ids'];thresholds=plan['thresholds']
    agreement=sum(r['correct'] for r in explanation)/len(explanation) if explanation else 0
    coverage=sum(r['prediction']!='abstain' for r in explanation)/len(explanation) if explanation else 0
    false_feasible=sum(r['false_feasible'] for r in rows)
    gains=[u['probe_reduction'] for u in uses if u['probe_reduction'] is not None]
    median=statistics.median(gains) if gains else None
    checks={'mechanical':mechanical['passed'],'complete_acquisition_cost':acquisition_cost_complete is True,
        'predictor_execution':not early,'explanation':bool(explanation) and agreement>=thresholds['min_agreement'] and coverage>=thresholds['min_coverage'] and false_feasible<=thresholds['max_false_feasible'],
        'use':bool(uses) and all(u['solvability_retained'] for u in uses) and median is not None and median>=thresholds['min_median_probe_reduction'],
        'regression':bool(regressions) and all(u['passed'] for u in regressions),'scope':bool(scope) and all(s['abstained'] for s in scope)}
    controls_pass=all(checks.values());qualified=controls_pass and plan['purpose']=='formal-qualification'
    return seal(root/'report.json',{'schema_version':VERSION,'identity':identity,'purpose':plan['purpose'],'candidate_hash':canonical_hash(candidate),
        'checks':checks,'controls_pass':controls_pass,'qualified':qualified,'rows':rows,'use_tests':uses,'regression_tests':regressions,'scope_tests':scope,
        'metrics':{'agreement':agreement,'coverage':coverage,'false_feasible':false_feasible,'median_probe_reduction':median},
        'cost':{'wall_s':time.perf_counter()-start,'cpu_s':cpu_seconds()-cpu,'reference_runs':probes,'predictor_calls':pred_calls,'provider_calls':0,'paid_cny':0},
        'early_failures':early,'blind_transfer':False,'agent_use_benefit_measured':False,
        'claim_boundary':'Reference validity and deterministic catalogue use checks only. Engineering plans cannot qualify knowledge; a formal qualification is still not blind Agent transfer.'})

def public_feedback(report,tasks):
    checked(report);ids={t['task_id']:t for t in tasks};out=[]
    for row in report['rows']:
        if row['group'] in {'explanation_ids','use_ids'}:
            task=ids[row['task_id']]
            if row['task_hash']!=task['content_hash']:raise ValueError('feedback task binding mismatch')
            out.append(learning_feedback(task,{k:row[k] for k in ('candidate_id','prediction','observed','run_hash','false_feasible','false_reject')}))
    return {'candidate_hash':report['candidate_hash'],'feedback':out,
            'excluded':'regression, out-of-scope and blind confirmation facts are not returned to candidate generation'}

def component_receipt(report,candidate):
    """Bind this executor's result into the existing independent activation API."""
    from .qualification import receipt
    checked(report)
    if report['candidate_hash']!=canonical_hash(candidate):raise ValueError('scientific receipt belongs to another candidate')
    expected=all(report['checks'].values()) and report['purpose']=='formal-qualification'
    if report['qualified']!=expected or (expected and not report['identity']['protocol_hash']):
        raise ValueError('scientific qualification cannot be self-promoted')
    return receipt('world-model',candidate,expected,{'scientific_report_hash':report['content_hash'],
        'plan_hash':report['identity']['plan_hash'],'protocol_hash':report['identity']['protocol_hash'],
        'checks':report['checks'],'metrics':report['metrics'],'purpose':report['purpose'],
        'claim_boundary':report['claim_boundary']})
