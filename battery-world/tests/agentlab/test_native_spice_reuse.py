import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from bfworld.agentlab.literature_native import evaluate_native, evaluate_manifest
from bfworld.agentlab.store import identity


class NativeSpiceReuseTests(unittest.TestCase):
    def fixture(self, root):
        workspace = root / 'runtime/participants/pi-own'
        (workspace / 'spice').mkdir(parents=True)
        manifest = {'kind': 'spice', 'files': ['stage.cir'], 'entrypoint': 'stage.cir', 'interfaces': {'source': 'explicit fixed test source'}}
        source = 'fixed circuit model\n'
        (workspace / 'spice/project.json').write_text(json.dumps(manifest))
        (workspace / 'spice/stage.cir').write_text(source)
        project = {'manifest': manifest, 'sources': {'stage.cir': source}}
        output = root / 'runtime/engineering/eng-own/project-trace.raw'
        output.parent.mkdir(parents=True)
        output.write_text('immutable test output\n')
        energy = {'load': 47}
        old = {'owner': 'pi-own', 'revision': 1, 'hashes': {'physical_hash': 'old'}, 'payload': {'energy': energy}}
        assembly = {'owner': 'pi-own', 'revision': 2, 'hashes': {'physical_hash': 'new'}, 'payload': {'energy': copy.deepcopy(energy)}}
        job = {'id': 'eng-own', 'owner': 'pi-own', 'engine': 'engineering-project', 'status': 'SUCCEEDED',
               'project': project, 'project_sha256': identity(project), 'parameters': {'project_path': 'spice/project.json'},
               'assembly': old, 'assembly_hashes': old['hashes'],
               'result': {'kind': 'spice', 'readback_passed': True, 'project_sha256': identity(project),
                          'independent_readback': {'finite_values': True, 'points': 3},
                          'outputs': [{'name': output.name, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}]}}
        report = {'schema_version': 'bf-paper-native-report-v1', 'paper_id': 'P01', 'source_identity': 'source',
                  'assembly_revision': 2, 'assembly_physical_hash': 'new', 'full_product_passed': False, 'physical_verified': False,
                  'gaps': ['source calibration and joint applicability unverified'],
                  'jobs': [{'job_id': 'eng-own', 'kind': 'spice', 'reused_unchanged': True}]}
        return workspace, job, report, assembly

    def run_check(self, root, job, report, assembly):
        return evaluate_native({'paper_id': 'P01', 'source_identity': 'source', 'required_project_kinds': ['spice']},
                               'pi-own', [job], report, root, assembly)

    def test_explicit_exact_spice_subset_reuse_retains_old_and_new_identities(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); _, job, report, assembly = self.fixture(root)
            before = copy.deepcopy(job)
            value = self.run_check(root, job, report, assembly)
            self.assertEqual('PASS', value['status'])
            c = value['native_checks'][0]
            self.assertEqual(1, c['assembly_revision'])
            self.assertEqual('old', c['assembly_physical_hash'])
            reuse = c['model_input_reuse']
            self.assertEqual(2, reuse['delivery_assembly_revision'])
            self.assertTrue(reuse['model_subset_only'])
            self.assertFalse(reuse['assembly_applicability_verified'])
            self.assertFalse(c['functional_passed'])
            self.assertFalse(value['full_product_passed'])
            self.assertFalse(value['physical_verified'])
            self.assertEqual(before, job)

    def test_current_manifest_can_bind_the_original_model_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); workspace, job, report, assembly = self.fixture(root)
            checks = self.run_check(root, job, report, assembly)['native_checks']
            files = [{'path': p, 'sha256': hashlib.sha256((workspace / p).read_bytes()).hexdigest()}
                     for p in ['spice/project.json', 'spice/stage.cir']]
            manifest = {'schema_version': 'bf-paper-native-delivery-v1', 'paper_id': 'P01', 'source_identity': 'source',
                        'assembly_revision': 2, 'assembly_physical_hash': 'new', 'files': files,
                        'trusted_jobs': [{'job_id': 'eng-own', 'project_sha256': job['project_sha256']}],
                        'unresolved_gates': ['model subset only; joint applicability unverified']}
            value = evaluate_manifest(workspace, manifest, {'paper_id': 'P01', 'source_identity': 'source'}, assembly, checks)
            self.assertEqual('PASS', value['status'])

    def test_flag_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); _, job, report, assembly = self.fixture(root)
            report['jobs'][0].pop('reused_unchanged')
            self.assertEqual('FAIL', self.run_check(root, job, report, assembly)['status'])

    def test_changed_current_circuit_cannot_reuse_old_numeric_result(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); workspace, job, report, assembly = self.fixture(root)
            (workspace / 'spice/stage.cir').write_text('changed source\n')
            self.assertEqual('FAIL', self.run_check(root, job, report, assembly)['status'])

    def test_changed_manifest_interface_cannot_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); workspace, job, report, assembly = self.fixture(root)
            value = json.loads((workspace / 'spice/project.json').read_text())
            value['interfaces']['source'] = 'different source'
            (workspace / 'spice/project.json').write_text(json.dumps(value))
            self.assertEqual('FAIL', self.run_check(root, job, report, assembly)['status'])

    def test_changed_energy_condition_rejects_identical_netlist(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); _, job, report, assembly = self.fixture(root)
            assembly['payload']['energy']['load'] = 100
            self.assertEqual('FAIL', self.run_check(root, job, report, assembly)['status'])

    def test_missing_declared_energy_and_original_hash_reject(self):
        for field in ['energy', 'hashes']:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                root = Path(d); _, job, report, assembly = self.fixture(root)
                if field == 'energy':job['assembly']['payload'].pop('energy')
                else:job['assembly'].pop('hashes')
                self.assertEqual('FAIL', self.run_check(root, job, report, assembly)['status'])

    def test_other_owner_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); _, job, report, assembly = self.fixture(root)
            job['owner'] = 'other'
            self.assertIn('NATIVE_JOB_OWNER', self.run_check(root, job, report, assembly)['problems'])

    def test_corrupt_output_is_rejected_even_with_current_identical_input(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); _, job, report, assembly = self.fixture(root)
            (root / 'runtime/engineering/eng-own/project-trace.raw').write_text('changed output')
            self.assertIn('NATIVE_OUTPUT_HASH', self.run_check(root, job, report, assembly)['problems'])

    def test_stale_cad_or_firmware_cannot_use_spice_reuse_flag(self):
        for kind in ['cadquery', 'firmware-stm32l031']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                root = Path(d); _, job, report, assembly = self.fixture(root)
                job['result']['kind'] = kind
                report['jobs'][0]['kind'] = kind
                self.assertEqual('FAIL', self.run_check(root, job, report, assembly)['status'])

    def test_missing_original_payload_or_root_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); _, job, report, assembly = self.fixture(root)
            self.assertEqual('FAIL', self.run_check(None, job, report, assembly)['status'])
            job['assembly'].pop('payload')
            self.assertEqual('FAIL', self.run_check(root, job, report, assembly)['status'])

    def test_path_escape_or_symlink_cannot_replace_original_source(self):
        for condition in ['escape', 'symlink']:
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as d:
                root = Path(d); workspace, job, report, assembly = self.fixture(root)
                if condition == 'escape':job['parameters']['project_path'] = '../pi-other/spice/project.json'
                else:
                    p = workspace / 'spice/stage.cir'
                    p.rename(p.with_suffix('.backup'))
                    p.symlink_to(p.with_suffix('.backup'))
                self.assertEqual('FAIL', self.run_check(root, job, report, assembly)['status'])

if __name__ == '__main__':
    unittest.main()
