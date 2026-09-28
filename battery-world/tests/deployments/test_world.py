import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from bfworld.deployments.runtime import execute,Session,DeploymentDesign
from bfworld.deployments.ports import port,Source,environment,SCENES
from bfworld.deployments.artifacts import validate,seal,verify

class DeploymentTests(unittest.TestCase):
    def test_all_families_couple_to_voltage(self):
        env={'irradiance_w_m2':700,'rpm':120,'acceleration_g':1.,'temperature_delta_k':30}
        for kind in ('solar','rotary','piezo','thermal'):
            s=Source('s',kind,(0,0,0),1,3 if kind=='thermal' else 1)
            low=port(s,.5,env,.03);high=port(s,3.3,env,.03)
            self.assertGreater(low['bus_current_a'],high['bus_current_a'])
            self.assertAlmostEqual(low['raw_power_w'],low['bus_power_w']+low['conversion_loss_w'])
    def test_zero_environment_has_no_energy(self):
        env={'irradiance_w_m2':0,'rpm':0,'acceleration_g':0,'temperature_delta_k':0}
        for kind in ('solar','rotary','piezo','thermal'):self.assertEqual(port(Source('s',kind,(0,0,0)),2.6,env,.1)['bus_power_w'],0)
    def test_six_deployments_have_real_requests_and_energy(self):
        for scene in SCENES:
            run=execute(scene);validate(run);self.assertEqual(len(run['requests']),3)
            self.assertTrue(all(len(r['samples'])==128 for r in run['requests']))
    def test_receiver_independent_of_tx(self):
        run=execute('solar-field',replace(DeploymentDesign(),receiver_distance_m=90))
        self.assertEqual(run['summary']['delivered_count'],0);self.assertEqual(run['summary']['correct_count'],3)
    def test_hybrid_source_removal(self):
        full=execute('hybrid-station');removed=execute('hybrid-station',replace(DeploymentDesign(),disabled_sources=('pv-1',)))
        self.assertNotIn('pv-1',removed['summary']['energy_by_source_j']);self.assertGreater(full['ledger']['raw_harvest'],removed['ledger']['raw_harvest'])
    def test_exact_checkpoint_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cp.json';Session('solar-field').advance(333).checkpoint(path)
            self.assertEqual(Session.restore(path).advance().result()['content_hash'],execute('solar-field')['content_hash'])
            obj=json.loads(path.read_text());obj['state']['voltage']=99;path.write_text(json.dumps(obj))
            with self.assertRaises(ValueError):Session.restore(path)
    def test_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            path=seal(Path(temp),execute('thermal-pipeline'));verify(path)
            (path/'events.jsonl').write_text('{}')
            with self.assertRaises(ValueError):verify(path)
    def test_small_storage_failures_remain(self):
        run=execute('indoor-office',replace(DeploymentDesign(),capacitance_f=.00033,esr_ohm=18))
        self.assertFalse(run['summary']['physical_mission_pass']);self.assertGreater(run['summary']['brownouts'],0)
