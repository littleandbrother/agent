#!/usr/bin/env python3
"""Apply the existing verified transparent compressor to explicit idle history.

All original paths and bytes remain readable. Open files, cloud placeholders,
recent writes and databases with journals are skipped. No new archive is kept.
"""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
HELPER = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world/scripts/storage_maintenance.py'


def compact(module, path, canonical):
    initial = module.snapshot(path)
    st = path.lstat()
    if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or
            st.st_flags & (0x40000000 | 0x22)):
        raise ValueError('NOT_IDLE_RESIDENT_SINGLE_LINK_FILE')
    if time.time() - st.st_mtime < 600:
        raise ValueError('FILE_TOO_RECENT')
    handles = subprocess.run(['/usr/sbin/lsof', '-nP', str(path)],
                             capture_output=True, text=True)
    if handles.returncode != 1 or handles.stdout.strip():
        raise ValueError('FILE_OPEN_OR_HANDLE_CHECK_UNAVAILABLE')
    if path.suffix in ('.sqlite', '.db') and any(
            Path(str(path) + s).exists() for s in ('-wal', '-journal')):
        raise ValueError('DATABASE_JOURNAL_PRESENT')
    free_before = module.shutil.disk_usage(path.parent).free
    if free_before < st.st_size + module.RESERVE:
        raise ValueError('MAINTENANCE_PEAK_HEADROOM')
    digest = module.sha(path)
    attrs = module.attributes.attrs(path)
    parent_mode = stat.S_IMODE(path.parent.stat().st_mode)
    try:
        # Frozen baseline directories remain read-only outside this verified
        # atomic replacement. Directory permissions are restored in finally.
        if not parent_mode & stat.S_IWUSR:
            path.parent.chmod(parent_mode | stat.S_IWUSR)
        with tempfile.TemporaryDirectory(prefix='.bf-compact-', dir=path.parent) as directory:
            target = Path(directory) / path.name
            shared = canonical.get(digest)
            subprocess.run(['/bin/cp', '-cp', str(shared or path), str(target)],
                           check=True, capture_output=True)
            if not shared:
                target.chmod(stat.S_IMODE(st.st_mode) | stat.S_IWUSR)
                subprocess.run([str(module.COMPRESSOR), 'compress', '--verify',
                                '--quiet', str(target)], check=True,
                               capture_output=True, timeout=300)
            target.chmod(stat.S_IMODE(st.st_mode) | stat.S_IWUSR)
            # APFS compression xattrs are storage, all user attrs stay intact.
            storage = {'com.apple.decmpfs', 'com.apple.ResourceFork'}
            for name in set(module.attributes.attrs(target)) - set(attrs) - storage:
                assert module.attributes.LIB.removexattr(
                    os.fsencode(target), os.fsencode(name), 1) == 0
            for name, value in attrs.items():
                if name not in storage and module.attributes.attrs(target).get(name) != value:
                    assert module.attributes.LIB.setxattr(
                        os.fsencode(target), os.fsencode(name), value,
                        len(value), 0, 1) == 0
            target.chmod(stat.S_IMODE(st.st_mode))
            os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
            if target.stat().st_blocks >= st.st_blocks and not shared:
                return {'path': str(path), 'status': 'NO_SAVING', 'sha256': digest}
            assert module.sha(target) == digest, 'TEMP_READBACK'
            assert module.snapshot(path) == initial, 'SOURCE_DRIFT'
            assert target.stat().st_ino != st.st_ino, 'INDEPENDENT_INODE'
            assert (target.stat().st_uid, target.stat().st_gid) == (st.st_uid, st.st_gid)
            with target.open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(target, path)
        assert module.sha(path) == digest, 'FINAL_READBACK'
        assert stat.S_IMODE(path.stat().st_mode) == stat.S_IMODE(st.st_mode)
        assert path.stat().st_mtime_ns == st.st_mtime_ns
        canonical[digest] = path
        return {'path': str(path), 'status': 'PASS', 'sha256': digest,
                'logical_bytes': st.st_size, 'allocated_before': st.st_blocks * 512,
                'allocated_after': path.stat().st_blocks * 512,
                'free_before': free_before, 'free_after': module.shutil.disk_usage(path.parent).free,
                'method': 'verified-compressed-clone' if shared else 'verified-transparent-compression',
                'metadata_preserved': True}
    finally:
        path.parent.chmod(parent_mode)


def main():
    spec = importlib.util.spec_from_file_location('verified_storage_helper', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    attr_spec = importlib.util.spec_from_file_location(
        'verified_apfs_helpers', ROOT / 'docs/storage-cleanup-20261019/compact.py')
    module.attributes = importlib.util.module_from_spec(attr_spec)
    attr_spec.loader.exec_module(module.attributes)
    module.RUNTIME_ROOT = Path('/')
    module.ALLOWED = tuple(str(p).lstrip('/') for p in [
        ROOT, Path.home() / '.local/share/bf-agent-runtime',
        Path.home() / '.local/share/bf-agent-architecture-v2',
        Path.home() / '.local/share/bf-agent-baselines',
        Path.home() / '.local/share/bf-campaign-20261019-s0',
    ])
    assert module.sha(module.COMPRESSOR) == module.COMPRESSOR_SHA
    entries = json.loads((HERE / (sys.argv[1] if len(sys.argv) > 1 else 'compression-candidates.json')).read_text())
    entries.sort(key=lambda e: e['alloc'], reverse=True)
    completed = set()
    canonical = {}
    receipt = HERE / 'compression.jsonl'
    if receipt.exists():
        previous = [json.loads(line) for line in receipt.read_text().splitlines()]
        completed = {e['path'] for e in previous if e['status'] in ['PASS', 'NO_SAVING']}
        canonical = {e['sha256']: Path(e['path']) for e in previous if e['status'] == 'PASS'}
    with receipt.open('a') as journal:
        for index, entry in enumerate(entries):
            path = Path(entry['path'])
            if str(path) in completed:
                continue
            try:
                result = compact(module, path, canonical)
            except ValueError as error:
                result = {'path': str(path), 'status': 'SKIPPED', 'reason': str(error)}
            result['time'] = time.time()
            journal.write(json.dumps(result) + '\n')
            journal.flush()
            os.fsync(journal.fileno())
            if index < 5 or index % 10 == 0:
                s = os.statvfs(HERE)
                print(json.dumps({'index': index, 'status': result['status'],
                                  'path': str(path),
                                  'available_bytes': s.f_bavail * s.f_frsize}), flush=True)


if __name__ == '__main__':
    main()
