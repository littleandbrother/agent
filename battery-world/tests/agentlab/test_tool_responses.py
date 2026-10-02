import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bfworld.agentlab.store import Store, canonical, identity
from bfworld.agentlab.tool_responses import ToolResponses
from bfworld.agentlab.request_evidence import describe


class ResponseEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'state')
        self.task = 'a' * 64
        self.engineering = SimpleNamespace(store=self.store,
            tasks=SimpleNamespace(binding=lambda owner: {'task_hash': self.task}),
            get=lambda owner, key: self.job if owner == 'alice' and key == self.job['id'] else self.denied())
        self.job = {'id': 'eng-123', 'status': 'SUCCEEDED', 'operation': 'one',
            'parameters': {'candidate': {'gap_mm': 48}},
            'result': {'artifacts': [{'name': 'result.json', 'sha256': 'b' * 64, 'bytes': 100}],
                       'unicode': '\u0000"\\🌱中文\n' * 15000}}
        self.bridge = ToolResponses(self.engineering)

    @staticmethod
    def denied():
        raise PermissionError('ENGINEERING_JOB_NOT_FOUND')

    def tearDown(self):
        self.tmp.cleanup()

    def page_args(self, response):
        return {'response_id': response['_response']['response_id'],
                'response_sha256': response['_response']['sha256']}

    def test_all_large_unicode_fields_reconstruct_exactly_and_restart(self):
        response = self.bridge.wrap('alice', self.job)
        self.assertLess(len(canonical(response).encode()), 24000)
        self.assertFalse(response['full_response_inline'])
        self.assertEqual('eng-123', response['id'])
        bridge = ToolResponses(self.engineering)
        args = {**self.page_args(response), 'limit': 16000}
        chunks = []
        while True:
            page = bridge.view('alice', args)
            self.assertLessEqual(len(canonical(page).encode()), 20000)
            chunks.append(page['text'])
            if page['next_offset'] is None:
                break
            self.assertGreater(page['next_offset'], args.get('offset', 0))
            args['offset'] = page['next_offset']
        restored = ''.join(chunks)
        self.assertEqual(self.job, json.loads(restored))
        self.assertEqual(response['_response']['sha256'], hashlib.sha256(restored.encode()).hexdigest())
        self.assertEqual(response, bridge.wrap('alice', self.job))

    def test_owner_task_hash_offset_tamper_boundaries(self):
        response = self.bridge.wrap('alice', self.job)
        args = self.page_args(response)
        with self.assertRaisesRegex(PermissionError, 'NOT_FOUND'):
            self.bridge.view('bob', args)
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            self.bridge.view('alice', {**args, 'response_sha256': 'f' * 64})
        for patch in ({'offset': -1}, {'offset': True}, {'offset': 10**9}, {'limit': 16001}, {'response_id': '../../private'}):
            with self.assertRaises(ValueError):
                self.bridge.view('alice', {**args, **patch})
        self.task = 'c' * 64
        with self.assertRaisesRegex(PermissionError, 'TASK_MISMATCH'):
            self.bridge.view('alice', args)
        self.task = 'a' * 64
        with self.store.connect() as db:
            db.execute("UPDATE engineering_responses SET body='{}'")
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            self.bridge.view('alice', args)

    def test_delivery_receipts_only_match_exact_post_projection_feedback(self):
        response = self.bridge.wrap('alice', self.job)
        page = self.bridge.view('alice', self.page_args(response))
        def capture(value, owner='alice'):
            raw = canonical(value).encode()
            with self.store.connect() as db:
                receipt = describe(db, owner, value, raw)
            self.assertEqual(raw, canonical(value).encode(), 'Observer must not mutate request')
            return receipt
        wire = {'messages': [{'role': 'tool', 'tool_call_id': 'call-1', 'content': json.dumps(page)}]}
        link = capture(wire)['feedback'][0]
        self.assertEqual('backend_response_present_in_wire', link['status'])
        self.assertEqual('eng-123', link['binding']['jobs'][0]['job_id'])
        self.assertEqual('unverified_tool_content', capture(wire, 'bob')['feedback'][0]['status'])
        altered = {**page, 'text': 'fabricated success'}
        self.assertEqual('unverified_tool_content', capture({'messages': [{'role': 'tool', 'content': json.dumps(altered)}]})['feedback'][0]['status'])
        self.assertEqual([], capture({'messages': []})['feedback'], 'Omitted feedback is not delivered')

    def test_method_presence_is_not_inferred_from_config_or_temporal_proximity(self):
        text = 'The frozen method instruction.'
        with self.store.connect() as db:
            db.execute('CREATE TABLE chat_events(seq INTEGER PRIMARY KEY,conversation TEXT,data TEXT)')
            event = {'type': 'method_activation', 'phase': 'invoked', 'instruction_text': text,
                     'prompt_hash': identity(text), 'profile': {'method_id': 'strong_generic'}}
            db.execute('INSERT INTO chat_events VALUES(1,?,?)', ('alice', canonical(event)))
            body = {'messages': [{'role': 'system', 'content': 'prefix\n' + text + '\nsuffix'}]}
            self.assertEqual('present_in_wire', describe(db, 'alice', body, canonical(body).encode())['method']['status'])
            body = {'messages': [{'role': 'user', 'content': text}]}
            self.assertEqual('absent_from_wire', describe(db, 'alice', body, canonical(body).encode())['method']['status'])
            event.pop('instruction_text')
            db.execute('UPDATE chat_events SET data=?', (canonical(event),))
            self.assertEqual('unknown', describe(db, 'alice', body, canonical(body).encode())['method']['status'])

    def test_javascript_integral_float_serialization_does_not_break_delivery_binding(self):
        response=self.bridge.wrap('alice',{'measurement':1.0,'offset':-0.0})
        original_sha=response['_response']['sha256']
        wire_value={**response,'measurement':1,'offset':0}
        body={'messages':[{'role':'tool','tool_call_id':'numeric','content':json.dumps(wire_value)}]}
        with self.store.connect() as db:
            receipt=describe(db,'alice',body,canonical(body).encode())
        self.assertEqual('backend_response_present_in_wire',receipt['feedback'][0]['status'])
        self.assertEqual(original_sha,receipt['feedback'][0]['response_sha256'])


if __name__ == '__main__':
    unittest.main()
