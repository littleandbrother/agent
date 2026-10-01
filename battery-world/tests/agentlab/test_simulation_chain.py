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
            self.assertTrue(list(Path(tmp).glob('native/*.partial-*/failure.json')))
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

if __name__=='__main__':unittest.main()
