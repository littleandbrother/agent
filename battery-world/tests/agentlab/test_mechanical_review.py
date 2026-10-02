import unittest
import numpy as np
from bfworld.agentlab.reference_checks import calculate
from bfworld.agentlab.mechanical_review import ForceTable, control


class MechanicalReviewTests(unittest.TestCase):
    def test_orientation_does_not_reverse_magnetization_twice(self):
        from scripts.run_magnetic_orientation_review import magnet_orientation
        r=magnet_orientation()
        a=np.deg2rad(r['driver_rotation_local_deg'][2])
        rotation=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])
        np.testing.assert_allclose(rotation@r['driver_magnetization_local'],
            r['driver_magnetization_in_unrotated_reference_frame'],atol=1e-14)
        self.assertEqual(-1,r['uniform_force_multiplier'])

    def test_units_reject_pi_report_factor_31_error(self):
        r=calculate({'kind':'elastic_displacement','inputs':{'energy_uJ':714.6,'stiffness_N_m':605.92},'reported_value':48.6})
        self.assertEqual('fail',r['arithmetic_check'])
        self.assertAlmostEqual(1.53582,r['value'],places=4)
        self.assertFalse(r['design_admission'])
        with self.assertRaisesRegex(ValueError,'UNITS'):
            calculate({'kind':'elastic_displacement','inputs':{'energy_J':714.6,'stiffness_N_m':605.92}})
        for bad in [float('nan'),-1,True,0]:
            with self.assertRaises(ValueError):calculate({'kind':'capacitor_energy','inputs':{'capacitance_uF':bad,'voltage_V':5.05}})

    def test_capacitance_bounds_and_stable_branch_controls(self):
        r=calculate({'kind':'capacitor_energy','inputs':{'capacitance_uF':2200,'voltage_V':5.05}})
        self.assertAlmostEqual(28052.75,r['value'])
        table=ForceTable([0,1],[-.008,0,.008],np.full((2,3),.1))
        roots=table.equilibria(0,100)
        self.assertEqual(1,len(roots));self.assertAlmostEqual(.001,roots[0]['q_m'])
        self.assertTrue(roots[0]['stable'])
        rom={'k':100,'mass':.01,'cp':2e-8,'theta':2e-4}
        spec={'mechanical':{'damping_ratio':.02,'opening_s':.1,'angle_deg':10}}
        fixed,_=control(rom,table,spec,'fixed_door',max_step=.005)
        released,_=control(rom,table,spec,'instant_force_removal',max_step=.005)
        self.assertLess(fixed['resistor_energy_J'],1e-14)
        self.assertGreater(released['resistor_energy_J'],1e-6)
        self.assertLess(released['relative_energy_residual'],1e-6)
        self.assertTrue(released['diagnostic_only'])
        self.assertFalse(released['full_door_loading_work_observed'])

    def test_loading_cycle_returns_to_far_magnet_not_closed_preload(self):
        table=ForceTable([0,1],[-.008,0,.008],[[.1,.1,.1],[0,0,0]])
        rom={'k':100,'mass':.01,'cp':2e-8,'theta':2e-4}
        spec={'mechanical':{'damping_ratio':.04,'opening_s':.1,'angle_deg':float(np.rad2deg(1))}}
        result,wave=control(rom,table,spec,'close_hold_open',max_step=.003)
        self.assertAlmostEqual(0,wave[0,1])
        self.assertGreater(max(abs(wave[:,1])),.0005)
        self.assertLess(abs(wave[-1,1]),.00005)
        self.assertLess(result['final_stored_J'],1e-8)
