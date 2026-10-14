import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from scripts.design_lab import watch_paper_receipts as observer


class PassiveObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = self.root / 'campaign/parallel-20261009/pi-queue'
        self.queue.mkdir(parents=True)
        self.index = self.queue.parent / 'pi-session-index.json'
        self.index.write_text('{"sessions":[]}')
        self.owner = 'pi-chat-1111111111111111'
        self.owners = {self.owner: 'P10'}
        self.initial = {self.owner: 'original-q1'}
        self.item = {'id': 'original-q1', 'owner': self.owner, 'paper': 'P10', 'status': 'RUNNING', 'started': 0}
        self.path = self.queue / (self.owner + '.json')
        self.path.write_text(json.dumps(self.item))
        (self.queue / 'worker.json').write_text('{"pid":1,"status":"RUNNING"}')
        self.dbpath = self.root / 'runtime/state/workbench.sqlite'
        self.dbpath.parent.mkdir(parents=True)
        with sqlite3.connect(self.dbpath) as db:
            db.execute('CREATE TABLE model_requests(owner TEXT, created REAL, status TEXT, charged REAL, reserved REAL)')
            db.execute('INSERT INTO model_requests VALUES(?,1,"UNKNOWN",0,.8)', (self.owner,))
            db.execute('INSERT INTO model_requests VALUES(?,2,"SETTLED",.2,.3)', (self.owner,))
        self.index_sha = observer.sha(self.index)

    def snapshot(self, **kwargs):
        return observer.read_snapshot(self.root, self.owners, self.initial, self.index_sha, **kwargs)

    def test_ro_snapshot_preserves_unknown_and_database(self):
        before = self.dbpath.read_bytes()
        value = self.snapshot()
        self.assertTrue(value['fresh'])
        row = value['papers'][0]
        self.assertEqual(.8, row['unknown_full_reserved_usd'])
        self.assertEqual(.2, row['registered_charged_usd'])
        self.assertEqual(2, row['observed_requests'])
        self.assertFalse(row['full_product_passed'])
        self.assertEqual(before, self.dbpath.read_bytes())
        self.assertEqual(0, value['workbench_instances_created'])

    def test_real_exclusive_lock_is_bounded_then_recovers(self):
        writer = sqlite3.connect(self.dbpath)
        writer.execute('BEGIN EXCLUSIVE')
        try:
            started = time.monotonic()
            state = observer.status_sample(self.root, self.owners, self.initial, self.index_sha, 123)
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual('DEGRADED_DATABASE_BUSY', state['status'])
            self.assertFalse(state['fresh'])
            self.assertEqual([], state['papers'])
            self.assertEqual(123, state['last_healthy_at'])
        finally:
            writer.rollback()
            writer.close()
        state = observer.status_sample(self.root, self.owners, self.initial, self.index_sha)
        self.assertTrue(state['fresh'])
        self.assertEqual(2, state['papers'][0]['observed_requests'])

    def test_identity_drift_is_terminal_and_never_adopted(self):
        self.path.write_text(json.dumps({**self.item, 'id': 'replacement'}))
        state = observer.status_sample(self.root, self.owners, self.initial, self.index_sha)
        self.assertEqual('OBSERVER_IDENTITY_ERROR', state['status'])
        self.assertFalse(state['fresh'])
        self.assertIn('ORIGINAL_QUEUE_REPLACED', state['error'])

    def test_non_lock_sql_error_is_not_silently_retried(self):
        with sqlite3.connect(self.dbpath) as db:
            db.execute('DROP TABLE model_requests')
        state = observer.status_sample(self.root, self.owners, self.initial, self.index_sha)
        self.assertEqual('OBSERVER_READ_ERROR', state['status'])
        self.assertFalse(state['fresh'])
        self.assertEqual([], state['papers'])

    def test_waiting_and_unknown_queue_states_are_not_phase_completion(self):
        for state in ('WAITING_NATIVE_IDENTITY_RELEASE', 'WAITING_QUALIFIED_RELEASE', 'QUEUED', 'RUNNING', 'UNRECOGNIZED'):
            self.assertFalse(observer.phase_ended(state), state)
        for state in ('FILE_CHECKS_COMPLETE', 'REPAIR_REQUIRED', 'DISPATCH_FAILED', 'CANCELLED'):
            self.assertTrue(observer.phase_ended(state), state)


if __name__ == '__main__':
    unittest.main()
