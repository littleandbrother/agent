from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]

class EngineeringWorkspaceProjectionTests(unittest.TestCase):
    def test_projection_negative_controls(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js unavailable')
        subprocess.run([node, str(ROOT / 'tests/agentlab/test_engineering_workspace.cjs')], check=True, capture_output=True, timeout=20)

    def test_script_syntax(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js unavailable')
        for file in ['engineering-workspace-model.js', 'engineering-workspace.js', 'app.js', 'studio.js']:
            subprocess.run([node, '--check', str(ROOT / 'apps/agent-studio' / file)], check=True, capture_output=True, timeout=20)

if __name__ == '__main__':
    unittest.main()
