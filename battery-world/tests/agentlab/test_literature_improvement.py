import json,tempfile,unittest
from pathlib import Path
from bfworld.agentlab.literature_improvement import make_tasks,check_output
from bfworld.agentlab.literature_rsi import qualify_candidate,comparison

class NativeLearningChecks(unittest.TestCase):
    def test_three_independent_references_and_negative_controls(self):
        with tempfile.TemporaryDirectory() as d:
            tasks=make_tasks(Path(d));self.assertEqual(len(tasks),3)
            for t in tasks:
                for arm,status in [('reference','PASS'),('negative','FAIL')]:
                    result=json.loads((Path(d)/'no-agent'/t['id']/arm/'result.json').read_text())
                    self.assertEqual(result['status'],status);self.assertFalse(result['physical_verified'])

    def test_mutated_true_geometry_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            make_tasks(Path(d));p=Path(d)/'no-agent/geometry/reference/workspace'
            (p/'cad-parameters.json').write_text('{"film_thickness_mm":0.05,"units":"mm"}')
            q=check_output('geometry',Path(d)/'public-tasks/geometry',p,Path(d)/'changed-check')
            self.assertEqual(q['status'],'FAIL');self.assertIn('INPUT_CHANGED:cad-parameters.json',q['problems'])

    def test_candidate_cannot_use_validation_feedback(self):
        body={'target':'literature_method_overlay','instruction':'Check the current contract.','hypothesis':'Fewer interface mistakes','falsifier':'No recovery','applies_to':'Native builds','evidence_trials':['cross-paper-hidden']}
        with self.assertRaisesRegex(ValueError,'CANDIDATE_FEEDBACK_LEAK'):qualify_candidate(body,['E01','E02','E03'])

    def test_paired_environment_mismatch_rejected(self):
        pairs=[]
        for split in ['development','new-variant','cross-paper']:
            p={'task_sha256':'same','environment_sha256':'A','evaluation':{'status':'FAIL'}}
            c={'task_sha256':'same','environment_sha256':'B','evaluation':{'status':'PASS'}}
            pairs.append({'task':split,'split':split,'parent':p,'child':c})
        with self.assertRaisesRegex(ValueError,'PAIRED_ENVIRONMENT_MISMATCH'):comparison(pairs)

if __name__=='__main__':unittest.main()
