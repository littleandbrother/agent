"""No trajectories, provider evaluations, magnetic states, or plan mutations."""
from pathlib import Path
import json,hashlib,math,sys,unittest
import numpy as np
from scipy.integrate._ivp.common import num_jac
import scipy.integrate._ivp.common as common
from jacobian_proposal import branch_jacobian,bounded_q_step,guarded_voltage,RecordedGuardError
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
PLAN=json.loads((ROOT/'PLAN.json').read_text());p=PLAN['mechanics']
K={'m':p['mass_kg'],'k':p['k_N_m'],'c':2*.02*math.sqrt(p['mass_kg']*p['k_N_m']),'theta':p['theta_C_m'],'cp':p['Cp_ritz_F'],'cin':47e-6,'R':1e5}

def synthetic_rhs(y):
    q,u,Q,vs=y[:4];vp=(Q-K['theta']*q)/K['cp'];I=max(abs(vp)-vs,0)/K['R'];i=np.sign(vp)*I
    # Synthetic linear magnetic force and driver-work functions, not a force
    # provider or a claim about an additional physical state.
    F=.03+7*q;Pt=.002+.2*q;Pr=-.001-.1*q
    return np.array([u,(F-K['c']*u-K['k']*q+K['theta']*vp)/K['m'],-i,I/K['cin'],K['c']*u*u,K['R']*I*I,Pt,Pr])

class AlgebraicRepairControls(unittest.TestCase):
    def test_piecewise_jacobian_matches_bounded_difference(self):
        for vp,vs in [(2.,.1),(-2.,.1),(.1,2.),(0.,2.)]:
            q=.001;y=np.array([q,.02,K['theta']*q+K['cp']*vp,vs,1e-4,2e-5,.003,-.0001])
            J=branch_jacobian(y,**K,dF_dq=7.,dPtrans_dq=.2,dProt_dq=-.1)
            for i,h in enumerate([1e-9,1e-7,1e-15,1e-6,1e-7,1e-7,1e-7,1e-7]):
                d=np.zeros(8);d[i]=h;fd=(synthetic_rhs(y+d)-synthetic_rhs(y-d))/(2*h)
                self.assertTrue(np.allclose(fd,J[:,i],atol=2e-6,rtol=1e-6),(vp,vs,i,fd,J[:,i]))
    def test_all_ledger_feedback_columns_exactly_zero(self):
        y=np.array([0.,.02,K['cp']*2,.1,0,0,0,0]);J=branch_jacobian(y,**K,dF_dq=7,dPtrans_dq=.2,dProt_dq=-.1)
        self.assertTrue(np.array_equal(J[:,4:],np.zeros((8,4))))
    def test_bridge_off_storage_feedback_exactly_zero(self):
        y=np.array([0.,.02,K['cp']*.1,2.,0,0,0,0]);J=branch_jacobian(y,**K,dF_dq=7,dPtrans_dq=.2,dProt_dq=-.1)
        self.assertTrue(np.array_equal(J[:,3],np.zeros(8)))
    def test_exact_kink_convention_finite(self):
        y=np.array([0.,.02,0.,0.,0,0,0,0]);J=branch_jacobian(y,**K,dF_dq=7,dPtrans_dq=.2,dProt_dq=-.1)
        self.assertTrue(np.isfinite(J).all());self.assertTrue(np.array_equal(J[[2,3,5]],np.zeros((3,8))))
    def test_bounded_q_interval(self):
        for q in [0,.007999,-.007999]:
            h=bounded_q_step(q);self.assertLess(abs(q)+h,.008);self.assertLessEqual(h,1e-7)
        for q in [.008,.009,float('nan')]:
            with self.assertRaises(ValueError):bounded_q_step(q)
    def test_exact_rejected_probe_telemetry(self):
        y=np.array([0.,.02,K['cp']*.1,501.,1e-4,2e-5,.003,1e152])
        with self.assertRaises(RecordedGuardError) as caught:guarded_voltage(y,t=1.,theta=K['theta'],cp=K['cp'],phase='jacobian_q_probe',last_accepted_t=.99)
        r=caught.exception.record;self.assertEqual(r['rejected_state'],y.tolist());self.assertTrue(r['Vs_guard_failed']);self.assertFalse(r['Vp_guard_failed']);self.assertEqual(r['phase'],'jacobian_q_probe');self.assertFalse(r['accepted_state'])
    def test_uncapped_fd_probe_failure_reproduction(self):
        y=np.array([0.,.02,K['cp']*.1,2.,1e-4,2e-5,.003,-.0001]);factor=None;rejected=[];history=[]
        def guarded(t,Y):
            out=[]
            for z in Y.T:
                vp=(z[2]-K['theta']*z[0])/K['cp']
                if abs(vp)>500 or z[3]>500:
                    rejected.append({'state':z.tolist(),'Vp_V':vp,'Vs_V':z[3]});raise ValueError('synthetic computational voltage guard')
                out.append(synthetic_rhs(z))
            return np.array(out).T
        for attempt in range(100):
            try:
                _,factor=num_jac(guarded,0.,y,synthetic_rhs(y),np.array(PLAN['resolutions']['coarse']['atol']),factor)
                history.append({'attempt':attempt+1,'factor':factor.tolist()})
            except ValueError:break
        self.assertTrue(rejected);self.assertGreater(rejected[0]['Vs_V'],500)
        self.assertAlmostEqual(rejected[0]['Vp_V'],.1,places=15)
        (HERE/'SYNTHETIC-FD-PROBE-REPRODUCTION.json').write_text(json.dumps({'scope':'Repeated derivative probes at one synthetic algebraic state; not a trajectory and not a replay of the unrecorded actual failed probe','num_jac_source_path':common.__file__,'num_jac_source_sha256':hashlib.sha256(Path(common.__file__).read_bytes()).hexdigest(),'physical_force_evaluations':0,'dynamic_trajectories':0,'completed_derivative_calls':len(history),'history':history,'rejected_probe':rejected[0]},indent=2)+'\n')

if __name__=='__main__':unittest.main()
