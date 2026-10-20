#!/usr/bin/env python3
"""Read-only final checks, streaming ledger rows to avoid large RAM/swap spikes."""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import subprocess
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LOCAL = Path.home() / '.local/share'


def file_hash(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def table(c, name):
    c.row_factory = sqlite3.Row
    h = hashlib.sha256(b'[')
    count = 0
    for row in c.execute('SELECT * FROM ' + name + ' ORDER BY rowid'):
        if count:
            h.update(b',')
        h.update(json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
        count += 1
    h.update(b']')
    return {'rows': count, 'sha256': h.hexdigest()}


def main():
    before = json.loads((HERE / 'protected-before.json').read_text())
    protected = {}
    for label, path in [('v2', LOCAL / 'bf-agent-architecture-v2/workbench/state/workbench.sqlite'),
                        ('production', LOCAL / 'bf-agent-runtime/workbench/state/workbench.sqlite')]:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as c:
            c.execute('PRAGMA query_only=ON')
            c.execute('BEGIN')
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            protected[label] = {n: table(c, n) for n in ['conversations', 'model_requests', 'design_projects'] if n in names}
    profile = json.loads((LOCAL / 'bf-agent-architecture-v2/profile.json').read_text())
    protected['baseline_manifest_sha256'] = file_hash(Path(profile['baseline']['path']) / 'manifest.json')
    assert protected == before['protected'], 'protected production/V2 state changed'
    row = {'status': 'PASS', 'protected': protected, 'model_requests_started': 0, 'native_dispatches': 0}
    for label, path in [('historical', LOCAL / 'bf-agent-runtime/reference-cases/literature-rsi-20261008/runtime/state/workbench.sqlite'),
                        ('campaign', LOCAL / 'bf-campaign-20261019-s0/workbench/state/workbench.sqlite')]:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as c:
            result = table(c, 'model_requests')
            counts = [list(x) for x in c.execute('SELECT status,count(*) FROM model_requests GROUP BY status')]
            assert result['sha256'] == before[label]['sha256'], label
            assert result['rows'] == before[label]['requests'] and counts == before[label]['status_counts']
            row[label] = {**result, 'status_counts': counts}
    endpoints = {}
    for port in [8768, 8870, 8980]:
        with urllib.request.urlopen('http://127.0.0.1:' + str(port), timeout=5) as response:
            endpoints[str(port)] = response.status
        assert endpoints[str(port)] == 200
    row['endpoints'] = endpoints
    source = ROOT / 'workbench/bf-campaign-s0-20261019'
    deleted = [x['path'] for x in json.loads((HERE / 'retirement.json').read_text())]
    deleted += [x['path'] for x in json.loads((HERE / 'environments-retired.json').read_text())]
    broken = []
    for directory, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__']]
        for name in dirs + files:
            p = Path(directory) / name
            if p.is_symlink():
                resolved = str(p.resolve())
                if any(resolved == t or resolved.startswith(t + '/') for t in deleted):
                    broken.append(str(p))
    assert not broken, broken
    row['active_source_links_to_retired_paths'] = broken
    scope = ['battery-world/PROJECT.yaml', 'battery-world/docs/PROGRESS.md', 'battery-world/docs/SESSION-HANDOFF.md']
    q = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(source), 'diff',
                        '--no-ext-diff', '--no-textconv', '--check', '--', *scope],
                       capture_output=True, text=True, timeout=20)
    assert q.returncode == 0, q.stdout + q.stderr
    row['source_diff_check'] = 'PASS (maintenance state paths)'
    row['source_diff_scope'] = scope
    row['verification_limitations'] = ['Initial unscoped git diff --check timed out after 20s; bounded maintenance-path review used. Root all-project init not run.']
    row['source_head'] = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    assert row['source_head'] == '317d40fef0137d3c1ad1873e53c3e9968b31200a'
    (HERE / 'verification.json').write_text(json.dumps(row, indent=2) + '\n')
    print(json.dumps({k:v for k,v in row.items() if k != 'protected'}))


if __name__ == '__main__':
    main()
