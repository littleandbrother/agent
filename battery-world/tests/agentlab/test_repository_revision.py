import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from test_repository_execution import ExecutionCase
from test_repository_integration import IntegrationCase, SOURCES
from test_design_repository import OWNER, OTHER
from bfworld.agentlab.design_lab.repository_actions import task, object_save
from bfworld.agentlab.design_lab.repository_contracts import check, declaration_spec, declaration_examples, fingerprint
from bfworld.agentlab.design_lab.repository_execution import consumed_input
from bfworld.agentlab.design_lab.repository_validation import qualification
from bfworld.agentlab.design_lab.repository import file_hash
from bfworld.agentlab.store import canonical, identity


class RevisionCase(IntegrationCase):
    def test_model_visible_generated_examples_are_accepted(self):
        extracted=self.action(OWNER,'extract',system_id=self.base['id'])
        spec=self.action(OWNER,'schema')
        self.assertEqual(declaration_spec(),spec)
        self.assertIn('{interface:',spec['description'])
        self.assertNotIn('{facts:',spec['description'])
        self.assertEqual('PASS',check(lambda p:SOURCES[p],self.base['files'],extracted['examples'])['status'])
        bad=extracted['examples']['firmware'];bad['facts']=bad.pop('interface')
        self.assertEqual('UNEVALUABLE',check(lambda p:SOURCES[p],self.base['files'],{'firmware':bad})['status'])

    def test_peer_read_consumes_frozen_commit_and_retains_parent(self):
        root=self.repo.root/'workspaces/PT-firmware';p='project-fw-s132/main.c'
        changed=SOURCES[p]+'\n// peer actual source'
        self.action(self.fw,'write',operation_id='source',path=p,content=changed,expected_sha256=file_hash(root/p))
        first=self.action(self.fw,'commit',operation_id='one',paths=[p],expected_revision=0,rationale='actual code')
        self.assertEqual(changed,self.action(OTHER,'read',domain_commit=first['id'],path=p)['content'])
        self.action(self.fw,'write',operation_id='interface',path='interfaces/firmware.json',content='{}',expected_sha256=None)
        second=self.action(self.fw,'commit',operation_id='two',paths=['interfaces/firmware.json'],expected_revision=1,rationale='partial declaration')
        self.assertEqual(first['files'][p],second['files'][p])
        self.assertEqual('RECHECK_REQUIRED',second['target_build'])

    def test_rebase_current_system_preserves_old_workspace_and_owner(self):
        old=task(self.repo,OTHER);oldroot=self.repo.root/'workspaces'/old['id']
        oldsession=oldroot/'.pi/repository-sessions/original.jsonl'
        oldsession.parent.mkdir(parents=True);oldsession.write_text('{"type":"session","id":"original-session"}\n')
        (oldroot/'.pi/repository-session-path').write_text(str(oldsession))
        before=oldsession.read_bytes()
        result=self.integrated();newbase=result['system_commit']
        v=self.action(OWNER,'rebase',operation_id='rebase',task_owner=OTHER,base_system=newbase,expected_revision=1,question='new candidate',completion='new evidence')
        self.assertEqual(OTHER,v['owner']);self.assertNotEqual(old['id'],v['id'])
        self.assertEqual(newbase,v['base_system']);self.assertTrue(oldroot.exists())
        newroot=self.repo.root/'workspaces'/v['id']
        copied=Path((newroot/'.pi/repository-session-path').read_text())
        self.assertTrue(copied.is_relative_to(newroot));self.assertEqual(before,copied.read_bytes())
        self.assertEqual(before,oldsession.read_bytes())
        for p,ref in self.repo.system(self.pid,newbase)['files'].items():self.assertEqual(ref['sha256'],file_hash(newroot/p))
        with self.store.connect() as db:self.assertEqual(1,db.execute('SELECT count(*) FROM design_professional_task_history').fetchone()[0])
        self.assertEqual(v,self.action(OWNER,'rebase',operation_id='rebase',task_owner=OTHER,base_system=newbase,expected_revision=1,question='new candidate',completion='new evidence'))

    def test_rebase_refuses_uncommitted_edits(self):
        root=self.repo.root/'workspaces/PT-power';p=root/'project-chain/load-timeline.json';p.write_text('dirty')
        with self.assertRaisesRegex(ValueError,'REBASE_UNCOMMITTED_FILES'):
            self.action(OWNER,'rebase',operation_id='bad-rebase',task_owner=OTHER,base_system=self.base['id'],expected_revision=0,question='new',completion='new')
        self.assertEqual('dirty',p.read_text());self.assertEqual('PT-power',task(self.repo,OTHER)['id'])

    def test_new_qualification_updates_evidence_not_immutable_commit(self):
        s=self.repo.system(self.pid,self.base['id']);before=canonical(s)
        with self.store.connect() as db:
            record=object_save(self.repo,db,'design_repository_validations','RV',{'project_id':self.pid,'target':s['id'],
                'kind':'fixture-independent-gate','status':'PASS','result':{'gates':{'power_load_chain':{
                    'status':'PASS','input_fingerprint':fingerprint(s,'power_load_chain'),'scope':'test only'}}}},['project_id','target','kind'])
        now=qualification(self.repo,s)
        self.assertEqual('PASS',now['gates']['power_load_chain']['status'])
        self.assertEqual(record['id'],now['gates']['power_load_chain']['validation_id'])
        self.assertEqual(before,canonical(self.repo.system(self.pid,s['id'])))
        child={**s,'files':{**s['files'],'project-chain/load-timeline.json':{**s['files']['project-chain/load-timeline.json'],'sha256':'different'}}}
        self.assertNotEqual('PASS',qualification(self.repo,child)['gates']['power_load_chain']['status'])

    def test_unknown_operation_blocks_retry_without_mutation(self):
        body={'action':'repository_write','project_id':self.pid,'operation_id':'unknown','path':'interfaces/power.json','content':'{}','expected_sha256':None}
        request={**body,'repository':True,'task_id':'repository:'+self.pid}
        with self.store.connect() as db:
            db.execute('INSERT INTO design_operations VALUES(?,?,?,?,?,?,?,?,?)',('R-fixture',OTHER,'unknown',identity(request),canonical(request),'UNKNOWN',None,None,0))
        with self.assertRaisesRegex(ValueError,'STATE_UNKNOWN'):self.repo.handle(OTHER,body)
        self.assertFalse((self.repo.root/'workspaces/PT-power/interfaces/power.json').exists())


class ExecutionReuseCase(ExecutionCase):
    def test_partial_commit_reuses_actual_consumed_complete_input(self):
        c=self.prepared()
        from bfworld.agentlab.design_lab.repository_execution import input_project
        project=input_project(self.repo,c,'project-fw-s132/project.json')
        artifacts={}
        with self.store.connect() as db:
            for name,value in [('input.json',{'project':project,'project_sha256':identity(project)}),('result.json',{
                'readback_passed':True,'project_sha256':identity(project),'independent_readback':{'memory_fit':True}})]:
                p=self.root/name;p.write_text(canonical(value));artifacts[name]=self.repo.asset(db,p)
            from bfworld.agentlab import engineering_projects
            old=object_save(self.repo,db,'design_domain_executions','EX',{'project_id':self.pid,'domain_commit':c['id'],
                'owner':self.fw,'job_id':'eng-fixed-test','status':'SUCCEEDED','project_sha256':identity(project),
                'artifacts':artifacts,'executor_sha256':file_hash(engineering_projects.__file__)},['project_id','domain_commit','owner'])
        self.action(self.fw,'write',operation_id='declaration',path='interfaces/firmware.json',content='{}',expected_sha256=None)
        c2=self.action(self.fw,'commit',operation_id='partial',paths=['interfaces/firmware.json'],expected_revision=1,rationale='declaration only')
        self.lab.app.engineering=SimpleNamespace(submit_repository=lambda *a,**k:self.fail('unchanged input dispatched'),dispatch_repository=lambda *a:self.fail('dispatched'))
        value=self.action(self.fw,'execute',operation_id='exact-reuse',domain_commit=c2['id'],path='project-fw-s132/project.json')
        self.assertEqual(c2['id'],value['domain_commit']);self.assertEqual('eng-fixed-test',value['job_id']);self.assertTrue(value['reused'])
        self.assertEqual(c['files']['project-fw-s132/main.c']['sha256'],value['consumed_input']['sources']['main.c'])
        self.assertEqual(old['id'],value['reused_from'])
        wrong={**project,'sources':{'main.c':'stale'}}
        with self.assertRaisesRegex(ValueError,'CONSUMED_SOURCE_CONFLICT'):consumed_input(self.repo,artifacts,wrong)
