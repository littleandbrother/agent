import math,sys,unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from ltc3588_rail_contract_v2 import *
class RailContract(unittest.TestCase):
    def test_zero_initial_rails(self):
        r=ideal_settled_rails(0);self.assertEqual(r['total_bypass_energy_j'],0)
    def test_sub_uvlo_rails_not_forced_zero(self):
        r=ideal_settled_rails(2.5);self.assertEqual(r['vin2_v'],2.5);self.assertEqual(r['cap_v'],0)
        self.assertAlmostEqual(r['total_bypass_energy_j'],17.8125e-6)
        r=ideal_settled_rails(4.5);self.assertAlmostEqual(r['total_bypass_energy_j'],57.7125e-6)
    def test_cap_is_differential(self):
        r=ideal_settled_rails(10);self.assertEqual(r['cap_v'],5.2);self.assertEqual(r['vin_minus_cap_v'],4.8)
        self.assertAlmostEqual(r['cap_energy_j'],11.52e-6);self.assertAlmostEqual(r['total_bypass_energy_j'],65.664e-6)
    def test_static_relation_continuous_and_no_second_gate(self):
        a,b=ideal_settled_rails(4.8-1e-9),ideal_settled_rails(4.8+1e-9)
        self.assertLess(abs(a['total_bypass_energy_j']-b['total_bypass_energy_j']),1e-12)
        self.assertIsNone(b['instantaneous_startup_threshold_j']);self.assertIsNone(b['settling_time_s'])
    def test_uvlo_hysteresis(self):
        s=advance_nominal_event_logic(LogicState(),5,0);self.assertFalse(s.buck_enabled)
        s=advance_nominal_event_logic(s,5.05,0);self.assertTrue(s.buck_enabled)
        s=advance_nominal_event_logic(s,4,0);self.assertTrue(s.buck_enabled)
        s=advance_nominal_event_logic(s,3.67,0);self.assertFalse(s.buck_enabled)
    def test_pgood_does_not_initially_assert_at_92_percent(self):
        s=advance_nominal_event_logic(LogicState(),5.1,3.2);self.assertTrue(s.buck_enabled);self.assertFalse(s.pgood)
        s=advance_nominal_event_logic(s,5.1,3.312,converter_sleep_event=True);self.assertTrue(s.pgood)
    def test_pgood_can_survive_uvlo(self):
        s=advance_nominal_event_logic(LogicState(True,True),3.5,3.2)
        self.assertFalse(s.buck_enabled);self.assertTrue(s.pgood)
        s=advance_nominal_event_logic(s,3.4,3);self.assertFalse(s.pgood)
    def test_contradictory_sleep_event_rejected(self):
        with self.assertRaises(ValueError):advance_nominal_event_logic(LogicState(),3,3.312,converter_sleep_event=True)
    def test_transient_prediction_fails_closed(self):
        with self.assertRaisesRegex(MissingDynamicEvidence,'BLOCKED'):require_transient_startup_prediction()
    def test_invalid_inputs_rejected(self):
        for v in [math.nan,math.inf,-1,True]:
            with self.assertRaises(ValueError):ideal_settled_rails(v)
    def test_logic_state_requires_real_booleans(self):
        for state in [LogicState(1,False),LogicState(False,'yes'),LogicState(None,False)]:
            with self.assertRaises(ValueError):advance_nominal_event_logic(state,5,3)
    def test_policy_is_finite_and_nonboolean(self):
        for name in ('uvlo_rise_v','uvlo_fall_v','vout_target_v','sleep_threshold_v','pgood_fall_fraction'):
            for value in [math.inf,math.nan,True]:
                with self.assertRaises(ValueError):advance_nominal_event_logic(LogicState(),5,3,policy=replace(Nominal3V3Policy(),**{name:value}))
if __name__=='__main__':unittest.main()
