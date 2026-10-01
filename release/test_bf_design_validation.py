"""Integration regressions: final patch order, immutable inputs, fail-closed rebuild."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import validate_bf_design as validation


class IntegrationTests(unittest.TestCase):
    def test_final_method_survives_legacy_rebuild_and_inputs_stay_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'new'
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
