import unittest
from bfworld.campaign.study import protocol,task,design_of
class ProtocolTests(unittest.TestCase):
 def test_preregistered_budget_and_disjoint_roles(self):
  p=protocol();self.assertLess(p['budget']['engineering_total_cny'],20)
  self.assertEqual(p['budget']['user_trial_cny'],2)
  self.assertTrue(p['all_arms_allow_python'])
  self.assertEqual(len(p['c_arms']),6)
 def test_task_id_does_not_embed_outcome(self):
  t=task(4,'c');self.assertNotIn('reference',t['public'])
  self.assertNotIn('receiver_loss',t['public']['conditions'])
  self.assertEqual(len(t['public']['candidates']),8)
  with self.assertRaises(ValueError):design_of(t,'unknown')
 def test_task_repeat_is_exact(self):self.assertEqual(task(3,'b'),task(3,'b'))
