import copy, importlib.util, pathlib, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import prepare_request as p
class Handoff(unittest.TestCase):
 def setUp(self):
  self.model={'model_version':'door-closed-simulation-v1-unqualified-native-provider','world_provider':'native-LTC3588-1-encrypted-macro','applicability':'source_declared_not_physical_qualified','physical_qualified':False,'source_hashes':{'model_fixture':'test-only-not-native-evidence'}}
  self.tools={**{k:'0'*64 for k in p.REQUIRED_TOOL_HASHES},'fixture':'TEST-ONLY-nonexecuting-adapter-test','python':'test-only','libraries':{'test':'fixture'}}
 def request(self,candidate=None):return p.prepare_request(candidate or {},self.model,self.tools)
 def test_existing_validator_accepts_emitted_spec(self):
  r=self.request();self.assertEqual(r['candidate'],p.aw.migrate_upstream_spec(r['candidate'],'upstream-338d603'))
 def test_kwargs_match_real_callable_signature_without_importing_native(self):
  import ast
  tree=ast.parse((p.DEFAULT_PIPELINE_ROOT/'pipeline.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='submit_candidate')
  names={a.arg for a in node.args.args+node.args.kwonlyargs}
  with tempfile.TemporaryDirectory() as t:
   k=p.pipeline_kwargs(self.request(),pathlib.Path(t)/'new-run',pathlib.Path(t)/'cache');self.assertTrue(set(k)<=names);self.assertTrue(k['confirm'])
 def test_camera_noop_scientific_namespace(self):
  self.assertEqual(self.request()['cache_namespace'],self.request({'presentation':{'camera_deg':99}})['cache_namespace'])
 def test_capacitance_invalidates_namespace(self):
  self.assertNotEqual(self.request()['cache_namespace'],self.request({'circuit':{'cin_uF':10}})['cache_namespace'])
 def test_provider_substitution_rejected(self):
  self.model['world_provider']='generic-event-fixture'
  with self.assertRaises(p.aw.ContractError):self.request()
 def test_continuation_not_smuggled_from_legacy(self):
  with self.assertRaises(p.aw.ContractError):p.prepare_request({},self.model,self.tools,task_name='DEV-COUPLING-01')
 def test_runtime_identity_recheck(self):
  r=self.request();self.assertTrue(p.verify_runtime(r,self.tools,r['installed_implementation']))
  with self.assertRaises(p.aw.ContractError):p.verify_runtime(r,{'changed':True},r['installed_implementation'])
  with self.assertRaises(p.aw.ContractError):p.verify_runtime(r,self.tools,{'changed':True})
 def test_no_outputs_or_native_execution_during_prepare(self):
  r=self.request();self.assertTrue(r['prepared_only']);self.assertFalse(r['execution_authorized_by_this_request'])
  self.assertFalse(r['physical_qualified']);self.assertFalse(r['formal_trial_admitted'])
 def test_existing_or_sealed_output_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(p.aw.ContractError):p.pipeline_kwargs(self.request(),t,pathlib.Path(t)/'cache')
  with self.assertRaises(p.aw.ContractError):p.pipeline_kwargs(self.request(),p.WORLD_ROOT/'new-run',pathlib.Path('/tmp/cache'))


class BindingRegression(unittest.TestCase):
 setUp=Handoff.setUp
 request=Handoff.request
 def test_mutable_candidate_is_rejected_at_both_boundaries(self):
  r=self.request();r['candidate']['circuit']['cin_uF']=10
  with self.assertRaises(p.aw.ContractError):p.verify_runtime(r,self.tools,r['installed_implementation'])
  with self.assertRaises(p.aw.ContractError):p.pipeline_kwargs(r,'/tmp/not-created-run','/tmp/not-created-cache')
 def test_rehashed_but_inconsistent_candidate_is_rejected(self):
  r=self.request();r['candidate']['circuit']['cin_uF']=10
  r['request_id']=p.aw.digest({k:v for k,v in r.items() if k!='request_id'})
  with self.assertRaises(p.aw.ContractError):p.validate_request(r)
 def test_mutated_model_solver_and_identity_are_rejected(self):
  for field in ['model','solver','identity','stage_keys']:
   r=self.request();r[field]['evil']=True
   r['request_id']=p.aw.digest({k:v for k,v in r.items() if k!='request_id'})
   with self.assertRaises(p.aw.ContractError):p.validate_request(r)
 def test_caller_dict_mutation_does_not_mutate_prepared_request(self):
  r=self.request();self.tools['fixture']='mutated';self.model['model_version']='mutated'
  self.assertTrue(p.validate_request(r))
 def test_all_transitive_source_changes_are_rejected(self):
  import shutil
  repo=p.DEFAULT_PIPELINE_ROOT.parents[6]
  with tempfile.TemporaryDirectory() as t:
   dst=pathlib.Path(t)/'repo';chain=dst/p.DEFAULT_PIPELINE_ROOT.relative_to(repo)
   chain.mkdir(parents=True)
   for f in p.DEFAULT_PIPELINE_ROOT.iterdir():
    if f.is_file() and f.suffix in ('.py','.c'):shutil.copyfile(f,chain/f.name)
   lock=p.aw.read_json(ROOT/'TRANSITIVE-SOURCES.json')['files']
   for rel in lock:
    (dst/rel).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/rel,dst/rel)
   request=p.prepare_request({},self.model,self.tools,chain)
   self.assertTrue(p.validate_request(request))
   for rel in lock:
    path=dst/rel;old=path.read_bytes();path.write_bytes(old+b'\nchanged')
    with self.assertRaises(p.aw.ContractError):p.validate_request(request)
    with self.assertRaises(p.aw.ContractError):p.prepare_request({},self.model,self.tools,chain)
    path.write_bytes(old)

if __name__=='__main__':unittest.main()
