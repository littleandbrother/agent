#!/usr/bin/env python3
"""Retire only reviewed source trees; preserve unique bytes once, never whole trees.

Usage: review.py plan | preserve | --verify | retire | restore ROLE DESTINATION
Git blobs, existing sealed overlays and a small unique-byte store are the restore
sources. Neither the original cloud worktree nor a live runtime is modified.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path('/Users/depengsu/Documents/Long-Horizon AI Agent')
HERE = Path(__file__).resolve().parent
CAMPAIGN = ROOT / 'docs/research/parallel-campaign-20261019'
GIT = Path.home() / '.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/campaign.git'
BASE = '317d40fef0137d3c1ad1873e53c3e9968b31200a'
CI = 'cf3594f9587cf75236334a594b25775e672093b8'
TARGETS = {
    'a': ROOT / 'workbench/bf-campaign-a-20261019',
    'b': ROOT / 'workbench/bf-campaign-b-20261019',
    'ci': Path.home() / '.local/share/bf-agent-architecture-v2/ci-publication-20261018/clean-source',
}


def available():
    s = os.statvfs(ROOT)
    return s.f_bavail * s.f_frsize


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    s = path.lstat()
    assert not s.st_flags & 0x40000000, 'cloud placeholder: ' + str(path)
    assert stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode), str(path)
    return os.readlink(path).encode() if path.is_symlink() else path.read_bytes()


def inventory(path):
    for directory, dirs, files in os.walk(path, followlinks=False):
        parent = Path(directory)
        assert not parent.lstat().st_flags & 0x40000000, str(parent)
        dirs[:] = sorted(d for d in dirs if d != '.git')
        for name in list(dirs):
            p = parent / name
            if p.is_symlink():
                dirs.remove(name)
                files.append(name)
        for name in sorted(files):
            if name != '.git':
                yield parent / name


class Objects:
    def __init__(self):
        self.process = subprocess.Popen(['git', '--git-dir=' + str(GIT), 'cat-file', '--batch'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.hashes = {}

    def blob(self, oid):
        self.process.stdin.write((oid + '\n').encode())
        self.process.stdin.flush()
        header = self.process.stdout.readline().split()
        assert len(header) == 3 and header[1] == b'blob', header
        length = int(header[2])
        data = self.process.stdout.read(length)
        assert len(data) == length and self.process.stdout.read(1) == b'\n'
        assert hashlib.sha1(b'blob ' + str(length).encode() + b'\0' + data).hexdigest() == oid
        return data

    def digest(self, oid):
        if oid not in self.hashes:
            self.hashes[oid] = sha(self.blob(oid))
        return self.hashes[oid]

    def close(self):
        self.process.stdin.close()
        assert self.process.wait(timeout=10) == 0


def tree(commit):
    raw = subprocess.check_output(['git', '--git-dir=' + str(GIT), 'ls-tree', '-rz', commit])
    rows = {}
    for row in raw.split(b'\0'):
        if row:
            meta, name = row.split(b'\t', 1)
            mode, kind, oid = meta.split()
            assert kind == b'blob', name
            rows[name.decode()] = oid.decode()
    return rows


def plan():
    known = {}
    # Sealed overlays are small, already canonical and remain in place.
    for part in ['baseline-v1', 'integrated-v1']:
        m = json.loads((CAMPAIGN / part / 'manifest.json').read_text())
        for e in m['entries']:
            p = CAMPAIGN / part / 'overlay' / e['path']
            if p.exists() or p.is_symlink():
                data = read(p)
                assert sha(data) == e['sha256'], str(p)
                known.setdefault(e['sha256'], {'type': 'file', 'path': str(p)})
    trees = {BASE: tree(BASE), CI: tree(CI)}
    objects = Objects()
    result = {'schema': 'reviewed-workspace-retirement-v1', 'git_admin': str(GIT),
              'baseline': BASE, 'ci_commit': CI, 'targets': {}, 'unique_bytes': 0,
              'limitations': 'Generated Python bytecode, Finder metadata, untracked CI Node dependencies and build outputs are omitted on restore; package sources and locks remain recoverable.'}
    unique = {}
    try:
        for role, path in TARGETS.items():
            rows, discarded = [], []
            for p in inventory(path):
                rel = str(p.relative_to(path))
                s = p.lstat()
                assert not s.st_flags & 0x40000000, str(p)
                oid = trees[CI if role == 'ci' else BASE].get(rel)
                ci_generated = (role == 'ci' and oid is None and
                                rel.startswith('pi-bf-aiot/packages/') and
                                ('/dist/' in rel or '/node_modules/' in rel or rel.endswith('.tsbuildinfo')))
                if '__pycache__' in p.parts or p.name == '.DS_Store' or ci_generated:
                    discarded.append({'path': rel, 'bytes': s.st_size,
                                      'reason': 'untracked CI npm install/build output' if ci_generated else 'bytecode/Finder metadata'})
                    continue
                data = read(p)
                digest = sha(data)
                route = known.get(digest)
                if route is None and oid and objects.digest(oid) == digest:
                    route = {'type': 'git', 'oid': oid}
                    known[digest] = route
                if route is None:
                    route = {'type': 'unique', 'path': str(HERE / 'unique-files' / digest)}
                    unique.setdefault(digest, {'source': str(p), 'bytes': len(data)})
                rows.append({'path': rel, 'sha256': digest, 'bytes': len(data),
                             'kind': 'symlink' if p.is_symlink() else 'file',
                             'mode': stat.S_IMODE(s.st_mode), 'mtime_ns': s.st_mtime_ns,
                             'restore': route})
            result['targets'][role] = {'path': str(path), 'entries': rows,
                                       'discarded_rebuildable': discarded,
                                       'allocated_bytes': sum(p.lstat().st_blocks * 512 for p in inventory(path))}
            print(role, len(rows), 'files; unique routes', sum(e['restore']['type'] == 'unique' for e in rows), flush=True)
    finally:
        objects.close()
    result['unique'] = unique
    result['unique_bytes'] = sum(e['bytes'] for e in unique.values())
    assert result['unique_bytes'] <= 50_000_000, 'review unique changes before allocating more storage'
    save('retirement-plan.json', result)
    print('unique bytes to preserve:', result['unique_bytes'])


def load():
    return json.loads((HERE / 'retirement-plan.json').read_text())


def preserve():
    m = load()
    for digest, item in m['unique'].items():
        data = read(Path(item['source']))
        assert sha(data) == digest
        p = HERE / 'unique-files' / digest
        p.parent.mkdir(exist_ok=True)
        if not p.exists():
            p.write_bytes(data)
        assert sha(p.read_bytes()) == digest
    verify()


def recovered(e, objects):
    route = e['restore']
    return objects.blob(route['oid']) if route['type'] == 'git' else read(Path(route['path']))


def verify():
    m = load()
    objects = Objects()
    checked = {}
    totals = collections.Counter()
    try:
        for role, target in m['targets'].items():
            path = Path(target['path'])
            if path.exists():
                planned = {e['path'] for e in target['entries']} | {e['path'] for e in target['discarded_rebuildable']}
                assert {str(p.relative_to(path)) for p in inventory(path)} == planned, 'inventory changed: ' + str(path)
            for e in target['entries']:
                key = json.dumps(e['restore'], sort_keys=True)
                if key not in checked:
                    checked[key] = sha(recovered(e, objects))
                assert checked[key] == e['sha256'], e['path']
                if path.exists():
                    p = path / e['path']
                    assert sha(read(p)) == e['sha256'], str(p)
                    assert stat.S_IMODE(p.lstat().st_mode) == e['mode'], str(p)
                totals[role] += 1
    finally:
        objects.close()
    row = {'status': 'PASS', 'files_by_target': dict(totals), 'unique_files': len(m['unique']),
           'unique_bytes': m['unique_bytes'], 'recovery_sources_checked': len(checked)}
    save('retirement-readback.json', row)
    print(json.dumps(row))
    return row


def retire():
    verify()
    m = load()
    # Inspect all visible file handles without recursively opening old directories.
    q = subprocess.run(['lsof', '-nP', '-F', 'n'], capture_output=True, text=True, timeout=30)
    assert q.returncode in (0, 1), q.stderr[-500:]
    handles = [x[1:] for x in q.stdout.splitlines() if x.startswith('n')]
    for item in m['targets'].values():
        target = item['path']
        assert not any(h == target or h.startswith(target + '/') for h in handles), 'open target: ' + target
    receipts = []
    for role, item in m['targets'].items():
        p = Path(item['path'])
        if not p.exists():
            continue
        before = available()
        if role in ('a', 'b'):
            subprocess.run(['git', '--git-dir=' + str(GIT), 'worktree', 'remove', '--force', str(p)], check=True, timeout=60)
        else:
            shutil.rmtree(p)
        assert not p.exists()
        receipts.append({'role': role, 'path': str(p), 'before_available_bytes': before,
                         'after_available_bytes': available(), 'allocation_before_bytes': item['allocated_bytes'],
                         'full_backup_created': False})
        save('retirement.json', receipts)
        print('retired', role, 'instant free delta', receipts[-1]['after_available_bytes'] - before, flush=True)
    verify()


def restore(role, destination):
    m = load()
    dest = Path(destination)
    assert not dest.exists(), 'restore destination must be new'
    if role in ('a', 'b'):
        subprocess.run(['git', '--git-dir=' + str(GIT), 'worktree', 'add',
                        '--no-checkout', '--detach', str(dest), BASE], check=True)
    else:
        dest.mkdir(parents=True)
    objects = Objects()
    try:
        for e in m['targets'][role]['entries']:
            p = dest / e['path']
            p.parent.mkdir(parents=True, exist_ok=True)
            data = recovered(e, objects)
            assert sha(data) == e['sha256']
            if e['kind'] == 'symlink':
                p.symlink_to(data.decode())
            else:
                p.write_bytes(data)
                p.chmod(e['mode'])
                os.utime(p, ns=(e['mtime_ns'], e['mtime_ns']))
            assert sha(read(p)) == e['sha256']
    finally:
        objects.close()
    if role in ('a', 'b'):
        subprocess.run(['git', '-C', str(dest), 'read-tree', BASE], check=True)
    print('RESTORED', role, str(dest))


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'restore':
        restore(sys.argv[2], sys.argv[3])
    else:
        {'plan': plan, 'preserve': preserve, '--verify': verify, 'retire': retire}[mode]()
