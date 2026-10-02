import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bfworld.agentlab.store import Store
from bfworld.agentlab.provider import Provider
from bfworld.agentlab.simulation_tasks import SimulationTasks
from bfworld.agentlab.design_pilot_view import projection, export_projection, evidence_file
from bfworld.agentlab.simulation_chain.contracts import file_hash


class PilotProjection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.store = Store(self.home/'state')
        Provider(self.store)
        SimulationTasks(self.store)
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE conversations(id TEXT, status TEXT, error TEXT, title TEXT, created REAL);
                CREATE TABLE engineering_jobs(id TEXT, owner TEXT, status TEXT, created REAL, started REAL,
                  ended REAL, request TEXT, result TEXT, error TEXT);''')
            db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',
                       ('door-test', 1, 5, 2, 'test-model', 'private authorization'))
            db.execute('INSERT INTO research_model_owners VALUES(?,?,?)', ('a', 'door-test', 't1'))
            db.execute('INSERT INTO conversations VALUES(?,?,?,?,?)', ('a', 'FAILED', 'PROVIDER_STREAM_LIMIT', 'test', 1))
            db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?)',
                       ('unknown-a', 'a', 1, 'h', .03, 0, 'UNKNOWN', None, None, 'STREAM'))
            db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?)',
                       ('unknown-b', 'b', 1, 'h', .04, 0, 'UNKNOWN', None, None, 'OTHER'))
            db.execute('INSERT INTO engineering_jobs VALUES(?,?,?,?,?,?,?,?,?)',
                       ('j', 'a', 'SUCCEEDED', 1, 2, 8,
                        json.dumps({'parameters': {'candidate': {'mechanical': {'gap_mm': 48}}}}),
                        json.dumps({'run_status': 'completed', 'elapsed_s': 4,
                                    'task_evaluation': {'nominal_task_status': 'unsatisfied'},
                                    'stages': {'beam': {'cache_hit': True}, 'joint': {'cache_hit': False}}}), None))
        root = self.home/'studies/door-test'
        root.mkdir(parents=True)
        (root/'seal.json').write_text(json.dumps({'task': {'task_hash': 'hash'},
            'protocol': {'pi_trials': [{'id': 't1', 'initial': 'nominal'}, {'id': 't2', 'initial': 'boundary'}]}}))
        self.patch = patch('bfworld.agentlab.design_pilot_view.HOME_ROOT', self.home)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_planned_trial_is_not_an_actual_result_and_unknown_reservation_retained(self):
        view = projection(self.store)
        a, b = view['trials']
        self.assertEqual(.03, a['cost_upper_usd'])
        self.assertFalse(a['usage_settled'])
        self.assertIsNone(a['submission'])
        self.assertTrue(b['planned_only'])
        self.assertEqual('NOT_STARTED', b['status'])
        self.assertEqual([], b['jobs'])
        self.assertEqual('PROVIDER_USAGE_UNKNOWN_STOP', view['studies'][0]['execution_blocker'])
        self.assertNotIn('private authorization', json.dumps(view))

    def test_owner_projection_does_not_disclose_other_owner_or_unstarted_trials(self):
        view = projection(self.store, 'a')
        self.assertEqual(['unknown-a'], [x['id'] for x in view['billing_blockers']])
        self.assertEqual(['t1'], [x['trial'] for x in view['trials']])
        self.assertEqual([], projection(self.store, 'unrelated')['trials'])

    def test_csv_matches_projection_and_separates_solver_from_end_to_end_cost(self):
        result = export_projection(self.store)
        rows = list(csv.DictReader(io.StringIO(result['trials_csv'])))
        self.assertEqual('unsatisfied', rows[0]['nominal_task_status'])
        self.assertEqual('7.0', rows[0]['end_to_end_job_s'])
        self.assertEqual('4', rows[0]['solver_s'])
        self.assertEqual('1', rows[0]['cache_hits'])
        self.assertEqual('1', rows[0]['cold_stages'])
        self.assertEqual('False', rows[0]['submitted'])
        self.assertEqual('True', rows[1]['planned_only'])
        self.assertEqual('', rows[1]['job_id'])

    def test_evidence_requires_registered_asset_hash_and_local_verification_scope(self):
        p = self.home/'verification/report/map.png'
        p.parent.mkdir(parents=True)
        p.write_bytes(b'local test image')
        index = self.home/'studies/door-test/evidence-index.json'
        asset = {'path': 'verification/report/map.png', 'sha256': file_hash(p)}
        index.write_text(json.dumps({'assets': {'map.png': asset}}))
        self.assertEqual(p, evidence_file('door-test', 'map.png'))
        with self.assertRaisesRegex(ValueError, 'ASSET'):
            evidence_file('door-test', '../../secrets/key')
        p.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'HASH'):
            evidence_file('door-test', 'map.png')
        for path in ('/private/key.png', '../key.png', 'state/key.png'):
            index.write_text(json.dumps({'assets': {'map.png': {**asset, 'path': path}}}))
            with self.assertRaisesRegex(ValueError, 'PATH'):
                evidence_file('door-test', 'map.png')


if __name__ == '__main__':
    unittest.main()
