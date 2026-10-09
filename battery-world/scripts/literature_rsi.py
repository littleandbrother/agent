#!/usr/bin/env python3
"""Prepare/audit the bounded literature study; execution reuses the Pi runtime."""
import argparse
import json
from pathlib import Path
from bfworld.agentlab.literature_rsi import execute, prepare, verify_prepared

parser = argparse.ArgumentParser()
parser.add_argument('command', choices=['prepare', 'audit', 'run'])
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--harness', type=Path)
parser.add_argument('--ledger-home', type=Path, help='Explicit existing study runtime; retains every historical fee and reservation.')
args = parser.parse_args()
if args.command == 'prepare':
    if args.harness is None:
        parser.error('--harness is required for prepare')
    result = prepare(args.root, args.harness)
elif args.command == 'audit':
    result = verify_prepared(args.root)
else:
    result = execute(args.root, args.ledger_home)
print(json.dumps({k: result.get(k) for k in ['schema_version', 'harness_identity', 'no_agent_reference', 'claim']}, ensure_ascii=False, indent=2))
