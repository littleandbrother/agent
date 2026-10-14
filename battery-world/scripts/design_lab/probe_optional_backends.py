#!/usr/bin/env python3
"""Test isolated backend APIs without touching participant engineering."""
import argparse
import fcntl
from pathlib import Path
import sys
import time

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.native_backends import probe_receipt
from bfworld.agentlab.runtime_config import RUNTIME_ROOT

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path)
args = parser.parse_args()
out = args.output or APP / 'docs/agentlab/executable-lab-20261012' / ('backend-probes-' + str(time.time_ns()))
with (RUNTIME_ROOT / 'design-native.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    report = probe_receipt(out)
print(out / 'backend-probes.json')
raise SystemExit(0 if report['ngspice_shared']['passed'] and report['renode_startup']['passed'] else 1)
