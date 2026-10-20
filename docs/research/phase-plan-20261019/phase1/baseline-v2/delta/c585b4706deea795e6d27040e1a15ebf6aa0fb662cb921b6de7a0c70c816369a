import hashlib
from contextlib import nullcontext
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from bfworld.agentlab import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.source = self.root/'source'
        self.target = self.root/'target'
        self.source.write_bytes(b'original artifact\n' * 4096)
        free = patch.object(storage.shutil, 'disk_usage', return_value=SimpleNamespace(free=100_000_000_000))
        free.start(); self.addCleanup(free.stop)

    def test_clone_is_independent_and_idempotent(self):
        sha = storage.digest(self.source)
        storage.copy_artifact(self.source, self.target, sha)
        storage.copy_artifact(self.source, self.target, sha)
        self.assertEqual(storage.digest(self.target), sha)
        self.assertNotEqual(self.source.stat().st_ino, self.target.stat().st_ino)
        self.assertEqual(self.target.stat().st_nlink, 1)
        self.target.write_bytes(b'new revision')
        self.assertEqual(storage.digest(self.source), sha)
        self.assertFalse(list(self.root.glob('.artifact-*')))

    def test_existing_conflict_is_never_overwritten(self):
        self.target.write_bytes(b'protected existing file')
        with self.assertRaisesRegex(ValueError, 'DESTINATION_CONFLICT'):
            storage.copy_artifact(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b'protected existing file')

    def test_trace_append_keeps_completed_snapshot_unchanged(self):
        original = self.source.read_bytes()
        storage.copy_artifact(self.source, self.target)
        with self.source.open('ab') as stream:
            stream.write(b'next turn\n')
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.source.read_bytes(), original+b'next turn\n')

    def test_expected_hash_rejected_before_publication(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            storage.copy_artifact(self.source, self.target, '0'*64)
        self.assertFalse(self.target.exists())

    def test_fallback_requires_full_peak_space(self):
        self.source.write_bytes(b'x' * storage.BLOCK)
        with patch.object(storage, '_clone', return_value=False), patch.object(
                storage.shutil, 'disk_usage', return_value=SimpleNamespace(free=storage.RESERVE_BYTES)):
            with self.assertRaisesRegex(ValueError, 'HEADROOM_REQUIRED'):
                storage.copy_artifact(self.source, self.target)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('.artifact-*')))

    def test_fallback_is_independent(self):
        with patch.object(storage, '_clone', return_value=False):
            storage.copy_artifact(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertNotEqual(self.source.stat().st_ino, self.target.stat().st_ino)

    def test_source_changed_during_copy_aborts_and_cleans(self):
        def changed(source, destination):
            destination.write_bytes(source.read_bytes())
            source.write_bytes(b'changed during copy')
            return True
        with patch.object(storage, '_clone', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'COPY_READBACK_FAILED'):
                storage.copy_artifact(self.source, self.target)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('.artifact-*')))

    def test_symlink_is_not_hydrated_or_copied(self):
        link = self.root/'link'; link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'RESIDENT_REGULAR'):
            storage.copy_artifact(link, self.target)

    def test_dataless_file_is_rejected_before_content_read(self):
        with patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=0o100644, st_flags=0x40000000)):
            with self.assertRaisesRegex(ValueError, 'RESIDENT_REGULAR'):
                storage.signature(self.source)

    def test_zlib_preserves_existing_encoding_and_bounded_reads(self):
        for data in (b'', b'x' * (3*storage.BLOCK), os.urandom(2*storage.BLOCK + 17)):
            self.source.write_bytes(data)
            self.target.unlink(missing_ok=True)
            storage.compress_zlib(self.source, self.target)
            self.assertEqual(self.target.read_bytes(), zlib.compress(data, 6))
            blocks = list(storage.zlib_blocks(self.target))
            self.assertTrue(all(len(block) <= storage.BLOCK for block in blocks))
            self.assertEqual(hashlib.sha256(b''.join(blocks)).digest(), hashlib.sha256(data).digest())
        self.assertFalse(list(self.root.glob('.deflate-*')))

    def test_truncated_and_trailing_zlib_are_rejected(self):
        for data, error in ((zlib.compress(b'data')[:-1], 'INCOMPLETE'),
                            (zlib.compress(b'data') + b'trailing', 'TRAILING')):
            self.target.write_bytes(data)
            with self.assertRaisesRegex(ValueError, error):
                list(storage.zlib_blocks(self.target))

    def test_failed_compression_readback_keeps_source_and_no_target(self):
        original = self.source.read_bytes()
        with patch.object(storage, 'zlib_blocks', return_value=iter([b'corrupt'])):
            with self.assertRaisesRegex(ValueError, 'READBACK_FAILED'):
                storage.compress_zlib(self.source, self.target)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('.deflate-*')))

    def test_waveform_exception_cleans_readback(self):
        from bfworld.agentlab.design_lab import feedback_native
        compressed = self.root/'system.raw.zlib'
        compressed.write_bytes(zlib.compress(b'complete raw bytes'))
        with patch.object(feedback_native, 'read_raw', side_effect=ValueError('injected reader failure')):
            with self.assertRaisesRegex(ValueError, 'injected reader'):
                feedback_native.waveform(self.root, 1)
        self.assertFalse(list(self.root.glob('.readback-*')))
        self.assertTrue(compressed.exists())

    def test_native_headroom_rejection_precedes_budget_and_dispatch(self):
        from bfworld.agentlab.design_lab import feedback_native
        cache = self.root/'cache'; cache.mkdir()
        calls = []
        with patch.object(feedback_native, 'native_slot', return_value=nullcontext()), patch.object(
                feedback_native, 'require_space', side_effect=ValueError('STORAGE_HEADROOM_REQUIRED')):
            with self.assertRaisesRegex(ValueError, 'HEADROOM_REQUIRED'):
                feedback_native.native(self.root/'native', cache, 'finite test deck', {},
                                       lambda: calls.append('budget'), 1)
        self.assertEqual(calls, [])
        self.assertFalse(list(cache.rglob('dispatch.json')))


if __name__ == '__main__':
    unittest.main()
