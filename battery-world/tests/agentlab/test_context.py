"""Owner-scoped machine-state projection preserves human requirements and evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from bfworld.agentlab import context as superseded_context

PREFIX = '当前任务事实快照（覆盖过时上下文；不改变既定要求）：'
HISTORICAL_PREFIX = '历史任务事实快照（仅保留追溯；当前事实以最新快照为准）：'
OWNER = 'pi-chat-test-original'


def state(**changes):
    return {'schema_version': 'bf-product-context-v1', 'owner': OWNER,
            'paper_id': 'P01', 'context_scope': 'current-original-paper-native-phase',
            'requirements': ['Keep original engineering; preserve all cost history'],
            'assumptions': ['Physical verification remains absent'],
            'native_jobs': [{'id': 'job-new', 'status': 'SUCCEEDED'}], **changes}


def wrapped(value, suffix='\n用户消息：Continue the original task. No new simulation.', typed=False):
    text = PREFIX + json.dumps(value, ensure_ascii=False) + suffix
    return {'role': 'user', 'content': [{'type': 'text', 'text': text}] if typed else text}


def unwrap(message):
    content = message['content']
    text = content[0]['text'] if isinstance(content, list) else content
    prefix = HISTORICAL_PREFIX if text.startswith(HISTORICAL_PREFIX) else PREFIX
    value, end = json.JSONDecoder().raw_decode(text[len(prefix):])
    return value, text[len(prefix) + end:]


class SupersededStateControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = superseded_context.ContextArchive(self.temp.name, OWNER)

    def project(self, messages):
        return superseded_context._project_superseded_phase_states(messages, self.archive)

    def test_latest_and_all_human_suffixes_preserved(self):
        suffix = '\n用户消息：Prior $30 authority; NEVER delete my files.\nLiteral {braces}. '
        older = wrapped(state(native_jobs=[{'id': 'job-old', 'status': 'FAIL'}]), suffix)
        latest = wrapped(state(), typed=True)
        source = [older, latest]
        frozen = copy.deepcopy(source)
        actual, records = self.project(source)
        history, human = unwrap(actual[0])
        self.assertEqual(source, frozen)
        self.assertEqual(actual[1], latest)
        self.assertEqual(human, suffix)
        self.assertEqual(history['state_authority'], 'HISTORICAL_SUPERSEDED')
        self.assertTrue(actual[0]['content'].startswith(HISTORICAL_PREFIX))
        self.assertEqual(history['constraints_kept_verbatim_in_latest'], ['requirements', 'assumptions'])
        path = Path(self.temp.name) / 'participants' / OWNER / records[0]['record_file']
        self.assertEqual(json.loads(path.read_text()), unwrap(older)[0])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), records[0]['sha256'])

    def test_distinct_constraints_are_not_subsumed(self):
        original = state(requirements=['Keep an additional source condition'], assumptions=['Different calibration'])
        result, _ = self.project([wrapped(original), wrapped(state())])
        historical, _ = unwrap(result[0])
        self.assertEqual(historical['requirements'], original['requirements'])
        self.assertEqual(historical['assumptions'], original['assumptions'])
        self.assertEqual(historical['constraints_kept_verbatim_in_latest'], [])

    def test_equal_python_values_with_distinct_json_types_remain_distinct(self):
        old = state(requirements=[1], assumptions=[True])
        latest = state(requirements=[1.0], assumptions=[1])
        result, _ = self.project([wrapped(old), wrapped(latest)])
        historical, _ = unwrap(result[0])
        self.assertEqual(historical['requirements'], [1])
        self.assertIs(historical['assumptions'][0], True)

    def test_string_and_single_typed_text_preserve_framing(self):
        result, _ = self.project([wrapped(state(), typed=True), wrapped(state())])
        self.assertIsInstance(result[0]['content'], list)
        self.assertEqual(result[0]['content'][0]['type'], 'text')
        self.assertIsInstance(result[1]['content'], str)

    def test_foreign_latest_or_unrecognized_current_scope_unchanged(self):
        for changes in ({'owner': 'pi-chat-foreign'}, {'context_scope': 'historical-registry'},
                        {'requirements': None}, {'assumptions': 'untyped'}):
            original = [wrapped(state()), wrapped(state(**changes))]
            result, records = self.project(original)
            self.assertEqual(result, original)
            self.assertEqual(records, [])

    def test_separately_identified_foreign_historical_state_unchanged(self):
        for changes in ({'owner': 'pi-chat-foreign'}, {'paper_id': 'P02'}):
            original = [wrapped(state(**changes)), wrapped(state())]
            result, records = self.project(original)
            self.assertEqual(result, original)
            self.assertEqual(records, [])

    def test_malformed_unrecognized_or_unframed_user_text_unchanged(self):
        originals = [
            {'role': 'user', 'content': PREFIX + '{bad json\n用户消息：Keep'},
            wrapped({'schema_version': 'untrusted-paper-fact', 'requirements': []}),
            wrapped(state(), suffix='This is ordinary user text'),
            {'role': 'user', 'content': [{'type': 'text', 'text': PREFIX + '{}'}, {'type': 'text', 'text': 'Keep both'}]},
            {'role': 'user', 'content': 'User quotes ' + PREFIX + json.dumps(state())},
        ]
        actual, records = self.project([*originals, wrapped(state())])
        self.assertEqual(actual, [*originals, wrapped(state())])
        self.assertEqual(records, [])

    def test_no_archive_single_snapshot_and_ordinary_user_history_unchanged(self):
        messages = [wrapped(state()), wrapped(state())]
        actual, records = superseded_context._project_superseded_phase_states(messages, None)
        self.assertEqual(actual, messages)
        self.assertEqual(records, [])
        actual, records = self.project(messages[:1])
        self.assertEqual(actual, messages[:1])
        self.assertEqual(records, [])

    def test_no_completed_or_pending_tool_pair_changes(self):
        calls = [{'role': 'assistant', 'tool_calls': [{'id': 'pending', 'function': {'name': 'bf_eda', 'arguments': '{}'}}]},
                 {'role': 'tool', 'tool_call_id': 'done', 'content': 'Real historical observation'}]
        messages = [wrapped(state()), *calls, wrapped(state())]
        actual, _ = self.project(messages)
        self.assertEqual(actual[1:3], calls)

    def test_projection_is_idempotent_and_reuses_archive(self):
        actual, _ = self.project([wrapped(state()), wrapped(state())])
        twice, records = self.project(actual)
        self.assertEqual(twice, actual)
        self.assertEqual(records, [])

    def test_real_projection_integration_keeps_instructions_and_latest(self):
        older = wrapped(state(native_jobs=[{'id': 'old'}]))
        latest = wrapped(state())
        payload = {'model': 'fixed-model', 'messages': [{'role': 'system', 'content': 'Frozen engineering rules'}, older, latest]}
        original = copy.deepcopy(payload)
        actual, audit = superseded_context.project_interactive(payload, self.archive, request_bytes=1000000, target_bytes=900000)
        self.assertEqual(payload, original)
        self.assertIn(latest, actual['messages'])
        self.assertTrue(any(m.get('content') == 'Frozen engineering rules' for m in actual['messages']))
        self.assertTrue(any(x['kind'] == 'superseded_product_context' for x in audit['archived_messages']))

    def test_corrupt_archive_fails_closed(self):
        value = state()
        record = self.archive(value)
        path = Path(self.temp.name) / 'participants' / OWNER / record['record_file']
        path.chmod(0o600)
        path.write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'CONTEXT_ARCHIVE_CONFLICT'):
            self.project([wrapped(value), wrapped(state())])


if __name__ == '__main__':
    unittest.main()
