import copy,hashlib,importlib.util,json
from pathlib import Path
import unittest,tempfile,contextlib
from bfworld.agentlab import literature_native as candidate
def data(tmp_path):
 owner='pi-chat-test-unchanged';work=tmp_path/owner;work.mkdir()
 phase={'schema_version':'bf-paper-recovery-phase-v1','paper_id':'P04','owner':owner,'phase':'engineering-review','stage_scope':'real-S132-target','required_project_kind':'firmware-nrf52832-s132','source_identity':'1'*64,'task_file':'campaign/recovery/P04/phases/engineering-review.json','task_sha256':'2'*64,'task':'Exact current authorized goal remains verbatim in human input.'}
 generic={'owner':owner,'schema_version':'bf-product-context-v1','revision':2,'hashes':{'physical_hash':'3'*64},'requirements':['1000 Hz','BLE + native nRF52832'],'assumptions':['Pins reconstructed'],'interfaces':['PCB BLOCKED no operator-bound EDA project'],'delivery':{'passed':False,'missing':['firmware','PCB','old-unused-registry']},'messages':[{'text':'Original user instruction must remain intact.'}]}
 binding={'owner':owner,'paper_id':'P04','project_uuid':'runtime-id','created_project_uuid':'creation-id','local_project':'/local/P04.eprj3','native_window_id':'native-window','runtime_alias_proof':'campaign/eda/P04/proof.json','native_design_accepted':False,'host_policy':{'host':'desktop','modes':['half-offline']}}
 jobs=[{'id':f'eng-{i}','status':'SUCCEEDED','operation':f'op-{i}','project_sha256':'4'*64,'result':{'kind':'firmware-nrf52832','readback_passed':True,'raw':'z'*200000}} for i in range(20)]
 return work,phase,binding,generic,jobs

def test_current_binding_not_stale_generic_block(data):
 w,p,b,g,j=data;r=candidate.native_phase_context_packet(w,p,b,g,j)
 assert r['local_eda']['bound'] and r['local_eda']['local_project']=='/local/P04.eprj3'
 assert 'no operator-bound EDA' not in json.dumps(r)
 assert r['native_phase']['required_project_kind']=='firmware-nrf52832-s132'
 assert r['requirements']==g['requirements'] and r['assumptions']==g['assumptions']

def test_legacy_snapshot_and_user_text_retained(data):
 w,p,b,g,j=data;r=candidate.native_phase_context_packet(w,p,b,g,j);a=r['generic_product_registry_history']['artifact'];f=w/a['path']
 assert f.read_bytes()==candidate.canonical(g).encode()
 assert hashlib.sha256(f.read_bytes()).hexdigest()==a['sha256']
 assert json.loads(f.read_text())['messages']==g['messages']
 assert p['task']=='Exact current authorized goal remains verbatim in human input.'

def test_large_job_results_archived_not_injected(data):
 w,p,b,g,j=data;r=candidate.native_phase_context_packet(w,p,b,g,j)
 assert len(candidate.canonical(r).encode())<15000 and len(r['native_jobs'])==12 and r['native_jobs_count']==20
 assert json.loads((w/r['native_jobs_reference']['path']).read_text())==j

def test_successful_job_never_grants_product_or_phase_acceptance(data):
 w,p,b,g,j=data;r=candidate.native_phase_context_packet(w,p,b,g,j)
 assert not r['delivery']['passed'] and not r['full_product_passed'] and not r['physical_verified']
 assert all(not x['selection_and_function_accepted'] for x in r['native_jobs'])
 assert not r['local_eda']['native_design_accepted']

def test_foreign_owner_and_binding_rejected(data):
 w,p,b,g,j=data
 with unittest.TestCase().assertRaises(ValueError):candidate.native_phase_context_packet(w,p,b,{**g,'owner':'foreign'},j)
 with unittest.TestCase().assertRaises(ValueError):candidate.native_phase_context_packet(w,p,{**b,'paper_id':'P09'},g,j)
 with unittest.TestCase().assertRaises(ValueError):candidate.native_phase_context_packet(w,p,{**b,'owner':'foreign'},g,j)

def test_symlink_archive_rejected_without_external_write(data,tmp_path):
 w,p,b,g,j=data;foreign=tmp_path/'outside';foreign.mkdir();(w/'public-context-history').symlink_to(foreign,target_is_directory=True)
 with unittest.TestCase().assertRaises(ValueError):candidate.native_phase_context_packet(w,p,b,g,j)
 assert list(foreign.iterdir())==[]

def test_original_owner_route_only():
 assert candidate.native_context_target({'role':'participant','owner':'o'},'o','o')=='o'
 assert candidate.native_context_target({'role':'operator'},'o','o')=='o'
 with unittest.TestCase().assertRaises(PermissionError):candidate.native_context_target({'role':'participant','owner':'foreign'},'o','o')
 with unittest.TestCase().assertRaises(PermissionError):candidate.native_context_target({'role':'operator'},'foreign','o')

def test_original_native_observation_pointer_survives_context(data):
 w,p,b,g,j=data
 obs={'owner':p['owner'],'project':b['project_uuid'],'latest_by_action':{'sch.read':{'id':'eda-current','status':'FAILED','receipt_status':'HASH_BOUND','receipt':{'path':'eda-receipts/eda-current.json','sha256':'5'*64}}},'full_product_passed':False}
 r=candidate.native_phase_context_packet(w,p,b,g,j,eda_observations=obs)
 assert r['local_eda']['observations']==obs
 assert not r['full_product_passed'] and not r['local_eda']['native_design_accepted']
 for change in [{'owner':'foreign'},{'project':'foreign'}]:
  with unittest.TestCase().assertRaisesRegex(ValueError,'OBSERVATION_SCOPE'):
   candidate.native_phase_context_packet(w,p,b,g,j,eda_observations={**obs,**change})

class NativePhaseContextTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)
 def run_case(self,name):
  args=globals()[name].__code__.co_varnames[:globals()[name].__code__.co_argcount]
  globals()[name](*[data(self.path) if a=="data" else self.path for a in args])
 def test_participant_foreign_query_rejected(self):
  with self.assertRaises(PermissionError):candidate.native_context_target({"role":"participant","owner":"original"},"foreign","original")
for name in list(globals()):
 if name.startswith("test_"):setattr(NativePhaseContextTests,name,lambda self,n=name:self.run_case(n))
if __name__=="__main__":unittest.main()
