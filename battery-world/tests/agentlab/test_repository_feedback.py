import copy
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import test_design_repository as fixtures
from test_design_repository import OWNER
from bfworld.agentlab.store import canonical
from bfworld.agentlab.design_lab.contracts import sealed
from bfworld.agentlab.design_lab.repository import file_hash
from bfworld.agentlab.design_lab.repository_profiles import definition,runtime_spec
from bfworld.agentlab.design_lab.repository_contracts import fingerprint
from bfworld.agentlab.design_lab.repository_task_execution import descriptor,verify
from bfworld.agentlab.design_lab import repository_feedback_node as execution
from bfworld.agentlab.design_lab import repository_feedback_contract as contract
from bfworld.agentlab.design_lab import feedback_native,feedback_program
from bfworld.agentlab.design_lab.repository_feedback_validation import interval_min,protocol

FIXTURE=Path(__file__).resolve().parents[2]/'configs/reference_cases/piezo-feedback'
RAW=json.loads((FIXTURE/'task.json').read_text())
FILES={'design.json':(FIXTURE/'design.json').read_text(),'firmware/main.c':(FIXTURE/'main.c').read_text()}


class FeedbackRepositoryTests(unittest.TestCase):
    setUp=fixtures.RepositoryCase.setUp

    def create(self):
        return self.repo.handle(OWNER,{'action':'repository_task_create','operation_id':'feedback-create',
            'definition':RAW,'files':FILES},True)

    def action(self,name,op,operator=False,**body):
        return self.repo.handle(OWNER,{'action':'repository_'+name,'operation_id':op,**body},operator)

    def test_contract_and_tool_example_are_executable(self):
        task=definition(RAW); spec=runtime_spec(task)
        self.assertEqual(contract.HEADER,spec['program']['header'])
        self.assertEqual(contract.GATES,task['required_gates'])
        self.assertEqual([],spec['profile']['roles'])
        self.assertTrue(all(i['consumer'] and i['executor'] and i['checker'] for i in task['interfaces']))

    def test_missing_current_provenance_or_unknown_condition_rejected(self):
        for edit in ('provenance','unknown','unit','range'):
            raw=copy.deepcopy(RAW)
            if edit=='provenance': raw['scenario']['current_model']['source']={}
            elif edit=='unknown': raw['scenario']['automatic_unmodelled_source']=1
            elif edit=='unit': raw['parameters'][0]['unit']='ms'
            else: raw['scenario']['start_v']=1
            with self.subTest(edit=edit),self.assertRaises(ValueError): definition(raw)

    def test_requirements_reuse_execution_but_invalidate_judgment(self):
        made=self.create(); old=self.repo.system(made['project_id'],made['id'])
        raw=copy.deepcopy(RAW);raw['scenario']['sample_validity_s']=.001
        changed=self.action('task_define','expiry',True,expected_revision=1,definition=raw)
        new=self.repo.system(made['project_id'],changed['id'])
        self.assertEqual(descriptor(old),descriptor(new))
        self.assertNotEqual(fingerprint(old,'receiver_service'),fingerprint(new,'receiver_service'))
        self.assertNotEqual(protocol(old)['id'],protocol(new)['id'])

    def test_initial_state_is_execution_input(self):
        made=self.create(); old=self.repo.system(made['project_id'],made['id'])
        raw=copy.deepcopy(RAW);raw['scenario']['initial_storage_v']=0;raw['parameters'][1]['value']=0
        changed=self.action('task_define','cold',True,expected_revision=1,definition=raw)
        self.assertNotEqual(descriptor(old),descriptor(self.repo.system(made['project_id'],changed['id'])))

    def test_full_parent_tree_reaches_executor_after_partial_commits(self):
        made=self.create()
        source=FILES['firmware/main.c'].replace('t+4.0','t+3.0')
        first=self.action('task_commit','code',base_system=made['id'],expected_revision=1,
            files={'firmware/main.c':source},rationale='change interval')
        second=self.action('task_commit','notes',base_system=first['id'],expected_revision=2,
            files={'notes/decision.md':'Retain new controller.'},rationale='explain decision')
        with patch.object(execution,'run',return_value=({'test_only':True},{'witness.json':'{}'})) as run:
            result=self.action('task_execute','run',True,system_id=second['id'])
        self.assertEqual('SUCCEEDED',result['status'])
        consumed=run.call_args.args[2]
        self.assertEqual(source,consumed['firmware/main.c'])
        self.assertEqual(FILES['design.json'],consumed['design.json'])
        self.assertEqual('Retain new controller.',self.action('read','read',system_id=second['id'],path='notes/decision.md')['content'])

    def test_unqualified_agent_cannot_dispatch(self):
        made=self.create()
        with patch.object(execution,'run') as run,self.assertRaisesRegex(ValueError,'REFERENCE_QUALIFICATION_REQUIRED'):
            self.action('task_execute','agent-run',system_id=made['id'])
        run.assert_not_called()

    def test_stale_checker_and_changed_qualification_are_rejected(self):
        from bfworld.agentlab.store import identity
        from bfworld.agentlab.design_lab.repository_feedback_qualification import require,CONTROLS
        from bfworld.agentlab.design_lab.repository_task_checks import evaluator_identity
        made=self.create();system=self.repo.system(made['project_id'],made['id'])
        folder=self.repo.root/'feedback-qualification';folder.mkdir()
        proof=folder/'qualification.json';pointer=folder/'current.json'
        value={'status':'PASS','controls':{k:True for k in CONTROLS},'environment':{'test_only':True},
            'checker':{'old-checker':True},'evidence':{},'protocol':'test-only'}
        value={'id':'FQ-'+identity(value),**value};proof.write_text(canonical(value))
        pointer.write_text(canonical({'path':str(proof),'sha256':file_hash(proof)}))
        with patch.object(execution,'environment',return_value={'test_only':True}):
            with self.assertRaisesRegex(ValueError,'REQUALIFY'):require(self.repo,system)
            value.pop('id');value['checker']=evaluator_identity(system);value={'id':'FQ-'+identity(value),**value}
            proof.write_text(canonical(value));pointer.write_text(canonical({'path':str(proof),'sha256':file_hash(proof)}))
            self.assertEqual(value['id'],require(self.repo,system)['qualification_id'])
            proof.write_text(proof.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'QUALIFICATION_CHANGED'):require(self.repo,system)

    def test_agent_cannot_edit_frozen_protocol(self):
        made=self.create()
        with self.assertRaisesRegex(PermissionError,'OPERATOR_ONLY'):
            self.action('task_define','relax',definition=RAW,expected_revision=1)
        with self.assertRaisesRegex(PermissionError,'DESIGN_SCOPE'):
            self.action('task_commit','checker',base_system=made['id'],expected_revision=1,
                files={'validation.py':'pass'},rationale='bypass check')

    def test_unknown_dispatch(self):
        made=self.create();system=self.repo.system(made['project_id'],made['id'])
        root=self.repo.root/'task-executions'/made['project_id']/descriptor(system)['id']
        root.mkdir(parents=True);sealed(root/'dispatch.json',{'descriptor':descriptor(system)})
        with patch.object(execution,'run') as run:
            for op in ('retry-a','retry-b'):
                with self.assertRaisesRegex(ValueError,'UNKNOWN_RECONCILE'):
                    self.action('task_execute',op,True,system_id=made['id'])
        run.assert_not_called()

    def test_timeout_remains_unknown_and_retry_cannot_dispatch(self):
        made=self.create()
        with patch.object(execution,'run',side_effect=subprocess.TimeoutExpired('native',1)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):self.action('task_execute','first',True,system_id=made['id'])
            with self.assertRaisesRegex(ValueError,'UNKNOWN_RECONCILE'):self.action('task_execute','second',True,system_id=made['id'])
        self.assertEqual(1,run.call_count)

    def test_completed_orphan_recovers_without_execution(self):
        made=self.create();system=self.repo.system(made['project_id'],made['id']);desc=descriptor(system)
        root=self.repo.root/'task-executions'/made['project_id']/desc['id'];root.mkdir(parents=True)
        (root/'witness.json').write_text('{"completed":true}')
        sealed(root/'dispatch.json',{'descriptor':desc})
        sealed(root/'completed.json',{'descriptor':desc,'status':'SUCCEEDED','metrics':{'recovered':True},
            'outputs':{'witness.json':{'sha256':file_hash(root/'witness.json')}}})
        with patch.object(execution,'run') as run:
            recovered=self.action('task_execute','recover',True,system_id=made['id'])
            second=self.action('task_execute','recover-again',True,system_id=made['id'])
        run.assert_not_called();self.assertEqual(recovered['id'],second['id']);self.assertTrue(second['reused'])

    def test_raw_binding(self):
        made=self.create()
        with patch.object(execution,'run',return_value=({}, {'coarse/system.raw.zlib':b'raw'})):
            result=self.action('task_execute','run',True,system_id=made['id'])
        artifact=self.repo.root/'blobs'/result['artifacts']['coarse/system.raw.zlib']['sha256']
        artifact.chmod(0o600);artifact.write_bytes(b'foreign-waveform')
        with self.assertRaisesRegex(ValueError,'ARTIFACT_CHANGED'):verify(self.repo,{k:v for k,v in result.items() if k!='reused'})

    def test_parser_failure_is_retained_and_not_repeated(self):
        from bfworld.agentlab.simulation_chain.contracts import ChainError
        made=self.create()
        with patch.object(execution,'run',side_effect=ChainError('solver_error','TRUNCATED_NATIVE_RAW')) as run:
            first=self.action('task_execute','bad-raw',True,system_id=made['id'])
            second=self.action('task_execute','bad-raw-repeat',True,system_id=made['id'])
        self.assertEqual('FAILED',first['status']);self.assertEqual(first['id'],second['id']);self.assertEqual(1,run.call_count)


class FeedbackExecutionTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'darwin', 'macOS sandbox integration; portable C supervisor covered separately')
    def test_program_cannot_claim_unpowered_leakage_while_powered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=FILES['firmware/main.c']+'\n'
            source=source.replace('int bf_step(', 'int reference_step(')
            source+='int bf_step(double t, double dt, double v, int pg) { (void)t; (void)dt; (void)v; (void)pg; return BF_OFF; }\n'
            binary=feedback_program.compile_program(root,source,feedback_native.tools())
            grid=np.array([0.,.001,.002]);v=np.full(len(grid),2.5)
            with self.assertRaisesRegex(ValueError,'FEEDBACK_PROGRAM_EXIT'):
                feedback_program.execute_program(root/'application',binary,RAW['scenario'],grid,v,v)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS sandbox integration; portable C supervisor covered separately')
    def test_brownout(self):
        # Actual compiled reference code: power loss interrupts TX, resets the
        # volatile sequence and delays the next sample until the new boot.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tools=feedback_native.tools()
            binary=feedback_program.compile_program(root,FILES['firmware/main.c'],tools)
            grid=np.linspace(0,.7,701);v=np.full(len(grid),2.5)
            v[(grid>=.262)&(grid<.4)]=0
            rows,_,events=feedback_program.execute_program(root/'application',binary,RAW['scenario'],grid,v,v)
            self.assertEqual(2,int(rows[-1,5]))
            self.assertTrue(np.all(rows[(grid[:-1]>=.262)&(grid[:-1]<.4),6]==0))
            tx=[e for e in events if e['state']=='tx']
            self.assertFalse(tx[0]['completed']);self.assertEqual(1,tx[0]['boot'])
            self.assertTrue(tx[-1]['completed']);self.assertEqual((2,1),(tx[-1]['boot'],tx[-1]['seq']))
            self.assertGreaterEqual(tx[-1]['t_s'],.66-1e-10)

    def test_raw_interval_minimum_catches_substep_dip(self):
        self.assertEqual(.8,interval_min(np.array([0,.49999,.5,.50001,1]),np.array([2.5,2.5,.8,2.5,2.5]),.49,.51))

    def test_nonconvergence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);counter=[0]
            def native(folder,*args):
                folder.mkdir();return {'key':'test-only','raw_sha256':'0'*64}
            def application(folder,binary,scenario,grid,*args):
                folder.mkdir();(folder/'program.csv').write_text('test only')
                counter[0]+=1
                return None,np.full(len(grid)-1,.001 if counter[0]%2 else 0.),[]
            scenario={**RAW['scenario'],'duration_s':.01}
            with patch.object(feedback_native,'native',side_effect=native),patch.object(feedback_native,'waveform',
                    return_value=(np.array([0,.01]),{'v(out)':np.array([2.5,2.5]),'v(pgood)':np.array([2.5,2.5])})),\
                    patch.object(feedback_program,'execute_program',side_effect=application):
                with self.assertRaisesRegex(ValueError,'FIXED_POINT_NOT_REACHED'):
                    execution.couple(root/'phase',root/'binary',json.loads(FILES['design.json']),scenario,{},root/'cache',.001,lambda:None)
            self.assertEqual(contract.NUMERICS['max_iterations'],counter[0])
            self.assertFalse((root/'phase/convergence.json').exists())

    def test_native_unknown_cache_cannot_repeat(self):
        import inspect
        from bfworld.agentlab.store import identity
        content='test-only';key=identity({'netlist':content,'tools':{},'reader':inspect.getsource(feedback_native.read_raw)})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'cache'/key;folder.mkdir(parents=True)
            sealed(folder/'dispatch.json',{'key':key})
            with patch.object(feedback_native,'native_slot',return_value=nullcontext()),patch('subprocess.run') as run:
                with self.assertRaisesRegex(ValueError,'UNKNOWN_RECONCILE'):
                    feedback_native.native(root/'run',root/'cache',content,{},lambda:None,1)
            run.assert_not_called()

    def test_load_transitions_preserve_program_intervals(self):
        pairs=np.asarray(feedback_native.load_pairs(np.array([0.,.01,.02,.03]),np.array([0.,.001,.008])))
        self.assertTrue(np.allclose(np.interp([.005,.015,.025],pairs[:,0],pairs[:,1]),[0,.001,.008],rtol=0,atol=1e-12))
        self.assertTrue(np.all(np.diff(pairs[:,0])>0))

    def test_load_has_no_predecision_effect_and_mechanical_loss_is_explicit(self):
        pairs=np.asarray(feedback_native.load_pairs(np.array([0.,.01,.02]),np.array([0.,.008])))
        self.assertEqual(0.,np.interp(.01-1e-10,pairs[:,0],pairs[:,1]))
        netlist=feedback_native.deck(json.loads(FILES['design.json']),RAW['scenario'],pairs,.0001)
        self.assertIn('Rser=0\nRdamper',netlist)


if __name__=='__main__':unittest.main()
