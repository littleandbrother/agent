"""Independent trusted-fixture and fail-closed checks; no production dispatch."""
import copy, hashlib, json, os, py_compile, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path('/workspace/shared/world-evaluator-independent-review-20261001/snapshots/protocol')
sys.path.insert(0,str(ROOT));import preflight as p
from test_preflight import complete_contract, approve
class Audit(unittest.TestCase):
 def test_all_source_bytes_and_external_sources(self):
  for r in json.loads((ROOT/'FILE-MANIFEST.json').read_text())['files']:
   path=ROOT/r['path'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),r['sha256']);self.assertEqual(path.stat().st_size,r['bytes'])
  for r in json.loads((ROOT/'SOURCE-MANIFEST.json').read_text())['files']:
   path=Path(r['path']);self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),r['sha256']);self.assertEqual(path.stat().st_size,r['bytes'])
 def test_draft_fails_closed_and_no_dispatch(self):
  proc=subprocess.run([sys.executable,'-B',str(ROOT/'preflight.py'),str(ROOT/'protocol-draft.json')],capture_output=True,text=True)
  self.assertEqual(proc.returncode,2);result=json.loads(proc.stdout);self.assertFalse(result['contract_complete']);self.assertFalse(result['live_launch_allowed']);self.assertEqual(result['provider_calls'],0)
 def test_each_independence_flag_required(self):
  base=complete_contract()
  for key,value in base['independence'].items():
   if type(value) is not bool:continue
   plan=copy.deepcopy(base);plan['independence'][key]=False;res=p.check_plan(approve(plan))
   self.assertFalse(res['contract_complete'],key);self.assertFalse(res['live_launch_allowed'])
 def test_exact_approval_binding(self):
  base=complete_contract();base['h_loop']['h0_hash']='f'*64
  self.assertIn('OWNER_APPROVAL_NOT_BOUND',p.check_plan(base)['blockers'])
 def test_global_limit_and_unsettled_types(self):
  for unsettled in (True,False,-1,1,None,'0'):
   plan=complete_contract();plan['unsettled_costs']=unsettled
   self.assertIn('UNSETTLED_OR_UNKNOWN_COSTS',p.check_plan(approve(plan))['blockers'])
  plan=complete_contract();plan['global_money_cap']=.5
  self.assertIn('EPISODE_CAP_EXCEEDS_GLOBAL_CAP',p.check_plan(approve(plan))['blockers'])
 def test_shared_attempt_never_independent_denominator(self):
  rows=[dict(episode_id=k,status='failure',attempt_ids=['same-effect'],cost_complete=True) for k in ('a','b')]
  self.assertIn('ATTEMPT_ID_REUSED',p.outcome_errors(['a','b'],rows))
 def test_actual_import_bypasses_stale_pyc(self):
  with tempfile.TemporaryDirectory() as temp:
   target=Path(temp);shutil.copyfile(ROOT/'fixture_load_probe.py',target/'fixture_load_probe.py');(target/'fixtures').mkdir()
   source=target/'fixtures/h0.py';real=(ROOT/'fixtures/h0.py').read_bytes();stale=real.replace(b'+ 1',b'+ 9');self.assertNotEqual(real,stale);self.assertEqual(len(real),len(stale))
   source.write_bytes(stale);mtime=int(source.stat().st_mtime);os.utime(source,(mtime,mtime));py_compile.compile(str(source),doraise=True)
   source.write_bytes(real);os.utime(source,(mtime,mtime))
   proc=subprocess.run([sys.executable,'-I','-S',str(target/'fixture_load_probe.py'),'h0','independent-fixed-nonce'],capture_output=True,text=True,timeout=5)
   self.assertEqual(proc.returncode,0,proc.stderr);r=json.loads(proc.stdout)
   self.assertEqual(r['fixture_output']['value'],4);self.assertEqual(r['harness_source_hash'],hashlib.sha256(real).hexdigest());self.assertEqual(r['nonce'],'independent-fixed-nonce')
 def test_actual_import_and_call_fail_without_receipt(self):
  for name in ('broken','call_failed'):
   proc=subprocess.run([sys.executable,'-I','-S',str(ROOT/'fixture_load_probe.py'),name,'nonce'],capture_output=True,text=True,timeout=5)
   self.assertNotEqual(proc.returncode,0);self.assertEqual(proc.stdout.strip(),'')
 def test_bundled_probe_cannot_request_arbitrary_module(self):
  proc=subprocess.run([sys.executable,'-I','-S',str(ROOT/'fixture_load_probe.py'),'../preflight','nonce'],capture_output=True,text=True,timeout=5)
  self.assertNotEqual(proc.returncode,0);self.assertEqual(proc.stdout.strip(),'')
if __name__=='__main__':unittest.main(verbosity=2)
