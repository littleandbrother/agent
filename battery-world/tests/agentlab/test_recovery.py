import io
import json
import socket
import ssl
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from bfworld.agentlab.provider import Provider
from bfworld.agentlab.recovery import ObservedHTTPSHandler, RequestNotSent, is_not_sent
from bfworld.agentlab.store import Store


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'state')
        self.provider = Provider(self.store)
        self.recovery = self.provider.recovery
        self.payload = {'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 4096}
        self.key = Path(self.tmp.name) / 'key'
        self.key.write_text('local-test-only')
        self.key_patch = patch('bfworld.agentlab.provider.KEY_PATH', self.key)
        self.key_patch.start()
        with self.store.connect() as db:
            db.execute('CREATE TABLE chat_messages(id TEXT PRIMARY KEY,conversation TEXT,status TEXT)')

    def tearDown(self):
        self.key_patch.stop()
        self.tmp.cleanup()

    def response(self):
        return io.BytesIO(json.dumps({'model': 'deepseek-flash', 'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}}).encode())

    def message(self, owner='chat', mid='m1'):
        self.store.grant(owner, [], 6, time.time() + 700)
        with self.store.connect() as db:
            db.execute('INSERT INTO chat_messages VALUES(?,?,?)', (mid, owner, 'QUEUED'))
        self.recovery.issue(owner, mid)

    def test_actual_tls_close_is_observed_before_any_application_write(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(10)
        records = []
        def close_handshake():
            with listener:
                conn, _ = listener.accept()
                with conn:
                    records.append(conn.recv(8192))
        thread = threading.Thread(target=close_handshake, daemon=True)
        thread.start()
        request = urllib.request.Request('https://127.0.0.1:' + str(listener.getsockname()[1]), data=b'private completion body')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), ObservedHTTPSHandler())
        with patch.object(ssl.SSLSocket, 'sendall', side_effect=AssertionError('HTTP_APPLICATION_BYTES_SENT')) as send:
            with self.assertRaises(urllib.error.URLError) as caught:
                opener.open(request, timeout=10)
            self.assertTrue(is_not_sent(caught.exception))
            send.assert_not_called()
        thread.join(10)
        self.assertEqual(22, records[0][0])  # TLS handshake record, not application data.

    def test_connect_failure_retains_reservation_without_poisoning_next_dispatch(self):
        error = urllib.error.URLError(RequestNotSent('TLS connect failed'))
        with patch('urllib.request.OpenerDirector.open', side_effect=error):
            with self.assertRaises(urllib.error.URLError): self.provider.complete('operator', self.payload)
        status = self.provider.status()
        self.assertEqual('NOT_SENT', status['requests'][0]['status'])
        self.assertIsNone(status['requests'][0]['usage'])
        held = status['upper_bound_usd']
        self.assertGreater(held, 0)
        with patch('urllib.request.OpenerDirector.open', return_value=self.response()):
            self.provider.complete('operator', self.payload)
        self.assertGreater(self.provider.status()['upper_bound_usd'], held)

    def test_generic_ssl_read_error_stays_unknown_and_blocks_retry(self):
        error = urllib.error.URLError(ssl.SSLEOFError('EOF after request may have been sent'))
        self.assertFalse(is_not_sent(error))
        with patch('urllib.request.OpenerDirector.open', side_effect=error):
            with self.assertRaises(urllib.error.URLError): self.provider.complete('operator', self.payload)
        self.assertEqual('UNKNOWN', self.provider.status()['requests'][0]['status'])
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_STOP'): self.provider.complete('operator', self.payload)

    def test_expired_batch_stays_blocked_but_new_user_has_bounded_lease(self):
        with self.store.connect() as db: db.execute('UPDATE model_limits SET expires=0')
        before = self.provider.status()['limits']
        with self.assertRaisesRegex(ValueError, 'MODEL_WALL_BUDGET'): self.provider.complete('operator', self.payload)
        self.message()
        with patch('urllib.request.OpenerDirector.open', return_value=self.response()):
            self.provider.complete('chat', self.payload)
        self.assertEqual(before, self.provider.status()['limits'])
        with self.store.connect() as db: db.execute('UPDATE interactive_leases SET expires=0')
        with self.assertRaisesRegex(ValueError, 'CHAT_TURN_WALL_BUDGET'): self.provider.complete('chat', self.payload)
        with self.assertRaisesRegex(ValueError, 'MODEL_WALL_BUDGET'): self.provider.complete('operator', self.payload)

    def test_duplicate_or_background_operation_cannot_renew_and_recall_revokes(self):
        self.message()
        with self.store.connect() as db: before = dict(db.execute('SELECT * FROM interactive_leases').fetchone())
        with patch('bfworld.agentlab.recovery.time.time', return_value=before['expires'] + 10): self.recovery.issue('chat', 'm1')
        with self.store.connect() as db: self.assertEqual(before, dict(db.execute('SELECT * FROM interactive_leases').fetchone()))
        with self.assertRaisesRegex(ValueError, 'LEASE_REQUIRES'): self.recovery.issue('background', 'm1')
        with self.store.connect() as db: db.execute("UPDATE chat_messages SET status='WITHDRAWN'")
        with self.assertRaisesRegex(ValueError, 'CHAT_TURN_AUTH_REQUIRED'): self.provider.complete('chat', self.payload)

    def test_owner_cap_rejects_before_dispatch(self):
        self.message()
        with self.store.connect() as db: db.execute('INSERT INTO owner_model_caps VALUES(?,?)', ('chat', .000001))
        with patch('urllib.request.OpenerDirector.open') as transport:
            with self.assertRaisesRegex(ValueError, 'MODEL_OWNER_USD_BUDGET'): self.provider.complete('chat', self.payload)
            transport.assert_not_called()
        self.assertEqual(0, self.provider.status()['calls'])

    def test_forged_historical_source_cannot_release_unknown(self):
        source = Path(self.tmp.name) / 'fake-ssl.c'
        source.write_text('not the verified CPython source')
        with patch('bfworld.agentlab.recovery.sys.version_info', (3, 11, 9)):
            with self.assertRaisesRegex(ValueError, 'SOURCE_MISMATCH'):
                self.recovery.resolve_historical_handshake('unknown', {'ssl_source': str(source)})
        with self.store.connect() as db: self.assertEqual(0, db.execute('SELECT COUNT(*) FROM model_resolutions').fetchone()[0])
