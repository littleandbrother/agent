"""Resource, identity and accounting controls before a paid BF episode."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from bfworld.agentlab.campaign20261019.phase1 import (
    BFPhaseGateway, digest, file_hash, ledger, require_lease, tool_definition,
)


class PhaseOneControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'ledger.sqlite'
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE model_requests(id TEXT,owner TEXT,created REAL,status TEXT,'
                       'reserved REAL,charged REAL,usage TEXT,response_hash TEXT,error TEXT)')
        self.bound = self.root / 'fixed-task.json'
        self.bound.write_text('{"dark_seconds":43200,"extra_energy":0}')
        self.lease = self.root / 'lease.json'
        self.lease.write_text(json.dumps({'status': 'GRANTED', 'episode': 'fixture-ar',
            'expires': time.time() + 600, 'holders': ['S0', 'A', 'Pi'], 'other_executor_status': 'idle'}))
        schema = {'type': 'object', 'properties': {
            'action': {'enum': ['inspect', 'check', 'submit']},
            'candidate': {'type': 'object', 'properties': {'capacitance_f': {'type': 'number', 'minimum': .001}},
                          'required': ['capacitance_f'], 'additionalProperties': False}},
            'required': ['action'], 'additionalProperties': False}
        self.protocol = {'id': 'fixture-ar', 'mode': 'fixture', 'owner': 'pi-fixture',
            'tool': tool_definition('bf_phase1', 'Inspect the frozen BF service and test a legal storage design.', schema),
            'provider_database': str(self.db), 'provider_service': 'http://127.0.0.1:9',
            'allowed_reported_models': ['deepseek-flash'], 'bound_files': {str(self.bound): file_hash(self.bound)},
            'candidate_fields': ['candidate'], 'candidate_actions': ['check'],
            'limits': {'model_requests': 2, 'candidates': 1, 'wall_seconds': 600, 'reserve_bytes': 0,
                'peak_remaining_bytes': 0, 'output_bytes': 1000000, 'tool_calls': 10,
                'tool_response_bytes': 96000, 'model_request_bytes': 512000,
                'model_response_bytes': 64000000, 'max_output_tokens': 32768}}
        self.calls = []
        def handler(body):
            self.calls.append(body)
            return {'public_fact': 'simulated storage-side joules; physical UNKNOWN'}
        self.gateway = BFPhaseGateway(self.protocol, self.root / 'episode', handler,
                                      provider_token='fixture-token', lease_path=self.lease)
        self.addCleanup(self.gateway.close)

    def payload(self):
        return {'model': 'deepseek-flash', 'stream': True, 'max_tokens': 4096,
                'tools': [{'type': 'function', 'function': {k: self.protocol['tool'][k]
                          for k in ('name', 'description', 'parameters')}}]}

    def row(self, key, status='SETTLED', usage=None, charge=.01):
        usage = usage or {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120,
            'prompt_cache_hit_tokens': 60, 'prompt_cache_miss_tokens': 40}
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?)',
                (key, 'pi-fixture', time.time(), status, .05, charge,
                 json.dumps(usage) if status == 'SETTLED' else None, 'response', None))

    def test_source_change_never_reaches_scientific_consumer(self):
        self.bound.write_text('{"dark_seconds":0,"extra_energy":1}')
        with self.assertRaisesRegex(ValueError, 'BOUND_INPUT_CHANGED'):
            self.gateway.tool({'action': 'inspect'})
        self.assertEqual(self.calls, [])

    def test_distinct_candidate_cap_allows_identical_input_reuse(self):
        first = {'action': 'check', 'candidate': {'capacitance_f': .015}}
        self.gateway.tool(first)
        self.gateway.tool(copy.deepcopy(first))
        with self.assertRaisesRegex(ValueError, 'CANDIDATE_LIMIT'):
            self.gateway.tool({'action': 'check', 'candidate': {'capacitance_f': .03}})
        self.assertEqual(len(self.calls), 2)

    def test_unknown_charge_blocks_before_any_provider_send(self):
        self.row('unknown', 'UNKNOWN')
        with self.assertRaisesRegex(ValueError, 'PROVIDER_USAGE_UNAVAILABLE'):
            self.gateway.model_payload(self.payload())
        account = ledger(self.db, 'pi-fixture')
        self.assertEqual(account['unknown_or_missing_usage'], ['unknown'])
        self.assertEqual(account['unsettled_reserved_usd'], .05)
        self.assertEqual(self.gateway.model_dispatches, 0)

    def test_submit_and_rejected_candidates_consume_budget_but_no_go_does_not(self):
        self.gateway.protocol['candidate_actions'] = ['check', 'submit']
        self.gateway.protocol['limits']['candidates'] = 2
        self.gateway.tool({'action': 'submit'})
        self.assertEqual(len(self.gateway.candidates), 0)
        self.gateway.tool({'action': 'submit', 'candidate': {'capacitance_f': .015}})
        with self.assertRaises(Exception):
            self.gateway.tool({'action': 'check', 'candidate': {'capacitance_f': -1}})
        self.assertEqual(len(self.gateway.candidates), 2)
        with self.assertRaisesRegex(ValueError, 'CANDIDATE_LIMIT'):
            self.gateway.tool({'action': 'submit', 'candidate': {'capacitance_f': .03}})
        self.gateway.tool({'action': 'submit'})
        self.assertEqual(len(self.calls), 3)

    def test_request_cap_preserves_failure_in_denominator(self):
        self.row('first')
        self.row('second', charge=.02)
        with self.assertRaisesRegex(ValueError, 'REQUEST_LIMIT'):
            self.gateway.model_payload(self.payload())
        account = ledger(self.db, 'pi-fixture')
        self.assertEqual(account['requests'], 2)
        self.assertAlmostEqual(account['settled_charge_upper_bound_usd'], .03)
        self.assertAlmostEqual(account['cache_aware_rate_estimate_usd'], 2 * (.006 * 60 + .3 * 40 + 1.2 * 20) / 1e6)

    def test_slot_overflow_and_schema_injection_are_denied(self):
        lease = json.loads(self.lease.read_text())
        lease['holders'].append('B')
        self.lease.write_text(json.dumps(lease))
        with self.assertRaisesRegex(ValueError, 'MODEL_SLOT_NOT_LEASED'):
            self.gateway.model_payload(self.payload())
        self.assertEqual(self.gateway.model_dispatches, 0)
        with self.assertRaises(Exception):
            self.gateway.tool({'action': 'inspect', 'replace_checker': True})
        self.assertEqual(self.calls, [])

    def test_sdk_schema_and_storage_guard_are_actual_dispatch_inputs(self):
        body = self.payload()
        body['tools'][0]['function']['description'] += ' extra design hint'
        with self.assertRaisesRegex(ValueError, 'SDK_TOOL_SCHEMA_CHANGED'):
            self.gateway.model_payload(body)
        self.assertEqual(self.gateway.stopped, 'ACTUAL_SDK_TOOL_SCHEMA_CHANGED')
        storage_gateway = BFPhaseGateway(self.protocol, self.root / 'storage-episode',
            lambda body: self.calls.append(body), provider_token='fixture-token', lease_path=self.lease)
        self.addCleanup(storage_gateway.close)
        with patch('bfworld.agentlab.campaign20261019.phase1.shutil.disk_usage') as usage:
            usage.return_value.free = 0
            storage_gateway.protocol['limits']['reserve_bytes'] = 10
            with self.assertRaisesRegex(ValueError, 'STORAGE_RESERVE'):
                storage_gateway.tool({'action': 'inspect'})
        self.assertEqual(self.calls, [])

    def test_repaired_file_does_not_silently_resume_stopped_episode(self):
        original = self.bound.read_bytes()
        self.bound.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'BOUND_INPUT_CHANGED'):
            self.gateway.tool({'action': 'inspect'})
        self.bound.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'EPISODE_STOPPED'):
            self.gateway.tool({'action': 'inspect'})
        self.assertEqual(self.calls, [])

    def test_nonempty_invalid_usage_is_not_treated_as_settled_information(self):
        self.row('malformed-usage', usage={'prompt_tokens': 'unknown', 'completion_tokens': 1})
        with self.assertRaisesRegex(ValueError, 'PROVIDER_USAGE_UNAVAILABLE'):
            self.gateway.model_payload(self.payload())
        self.assertEqual(ledger(self.db, 'pi-fixture')['unknown_or_missing_usage'], ['malformed-usage'])

    def test_production_cannot_silently_use_fixture_reserve(self):
        p = copy.deepcopy(self.protocol)
        p['mode'] = 'public-development'
        with self.assertRaisesRegex(ValueError, 'FINITE_EPISODE_LIMITS'):
            BFPhaseGateway(p, self.root / 'invalid', lambda x: {}, provider_token='', lease_path=self.lease)


if __name__ == '__main__':
    unittest.main()
