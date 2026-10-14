"""Original P01 consumer contracts; disposable native observations, no paid run.

These tests prove lifecycle/HTTP/recovery behavior, not engineering acceptance.
"""
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from types import SimpleNamespace

from bfworld.agentlab.server import Workbench, handler
from bfworld.agentlab.solar_companion import definition
from bfworld.agentlab.store import canonical, identity
from bfworld.agentlab.design_lab import paper_candidate as pc
from bfworld.agentlab.design_lab.service import DesignLab
from bfworld.agentlab.paper_sessions import ReadOnlyStore, reader


class OriginalPaperConsumer(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.runtime=self.root/'runtime';self.runtime.mkdir()
        (self.runtime/'paid-window-closed.json').write_text('{}')
        self.app=Workbench(self.runtime/'state')
        self.owner=self.app.conversations.create('Restore the original paper candidate',None,'P01')['id']
        self.workspace=self.runtime/'participants'/self.owner;self.workspace.mkdir(parents=True,exist_ok=True)
        source=self.app.conversations.detail(self.owner)['messages'][0]['id']
        self.app.assemblies.write(self.owner,{'source_message_id':source,'operation_id':'old-assembly',
            'expected_revision':0,'payload':definition()})
        self.app.eda_cli.bind(self.owner,'original-native-project','original operator authorization',True)
        self.put('campaign/parallel-20261009/pi-session-index.json',{'sessions':[{'paper_id':'P01','owner':self.owner}]})
        self.put('campaign/acceptance/P01/scope-v1.json',{'paper':'P01','owner':self.owner,
            'scope':'complete-digital-system','required_gates':[{'id':g} for g in pc.GATES]})
        previous=self.put('campaign/acceptance/old.json',{'papers':[{'paper':'P01','owner':self.owner,'issues':[]}]})
        self.put('campaign/acceptance/current.json',{'path':'campaign/acceptance/old.json','sha256':pc.sha(previous)})
        self.project={'schema_version':'bf-engineering-project-v1','kind':'spice','entrypoint':'model.cir',
            'files':['model.cir'],'interfaces':{'units':'SI'}}
        (self.workspace/'project').mkdir()
        (self.workspace/'project/project.json').write_text(canonical(self.project))
        (self.workspace/'project/model.cir').write_text('fixture circuit source; never executed')
        (self.workspace/'plan.md').write_text('Existing Pi authored fixture decision')
        (self.workspace/'contract.json').write_text(canonical({'paper_id':'P01','source_identity':'original-source',
            'required_project_kinds':['spice']}))
        self.choice={'schema_version':pc.SCHEMA,'files':['plan.md','contract.json'],'projects':['project/project.json'],
            'eda_receipts':[],'selected_jobs':[],'decision':'Import the existing candidate without choosing its devices'}
        self.bind()
        self.token=self.app.store.issue(self.owner)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app))
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close()
        self.app.design_lab.closing.set();self.app.design_lab.wake.set()
        self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()

    def put(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(canonical(value));return p

    def bind(self):
        self.view=self.app.design_lab.handle(self.owner,{'action':'configure_paper','root':str(self.root),
            'sources':{'candidate.json':canonical(self.choice)}},operator=True)

    def request(self,route,body):
        req=urllib.request.Request(self.url+route,data=json.dumps(body).encode(),headers={
            'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=10) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as e:return e.code,json.load(e)

    def write(self,operation='native-change',**extra):
        return {'action':'command','argv':['sch','replace','--id','old','--lcsc','C123'],
            'operation_id':operation,'candidate_id':self.view['working_design'],
            'candidate_revision':self.view['revision'],'decision_use':'Decide whether the chosen device maps correctly',**extra}

    def blocker(self):
        value={'schema_version':'bf-eda-cli-operation-v1','owner':self.owner,'project':'original-native-project',
            'command_entered':True,'argv':['sch','replace','--id','old'],'status':'FAILED',
            'native_host':{'window_id':'retired-desktop'},
            'error':'context deadline exceeded; the response does not prove no write'}
        p=self.put('runtime/participants/'+self.owner+'/eda-receipts/interrupted.json',value)
        pc.record_blocker(self.app.design_lab,self.owner,'import-old-write',{'operation_id':'import-old-write',
            'receipt_path':str(p.relative_to(self.root)),'receipt_sha256':pc.sha(p)})
        return p,value

    def reconciliation(self):
        from bfworld.agentlab.runtime_config import eda_policy
        op=self.app.design_lab.view(self.owner)['intent']['job_id']
        original=self.app.design_lab.operation(self.owner,op)['request']['public_fact']
        def ref(name,value):
            p=self.put('deployment/reconciliation/'+name+'.json',value)
            return {'path':str(p.relative_to(self.root)),'sha256':pc.sha(p)}
        native=(self.root/'native').resolve();native.mkdir(exist_ok=True)
        project=native/'original.eprj3';project.write_text(canonical({'name':'original'}))
        (native/'P1.esch2').write_text('fixture persisted schematic');(native/'PCB1.epcb2').write_text('fixture PCB')
        creation=ref('creation',{'name':'original'})
        self.put('campaign/eda/P01/binding.json',{'local_project':str(project),'creation':creation})
        host={'host':'desktop','mode':'half-offline'}
        health={'found':{'raw':{'windows':[{'windowId':'new-desktop','connectorVersion':eda_policy()['connector_version'],
            'context':{'projectUuid':'original-native-project','environment':host}}]}}}
        scene={'ok':True,'context':{'projectUuid':'original-native-project','documentUuid':'P1'},
            'result':{'componentCount':1,'components':[{'id':'remaining'}],'netlistAvailable':True,'nets':[]}}
        files={str(p):{'sha256':pc.sha(p),'bytes':p.stat().st_size} for p in native.iterdir()}
        proof={'schema_version':'bf-desktop-native-reconciliation-v1','owner':self.owner,
            'original_receipt':original,'human_confirmed_full_restart':True,'window_id':'new-desktop','document_uuid':'P1',
            'health_before':ref('health-before',health),'health_after':ref('health-after',health),
            'reads':[ref('read-one',scene),ref('read-two',scene)],
            'persisted_before':ref('files-before',files),'persisted_after':ref('files-after',files)}
        return op,proof,ref('proof',proof),native

    def test_operator_reconciles_retired_desktop_without_replay_or_rewriting_native_history(self):
        path,original=self.blocker();op,proof,reference,native=self.reconciliation()
        with patch('bfworld.agentlab.runtime_config.configured',return_value=native),patch.object(self.app.eda_cli,'action') as sdk:
            value=pc.reconcile_desktop(self.app.design_lab,self.owner,op,reference,True)
            again=pc.reconcile_desktop(self.app.design_lab,self.owner,op,reference,True)
        self.assertEqual(value,again);sdk.assert_not_called()
        self.assertEqual('RECONCILED',value['status']);self.assertFalse(value['result']['replacement_success_claimed'])
        self.assertEqual(original,json.loads(path.read_text()))
        self.assertEqual('AWAITING_PI_DECISION',self.app.design_lab.view(self.owner)['intent']['kind'])
        with patch.object(self.app.eda_cli,'action',return_value={'id':'bf-new-decision','status':'SUCCEEDED'}) as sdk:
            self.assertEqual(200,self.request('/api/eda-cli',self.write('BF-separate-repair'))[0]);self.assertEqual(1,sdk.call_count)

    def test_reconciliation_refuses_participant_proofs_live_old_host_foreign_scene_and_changed_disk(self):
        self.blocker();op,proof,reference,native=self.reconciliation()
        self.assertEqual(403,self.request('/api/design-lab',{'action':'reconcile_native','job_id':op,'proof':reference})[0])
        def replace(name,body):
            p=self.put('deployment/reconciliation/'+name+'.json',body)
            return {'path':str(p.relative_to(self.root)),'sha256':pc.sha(p)}
        mutations=[{'owner':'foreign'}, {'human_confirmed_full_restart':False},
            {'health_after':replace('old-host',{'found':{'raw':{'windows':[{'windowId':'retired-desktop'}]}}})},
            {'reads':[proof['reads'][0],replace('foreign-scene',{'ok':True,'context':{'projectUuid':'foreign'}})]}]
        with patch('bfworld.agentlab.runtime_config.configured',return_value=native):
            for fields in mutations:
                with self.subTest(fields=list(fields)):
                    ref=replace('bad-proof',{**proof,**fields})
                    with self.assertRaises(ValueError):pc.reconcile_desktop(self.app.design_lab,self.owner,op,ref,True)
                    self.assertEqual('UNKNOWN',self.app.design_lab.operation(self.owner,op)['status'])
            (native/'P1.esch2').write_text('Changed native file')
            with self.assertRaisesRegex(ValueError,'PERSISTED_FILES'):pc.reconcile_desktop(self.app.design_lab,self.owner,op,reference,True)

    def test_original_owner_existing_sources_scope_and_readonly_index_are_preserved(self):
        self.assertTrue(pc.readonly_bound(self.root,self.owner));self.assertFalse(pc.readonly_bound(self.root,'foreign'))
        self.assertEqual('candidate-lifecycle',self.view['control_route'])
        self.assertEqual(list(pc.GATES),self.view['contract']['requirements'])
        self.assertFalse(self.view['full_product_passed']);self.assertEqual('NOT_TESTED',self.view['physical'])
        self.assertEqual('Existing Pi authored fixture decision',(self.workspace/'plan.md').read_text())

    def test_actual_http_native_write_has_candidate_binding_and_exact_retry_uses_original_receipt(self):
        native={'id':'eda-real-consumer-fixture','status':'SUCCEEDED','result':{'stdout':'actual native fixture'}}
        with patch.object(self.app.eda_cli,'action',return_value=native) as executor:
            first=self.request('/api/eda-cli',self.write());second=self.request('/api/eda-cli',self.write())
        self.assertEqual(200,first[0]);self.assertEqual(first,second);self.assertEqual(1,executor.call_count)
        sent=executor.call_args.args[1]
        self.assertNotIn('candidate_id',sent);self.assertNotIn('decision_use',sent)
        operation=self.app.design_lab.operation(self.owner,first[1]['candidate_operation_id'])
        self.assertEqual(self.view['working_design'],operation['request']['design_id'])
        self.assertEqual('SUCCEEDED',operation['status'])

    def test_stale_or_unbound_native_write_refuses_before_real_executor(self):
        for changed in ({'candidate_revision':99},{'candidate_id':'foreign'},{'decision_use':''}):
            with self.subTest(changed=changed),patch.object(self.app.eda_cli,'action') as executor:
                self.assertEqual(400,self.request('/api/eda-cli',self.write(**changed))[0]);executor.assert_not_called()

    def test_unknown_write_blocks_renamed_write_and_freeze_but_allows_original_readback(self):
        p,before=self.blocker()
        with patch.object(self.app.eda_cli,'action',return_value={'id':'read-fresh','status':'SUCCEEDED'}) as executor:
            status,value=self.request('/api/eda-cli',self.write('renamed'))
            self.assertEqual(400,status);self.assertIn('PENDING_OPERATION',value['error']);executor.assert_not_called()
            self.assertEqual(200,self.request('/api/eda-cli',{'action':'command','operation_id':'read-original',
                'argv':['sch','list']})[0])
        self.assertEqual(before,json.loads(p.read_text()))
        status,_=self.request('/api/design-lab',{'action':'freeze','parent':self.view['working_design'],
            'sources':{'candidate.json':canonical(self.choice)}})
        self.assertEqual(400,status)

    def test_entered_executor_exception_stays_unknown_even_if_value_error(self):
        with patch.object(self.app.eda_cli,'action',side_effect=ValueError('native SDK lost reply')):
            self.assertEqual(400,self.request('/api/eda-cli',self.write())[0])
        with self.app.store.connect() as db:row=db.execute('SELECT status FROM design_operations WHERE owner=?',(self.owner,)).fetchone()
        self.assertEqual('UNKNOWN',row['status'])

    def test_restart_preserves_working_candidate_plan_unknown_and_never_calls_case_c(self):
        self.blocker()
        self.app.design_lab.handle(self.owner,{'action':'intent','kind':'BLOCKED',
            'rationale':'Wait for native host reconciliation','plan':['Reconcile the original operation']})
        restarted=DesignLab(self.app,start_worker=False)
        with patch('bfworld.agentlab.design_lab.case_c.execute') as wrong:
            value=restarted.view(self.owner)
            self.assertEqual('BLOCKED',value['intent']['kind']);self.assertEqual(['Reconcile the original operation'],value['plan'])
            with self.assertRaisesRegex(ValueError,'NATIVE_ENTRY'):restarted.run(self.owner,'wrong',value['working_design'])
            with self.assertRaisesRegex(ValueError,'ORIGINAL_QUEUE'):self.app.conversations.start(self.owner)
            wrong.assert_not_called()

    def test_modified_source_requires_new_frozen_candidate_and_does_not_automatically_adopt(self):
        (self.workspace/'project/model.cir').write_text('BF changed the candidate source')
        with patch.object(self.app.eda_cli,'action') as executor:
            self.assertEqual(400,self.request('/api/eda-cli',self.write())[0]);executor.assert_not_called()
        status,value=self.request('/api/design-lab',{'action':'freeze','parent':self.view['working_design'],
            'sources':{'candidate.json':canonical(self.choice)}})
        self.assertEqual(200,status);self.assertNotEqual(value['design_id'],self.view['working_design'])
        fresh=self.app.design_lab.view(self.owner)
        self.assertEqual(value['design_id'],fresh['working_design']);self.assertEqual(self.view['current_design'],fresh['current_design'])

    def test_actual_engineering_entry_requires_selected_project_and_tracks_existing_native_job(self):
        body={'action':'run','engine':'engineering-project','operation_id':'build-one',
            'parameters':{'assembly_revision':1,'project_path':'project/project.json'},'candidate_id':self.view['working_design'],
            'candidate_revision':self.view['revision'],'decision_use':'Check the current model input'}
        with patch.object(self.app.engineering,'authorize'),patch.object(self.app.engineering,'submit',
                return_value={'id':'eng-native-fixture','status':'QUEUED'}) as executor:
            status,value=self.request('/api/engineering',body)
        self.assertEqual(202,status);self.assertEqual(1,executor.call_count)
        op=self.app.design_lab.operation(self.owner,value['candidate_operation_id']);self.assertEqual('WAITING_NATIVE',op['status'])
        with patch.object(self.app.engineering,'get',return_value={'id':'eng-native-fixture','status':'SUCCEEDED'}) as observe:
            status,done=self.request('/api/design-lab',{'action':'job','job_id':op['id']})
        self.assertEqual(200,status);self.assertEqual('SUCCEEDED',done['status']);self.assertEqual(1,observe.call_count)

    def test_real_http_eda_rejects_before_creating_candidate_action(self):
        for argv in [['debug','--help'],['call','debug.exec_js'],['pcb','read','--project','foreign']]:
            with self.subTest(argv=argv),patch.object(self.app.eda_cli,'action') as execute:
                body=self.write('bad-'+str(len(argv)),argv=argv)
                self.assertEqual(400,self.request('/api/eda-cli',body)[0]);execute.assert_not_called()
            with self.app.store.connect() as db:
                self.assertEqual(0,db.execute('SELECT COUNT(*) FROM design_operations WHERE owner=?',(self.owner,)).fetchone()[0])

    def test_readonly_pcb_inventory_remains_available_during_unknown_write(self):
        self.blocker()
        for action in ['dump','board-info','outline-get','nets','drc-rules']:
            with self.subTest(action=action),patch.object(self.app.eda_cli,'action',return_value={'status':'SUCCEEDED','id':'read-'+action}) as execute:
                status,value=self.request('/api/eda-cli',{'action':'command','argv':['pcb',action],
                    'operation_id':'read-'+action})
                self.assertEqual(200,status);self.assertEqual(1,execute.call_count)
        with patch.object(self.app.eda_cli,'action') as execute:
            self.assertEqual(400,self.request('/api/eda-cli',self.write())[0]);execute.assert_not_called()

    def test_help_reconciliation_keeps_unknown_receipt_without_native_replay(self):
        body={'action':'command','argv':['call','--help'],'operation_id':'old-call-help'}
        with patch.object(self.app.eda_cli,'action',side_effect=ValueError('EDA_TYPED_ACTION_DENIED')):
            self.assertEqual(400,self.request('/api/eda-cli',body)[0])
        with self.app.store.connect() as db:
            key=db.execute('SELECT id FROM design_operations WHERE owner=?',(self.owner,)).fetchone()[0]
            fees=list(db.execute('SELECT * FROM model_requests'))
        original=self.app.design_lab.root/self.owner/'operations'/key/'result.json';before=original.read_bytes()
        def ref(name,value):
            p=self.put('deployment/eda-admission/'+name,value);return {'path':str(p.resolve().relative_to(self.root.resolve())),'sha256':pc.sha(p)}
        validator=self.root/'deployment/eda-admission/validator.py';validator.parent.mkdir(parents=True,exist_ok=True)
        validator.write_text('pinned original typed admission')
        vr={'path':str(validator.resolve().relative_to(self.root.resolve())),'sha256':pc.sha(validator)}
        qualification=ref('qualification.json',{'status':'PASS','apparatus_modules':{'bfworld.agentlab.eda_cli':vr['sha256']}})
        proof=ref('proof.json',{'schema_version':'bf-eda-admission-reconciliation-v1','owner':self.owner,'operation_id':key,
            'error':'ValueError: EDA_TYPED_ACTION_DENIED','argv':['call','--help'],
            'original_result':{'path':str(original.relative_to(self.root.resolve())),'sha256':pc.sha(original)},
            'validator':vr,'qualification':qualification})
        with self.assertRaises(PermissionError):pc.reconcile_eda_admission(self.app.design_lab,self.owner,key,proof)
        with patch.object(self.app.eda_cli,'action') as execute:
            one=pc.reconcile_eda_admission(self.app.design_lab,self.owner,key,proof,True)
            self.assertEqual(one,pc.reconcile_eda_admission(self.app.design_lab,self.owner,key,proof,True));execute.assert_not_called()
        self.assertEqual('RECONCILED',one['status']);self.assertEqual(before,original.read_bytes())
        with self.app.store.connect() as db:self.assertEqual(fees,list(db.execute('SELECT * FROM model_requests')))

    def test_real_http_spice_measurement_is_admitted_and_external_directive_creates_no_unknown(self):
        def frozen(text):
            (self.workspace/'project/model.cir').write_text(text)
            self.app.design_lab.handle(self.owner,{'action':'freeze','parent':self.app.design_lab.view(self.owner)['working_design'],
                'sources':{'candidate.json':canonical(self.choice)}})
            view=self.app.design_lab.view(self.owner)
            return {'action':'run','engine':'engineering-project','operation_id':'measure-admission',
                'parameters':{'assembly_revision':1,'project_path':'project/project.json'},
                'candidate_id':view['working_design'],'candidate_revision':view['revision'],'decision_use':'Observe actual measurements'}
        body=frozen('Measure fixture\nV1 x 0 1\nR1 x 0 1000\n.meas tran value FIND v(x) AT=0.1\n.measure tran charge INTEG i(V1)\n.tran 0.01 0.2\n.end\n')
        with patch.object(self.app.engineering,'authorize'),patch.object(self.app.engineering,'submit',return_value={'id':'eng-measure','status':'SUCCEEDED'}) as sdk:
            self.assertEqual(202,self.request('/api/engineering',body)[0]);self.assertEqual(1,sdk.call_count)
        for directive in ('.control\nshell echo wrong','.include /outside','.lib /outside'):
            bad=frozen('Rejected fixture\n'+directive+'\n.end\n');bad['operation_id']='denied-'+str(len(directive))
            with patch.object(self.app.engineering,'authorize'),patch.object(self.app.engineering,'submit') as sdk:
                self.assertEqual(400,self.request('/api/engineering',bad)[0]);sdk.assert_not_called()
            with self.app.store.connect() as db:
                self.assertIsNone(db.execute('SELECT status FROM design_operations WHERE owner=? AND operation=?',(self.owner,bad['operation_id'])).fetchone())

    def test_admission_reconciliation_preserves_unknown_receipt_and_refuses_unproven_errors(self):
        body={'action':'run','engine':'engineering-project','operation_id':'old-admission',
            'parameters':{'assembly_revision':1,'project_path':'project/project.json'},'candidate_id':self.view['working_design'],
            'candidate_revision':self.view['revision'],'decision_use':'Execute original frozen model'}
        with patch.object(self.app.engineering,'authorize'),patch.object(self.app.engineering,'submit',side_effect=ValueError('PROJECT_SPICE_DIRECTIVE_DENIED')):
            self.assertEqual(400,self.request('/api/engineering',body)[0])
        with self.app.store.connect() as db:key=db.execute('SELECT id FROM design_operations WHERE owner=? AND operation=?',(self.owner,'old-admission')).fetchone()[0]
        original=self.app.design_lab.root/self.owner/'operations'/key/'result.json';bytes_before=original.read_bytes()
        def ref(name,text):
            p=self.root/'deployment/admission'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            return {'path':str(p.relative_to(self.root)),'sha256':pc.sha(p)}
        validator=ref('validator.py',"def request():\n allowed={'.tran','.end'}\n")
        dispatcher=ref('dispatcher.py','fixture original dispatcher')
        qualification=ref('qualification.json',canonical({'status':'PASS','apparatus_modules':{
            'bfworld.agentlab.engineering_projects':validator['sha256'],'bfworld.agentlab.engineering':dispatcher['sha256']}}))
        proof={'schema_version':'bf-engineering-admission-reconciliation-v1','owner':self.owner,'operation_id':key,
            'error':'ValueError: PROJECT_SPICE_DIRECTIVE_DENIED','original_result':{'path':str(original.relative_to(self.root.resolve())),'sha256':pc.sha(original)},
            'validator':validator,'dispatcher':dispatcher,'qualification':qualification}
        reference=ref('proof.json',canonical(proof))
        with self.assertRaisesRegex(PermissionError,'OPERATOR'):pc.reconcile_admission(self.app.design_lab,self.owner,key,reference)
        with self.assertRaisesRegex(ValueError,'NOT_REPRODUCED'):pc.reconcile_admission(self.app.design_lab,self.owner,key,reference,True)
        self.assertEqual('UNKNOWN',self.app.design_lab.operation(self.owner,key)['status'])
        self.assertEqual(bytes_before,original.read_bytes())

    def test_proven_historical_admission_reconciles_idempotently_without_native_or_fee_edits(self):
        (self.workspace/'project/model.cir').write_text('measurement fixture\n.meas tran value FIND v(x) AT=0.1\n.tran 0.01 0.2\n.end\n')
        self.app.design_lab.handle(self.owner,{'action':'freeze','parent':self.view['working_design'],
            'sources':{'candidate.json':canonical(self.choice)}})
        view=self.app.design_lab.view(self.owner)
        body={'action':'run','engine':'engineering-project','operation_id':'historical-admission',
            'parameters':{'assembly_revision':1,'project_path':'project/project.json'},'candidate_id':view['working_design'],
            'candidate_revision':view['revision'],'decision_use':'Observe the original model'}
        with patch.object(self.app.engineering,'authorize'),patch.object(self.app.engineering,'submit',side_effect=ValueError('PROJECT_SPICE_DIRECTIVE_DENIED')):
            self.assertEqual(400,self.request('/api/engineering',body)[0])
        with self.app.store.connect() as db:
            key=db.execute('SELECT id FROM design_operations WHERE owner=? AND operation=?',(self.owner,'historical-admission')).fetchone()[0]
            fee_before=list(db.execute('SELECT * FROM model_requests'))
        original=self.app.design_lab.root/self.owner/'operations'/key/'result.json';old_bytes=original.read_bytes()
        def ref(name,text):
            p=self.root/'deployment/admission'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            return {'path':str(p.relative_to(self.root)),'sha256':pc.sha(p)}
        validator=ref('validator.py',"def request():\n allowed={'.tran','.end'}\n")
        dispatcher=ref('dispatcher.py','pinned original dispatcher')
        qualification=ref('qualification.json',canonical({'status':'PASS','apparatus_modules':{
            'bfworld.agentlab.engineering_projects':validator['sha256'],'bfworld.agentlab.engineering':dispatcher['sha256']}}))
        proof={'schema_version':'bf-engineering-admission-reconciliation-v1','owner':self.owner,'operation_id':key,
            'error':'ValueError: PROJECT_SPICE_DIRECTIVE_DENIED','original_result':{'path':str(original.relative_to(self.root.resolve())),'sha256':pc.sha(original)},
            'validator':validator,'dispatcher':dispatcher,'qualification':qualification}
        reference=ref('proof.json',canonical(proof))
        with patch.object(self.app.engineering,'submit') as native:
            first=pc.reconcile_admission(self.app.design_lab,self.owner,key,reference,True)
            self.assertEqual(first,pc.reconcile_admission(self.app.design_lab,self.owner,key,reference,True));native.assert_not_called()
        self.assertEqual('RECONCILED',first['status']);self.assertEqual(['.meas'],first['result']['denied_directives'])
        self.assertEqual(old_bytes,original.read_bytes())
        with self.app.store.connect() as db:
            self.assertEqual(fee_before,list(db.execute('SELECT * FROM model_requests')))
            self.assertEqual(0,db.execute('SELECT COUNT(*) FROM engineering_jobs').fetchone()[0])

    def test_original_eda_job_query_settles_candidate_once_without_native_replay(self):
        with patch.object(self.app.eda_cli,'action',return_value={'id':'eda-completed','status':'RUNNING'}):
            status,started=self.request('/api/eda-cli',self.write())
        key=started['candidate_operation_id']
        dispatch=(self.app.design_lab.root/self.owner/'operations'/key/'dispatch.json').read_bytes()
        with patch.object(self.app.eda_cli,'action',return_value={'id':'eda-completed','status':'SUCCEEDED'}) as executor:
            for _ in range(2):
                status,done=self.request('/api/eda-cli',{'action':'job','job_id':'eda-completed'})
                self.assertEqual(200,status)
                self.assertEqual('SUCCEEDED',self.app.design_lab.operation(self.owner,key)['status'])
                self.assertEqual(key,done['candidate_operation_id'])
            self.assertTrue(all(c.args[1]['action']=='job' for c in executor.call_args_list))
        with self.app.store.connect() as db:
            events=[json.loads(r[0]) for r in db.execute(
                "SELECT data FROM design_events WHERE owner=? AND kind='candidate_action_observed'",(self.owner,))]
        self.assertEqual(1,sum(e['operation_id']==key and e['status']=='SUCCEEDED' for e in events))
        self.assertEqual(dispatch,(self.app.design_lab.root/self.owner/'operations'/key/'dispatch.json').read_bytes())

    def test_native_job_still_running_failure_unknown_and_foreign_query(self):
        for final in ('RUNNING','FAILED','UNKNOWN'):
            with self.subTest(final=final):
                self.app.design_lab.root.joinpath(self.owner).mkdir(exist_ok=True)
                with patch.object(self.app.eda_cli,'action',return_value={'id':'eda-'+final,'status':'RUNNING'}):
                    _,started=self.request('/api/eda-cli',{'action':'command','operation_id':'read-'+final,'argv':['sch','connectivity']})
                key=started['candidate_operation_id']
                with patch.object(self.app.eda_cli,'action',return_value={'id':'different-job','status':'SUCCEEDED'}):
                    self.assertEqual(200,self.request('/api/eda-cli',{'action':'job','job_id':'different-job'})[0])
                self.assertEqual('WAITING_NATIVE',self.app.design_lab.operation(self.owner,key)['status'])
                with patch.object(self.app.eda_cli,'action',return_value={'id':'eda-'+final,'status':final}):
                    self.assertEqual(200,self.request('/api/eda-cli',{'action':'job','job_id':'eda-'+final})[0])
                self.assertEqual('WAITING_NATIVE' if final=='RUNNING' else final,self.app.design_lab.operation(self.owner,key)['status'])

    def test_connectivity_read_is_available_while_unknown_write_is_blocked(self):
        self.blocker()
        with patch.object(self.app.eda_cli,'action',return_value={'id':'eda-read','status':'SUCCEEDED'}) as executor:
            status,_=self.request('/api/eda-cli',{'action':'command','operation_id':'locate-existing-pins',
                'argv':['sch','connectivity','--doc','original-page']})
        self.assertEqual(200,status);self.assertEqual(1,executor.call_count)
        for argv in (['sch','replace'],['sch','connect'],['pcb','import-changes']):
            self.assertFalse(pc.readonly_eda({'argv':argv}))

    def test_engineering_job_query_settles_only_its_candidate_channel(self):
        body={'action':'run','engine':'engineering-project','operation_id':'native-build',
            'parameters':{'assembly_revision':1,'project_path':'project/project.json'},'candidate_id':self.view['working_design'],
            'candidate_revision':self.view['revision'],'decision_use':'Build current selected input'}
        with patch.object(self.app.engineering,'authorize'),patch.object(self.app.engineering,'submit',
                return_value={'id':'eng-existing','owner':self.owner,'status':'QUEUED'}):
            _,started=self.request('/api/engineering',body)
        key=started['candidate_operation_id']
        with patch.object(self.app.engineering,'authorize'),patch.object(self.app.engineering,'get',
                return_value={'id':'eng-existing','owner':self.owner,'status':'SUCCEEDED'}):
            req=urllib.request.Request(self.url+'/api/engineering/jobs/eng-existing',headers={'Authorization':'Bearer '+self.token})
            with urllib.request.urlopen(req,timeout=10) as response:done=json.load(response)
        self.assertEqual(key,done['candidate_operation_id'])
        self.assertEqual('SUCCEEDED',self.app.design_lab.operation(self.owner,key)['status'])

    def test_resume_inspection_reconciles_completed_original_job_after_restart(self):
        with patch.object(self.app.eda_cli,'action',return_value={'id':'eda-original','status':'RUNNING'}):
            _,started=self.request('/api/eda-cli',self.write())
        restarted=DesignLab(self.app,start_worker=False)
        with patch.object(self.app.eda_cli,'get',return_value={'id':'eda-original','status':'SUCCEEDED'}) as lookup,\
                patch.object(self.app.eda_cli,'action') as executor:
            first=restarted.view(self.owner);second=restarted.view(self.owner)
        self.assertEqual(first,second)
        lookup.assert_called_once_with(self.owner,'eda-original');executor.assert_not_called()
        self.assertEqual('SUCCEEDED',restarted.operation(self.owner,started['candidate_operation_id'])['status'])

    def test_concurrent_terminal_lookups_keep_one_completion_event(self):
        with patch.object(self.app.eda_cli,'action',return_value={'id':'eda-once','status':'RUNNING'}):
            _,started=self.request('/api/eda-cli',self.write())
        native={'id':'eda-once','status':'SUCCEEDED'}
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as workers:
            results=list(workers.map(lambda _:pc.observe_native(self.app.design_lab,self.owner,'eda',native),range(4)))
        self.assertTrue(all(x['candidate_operation_id']==started['candidate_operation_id'] for x in results))
        with self.app.store.connect() as db:
            events=[json.loads(r[0]) for r in db.execute(
                "SELECT data FROM design_events WHERE owner=? AND kind='candidate_action_observed'",(self.owner,))]
        self.assertEqual(1,sum(e['status']=='SUCCEEDED' for e in events))

    def test_same_selected_exact_job_is_reused_without_solver_or_new_native_build(self):
        snap=self.app.design_lab.design(self.owner,self.view['working_design'])
        project={'manifest':self.project,'sources':{'model.cir':'fixture circuit source; never executed'}}
        result={'outputs':[{'name':'existing.raw','sha256':identity('placeholder')}],'kind':'spice'}
        output=self.runtime/'engineering/eng-original/existing.raw';output.parent.mkdir(parents=True);output.write_text('Existing output')
        result['outputs'][0]['sha256']=pc.sha(output)
        job={'id':'eng-original','owner':self.owner,'status':'SUCCEEDED','engine':'engineering-project',
            'project':project,'project_sha256':snap['projects']['project/project.json']['project_sha256'],
            'parameters':{'assembly_revision':1,'project_path':'project/project.json'},'input_dimensions':snap['assembly']['hashes'],'result':result}
        choice={**self.choice,'selected_jobs':['eng-original']}
        with patch.object(self.app.engineering,'get',return_value=job):
            next_design=self.app.design_lab.handle(self.owner,{'action':'freeze','parent':self.view['working_design'],
                'sources':{'candidate.json':canonical(choice)}})
            view=self.app.design_lab.view(self.owner)
            body={'action':'run','engine':'engineering-project','operation_id':'reuse-build',
                'candidate_id':next_design['design_id'],'candidate_revision':view['revision'],
                'decision_use':'Reuse unchanged verified output','parameters':job['parameters']}
            with patch.object(self.app.engineering,'authorize'),patch.object(self.app.engineering,'submit') as executor:
                status,value=self.request('/api/engineering',body)
        self.assertEqual(202,status);self.assertTrue(value['reused_existing_job']);executor.assert_not_called()

    def test_independent_check_uses_actual_paper_scope_and_unknown_cannot_become_full_pass(self):
        self.blocker()
        with patch('bfworld.agentlab.design_lab.case_c.execute') as wrong:
            status,result=self.request('/api/design-lab',{'action':'check','operation_id':'current-scope'})
        self.assertEqual(200,status,result);wrong.assert_not_called()
        self.assertFalse(result['acceptance']['full_product_passed'])
        self.assertEqual('BLOCKED_NATIVE_OPERATION',result['acceptance']['digital_engineering_status'])
        self.assertEqual('NOT_TESTED',result['physical'])

    def test_inspect_returns_exact_current_selector_and_inputs_without_design_mutation(self):
        with self.app.store.connect() as db:
            before=[tuple(r) for r in db.execute('SELECT * FROM design_tasks WHERE owner=?',(self.owner,))]
            events=db.execute('SELECT COUNT(*) FROM design_events WHERE owner=?',(self.owner,)).fetchone()[0]
        value=pc.frozen_view(self.app.design_lab,self.owner)
        snap=self.app.design_lab.design(self.owner,value['working_design'])
        self.assertEqual(self.choice,value['candidate_selector'])
        self.assertEqual(snap['files'],value['input_manifest'])
        self.assertEqual(len(snap['files']),value['input_files'])
        with self.app.store.connect() as db:
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM design_tasks WHERE owner=?',(self.owner,))])
            self.assertEqual(events,db.execute('SELECT COUNT(*) FROM design_events WHERE owner=?',(self.owner,)).fetchone()[0])

    def test_actual_paper_submit_download_preserves_failed_verdict_and_is_idempotent(self):
        import zipfile
        with patch('bfworld.agentlab.design_lab.case_c.execute') as wrong:
            status,check=self.request('/api/design-lab',{'action':'check','operation_id':'review-export'})
            self.assertEqual(200,status)
            body={'action':'submit','job_id':check['check_id'],'rationale':'Submit the inspected candidate with its open gates'}
            status,receipt=self.request('/api/design-lab',body)
            self.assertEqual(200,status,receipt)
            self.assertEqual((status,receipt),self.request('/api/design-lab',body))
            wrong.assert_not_called()
        self.assertFalse(receipt['acceptance']['full_product_passed'])
        req=urllib.request.Request(self.url+'/api/design-lab/package',headers={'Authorization':'Bearer '+self.token})
        with urllib.request.urlopen(req,timeout=10) as response:data=response.read()
        self.assertEqual(Path(receipt['package_path']).read_bytes(),data)
        with zipfile.ZipFile(receipt['package_path']) as archive:
            self.assertEqual('Existing Pi authored fixture decision',archive.read('candidate/plan.md').decode())
            self.assertEqual(check,json.loads(archive.read('check.json')))
        with self.app.store.connect() as db:
            self.assertEqual(1,db.execute("SELECT COUNT(*) FROM design_events WHERE owner=? AND kind='task_submitted'",(self.owner,)).fetchone()[0])

    def test_paper_submit_rejects_unrecorded_changed_and_foreign_check(self):
        _,check=self.request('/api/design-lab',{'action':'check','operation_id':'source-check'})
        path=self.app.design_lab.root/self.owner/'checks'/check['check_id']/'check.json'
        original=path.read_bytes()
        for changed in ({'design_id':'foreign'},{'pending_operations':[{'id':'unknown'}]},
                        {'evaluator_sha256':'forged'}, {'acceptance':{'full_product_passed':True}}):
            path.write_text(canonical({**check,**changed}))
            status,_=self.request('/api/design-lab',{'action':'submit','job_id':check['check_id'],'rationale':'Review'})
            self.assertEqual(400,status)
        path.write_bytes(original)
        self.assertEqual(400,self.request('/api/design-lab',{'action':'submit','job_id':'../check','rationale':'Review'})[0])
        (self.workspace/'project/model.cir').write_text('Changed after check')
        self.assertEqual(400,self.request('/api/design-lab',{'action':'submit','job_id':check['check_id'],'rationale':'Review'})[0])

    def test_export_contains_exact_public_review_scope_and_original_check_input(self):
        import zipfile
        _,check=self.request('/api/design-lab',{'action':'check','operation_id':'public-review-files'})
        _,receipt=self.request('/api/design-lab',{'action':'submit','job_id':check['check_id'],'rationale':'Export public evidence'})
        with zipfile.ZipFile(receipt['package_path']) as archive:
            index=json.loads(archive.read('evidence/index.json'))
            self.assertEqual(self.owner,index['owner'])
            self.assertEqual({'scope','current-input'},{x['kind'] for x in index['references']})
            for ref in index['references']:
                self.assertEqual((self.root/ref['original_path']).read_bytes(),archive.read(ref['package_path']))
                self.assertEqual(ref['sha256'],hashlib.sha256(archive.read(ref['package_path'])).hexdigest())

    def test_public_evidence_refuses_changed_review_and_private_runtime_source(self):
        from bfworld.agentlab.design_lab.paper_delivery import public_evidence
        _,check=self.request('/api/design-lab',{'action':'check','operation_id':'review-integrity'})
        public=self.put('campaign/reviews/P01/digital-gates/public.json',{'owner':self.owner,'paper':'P01','actor':'independent-checker',
            'gate_id':'power_load_chain','status':'FAIL'})
        changed={**check,'acceptance':{**check['acceptance'],'functional_gates':[
            {'id':'power_load_chain','evidence':{'path':str(public.relative_to(self.root)),'sha256':'wrong'}}]}}
        with self.assertRaisesRegex(ValueError,'REVIEW_HASH_CHANGED'):
            public_evidence(self.app.design_lab,self.owner,changed)
        private=self.runtime/'state/private.json';private.write_text('{"private":true}')
        changed['acceptance']['functional_gates'][0]['evidence']={'path':str(private.relative_to(self.root)),'sha256':pc.sha(private)}
        with self.assertRaisesRegex(ValueError,'PUBLIC_REVIEW_REQUIRED'):
            public_evidence(self.app.design_lab,self.owner,changed)

    def test_public_evidence_bundles_failed_gate_and_its_exact_source_review(self):
        from bfworld.agentlab.design_lab.paper_delivery import public_evidence
        _,check=self.request('/api/design-lab',{'action':'check','operation_id':'failed-public-review'})
        source=self.put('campaign/reviews/P01/geometry/result.json',{'measured_overlap_mm3':12})
        public=self.put('campaign/reviews/P01/digital-gates/geometry.json',{'owner':self.owner,
            'paper':'P01','actor':'independent-checker','gate_id':'geometry_fit','status':'FAIL',
            'source_review':{'path':str(source.relative_to(self.root)),'sha256':pc.sha(source)}})
        changed={**check,'acceptance':{**check['acceptance'],'functional_gates':[
            {'id':'geometry_fit','status':'FAIL','evidence':{'path':str(public.relative_to(self.root)),'sha256':pc.sha(public)}}]}}
        files,index=public_evidence(self.app.design_lab,self.owner,changed)
        self.assertEqual({'scope','current-input','gate','source-review'},{r['kind'] for r in index['references']})
        self.assertEqual(source.resolve(),files['evidence/artifacts/'+str(source.relative_to(self.root))].resolve())
        self.assertEqual('FAIL',json.loads(public.read_text())['status'])
        self.assertFalse(changed['acceptance']['full_product_passed'])

    def test_main_operator_download_routes_to_readonly_original_paper_and_rechecks_receipt(self):
        _,check=self.request('/api/design-lab',{'action':'check','operation_id':'federated-export'})
        _,receipt=self.request('/api/design-lab',{'action':'submit','job_id':check['check_id'],'rationale':'Same-version review'})
        read_app=SimpleNamespace(store=ReadOnlyStore(self.app.store.root),engineering=self.app.engineering)
        read_app.design_lab=reader(DesignLab,read_app,root=self.app.design_lab.root)
        papers=SimpleNamespace(has=lambda owner:owner==self.owner,view=lambda:read_app)
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app,papers))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        token=(self.app.store.root/'operator.token').read_text().strip()
        url=f'http://127.0.0.1:{server.server_port}/api/design-lab/package?session_id={self.owner}'
        def rows():
            with read_app.store.connect() as db:
                return identity({name:[dict(r) for r in db.execute('SELECT * FROM '+name)] for name in
                    ('model_requests','engineering_jobs','design_tasks','design_events')})
        before=rows()
        try:
            with patch.object(self.app.design_lab,'delivery',side_effect=AssertionError('main writer must not serve paper ZIP')):
                req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
                with urllib.request.urlopen(req,timeout=10) as response:data=response.read()
                self.assertEqual(Path(receipt['package_path']).read_bytes(),data)
                self.assertEqual(before,rows())
                path=self.app.design_lab.root/self.owner/'checks'/check['check_id']/'check.json'
                original=path.read_bytes();value=json.loads(original);value['acceptance']['full_product_passed']=True
                path.write_text(canonical(value))
                try:
                    with self.assertRaises(urllib.error.HTTPError) as refused:urllib.request.urlopen(req,timeout=10)
                    self.assertEqual(400,refused.exception.code)
                    self.assertEqual(before,rows())
                finally:path.write_bytes(original)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_paper_download_detects_altered_archive_and_new_working_candidate(self):
        _,check=self.request('/api/design-lab',{'action':'check','operation_id':'archived-check'})
        _,receipt=self.request('/api/design-lab',{'action':'submit','job_id':check['check_id'],'rationale':'Review'})
        from bfworld.agentlab.design_lab import paper_delivery
        package=Path(receipt['package_path']);original=package.read_bytes()
        package.write_bytes(b'broken archive')
        import zipfile
        with self.assertRaises((ValueError,zipfile.BadZipFile)):
            paper_delivery.delivery(self.app.design_lab,self.owner)
        package.write_bytes(original)
        (self.workspace/'plan.md').write_text('New Pi decision')
        self.request('/api/design-lab',{'action':'freeze','parent':self.view['working_design'],
            'sources':{'candidate.json':canonical(self.choice)}})
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):
            paper_delivery.delivery(self.app.design_lab,self.owner)

    def test_paper_export_checks_selected_native_output_and_exact_source(self):
        snap=self.app.design_lab.design(self.owner,self.view['working_design'])
        output=self.runtime/'engineering/eng-current/trace.raw';output.parent.mkdir(parents=True);output.write_text('Native fixture output')
        result={'kind':'spice','outputs':[{'name':'trace.raw','sha256':pc.sha(output)}]}
        job={'id':'eng-current','owner':self.owner,'status':'SUCCEEDED','engine':'engineering-project',
            'project_sha256':snap['projects']['project/project.json']['project_sha256'],
            'parameters':{'project_path':'project/project.json'},'result':result}
        with patch.object(self.app.engineering,'get',return_value=job):
            self.request('/api/design-lab',{'action':'freeze','parent':self.view['working_design'],
                'sources':{'candidate.json':canonical({**self.choice,'selected_jobs':['eng-current']})}})
            _,check=self.request('/api/design-lab',{'action':'check','operation_id':'exact-native-output'})
            output.write_text('Altered native output')
            status,error=self.request('/api/design-lab',{'action':'submit','job_id':check['check_id'],'rationale':'Review'})
            self.assertEqual(400,status);self.assertIn('OUTPUT_CHANGED',error['error'])

    def test_old_paper_route_refuses_before_workbench_construction_or_dispatch(self):
        from bfworld.agentlab.literature_native import run_native_tasks
        with patch('bfworld.agentlab.server.Workbench') as second:
            with self.assertRaisesRegex(ValueError,'CANDIDATE_ROUTE_REQUIRED'):
                run_native_tasks(self.root,['P01'],resume=True,phase='engineering-review')
            second.assert_not_called()

    def test_input_paths_and_forged_interrupted_fact_refuse(self):
        for files in (['../secret'],['.pi/session.json'],[{'invalid':'unhashable'}]):
            choice={**self.choice,'files':files}
            with self.subTest(files=files),self.assertRaises(ValueError):
                pc.selector({'candidate.json':canonical(choice)}) if isinstance(files[0],dict) else pc.capture(
                    self.app.design_lab,self.owner,self.view['contract'],self.app.design_lab.task(self.owner)['environment'],
                    {'candidate.json':canonical(choice)})
        p=self.put('fake.json',{'owner':self.owner,'status':'UNKNOWN'})
        with self.assertRaisesRegex(ValueError,'INTERRUPTED_WRITE_IDENTITY'):
            pc.record_blocker(self.app.design_lab,self.owner,'forged',{'receipt_path':'fake.json','receipt_sha256':pc.sha(p)})


if __name__=='__main__':unittest.main()
