import json
import tempfile
import unittest
from pathlib import Path

from bfworld.agentlab.context import ContextArchive, project_interactive
from bfworld.agentlab.store import canonical, identity


class RepositoryContext(unittest.TestCase):
    def payload(self):
        messages = [{'role': 'system', 'content': 'Exact repository rules'},
                    {'role': 'user', 'content': 'Keep the original design and reuse successful jobs.'}]
        for i in range(10):
            task = {'id': 'PT-original', 'owner': 'owner', 'base_system': 'SC-base',
                    'question': 'question-' + str(i) + 'x' * 6000}
            goal = {'goal': 'Complete the assigned question, submit an actual Domain Commit and finish.',
                    'professional_task': task}
            state = {'adopted': 'SC-adopted', 'branch': {'revision': i}, 'cost_upper_bound_usd': 4,
                     'current_system': 'SC-current', 'error': None, 'model_calls': i,
                     'owner': 'owner', 'project_id': 'PR-project', 'revision': 11,
                     'status': 'RUNNING', 'task': task, 'unknown_requests': 0}
            messages += [{'role': 'user', 'content': [{'type': 'text', 'text': canonical(x)}]}
                         for x in (goal, state)]
        latest = messages[-2:]
        for i in range(6):
            messages += [{'role': 'assistant', 'tool_calls': [
                {'id': 'source-' + str(i), 'function': {'name': 'bf_repository', 'arguments': '{}'}}]},
                {'role': 'tool', 'tool_call_id': 'source-' + str(i), 'content': 'current source ' + 'c' * 15000}]
        return {'messages': messages, 'tools': [{'type': 'function', 'function': {'name': 'bf_repository'}}]}, latest

    def test_superseded_generated_restores_make_room_for_current_source(self):
        payload, latest = self.payload()
        original = canonical(payload)
        with tempfile.TemporaryDirectory() as root:
            result, audit = project_interactive(payload, ContextArchive(root, 'owner'),
                request_bytes=1048576, target_bytes=220000)
            self.assertEqual(original, canonical(payload))
            self.assertLess(audit['projected_bytes'], 130000)
            self.assertEqual([], audit['bounded_turn_omitted_call_ids'])
            self.assertEqual(6, sum(m['role'] == 'tool' for m in result['messages']))
            self.assertIn(payload['messages'][1], result['messages'])
            for m in latest:
                self.assertIn(m, result['messages'])
            archives = [x for x in audit['archived_messages'] if x['kind'].startswith('superseded_repository_')]
            self.assertEqual(18, len(archives))
            for x in archives:
                raw = json.loads((Path(root) / 'participants/owner' / x['record_file']).read_text())
                self.assertEqual(x['sha256'], identity(raw))
                self.assertIn(raw, payload['messages'])
            again, _ = project_interactive(payload, ContextArchive(root, 'owner'),
                request_bytes=1048576, target_bytes=220000)
            self.assertEqual(result, again)

    def test_real_user_instructions_are_never_classified_as_generated_state(self):
        payload, _ = self.payload()
        human = [{'role': 'user', 'content': 'Approve only after I confirm. ' + 'h' * 20000},
                 {'role': 'user', 'content': canonical({'goal': 'Different actual requirement',
                    'professional_task': {'id': 'PT-human', 'owner': 'owner', 'base_system': 'SC-base'}})}]
        payload['messages'].extend(human)
        with tempfile.TemporaryDirectory() as root:
            result, _ = project_interactive(payload, ContextArchive(root, 'owner'),
                request_bytes=1048576, target_bytes=220000)
            for m in human:
                self.assertIn(m, result['messages'])

    def test_repeated_old_reads_do_not_spill_the_new_complete_source_tree(self):
        payload, _ = self.payload()
        payload['messages'] = payload['messages'][:-12]
        for i in range(8):
            payload['messages'] += [{'role': 'assistant', 'reasoning_content': 'r' * 20000,
                'tool_calls': [{'id': 'old-' + str(i)}]},
                {'role': 'tool', 'tool_call_id': 'old-' + str(i), 'content': 'old source page'}]
        sources = []
        for i in range(3):
            source = {'role': 'tool', 'tool_call_id': 'new-' + str(i), 'content': 'new source ' + 'c' * 18000}
            payload['messages'] += [{'role': 'assistant', 'tool_calls': [{'id': 'new-' + str(i)}]}, source]
            sources.append(source)
        with tempfile.TemporaryDirectory() as root:
            result, audit = project_interactive(payload, ContextArchive(root, 'owner'),
                request_bytes=1048576, target_bytes=220000)
            self.assertLess(audit['projected_bytes'], 221000)
            self.assertTrue(audit['bounded_turn_omitted_call_ids'])
            for source in sources:
                self.assertIn(source, result['messages'])

    def test_other_tools_owner_and_malformed_ids_are_not_compacted(self):
        payload, _ = self.payload()
        for replacement in ('other_tool', None):
            candidate = json.loads(canonical(payload))
            if replacement:
                candidate['tools'][0]['function']['name'] = replacement
            else:
                for m in candidate['messages']:
                    if m['role'] == 'user' and isinstance(m['content'], list):
                        value = json.loads(m['content'][0]['text'])
                        value.get('professional_task', value.get('task', {}))['id'] = None
                        value['owner'] = 'other'
                        m['content'][0]['text'] = canonical(value)
            with tempfile.TemporaryDirectory() as root:
                _, audit = project_interactive(candidate, ContextArchive(root, 'different-owner'),
                    request_bytes=1048576, target_bytes=600000)
                self.assertEqual([], [x for x in audit['archived_messages']
                    if x['kind'].startswith('superseded_repository_')])


if __name__ == '__main__':
    unittest.main()
