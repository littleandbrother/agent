import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
import paths
from paths import read, sha, digest, write_once
import service_adapter as s
import run_probe

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / 'reports')
        self.root = Path(self.tmp.name)
        self.settings = self.root / 'profile.json'
        write_once(self.settings, s.fixture_settings())
        self.service = s.RegistryService(self.root / 'service', self.settings, method_id='strong_generic')
        self.packet = self.service.packet('DEV-FEASIBLE-01')

    def tearDown(self):
        self.tmp.cleanup()

    def upload_body(self, candidate=None):
        return {'files': {'candidate.json': json.dumps(candidate or {})}, 'execution_packet_id': self.packet['packet_id']}

    def upload(self, candidate=None):
        return self.service.snapshot(s.FIXTURE_OWNER, self.upload_body(candidate))

    def job_body(self, upload, operation='op1'):
        return {'task_id': 'DEV-FEASIBLE-01', 'snapshot_id': upload['snapshot_id'],
            'operation_id': operation, 'execution_packet_id': self.packet['packet_id']}

    def kinds(self, name):
        return [r for r in self.service.journal.read() if r['type'] == name]

    def test_exact_registry_task_and_explicit_profile(self):
        task = self.service.public_task(s.FIXTURE_OWNER, 'DEV-FEASIBLE-01')
        self.assertEqual(task['task']['task_id'], 'DEV-FEASIBLE-01')
        self.assertEqual(task['binding']['task_contract_hash'], s.handoff.aw.task_id(self.service.tasks['DEV-FEASIBLE-01']))
        self.assertEqual(task['execution_packet_id'], self.packet['packet_id'])
        self.assertEqual(self.packet['packet_id'], digest({k:v for k,v in self.packet.items() if k != 'packet_id'}))
        self.assertIsNone(self.packet['approved_model'])
        self.assertIsNone(self.packet['approved_budget'])
        self.assertFalse(self.packet['execution_authorized'])

    def test_old_task_aliases_and_operator_bypass_denied(self):
        for task in ['dev-01', 'dev-02', 'rotary-reference', 'transfer-01', 'unknown']:
            with self.assertRaisesRegex(ValueError, 'SOURCE_BOUND_MAGNETIC_REGISTRY'):
                self.service.public_task(s.FIXTURE_OWNER, task)
            with self.assertRaisesRegex(PermissionError, 'NO_PRODUCTION_OR_OPERATOR'):
                self.service.public_task('operator', task)
        with self.assertRaisesRegex(PermissionError, 'OFFLINE_ASSIGNMENT'):
            self.service.packet('DEV-COUPLING-01')

    def test_upload_then_job_is_bound_and_native_tools_remain_absent(self):
        upload = self.upload()
        result = self.service.job(s.FIXTURE_OWNER, self.job_body(upload))
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['execution_packet_id'], self.packet['packet_id'])
        self.assertEqual(result['native_tool_identities'], {})
        self.assertEqual(result['native_prepare_error'], 'TOOL_IDENTITY_MISSING_OR_INVALID:pmic_model')
        self.assertEqual(result['binding']['world_id'], self.packet['world_id'])
        self.assertEqual(result['binding']['evaluator_sha256'], self.packet['evaluator_sha256'])
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(result['native_solver_calls'], 0)
        self.assertFalse(result['scientific_success'])

    def test_exact_uploaded_candidate_bytes_are_retained(self):
        text = ' { "circuit" : { "cin_uF" : 100 } } \n'
        body = {'files': {'candidate.json': text}, 'execution_packet_id': self.packet['packet_id']}
        upload = self.service.snapshot(s.FIXTURE_OWNER, body)
        receipt = read(self.service.root / 'snapshots' / upload['snapshot_id'] / 'receipt.json')
        self.assertEqual(receipt['uploaded_files'], {'candidate.json': text})
        self.assertEqual(receipt['file_hash'], digest(body['files']))
        self.assertEqual(receipt['candidate']['circuit']['cin_uF'], 100)
        self.assertEqual(self.service.job(s.FIXTURE_OWNER, self.job_body(upload))['status'], 'BLOCKED')

    def test_identical_upload_and_job_retry_are_idempotent(self):
        first = self.upload()
        self.assertEqual(first, self.upload())
        body = self.job_body(first)
        result = self.service.job(s.FIXTURE_OWNER, body)
        self.assertEqual(result, self.service.job(s.FIXTURE_OWNER, body))
        self.assertEqual(len(self.kinds('snapshot_intent')), 1)
        self.assertEqual(len(self.kinds('snapshot_complete')), 1)
        self.assertEqual(len(self.kinds('job_intent')), 1)
        self.assertEqual(len(self.kinds('job_blocked')), 1)

    def test_duplicate_operation_with_changed_candidate_denied(self):
        first = self.upload()
        self.service.job(s.FIXTURE_OWNER, self.job_body(first))
        second = self.upload({'circuit': {'cin_uF': 100}})
        with self.assertRaisesRegex(ValueError, 'IDENTITY_CONFLICT'):
            self.service.job(s.FIXTURE_OWNER, self.job_body(second))

    def test_concurrent_identical_job_has_one_durable_attempt(self):
        body = self.job_body(self.upload())
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: self.service.job(s.FIXTURE_OWNER, body), range(2)))
        self.assertEqual(values[0], values[1])
        self.assertEqual(len(self.kinds('job_intent')), 1)

    def test_interrupted_upload_before_artifact_resumes_without_implicit_job(self):
        body = self.upload_body()
        with mock.patch.object(self.service, 'checkpoint', side_effect=RuntimeError('injected interruption')):
            with self.assertRaisesRegex(RuntimeError, 'interruption'):
                self.service.snapshot(s.FIXTURE_OWNER, body)
        sid = digest({'owner': s.FIXTURE_OWNER, 'packet_id': self.packet['packet_id'], 'files': body['files']})
        with self.assertRaisesRegex(ValueError, 'UPLOAD_NOT_DURABLY_COMPLETED'):
            self.service.job(s.FIXTURE_OWNER, self.job_body({'snapshot_id': sid}))
        final = self.service.snapshot(s.FIXTURE_OWNER, body)
        self.assertEqual(final['snapshot_id'], sid)
        self.assertEqual(len(self.kinds('snapshot_intent')), 1)
        self.assertEqual(len(self.kinds('snapshot_complete')), 1)

    def test_interrupted_upload_after_artifact_then_restart(self):
        def fault(label):
            if label == 'snapshot_after_artifact':
                raise RuntimeError('after artifact')
        with mock.patch.object(self.service, 'checkpoint', side_effect=fault):
            with self.assertRaises(RuntimeError):
                self.upload()
        restored = s.RegistryService(self.root / 'service', self.settings, method_id='strong_generic')
        final = restored.snapshot(s.FIXTURE_OWNER, self.upload_body())
        self.assertTrue(final['snapshot_id'])
        self.assertEqual(len(self.kinds('snapshot_intent')), 1)
        self.assertEqual(len(self.kinds('snapshot_complete')), 1)

    def test_partial_upload_artifact_is_never_overwritten_or_dispatched(self):
        def fault(label):
            if label == 'snapshot_after_artifact':
                raise RuntimeError('after artifact')
        with mock.patch.object(self.service, 'checkpoint', side_effect=fault):
            with self.assertRaises(RuntimeError):
                self.upload()
        receipt = next((self.service.root / 'snapshots').glob('*/receipt.json'))
        receipt.write_text('{"partial"')
        with self.assertRaises(json.JSONDecodeError):
            self.upload()
        self.assertEqual(receipt.read_text(), '{"partial"')
        self.assertEqual(len(self.kinds('snapshot_complete')), 0)
        self.assertEqual(len(self.kinds('job_intent')), 0)

    def test_interrupted_job_reconciles_before_and_after_artifact(self):
        upload = self.upload()
        for number, point in enumerate(('job_after_intent', 'job_after_artifact')):
            body = self.job_body(upload, 'op' + str(number))
            def fault(label):
                if label == point:
                    raise RuntimeError('interrupted')
            with mock.patch.object(self.service, 'checkpoint', side_effect=fault):
                with self.assertRaises(RuntimeError):
                    self.service.job(s.FIXTURE_OWNER, body)
            result = self.service.job(s.FIXTURE_OWNER, body)
            self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(len(self.kinds('job_intent')), 2)
        self.assertEqual(len(self.kinds('job_blocked')), 2)

    def test_changed_snapshot_or_job_receipt_fails_closed(self):
        upload = self.upload()
        body = self.job_body(upload)
        result = self.service.job(s.FIXTURE_OWNER, body)
        path = self.service.root / 'jobs' / (result['id'] + '.json')
        value = read(path)
        value['status'] = 'SUCCEEDED'
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'JOB_RECEIPT_TAMPER'):
            self.service.job(s.FIXTURE_OWNER, body)
        snapshot = self.service.root / 'snapshots' / upload['snapshot_id'] / 'receipt.json'
        snapshot.write_text(snapshot.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'UPLOAD_NOT_DURABLY_COMPLETED'):
            self.service.job(s.FIXTURE_OWNER, body)

    def test_packet_budget_and_model_drift_never_rebaseline(self):
        for key in ('budget', 'model'):
            original = self.settings.read_text()
            value = read(self.settings)
            value[key]['changed'] = True
            self.settings.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'STALE_REGISTRY_MODEL_BUDGET_OR_EVALUATOR'):
                self.upload()
            with self.assertRaisesRegex(ValueError, 'UNREVIEWED_RUNTIME_PROFILE'):
                s.RegistryService(self.root / ('changed-' + key), self.settings, method_id='strong_generic')
            self.settings.write_text(original)
        body = self.upload_body()
        body['execution_packet_id'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'PACKET_IDENTITY'):
            self.service.snapshot(s.FIXTURE_OWNER, body)

    def test_prestart_source_modification_rejected_before_packet_or_journal(self):
        fake = self.root / 'fake-first-layer'
        fake.mkdir()
        source = fake / 'registry.json'
        source.write_text('{}')
        write_once(fake / 'INPUT-LOCK.json', {'files': {str(source): sha(source)}})
        write_once(fake / 'FILE-MANIFEST.json', {'files': {}})
        source.write_text('{"changed":true}')
        with mock.patch.object(paths, 'FIRST', fake):
            with self.assertRaisesRegex(ValueError, 'SEALED_INPUT_CHANGED'):
                s.RegistryService(self.root / 'should-not-exist', self.settings, method_id='strong_generic')
        self.assertFalse((self.root / 'should-not-exist').exists())

    def test_local_caps_count_all_job_intents_and_snapshot_intents(self):
        upload = self.upload()
        self.service.job(s.FIXTURE_OWNER, self.job_body(upload, 'a'))
        self.service.job(s.FIXTURE_OWNER, self.job_body(upload, 'b'))
        with self.assertRaisesRegex(ValueError, 'JOB_ATTEMPT_BUDGET_STOP'):
            self.service.job(s.FIXTURE_OWNER, self.job_body(upload, 'c'))
        self.upload({'circuit': {'cin_uF': 100}})
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT_BUDGET_STOP'):
            self.upload({'circuit': {'cin_uF': 110}})
        self.assertTrue(self.kinds('request_rejected'))

    def test_changed_world_input_and_injected_electrical_energy_denied(self):
        for candidate in ({'mechanical': {'opening_s': 1}}, {'circuit': {'initial_vin_V': 1}}, {'circuit': {'diagnostic_input_A': .001}}):
            with self.assertRaises(ValueError):
                self.upload(candidate)
        self.assertEqual(len(self.kinds('snapshot_intent')), 0)

    def test_actual_http_handler_denies_model_solve_and_submit(self):
        with (mock.patch.object(s.server, 'Workbench', side_effect=AssertionError('legacy initialization')),
              mock.patch.object(s.server.Provider, 'complete', side_effect=AssertionError('provider')),
              self.service.serve() as url):
            for route in ('/v1/chat/completions', '/api/solve', '/api/submit'):
                request = Request(url + route, data=b'{}', headers={'Authorization': 'Bearer ' + s.FIXTURE_BEARER, 'Content-Type': 'application/json'})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 403)
                self.assertIn(b'QUALIFICATION_REQUIRED', caught.exception.read())
            request = Request(url + '/api/tasks/dev-01', headers={'Authorization': 'Bearer ' + s.FIXTURE_BEARER})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=5)
            self.assertEqual(caught.exception.code, 400)

    def test_overlay_legacy_launcher_is_disabled_before_grants(self):
        with mock.patch.object(run_probe.launcher.Store, 'grant', side_effect=AssertionError('grant')):
            with self.assertRaisesRegex(RuntimeError, 'LEGACY_LAUNCH_DISABLED'):
                run_probe.launcher.launch('/nonexistent')

    def test_node_rejects_changed_packet_content_with_old_id_before_activation(self):
        for field in ('model', 'budget'):
            packet = copy.deepcopy(self.packet)
            packet['runtime_profile'][field]['unexpected'] = 'tampered'
            config = {'workspace': str(self.root), 'taskId': 'DEV-FEASIBLE-01', 'dryRun': True,
                'executionPacket': packet}
            process = subprocess.run([run_probe.launcher.NODE, str(paths.PI / 'packages/bf-agent/dist/main.js'), '-'],
                input=json.dumps(config), text=True, capture_output=True, timeout=15,
                env={'PATH': str(Path(run_probe.launcher.NODE).parent) + ':/usr/bin:/bin', 'HOME': str(self.root)})
            self.assertNotEqual(process.returncode, 0)
            self.assertIn('EXECUTION_PACKET_CONTENT_HASH_MISMATCH', process.stderr)
            self.assertNotIn('harness_loaded', process.stdout)

    def test_rehashed_changed_model_or_budget_packet_rejected_by_actual_service(self):
        harness = run_probe.launcher.freeze(source=paths.PI / 'packages/bf-harness', label='EXPLICIT-PACKET-H0-v2', home_root=ROOT / 'fixture-runtime')
        manifest = read(harness / 'manifest.json')
        for field in ('model', 'budget'):
            workspace = self.root / ('mutated-' + field)
            workspace.mkdir()
            (workspace / '.pi').mkdir()
            packet = copy.deepcopy(self.packet)
            if field == 'model':
                packet['runtime_profile']['model']['max_output_tokens'] = 512
            else:
                packet['runtime_profile']['budget']['wall_seconds'] = 20
            packet['packet_id'] = digest({k:v for k,v in packet.items() if k != 'packet_id'})
            config = {'workspace': str(workspace), 'taskId': 'DEV-FEASIBLE-01', 'mode': 'solve', 'dryRun': True,
                'executionPacket': packet, 'token': s.FIXTURE_BEARER, 'sourceManifest': manifest,
                'solverModule': str(harness / 'dist/solver.js'), 'improverModule': str(harness / 'dist/improver.js'),
                'controlledActivation': {'nonce': 'trusted-negative', 'harnessSourceHash': manifest['source_hash'],
                    'appBuildHash': manifest['app_build_hash'], 'loaded': {k:manifest['loaded_modules'][k] for k in ('solver','improver')},
                    'bindingHash': digest(packet)}}
            with self.service.serve() as url:
                config['service'] = url
                process = subprocess.run([run_probe.launcher.NODE, str(paths.PI / 'packages/bf-agent/dist/main.js'), '-'],
                    input=json.dumps(config), text=True, capture_output=True, timeout=15,
                    env={'PATH': str(Path(run_probe.launcher.NODE).parent) + ':/usr/bin:/bin', 'HOME': str(workspace)})
            self.assertNotEqual(process.returncode, 0)
            self.assertIn('SERVICE_BUDGET_PACKET_MISMATCH', process.stderr)
            self.assertNotIn('controlled_runtime_configuration', process.stdout)

    def test_real_pi_registered_tool_to_real_handler_and_native_handoff_block(self):
        result = run_probe.run(self.root / 'end-to-end', 'strong_generic')
        self.assertEqual(result['status'], 'transport_and_identity_pass_native_blocked')
        self.assertEqual(result['task_id'], 'DEV-FEASIBLE-01')
        self.assertEqual(result['invoked'], ['solver.initialState', 'solver.solverPrompt'])
        self.assertEqual(result['native_tool_identities'], {})
        self.assertEqual(result['model_calls'], 0)
        self.assertFalse(result['autonomous_participant'])
        events = [json.loads(line) for line in (self.root / 'end-to-end/process/stdout.jsonl').read_text().splitlines()]
        probe = next(e for e in events if e.get('type') == 'trusted_controller_probe')
        self.assertEqual(probe['tool_name'], 'bf_experiment')
        self.assertEqual(probe['arguments'], {'operation_id': 'trusted-controller-probe-1'})

class TraceReadbackTests(unittest.TestCase):
    def setUp(self):
        run = ROOT / 'reports/probe-v3'
        if not run.exists():
            run = ROOT / 'reports/probe-v1'
        self.events = [json.loads(x) for x in (run / 'process/stdout.jsonl').read_text().splitlines()]
        self.packet = read(run / 'EXECUTION-PACKET.json')
        self.manifest = next(e['source'] for e in self.events if e['type'] == 'harness_loaded')
        first = next(e for e in self.events if e['type'] == 'controlled_activation')
        self.pid, self.nonce = first['pid'], first['nonce']

    def check(self, events):
        return run_probe.validate_trace(events, self.packet, self.manifest, self.pid, self.nonce, 0)

    def test_missing_activation_is_not_tool_or_transport_success(self):
        self.assertEqual(self.check(self.events)['status'], 'BLOCKED')
        with self.assertRaisesRegex(ValueError, 'EXACT_POST_IMPORT'):
            self.check([e for e in self.events if e['type'] != 'controlled_activation'])

    def test_wrong_registered_tool_or_arguments_denied(self):
        for field, value in [('tool_name', 'fake_tool'), ('arguments', {'operation_id': 'wrong'})]:
            events = copy.deepcopy(self.events)
            next(e for e in events if e['type'] == 'trusted_controller_probe')[field] = value
            with self.assertRaisesRegex(ValueError, 'EXACT_REGISTERED_TOOL'):
                self.check(events)

    def test_wrong_task_binding_or_duplicate_completion_denied(self):
        events = copy.deepcopy(self.events)
        next(e for e in events if e['type'] == 'controlled_task_bound')['binding']['world_id'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'EXACT_TASK_PACKET'):
            self.check(events)
        events = self.events + [next(e for e in self.events if e['type'] == 'session_complete')]
        with self.assertRaisesRegex(ValueError, 'EXACT_ZERO_MODEL_COMPLETION'):
            self.check(events)

if __name__ == '__main__':
    unittest.main()
