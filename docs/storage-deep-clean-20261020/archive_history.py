#!/usr/bin/env python3
"""Cold-store reviewed obsolete directories, verify every byte, then retire files.

Archived files have exact paths, modes, timestamps, hashes and xattrs in a small
manifest. Cloud placeholders and symlinks stay at their original locations.
restore ROLE recreates archived files without rerunning any experiment.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COLD = Path.home() / '.local/share/bf-agent-history-20261020'
TARGETS = {
    'temporary-work': ROOT / '.tmp',
    'old-qualification': ROOT / 'workbench/bf-refactor-r0-r2-20261011/battery-world/docs/agentlab/executable-lab-20261012/qualification-1791749076360992000',
    'old-claude-runs': ROOT / '.claude/worktrees/optimistic-heyrovsky-346b2f/runs',
    'old-publication-source': Path.home() / '.local/share/bf-agent-maintenance/publication-20261010-j2xlka4b/source',
}
spec = importlib.util.spec_from_file_location('apfs_metadata', ROOT / 'docs/storage-cleanup-20261019/compact.py')
META = importlib.util.module_from_spec(spec)
spec.loader.exec_module(META)


def free():
    s = os.statvfs(HERE)
    return s.f_bavail * s.f_frsize


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sig(path):
    s = path.lstat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def inventory(base):
    entries, skipped = [], []
    for directory, dirs, files in os.walk(base, followlinks=False):
        for name in dirs[:]:
            p = Path(directory) / name
            if p.is_symlink() or p.lstat().st_flags & 0x40000000:
                skipped.append(str(p)); dirs.remove(name)
        for name in files:
            p = Path(directory) / name
            s = p.lstat()
            if (not stat.S_ISREG(s.st_mode) or s.st_flags & (0x40000000 | 2) or
                    time.time() - s.st_mtime < 3600):
                skipped.append(str(p)); continue
            entries.append({'name': str(p.relative_to(base)), 'sha256': sha(p),
                            'bytes': s.st_size, 'allocated_bytes': s.st_blocks * 512,
                            'signature': sig(p), 'mode': stat.S_IMODE(s.st_mode), 'links': s.st_nlink,
                            'atime_ns': s.st_atime_ns, 'mtime_ns': s.st_mtime_ns,
                            'attrs': {n: base64.b64encode(v).decode() for n, v in META.attrs(p).items()
                                      if n != 'com.apple.decmpfs' and
                                      (n != 'com.apple.ResourceFork' or not s.st_flags & 0x20)}})
    return entries, skipped


def readback(archive, expected, restore=None, restore_names=None):
    process = subprocess.Popen(['zstd', '-d', '-q', '-c', '--long=29', str(archive)], stdout=subprocess.PIPE)
    by_name = {e['name']: e for e in expected}
    seen = set()
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as source:
            for member in source:
                assert member.isfile() and member.name in by_name, ('UNEXPECTED_ARCHIVE_ENTRY', member.name, member.type)
                assert member.name not in seen, 'DUPLICATE_ARCHIVE_ENTRY'
                expected_entry = by_name[member.name]
                assert member.size == expected_entry['bytes'], 'ARCHIVE_SIZE_MISMATCH'
                h = hashlib.sha256()
                destination = None
                if restore and (restore_names is None or member.name in restore_names):
                    destination = restore / member.name
                    assert destination.resolve().is_relative_to(restore.resolve())
                    if destination.exists():
                        assert sha(destination) == expected_entry['sha256'], 'RESTORE_PATH_CONFLICT'
                        destination = None
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                output = destination.open('wb') if destination else None
                try:
                    stream = source.extractfile(member)
                    for chunk in iter(lambda: stream.read(1 << 20), b''):
                        h.update(chunk)
                        if output: output.write(chunk)
                finally:
                    if output: output.close()
                assert h.hexdigest() == expected_entry['sha256'], 'ARCHIVE_CONTENT_MISMATCH'
                if destination:
                    for name, value in expected_entry['attrs'].items():
                        data = base64.b64decode(value)
                        assert META.LIB.setxattr(os.fsencode(destination), os.fsencode(name),
                                                 data, len(data), 0, 1) == 0
                    destination.chmod(expected_entry['mode'])
                    os.utime(destination, ns=(expected_entry['atime_ns'], expected_entry['mtime_ns']))
                seen.add(member.name)
        assert process.wait(timeout=60) == 0, 'ARCHIVE_DECODER_FAILED'
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate(); process.wait(timeout=10)
    assert seen == set(by_name), 'ARCHIVE_ENTRY_OMISSION'
    return len(seen)


def archive(role):
    base = TARGETS[role]
    COLD.mkdir(exist_ok=True, mode=0o700)
    manifest_path = COLD / (role + '.json')
    target = COLD / (role + '.tar.zst')
    assert not target.exists(), 'ARCHIVE_ALREADY_EXISTS'
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        assert old['status'] == 'PREPARED', 'PREVIOUS_ARCHIVE_MUST_BE_REVIEWED'
        # A failed pre-retirement attempt keeps every source file untouched.
        assert all(sig(base / e['name']) == e['signature'] for e in old['entries'])
    handles = subprocess.run(['/usr/sbin/lsof', '-nP', '+D', str(base)],
                             capture_output=True, text=True, timeout=45)
    assert handles.returncode == 1 and not handles.stdout.strip(), 'OPEN_DIRECTORY'
    before = free()
    entries, skipped = inventory(base)
    total = sum(e['bytes'] for e in entries)
    assert before > total + 2_000_000_000, 'ARCHIVE_PEAK_HEADROOM'
    manifest = {'schema': 'bf-cold-history-v1', 'role': role, 'source': str(base),
                'archive': str(target), 'entries': entries, 'skipped': skipped,
                'before_available_bytes': before, 'logical_bytes': total,
                'allocated_upper_bound': sum(e['allocated_bytes'] for e in entries),
                'status': 'PREPARED', 'codec': 'zstd-3-long29-single-thread'}
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    temporary = target.with_suffix('.partial')
    try:
        with temporary.open('wb') as output:
            process = subprocess.Popen(['zstd', '-q', '-3', '-T1', '--long=29', '-c'],
                                       stdin=subprocess.PIPE, stdout=output)
            try:
                with tarfile.open(fileobj=process.stdin, mode='w|', format=tarfile.PAX_FORMAT,
                                  dereference=True) as tar:
                    for entry in entries:
                        path = base / entry['name']
                        assert sig(path) == entry['signature'], 'SOURCE_DRIFT_BEFORE_ARCHIVE'
                        tar.add(path, arcname=entry['name'], recursive=False)
                process.stdin.close()
                assert process.wait(timeout=600) == 0, 'ARCHIVE_ENCODER_FAILED'
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=10)
            output.flush(); os.fsync(output.fileno())
        assert temporary.stat().st_size < manifest['allocated_upper_bound'], 'NO_ARCHIVE_REDUCTION'
        verified = readback(temporary, entries)
        temporary.chmod(0o600)
        os.replace(temporary, target)
        manifest.update({'status': 'VERIFIED', 'verified_entries': verified,
                         'archive_bytes': target.stat().st_size, 'archive_sha256': sha(target)})
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        # All entries must still be unchanged before the first source unlink.
        assert all(sig(base / e['name']) == e['signature'] for e in entries), 'SOURCE_DRIFT_BEFORE_RETIRE'
        with (HERE / 'retired-files.jsonl').open('a') as journal:
            for entry in entries:
                path = base / entry['name']
                current = sig(path)
                if current != entry['signature']:
                    # Unlinking an earlier alias changes the ctime of every
                    # remaining hard link. Its bytes, inode and mtime stay fixed.
                    assert entry['links'] > 1 and current[:4] == entry['signature'][:4], 'SOURCE_DRIFT_DURING_RETIRE'
                    assert sha(path) == entry['sha256'], 'HARDLINK_CONTENT_DRIFT'
                path.unlink()
                journal.write(json.dumps({'role': role, 'path': str(path), 'sha256': entry['sha256']}) + '\n')
            journal.flush(); os.fsync(journal.fileno())
        (base / 'ARCHIVED-20261020.md').write_text(
            '# 已归档的过渡材料\n\n存档：' + str(target) + '\n\n恢复：\n\n    rtk proxy python3 -B "' + str(HERE / 'archive_history.py') + '" restore ' + role + '\n')
        manifest.update({'status': 'RETIRED', 'after_available_bytes': free(),
                         'available_delta_bytes': free() - before})
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        summary = {k: v for k, v in manifest.items() if k not in ['entries', 'skipped']}
        summary['skipped_count'] = len(skipped)
        (HERE / (role + '-receipt.json')).write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary), flush=True)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['archive', 'verify', 'restore'])
    parser.add_argument('roles', nargs='+', choices=sorted(TARGETS))
    args = parser.parse_args()
    for role in args.roles:
        if args.action == 'archive':
            archive(role)
        else:
            m = json.loads((COLD / (role + '.json')).read_text())
            assert sha(Path(m['archive'])) == m['archive_sha256']
            count = readback(Path(m['archive']), m['entries'],
                             Path(m['source']) if args.action == 'restore' else None)
            print(json.dumps({'role': role, 'status': 'PASS', 'files': count}), flush=True)


if __name__ == '__main__':
    main()
