import tempfile
import unittest
from pathlib import Path
from bfworld.campaign.sandbox import preflight,execute
class IsolationTests(unittest.TestCase):
 def test_real_private_network_write_and_fork_denial(self):
  repo=Path(__file__).resolve().parents[2]
  report=preflight(repo/'.bfworld/sandbox-tests',repo/'PROJECT.yaml')
  self.assertEqual(report['status'],'pass')
 def test_pure_program_detaches_from_session(self):
  repo=Path(__file__).resolve().parents[2]
  self.assertEqual(execute('def plan(ctx): return sorted(ctx["values"])',{'values':[3,1,2]},repo/'.bfworld/sandbox-tests'),[1,2,3])
