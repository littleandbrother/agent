import copy
import tempfile
import unittest
from pathlib import Path
from bfworld.coupled.engine import Design,Reference
from bfworld.coupled.profiled import LoadProfile
from bfworld.campaign.task_context import physics_for
from bfworld.campaign.splits import task_record
from bfworld.campaign.semantic_development import diagnostic_context,selection_order,use_control
from bfworld.campaign.measurements import read_current,extrema_projection

class SemanticControls(unittest.TestCase):
    def setUp(self):
        t=task_record('public','development',physics_for({'a':Design(),'b':Design(esr_ohm=5)},Reference(),LoadProfile()))
        self.ctx=diagnostic_context(t)
        self.obs={'a':{'run_hash':'sha256:a','physical_pass':False},'b':{'run_hash':'sha256:b','physical_pass':True}}
    def test_abstention_falls_back_and_never_self_admits(self):
        output={'scope_ok':True,'predictions':{'a':{'verdict':'feasible'},'b':{'verdict':'abstain'}}}
        result=use_control(self.ctx,output,self.obs)
        self.assertEqual(result['probes'],2);self.assertEqual(result['submission']['candidate_id'],'b')
        self.assertEqual(result['false_admissions'],0)
    def test_wrong_pruning_is_not_hidden(self):
        output={'scope_ok':True,'predictions':{'a':{'verdict':'feasible'},'b':{'verdict':'infeasible'}}}
        self.assertFalse(use_control(self.ctx,output,self.obs)['success'])
        self.assertTrue(use_control(self.ctx,None,self.obs)['success'])
    def test_scope_and_receipt_completeness(self):
        self.assertEqual(selection_order(self.ctx,{'scope_ok':False,'predictions':{}}),['a','b'])
        with self.assertRaises(ValueError):use_control(self.ctx,None,{'a':self.obs['a']})
        for field in ('label','ground_truth','observations','minimum_input_v'):self.assertNotIn(field,str(self.ctx.keys()))
    def test_extrema_are_original_time_bound_samples(self):
        points=[{'sample':i,'time_s':i*.001,'current_a':99 if i==3 else -5 if i==4 else 1} for i in range(30)]
        projected=extrema_projection(points,3)
        self.assertIn(points[3],projected);self.assertIn(points[4],projected)
        self.assertEqual(projected,sorted(projected,key=lambda p:p['time_s']))
    def test_measured_units_monotonicity_and_finite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'current.csv'
            path.write_text('sample,time_s,current_A\n0,0,0.1\n1,0.1,0.2\n')
            self.assertEqual(len(read_current(path)),2)
            path.write_text('sample,time_s,current_A\n0,0,0.1\n1,0,nan\n')
            with self.assertRaises(ValueError):read_current(path)

if __name__=='__main__':unittest.main()
