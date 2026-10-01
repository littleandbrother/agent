"""Source, geometry, domain and retained-result tests; no new magnetic states."""
import copy,hashlib,json,math,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from magnetic_interface import Cuboid,DomainError,StaticMagneticInterface,proper_rotation,potential_force_torque,separation_diagnostic

class StaticInterfaceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.m=StaticMagneticInterface();cls.results=json.loads((ROOT/'outputs'/'STATIC-RESULTS.json').read_text())
  cls.summary=json.loads((ROOT/'outputs'/'SUMMARY.json').read_text());cls.frames=json.loads((ROOT/'outputs'/'FRAME-VERIFICATION.json').read_text())
 def test_plan_sealed(self):
  self.assertEqual(hashlib.sha256((ROOT/'STATIC-PLAN.json').read_bytes()).hexdigest(),json.loads((ROOT/'PLAN-SEAL.json').read_text())['plan_sha256'])
 def test_source_bindings(self):
  for x in self.m.plan['source_bindings'].values():self.assertEqual(hashlib.sha256((ROOT/x['snapshot_path']).read_bytes()).hexdigest(),x['sha256'])
 def test_provider_matches_evaluated_hash(self):
  self.assertEqual(hashlib.sha256((ROOT/'magnetic_interface.py').read_bytes()).hexdigest(),self.results['identity']['implementation_sha256'])
 def test_exact_five_state_plan(self):
  self.assertEqual([(s['angle_deg'],s['q_m']) for s in self.m.plan['states']],[(0,0),(2,-.004),(2,.004),(15,.004),(65,0)])
  self.assertEqual([r['state'] for r in self.results['states']],self.m.plan['states'])
 def test_exact_orders_steps(self):
  for row in self.results['states']:
   self.assertEqual([r['quadrature_order'] for r in row['orders']],[4,6,10])
   for r in row['orders']:self.assertEqual([d['h_m'] for d in r['q_energy_finite_differences']],[2e-6,1e-6,5e-7])
 def test_static_boundary(self):
  self.assertEqual(self.results['identity']['static_voltage_V'],0)
  for k in ['extra_magnetic_states','table_sweeps','time_integrations','equilibrium_solves']:self.assertEqual(self.results['identity'][k],0)
  self.assertFalse(self.results['identity']['physical_qualified']);self.assertFalse(self.results['identity']['native_equivalent'])
 def test_frame_origin(self):
  np.testing.assert_allclose(self.frames['beam_origin_world_m'],[1,.070,2.140],rtol=0,atol=1e-15)
  np.testing.assert_allclose(self.frames['canonical_rest_tip_world_m'],[.904,.075265,2.140],rtol=0,atol=1e-15)
 def test_proper_rotations_and_signs(self):
  self.assertTrue(self.frames['verified_before_force_evaluation'])
  for row in self.results['states']:
   for r in row['orders']:
    proper_rotation(r['tip_rotation']);proper_rotation(r['driver_rotation'])
    self.assertLess(self.frames['states'][self.results['states'].index(row)]['relative_formula_max_error_m'],2e-15)
 def test_q0_polarity(self):
  r=self.results['states'][0]['orders'][-1]
  self.assertEqual(r['tip_magnetization_unit_beam'],[1,0,0]);self.assertEqual(r['driver_magnetization_unit_beam'],[1,0,0])
 def test_geometry_matches_old_at_q0(self):
  for i in [0,4]:
   for r in self.results['states'][i]['orders']:
    np.testing.assert_allclose(r['force_beam_N'],r['legacy_fixed_tip_force_beam_N'],rtol=2e-10,atol=1e-13)
 def test_projection_terms(self):
  for row in self.results['states']:
   for r in row['orders']:self.assertAlmostEqual(sum(r['projection_terms'].values()),r['generalized_force_N'],places=14)
 def test_45_energy_derivatives(self):
  values=[d for row in self.results['states'] for r in row['orders'] for d in r['q_energy_finite_differences']]
  self.assertEqual(len(values),45);self.assertTrue(all(d['passed'] for d in values))
 def test_quadrature_checks(self):
  self.assertTrue(all(r['quadrature_check']['passed'] for r in self.results['states']))
 def test_internal_moment_balance(self):
  for row in self.results['states']:
   for r in row['orders']:self.assertLess(np.linalg.norm(r['internal_moment_balance_N_m']),1e-14)
 def test_contact_diagnostic_is_not_exact_clearance(self):
  for row in self.results['states']:
   for r in row['orders']:
    self.assertTrue(r['contact']['obb_separated']);self.assertGreater(r['contact']['surface_distance_lower_bound_m'],0)
    self.assertIn('only',r['contact']['scope'])
 def test_force_only_negative_control_fails_chain_rule(self):
  r=self.results['states'][0]['orders'][-1];fd=r['q_energy_finite_differences'][-1]
  self.assertGreater(abs(fd['minus_dU_dq_N']-r['force_beam_N'][2]),1000*fd['predeclared_tolerance_N'])
 def test_missing_torque_negative_control_fails(self):
  r=self.results['states'][3]['orders'][-1];fd=r['q_energy_finite_differences'][-1]
  wrong=r['projection_terms']['transverse_Fz_N']+r['projection_terms']['axial_virtual_work_N']
  self.assertGreater(abs(wrong-fd['minus_dU_dq_N']),1000*fd['predeclared_tolerance_N'])
 def test_reflection_rejected(self):
  with self.assertRaises(DomainError):proper_rotation(np.diag([-1,1,1]))
 def test_nonfinite_inputs_rejected_before_force(self):
  for args in [(float('nan'),0),(0,float('inf')),(True,0)]:
   with self.assertRaises(DomainError):self.m.pose(*args)
 def test_outside_support_rejected_before_force(self):
  for args in [(-.01,0),(2,0),(0,.00801),(0,-.00801)]:
   with self.assertRaises(DomainError):self.m.pose(*args)
  for gap in [.027,.071]:
   with self.assertRaises(DomainError):self.m.pose(0,0,gap)
 def test_overlap_touch_rejected_before_quadrature(self):
  size=np.array(self.m.world['geometry']['tip_size_m']);br=self.m.world['force']['remanence_T']
  a=Cuboid(np.zeros(3),np.eye(3),size,br)
  for center in [np.zeros(3),np.array([size[0],0,0])]:
   b=Cuboid(center,np.eye(3),size,br)
   self.assertFalse(separation_diagnostic(a,b)['obb_separated'])
   with self.assertRaises(DomainError):potential_force_torque(a,b,6)
 def test_inherited_material_identity(self):
  self.assertEqual(self.m.world['force']['remanence_T'],1.25);self.assertEqual(self.m.world['force']['recoil_permeability'],1)
  self.assertEqual(self.m.design['magnets']['relative_permeability'],1.05) # source disagreement is retained, not silently erased
 def test_rom_coefficients_reproduced(self):
  saved=json.loads((ROOT/'sources'/'beam-static-rom.json').read_text())
  for k in ['k_N_m','mass_kg','theta_C_m','Cp_ritz_F','magnet_pitch_slope_per_m','magnet_axial_shape']:
   self.assertAlmostEqual(self.m.rom[k],saved[k],places=13)
 def test_replay_recording_frozen(self):
  p=ROOT/'evidence-completion-replay';seal=json.loads((p/'REPLAY-SEAL.json').read_text())
  self.assertEqual(hashlib.sha256((p/'replay.py').read_bytes()).hexdigest(),seal['recording_code_sha256'])
  self.assertEqual(hashlib.sha256((ROOT/'outputs/STATIC-RESULTS.json').read_bytes()).hexdigest(),seal['original_result_sha256'])
 def test_replay_exact_reproduction(self):
  r=json.loads((ROOT/'evidence-completion-replay/RAW-REPLAY-RESULTS.json').read_text())
  self.assertFalse(r['independent_samples']);self.assertEqual(r['new_physical_states'],0)
  self.assertEqual(len(r['comparison_checks']),105)
  self.assertTrue(all(c['passed'] and c['max_absolute_difference']==0 for c in r['comparison_checks']))
 def test_raw_potential_derivatives(self):
  r=json.loads((ROOT/'evidence-completion-replay/RAW-REPLAY-RESULTS.json').read_text());count=0
  for row in r['states']:
   for order in row['orders']:
    for pair in order['raw_perturbation_pairs']:
     fd=-(pair['plus']['mutual_potential_J']-pair['minus']['mutual_potential_J'])/(2*pair['h_m'])
     self.assertEqual(fd,pair['minus_dU_dq_N'])
     self.assertLessEqual(abs(fd-pair['analytic_projection_N']),pair['predeclared_virtual_work_tolerance_N'])
     for sign in ['plus','minus']:self.assertTrue(pair[sign]['contact']['obb_separated'])
     count+=1
  self.assertEqual(count,45)
if __name__=='__main__':unittest.main(verbosity=2)
