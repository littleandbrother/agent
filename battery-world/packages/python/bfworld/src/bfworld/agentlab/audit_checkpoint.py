"""Local, atomic validation checkpoints. These are execution caches, not verdicts.

An input stat change or checker change always invalidates a checkpoint. Hard
links share a read, but callers must still validate each manifest binding.
"""
import gzip
import hashlib
import json
import lzma
import os
import threading
import time
from pathlib import Path


def primitives(value):
    if isinstance(value, dict):
        return {str(k): primitives(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitives(v) for v in value]
    if hasattr(value, 'item'):
        return primitives(value.item())
    return value


def atomic_json(path, value):
    # Serialize before touching the destination. A late JSON error cannot
    # invalidate the completed validation checkpoints.
    data = json.dumps(primitives(value), ensure_ascii=False, allow_nan=False, indent=2)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.partial')
    try:
        with temporary.open('w') as f:
            f.write(data + '\n'); f.flush(); os.fsync(f.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def fingerprint(path):
    p = Path(path)
    if p.is_symlink():
        # Resolve intentional operator aliases, then fingerprint the real data.
        p = p.resolve(strict=True)
    s = p.stat()
    if not p.is_file():
        raise ValueError('CHECKPOINT_INPUT_NOT_FILE')
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


class Checkpoints:
    def __init__(self, root, checker):
        self.root = Path(root); self.checker = checker
        self._guard = threading.Lock(); self._locks = {}
        self.hits = 0; self.misses = 0

    def run(self, kind, paths, operation, context=None):
        paths = list(map(Path, paths))
        signature = {'checker': self.checker, 'kind': kind,
                     'inputs': [fingerprint(p) for p in paths], 'context': context}
        key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        target = self.root / (key + '.json')
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            if target.is_file():
                try:
                    entry = json.loads(target.read_text())
                    if entry['signature'] == signature and entry['complete'] is True:
                        self.hits += 1
                        return entry['result']
                except (ValueError, KeyError, TypeError):
                    pass
            started = time.monotonic()
            value = primitives(operation())
            if [fingerprint(p) for p in paths] != signature['inputs']:
                raise ValueError('CHECKPOINT_INPUT_CHANGED_DURING_CHECK')
            atomic_json(target, {'signature': signature, 'complete': True,
                                 'elapsed_s': time.monotonic() - started, 'result': value})
            self.misses += 1
            return value


class HashingReader:
    def __init__(self, stream):
        self.stream = stream; self.hash = hashlib.sha256(); self.bytes = 0

    def read(self, size=-1):
        data = self.stream.read(size)
        self.hash.update(data); self.bytes += len(data)
        return data

    def __getattr__(self, name):
        return getattr(self.stream, name)


def inspect_archive(path):
    """One physical archive read gives compressed and uncompressed identities."""
    path = Path(path); original = hashlib.sha256(); count = 0
    with path.open('rb') as source:
        hashed = HashingReader(source)
        opener = lzma.LZMAFile if path.suffix == '.xz' else gzip.GzipFile
        kwargs = {'filename': hashed} if path.suffix == '.xz' else {'fileobj': hashed}
        with opener(mode='rb', **kwargs) as decoded:
            while chunk := decoded.read(1 << 20):
                original.update(chunk); count += len(chunk)
        # Any trailing bytes must be included in the compressed identity.
        while hashed.read(1 << 20):
            pass
    return {'archive_sha256': hashed.hash.hexdigest(), 'archive_bytes': hashed.bytes,
            'original_sha256': original.hexdigest(), 'original_bytes': count}


def archive_matches(observed, binding):
    return (binding.get('readback_verified') is True and
            all(observed[k] == binding[k] for k in
                ('archive_sha256', 'original_sha256', 'original_bytes')) and
            ('archive_bytes' not in binding or observed['archive_bytes'] == binding['archive_bytes']))
