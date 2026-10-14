"""Real flock controls for restoring a terminal worker after PID reuse."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.design_lab.p01_mainline_preflight import worker_lock_held


class WorkerIdleGuardTests(unittest.TestCase):
    def test_reused_live_pid_with_free_worker_lock_is_idle(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp)
            (queue/'worker.lock').touch()
            (queue/'worker.json').write_text(json.dumps({'pid': os.getpid(), 'status': 'PROVIDER_BLOCKED'}))
            self.assertFalse(worker_lock_held(queue))

    def test_live_cross_process_worker_lock_is_busy(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp)
            path = queue/'worker.lock'
            path.touch()
            code = "import fcntl,sys; f=open(sys.argv[1],'r'); fcntl.flock(f,fcntl.LOCK_EX); print('held',flush=True); sys.stdin.read()"
            proc = subprocess.Popen([sys.executable, '-c', code, str(path)], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(proc.stdout.readline().strip(), 'held')
                self.assertTrue(worker_lock_held(queue))
            finally:
                proc.communicate('', timeout=5)
            self.assertFalse(worker_lock_held(queue))

    def test_missing_or_symlinked_worker_lock_cannot_claim_idle(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'ORIGINAL_WORKER_LOCK_REQUIRED'):
                worker_lock_held(queue)
            actual = queue/'actual'
            actual.touch()
            (queue/'worker.lock').symlink_to(actual)
            with self.assertRaisesRegex(ValueError, 'ORIGINAL_WORKER_LOCK_REQUIRED'):
                worker_lock_held(queue)
