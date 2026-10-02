"""Observed G2 semantic ablations, never an Agent repair or qualification result.

All variants receive identical complete public inputs. The original program is
adapted only at its interface; the semantic changes are separately enumerated.
Reference runs and candidate ordering are independent of the program outputs.
"""
from __future__ import annotations
import copy
import difflib
from bfworld.kernel.canonical import canonical_hash
from .compiler import compile_candidate, output_errors
from .sandbox import execute as sandbox_execute
from .task_context import public_context

def variants(original):
    guard="    if not isinstance(ctx, dict) or not isinstance(ctx.get('conditions'), dict) or not ctx.get('candidates') or ctx.get('source_family') != 'rotary':"
    old_guard="    if ctx.get('source_family') != 'rotary':"
    old_output="{'pass': pass_flag, 'minimum_input_v': min_input_v}"
    new_output="{'verdict': 'feasible' if pass_flag else 'infeasible', 'minimum_input_v': min_input_v}"
    load_site="load_energy = tx_power * cand.get('release_s', 0.25) / regulator_efficiency"
    for site in (old_guard,old_output,load_site):
        if original.count(site)!=1:raise ValueError('frozen G2 source no longer matches exact semantic patch site')
    adapter=original.replace(old_guard,guard).replace(old_output,new_output)
    duration=adapter.replace(load_site,"load_energy = tx_power * ctx['load_profile']['tx_duration_s'] / regulator_efficiency")
    complete=adapter.replace(load_site,"load_energy = (tx_power * ctx['load_profile']['tx_duration_s'] + sum(ctx['load_profile'][state + '_power_w'] * ctx['load_profile'][state + '_duration_s'] for state in ['boot', 'sense', 'infer'])) / regulator_efficiency")
    result=[]
    for id,code,title in [('interface-only',adapter,'Original G2 decisions; explicit interface adapter'),
                           ('tx-duration-only',duration,'Only replace release time with TX duration'),
                           ('complete-action-energy',complete,'Include explicit boot/sense/infer/TX energy')]:
        c={'schema_version':'world-model-patch-v1','kind':'world-model','scope':{'source_families':['rotary']},'code':code}
        result.append({'id':id,'title':title,'candidate':c,'candidate_hash':canonical_hash(c),
            'authorship':'engineer-authored diagnostic patch, not a model-generated G3/G4',
            'source_hash':canonical_hash(original),'diff_from_interface':''.join(difflib.unified_diff(adapter.splitlines(True),code.splitlines(True),fromfile='interface-only.py',tofile=id+'.py'))})
    return result

def diagnostic_context(task):
    ctx=public_context(task)
    # Explicit compatibility aliases; source law remains in ctx.source. There is
    # no observed voltage, feasibility, diagnosis label or evaluator output here.
    s=ctx['source'];ctx['conditions'].update(rpm=s['rpm'],nominal_source_peak_a=s['source_peak_a'],
        regulator_efficiency=ctx['conditions']['efficiency'],possible_source_surge=s['surge_multiplier']>1)
    return ctx

def selection_order(context, output=None):
    ids=[c['id'] for c in context['candidates']]
    if output is None:return ids
    errors=output_errors(output,context)
    if errors:raise ValueError('; '.join(errors))
    # An explicit per-candidate abstention does not prune a potentially feasible
    # design. Global out-of-scope also falls back to raw verification.
    if not output['scope_ok']:return ids
    return [cid for cid in ids if output['predictions'][cid]['verdict']!='infeasible']

def use_control(context,output,observations):
    if set(observations)!={c['id'] for c in context['candidates']}:
        raise ValueError('complete controller-owned observations required')
    actions=[];submitted=None
    for cid in selection_order(context,output):
        facts=observations[cid]
        actions.append({'action':'transient','candidate_id':cid,'run_hash':facts['run_hash'],'physical_pass':facts['physical_pass']})
        if facts['physical_pass']:
            submitted={'candidate_id':cid,'run_hash':facts['run_hash']};break
    return {'controller':'deterministic equal-order catalogue; not LLM baseline','probes':len(actions),
        'success':submitted is not None,'actions':actions,'submission':submitted,'false_admissions':0,
        'evidence_scope':'complete synthetic reference; no scientific qualification or hardware claim'}

def evaluate_variant(variant,tasks,observations,root):
    contexts=[diagnostic_context(t) for t in tasks]
    mechanical=compile_candidate(variant['candidate'],contexts[:1],root/'compiler')
    if not mechanical['passed']:
        return {**variant,'mechanical':mechanical,'evaluated':False}
    tests=[]
    for task,ctx in zip(tasks,contexts):
        output=sandbox_execute(variant['candidate']['code'],ctx,root/'original-session')
        # Fresh sandbox process, detached code + current public task only; no
        # original chat/history. This tests portability, not new Agent benefit.
        transplanted=sandbox_execute(variant['candidate']['code'],copy.deepcopy(ctx),root/'detached-session')
        errors=output_errors(output,ctx)
        if errors or transplanted!=output:raise ValueError('program portability/schema check failed')
        facts=observations[task['task_id']]
        rows=[]
        for c in ctx['candidates']:
            cid=c['id'];pred=output['predictions'][cid]['verdict'] if output['scope_ok'] else 'abstain'
            rows.append({'candidate_id':cid,'prediction':pred,'observed':facts[cid]['physical_pass'],
                'false_reject':pred=='infeasible' and facts[cid]['physical_pass'],
                'false_feasible_prediction':pred=='feasible' and not facts[cid]['physical_pass'],
                'run_hash':facts[cid]['run_hash']})
        raw=use_control(ctx,None,facts);used=use_control(ctx,output,facts)
        tests.append({'task_id':task['task_id'],'task_hash':task['content_hash'],'context_hash':canonical_hash(ctx),'rows':rows,
            'raw':raw,'program':used,'removed':use_control(ctx,None,facts),
            'detached':use_control(ctx,transplanted,facts),'detached_output_equal':True,
            'scope':'observed development / deterministic controls; not blind transfer'})
    return {**variant,'mechanical':mechanical,'evaluated':True,'tasks':tests,
        'false_rejects':sum(r['false_reject'] for t in tests for r in t['rows']),
        'false_feasible_predictions':sum(r['false_feasible_prediction'] for t in tests for r in t['rows']),
        'physical_successes':sum(t['program']['success'] for t in tests),'qualified':False,'promoted':False}
