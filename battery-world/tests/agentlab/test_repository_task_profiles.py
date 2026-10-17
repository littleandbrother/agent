import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_design_repository as fixtures
from test_design_repository import OWNER, OTHER
from bfworld.agentlab.design_lab.repository_profiles import definition, profile, execution_identity
from bfworld.agentlab.design_lab.repository_contracts import fingerprint
from bfworld.agentlab.design_lab.repository_task_execution import descriptor


def curve_definition(limit=0.2):
    return {'profile': 'curve-reproduction-v1', 'intent': 'reproduce', 'goal': 'Reproduce the specified reference curve',
            'scenario': {'axis_units': {'x': 'Hz', 'y': 'V'}, 'initial_state': 'steady-state'}, 'parameters': [],
            'acceptance': {'curve_binding': {'condition': 'same abscissae'},
                'curve_accuracy': {'condition': 'absolute error at every sample', 'max_abs_error': limit},
                'delivery_version': {'condition': 'all inputs are immutable and readable'}}}


class TaskProfileTests(unittest.TestCase):
    setUp = fixtures.RepositoryCase.setUp
    def create_curve(self):
        return self.repo.handle(OWNER, {'action': 'repository_task_create', 'operation_id': 'new-curve',
            'definition': curve_definition(), 'files': {'reference.csv': 'x,y\n1,2\n2,3\n',
                'observation.csv': 'x,y\n1,2.1\n2,3.1\n'}}, True)

    def action(self, action, operation, **values):
        return self.repo.handle(OWNER, {'action': 'repository_'+action, 'operation_id': operation, **values})

    def test_pcb_entry_inherits_files_and_only_uses_pcb_scope(self):
        from bfworld.agentlab.design_lab.repository_profiles import REPORTS
        baseline=self.repo.handle(OWNER,self.body,True)
        cfg=profile('pcb-completion-v1')
        definition={**curve_definition(),'profile':'pcb-completion-v1','intent':'complete',
            'acceptance':{g:{'condition':'existing native evidence'} for g in cfg['gates']}}
        c=self.repo.handle(OTHER,{'action':'repository_task_create','operation_id':'pcb-task','definition':definition,
            'source_project':baseline['project_id'],'source_system':baseline['submitted']},True)
        system=self.repo.system(c['project_id'],c['id'])
        self.assertEqual(self.repo.system(baseline['project_id'],baseline['submitted'])['files'],system['files'])
        checked=self.repo.handle(OTHER,{'action':'repository_validate','operation_id':'pcb-check','system_id':c['id']})
        self.assertEqual(set(cfg['gates']),set(checked['result']['gates']))
        self.assertEqual('RECHECK_REQUIRED',checked['result']['gates']['pcb_connectivity_drc']['status'])
        content={'conclusion':'当前缺少板卡证据。','sections':{k:{'text':'保留原文件，当前原生板卡检查需要补齐。','sources':['delivery_version']} for k in REPORTS[cfg['report']]}}
        report=self.repo.handle(OTHER,{'action':'repository_task_report','operation_id':'pcb-report','system_id':c['id'],
            'content':json.dumps(content,ensure_ascii=False)})
        self.assertEqual('PASS',report['status'])

    def test_explicit_p01_task_entry_preserves_its_eight_gate_profile(self):
        baseline=self.repo.handle(OWNER,self.body,True)
        cfg=profile('p01-digital-v1')
        raw={**curve_definition(),'profile':'p01-digital-v1','intent':'reconstruct',
            'acceptance':{g:{'condition':'original eight engineering gates'} for g in cfg['gates']}}
        c=self.repo.handle(OTHER,{'action':'repository_task_create','operation_id':'p01-task','definition':raw,
            'source_project':baseline['project_id'],'source_system':baseline['submitted']},True)
        self.assertEqual(8,len(c['task_definition']['required_gates']))
        self.assertEqual(baseline['submitted'],self.repo.system(c['project_id'],c['id'])['inherited_from']['system_id'])

    def test_three_entry_contracts_without_p01_gate_inheritance(self):
        curve = self.create_curve()
        self.assertEqual(3, len(curve['task_definition']['required_gates']))
        self.assertNotIn('pcb_connectivity_drc', curve['task_definition']['required_gates'])
        for key, intent in [('pcb-completion-v1', 'complete'), ('p01-digital-v1', 'reconstruct')]:
            cfg = profile(key)
            raw = {**curve_definition(), 'profile': key, 'intent': intent,
                   'acceptance': {g: {'condition': 'fixed adapter check'} for g in cfg['gates']}}
            d = definition(raw)
            self.assertEqual(cfg['gates'], d['required_gates'])
            self.assertEqual(cfg['report'], d['report'])
            self.assertTrue(all(i['consumer'] and i['executor'] and i['checker'] for i in d['interfaces']))

    def test_real_entry_execution_validation_and_task_scoped_adoption(self):
        c = self.create_curve(); s = c['id']
        e = self.action('task_execute', 'run', system_id=s)
        v = self.action('validate', 'check', system_id=s)
        self.assertEqual('PASS', v['status'])
        q = self.repo.view(c['project_id'], OWNER)['systems'][0]['current_qualification']
        self.assertTrue(q['task_passed']); self.assertFalse(q['product_passed'])
        d = self.action('decide', 'adopt', system_id=s, expected_revision=1, decision='ADOPT_PASSED', rationale='curve meets required tolerance')
        self.assertFalse(d['product_passed'])
        self.assertEqual('curve-reproduction', d['accepted_scope'])
        self.assertEqual(e, self.action('task_execute', 'run', system_id=s))

    def test_requirement_change_reuses_execution_and_invalidates_acceptance(self):
        c = self.create_curve(); old = self.repo.system(c['project_id'], c['id'])
        first = self.action('task_execute', 'run', system_id=old['id'])
        self.action('validate', 'check', system_id=old['id'])
        changed = self.repo.handle(OWNER, {'action': 'repository_task_define', 'operation_id': 'strict',
            'expected_revision': 1, 'definition': curve_definition(0.01)}, True)
        new = self.repo.system(c['project_id'], changed['id'])
        self.assertEqual(descriptor(old), descriptor(new))
        self.assertNotEqual(fingerprint(old, 'curve_accuracy'), fingerprint(new, 'curve_accuracy'))
        second = self.action('task_execute', 'reuse', system_id=new['id'])
        self.assertEqual(first['id'], second['id']); self.assertTrue(second['reused'])
        v = self.action('validate', 'strict-check', system_id=new['id'])
        self.assertEqual('FAIL', v['result']['gates']['curve_accuracy']['status'])
        view = self.repo.view(c['project_id'], OWNER)
        self.assertEqual('PASS', view['systems'][0]['current_qualification']['status'])
        self.assertEqual('REPAIR_REQUIRED', view['systems'][1]['current_qualification']['status'])
        self.assertEqual(1, len(view['task_executions']))

    def test_report_notes_do_not_change_execution(self):
        c = self.create_curve(); old = self.repo.system(c['project_id'], c['id'])
        d = self.action('task_commit', 'notes', base_system=c['id'], expected_revision=1,
            files={'notes/review.md': 'Explain the observed curve'}, rationale='report explanation')
        new = self.repo.system(c['project_id'], d['id'])
        self.assertEqual(descriptor(old), descriptor(new))

    def test_two_partial_commits_retain_source_and_require_new_execution(self):
        c = self.create_curve(); old = self.repo.system(c['project_id'], c['id'])
        d1 = self.action('task_commit', 'rev1', base_system=c['id'], expected_revision=1,
            files={'observation.csv': 'x,y\n1,2\n2,3\n'}, rationale='correct model output')
        d2 = self.action('task_commit', 'rev2', base_system=d1['id'], expected_revision=2,
            files={'notes/review.md': 'record change'}, rationale='explain revised output')
        new = self.repo.system(c['project_id'], d2['id'])
        self.assertNotEqual(descriptor(old), descriptor(new))
        self.assertEqual('x,y\n1,2\n2,3\n', self.action('read', 'r', system_id=new['id'], path='observation.csv')['content'])
        self.assertEqual(old['files']['reference.csv'], new['files']['reference.csv'])

    def test_agent_cannot_relax_requirements_or_change_reference(self):
        c = self.create_curve()
        with self.assertRaisesRegex(PermissionError, 'OPERATOR_ONLY'):
            self.action('task_define', 'loosen', expected_revision=1, definition=curve_definition(1))
        with self.assertRaisesRegex(PermissionError, 'DESIGN_SCOPE'):
            self.action('task_commit', 'overwrite', base_system=c['id'], expected_revision=1,
                files={'reference.csv': 'x,y\n1,2\n2,3\n'}, rationale='replace target')

    def test_unknown_dispatch_does_not_repeat(self):
        c = self.create_curve(); s = self.repo.system(c['project_id'], c['id'])
        root = self.repo.root/'task-executions'/c['project_id']/descriptor(s)['id']
        root.mkdir(parents=True); (root/'dispatch.json').write_text('{}')
        for operation in ('retry1', 'retry2'):
            with self.assertRaisesRegex(ValueError, 'UNKNOWN_RECONCILE'):
                self.action('task_execute', operation, system_id=s['id'])

    def test_unknown_profile_source_role_and_empty_gates_rejected(self):
        for edit in ({'profile': 'other'}, {'acceptance': {}}, {'intent': 'anything'},
                     {'parameters': [{'name': 'x', 'value': 1, 'unit': 'V', 'source': 'constraint', 'role': 'literature'}]}):
            with self.subTest(edit=edit), self.assertRaises(ValueError): definition({**curve_definition(), **edit})

    def test_shared_component_is_not_duplicated_by_function(self):
        d = definition({**curve_definition(), 'components': [{'id': 'soc'}],
            'functions': [{'id': 'compute', 'components': ['soc']}, {'id': 'radio', 'components': ['soc']}]})
        self.assertEqual(1, len(d['components']))
        with self.assertRaisesRegex(ValueError, 'COMPONENT_IDENTITY'):
            definition({**curve_definition(), 'components': [{'id': 'soc'}, {'id': 'soc'}]})

    def test_raw_result_tamper_removes_current_qualification(self):
        c = self.create_curve()
        execution = self.action('task_execute', 'run', system_id=c['id'])
        self.action('validate','check',system_id=c['id'])
        ref = execution['artifacts']['samples.json']
        artifact = self.repo.root/'blobs'/ref['sha256']
        artifact.chmod(0o600); artifact.write_text('{}')
        with self.assertRaisesRegex(ValueError,'ARTIFACT_CHANGED'):
            self.repo.view(c['project_id'],OWNER)

    def test_audit_cannot_become_an_implicit_design_revision(self):
        d = {**curve_definition(), 'intent':'audit'}
        c = self.repo.handle(OWNER,{'action':'repository_task_create','operation_id':'audit',
            'definition':d,'files':{'reference.csv':'x,y\n1,2\n2,3\n','observation.csv':'x,y\n1,2\n2,3\n'}},True)
        with self.assertRaisesRegex(PermissionError,'READ_ONLY'):
            self.action('task_commit','change',base_system=c['id'],expected_revision=1,files={'observation.csv':'x,y\n1,5\n2,5\n'},rationale='change')

    def test_bad_source_data_is_a_recorded_failure_and_not_dispatched_again(self):
        c=self.create_curve()
        bad=self.action('task_commit','bad-csv',base_system=c['id'],expected_revision=1,
            files={'observation.csv':'x,y\n1,nan\n2,3\n'},rationale='negative control')
        first=self.action('task_execute','bad-run',system_id=bad['id'])
        self.assertEqual('FAILED',first['status'])
        second=self.action('task_execute','retry',system_id=bad['id'])
        self.assertTrue(second['reused']);self.assertEqual(first['id'],second['id'])
        check=self.action('validate','bad-check',system_id=bad['id'])
        self.assertEqual('UNEVALUABLE',check['result']['gates']['curve_accuracy']['status'])

    def test_result_reads_bound_execution_without_dispatch_and_rejects_invalid_paths(self):
        c=self.create_curve()
        execution=self.action('task_execute','run',system_id=c['id'])
        result=self.action('task_result','result',system_id=c['id'],path='samples.json',offset=2,limit=20)
        raw=(self.repo.root/'blobs'/execution['artifacts']['samples.json']['sha256']).read_text()
        self.assertEqual(raw[2:22],result['read']['content'])
        self.assertEqual(execution['id'],result['execution_id'])
        self.assertEqual(1,len(self.repo.view(c['project_id'],OWNER)['task_executions']))
        for kwargs, message in [({'path':'../../operator.token'},'ARTIFACT_UNKNOWN'),
                ({'path':'samples.json','limit':25000},'READ_RANGE')]:
            with self.assertRaisesRegex(ValueError,message): self.action('task_result','bad-read',system_id=c['id'],**kwargs)
        with self.assertRaises(PermissionError):
            self.repo.handle(OTHER,{'action':'repository_task_result','project_id':c['project_id'],'system_id':c['id']})

    def test_result_facts_use_load_rail_and_actual_service_window(self):
        from bfworld.agentlab.design_lab.repository_task_result import facts
        values={'events.json':json.dumps([{'t_s':1,'duration_s':.1,'state':'tx','seq':1}]),
            'load.json':json.dumps([[0,.001],[2,.001]]),
            'storage.dat':'0 2.5 .004 .0025 0\n1 2.9 .004 .0025 0\n1.1 2.8 .004 .0025 0\n2 3 .004 .0025 0\n',
            'design.json':json.dumps({'storage_f':47e-6})}
        artifacts={}
        import hashlib
        (self.repo.root/'blobs').mkdir(parents=True,exist_ok=True)
        for path,raw in values.items():
            h=hashlib.sha256(raw.encode()).hexdigest();(self.repo.root/'blobs'/h).write_text(raw);artifacts[path]={'sha256':h}
        system={'task_definition':{'case_adapter':'piezo-reference-v1','scenario':{
            'rail_v':2.5,'duration_s':2,'initial_storage_v':2.5,'minimum_storage_v':2.2}}}
        result=facts(self.repo,system,{'id':'TX-test','status':'SUCCEEDED','artifacts':artifacts,'metrics':{'available_power_w':.004}})
        by={v['key']:v['value'] for v in result}
        self.assertAlmostEqual(2500,by['average_load_uw'])
        self.assertAlmostEqual(2.8,by['tx_1_minimum_v'])
        self.assertAlmostEqual(.6,by['minimum_service_margin_v'])

    def test_profile_report_and_zip_are_same_candidate_and_expire_with_acceptance(self):
        import zipfile
        from bfworld.agentlab.design_lab.repository_task_reports import required
        c=self.create_curve();self.action('task_execute','run',system_id=c['id'])
        self.action('validate','check',system_id=c['id'])
        content={'conclusion':'当前曲线满足声明的误差要求。','sections':{k:{'text':'同一采样轴下完成对比，最大绝对误差为 0.1 V。',
            'sources':['observation.csv','curve_accuracy']} for k in ('target_and_conditions','curves_and_error','conclusion_and_files')}}
        report=self.action('task_report','report',system_id=c['id'],content=json.dumps(content,ensure_ascii=False))
        self.assertEqual('PASS',report['status'])
        release=self.action('release','release',system_id=c['id'],rationale='scoped curve review')
        with zipfile.ZipFile(self.repo.root/'releases'/(release['id']+'.zip')) as z:
            self.assertIn('reports/task-report.pdf',z.namelist())
            self.assertIn('execution/samples.json',z.namelist())
            self.assertEqual(c['id'],json.loads(z.read('manifest.json'))['target'])
        changed=self.repo.handle(OWNER,{'action':'repository_task_define','operation_id':'strict',
            'expected_revision':1,'definition':curve_definition(.01)},True)
        with self.assertRaisesRegex(ValueError,'REPORT_MISSING'):
            required(self.repo,OWNER,self.repo.system(c['project_id'],changed['id']))


if __name__ == '__main__': unittest.main()
