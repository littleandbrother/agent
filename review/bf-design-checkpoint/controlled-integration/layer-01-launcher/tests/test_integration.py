import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import integration as i
from paths import read, sha, digest, write_once


class Cases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'reports')
        self.root = Path(self.temp.name)
        self.binding = i.current_binding()

    def tearDown(self):
        self.temp.cleanup()

    def book(self, assignments=('e1', 'e2'), max_attempts=20):
        return i.AttemptBook(self.root / 'book', assignments, self.binding, max_attempts=max_attempts)

    def test_actual_pi_improver_import_and_invocation(self):
        result = i.run_trusted_fixture(self.book(), 'e1', 'a1')
        self.assertEqual(result['status'], 'activation_pass', result)
        details = result['details']
        actual = i.verify_process_receipt(details)
        self.assertEqual(actual['imports'], ['solver', 'improver'])
        self.assertEqual(actual['invoked'], ['solver.initialState', 'improver.improvementPrompt'])
        self.assertFalse(details['model_prompt_called'])
        self.assertEqual(details['service_requests'], [])
        self.assertFalse(result['scientific_success'])

    def test_actual_pi_solver_prompt_and_local_budget_route(self):
        result = i.run_trusted_fixture(self.book(), 'e1', 'a1', mode='solve')
        self.assertEqual(result['status'], 'activation_pass', result)
        self.assertEqual(i.verify_process_receipt(result['details'])['invoked'], ['solver.initialState', 'solver.solverPrompt'])
        self.assertEqual(result['details']['service_requests'], [{'method': 'GET', 'path': '/api/budget'}])

    def test_relative_output_has_absolute_process_workspace(self):
        relative = self.root.relative_to(ROOT) / 'relative-book'
        book = i.AttemptBook(relative, ('e1',), self.binding)
        receipt = i.run_trusted_fixture(book, 'e1', 'a1', mode='solve')
        self.assertEqual(receipt['status'], 'activation_pass', receipt)
        self.assertTrue(Path(receipt['details']['fresh_workspace']).is_absolute())
        self.assertTrue((Path(receipt['details']['fresh_workspace']) / 'state.json').is_file())
        self.assertEqual(receipt['details']['prospective_contract_errors'], [])

    def test_actual_import_failure_is_not_preimport_success(self):
        result = i.run_trusted_fixture(self.book(), 'e1', 'a1', variant='import-failure')
        self.assertEqual(result['status'], 'import_failed', result)
        events = [json.loads(x) for x in Path(result['details']['trace_file']).read_text().splitlines()]
        self.assertTrue(any(e['type'] == 'harness_loaded' for e in events))
        self.assertFalse(result['details']['activation_passed'])
        self.assertEqual(i.verify_process_receipt(result['details'])['imports'], [])

    def test_actual_invocation_failure_after_successful_import(self):
        result = i.run_trusted_fixture(self.book(), 'e1', 'a1', variant='invoke-failure')
        self.assertEqual(result['status'], 'invocation_failed', result)
        actual = i.verify_process_receipt(result['details'])
        self.assertEqual(actual['imports'], ['solver', 'improver'])
        self.assertEqual(actual['invoked'], [])

    def test_actual_improver_failure_does_not_count_solver_startup(self):
        result = i.run_trusted_fixture(self.book(), 'e1', 'a1', variant='improver-failure')
        self.assertEqual(result['status'], 'invocation_failed', result)
        self.assertEqual(i.verify_process_receipt(result['details'])['invoked'], ['solver.initialState'])

    def test_actual_process_wall_stop(self):
        result = i.run_trusted_fixture(self.book(), 'e1', 'a1', variant='timeout', timeout=2)
        self.assertEqual(result['status'], 'timed_out', result)
        self.assertEqual(result['details']['exit_code'], -9)
        self.assertFalse(result['details']['activation_passed'])

    def test_real_freeze_rejects_typescript_build_failure(self):
        with self.assertRaisesRegex(ValueError, 'CANDIDATE_BUILD_FAILED'):
            i.build_fixture('build-failure')

    def test_build_failure_retained_in_all_attempts(self):
        book = self.book()
        receipt = i.run_trusted_fixture(book, 'e1', 'build-bad', variant='build-failure')
        self.assertEqual(receipt['status'], 'build_failed')
        self.assertFalse(receipt['details']['process_started'])
        self.assertGreater(receipt['details']['local_cost']['wall_seconds'], 0)
        self.assertEqual(book.summary()['episodes'][0]['statuses'], ['build_failed'])

    def test_actual_source_build_and_app_stale_denial(self):
        h = i.build_fixture('h0')
        for target, code in [(h / 'src/solver.ts', 'SOURCE'), (h / 'dist/solver.js', 'BUILD'),
                             (i.PI / 'packages/bf-agent/dist/main.js', 'APP')]:
            original = target.read_bytes()
            try:
                target.write_bytes(original + b'\n// stale\n')
                with self.assertRaisesRegex(ValueError, 'STALE'):
                    i.verify_harness(h, 'h0')
            finally:
                target.write_bytes(original)

    def test_arbitrary_harness_and_variant_denied(self):
        with self.assertRaisesRegex(ValueError, 'ARBITRARY_SOURCE'):
            i.build_fixture('participant-upload')
        with self.assertRaisesRegex(ValueError, 'NONFIXTURE'):
            i.verify_harness('/tmp/arbitrary', 'h0')

    def test_replay_does_not_spawn_another_process(self):
        book = self.book()
        first = i.run_trusted_fixture(book, 'e1', 'a1')
        with mock.patch.object(i.subprocess, 'Popen', side_effect=AssertionError('redispatched')):
            second = i.run_trusted_fixture(book, 'e1', 'a1')
        self.assertEqual(first, second)
        self.assertEqual(book.summary()['attempt_count'], 1)

    def test_recovery_after_receipt_before_journal_has_no_duplicate_effect(self):
        book = self.book()
        first = i.run_trusted_fixture(book, 'e1', 'a1', artifact_only=True)
        self.assertEqual(book.attempts()['a1']['status'], 'unknown')
        with self.assertRaisesRegex(ValueError, 'RECONCILIATION'):
            i.run_trusted_fixture(book, 'e1', 'a1')
        with mock.patch.object(i.subprocess, 'Popen', side_effect=AssertionError('redispatched')):
            self.assertEqual(book.recover('a1'), first)
            self.assertEqual(i.run_trusted_fixture(book, 'e1', 'a1'), first)

    def test_interruption_before_receipt_blocks_same_and_new_attempt(self):
        book = self.book()
        book.begin('e1', 'a1', {'effect': 'unknown'})
        with self.assertRaisesRegex(ValueError, 'RECONCILIATION'):
            book.begin('e1', 'a1', {'effect': 'unknown'})
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_COST'):
            book.begin('e1', 'a2', {'effect': 'new'})
        with self.assertRaisesRegex(ValueError, 'RECONCILIATION'):
            book.recover('a1')
        self.assertEqual(book.summary()['episodes'][1]['statuses'], ['not_started'])

    def test_all_attempt_budget_keeps_failure_and_budget_stop(self):
        book = self.book(max_attempts=1)
        book.begin('e1', 'a1', {})
        book.finish('a1', 'import_failed', {'process_started': False})
        with self.assertRaises(i.BudgetStop):
            book.begin('e1', 'a2', {})
        summary = book.summary()
        self.assertEqual(summary['assigned_episode_count'], 2)
        self.assertEqual(summary['attempt_count'], 2)
        self.assertEqual(summary['episodes'][0]['statuses'], ['import_failed', 'budget_exhausted'])
        self.assertEqual(summary['episodes'][1]['statuses'], ['not_started'])

    def test_idempotency_identity_and_journal_tamper_stop(self):
        book = self.book()
        book.begin('e1', 'a1', {'x': 1})
        with self.assertRaisesRegex(ValueError, 'IDEMPOTENCY'):
            book.begin('e1', 'a1', {'x': 2})
        with self.assertRaises(Exception):
            i.AttemptBook(book.root, ('e1', 'e2'), {**self.binding, 'world_id': 'changed'})
        journal = book.root / 'events.jsonl'
        journal.write_text(journal.read_text().replace('"x":1', '"x":2'))
        with self.assertRaises(Exception):
            book.summary()

    def test_terminal_receipt_tamper_denied(self):
        book = self.book()
        book.begin('e1', 'a1', {})
        book.finish('a1', 'blocked', {'process_started': False})
        target = book.root / book.receipt_file('a1')
        target.write_text(target.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'RECEIPT_TAMPER'):
            book.begin('e1', 'a1', {})

    def test_status_string_cannot_create_activation_without_process(self):
        book = self.book()
        book.begin('e1', 'a1', {})
        with self.assertRaisesRegex(ValueError, 'ACTUAL_PROCESS'):
            book.finish('a1', 'activation_pass', {'process_started': False})

    def test_missing_or_changed_invocation_output_rejected(self):
        receipt = i.run_trusted_fixture(self.book(), 'e1', 'a1')
        original = receipt['details']
        for field in ('output', 'output_hash'):
            details = copy.deepcopy(original)
            path = self.root / (field + '.jsonl')
            events = [json.loads(x) for x in Path(details['trace_file']).read_text().splitlines()]
            next(e for e in events if e.get('phase') == 'invoked').pop(field)
            path.write_text(''.join(json.dumps(e) + '\n' for e in events))
            details['trace_file'] = str(path)
            details['trace_sha256'] = sha(path)
            with self.assertRaisesRegex(ValueError, 'INVOCATION_OUTPUT'):
                i.verify_process_receipt(details)

    def test_nonce_pid_and_preimport_only_receipt_denied(self):
        receipt = i.run_trusted_fixture(self.book(), 'e1', 'a1')
        for field in ('pid', 'nonce', 'binding_hash'):
            details = copy.deepcopy(receipt['details'])
            details['expected'][field] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'BINDING'):
                i.verify_process_receipt(details)
        details = copy.deepcopy(receipt['details'])
        path = self.root / 'preimport.jsonl'
        path.write_text('\n'.join(x for x in Path(details['trace_file']).read_text().splitlines() if 'controlled_activation' not in x) + '\n')
        details['trace_file'] = str(path)
        details['trace_sha256'] = sha(path)
        with self.assertRaisesRegex(ValueError, 'VERDICT'):
            i.verify_process_receipt(details)

    def test_actual_h0_rollback_requires_fresh_h0_invocation(self):
        book = self.book()
        child = i.run_trusted_fixture(book, 'e1', 'h1', variant='h1-manual-fixture')
        restored = i.run_trusted_fixture(book, 'e1', 'rollback', variant='h0')
        h0 = Path(restored['details']['harness_path'])
        h1 = Path(child['details']['harness_path'])
        with self.assertRaisesRegex(ValueError, 'ACTUAL_H0'):
            i.rollback_h0(h0, h1, child)
        receipt = i.rollback_h0(h0, h1, restored)
        self.assertTrue(receipt['exact_h0_restored'])
        self.assertFalse(receipt['generation_created'])
        self.assertNotEqual(child['details']['expected']['pid'], restored['details']['expected']['pid'])

    def test_live_dispatch_fails_before_existing_launcher_grants_or_keys(self):
        with (mock.patch.object(i.launcher, 'launch', side_effect=AssertionError('real dispatch')),
              mock.patch.object(i.launcher.Store, 'grant', side_effect=AssertionError('grant')),
              mock.patch.object(i.launcher.Store, 'issue', side_effect=AssertionError('token'))):
            r = i.live_readiness()
            self.assertEqual(r['qualified_tasks'], 0)
            self.assertIn('ACTUAL_HOST_SEATBELT_UNAVAILABLE', r['blockers'])
            with self.assertRaisesRegex(RuntimeError, 'CONTROLLED_LAUNCH_BLOCKED'):
                i.launch_participant()

    def test_existing_budget_unknown_request_never_retries(self):
        ledger = i.Ledger(self.root / 'fixture-only.sqlite', total=1000000, per_trial=1000000, max_calls=3, max_tokens=100000)
        request = {'max_tokens': 10, 'fixture_only': True}
        self.assertIsNone(ledger.reserve('k1', 'fixture', request))
        with self.assertRaisesRegex(i.BudgetStop, 'uncertain'):
            ledger.reserve('k1', 'fixture', request)
        self.assertEqual(ledger.summary()['unsettled'], 1)
        ledger.db.close()

    def test_existing_budget_conservative_cap_and_settlement(self):
        request = {'max_tokens': 10, 'fixture_only': True}
        small = i.Ledger(self.root / 'small-fixture-only.sqlite', total=1, per_trial=1)
        with self.assertRaises(i.BudgetStop):
            small.reserve('k1', 'fixture', request)
        self.assertEqual(small.summary()['calls'], 0)
        small.db.close()
        ledger = i.Ledger(self.root / 'fixture-only.sqlite', total=1000000, per_trial=1000000)
        ledger.reserve('k1', 'fixture', request)
        receipt = {'fixture_only': True, 'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}}
        ledger.settle('k1', receipt)
        self.assertEqual(ledger.reserve('k1', 'fixture', request), receipt)
        self.assertEqual(ledger.summary()['calls'], 1)
        with self.assertRaisesRegex(i.BudgetStop, 'mutation'):
            ledger.settle('k1', {**receipt, 'changed': True})
        ledger.db.close()

    def test_native_handoff_uses_exact_pipeline_kwargs_and_recheck(self):
        model = {'model_version': 'TEST-ONLY-unqualified', 'world_provider': 'native-LTC3588-1-encrypted-macro',
            'applicability': 'test-only', 'physical_qualified': False, 'source_hashes': {'fixture': 'not-native-evidence'}}
        tools = {**{k: '0' * 64 for k in i.handoff.REQUIRED_TOOL_HASHES},
            'python': 'TEST-ONLY', 'libraries': {'fixture': 'TEST-ONLY'}}
        result = i.prepare_native_handoff({}, model, tools)
        request = result['request']
        self.assertTrue(i.handoff.verify_runtime(request, tools, request['installed_implementation']))
        kwargs = i.handoff.pipeline_kwargs(request, self.root / 'native-output-never-executed', self.root / 'cache')
        self.assertEqual(set(kwargs), {'candidate', 'output', 'cache_root', 'confirm'})
        self.assertFalse(result['native_execution'])
        self.assertFalse(kwargs['output'].exists())
        with self.assertRaises(Exception):
            i.handoff.verify_runtime(request, {**tools, 'host_compiler': 'f' * 64}, request['installed_implementation'])
        with self.assertRaises(Exception):
            i.prepare_native_handoff({}, model, tools, 'DEV-COUPLING-01')


class Lineage(unittest.TestCase):
    def setUp(self):
        self.root = 'a' * 64
        self.child = 'b' * 64
        self.row = {'parent_hash': self.root, 'child_hash': self.child, 'generation': 1,
            'author_kind': 'participant', 'external_manual_edits': [], 'generator_loaded_harness_hash': self.root,
            **{k: 'c' * 64 for k in ('participant_trace_hash', 'patch_hash', 'build_receipt_hash', 'load_receipt_hash', 'public_history_hash', 'generator_invocation_receipt_hash')},
            'changed_paths': ['harness/solver.ts'], 'allowed_paths': ['harness/solver.ts']}
        self.receipt = {'participant_execution': True, 'activated_harness_hash': self.root,
            'post_import': True, 'invoked': True, 'hidden_feedback_exposed': False}
        self.physics = {'source': {'amplitude': 1}, 'initial_state': {'voltage': 0},
            'load_profile': {'load': 1}, 'receiver': {'sensitivity': 1}, 'model_card': {'version': 1},
            'label': 'test', 'deadline_s': 1, 'candidate_designs': [{'capacitance_f': 1, 'esr_ohm': 0}], 'reference_version': 'fixture'}

    def check(self, rows=None, tasks=(), exposed=()):
        self.row['generator_invocation_receipt_hash'] = digest(self.receipt)
        if rows:
            rows = [{**r, 'generator_invocation_receipt_hash': digest(self.receipt)} for r in rows]
        return i.validate_lineage(rows or [self.row], self.root, tasks, exposed, lambda h: self.receipt)

    def test_lineage_consistency_never_self_promotes(self):
        self.assertFalse(self.check()['promotion_granted'])

    def test_wrong_generator_receipt_digest_denied(self):
        with self.assertRaisesRegex(ValueError, 'DIGEST_MISMATCH'):
            i.validate_lineage([self.row], self.root, (), (), lambda h: self.receipt)

    def test_external_manual_h1_cannot_be_participant_h1(self):
        self.row['author_kind'] = 'external_manual'
        with self.assertRaisesRegex(ValueError, 'NOT_PARTICIPANT'):
            self.check()

    def test_noop_and_generation_break_denied(self):
        for field, value in [('child_hash', self.root), ('generation', 2), ('generator_loaded_harness_hash', 'f' * 64)]:
            row = {**self.row, field: value}
            with self.assertRaises(ValueError):
                self.check([row])

    def test_fixture_or_missing_parent_invocation_denied(self):
        for delta in [{'fixture_only': True}, {'invoked': False}, {'activated_harness_hash': 'f' * 64}]:
            old = self.receipt.copy()
            self.receipt.update(delta)
            with self.assertRaises(ValueError):
                self.check()
            self.receipt = old

    def test_hidden_feedback_and_exposed_physics_denied(self):
        self.receipt['hidden_feedback_exposed'] = True
        with self.assertRaisesRegex(ValueError, 'HELDOUT'):
            self.check()
        self.receipt['hidden_feedback_exposed'] = False
        task = i.splits.task_record('blind-fixture', 'blind-transfer', self.physics)
        with self.assertRaisesRegex(ValueError, 'exposed'):
            self.check(tasks=[task], exposed=[task['environment_hash']])

    def test_sibling_final_tasks_cannot_be_relabeled_as_development(self):
        task = i.splits.task_record('dev-fixture', 'development', self.physics, prior_exposure='public')
        hidden = i.splits.task_record('hidden-alias', 'blind-transfer', self.physics)
        with self.assertRaisesRegex(ValueError, 'physical specification'):
            self.check(tasks=[task, hidden])


if __name__ == '__main__':
    unittest.main()
