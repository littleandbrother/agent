import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from bfworld.agentlab.literature_rsi import CONFIG, check_authorization, comparison, evaluate_answer, expected, load, qualify_candidate, sha, validate_billing_liabilities, verify_prepared, write_once
from bfworld.agentlab.store import identity


class LiteratureRSITest(unittest.TestCase):
    def setUp(self):
        self.tasks = load(CONFIG)['tasks']
        self.source = {'assets': {'article.pdf': {'sha256': 'a'*64}}}

    def answer(self, task):
        return {'schema_version': 'bf-literature-engineering-answer-v1', 'task_id': task['id'],
                'source_sha256': 'a'*64, 'values': expected(task), 'boundaries': dict(task['required_boundaries']),
                'source_locators': ['article p8']}

    def test_classical_reference_and_units(self):
        # These independent hand calculations distinguish microfarads, millifarads
        # and average power from the peak-duration assumption used in real papers.
        first, second, third = [expected(t) for t in self.tasks]
        self.assertAlmostEqual(first['component_total_uW'], 94.41)
        self.assertAlmostEqual(first['component_nominal_margin_uW'], 16.37)
        self.assertEqual(second['selected_capacitance_uF'], 1000)
        self.assertAlmostEqual(second['usable_energy_uJ'], 3328)
        self.assertAlmostEqual(third['stored_energy_J'], .1299375)
        self.assertAlmostEqual(third['idle_window_energy_J'], .04752)
        self.assertLess(third['maximum_total_active_s'], .665)

    def test_participant_claims_do_not_certify(self):
        task = self.tasks[0]; answer = self.answer(task)
        self.assertEqual(evaluate_answer(task, self.source, answer)['status'], 'PASS')
        answer.update(status='PASS', passed=True)
        answer['values']['component_total_uW'] = 35.51
        self.assertEqual(evaluate_answer(task, self.source, answer)['status'], 'FAIL')

    def test_identity_manual_and_physical_boundaries(self):
        task = self.tasks[0]
        for key, value in [('source_sha256', 'b'*64), ('task_id', 'other')]:
            answer = self.answer(task); answer[key] = value
            self.assertEqual(evaluate_answer(task, self.source, answer)['status'], 'FAIL')
        for key in ['manual_start_preserved', 'physical_verified', 'device_identity_resolved']:
            answer = self.answer(task); answer['boundaries'][key] = not answer['boundaries'][key]
            self.assertEqual(evaluate_answer(task, self.source, answer)['status'], 'FAIL')

    def test_nonfinite_boolean_and_unit_answers_fail(self):
        task = self.tasks[2]
        for bad in [True, float('nan'), float('inf'), 129.9375]:
            answer = self.answer(task); answer['values']['stored_energy_J'] = bad
            self.assertEqual(evaluate_answer(task, self.source, answer)['status'], 'FAIL')

    def test_budget_cannot_be_inferred_or_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(FileNotFoundError):
                check_authorization(root)
            write_once(root/'authorization.json', {'max_usd': 30, 'expires_at_utc': '2026-10-08T21:34:33Z', 'max_solver_traces': 6, 'max_candidates': 2})
            _, expiry = check_authorization(root, at=1)
            for kwargs in [dict(at=expiry), dict(at=1, spent=30), dict(at=1, solver_traces=7), dict(at=1, candidates=3)]:
                with self.assertRaises(ValueError):
                    check_authorization(root, **kwargs)
            with self.assertRaises(FileExistsError):
                write_once(root/'authorization.json', {})

    def test_candidate_cannot_touch_evaluator_or_hidden_feedback(self):
        candidate = {'target': 'literature_method_overlay', 'instruction': 'Check unit scales and source scope.',
                     'hypothesis': 'Unit mistakes decline.', 'falsifier': 'New variant still has unit mistakes.',
                     'applies_to': 'Stored energy tasks.', 'evidence_trials': ['M0-ledger']}
        result = qualify_candidate(candidate, ['M0-ledger'])
        self.assertFalse(result['adopted'])
        for change in [{'target': 'evaluator'}, {'evidence_trials': ['M0-transfer']}]:
            with self.assertRaises(ValueError):
                qualify_candidate({**candidate, **change}, ['M0-ledger'])

    def test_one_task_cannot_masquerade_as_transfer(self):
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE'):
            comparison([])
        pairs = [{'task': t['id'], 'split': t['split'], 'parent': {'task_sha256': 'same', 'environment_sha256': 'env', 'evaluation': {'status': 'PASS'}}, 'child': {'task_sha256': 'same', 'environment_sha256': 'env', 'evaluation': {'status': 'PASS'}}} for t in self.tasks]
        result = comparison(pairs)
        self.assertEqual(result['status'], 'NO_MEASURED_BENEFIT')
        self.assertFalse(result['recursive_self_improvement_claim'])
        pairs[1]['child']['task_sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'TASK_MISMATCH'):
            comparison(pairs)

    def test_specific_unknown_liability_never_covers_new_requests(self):
        old = {'id': 'first', 'status': 'UNKNOWN', 'reserved': .0494139, 'charged': 0}
        permitted = [{'id': old['id'], 'original_row_sha256': identity(old)}]
        validate_billing_liabilities([old], permitted)
        for rows in [[{**old, 'charged': .001}], [old, {**old, 'id': 'new'}]]:
            with self.assertRaisesRegex(ValueError, 'NEW_UNKNOWN'):
                validate_billing_liabilities(rows, permitted)

    def test_prepared_source_tampering_stops_before_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'article.pdf').write_bytes(b'original source')
            write_once(root/'sources.json', {'papers': [{'assets': {'article.pdf': {'path': 'article.pdf', 'sha256': sha(root/'article.pdf')}}}]})
            write_once(root/'prepared.json', {'harness': str(root/'unused'), 'files': {'sources.json': sha(root/'sources.json')}, 'evaluator_sha256': sha(__import__('bfworld.agentlab.literature_rsi', fromlist=['']).__file__)})
            with patch('bfworld.agentlab.literature_rsi.verify_method') as method:
                verify_prepared(root)
                self.assertEqual(method.call_count, 1)
                (root/'article.pdf').write_bytes(b'changed source')
                with self.assertRaisesRegex(ValueError, 'SOURCE_CONTENT_TAMPER'):
                    verify_prepared(root)
                self.assertEqual(method.call_count, 1)


if __name__ == '__main__':
    unittest.main()
