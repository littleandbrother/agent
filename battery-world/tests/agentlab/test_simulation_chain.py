import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from bfworld.agentlab.simulation_chain.contracts import ChainError,DEFAULT,digest,physical_spec,validate
from bfworld.agentlab.simulation_chain.cache import Cache

class ContractsAndRecovery(unittest.TestCase):
    def test_reject_nonphysical_unknown_and_boolean_values(self):
        for s in [{'mechanical':{'gap_mm':float('nan')}},{'circuit':{'cin_uF':-1}},
                  {'mechanical':{'gap_mm':True}},{'firmware':{'interval_ms':20,'tx_ms':20}},
                  {'schema_version':'future'},{'override_verdict':True}]:
            with self.subTest(s=s),self.assertRaises(ChainError):validate(s)

    def test_camera_identity_and_no_input_mutation(self):
        original=json.dumps(DEFAULT,sort_keys=True)
        a=validate({});b=validate({'presentation':{'camera_deg':-35}})
        self.assertEqual(digest(physical_spec(a)),digest(physical_spec(b)))
        self.assertNotEqual(digest(a),digest(b));self.assertEqual(original,json.dumps(DEFAULT,sort_keys=True))

    def test_partial_stage_is_not_a_hit_then_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Cache(tmp);called=[]
            def bad(p):
                (p/'model').write_text('incomplete');raise RuntimeError('interrupted')
            with self.assertRaises(RuntimeError):c.stage('native',{'input':1},bad)
            def good(p):called.append(1);(p/'model').write_text('complete');return {'solved':True}
            p,_,key,hit=c.stage('native',{'input':1},good);self.assertFalse(hit)
            self.assertTrue(c.stage('native',{'input':1},good)[3]);self.assertEqual([1],called)
            self.assertTrue(list(c.root.glob('native/*.partial-*/failure.json')))
            self.assertNotEqual(key,c.stage('native',{'input':2},good)[2])

    def test_cached_native_bytes_cannot_be_silently_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Cache(tmp)
            def f(p):(p/'model').write_text('original');return {}
            p,*_=c.stage('beam',{},f);(p/'model').write_text('tampered')
            with self.assertRaisesRegex(ChainError,'hash mismatch'):c.stage('beam',{},f)

    def test_fresh_and_cached_results_have_identical_json_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Cache(tmp)
            def f(p):(p/'data').write_text('native');return {'coordinate':(1.,2.)}
            fresh=c.stage('native',{},f)[1];cached=c.stage('native',{},f)[1]
            self.assertEqual(fresh,cached)
            self.assertIsInstance(fresh['coordinate'],list)

    def test_agent_adapter_uses_same_contract(self):
        from bfworld.agentlab.engineering import validate as engine_validate
        result=engine_validate('closed-simulation',{'candidate':{'circuit':{'cin_uF':22}}})
        self.assertEqual(22,result['candidate']['circuit']['cin_uF']);self.assertTrue(result['confirmation'])
        with self.assertRaises(ValueError):engine_validate('closed-simulation',{'confirmation':'yes'})

class EngineeringIntegration(unittest.TestCase):
    def test_structured_design_failure_reaches_product_and_trace_without_acceptance(self):
        from bfworld.agentlab.server import Workbench
        from bfworld.agentlab.simulation_chain.contracts import write_json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'paid-window-closed.json').write_text('{}')
            app=Workbench(root/'state')
            try:
                owner=app.conversations.create('simulation integration fixture',None,'simulation-fixture')['id']
                def fake(engine,job,directory,deadline):
                    result={'run_status':'completed','design_status':'insufficient_evidence',
                      'predicted_design_status':'unsatisfied','product_verified':False,
                      'metrics':{'peak_storage_V':.1,'tx_completed':0,'received_events':0},
                      'checks':{'magnetic_mesh':False},'stages':{'joint':{'key':'a'*64,'cache_hit':False,'status':'completed'}},
                      'summary_zh':'接口测试数据，非原生证据','energy_ledger':{},'applicability':{}}
                    write_json(directory/'result.json',result)
                    engine.event(owner,job['id'],'simulation_stage_completed',{'stage':'joint','key':'a'*64})
                    return {**result,'_job_status':'SUCCEEDED'}
                with patch('bfworld.agentlab.simulation_chain.run',side_effect=fake):
                    job=app.engineering.submit(owner,{'engine':'closed-simulation','parameters':{'candidate':{}},'operation_id':'simulation-fixture'},'operator')
                    end=time.time()+5
                    while time.time()<end:
                        job=app.engineering.get(owner,job['id'])
                        if job['status'] not in ('RUNNING','QUEUED'):break
                        time.sleep(.02)
                self.assertEqual('SUCCEEDED',job['status'])
                r=next(x for x in app.results.inspect(owner)['results'] if x['id']==job['id'])
                self.assertEqual('insufficient_evidence',r['design_status'])
                self.assertEqual('unsatisfied',r['predicted_design_status'])
                self.assertFalse(r['hardware_verified']);self.assertFalse(r['readback_passed'])
                self.assertEqual('unbound',r['applicability']['state'])
                self.assertTrue(all(f['integrity'] for f in r['files']))
                with app.store.connect() as db:
                    self.assertEqual(1,db.execute("SELECT count(*) FROM engineering_events WHERE job_id=? AND kind='simulation_stage_completed'",(job['id'],)).fetchone()[0])
                    self.assertEqual(0,db.execute('SELECT count(*) FROM model_requests').fetchone()[0])
            finally:app.stop.set();app.thread.join(3);app.lock.close()

@unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('scipy'),'numerical tests run in isolated CAD Python')
class SoftwareInLoop(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from bfworld.agentlab.simulation_chain import native
        self.np=np;self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        native.firmware(self.path,DEFAULT['firmware'])

    def tearDown(self):self.tmp.cleanup()

    def test_no_supply_and_pgood_does_not_cut_load(self):
        from bfworld.agentlab.simulation_chain.solver import execute_program
        t=self.np.linspace(0,.2,2001);z=self.np.zeros(len(t))
        current,states,events=execute_program(self.path,t,z,z)
        self.assertEqual([],events);self.assertTrue((current>0).all());self.assertEqual({0},set(states))
        current,states,events=execute_program(self.path,t,z+3.3,z)
        self.assertEqual([],events);self.assertIn(1,states);self.assertIn(2,states)

    def test_brownout_inside_tx_cannot_create_packet(self):
        from bfworld.agentlab.simulation_chain.solver import execute_program
        t=self.np.linspace(0,.15,1501);v=self.np.full(len(t),3.3)
        _,states,events=execute_program(self.path,t,v,v)
        self.assertGreater(len(events),0)
        first_tx=self.np.flatnonzero(states==4)[0];v[first_tx+2:]=0
        _,states,events=execute_program(self.path,t,v,v)
        self.assertEqual([],events);self.assertEqual(0,states[-1])

    def test_virtual_receiver_loss_and_duplicate_behavior(self):
        from bfworld.agentlab.simulation_chain.solver import execute_program,receive
        t=self.np.linspace(0,.4,4001);v=self.np.full(len(t),3.3)
        _,_,events=execute_program(self.path,t,v,v)
        a=receive(self.path,events,DEFAULT['link']);self.assertGreater(len(a['events']),0)
        b=receive(self.path,events,{**DEFAULT['link'],'loss_probability':1});self.assertEqual([],b['events'])
        c=receive(self.path,events+events,DEFAULT['link']);self.assertEqual(a['events'],c['events'])

    def test_force_symmetry_and_quadrature(self):
        from bfworld.agentlab.simulation_chain.native import force
        a=force(.048,.02,n=8);b=force(.048,-.02,n=8)
        self.assertAlmostEqual(a[0],b[0],places=10);self.assertAlmostEqual(a[2],-b[2],places=10)
        self.assertLess(self.np.linalg.norm(a-force(.048,.02,n=12))/self.np.linalg.norm(a),.005)



# Cache v2 integration regressions: portable consistency, not native acceptance.
import hashlib
from bfworld.agentlab.simulation_chain.contracts import write_json
from bfworld.agentlab.simulation_chain import cache as module

class CacheConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = Cache(self.root)
        self.calls = 0
        self.rom = {'k': 100., 'mass': .01, 'theta': .002, 'cp': 1e-8}

    def tearDown(self):
        self.tmp.cleanup()

    def producer(self, p):
        self.calls += 1
        write_json(p / 'rom.json', self.rom)
        return self.rom

    def make(self):
        return self.cache.stage('beam', {'source': 'fixed'}, self.producer)

    def edit_manifest(self, p, fn):
        m = json.loads((p / 'checkpoint.json').read_text())
        fn(m)
        write_json(p / 'checkpoint.json', m)

    def test_unchanged_hit_uses_hash_listed_canonical_value(self):
        p, a, k, hit = self.make()
        self.assertFalse(hit)
        _, b, kb, hit = self.make()
        self.assertTrue(hit)
        self.assertEqual(self.calls, 1)
        self.assertEqual((a, k), (b, kb))
        m = json.loads((p / 'checkpoint.json').read_text())
        self.assertEqual(m['schema_version'], module.CACHE_SCHEMA)
        self.assertIn(module.VALUE_FILE, [x['path'] for x in m['files']])
        self.assertEqual(b, json.loads((p / module.VALUE_FILE).read_text()))

    def test_metadata_only_corruption_is_rejected(self):
        p, *_ = self.make()
        self.edit_manifest(p, lambda m: m['value'].update(k=200.))
        with self.assertRaisesRegex(ChainError, 'metadata/value mismatch'):
            self.make()

    def test_value_artifact_corruption_is_rejected(self):
        p, *_ = self.make()
        write_json(p / module.VALUE_FILE, {**self.rom, 'k': 200.})
        with self.assertRaisesRegex(ChainError, 'hash mismatch'):
            self.make()

    def test_missing_value_artifact_is_rejected(self):
        p, *_ = self.make()
        (p / module.VALUE_FILE).unlink()
        with self.assertRaisesRegex(ChainError, 'hash mismatch'):
            self.make()

    def test_unlisted_value_is_rejected(self):
        p, *_ = self.make()
        self.edit_manifest(p, lambda m: m.update(files=[f for f in m['files'] if f['path'] != module.VALUE_FILE]))
        with self.assertRaisesRegex(ChainError, 'canonical value artifact'):
            self.make()

    def test_legacy_schema_in_new_namespace_is_rejected(self):
        p, *_ = self.make()
        self.edit_manifest(p, lambda m: m.update(schema_version='simulation-checkpoint-v1'))
        with self.assertRaisesRegex(ChainError, 'schema/identity'):
            self.make()

    def test_legacy_namespace_is_preserved_not_reused(self):
        oldkey = digest({'stage': 'beam', 'inputs': {'source': 'fixed'}})
        p = self.root / 'beam' / oldkey
        p.mkdir(parents=True)
        self.producer(p)
        write_json(p / 'checkpoint.json', {'schema_version': 'simulation-checkpoint-v1', 'value': self.rom})
        (p / 'retained-failure.txt').write_text('Old evidence must remain unchanged')
        before = {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest()
                  for f in p.rglob('*') if f.is_file()}
        newp, _, newkey, hit = self.make()
        self.assertFalse(hit)
        self.assertNotEqual(oldkey, newkey)
        self.assertNotEqual(p, newp)
        self.assertEqual(before, {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest()
                                  for f in p.rglob('*') if f.is_file()})

    @unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('scipy'), 'numerical deck construction dependencies')
    def test_real_cache_to_deck_consistency_and_rejection(self):
        import numpy as np
        from bfworld.agentlab.simulation_chain import solver
        p, first, _, _ = self.make()
        _, cached, _, hit = self.make()
        self.assertTrue(hit)
        table = self.root / 'table.npz'
        np.savez(table, angles=[0., 1.2], qs=[-.008, .008], values=np.zeros((2, 2)))
        placeholder = self.root / 'placeholder.sub'
        placeholder.write_text('* inert placeholder; no native solver call\n')
        old = solver.PMIC
        solver.PMIC = placeholder
        try:
            texts = []
            for name, rom in [('fresh', first), ('cached', cached)]:
                out = self.root / name
                out.mkdir()
                solver.deck(out, validate({}), rom, table, np.array([0., 4.]), np.zeros(2), resistor=100000)
                texts.append((out / 'system.cir').read_text())
            self.assertEqual(*texts)
            self.assertIn('-100.0*V(q)', texts[0])
            self.edit_manifest(p, lambda m: m['value'].update(k=200.))
            with self.assertRaisesRegex(ChainError, 'metadata/value mismatch'):
                self.make()
        finally:
            solver.PMIC = old

    def test_json_types_and_partial_failure_remain_supported(self):
        def tuple_producer(p):
            (p / 'data').write_text('value')
            return {'coordinate': (1., 2.)}
        a = self.cache.stage('tuple', {}, tuple_producer)[1]
        b = self.cache.stage('tuple', {}, tuple_producer)[1]
        self.assertEqual(a, b)
        self.assertIsInstance(a['coordinate'], list)
        def bad(p):
            (p / 'data').write_text('incomplete')
            raise RuntimeError('interrupted')
        with self.assertRaises(RuntimeError):
            self.cache.stage('partial', {}, bad)
        self.assertTrue(list((self.root / module.CACHE_NAMESPACE / 'partial').glob('*.partial-*/failure.json')))

    def test_acceptance_resolver_uses_versioned_cache_root(self):
        import ast
        p, _, key_value, _ = self.make()
        tree = ast.parse((Path(__file__).resolve().parents[2] / 'scripts/run_closed_simulation.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'acceptance')
        names = {'checkpoint_root', 'beam', 'force', 'fw'}
        nodes = [n for n in function.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
        self.assertEqual(len(nodes), 4)
        scope = {'Cache': Cache, 'cache': self.root, 'baseline': {}, 'key': lambda r, stage: key_value}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'patched-acceptance-resolver', 'exec'), scope)
        self.assertEqual(scope['beam'], p)
        self.assertEqual(scope['checkpoint_root'], self.root / module.CACHE_NAMESPACE)

    def test_reserved_producer_value_filename_is_rejected(self):
        def bad(p):
            (p / module.VALUE_FILE).write_text('{}')
            return {}
        with self.assertRaisesRegex(ChainError, 'reserved'):
            self.cache.stage('reserved', {}, bad)


if __name__=='__main__':unittest.main()
