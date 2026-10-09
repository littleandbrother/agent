import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from bfworld.agentlab.simulation_tasks import load_task, check_candidate, evaluate, NUMERICAL, PHYSICAL, TASK_ROOT
from bfworld.agentlab.simulation_chain.contracts import validate, write_json


class TaskRules(unittest.TestCase):
    def test_protected_fields_and_confirmation_cannot_be_relaxed(self):
        binding = load_task()
        changes = [('mechanical','damping_ratio',.01), ('mechanical','opening_s',1),
                   ('mechanical','remanence_T',1.4), ('circuit','initial_vin_V',3),
                   ('circuit','diagnostic_input_A',.001), ('firmware','boot_mA',.05),
                   ('link','seed',18), ('link','loss_probability',.2),
                   ('solver','reltol',.001), ('presentation','camera_deg',0)]
        for group, key, value in changes:
            with self.subTest(group=group,key=key), self.assertRaisesRegex(ValueError,'TASK_PROTECTED_FIELD'):
                check_candidate(binding, {'candidate':{group:{key:value}},'confirmation':True})
        with self.assertRaisesRegex(ValueError,'TASK_CONFIRMATION_REQUIRED'):
            check_candidate(binding,{'candidate':{},'confirmation':False})

    def test_real_design_fields_and_standard_values(self):
        binding=load_task()
        s=check_candidate(binding,{'candidate':{'mechanical':{'gap_mm':40},'circuit':{'cin_uF':22,'cout_uF':47},'firmware':{'interval_ms':200}},'confirmation':True})
        self.assertEqual(40,s['mechanical']['gap_mm'])
        for patch_value in ({'circuit':{'cin_uF':23}}, {'firmware':{'interval_ms':123}}):
            with self.assertRaisesRegex(ValueError,'TASK_DESIGN_VALUE'):
                check_candidate(binding,{'candidate':patch_value,'confirmation':True})

    def test_task_hash_tamper_rejected(self):
        b=load_task();b['task']['baseline']['circuit']['initial_vin_V']=3
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):
            check_candidate(b,{'candidate':{},'confirmation':True})

    def test_numerical_prediction_and_physical_ranking_separate(self):
        b=load_task();spec=validate({})
        result={'run_status':'completed','metrics':{'cold_start_reached':True},'checks':dict.fromkeys(NUMERICAL,True)}
        event={'capture_id':'tx0','time_s':2,'payload_hex':b['task']['service']['expected_payload_hex']}
        receiver={'transmitted':[event],'delivered':[event],'events':[{}]}
        e=evaluate(b,spec,result,receiver)
        self.assertEqual('satisfied',e['nominal_task_status']);self.assertFalse(e['design_ranking_eligible'])
        self.assertFalse(e['product_verified']);self.assertFalse(e['exactly_once_semantics_qualified'])
        result['checks'].update(dict.fromkeys(PHYSICAL,True))
        self.assertFalse(evaluate(b,spec,result,receiver)['design_ranking_eligible'])
        result['applicability']={'full_rotated_FEM_coverage':True}
        self.assertTrue(evaluate(b,spec,result,receiver)['design_ranking_eligible'])
        result['run_status']='out_of_domain'
        self.assertEqual('not_evaluable',evaluate(b,spec,result,receiver)['nominal_task_status'])

    def test_late_wrong_or_invented_packet_not_success(self):
        b=load_task();r={'run_status':'completed','metrics':{'cold_start_reached':True},'checks':dict.fromkeys(NUMERICAL,True)}
        event={'capture_id':'tx0','time_s':2,'payload_hex':b['task']['service']['expected_payload_hex']}
        for e in ({**event,'time_s':4.1}, {**event,'payload_hex':'00'}, {**event,'capture_id':'invented'}):
            evaluation=evaluate(b,validate({}),r,{'transmitted':[event],'delivered':[e]})
            self.assertEqual('unsatisfied',evaluation['nominal_task_status'])
        s=validate({'circuit':{'diagnostic_input_A':.001}})
        self.assertEqual('not_evaluable',evaluate(b,s,r,{'transmitted':[event],'delivered':[event]})['nominal_task_status'])


class TaskService(unittest.TestCase):
    def test_real_pi_reference_only_folder_starts_without_engineering_permission(self):
        import threading
        from http.server import ThreadingHTTPServer
        from bfworld.agentlab.server import Workbench, handler
        from bfworld.agentlab.provider import MODEL
        with tempfile.TemporaryDirectory() as tmp:
            app=Workbench(Path(tmp)/'state')
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(app))
            app.conversations.port=server.server_port
            threading.Thread(target=server.serve_forever,daemon=True).start()
            requests=[]
            def fake_model(owner,payload,on_chunk=None):
                requests.append(payload)
                names=[t['function']['name'] for t in payload['tools']]
                self.assertIn('bf_reference',names)
                self.assertNotIn('bf_engineering',names)
                self.assertNotIn('bash',names)
                base={'id':'fixture-reference','object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
                on_chunk({**base,'choices':[{'index':0,'delta':{'role':'assistant','content':'Reference-only startup fixture.'},'finish_reason':None}]})
                on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})
                return {'model':MODEL,'usage':{'prompt_tokens':20,'completion_tokens':5,'total_tokens':25}}
            try:
                app.provider.complete=fake_model
                folder=app.organization.create_folder('reference only')
                app.organization.configure(folder['id'],{**folder['config'],'tools':['bf_reference','read','write']},0)
                c=app.conversations.create('Read sources only.',None,'reference-fixture',folder['id'])
                end=time.time()+35
                while c['id'] in app.conversations.starting and time.time()<end:time.sleep(.05)
                final=app.conversations.get(c['id'])
                self.assertEqual('IDLE',final['status'],final['error'])
                self.assertEqual(1,len(requests))
                self.assertEqual([],app.engineering.jobs(c['id']))
            finally:
                for cid in list(app.conversations.processes):app.conversations.stop(cid)
                end=time.time()+8
                while app.conversations.starting and time.time()<end:time.sleep(.05)
                server.shutdown();server.server_close();app.stop.set();app.thread.join(3);app.lock.close()

    def test_real_pi_restricted_tools_and_independent_submission_with_fixture_provider(self):
        """Real Pi process / fixture model and native result: integration, not design evidence."""
        import threading
        from http.server import ThreadingHTTPServer
        from bfworld.agentlab.server import Workbench, handler
        from bfworld.agentlab.provider import MODEL
        with tempfile.TemporaryDirectory() as tmp:
            app=Workbench(Path(tmp)/'state')
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(app))
            app.conversations.port=server.server_port
            threading.Thread(target=server.serve_forever,daemon=True).start()
            requests=[]
            response_ref=[]
            admission_attempts=[]
            original_submit=app.engineering.submit
            def busy_then_admit(owner,body,initiator='unrecorded'):
                admission_attempts.append(json.loads(json.dumps(body)))
                if len(admission_attempts)<=2:raise ValueError('ENGINEERING_BUSY')
                return original_submit(owner,body,initiator)
            app.engineering.submit=busy_then_admit
            def fake_model(owner,payload,on_chunk=None):
                requests.append(payload);step=len(requests)
                self.assertEqual(['bf_engineering'],[t['function']['name'] for t in payload['tools']])
                properties=payload['tools'][0]['function']['parameters']['properties']
                self.assertIn('requested_kind',properties)
                self.assertIn('falsifier',properties)
                job=app.engineering.jobs(owner)
                if step==4:
                    tool=next(m for m in reversed(payload['messages']) if m.get('role')=='tool')
                    descriptor=json.loads(tool['content'])
                    self.assertFalse(descriptor['full_response_inline'])
                    response_ref.append(descriptor['_response'])
                if step==5:
                    tool=next(m for m in reversed(payload['messages']) if m.get('role')=='tool')
                    page=json.loads(tool['content'])
                    self.assertEqual(response_ref[0],page['_response'])
                    self.assertIsNotNone(page['next_offset'])
                    self.assertIn(job[0]['id'],page['text'])
                    self.assertLess(len(tool['content'].encode()),24000)
                args=({'action':'run','engine':'closed-simulation','parameters':{'candidate':{'circuit':{'cin_uF':22}}},'operation_id':'fixture-candidate'} if step==1 else
                      {'action':'inspect'} if step==2 else
                      {'action':'job','job_id':job[0]['id']} if step==3 else
                      {'action':'response_view','response_id':response_ref[0]['response_id'],'response_sha256':response_ref[0]['sha256'],'offset':0,'limit':16000} if step==4 else
                      {'action':'artifact_view','job_id':job[0]['id'],'artifact_name':'task-evaluation.json'} if step==5 else
                      {'action':'submit','job_id':job[0]['id'],'rationale':'Fixture negative candidate; not actual design evidence.'})
                if step==3:
                    tool=next(m for m in reversed(payload['messages']) if m.get('role')=='tool')
                    index=json.loads(tool['content'])
                    self.assertEqual(job[0]['id'],index['jobs'][0]['id'])
                    self.assertNotIn('record_file',index)
                    self.assertLess(len(tool['content'].encode()),24000)
                base={'id':'fixture-'+str(step),'object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
                delta={'role':'assistant','tool_calls':[{'index':0,'id':'call-'+str(step),'type':'function','function':{'name':'bf_engineering','arguments':json.dumps(args)}}]} if step<=6 else {'role':'assistant','content':'测试夹具已提交，不能作为真实设计结果。'}
                on_chunk({**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]})
                on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if step<=6 else 'stop'}]})
                on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':5,'total_tokens':25}})
                return {'model':MODEL,'usage':{'prompt_tokens':20,'completion_tokens':5,'total_tokens':25}}
            def fake_native(engine,job,directory,deadline):
                write_json(directory/'design-spec.json',job['parameters']['candidate'])
                write_json(directory/'receiver.json',{'transmitted':[],'delivered':[],'events':[]})
                return {'run_status':'completed','checks':dict.fromkeys(NUMERICAL,True),'metrics':{'cold_start_reached':False},'artifacts':[],'product_verified':False,'oversized_native_detail':'x'*60000}
            try:
                app.provider.complete=fake_model
                with app.store.connect() as db:
                    db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',(json.loads((TASK_ROOT/'protocol.json').read_text())['id'],time.time(),time.time()+90,2,MODEL,'fixture only'))
                with patch('bfworld.agentlab.simulation_chain.run',side_effect=fake_native):
                    trial=app.engineering.tasks.create_trial(app,'baseline-r1','Fixture integration only: exercise tools and seal the negative candidate.')
                    end=time.time()+35
                    while trial['id'] in app.conversations.starting and time.time()<end:time.sleep(.05)
                    final=app.conversations.get(trial['id'])
                self.assertEqual('IDLE',final['status'],final['error'])
                self.assertEqual(7,len(requests))
                self.assertEqual(3,len(admission_attempts))
                self.assertEqual(admission_attempts[0],admission_attempts[1])
                self.assertEqual(admission_attempts[1],admission_attempts[2])
                self.assertEqual(1,len(app.engineering.jobs(trial['id'])))
                with app.store.connect() as db:
                    receipt=json.loads(db.execute('SELECT receipt FROM simulation_task_submissions WHERE owner=?',(trial['id'],)).fetchone()[0])
                self.assertEqual('unsatisfied',receipt['evaluation']['nominal_task_status'])
                self.assertEqual(0,app.provider.status()['calls'])
            finally:
                for cid in list(app.conversations.processes):app.conversations.stop(cid)
                end=time.time()+8
                while app.conversations.starting and time.time()<end:time.sleep(.05)
                server.shutdown();server.server_close();app.stop.set();app.thread.join(3);app.lock.close()

    def test_trial_authority_bound_before_first_dispatch(self):
        from bfworld.agentlab.server import Workbench
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'paid-window-closed.json').write_text('{}')
            app=Workbench(root/'state')
            try:
                with app.store.connect() as db:
                    db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',
                        (json.loads((TASK_ROOT/'protocol.json').read_text())['id'],time.time(),time.time()+60,2,'deepseek-flash','fixture only'))
                inspected=[]
                def inspect(cid,text,operation,dispatch=True):
                    self.assertTrue(dispatch)
                    self.assertEqual(3,app.engineering.tasks.binding(cid)['max_candidates'])
                    with app.store.connect() as db:
                        self.assertEqual(.5,db.execute('SELECT max_usd FROM owner_model_caps WHERE owner=?',(cid,)).fetchone()[0])
                        self.assertEqual('baseline-r1',db.execute('SELECT trial FROM research_model_owners WHERE owner=?',(cid,)).fetchone()[0])
                        self.assertEqual(0,db.execute('SELECT count(*) FROM model_requests').fetchone()[0])
                    inspected.append(cid)
                with patch.object(app.conversations,'send',side_effect=inspect):
                    trial=app.engineering.tasks.create_trial(app,'baseline-r1','Fixture; must not dispatch a model')
                self.assertEqual([trial['id']],inspected)
            finally:
                app.stop.set();app.thread.join(3);app.lock.close()

    def test_bounded_waveform_window(self):
        from bfworld.agentlab.simulation_tasks import SimulationTasks
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'waveform.csv'
            p.write_text('time_s,supply_V,tip_m\n'+''.join(f'{i/1000},3.3,0.001\n' for i in range(1000)))
            tasks=object.__new__(SimulationTasks)
            eng=SimpleNamespace(artifact=lambda *args:p)
            body={'job_id':'fixture','artifact_name':p.name,'channels':['time_s','supply_V'],'time_from':.1,'time_to':.4}
            a=tasks.artifact_view(eng,'owner',body)
            self.assertEqual(301,a['matched_rows']);self.assertEqual(200,len(a['rows']))
            b=tasks.artifact_view(eng,'owner',{**body,'offset':a['next_offset']})
            self.assertEqual(101,len(b['rows']));self.assertIsNone(b['next_offset'])
            self.assertEqual('0.3',b['rows'][0]['time_s'])

    def test_owner_binding_cap_submission_and_hashes(self):
        from bfworld.agentlab.server import Workbench
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'paid-window-closed.json').write_text('{}')
            app=Workbench(root/'state')
            try:
                owner=app.conversations.create('task boundary fixture',None,'task-boundary-fixture')['id']
                b=app.engineering.tasks.bind(owner,'door-event-nominal-v1',1)
                with self.assertRaisesRegex(ValueError,'NOT_AUTHORIZED'):
                    app.engineering.tasks.create_trial(app,'baseline-r1','No model dispatch')
                self.assertEqual(b,app.engineering.tasks.bind(owner,'door-event-nominal-v1',1))
                with self.assertRaisesRegex(ValueError,'IMMUTABLE'):
                    app.engineering.tasks.bind(owner,'door-event-nominal-v1',2)
                with self.assertRaisesRegex(ValueError,'TASK_ENGINE_NOT_ALLOWED'):
                    app.engineering.submit(owner,{'engine':'blender','parameters':{},'operation_id':'alternate'})
                with self.assertRaisesRegex(ValueError,'TASK_PROTECTED_FIELD'):
                    app.engineering.submit(owner,{'engine':'closed-simulation','parameters':{'candidate':{'circuit':{'initial_vin_V':3}}},'operation_id':'precharged'})
                self.assertEqual([],app.engineering.jobs(owner))
                def fake(engine,job,directory,deadline):
                    write_json(directory/'design-spec.json',job['parameters']['candidate'])
                    write_json(directory/'receiver.json',{'transmitted':[],'delivered':[],'events':[]})
                    r={'run_status':'completed','checks':dict.fromkeys(NUMERICAL,True),'metrics':{'cold_start_reached':False},'artifacts':[],'product_verified':False}
                    write_json(directory/'result.json',r)
                    return r
                body={'engine':'closed-simulation','parameters':{'candidate':{}},'operation_id':'one'}
                with patch('bfworld.agentlab.simulation_chain.run',side_effect=fake):
                    job=app.engineering.submit(owner,body)
                    end=time.time()+5
                    while time.time()<end:
                        job=app.engineering.get(owner,job['id'])
                        if job['status'] not in ('RUNNING','QUEUED'):break
                        time.sleep(.02)
                self.assertEqual('SUCCEEDED',job['status'],job.get('error'))
                self.assertEqual(job['id'],app.engineering.submit(owner,body)['id'])
                with self.assertRaisesRegex(ValueError,'TASK_CANDIDATE_BUDGET'):
                    app.engineering.submit(owner,{**body,'operation_id':'two'})
                receipt=app.engineering.tasks.submit(app.engineering,owner,job['id'],'No feasible candidate observed.')
                self.assertEqual('unsatisfied',receipt['evaluation']['nominal_task_status'])
                with self.assertRaises(PermissionError):
                    app.engineering.get('another-owner',job['id'])
                p=app.engineering.artifact(owner,job['id'],'result.json');p.write_text('{}')
                with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):
                    app.engineering.tasks.submit(app.engineering,owner,job['id'],'No feasible candidate observed.')
            finally:
                app.stop.set();app.thread.join(3);app.lock.close()


if __name__=='__main__':unittest.main()
