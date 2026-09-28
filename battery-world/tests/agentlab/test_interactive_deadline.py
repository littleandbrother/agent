import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bfworld.agentlab.launcher import wait_interactive, freeze
from bfworld.agentlab.recovery import Recovery, INTERACTIVE_WALL_SECONDS
from bfworld.agentlab.store import Store


class ClockProcess:
    """Advances the test clock through real supervisor waits, not 30-minute sleeps."""
    pid=12345
    def __init__(self, clock, finish_at=None, graceful=True, tick=None):
        self.clock=clock;self.finish_at=finish_at;self.graceful=graceful;self.tick=tick
        self.stdin=io.BytesIO();self.returncode=None;self.waits=[]
    def poll(self):return self.returncode
    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.returncode is not None:return self.returncode
        if self.graceful and b'"close"' in self.stdin.getvalue():
            self.returncode=0;return 0
        self.clock[0]+=timeout
        if self.tick:self.tick()
        if self.finish_at is not None and self.clock[0]>=self.finish_at:
            self.returncode=0;return 0
        raise subprocess.TimeoutExpired('fixture',timeout)


class InteractiveDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'state')
        self.recovery=Recovery(self.store);self.clock=[0.]
        with self.store.connect() as db:db.execute('CREATE TABLE chat_messages(id TEXT PRIMARY KEY,conversation TEXT,status TEXT)')
        self.clock_patch=patch('bfworld.agentlab.recovery.time.time',side_effect=lambda:self.clock[0]);self.clock_patch.start()
        self.message('first')
    def tearDown(self):self.clock_patch.stop();self.tmp.cleanup()
    def message(self,mid):
        with self.store.connect() as db:db.execute("INSERT INTO chat_messages VALUES(?,'chat','QUEUED')",(mid,))
        self.recovery.issue('chat',mid)
    def test_long_engineering_wait_survives_the_old_600_second_timer(self):
        self.assertEqual(1800,INTERACTIVE_WALL_SECONDS)
        proc=ClockProcess(self.clock,finish_at=1500)
        self.assertIsNone(wait_interactive(proc,self.store,'chat'))
        self.assertEqual(1500,self.clock[0]);self.assertEqual(b'',proc.stdin.getvalue())
    def test_new_user_message_extends_deadline_but_duplicate_does_not(self):
        def tick():
            if self.clock[0]==1000:self.message('second')
            if self.clock[0]==1800:self.recovery.issue('chat','second')
        proc=ClockProcess(self.clock,finish_at=2000,tick=tick)
        self.assertIsNone(wait_interactive(proc,self.store,'chat'))
        with self.store.connect() as db:self.assertEqual(2800,self.recovery.lease(db,'chat')['expires'])
    def test_deadline_sends_close_and_records_pause_instead_of_success(self):
        self.clock[0]=1800;proc=ClockProcess(self.clock)
        with patch('bfworld.agentlab.launcher.os.killpg') as kill:
            result=wait_interactive(proc,self.store,'chat')
        self.assertEqual('CHAT_TURN_WALL_BUDGET',result['error']);self.assertFalse(result['forced_kill'])
        self.assertEqual('first',result['message_id']);kill.assert_not_called()
        self.assertEqual({'type':'close'},json.loads(proc.stdin.getvalue()))
        with self.store.connect() as db:self.assertEqual(1,db.execute("SELECT count(*) FROM events WHERE kind='interactive_deadline_reached'").fetchone()[0])
    def test_unresponsive_process_is_killed_only_after_shutdown_grace(self):
        self.clock[0]=1800;proc=ClockProcess(self.clock,graceful=False)
        def kill(*args):proc.returncode=-9
        with patch('bfworld.agentlab.launcher.os.killpg',side_effect=kill) as signal:
            result=wait_interactive(proc,self.store,'chat')
        self.assertTrue(result['forced_kill']);self.assertEqual(1810,self.clock[0]);signal.assert_called_once()
    def test_withdrawn_lease_does_not_keep_process_alive(self):
        with self.store.connect() as db:db.execute("UPDATE chat_messages SET status='WITHDRAWN'")
        result=wait_interactive(ClockProcess(self.clock),self.store,'chat')
        self.assertEqual('CHAT_TURN_AUTH_REQUIRED',result['error'])
    def test_new_message_racing_expiry_is_rechecked_before_closing(self):
        self.clock[0]=1800
        def expired(proc):self.message('racing');return False
        proc=ClockProcess(self.clock,finish_at=1801)
        self.assertIsNone(wait_interactive(proc,self.store,'chat',expired));self.assertEqual(b'',proc.stdin.getvalue())
    def test_batch_and_interactive_manifest_caps_are_distinct(self):
        batch=json.loads((freeze(home_root=self.tmp.name,app_entry='main.js')/'manifest.json').read_text())
        interactive=json.loads((freeze(home_root=self.tmp.name,app_entry='chat-product.js')/'manifest.json').read_text())
        self.assertEqual(600,batch['session_caps']['wall_seconds'])
        self.assertEqual(1800,interactive['session_caps']['wall_seconds'])
