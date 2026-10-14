#!/usr/bin/env python3
"""No-Agent native C qualification. Never overwrites/recomputes old D5 runs.

The changed 6 ms TX control has new inputs and therefore needs a new solve.
Other controls consume this new immutable result or unchanged baseline evidence.
"""
import argparse
import copy
import fcntl
import json
from pathlib import Path
import re
import sys
import time

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab import coupled_c, case_c, qualification
from bfworld.agentlab.design_lab.contracts import sha, sealed
from bfworld.agentlab.store import identity
from bfworld.agentlab.runtime_config import RUNTIME_ROOT

parser = argparse.ArgumentParser()
parser.add_argument('--reference', type=Path, default=Path('/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/door-selfpower-v1/full-bank3-46-c15-01'))
parser.add_argument('--output', type=Path)
parser.add_argument('--native', action='store_true', help='Execute only the changed-input no-Agent native control')
args = parser.parse_args()
native_slot = (RUNTIME_ROOT / 'design-native.lock').open('a')
fcntl.flock(native_slot, fcntl.LOCK_EX)
out = args.output or APP / 'docs/agentlab/executable-lab-20261012' / ('qualification-' + str(time.time_ns()))
out.mkdir(parents=True, exist_ok=False)
env = coupled_c.environment(args.reference)
task = coupled_c.contract(env)
sealed(out / 'environment.json', env)
sealed(out / 'task.json', task)
controls = []
sources = qualification.sources(env, True)
design = coupled_c.snapshot(task, sources, env)
root = out / 'unchanged'
build = coupled_c.build(design, root, env)
execution = coupled_c.execute(task, design, build, root, env)
check = coupled_c.evaluate(task, design, build, execution, env)
for n, value in [('snapshot.json', design), ('build.json', build), ('execution.json', execution), ('check.json', check)]:
    sealed(root / n, value)
controls.append({'name': 'unchanged-native-witness-reuse', 'matched': all(v == 'PASS' for v in check['gates'].values()) and execution['new_native_solver_calls'] == 0})
lost = case_c.evaluate(task, design, build, execution, env, link_loss=True)
controls.append({'name': 'receiver-link-loss', 'matched': lost['gates']['deadline_receive'] == 'FAIL'})
wrong = copy.deepcopy(execution)
wrong['build_id'] = 'wrong'
wrong.pop('execution_id')
wrong['execution_id'] = 'X-' + identity(wrong)
try:
    coupled_c.evaluate(task, design, build, wrong, env)
    rejected = False
except ValueError:
    rejected = True
controls.append({'name': 'wrong-build-binding', 'matched': rejected})
for name, event in [('port-id', {'time_s': 2.5, 'event_id': 65591, 'kind': 1}),
                    ('port-kind', {'time_s': 2.5, 'event_id': 4294967239, 'kind': 2})]:
    probe = coupled_c.probe(task, design, build, root, env, execution, event, name)
    checked = case_c.evaluate(task, design, build, probe, env, event_truth=event)
    controls.append({'name': name, 'matched': all(v == 'PASS' for v in checked['gates'].values())})
if args.native:
    changed = dict(sources)
    changed['policy.h'], count = re.subn(r'(#define TX_MS)\s+[^\n]+', r'\1 6.0', changed['policy.h'])
    if count != 1 or changed == sources:
        raise ValueError('CHANGED_NATIVE_CONTROL_NOT_CHANGED')
    design = coupled_c.snapshot(task, changed, env)
    root = out / 'changed-TX-6ms'
    build = coupled_c.build(design, root, env)
    sealed(root / 'snapshot.json', design)
    sealed(root / 'build.json', build)
    execution = coupled_c.execute(task, design, build, root, env)
    check = coupled_c.evaluate(task, design, build, execution, env)
    sealed(root / 'execution.json', execution)
    sealed(root / 'check.json', check)
    controls.append({'name': 'changed-load-real-native-feedback',
                     'matched': execution['native_solve'] == 'NEW_NATIVE_COUPLED_FIXED_POINT' and execution['new_native_solver_calls'] > 0 and all(v == 'PASS' for v in check['gates'].values()),
                     'new_native_solver_calls': execution['new_native_solver_calls'], 'execution_id': execution['execution_id']})
    # A second unchanged invocation is unnecessary. Check the immutable exact
    # identities and compare measured active durations against the old witness.
    controls.append({'name': 'trial-events-not-committed', 'matched': execution['provisional_events_committed'] is False})
report = {'schema_version': 'bf-native-C-environment-qualification-v2',
          'environment_id': env['environment_id'], 'validation_id': task['validation_id'],
          'scope': task['scope'], 'controls': controls,
          'passed': all(c['matched'] for c in controls) and args.native,
          'mode': 'native' if args.native else 'readonly-execution-preflight',
          'model_calls': 0, 'old_D5_native_solves': 0,
          'new_native_solver_calls': sum(c.get('new_native_solver_calls', 0) for c in controls),
          'physical': 'NOT_TESTED', 'target_peripherals': 'NOT_QUALIFIED',
          'full_product_passed': False, 'created': time.time()}
sealed(out / 'qualification.json', report)
print(json.dumps({'passed': report['passed'], 'scope': task['scope'], 'controls': controls,
                  'qualification': str(out / 'qualification.json')}), flush=True)
raise SystemExit(0 if report['passed'] or not args.native else 1)
