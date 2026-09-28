import json
import copy
import tempfile
import unittest
from pathlib import Path
from bfworld.kernel.canonical import file_hash, canonical_hash
from bfworld.campaign.diagnostics import g2_residuals, canonical_interventions, validate_dossier

REPO = Path(__file__).resolve().parents[2]


class DiagnosticsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(dir=REPO/'.bfworld',prefix='b2-test-')
  cls.root=Path(cls.temp.name)
  cls.before=file_hash(REPO/'docs/campaign/report.json')
  report=json.loads((REPO/'docs/campaign/report.json').read_text());cls.pilot=report
  cls.residual=g2_residuals(report,REPO,cls.root/'runs')
  cls.episode=canonical_interventions(REPO,cls.root/'runs')
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_g2_false_rejections_and_lost_tasks_reproduce(self):
  self.assertEqual(len(self.residual['rows']),24)
  r=self.residual['residuals']
  self.assertEqual(len(r['false_reject_region']),10)
  self.assertEqual(r['false_admit_region'],[])
  self.assertEqual({x['task'] for x in r['lost_solvable_task']},{'qualification-6','qualification-7'})
  self.assertEqual(r['probe_reduction'][2]['probe_reduction'],2)
  self.assertFalse(self.residual['promotion'])
 def test_semantic_mismatch_is_source_bound_not_unique_causal_diagnosis(self):
  m=self.residual['residuals']['missing_state_variable'][0]
  self.assertEqual(m['reference_fact']['tx_duration_s'],.04)
  self.assertTrue(m['candidate_source_sites'])
  self.assertIn("release_s",m['candidate_source_sites'][0]['source'])
  self.assertTrue(all(h['status']=='candidate-explanation' for h in self.episode['competing_explanations']))
 def test_interventions_change_only_declared_fields(self):
  base=self.episode['runs'][0]
  self.assertIsNotNone(base['summary']['first_brownout_s'])
  for r in self.episode['runs']:
   changes=[f'{part}.{key}' for part in ('design','reference') for key,v in r[part].items() if v!=base[part][key]]
   self.assertEqual(changes,r['changed_fields'])
   self.assertEqual(len(r['trace']),1601)
   self.assertLess(r['energy_ledger']['normalized_residual'],1e-7)
   self.assertEqual(r['comparison']['baseline_hash'],base['run_hash'])
 def test_old_report_not_overwritten_and_diagnostics_sealed(self):
  self.assertEqual(file_hash(REPO/'docs/campaign/report.json'),self.before)
  self.assertEqual(canonical_hash({k:v for k,v in self.residual.items() if k!='content_hash'}),self.residual['content_hash'])
 def test_rehashed_fake_counterexample_is_rejected(self):
  g=copy.deepcopy(self.residual);g['rows'][0]['predicted']=True
  g.pop('content_hash');g['content_hash']=canonical_hash(g)
  d={'g2':g,'episode':self.episode};d['content_hash']=canonical_hash(d)
  with self.assertRaisesRegex(ValueError,'historical evidence'):validate_dossier(d,self.pilot,REPO)
 def test_rehashed_visual_sample_is_rejected(self):
  episode=copy.deepcopy(self.episode);episode['runs'][0]['trace'][0]['input_voltage_v']=9.
  episode.pop('content_hash');episode['content_hash']=canonical_hash(episode)
  d={'g2':self.residual,'episode':episode};d['content_hash']=canonical_hash(d)
  with self.assertRaisesRegex(ValueError,'trace sample'):validate_dossier(d,self.pilot,REPO)
