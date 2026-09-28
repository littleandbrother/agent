import copy
import unittest
from bfworld.campaign.splits import environment_hash, task_record, validate_registry, learning_feedback, launch_readiness

PHYSICS = {'source':{'family':'rotary','peak_a':.0033,'phase_rad':0.,'rpm':120},
 'initial_state':{'storage_v':2.65},'load_profile':{'tx_power_w':.036,'tx_duration_s':.04},
 'receiver':{'loss':False},'model_card':{'weights':[1,-1],'threshold':25},
 'label':'bearing-fault','deadline_s':1.1,'candidate_designs':[
 {'id':'d1','capacitance_f':.00033,'esr_ohm':18}, {'id':'d2','capacitance_f':.0022,'esr_ohm':4}],
 'reference_version':'coupled-v1'}


class SplitTests(unittest.TestCase):
 def test_renaming_order_numeric_types_and_session_do_not_create_transfer(self):
  p=copy.deepcopy(PHYSICS);p['candidate_designs'].reverse();p['candidate_designs'][0]['id']='renamed'
  p['source']['device_session']='new-session';p['source']['rpm']=120.;p['model_card']['id']='new-card-name'
  p['reference_version']='renamed-reference'
  self.assertEqual(environment_hash(p),environment_hash(PHYSICS))
  with self.assertRaisesRegex(ValueError,'share physical'):
   validate_registry([task_record('dev','development',PHYSICS),task_record('new-id','blind-transfer',p)])
 def test_explicit_new_physics_and_exposure_gate(self):
  p=copy.deepcopy(PHYSICS);p['source']['phase_rad']=.29
  self.assertNotEqual(environment_hash(p),environment_hash(PHYSICS))
  self.assertEqual(validate_registry([task_record('dev','development',PHYSICS),task_record('new','blind-transfer',p)])['tasks'],2)
  with self.assertRaises(ValueError):task_record('old-final','blind-transfer',p,prior_exposure='observed-final')
  with self.assertRaises(ValueError):validate_registry([task_record('new','blind-transfer',p)],[environment_hash(p)])
 def test_regression_must_be_explicit_not_fake_transfer(self):
  tasks=[task_record('dev','development',PHYSICS,prior_exposure='public'),task_record('old','regression',PHYSICS,prior_exposure='public',regression_of='dev')]
  self.assertEqual(validate_registry(tasks)['unique_environments'],1)
  tasks[1]=task_record('old','regression',PHYSICS,prior_exposure='public')
  with self.assertRaises(ValueError):validate_registry(tasks)
 def test_blind_feedback_is_not_learning_input(self):
  for split in ('blind-transfer','regression','out-of-scope'):
   with self.assertRaises(ValueError):learning_feedback(task_record(split,split,PHYSICS),{'pass':True})
  self.assertEqual(learning_feedback(task_record('dev','development',PHYSICS),{'pass':False})['split'],'development')
 def test_incomplete_protocol_cannot_dispatch(self):
  self.assertFalse(launch_readiness({})['paid_dispatch_allowed'])
  self.assertFalse(launch_readiness({'status':'owner-approved','owner_approval':'invented'})['ready'])
 def test_invalid_physics_and_hash_tamper(self):
  p=copy.deepcopy(PHYSICS);p['source']['peak_a']=float('nan')
  with self.assertRaises(ValueError):environment_hash(p)
  p=copy.deepcopy(PHYSICS);p['candidate_designs'][0]['capacitance_f']=-.1
  with self.assertRaises(ValueError):environment_hash(p)
  t=task_record('a','development',PHYSICS);t['physics']=p
  with self.assertRaises(ValueError):validate_registry([t])
