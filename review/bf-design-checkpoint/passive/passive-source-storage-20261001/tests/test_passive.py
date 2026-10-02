import json,sys,unittest,math
from pathlib import Path
import numpy as np
import tempfile,time,contextlib,io
from unittest.mock import patch,MagicMock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from passive_runner import Model,rectifier,polynomial_bounds,check_frozen,sha,Polynomial,require_complete,run_one

class PassiveControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=Model(47e-6);cls.eq=json.loads((ROOT/'outputs/EQUILIBRIUM-PREFLIGHT.json').read_text())
        cls.y=np.array([cls.eq['q0_m'],0,cls.eq['Q0_C'],0,0,0,0,0])
    def test_initial_physical_voltage_zero(self):self.assertEqual((self.y[2]-self.m.theta*self.y[0])/self.m.cp,0)
    def test_equilibrium_zero_motion_rhs(self):
        dy=self.m.rhs(0,self.y,0.)
        self.assertLess(abs(dy[1]),3e-8);self.assertTrue(np.all(np.delete(dy,1)==0))
    def test_bridge_bidirectional_passivity(self):
        for vp in [-12.,-2.,0.,2.,12.]:
            for vs in [0.,3.,20.]:
                I,i=rectifier(vp,vs,1e5)
                self.assertGreaterEqual(I,0);self.assertGreaterEqual(vp*i,-1e-20)
                self.assertAlmostEqual(vp*i,vs*I+1e5*I*I,places=15)
    def test_bridge_no_reverse_drain(self):self.assertEqual(rectifier(2.,3.,1e5),(0.,0.))
    def test_bridge_zero_unbiased(self):self.assertEqual(rectifier(0.,0.,1e5),(0.,0.))
    def test_storage_only_analytic_rc_control(self):
        # Analytic two-capacitor positive conducting branch, frozen mechanics.
        # Total Cp*Vp+Cin*Vs conserved; delta(t)=delta0*exp(-t/tau).
        cp=self.m.cp;cin=self.m.cin;R=self.m.R;tau=R*cp*cin/(cp+cin)
        vp0=10.;vs0=1.;charge=cp*vp0+cin*vs0
        for t in [0.,tau,5*tau]:
            delta=(vp0-vs0)*math.exp(-t/tau);vs=(charge-cp*delta)/(cp+cin);vp=vs+delta
            I,i=rectifier(vp,vs,R)
            self.assertAlmostEqual(cp*vp+cin*vs,charge,places=18)
            self.assertAlmostEqual(-i/cp-I/cin,-delta/tau,places=10)
            self.assertAlmostEqual(vp*(-i)+vs*I,-R*I*I,places=15)
    def test_charge_coordinate_energy_chain_rule(self):
        m=self.m;q=.001;u=-.03;vp=-4.;vs=.5;F=.12
        I,i=rectifier(vp,vs,m.R);qdd=(F-m.c*u-m.k*q+m.theta*vp)/m.m
        derivative=m.m*u*qdd+m.k*q*u+vp*(-i-m.theta*u)+vs*I
        self.assertAlmostEqual(derivative,F*u-m.c*u*u-m.R*I*I,places=15)
    def test_missing_reciprocal_sign_detected(self):
        m=self.m;u=.03;vp=4.
        self.assertGreater(abs(2*m.theta*vp*u),1e-6)
    def test_source_bindings(self):
        for p,h in json.loads((ROOT/'SOURCE-MANIFEST.json').read_text()).items():self.assertEqual(sha(ROOT/p),h)
    def test_direct_Cp_ritz(self):self.assertEqual(self.m.cp,self.m.rom['Cp_ritz_F'])
    def test_initial_signed_energy_retained(self):
        self.assertGreater(self.eq['initial_elastic_J'],0);self.assertLess(self.eq['initial_mutual_magnetic_J'],0)
    def test_gauge_invariant_residual(self):
        E0=-.006;Et=.004;D=.001;W=.011
        self.assertAlmostEqual(Et-E0+D-W,(Et+7)-(E0+7)+D-W,places=14)
    def test_driver_potential_derivative(self):
        m=self.m;q=self.y[0];h=1e-6
        r0=m.force(0.,float(q),10);r1=m.force(h,float(q),10);r2=m.force(2*h,float(q),10)
        _,_,analytic=m.driver_terms(r0,1.)
        numeric=(-3*r0['mutual_potential_J']+4*r1['mutual_potential_J']-r2['mutual_potential_J'])/(2*h)
        self.assertLess(abs(numeric-analytic),1e-8+1e-6*abs(analytic))
        (ROOT/'outputs/DRIVER-STATIC-CONTROL.json').write_text(json.dumps({'angle_rad':[0.,h,2*h],'q_m':float(q),'raw_U_J':[r['mutual_potential_J'] for r in [r0,r1,r2]],'analytic_dU_da':analytic,'finite_difference_dU_da':numeric,'additional_static_states':2,'dynamic_trajectories':0},indent=2)+'\n')
    def test_cubic_domain_extrema(self):
        lo,hi=polynomial_bounds(Polynomial([0,4,-4]));self.assertAlmostEqual(lo,0);self.assertAlmostEqual(hi,1)
    def test_domain_exit_refused(self):
        y=self.y.copy();y[0]=.009
        with self.assertRaises(ValueError):self.m.rhs(0,y,0.)
    def test_negative_storage_refused(self):
        y=self.y.copy();y[3]=-.001
        with self.assertRaises(ValueError):self.m.rhs(0,y,0.)
    def test_nonfinite_refused(self):
        y=self.y.copy();y[0]=float('nan')
        with self.assertRaises(ValueError):self.m.rhs(0,y,0.)
    def test_dynamic_auth_gate_closed(self):
        if (ROOT/'DYNAMIC-AUTHORIZATION.json').exists():self.skipTest('execution subsequently approved; tested closed in preflight')
        with self.assertRaises(FileNotFoundError):check_frozen()

class ExecutionIntegrityControls(unittest.TestCase):
    def test_complete_grid_control(self):
        a=np.zeros((4001,9));a[:,0]=np.linspace(0,4,4001);b=a[[0,-1]].copy();require_complete(a,b)
    def test_partial_grid_rejected(self):
        a=np.zeros((4001,9));a[:,0]=np.linspace(0,4,4001)
        for sample,accepted in [(a[:-1],a),(a,a[:-1]),(a[::-1],a),(a,a[::-1])]:
            with self.assertRaises(RuntimeError):require_complete(sample,accepted)
    def test_nonfinite_complete_grid_rejected(self):
        a=np.zeros((4001,9));a[:,0]=np.linspace(0,4,4001);a[100,1]=np.nan
        with self.assertRaises(RuntimeError):require_complete(a,a)
    def test_total_budget_in_cell(self):
        m=object.__new__(Model);m.plan=json.loads((ROOT/'PLAN.json').read_text());m.evaluations=0;m.force_evaluations=0;m.start=time.monotonic();m.study_deadline_unix=time.time()-1
        with self.assertRaises(RuntimeError):m.budget()
    def mock_abort(self,exception):
        # No ODE RHS, physical provider, or magnetic evaluation is invoked.
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);(temp/'outputs').mkdir()
            for f in ['PLAN.json','outputs/EQUILIBRIUM-PREFLIGHT.json']:(temp/f).write_bytes((ROOT/f).read_bytes())
            (temp/'PLAN-SEAL.json').write_text('{}')
            fake=MagicMock();fake.force.return_value={};fake.stored.return_value=np.zeros(5);fake.amax=1.;fake.start=time.monotonic();fake.evaluations=0;fake.force_evaluations=0;fake.last=None
            solver=MagicMock();solver.status='running';solver.step.side_effect=exception
            with patch('passive_runner.ROOT',temp),patch('passive_runner.check_frozen'),patch('passive_runner.Model',return_value=fake),patch('passive_runner.Radau',return_value=solver),contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(run_one('cin47','coarse'))
            summary=json.loads((temp/'outputs/cin47-coarse/SUMMARY.json').read_text())
            self.assertEqual(summary['status'],'INSUFFICIENT_NUMERICAL_EVIDENCE');self.assertEqual(summary['last_accepted_t_s'],0.)
            self.assertIsNotNone(summary['exception']);self.assertTrue((temp/'outputs/cin47-coarse/RUN-SEAL.json').exists())
            fake.rhs.assert_not_called()
    def test_keyboard_interrupt_fails_closed(self):self.mock_abort(KeyboardInterrupt())
    def test_system_exit_fails_closed(self):self.mock_abort(SystemExit(143))
    def test_timeout_fails_closed(self):self.mock_abort(RuntimeError('synthetic timeout'))

if __name__=='__main__':unittest.main()
