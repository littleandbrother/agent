import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from bfworld.campaign.budget import Ledger,BudgetStop
class PaidRecoveryTests(unittest.TestCase):
 def test_process_death_after_reservation_blocks_duplicate_dispatch(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'cost.sqlite'
   code='from pathlib import Path;from bfworld.campaign.budget import Ledger;import os,sys;l=Ledger(Path(sys.argv[1]));l.reserve("call","trial",{"max_tokens":100});os._exit(137)'
   result=subprocess.run([sys.executable,'-c',code,str(path)],env=dict(os.environ),capture_output=True)
   self.assertEqual(result.returncode,137)
   l=Ledger(path)
   with self.assertRaises(BudgetStop):l.reserve('call','trial',{'max_tokens':100})
   self.assertEqual(l.summary()['calls'],1);self.assertEqual(l.summary()['unsettled'],1)
 def test_process_death_after_settlement_recovers_exact_response(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'cost.sqlite';receipt={'usage':{'prompt_tokens':12,'completion_tokens':3,'total_tokens':15},'content':'{"action":"submit"}'}
   code='from pathlib import Path;from bfworld.campaign.budget import Ledger;import os,sys,json;l=Ledger(Path(sys.argv[1]));l.reserve("call","trial",{"max_tokens":100});l.settle("call",json.loads(sys.argv[2]));os._exit(137)'
   result=subprocess.run([sys.executable,'-c',code,str(path),json.dumps(receipt)],env=dict(os.environ),capture_output=True)
   self.assertEqual(result.returncode,137);l=Ledger(path)
   self.assertEqual(l.reserve('call','trial',{'max_tokens':100}),receipt)
   self.assertEqual(l.summary()['calls'],1);self.assertEqual(l.summary()['unsettled'],0)
