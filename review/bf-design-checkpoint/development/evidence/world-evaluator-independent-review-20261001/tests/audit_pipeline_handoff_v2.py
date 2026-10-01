"""Independent non-solving checks for additive v2 handoff."""
import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path('/workspace/shared/world-evaluator-independent-review-20261001/snapshots/world/pipeline-handoff-v2')
sys.path.insert(0,str(ROOT));import prepare_request as p
class Audit(unittest.TestCase):
 def setUp(self):
  self.tools={k:'a'*64 for k in p.REQUIRED_TOOL_HASHES};self.tools.update(python='synthetic',libraries={'synthetic':'v1'})
  self.model={'model_version':'synthetic','world_provider':'native-LTC3588-1-encrypted-macro','applicability':'synthetic-test-only','physical_qualified':False,'source_hashes':{'fixture':'a'*64}}
 def request(self):return p.prepare_request({},self.model,self.tools)
 def test_all_required_tool_pins_and_versions(self):
  for key in p.REQUIRED_TOOL_HASHES:
   t=copy.deepcopy(self.tools);t.pop(key)
   with self.assertRaises(p.aw.ContractError,msg=key):p.prepare_request({},self.model,t)
   t=copy.deepcopy(self.tools);t[key]=True
   with self.assertRaises(p.aw.ContractError,msg=key):p.prepare_request({},self.model,t)
  t=copy.deepcopy(self.tools);t['libraries']={}
  with self.assertRaises(p.aw.ContractError):p.prepare_request({},self.model,t)
 def test_mutating_prepared_request_cannot_preserve_old_identity(self):
  for rehash in (False,True):
   r=self.request();r['candidate']['circuit']['cin_uF']=10
   if rehash:r['request_id']=p.aw.digest({k:v for k,v in r.items() if k!='request_id'})
   with self.assertRaises(p.aw.ContractError):p.verify_runtime(r,self.tools,r['installed_implementation'])
   with self.assertRaises(p.aw.ContractError):p.pipeline_kwargs(r,'/tmp/noncreated-audit-run','/tmp/noncreated-audit-cache')
 def test_other_mutable_authority_fields_are_reconstructed(self):
  for key,value in [('callable','untrusted.function'),('prepared_only',False),('execution_authorized_by_this_request',True),('cache_namespace','x'*64),('formal_trial_admitted',True)]:
   r=self.request();r[key]=value;r['request_id']=p.aw.digest({k:v for k,v in r.items() if k!='request_id'})
   with self.assertRaises(p.aw.ContractError,msg=key):p.validate_request(r)
 def test_prepare_and_kwargs_create_no_files(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);r=self.request();kw=p.pipeline_kwargs(r,root/'run',root/'cache')
   self.assertEqual(list(root.iterdir()),[]);self.assertFalse(r['execution_authorized_by_this_request'])
   self.assertTrue(p.verify_runtime(r,self.tools,r['installed_implementation']))
   self.assertEqual(kw['candidate'],r['candidate']);self.assertIsNot(kw['candidate'],r['candidate'])
 def test_transitive_manifest_covers_known_external_inputs(self):
  pins=p.transitive_sources(p.DEFAULT_PIPELINE_ROOT)
  required={'scripts/door_case/build_cad.py','scripts/build_pluck_product.py','configs/reference_cases/door-magnetic-v1/DoorBeam.java','configs/reference_cases/door-magnetic-v1/DoorMagnetic.java','configs/reference_cases/door-magnetic-v1/design.json','packages/python/bfworld/src/bfworld/agentlab/engineering_templates/product_cad.py','scripts/pluck_receiver.py','packages/python/bfworld/src/bfworld/agentlab/runtime_config.py'}
  self.assertEqual(set(pins),required)
  repo=p.DEFAULT_PIPELINE_ROOT.parents[6]
  for name,pin in pins.items():self.assertEqual(hashlib.sha256((repo/name).read_bytes()).hexdigest(),pin['sha256'])
 def test_runtime_collection_requires_actual_cad_and_material_bytes(self):
  class Native:CAD='/synthetic/cad/python'
  class Pipeline:
   native=Native()
   @staticmethod
   def tool_identity():return {'existing':'synthetic'}
  calls=[]
  def read_hash(path):calls.append(str(path));return 'a'*64
  with patch.object(p.aw,'file_hash',side_effect=read_hash):r=p.collect_runtime_identity(Pipeline())
  self.assertEqual(calls,['/synthetic/cad/python','/Applications/COMSOL62/Multiphysics/data/comsol_piezo_lib.mph'])
  self.assertEqual(r['cad_python'],'a'*64);self.assertEqual(r['comsol_piezo_library'],'a'*64)
  with patch.object(p.aw,'file_hash',side_effect=FileNotFoundError):
   with self.assertRaises(FileNotFoundError):p.collect_runtime_identity(Pipeline())
if __name__=='__main__':unittest.main(verbosity=2)
