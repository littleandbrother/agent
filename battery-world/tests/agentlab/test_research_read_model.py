import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from bfworld.agentlab.research.read_model import read


class ResearchReadModel(unittest.TestCase):
    def test_real_isolated_read_does_not_change_study_results(self):
        with tempfile.TemporaryDirectory() as directory:
            value = read(Path(directory))
            self.assertEqual([], value['trials'])
            self.assertEqual([], value['reports'])
            self.assertIn('boundary', value)

    def test_timeout_is_bounded_and_private_child_trace_is_not_returned(self):
        with patch('bfworld.agentlab.research.read_model.subprocess.run', side_effect=subprocess.TimeoutExpired(['test'], 8)) as call:
            with self.assertRaisesRegex(ValueError, 'RESEARCH_READ_TIMEOUT'):
                read(Path('/local/test'))
            self.assertEqual(8, call.call_args.kwargs['timeout'])
            self.assertNotIn('PROVIDER_KEY', call.call_args.kwargs['env'])
        with patch('bfworld.agentlab.research.read_model.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout=b'', stderr=b'private data')):
            with self.assertRaisesRegex(ValueError, '^RESEARCH_READ_FAILED:') as caught:
                read(Path('/local/test'))
            self.assertNotIn('private data', str(caught.exception))
