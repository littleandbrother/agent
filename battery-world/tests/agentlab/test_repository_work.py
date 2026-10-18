import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_design_repository as fixtures
from test_design_repository import OWNER, OTHER
from test_repository_feedback import RAW, FILES
from test_repository_task_profiles import curve_definition
from bfworld.agentlab.design_lab import repository_feedback_node as execution
from bfworld.agentlab.design_lab.repository_work import document
from bfworld.agentlab.design_lab.repository_controller import ingest


class ScopedWorkTests(unittest.TestCase):
    def setUp(self):
        fixtures.RepositoryCase.setUp(self)
        self.made=self.repo.handle(OWNER,{'action':'repository_task_create','operation_id':'create',
            'definition':RAW,'files':FILES},True)
        self.pid=self.made['project_id'];self.sid=self.made['id']
        self.serial=0
        def create(*args,**kwargs):
            self.serial+=1; cid=OTHER if self.serial==1 else 'pi-chat-d1234567890abcde'
            with self.store.connect() as db: db.execute('INSERT OR IGNORE INTO conversations VALUES(?)',(cid,))
            return {'id':cid}
        self.lab.app.conversations=SimpleNamespace(create=create)

    def act(self,action,op='action',owner=OWNER,operator=False,**kw):
        return self.repo.handle(owner,{'action':'repository_'+action,'operation_id':op,**kw},operator)

    def configure(self,arm='temporary',kind='design'):
        return self.act('work_configure','cfg',operator=True,policy={'organization':arm,'kind':kind,
            'protocol_sha256':'0'*64,'limits':{'candidate_evaluations_per_trial':1,'requests_per_trial':12}})

    def assign(self,kind='source',op='assign'):
        return self.act('work_assign',op,kind=kind,base_system=self.sid,
            question='Check source conditions',completion='Return sourced facts',rationale='Need the exact current envelope')

    def result(self,files=None):
        text,digest=document(self.repo,self.pid,self.sid,'task-definition.json')
        return {'completed_scope':'Checked current envelope','files':files or {},'facts':[{'field':'tx_a','value':.008,
            'unit':'A','conditions':'nominal model','sources':[{'path':'task-definition.json','sha256':digest,
                'locator':'/scenario/current_model/values_a/tx'}]}],
            'judgment':'Value is a declared current model','assumptions':[],'issues':[]}

    def test_frozen_policy_and_no_worker_in_single(self):
        self.configure('single')
        with self.assertRaisesRegex(PermissionError,'NOT_ALLOWED'):self.assign()
        with self.assertRaisesRegex(ValueError,'ALREADY_FROZEN'):self.act('work_configure','cfg2',operator=True,
            policy={'organization':'joint','kind':'design','protocol_sha256':'0'*64,
                'limits':{'candidate_evaluations_per_trial':1,'requests_per_trial':12}})
        with self.assertRaisesRegex(PermissionError,'OPERATOR_ONLY'):self.act('work_configure','cfg3',policy={})

    def test_one_depth_read_only_base_and_source_hash(self):
        self.configure();t=self.assign();self.assertEqual(self.pid,self.repo.bound(t['owner']))
        for action in ('task_commit','task_define','work_assign','decide','task_execute','task_assess'):
            with self.subTest(action=action),self.assertRaisesRegex(PermissionError,'ACTION_DENIED'):
                self.act(action,owner=t['owner'])
        with self.assertRaisesRegex(PermissionError,'BASE_CONFLICT'):
            self.act('work_read',owner=t['owner'],path='design.json',system_id='SC-wrong')
        got=self.act('work_read',owner=t['owner'],path='design.json')
        self.assertEqual(FILES['design.json'],got['content'])
        bad=self.result();bad['facts'][0]['sources'][0]['sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'HASH_CONFLICT'):
            self.act('work_submit','bad',owner=t['owner'],content=bad)
        good=self.act('work_submit','good',owner=t['owner'],content=self.result())
        self.assertEqual('source',good['kind']);self.assertEqual(self.sid,self.repo.project(self.pid)['submitted'])
        self.assertEqual(good,self.act('work_submit','good',owner=t['owner'],content=self.result()))
        with self.assertRaisesRegex(ValueError,'ALREADY_SUBMITTED'):
            self.act('work_submit','again',owner=t['owner'],content=self.result())

    def test_source_cannot_submit_engineering_patch(self):
        self.configure();t=self.assign()
        with self.assertRaisesRegex(PermissionError,'READ_ONLY'):
            self.act('work_submit',owner=t['owner'],content=self.result({'design.json':FILES['design.json']}))

    def test_source_pair_requires_parent_to_wait_for_worker(self):
        self.configure('temporary','source')
        with self.assertRaisesRegex(ValueError,'NOT_SUBMITTED'):
            self.act('work_answer',content=self.result())
        t=self.assign();self.act('work_submit','child',owner=t['owner'],content=self.result())
        answer=self.act('work_answer','answer',content=self.result())
        self.assertIsNone(answer['task_id'])
        with self.assertRaisesRegex(ValueError,'EXHAUSTED'):self.assign('source','extra')

    def test_shared_request_guard_counts_lead_and_worker(self):
        self.configure();t=self.assign()
        with self.store.connect() as db:
            db.execute('CREATE TABLE model_requests(id TEXT,owner TEXT)')
            db.executemany('INSERT INTO model_requests VALUES(?,?)',[(str(i),OWNER if i<6 else t['owner']) for i in range(12)])
        for owner in (OWNER,t['owner']):
            with self.assertRaisesRegex(ValueError,'MODEL_LIST_EXHAUSTED'):
                self.act('work_request_guard',owner=owner)

    def test_fixed_scopes_submit_then_three_way_merge(self):
        self.configure('fixed');power=self.assign('power');firmware=self.assign('firmware','f')
        with self.assertRaisesRegex(ValueError,'NOT_SUBMITTED'):
            self.act('decide',system_id=self.sid)
        design=json.loads(FILES['design.json']);design['output_f']*=2
        pr=self.act('work_submit','p',owner=power['owner'],content=self.result({'design.json':json.dumps(design)}))
        source=FILES['firmware/main.c'].replace('t+4.0','t+3.0')
        fr=self.act('work_submit','f',owner=firmware['owner'],content=self.result({'firmware/main.c':source}))
        p=self.act('work_apply','apply-p',result_id=pr['id'],base_system=self.sid,expected_revision=1,rationale='Use power proposal')
        f=self.act('work_apply','apply-f',result_id=fr['id'],base_system=p['id'],expected_revision=2,rationale='Use program proposal')
        final=self.repo.system(self.pid,f['id'])
        self.assertEqual(design,json.loads((self.repo.root/'blobs'/final['files']['design.json']['sha256']).read_text()))
        self.assertEqual(source,(self.repo.root/'blobs'/final['files']['firmware/main.c']['sha256']).read_text())
        self.assertIn(pr['id'],self.repo.system(self.pid,p['id'])['rationale'])

    def test_stale_overlapping_proposal_is_rejected(self):
        self.configure('joint');t=self.assign('joint');design=json.loads(FILES['design.json']);design['output_f']*=2
        result=self.act('work_submit',owner=t['owner'],content=self.result({'design.json':json.dumps(design)}))
        design['output_f']*=2
        changed=self.act('task_commit','other',base_system=self.sid,expected_revision=1,
            files={'design.json':json.dumps(design)},rationale='Another design change')
        with self.assertRaisesRegex(ValueError,'REBASE_REQUIRED'):
            self.act('work_apply',result_id=result['id'],base_system=changed['id'],expected_revision=2,rationale='Stale overwrite')

    def test_solver_releases_database_writer_and_recovery_reuses(self):
        self.configure('single')
        def run(*args):
            with self.store.connect() as db:
                db.execute("INSERT INTO settings VALUES('trace-witness','write-during-solver')")
            return {'test_only':True},{'witness.json':'{}'}
        with patch.object(execution,'environment',return_value={'test_only':True}),patch.object(execution,'run',side_effect=run) as native:
            first=self.act('task_execute','run',operator=True,system_id=self.sid)
            again=self.act('task_execute','reuse',operator=True,system_id=self.sid)
        self.assertEqual(1,native.call_count);self.assertEqual(first['id'],again['id']);self.assertTrue(again['reused'])

    def test_trace_lock_defers_without_aborting_but_tamper_fails(self):
        import sqlite3
        self.lab.app.conversations.ingest=lambda *a,**kw: (_ for _ in ()).throw(sqlite3.OperationalError('database is locked'))
        receipt={};ingest(self.repo,OWNER,receipt);self.assertEqual(1,receipt['trace_lock_deferrals'])
        self.lab.app.conversations.ingest=lambda *a,**kw: (_ for _ in ()).throw(ValueError('TRACE_HISTORY_CHANGED'))
        with self.assertRaisesRegex(ValueError,'TRACE_HISTORY_CHANGED'):ingest(self.repo,OWNER,receipt)


if __name__=='__main__':unittest.main()
