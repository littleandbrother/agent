import importlib.util,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('diagnostic_profiled',here/'build_b2_profiled.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RuntimeDiagnostic(unittest.TestCase):
 def test_actual_linux_preflight_is_nonzero_before_artifacts(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'never-created'
   with self.assertRaisesRegex(RuntimeError,'B2_PROFILED_UNSUPPORTED_RUNTIME.*sandbox-exec'):m.build(p)
   self.assertFalse(p.exists())
 def test_missing_configured_python_stays_blocked(self):
  with patch.object(Path,'is_file',lambda p:str(p)=='/usr/bin/sandbox-exec'),patch.object(m.os,'access',return_value=True):
   with self.assertRaisesRegex(RuntimeError,'B2_PROFILED_UNSUPPORTED_RUNTIME.*Python.framework'):m.require_isolation_runtime()
 def test_present_executables_only_pass_availability(self):
  with patch.object(Path,'is_file',return_value=True),patch.object(m.os,'access',return_value=True):m.require_isolation_runtime()
 def test_nonexecutable_runtime_stays_blocked(self):
  with patch.object(Path,'is_file',return_value=True),patch.object(m.os,'access',return_value=False):
   with self.assertRaisesRegex(RuntimeError,'UNSUPPORTED_RUNTIME'):m.require_isolation_runtime()
 def test_unevaluated_variant_reports_gate_not_keyerror(self):
  result=[{'id':'fixture','evaluated':False,'mechanical':{'passed':False,'error':'sandbox unavailable'}}]
  with self.assertRaisesRegex(RuntimeError,'B2_PROFILED_MECHANICAL_GATE_BLOCKED.*sandbox unavailable'):m.require_evaluated_variants(result)
 def test_evaluated_variant_preserves_existing_path(self):m.require_evaluated_variants([{'id':'fixture','evaluated':True,'tasks':[]}])
if __name__=='__main__':unittest.main(verbosity=2)
