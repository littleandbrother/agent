import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from numpy.polynomial import Polynomial as P
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import beam_rom as b

class StaticROM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=b.load_inputs(); cls.r=b.build()

    def test_source_pinned(self):
        self.assertEqual(self.r["provider_version"],b.VERSION)
        self.assertFalse(self.r["native_equivalent"])
        self.assertEqual(self.r["new_dynamic_runs"],0)

    def test_source_mass(self):
        self.assertAlmostEqual(self.r['magnet_mass_kg'],.0075,14)
        self.assertAlmostEqual(self.r['magnet_centroid_Jyy_kg_m2'],1.25e-7,19)

    def test_section_neutral_axis(self):
        p=self.p; r=self.r; zn=r['neutral_axis_patch_z_m'];zp=(p['copper_thickness']+p['pzt_thickness'])/2
        self.assertAlmostEqual(p['copper_young']*p['copper_width']*p['copper_thickness']*(0-zn)+p['pzt_young_E1']*p['pzt_width']*p['pzt_thickness']*(zp-zn),0,10)

    def test_normalization_and_clamp(self):
        self.assertAlmostEqual(self.r['phi_magnet_center'],1,13)
        p=P(self.r['shapes'][0]['phi_coefficients_in_local_x'])
        self.assertEqual(p(0),0);self.assertEqual(p.deriv()(0),0)

    def test_interface_continuity(self):
        spans=self.r['shapes']
        for a,c in zip(spans,spans[1:]):
            pa=P(a['phi_coefficients_in_local_x']);pc=P(c['phi_coefficients_in_local_x']);h=a['x_end_m']-a['x_start_m']
            self.assertAlmostEqual(pa(h),pc(0),13);self.assertAlmostEqual(pa.deriv()(h),pc.deriv()(0),12)
            ua=P(a['u0q_coefficients_in_local_x']);uc=P(c['u0q_coefficients_in_local_x'])
            self.assertAlmostEqual(ua(h),uc(0),13)

    def test_strain_energy_stiffness(self):
        self.assertAlmostEqual(self.r['k_N_m']/self.r['k_from_strain_energy_N_m'],1,13)

    def test_constitutive_capacitance_order(self):
        r=self.r
        self.assertLess(r['Cp_scalar_S1_fixed_Tother0_F'],r['Cp_ritz_F'])
        self.assertLess(r['Cp_ritz_F'],r['Cp_static_q_condensed_F'])
        self.assertLess(r['Cp_static_q_condensed_F'],r['Cfree_continuum_static_F'])
        self.assertLess(r['Cfree_continuum_static_F'],r['Cp_free_material_T_fixed_F'])

    def test_open_short_frequencies(self):
        self.assertGreater(self.r['f_OC_ritz_Hz'],self.r['f_SC_ritz_Hz'])

    def test_mass_decomposition(self):
        self.assertAlmostEqual(sum(self.r['mass_terms_kg'].values()),self.r['mass_kg'],14)

    def test_reciprocal_enthalpy_gradients(self):
        r=self.r;q=.0008;v=3.;dq=1e-8;dv=1e-4
        F=(b.enthalpy(r,q+dq,v)-b.enthalpy(r,q-dq,v))/(2*dq)
        Q=-(b.enthalpy(r,q,v+dv)-b.enthalpy(r,q,v-dv))/(2*dv)
        a=b.static_port(r,q,v)
        self.assertAlmostEqual(F/a['force_N'],1,9)
        self.assertAlmostEqual(Q/a['charge_C'],1,9)

    def test_volume_enthalpy_independent_quadrature(self):
        # Reintegrate primitive material enthalpy in x and z, before section reduction.
        # This tests N=0 axial condensation, electric-field signs and Cp exactly once.
        p=self.p;r=self.r;gp,gw=np.polynomial.legendre.leggauss(8)
        for q,v in [(0.,2.),(.001,0.),(.0008,3.)]:
            H=0.
            for sh in r['shapes']:
                if sh.get('rigid'):continue
                left,right=sh['x_start_m'],sh['x_end_m'];h=right-left
                curvature=P(sh['phi_coefficients_in_local_x']).deriv(2)
                patched=left==p['pzt_start']
                for xx,ww in zip((gp+1)*h/2,gw*h/2):
                    kap=q*curvature(xx)
                    ustrain=sh['neutral_axis_z_m']*kap
                    if patched:ustrain-=r['pzt_e31_scalar_C_m2']*p['pzt_width']/r['patch_axial_rigidity_N']*v
                    for zz,wz in zip(gp*p['copper_thickness']/2,gw*p['copper_thickness']/2):
                        S=ustrain-zz*kap
                        H+=ww*wz*p['copper_width']*.5*p['copper_young']*S*S
                    if patched:
                        for zz,wz in zip(p['copper_thickness']/2+(gp+1)*p['pzt_thickness']/2,gw*p['pzt_thickness']/2):
                            S=ustrain-zz*kap;E=-v/p['pzt_thickness']
                            density=.5*p['pzt_young_E1']*S*S-r['pzt_e31_scalar_C_m2']*S*E-.5*r['pzt_epsilon_S1_Tother0_F_m']*E*E
                            H+=ww*wz*p['pzt_width']*density
            self.assertAlmostEqual(H/b.enthalpy(r,q,v),1,11)

    def test_charge_energy_positive(self):
        r=self.r
        for q in [-.001,0,.001]:
            for charge in [-1e-6,0,1e-6]:
                U=.5*r['k_N_m']*q*q+.5*(charge-r['theta_C_m']*q)**2/r['Cp_ritz_F']
                self.assertGreaterEqual(U,0)

    def test_static_reciprocity(self):
        self.assertEqual(self.r['voltage_actuation_q_m_per_V'],self.r['short_circuit_charge_C_per_N'])

    def test_zero_piezo_coupling(self):
        p=copy.deepcopy(self.p);p['pzt_d31']=0;r=b.derive(p)
        self.assertEqual(r['theta_C_m'],0)
        self.assertAlmostEqual(r['Cp_ritz_F']/r['Cp_free_material_T_fixed_F'],1,13)
        self.assertEqual(r['f_OC_ritz_Hz'],r['f_SC_ritz_Hz'])

    def test_polarity_flip(self):
        p=copy.deepcopy(self.p);p['poling_sign']=-1;r=b.derive(p)
        self.assertEqual(r['theta_C_m'],-self.r['theta_C_m'])
        for key in ['Cp_ritz_F','k_N_m','mass_kg','f_OC_ritz_Hz']:
            self.assertEqual(r[key],self.r[key])

    def test_geometric_unit_scaling(self):
        p=copy.deepcopy(self.p)
        for key,u in b.UNITS.items():
            if u=='m':p[key]*=2
        r=b.derive(p)
        for key,ratio in [('k_N_m',2),('mass_kg',8),('theta_C_m',2),('Cp_ritz_F',2),('f_SC_ritz_Hz',.5)]:
            self.assertAlmostEqual(r[key]/self.r[key],ratio,11)

    def test_negative_geometry(self):
        p=copy.deepcopy(self.p);p['pzt_thickness']=-.003
        with self.assertRaises(ValueError):b.derive(p)

    def test_nonfinite_rejected(self):
        p=copy.deepcopy(self.p);p['pzt_d31']=float('nan')
        with self.assertRaises(ValueError):b.derive(p)
        with self.assertRaises(ValueError):b.static_port(self.r,float('nan'),0)

    def test_nonpassive_material(self):
        p=copy.deepcopy(self.p);p['pzt_d31']=-1e-6
        with self.assertRaises(ValueError):b.derive(p)

    def test_unknown_or_wrong_units(self):
        d=json.loads((b.ROOT/'parameters.json').read_text())
        for value in ['mm','F','unknown']:
            d['parameters']['pzt_thickness']['unit']=value
            with tempfile.TemporaryDirectory() as t:
                f=Path(t)/'p.json';f.write_text(json.dumps(d))
                with self.assertRaises(ValueError):b.load_inputs(f)

    def test_missing_parameter(self):
        p=copy.deepcopy(self.p);del p['pzt_d31']
        with self.assertRaises(ValueError):b.derive(p)

    def test_dynamic_adapter_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,'Static-only'):b.dynamic_export(self.r)

    def test_pose_rotation_is_proper(self):
        for q in [-.008,0,.008]:
            a=b.pose_and_jacobian(self.r,q,.005265);R=np.asarray(a['rotation_from_reference'])
            self.assertTrue(np.allclose(R@R.T,np.eye(3),atol=1e-14))
            self.assertAlmostEqual(np.linalg.det(R),1,13)

    def test_force_virtual_work_synthetic_potential(self):
        # U(x,z,beta)=Ax^2/2+Bz^2/2+Cxz+D sin(beta)+Ex cos(beta)
        # Analytic F=-grad_r U and tau_y=-dU/dbeta, compared to -dU(q)/dq.
        r=self.r;A,B,C,D,E=3.,4.,.7,.003,.06
        def values(q):
            s=b.pose_and_jacobian(r,q,.005265);x,_,z=s['center_m'];beta=s['pitch_about_positive_y_rad']
            U=.5*A*x*x+.5*B*z*z+C*x*z+D*math.sin(beta)+E*x*math.cos(beta)
            F=[-A*x-C*z-E*math.cos(beta),0.,-B*z-C*x]
            tau=[0.,-D*math.cos(beta)+E*x*math.sin(beta),0.]
            return U,b.project_force(r,F,tau)
        for q in [-.001,0,.001]:
            h=1e-7;fd=-(values(q+h)[0]-values(q-h)[0])/(2*h)
            self.assertAlmostEqual(fd/values(q)[1],1,8)

    def test_missing_axial_or_torque_is_detectable(self):
        r=self.r
        self.assertNotEqual(b.project_force(r,[1,0,0],[0,0,0]),0)
        self.assertNotEqual(b.project_force(r,[0,0,0],[0,1,0]),0)

    def test_dimension_identities(self):
        # SI base dimensions [mass,length,time,current], independent of numbers.
        kg=np.array([1,0,0,0]);m=np.array([0,1,0,0]);s=np.array([0,0,1,0]);amp=np.array([0,0,0,1])
        N=kg+m-2*s;C=amp+s;V=kg+2*m-3*s-amp;F=C-V
        EI=N+2*m;curvature=-2*m;length=m
        self.assertTrue(np.array_equal(EI+2*curvature+length,N-m))
        theta=C-m;k=N-m
        self.assertTrue(np.array_equal(theta+V,N))
        self.assertTrue(np.array_equal(2*theta-k,F))
        eps=F-m;d=C-N;young=N-2*m
        self.assertTrue(np.array_equal(young+2*d,eps))

if __name__=='__main__':unittest.main(verbosity=2)
