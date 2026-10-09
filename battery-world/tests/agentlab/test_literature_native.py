import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from bfworld.agentlab.literature_native import validate_plan,evaluate_native,evaluate_manifest,previous_native_attempt,continuation_deadline,latest_closed_result,archive_closed_traces
from bfworld.agentlab.literature_campaign import digest
from bfworld.agentlab.store import identity

class NativePaperTests(unittest.TestCase):
    def test_continuation_keeps_original_deadline(self):
        self.assertEqual(150,continuation_deadline({'usd_cap':30,'expires':150},100))
    def test_continuation_cannot_renew_expired_original_budget(self):
        with self.assertRaisesRegex(ValueError,'BUDGET_EXPIRED'):continuation_deadline({'usd_cap':30,'expires':99},100)
    def test_previous_attempt_is_selected_across_controller_revisions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for tag,started in [('old',1),('new',2)]:
                p=root/'campaign/native-runs'/('P01-native-source-'+tag)/'attempt.json';p.parent.mkdir(parents=True)
                p.write_text(json.dumps({'paper':'P01','owner':'same-'+tag,'started':started}))
            self.assertEqual('same-new',previous_native_attempt(root,'P01')[1]['owner'])
            self.assertIsNone(previous_native_attempt(root,'P02'))
    def test_recovery_uses_latest_closed_turn_in_same_task(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for target,started in [(root,1),(root/'continuations/turn-001',2),(root/'continuations/turn-002',3)]:
                target.mkdir(parents=True,exist_ok=True)
                (target/'attempt.json').write_text(json.dumps({'started':started}))
                if started!=3:(target/'result.json').write_text('{}')
            self.assertEqual(root/'continuations/turn-001/result.json',latest_closed_result(root))
    def test_closed_trace_prefix_is_preserved_before_append(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target=root/'campaign/native-runs/P01-native';target.mkdir(parents=True)
            trace=root/'trace.jsonl';closed=b'{"closed":1}\n';trace.write_bytes(closed+b'{"later":2}\n')
            result=target/'result.json';result.write_text(json.dumps({'raw_trace':'trace.jsonl','trace_sha256':hashlib.sha256(closed).hexdigest()}))
            before=result.read_bytes();receipts=archive_closed_traces(root,target)
            self.assertEqual(closed,(root/receipts[0]['closed_trace']).read_bytes())
            self.assertEqual(before,result.read_bytes());self.assertEqual(receipts,archive_closed_traces(root,target))
            (target/'trace.jsonl').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'SNAPSHOT_CHANGED'):archive_closed_traces(root,target)
    def test_missing_closed_trace_prefix_stops_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target=root/'task';target.mkdir();(root/'trace.jsonl').write_text('{}\n')
            (target/'result.json').write_text(json.dumps({'raw_trace':'trace.jsonl','trace_sha256':hashlib.sha256(b'absent\n').hexdigest()}))
            with self.assertRaisesRegex(ValueError,'PREFIX_NOT_FOUND'):archive_closed_traces(root,target)
    def plan(self):
        return {'tasks':[{'id':'A','discipline':'circuit','inputs':['source'],'produces':['netlist.cir'],
                         'depends_on':[],'independent_checks':['native solver'],'stop_condition':'actual readback'}]}
    def contract(self):return {'paper_id':'P01','source_identity':'source'}
    def report(self):return {'schema_version':'bf-paper-native-report-v1','paper_id':'P01','source_identity':'source',
                             'full_product_passed':False,'physical_verified':False,'gaps':['hardware untested'],
                             'jobs':[{'job_id':'eng-own','kind':'cadquery'}]}
    def jobs(self):
        project={'manifest':{'kind':'cadquery'},'sources':{'main.py':'source'}}
        return [{'id':'eng-own','owner':'pi-own','engine':'engineering-project','status':'SUCCEEDED',
                 'project':project,'project_sha256':identity(project),'assembly':{'revision':1},
                 'assembly_hashes':{'physical_hash':'physical'},'result':{'kind':'cadquery','readback_passed':True,
                 'project_sha256':identity(project),'independent_readback':{'native_valid':True,'solid_count':3},
                 'outputs':[{'name':'project-assembly.step','sha256':identity('fixture')} ]}}]
    def test_dependency_contract_valid(self):self.assertTrue(validate_plan(self.plan())['dag_valid'])
    def test_dependency_cycle_is_rejected(self):
        plan=self.plan();plan['tasks'][0]['depends_on']=['A']
        with self.assertRaisesRegex(ValueError,'CYCLE'):validate_plan(plan)
    def test_unknown_dependency_is_rejected(self):
        plan=self.plan();plan['tasks'][0]['depends_on']=['missing']
        with self.assertRaisesRegex(ValueError,'UNKNOWN_DEPENDENCY'):validate_plan(plan)
    def test_native_readback_has_limited_claim(self):
        result=evaluate_native(self.contract(),'pi-own',self.jobs(),self.report())
        self.assertEqual(result['status'],'PASS');self.assertFalse(result['full_product_passed']);self.assertFalse(result['physical_verified'])
    def test_participant_success_cannot_replace_job(self):
        report=self.report();report['full_product_passed']=True
        result=evaluate_native(self.contract(),'pi-own',[],report)
        self.assertIn('SELF_AWARDED_PRODUCT_PASS',result['problems']);self.assertIn('NO_NATIVE_OUTPUT_READBACK',result['problems'])
    def test_other_owner_native_job_is_rejected(self):
        jobs=self.jobs();jobs[0]['owner']='other'
        self.assertIn('NATIVE_JOB_OWNER',evaluate_native(self.contract(),'pi-own',jobs,self.report())['problems'])
    def test_changed_immutable_project_is_rejected(self):
        jobs=self.jobs();jobs[0]['project']['sources']['main.py']='changed'
        self.assertIn('NATIVE_PROJECT_IDENTITY',evaluate_native(self.contract(),'pi-own',jobs,self.report())['problems'])
    def test_corrupted_output_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/'runtime/engineering/eng-own/project-assembly.step';p.parent.mkdir(parents=True);p.write_text('changed')
            self.assertIn('NATIVE_OUTPUT_HASH',evaluate_native(self.contract(),'pi-own',self.jobs(),self.report(),root)['problems'])
    def test_wrong_firmware_target_is_rejected(self):
        jobs=self.jobs();jobs[0]['result'].update(kind='firmware-nrf52832',independent_readback={'target':'STM32L432','memory_fit':True})
        report=self.report();report['jobs'][0]['kind']='firmware-nrf52832'
        self.assertIn('NATIVE_READBACK_INVALID:firmware-nrf52832',evaluate_native(self.contract(),'pi-own',jobs,report)['problems'])
    def test_missing_true_native_readback_is_rejected(self):
        jobs=self.jobs();jobs[0]['result']['readback_passed']=False
        self.assertIn('NO_NATIVE_OUTPUT_READBACK',evaluate_native(self.contract(),'pi-own',jobs,self.report())['problems'])
    def test_superseded_success_is_history_not_current_delivery(self):
        jobs=self.jobs();old=copy.deepcopy(jobs[0]);old['id']='eng-old';jobs.append(old)
        result=evaluate_native(self.contract(),'pi-own',jobs,self.report())
        self.assertEqual('PASS',result['status']);self.assertEqual(['eng-own'],[x['job_id'] for x in result['native_checks']])
    def test_unselected_success_cannot_satisfy_required_engineering(self):
        jobs=self.jobs();other=copy.deepcopy(jobs[0]);other['id']='eng-spice'
        other['result'].update(kind='spice',independent_readback={'finite_values':True,'points':3});jobs.append(other)
        contract=self.contract();contract['required_project_kinds']=['cadquery','spice']
        self.assertIn('REQUIRED_NATIVE_PROJECT_MISSING:spice',evaluate_native(contract,'pi-own',jobs,self.report())['problems'])
    def test_one_successful_file_cannot_replace_required_projects(self):
        contract=self.contract();contract['required_project_kinds']=['cadquery','spice','firmware-nrf52832']
        problems=evaluate_native(contract,'pi-own',self.jobs(),self.report())['problems']
        self.assertIn('REQUIRED_NATIVE_PROJECT_MISSING:spice',problems)
        self.assertIn('REQUIRED_NATIVE_PROJECT_MISSING:firmware-nrf52832',problems)
    def test_stale_assembly_native_outputs_do_not_pass(self):
        assembly={'revision':2,'hashes':{'physical_hash':'new'}}
        problems=evaluate_native(self.contract(),'pi-own',self.jobs(),self.report(),assembly=assembly)['problems']
        self.assertIn('NO_NATIVE_OUTPUT_READBACK',problems);self.assertIn('NATIVE_REPORT_ASSEMBLY_IDENTITY',problems)
    def test_wrong_source_identity_and_physical_claim_are_rejected(self):
        report=self.report();report.update(source_identity='wrong',physical_verified=True)
        problems=evaluate_native(self.contract(),'pi-own',self.jobs(),report)['problems']
        self.assertIn('NATIVE_SOURCE_IDENTITY',problems);self.assertIn('UNSUPPORTED_PHYSICAL_CLAIM',problems)
    def delivery(self,root):
        path=root/'cad/main.py';path.parent.mkdir();path.write_text('paper-derived source')
        return {'schema_version':'bf-paper-native-delivery-v1','paper_id':'P01','source_identity':'source',
                'assembly_revision':1,'assembly_physical_hash':'physical',
                'files':[{'path':'cad/main.py','sha256':digest(path)}],
                'trusted_jobs':[{'job_id':'eng-own','project_sha256':'project'}],
                'unresolved_gates':['No physical verification']}
    def delivery_check(self,root,manifest):
        return evaluate_manifest(root,manifest,self.contract(),{'revision':1,'hashes':{'physical_hash':'physical'}},
                                 [{'job_id':'eng-own','project_sha256':'project'}])
    def source_bound_delivery(self,root):
        manifest=self.delivery(root);path=root/'cad/project.json';project={'kind':'cadquery','files':['main.py']}
        path.write_text(json.dumps(project));manifest['files'].append({'path':'cad/project.json','sha256':digest(path)})
        check={'job_id':'eng-own','project_sha256':'project','participant_project_path':'cad/project.json',
               'project_manifest':project,'project_source_sha256':{'cad/main.py':hashlib.sha256((root/'cad/main.py').read_text().encode()).hexdigest()}}
        return manifest,check
    def test_updated_file_hash_cannot_hide_source_changed_after_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,check=self.source_bound_delivery(root)
            args=(self.contract(),{'revision':1,'hashes':{'physical_hash':'physical'}},[check])
            self.assertEqual('PASS',evaluate_manifest(root,manifest,*args)['status'])
            (root/'cad/main.py').write_text('different source after build')
            manifest['files'][0]['sha256']=digest(root/'cad/main.py')
            self.assertIn('DELIVERY_PROJECT_SOURCE_CHANGED:cad/main.py',evaluate_manifest(root,manifest,*args)['problems'])
    def test_missing_native_source_cannot_be_replaced_by_another_listed_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,check=self.source_bound_delivery(root);manifest['files']=manifest['files'][1:]
            result=evaluate_manifest(root,manifest,self.contract(),{'revision':1,'hashes':{'physical_hash':'physical'}},[check])
            self.assertIn('DELIVERY_NATIVE_INPUT_MISSING:cad/main.py',result['problems'])
    def test_updated_manifest_hash_cannot_change_compiled_project_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,check=self.source_bound_delivery(root)
            (root/'cad/project.json').write_text(json.dumps({'kind':'spice','files':['main.py']}))
            manifest['files'][1]['sha256']=digest(root/'cad/project.json')
            result=evaluate_manifest(root,manifest,self.contract(),{'revision':1,'hashes':{'physical_hash':'physical'}},[check])
            self.assertIn('DELIVERY_PROJECT_MANIFEST_CHANGED:cad/project.json',result['problems'])
    def test_actual_delivery_file_and_version_are_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self.delivery_check(root,self.delivery(root))
            self.assertEqual(result['status'],'PASS');self.assertEqual(len(result['verified_files']),1)
    def test_delivery_file_changed_after_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest=self.delivery(root);(root/'cad/main.py').write_text('later change')
            self.assertIn('DELIVERY_FILE_HASH',self.delivery_check(root,manifest)['problems'])
    def test_delivery_cannot_escape_participant_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest=self.delivery(root);manifest['files'][0]['path']='../other/main.py'
            self.assertIn('DELIVERY_FILE_PATH',self.delivery_check(root,manifest)['problems'])
    def test_delivery_symlink_cannot_substitute_original_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest=self.delivery(root);(root/'cad/alias.py').symlink_to('main.py')
            manifest['files'][0]['path']='cad/alias.py'
            self.assertIn('DELIVERY_FILE_SYMLINK',self.delivery_check(root,manifest)['problems'])
    def test_delivery_wrong_native_input_and_assembly_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest=self.delivery(root);manifest['assembly_revision']=0
            manifest['trusted_jobs'][0]['project_sha256']='another-input'
            problems=self.delivery_check(root,manifest)['problems']
            self.assertIn('DELIVERY_ASSEMBLY_IDENTITY',problems);self.assertIn('DELIVERY_NATIVE_BINDINGS',problems)
    def test_delivery_wrong_source_and_unresolved_gates_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest=self.delivery(root);manifest['source_identity']='old'
            manifest['unresolved_gates']=[];problems=self.delivery_check(root,manifest)['problems']
            self.assertIn('DELIVERY_SOURCE_IDENTITY',problems);self.assertIn('DELIVERY_UNRESOLVED_GATES',problems)


class NativeRecoveryPhaseTests(unittest.TestCase):
    def task(self,root,owner='pi-own',paper='P01',phase='firmware'):
        p=root/'campaign/recovery'/paper/'phases'/(phase+'.json');p.parent.mkdir(parents=True)
        row={'schema_version':'bf-paper-recovery-phase-v1','paper_id':paper,'owner':owner,'phase':phase,'source_identity':'source','actor':'Codex public engineering reviewer','task':'Explicit scoped public firmware recovery task. '+('x'*40),'assets':[]}
        p.write_text(json.dumps(row));return p,row
    def test_phase_cannot_create_a_fresh_budget_owner(self):
        from bfworld.agentlab.literature_native import run_native_tasks
        with self.assertRaisesRegex(ValueError,'ORIGINAL_OWNER'):run_native_tasks(Path('/unused'),['P01'],phase='firmware')
    def test_unknown_phase_and_chipless_firmware_are_rejected(self):
        from bfworld.agentlab.literature_native import recovery_phase
        for paper,phase in [('P01','new-owner'),('P09','firmware')]:
            with self.assertRaisesRegex(ValueError,'SCOPE_DENIED'):recovery_phase(Path('/unused'),paper,phase,'pi-own',{'source_identity':'source'})
    def test_phase_is_bound_to_original_paper_owner_and_source(self):
        from bfworld.agentlab.literature_native import recovery_phase
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p,row=self.task(root)
            value=recovery_phase(root,'P01','firmware','pi-own',{'source_identity':'source'})
            self.assertEqual(digest(p),value['task_sha256'])
            with self.assertRaisesRegex(ValueError,'IDENTITY'):recovery_phase(root,'P01','firmware','another',{'source_identity':'source'})
            with self.assertRaisesRegex(ValueError,'IDENTITY'):recovery_phase(root,'P01','firmware','pi-own',{'source_identity':'changed'})
    def test_changed_public_feedback_is_rejected(self):
        from bfworld.agentlab.literature_native import recovery_phase
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p,row=self.task(root);asset=root/'review.json';asset.write_text('original review')
            row['assets']=[{'path':'review.json','sha256':digest(asset)}];p.write_text(json.dumps(row));asset.write_text('changed review')
            with self.assertRaisesRegex(ValueError,'INTEGRITY'):recovery_phase(root,'P01','firmware','pi-own',{'source_identity':'source'})
    def test_phase_explicit_profile_is_validated_before_execution(self):
        from bfworld.agentlab.literature_native import recovery_phase
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p,row=self.task(root)
            row['model_profile']='engineering-reasoning-compact-v2';p.write_text(json.dumps(row))
            self.assertEqual(row['model_profile'],recovery_phase(root,'P01','firmware','pi-own',{'source_identity':'source'})['model_profile'])
            row['model_profile']='arbitrary-provider';p.write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError,'MODEL_PROFILE_INVALID'):
                recovery_phase(root,'P01','firmware','pi-own',{'source_identity':'source'})
    def test_qualified_sdk_build_satisfies_same_mcu_native_requirement(self):
        t=NativePaperTests();jobs=t.jobs();job=jobs[0]
        job['result'].update(kind='firmware-nrf52832-s132',independent_readback={'target':'nRF52832-QFAA','softdevice':'S132-7.2.0','memory_fit':True})
        report=t.report();report['jobs'][0]['kind']='firmware-nrf52832-s132';contract=t.contract();contract['required_project_kinds']=['firmware-nrf52832']
        self.assertEqual('PASS',evaluate_native(contract,'pi-own',jobs,report)['status'])
        job['result']['independent_readback']['target']='another MCU'
        self.assertEqual('FAIL',evaluate_native(contract,'pi-own',jobs,report)['status'])

if __name__=='__main__':unittest.main()
