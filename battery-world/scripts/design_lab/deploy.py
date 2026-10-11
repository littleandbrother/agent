#!/usr/bin/env python3
"""Deploy the scoped BF implementation only after existing services drain.

Database inspection is read-only. No second Workbench is constructed for audit.
The one intentional server launch uses the existing original state directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.request

APP = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, default=Path('/Users/depengsu/.local/share/bf-agent-runtime'))
parser.add_argument('--port', type=int, default=8768)
parser.add_argument('--apply', action='store_true')
parser.add_argument('--toolchain', type=Path, help='Separately qualified native ARM compiler manifest; leaves old runtime config intact')
args = parser.parse_args()
state = args.runtime / 'workbench/state'
paper_state = args.runtime / 'reference-cases/literature-rsi-20261008/runtime/state'
out = APP / 'docs/agentlab/refactor-r0-r2-20261011/deployment'
out.mkdir(parents=True, exist_ok=True)
def inventory():
    result = {}
    for root in (state, paper_state):
        with sqlite3.connect('file:' + str(root / 'workbench.sqlite') + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            records = {}
            for name in ('model_requests', 'engineering_jobs', 'jobs', 'conversations'):
                if name in tables:
                    rows = [dict(r) for r in db.execute('SELECT * FROM ' + name + ' ORDER BY id')]
                    encoded = json.dumps(rows, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
                    records[name] = {'count': len(rows), 'sha256': hashlib.sha256(encoded).hexdigest()}
            for name in ('jobs', 'engineering_jobs', 'design_operations'):
                if name in tables and db.execute('SELECT 1 FROM ' + name + " WHERE status IN ('QUEUED','RUNNING')").fetchone():
                    raise RuntimeError('DEPLOY_REQUIRES_DRAINED_' + name)
            if db.execute("SELECT 1 FROM conversations WHERE status IN ('STARTING','RUNNING')").fetchone():
                raise RuntimeError('DEPLOY_REQUIRES_DRAINED_CONVERSATIONS')
            result[str(root)] = records
    return result
before = inventory()
active = json.loads((state / 'active-runtime.json').read_text())
command = subprocess.run(['ps', '-ww', '-p', str(active['pid']), '-o', 'command='], capture_output=True, text=True).stdout.strip()
listening = socket.socket()
occupied = listening.connect_ex(('127.0.0.1', args.port)) == 0
listening.close()
if occupied and ('bfworld.agentlab.server' not in command or str(state) not in command):
    raise RuntimeError('UNIDENTIFIED_SERVER_ON_PORT')
if not args.apply:
    print(json.dumps({'ready': True, 'existing_server': command, 'would_launch': str(APP), 'rows': before}))
    raise SystemExit(0)
if occupied:
    os.kill(active['pid'], signal.SIGTERM)
    for _ in range(100):
        check = socket.socket()
        closed = check.connect_ex(('127.0.0.1', args.port)) != 0
        check.close()
        if closed:
            break
        time.sleep(.1)
    else:
        raise RuntimeError('EXISTING_SERVER_DID_NOT_DRAIN')
env = {**os.environ, 'PYTHONPATH': str(APP / 'packages/python/bfworld/src'), 'BF_PI_ROOT': str(APP.parent / 'pi-bf-aiot')}
toolchain = None
if args.toolchain:
    toolchain = json.loads(args.toolchain.read_text())
    compiler = Path(toolchain['compiler_path'])
    if hashlib.sha256(compiler.read_bytes()).hexdigest() != toolchain['compiler_sha256']:
        raise RuntimeError('DEPLOY_COMPILER_PIN_MISMATCH')
    env.update(BF_ARM_GCC=str(compiler), ARM_GCC=str(compiler))
argv = [str(APP / '.venv/bin/python'), '-m', 'bfworld.agentlab.server', '--root', str(state), '--port', str(args.port)]
with (out / 'server.log').open('a') as log:
    process = subprocess.Popen(argv, cwd=APP, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for _ in range(100):
    if process.poll() is not None:
        raise RuntimeError('NEW_SERVER_EXITED_' + str(process.returncode))
    try:
        with opener.open('http://127.0.0.1:' + str(args.port) + '/', timeout=2) as response:
            main = response.read()
        break
    except (OSError, urllib.error.URLError):
        time.sleep(.1)
else:
    raise RuntimeError('NEW_SERVER_NOT_READY')
after = inventory()
receipt = {'schema_version': 'bf-design-rollout-v1', 'old_runtime': active,
           'new_runtime': json.loads((state / 'active-runtime.json').read_text()), 'source': str(APP),
           'pi_source': str(APP.parent / 'pi-bf-aiot'), 'argv': argv, 'before': before, 'after': after,
           'old_rows_unchanged': before == after, 'time': time.time(),
           'native_toolchain_manifest': str(args.toolchain) if args.toolchain else None,
           'native_compiler_sha256': toolchain['compiler_sha256'] if toolchain else None,
           'environment_overrides': {k: env[k] for k in ('BF_PI_ROOT','BF_ARM_GCC') if k in env},
           'main_ui_design_assets_absent': b'design-lab.css' not in main and b'design-lab.js' not in main,
           'scope': 'One original Workbench; additive C backend. Original paper owners not dispatched.'}
path = out / ('rollout-' + str(time.time_ns()) + '.json')
path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
if before != after:
    raise RuntimeError('ORIGINAL_LEDGER_OR_ENGINEERING_ROWS_CHANGED_DURING_ROLLOUT')
print(json.dumps({'pid': process.pid, 'old_rows_unchanged': True, 'receipt': str(path), 'ui_restored': receipt['main_ui_design_assets_absent']}))
