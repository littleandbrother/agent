import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from run_diagnostics import bind_cases,expected_spec,plan
class RunnerBindings(unittest.TestCase):
    def cases(self):
        return {f'{mode}-{load}-{i}':{'spec':expected_spec(mode,load),'max_step_s':step} for mode in plan['feedback_modes'] for load in plan['idle_current_a'] for i,step in enumerate(plan['max_steps_s'])}
    def test_exact_input_matrix_is_accepted(self):
        bind_cases(self.cases())
    def test_mislabeled_mode_idle_or_step_rejected(self):
        for field in ['mode','idle','step']:
            cases=self.cases();c=cases['reciprocal-baseline-0']
            if field=='mode':c['spec']['control']['feedback_mode']='no-feedback'
            elif field=='idle':c['spec']['workload']['idle_current_a']=.01
            else:c['max_step_s']=5e-6
            with self.assertRaisesRegex(ValueError,'IDENTITY_MISMATCH'):bind_cases(cases)
    def test_extra_cell_rejected(self):
        cases=self.cases();cases['unplanned']={}
        with self.assertRaisesRegex(ValueError,'COUNT_MISMATCH'):bind_cases(cases)
if __name__=='__main__':unittest.main()
