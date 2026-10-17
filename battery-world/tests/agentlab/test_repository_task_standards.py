import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_design_repository as fixtures
from test_design_repository import OWNER
from test_repository_task_profiles import curve_definition
from bfworld.agentlab.store import canonical, identity
from bfworld.agentlab.design_lab.repository_profiles import definition, execution_identity, runtime_spec
from bfworld.agentlab.design_lab.repository_contracts import fingerprint
from bfworld.agentlab.design_lab.repository_task_execution import descriptor, current_execution, pending_execution

APP = Path(__file__).resolve().parents[2]


def node_raw():
    return json.loads((APP/'configs/reference_cases/task-design/piezo-node-v1.json').read_text())


class TaskStandardsTests(unittest.TestCase):
    setUp = fixtures.RepositoryCase.setUp

    def create(self, raw=None, files=None):
        raw = raw or node_raw()
        if files is None:
            files = {'design.json': (APP/'configs/reference_cases/task-design/design.json').read_text(),
                     'firmware/main.c': (APP/'configs/reference_cases/task-design/main.c').read_text()}
        return self.repo.handle(OWNER, {'action': 'repository_task_create', 'operation_id': 'create',
            'definition': raw, 'files': files}, True)

    def action(self, action, op, operator=False, **values):
        return self.repo.handle(OWNER, {'action': 'repository_'+action, 'operation_id': op, **values}, operator)

    def revise_design(self, created, **values):
        design = json.loads((APP/'configs/reference_cases/task-design/design.json').read_text())
        design.update(values)
        return self.action('task_commit', 'edit', base_system=created['id'], expected_revision=1,
            files={'design.json': json.dumps(design)}, rationale='compare candidate')

    def test_source_and_role_are_independent_and_fixed_parameter_is_enforced(self):
        raw = node_raw()
        raw['parameters'].append({'name': 'length_m', 'value': .05, 'unit': 'm', 'source': 'user', 'role': 'constraint'})
        c = self.create(raw)
        spec = runtime_spec(c['task_definition'])
        self.assertNotIn('length_m', spec['design_fields'])
        with self.assertRaisesRegex(PermissionError, 'UNDECLARED_DESIGN_VARIABLE|FIXED_PARAMETER'):
            self.revise_design(c, length_m=.06)
        self.assertEqual(c['id'], self.repo.project(c['project_id'])['submitted'])

    def test_user_reference_value_remains_a_design_variable(self):
        raw = node_raw()
        raw['parameters'].append({'name': 'length_m', 'value': .05, 'unit': 'm', 'source': 'user', 'role': 'design_choice'})
        c = self.create(raw); child = self.revise_design(c, length_m=.06)
        self.assertNotEqual(c['id'], child['id'])

    def test_unbound_constraint_rejected(self):
        raw = node_raw(); raw['parameters'].append({'name': 'magic', 'value': 5, 'unit': 'V', 'source': 'user', 'role': 'constraint'})
        with self.assertRaisesRegex(ValueError, 'CONSTRAINT_BINDING'): definition(raw)

    def test_wrong_units_cannot_enter_the_design(self):
        raw = node_raw(); raw['parameters'][0]['unit'] = 'kHz'
        with self.assertRaisesRegex(ValueError, 'UNIT_MISMATCH'): definition(raw)

    def test_unknown_parameter_fields_and_nonfinite_values_rejected(self):
        for key, val in [('hidden', 1), ('value', float('nan'))]:
            raw = node_raw(); raw['parameters'][0][key] = val
            with self.subTest(key=key), self.assertRaises(ValueError): definition(raw)

    def test_literature_value_requires_a_locator(self):
        raw = node_raw(); raw['parameters'][0]['source'] = 'literature'
        with self.assertRaisesRegex(ValueError, 'SOURCE_LOCATOR'): definition(raw)

    def test_narrowed_design_space_rejects_other_variable_and_bounds(self):
        raw = node_raw(); raw['design_space'] = {'fields': {'storage_f': {'unit': 'F', 'min': 47e-6, 'max': 220e-6}},
                                                'editable_files': ['design.json', 'notes/']}
        c = self.create(raw)
        with self.assertRaisesRegex(PermissionError, 'UNDECLARED_DESIGN_VARIABLE'): self.revise_design(c, length_m=.06)
        with self.assertRaisesRegex(PermissionError, 'BOUNDS'):
            self.action('task_commit', 'too-small', base_system=c['id'], expected_revision=1,
                files={'design.json': json.dumps({**json.loads((APP/'configs/reference_cases/task-design/design.json').read_text()), 'storage_f': 22e-6})}, rationale='probe')
        with self.assertRaisesRegex(PermissionError, 'DESIGN_SCOPE'):
            self.action('task_commit', 'program', base_system=c['id'], expected_revision=1,
                files={'firmware/main.c': 'int main(void){return 0;}'}, rationale='probe')

    def test_fixed_variable_and_declared_mutability_conflict_rejected(self):
        raw = node_raw(); raw['parameters'].append({'name': 'storage_f', 'value': 220e-6, 'unit': 'F', 'source': 'user', 'role': 'constraint'})
        raw['design_space'] = {'fields': {'storage_f': {'unit': 'F', 'min': 1e-6, 'max': .02}}, 'editable_files': ['design.json']}
        with self.assertRaisesRegex(ValueError, 'FIXED_VARIABLE_CONFLICT'): definition(raw)

    def test_fixed_artifact_cannot_be_changed(self):
        data = 'x,y\n1,2\n2,3\n'; raw = curve_definition()
        raw['parameters'] = [{'name': 'measured_data', 'value': hashlib.sha256(data.encode()).hexdigest(),
            'unit': 'bytes', 'source': 'measurement', 'locator': 'record-1', 'role': 'constraint',
            'binding': {'target': 'artifact', 'path': 'observation.csv'}}]
        c = self.create(raw, {'reference.csv': data, 'observation.csv': data})
        with self.assertRaisesRegex(PermissionError, 'FIXED_ARTIFACT'):
            self.action('task_commit', 'fake', base_system=c['id'], expected_revision=1,
                files={'observation.csv': data+'3,4\n'}, rationale='probe')

    def test_extra_design_field_is_not_silently_ignored(self):
        c = self.create()
        with self.assertRaisesRegex(ValueError, 'DESIGN_FIELDS'): self.revise_design(c, fake_efficiency=.9)

    def test_malformed_mapping_and_material_fields_are_rejected(self):
        changes = [('functions', [{'id': 'R', 'components': [{}]}]),
                   ('assignments', [{'role': 'lead', 'functions': 'H'}]),
                   ('design_space', {'fields': {}, 'editable_files': [{}]})]
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(ValueError): definition({**node_raw(), key: value})
        raw = node_raw(); raw['scenario']['material']['secret_efficiency'] = 1
        with self.assertRaisesRegex(ValueError, 'MATERIAL_FIELDS'): definition(raw)

    def test_effective_predicates_show_numeric_conditions_actually_consumed(self):
        raw = node_raw(); raw['scenario']['minimum_storage_v'] = 2.8
        standard = definition(raw)['standards']
        for gate in ('power_service', 'receiver_service'):
            self.assertEqual(2.8, standard['acceptance_predicates'][gate]['parameters']['minimum_sample_and_tx_storage_v'])
        self.assertEqual(20, standard['service']['deadline_s'])

    def test_review_profile_does_not_advertise_unimplemented_writes_or_execution(self):
        from bfworld.agentlab.design_lab.repository_profiles import profile
        raw = {**curve_definition(), 'profile': 'pcb-completion-v1',
            'acceptance': {g: {'condition': 'native evidence'} for g in profile('pcb-completion-v1')['gates']}}
        spec = runtime_spec(definition(raw))
        self.assertEqual([], spec['profile']['roles']); self.assertEqual([], spec['write_paths'])
        self.assertIn('validate', spec['qualified_operations']); self.assertIn('task_report', spec['qualified_operations'])
        for op in ('assign', 'task_commit', 'task_execute'): self.assertNotIn(op, spec['qualified_operations'])

    def test_unsupported_scenario_and_criterion_are_rejected(self):
        for field in ('scenario', 'criterion'):
            raw = node_raw()
            if field == 'scenario': raw['scenario']['auto_start'] = True
            else: raw['acceptance']['power_service']['min_voltage'] = 9
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'UNSUPPORTED_FIELD'): definition(raw)

    def test_service_cannot_silently_claim_automatic_startup(self):
        raw = node_raw(); raw['service'] = {'observable': 'valid-digital-frames', 'startup': 'automatic', 'deadline_s': 20, 'minimum_results': 3}
        with self.assertRaisesRegex(ValueError, 'SERVICE_UNSUPPORTED'): definition(raw)

    def test_checker_only_changes_reuse_execution_but_change_acceptance(self):
        c = self.create(); base = self.repo.system(c['project_id'], c['id'])
        for key, val in [('minimum_storage_v', 2.4), ('minimum_sample_s', .02), ('minimum_tx_s', .005), ('sensor_value', 10)]:
            raw = node_raw(); raw['scenario'][key] = val
            child = {**base, 'task_definition': definition(raw)}
            with self.subTest(key=key):
                self.assertEqual(execution_identity(base, 'x', {}), execution_identity(child, 'x', {}))
                self.assertNotEqual(fingerprint(base, 'power_service'), fingerprint(child, 'power_service'))

    def test_real_input_changes_require_new_execution(self):
        c = self.create(); base = self.repo.system(c['project_id'], c['id'])
        for key, val in [('frequency_hz', 31), ('duration_s', 30), ('initial_storage_v', 2.4), ('conversion_efficiency', .4)]:
            raw = node_raw(); raw['scenario'][key] = val
            raw['parameters'] = [p for p in raw['parameters'] if p['name'] != key]
            child = {**base, 'task_definition': definition(raw)}
            with self.subTest(key=key): self.assertNotEqual(execution_identity(base, 'x', {}), execution_identity(child, 'x', {}))

    def test_display_wording_does_not_invalidate_engineering(self):
        c = self.create(); base = self.repo.system(c['project_id'], c['id'])
        raw = node_raw(); raw['scenario']['boundary'] += '；补充说明'
        child = {**base, 'task_definition': definition(raw)}
        self.assertEqual(execution_identity(base, 'x', {}), execution_identity(child, 'x', {}))
        self.assertEqual(fingerprint(base, 'power_service'), fingerprint(child, 'power_service'))

    def test_phase_change_preserves_history_and_requires_reason(self):
        c = self.create(curve_definition(), {'reference.csv': 'x,y\n1,2\n2,3\n', 'observation.csv': 'x,y\n1,2\n2,3\n'})
        raw = curve_definition(); raw['intent'] = 'audit'
        with self.assertRaisesRegex(ValueError, 'TRANSITION_REASON'):
            self.action('task_define', 'no-reason', True, expected_revision=1, definition=raw)
        new = self.action('task_define', 'phase', True, expected_revision=1, definition=raw, rationale='Review completed reconstruction')
        child = self.repo.system(c['project_id'], new['id'])
        self.assertEqual(c['id'], child['parent']); self.assertEqual('reproduce', self.repo.system(c['project_id'], c['id'])['task_definition']['intent'])
        self.assertEqual(['intent', 'phase'], child['task_transition']['changed'])
        with self.assertRaisesRegex(PermissionError, 'READ_ONLY'):
            self.action('task_commit', 'audit-edit', base_system=new['id'], expected_revision=2, files={'notes/x.md': 'x'}, rationale='edit')

    def test_profile_transition_requires_compatible_assets(self):
        c = self.create(curve_definition(), {'reference.csv': 'x,y\n1,2\n2,3\n', 'observation.csv': 'x,y\n1,2\n2,3\n'})
        with self.assertRaisesRegex(ValueError, 'INPUT_MISSING'):
            self.action('task_define', 'wrong-input', True, expected_revision=1, definition=node_raw(), rationale='new product phase')
        files = {'design.json': (APP/'configs/reference_cases/task-design/design.json').read_text(),
                 'firmware/main.c': (APP/'configs/reference_cases/task-design/main.c').read_text()}
        new = self.action('task_define', 'new-phase', True, expected_revision=1, definition=node_raw(), files=files, rationale='new product phase')
        s = self.repo.system(c['project_id'], new['id'])
        self.assertIn('reference.csv', s['files']); self.assertIn('design.json', s['files'])
        self.assertEqual('nominal-reference-chain', s['task_definition']['scope'])

    def test_repeated_definition_does_not_create_a_new_candidate(self):
        c = self.create()
        with self.assertRaisesRegex(ValueError, 'UNCHANGED'):
            self.action('task_define', 'repeat', True, expected_revision=1, definition=node_raw())

    def test_shared_chip_has_one_physical_instance(self):
        raw = node_raw(); raw['components'][2]['physical_instance'] = 'U1'
        d = definition(raw); self.assertEqual(1, sum(c.get('physical_instance') == 'U1' for c in d['components']))
        raw['components'].append({'id': 'second-radio', 'physical_instance': 'U1'})
        with self.assertRaisesRegex(ValueError, 'PHYSICAL_INSTANCE_DUPLICATE'): definition(raw)

    def test_assignment_cannot_name_unqualified_role_or_unknown_object(self):
        for edit in ({'role': 'mechanical'}, {'components': ['missing']}):
            raw = node_raw(); raw['assignments'][0].update(edit)
            with self.subTest(edit=edit), self.assertRaises(ValueError): definition(raw)

    def test_unavailable_professional_entry_is_rejected_before_creating_owner(self):
        c = self.create()
        with self.assertRaisesRegex(ValueError, 'PROFILE_ROLE'):
            self.action('assign', 'unqualified', role='power', base_system=c['id'], question='x', completion='y')

    def test_seven_interface_families_keep_source_and_engineering_levels(self):
        standard = definition(node_raw())['standards']
        self.assertEqual(7, len(standard['interface_consumers']))
        self.assertEqual('NOT_IMPLEMENTED', standard['interface_consumers']['board-package']['status'])
        power = standard['interface_consumers']['power-runtime']
        self.assertEqual(['load_binding'], power['source_gates']); self.assertEqual(['power_service'], power['engineering_gates'])

    def test_lifecycle_tracks_execution_check_failure_and_unknown_recovery(self):
        c = self.create(curve_definition(.01), {'reference.csv': 'x,y\n1,2\n2,3\n', 'observation.csv': 'x,y\n1,5\n2,6\n'})
        self.assertEqual('READY_TO_EXECUTE', self.action('task_state', 's1')['stage'])
        self.action('task_execute', 'run', system_id=c['id'])
        self.assertEqual('READY_TO_VALIDATE', self.action('task_state', 's2')['stage'])
        self.action('validate', 'check', system_id=c['id'])
        s = self.action('task_state', 's3')
        self.assertEqual('DECISION_REQUIRED', s['stage']); self.assertFalse(s['qualification']['task_passed'])

    def test_completed_unregistered_execution_is_recovered_without_reexecution(self):
        c = self.create(curve_definition(), {'reference.csv': 'x,y\n1,2\n2,3\n', 'observation.csv': 'x,y\n1,2\n2,3\n'})
        first = self.action('task_execute', 'run', system_id=c['id'])
        with self.repo.store.connect() as db: db.execute('DELETE FROM design_task_executions WHERE id=?', (first['id'],))
        state = self.action('task_state', 'interrupted')
        self.assertEqual('COMPLETED_NOT_REGISTERED', state['operation_state'])
        self.assertFalse(state['dispatch_allowed']); self.assertIn('task_execute', state['allowed_actions'])
        with patch('bfworld.agentlab.design_lab.repository_task_checks.curve_rows', side_effect=AssertionError('must not rerun')):
            restored = self.action('task_execute', 'recover', system_id=c['id'])
        self.assertEqual(first['id'], restored['id'])
        self.assertEqual('READY_TO_VALIDATE', self.action('task_state', 'restored')['stage'])

    def test_task_state_tracks_same_version_report_and_delivery(self):
        c = self.create(curve_definition(), {'reference.csv': 'x,y\n1,2\n2,3\n', 'observation.csv': 'x,y\n1,2\n2,3\n'})
        self.action('task_execute', 'run', system_id=c['id']); self.action('validate', 'check', system_id=c['id'])
        content = {'conclusion': '配对数据一致。', 'sections': {k: {'text': '两项采样均与目标一致。', 'sources': ['curve_accuracy']}
            for k in ('target_and_conditions', 'curves_and_error', 'conclusion_and_files')}}
        self.action('task_report', 'report', system_id=c['id'], content=json.dumps(content))
        self.assertEqual('READY_TO_DELIVER', self.action('task_state', 'ready')['stage'])
        release = self.action('release', 'release', system_id=c['id'], rationale='scoped review')
        state = self.action('task_state', 'done')
        self.assertEqual('DELIVERED', state['stage']); self.assertEqual(release['id'], state['release_id'])

    def test_legacy_unknown_operation_cannot_be_reissued_after_standardization(self):
        c = self.create(); s = self.repo.system(c['project_id'], c['id'])
        with patch('bfworld.agentlab.design_lab.repository_reference_node.environment', return_value={'tool': 'fixed'}):
            legacy = copy.deepcopy(s); legacy['task_definition'].pop('standards')
            old = descriptor(legacy); new = descriptor(s)
            self.assertNotEqual(old['id'], new['id'])
            root = self.repo.root/'task-executions'/c['project_id']/old['id']; root.mkdir(parents=True)
            (root/'dispatch.json').write_text(canonical({'descriptor': old, 'system_id': c['id']}))
            self.assertEqual(root, pending_execution(self.repo, s))
            status = self.action('task_state', 'unknown')
            self.assertEqual('RECOVERY_REQUIRED', status['stage']); self.assertFalse(status['dispatch_allowed'])

    def test_legacy_success_is_reused_without_changing_its_receipt(self):
        c = self.create(); s = self.repo.system(c['project_id'], c['id'])
        with patch('bfworld.agentlab.design_lab.repository_reference_node.environment', return_value={'tool': 'fixed'}):
            legacy = copy.deepcopy(s); legacy['task_definition'].pop('standards'); desc = descriptor(legacy)
            value = {'project_id': c['project_id'], 'target': c['id'], 'execution_key': desc['id'],
                     'descriptor': desc, 'status': 'SUCCEEDED', 'artifacts': {}, 'metrics': {}}
            value['id'] = 'TX-'+identity(value)
            with self.repo.store.connect() as db:
                db.execute('INSERT INTO design_task_executions VALUES(?,?,?,?)', (value['id'], c['project_id'], c['id'], canonical(value)))
            self.assertEqual(value, current_execution(self.repo, s))


class ProfessionalPhaseTests(unittest.TestCase):
    from test_repository_integration import IntegrationCase as fixture
    setUp = fixture.setUp
    imported = fixture.imported
    action = fixture.action

    def test_old_professional_workspace_cannot_write_or_commit_across_task_revision(self):
        from bfworld.agentlab.design_lab.repository_profiles import profile
        raw = {**curve_definition(), 'profile': 'p01-digital-v1', 'intent': 'reconstruct',
               'acceptance': {g: {'condition': 'current native evidence'} for g in profile('p01-digital-v1')['gates']}}
        self.repo.handle(OWNER, {'action': 'repository_task_define', 'project_id': self.pid, 'operation_id': 'phase',
            'expected_revision': 1, 'definition': raw, 'rationale': 'establish explicit requirements'}, True)
        with self.assertRaisesRegex(ValueError, 'PHASE_REBASE'):
            self.action(self.fw, 'write', operation_id='old-write', path='interfaces/firmware.json', content='{}', expected_sha256=None)
        with self.assertRaisesRegex(ValueError, 'PHASE_REBASE'):
            self.action(self.fw, 'commit', operation_id='old-commit', paths=['project-fw-s132/main.c'], expected_revision=0, rationale='old task')

    def test_audit_profile_rejects_professional_assignment(self):
        from bfworld.agentlab.design_lab.repository_profiles import profile
        raw = {**curve_definition(), 'profile': 'p01-digital-v1', 'intent': 'audit',
               'acceptance': {g: {'condition': 'current native evidence'} for g in profile('p01-digital-v1')['gates']}}
        c = self.repo.handle(OWNER, {'action': 'repository_task_define', 'project_id': self.pid, 'operation_id': 'audit',
            'expected_revision': 1, 'definition': raw, 'rationale': 'read-only audit stage'}, True)
        with self.assertRaisesRegex(PermissionError, 'READ_ONLY'):
            self.action(OWNER, 'assign', operation_id='writer', role='power', base_system=c['id'], question='x', completion='y')


if __name__ == '__main__': unittest.main()
