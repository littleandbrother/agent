import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from bfworld.agentlab.research.core import Research, implementation_binding
from bfworld.agentlab.research.catalog import protocol, b_changes
from bfworld.agentlab.research import evidence, gates, scope
from bfworld.agentlab.store import canonical, identity, Store
from bfworld.agentlab.recovery import Recovery
from bfworld.agentlab.provider import Provider


def query():
    return {'schema_version': 'bf-energy-query-v1', 'product_revision': {'owner': 'fixture', 'revision': 1},
        'world_revision': 'first-order-energy-v2', 'verifier_revision': evidence.verifier_revision(),
        'energy': {'pv_power_mw': .289, 'illuminance_lux': 200, 'lit_hours': 8, 'conversion_efficiency': .7,
                   'capacitance_f': 1, 'capacitance_tolerance_low': .8, 'v_high': 4.2, 'v_low': 3.3107,
                   'sleep_ua': 2, 'leakage_ua': 8, 'supply_v': 3, 'led_total_ma': 4, 'pulse_ms': 100,
                   'mcu_event_mj': .6, 'events_per_day': 60, 'restore_voltage_v': 3.6104},
        'requirements': {'minimum_service_fraction': 1., 'cold_deadline_s': 172800},
        'assumptions': ['test fixture, not measurement'], 'calibration_required': False, 'calibration_id': None, 'duration_s': 172800}


class ResearchCoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.r = Research(self.home)
        self.source = self.home/'input'
        self.source.mkdir()
        (self.source/'design.json').write_text('{"x":1}')
        self.state = dict(product_revision='p1', world_revision='w1', harness_revision='h1',
                          requirements={'target': 1}, assumptions=[], public_context={'memory': 'frozen'}, evidence={}, split='development')
        self.proto = protocol('B', ['one'])
        self.cp = self.r.checkpoint(self.source, ['design.json'], self.state, native_state='none')
        self.proto['checkpoints'] = {'one': self.cp}
        self.pk = self.r.register(self.proto)

    def branch(self, arm='full-recompute'):
        return self.r.branch(self.pk, self.cp, arm, 'one', 1)

    def test_branch_files_and_memory_are_independent(self):
        a, b = self.branch(), self.branch('dependency-cache')
        x = self.r.root/'trials'/a/'workspace/design.json'
        y = self.r.root/'trials'/b/'workspace/design.json'
        self.assertNotEqual(x.stat().st_ino, y.stat().st_ino)
        x.write_text('{"x":99}')
        self.assertEqual(y.read_text(), '{"x":1}')
        self.assertEqual((self.source/'design.json').read_text(), '{"x":1}')
        (self.r.root/'trials'/a/'public-context.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'CONTEXT_DRIFT'):
            self.r.check_trial(a)
        self.r.check_trial(b)

    def test_duplicate_branch_retains_claim_and_deadline(self):
        trial = self.branch()
        original = self.r.claim(trial)
        self.assertEqual(self.branch(), trial)
        self.assertEqual(original, self.r.claim(trial))
        with patch('bfworld.agentlab.research.core.time.time', return_value=original['deadline']+1):
            with self.assertRaisesRegex(ValueError, 'CUMULATIVE_WALL'):
                self.r.check_trial(trial)

    def test_invalid_arms_and_repetition_rejected(self):
        for arm, repeat in [('invented', 1), ('full-recompute', 2)]:
            with self.assertRaisesRegex(ValueError, 'UNDECLARED_CELL'):
                self.r.branch(self.pk, self.cp, arm, 'one', repeat)

    def test_declared_cell_cannot_substitute_another_checkpoint(self):
        (self.source/'design.json').write_text('{"x":2}')
        other = self.r.checkpoint(self.source, ['design.json'], self.state, native_state='none')
        with self.assertRaisesRegex(ValueError, 'CHECKPOINT_BINDING_REQUIRED'):
            self.r.branch(self.pk, other, 'full-recompute', 'one', 1)

    def test_restore_is_fresh_and_does_not_reuse_mutated_directory(self):
        first = self.r.restore(self.cp, 'one')
        self.assertTrue(first['passed'])
        (Path(first['destination'])/'workspace/design.json').write_text('changed')
        second = self.r.restore(self.cp, 'two')
        self.assertTrue(second['passed'])
        with self.assertRaisesRegex(ValueError, 'DESTINATION_EXISTS'):
            self.r.restore(self.cp, 'one')

    def test_protocol_archives_implementation_bytes(self):
        for name, digest in self.proto['implementation'].items():
            self.assertTrue((self.r.root/'blobs'/digest).is_file(), name)

    def test_path_escape_and_symlink_rejected(self):
        (self.source/'link').symlink_to(self.source/'design.json')
        for name in ['../input/design.json', '/tmp/a', 'a/../design.json', 'link']:
            with self.assertRaises(ValueError):
                self.r.checkpoint(self.source, [name], self.state)

    def test_active_job_prevents_checkpoint(self):
        with self.assertRaisesRegex(ValueError, 'QUIESCENCE'):
            self.r.checkpoint(self.source, ['design.json'], self.state, active_jobs=['job-1'])

    def test_corrupt_blob_prevents_restore(self):
        digest = self.r.get('checkpoints', self.cp)['files']['design.json']['sha256']
        (self.r.root/'blobs'/digest).write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'BLOB_TAMPER'):
            self.branch()

    def test_protocol_source_drift_rejected(self):
        wrong = copy.deepcopy(self.proto)
        wrong['implementation'] = {}
        with self.assertRaisesRegex(ValueError, 'IMPLEMENTATION_DRIFT'):
            self.r.register(wrong)

    def test_protocol_missing_or_nan_budget_rejected(self):
        for value in [None, float('nan'), -1]:
            p = copy.deepcopy(self.proto)
            p['budget']['trial_usd'] = value
            with self.assertRaisesRegex(ValueError, 'BUDGET'):
                self.r.register(p)

    def test_results_cannot_be_overwritten(self):
        trial = self.branch()
        self.r.finish(trial, 'FAIL', {'reason': 'retained'})
        with self.assertRaisesRegex(ValueError, 'ALREADY_SEALED'):
            self.r.finish(trial, 'PASS', {})
        self.assertEqual(self.r.trials()[0]['status'], 'FAIL')

    def test_unfinished_attempt_is_retained(self):
        self.branch()
        self.assertEqual(self.r.trials()[0]['status'], 'CLAIMED')
        self.assertIsNone(self.r.trials()[0]['cost_upper_usd'])

    def test_tampered_result_visible_as_corrupt(self):
        trial = self.branch()
        self.r.finish(trial, 'FAIL', {})
        p = self.r.root/'trials'/trial/'result.json'
        p.write_text(p.read_text().replace('FAIL', 'PASS'))
        self.assertEqual(self.r.trials()[0]['status'], 'CORRUPT')

    def test_journal_rejects_incomplete_tail(self):
        with (self.r.root/'events.jsonl').open('ab') as f:
            f.write(b'{')
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE'):
            self.r.journal()

    def test_export_matches_retained_failure(self):
        self.r.finish(self.branch(), 'FAIL', {'original': True})
        out = self.r.export()
        self.assertIn(',FAIL,', out['trials_csv'])
        self.assertEqual(out['projection']['trials'][0]['result'], {'original': True})

    def test_gate_requires_preexecution_identity_and_nonzero_exposure(self):
        t = self.branch()
        rule = {'source': 'x > 1', 'identity': identity('x > 1'), 'origin': 'INJECTED_CONTROL'}
        activation = {'trial': t, 'rule_identity': rule['identity']}
        with self.assertRaisesRegex(ValueError, 'INVALID'):
            gates.observe(self.r, rule=rule, candidate={'x': 2}, decision='block', probability=0, trial=t, activation=activation)
        record = gates.observe(self.r, rule=rule, candidate={'x': 2}, decision='block', probability=.1, trial=t, activation=activation)
        self.assertIsNone(record['data']['outcome'])
        self.assertFalse(record['data']['origin_verified'])
        self.r.finish(t, 'PASS', {'kind': 'injected-control'})
        with self.assertRaisesRegex(ValueError, 'FINISHED'):
            gates.observe(self.r, rule=rule, candidate={'x': 3}, decision='allow', probability=.1, trial=t, activation=activation)


class EvidenceTransferTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = query()
        cls.results = evidence.full_evaluate(cls.q)

    def setUp(self):
        self.e = {'query': self.q, 'query_hash': identity(self.q), 'evaluator': evidence.verifier_revision(), 'results': self.results}

    def test_camera_reuses_all_properties(self):
        q = b_changes(self.q)['camera-only']
        for prop in evidence.PROPERTIES:
            self.assertIsNotNone(evidence.transfer(self.e, q, prop, 'exact-dependencies'))

    def test_requirement_only_invalidates_its_predicate(self):
        q = b_changes(self.q)['requirement-only']
        self.assertIsNone(evidence.transfer(self.e, q, 'normal_service', 'exact-dependencies'))
        self.assertIsNotNone(evidence.transfer(self.e, q, 'daily_balance', 'exact-dependencies'))

    def test_small_change_bound_preserves_predicate_not_number(self):
        q = b_changes(self.q)['small-pv-change']
        cert = evidence.transfer(self.e, q, 'daily_balance', 'margin-bound')
        self.assertIsNotNone(cert)
        self.assertIsNone(cert['result']['margin'])
        self.assertEqual(cert['result']['verdict'], self.results['daily_balance']['verdict'])

    def test_startup_cannot_use_daily_energy_bound(self):
        q = b_changes(self.q)['larger-storage']
        self.assertIsNone(evidence.transfer(self.e, q, 'cold_ready', 'margin-bound'))

    def test_old_verifier_and_missing_measurements_abstain(self):
        for name in ['verifier-change', 'missing-calibration']:
            q = b_changes(self.q)[name]
            for prop in evidence.PROPERTIES:
                for operator in ['exact-dependencies', 'margin-bound']:
                    self.assertIsNone(evidence.transfer(self.e, q, prop, operator))
            self.assertTrue(all(x['verdict'] == 'UNKNOWN' for x in evidence.full_evaluate(q).values()))

    def test_false_old_margin_cannot_certify_bound(self):
        fake = copy.deepcopy(self.e)
        fake['results']['daily_balance']['margin'] = 999
        self.assertIsNone(evidence.transfer(fake, b_changes(self.q)['small-pv-change'], 'daily_balance', 'margin-bound'))

    def test_zero_input_and_bad_domain_rejected(self):
        q = copy.deepcopy(self.q)
        q['energy']['conversion_efficiency'] = 0
        with self.assertRaisesRegex(ValueError, 'DOMAIN'):
            evidence.full_evaluate(q)


class ScopePilotTest(unittest.TestCase):
    def test_generator_and_selector_use_the_same_artifact_ids(self):
        d = scope.cases()['local-voltage']
        feedback = {'checks': {}}
        generated = json.loads(scope.prompt(d, feedback, ['circuit'], [])[1]['content'])
        selected = json.loads(scope.selection_prompt(d, feedback)[1]['content'])
        self.assertEqual(set(generated['design']), set(scope.SCOPES))
        self.assertEqual(set(selected['artifacts']), set(scope.SCOPES))
        self.assertEqual(set(generated['editable_artifacts']), {'circuit'})

    def test_passing_reference_and_injected_conflicts(self):
        values = scope.cases()
        fixed = {**values['local-voltage'], 'clamp_v': 3.45}
        self.assertTrue(scope.evaluate(fixed)['checks']['value'])
        for d in values.values():
            self.assertFalse(scope.evaluate(d)['checks']['value'])

    def test_patch_cannot_edit_other_scope_or_resources(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            for name, data in scope.artifacts(scope.cases()['local-voltage']).items():
                (p/name).write_text(canonical(data))
            with self.assertRaisesRegex(ValueError, 'OUTSIDE'):
                scope.apply_patch(p, {'classifier': {'model_threshold': 25}}, ['circuit'])
            with self.assertRaisesRegex(ValueError, 'RESOURCE'):
                scope.apply_patch(p, {'classifier': {'flash_bytes': 1}}, ['classifier'])


class ResearchBudgetTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.store = Store(Path(self.t.name)/'state')
        self.provider = Provider(self.store)
        self.recovery = self.provider.recovery
        self.owner = 'research-example'
        self.store.grant(self.owner, [], 0, time.time()+60)
        with self.store.connect() as db:
            db.execute('UPDATE model_limits SET expires=?', (time.time()-1,))

    def test_scoped_window_does_not_renew_old_batch(self):
        with self.store.connect() as db:
            db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)', ('p', time.time(), time.time()+60, .1, 'deepseek-flash', 'test'))
            db.execute('INSERT INTO research_model_owners VALUES(?,?,?)', (self.owner, 'p', 't'))
            limit = db.execute('SELECT * FROM model_limits').fetchone()
            grant = db.execute('SELECT * FROM grants WHERE owner=?', (self.owner,)).fetchone()
            self.recovery.check_window(db, self.owner, grant, limit)
            old = db.execute("SELECT * FROM grants WHERE owner='operator'").fetchone()
            with self.assertRaisesRegex(ValueError, 'MODEL_WALL_BUDGET'):
                self.recovery.check_window(db, 'operator', old, limit)

    def test_study_cap_stops_before_network(self):
        with self.store.connect() as db:
            db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)', ('p', time.time(), time.time()+60, .000001, 'deepseek-flash', 'test'))
            db.execute('INSERT INTO research_model_owners VALUES(?,?,?)', (self.owner, 'p', 't'))
        with self.assertRaisesRegex(ValueError, 'RESEARCH_MODEL_USD_BUDGET'):
            self.provider.complete(self.owner, {'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': 'x'}], 'max_tokens': 1})
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM model_requests').fetchone()[0], 0)


class ResearchHTTPTest(unittest.TestCase):
    def test_operator_only_projection_and_record_boundary(self):
        import threading
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from bfworld.agentlab.server import Workbench, handler
        with tempfile.TemporaryDirectory() as t:
            app = Workbench(Path(t)/'state')
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(app))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                operator = (app.store.root/'operator.token').read_text()
                participant = app.store.issue('participant')
                base = 'http://127.0.0.1:'+str(server.server_port)
                def request(path, token):
                    req = urllib.request.Request(base+path, headers={'Authorization': 'Bearer '+token})
                    try:
                        with urllib.request.urlopen(req) as response:
                            return response.status, json.load(response)
                    except urllib.error.HTTPError as exc:
                        return exc.code, json.load(exc)
                self.assertEqual(request('/api/developer/research', participant)[0], 403)
                code, value = request('/api/developer/research', operator)
                self.assertEqual(code, 200)
                self.assertEqual(value['trials'], [])
                self.assertEqual(request('/api/developer/research/record?kind=../secrets&id=x', operator)[0], 400)
                self.assertEqual(request('/api/developer/research/export', operator)[0], 200)
            finally:
                server.shutdown()
                server.server_close()
                app.stop.set()
                app.thread.join(3)
                app.lock.close()
