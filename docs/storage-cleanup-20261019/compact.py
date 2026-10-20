#!/usr/bin/env python3
"""Hash-verified APFS copy-on-write compaction of idle BF artifacts."""
import argparse
import collections
import ctypes
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import time

OUT = Path(__file__).resolve().parent
SHARE = Path.home()/'.local/share'
ROOTS = [SHARE/'bf-agent-runtime', SHARE/'bf-agent-architecture-v2']
SKIP = {'state', 'sessions', 'secrets', 'vendor', 'toolchains', 'product-cad',
        'node_modules', '.git', '.venv', 'venv', '__pycache__', 'harness-home',
        'receiver-runtime-20261013', 'engineering-content-env', 'preview-tools',
        'ui-tools', 'ci-python', 'workspaces', 'lead'}
EXTENSIONS = {'.raw', '.xz', '.zlib', '.zip', '.pdf', '.png', '.svg', '.step',
              '.stp', '.bin', '.elf', '.hex', '.map', '.csv', '.stl', '.gltf',
              '.glb', '.epro2'}
LIB = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
LIB.clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
LIB.clonefile.restype = ctypes.c_int
LIB.copyfile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                         ctypes.c_uint32]
LIB.copyfile.restype = ctypes.c_int
LIB.listxattr.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
LIB.listxattr.restype = ctypes.c_ssize_t
LIB.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                         ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
LIB.getxattr.restype = ctypes.c_ssize_t
LIB.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                         ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
LIB.setxattr.restype = ctypes.c_int
LIB.removexattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
LIB.removexattr.restype = ctypes.c_int


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(4*1024*1024):
            h.update(chunk)
    return h.hexdigest()


def sig(path):
    s = path.lstat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns,
            s.st_mode, s.st_uid, s.st_gid, s.st_nlink, s.st_flags]


def attrs(path):
    raw = os.fsencode(path)
    size = LIB.listxattr(raw, None, 0, 1)
    if size < 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(path))
    names = ctypes.create_string_buffer(size)
    assert LIB.listxattr(raw, names, size, 1) == size
    result = {}
    for name in names.raw.split(b'\0'):
        if not name:
            continue
        n = LIB.getxattr(raw, name, None, 0, 0, 1)
        assert n >= 0
        value = ctypes.create_string_buffer(n)
        assert LIB.getxattr(raw, name, value, n, 0, 1) == n
        result[os.fsdecode(name)] = value.raw
    return result


def metadata(path):
    s = path.lstat()
    return (stat.S_IMODE(s.st_mode), s.st_uid, s.st_gid, s.st_mtime_ns,
            s.st_flags, attrs(path))


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def probe():
    directory = OUT/('cow-probe-'+str(time.time_ns()))
    directory.mkdir(exist_ok=False)
    a, b = directory/'source', directory/'clone'
    a.write_bytes(b'original-private-content')
    assert LIB.clonefile(os.fsencode(a), os.fsencode(b), 1) == 0
    assert a.stat().st_ino != b.stat().st_ino
    b.write_bytes(b'modified-independent-clone')
    assert a.read_bytes() == b'original-private-content'
    return {'independent_inodes': True, 'copy_on_write': 'PASS'}


def plan():
    groups = collections.defaultdict(list)
    errors = []
    for root in ROOTS:
        for parent, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [n for n in dirs if n not in SKIP and
                       not (Path(parent)/n).is_symlink()]
            for name in names:
                p = Path(parent)/name
                if p.suffix.lower() not in EXTENSIONS and not (
                        p.parent.name == 'blobs' and len(name) == 64):
                    continue
                try:
                    s = p.lstat()
                    if (not stat.S_ISREG(s.st_mode) or s.st_size < 1024**2 or
                            s.st_flags & (0x40000000 | 0x800 | 0x2 | 0x20000 | 0x20) or
                            s.st_mtime > time.time()-300):
                        continue
                    groups[s.st_size].append(p)
                except OSError as e:
                    errors.append({'path': str(p), 'error': str(e)})
    sampled = collections.defaultdict(list)
    for size, paths in groups.items():
        if len(paths) < 2:
            continue
        for p in paths:
            before = sig(p)
            with p.open('rb') as stream:
                h = hashlib.sha256(stream.read(65536))
                stream.seek(max(0, size-65536))
                h.update(stream.read(65536))
            if sig(p) == before:
                sampled[(size, h.hexdigest())].append(p)
    entries = []
    hashed = 0
    for (size, _), paths in sorted(sampled.items(), reverse=True):
        if len(paths) < 2:
            continue
        by_hash = collections.defaultdict(list)
        seen = {}
        for p in paths:
            before = sig(p)
            inode = tuple(before[:2])
            if inode not in seen:
                seen[inode] = sha(p)
                hashed += size
            if sig(p) == before:
                by_hash[seen[inode]].append((p, before))
        for digest, matches in by_hash.items():
            if len(matches) < 2:
                continue
            # Existing multi-link immutable objects are read-only canonical sources.
            matches.sort(key=lambda item: (-item[1][8], str(item[0])))
            source, source_sig = matches[0]
            for target, target_sig in matches[1:]:
                if target_sig[8] != 1 or source_sig[:2] == target_sig[:2]:
                    continue
                entries.append({'source': str(source), 'target': str(target),
                                'sha256': digest, 'bytes': size,
                                'source_signature': source_sig,
                                'target_signature': target_sig})
        if hashed and hashed//10**9 != (hashed-size)//10**9:
            print(json.dumps({'stage': 'hashing', 'gb_read': round(hashed/1e9, 1),
                              'duplicate_targets': len(entries)}), flush=True)
    result = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'roots': list(map(str, ROOTS)), 'skipped_directory_names': sorted(SKIP),
              'entries': entries, 'errors': errors, 'hashed_bytes': hashed,
              'duplicate_logical_bytes': sum(e['bytes'] for e in entries)}
    save('clone-plan.json', result)
    return result


def apply(value):
    before_free = shutil.disk_usage(OUT).free
    result = {'before_free_bytes': before_free, 'probe': probe(),
              'completed': [], 'skipped': []}
    with (OUT/'clone-journal.jsonl').open('a') as journal:
        for entry in value['entries']:
            source, target = Path(entry['source']), Path(entry['target'])
            if source.stat().st_flags & 0x20 or target.stat().st_flags & 0x20:
                result['skipped'].append({'target': str(target),
                                          'reason': 'already_transparently_compressed'})
                continue
            if sig(source) != entry['source_signature'] or sig(target) != entry['target_signature']:
                result['skipped'].append({'target': str(target), 'reason': 'changed'})
                continue
            original_metadata = metadata(target)
            atime_ns = target.stat().st_atime_ns
            tmp = target.with_name(target.name+'.bf-storage-clone-'+str(os.getpid()))
            if LIB.clonefile(os.fsencode(source), os.fsencode(tmp), 1):
                raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(target))
            # COPYFILE_METADATA is ACL|STAT|XATTR; no data is recopied.
            if LIB.copyfile(os.fsencode(target), os.fsencode(tmp), None, 7):
                raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(tmp))
            expected_attrs = original_metadata[-1]
            copied_attrs = attrs(tmp)
            for name in set(copied_attrs)-set(expected_attrs):
                assert LIB.removexattr(os.fsencode(tmp), os.fsencode(name), 1) == 0
            for name, data in expected_attrs.items():
                if copied_attrs.get(name) != data:
                    assert LIB.setxattr(os.fsencode(tmp), os.fsencode(name), data,
                                        len(data), 0, 1) == 0
            os.utime(tmp, ns=(atime_ns, target.stat().st_mtime_ns))
            os.chflags(tmp, original_metadata[4])
            assert metadata(tmp) == original_metadata, 'TARGET_METADATA_CHANGED'
            assert sha(tmp) == entry['sha256'], 'CLONE_READBACK_CHANGED'
            assert not os.path.samefile(source, tmp), 'SHARED_INODE'
            assert sig(source) == entry['source_signature'], 'SOURCE_CHANGED'
            assert sig(target) == entry['target_signature'], 'TARGET_CHANGED'
            with tmp.open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(tmp, target)
            assert sha(target) == entry['sha256'], 'REPLACEMENT_CHANGED'
            assert metadata(target) == original_metadata, 'REPLACEMENT_METADATA_CHANGED'
            done = {k: entry[k] for k in ('source', 'target', 'sha256', 'bytes')}
            result['completed'].append(done)
            journal.write(json.dumps(done)+'\n')
            journal.flush()
            os.fsync(journal.fileno())
            if len(result['completed']) % 20 == 0:
                print(json.dumps({'stage': 'compacting', 'files': len(result['completed']),
                                  'free_gb': round(shutil.disk_usage(OUT).free/1e9, 2)}), flush=True)
    result['after_free_bytes'] = shutil.disk_usage(OUT).free
    result['net_free_bytes'] = result['after_free_bytes']-before_free
    result['logical_bytes_shared'] = sum(e['bytes'] for e in result['completed'])
    result['paths_and_content_preserved'] = True
    result['all_completed'] = [json.loads(line) for line in
                               (OUT/'clone-journal.jsonl').read_text().splitlines()]
    save('clone-receipt.json', result)
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('completed', 'skipped', 'all_completed')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--output', type=Path,
                        help='Fresh receipt directory; existing receipts are never replaced.')
    args = parser.parse_args()
    if args.output:
        OUT = args.output.resolve()
        OUT.mkdir(parents=True, exist_ok=False)
    if (OUT/'clone-plan.json').exists():
        parser.error('Existing cleanup receipt: use --output with a new directory.')
    with (OUT/'compaction.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        value = plan()
        print(json.dumps({'stage': 'plan', 'files': len(value['entries']),
                          'duplicate_logical_gb': value['duplicate_logical_bytes']/1e9}), flush=True)
        if args.apply:
            apply(value)
