#!/usr/bin/env python3
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'packages/python/bfworld/src'))
from bfworld.agentlab.runtime_config import CAD
# The historical CLI entry uses the same interpreter as the resident launcher.
# Resolve both paths: venv Python executables may share a framework binary.
if Path(sys.prefix).resolve() != CAD.parent.parent.resolve() and CAD.is_file():
    os.execv(str(CAD), [str(CAD), __file__, *sys.argv[1:]])
from bfworld.agentlab.server import main
main()
