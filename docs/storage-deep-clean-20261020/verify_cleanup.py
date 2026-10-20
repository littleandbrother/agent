#!/usr/bin/env python3
"""Read-only preservation audit and bounded real-archive restore sampling."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCAL = Path.home() / '.local/share'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    result = {'status': 'IN_PROGRESS', 'paid_model_requests': 0, 'new_native_solves': 0}
    before = json.loads((HERE / 'protected-before.json').read_text())
    protected = {}
    for label, path in [
        ('production', LOCAL / 'bf-agent-runtime/workbench/state/workbench.sqlite'),
        ('v2', LOCAL / 'bf-agent-architecture-v2/workbench/state/workbench.sqlite'),
        ('historical', LOCAL / 'bf-agent-runtime/reference-cases/literature-rsi-20261008/runtime/state/workbench.sqlite'),
        ('campaign', LOCAL / 'bf-campaign-20261019-s0/workbench/state/workbench.sqlite'),
    ]:
        current = {}
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as c:
            c.execute('PRAGMA query_only=ON'); c.execute('BEGIN'); c.row_factory = sqlite3.Row
            for table in [n for n in before[label] if n != 'status_counts']:
                h = hashlib.sha256(); count = 0
                for row in c.execute('SELECT * FROM ' + table + ' ORDER BY rowid'):
                    h.update(json.dumps(dict(row), ensure_ascii=False, sort_keys=True,
                                        separators=(',', ':')).encode()); h.update(b'\n'); count += 1
                current[table] = {'rows': count, 'sha256': h.hexdigest()}
            current['status_counts'] = [list(x) for x in c.execute('SELECT status,count(*) FROM model_requests GROUP BY status')]
            assert current == before[label], 'PROTECTED_DATABASE_CHANGED: ' + label
            protected[label] = current
        print('Protected DB unchanged:', label, flush=True)
    result['protected'] = protected
    baseline = LOCAL / 'bf-agent-baselines/bf-p01-demo-20261014'
    manifest = baseline / 'manifest.json'
    assert sha(manifest) == before['baseline_manifest_sha256']
    baseline_manifest = json.loads(manifest.read_text())
    for name, entry in baseline_manifest['files'].items():
        path = baseline / name
        assert path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], 'BASELINE_FILE_CHANGED: ' + name
    result['baseline'] = {'files': len(baseline_manifest['files']), 'all_hashes': 'PASS',
                          'manifest_sha256': sha(manifest)}
    print('Baseline full readback:', result['baseline']['files'], flush=True)
    result['delivery'] = []
    for path in (LOCAL / 'bf-agent-architecture-v2/workbench/design-lab/repository/node-realizations').glob('*/manifest.json'):
        m = json.loads(path.read_text())
        for name, entry in m['outputs'].items():
            output = path.parent / name
            assert output.stat().st_size == entry['bytes'] and sha(output) == entry['sha256'], 'DELIVERY_CHANGED: ' + str(output)
        result['delivery'].append({'system_id': m['system_id'], 'realization_id': m['id'],
                                   'outputs_verified': len(m['outputs'])})
    print('Engineering delivery manifests:', len(result['delivery']), flush=True)
    spec = importlib.util.spec_from_file_location('cold_history', HERE / 'archive_history.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    result['cold_archives'] = []
    for role in module.TARGETS:
        m = json.loads((module.COLD / (role + '.json')).read_text())
        assert m['status'] == 'RETIRED' and sha(Path(m['archive'])) == m['archive_sha256']
        small = [e for e in m['entries'] if 0 < e['bytes'] < 1_000_000]
        if not small:
            small = sorted(m['entries'], key=lambda e: e['bytes'])[:3]
        chosen = [small[i] for i in sorted({0, len(small)//2, len(small)-1})]
        with tempfile.TemporaryDirectory(prefix='restore-sample-', dir=HERE) as directory:
            target = Path(directory)
            count = module.readback(Path(m['archive']), m['entries'], restore=target,
                                    restore_names={e['name'] for e in chosen})
            for entry in chosen:
                path = target / entry['name']
                assert sha(path) == entry['sha256'] and path.stat().st_mtime_ns == entry['mtime_ns']
        result['cold_archives'].append({'role': role, 'verified_files': count, 'restored_samples': len(chosen),
                                        'archive_sha256': m['archive_sha256']})
        print('Archive/readback/restore:', role, count, flush=True)
    handoff = json.loads((ROOT / 'docs/research/phase-plan-20261019/phase1/CLEANUP-HANDOFF.json').read_text())
    for entry in handoff['must_preserve']:
        assert Path(entry['path']).exists(), 'CURRENT_WORK_MISSING: ' + entry['path']
    for name in handoff['live_shared_dependencies']:
        assert Path(name).exists(), 'ACTIVE_DEPENDENCY_MISSING: ' + name
    result['active_handoff_paths'] = len(handoff['must_preserve'])
    result['active_dependencies'] = len(handoff['live_shared_dependencies'])
    result['source_heads'] = {}
    for role in ['s0', 'a', 'b']:
        path = ROOT / ('workbench/bf-campaign-' + role + '-20261019')
        head = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        assert head == '317d40fef0137d3c1ad1873e53c3e9968b31200a'
        result['source_heads'][role] = head
    result['endpoints'] = {}
    for port in [8768, 8870, 8980]:
        with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/', timeout=8) as response:
            assert response.status == 200
            result['endpoints'][str(port)] = response.status
    result.update({'status': 'PASS', 'available_bytes': os.statvfs(HERE).f_bavail * os.statvfs(HERE).f_frsize,
                   'restoration_temporary_directories': len(list(HERE.glob('restore-sample-*')))})
    assert result['restoration_temporary_directories'] == 0
    (HERE / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['protected']}), flush=True)


if __name__ == '__main__':
    main()
