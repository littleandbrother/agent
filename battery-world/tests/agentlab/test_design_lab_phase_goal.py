import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from bfworld.agentlab.literature_native import phase_gate_problems, stage_current_task, stage_candidate_task, prior_result_reference
from scripts.literature_pi_queue import live_queue_item


class ExactRecoveryGoalTests(unittest.TestCase):
    def test_candidate_resume_replaces_stale_task_with_exact_registered_scope_and_keeps_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace=Path(folder);(workspace/'TASK.md').write_bytes(b'old completed EDA phase')
            (workspace/'main.c').write_bytes(b'original Pi firmware')
            contract={'task_id':'original-P01','goal':'Original complete product',
                'requirements':['source','power','delivery'],'scenario':{'manual_mcu_connection':True},
                'scope':'complete-digital-system'}
            message='Current authorized work: connect motion to source and actual workload; export observed result.'
            first=stage_candidate_task(workspace,contract,message)
            self.assertEqual(first,stage_candidate_task(workspace,contract,message))
            self.assertIn(message,(workspace/'TASK.md').read_text())
            current=json.loads((workspace/'CURRENT-CANDIDATE-WORK.json').read_text())
            self.assertEqual(contract['requirements'],current['requirements'])
            self.assertEqual(contract['scenario'],current['scenario'])
            self.assertEqual(b'original Pi firmware',(workspace/'main.c').read_bytes())
            self.assertIn(b'old completed EDA phase',[p.read_bytes() for p in (workspace/'public-context-history').iterdir()])
            stage_candidate_task(workspace,contract,'Next authorized interface work')
            self.assertIn(message,'\n'.join(p.read_text() for p in (workspace/'public-context-history').iterdir()))

    def test_candidate_resume_refuses_empty_scope_and_task_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace=Path(folder);outside=workspace/'source.c';outside.write_bytes(b'original')
            (workspace/'TASK.md').symlink_to(outside)
            contract={'task_id':'P01','goal':'product','requirements':['power'],'scenario':{},'scope':'complete'}
            with self.assertRaisesRegex(ValueError,'CURRENT_WORK_REQUIRED'):
                stage_candidate_task(workspace,contract,'')
            with self.assertRaisesRegex(ValueError,'PATH_SYMLINK'):
                stage_candidate_task(workspace,contract,'Authorized work')
            self.assertEqual(b'original',outside.read_bytes())

    def test_real_s132_goal_rejects_bare_build(self):
        phase = {'required_project_kind': 'firmware-nrf52832-s132'}
        checks = [{'kind': 'cadquery'}, {'kind': 'spice'}, {'kind': 'firmware-nrf52832'}]
        self.assertEqual(['RECOVERY_TARGET_BUILD_MISSING:firmware-nrf52832-s132'],
                         phase_gate_problems(phase, checks, {'status': 'IDLE'}))
        self.assertEqual([], phase_gate_problems(phase, checks + [{'kind': 'firmware-nrf52832-s132'}], {'status': 'IDLE'}))

    def test_failed_execution_retains_files_without_completing_phase(self):
        self.assertEqual(['RECOVERY_EXECUTION_NOT_COMPLETE'], phase_gate_problems({}, [{'kind': 'spice'}], {'status': 'FAILED'}))
        self.assertEqual([], phase_gate_problems(None, [{'kind': 'spice'}], {'status': 'FAILED'}))

    def test_resume_exposes_exact_phase_and_preserves_old_public_and_engineering_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);workspace=root/'participant';workspace.mkdir()
            relative='campaign/recovery/P04/phases/engineering-review.json'
            source=root/relative;source.parent.mkdir(parents=True)
            phase={'paper_id':'P04','phase':'engineering-review','task':'Build actual S132, retain prior paid history.'}
            source.write_text(json.dumps(phase))
            focused={**phase,'task_file':relative,'task_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
            (workspace/'TASK.md').write_bytes(b'old generic instructions')
            (workspace/'main.c').write_bytes(b'Pi original source')
            local=workspace/relative;local.parent.mkdir(parents=True);local.write_bytes(b'old phase')
            receipt=stage_current_task(root,workspace,focused)
            self.assertEqual(source.read_bytes(),local.read_bytes())
            self.assertIn(phase['task'],(workspace/'TASK.md').read_text())
            self.assertEqual(b'Pi original source',(workspace/'main.c').read_bytes())
            history=[p.read_bytes() for p in (workspace/'public-context-history').iterdir()]
            self.assertIn(b'old generic instructions',history)
            self.assertIn(b'old phase',history)
            self.assertEqual(receipt,stage_current_task(root,workspace,focused))

    def test_phase_paths_and_symlinks_cannot_overwrite_engineering(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);workspace=root/'participant';workspace.mkdir()
            focused={'paper_id':'P04','phase':'engineering-review','task_file':'../main.c','task_sha256':'0'*64}
            with self.assertRaisesRegex(ValueError,'RECOVERY_PUBLIC_PHASE_SCOPE'):
                stage_current_task(root,workspace,focused)
            relative='campaign/recovery/P04/phases/engineering-review.json'
            source=root/relative;source.parent.mkdir(parents=True);source.write_text('{}')
            focused.update(task_file=relative,task_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),task='current goal')
            outside=root/'old-engineering.c';outside.write_bytes(b'preserve')
            (workspace/'TASK.md').symlink_to(outside)
            with self.assertRaisesRegex(ValueError,'RECOVERY_PUBLIC_PATH_SYMLINK'):
                stage_current_task(root,workspace,focused)
            self.assertEqual(b'preserve',outside.read_bytes())

    def test_large_old_result_becomes_exact_readable_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace=Path(folder)
            old={'execution':{'status':'IDLE'},'evaluation':{'status':'PASS'},
                 'delivery_integrity':{'status':'PASS','verified_files':[{'path':'x'+str(i),'sha256':'a'*64} for i in range(1000)]}}
            reference=prior_result_reference(workspace,old)
            self.assertLess(len(json.dumps(reference)),1000)
            self.assertTrue(reference['history_only'])
            frozen=workspace/reference['path']
            self.assertEqual(old,json.loads(frozen.read_text()))
            self.assertEqual(reference['sha256'],hashlib.sha256(frozen.read_bytes()).hexdigest())

    def test_backup_glob_cannot_dispatch_old_queue_twice(self):
        owner='pi-chat-1111111111111111'
        item={'schema_version':'bf-paper-continuation-queue-v1','owner':owner,'status':'QUEUED'}
        self.assertTrue(live_queue_item(Path(owner+'.json'),item))
        for name in (owner+'-backup.json',owner+'-stop.json',owner+'-20261009.json'):
            self.assertFalse(live_queue_item(Path(name),item))


if __name__ == '__main__':
    unittest.main()
