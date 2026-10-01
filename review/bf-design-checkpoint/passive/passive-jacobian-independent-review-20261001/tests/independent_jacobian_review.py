"""Pure algebra, retained-data replay and rejection tests; no force/ODE calls."""
from pathlib import Path
import hashlib,json,math,sys,unittest
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
SNAP=ROOT/'snapshot'
sys.path.insert(0,str(SNAP))
import passive_runner as runner

def expected_matrix(y,p,derivatives):
    m,k,th,cp=(p['mechanics'][x] for x in ('mass_kg','k_N_m','theta_C_m','Cp_ritz_F'))
    c=2*p['damping_ratio']*math.sqrt(k*m);R=p['rectifier']['series_resistance_ohm'];cin=p['cases'][0]['cin_F']
    q,u,Q,vs=y[:4];v=(Q-th*q)/cp;s=math.copysign(1.,v) if v else 0.;g=float(abs(v)>vs);I=max(abs(v)-vs,0)/R
    a=np.zeros((8,8));a[0,1]=1
    a[1,:3]=[(derivatives[0]-k-th*th/cp)/m,-c/m,th/(m*cp)]
    a[2,0]=g*th/(R*cp);a[2,2]=-g/(R*cp);a[2,3]=g*s/R
    a[3,0]=-g*s*th/(R*cp*cin);a[3,2]=g*s/(R*cp*cin);a[3,3]=-g/(R*cin)
    a[4,1]=2*c*u
    a[5,0]=-2*I*g*s*th/cp;a[5,2]=2*I*g*s/cp;a[5,3]=-2*I*g
    a[6,0],a[7,0]=derivatives[1:]
    return a

class IndependentJacobianReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=json.loads((SNAP/'PLAN.json').read_text())
        cls.testplan=json.loads((SNAP/'DERIVATIVE-TEST-PLAN.json').read_text())
        cls.records=json.loads((SNAP/'outputs/STATIC-JACOBIAN-CHECKS.json').read_text())
    def setUp(self):
        self.guard=patch.object(runner.StaticMagneticInterface,'evaluate',side_effect=AssertionError('no reviewer magnetic calls allowed'))
        self.guard.start();self.addCleanup(self.guard.stop)
    def test_retained_states_and_unchanged_science(self):
        p=self.testplan;source=Path(p['retained_state_source'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),p['source_sha256'])
        a=np.load(source)['accepted']
        self.assertTrue(np.array_equal(a[p['indices']],p['states']))
        old=json.loads((SNAP/'BASELINE-PLAN.json').read_text());ignored={'model_version','implementation_revision','jacobian','authorization_status'}
        self.assertEqual({k:v for k,v in old.items() if k not in ignored},{k:v for k,v in self.plan.items() if k not in ignored})
    def test_raw_derivatives_and_all_matrix_entries(self):
        discrepancies=[]
        for state,result in zip(self.testplan['states'],self.records['results']):
            d=result['derivative_record'];h=d['h_m'];r=d['raw']
            v=np.array([[x[k] for k in ('Fq_N','Ptranslation_W','Protation_W')] for x in r])
            coarse=(v[1]-v[0])/(2*h);fine=(v[3]-v[2])/h
            np.testing.assert_allclose(coarse,d['derivative_h'],atol=1e-14,rtol=1e-13)
            np.testing.assert_allclose(fine,d['derivative_half_h'],atol=1e-14,rtol=1e-13)
            self.assertTrue(np.all(abs(coarse-fine)<=np.asarray(d['thresholds'])))
            np.testing.assert_allclose(result['jacobian'],expected_matrix(state[1:],self.plan,fine),atol=1e-12,rtol=1e-13)
            discrepancies.append(abs(coarse-fine))
        self.assertEqual(self.records['force_evaluations'],12)
        self.assertEqual(self.records['dynamic_trajectories'],0)
        self.max_discrepancies=np.max(discrepancies,axis=0)
    def test_adapter_using_only_retained_values(self):
        m=runner.Model(47e-6)
        for state,result in zip(self.testplan['states'],self.records['results']):
            d=result['derivative_record'];lookup={x['q_m']:x for x in d['raw']}
            def force(a,q,n):
                self.assertEqual(a,d['angle_rad']);self.assertEqual(n,6)
                x=lookup[q]
                return {'generalized_force_N':x['Fq_N'],'pt':x['Ptranslation_W'],'pr':x['Protation_W']}
            with patch.object(m,'force',side_effect=force),patch.object(m,'driver_terms',side_effect=lambda r,a:(r['pt'],r['pr'],r['pt']+r['pr'])):
                J=m.jacobian(state[0],np.asarray(state[1:]),d['angle_dot_rad_s'])
            np.testing.assert_allclose(J,result['jacobian'],atol=1e-12,rtol=1e-13)
        self.assertEqual(m.force_evaluations,0)
    def test_zero_columns_both_polarities_and_kink(self):
        m=runner.Model(47e-6);p=self.plan
        for voltage,storage in [(2.,.2),(-2.,.2),(.1,2.),(0.,0.)]:
            y=np.array([0.,.02,m.cp*voltage,storage,1e152,-1e152,1e152,-1e152])
            actual=runner.branch_jacobian(y,m=m.m,k=m.k,c=m.c,theta=m.theta,cp=m.cp,cin=m.cin,R=m.R,dF_dq=7.,dPtrans_dq=.2,dProt_dq=-.1)
            np.testing.assert_allclose(actual,expected_matrix(y,p,[7.,.2,-.1]),atol=1e-12,rtol=1e-13)
            self.assertTrue(np.array_equal(actual[:,4:],np.zeros((8,4))))
            if abs(voltage)<=storage:self.assertTrue(np.array_equal(actual[:,3],np.zeros(8)))
    def test_rejected_values_and_nonfinite_telemetry(self):
        for bad_kind in ('piezo','storage','nan','infinity'):
            m=runner.Model(47e-6);m.last_accepted_t=.2;m.last_accepted_state=[0.]*8
            y=np.zeros(8)
            if bad_kind=='piezo':y[2]=m.cp*501
            elif bad_kind=='storage':y[3]=501
            elif bad_kind=='nan':y[0]=np.nan
            else:y[2]=np.inf
            with self.assertRaises(ValueError):m.validate(.3,y,'synthetic-review-probe')
            r=m.rejected_evaluation
            self.assertFalse(r['accepted_state']);self.assertEqual(r['phase'],'synthetic-review-probe')
            self.assertEqual(r['last_accepted_t_s'],.2)
            json.dumps(r,allow_nan=False)
            if bad_kind=='piezo':self.assertTrue(r['Vp_guard_failed']);self.assertFalse(r['Vs_guard_failed'])
            if bad_kind=='storage':self.assertTrue(r['Vs_guard_failed']);self.assertFalse(r['Vp_guard_failed'])
            self.assertEqual(m.force_evaluations,0)
    def test_bounded_step_support_and_refusal(self):
        for q in (0.,-.006,.007999,-.007999):
            h=runner.bounded_q_step(q)
            self.assertLessEqual(h,1e-7);self.assertLess(abs(q)+h,.008)
        for q in (.008,-.008,.009,np.nan,np.inf):
            with self.assertRaises(ValueError):runner.bounded_q_step(q)

if __name__=='__main__':unittest.main(verbosity=2)
