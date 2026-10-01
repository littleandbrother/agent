"""Independent real Python producer/cache/deck dataflow; native tools never run."""
import os
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import sys,json,hashlib,copy,importlib.util,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REPO=Path('/workspace/shared/current-cache-integration-20261001/working/battery-world')
ROOT=HERE/'cache-execution-v2';ROOT.mkdir(exist_ok=False)
os.environ['BF_HOME']=str(ROOT/'bf-home')
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
import numpy as np
from bfworld.agentlab.simulation_chain import cache,native,solver,contracts
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
CHECKS=[]
def record(name,**kw):CHECKS.append({'check':name,'passed':True,**kw})
class StopBeforeNative(Exception):pass
class Checks(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.case_root=ROOT/'acceptance-fixture';cls.case_root.mkdir()
  cls.base=cls.case_root/'cache';legacy=cls.base/'beam'/'legacy-v1';legacy.mkdir(parents=True)
  (legacy/'checkpoint.json').write_text('{"historical":"must remain byte exact"}\n');(legacy/'rom.json').write_text('{"k":123}\n')
  cls.old={str(p.relative_to(cls.base)):sha(p) for p in cls.base.rglob('*') if p.is_file()}
  cls.c=cache.Cache(cls.base);cls.calls=[]
  def beam_producer(p):
   cls.calls.append('beam')
   # This exercises unchanged native.beam parsing against a clearly synthetic log, not COMSOL.
   log='BF_DATA,tip3,0.0034403062781818306\nBF_DATA,tip4,0.00345\nBF_DATA,eigen,15.9152427488183\nBF_DATA,actuation,-2.4862056721220446e-6,1.7773565412243214e-8\n'
   (p/'synthetic-beam-input.log').write_text(log)
   with patch.object(native,'comsol',return_value=log):return native.beam(p)
  cls.bp,cls.rom,cls.bkey,_=cls.c.stage('beam',{'test_scope':'synthetic-log-real-beam-parser'},beam_producer)
  cls.fp,cls.force,cls.fkey,_=cls.c.stage('force',{'mechanical':contracts.DEFAULT['mechanical'],'implementation':sha(native.__file__)},lambda p:(cls.calls.append('force'),native.force_table(p,contracts.DEFAULT['mechanical']))[1])
  cls.wp,_,cls.wkey,_=cls.c.stage('firmware',{'scope':'path-only-fixture'},lambda p:((p/'NO_NATIVE_EXECUTION.txt').write_text('No compiler or MCU execution in this cache fixture.'),{'scope':'path-only-fixture'})[1])
  cls.fake_pmic=ROOT/'NON_EXECUTABLE_PMIC_PLACEHOLDER.sub';cls.fake_pmic.write_text('* inert test placeholder; NOT vendor model; never simulated\n')
 def test_01_real_force_cache_to_real_deck(self):
  cp,v,key,hit=self.c.stage('force',{'mechanical':contracts.DEFAULT['mechanical'],'implementation':sha(native.__file__)},lambda p:self.fail('cache hit invoked producer'))
  self.assertTrue(hit);self.assertEqual(key,self.fkey);self.assertEqual(v,self.force)
  decks=[]
  for tag,rom,fp in [('fresh',self.rom,self.fp),('cached',json.loads((self.bp/cache.VALUE_FILE).read_text()),cp)]:
   out=ROOT/('deck-'+tag);out.mkdir()
   with patch.object(solver,'PMIC',self.fake_pmic):q0,damping=solver.deck(out,contracts.DEFAULT,rom,fp/'force-table.npz',np.array([0.,.1]),np.array([0.,0.]))
   decks.append((out/'system.cir').read_bytes())
  self.assertEqual(decks[0],decks[1]);self.assertIn(b'.func magnetic',decks[0]);self.assertIn(str(self.rom['k']).encode(),decks[0])
  record('real_force_producer_cache_real_deck_byte_identity',force_sha256=sha(self.fp/'force-table.npz'),deck_sha256=sha(ROOT/'deck-fresh/system.cir'),beam_scope='real parser of synthetic log',vendor_solver_calls=0)
 def test_02_manifest_value_edit_rejected(self):
  p=self.bp/'checkpoint.json';original=p.read_bytes();m=json.loads(original);m['value']['k']*=1.2;p.write_text(json.dumps(m))
  try:
   with self.assertRaises(contracts.ChainError):self.c.stage('beam',{'test_scope':'synthetic-log-real-beam-parser'},lambda p:None)
  finally:p.write_bytes(original)
  record('manifest_value_only_tamper_rejected')
 def test_03_canonical_value_and_raw_artifact_tamper_rejected(self):
  for p in [self.bp/cache.VALUE_FILE,self.fp/'force-table.npz']:
   original=p.read_bytes();p.write_bytes(original+b'X')
   try:
    stage='beam' if p.parent==self.bp else 'force';inputs={'test_scope':'synthetic-log-real-beam-parser'} if stage=='beam' else {'mechanical':contracts.DEFAULT['mechanical'],'implementation':sha(native.__file__)}
    with self.assertRaises(contracts.ChainError):self.c.stage(stage,inputs,lambda p:None)
   finally:p.write_bytes(original)
  record('canonical_value_and_force_bytes_tamper_rejected')
 def test_04_old_namespace_unchanged(self):
  observed={str(p.relative_to(self.base)):sha(p) for p in self.base.rglob('*') if p.is_file() and cache.CACHE_NAMESPACE not in p.parts}
  self.assertEqual(self.old,observed);self.assertEqual(self.c.root,self.base/cache.CACHE_NAMESPACE)
  record('old_namespace_full_directory_preserved',files=observed)
 def test_05_resumed_value_is_authoritative_in_deck(self):
  _,rom,key,hit=self.c.stage('beam',{'test_scope':'synthetic-log-real-beam-parser'},lambda p:self.fail('unexpected producer'))
  self.assertTrue(hit);self.assertEqual(rom,json.loads((self.bp/'rom.json').read_text()))
  p=ROOT/'deck-altered-input';p.mkdir();alt=dict(rom);alt['theta']*=1.2
  with patch.object(solver,'PMIC',self.fake_pmic):solver.deck(p,contracts.DEFAULT,alt,self.fp/'force-table.npz',np.array([0.,.1]),np.array([0.,0.]))
  self.assertNotEqual((p/'system.cir').read_bytes(),(ROOT/'deck-fresh/system.cir').read_bytes())
  record('returned_rom_reaches_generated_deck_no_dormant_read')
 def test_06_acceptance_uses_versioned_cache_runtime_paths(self):
  script=REPO/'scripts/run_closed_simulation.py';spec=importlib.util.spec_from_file_location('audit_acceptance_runner',script);runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
  paths=[]
  def fake_submit(candidate,output,cache_root,**kw):
   output.mkdir(parents=True,exist_ok=True)
   r={'run_status':'completed','physics_hash':'fixture','metrics':{'cold_start_reached':False,'peak_storage_V':.1,'tx_completed':0},'stages':{n:{'key':k,'cache_hit':True} for n,k in [('cad','fixture-cad'),('beam',self.bkey),('force',self.fkey),('firmware',self.wkey),('joint','fixture-joint')]},'energy_ledger':{'pmic_port_energy_J':0},'design_status':'insufficient_evidence','predicted_design_status':None,'product_verified':False}
   (output/'result.json').write_text(json.dumps(r));return r
  def block_native(out,spec,rom,force_path,fw,resistor=None):
   self.assertEqual(Path(force_path),self.fp/'force-table.npz');self.assertEqual(Path(fw),self.wp);self.assertEqual(rom,self.rom);paths.append(str(force_path));raise StopBeforeNative('Acceptance reached the migrated passive path; native solve intentionally blocked')
  with patch.object(runner,'submit_candidate',side_effect=fake_submit),patch.object(runner.solver,'solve',side_effect=block_native):
   with self.assertRaises(StopBeforeNative):runner.acceptance(self.case_root)
  self.assertEqual(len(paths),1);record('acceptance_runtime_uses_cache_root',force_path=paths[0],scope='mock candidate records to exercise path plumbing only; stopped before native solve')

if __name__=='__main__':
 started=time.monotonic();suite=unittest.defaultTestLoader.loadTestsFromTestCase(Checks);r=unittest.TextTestRunner(verbosity=2).run(suite)
 result={'status':'passed' if r.wasSuccessful() else 'failed','tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'checks':CHECKS,'vendor_solver_calls':0,'ARM_compiler_calls':0,'model_API_calls':0,'source_files':{str(Path(m.__file__)):sha(m.__file__) for m in (cache,native,solver,contracts)},'scope':'Trusted-operator corruption/dataflow/path audit; not adversarial isolation or native-physics validation','python':sys.version,'numpy':np.__version__,'wall_s':time.monotonic()-started}
 (HERE/'cache-integration-independent-audit.json').write_text(json.dumps(result,indent=2)+'\n');sys.exit(not r.wasSuccessful())
