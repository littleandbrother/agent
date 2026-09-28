import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash
from bfworld.campaign.measurements import restore_archive,verify_bundle
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts'))
from build_b2_profiled import build,validate

class ArtifactProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=build(REPO)
    def test_fixed_conditions_and_negative_semantic_result(self):
        d=self.report;self.assertEqual(len(d['runs']),36);self.assertEqual(len(d['registry']['tasks']),7)
        self.assertFalse(d['registry']['blind']);self.assertFalse(d['registry']['qualification'])
        self.assertEqual([v['false_rejects'] for v in d['variants']],[12,0,0])
        self.assertEqual([v['false_feasible_predictions'] for v in d['variants']],[1,18,17])
        self.assertFalse(any(v['promoted'] or v['qualified'] for v in d['variants']))
        pilot=json.loads((REPO/'docs/campaign/report.json').read_text())
        for t,u in zip(d['variants'][0]['tasks'][:3],pilot['qualifications'][2]['use_tests']):
            self.assertEqual(t['raw']['probes'] if t['raw']['success'] else None,u['baseline_probes'])
            self.assertEqual(t['program']['probes'] if t['program']['success'] else None,u['learned_probes'])
    def test_rehashed_control_or_aggregate_tamper_rejected(self):
        for edit in ('aggregate','use','task'):
            d=copy.deepcopy(self.report)
            if edit=='aggregate':d['variants'][1]['false_feasible_predictions']=0
            if edit=='use':d['variants'][1]['tasks'][0]['program']['probes']=0
            if edit=='task':d['runs'][0]['candidate_id']='wrong-candidate'
            d.pop('content_hash');d['content_hash']=canonical_hash(d)
            with self.assertRaises(ValueError):validate(d,REPO)
    def test_measured_archive_detaches_without_source_hardware_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,report=restore_archive(REPO/'docs/b2-development/measured-replay.zip',Path(tmp))
            self.assertEqual(verify_bundle(root),report)
            self.assertEqual(report['observations']['current']['raw_samples'],119998)
            self.assertIsNone(report['observations']['current']['measured_energy_j'])
            self.assertFalse(report['observations']['source_boundary']['current_and_receiver_same_session'])
            self.assertTrue(any(r['reported_tx_energy_mj'] is None for r in report['observations']['historical_phases']))
            (root/'current.csv').write_text('tamper')
            with self.assertRaises(ValueError):verify_bundle(root)

if __name__=='__main__':unittest.main()
