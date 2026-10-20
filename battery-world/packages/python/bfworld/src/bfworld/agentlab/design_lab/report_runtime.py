"""Resolve a PDF interpreter for both server and standalone installations."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys


def report_python():
    override = os.environ.get('BF_REPORT_PYTHON')
    if override:
        executable = shutil.which(override)
        if executable is None:
            raise ValueError('REPORT_PYTHON_UNAVAILABLE:' + override)
        candidates = [executable]
    elif all(importlib.util.find_spec(name) is not None for name in ('reportlab', 'pypdf')):
        return sys.executable
    else:
        # Compatibility with existing desktop deployments whose CAD interpreter
        # is separate from the optional bundled PDF interpreter.
        bundled = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
        candidates = [str(bundled)] if bundled.is_file() else []
    for executable in candidates:
        result = subprocess.run([executable, '-c', 'import reportlab, pypdf'],
            capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return executable
    raise ValueError('REPORT_DEPENDENCIES_MISSING:reportlab,pypdf')
