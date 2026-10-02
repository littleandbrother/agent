"""Read retained initializer and check synthetic algebra only; never import a provider.

No equilibrium solve, magnetic evaluation, time integration, or scientific run.
"""
from pathlib import Path
import hashlib
import json
import math
import unittest
import numpy as np

STUDY = Path('/workspace/shared/passive-source-storage-20261001')
ROM = Path('/workspace/shared/canonical-beam-rom-20261001/outputs/canonical-static-rom.json')


class StaticAndPowerReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads(ROM.read_text())
        cls.e = json.loads((STUDY/'outputs/EQUILIBRIUM-PREFLIGHT.json').read_text())

    def test_retained_root_initial_energy_and_charge(self):
        r, e = self.r, self.e
        q = e['q0_m']
        f = e['selected_root']['raw']['generalized_force_N']
        self.assertLess(abs(r['k_N_m']*q-f), 1e-9)
        self.assertLess(abs(q), .008-1e-5)
        self.assertAlmostEqual(e['Q0_C'], r['theta_C_m']*q, delta=1e-19)
        self.assertAlmostEqual(e['initial_elastic_J'], .5*r['k_N_m']*q*q, delta=1e-16)
        self.assertEqual(e['initial_mutual_magnetic_J'], e['selected_root']['raw']['mutual_potential_J'])
        for k in ('qdot0_m_s', 'Vpiezo0_V', 'Vstorage0_V', 'initial_piezo_J', 'initial_kinetic_J', 'initial_storage_J'):
            self.assertEqual(e[k], 0)
        self.assertIs(e['preparation_reset_work_qualified'], False)
        self.assertIs(e['scan_is_exhaustive_root_proof'], False)

    def test_retained_stability_derivatives(self):
        e, r = self.e, self.r
        q = e['q0_m']
        raw = e['raw_evaluations']
        for h, expected in zip(e['plan']['stability_steps_m'], e['selected_root']['effective_stiffness_N_m']):
            plus = next(x['Fq_N'] for x in raw if x['q_m'] == q+h and x['n'] == 10)
            minus = next(x['Fq_N'] for x in raw if x['q_m'] == q-h and x['n'] == 10)
            independently_recomputed = r['k_N_m']-(plus-minus)/(2*h)
            self.assertAlmostEqual(independently_recomputed, expected, delta=1e-10)
            self.assertGreater(independently_recomputed, e['plan']['minimum_stiffness_N_m'])
        # Positive short-circuit tangent is sufficient; fixed-charge electric
        # stiffness adds theta^2/Cp, it does not subtract it.
        self.assertGreater(r['theta_C_m']**2/r['Cp_ritz_F'], 0)

    def test_retained_projection_and_counts(self):
        e, r = self.e, self.r
        p = e['selected_root']['raw']
        f = p['force_beam_N']; tau = p['tip_torque_about_COM_beam_N_m']
        expected = f[2]+r['magnet_axial_shape']*f[0]-r['magnet_pitch_slope_per_m']*tau[1]
        self.assertAlmostEqual(p['generalized_force_N'], expected, delta=1e-14)
        self.assertEqual(len(e['raw_evaluations']), e['evaluations'])
        self.assertEqual(e['dynamic_trajectories'], 0)
        self.assertLess(e['evaluations'], e['plan']['maximum_evaluations'])
        self.assertTrue(all(x['contact']['obb_separated'] for x in e['raw_evaluations']))

    def test_synthetic_passive_power_identity(self):
        # Synthetic algebraic states, with arbitrary generalized and driver
        # magnetic powers. These are not physical states evaluated by a model.
        r = self.r
        k, m, theta, cp = (r[x] for x in ('k_N_m','mass_kg','theta_C_m','Cp_ritz_F'))
        c = 2*.02*math.sqrt(k*m)
        for cin in (47e-6, 10e-6):
            for q in (-.006, 0, .003):
                for u in (-.03, 0, .02):
                    for vp, vs in ((-3., .2), (2., .3), (.1, .5), (0., 0.)):
                        resistance = 1e5
                        imag = max(abs(vp)-vs, 0)/resistance
                        outflow = math.copysign(imag, vp) if vp else 0.
                        qcharge = theta*q+cp*vp
                        self.assertAlmostEqual((qcharge-theta*q)/cp, vp, delta=1e-12)
                        fmag = .07
                        magnetic_power_on_driver = -.005
                        acceleration = (fmag-c*u-k*q+theta*vp)/m
                        qcharge_dot = -outflow
                        vs_dot = imag/cin
                        # dE includes U_q*qdot+U_explicit_t. This sign includes
                        # prescribed driver's rotation and translation alike.
                        derivative = m*u*acceleration+k*q*u+vp*(qcharge_dot-theta*u)+cin*vs*vs_dot-fmag*u-magnetic_power_on_driver
                        expected = -magnetic_power_on_driver-c*u*u-resistance*imag*imag
                        self.assertAlmostEqual(derivative, expected, delta=1e-15)
                        self.assertGreaterEqual(vs_dot, 0.)
                        self.assertAlmostEqual(vp*outflow, vs*imag+resistance*imag*imag, delta=1e-19)

    def test_retained_driver_work_sign_and_derivative(self):
        control = json.loads((STUDY/'outputs/DRIVER-STATIC-CONTROL.json').read_text())
        world = json.loads((STUDY/'sources/world/world-v1.json').read_text())
        design = json.loads((STUDY/'sources/magnetic/sources/source-design.json').read_text())
        geometry = world['geometry']
        transform = np.asarray(geometry['force_from_world'])
        origin = np.asarray(design['door']['product_origin_world_mm'])/1000 + transform.T@np.array([design['beam']['clamp_end_x']/1000, 0, 0])
        pivot = transform@(np.asarray(geometry['pivot_world_m'])-origin)
        raw = self.e['selected_root']['raw']
        dr_da = np.cross([0.,1.,0.], np.asarray(raw['driver_center_beam_m'])-pivot)
        derivative = np.asarray(raw['force_beam_N'])@dr_da - raw['driver_torque_about_COM_beam_N_m'][1]
        u0, u1, u2 = control['raw_U_J']
        h = control['angle_rad'][1]
        finite_difference = (-3*u0+4*u1-u2)/(2*h)
        self.assertAlmostEqual(derivative, control['analytic_dU_da'], delta=1e-14)
        self.assertAlmostEqual(finite_difference, control['finite_difference_dU_da'], delta=1e-14)
        self.assertLess(abs(finite_difference-derivative), 1e-8+1e-6*abs(derivative))
        self.assertLess(derivative, 0.)
        self.assertGreater(abs(raw['driver_torque_about_COM_beam_N_m'][1]), 1e-4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
