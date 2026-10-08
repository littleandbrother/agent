"""Losslessly archive only this turn's finished D5 native waveforms.

Original result/manifest bytes are never rewritten. A recovery receipt binds
the original RAW size/hash to a verified gzip stream before RAW removal.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def stream_identity(stream):
    sha, count = hashlib.sha256(), 0
    while chunk := stream.read(1 << 20):
        sha.update(chunk); count += len(chunk)
    return sha.hexdigest(), count


def archive_raw(path):
    path = Path(path)
    if path.is_symlink() or path.suffix != '.raw':
        raise ValueError('RAW_ARCHIVE_INPUT_INVALID')
    target = path.with_suffix('.raw.gz')
    receipt = path.with_suffix('.raw.archive.json')
    if target.exists() or receipt.exists():
        raise ValueError('RAW_ARCHIVE_ALREADY_EXISTS')
    with path.open('rb') as f:
        original_sha, original_bytes = stream_identity(f)
    temp = target.with_suffix('.gz.partial')
    with path.open('rb') as source, temp.open('wb') as destination:
        with gzip.GzipFile(filename='', mode='wb', fileobj=destination, compresslevel=3, mtime=0) as z:
            while chunk := source.read(1 << 20): z.write(chunk)
    with gzip.open(temp, 'rb') as restored:
        restored_sha, restored_bytes = stream_identity(restored)
    if (restored_sha, restored_bytes) != (original_sha, original_bytes):
        raise ValueError('RAW_ARCHIVE_READBACK_FAILED')
    temp.replace(target)
    with target.open('rb') as f:
        compressed_sha, compressed_bytes = stream_identity(f)
    value = {'schema_version': 'bf-native-lossless-archive-v1', 'original_name': path.name,
             'original_bytes': original_bytes, 'original_sha256': original_sha,
             'archive_name': target.name, 'archive_bytes': compressed_bytes, 'archive_sha256': compressed_sha,
             'readback_verified': True, 'restore_command': 'gzip -dk ' + target.name}
    receipt.write_text(json.dumps(value, indent=2) + '\n')
    path.unlink()
    return value


def archive_run(root):
    root = Path(root).resolve()
    if root.parent.name != 'door-selfpower-v1':
        raise ValueError('ONLY_NEW_D5_RUNS_MAY_BE_ARCHIVED')
    result_path = root / 'result.json'
    result_bytes = result_path.read_bytes()
    result = json.loads(result_bytes)
    status = result.get('run_status', result.get('status'))
    if status is None or status == 'running':
        raise ValueError('ACTIVE_RUN_MUST_NOT_BE_ARCHIVED')
    if root.name.startswith('probe-'):
        log = (root / 'system.log').read_text(errors='replace')
        if 'Total elapsed time:' not in log:
            raise ValueError('PROBE_NATIVE_COMPLETION_REQUIRED')
        if hashlib.sha256((root / 'system.cir').read_bytes()).hexdigest() != result['deck_sha256']:
            raise ValueError('PROBE_DECK_IDENTITY_CHANGED')
    output = root / 'native-archive-recovery.json'
    if output.exists(): raise ValueError('RECOVERY_RECEIPT_ALREADY_EXISTS')
    records = []
    for path in sorted(root.rglob('*.raw')):
        value = archive_raw(path)
        records.append({'path': str(path.relative_to(root)), **value})
    if not records: return {'archived': 0}
    if result_path.read_bytes() != result_bytes:
        raise ValueError('RESULT_CHANGED_DURING_ARCHIVE')
    output.write_text(json.dumps({'records': records, 'old_result_unchanged': True,
        'result_sha256': hashlib.sha256(result_bytes).hexdigest()}, indent=2) + '\n')
    return {'archived': len(records), 'saved_bytes': sum(r['original_bytes']-r['archive_bytes'] for r in records)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run', type=Path, required=True)
    args = p.parse_args(); print(json.dumps(archive_run(args.run)))
