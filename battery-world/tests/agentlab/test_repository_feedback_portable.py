"""Compile trusted reference fixtures on CI to check actual C reset semantics.

Only fixed repository test sources run here. Participant execution continues to
require the macOS sandbox; its native integration is tested on the local worker.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from bfworld.agentlab.design_lab import feedback_program
from bfworld.agentlab.design_lab.repository_feedback_contract import HEADER
from test_repository_feedback import FILES, RAW


class PortableProgramTests(unittest.TestCase):
    def compile_fixture(self, root, source):
        cc = shutil.which('cc')
        if cc is None:
            self.skipTest('trusted C fixture requires a host C compiler')
        (root/'main.c').write_text(source)
        (root/'feedback.h').write_text(HEADER)
        (root/'runner.c').write_text(feedback_program.RUNNER)
        binary = root/'fixture'
        subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
            'main.c', 'runner.c', '-o', str(binary)], cwd=root, check=True, capture_output=True, text=True)
        return binary

    @staticmethod
    def trusted_fixture_process(command, root, timeout):
        return subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=timeout)

    def test_compiled_brownout_resets_sequence_and_waits_for_new_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = self.compile_fixture(root, FILES['firmware/main.c'])
            grid = np.linspace(0, .7, 701)
            supply = np.full(len(grid), 2.5)
            supply[(grid >= .262) & (grid < .4)] = 0
            with patch.object(feedback_program, 'sandbox_run', side_effect=self.trusted_fixture_process):
                rows, _, events = feedback_program.execute_program(
                    root/'application', binary, RAW['scenario'], grid, supply, supply)
            self.assertEqual(2, int(rows[-1, 5]))
            self.assertTrue(np.all(rows[(grid[:-1] >= .262) & (grid[:-1] < .4), 6] == 0))
            tx = [event for event in events if event['state'] == 'tx']
            self.assertFalse(tx[0]['completed'])
            self.assertEqual(1, tx[0]['boot'])
            self.assertTrue(tx[-1]['completed'])
            self.assertEqual((2, 1), (tx[-1]['boot'], tx[-1]['seq']))
            self.assertGreaterEqual(tx[-1]['t_s'], .66 - 1e-10)

    def test_compiled_powered_program_cannot_request_off_leakage(self):
        source = FILES['firmware/main.c'].replace('int bf_step(', 'int reference_step(')
        source += '\nint bf_step(double t,double dt,double v,int pg) { (void)t;(void)dt;(void)v;(void)pg;return BF_OFF; }\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = self.compile_fixture(root, source)
            grid = np.array([0., .001, .002])
            supply = np.full(len(grid), 2.5)
            with patch.object(feedback_program, 'sandbox_run', side_effect=self.trusted_fixture_process):
                with self.assertRaisesRegex(ValueError, 'FEEDBACK_PROGRAM_EXIT'):
                    feedback_program.execute_program(root/'application', binary, RAW['scenario'], grid, supply, supply)


if __name__ == '__main__':
    unittest.main()
