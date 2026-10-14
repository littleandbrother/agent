import hashlib
import json
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import patch

from bfworld.agentlab.design_lab.paper_mainline import (
    DeferredCapability, selected_paper, startup_capabilities, process_alive,
    project_snapshot, reusable_job, eda_capability_failure)
from bfworld.agentlab.literature_eda import runtime_alias_project
from scripts import literature_pi_queue
from bfworld.agentlab.recovery import Recovery
from bfworld.agentlab.store import identity


class MainlineRecoveryTests(unittest.TestCase):
    def test_current_client_error_text_retains_read_failure_and_dispatch_fact(self):
        failure = eda_capability_failure(ValueError('NATIVE_DIAGNOSTIC_TIMEOUT: readonly result unavailable'))
        # The current Pi client throws only response.error. The detailed
        # reason must survive that actual consumer contract.
        self.assertIn('NATIVE_DIAGNOSTIC_TIMEOUT', failure['error'])
        self.assertIn('native_write_dispatched=false', failure['error'])
        self.assertEqual(failure['error_code'], 'EDA_CAPABILITY_UNAVAILABLE')
        self.assertFalse(failure['native_write_dispatched'])
        self.assertLess(len(eda_capability_failure(ValueError('x'*10000))['error']), 600)

    def test_unbounded_original_protocol_reads_new_carryforward_without_changing_ledger(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.executescript('CREATE TABLE research_model_owners(owner,protocol);'
                        'CREATE TABLE research_usage_carryforwards(protocol,request_id,original_row_hash,authorization);'
                        'CREATE TABLE model_requests(id,owner,status,reserved,charged,usage);')
        owner='pi-chat-original';db.execute('INSERT INTO research_model_owners VALUES(?,?)',(owner,'old-finite-study'))
        db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?)',('new-unknown',owner,'UNKNOWN',.1015155,0,None))
        row=dict(db.execute('SELECT * FROM model_requests').fetchone());before=list(tuple(r) for r in db.execute('SELECT * FROM model_requests'))
        db.execute('INSERT INTO research_usage_carryforwards VALUES(?,?,?,?)',('old-finite-study',row['id'],identity(row),'direct-user-continuation'))
        recovery=Recovery.__new__(Recovery)
        with patch.object(recovery,'usage_continuation',return_value=None),patch.object(recovery,'resolved',return_value=set()),patch('bfworld.agentlab.budget_policy.unbounded_time',return_value={'unknown_carryforward':{}}):
            self.assertEqual([],recovery.unknown_blockers(db,owner))
            # A different original owner's protocol cannot silently inherit it.
            self.assertEqual([row],recovery.unknown_blockers(db,'pi-chat-foreign'))
            db.execute("UPDATE research_usage_carryforwards SET original_row_hash=?",('0'*64,))
            self.assertEqual([row],recovery.unknown_blockers(db,owner))
        with patch.object(recovery,'usage_continuation',return_value=None),patch.object(recovery,'resolved',return_value=set()),patch('bfworld.agentlab.budget_policy.unbounded_time',return_value=None):
            self.assertEqual([row],recovery.unknown_blockers(db,owner))
        self.assertEqual(before,list(tuple(r) for r in db.execute('SELECT * FROM model_requests')))
        db.close()

    def test_dead_worker_is_observation_not_permission_to_replay(self):
        with patch('os.kill',side_effect=ProcessLookupError):
            self.assertFalse(process_alive(86374))
        with patch('os.kill',side_effect=PermissionError):
            self.assertTrue(process_alive(86374))
        for value in (None, '86374', True, 0, -1):
            self.assertFalse(process_alive(value))

    def test_exact_source_identity_matches_request_and_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/'main.c').write_text('int main(void){return 0;}')
            manifest={'schema_version':'bf-engineering-project-v1','kind':'firmware-nrf52832',
                      'entrypoint':'main.c','files':['main.c'],'interfaces':{'units':'SI'}}
            (root/'project.json').write_text(json.dumps(manifest))
            snapshot=project_snapshot(root,'project.json')
            request={'project_sha256':snapshot['project_sha256'],'input_dimensions':{'physical_hash':'actual'}}
            current={'physical_hash':'actual'}
            self.assertTrue(reusable_job(snapshot,request,'SUCCEEDED',current,True)['execution_reusable'])
            for status,hashes,artifacts in [('UNKNOWN',current,True),('RUNNING',current,True),
                                          ('SUCCEEDED',{'physical_hash':'changed'},True),('SUCCEEDED',current,False)]:
                self.assertFalse(reusable_job(snapshot,request,status,hashes,artifacts)['execution_reusable'])
            (root/'main.c').write_text('int main(void){return 1;}')
            changed=project_snapshot(root,'project.json')
            self.assertFalse(reusable_job(changed,request,'SUCCEEDED',current,True)['execution_reusable'])
            self.assertFalse(reusable_job(snapshot,request,'SUCCEEDED',current,True)['full_product_passed'])
            (root/'main.c').unlink();(root/'main.c').symlink_to(root/'project.json')
            with self.assertRaisesRegex(ValueError,'PROJECT_PATH_DENIED'):project_snapshot(root,'project.json')

    def test_bound_eda_not_prerequisite_for_other_work(self):
        for phase in ('firmware', 'engineering-review', 'engineering-repair', 'delivery'):
            self.assertNotIn('eda', startup_capabilities(phase))
        self.assertEqual({'eda'}, startup_capabilities('eda'))

    def test_explicit_requirements_validate_without_removing_eda_phase_gate(self):
        policy={'schema_version':'bf-phase-capability-policy-v1','required_at_start':['spice']}
        self.assertEqual({'spice'},startup_capabilities('engineering-review',{'capability_policy':policy}))
        self.assertEqual({'spice','eda'},startup_capabilities('eda',{'capability_policy':policy}))
        for bad in (None, ['eda'], {'schema_version':'v0'},
                    {**policy,'required_at_start':['eda','eda']},
                    {**policy,'required_at_start':['unknown']},
                    {**policy,'required_at_start':[{}]}):
            if bad is None: continue
            with self.assertRaises(ValueError):startup_capabilities('firmware',{'capability_policy':bad})

    def test_help_skill_and_unknown_job_observation_do_not_open_application(self):
        calls=[]
        def unavailable():
            calls.append(1)
            raise ValueError('EDA_NO_CONNECTED_WINDOW')
        capability=DeferredCapability(unavailable)
        for body in ({'action':'skill'}, {'action':'job','job_id':'unknown-original-write'},
                     {'action':'command','argv':['sch','--help']},
                     {'action':'command','argv':['spec','schema']}):
            self.assertIsNone(capability.for_eda_request(body))
        self.assertEqual([],calls)
        with self.assertRaisesRegex(ValueError,'EDA_NO_CONNECTED_WINDOW'):
            capability.for_eda_request({'action':'command','argv':['sch','list']})
        self.assertEqual([1],calls)
        # Failure of this dependency does not prevent offline work afterwards.
        capability.for_eda_request({'action':'command','argv':['sch','--help']})
        self.assertEqual([1],calls)

    def test_actual_use_resolves_once_without_replaying_any_operation(self):
        calls=[]; receipt={'owner':'original','project_uuid':'exact'}
        capability=DeferredCapability(lambda:(calls.append('resolve'),receipt)[1])
        for body in ({'action':'inspect'}, {'action':'command','argv':['sch','list']},
                     {'action':'job','job_id':'previous-success'}):
            self.assertEqual(receipt,capability.for_eda_request(body))
        self.assertEqual(['resolve'],calls)

    def test_alias_requires_exact_operator_proof_not_matching_project_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();local=root/'projects/P01.eprj3';local.parent.mkdir();local.write_text('{"name":"BF-Literature-P01-Native-test"}')
            record={'project_uuid':'created-project-01','owner':'original','local_project':str(local)}
            record_path=root/'campaign/eda/P01/binding.json';record_path.parent.mkdir(parents=True);record_path.write_text(json.dumps(record))
            digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            alias_path=record_path.parent/('runtime-file-binding-'+digest(record_path)[:20]+'-runtime-project-01.json')
            alias={'schema_version':'bf-paper-eda-file-alias-v1','actor':'Codex environment preparation',
                'owner':'original','paper_id':'P01','binding_record_sha256':digest(record_path),
                'created_project_uuid':record['project_uuid'],'runtime_project_uuid':'runtime-project-01',
                'local_project':str(local),'design_restore_claimed':False}
            alias_path.write_text(json.dumps(alias));prior={'project':'runtime-project-01','owner':'original','writable':1,'proof':digest(alias_path)}
            with patch('bfworld.agentlab.runtime_config.configured',return_value=local.parent):
                self.assertEqual('runtime-project-01',runtime_alias_project(root,'P01',record,{'name':'BF-Literature-P01-Native-test'},prior))
                for change in ({'owner':'foreign'},{'proof':'0'*64},{'writable':0}):
                    with self.assertRaisesRegex(ValueError,'PAPER_EDA_RUNTIME_ALIAS_INVALID'):
                        runtime_alias_project(root,'P01',record,{'name':'BF-Literature-P01-Native-test'},{**prior,**change})
                alias['local_project']=str(root/'wrong.eprj3');alias_path.write_text(json.dumps(alias))
                with self.assertRaisesRegex(ValueError,'PAPER_EDA_RUNTIME_ALIAS_INVALID'):
                    runtime_alias_project(root,'P01',record,{'name':'BF-Literature-P01-Native-test'},{**prior,'proof':digest(alias_path)})

    def test_selected_worker_never_mutates_an_unselected_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);queue=root/'campaign/parallel-20261009/pi-queue';queue.mkdir(parents=True)
            qual=root/'campaign/native-qualification.json';qual.write_text('{}')
            ready=queue.parent/'READY.json';ready.write_text(json.dumps({'status':'PASS','qualification_sha256':literature_pi_queue.digest(qual)}))
            owner='pi-chat-preserved-other';path=queue/(owner+'.json')
            # Deliberately wrong authority: the selector must precede rejection.
            item={'schema_version':'bf-paper-continuation-queue-v1','paper':'P02','owner':owner,'status':'QUEUED','authorization_sha256':'old'}
            path.write_text(json.dumps(item));before=path.read_bytes()
            authority={'owners':[{'owner':owner,'paper_id':'P02'}],'authority_sha256':'new'}
            with patch('sys.argv',['worker','--root',str(root),'--paper','P01']), patch.object(literature_pi_queue,'load_authority',return_value=authority), patch.object(literature_pi_queue.subprocess,'Popen') as proc:
                literature_pi_queue.main()
            self.assertEqual(before,path.read_bytes());proc.assert_not_called()
            self.assertEqual('DRAINED',json.loads((queue/'worker.json').read_text())['status'])
            self.assertFalse(selected_paper(item,{'P01'}))


if __name__=='__main__':unittest.main()
