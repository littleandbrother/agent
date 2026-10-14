#!/usr/bin/env python3
"""Read new native evidence against the existing fixed P02 demand contract.

No solver, model call or participant edit. The old review is retained. Public
assessment only: this does not replace or relax a paper's core evaluator.
"""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

import numpy as np

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.contracts import sealed, sha
from bfworld.agentlab.engineering_projects import raw_readback
from bfworld.agentlab.store import identity

ROOT = Path('/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008')
OWNER = 'pi-chat-103e79405f0e0c6d'
parser = argparse.ArgumentParser()
parser.add_argument('--job', required=True)
args = parser.parse_args()
if not re.fullmatch(r'eng-[0-9a-f]{16}', args.job):
    raise ValueError('EXACT_NATIVE_JOB_REQUIRED')

# Use the pre-existing public rule verbatim, without executing its old
# top-level file writes or importing participant analysis code.
rule = ROOT / 'campaign/reviews/P02/r16-independent-energy-002/check.py'
rule_bytes = rule.read_bytes()
rule_sha = hashlib.sha256(rule_bytes).hexdigest()
prior_receipt = json.loads((rule.parent / 'result.json').read_text())
assert rule_sha == prior_receipt['checker_sha256'], 'ORIGINAL_PUBLIC_RULE_CHANGED'
tree = ast.parse(rule_bytes)
names = {'profiles', 'task_segments', 'evaluate', 'read_trace'}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
assert {n.name for n in nodes} == names
namespace = {'np': np, 'io': io, 're': re, 'raw_readback': raw_readback}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(rule), 'exec'), namespace)
profiles, task_segments, evaluate, read_trace = (namespace[n] for n in
                                               ('profiles', 'task_segments', 'evaluate', 'read_trace'))

def job(job_id):
    folder = ROOT / 'runtime/engineering' / job_id
    inp = json.loads((folder / 'input.json').read_text())
    result = json.loads((folder / 'result.json').read_text())
    with sqlite3.connect('file:' + str(ROOT / 'runtime/state/workbench.sqlite') + '?mode=ro', uri=True) as db:
        assert db.execute('SELECT owner,status FROM engineering_jobs WHERE id=?',
                          (job_id,)).fetchone() == (OWNER, 'SUCCEEDED')
    assert identity(inp['project']) == inp['project_sha256'] == result['project_sha256']
    assert result['kind'] == 'spice' and result['readback_passed']
    raw = folder / 'project-trace.raw'
    assert sha(raw) == next(x['sha256'] for x in result['outputs'] if x['name'] == raw.name)
    project = inp['project']
    net = project['sources'][project['manifest']['entrypoint']]
    return inp, net, raw, read_trace(raw)

base_inp, base_net, base_raw, _ = job('eng-f41bd73829a488cd')
inp, net, raw, data = job(args.job)
assert base_inp['project_sha256'] == 'a54219be51042d4545f1c6236e3d389e8cd8e5261f0983d16141201d803a45ff'
original = task_segments(profiles(base_net)[0])
assert len(original) == 20
candidate_profiles = profiles(net)
assert len(candidate_profiles) == 2
candidate_segments = task_segments(candidate_profiles[0])
def evaluate_segments(segments):
    return [evaluate(*(data[x] for x in ('time', 'v(nsa)', 'v(nswa)', 'i(vsensea)')),
                     segment) for segment in segments]
fixed_tasks = evaluate_segments(original)
candidate_tasks = evaluate_segments(candidate_segments)
fixed_times = [[float(s[0, 0]), float(s[-1, 0])] for s in original]
candidate_times = [[float(s[0, 0]), float(s[-1, 0])] for s in candidate_segments[:20]]
schedule_exact = (len(candidate_segments) >= 20 and all(
    np.array_equal(a, b) for a, b in zip(original, candidate_segments[:20])))
def source_line(text, name):
    match = re.search(r'(?im)^' + re.escape(name) + r'\s+[^\n]+', text)
    if not match:
        raise ValueError('SOURCE_PORT_NOT_IDENTIFIED:' + name)
    return match.group(0).lower().split()
source_parameters = {name: source_line(net, name) == source_line(base_net, name)
                     for name in ('VsrcA', 'RsA', 'CinA')}
assert data['time'][0] == 0 and data['time'][-1] >= 26

# These are the old independent signal rules, including their original
# signed energy, boundary samples and voltage floor, not new thresholds.
ct = np.array([0., .25, .5, .75, 1.])
cv = np.full(5, 4.)
segment = np.array([[0., 0.], [.25, .04], [.75, .04], [1., 0.]])
ci = (np.interp(ct, segment[:, 0], segment[:, 1]) + .00792) / 4
def synthetic(i=ci, store=cv, t=ct):
    return evaluate(t, store[:len(t)], cv[:len(t)], i[:len(t)], segment)['status']
drop = ci.copy(); drop[2] = 0
low = cv.copy(); low[2] = 3.4
controls = {
    'known_complete_signal': synthetic() == 'PASS',
    'zero_current_rejected': synthetic(i=ci * 0) == 'FAIL',
    'reverse_current_rejected': synthetic(i=-ci) == 'FAIL',
    'gate_drop_rejected': synthetic(i=drop) == 'FAIL',
    'brownout_rejected': synthetic(store=low) == 'FAIL',
    'partial_trace_unevaluable': synthetic(t=ct[:-1]) == 'UNEVALUABLE',
    'different_schedule_never_counted_as_fixed_schedule': not np.array_equal(
        original[0], original[0] + np.array([.01, 0.])),
}
assert all(controls.values())
passed = sum(x['status'] == 'PASS' for x in fixed_tasks)
receipt = {
    'schema_version': 'bf-p02-existing-demand-readback-v1', 'created': time.time(),
    'paper_id': 'P02', 'owner': OWNER, 'actor': 'Codex independent public reviewer',
    'job_id': args.job, 'project_sha256': inp['project_sha256'], 'raw_sha256': sha(raw),
    'source_sha256': hashlib.sha256(net.encode()).hexdigest(),
    'rule_path': str(rule), 'rule_sha256': rule_sha, 'checker_sha256': sha(__file__),
    'original_demand_job': 'eng-f41bd73829a488cd', 'original_raw_sha256': sha(base_raw),
    'original_demands': 20, 'original_tasks_passed': passed, 'original_tasks': fixed_tasks,
    'candidate_schedule_exact': schedule_exact, 'original_windows': fixed_times,
    'original_source_parameters_retained': source_parameters,
    'candidate_windows': candidate_times,
    'candidate_declared_windows_results': candidate_tasks,
    'controls': controls,
    'status': 'PASS' if schedule_exact and all(source_parameters.values()) and passed == 20 else 'REPAIR_REQUIRED',
    'numerical_scope': 'Existing saved-sample signed-energy rule only; no intersample bound.',
    'claim_boundary': 'New or delayed demand windows are reported separately and do not close the original fixed-demand failures. No calibrated source, firmware, RF, hardware or full-product acceptance.',
    'full_product_passed': False, 'physical_verified': False,
    'model_calls': 0, 'new_solver_runs': 0, 'participant_source_edits': 0,
}
out = ROOT / 'campaign/reviews/P02' / ('executable-lab-demand-' + str(time.time_ns()))
out.mkdir()
checker_bytes = Path(__file__).read_bytes()
assert hashlib.sha256(checker_bytes).hexdigest() == receipt['checker_sha256']
(out / 'checker.py').write_bytes(checker_bytes)
(out / 'existing-public-rule.py').write_bytes(rule_bytes)
sealed(out / 'result.json', receipt)
print(json.dumps({'result': str(out / 'result.json'), 'status': receipt['status'],
                  'fixed_demand_passed': passed, 'schedule_exact': schedule_exact,
                  'controls': controls}))
