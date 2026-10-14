import importlib.util
from pathlib import Path
import unittest

from bfworld.agentlab.model_profile import ENGINEERING, OUTPUT64, qualified_owner

spec = importlib.util.spec_from_file_location('original_paper_queue', Path(__file__).resolve().parents[2] / 'scripts/literature_pi_queue.py')
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)


class CandidateQueueOutcomeTests(unittest.TestCase):
    def result(self, execution='IDLE', fresh=None):
        return {'control_route': 'candidate-lifecycle', 'execution': {'status': execution},
                'candidate_lifecycle': {'status': 'CONTINUE', 'intent': {'kind': 'CONTINUE', 'rationale': 'previous attempt'}},
                'candidate_decision_current_attempt': fresh}

    def test_failed_model_cannot_inherit_previous_continue(self):
        value = self.result('FAILED')
        value['execution']['error'] = 'MODEL_OUTPUT_TRUNCATED'
        self.assertEqual(('RUN_FAILED', None), queue.candidate_outcome(value))
        self.assertEqual('previous attempt', value['candidate_lifecycle']['intent']['rationale'])

    def test_no_new_decision_remains_review_required(self):
        self.assertEqual(('CANDIDATE_REVIEW_REQUIRED', None), queue.candidate_outcome(self.result()))

    def test_current_decision_is_used(self):
        decision = {'kind': 'REJECT', 'rationale': 'current evidence'}
        self.assertEqual(('CANDIDATE_REJECT', decision), queue.candidate_outcome(self.result(fresh=decision)))

    def test_current_submission_is_distinct_from_product_pass(self):
        decision = {'kind': 'CONTINUE'}
        value = self.result(fresh=decision)
        value['candidate_lifecycle']['status'] = 'REVIEW_SUBMITTED'
        self.assertEqual(('CANDIDATE_REVIEW_SUBMITTED', decision), queue.candidate_outcome(value))

    def test_output_profile_is_explicit_and_owner_scoped(self):
        qualification = {'original_owner_output_profiles': {'P01-original': OUTPUT64['version']}}
        actual = qualified_owner(ENGINEERING, qualification, 'P01-original')
        self.assertEqual(65536, actual['max_output_tokens'])
        self.assertEqual(ENGINEERING, qualified_owner(ENGINEERING, qualification, 'P02-original'))
        for name in ('thinking', 'reasoning_effort', 'request_bytes', 'target_bytes'):
            self.assertEqual(ENGINEERING[name], actual[name])
        self.assertEqual(32768, ENGINEERING['max_output_tokens'])


if __name__ == '__main__':
    unittest.main()
