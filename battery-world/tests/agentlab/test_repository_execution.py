import json
from types import SimpleNamespace
from test_repository_integration import IntegrationCase, SOURCES
from bfworld.agentlab.design_lab.repository_execution import input_project, handle
from bfworld.agentlab.design_lab.repository import file_hash
from bfworld.agentlab.store import canonical,identity
import unittest

class ExecutionCase(IntegrationCase):
    def prepared(self):
        root=self.repo.root/'workspaces/PT-firmware'
        spec={'schema_version':'bf-engineering-project-v1','kind':'firmware-nrf52832-s132','entrypoint':'main.c',
              'files':['main.c'],'interfaces':{'units':'SI','target':'nRF52832-QFAA','sdk':'17.1.0_ddde560','softdevice':'S132-7.2.0','board':'PCA10040'}}
        self.action(self.fw,'write',operation_id='spec',path='project-fw-s132/project.json',content=canonical(spec),expected_sha256=None)
        self.action(self.fw,'write',operation_id='edit',path='project-fw-s132/main.c',content=SOURCES['project-fw-s132/main.c']+'\n// new source',expected_sha256=file_hash(root/'project-fw-s132/main.c'))
        return self.action(self.fw,'commit',operation_id='execute-commit',paths=['project-fw-s132/project.json','project-fw-s132/main.c'],expected_revision=0,rationale='changed fixed target input')

    def test_fixed_executor_source_snapshot_and_escape(self):
        c=self.prepared();p=input_project(self.repo,c,'project-fw-s132/project.json')
        self.assertEqual(c['files']['project-fw-s132/main.c']['sha256'],__import__('hashlib').sha256(p['sources']['main.c'].encode()).hexdigest())
        with self.assertRaisesRegex(ValueError,'PATH_INVALID'):input_project(self.repo,c,'../project.json')
        with self.assertRaisesRegex(PermissionError,'PROJECT_SCOPE'):input_project(self.repo,c,'project-chain/project.json')

    def test_queue_receipt_retry_dispatch_identity(self):
        c=self.prepared();calls=[]
        def submit(owner,op,project,binding,db=None):
            calls.append(op);self.assertIsNotNone(db)
            return {'id':'eng-fixture','status':'QUEUED'}
        self.lab.app.engineering=SimpleNamespace(submit_repository=submit,dispatch_repository=lambda owner,jid:None)
        body={'action':'repository_execute','operation_id':'execute-one','project_id':self.pid,'domain_commit':c['id'],'path':'project-fw-s132/project.json'}
        one=handle(self.repo,self.fw,body);self.assertEqual(one,handle(self.repo,self.fw,body));self.assertEqual(1,len(calls))
        with self.assertRaisesRegex(PermissionError,'SPECIALIST_EXECUTION_REQUIRED'):handle(self.repo,'pi-chat-a1234567890abcde',body)

    def test_unbuilt_changed_domain_stays_blocked(self):
        c=self.prepared();self.assertEqual('RECHECK_REQUIRED',c['target_build'])
        power=self.domain('power')
        with self.assertRaisesRegex(ValueError,'NEW_INPUT_EXECUTION_REQUIRED'):
            self.action('pi-chat-a1234567890abcde','contract',operation_id='blocked',domain_commits={'power':power['id'],'firmware':c['id']},rationale='must build')

    def test_failed_build_returns_actual_source_and_bounded_diagnostics_without_dispatch(self):
        c=self.prepared();project=input_project(self.repo,c,'project-fw-s132/project.json')
        root=self.repo.root/'failed-worker';root.mkdir()
        (root/'input.json').write_text(canonical({'project':project,'project_sha256':identity(project)}))
        (root/'process.log').write_text('build log\n'*2000+'main.c:42: error: missing_symbol\n')
        artifacts=[{'name':p.name,'sha256':file_hash(p)} for p in root.iterdir()]
        job={'id':'eng-failed','status':'FAILED','error':'PROJECT_PROCESS_EXIT_1',
            'project_sha256':identity(project),'repository_binding':{'domain_commit':c['id']},
            'result':{'artifacts':artifacts}}
        self.lab.app.engineering=SimpleNamespace(get=lambda owner,jid:job,
            artifact=lambda owner,jid,name:root/name,
            dispatch_repository=lambda *a: self.fail('Failed log read dispatched another build'))
        body={'action':'repository_execution','project_id':self.pid,'domain_commit':c['id'],
              'path':'project-fw-s132/project.json','job_id':job['id']}
        result=handle(self.repo,self.fw,body)
        self.assertEqual('FAILED',result['status'])
        self.assertEqual(identity(project),result['consumed_input']['project_sha256'])
        self.assertIn('missing_symbol',result['diagnostics']['process.log']['content'])
        self.assertEqual(16000,len(result['diagnostics']['process.log']['content']))
        first=handle(self.repo,self.fw,{**body,'offset':0,'limit':50})
        self.assertEqual(result['id'],first['id'])
        self.assertEqual(50,len(first['diagnostics']['process.log']['content']))
        self.assertEqual(50,first['diagnostics']['process.log']['next_offset'])
        with self.assertRaisesRegex(ValueError,'DIAGNOSTIC_RANGE_INVALID'):
            handle(self.repo,self.fw,{**body,'limit':999999})
