import copy
import unittest
from bfworld.agentlab.literature_eda import validate_binding


class PaperEdaBindingTests(unittest.TestCase):
    def proofs(self):
        record = {'schema_version': 'bf-paper-eda-binding-v1', 'paper_id': 'P01',
                  'owner': 'pi-one', 'actor': 'Codex environment preparation',
                  'writable': True, 'project_uuid': 'independent-project-01'}
        created = {'actor': record['actor'], 'created': True, 'uuid': record['project_uuid'],
                   'name': 'BF-Literature-P01-Native-test', 'previous_current_project': 'old-door-project'}
        opened = {'actor': record['actor'], 'response': {'ok': True, 'result': {
            'uuid': record['project_uuid'], 'friendlyName': created['name']}}}
        return record, created, opened

    def test_exact_original_paper_owner_and_project(self):
        r, c, o = self.proofs()
        self.assertEqual(r['project_uuid'], validate_binding(r, c, o, 'P01', 'pi-one'))

    def test_paper_owner_operator_and_write_scope_are_required(self):
        for key, value in [('owner', 'pi-two'), ('paper_id', 'P02'), ('writable', False),
                           ('actor', 'Pi'), ('schema_version', 'unverified')]:
            with self.subTest(key=key):
                r, c, o = self.proofs(); r[key] = value
                with self.assertRaisesRegex(ValueError, 'OPERATOR_BINDING'):
                    validate_binding(r, c, o, 'P01', 'pi-one')

    def test_authoritative_new_creation_is_required(self):
        for key, value in [('created', False), ('uuid', 'old-door-project'),
                           ('name', 'BF-Literature-P02-Native-test'), ('actor', 'Pi')]:
            with self.subTest(key=key):
                r, c, o = self.proofs(); c[key] = value
                with self.assertRaisesRegex(ValueError, 'INDEPENDENT_CREATION'):
                    validate_binding(r, c, o, 'P01', 'pi-one')

    def test_preexisting_current_project_cannot_be_relabelled(self):
        r, c, o = self.proofs(); c['previous_current_project'] = r['project_uuid']
        with self.assertRaisesRegex(ValueError, 'INDEPENDENT_CREATION'):
            validate_binding(r, c, o, 'P01', 'pi-one')

    def test_unopened_failed_or_foreign_readback_is_rejected(self):
        for mode in ['failed', 'foreign', 'different_title', 'participant']:
            with self.subTest(mode=mode):
                r, c, o = self.proofs()
                if mode == 'failed': o['response']['ok'] = False
                if mode == 'foreign': o['response']['result']['uuid'] = 'foreign-project'
                if mode == 'different_title': o['response']['result']['friendlyName'] = 'other-title'
                if mode == 'participant': o['actor'] = 'Pi'
                with self.assertRaisesRegex(ValueError, 'OPEN_READBACK'):
                    validate_binding(r, c, o, 'P01', 'pi-one')

    def test_same_project_cannot_be_shared_by_other_paper_owner(self):
        r, c, o = self.proofs()
        with self.assertRaisesRegex(ValueError, 'SHARED_PROJECT'):
            validate_binding(r, c, o, 'P01', 'pi-one', [{'owner': 'pi-two', 'project': r['project_uuid']}])

    def test_exact_same_owner_can_resume_same_binding(self):
        r, c, o = self.proofs()
        self.assertEqual(r['project_uuid'], validate_binding(r, c, o, 'P01', 'pi-one', [
            {'owner': 'pi-one', 'project': r['project_uuid']}]))

    def test_empty_and_executable_project_identifiers_are_rejected(self):
        for value in [None, '', 'bad;command', '../foreign-project']:
            with self.subTest(value=value):
                r, c, o = self.proofs(); r['project_uuid'] = value
                with self.assertRaisesRegex(ValueError, 'PROJECT_IDENTITY'):
                    validate_binding(r, c, o, 'P01', 'pi-one')
