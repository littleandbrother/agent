"""Bounded, durable mechanical repair. No provider implementation is imported.

The proposer callback owns any separately authorized dispatch and cost receipt.
Unknown callback effects stop rather than repeat after a crash. Repeated code
does not receive another mechanical verifier budget. This is not semantic RSI.
"""
from __future__ import annotations
import json
import math
import resource
import time
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash, write_canonical_json, file_hash
from .compiler import compile_candidate, VERSION


def checked(obj):
    if obj.get('content_hash') != canonical_hash({k: v for k, v in obj.items() if k != 'content_hash'}):
        raise ValueError('repair artifact hash mismatch')
    return obj


def seal(path, obj):
    obj = {**obj, 'content_hash': canonical_hash(obj)}
    if path.exists():
        if json.loads(path.read_text()) != obj:
            raise ValueError('immutable repair artifact differs')
    else:
        write_canonical_json(path, obj)
    return obj


def cpu_seconds():
    return sum(r.ru_utime + r.ru_stime for r in (resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)))


def run_repair(initial, contexts, directory: Path, proposer, *, max_repairs=2):
    if type(max_repairs) is not int or not 0 <= max_repairs <= 2:
        raise ValueError('at most two repairs / three candidates')
    directory.mkdir(parents=True, exist_ok=True)
    binding = {'compiler': VERSION, 'compiler_hash':file_hash(Path(__file__).with_name('compiler.py')),
               'repair_runtime_hash':file_hash(Path(__file__)), 'initial_hash': canonical_hash(initial),
               'fixtures_hash': canonical_hash(contexts), 'max_repairs': max_repairs}
    seal(directory/'identity.json', binding)
    result_path = directory/'result.json'
    if result_path.exists():
        result = checked(json.loads(result_path.read_text()))
        if result['binding'] != binding:
            raise ValueError('repair result identity mismatch')
        for attempt in result['attempts']:
            checked(attempt); checked(attempt['compile'])
        return result
    candidate, attempts, seen = initial, [], set()
    status = 'repair-limit'
    for index in range(max_repairs + 1):
        candidate_hash = canonical_hash(candidate)
        if candidate_hash in seen:
            status = 'duplicate-candidate'; break
        seen.add(candidate_hash)
        path = directory/f'attempt-{index}.json'
        identity = canonical_hash({**binding, 'index': index, 'candidate_hash': candidate_hash})
        if path.exists():
            attempt = checked(json.loads(path.read_text()))
            if attempt['attempt_id'] != identity:
                raise ValueError('attempt identity mismatch')
            checked(attempt['compile'])
        else:
            start, cpu = time.perf_counter(), cpu_seconds()
            receipt = compile_candidate(candidate, contexts, directory/'sandbox')
            attempt = seal(path, {'attempt_id': identity, 'index': index, 'candidate': candidate,
                'compile': receipt, 'cost': {'wall_s': time.perf_counter()-start,
                'cpu_s': cpu_seconds()-cpu, 'provider_calls': 0, 'paid_cny': 0}})
        attempts.append(attempt)
        if attempt['compile']['passed']:
            status = 'mechanically-ready'; break
        if index == max_repairs:
            break
        # Intent precedes callback. An unknown dispatch never silently repeats.
        request = {'attempt_id': identity, 'candidate': candidate, 'compile_feedback': attempt['compile'],
                   'repairs_remaining': max_repairs-index, 'scientific_feedback': None}
        response_path = directory/f'replacement-{index}.json'
        intent_path = directory/f'request-{index}.json'
        if response_path.exists():
            response = checked(json.loads(response_path.read_text()))
            if response['request_hash'] != canonical_hash(request):
                raise ValueError('replacement request binding mismatch')
        elif intent_path.exists():
            raise RuntimeError('unsettled repair callback; reconcile its receipt before retry')
        else:
            seal(intent_path, request)
            response = proposer(request)
            if not isinstance(response, dict) or 'candidate' not in response or 'cost_receipt' not in response:
                raise ValueError('replacement requires candidate and actual cost receipt')
            cost = response['cost_receipt']
            if any(type(cost.get(k)) not in (int,float) or not math.isfinite(cost[k]) or cost[k] < 0 for k in ('provider_calls','paid_cny','wall_s','cpu_s')):
                raise ValueError('complete nonnegative callback cost required')
            response = seal(response_path, {**response, 'request_hash': canonical_hash(request)})
        candidate = response['candidate']
    callback_costs = [checked(json.loads(p.read_text()))['cost_receipt'] for p in sorted(directory.glob('replacement-*.json'))]
    costs = [a['cost'] for a in attempts] + callback_costs
    return seal(result_path, {'schema_version': 'candidate-repair-trace-v1', 'binding': binding,
        'status': status, 'attempts': attempts, 'final_candidate': candidate,
        'cost': {k: sum(c[k] for c in costs) for k in ('wall_s','cpu_s','provider_calls','paid_cny')},
        'scientific_probes': 0, 'qualification': 'not-run',
        'claim_boundary': 'bounded mechanical recovery; not semantic repair or cross-task learning'})
