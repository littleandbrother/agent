import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from bfworld.agentlab.store import Store,identity,canonical
from bfworld.agentlab.design_lab import contracts,case_c
from bfworld.agentlab.design_lab.service import DesignLab
from bfworld.agentlab.design_lab.resources import load

OWNER='pi-chat-1234567890abcdef'
OTHER='pi-chat-fedcba0987654321'


class Contracts(unittest.TestCase):
    def setUp(self):
        self.task=contracts.contract('E-fixed','V-fixed')
        self.design=contracts.snapshot(self.task,{'program.c':'void bf_reset(void){}'})
        self.check={'task_id':self.task['task_id'],'scope':self.task['scope'],'design_id':self.design['design_id'],
                    'environment_id':'E-fixed','validation_id':'V-fixed','gates':dict.fromkeys(contracts.GATES,'PASS'),'check_id':'trusted'}

    def test_real_positive_scope_does_not_grant_full_or_physical(self):
        a=contracts.acceptance(self.task,self.design['design_id'],self.check,self.design['design_id'])
        self.assertTrue(a['scoped_passed']);self.assertFalse(a['full_product_passed'])
        self.assertEqual({'NOT_CHECKED'},set(a['physical'].values()))

    def test_each_missing_gate_is_rejected(self):
        for name in contracts.GATES:
            c=copy.deepcopy(self.check);c['gates'].pop(name)
            with self.subTest(gate=name),self.assertRaisesRegex(ValueError,'GATE_SET'):contracts.acceptance(self.task,self.design['design_id'],c,self.design['design_id'])

    def test_scoped_fail_and_unevaluable_are_distinct(self):
        for value in ('FAIL','UNEVALUABLE'):
            c=copy.deepcopy(self.check);c['gates']['power_fixed_point']=value
            a=contracts.acceptance(self.task,self.design['design_id'],c,self.design['design_id'])
            self.assertFalse(a['scoped_passed']);self.assertEqual(value,a['scoped_status'])

    def test_stale_success_is_not_accepted(self):
        a=contracts.acceptance(self.task,self.design['design_id'],self.check,'D-new')
        self.assertEqual('STALE',a['scoped_status']);self.assertFalse(a['scoped_passed'])

    def test_wrong_identity_scope_environment_or_evaluator_rejected(self):
        for key in ('task_id','scope','environment_id','validation_id','design_id'):
            c=copy.deepcopy(self.check);c[key]='wrong'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'BINDING'):contracts.acceptance(self.task,self.design['design_id'],c,self.design['design_id'])

    def test_source_change_has_new_D_and_old_physical_dimension(self):
        d=contracts.snapshot(self.task,{'program.c':'void bf_reset(void){return;}'},self.design['design_id'])
        self.assertNotEqual(d['design_id'],self.design['design_id'])
        self.assertEqual(d['dimensions']['physical'],self.design['dimensions']['physical'])

    def test_result_or_self_pass_cannot_be_in_snapshot(self):
        d=copy.deepcopy(self.design);d['passed']=True
        with self.assertRaisesRegex(ValueError,'TAMPER'):contracts.check_snapshot(self.task,d)

    def test_source_path_size_and_type_rejected(self):
        for sources in ({'program.c':'x','../test.c':'x'},{'program.c':1},{'program.c':'x'*128001},{'not.c':'x'}):
            with self.subTest(sources=list(sources)),self.assertRaises(ValueError):contracts.snapshot(self.task,sources)

    def test_wrong_skill_id_no_default_fallback(self):
        with self.assertRaisesRegex(ValueError,'SKILL_NOT_FOUND'):load('easyeda-wrong')
        self.assertEqual('bf-design-task-control-v1',load('bf-design-task-control-v1')['skill_id'])

    def test_independent_decoder_width_endian_and_checksum(self):
        frame=bytearray(b'BFMC'+bytes([1,1])+int(4294967239).to_bytes(4,'little')+bytes([0,0]))
        for x in frame[:11]:frame[11]^=x
        self.assertEqual({'event_id':4294967239,'kind':1},case_c.decode(frame.hex()))
        for index in range(12):
            wrong=bytearray(frame);wrong[index]^=1
            with self.subTest(index=index):self.assertIsNone(case_c.decode(wrong.hex()))


class DurableTask(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'state')
        with self.store.connect() as db:
            db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY)')
            db.executemany('INSERT INTO conversations VALUES(?)',[(OWNER,),(OTHER,)])
        self.app=SimpleNamespace(store=self.store,engineering=SimpleNamespace(lock=threading.Lock()))
        self.lab=DesignLab(self.app,start_worker=False)
        self.env={'root':self.tmp.name,'environment_id':'E-fixed'}
        with patch('bfworld.agentlab.design_lab.baseline.environment',return_value=self.env):
            self.lab.configure(OWNER,self.env,{'program.c':'initial'})
            self.lab.configure(OTHER,self.env,{'program.c':'other'})
        self.initial=self.lab.view(OWNER)['current_design']

    def test_foreign_owner_cannot_read_design_or_operation(self):
        with self.assertRaisesRegex(PermissionError,'NOT_OWNED'):self.lab.design(OTHER,self.initial)
        job=self.lab.run(OWNER,'build-1',self.initial)
        with self.assertRaisesRegex(PermissionError,'NOT_OWNED'):self.lab.operation(OTHER,job['id'])

    def test_same_operation_retry_and_new_name_pending_return_same_job(self):
        a=self.lab.run(OWNER,'first',self.initial)
        b=self.lab.run(OWNER,'first',self.initial)
        c=self.lab.run(OWNER,'new-name',self.initial)
        self.assertEqual(a['id'],b['id']);self.assertEqual(a['id'],c['id'])

    def test_operation_id_conflict_rejected(self):
        self.lab.run(OWNER,'first',self.initial)
        d=self.lab.freeze(OWNER,{'program.c':'changed'},self.initial)
        with self.assertRaisesRegex(ValueError,'CONFLICT'):self.lab.run(OWNER,'first',d['design_id'])

    def test_unknown_interruption_never_automatically_dispatches(self):
        a=self.lab.run(OWNER,'first',self.initial)
        with self.store.connect() as db:db.execute("UPDATE design_operations SET status='RUNNING' WHERE id=?",(a['id'],))
        restarted=DesignLab(self.app,start_worker=False)
        old=restarted.operation(OWNER,a['id']);self.assertEqual('UNKNOWN',old['status'])
        repeat=restarted.run(OWNER,'renamed-after-crash',self.initial)
        self.assertEqual(a['id'],repeat['id']);self.assertEqual('UNKNOWN',repeat['status'])

    def test_queued_job_survives_restart_without_new_id(self):
        a=self.lab.run(OWNER,'first',self.initial)
        restarted=DesignLab(self.app,start_worker=False)
        self.assertEqual(a['id'],restarted.run(OWNER,'first',self.initial)['id'])

    def test_CAS_rejects_stale_second_adoption(self):
        a=self.lab.freeze(OWNER,{'program.c':'one'},self.initial)
        b=self.lab.freeze(OWNER,{'program.c':'two'},self.initial)
        self.lab.adopt(OWNER,a['design_id'],1,'actual first choice')
        with self.assertRaisesRegex(ValueError,'STALE'):self.lab.adopt(OWNER,b['design_id'],1,'stale second choice')
        self.assertEqual(a['design_id'],self.lab.view(OWNER)['current_design'])

    def test_success_does_not_automatically_adopt_latest_design(self):
        d=self.lab.freeze(OWNER,{'program.c':'new'},self.initial)
        job=self.lab.run(OWNER,'run-new',d['design_id'])
        with self.store.connect() as db:db.execute("UPDATE design_operations SET status='SUCCEEDED' WHERE id=?",(job['id'],))
        self.assertEqual(self.initial,self.lab.view(OWNER)['current_design'])

    def test_wait_requires_real_pending_job(self):
        with self.assertRaises(PermissionError):self.lab.set_intent(OWNER,'WAIT','absent')
        job=self.lab.run(OWNER,'run',self.initial)
        self.lab.set_intent(OWNER,'WAIT',job['id'],['inspect operation on completion'])
        self.assertEqual(job['id'],self.lab.view(OWNER)['intent']['job_id'])

    def test_plan_and_intent_restore_on_restart(self):
        self.lab.set_intent(OWNER,'CONTINUE',plan=['Read actual payload','Compare event and power scope'])
        restarted=DesignLab(self.app,start_worker=False)
        self.assertEqual(['Read actual payload','Compare event and power scope'],restarted.view(OWNER)['plan'])

    def test_duplicate_ack_and_wrong_sequence_rejected(self):
        events=self.lab.events(OWNER);cursor=events['next_cursor']
        self.lab.acknowledge(OWNER,cursor);self.lab.acknowledge(OWNER,cursor)
        with self.assertRaisesRegex(ValueError,'CURSOR'):self.lab.acknowledge(OWNER,cursor+999)
        self.assertEqual([],self.lab.events(OWNER,cursor)['events'])

    def test_tampered_frozen_file_rejected(self):
        path=self.lab.root/OWNER/'designs'/self.initial/'snapshot.json'
        value=json.loads(path.read_text());value['sources']['program.c']='tampered';path.write_text(canonical(value))
        with self.assertRaisesRegex(ValueError,'TAMPER'):self.lab.design(OWNER,self.initial)

    def test_participant_cannot_supply_check_or_configure(self):
        with self.assertRaises(PermissionError):self.lab.handle(OWNER,{'action':'configure','actor':'operator'},False)
        with self.assertRaisesRegex(ValueError,'ACTION_INVALID'):self.lab.handle(OWNER,{'action':'check_receipt','issuer':'trusted-design-service','passed':True},False)

    def test_check_needs_actual_completed_operation(self):
        job=self.lab.run(OWNER,'run',self.initial)
        with self.assertRaisesRegex(ValueError,'SUCCESSFUL_EXECUTION'):self.lab.inspect_check(OWNER,job['id'])

    def test_operator_action_is_recorded_as_external_intervention(self):
        self.lab.handle(OWNER,{'action':'intent','kind':'CONTINUE'},True)
        self.assertIn('external_intervention',[v['kind'] for v in self.lab.events(OWNER)['events']])

    def test_new_C_authority_binds_grant_without_overwriting_original(self):
        from bfworld.agentlab import budget_policy
        from bfworld.agentlab.provider import Provider
        Provider(self.store)
        with self.store.connect() as db:
            original=dict(db.execute("SELECT * FROM grants WHERE owner='operator'").fetchone())
        self.lab.handle(OWNER,{'action':'authorize','wall_authorization_text':'持续运行 不设置时间限制'},True)
        with self.store.connect() as db:
            grant=dict(db.execute('SELECT * FROM grants WHERE owner=?',(OWNER,)).fetchone())
            self.assertEqual([self.lab.task(OWNER)['task_id']],json.loads(grant['task_ids']))
            self.assertIsNotNone(budget_policy.unbounded_time(db,OWNER))
            self.assertEqual(original,dict(db.execute("SELECT * FROM grants WHERE owner='operator'").fetchone()))

    def test_required_arguments_report_exact_field_without_side_effect(self):
        before=len(self.lab.events(OWNER)['events'])
        for action,field in [('observe','job_id'),('freeze','parent'),('submit','rationale')]:
            with self.subTest(action=action),self.assertRaisesRegex(ValueError,'ARGUMENTS_REQUIRED.*'+field):
                self.lab.handle(OWNER,{'action':action},False)
        self.assertEqual(before,len(self.lab.events(OWNER)['events']))


class WorkerLifecycle(unittest.TestCase):
    def test_shutdown_wake_does_not_reopen_store(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'state')
            lab=DesignLab(SimpleNamespace(store=store),start_worker=False)
            lab.closing.set();lab.wake.set()
            with patch.object(store,'connect',side_effect=AssertionError('Store reopened during teardown')):
                lab.worker()

    def test_removed_temporary_store_stops_without_thread_exception_or_recreation(self):
        directory=tempfile.TemporaryDirectory()
        store=Store(Path(directory.name)/'state')
        lab=DesignLab(SimpleNamespace(store=store),start_worker=False)
        directory.cleanup();lab.wake.set()
        errors=[]
        with patch('threading.excepthook',side_effect=lambda args:errors.append(args.exc_value)):
            worker=threading.Thread(target=lab.worker)
            worker.start();worker.join(timeout=2)
        self.assertFalse(worker.is_alive());self.assertEqual([],errors)
        self.assertFalse(store.db.exists())


if __name__=='__main__':unittest.main()

