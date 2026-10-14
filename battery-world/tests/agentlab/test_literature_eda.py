import copy
import unittest
import json
import subprocess
from pathlib import Path
from unittest.mock import patch
from bfworld.agentlab.literature_eda import validate_binding, live_project_probe, open_local_destination


class PaperEdaBindingTests(unittest.TestCase):
    def test_existing_local_desktop_connect_requires_no_headless_open(self):
        policy={'host':'desktop','transport':'easyeda-typed-v1','modes':['half-offline'],'wait_s':30}
        window={'windowId':'exact-desktop','context':{'projectUuid':'exact-project'}}
        with patch('bfworld.agentlab.literature_eda.local_destination',return_value=Path('/public/exact.eprj3')), \
             patch('bfworld.agentlab.eda_cli.ready_window',return_value=window) as ready, \
             patch('bfworld.agentlab.literature_eda.subprocess.run') as run:
            self.assertEqual(open_local_destination({}, {}, 'exact-project',policy),(window,None))
            ready.assert_called_once_with('exact-project',policy,0);run.assert_not_called()

    def test_missing_desktop_and_readonly_native_preflight_never_open_another_backend(self):
        for transport,expected in [('easyeda-typed-v1','DESKTOP_CONNECT_PROJECT_NOT_OPEN'),('native-cli-v1','LOCAL_PROJECT_NOT_OPEN')]:
            policy={'host':'desktop','transport':transport,'wait_s':30}
            with self.subTest(transport=transport), \
                 patch('bfworld.agentlab.literature_eda.local_destination',return_value=Path('/public/exact.eprj3')), \
                 patch('bfworld.agentlab.eda_cli.ready_window',side_effect=ValueError('EDA_BOUND_PROJECT_NOT_OPEN')), \
                 patch('bfworld.agentlab.literature_eda.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError,expected):
                    open_local_destination({}, {}, 'exact-project',policy,allow_open_missing=False)
                run.assert_not_called()

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

    def test_transport_error_preserves_cause_without_claiming_foreign_identity(self):
        for response in [subprocess.CompletedProcess([], 1, json.dumps({'ok': False, 'error': {'code': 'NATIVE_DIAGNOSTIC_TIMEOUT', 'message': 'readonly timeout'}}), ''),
                         subprocess.TimeoutExpired(['project', 'info'], 20)]:
            with self.subTest(response=type(response).__name__):
                options = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
                with patch('bfworld.agentlab.literature_eda.subprocess.run', **options):
                    with self.assertRaises(ValueError) as caught:
                        live_project_probe('cli', 'exact-window', 'exact-project', 'exact-name')
                self.assertIn('ACTION_NOT_SENT', str(caught.exception))
                self.assertNotIn('MISMATCH', str(caught.exception))
                self.assertRegex(str(caught.exception), 'TIMEOUT|readonly timeout')

    def test_fresh_correct_read_passes_but_foreign_failed_and_malformed_do_not(self):
        good = {'ok': True, 'result': {'uuid': 'exact-project', 'friendlyName': 'exact-name'}}
        with patch('bfworld.agentlab.literature_eda.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(good), '')) as run:
            self.assertEqual(live_project_probe('cli', 'exact-window', 'exact-project', 'exact-name'), good)
            self.assertEqual(run.call_args.kwargs['timeout'], 20)
            self.assertEqual(run.call_count, 1)
        for output, code, expected in [(json.dumps({**good, 'result': {'uuid': 'foreign', 'friendlyName': 'exact-name'}}), 0, 'MISMATCH'),
                                      (json.dumps(good), 1, 'UNAVAILABLE'), ('unanswered', 0, 'RESPONSE_INVALID'), ('[]', 0, 'UNAVAILABLE')]:
            with self.subTest(output=output), patch('bfworld.agentlab.literature_eda.subprocess.run', return_value=subprocess.CompletedProcess([], code, output, 'transport failed')):
                with self.assertRaisesRegex(ValueError, expected):
                    live_project_probe('cli', 'exact-window', 'exact-project', 'exact-name')
