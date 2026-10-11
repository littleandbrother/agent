#!/usr/bin/env python3
"""Capture the actual local dependency identities without dispatching work."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

APP = Path(__file__).resolve().parents[2]
PI = APP.parent / 'pi-bf-aiot'
OUT = APP / 'docs/agentlab/refactor-r0-r2-20261011'
RT = Path('/Users/depengsu/.local/share/bf-agent-runtime')
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.runtime_config import NODE
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
review = json.loads((OUT / 'trial/independent-review.json').read_text())
build_path = RT / 'workbench/design-lab' / review['owner'] / 'operations' / review['submission']['operation_id'] / 'build.json'
build = json.loads(build_path.read_text())
compiler = build['compiler']
assert sha(compiler['host']) == compiler['compiler_sha256']
assert sha(Path(compiler['host_sdk']) / 'SDKSettings.json') == compiler['host_sdk_settings_sha256']
arm = json.loads((OUT / 'verification/native-arm-toolchain.json').read_text())
assert sha(arm['compiler_path']) == arm['compiler_sha256']
packages = []
for name in ('pi-coding-agent', 'pi-agent-core', 'pi-ai'):
    path = PI / 'node_modules/@earendil-works' / name / 'package.json'
    if path.is_file():
        d = json.loads(path.read_text())
        packages.append({'name': d['name'], 'version': d['version'],
                         'resolved_manifest': str(path.resolve()), 'sha256': sha(path)})
receipt = {'schema_version': 'bf-refactor-local-environment-snapshot-v1', 'time': time.time(),
    'system': {'platform': platform.platform(), 'machine': platform.machine(), 'python': sys.version,
               'python_executable': sys.executable},
    'node': {'path': str(NODE), 'sha256': sha(NODE),
             'version': subprocess.check_output([str(NODE), '--version'], text=True).strip()},
    'pi_package_lock_sha256': sha(PI / 'package-lock.json'), 'resolved_sdk_packages': packages,
    'C_actual_build_receipt': {'path': str(build_path), 'sha256': sha(build_path),
                              'build_id': build['build_id'], 'compiler': compiler},
    'separately_qualified_legacy_native_arm_compiler': {'manifest_sha256': sha(OUT / 'verification/native-arm-toolchain.json'),
                                                     'compiler_sha256': arm['compiler_sha256']},
    'paid_C_harness_id': review['harness_id'],
    'latest_zero_model_harness_id': 'H-2336102e0d2205ae25dac2c2453595384ffb512e5e7dca8c5add1d304fb5808c',
    'environment_id': review['submission']['acceptance']['environment_id'],
    'validation_id': review['submission']['acceptance']['validation_id'],
    'capabilities': {'finite_compiled_C': 'QUALIFIED', 'same_version_delivery': 'QUALIFIED',
        'zero_model_recovery': 'QUALIFIED', 'unchanged_D5_witness_reuse': 'QUALIFIED',
        'changed_load_native_recoupling': 'NOT_QUALIFIED', 'arbitrary_SoC_HEX_execution': 'NOT_QUALIFIED',
        'full_A_B_cases': 'NOT_QUALIFIED', 'board_and_RF': 'NOT_CHECKED', 'hardware': 'NOT_TESTED',
        'method_gain_or_RSI': 'NOT_EVALUATED', 'fresh_offline_dependency_install': 'NOT_TESTED'},
    'boundary': 'Local identity and finite qualification. SDK dependencies still use existing pinned local installation; not an independently reproduced clean-room environment.',
    'model_calls': 0, 'native_solver_calls': 0}
dest = OUT / ('environment-snapshot-' + str(time.time_ns()) + '.json')
dest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
print(json.dumps({'captured': True, 'sdk_packages': len(packages), 'receipt': str(dest)}))
