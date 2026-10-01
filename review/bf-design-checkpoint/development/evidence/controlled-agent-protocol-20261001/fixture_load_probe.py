#!/usr/bin/env python3
"""Launch only the bundled trusted fixtures, never arbitrary participant code.

A clean Python process is a load-proof fixture, NOT a qualified sandbox or
substitute for the actual macOS participant launcher.
"""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
if len(sys.argv) != 3 or sys.argv[1] not in ('h0', 'h1', 'broken', 'call_failed'):
    raise SystemExit('Only bundled trusted h0/h1/broken/call_failed fixtures are accepted')
source = root / 'fixtures' / (sys.argv[1] + '.py')
data = source.read_bytes(); h = hashlib.sha256(data).hexdigest()
spec = importlib.util.spec_from_file_location('trusted_load_fixture', source)
module = importlib.util.module_from_spec(spec)

# Execute the exact prehashed bytes, never timestamp-based bytecode cache.
exec(compile(data, str(source), "exec"), module.__dict__)
output = module.plan({'value': 3})
canonical = json.dumps(output, sort_keys=True, separators=(',', ':')).encode()
print(json.dumps({'harness_source_hash': h, 'harness_build_hash': h,
 'controller_hash': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'nonce': sys.argv[2], 'entrypoint': 'plan', 'fresh_process': True,
 'clean_context': bool(sys.flags.isolated and sys.flags.no_site),
 'post_import': True, 'invoked': True, 'pid': os.getpid(),
 'loaded_modules': {'trusted_load_fixture': h}, 'invocation_output_hash': hashlib.sha256(canonical).hexdigest(),
 'fixture_output': output, 'evidence_kind': 'trusted-synthetic-load-fixture',
 'participant_runtime_qualified': False}))
