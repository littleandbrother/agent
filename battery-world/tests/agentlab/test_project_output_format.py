import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from bfworld.agentlab.engineering_projects import run_process


class ProjectOutputFormatTests(unittest.TestCase):
    def test_real_executor_does_not_force_ascii_or_inherit_host_environment(self):
        engineering = Mock()
        proc = Mock(pid=987654321)
        proc.wait.return_value = 0
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            args = ['/opt/homebrew/bin/ngspice', '-b', '-r', directory / 'trace.raw', directory / 'input.cir']
            with patch('bfworld.agentlab.engineering_projects.subprocess.Popen', return_value=proc) as popen, \
                 patch('bfworld.agentlab.engineering_projects.os.killpg'), \
                 patch.dict('os.environ', {'SPICE_ASCIIRAWFILE': '1', 'SECRET_FOR_TEST': 'do-not-inherit'}):
                run_process(engineering, {'owner': 'original-owner', 'id': 'fixture'}, args,
                            directory, directory, [directory], time.monotonic() + 5)
            actual = popen.call_args
            self.assertEqual(list(map(str, args)), actual.args[0][3:])
            self.assertNotIn('SPICE_ASCIIRAWFILE', actual.kwargs['env'])
            self.assertNotIn('SECRET_FOR_TEST', actual.kwargs['env'])
            self.assertEqual(str(directory), actual.kwargs['env']['HOME'])
            events = engineering.event.call_args_list
            self.assertEqual(64 * 1024 * 1024, events[0].args[3]['file_bytes'])
            self.assertEqual('macOS-deny-network-scoped-files', events[0].args[3]['sandbox'])


if __name__ == '__main__':
    unittest.main()
