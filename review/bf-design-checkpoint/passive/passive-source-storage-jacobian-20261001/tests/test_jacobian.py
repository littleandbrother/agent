import json,sys,unittest,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from passive_runner import Model,rectifier,branch_jacobian,bounded_q_step

class StructuredDerivativeTests(unittest.TestCase):
    def test_physical_plan_parameters_unchanged(self):
        baseline=json.loads((ROOT/'BASELINE-PLAN.json').read_text());new=json.loads((ROOT/'PLAN.json').read_text())
        allowed={'model_version','implementation_revision','jacobian','authorization_status'}
        self.assertEqual({k:v for k,v in baseline.items() if k not in allowed},{k:v for k,v in new.items() if k not in allowed})
    def test_zero_columns_and_piecewise_electrical_derivatives(self):
        m=Model(47e-6)
        def rhs(y):
            q,u,Q,vs=y[:4];vp=(Q-m.theta*q)/m.cp;I,i=rectifier(vp,vs,m.R)
            return np.array([u,(.03+7*q-m.c*u-m.k*q+m.theta*vp)/m.m,-i,I/m.cin,m.c*u*u,m.R*I*I,.002+.2*q,-.001-.1*q])
        for vp,vs in [(2.,.1),(-2.,.1),(.1,2.)]:
            q=.001;y=np.array([q,.02,m.theta*q+m.cp*vp,vs,1e-4,2e-5,.003,-.0001])
            J=branch_jacobian(y,m=m.m,k=m.k,c=m.c,theta=m.theta,cp=m.cp,cin=m.cin,R=m.R,dF_dq=7.,dPtrans_dq=.2,dProt_dq=-.1)
            self.assertTrue(np.array_equal(J[:,4:],np.zeros((8,4))))
            for i,h in enumerate([1e-9,1e-7,1e-15,1e-6,1e-7,1e-7,1e-7,1e-7]):
                dy=np.zeros(8);dy[i]=h;fd=(rhs(y+dy)-rhs(y-dy))/(2*h)
                self.assertTrue(np.allclose(fd,J[:,i],atol=2e-6,rtol=1e-6))
    def test_exact_rejected_trial_telemetry(self):
        m=Model(47e-6);m.last_accepted_t=.9;m.last_accepted_state=[0.]*8;y=np.array([0.,0.,m.cp*.1,501.,0,0,0,1e152])
        with self.assertRaises(ValueError):m.rhs(1.,y,0.)
        r=m.rejected_evaluation;self.assertEqual(r['rejected_state'],y.tolist());self.assertTrue(r['Vs_guard_failed']);self.assertFalse(r['Vp_guard_failed']);self.assertEqual(r['phase'],'solver_rhs_trial');self.assertEqual(m.force_evaluations,0)
    def test_derivative_margin_refuses_boundary(self):
        for q in [.008,-.008,.009,float('nan')]:
            with self.assertRaises(ValueError):bounded_q_step(q)
    def test_three_retained_states_magnetic_derivatives(self):
        p=json.loads((ROOT/'DERIVATIVE-TEST-PLAN.json').read_text())
        self.assertEqual(hashlib.sha256(Path(p['retained_state_source']).read_bytes()).hexdigest(),p['source_sha256'])
        m=Model(47e-6);results=[]
        for row in p['states']:
            t=row[0];y=np.array(row[1:]);adot=m.amax/2
            J=m.jacobian(t,y,adot)
            self.assertTrue(np.isfinite(J).all());self.assertTrue(np.array_equal(J[:,4:],np.zeros((8,4))))
            results.append({'t_s':t,'jacobian':J.tolist(),'derivative_record':m.derivative_records[-1]})
        self.assertLessEqual(m.force_evaluations,p['max_new_force_evaluations'])
        (ROOT/'outputs/STATIC-JACOBIAN-CHECKS.json').write_text(json.dumps({'scope':'three retained states and bounded static q perturbations, no trajectories','force_evaluations':m.force_evaluations,'dynamic_trajectories':0,'results':results},indent=2)+'\n')
