#!/usr/bin/env python3
"""Inspect BF storage or compact explicit, idle resident files without byte changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time

RESERVE = 2_000_000_000  # Maintenance only; development reserves more.
RUNTIME_ROOT = Path.home() / '.local/share'
ALLOWED = ('bf-agent-runtime', 'bf-agent-architecture-v2', 'bf-campaign-20261019-s0')
COMPRESSOR = RUNTIME_ROOT / 'bf-agent-runtime/maintenance-tools/applesauce-v0.5.30/applesauce'
COMPRESSOR_SHA = '930a613509fa1db336f3810a59c7c1747d2241630ebac8629bef651896ff0a8b'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def snapshot(path):
    s = path.lstat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns,
            s.st_mode, s.st_uid, s.st_gid, s.st_flags, s.st_nlink)


def compact(path):
    path = Path(os.path.abspath(path))
    if path.resolve() != path or not any(path.is_relative_to(RUNTIME_ROOT / r) for r in ALLOWED):
        raise ValueError('EXPLICIT_RESIDENT_RUNTIME_FILE_REQUIRED')
    initial = snapshot(path)
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_flags & (0x40000000 | 0x22):
        raise ValueError('NOT_IDLE_UNCOMPRESSED_SINGLE_LINK_FILE')
    if time.time() - st.st_mtime < 600:
        raise ValueError('FILE_TOO_RECENT')
    handles = subprocess.run(['/usr/sbin/lsof', '-nP', str(path)], capture_output=True, text=True)
    if handles.returncode != 1 or handles.stdout.strip():
        raise ValueError('FILE_OPEN_OR_HANDLE_CHECK_UNAVAILABLE')
    if path.suffix in ('.sqlite', '.db') and any(Path(str(path) + s).exists() for s in ('-wal', '-journal')):
        raise ValueError('DATABASE_JOURNAL_PRESENT')
    free_before = shutil.disk_usage(path.parent).free
    if free_before < st.st_size + RESERVE:
        raise ValueError('MAINTENANCE_PEAK_HEADROOM')
    digest = sha(path)
    with tempfile.TemporaryDirectory(prefix='.bf-compact-', dir=path.parent) as directory:
        target = Path(directory) / path.name
        if COMPRESSOR.is_file():
            if sha(COMPRESSOR) != COMPRESSOR_SHA:
                raise ValueError('COMPRESSOR_BINARY_CHANGED')
            # Independent COW clone keeps the original available until verified.
            subprocess.run(['/bin/cp', '-cp', str(path), str(target)], check=True, capture_output=True)
            subprocess.run([str(COMPRESSOR), 'compress', '--verify', '--quiet', str(target)],
                           check=True, capture_output=True, timeout=300)
            method = 'APFS-transparent-compression/lzfse-applesauce-0.5.30'
        else:
            subprocess.run(['/usr/bin/ditto', '--noclone', '--hfsCompression', str(path), str(target)],
                           check=True, capture_output=True, timeout=300)
            method = 'APFS-transparent-compression/ditto'
        after = target.stat()
        if after.st_blocks >= st.st_blocks:
            return {'path': str(path), 'status': 'NO_SAVING', 'sha256': digest}
        if sha(target) != digest or snapshot(path) != initial:
            raise ValueError('COMPACTION_READBACK_OR_SOURCE_DRIFT')
        if (after.st_size, after.st_mode, after.st_uid, after.st_gid, after.st_mtime_ns) != (
                st.st_size, st.st_mode, st.st_uid, st.st_gid, st.st_mtime_ns):
            raise ValueError('COMPACTION_METADATA_CHANGED')
        with target.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(target, path)
    # Read the final name, not only the temporary file.
    if sha(path) != digest:
        raise ValueError('FINAL_NAME_READBACK_FAILED')
    return {'path': str(path), 'status': 'PASS', 'sha256': digest,
            'logical_bytes': st.st_size, 'allocated_before': st.st_blocks * 512,
            'allocated_after': path.stat().st_blocks * 512,
            'free_before': free_before, 'free_after': shutil.disk_usage(path.parent).free,
            'mode_and_mtime_preserved': True, 'method': method}


def audit(roots):
    result = {'schema_version': 'bf-storage-audit-v1', 'time': time.time(), 'roots': []}
    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            continue
        groups = {}
        dataless = 0
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', 'vendor', 'toolchains')]
            for filename in files:
                path = Path(directory) / filename
                s = path.lstat()
                if not stat.S_ISREG(s.st_mode):
                    continue
                dataless += bool(s.st_flags & 0x40000000)
                key = path.relative_to(root).parts[0]
                value = groups.setdefault(key, {'files': 0, 'logical': 0, 'allocated_upper_bound': 0})
                value['files'] += 1
                value['logical'] += s.st_size
                value['allocated_upper_bound'] += s.st_blocks * 512
        result['roots'].append({'root': str(root), 'free_bytes': shutil.disk_usage(root).free,
                                'dataless_skipped_for_content': dataless, 'groups': groups})
    result['boundary'] = 'APFS shared blocks may be counted repeatedly; free-space deltas prove net reclamation.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('audit')
    scan.add_argument('paths', nargs='*', default=[str(RUNTIME_ROOT / p) for p in ALLOWED])
    compress = commands.add_parser('compact')
    compress.add_argument('paths', nargs='+')
    compress.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'audit':
        print(json.dumps(audit(args.paths), ensure_ascii=False, indent=2))
    else:
        # One append-only small receipt stream; no full-tree backup or copied logs.
        with args.receipt.open('a') as receipt:
            for path in args.paths:
                try:
                    result = compact(path)
                except Exception as error:
                    result = {'path': str(path), 'status': 'STOPPED', 'error': str(error)}
                receipt.write(json.dumps(result, ensure_ascii=False) + '\n')
                receipt.flush()
                print(json.dumps(result, ensure_ascii=False), flush=True)
                if result['status'] == 'STOPPED':
                    raise SystemExit(1)


if __name__ == '__main__':
    main()
