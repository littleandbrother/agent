"""Versioned trusted-operator cache with artifact-bound canonical result values.

This detects local inconsistency/corruption, not an adversary able to rewrite a
manifest and all its hashes. Old namespaces are preserved and never migrated.
"""
import os
import json
import time
import secrets
from pathlib import Path
from .contracts import digest, file_hash, write_json, ChainError

CACHE_SCHEMA = 'simulation-checkpoint-v2'
CACHE_NAMESPACE = 'simulation-cache-v2'
VALUE_FILE = 'producer-value.json'

class Cache:
    def __init__(self, root, event=lambda *args: None):
        self.root = Path(root) / CACHE_NAMESPACE
        self.root.mkdir(parents=True, exist_ok=True)
        self.event = event

    def stage(self, name, inputs, producer):
        key = digest({'cache_schema': CACHE_SCHEMA, 'stage': name, 'inputs': inputs})
        dest = self.root / name / key
        manifest = dest / 'checkpoint.json'
        if manifest.is_file():
            m = json.loads(manifest.read_text())
            if (m.get('schema_version') != CACHE_SCHEMA or m.get('key') != key
                    or m.get('stage') != name or digest(m.get('inputs')) != digest(inputs)
                    or not isinstance(m.get('files'), list) or not m['files']):
                raise ChainError('tool_fail', 'Invalid checkpoint schema/identity ' + name)
            entries = m['files']
            if sum(f.get('path') == VALUE_FILE for f in entries) != 1:
                raise ChainError('tool_fail', 'Missing/duplicate canonical value artifact ' + name)
            for f in entries:
                relative = Path(f['path'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ChainError('tool_fail', 'Invalid checkpoint artifact path ' + name)
                path = dest / relative
                if path.is_symlink() or not path.is_file() or file_hash(path) != f['sha256']:
                    raise ChainError('tool_fail', 'Checkpoint hash mismatch: ' + name + '/' + f['path'])
            # The verified artifact is the sole returned authority. The duplicate
            # manifest value is retained for readability but must agree exactly.
            value = json.loads((dest / VALUE_FILE).read_text())
            if 'value' not in m or digest(m['value']) != digest(value):
                raise ChainError('tool_fail', 'Checkpoint metadata/value mismatch: ' + name)
            self.event('stage_cached', {'stage': name, 'key': key})
            return dest, value, key, True
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.parent / (key + '.partial-' + secrets.token_hex(4))
        temp.mkdir()
        self.event('stage_started', {'stage': name, 'key': key})
        started = time.time()
        try:
            value = producer(temp)
            if (temp / VALUE_FILE).exists() or (temp / 'checkpoint.json').exists():
                raise ChainError('tool_fail', 'Producer used reserved cache artifact name')
            write_json(temp / VALUE_FILE, value)
            value = json.loads((temp / VALUE_FILE).read_text())
            files = [{'path': str(p.relative_to(temp)), 'bytes': p.stat().st_size,
                      'sha256': file_hash(p)} for p in sorted(temp.rglob('*'))
                     if p.is_file() and not p.is_symlink()]
            m = {'schema_version': CACHE_SCHEMA, 'key': key, 'stage': name,
                 'inputs': inputs, 'value': value, 'files': files,
                 'elapsed_s': time.time() - started}
            write_json(temp / 'checkpoint.json', m)
            # Callers retain the existing cache lock; rename is the commit point.
            os.rename(temp, dest)
            self.event('stage_completed', {'stage': name, 'key': key, 'files': len(files)})
            return dest, value, key, False
        except Exception as exc:
            write_json(temp / 'failure.json', {'error': str(exc), 'elapsed_s': time.time() - started})
            self.event('stage_failed', {'stage': name, 'key': key, 'error': str(exc)})
            raise
