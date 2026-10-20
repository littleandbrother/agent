#!/usr/bin/env python3
"""Inspect and retire only named idle, reconstructible dependency directories."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LOCAL = Path.home() / '.local/share'
OLD = ROOT / 'workbench/bf-refactor-r0-r2-20261011/battery-world/node_modules'
PUBLICATION = LOCAL / 'bf-agent-maintenance/publication-20261010-j2xlka4b/source/pi-bf-aiot/node_modules'
RECEIVER = LOCAL / 'bf-agent-runtime/reference-cases/literature-rsi-20261008/deployment/p01-mainline-20261013/funded-resume-1791872106979043000/receiver-isolation/previous-receiver/venv'
TARGETS = [OLD, PUBLICATION, RECEIVER]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(p):
    s = p.lstat()
    if s.st_flags & 0x40000000:
        raise ValueError('CLOUD_PLACEHOLDER:' + str(p))
    return os.readlink(p).encode() if p.is_symlink() else p.read_bytes()


def entries(root):
    for directory, dirs, files in os.walk(root, followlinks=False):
        p = Path(directory)
        if p.lstat().st_flags & 0x40000000:
            raise ValueError('CLOUD_PLACEHOLDER:' + str(p))
        for name in list(dirs):
            if (p / name).is_symlink():
                dirs.remove(name)
                files.append(name)
        for name in sorted(files):
            q = p / name
            s = q.lstat()
            b = read(q)
            yield {'path': str(q.relative_to(root)), 'sha256': sha(b), 'bytes': len(b),
                   'link': q.is_symlink(), 'mode': stat.S_IMODE(s.st_mode)}


def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2) + '\n')


def plan():
    rows = []
    skipped = []
    for target in [OLD, PUBLICATION]:
        assert target.is_dir() and not target.is_symlink()
        # Package-manager state and exact lock are kept, sources are untouched.
        names = ['.modules.yaml', '.pnpm/lock.yaml'] if target == OLD else ['.package-lock.json']
        names += [] if target == OLD else ['../package.json', '../package-lock.json']
        dest = HERE / 'dependency-locks' / ('old-world-ui' if target == OLD else 'publication-pi')
        dest.mkdir(parents=True, exist_ok=True)
        locks = []
        for name in names:
            p = target / name
            assert p.exists(), str(p)
            data = read(p)
            q = dest / name.replace('../', 'source-').replace('/', '-')
            q.write_bytes(data)
            assert read(q) == data
            locks.append({'source': str(p), 'retained': str(q), 'sha256': sha(data)})
        try:
            inv = list(entries(target))
        except ValueError as error:
            if not str(error).startswith('CLOUD_PLACEHOLDER:'):
                raise
            skipped.append({'path': str(target), 'reason': str(error), 'action': 'retained; no hydration/deletion'})
            print('retained cloud-backed environment:', target, flush=True)
            continue
        # Reject dependency trees containing apparent project data or local patches.
        suspicious = [e['path'] for e in inv if e['path'].endswith(('.sqlite', '.db', '.raw', '.mp4'))
                      or any(s in Path(e['path']).parts for s in ('patches', 'experiments', 'billing'))]
        # cpu-features ships a vendor patch; verify against the retained install.
        canonical_node = LOCAL / 'bf-agent-runtime/pi-bf-aiot/node_modules'
        suspicious = [name for name in suspicious if not (
            name.startswith('cpu-features/deps/cpu_features/patches/') and
            (canonical_node / name).is_file() and read(canonical_node / name) == read(target / name))]
        assert not suspicious, suspicious[:10]
        rows.append({'target': str(target), 'reason': 'idle historical install; source and exact lock retained',
                     'restore': 'pnpm@11.7.0 install --frozen-lockfile' if target == OLD else 'npm ci --include=dev',
                     'locks': locks, 'entries': inv, 'allocated_bytes': sum(p.lstat().st_blocks * 512
                       for p in target.rglob('*') if p.is_file() and not p.is_symlink())})
    previous = json.loads((HERE / 'receiver-env-review.json').read_text())
    assert set(previous['different_paths']) == {'pyvenv.cfg', 'bin/python3'}
    overrides = []
    for name in previous['different_paths']:
        p = RECEIVER / name
        data = read(p)
        q = HERE / 'unique-files' / sha(data)
        q.write_bytes(data)
        assert read(q) == data
        overrides.append({'path': name, 'sha256': sha(data), 'link': p.is_symlink(), 'retained': str(q)})
    rows.append({'target': str(RECEIVER), 'reason': 'historical receiver backup environment, 1682/1684 entries identical to retained canonical environment',
                 'canonical': previous['canonical'], 'entries': [dict(path=k, **v) for k,v in previous['old_inventory'].items()],
                 'overrides': overrides, 'restore': 'copy canonical venv to old path, then restore the two recorded configuration/link overrides',
                 'allocated_bytes': sum(p.lstat().st_blocks * 512 for p in RECEIVER.rglob('*') if p.is_file() and not p.is_symlink())})
    save('environment-plan.json', rows)
    save('environment-skipped.json', skipped)
    print([(r['target'], len(r['entries']), r['allocated_bytes']) for r in rows])


def verify_live(rows):
    for row in rows:
        target = Path(row['target'])
        actual = {e['path']: {k:v for k,v in e.items() if k != 'path'} for e in entries(target)}
        expected = {e['path']: {k:v for k,v in e.items() if k != 'path'} for e in row['entries']}
        assert actual == expected, 'environment changed: ' + str(target)
        for lock in row.get('locks', []):
            assert sha(read(Path(lock['retained']))) == lock['sha256']
            assert read(Path(lock['source'])) == read(Path(lock['retained']))
        if 'canonical' in row:
            overrides = {e['path']: e for e in row['overrides']}
            canonical = Path(row['canonical'])
            for e in row['entries']:
                if e['path'] in overrides:
                    assert sha(read(Path(overrides[e['path']]['retained']))) == e['sha256']
                else:
                    assert sha(read(canonical / e['path'])) == e['sha256']


def retire():
    rows = json.loads((HERE / 'environment-plan.json').read_text())
    verify_live(rows)
    q = subprocess.run(['lsof', '-nP', '-F', 'n'], capture_output=True, text=True, timeout=30)
    assert q.returncode in (0, 1)
    handles = [x[1:] for x in q.stdout.splitlines() if x.startswith('n')]
    receipts = []
    for row in rows:
        target = Path(row['target'])
        assert not any(h == str(target) or h.startswith(str(target) + '/') for h in handles), str(target)
        s = os.statvfs(ROOT)
        before = s.f_bavail * s.f_frsize
        shutil.rmtree(target)
        assert not target.exists()
        s = os.statvfs(ROOT)
        receipts.append({'path': str(target), 'before_available_bytes': before,
                         'after_available_bytes': s.f_bavail * s.f_frsize,
                         'allocated_bytes_before': row['allocated_bytes'], 'source_and_experiments_removed': False})
        save('environments-retired.json', receipts)
        print('retired', target, 'instant delta', receipts[-1]['after_available_bytes'] - before, flush=True)


if __name__ == '__main__':
    {'plan': plan, 'retire': retire}[sys.argv[1]]()
