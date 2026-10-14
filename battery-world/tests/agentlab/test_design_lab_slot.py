from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from bfworld.agentlab.design_lab.native_slot import native_slot


class NativeProcessLease(unittest.TestCase):
    def probe(self, path):
        code = "from bfworld.agentlab.design_lab.native_slot import native_slot\nimport sys\ntry:\n with native_slot(sys.argv[1],blocking=False): print('ACQUIRED')\nexcept BlockingIOError: print('BLOCKED')\n"
        source=Path(__file__).resolve().parents[2]/'packages/python/bfworld/src'
        env={**os.environ,'PYTHONPATH':str(source)+os.pathsep+os.environ.get('PYTHONPATH','')}
        return subprocess.check_output([sys.executable, '-c', code, str(path)], text=True, timeout=5,env=env).strip()

    def test_phase_can_handoff_to_engineering_thread_without_unlocking_other_process(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'slot'; entered = threading.Event(); release = threading.Event()
            def engineering():
                with native_slot(path): entered.set(); release.wait(5)
            with native_slot(path):
                thread = threading.Thread(target=engineering); thread.start()
                try:
                    self.assertTrue(entered.wait(2), 'phase/engineering deadlock')
                    self.assertEqual('BLOCKED', self.probe(path))
                finally: release.set(); thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual('ACQUIRED', self.probe(path))

    def test_outer_exit_cannot_release_a_live_engineering_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'slot'; entered = threading.Event(); release = threading.Event()
            def engineering():
                with native_slot(path): entered.set(); release.wait(5)
            with native_slot(path):
                thread = threading.Thread(target=engineering); thread.start()
                self.assertTrue(entered.wait(2))
            try: self.assertEqual('BLOCKED', self.probe(path))
            finally: release.set(); thread.join(3)
            self.assertEqual('ACQUIRED', self.probe(path))


if __name__ == '__main__': unittest.main()
