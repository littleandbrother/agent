"""Integration regressions: final patch order, immutable inputs, fail-closed rebuild."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import validate_bf_design as validation


class IntegrationTests(unittest.TestCase):
    def test_children_verify_same_source_manifest_without_credentials(self):
        env = validation.validation_environment({
            'PATH': '/bin', 'HOME': '/tmp/home',
            'BF_INTEGRATION_SOURCE_MANIFEST': '/tmp/current.json',
            'DEEPSEEK_API_KEY': 'must-not-be-inherited',
            'BF_PROVIDER_URL': 'must-not-be-inherited'})
        self.assertEqual(env['BF_INTEGRATION_SOURCE_MANIFEST'], '/tmp/current.json')
        self.assertNotIn('DEEPSEEK_API_KEY', env)
        self.assertNotIn('BF_PROVIDER_URL', env)

    def test_relocation_quotes_and_windows_backslashes_are_literal_values(self):
        for path in ["/tmp/reviewer's copy", r'C:\Users\reviewer\BF Design']:
            source = "ROOT = '/workspace/shared/example'\nCHILD = '/workspace/shared/example/child'\n"
            fixed = validation.relocate_python(source, {'/workspace/shared/example': path})
            namespace = {}
            exec(compile(fixed, '<relocated-path>', 'exec'), namespace)
            self.assertEqual(namespace['ROOT'], path)
            self.assertEqual(namespace['CHILD'], path + '/child')

    def test_unittest_skips_are_not_complete_coverage(self):
        result = validation.test_coverage('Ran 17 tests in 0.1s\n\nOK (skipped=1)\n', 0)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['tests_run'], 17)
        self.assertEqual(result['skipped_count'], 1)
        self.assertEqual(validation.test_coverage('Ran 17 tests in 0.1s\n\nOK\n', 0)['status'], 'passed')

    def test_final_method_survives_legacy_rebuild_and_inputs_stay_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "reviewer's integration"
            sources, service, patch = validation.prepare(output)
            rows = json.loads((patch / 'PATCH-SOURCE-MANIFEST.json').read_text())['files']
            for row in rows:
                if row['path'] != 'src/launcher_overlay.py':
                    self.assertEqual(validation.sha(service / row['path']), row['after_sha256'])
                self.assertEqual((service / row['path']).read_bytes(), (patch / 'changed' / row['path']).read_bytes())
            before = {str(p): validation.sha(p) for p in service.rglob('*') if p.is_file()}
            for directory in [service, sources / 'controlled-integration/layer-01-launcher', sources / 'controlled-integration/layer-02-magnetic-service']:
                result = subprocess.run([sys.executable, '-B', 'build_overlay.py'], cwd=directory, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('LEGACY_GENERATOR_DISABLED', result.stderr)
            self.assertEqual(before, {str(p): validation.sha(p) for p in service.rglob('*') if p.is_file()})
            self.assertEqual(validation.verify_checkpoint(), 636)
            with self.assertRaises(FileExistsError):
                validation.prepare(output)


if __name__ == '__main__':
    unittest.main()
