import contextlib
import io
import fcntl
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from bfworld.agentlab.concurrency import conversation_slot
from bfworld.agentlab.provider import MODEL, Provider
from bfworld.agentlab.server import Workbench, handler
from bfworld.agentlab.store import Store


def owner(number):
    return 'pi-chat-' + f'{number:016x}'


class SlotTests(unittest.TestCase):
    def test_observed_charge_above_reservation_is_recorded_and_blocks_future_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = Provider(Store(root / 'state'))
            key = root / 'key'; key.write_text('local-test-key')
            usage = {'prompt_tokens': 20000, 'completion_tokens': 8192, 'total_tokens': 28192}
            response = io.BytesIO(json.dumps({'model': MODEL, 'usage': usage}).encode())
            with patch('bfworld.agentlab.provider.KEY_PATH', key), patch('urllib.request.OpenerDirector.open', return_value=response) as upstream:
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, 'PROVIDER_RESERVATION_EXCEEDED'):
                        provider.complete('operator', {'model': MODEL, 'messages': [], 'max_tokens': 4096})
                upstream.assert_called_once()
            row = provider.status()['requests'][0]
            self.assertEqual('SETTLED', row['status'])
            self.assertGreater(row['charged'], row['reserved'])
            self.assertEqual(usage, json.loads(row['usage']))

    def test_output_violation_settles_known_usage_without_accepting_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            provider=Provider(Store(root/'state'))
            key=root/'key';key.write_text('local-test-key')
            usage={'prompt_tokens':10,'completion_tokens':4097,'total_tokens':4107}
            chunks=[{'model':MODEL,'choices':[],'usage':usage}]
            wire=('data: '+json.dumps(chunks[0])+'\n\ndata: [DONE]\n\n').encode()
            with patch('bfworld.agentlab.provider.KEY_PATH',key),patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(wire)):
                with self.assertRaisesRegex(ValueError,'PROVIDER_TOKEN_BOUND_VIOLATION'):
                    provider.complete('operator',{'model':MODEL,'messages':[],'max_tokens':4096},on_chunk=lambda c:None)
            row=provider.status()['requests'][0]
            self.assertEqual('SETTLED',row['status'])
            self.assertEqual(usage,json.loads(row['usage']))
            self.assertEqual('PROVIDER_TOKEN_BOUND_VIOLATION',row['error'])
            self.assertAlmostEqual((10*.30+4097*1.20)/1000000,row['charged'])

    def test_three_slots_same_owner_and_legacy_batch_exclusion(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with contextlib.ExitStack() as stack:
                for number in range(3):
                    stack.enter_context(conversation_slot(home, owner(number)))
                with self.assertRaisesRegex(ValueError, 'PI_SESSION_ALREADY_RUNNING'):
                    with conversation_slot(home, owner(0)):
                        self.fail('same owner admitted twice')
                with self.assertRaisesRegex(ValueError, 'PI_CONVERSATION_CAPACITY'):
                    with conversation_slot(home, owner(3)):
                        self.fail('fourth owner admitted')
                with (home / 'pi-session.lock').open('a') as batch:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(batch, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with (home / 'pi-session.lock').open('a') as batch:
                fcntl.flock(batch, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(ValueError, 'PI_BATCH_ALREADY_RUNNING'):
                    with conversation_slot(home, owner(0)):
                        self.fail('conversation overlapped exclusive batch')
            with conversation_slot(home, owner(3)):
                pass  # Failed acquisitions and completed runs released capacity.

    def test_concurrent_provider_reservations_share_one_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = Store(root / 'state')
            provider = Provider(store)
            key = root / 'test-key'
            key.write_text('local-only-test-key')
            for i in range(3):
                store.grant(owner(i), [], 6, time.time() + 60)
            with store.connect() as db:
                db.execute('UPDATE model_limits SET total_usd=.007')
            entered, release = threading.Event(), threading.Event()

            class Response:
                def __enter__(self):
                    entered.set()
                    return self
                def __exit__(self, *args):
                    pass
                def read(self, _):
                    if not release.wait(5):
                        raise RuntimeError('test timeout')
                    return json.dumps({'model': MODEL, 'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}).encode()

            class Opener:
                def open(self, *args, **kwargs):
                    return Response()

            with patch('bfworld.agentlab.provider.KEY_PATH', key), patch('bfworld.agentlab.provider.urllib.request.build_opener', return_value=Opener()):
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futures = [pool.submit(provider.complete, owner(i), {'model': MODEL, 'messages': [{'role': 'user', 'content': 'one'}]}) for i in range(3)]
                    try:
                        self.assertTrue(entered.wait(3))
                        deadline = time.monotonic() + 3
                        while sum(f.done() for f in futures) < 2 and time.monotonic() < deadline:
                            time.sleep(.01)
                        self.assertEqual(2, sum(f.done() for f in futures))
                        for future in futures:
                            if future.done():
                                self.assertEqual('MODEL_USD_BUDGET', str(future.exception()))
                        status = provider.status()
                        self.assertEqual(1, status['calls'])
                        self.assertLess(status['upper_bound_usd'], .007)
                    finally:
                        release.set()
                    self.assertEqual(1, sum(f.exception() is None for f in futures))


class ParallelChatTests(unittest.TestCase):
    def test_three_actual_pi_processes_overlap_and_keep_messages_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = Workbench(Path(temporary) / 'state')
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(app))
            app.conversations.port = server.server_port
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            release = threading.Event()
            all_entered = threading.Event()
            mutex = threading.Lock()
            payloads = {}

            def local_provider(cid, payload, on_chunk=None):
                with mutex:
                    payloads[cid] = payload
                    if len(payloads) == 3:
                        all_entered.set()
                if not release.wait(25):
                    raise RuntimeError('parallel test did not release provider')
                base = {'id': cid, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': MODEL}
                on_chunk({**base, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': '独立进程 ' + cid}, 'finish_reason': None}]})
                on_chunk({**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})
                usage = {'prompt_tokens': 20, 'completion_tokens': 8, 'total_tokens': 28}
                on_chunk({**base, 'choices': [], 'usage': usage})
                return {'model': MODEL, 'usage': usage}

            app.provider.complete = local_provider
            try:
                folder = app.organization.create_folder('并行项目')
                conversations = [app.conversations.create('任务独立标记-' + str(i), None, 'parallel-' + str(i), folder['id']) for i in range(3)]
                self.assertTrue(all_entered.wait(20), [app.conversations.get(c['id']) for c in conversations])
                self.assertEqual(3, len(app.conversations.processes))
                self.assertEqual(3, len({p.pid for p in app.conversations.processes.values()}))
                self.assertEqual(3, app.conversations.readiness()['concurrency']['limit'])
                for i, conversation in enumerate(conversations):
                    text = json.dumps(payloads[conversation['id']], ensure_ascii=False)
                    self.assertIn('任务独立标记-' + str(i), text)
                    self.assertTrue(all('任务独立标记-' + str(j) not in text for j in range(3) if i != j))
                    self.assertEqual('RUNNING', app.conversations.get(conversation['id'])['status'])
                fourth = app.conversations.create('第四条等待', None, 'fourth', folder['id'])
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and app.conversations.get(fourth['id'])['status'] == 'STARTING':
                    time.sleep(.02)
                self.assertEqual('PI_CONVERSATION_CAPACITY', app.conversations.get(fourth['id'])['error'])
                release.set()
                deadline = time.monotonic() + 15
                while app.conversations.starting and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertFalse(app.conversations.starting)
                for conversation in conversations:
                    detail = app.conversations.detail(conversation['id'])
                    self.assertEqual('IDLE', detail['status'])
                    self.assertTrue(all(m['status'] == 'ACCEPTED' for m in detail['messages']))
                    self.assertTrue(any(e['data']['type'] == 'text_delta' for e in detail['events']))
                    self.assertEqual(folder['id'], detail['shared_context']['folder_id'])
                self.assertNotIn(fourth['id'], payloads)
                with app.store.connect() as db:
                    self.assertEqual(0, db.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0])

                # Shared memory uses a compare-and-swap revision. One writer
                # cannot silently overwrite another task's newly saved note.
                cid1, cid2 = [c['id'] for c in conversations[:2]]
                first = app.organization.memory(cid1)
                app.organization.memory(cid1, {'expected_revision': first['revision'], 'memory': 'common capability finding'})
                with self.assertRaisesRegex(ValueError, 'FOLDER_CHANGED_REFRESH'):
                    app.organization.memory(cid2, {'expected_revision': first['revision'], 'memory': 'stale overwrite'})
                self.assertEqual('common capability finding', app.organization.memory(cid2)['memory'])
            finally:
                release.set()
                for cid in list(app.conversations.processes):
                    app.conversations.stop(cid)
                deadline = time.monotonic() + 5
                while app.conversations.starting and time.monotonic() < deadline:
                    time.sleep(.05)
                server.shutdown()
                server.server_close()
                app.stop.set()
                app.thread.join(3)
                app.lock.close()
