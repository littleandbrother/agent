import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bfworld.kernel.canonical import canonical_hash, write_canonical_json
from bfworld.coupled.profiled_artifacts import seal_run
from bfworld.campaign.task_context import execute_candidate, public_context
from bfworld.campaign.splits import task_record
from bfworld.campaign.qualification import receipt, activated_components
from bfworld.campaign.workflow_use import (
    VERSION, CANDIDATE_VERSION, execute_qualification, component_receipt,
    scoped_route, execution_pins, policy_use)
from test_b2_scientific import fixture


def workflow(descending=False):
    return {'schema_version': CANDIDATE_VERSION, 'kind': 'workflow',
            'scope': {'source_families': ['rotary'], 'context_versions': ['profiled-predictor-context-v2']},
            'workflow': {'schema_version': 'harness-patch-v1', 'kind': 'workflow', 'policy': {
                'order_by': 'capacitance_f', 'descending': descending,
                'require_transient_before_submit': True, 'stop_after_verified': True}}}


class WorkflowUseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_tmp = tempfile.TemporaryDirectory(); cls.source = Path(cls.source_tmp.name)
        cls.tasks, scientific, _ = fixture()
        cls.plan = {'schema_version': VERSION, 'purpose': 'engineering-controls',
                    'task_manifest_hash': canonical_hash(cls.tasks), 'reference_version': scientific['reference_version'],
                    'use_ids': scientific['use_ids'], 'regression_ids': scientific['regression_ids'],
                    'baseline': workflow(), 'thresholds': {'min_median_probe_reduction': 1,
                        'max_false_admissions': 0, 'retain_all_solvable': True},
                    'regression_probe_ceiling': scientific['regression_probe_ceiling'],
                    'oos_contexts': scientific['oos_contexts'] + [{}, None], 'max_reference_observations': 4}
        cls.evidence = []
        for task in cls.tasks[1:]:
            for design in task['physics']['candidate_designs']:
                run = execute_candidate(task, design['id']); bundle = seal_run(cls.source/'runs', run)
                cls.evidence.append({'task_id': task['task_id'], 'candidate_id': design['id'],
                    'artifact': str(bundle.relative_to(cls.source)), 'run_hash': run['content_hash']})
        cls.acquisition = {'complete': True, 'source_hash': canonical_hash(cls.evidence),
                           'scope': 'isolated hand-authored unpaid fixture, not a real campaign'}

    @classmethod
    def tearDownClass(cls): cls.source_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.tasks = copy.deepcopy(type(self).tasks); self.plan = copy.deepcopy(type(self).plan)
        self.evidence = copy.deepcopy(type(self).evidence); self.candidate = workflow(True)
        self.acquisition = copy.deepcopy(type(self).acquisition)

    def tearDown(self): self.tmp.cleanup()

    def run_fixture(self, **kw):
        return execute_qualification(self.candidate, self.tasks, self.plan, self.evidence,
                                     self.acquisition, self.source, self.root, **kw)

    def test_independent_use_gain_is_not_formal_or_agent_qualification(self):
        result = self.run_fixture()
        self.assertTrue(result['controls_pass'], result['checks'])
        self.assertEqual(result['metrics']['median_probe_reduction'], 1)
        self.assertEqual(result['metrics']['candidate_policy_probes'], 2)
        self.assertEqual(result['cost']['new_reference_runs'], 0)
        self.assertEqual(result['cost']['imported_reference_observations'], 4)
        self.assertFalse(result['qualified']); self.assertFalse(result['agent_use_benefit_measured'])
        self.assertIsNone(result['world_receipt_dependency'])
        world = {'code': 'invalid world model'}
        active = activated_components(world, receipt('world-model', world, False, {}),
                                      self.candidate, component_receipt(result, self.candidate))
        self.assertIsNone(active['world-model']); self.assertIsNone(active['workflow'])
        # World rejection did not prevent measuring workflow usefulness, but
        # independent engineering success still cannot promote either component.

    def test_no_gain_and_regression_are_separate_failure_reasons(self):
        self.candidate = workflow()
        result = self.run_fixture()
        self.assertEqual(result['metrics']['median_probe_reduction'], 0)
        self.assertTrue(result['checks']['retains_solvability'])
        self.assertFalse(result['checks']['use']); self.assertFalse(result['checks']['regression'])

    def test_regression_loss_cannot_be_hidden_by_use_gain(self):
        self.plan['regression_probe_ceiling']['regression-fixture'] = 0
        result = self.run_fixture()
        self.assertTrue(result['checks']['use']); self.assertFalse(result['checks']['regression'])
        self.assertFalse(result['controls_pass'])

    def test_scope_abstention_that_loses_solvable_tasks_is_rejected(self):
        self.candidate['scope']['source_families'] = ['solar']
        result = self.run_fixture()
        self.assertFalse(result['checks']['retains_solvability'])
        self.assertEqual(len(result['metrics']['lost_solvable_tasks']), 2)
        self.assertIsNone(result['metrics']['median_probe_reduction'])

    def test_scope_must_not_execute_outside_domain(self):
        self.candidate['scope']['source_families'].append('solar')
        result = self.run_fixture()
        self.assertFalse(result['checks']['scope'])
        self.assertTrue(result['checks']['use'])

    def test_weak_baseline_cannot_manufacture_benefit(self):
        self.plan['baseline']['scope']['source_families'] = ['solar']
        result = self.run_fixture()
        self.assertFalse(result['checks']['baseline_retains_solvability'])
        self.assertFalse(result['controls_pass'])

    def test_complete_evidence_and_exact_task_binding_required(self):
        self.evidence.pop()
        with self.assertRaisesRegex(ValueError, 'complete unique'): self.run_fixture()
        self.evidence = copy.deepcopy(type(self).evidence)
        self.evidence[0]['candidate_id'], self.evidence[1]['candidate_id'] = (
            self.evidence[1]['candidate_id'], self.evidence[0]['candidate_id'])
        with self.assertRaisesRegex(ValueError, 'misbound'): self.run_fixture()

    def test_path_escape_and_draft_authority_stop(self):
        self.evidence[0]['artifact'] = '../escaped'
        with self.assertRaisesRegex(ValueError, 'escaped'): self.run_fixture()
        self.evidence = copy.deepcopy(type(self).evidence)
        self.plan['purpose'] = 'formal-workflow-qualification'
        with self.assertRaisesRegex(ValueError, 'owner-approved'): self.run_fixture(protocol={})

    def test_missing_scope_and_safety_change_fail_before_evidence_access(self):
        self.candidate['scope']['source_families'] = []
        with patch('bfworld.campaign.workflow_use._observations', side_effect=AssertionError('truth reached')):
            with self.assertRaisesRegex(ValueError, 'mechanical'): self.run_fixture()
        self.candidate = workflow(True)
        self.candidate['workflow']['policy']['require_transient_before_submit'] = False
        with self.assertRaisesRegex(ValueError, 'mechanical'): self.run_fixture()

    def test_replay_rechecks_projection_without_solver_or_paid_calls(self):
        result = self.run_fixture()
        with patch('bfworld.coupled.profiled.execute', side_effect=AssertionError('solver ran')):
            self.assertEqual(result, self.run_fixture())
        result['rows'][0]['workflow']['probes'] = 0
        result.pop('content_hash'); result['content_hash'] = canonical_hash(result)
        write_canonical_json(self.root/'report.json', result)
        with self.assertRaisesRegex(ValueError, 'projection'): self.run_fixture()

    def test_engineering_self_promotion_and_incomplete_acquisition_denied(self):
        self.acquisition['complete'] = False
        result = self.run_fixture()
        self.assertTrue(result['controls_pass'])
        self.assertFalse(result['checks']['complete_acquisition_cost'])
        self.assertFalse(component_receipt(result, self.candidate)['passed'])
        result['qualified'] = True; result.pop('content_hash'); result['content_hash'] = canonical_hash(result)
        with self.assertRaisesRegex(ValueError, 'self-promoted'): component_receipt(result, self.candidate)

    def test_candidate_order_invariance_infeasible_abstention_and_evidence_safety(self):
        ctx = public_context(self.tasks[1]); altered = copy.deepcopy(ctx); altered['candidates'].reverse()
        facts = {c['id']: {'physical_pass': False, 'run_hash': 'sha256:control'} for c in ctx['candidates']}
        result = policy_use(self.candidate, ctx, facts)
        self.assertEqual(result, policy_use(self.candidate, altered, facts))
        self.assertEqual(result['probes'], 2); self.assertFalse(result['success'])
        self.assertEqual(result['terminal']['action'], 'abstain')
        with self.assertRaisesRegex(ValueError, 'completed'):
            scoped_route(self.candidate, ctx, [], ['large'])

    def test_pins_include_workflow_scope_baseline_cost_and_evidence(self):
        before = execution_pins(self.candidate, self.tasks, self.plan, self.evidence, self.acquisition)
        self.candidate['scope']['source_families'].append('solar')
        self.assertNotEqual(before, execution_pins(self.candidate, self.tasks, self.plan, self.evidence, self.acquisition))
        self.plan['baseline'] = workflow(True)
        self.assertNotEqual(before['plan_hash'], canonical_hash(self.plan))

    def _formal_fixture(self):
        # An isolated authority fixture exercises the gate, never authorizes a
        # real campaign or makes these test-generated conditions scientifically hidden.
        from test_b2_repair_bridge import fixture_protocol
        t = self.tasks[1]
        self.tasks[1] = task_record(t['task_id'], 'qualification', t['physics'])
        self.plan['task_manifest_hash'] = canonical_hash(self.tasks)
        self.plan['purpose'] = 'formal-workflow-qualification'
        p = fixture_protocol()
        p['workflow_qualification_execution'] = execution_pins(
            self.candidate, self.tasks, self.plan, self.evidence, self.acquisition)
        p['owner_approval'] = {'approval_id': 'TEST-ONLY-NOT-PRODUCTION-AUTHORITY',
                              'protocol_hash': canonical_hash({k: v for k, v in p.items() if k != 'owner_approval'})}
        return p

    def test_isolated_protocol_fixture_qualifies_workflow_without_world(self):
        p = self._formal_fixture()
        result = self.run_fixture(protocol=p)
        self.assertTrue(result['qualified']); self.assertFalse(result['agent_use_benefit_measured'])
        world = {'invalid': True}
        active = activated_components(world, receipt('world-model', world, False, {}), self.candidate,
                                      component_receipt(result, self.candidate))
        self.assertIsNone(active['world-model']); self.assertEqual(active['workflow'], self.candidate)

    def test_formal_window_expiry_and_exact_policy_pins_fail_closed(self):
        p = self._formal_fixture()
        self.plan['baseline'] = workflow(True)
        with self.assertRaisesRegex(ValueError, 'bind exact'): self.run_fixture(protocol=p)
        self.plan['baseline'] = workflow()
        p['shared_budget']['new_campaign_execution_window'] = {'starts_unix_s': 1, 'ends_unix_s': 2}
        p['owner_approval']['protocol_hash'] = canonical_hash({k: v for k, v in p.items() if k != 'owner_approval'})
        with self.assertRaisesRegex(ValueError, 'window expired'): self.run_fixture(protocol=p)


if __name__ == '__main__': unittest.main()
