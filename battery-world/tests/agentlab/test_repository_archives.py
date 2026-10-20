import json
import unittest

from test_repository_integration import IntegrationCase
from test_design_repository import OWNER, OTHER
from bfworld.agentlab.context import ContextArchive, project_interactive
from bfworld.agentlab.store import canonical


class ArchiveConsumerTests(unittest.TestCase):
    setUp = IntegrationCase.setUp
    imported = IntegrationCase.imported
    action = IntegrationCase.action

    def record(self, value=None):
        archive = ContextArchive(self.store.root.parent, OWNER)
        value = value or {'role': 'tool', 'tool_call_id': 'summary',
                         'content': canonical({'project': {'submitted': 'SC-current'},
                                               'branches': [{'head': 'DC-current'}]})}
        return archive(value)

    def test_actual_repository_transport_reads_paged_original_and_selected_field(self):
        ref = self.record()
        before = self.store.root.parent/'participants'/OWNER/ref['record_file']
        original = before.read_bytes()
        selected = self.action(OWNER, 'archive_read', path=ref['text_file'], pointer='/branches/0/head')
        self.assertEqual('DC-current', json.loads(selected['content']))
        self.assertEqual(OWNER, selected['owner'])
        self.assertEqual(ref['text_sha256'], selected['sha256'])
        page = self.action(OWNER, 'archive_read', path=ref['record_file'], limit=5)
        self.assertEqual(5, page['next_offset'])
        rest = self.action(OWNER, 'archive_read', path=ref['record_file'], offset=5)
        self.assertEqual(original.decode(), page['content']+rest['content'])
        self.assertEqual(original, before.read_bytes())

    def test_old_read_hints_are_compatible_and_own_observation_stays_read_only(self):
        ref = self.record()
        with self.store.connect() as db:
            before = db.execute('SELECT count(*) FROM design_operations').fetchone()[0]
        for action in ('read', 'workspace_read'):
            value = self.action(OWNER, action, path=ref['text_file'], pointer='/project/submitted')
            self.assertEqual('SC-current', json.loads(value['content']))
        with self.store.connect() as db:
            self.assertEqual(before, db.execute('SELECT count(*) FROM design_operations').fetchone()[0])

    def test_other_owner_path_escape_bad_pointer_and_bad_range_are_rejected(self):
        ref = self.record()
        with self.assertRaisesRegex(ValueError, 'CONTEXT_ARCHIVE_NOT_FOUND'):
            self.action(OTHER, 'archive_read', path=ref['text_file'])
        for path in ('../'+ref['text_file'], '/tmp/source', 'context-records/../secret', 1):
            with self.assertRaisesRegex(ValueError, 'CONTEXT_ARCHIVE_PATH_INVALID'):
                self.action(OWNER, 'archive_read', path=path)
        for pointer in ('branches', '/branches/-1', '/branches/2', '/missing', '/x~2'):
            with self.assertRaisesRegex(ValueError, 'CONTEXT_ARCHIVE_POINTER_INVALID'):
                self.action(OWNER, 'archive_read', path=ref['text_file'], pointer=pointer)
        with self.assertRaisesRegex(ValueError, 'CONTEXT_ARCHIVE_RANGE_INVALID'):
            self.action(OWNER, 'archive_read', path=ref['text_file'], limit=40000)

    def test_changed_companion_or_original_and_symlink_are_rejected(self):
        ref = self.record()
        root = self.store.root.parent/'participants'/OWNER
        companion = root/ref['text_file']
        raw = companion.read_bytes()
        companion.chmod(0o600); companion.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, 'CONTEXT_ARCHIVE_CONFLICT'):
            self.action(OWNER, 'archive_read', path=ref['text_file'])
        companion.write_bytes(raw)
        original = root/ref['record_file']
        data = original.read_bytes()
        original.chmod(0o600); original.write_bytes(data+b' ')
        with self.assertRaisesRegex(ValueError, 'CONTEXT_ARCHIVE_CONFLICT'):
            self.action(OWNER, 'archive_read', path=ref['record_file'])
        original.write_bytes(data)
        companion.unlink(); companion.symlink_to(original)
        with self.assertRaisesRegex(ValueError, 'CONTEXT_ARCHIVE_SYMLINK'):
            self.action(OWNER, 'archive_read', path=ref['text_file'])

    def test_private_model_reasoning_is_not_exposed_as_tool_observation(self):
        ref = self.record({'role': 'assistant', 'content': 'public', 'reasoning_content': 'private'})
        with self.assertRaisesRegex(ValueError, 'CONTEXT_ARCHIVE_PUBLIC_RECORD_REQUIRED'):
            self.action(OWNER, 'archive_read', path=ref['record_file'])

    def test_model_visible_projector_hint_names_available_archive_action(self):
        payload = {'tools': [{'type': 'function', 'function': {'name': 'bf_repository'}}],
                   'messages': [{'role': 'user', 'content': 'inspect current state'},
                                {'role': 'assistant', 'content': None, 'tool_calls': [
                                    {'id': 'summary', 'type': 'function', 'function': {'name': 'bf_repository', 'arguments': '{}'}}]},
                                {'role': 'tool', 'tool_call_id': 'summary', 'content': canonical({'values': 'v'*40000})}]}
        projected, receipt = project_interactive(payload, ContextArchive(self.store.root.parent, OWNER),
                                                 request_bytes=18000, target_bytes=8000)
        text = canonical(projected)
        self.assertIn('bf_repository.archive_read', text)
        references = [json.loads(m['content']) for m in projected['messages'] if m['role'] == 'tool']
        self.assertIn('action="archive_read"', references[0]['read_hint'])
        self.assertEqual('bf_repository.archive_read', references[0]['read_action'])
        self.assertTrue(receipt['archived_messages'])


if __name__ == '__main__':
    unittest.main()
