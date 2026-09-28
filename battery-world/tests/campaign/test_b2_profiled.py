import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from bfworld.coupled.engine import Design,Reference,execute as frozen_execute
from bfworld.coupled.profiled import LoadProfile,execute,verify
from bfworld.coupled.profiled_artifacts import seal_run,verify_bundle
from bfworld.campaign.task_context import physics_for,public_context,execute_candidate,materialize
from bfworld.campaign.splits import task_record

class ProfiledTests(unittest.TestCase):
    def test_default_agrees_with_frozen_v1_without_rewriting_it(self):
        for d in [Design(),replace(Design(),capacitance_f=.00033,esr_ohm=18)]:
            new=execute(d);old=frozen_execute(d)
            self.assertEqual(new['summary'],old['summary']);self.assertEqual(new['physical_mission_pass'],old['physical_mission_pass'])
            self.assertEqual([r['storage_voltage_v'] for r in new['rows']],[r['storage_voltage_v'] for r in old['rows']])
            self.assertTrue(verify(new,True)['reproduced'])
    def test_tx_duration_is_causal_input_not_release_alias(self):
        base=execute();long=execute(load=replace(LoadProfile(),tx_duration_s=.2))
        self.assertTrue(base['physical_mission_pass']['value']);self.assertFalse(long['physical_mission_pass']['value'])
        self.assertEqual(base['design']['release_s'],long['design']['release_s'])
        self.assertIsNotNone(long['summary']['first_brownout_s'])
    def test_independent_failure_axes(self):
        late=execute(ref=replace(Reference(),deadline_s=.4))
        wrong=execute(design=replace(Design(),model_threshold=100))
        lost=execute(ref=replace(Reference(),receiver_loss=True))
        over=execute(design=replace(Design(),clamp_v=None),ref=replace(Reference(),surge_after_s=.8,surge_multiplier=8))
        self.assertTrue(late['physical_mission_pass']['delivered']);self.assertFalse(late['physical_mission_pass']['deadline_met'])
        self.assertTrue(wrong['physical_mission_pass']['delivered']);self.assertFalse(wrong['physical_mission_pass']['quality_valid'])
        self.assertFalse(lost['physical_mission_pass']['delivered']);self.assertIsNotNone(over['summary']['first_overvoltage_s'])
        for r in [late,wrong,lost,over]:verify(r,True)
    def test_fractional_endpoint_and_domain(self):
        r=execute(ref=replace(Reference(),duration_s=1.6004));self.assertEqual(r['rows'][-1]['time_s'],1.6004);verify(r,True)
        for l in [replace(LoadProfile(),tx_duration_s=0),replace(LoadProfile(),sample_count=64),replace(LoadProfile(),source_kind='measured'),replace(LoadProfile(),infer_power_w=float('nan'))]:
            with self.assertRaises(ValueError):execute(load=l)
        with self.assertRaises(ValueError):execute(design=replace(Design(),tx_power_w=True))
    def test_power_collapse_above_voltage_threshold_cannot_complete_actions(self):
        r=execute(replace(Design(),esr_ohm=1000,clamp_v=5.5),replace(Reference(),initial_v=5.,max_v=6.))
        self.assertGreater(r['summary']['minimum_input_v'],r['reference']['off_v'])
        self.assertIsNone(r['summary']['first_brownout_s'])
        self.assertTrue(r['power_delivery_failures_s'])
        self.assertFalse(r['physical_mission_pass']['value']);self.assertFalse(r['physical_mission_pass']['delivered'])
        self.assertTrue(any(e['type']=='constant_power_collapse' for e in r['events']))
        verify(r,True)
    def test_sealed_projection_replay_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=execute();root=seal_run(Path(tmp),r);self.assertEqual(seal_run(Path(tmp),r),root);verify_bundle(root,reproduce=True)
            (root/'events.jsonl').write_text('[]\n')
            with self.assertRaises(ValueError):verify_bundle(root)
    def test_explicit_context_and_private_truth(self):
        physics=physics_for({'a':Design()},Reference(),LoadProfile())
        t=task_record('dev-explicit','development',physics,prior_exposure='public')
        c=public_context(t)
        self.assertEqual(c['load_profile']['tx_duration_s'],.04);self.assertEqual(c['candidates'][0]['release_s'],.25)
        self.assertNotIn('label',c);self.assertNotIn('receiver',c)
        self.assertEqual(execute_candidate(t,'a')['content_hash'],execute()['content_hash'])
        bad=copy.deepcopy(physics);bad['load_profile'].pop('tx_duration_s')
        with self.assertRaises(ValueError):materialize(task_record('bad','development',bad))

if __name__=='__main__':unittest.main()
