"""Negative controls for the trusted consumer; fixtures are not BF experiments."""
import unittest
import tempfile
from pathlib import Path
from bfworld.agentlab.campaign20261019.phase2 import consume, design, authoritative_consume
from bfworld.agentlab.campaign20261019.common import digest


class TrustedConsumerTests(unittest.TestCase):
    current = {'capacitance_f': 10e-6, 'tx_not_before_s': .045}
    selected = {'capacitance_f': 10e-6, 'tx_not_before_s': 0}

    def test_missing_and_self_signed_authority_are_unknown(self):
        policy = [{'equals': 'volatile', 'design': self.selected}]
        self.assertEqual(consume(None, policy, self.current)['judgment'], 'UNKNOWN')
        forged = {'qualification': 'EXTERNAL_PASS', 'value': 'volatile'}
        self.assertFalse(consume(forged, policy, self.current)['used_observation'])

    def test_actual_registry_value_selects_typed_design(self):
        observation = {'qualification': 'EXTERNAL_PASS', 'value': 'volatile'}
        registry = {digest(observation): observation}
        policy = [{'equals': 'volatile', 'design': self.selected}]
        result = consume(observation, policy, self.current, registry=registry)
        self.assertEqual(result['design'], self.selected)
        self.assertTrue(result['used_observation'])
        changed = {**observation, 'value': 'passive-mechanical'}
        self.assertEqual(consume(changed, policy, self.current, registry=registry)['judgment'], 'UNKNOWN')
        self.assertEqual(self.current['tx_not_before_s'], .045)

    def test_boolean_does_not_alias_integer_branch(self):
        observation = {'qualification': 'EXTERNAL_PASS', 'value': True}
        policy = [{'equals': 1, 'design': self.selected}]
        self.assertEqual(consume(observation, policy, self.current,
                         registry={digest(observation): observation})['judgment'], 'UNKNOWN')

    def test_out_of_domain_and_physics_overwrite_are_rejected(self):
        for value in ({**self.selected, 'capacitance_f': 1},
                      {**self.selected, 'tx_not_before_s': -.1},
                      {**self.selected, 'event_latch': 'passive-mechanical'},
                      {**self.selected, 'capacitance_f': float('nan')}):
            with self.assertRaises(ValueError):
                design(value)

    def test_unmatched_or_unqualified_value_leaves_current_design(self):
        policy = [{'equals': 'x', 'design': self.selected}]
        for obs in ({'value': 'x'}, {'value': 'y', 'qualification': 'EXTERNAL_PASS'}):
            self.assertEqual(consume(obs, policy, self.current,
                      registry={digest(obs): obs})['design'], self.current)

    def test_external_source_tampering_rejected_before_execution(self):
        class FixtureStore:
            executed = False
            def source(self, source_id, world=None):
                return {'source_sha256':'verified-source','parent_sha256':'verified-parent'}
            def execute(self, *args):
                self.executed = True
                raise AssertionError('Must not execute')
        store = FixtureStore()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'ACQUISITION_SOURCE_TAMPERED'):
                authoritative_consume({'source_id':'fixture'}, [],
                    {'source_sha256':'forged','parent_sha256':'verified-parent'},
                    None, self.current, store, Path(d))
        self.assertFalse(store.executed)

    def test_uninformative_relation_is_rejected_before_consumer_or_run(self):
        class FixtureStore:
            executed = False
            def source(self, source_id, world=None):
                return {'source_sha256':'source','parent_sha256':'parent','payload':{'constant':1},'field_units':{'/constant':'1'}}
            def execute(self,*args):
                self.executed = True
                raise AssertionError('Must not execute')
        store = FixtureStore()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'UNINFORMATIVE'):
                authoritative_consume({'source_id':'fixture','domain':{'fixture':True}},
                    [{'equals':1,'design':self.selected}],
                    {'source_sha256':'source','parent_sha256':'parent'},
                    lambda s,p,**kw: {'value':p['constant'],'units':'1','status':'OBSERVED',
                                     'unit_status':'CHECKED_AGAINST_SUPPLIED_MAPPING'},
                    self.current, store, Path(d))
        self.assertFalse(store.executed)


if __name__ == '__main__':
    unittest.main()
