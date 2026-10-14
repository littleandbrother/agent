#!/usr/bin/env python3
"""Freeze and test the real continuation entry, without starting a Workbench."""
import json
from pathlib import Path
import sys
import subprocess
import time
import unittest

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
sys.path.insert(0, str(APP / 'tests/agentlab'))
from bfworld.agentlab import literature_native
from bfworld.agentlab.literature_campaign import digest
from bfworld.agentlab.design_lab.contracts import sealed
from bfworld.agentlab.runtime_config import PI

SUITES = ['test_context', 'test_provider', 'test_recovery', 'test_context_recovery',
          'test_context_compact', 'test_literature_continuation',
          'test_literature_native', 'test_literature_campaign',
          'test_paper_sessions', 'test_chat', 'test_unbounded_budget',
          'test_native_spice_reuse', 'test_literature_acceptance',
          'test_literature_eda', 'test_eda_cli', 'test_nordic_sdk',
          'test_firmware_targets', 'test_stm32_l432', 'test_spice_observation',
          'test_cad_preview', 'test_runtime_architecture', 'test_current_working_context', 'test_closed_continuation_context', 'test_engineering_cases', 'test_session_receipt', 'test_literature_package', 'test_design_lab_slot',
          'test_design_lab_receipt_observer', 'test_design_lab_trace_ingest', 'test_design_lab_phase_goal', 'test_design_lab_eda_migration', 'test_design_lab_native_context', 'test_design_lab_ingress', 'test_execution_progress', 'test_design_lab_operator_restore', 'test_design_lab_mainline', 'test_design_lab_preflight_lock', 'test_native_unknown_recovery', 'test_receiver_runtime_capability', 'test_native_protocol_codec', 'test_native_reference_capability', 'test_reference_materialize']
SUITES.extend(['test_design_lab_paper', 'test_spice_readback', 'test_project_output_format', 'test_candidate_queue_outcome', 'test_active_request_capacity', 'test_round2_efficiency'])

out = APP / 'docs/agentlab/executable-lab-20261012' / ('paper-release-tests-' + str(time.time_ns()))
out.mkdir(parents=True)
before, modules = literature_native.apparatus_identity()
test_sources = {name: digest(APP/'tests/agentlab'/(name+'.py')) for name in SUITES}
controller = digest(literature_native.__file__)
start = time.time()
suite = unittest.TestLoader().loadTestsFromNames(SUITES)
with (out/'tests.log').open('w') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
native_test = APP/'scripts/eda/native_connector.test.mjs'
native_source = APP/'scripts/eda/native_connector.mjs'
native_before = {str(p.relative_to(APP)): digest(p) for p in (native_test, native_source)}
node = subprocess.run(['node', '--test', str(native_test)], capture_output=True, text=True, timeout=30)
(out/'native-transport-tests.log').write_text(node.stdout + node.stderr)
native_unchanged = all(digest(APP/name) == value for name, value in native_before.items())
context_test = APP/'scripts/design_lab/current_context.test.mjs'
candidate_test = APP/'scripts/design_lab/paper_candidate.test.mjs'
efficiency_test = APP/'scripts/design_lab/round2_efficiency.test.mjs'
context_files = [context_test, candidate_test, efficiency_test, *(PI/'packages/bf-agent/src'/name for name in ('chat-product.ts', 'current-context.ts', 'paper-candidate.ts', 'skill-resources.ts', 'workspace-inspect.ts', 'read-progress.ts', 'tool-reply.ts', 'bounded-bash.ts'))]
context_before = {str(path): digest(path) for path in context_files}
context_node = subprocess.run(['node', '--import', str(PI/'node_modules/tsx/dist/loader.mjs'),
                               '--test', str(context_test), str(candidate_test), str(efficiency_test)], capture_output=True, text=True, timeout=30)
(out/'current-context-tests.log').write_text(context_node.stdout + context_node.stderr)
caller_build = subprocess.run(['npm', '--prefix', str(PI/'packages/bf-agent'), 'run', 'build'],
                              capture_output=True, text=True, timeout=120)
(out/'pi-caller-build.log').write_text(caller_build.stdout + caller_build.stderr)
context_unchanged = all(digest(path) == value for path, value in context_before.items())
after, _ = literature_native.apparatus_identity()
test_sources_unchanged = all(digest(APP/'tests/agentlab'/(name+'.py')) == value for name,value in test_sources.items())
report = {'status': 'PASS' if result.wasSuccessful() and before == after and test_sources_unchanged and node.returncode == 0 and native_unchanged and context_node.returncode == 0 and caller_build.returncode == 0 and context_unchanged else 'FAIL',
          'tests': result.testsRun, 'failures': len(result.failures),
          'errors': len(result.errors), 'seconds': time.time()-start,
          'suites': SUITES, 'apparatus_identity': after, 'apparatus_modules': modules,
          'test_source_sha256':test_sources,'test_sources_unchanged':test_sources_unchanged,
          'controller_sha256': controller,
          'controller_unchanged': controller == digest(literature_native.__file__),
          'native_transport': {'exit_code': node.returncode, 'source_sha256': native_before,
                               'source_unchanged': native_unchanged,
                               'log_sha256': digest(out/'native-transport-tests.log')},
          'current_context_interface': {'exit_code': context_node.returncode, 'source_sha256': context_before,
                                        'source_unchanged': context_unchanged,
                                        'log_sha256': digest(out/'current-context-tests.log'),
                                        'caller_build_exit_code': caller_build.returncode,
                                        'caller_build_log_sha256': digest(out/'pi-caller-build.log')},
          'log_sha256': digest(out/'tests.log'),
          'external_model_calls': 0, 'new_native_solver_runs': 0,
          'scope': 'Continuation, provider/context, authority, independent acceptance and typed native-worker interfaces. Mocks are not fresh vendor-model or hardware qualification.'}
sealed(out/'result.json', report)
print(json.dumps({k: report[k] for k in ('status','tests','failures','errors','seconds')}, ensure_ascii=False))
print(out/'result.json')
raise SystemExit(0 if report['status'] == 'PASS' and report['controller_unchanged'] else 1)
