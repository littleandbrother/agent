import copy
import json
import tempfile
import unittest
from pathlib import Path
from bfworld.knowledge.registry import create_capsule,verify_capsule,transition,verify_lifecycle
from bfworld.knowledge.burst_program import predict
from bfworld.kernel.canonical import canonical_hash

REPO=Path(__file__).resolve().parents[2]
class KnowledgeTests(unittest.TestCase):
    def test_capsule_identity_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=create_capsule(Path(tmp),{'example':1},['sha256:test-source'])
            root=Path(result['path']);verify_capsule(root)
            (root/'program.py').write_text('print("forged")')
            with self.assertRaises(ValueError):verify_capsule(root)
    def test_missing_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):create_capsule(Path(tmp),{},[])
    def test_self_promotion_denied(self):
        with self.assertRaises(ValueError):transition([],'sha256:k','EXPLANATION_VALIDATED',{'passed':True,'candidate_hash':'sha256:k'})
    def test_dual_receipts_and_chain(self):
        h='sha256:k';e={'passed':True,'candidate_hash':h};log=[]
        for state in ('EXPLANATION_VALIDATED','USE_VALIDATED'):log=transition(log,h,state,e,role='qualifier')
        with self.assertRaises(ValueError):transition(log,h,'PROMOTED',e,role='qualifier')
        log=transition(log,h,'PROMOTED',{**e,'explanation_hash':'sha256:e','use_hash':'sha256:u'},role='qualifier')
        log=transition(log,h,'RESTRICTED',{'candidate_hash':h,'reason':'new counterexample'},role='qualifier');verify_lifecycle(log)
        log[0]['state']='REJECTED'
        with self.assertRaises(ValueError):verify_lifecycle(log)
    def test_wrong_candidate_receipt(self):
        with self.assertRaises(ValueError):transition([],'sha256:a','EXPLANATION_VALIDATED',{'passed':True,'candidate_hash':'sha256:b'},role='qualifier')
    def test_out_of_scope_rejected_before_prediction(self):
        result=predict({}, {}, {'harvest_during_burst':True})
        self.assertFalse(result['in_scope']);self.assertIsNone(result['energy_feasible'])
    def test_failed_gate_not_promoted(self):
        report=json.loads((REPO/'docs/knowledge/reference-study.json').read_text())
        self.assertEqual(canonical_hash({k:v for k,v in report.items() if k!='content_hash'}),report['content_hash'])
        verify_lifecycle(report['lifecycle'])
        self.assertTrue(report['explanation']['passed'])
        self.assertFalse(report['use']['passed']);self.assertEqual(report['reference_qualified_knowledge'],0)
        self.assertFalse(any(e['state']=='PROMOTED' for e in report['lifecycle']))
        self.assertEqual(len(report['use']['future_tasks']),4)
        for task in report['use']['future_tasks'][:3]:
            arms={a['arm']:a for a in task['arms']}
            self.assertTrue(arms['executable-capsule']['success'])
            self.assertLess(arms['executable-capsule']['probe_count'],arms['raw-search-removal']['probe_count'])
        self.assertTrue(all(not a['success'] for a in report['use']['future_tasks'][3]['arms']))
