import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from bfworld.agentlab.design_lab import report_runtime as runtime


class ReportRuntimeTests(unittest.TestCase):
    def test_current_interpreter_with_dependencies_never_uses_desktop_path(self):
        with patch.dict(os.environ, {'BF_REPORT_PYTHON': ''}), \
                patch.object(runtime.importlib.util, 'find_spec', return_value=object()), \
                patch.object(runtime.subprocess, 'run') as run:
            self.assertEqual(sys.executable, runtime.report_python())
        run.assert_not_called()

    def test_explicit_runtime_is_probed_and_takes_priority(self):
        with patch.dict(os.environ, {'BF_REPORT_PYTHON': '/configured/pdf python'}), \
                patch.object(runtime.shutil, 'which', return_value='/configured/pdf python'), \
                patch.object(runtime.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual('/configured/pdf python', runtime.report_python())
        self.assertEqual(['/configured/pdf python', '-c', 'import reportlab, pypdf'], run.call_args.args[0])

    def test_invalid_explicit_runtime_does_not_fall_back(self):
        with patch.dict(os.environ, {'BF_REPORT_PYTHON': '/missing/python'}), \
                patch.object(runtime.shutil, 'which', return_value=None), \
                patch.object(runtime.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'REPORT_PYTHON_UNAVAILABLE'):
                runtime.report_python()
        run.assert_not_called()

    def test_explicit_runtime_requires_both_pdf_dependencies(self):
        with patch.dict(os.environ, {'BF_REPORT_PYTHON': sys.executable}), \
                patch.object(runtime.shutil, 'which', return_value=sys.executable), \
                patch.object(runtime.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaisesRegex(ValueError, 'REPORT_DEPENDENCIES_MISSING'):
                runtime.report_python()

    def test_existing_desktop_compatibility_runtime_is_probed(self):
        with patch.dict(os.environ, {'BF_REPORT_PYTHON': ''}), \
                patch.object(runtime.importlib.util, 'find_spec', return_value=None), \
                patch.object(Path, 'is_file', return_value=True), \
                patch.object(runtime.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            self.assertIn('codex-primary-runtime', runtime.report_python())

    def test_missing_runtime_has_an_explicit_dependency_error(self):
        with patch.dict(os.environ, {'BF_REPORT_PYTHON': ''}), \
                patch.object(runtime.importlib.util, 'find_spec', return_value=None), \
                patch.object(Path, 'is_file', return_value=False):
            with self.assertRaisesRegex(ValueError, 'REPORT_DEPENDENCIES_MISSING'):
                runtime.report_python()


if __name__ == '__main__':
    unittest.main()
