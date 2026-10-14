import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from bfworld.agentlab.chat import Conversations


class IncrementalTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.chat = Conversations.__new__(Conversations)
        self.chat.home = Path(self.tmp.name)
        self.chat.lock = threading.RLock()
        self.chat._trace_cursors = {}
        self.chat._trace_locks = {}
        self.chat.processes = {}
        self.chat.recalls = Mock()
        self.cid = 'pi-chat-1111111111111111'
        folder = self.chat.home / 'sessions' / self.cid
        folder.mkdir(parents=True)
        self.path = folder / 'trace.jsonl'
        self.events = {}
        self.calls = []
        def event(cid, source, data):
            self.calls.append(source)
            if source in self.events:
                return False
            self.events[source] = data
            return True
        self.chat.event = event
        self.chat.state = Mock()
        self.chat.get = Mock(return_value={'status': 'STARTING'})

    def test_idle_poll_does_not_replay_old_rows(self):
        rows = [{'type': 'text_delta', 'delta': str(i)} for i in range(400)]
        self.path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        self.chat.ingest(self.cid)
        for _ in range(20):
            self.chat.ingest(self.cid)
        self.assertEqual(400, len(self.calls))
        self.assertEqual(rows, list(self.events.values()))
        with self.path.open('a') as stream:
            stream.write('{"type":"text_delta","delta":"next"}\n')
        self.chat.ingest(self.cid)
        self.assertEqual('trace-400', self.calls[-1])

    def test_partial_utf8_and_unterminated_line_are_deferred(self):
        raw = (json.dumps({'type': 'text_delta', 'delta': '继续'}, ensure_ascii=False) + '\n').encode()
        split = raw.index('继'.encode()) + 1
        self.path.write_bytes(raw[:split])
        self.chat.ingest(self.cid)
        self.assertEqual([], self.calls)
        with self.path.open('ab') as stream:
            stream.write(raw[split:-1])
        self.chat.ingest(self.cid)
        self.assertEqual([], self.calls)
        with self.path.open('ab') as stream:
            stream.write(b'\n')
        self.chat.ingest(self.cid)
        self.assertEqual('继续', self.events['trace-0']['delta'])

    def test_concurrent_drains_have_exact_line_ids(self):
        self.path.write_text(''.join('{"type":"text_delta"}\n' for _ in range(120)))
        threads = [threading.Thread(target=self.chat.ingest, args=(self.cid,)) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(120, len(self.calls))
        self.assertEqual({f'trace-{i}' for i in range(120)}, set(self.calls))

    def test_cold_recovery_preserves_history_without_replaying_terminal_state(self):
        self.path.write_text('{"type":"turn_error","error":"old"}\n{"type":"chat_idle"}\n')
        self.chat.ingest(self.cid, execution_state=False)
        self.chat.state.assert_not_called()
        self.chat.ingest(self.cid)
        self.chat.state.assert_not_called()
        with self.path.open('a') as stream:
            stream.write('{"type":"turn_error","error":"new"}\n')
        self.chat.ingest(self.cid)
        self.chat.state.assert_called_once_with(self.cid, 'FAILED', 'new')

    def test_truncated_or_rewritten_prefix_is_rejected(self):
        self.path.write_text('{"type":"text_delta","delta":"first"}\n')
        self.chat.ingest(self.cid)
        before = dict(self.events)
        self.path.write_text('{"type":"text_delta","delta":"other"}\n')
        with self.assertRaisesRegex(ValueError, 'TRACE_HISTORY_CHANGED'):
            self.chat.ingest(self.cid)
        self.assertEqual(before, self.events)


if __name__ == '__main__':
    unittest.main()
