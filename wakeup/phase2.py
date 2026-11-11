"""Evidence experiments: existing physics, one model loop, one append-only record."""
import argparse
import concurrent.futures
import copy
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
OUT = HERE / 'phase2'
JOURNAL = OUT / 'results.jsonl'
LOCK = threading.Lock()
SCIENCE = threading.Lock()
HALT = threading.Event()
START = time.monotonic()
TALLY = dict(spent=0., conservative=0., reserved=0., requests=0, groups={}, full=0, numeric=0)
CAPS = dict(A=12., G=8., J=4., C=8.)
MODEL = 'deepseek-flash'


def group(job):
    return 'C' if job.startswith(('CA/', 'CG/')) else job[0]


def emit(row):
    with LOCK:
        with JOURNAL.open('a') as f:
            f.write(json.dumps(row, ensure_ascii=False, default=lambda v: v.item()) + '\n')


def request(messages, tools, job):
    body = json.dumps(dict(model=MODEL, messages=messages, tools=tools,
        thinking=dict(type='enabled'), reasoning_effort='high', max_tokens=32768, stream=False)).encode()
    key = os.environ.get('DEEPSEEK_API_KEY') or (Path.home() / '.local/share/bf-campaign-20261019-s0/workbench/secrets/deepseek.key').read_text().strip()
    reserve = (len(body)*.30 + 32768*1.20)/1e6
    while True:
        with LOCK:
            g = TALLY['groups'].setdefault(group(job), dict(spent=0., reserved=0.))
            if HALT.is_set() or TALLY['spent'] + TALLY['reserved'] + reserve > 32 or g['spent']+g['reserved']+reserve > CAPS[group(job)] or time.monotonic()-START > 28800:
                raise RuntimeError('BATCH_LIMIT_OR_DEPENDENCY_STOP')
            TALLY['requests'] += 1
            rid = TALLY['requests']
            TALLY['reserved'] += reserve
            g['reserved'] += reserve
        emit(dict(kind='request', job=job, id=rid, reservation_usd=reserve))
        try:
            req = urllib.request.Request('https://api.deepseek.com/chat/completions', data=body,
                headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=600) as f:
                answer = json.load(f)
            u = answer.get('usage', {})
            if not all(type(u.get(k)) is int for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')):
                raise RuntimeError('PROVIDER_USAGE_UNAVAILABLE')
            hit = u.get('prompt_cache_hit_tokens', 0)
            cost = ((u['prompt_tokens']-hit)*.30 + hit*.006 + u['completion_tokens']*1.20)/1e6
            conservative = (u['prompt_tokens']*.30 + u['completion_tokens']*1.20)/1e6
            with LOCK:
                TALLY['spent'] += cost
                TALLY['conservative'] += conservative
                TALLY['reserved'] -= reserve
                g['spent'] += cost
                g['reserved'] -= reserve
            emit(dict(kind='response', job=job, id=rid, response=answer, estimated_usd=cost,
                conservative_usd=conservative))
            return answer
        except Exception as e:
            emit(dict(kind='UNKNOWN', job=job, id=rid, error=str(e), reservation_usd=reserve))
            if isinstance(e, urllib.error.HTTPError) and e.code == 500:
                time.sleep(2)
                continue
            HALT.set()
            raise


def function(name, description, fields, required):
    return dict(type='function', function=dict(name=name, description=description,
        parameters=dict(type='object', properties=fields, required=required)))


def jobs():
    import phase2_physics as physical
    import phase2_scope as scope
    out = []
    for rep in (0, 1):
        for t in physical.tasks('A1'):
            for condition in ('R', 'P', 'D', 'K'):
                out.append(dict(stage='A1', round=rep+1, task=t, condition=condition, rep=rep))
    for t in scope.tasks('G'):
        for condition in ('H', 'P', 'S'):
            out.append(dict(stage='G', round=1, task=t, condition=condition, rep=0))
    for t in physical.tasks('J'):
        for condition in ('P', 'D', 'PS', 'DS'):
            out.append(dict(stage='J', round=2, task=t, condition=condition, rep=0))
    for t in physical.tasks('CA'):
        for condition in ('P', 'D'):
            out.append(dict(stage='CA', round=2, task=t, condition=condition, rep=0))
    for t in scope.tasks('CG'):
        for condition in ('P', 'S'):
            out.append(dict(stage='CG', round=2, task=t, condition=condition, rep=0))
    for t in physical.anchoring_cases():
        for condition in ('N', 'M'):
            out.append(dict(stage='A2', round=1, task=t, condition=condition, rep=0))
    for rep in (0, 1):
        for t in physical.tasks('A1'):
            if t['id'] in ('A1-E1-offset', 'A1-T1-offset'):
                for condition in ('Q0', 'Q1'):
                    out.append(dict(stage='A3', round=rep+1, task=t, condition=condition, rep=rep))
    random.Random(20261110).shuffle(out)
    return out


def probe(job):
    """The two short probes share the same client and journal, not another harness."""
    import phase2_physics as physical
    from agent_limits import response
    from sim import beam
    t, arm, stage = job['task'], job['condition'], job['stage']
    jid = f"{stage}/{t['id']}/{arm}/r{job['rep']}"
    answer = None
    count = 0
    if stage == 'A2':
        payload = dict(measured_points=t['measured_points'], response=t['response'],
            question='Which of these two already measured points has larger actual voltage amplitude? Return index 0 or 1 and confidence. Judge this local response only.')
        if arm == 'M':
            payload['nominal_prediction'] = t['nominal_prediction']
        tools = [function('answer', 'Submit judgment.', dict(index=dict(type='integer', enum=[0, 1]),
            confidence=dict(type='number'), reason=dict(type='string')), ['index', 'confidence', 'reason'])]
    else:
        main = t['family'].startswith('E')
        key = 'main_length_mm' if main else 'aux_length_mm'
        lo, hi = t['domain'][key]
        x = t['initial'].copy()
        def calculate(v):
            nonlocal count
            if count >= 16 or not lo <= v <= hi:
                raise ValueError('Sixteen total mathematical points; stay in declared range')
            z = x | {key: v}
            d = physical._design(t, z)
            b = beam(d['harvester' if main else 'trigger_beam'])
            _, amplitude = response(b, 45. if main else 210., .15 if main else .5, 1e8)
            count += 1
            with LOCK:
                TALLY['numeric'] += 1
            emit(dict(kind='math_point', job=jid, value=v, amplitude_V=float(amplitude)))
            return dict(value=v, amplitude_V=float(amplitude), remaining=16-count)
        payload = dict(task={k:t[k] for k in ('initial', 'domain', 'spec')},
            calibration=t['private']['factors'], variable=key,
            numerical_task='Maximize settled open-circuit response amplitude at the stated excitation. This proxy omits rectifier loading, transient and classification. Then submit exactly one design to the original full transient.',
            numerical_frequency_Hz=45 if main else 210, budget=dict(mathematical_points=16, full_submissions=1))
        tools = [function('points', 'Evaluate one or more chosen mathematical points; every point counts.',
            dict(values=dict(type='array', items=dict(type='number'))), ['values']),
            function('submit', 'Submit one numerical value to the original full transient and finish.',
            dict(value=dict(type='number'), reason=dict(type='string')), ['value', 'reason'])]
        if arm == 'Q1':
            tools.append(function('optimize', 'Bounded scalar search, all underlying points use the same remaining 16-point budget.', {}, []))
    messages = [dict(role='system', content='Use the declared tools to answer this engineering task. All stated results and uncertainty matter.'),
                dict(role='user', content=json.dumps(payload))]
    emit(dict(kind='start', job=jid, stage=stage, round=job['round'], public_messages=messages, tools=tools))
    error = None
    try:
        for _ in range(12 if stage=='A3' else 3):
            r = request(messages, tools, jid)
            msg = r['choices'][0]['message']; messages.append(msg)
            for call in msg.get('tool_calls', []):
                a = json.loads(call['function']['arguments']); name = call['function']['name']
                try:
                    if name == 'answer' and stage == 'A2':
                        answer = a; reply = dict(accepted=True)
                    elif name == 'points' and stage == 'A3':
                        reply = [calculate(float(v)) for v in a['values']]
                    elif name == 'optimize' and stage == 'A3' and arm == 'Q1':
                        from scipy.optimize import minimize_scalar
                        seen = []
                        def obj(v):
                            row = calculate(v); seen.append(row)
                            return -row['amplitude_V']
                        minimize_scalar(obj, bounds=(lo, hi), method='bounded', options=dict(maxiter=16-count))
                        reply = dict(best_found=max(seen, key=lambda z:z['amplitude_V']), evaluations=len(seen))
                    elif name == 'submit' and stage == 'A3':
                        v = float(a['value'])
                        if not lo <= v <= hi:
                            raise ValueError('Outside declared domain')
                        x[key] = v
                        with SCIENCE:
                            reply = physical.evaluate(t, x)
                        with LOCK:
                            TALLY['full'] += reply['cost']['full']
                        emit(dict(kind='evaluation', job=jid, design=x, result=reply))
                        answer = dict(design=x, result=reply, reason=a['reason'])
                    else:
                        raise ValueError('Undeclared tool')
                except ValueError as e:
                    reply = dict(error=str(e))
                messages.append(dict(role='tool', tool_call_id=call['id'], content=json.dumps(reply)))
                if answer is not None:
                    break
            if answer is not None:
                break
            if r['choices'][0]['finish_reason']=='length':
                error='OUTPUT_LENGTH'; break
        if answer is None and error is None:
            error='NO_SUBMISSION'
    except Exception as e:
        error=repr(e)
    emit(dict(kind='terminal', job=jid, stage=stage, round=job['round'], task=t['id'], condition=arm,
        rep=job['rep'], answer=answer, pass_=answer.get('result', {}).get('pass_') if answer else None,
        numeric_evaluations=count, error=error, truth=t.get('private')))
    print(jid, 'ANSWER' if answer else error, flush=True)


def episode(job):
    import phase2_physics as physical
    import phase2_scope as scope
    if HALT.is_set():
        return
    if job['stage'] in ('A2', 'A3'):
        return probe(job)
    stage, t, condition = job['stage'], job['task'], job['condition']
    module = scope if stage in ('G', 'CG') else physical
    jid = f"{stage}/{t['id']}/{condition}/r{job['rep']}"
    x = t['initial'].copy()
    history = []
    observed = []
    actions = numeric = 0
    diagnosis = error = None
    started = time.monotonic()

    def measure(z):
        nonlocal numeric
        with SCIENCE:
            r = module.evaluate(t, z)
        numeric += int(module is scope)
        with LOCK:
            for k in ('full', 'numeric'):
                TALLY[k] += r.get('cost', {}).get(k, 0)
            if TALLY['full'] > 632 or TALLY['numeric'] > 1280:
                HALT.set()
                raise RuntimeError('SCIENTIFIC_EVALUATION_LIMIT')
        emit(dict(kind='evaluation', job=jid, design=z, result=r))
        if module is scope:
            observed.append(dict(design=z.copy(), pass_=r['pass_'], slack=r['slack'], base=r['base']))
        return r

    def present(r):
        if module is physical:
            feedback = physical.view(t, x, r, condition.replace('S', ''))
        else:
            feedback = {k: r[k] for k in ('pass_', 'slack', 'terminal', 'base', 'fidelity') if k in r}
        feedback |= dict(current_design=x.copy(), remaining_design_actions=6-actions)
        if module is scope:
            feedback['remaining_numeric_evaluations'] = 16-numeric
            feedback['actual_numerical_points'] = observed.copy()
        if condition in ('S', 'PS', 'DS'):
            changed = sorted({k for h in (observed if module is scope else history)
                              for k in h['design'] if h['design'][k] != t['initial'][k]})
            feedback['scope_summary'] = dict(evaluated_designs=[h['design'] for h in (observed if module is scope else history)],
                changed_variables=changed, not_changed_in_this_run=sorted(set(t['domain'])-set(changed)),
                interpretation='Finite evaluated points; no claim that intervals between them were exhausted.')
        elif condition in ('P', 'D') and (module is scope or stage == 'J'):
            feedback['progress_summary'] = dict(actions=actions, numerical_evaluations=numeric,
                observed_pass=r['pass_'], latest_slack=r['slack'])
        return feedback

    try:
        initial = copy.deepcopy(t['prefix'][0]['result']) if module is scope else measure(x)
        # The shared initial evaluation is not charged against the follow-up point budget.
        numeric = 0
        public = {k: t[k] for k in ('initial', 'domain', 'spec')}
        public['id'] = t.get('public_id', 'declared-node')
        if module is scope:
            public['shared_evidence'] = scope.view(t, condition)
        messages = [dict(role='system', content='Design the declared scientific system using actual tools. '
            'All legal variables may be changed jointly. Account for the stated uncertainty. '
            'Tools return facts, not design recommendations. '
            'Stop when the evidence and budget warrant it. No particular module or diagnosis is prescribed.'),
            dict(role='user', content=json.dumps(dict(task=public, initial_feedback=present(initial),
                budget=dict(design_actions=6, numeric_evaluations=16 if module is scope else None, model_responses=12))))]
        tools = [function('evaluate', 'Apply changes to CURRENT design and run the original declared evaluator.',
            dict(changes=dict(type='object'), reason=dict(type='string')), ['changes', 'reason']),
            function('finish', 'Stop freely; distinguish point, branch and global conclusions. No label is forbidden.',
            dict(label=dict(type='string', enum=['FEASIBLE', 'INFEASIBLE', 'UNSURE']),
                 scope=dict(type='string', enum=['point', 'branch', 'global']),
                 p_global=dict(type='number', description='Probability 0..1 that some legal design in the entire domain can PASS.'),
                 p_branch=dict(type='number', description='Probability 0..1 that some design in the current module branch can PASS.'),
                 reason=dict(type='string')), ['label', 'scope', 'p_global', 'reason'])]
        if module is scope:
            tools.append(function('optimize', 'Bounded numerical search from current design; every internal point counts. '
                'Returns best FOUND point, not a global extreme or proof. You choose variables and initial changes.',
                dict(changes=dict(type='object'), variables=dict(type='array', items=dict(type='string'))), ['variables']))
        emit(dict(kind='start', job=jid, stage=stage, round=job['round'], task=t['id'],
            condition=condition, rep=job['rep'], public_messages=messages, tools=tools))
        result = initial
        for turn in range(12):
            if diagnosis is not None:
                break
            exhausted = result['pass_'] or actions >= 6 or module is scope and numeric >= 16
            if exhausted and module is not scope:
                break
            active_tools = [tools[1]] if exhausted else tools
            if exhausted:
                messages.append(dict(role='user', content='Scientific evaluation has ended. No more evaluation points are available. Use finish to state your final conclusion and its scope; distinguish a found witness, a proof, and exhausted finite search.'))
            if time.monotonic()-started > 900:
                error = 'EPISODE_TIME_LIMIT'
                break
            answer = request(messages, active_tools, jid)
            msg = answer['choices'][0]['message']
            messages.append(msg)
            if not msg.get('tool_calls'):
                if answer['choices'][0]['finish_reason'] == 'length':
                    error = 'OUTPUT_LENGTH'
                    break
                messages.append(dict(role='user', content='Use one of the declared tools to act or finish.'))
                continue
            for call in msg['tool_calls']:
                name = call['function']['name']
                try:
                    a = json.loads(call['function']['arguments'])
                    if name == 'finish':
                        diagnosis = a
                        reply = dict(stopped=True)
                    elif name in ('evaluate', 'optimize'):
                        if actions >= 6 or result['pass_'] or module is scope and numeric >= 16:
                            reply = dict(not_executed='Already passed or evaluation budget used')
                        else:
                            changes = a.get('changes', {})
                            for k, v in changes.items():
                                d = t['domain'].get(k)
                                if d is None or type(d[0]) is bool and type(v) is not bool or type(d[0]) is not bool and (type(v) not in (int, float) or not d[0] <= v <= d[1]):
                                    raise ValueError('Outside public domain: '+k)
                            proposed = x | changes
                            before = x.copy()
                            if name == 'optimize' and module is scope:
                                keys = a['variables']
                                if not keys or any(k not in t['domain'] or type(t['domain'][k][0]) is bool for k in keys):
                                    raise ValueError('Optimizer variables must be declared continuous variables')
                                best = [proposed, None, -float('inf')]
                                def objective(u):
                                    if numeric >= 16:
                                        raise StopIteration
                                    z = proposed | {k: float(t['domain'][k][0] + v*(t['domain'][k][1]-t['domain'][k][0])) for k, v in zip(keys, u)}
                                    r = measure(z)
                                    score = min(r['slack'].values())
                                    if score > best[2]:
                                        best[:] = [z, r, score]
                                    return sum(min(v, 0)**2 for v in r['slack'].values())
                                u = [(proposed[k]-t['domain'][k][0])/(t['domain'][k][1]-t['domain'][k][0]) for k in keys]
                                try:
                                    minimize(objective, u, method='SLSQP', bounds=[(0, 1)]*len(keys), options=dict(maxiter=16, ftol=1e-10))
                                except StopIteration:
                                    pass
                                x, result = best[:2]
                            elif name == 'evaluate':
                                x, result = proposed, measure(proposed)
                            else:
                                raise ValueError('Tool not supplied')
                            actions += 1
                            history.append(dict(changes={k:v for k,v in x.items() if before[k] != v}, design=x.copy()))
                            reply = present(result)
                            emit(dict(kind='action', job=jid, step=actions, tool=name, arguments=a,
                                before=before, design=x, result=result, public_feedback=reply))
                    else:
                        raise ValueError('Unknown tool: '+name)
                except (KeyError, ValueError, TypeError) as e:
                    emit(dict(kind='invalid_action', job=jid, error=str(e)))
                    reply = dict(error=str(e), remaining_design_actions=6-actions)
                messages.append(dict(role='tool', tool_call_id=call['id'], content=json.dumps(reply)))
        else:
            error = 'MODEL_RESPONSE_LIMIT'
        emit(dict(kind='terminal', job=jid, stage=stage, round=job['round'], task=t['id'], condition=condition,
            rep=job['rep'], pass_=result['pass_'], design=x, result=result, actions=actions,
            numeric_evaluations=numeric, diagnosis=diagnosis, error=error,
            truth=t.get('private', {}).get('truth'), runtime_s=time.monotonic()-started))
        print(jid, 'PASS' if result['pass_'] else error or 'NO_PASS', actions, flush=True)
    except Exception as e:
        emit(dict(kind='terminal', job=jid, stage=stage, round=job['round'], task=t['id'],
            condition=condition, rep=job['rep'], pass_=False, actions=actions, error=repr(e)))
        print(jid, 'ERROR', repr(e), flush=True)


def run(round_number):
    old = [json.loads(line) for line in JOURNAL.read_text().splitlines()] if JOURNAL.exists() else []
    if old:
        global START
        START -= sum(r.get('runtime_s', 0) for r in old if r['kind']=='round_end')
    done = {r['job'] for r in old if r['kind'] == 'terminal'}
    requests = {r['id'] for r in old if r['kind'] == 'request'}
    settled = {r['id'] for r in old if r['kind'] in ('response', 'UNKNOWN')}
    if requests-settled:
        raise SystemExit('Existing in-flight request: read original outcome before continuing')
    if any(r['kind']=='UNKNOWN' and 'HTTP Error 500' not in r['error'] for r in old):
        raise SystemExit('Non-HTTP500 missing usage: dependent paid work stopped')
    TALLY.update(spent=sum(r.get('estimated_usd', 0) for r in old),
        conservative=sum(r.get('conservative_usd', 0) for r in old),
        reserved=sum(r.get('reservation_usd', 0) for r in old if r['kind'] == 'UNKNOWN'),
        requests=max(requests, default=0))
    for g in CAPS:
        rows = [r for r in old if group(r.get('job', '?')) == g]
        TALLY['groups'][g] = dict(spent=sum(r.get('estimated_usd', 0) for r in rows),
            reserved=sum(r.get('reservation_usd', 0) for r in rows if r['kind']=='UNKNOWN'))
    for k in ('full', 'numeric'):
        TALLY[k] = sum(r['result'].get('cost', {}).get(k, 0) for r in old if r['kind']=='evaluation')
    TALLY['numeric'] += sum(r['kind']=='math_point' for r in old)
    manifest = OUT / 'jobs.json'
    if not manifest.exists():
        batch = jobs()
        manifest.write_text(json.dumps(batch, ensure_ascii=False, indent=2))
    else:
        batch = json.loads(manifest.read_text())
    pending = [j for j in batch if j['round'] == round_number and f"{j['stage']}/{j['task']['id']}/{j['condition']}/r{j['rep']}" not in done]
    if round_number == 2:
        # Reproduce the observed false exclusion and proxy mismatch first; the frozen set is unchanged.
        pending.sort(key=lambda j: 0 if j['stage']=='A1' and j['task']['id']=='A1-E2-nominal' and j['condition']=='P'
                     else 1 if j['stage']=='A3' and j['task']['family']=='E1' else 2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(episode, pending))
    emit(dict(kind='round_end', round=round_number, accounting=TALLY, runtime_s=time.monotonic()-START))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--round', type=int, default=1)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    if args.run:
        run(args.round)
