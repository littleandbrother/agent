"""Provider-backed matched trials, with explicit protocol and recovery authority.

v1 scripted controls remain unchanged. This v2 runner uses original Provider/
Ledger settlement, immutable local effects and a post-trial final barrier.
Provider-control fixtures use the same path but can never become Agent results.
"""
from __future__ import annotations
import copy
import json
import math
import time
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash, file_hash
from bfworld.coupled.profiled_artifacts import seal_run, verify_bundle
from .budget import BudgetStop
from .provider import Provider, MODEL
from .repair import checked, seal, cpu_seconds
from .repair_bridge import ProviderRepairAdapter, exclusive, request_body
from .compiler import compile_candidate, output_errors
from .sandbox import execute as run_python
from .scientific import component_receipt
from .splits import launch_readiness, validate_registry
from .task_context import public_context, execute_candidate
from .trials import ARMS, TOOLS, SYSTEM, _history, _effect, observation

VERSION = 'matched-provider-trials-v2'


def implementation():
    here = Path(__file__)
    paths = [here.with_name(n) for n in ('live_trials.py', 'trials.py', 'repair_bridge.py',
             'repair.py', 'compiler.py', 'sandbox.py', 'provider.py', 'budget.py',
             'scientific.py', 'qualification.py', 'task_context.py', 'splits.py')]
    paths += [here.parents[1]/'coupled'/n for n in ('engine.py', 'profiled.py', 'profiled_artifacts.py')]
    return {str(p.relative_to(here.parents[1])): file_hash(p) for p in paths}


def execution_pins(plan, tasks, history, capsule, qualification):
    return {'plan_hash': canonical_hash(plan), 'task_manifest_hash': canonical_hash(tasks),
            'history_hash': history['content_hash'], 'capsule_hash': canonical_hash(capsule),
            'qualification_hash': qualification['content_hash'], 'implementation': implementation()}


def window_check(protocol, *, dispatch):
    window = protocol['shared_budget'].get('new_campaign_execution_window')
    if (not isinstance(window, dict) or set(window) != {'starts_unix_s', 'ends_unix_s'}
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in window.values())):
        raise BudgetStop('explicit finite approved execution window required')
    start, end = window['starts_unix_s'], window['ends_unix_s']
    if not 0 < end-start <= 3600 or (dispatch and not start <= time.time() < end):
        raise BudgetStop('approved trial execution window expired')


def validate(plan, tasks, history, capsule, qualification, protocol, *, dispatch=False):
    if not launch_readiness(protocol)['ready']:
        raise BudgetStop('matched trials require exact owner-approved protocol')
    if plan.get('schema_version') != VERSION or plan.get('purpose') not in {'provider-controls', 'formal-agent-trial'}:
        raise BudgetStop('explicit provider-control or formal trial plan required')
    if plan.get('arms') != ARMS or plan.get('tools') != TOOLS or plan.get('candidate_order_rule') != 'stable-capacitance-ascending':
        raise BudgetStop('matched arms, tools and ordering must be fixed')
    if (type(plan.get('max_turns')) is not int or not 2 <= plan['max_turns'] <= 32
            or type(plan.get('max_experiments')) is not int or not 1 <= plan['max_experiments'] < plan['max_turns']):
        raise BudgetStop('bounded complete trial/experiment budgets required')
    if not isinstance(plan.get('session_namespace'), str) or not plan['session_namespace'].strip():
        raise BudgetStop('stable trial namespace required')
    _history(history); checked(qualification)
    exposed = [r['environment_hash'] for r in history['records']]
    validate_registry(tasks, exposed)
    if len(tasks) != 2 or plan.get('task_id') != tasks[0]['task_id'] or plan.get('confirmation_id') != tasks[1]['task_id']:
        raise BudgetStop('exact public task and separate final confirmation required')
    contexts = [public_context(t) for t in tasks]
    if contexts[0]['candidates'] != contexts[1]['candidates'] or len(contexts[0]['candidates']) > plan['max_experiments']:
        raise BudgetStop('same designs and sufficient exhaustive-reference budget required')
    if any(t['environment_hash'] in exposed for t in tasks):
        raise BudgetStop('trial or confirmation duplicates historical physics')
    required_split = 'blind-transfer' if plan['purpose'] == 'formal-agent-trial' else 'development'
    if any(t['split'] != required_split for t in tasks):
        raise BudgetStop('task roles do not match declared execution purpose')
    if capsule.get('history_hash') != history['content_hash'] or not isinstance(capsule.get('text_lesson'), str) or not capsule['text_lesson'].strip():
        raise BudgetStop('same nonempty source history and text lesson required')
    if qualification['candidate_hash'] != canonical_hash(capsule['candidate']):
        raise BudgetStop('qualified treatment belongs to a different candidate')
    qualified = component_receipt(qualification, capsule['candidate'])
    if plan['purpose'] == 'formal-agent-trial':
        if not qualified['passed'] or qualification['purpose'] != 'formal-qualification':
            raise BudgetStop('formal qualified arm requires independent scientific qualification')
    elif qualification.get('purpose') != 'engineering-controls' or not qualification.get('controls_pass'):
        raise BudgetStop('provider control requires a passing explicitly engineering qualification control')
    shared = protocol['shared_budget']; spec = protocol.get('matched_trial_execution') or {}
    if (protocol.get('model_identity') != MODEL or shared.get('ledger') != '.bfworld/paid-campaign/cost.sqlite'
            or shared.get('user_trial_cny') != 2 or shared.get('user_total_strictly_less_than_cny') != 20
            or shared.get('reset_or_extension_authorized') is not False):
        raise BudgetStop('retain exact model and original shared ledger/caps')
    pins = execution_pins(plan, tasks, history, capsule, qualification)
    if any(spec.get(k) != v for k, v in pins.items()) or protocol.get('task_manifest_hash') != pins['task_manifest_hash']:
        raise BudgetStop('trial plan/history/capsule/qualification/implementation pins mismatch')
    fp = spec.get('model_fingerprint')
    if not isinstance(fp, str) or not fp.strip() or fp == 'unavailable':
        raise BudgetStop('exact model fingerprint required')
    window_check(protocol, dispatch=dispatch)
    return {**pins, 'protocol_hash': canonical_hash(protocol), 'model_fingerprint': fp}


class DecisionAdapter(ProviderRepairAdapter):
    """One immutable slot per turn; every response rechecked against SQLite."""
    def __init__(self, protocol, repo, plan, tasks, history, capsule, qualification,
                 provider, root, arm, initial_messages, *, fault=None, reconcile_only=False):
        self.plan, self.tasks, self.history = plan, tasks, history
        self.capsule, self.qualification = capsule, qualification
        self.arm, self.initial_messages = arm, copy.deepcopy(initial_messages)
        self.reconcile_only = reconcile_only
        self.pins = validate(plan, tasks, history, capsule, qualification, protocol)
        if arm not in ARMS[:-1]:
            raise BudgetStop('oracle is not a provider participant')
        actual = type(provider) is Provider
        if actual != (plan['purpose'] == 'formal-agent-trial') and not reconcile_only:
            raise BudgetStop('real provider and fixture purpose cannot be relabeled')
        self.transport_kind = 'real-provider' if plan['purpose'] == 'formal-agent-trial' else 'isolated-fake-transport'
        super().__init__(protocol, repo, self.pins, [public_context(tasks[0])], provider, root,
                         plan['session_namespace']+'/'+arm, fault=fault)

    def _authorize(self):
        if self.reconcile_only:
            raise BudgetStop('read-only reconciliation cannot dispatch an absent decision')
        if self.ledger.db.execute('SELECT COUNT(*) FROM calls WHERE state != ?', ('settled',)).fetchone()[0]:
            raise BudgetStop('shared ledger has an uncertain prior call; no new dispatch')
        return validate(self.plan, self.tasks, self.history, self.capsule, self.qualification, self.protocol, dispatch=True)

    def _expected_fingerprint(self):
        return self.pins['model_fingerprint']

    def _transaction(self, request):
        if set(request) != {'session_id', 'turn', 'messages', 'tools', 'turns_remaining', 'experiments_remaining'}:
            raise BudgetStop('exact decision request fields required')
        n = request['turn']; messages = request['messages']
        if (type(n) is not int or not 0 <= n < self.plan['max_turns'] or request['session_id'] != self.trial_id
                or request['tools'] != TOOLS or request['turns_remaining'] != self.plan['max_turns']-n
                or type(request['experiments_remaining']) is not int
                or not 0 <= request['experiments_remaining'] <= self.plan['max_experiments']):
            raise BudgetStop('decision identity or budget drift')
        if not isinstance(messages, list) or len(messages) != 2+2*n or messages[:2] != self.initial_messages:
            raise BudgetStop('participant transcript initial state changed')
        if n:
            previous = checked(json.loads((self.root.parent/f'decision-{n-1}.json').read_text()))['value']
            effect = checked(json.loads((self.root.parent/f'effect-{n-1}.json').read_text()))['value']
            slot = checked(json.loads((self.root/'slots'/f'{n-1}.json').read_text()))
            expected = slot['request']['messages'] + [
                {'role': 'assistant', 'content': json.dumps(previous['candidate'], sort_keys=True)},
                {'role': 'user', 'content': json.dumps({'tool_result': effect['facts']}, sort_keys=True)}]
            if messages != expected or request['experiments_remaining'] != self.plan['max_experiments']-effect['counters']['experiments']:
                raise BudgetStop('decision transcript differs from completed local effects')
        elif request['experiments_remaining'] != self.plan['max_experiments']:
            raise BudgetStop('initial experiment budget changed')
        # Budget is visible to the model, not merely controller-side metadata.
        body_messages = messages + [{'role': 'user', 'content': json.dumps({
            'remaining_turns_including_this_one': request['turns_remaining'],
            'remaining_experiments': request['experiments_remaining'], 'allowed_actions': TOOLS}, sort_keys=True)}]
        binding = {'adapter_version': 'provider-decision-bridge-v1', 'pins': self.pins,
                   'trial_id': self.trial_id, 'turn': n, 'request_hash': canonical_hash(request),
                   'request_body_hash': canonical_hash(request_body(body_messages)), 'transport_kind': self.transport_kind}
        key = 'b2-decision:'+canonical_hash(binding).split(':')[1]
        return self.root/key.split(':')[1], key, binding, body_messages

    def __call__(self, request):
        self._transaction(request)
        with exclusive(self.root/'slots'):
            path = self.root/'slots'/f'{request["turn"]}.json'
            seal(path, {'request': request})
            return super().__call__(request)

    def _response(self, root, key, binding, row):
        response = super()._response(root, key, binding, row)
        if response is not None:
            response['proposer'] = 'trial decision, not scientific qualification'
            response['transport_kind'] = self.transport_kind
        return response


def checkpoint(root, name, inputs, compute, *, recover=None, fault=None, allow_compute=True):
    """Complete local effect is reusable; unknown local effect is not rerun."""
    path = root/(name+'.json'); binding = canonical_hash(inputs)
    if path.exists():
        old = checked(json.loads(path.read_text()))
        if old['input_hash'] != binding:
            raise ValueError('local effect input changed: '+name)
        return old
    start_path = root/(name+'-started.json')
    if start_path.exists():
        old = checked(json.loads(start_path.read_text()))
        if old['input_hash'] != binding:
            raise ValueError('interrupted local effect identity changed')
        value = recover() if recover else None
        if value is None:
            raise BudgetStop('unresolved local effect; no automatic replay: '+name)
        return seal(path, {'input_hash': binding, 'value': value, 'local_cost_complete': False,
                           'cost': {'wall_s': None, 'cpu_s': None}, 'recovery': 'settled receipt; local interval unknown'})
    if not allow_compute:
        raise BudgetStop('read-only reconciliation cannot start new local effect: '+name)
    root.mkdir(parents=True, exist_ok=True)
    seal(start_path, {'input_hash': binding, 'unix_s': time.time()})
    start, cpu = time.perf_counter(), cpu_seconds()
    value = compute()
    if fault:
        fault(name+'-computed')
    return seal(path, {'input_hash': binding, 'value': value, 'local_cost_complete': True,
                       'cost': {'wall_s': time.perf_counter()-start, 'cpu_s': cpu_seconds()-cpu}, 'recovery': None})


def _initial_context(task, history, capsule, arm, root, fault, allow_compute, before_compute):
    ctx = public_context(task); ctx['candidates'] = sorted(ctx['candidates'], key=lambda c: c['capacitance_f'])
    context = {'task': ctx, 'raw_history': history['records'], 'lesson': capsule['text_lesson'] if arm == 'text-lesson' else None,
               'knowledge': None, 'observations': []}
    treatment = {'program_invocations': 0, 'candidate_hash': None}
    costs = []
    if arm in {'unqualified-executable', 'qualified-executable'}:
        def invoke():
            before_compute()
            out = run_python(capsule['candidate']['code'], ctx, root/'sandbox')
            if output_errors(out, ctx):
                raise BudgetStop('knowledge treatment output invalid')
            return out
        receipt = checkpoint(root, 'treatment', {'candidate': capsule['candidate'], 'context': ctx}, invoke,
                             fault=fault, allow_compute=allow_compute)
        output = receipt['value']; costs.append(receipt)
        context['knowledge'] = {'candidate': capsule['candidate'], 'output': output,
                                'status': 'qualified' if arm == 'qualified-executable' else 'unqualified'}
        treatment = {'program_invocations': 1, 'candidate_hash': canonical_hash(capsule['candidate']),
                     'input_hash': canonical_hash(ctx), 'output_hash': canonical_hash(output),
                     'scope_ok': output['scope_ok'], 'non_abstain_predictions': sum(p['verdict'] != 'abstain' for p in output['predictions'].values())}
    return context, treatment, costs


def run_matrix(plan, tasks, history, capsule, qualification, protocol, repo, provider, root, *, fault=None, reconcile_only=False):
    pins = validate(plan, tasks, history, capsule, qualification, protocol)
    root = Path(root)
    with exclusive(root):
        identity = {**pins, 'purpose': plan['purpose']}
        seal(root/'identity.json', identity)
        seal(root/'inputs.json', {'plan': plan, 'tasks': tasks, 'history': history, 'capsule': capsule,
                                 'qualification': qualification, 'protocol': protocol})
        costs, trials, adapters = [], [], {}
        def allowed():
            if not reconcile_only:
                window_check(protocol, dispatch=True)
            return not reconcile_only
        def compile_now():
            allowed()
            return compile_candidate(capsule['candidate'], [public_context(tasks[0])], root/'sandbox')
        mechanical = checkpoint(root, 'mechanical', {'candidate': capsule['candidate'], 'context': public_context(tasks[0])},
             compile_now,
             fault=fault, allow_compute=not reconcile_only)
        costs.append(mechanical)
        if not mechanical['value']['passed']:
            raise BudgetStop('mechanical rejection before provider trials')
        for arm in plan['arms']:
            directory = root/arm; directory.mkdir(parents=True, exist_ok=True)
            context, treatment, extra = _initial_context(tasks[0], history, capsule, arm, directory, fault, not reconcile_only, allowed)
            costs.extend(extra)
            if plan['purpose'] == 'provider-controls' and context['knowledge']:
                context['knowledge']['status'] = 'engineering-interface-only' if arm == 'qualified-executable' else 'unqualified'
            messages = [{'role': 'system', 'content': SYSTEM},
                        {'role': 'user', 'content': json.dumps(context, ensure_ascii=False, sort_keys=True)}]
            initial_messages = copy.deepcopy(messages)
            adapter = None
            if arm != 'exhaustive-reference':
                adapter = DecisionAdapter(protocol, repo, plan, tasks, history, capsule, qualification, provider,
                                          directory/'provider', arm, messages, reconcile_only=reconcile_only)
                adapters[arm] = adapter
            counters = {'experiments': 0, 'python_calls': 0, 'decision_calls': 0}
            completed, steps, submission = [], [], None
            for turn in range(plan['max_turns']):
                request = {'session_id': plan['session_namespace']+'/'+arm, 'turn': turn, 'messages': copy.deepcopy(messages),
                           'tools': TOOLS, 'turns_remaining': plan['max_turns']-turn,
                           'experiments_remaining': plan['max_experiments']-counters['experiments']}
                if adapter:
                    decision = checkpoint(directory, f'decision-{turn}', request, lambda: adapter(request),
                        recover=lambda: adapter.reconcile(request), fault=fault, allow_compute=not reconcile_only)
                    # Reconcile even a cached complete decision against the original ledger.
                    if adapter.reconcile(request) != decision['value']:
                        raise BudgetStop('decision receipt changed from actual settlement')
                    action = decision['value']['candidate']; counters['decision_calls'] += 1
                    costs.append(decision)
                else:
                    good = next((e for e in completed if e['physical_pass']), None)
                    if good:
                        action = {'action': 'submit', 'candidate_id': good['candidate_id'], 'claim_pass': True, 'evidence_hash': good['content_hash']}
                    elif counters['experiments'] < len(context['task']['candidates']):
                        action = {'action': 'experiment', 'candidate_id': context['task']['candidates'][counters['experiments']]['id'], 'predicted_pass': False}
                    else:
                        action = {'action': 'abstain', 'reason': 'catalogue exhausted'}
                    decision = None
                if not isinstance(action, dict):
                    action = {'action': 'invalid'}
                before = {'action': action, 'context': context, 'completed': completed, 'counters': counters}
                def perform():
                    allowed()
                    current, counts = copy.deepcopy(completed), copy.deepcopy(counters)
                    facts, sub = _effect(tasks[0], action, context, current, directory, counts, plan['max_experiments'])
                    return {'facts': facts, 'submission': sub, 'completed': current, 'counters': counts}
                effect = checkpoint(directory, f'effect-{turn}', before, perform, fault=fault, allow_compute=not reconcile_only)
                costs.append(effect); value = effect['value']
                _audit_effect(tasks[0], action, before, value, directory, plan['max_experiments'])
                completed, counters, submission = value['completed'], value['counters'], value['submission']
                _audit_experiments(tasks[0], completed, directory)
                facts = value['facts']; context['observations'].append(facts)
                steps.append({'turn': turn, 'request_hash': canonical_hash(request), 'action': action, 'facts': facts,
                              'decision_hash': decision['content_hash'] if decision else None, 'effect_hash': effect['content_hash']})
                messages.extend([{'role': 'assistant', 'content': json.dumps(action, sort_keys=True)},
                                 {'role': 'user', 'content': json.dumps({'tool_result': facts}, sort_keys=True)}])
                if submission is not None:
                    break
            trial = seal(directory/'trial.json', {'arm': arm, 'session_id': plan['session_namespace']+'/'+arm,
                'history_hash': history['content_hash'], 'task_hash': tasks[0]['content_hash'], 'initial_messages': initial_messages,
                'tools': TOOLS, 'treatment': treatment, 'steps': steps, 'submission': submission, 'counters': counters,
                'decision_origin': adapter.transport_kind if adapter else 'deterministic-enumeration',
                'agent_result': bool(adapter and adapter.transport_kind == 'real-provider')})
            trials.append(trial)
        barrier = seal(root/'learning-frozen.json', {'trial_hashes': [t['content_hash'] for t in trials], 'identity': identity})
        if fault:
            fault('all-trials-frozen')
        outcomes = []
        for trial in trials:
            sub = trial['submission']; final = None
            if sub and sub.get('candidate_id'):
                def confirm():
                    allowed(); run = execute_candidate(tasks[1], sub['candidate_id'])
                    artifact = seal_run(root/'confirmation', run)
                    return {**observation(tasks[1], sub['candidate_id'], run), 'artifact': str(artifact.relative_to(root))}
                rec = checkpoint(root, 'final-'+trial['arm'], {'barrier_hash': barrier['content_hash'], 'submission': sub},
                                 confirm, fault=fault, allow_compute=not reconcile_only)
                costs.append(rec); final = rec['value']
                verify_bundle(root/final['artifact'])
                actual = json.loads((root/final['artifact']/'run.json').read_text())
                if any(final[k] != v for k, v in observation(tasks[1], sub['candidate_id'], actual, reproduce=False).items()):
                    raise BudgetStop('final confirmation differs from sealed reference')
            admitted = bool(sub and sub['claim_pass'] and sub['evidence_admissible'] and final and final['physical_pass'])
            outcomes.append({'arm': trial['arm'], 'trial_hash': trial['content_hash'], 'final': final,
                             'evidence_bound_computational_success': admitted,
                             'false_claim': bool(sub and sub['claim_pass'] and not (final and final['physical_pass']))})
        paid = []
        for arm, adapter in adapters.items():
            for step in next(t for t in trials if t['arm'] == arm)['steps']:
                value = checked(json.loads((root/arm/f'decision-{step["turn"]}.json').read_text()))['value']
                paid.append(value['cost_receipt'])
        local_complete = all(c['local_cost_complete'] for c in costs) and all(c['local_cost_status'] == 'complete' for c in paid)
        return seal(root/'report.json', {'schema_version': VERSION, 'identity': identity, 'barrier_hash': barrier['content_hash'],
            'trials': trials, 'outcomes': outcomes, 'formal_agent_result': plan['purpose'] == 'formal-agent-trial',
            'cost': {'provider_calls': len(paid), 'usage_tokens': sum(c['usage_tokens'] for c in paid),
                     'charged_upper_micro_cny': sum(c['charged_upper_micro_cny'] for c in paid),
                     'actual_provider_calls': len(paid) if plan['purpose'] == 'formal-agent-trial' else 0,
                     'measured_local_wall_s': sum(c['cost']['wall_s'] or 0 for c in costs),
                     'measured_local_cpu_s': sum(c['cost']['cpu_s'] or 0 for c in costs),
                     'local_cost_complete': local_complete, 'total_campaign_cost_complete': False,
                     'scope': 'effect intervals and provider usage; missing intervals stay unknown; historical learning/qualification and replay/audit maintenance excluded'},
            'transfer_validated': False, 'claim_boundary': 'Provider control is not real Agent evidence. A formal matched matrix is still not statistical transfer, hardware or RSI.'})


def _audit_experiments(task, completed, root):
    for index, receipt in enumerate(completed, 1):
        checked(receipt)
        if checked(json.loads((root/f'experiment-{index}.json').read_text())) != receipt:
            raise BudgetStop('local experiment receipt changed')
        bundle = (root/receipt['artifact']).resolve()
        if not bundle.is_relative_to((root/'runs').resolve()):
            raise BudgetStop('experiment artifact escaped')
        verify_bundle(bundle)
        run = json.loads((bundle/'run.json').read_text())
        # Sealing already numerically reproduced this immutable run. Recovery
        # audits its inventory/hash and exact projection, not another solver run.
        if any(receipt[k] != v for k, v in observation(task, receipt['candidate_id'], run, reproduce=False).items()):
            raise BudgetStop('experiment observations changed from sealed reference')


def _audit_effect(task, action, before, value, root, budget):
    old, current = before['completed'], value['completed']
    if current[:len(old)] != old:
        raise BudgetStop('completed experiment prefix changed')
    facts, kind = value['facts'], action.get('action')
    if kind in {'submit', 'abstain'}:
        expected_facts, expected_sub = _effect(task, action, before['context'], old, root, copy.deepcopy(before['counters']), budget)
        if facts != expected_facts or value['submission'] != expected_sub or current != old or value['counters'] != before['counters']:
            raise BudgetStop('submission evidence or pure control effect changed')
    elif value['submission'] is not None:
        raise BudgetStop('non-submission action cannot claim admission')
    if 'run_hash' in facts:
        if kind != 'experiment' or len(current) != len(old)+1 or facts['candidate_id'] != action.get('candidate_id') or facts['predicted_pass'] != action.get('predicted_pass'):
            raise BudgetStop('experiment effect does not match model action')
        if {k: v for k, v in current[-1].items() if k != 'artifact'} != facts:
            raise BudgetStop('experiment feedback changed from its receipt')
    counts = copy.deepcopy(before['counters'])
    counts['experiments'] += int('run_hash' in facts)
    counts['python_calls'] += int(kind == 'python' and facts.get('error') != 'Python mechanical rejection')
    if value['counters'] != counts:
        raise BudgetStop('tool cost counters changed')
