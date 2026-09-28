"""Mechanical preflight only: no scientific truth, qualification or provider access.

AST checks are defense in depth; all execution still uses the OS sandbox.
An all-abstain program may compile, but earns no scientific qualification.
"""
from __future__ import annotations

import ast
import math
import re
from pathlib import Path

from bfworld.kernel.canonical import canonical_hash, file_hash
from .sandbox import execute

VERSION = 'candidate-compiler-v1'
BUILTINS = {'abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'float', 'int',
            'isinstance', 'len', 'list', 'max', 'min', 'range', 'round', 'set',
            'sorted', 'str', 'sum', 'tuple', 'zip'}
METHODS = {'get', 'items', 'keys', 'values', 'append', 'extend', 'copy', 'sort'}
MATH = {n for n in dir(math) if not n.startswith('_')}


def context_errors(ctx):
    errors = []
    if not isinstance(ctx, dict):
        return ['context must be an object']
    if not isinstance(ctx.get('source_family'), str):
        errors.append('source_family must be a string')
    conditions = ctx.get('conditions')
    if not isinstance(conditions, dict):
        errors.append('conditions must be an object')
    else:
        for field in ('initial_v', 'off_v', 'duration_s'):
            value = conditions.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                errors.append(f'conditions.{field} must be finite and positive')
    candidates = ctx.get('candidates')
    if not isinstance(candidates, list) or not candidates:
        errors.append('candidates must be a nonempty list')
    else:
        ids = []
        for c in candidates:
            if not isinstance(c, dict) or not isinstance(c.get('id'), str):
                errors.append('candidate identity required')
                continue
            ids.append(c['id'])
            for field in ('capacitance_f', 'esr_ohm', 'tx_power_w', 'start_v'):
                value = c.get(field)
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    errors.append(f'candidate.{field} must be finite and nonnegative')
            if c.get('capacitance_f', 0) == 0:
                errors.append('candidate capacitance must be positive')
        if len(ids) != len(set(ids)):
            errors.append('duplicate candidate identities')
    return errors


def static_errors(code):
    if not isinstance(code, str) or not code.strip():
        return [{'code': 'missing_program', 'message': 'nonempty Python code required'}]
    if len(code.encode()) > 24000:
        return [{'code': 'program_size', 'message': 'code exceeds 24000 bytes'}]
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return [{'code': 'syntax', 'line': getattr(exc, 'lineno', None), 'message': str(exc).split(' (<unknown>')[0]}]
    errors = []
    def issue(node, msg):
        errors.append({'code': 'ast_policy', 'line': getattr(node, 'lineno', None), 'message': msg})
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    plans = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'plan']
    if len(plans) != 1:
        errors.append({'code': 'signature', 'message': 'exactly one top-level plan(ctx) required'})
    elif (len(plans[0].args.args) != 1 or plans[0].args.args[0].arg != 'ctx'
          or plans[0].args.posonlyargs or plans[0].args.kwonlyargs or plans[0].args.vararg
          or plans[0].args.kwarg or plans[0].args.defaults):
        errors.append({'code': 'signature', 'message': 'plan must accept exactly one positional ctx argument'})
    aliases = {'math'}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name != 'math':
                    issue(node, 'only math imports allowed')
                aliases.add(item.asname or item.name)
        if isinstance(node, ast.ImportFrom):
            if node.module != 'math' or node.level:
                issue(node, 'only math imports allowed')
            for item in node.names:
                if item.name not in MATH:
                    issue(node, 'unknown math import')
                imported.add(item.asname or item.name)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Assign):
            try:
                ast.literal_eval(node.value)
                continue
            except (ValueError, TypeError):
                pass
        issue(node, 'top-level execution is not permitted')
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.With, ast.AsyncWith,
                             ast.Global, ast.Nonlocal, ast.Delete, ast.Lambda)):
            issue(node, 'unsupported executable construct')
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.returns
                or any(arg.annotation for arg in node.args.args)):
            issue(node, 'decorators and executable annotations are not permitted')
        if isinstance(node, ast.Name) and node.id.startswith('__'):
            issue(node, 'dunder access denied')
        if isinstance(node, ast.Attribute):
            allowed = node.attr in METHODS or (isinstance(node.value, ast.Name)
                        and node.value.id in aliases and node.attr in MATH)
            if not allowed:
                issue(node, 'attribute not in pure computation allowlist: ' + node.attr)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id not in BUILTINS | functions | imported:
                issue(node, 'call not in pure computation allowlist: ' + node.func.id)
            elif not isinstance(node.func, (ast.Name, ast.Attribute)):
                issue(node, 'dynamic calls denied')
    return errors


def output_errors(output, ctx, must_abstain=False):
    if not isinstance(output, dict) or set(output) != {'scope_ok', 'predictions'}:
        return ['output must contain exactly scope_ok and predictions']
    if type(output['scope_ok']) is not bool or not isinstance(output['predictions'], dict):
        return ['scope_ok must be boolean; predictions must be object']
    if must_abstain or output['scope_ok'] is False:
        return [] if output == {'scope_ok': False, 'predictions': {}} else ['invalid/domain input requires explicit abstention and empty predictions']
    expected = {c['id'] for c in ctx['candidates']}
    if set(output['predictions']) != expected:
        return ['in-scope predictions must cover each candidate exactly once']
    errors = []
    for cid, pred in output['predictions'].items():
        if not isinstance(pred, dict) or pred.get('verdict') not in {'feasible', 'infeasible', 'abstain'}:
            errors.append(cid + ': verdict must be feasible/infeasible/abstain')
        elif set(pred) - {'verdict', 'minimum_input_v', 'reason'}:
            errors.append(cid + ': unexpected prediction fields')
        elif 'minimum_input_v' in pred and (type(pred['minimum_input_v']) not in (int, float)
                or not math.isfinite(pred['minimum_input_v'])):
            errors.append(cid + ': finite voltage required')
        elif 'reason' in pred and not isinstance(pred['reason'], str):
            errors.append(cid + ': reason must be string')
    return errors


def compile_candidate(candidate, contexts, sandbox: Path):
    """Contexts are public mechanical fixtures, never qualification/blind truth."""
    errors = []
    if not isinstance(candidate, dict):
        candidate = {'invalid_envelope': str(type(candidate).__name__)}
    scope = candidate.get('scope', {})
    if (candidate.get('kind') != 'world-model' or candidate.get('schema_version') != 'world-model-patch-v1'
            or not isinstance(scope, dict) or not isinstance(scope.get('source_families'), list)
            or not scope['source_families'] or any(not isinstance(x, str) for x in scope['source_families'])):
        errors.append({'code': 'envelope', 'message': 'world-model-patch-v1 requires kind world-model and explicit source_families scope'})
    errors.extend(static_errors(candidate.get('code')))
    if not contexts or any(context_errors(ctx) for ctx in contexts):
        errors.append({'code': 'fixture', 'message': 'valid, nonempty public mechanical fixtures required'})
    checks = []
    if not errors:
        # JSON roundtrip avoids participant mutation of the fixture object.
        import copy
        cases = [('valid-' + str(i), copy.deepcopy(ctx), False) for i, ctx in enumerate(contexts)]
        domain = copy.deepcopy(contexts[0]); domain['source_family'] = '__outside_declared_domain__'
        cases += [('out-of-scope', domain, True), ('missing-input', {}, True),
                  ('null-input', None, True), ('malformed-conditions', {'source_family': 'rotary', 'conditions': None, 'candidates': []}, True)]
        for name, ctx, abstain in cases:
            try:
                result = execute(candidate['code'], ctx, sandbox)
                expected_abstain = abstain or ctx['source_family'] not in scope['source_families']
                problems = output_errors(result, ctx, expected_abstain)
                checks.append({'case': name, 'passed': not problems, 'errors': problems, 'output': result})
            except Exception as exc:
                # No host paths or unbounded stderr become repair instructions.
                message = re.sub(r'File "[^"]+"', 'File "participant.py"', str(exc))[-500:]
                checks.append({'case': name, 'passed': False, 'errors': [message]})
        if not all(c['passed'] for c in checks):
            errors.append({'code': 'smoke_or_schema', 'message': 'mechanical fixture failed; inspect case errors'})
    report = {'schema_version': VERSION, 'compiler_hash':file_hash(Path(__file__)), 'candidate_hash': canonical_hash(candidate),
              'fixtures_hash': canonical_hash(contexts), 'passed': not errors, 'errors': errors,
              'checks': checks, 'scientific_qualification': 'not-evaluated', 'scientific_probes': 0}
    report['content_hash'] = canonical_hash(report)
    return report
