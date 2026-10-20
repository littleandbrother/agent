"""Bounded, byte-preserving artifact storage. No scientific verdicts or deletion policy."""
import ctypes
import errno
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import zlib

RESERVE_BYTES = 10_000_000_000
NATIVE_PEAK_BYTES = 2_000_000_000
BLOCK = 1 << 20


def require_space(directory, additional_bytes, reserve_bytes=RESERVE_BYTES):
    if additional_bytes < 0 or reserve_bytes < 0:
        raise ValueError('STORAGE_ESTIMATE_INVALID')
    if shutil.disk_usage(directory).free < additional_bytes + reserve_bytes:
        raise ValueError('STORAGE_HEADROOM_REQUIRED')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(BLOCK), b''):
            h.update(block)
    return h.hexdigest()


def signature(path):
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or getattr(s, 'st_flags', 0) & 0x40000000:
        raise ValueError('STORAGE_RESIDENT_REGULAR_FILE_REQUIRED')
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def _clone(source, destination):
    if sys.platform != 'darwin':
        return False
    clone = ctypes.CDLL(None, use_errno=True).clonefile
    clone.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    clone.restype = ctypes.c_int
    if clone(os.fsencode(source), os.fsencode(destination), 0) == 0:
        return True
    code = ctypes.get_errno()
    if code in (errno.EXDEV, errno.ENOTSUP, errno.ENOSYS, errno.EINVAL):
        return False
    raise OSError(code, os.strerror(code), str(destination))


def copy_artifact(source, destination, expected=None):
    """Publish a checked independent inode; an existing different file is an error."""
    source, destination = Path(source), Path(destination)
    before = signature(source)
    sha = digest(source)
    if expected is not None and sha != expected:
        raise ValueError('STORAGE_SOURCE_CHANGED')
    if destination.exists() or destination.is_symlink():
        signature(destination)
        if digest(destination) != sha:
            raise ValueError('STORAGE_DESTINATION_CONFLICT')
        if signature(source) != before:
            raise ValueError('STORAGE_SOURCE_CHANGED')
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.artifact-', dir=destination.parent) as directory:
        temporary = Path(directory) / 'data'
        if not _clone(source, temporary):
            # Metadata writes remain possible near a gate; large fallback copies
            # must reserve their full allocation before starting.
            require_space(destination.parent, before[2], RESERVE_BYTES if before[2] >= BLOCK else 0)
            with source.open('rb') as src, temporary.open('xb') as dst:
                shutil.copyfileobj(src, dst, BLOCK)
        if signature(source) != before or digest(temporary) != sha:
            raise ValueError('STORAGE_COPY_READBACK_FAILED')
        temporary.chmod(stat.S_IMODE(source.stat().st_mode))
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        # A link from our independent temporary inode gives no-overwrite atomic
        # publication; deleting the temporary name leaves a single destination.
        try:
            os.link(temporary, destination)
        except FileExistsError:
            signature(destination)
            if digest(destination) != sha:
                raise ValueError('STORAGE_DESTINATION_CONFLICT')
    return destination


def zlib_blocks(path):
    decoder = zlib.decompressobj()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(BLOCK), b''):
            while chunk:
                output = decoder.decompress(chunk, BLOCK)
                if output:
                    yield output
                chunk = decoder.unconsumed_tail
                if decoder.unused_data:
                    raise ValueError('STORAGE_ZLIB_TRAILING_DATA')
    if not decoder.eof:
        raise ValueError('STORAGE_ZLIB_INCOMPLETE')


def compress_zlib(source, destination):
    """Keep zlib's existing byte representation; verify restoration before publish."""
    source, destination = Path(source), Path(destination)
    before = signature(source)
    require_space(destination.parent, before[2] + BLOCK)
    sha = digest(source)
    with tempfile.TemporaryDirectory(prefix='.deflate-', dir=destination.parent) as directory:
        temporary = Path(directory) / 'data'
        encoder = zlib.compressobj(6)
        with source.open('rb') as src, temporary.open('xb') as dst:
            for chunk in iter(lambda: src.read(BLOCK), b''):
                dst.write(encoder.compress(chunk))
            dst.write(encoder.flush())
        restored = hashlib.sha256()
        for chunk in zlib_blocks(temporary):
            restored.update(chunk)
        if restored.hexdigest() != sha or signature(source) != before:
            raise ValueError('STORAGE_ZLIB_READBACK_FAILED')
        copy_artifact(temporary, destination)
    return destination
