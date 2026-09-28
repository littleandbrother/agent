"""Serial development pilots with predeclared cells and retained failures."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import time

from ..store import canonical, identity
from .core import implementation_binding, write_atomic
from . import catalog, evidence, scope, gates, paid


def setup(research):
    target = research.root/'setup.json'
    if target.exists():
        previous = json.loads(target.read_text())
        if previous['implementation'] != implementation_binding():
            raise ValueError('RESEARCH_SETUP_DRIFT_CREATE_NEW_STUDY')
        return previous
    inv = catalog.inventory(research)
    product = catalog.product_checkpoint(research)
    base = catalog.base_query(research, product)
    changes = catalog.b_changes(base)
    original_evidence = evidence.make_evidence(research, base)
    prototypes = {}
    for name, design in scope.cases().items():
        source = research.root/'inputs'/'A'/name
        for file, data in scope.artifacts(design).items():
            write_atomic(source/file, canonical(data).encode())
        baseline = scope.evaluate(design)
        state = dict(product_revision={'case': name, 'design_hash': identity(design)},
                     world_revision='coupled-programmed-reference-v3', harness_revision='scope-selector-v1',
                     requirements={'deadline_s': 1.1, 'max_voltage_v': 3.6, 'quality_min': .7},
                     assumptions=['Synthetic signal and hand-authored classifier; no measured mechanical or TinyML chain.',
                                  'Conflicts are injected independent constraints; physical coupling is not established.'],
                     public_context={'design': design, 'baseline_feedback': baseline}, evidence={}, split='development')
        prototypes[name] = research.checkpoint(source, list(scope.artifacts(design)), state, native_state='none')
    # A no-Agent passing reference and failing initial states are distinct facts.
    reference_design = {**scope.cases()['local-voltage'], 'clamp_v': 3.45}
    reference = scope.evaluate(reference_design)
    if not reference['checks']['value']:
        raise ValueError('RESEARCH_NO_AGENT_REFERENCE_FAILED')
    reference_key = research.put('reports', {'paper': 'A', 'kind': 'no-agent-reference',
        'design': reference_design, 'result': reference, 'status': 'PASS', 'claim': 'Computational apparatus only.'})
    # The B intervention changes query inputs only; the full product checkpoint is
    # referenced rather than copying large CAD archives into every evaluator cell.
    source = research.root/'inputs'/'B'
    write_atomic(source/'query.json', canonical(base).encode())
    cp = research.get('checkpoints', product)
    bstate = {**cp['state'], 'public_context': {'query': base, 'product_checkpoint': product},
              'evidence': {'old_evidence': original_evidence},
              'harness_revision': 'shared-operator-library-v1'}
    bcp = research.checkpoint(source, ['query.json'], bstate, native_state='none')
    aproto = catalog.protocol('A', list(prototypes), paid=True)
    aproto['checkpoints'] = prototypes
    aproto['pilot_scope'] = 'Injected circuit/classifier/schedule artifact constraints; not the physical co-design A study.'
    aproto['selector'] = 'Fixed heuristic closure, no learned-policy efficacy claim.'
    aproto['generator'] = 'Direct model completion through existing guarded provider proxy; not a Pi SDK session.'
    aproto['free_scope_baseline'] = 'One explicit model scope-selection call before the common repair generator; its cost counts toward the same three-call cap. Not an unrestricted coding agent.'
    bproto = catalog.protocol('B', list(changes))
    bproto['checkpoints'] = {unit: bcp for unit in changes}
    bproto['audit'] = 'Fresh subprocess fully recomputes after the method submits; never supplied as corrective feedback.'
    bproto['timing'] = 'Measured method/planning/recompute time; independent audit cost reported separately; no invented price for skipped checks.'
    bproto['baseline_gap'] = 'Free-LLM planner and wider operators are deferred until these classical controls establish a useful task.'
    cproto = catalog.protocol('C', [f'gate-{i:02}' for i in range(12)])
    cproto['pilot_scope'] = 'Organic-rule discovery. Cells remain blocked until eligible gate-before observations exist.'
    value = dict(implementation=implementation_binding(), inventory=inv, product_checkpoint=product,
                 A={'protocol': research.register(aproto), 'checkpoints': prototypes, 'reference': reference_key},
                 B={'protocol': research.register(bproto), 'checkpoint': bcp, 'evidence': original_evidence, 'changes': changes},
                 C={'protocol': research.register(cproto)})
    write_atomic(target, canonical(value).encode())
    research.event('study_prepared', {'setup_hash': identity(value), 'papers': ['A', 'B', 'C']})
    return value


def read_setup(research):
    value = json.loads((research.root/'setup.json').read_text())
    if value['implementation'] != implementation_binding():
        raise ValueError('RESEARCH_IMPLEMENTATION_DRIFT')
    for paper in ['A', 'B', 'C']:
        research.get('protocols', value[paper]['protocol'])
    return value


def audit_subprocess(kind, source, timeout=120):
    started = time.perf_counter()
    result = subprocess.run([sys.executable, '-m', 'bfworld.agentlab.research.cli', 'audit-'+kind,
                             '--input', str(source)], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('RESEARCH_INDEPENDENT_AUDIT_FAILED:'+result.stderr[-1000:])
    return json.loads(result.stdout), time.perf_counter()-started


def done(research, trial):
    return (research.root/'trials'/trial/'result.json').exists()


def run_b(research):
    config = read_setup(research)['B']
    p = research.get('protocols', config['protocol'])
    cells = [(u, a) for u in p['units'] for a in p['arms']]
    random.Random(p['randomization_seed']).shuffle(cells)
    for unit, arm in cells:
        trial = research.branch(config['protocol'], config['checkpoint'], arm, unit, 1)
        if done(research, trial):
            continue
        try:
            research.check_trial(trial)
            root = research.root/'trials'/trial
            query = config['changes'][unit]
            write_atomic(root/'workspace/query.json', canonical(query).encode())
            result = evidence.plan(research, config['evidence'], query, arm)
            write_atomic(root/'method-submission.json', canonical(result).encode())
            # Audit is only evaluated after submission, outside the method.
            truth, audit_s = audit_subprocess('energy', root/'workspace/query.json')
            support_ok = all(evidence.check_support(research, key) for key in result['supports'].values())
            disagreements = [prop for prop in evidence.PROPERTIES if result['results'][prop]['verdict'] != truth[prop]['verdict']]
            false_accepts = [prop for prop in disagreements if result['results'][prop]['verdict'] == 'PASS']
            audit = {'schema_version': 'bf-research-audit-v1', 'trial': trial, 'query_hash': identity(query),
                     'submission_hash': identity(result), 'truth': truth, 'audit_s': audit_s,
                     'disagreements': disagreements, 'false_accepts': false_accepts, 'supports_checked': support_ok,
                     'verifier_revision': evidence.verifier_revision(), 'hardware_verified': False}
            audit_key = research.put('audits', audit)
            research.finish(trial, 'PASS' if not disagreements and support_ok else 'FAIL',
                            {'method': result, 'audit': audit_key, 'audit_s': audit_s,
                             'meaning': 'PASS means computational decision/support audit agreed; not product PASS.'})
        except Exception as exc:
            if not done(research, trial):
                research.finish(trial, 'INFRA_ERROR', {'error': str(exc), 'type': type(exc).__name__})
        print(canonical({'paper': 'B', 'unit': unit, 'arm': arm, 'trial': trial}), flush=True)
    rows = [r for r in research.trials() if r.get('protocol') == config['protocol']]
    summary = []
    for arm in p['arms']:
        own = [r for r in rows if r['arm'] == arm]
        methods = [r['result']['method'] for r in own if 'method' in r['result']]
        summary.append({'arm': arm, 'attempted': len(own), 'audit_agreed': sum(r['status'] == 'PASS' for r in own),
                        'model_executions': sum(x['full_model_executions'] for x in methods),
                        'supported_properties': sum(len(x['supports']) for x in methods),
                        'planning_s': sum(x['planning_s'] for x in methods),
                        'method_total_s': sum(x['total_s'] for x in methods),
                        'audit_s': sum(r['result'].get('audit_s', 0) for r in own),
                        'unknown_predicates': sum(v['verdict'] == 'UNKNOWN' for x in methods for v in x['results'].values())})
    report = {'paper': 'B', 'kind': 'fixed-change-pilot', 'protocol': config['protocol'],
              'status': 'COMPLETED' if len(rows) == len(cells) and all(r['status'] in {'PASS', 'FAIL'} for r in rows) else 'INCOMPLETE',
              'summary': summary, 'paired_units': len(p['units']), 'provider_calls': 0,
              'claim': 'Fixed changes of an actual product energy specification; conditional computational checks only.',
              'limitations': ['Single pass per arm/change is a timing pilot, not statistical efficacy.',
                             'Strong dependency cache is retained. Transfer can preserve predicates without eliminating a full transient run.',
                             'No calibrated bounds or hardware evidence; no free-LLM planner comparison yet.']}
    return research.put('reports', report)


def run_a(research, port=8768):
    config = read_setup(research)['A']
    p = research.get('protocols', config['protocol'])
    if not research.get('reports', config['reference'])['result']['checks']['value']:
        raise ValueError('RESEARCH_REFERENCE_NOT_SEALED')
    cells = [(u, a, r) for u in p['units'] for a in p['arms'] for r in range(1, p['repetitions']+1)]
    random.Random(p['randomization_seed']).shuffle(cells)
    for unit, arm, repeat in cells:
        trial = research.branch(config['protocol'], config['checkpoints'][unit], arm, unit, repeat)
        if done(research, trial):
            continue
        history = []
        try:
            research.check_trial(trial)
            root = research.root/'trials'/trial
            current = scope.read_design(root/'workspace')
            feedback = scope.evaluate(current)
            selected_scope = None
            if arm == 'free-scope':
                output = paid.complete(research, trial, scope.selection_prompt(current, feedback), port)
                selected_scope = json.loads(output)
                if not isinstance(selected_scope, list) or not selected_scope or len(set(selected_scope)) != len(selected_scope) or set(selected_scope)-set(scope.SCOPES):
                    raise ValueError('SCOPE_SELECTION_INVALID')
                research.event('model_scope_selected', {'trial': trial, 'allowed': selected_scope, 'observation_hash': identity(feedback)})
            for step in range(p['budget']['model_calls_per_trial']-(1 if selected_scope else 0)):
                if feedback['checks']['value']:
                    break
                allowed = selected_scope or scope.scope_for(arm, feedback)
                research.event('scope_selected', {'trial': trial, 'step': step, 'allowed': allowed,
                                                  'observation_hash': identity(feedback)})
                output = paid.complete(research, trial, scope.prompt(current, feedback, allowed, history), port)
                try:
                    patch = json.loads(output)
                    edits = scope.apply_patch(root/'workspace', patch, allowed)
                    current = scope.read_design(root/'workspace')
                    feedback = scope.evaluate(current)
                    history.append({'step': step, 'allowed': allowed, 'patch': patch, 'edits': edits, 'feedback': feedback})
                except (ValueError, TypeError, KeyError) as exc:
                    history.append({'step': step, 'allowed': allowed, 'error': str(exc), 'output': output})
                write_atomic(root/'steps.json', canonical(history).encode())
            write_atomic(root/'final-design.json', canonical(current).encode())
            verified, audit_s = audit_subprocess('scope', root/'final-design.json')
            audit = research.put('audits', {'trial': trial, 'design_hash': identity(current), 'result': verified,
                                          'audit_s': audit_s, 'independent_process': True})
            usage = paid.metrics(research, trial)
            research.finish(trial, 'PASS' if verified['checks']['value'] else 'FAIL',
                            {'audit': audit, 'feedback': verified, 'history': history,
                             'fidelity': 'synthetic computational artifact-scope pilot; no physical coupling claim'},
                            cost_usd=usage['cost_usd'], model_calls=usage['calls'])
        except Exception as exc:
            usage = paid.metrics(research, trial)
            if not done(research, trial):
                research.finish(trial, 'UNKNOWN' if usage['unknown'] else 'FAIL' if isinstance(exc, json.JSONDecodeError) or str(exc)=='SCOPE_SELECTION_INVALID' else 'BLOCKED' if any(k in str(exc) for k in ['BUDGET', 'CAP', 'AUTHORIZED', 'EXPIRED', 'WINDOW']) else 'INFRA_ERROR',
                                {'error': str(exc), 'type': type(exc).__name__, 'history': history},
                                cost_usd=usage['cost_usd'], model_calls=usage['calls'])
        print(canonical({'paper': 'A', 'unit': unit, 'arm': arm, 'repeat': repeat, 'trial': trial}), flush=True)
    rows = [r for r in research.trials() if r.get('protocol') == config['protocol']]
    report = {'paper': 'A', 'kind': 'scope-pilot', 'protocol': config['protocol'],
              'status': 'COMPLETED' if len(rows) == len(cells) and all(r['status'] in {'PASS', 'FAIL'} for r in rows) else 'INCOMPLETE',
              'summary': [{'arm': a, 'attempted': sum(r['arm'] == a for r in rows),
                           'passed': sum(r['arm'] == a and r['status'] == 'PASS' for r in rows),
                           'cost_upper_usd': sum(r.get('cost_upper_usd') or 0 for r in rows if r['arm'] == a),
                           'model_calls': sum(r.get('model_calls') or 0 for r in rows if r['arm'] == a)} for a in p['arms']],
              'limitations': ['Injected independent conflicts; not evidence for physical interaction.',
                             'Heuristic closure is not learned repair granularity.',
                             'Direct model patch generator, not Pi SDK or unrestricted coding.',
                             'Provider reports alias only; immutable model weights cannot be pinned.',
                             'Four starting states, correlated repetitions; no confirmatory generalization.']}
    return research.put('reports', report)


def run_c(research):
    config = read_setup(research)['C']
    audit_key = gates.audit_history(research)
    report = research.get('reports', audit_key)
    # Do not invent 12 organic cases from source-code text. The matrix remains
    # declared but unlaunched and is displayed as not eligible.
    return research.put('reports', {'paper': 'C', 'kind': 'pilot-readiness', 'protocol': config['protocol'],
        'status': 'BLOCKED_ORGANIC_EVIDENCE', 'audit': audit_key, 'eligible_pairs': report['eligible_pairs'],
        'launched_cells': 0, 'planned_cells': 48, 'provider_calls': 0,
        'reason': 'Existing histories have autonomous code edits but no bound candidate-before-gate observations.',
        'next': 'Collect 3–5 real learned rules with explicit proposals and loaded identities; select eligible paired states before paid exposure.'})
