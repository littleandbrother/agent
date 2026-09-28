import unittest
from scripts.check_pilot_readiness import readiness,REPO
import yaml

class PilotReadinessTests(unittest.TestCase):
    def test_no_launch_without_real_identity_budget_and_isolation(self):
        protocol=yaml.safe_load((REPO/'studies/protocols/fixed-model-pilot.yaml').read_text())
        protocol['budget']['max_paid_cost']=None
        result=readiness(protocol)
        self.assertFalse(result['launchable']);self.assertEqual(result['external_calls_made'],0)
        self.assertTrue(any('budget' in b for b in result['blockers']))
    def test_final_feedback_leak_is_blocker(self):
        protocol=yaml.safe_load((REPO/'studies/protocols/fixed-model-pilot.yaml').read_text());protocol['history_and_evaluation']['final_feedback_to_evolver']=True
        self.assertIn('sealed final feedback leak',readiness(protocol)['blockers'])
