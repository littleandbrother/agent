import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from bfworld.coupled.engine import Design,Reference,execute,reference_cases,classify,signal_window,input_current
from bfworld.coupled.artifacts import seal_run,verify_bundle,validate_run

class CoupledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.cases={k:execute(d,r) for k,(d,r) in reference_cases().items()}
    def test_five_computed_controls(self):
        self.assertTrue(self.cases['pass']['physical_mission_pass']['value'])
        for k in ('overvoltage','brownout'):self.assertFalse(self.cases[k]['physical_mission_pass']['electrical_safe'])
        self.assertFalse(self.cases['wrong-diagnosis']['physical_mission_pass']['quality_valid'])
        self.assertTrue(self.cases['wrong-diagnosis']['physical_mission_pass']['delivered'])
        self.assertFalse(self.cases['receiver-loss']['physical_mission_pass']['delivered'])
    def test_ledger_and_order(self):
        for run in self.cases.values():validate_run(run,reproduce=True);self.assertGreater(run['energy_ledger']['esr_loss'],0)
    def test_classifier_is_executed(self):
        for label in ('normal','bearing-fault'):
            self.assertEqual(classify(signal_window(replace(Reference(),fault=label)),25)['predicted_label'],label)
        with self.assertRaises(ValueError):classify([0]*127,25)
        with self.assertRaises(ValueError):classify([999]*128,25)
    def test_brownout_interrupts_delivery(self):
        events=self.cases['brownout']['events'];types=[e['type'] for e in events]
        self.assertIn('request_aborted',types);self.assertNotIn('transmission_completed',types);self.assertNotIn('receiver_delivered',types)
    def test_tx_is_not_rx(self):
        types=[e['type'] for e in self.cases['receiver-loss']['events']]
        self.assertIn('transmission_completed',types);self.assertNotIn('receiver_delivered',types)
    def test_load_affects_voltage(self):
        low=execute(replace(Design(),tx_power_w=.008));high=self.cases['pass']
        self.assertGreater(low['rows'][450]['storage_voltage_v'],high['rows'][450]['storage_voltage_v'])
    def test_resolution(self):
        fine=execute(ref=replace(Reference(),dt_s=.0005))
        self.assertEqual(fine['physical_mission_pass'],self.cases['pass']['physical_mission_pass'])
        self.assertLess(abs(fine['rows'][-1]['storage_voltage_v']-self.cases['pass']['rows'][-1]['storage_voltage_v']),.001)
    def test_immutable_artifacts_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=seal_run(Path(tmp),self.cases['pass']);verify_bundle(root,reproduce=True)
            self.assertEqual(root,seal_run(Path(tmp),self.cases['pass']))
            (root/'events.jsonl').write_text('{}\n')
            with self.assertRaises(ValueError):verify_bundle(root)
            with self.assertRaises(ValueError):seal_run(Path(tmp),self.cases['pass'])
    def test_forged_success_rejected(self):
        run=copy.deepcopy(self.cases['pass']);run['verified_mission_success']=True
        with self.assertRaises(ValueError):validate_run(run)
    def test_esr_power_equation(self):
        current=input_current(2.6,.036,4,.82)
        self.assertAlmostEqual((2.6-4*current)*current*.82,.036)
