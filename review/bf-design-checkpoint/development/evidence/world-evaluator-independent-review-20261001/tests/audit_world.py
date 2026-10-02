"""Independent metadata/metamorphic tests. No solver or participant dispatch."""
import copy, hashlib, importlib.util, json, math, sys, unittest
from pathlib import Path
ROOT=Path(sys.argv.pop(1))
s=importlib.util.spec_from_file_location('audited_world',ROOT/'src/authoritative_world.py')
a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
def read(p):return json.loads((ROOT/p).read_text())
def sha(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
class Audit(unittest.TestCase):
 def setUp(self):
  self.w=read('contracts/world-v1.json');self.legacy=read('contracts/legacy-world-v1.json')
  self.tasks=read('contracts/tasks-v2.json')['tasks'];self.t=self.tasks[0]
  self.d={'mechanical':{'gap_m':.048},'circuit':{'cap_f':47e-6},'firmware':{'interval_s':.1},'link':{'loss_probability':0}}
  self.m={'model_version':'fixture','applicability':'synthetic-only','physical_qualified':False,'source_hashes':{'model':'0'*64}}
  self.s={'solver_version':'fixture','settings':{'step_s':1e-4},'tool_hashes':{'solver':'1'*64}}
  self.sources=a.source_identity(read('contracts/source-registry.json'))
 def keys(self,**kwargs):
  args=dict(world=self.w,design=self.d,task=self.t,model=self.m,solver=self.s,sources=self.sources);args.update(kwargs);return a.stage_keys(**args)
 def test_source_snapshot_bytes(self):
  registry=read('contracts/source-registry.json')
  self.assertGreater(len(registry['sources']),0)
  for name,row in registry['sources'].items():
   path=ROOT/row['snapshot_path'];self.assertEqual(path.stat().st_size,row['bytes'],name)
   self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['sha256'],name)
   self.assertEqual(self.w['source_bindings'][name],row['sha256'])
  self.assertEqual(a.verify_sources(root=ROOT,check_originals=True),[])
 def test_world_hash_and_unknowns(self):
  self.assertEqual(a.world_id(self.w),sha(self.w));self.assertNotEqual(a.world_id(self.w),a.world_id(self.legacy))
  self.assertFalse(self.w['qualification']['physical_qualified']);self.assertFalse(self.w['qualification']['formal_trial_admitted'])
  self.assertTrue(self.w['qualification']['computational_spec_frozen'])
  for row in self.w['unresolved_facts']:
   self.assertEqual(row['status'],'unknown');self.assertIsNone(row['value'])
 def test_unknown_mutation_and_fake_qualification_rejected(self):
  for change in ('unknown','physical','formal'):
   w=copy.deepcopy(self.w)
   if change=='unknown':w['unresolved_facts'][0]['value']=0
   else:w['qualification'][{'physical':'physical_qualified','formal':'formal_trial_admitted'}[change]]=True
   with self.assertRaises(a.ContractError):a.validate_world(w)
 def test_presentation_noop(self):
  d=copy.deepcopy(self.d);d['presentation']={'camera':[1,2,3],'color':'blue','label':'renamed'}
  self.assertEqual(self.keys(design=d),self.keys())
 def test_all_scientific_design_fields_invalidate(self):
  for field in ('mechanical','circuit','firmware','link','future_scientific_parameter'):
   d=copy.deepcopy(self.d);d[field]={'changed':True}
   before=self.keys();after=self.keys(design=d)
   self.assertTrue(all(before[k]!=after[k] for k in before),field)
 def test_solver_identity_invalidate_geometry_and_force(self):
  for field in ('settings','tool_hashes','solver_version'):
   s=copy.deepcopy(self.s);s[field]={'changed':True} if field!='solver_version' else 'new'
   before=self.keys();after=self.keys(solver=s)
   self.assertTrue(all(before[k]!=after[k] for k in before),field)
 def test_source_and_model_invalidation(self):
  m=copy.deepcopy(self.m);m['model_version']='new'
  sources=copy.deepcopy(self.sources);sources['new_evaluator_component']={'sha256':'f'*64,'bytes':123,'role':'additional_component'}
  for after in (self.keys(model=m),self.keys(sources=sources)):
   self.assertTrue(all(self.keys()[k]!=after[k] for k in after))
 def test_comparison_source_and_world_and_unit_separation(self):
  r=a.make_run_identity(self.w,self.d,self.t,self.m,self.s,self.sources)
  self.assertTrue(a.validate_comparison([r,r])['comparable'])
  for field in ('world_id','source_id','task_contract_id','model_id','solver_id','input_id','experimental_unit'):
   other=copy.deepcopy(r);other[field]='changed'
   with self.assertRaises(a.ContractError,msg=field):a.validate_comparison([r,other])
  with self.assertRaises(a.ContractError):a.validate_comparison([r,r],formal=True)
 def test_pinned_source_mutation_rejected(self):
  sources=copy.deepcopy(self.sources);sources['upstream_program']['sha256']='f'*64
  with self.assertRaises(a.ContractError):self.keys(sources=sources)
 def test_execution_input_and_initial_state_invalidate(self):
  ordinary=self.keys();zero=self.keys(input_control='no_motion')
  self.assertTrue(all(ordinary[k]!=zero[k] for k in ordinary))
  bound=a.bind_initial_state(self.w,q0_m=.001,stiffness_N_m=100,force_at_q0_N=.1,force_artifact_sha256='c'*64)
  changed=self.keys(initial_state=bound)
  self.assertTrue(all(ordinary[k]!=changed[k] for k in ordinary))
  other=copy.deepcopy(bound);other['mechanical_J']=0
  with self.assertRaises(a.ContractError):self.keys(initial_state=other)
  with self.assertRaises(a.ContractError):self.keys(input_control='weak_motion')
 def test_continuation_state_and_checkpoint_are_bound(self):
  task=copy.deepcopy(self.tasks[1])
  args=(self.w,self.d,task,self.m,self.s,self.sources)
  recipe=a.make_run_identity(*args)
  with self.assertRaises(a.ContractError):a.validate_comparison([recipe,recipe])
  state=a.bind_initial_state(self.w,q0_m=.001,stiffness_N_m=100,force_at_q0_N=.1,force_artifact_sha256='c'*64)
  bound=a.make_run_identity(*args,initial_state=state,checkpoint_sha256='e'*64)
  self.assertTrue(a.validate_comparison([bound,bound])['comparable'])
  other=a.make_run_identity(*args,initial_state=state,checkpoint_sha256='f'*64)
  with self.assertRaises(a.ContractError):a.validate_comparison([bound,other])
  ka=a.stage_keys(*args,initial_state=state,checkpoint_sha256='e'*64);kb=a.stage_keys(*args,initial_state=state,checkpoint_sha256='f'*64)
  self.assertTrue(all(ka[k]!=kb[k] for k in ka))
 def test_frozen_input_and_precharge_rejected(self):
  for group,key,value in [('mechanical','opening_s',1),('mechanical','angle_deg',80),('circuit','initial_vin_V',1),('circuit','diagnostic_input_A',.001)]:
   d=copy.deepcopy(self.d);d[group][key]=value
   with self.assertRaises(a.ContractError):self.keys(design=d)
 def test_task_migration_never_ports_success(self):
  for t in self.tasks:
   self.assertEqual(t['world_id'],a.world_id(self.w));self.assertFalse(t['formal_trials_authorized'])
   self.assertFalse(t['requirements_owner_frozen']);self.assertIsNone(t['reference_witness'])
   self.assertFalse(t['migration']['acceptance_results_reused'])
   if t['starting_state']['type']=='canonical_failure_snapshot_required':
    self.assertIsNone(t['starting_state']['case']);self.assertIsNot(t['qualification']['cross_domain_bottleneck_observed'],True)
 def test_geometry_matches_independent_rotation(self):
  for gap in (.028,.042,.048,.07):
   for time in (0.,.25,1.,2.,4.):
    theta=65*math.pi/180*min(time/2,1);c,s=math.cos(theta),math.sin(theta)
    for world,driver_x,tip_x in ((self.w,.904-gap,.904),(self.legacy,.856,.856+gap)):
     for q in (-.008,0,.008):
      r=a.geometry_at(world,gap,time,q)
      expected=[tip_x-driver_x*c+.045*s,0,driver_x*s+.045*c-.075265-q]
      for x,y in zip(r['force_separation_m'],expected):self.assertAlmostEqual(x,y,places=13)
 def test_geometry_nonfinite_and_support(self):
  for gap,time,q in ((float('nan'),0,0),(.048,float('inf'),0),(.02,0,0),(.048,5,0),(.048,0,.009)):
   with self.assertRaises(a.ContractError):a.geometry_at(self.w,gap,time,q)
if __name__=='__main__':unittest.main(verbosity=2)
