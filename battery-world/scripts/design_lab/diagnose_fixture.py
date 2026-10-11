#!/usr/bin/env python3
"""Run unchanged fixture-provider integration tests and retain launch failures.

No production Workbench, supplier call, old engineering job or test-rule change.
"""
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[2]
OUT = APP / 'docs/agentlab/refactor-r0-r2-20261011/verification' / ('fixture-diagnostic-' + str(time.time_ns()))
OUT.mkdir()
os.environ['BF_PI_ROOT'] = str(APP.parent / 'pi-bf-aiot')
manifest = json.loads((APP / 'docs/agentlab/refactor-r0-r2-20261011/verification/native-arm-toolchain.json').read_text())
os.environ['BF_ARM_GCC'] = manifest['compiler_path']
os.environ['ARM_GCC'] = manifest['compiler_path']
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab import launcher
original = launcher.launch
receipts = []
def observed_launch(*args, **kwargs):
    result = original(*args, **kwargs)
    path = Path(kwargs['home_root']) / 'sessions' / result['owner'] / 'stderr.log'
    record = {k: result.get(k) for k in ('owner', 'exit_code', 'status', 'error', 'app_entry')}
    record['stderr'] = path.read_text()[-12000:] if path.exists() else ''
    receipts.append(record)
    (OUT / 'launches.json').write_text(json.dumps(receipts, indent=2))
    return result
suite = unittest.defaultTestLoader.discover(str(APP / 'tests/agentlab'), pattern='test_simulation_tasks.py')
with (OUT / 'test.log').open('w') as log, patch.object(launcher, 'launch', side_effect=observed_launch):
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
report = {'passed': result.wasSuccessful(), 'tests': result.testsRun,
    'failures': len(result.failures), 'errors': len(result.errors),
    'launches': receipts, 'external_provider_calls': 0,
    'old_sealed_jobs_rerun': 0, 'scope': 'Unchanged public fixture-provider integration diagnostics.'}
(OUT / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'passed': result.wasSuccessful(), 'tests': result.testsRun, 'report': str(OUT / 'report.json')}))
sys.exit(0 if result.wasSuccessful() else 1)
