#!/usr/bin/env python3
"""Qualify a separately pinned compiler against unchanged legacy build tests.

No old paper/D5 job is dispatched. These are disposable build/SIL controls.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

APP = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--toolchain', type=Path, default=APP / 'docs/agentlab/refactor-r0-r2-20261011/verification/native-arm-toolchain.json')
parser.add_argument('--full-init', action='store_true')
args = parser.parse_args()
manifest = json.loads(args.toolchain.read_text())
gcc = Path(manifest['compiler_path'])
assert hashlib.sha256(gcc.read_bytes()).hexdigest() == manifest['compiler_sha256'], 'COMPILER_PIN_MISMATCH'
environment = {**os.environ, 'ARM_GCC': str(gcc), 'BF_ARM_GCC': str(gcc), 'BF_PI_ROOT': str(APP.parent / 'pi-bf-aiot'),
               'PYTHONPATH': str(APP / 'packages/python/bfworld/src')}
out = APP / 'docs/agentlab/refactor-r0-r2-20261011/verification' / ('native-environment-' + str(time.time_ns()))
out.mkdir()
if args.full_init:
    commands = [('application-init', ['./init.sh'])]
else:
    groups = ['test_door_selfpower.py', 'test_firmware_targets.py', 'test_simulation_chain.py',
              'test_deployment.py', 'test_product.py', 'test_product_authority.py']
    commands = [(name, [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/agentlab', '-p', name, '-v']) for name in groups]
results = []
for name, argv in commands:
    started = time.time()
    with (out / (name + '.log')).open('w') as log:
        result = subprocess.run(argv, cwd=APP, env=environment, stdout=log, stderr=subprocess.STDOUT)
    record = {'name': name, 'argv': argv, 'exit_code': result.returncode, 'elapsed_s': time.time() - started}
    results.append(record)
    print(json.dumps(record), flush=True)
report = {'schema_version': 'bf-compiler-environment-qualification-v1', 'time': time.time(),
          'toolchain_manifest_sha256': hashlib.sha256(args.toolchain.read_bytes()).hexdigest(),
          'compiler_path': str(gcc), 'compiler_sha256': manifest['compiler_sha256'],
          'environment_overrides': {k: environment[k] for k in ('ARM_GCC', 'BF_ARM_GCC', 'BF_PI_ROOT', 'PYTHONPATH')},
          'passed': all(r['exit_code'] == 0 for r in results), 'checks': results,
          'old_sealed_jobs_rerun': 0, 'external_provider_calls': 0,
          'scope': 'Fresh disposable build/SIL controls, or application init when requested; not old product acceptance.'}
(out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({'passed': report['passed'], 'report': str(out / 'report.json')}))
sys.exit(0 if report['passed'] else 1)
