import copy
import json
from pathlib import Path
import tempfile
import unittest

from bfworld.agentlab import literature_package as package
from bfworld.agentlab.literature_native import evaluate_native, evaluate_manifest, native_phase_context_packet
from bfworld.agentlab.store import identity


class DeliveryMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'pi-original'
        self.root.mkdir()
        (self.root / 'cad').mkdir()
        (self.root / 'delivery').mkdir()
        self.project = {'manifest': {'kind': 'cadquery', 'files': ['main.py']}, 'sources': {'main.py': 'checked source\n'}}
        (self.root / 'cad/project.json').write_text(json.dumps(self.project['manifest'], indent=2))
        (self.root / 'cad/main.py').write_text(self.project['sources']['main.py'])
        (self.root / 'delivery/UNVERIFIED.md').write_text('Core function and physical validation remain unverified.')
        self.assembly = {'revision': 1, 'hashes': {'physical_hash': 'physical'}}
        self.contract = {'paper_id': 'P01', 'source_identity': 'paper-source', 'required_project_kinds': ['cadquery']}
        self.report = {'paper_id': 'P01', 'source_identity': 'paper-source', 'assembly_revision': 1,
                       'assembly_physical_hash': 'physical', 'jobs': [{'job_id': 'old-mixed-eda', 'kind': 'eda-read'}]}
        (self.root / 'native-report.json').write_text(json.dumps(self.report))
        (self.root / 'delivery/manifest.json').write_text('{"old":true}')
        self.job = {'id': 'eng-current', 'owner': 'pi-original', 'engine': 'engineering-project', 'status': 'SUCCEEDED',
                    'parameters': {'project_path': 'cad/project.json'}, 'project': self.project,
                    'project_sha256': identity(self.project), 'assembly': {'revision': 1},
                    'assembly_hashes': self.assembly['hashes'], 'result': {'kind': 'cadquery', 'readback_passed': True,
                    'project_sha256': identity(self.project), 'independent_readback': {'native_valid': True, 'solid_count': 3}}}
        self.index = package.job_index('pi-original', [self.job], self.assembly, 'native-project')
        self.recipe = {'operation_id': 'metadata-001', 'engineering_jobs': ['eng-current'], 'files': [],
                       'unresolved_gates': ['CAD function and complete product not independently accepted']}

    def prepare(self, recipe=None, index=None):
        return package.prepare(self.root, index or self.index, recipe or self.recipe, self.report, self.contract, created=42)

    def test_actual_unchanged_acceptance_consumes_generated_metadata(self):
        old_source = (self.root / 'cad/main.py').read_bytes()
        report, manifest = self.prepare()
        receipt = package.install(self.root, 'metadata-001', report, manifest)
        native = evaluate_native(self.contract, 'pi-original', [self.job], json.loads(report), assembly=self.assembly)
        self.assertEqual('PASS', native['status'], native['problems'])
        checked = evaluate_manifest(self.root, json.loads(manifest), self.contract, self.assembly, native['native_checks'])
        self.assertEqual('PASS', checked['status'], checked['problems'])
        self.assertFalse(native['full_product_passed'])
        self.assertFalse(native['physical_verified'])
        self.assertEqual(old_source, (self.root / 'cad/main.py').read_bytes())
        self.assertEqual(0, receipt['engineering_source_edits'])
        self.assertEqual(2, len(receipt['previous']))
        self.assertEqual(b'{"old":true}', (self.root / receipt['previous'][1]['path']).read_bytes())

    def test_eda_receipt_is_separate_and_does_not_satisfy_native_kind(self):
        (self.root / 'eda.json').write_text(json.dumps({'job_id': 'eda-read', 'owner': 'pi-original',
                                                      'project': 'native-project', 'status': 'SUCCEEDED'}))
        recipe = {**self.recipe, 'eda_receipts': ['eda.json']}
        report, manifest = self.prepare(recipe)
        self.assertEqual(['eng-current'], [j['job_id'] for j in json.loads(report)['jobs']])
        self.assertEqual('eda-read', json.loads(report)['eda_jobs'][0]['job_id'])
        native = evaluate_native({**self.contract, 'required_project_kinds': ['cadquery', 'spice']},
                                  'pi-original', [self.job], json.loads(report), assembly=self.assembly)
        self.assertIn('REQUIRED_NATIVE_PROJECT_MISSING:spice', native['problems'])
        self.assertEqual(1, len(json.loads(manifest)['trusted_jobs']))

    def test_changed_source_cannot_be_hidden_by_a_fresh_hash(self):
        (self.root / 'cad/main.py').write_text('changed after build')
        with self.assertRaisesRegex(ValueError, 'SELECTED_SOURCE_CHANGED'):
            self.prepare()

    def test_changed_project_manifest_is_rejected(self):
        (self.root / 'cad/project.json').write_text('{"kind":"spice"}')
        with self.assertRaisesRegex(ValueError, 'SELECTED_MANIFEST_CHANGED'):
            self.prepare()

    def test_failed_unknown_foreign_and_stale_jobs_are_rejected(self):
        for change in [{'status': 'FAILED'}, {'status': 'UNKNOWN'}, {'owner': 'foreign'},
                       {'assembly_revision': 2}, {'project_identity_valid': False}]:
            with self.subTest(change=change):
                index = copy.deepcopy(self.index)
                index['jobs'][0].update(change)
                with self.assertRaisesRegex(ValueError, 'SELECTED_NATIVE_JOB_UNAVAILABLE'):
                    self.prepare(index=index)

    def test_recipe_cannot_auto_select_or_claim_product_acceptance(self):
        for change in [{'engineering_jobs': []}, {'engineering_jobs': ['eng-current', 'eng-current']},
                       {'engineering_jobs': ['eda-read']}, {'unresolved_gates': []}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepare({**self.recipe, **change})
        report, _ = self.prepare({**self.recipe, 'full_product_passed': True})
        self.assertFalse(json.loads(report)['full_product_passed'])

    def test_file_escape_and_symlinks_never_write_engineering(self):
        (self.root / 'alias').symlink_to(self.root / 'cad', target_is_directory=True)
        for name in ['../outside', '/private/file', 'alias/main.py', 'delivery/manifest.json']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.prepare({**self.recipe, 'files': [name]})
        report, manifest = self.prepare()
        (self.root / 'delivery/manifest.json').unlink()
        (self.root / 'delivery/manifest.json').symlink_to(self.root / 'cad/main.py')
        with self.assertRaisesRegex(ValueError, 'DESTINATION_SYMLINK'):
            package.install(self.root, 'metadata-001', report, manifest)
        self.assertEqual(self.project['sources']['main.py'], (self.root / 'cad/main.py').read_text())

    def test_foreign_workspace_and_repeated_install_do_not_overwrite_history(self):
        index = {**self.index, 'owner': 'foreign'}
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_WORKSPACE_REQUIRED'):
            self.prepare(index=index)
        report, manifest = self.prepare()
        package.install(self.root, 'metadata-001', report, manifest)
        previous = {p.name: p.read_bytes() for p in (self.root / 'delivery/metadata-history').iterdir()}
        with self.assertRaisesRegex(ValueError, 'ALREADY_RECORDED'):
            package.install(self.root, 'metadata-001', report, manifest)
        self.assertEqual(previous, {p.name: p.read_bytes() for p in (self.root / 'delivery/metadata-history').iterdir()})

    def test_new_native_job_gets_a_fresh_live_index_without_workbench_query(self):
        phase = {'schema_version': 'bf-paper-recovery-phase-v1', 'owner': 'pi-original', 'paper_id': 'P01',
                 'phase': 'engineering-review', 'task_file': 'phase.json', 'task_sha256': '2' * 64}
        generic = {'owner': 'pi-original', **self.assembly}
        binding = {'owner': 'pi-original', 'paper_id': 'P01', 'project_uuid': 'native-project'}
        first = native_phase_context_packet(self.root, phase, binding, generic, [self.job])
        new = {**self.job, 'id': 'eng-new'}
        second = native_phase_context_packet(self.root, phase, binding, generic, [new, self.job])
        old_ref, new_ref = first['delivery_job_index_reference'], second['delivery_job_index_reference']
        self.assertNotEqual(old_ref['path'], new_ref['path'])
        self.assertEqual(1, len(json.loads((self.root / old_ref['path']).read_text())['jobs']))
        self.assertEqual(2, len(json.loads((self.root / new_ref['path']).read_text())['jobs']))
        self.assertFalse(second['full_product_passed'])

