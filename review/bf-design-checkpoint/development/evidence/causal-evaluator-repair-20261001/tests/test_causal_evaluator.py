import copy, json, math, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import event_apparatus_v2 as a
import causal_evaluator_v2 as e
PLAN=json.loads((ROOT/'contracts/prospective-plan-v2.json').read_text())
FIX=json.loads((ROOT/'contracts/base-fixture-v2.json').read_text())
class ModelContract(unittest.TestCase):
    def test_fixed_timer_under_step_refinement(self):
        decks=[a.netlist(FIX,x,'out.tsv') for x in PLAN['max_steps_s']]
        timers=[next(l for l in d.splitlines() if l.startswith('Btimer ')) for d in decks]
        self.assertEqual(len(set(timers)),1);self.assertIn('/1e-06)',timers[0])
        normalized=['\n'.join(l for l in d.splitlines() if not l.startswith('tran ')) for d in decks]
        self.assertEqual(len(set(normalized)),1)
    def test_explicit_ports_and_no_feedback(self):
        d=a.netlist(FIX,1e-5,'out.tsv');self.assertIn('Vpiezo_port p bridge_p 0',d)
        s=copy.deepcopy(FIX);s['control']['feedback_mode']='no-feedback';n=a.netlist(s,1e-5,'out.tsv')
        self.assertIn('Bpiezo_force u 0 I=0*v(p)',n);self.assertIn('Bpiezo_current 0 p I=0.0005*v(u)',n)
        diff=[(x,y) for x,y in zip(d.splitlines(),n.splitlines()) if x!=y]
        self.assertEqual(len(diff),1)
    def test_old_schema_not_silently_admitted(self):
        s=copy.deepcopy(FIX);s['schema_version']='bf-event-design-v1'
        with self.assertRaisesRegex(ValueError,'SCHEMA'):a.validate(s)
    def test_missing_control_or_provenance_rejected(self):
        for field in ['timer_reset_tau_s','feedback_mode']:
            s=copy.deepcopy(FIX);del s['control'][field]
            with self.assertRaises(ValueError):a.validate(s)
        s=copy.deepcopy(FIX);s['provenance']=[r for r in s['provenance'] if r['parameter']!='control']
        with self.assertRaisesRegex(ValueError,'CONTROL_PROVENANCE'):a.validate(s)
    def test_invalid_reset_and_output_rejected(self):
        for tau in [0,-1,math.nan,math.inf,True]:
            s=copy.deepcopy(FIX);s['control']['timer_reset_tau_s']=tau
            with self.assertRaises(ValueError):a.validate(s)
        with self.assertRaisesRegex(ValueError,'BASENAME'):a.netlist(FIX,1e-5,'../out.tsv')
    def test_channel_nonfinite_and_time_errors_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x'
            for rows in [[['nan']+['0']*14 for _ in range(10)],[['1']+['0']*14 for _ in range(10)]]:
                p.write_text('header\n'+'\n'.join(' '.join(r) for r in rows))
                with self.assertRaises(ValueError):a.read_channels(p)
class EvaluatorContract(unittest.TestCase):
    def rows(self,amplitude=0,active=True):
        rows=[]
        for i in range(101):
            t=.25*i/100;r={k:0. for k in a.CHANNEL_KEYS};r.update(time_s=t,displacement_m=amplitude*t,enabled=float(active),stage_time_s=t,load_a=1e-6 if active else 0)
            rows.append(r)
        return rows
    def cases(self):
        return {f'{mode}-{load}-{i}':{'rows':self.rows(.001 if mode=='reciprocal' and load=='treatment' else 0),'spec':copy.deepcopy(FIX)} for mode in PLAN['feedback_modes'] for load in PLAN['idle_current_a'] for i in range(3)}
    def test_partial_matrix_rejected(self):
        with self.assertRaisesRegex(ValueError,'CASE_MATRIX'):e.evaluate(PLAN,{})
    def test_interpolation_and_coverage(self):
        self.assertAlmostEqual(e.interpolate(self.rows(2),[.001])[0],.002)
        with self.assertRaisesRegex(ValueError,'UNCOVERED'):e.interpolate(self.rows(),[.3])
    def test_positive_control_is_separate_from_energy(self):
        result=e.evaluate(PLAN,self.cases())
        self.assertTrue(result['checks']['finite_positive_activation'])
        self.assertTrue(result['checks']['postactivation_causal_separation'])
        self.assertFalse(result['checks']['reciprocal_energy_ports'])
        self.assertFalse(result['diagnostic_passed'])
    def test_no_activation_cannot_pass(self):
        cases=self.cases()
        for c in cases.values():c['rows']=self.rows(active=False)
        result=e.evaluate(PLAN,cases)
        self.assertFalse(result['checks']['finite_positive_activation']);self.assertFalse(result['checks']['postactivation_causal_separation'])
    def test_no_feedback_response_rejected(self):
        cases=self.cases()
        for i in range(3):cases[f'no-feedback-treatment-{i}']['rows']=self.rows(.001)
        result=e.evaluate(PLAN,cases)
        self.assertFalse(result['checks']['no_feedback_negative_control']);self.assertFalse(result['checks']['postactivation_causal_separation'])
    def test_unconverged_trace_rejected(self):
        cases=self.cases();cases['reciprocal-treatment-1']['rows']=self.rows(.01)
        self.assertFalse(e.evaluate(PLAN,cases)['checks']['time_convergence'])
    def test_external_work_is_explicit_in_ablation(self):
        s=copy.deepcopy(FIX);s['control']['feedback_mode']='no-feedback';rows=self.rows()
        for r in rows:r.update(velocity_m_s=2,piezo_v=3)
        ledger=e.energy_ledger(s,rows)
        self.assertEqual(ledger['mechanical_reaction_work'],0)
        self.assertAlmostEqual(ledger['artificial_external_electrical_work'],.00075)
        s['control']['feedback_mode']='reciprocal';ledger=e.energy_ledger(s,rows)
        self.assertEqual(ledger['artificial_external_electrical_work'],0)
        self.assertAlmostEqual(ledger['mechanical_reaction_work'],.00075)
    def test_nonfinite_comparison_rejected(self):
        with self.assertRaisesRegex(ValueError,'NONFINITE'):e.maxdiff([math.nan],[0])
if __name__=='__main__':unittest.main(verbosity=2)
