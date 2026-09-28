#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'packages/python/bfworld/src'))
from bfworld.agentlab.server import main
main()
