import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash
from bfworld.coupled.engine import Design, Reference
from bfworld.coupled.profiled import LoadProfile
from bfworld.campaign.task_context import physics_for, execute_candidate, public_context
from bfworld.campaign.splits import task_record
from bfworld.campaign.trials import history_from_runs, proposal_request
from bfworld.campaign.proposal import SemanticProposalAdapter, proposal_pins, inspect_proposal
from bfworld.campaign.budget import Ledger, BudgetStop

sys.path.insert(0, str(Path(__file__).parent))
from test_b2_repair_bridge import FakeTransport, fixture_protocol, INITIAL, VALID


class SemanticProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.task = task_record('public-history', 'development', physics_for({'a': Design()}, Reference(), LoadProfile()), prior_exposure='public')
        self.history = history_from_runs([(self.task, 'a', execute_candidate(self.task, 'a'))])
        self.request = proposal_request(self.history, INITIAL, generation='G3')
        self.protocol = fixture_protocol()
        self.protocol['proposal_execution'] = {**proposal_pins(self.request), 'model_fingerprint': 'fixture-fingerprint'}
        self.approve_fixture()
        self.packet = {'decision': 'propose', 'world_model': INITIAL, 'text_lesson': 'No transferable model yet; preserve observed limits.',
                       'workflow': {'schema_version': 'harness-patch-v1', 'kind': 'workflow', 'policy': {'order_by': 'capacitance_f', 'descending': False, 'require_transient_before_submit': True, 'stop_after_verified': True}},
                       'source_run_hashes': [self.history['records'][0]['facts']['run_hash']], 'decision_summary': 'Isolated fixture, not generated scientific knowledge.'}
        self.ledger = Ledger(self.root/'.bfworld/paid-campaign/cost.sqlite')
        self.fake = FakeTransport(self.ledger, [json.dumps(self.packet)])

    def approve_fixture(self):
        self.protocol['owner_approval'] = {'protocol_hash': canonical_hash({k: v for k, v in self.protocol.items() if k != 'owner_approval'}),
                                           'approval_id': 'TEST-ONLY-NOT-PRODUCTION'}

    def adapter(self):
        return SemanticProposalAdapter(self.protocol, self.root, self.request, self.history, self.fake, self.root/'adapter')

    def tearDown(self):
        self.ledger.db.close(); self.temp.cleanup()

    def test_semantic_request_uses_one_settled_effect_and_separate_component_triage(self):
        a = self.adapter(); response = a(self.request)
        self.assertEqual(a.reconcile(self.request), response)
        self.assertEqual(a(self.request), response)
        self.assertEqual(self.fake.requests, 1)
        result = inspect_proposal(response, self.request, [public_context(self.task)], self.root/'sandbox')
        self.assertFalse(result['world_mechanical']['passed'])
        self.assertTrue(result['workflow_safety']['passed'])
        self.assertFalse(result['scientific_qualified'])
        self.assertEqual(result['cost_receipt']['usage_tokens'], 150)

    def test_unapproved_or_drifted_pin_stops_before_dispatch(self):
        for change in ('draft', 'pin', 'window'):
            p = copy.deepcopy(self.protocol)
            if change == 'draft': self.protocol['status'] = 'draft-not-authorized'
            if change == 'pin': self.protocol['proposal_execution']['request_hash'] = 'sha256:wrong'
            if change == 'window': self.protocol['shared_budget']['new_campaign_execution_window']['ends_unix_s'] = 1
            self.approve_fixture()
            with self.assertRaises(BudgetStop): self.adapter()(self.request)
            self.protocol = p
        self.assertEqual(self.fake.requests, 0)
        self.assertEqual(self.ledger.summary()['calls'], 0)

    def test_extra_feedback_and_false_source_citations_fail(self):
        altered = {**self.request, 'hidden': True}
        with self.assertRaisesRegex(BudgetStop, 'additional'):
            self.adapter()(altered)
        response = self.adapter()(self.request)
        response['candidate']['source_run_hashes'] = ['sha256:invented']
        with self.assertRaisesRegex(ValueError, 'citations'):
            inspect_proposal(response, self.request, [public_context(self.task)], self.root/'sandbox')

    def test_no_update_is_not_rejection_or_promotion(self):
        self.packet.update(decision='no-update', world_model=None, workflow=None)
        self.fake.outputs = [json.dumps(self.packet)]
        result = inspect_proposal(self.adapter()(self.request), self.request, [public_context(self.task)], self.root/'sandbox')
        self.assertIsNone(result['world_mechanical'])
        self.assertIsNone(result['workflow_safety'])
        self.assertFalse(result['scientific_qualified'])

    def test_unknown_transport_is_not_retried(self):
        self.fake.failure = BudgetStop('fixture transport interruption')
        a = self.adapter()
        with self.assertRaises(BudgetStop): a(self.request)
        with self.assertRaisesRegex(BudgetStop, 'uncertain'): a.reconcile(self.request)
        self.assertEqual(self.fake.requests, 1)
        self.assertEqual(self.ledger.summary()['unsettled'], 1)

    def test_world_mechanical_pass_does_not_require_workflow_acceptance(self):
        self.packet.update(world_model=VALID)
        self.packet['workflow']['policy']['require_transient_before_submit'] = False
        self.fake.outputs = [json.dumps(self.packet)]
        result = inspect_proposal(self.adapter()(self.request), self.request, [public_context(self.task)], self.root/'sandbox')
        self.assertTrue(result['world_mechanical']['passed'])
        self.assertFalse(result['workflow_safety']['passed'])
        self.assertFalse(result['scientific_qualified'])


if __name__ == '__main__': unittest.main()
