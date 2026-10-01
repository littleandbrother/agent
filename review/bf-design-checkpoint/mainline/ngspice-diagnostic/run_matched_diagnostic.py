#!/usr/bin/env python3
"""Exactly four authorized local ngspice diagnostics; no gate or source edits."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
SOURCE = Path('/workspace/shared/current-cache-integration-20261001/working/battery-world')
SPICE = Path('/workspace/shared/current-cache-integration-20261001/toolchains/ngspice/usr/bin/ngspice')
TEST = SOURCE / 'tests/agentlab/test_reference_event.py'
MODEL = SOURCE / 'packages/python/bfworld/src/bfworld/agentlab/event_design.py'
os.environ['BF_HOME'] = str(ROOT / 'isolated-unused-home')
os.environ['BF_NGSPICE'] = str(SPICE)
sys.path.insert(0, str(SOURCE / 'packages/python/bfworld/src'))
from bfworld.agentlab import event_design

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

# Extract only the literal fixture function. Do not import/construct Workbench,
# a participant, test harness, provider, or production service.
node = next(n for n in ast.parse(TEST.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'fixture')
scope = {}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(TEST), 'exec'), scope)
fixture = scope['fixture']
baseline = fixture()
feedback = copy.deepcopy(baseline)
feedback['power'].update(start_v=.8, stop_v=.5, output_v=.4)
feedback['workload']['idle_current_a'] = .01

version = subprocess.run([str(SPICE), '--version'], capture_output=True, text=True, check=True)
(ROOT / 'ngspice-version.txt').write_text(version.stdout + version.stderr)
receipt = {
    'schema_version': 'ngspice-matched-step-diagnostic-v1',
    'source_commit': '338d60384d5805abf1e02252a4513860066a2c39',
    'diagnostic_only': True, 'gate_promoted': False,
    'maximum_solver_runs': 4, 'solver_runs_started': 0,
    'python': sys.version, 'platform': platform.platform(),
    'ngspice_version': version.stdout + version.stderr,
    'ngspice_path': str(SPICE), 'ngspice_sha256': digest(SPICE),
    'source_sha256': {str(p): digest(p) for p in (TEST, MODEL)},
    'settings': {'duration_s': .25, 'steps_s': [1e-5, 5e-6],
                 'reltol': 1e-5, 'abstol': 1e-11, 'vntol': 1e-8,
                 'method': 'gear', 'initial_conditions': 'original uic, q/u/p=0, storage=0',
                 'timer_reset_time_constant': 'step/10 (original model retained)'},
    'cases': {},
}

def save():
    (ROOT / 'DIAGNOSTIC-RESULT.json').write_text(json.dumps(receipt, indent=2) + '\n')

for configuration, spec in [('baseline', baseline), ('feedback', feedback)]:
    event_design.validate(spec)
    for label, step in [('10us', 1e-5), ('5us', 5e-6)]:
        name = configuration + '-' + label
        out = ROOT / 'runs' / name
        out.mkdir(parents=True, exist_ok=False)
        (out / 'input.json').write_text(json.dumps(spec, indent=2) + '\n')
        deck = out / 'test.cir'
        deck.write_text(event_design.netlist(spec, step, 'out.tsv'))
        command = [str(SPICE), '-n', '-b', 'test.cir']
        start = time.monotonic()
        receipt['solver_runs_started'] += 1
        case = {'configuration': configuration, 'step_s': step, 'command': command,
                'cwd': str(out), 'deck_sha256': digest(deck), 'input_sha256': digest(out / 'input.json')}
        receipt['cases'][name] = case
        save()
        with (out / 'process.log').open('w') as log:
            proc = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=40)
        case['returncode'] = proc.returncode
        case['wall_seconds'] = time.monotonic() - start
        save()
        if proc.returncode:
            raise SystemExit('Diagnostic stopped: ngspice failed; no automatic retry')
        rows = event_design.read_channels(out / 'out.tsv')
        summary = event_design.summarize(spec, rows)
        peak = max(rows, key=lambda r: abs(r['displacement_m']))
        case.update(summary=summary, rows=len(rows), peak_row=peak,
                    maximum_actual_load_a=max(r['load_a'] for r in rows),
                    enabled_rows=sum(r['enabled'] > .5 for r in rows),
                    post_stage_idle_rows=sum(r['enabled'] > .5 and r['stage_time_s'] >= .004 for r in rows),
                    final_time_s=rows[-1]['time_s'],
                    first_data_line=(out / 'out.tsv').open().readlines()[1].strip())
        case['artifacts'] = {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in out.iterdir() if p.is_file()}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        save()

def peak(name):
    return receipt['cases'][name]['summary']['peak_deflection_m']

comparisons = {'matched_steps': {}, 'refinement': {}}
for label in ('10us', '5us'):
    signed = peak('feedback-' + label) - peak('baseline-' + label)
    comparisons['matched_steps'][label] = {'feedback_minus_baseline_m': signed,
        'absolute_delta_m': abs(signed), 'original_strict_gt_1e_minus_7': abs(signed) > 1e-7}
for configuration in ('baseline', 'feedback'):
    signed = peak(configuration + '-5us') - peak(configuration + '-10us')
    comparisons['refinement'][configuration] = {'fine_minus_coarse_m': signed,
        'absolute_change_m': abs(signed), 'relative_change': abs(signed) / abs(peak(configuration + '-5us'))}
signed = peak('feedback-10us') - peak('baseline-5us')
comparisons['original_mixed_step'] = {'feedback_10us_minus_baseline_5us_m': signed,
    'absolute_delta_m': abs(signed), 'original_strict_gt_1e_minus_7': abs(signed) > 1e-7}
receipt['comparisons'] = comparisons
receipt['completed'] = True
receipt['all_sources_unchanged'] = all(digest(Path(p)) == h for p, h in receipt['source_sha256'].items())
save()
print(json.dumps({'runs': receipt['solver_runs_started'], 'comparisons': comparisons,
                  'sources_unchanged': receipt['all_sources_unchanged']}, indent=2))
