"""Byte-preserving RAW storage; no resampling, numeric or acceptance change."""
import lzma
import hashlib
import json
import re
from pathlib import Path


def identity(stream):
    sha, count = hashlib.sha256(), 0
    while chunk := stream.read(1 << 20):
        sha.update(chunk); count += len(chunk)
    return sha.hexdigest(), count


def archive_raw(path):
    path = Path(path)
    if path.is_symlink() or path.suffix != '.raw':
        raise ValueError('RAW_ARCHIVE_INPUT_INVALID')
    target = path.with_suffix('.raw.xz')
    receipt = path.with_suffix('.raw.archive.json')
    if target.exists() or receipt.exists():
        raise ValueError('RAW_ARCHIVE_ALREADY_EXISTS')
    with path.open('rb') as f: original_sha, original_bytes = identity(f)
    temp = target.with_suffix('.xz.partial')
    # Standard XZ's reversible byte-delta filter follows the native RAW row
    # stride; it does not change a single restored sample or header byte.
    # Plain XZ remains available for arbitrary/nonstandard RAW headers.
    with path.open('rb') as f: header = f.read(32768).decode('utf-16-le', errors='replace')
    variables = re.search(r'No. Variables:\s*(\d+)', header)
    stride = 8+4*(int(variables[1])-1) if variables and 'Flags: real' in header else None
    filters = ([{'id': lzma.FILTER_DELTA, 'dist': stride}] if stride and 1<=stride<=256 else [])
    filters.append({'id': lzma.FILTER_LZMA2, 'preset': 1})
    with path.open('rb') as source, temp.open('wb') as destination:
        with lzma.LZMAFile(destination, mode='wb', filters=filters) as z:
            while chunk := source.read(1 << 20): z.write(chunk)
    with lzma.open(temp, 'rb') as restored: restored_sha, restored_bytes = identity(restored)
    if (restored_sha, restored_bytes) != (original_sha, original_bytes):
        raise ValueError('RAW_ARCHIVE_READBACK_FAILED')
    temp.replace(target)
    with target.open('rb') as f: compressed_sha, compressed_bytes = identity(f)
    value = {'schema_version': 'bf-native-lossless-archive-v1', 'original_name': path.name,
             'original_bytes': original_bytes, 'original_sha256': original_sha,
             'archive_name': target.name, 'archive_bytes': compressed_bytes, 'archive_sha256': compressed_sha,
             'codec':'xz/lzma2+byte-delta' if stride and 1<=stride<=256 else 'xz/lzma2',
             'row_stride_bytes':stride, 'readback_verified': True, 'restore_command': 'xz -dk ' + target.name}
    receipt.write_text(json.dumps(value, indent=2) + '\n')
    path.unlink()
    return value
