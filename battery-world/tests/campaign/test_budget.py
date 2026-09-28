import tempfile
import unittest
from pathlib import Path
from bfworld.campaign.budget import Ledger,BudgetStop
class BudgetTests(unittest.TestCase):
 def test_reserve_settle_repeat_conflict(self):
  with tempfile.TemporaryDirectory() as tmp:
   l=Ledger(Path(tmp)/'cost.db');request={'max_tokens':100,'messages':['hello']}
   self.assertIsNone(l.reserve('a','trial',request));r={'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
   l.settle('a',r);self.assertEqual(l.reserve('a','trial',request),r)
   self.assertEqual(l.summary()['calls'],1)
   with self.assertRaises(BudgetStop):l.reserve('a','trial',{'max_tokens':101})
 def test_unknown_calls_cannot_retry_or_release_budget(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'cost.db';l=Ledger(p);l.reserve('a','t',{'max_tokens':100})
   with self.assertRaises(BudgetStop):Ledger(p).reserve('a','t',{'max_tokens':100})
   self.assertGreater(l.summary()['accounted_upper_bound_cny'],0)
   with self.assertRaises(BudgetStop):l.settle('a',{'usage':{}})
 def test_limits_before_dispatch(self):
  with tempfile.TemporaryDirectory() as tmp:
   l=Ledger(Path(tmp)/'cost.db',total=100)
   with self.assertRaises(BudgetStop):l.reserve('a','t',{'max_tokens':100})
   self.assertEqual(l.summary()['calls'],0)
