import copy
import csv
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

from bfworld.agentlab import pluck_case as pluck

ROOT=Path(__file__).resolve().parents[2]
CASE=json.loads((ROOT/'configs/reference_cases/pluck-v1/case.json').read_text())


class PluckNumerics(unittest.TestCase):
    def test_force_is_negative_potential_gradient_and_repulsive_at_center(self):
        m=CASE['mechanics'];epsilon=1e-7
        for q,b in ((.001,.005),(-.003,-.01),(.005,.02)):
            up=pluck.magnetic(q+epsilon,b,m,.026)[0]
            um=pluck.magnetic(q-epsilon,b,m,.026)[0]
            f=pluck.magnetic(q,b,m,.026)[1]
            self.assertAlmostEqual(f,-(up-um)/(2*epsilon),delta=abs(f)*1e-5)
        self.assertGreater(pluck.magnetic(epsilon,0,m,.026)[1],0)
        literal={**m,'magnetic_polarity':1}
        self.assertLess(pluck.magnetic(epsilon,0,literal,.026)[1],0)

    def test_invalid_boundaries_rejected_before_execution(self):
        for kwargs in ({'capacitance_f':-1},{'gap':0},{'step':float('nan')},{'initial_deflection_m':1},{'interface':'invented'}):
            with self.assertRaises(ValueError):pluck.netlist(CASE,**kwargs)
        bad=copy.deepcopy(CASE);bad['power']['efficiency']=1.01
        with self.assertRaises(ValueError):pluck.netlist(bad)

    @unittest.skipUnless(Path('/opt/homebrew/bin/ngspice').exists(),'ngspice optional local solver')
    def test_real_solver_free_decay_and_no_energy_negative_control(self):
        case=copy.deepcopy(CASE);case['motion']['duration_s']=.15
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            no=pluck.run(case,root/'zero',interface='sece',motion_scale=0,loaded=True)
            self.assertTrue(no['checks']['complete']);self.assertFalse(no['checks']['service'])
            self.assertEqual(no['tx_complete_times_s'],[])
            self.assertLess(no['peak_storage_v'],1e-6)
            free=pluck.run(case,root/'free',interface='open',motion_scale=0,initial_deflection_m=.001)
            self.assertTrue(all(v for v in free['checks'].values() if v is not None))
            m=case['mechanics'];alpha=m['damping_ns_m']/(2*m['mass_kg'])
            omega=math.sqrt((m['stiffness_n_m']+m['coupling_n_v']**2/m['piezo_capacitance_f'])/m['mass_kg']-alpha**2)
            for row in csv.DictReader((root/'free/trace.csv').read_text().splitlines()):
                t=float(row['time_s']);expected=.001*math.exp(-alpha*t)*(math.cos(omega*t)+alpha/omega*math.sin(omega*t))
                self.assertAlmostEqual(float(row['displacement_m']),expected,delta=1e-6)
            self.assertTrue((root/'free/channels.csv.gz').is_file())
            with self.assertRaises(FileExistsError):pluck.run(case,root/'free')

    def test_loss_order_and_unknown_direction(self):
        times=[.1,.2,.3,1.0]
        self.assertEqual([3,1],[e['packets'] for e in pluck.receive(times)])
        self.assertTrue(all(e['direction']=='unknown' for e in pluck.receive(times)))
        self.assertEqual([],pluck.receive(times,range(4)))
        for invalid in ([.2,.1],[float('nan')],[-1]):
            with self.assertRaises(ValueError):pluck.receive(invalid,range(3))

    def test_real_payload_decoder_separates_devices(self):
        spec=importlib.util.spec_from_file_location('pluck_receiver',ROOT/'scripts/pluck_receiver.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertIsNone(module.decode(b'anything'))
        records=[{'time_s':t,'payload_hex':(b'BFP1'+bytes([i])*8).hex(),'origin':'test-synthetic'} for t,i in ((.1,1),(.2,2),(.25,1),(.8,1))]
        events=module.group(records)
        self.assertEqual([2,1,1],[e['packets'] for e in events])
        self.assertEqual(2,len({e['device_id'] for e in events}))
        with self.assertRaises(ValueError):module.group([{**records[0],'time_s':float('nan')}])

    def test_html_download_and_unpinned_pdf_are_rejected(self):
        spec=importlib.util.spec_from_file_location('fetch_pluck',ROOT/'scripts/fetch_pluck_sources.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with self.assertRaisesRegex(ValueError,'SOURCE_IS_NOT_PDF'):module.verify(b'<html>publisher error</html>','0'*64)
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):module.verify(b'%PDF-1.7 modified','0'*64)


class PluckProjection(unittest.TestCase):
    def test_tamper_and_path_escape_are_detected_without_following_external_files(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);root=home/'reference-cases/pluck-v1';root.mkdir(parents=True)
            artifact=root/'result.json';artifact.write_text('{"passed":false}')
            record={'path':'result.json','sha256':pluck.digest(artifact)}
            (root/'receipt.json').write_text(json.dumps({'artifacts':[record]}))
            self.assertTrue(pluck.projection(home)['artifact_integrity'])
            artifact.write_text('{"passed":true}')
            self.assertFalse(pluck.projection(home)['artifact_integrity'])
            outside=home/'private.json';outside.write_text('private')
            record={'path':'../../private.json','sha256':pluck.digest(outside)}
            (root/'receipt.json').write_text(json.dumps({'artifacts':[record]}))
            self.assertFalse(pluck.projection(home)['artifact_integrity'])


if __name__=='__main__':unittest.main()
