"""Closed-stage provenance and lossless-history controls; no paid calls or hardware."""
import copy
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from bfworld.agentlab.store import canonical, identity
from bfworld.agentlab.context import ContextArchive, project_interactive
from bfworld.agentlab import continuation_context as cc

OWNER = 'pi-chat-test-P01'


def user(text, owner=OWNER, requirements=None):
    state = {'schema_version': 'bf-product-context-v1', 'owner': owner, 'paper_id': 'P01',
             'context_scope': 'current-original-paper-native-phase',
             'requirements': requirements or ['source', 'S132', 'PCB', 'same-version-delivery'],
             'assumptions': ['physical not tested']}
    return {'role': 'user', 'content': [{'type': 'text', 'text': cc.PREFIXES[0] + canonical(state) + cc.DELIMITER + text}]}


class ClosedContinuationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / 'runtime'
        self.state = self.home / 'state'
        self.state.mkdir(parents=True)
        self.db_path = self.state / 'test.sqlite'
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('CREATE TABLE chat_messages(id,conversation,operation,text,status,created); CREATE TABLE chat_contexts(owner,config);')
        self.run = self.root / 'campaign/native-runs/P01-native-test'
        self.closed = self.run / 'continuations/turn-001'
        self.active = self.run / 'continuations/turn-002'
        self.closed.mkdir(parents=True)
        self.active.mkdir()
        original = {'owner': OWNER, 'task': 'P01-native-test', 'paper': 'P01'}
        (self.run / 'attempt.json').write_text(canonical(original))
        (self.closed / 'attempt.json').write_text(canonical({**original, 'continuation': True}))
        (self.closed / 'result.json').write_text(canonical({'execution': {'status': 'FAILED'}, 'functional_passed': False}))
        self.old_text = 'Generated old controller stage: inspect known source. ' + 'Old facts. ' * 300
        self.current_text = 'Current complete task: source to S132/BLE/receiver, native PCB, independent gates, same-version package.'
        (self.active / 'phase-task.json').write_text(canonical({'task': self.current_text}))
        for folder, text, mid in ((self.closed, self.old_text, 'old'), (self.active, self.current_text, 'current')):
            self.db.execute('INSERT INTO chat_messages VALUES(?,?,?,?,?,?)', (mid, OWNER, cc._operation(folder), text, 'ACCEPTED', 1 if mid == 'old' else 2))
        self.db.commit()
        self.manifest = cc.build_manifest(self.root, OWNER, self.active, self.db)
        self.messages = [{'role': 'system', 'content': 'Exact protected core and method'},
                         user(self.old_text), {'role': 'user', 'content': 'Real human: preserve costs and manual startup.'},
                         user(self.current_text)]
        self.archive = ContextArchive(self.home, OWNER)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def project(self, messages=None, manifest=None, archive=True):
        return cc.project_closed_continuations(self.messages if messages is None else messages,
            self.archive if archive else None, self.manifest if manifest is None else manifest)

    def install(self):
        path = self.active / 'closed-continuation-context.json'
        path.write_text(canonical(self.manifest))
        reference = {'owner': OWNER, 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        self.db.execute('INSERT INTO chat_contexts VALUES(?,?)', (OWNER, canonical({cc.KEY: reference})))
        self.db.commit()

        @contextmanager
        def connect():
            db = sqlite3.connect('file:' + str(self.db_path) + '?mode=ro', uri=True)
            db.row_factory = sqlite3.Row
            try:
                yield db
            finally:
                db.close()
        return SimpleNamespace(root=self.state, connect=connect)

    def test_current_human_core_and_original_payload_exact(self):
        before = copy.deepcopy(self.messages)
        out, records = self.project()
        self.assertEqual(len(records), 1)
        for i in (0, 2, 3): self.assertEqual(out[i], before[i])
        self.assertEqual(self.messages, before)
        self.assertLess(len(canonical(out).encode()), len(canonical(before).encode()))

    def test_registered_closed_stages_archive_below_request_size_threshold(self):
        payload = {'model': 'fixed-model', 'messages': copy.deepcopy(self.messages)}
        before = copy.deepcopy(payload)
        self.assertLess(len(canonical(payload).encode()), 24000)
        projected, report = project_interactive(payload, self.archive,
            request_bytes=32000, target_bytes=24000, closed_continuations=self.manifest)
        self.assertNotIn(self.old_text, canonical(projected))
        for index in (0, 2, 3):
            self.assertIn(before['messages'][index], projected['messages'])
        self.assertEqual(payload, before)
        self.assertIn('CLOSED_CONTROLLER_STAGE', canonical(projected['messages']))

    def test_archive_exact_bytes_and_failed_history_preserved(self):
        out, records = self.project()
        record = records[0]
        data = (self.home / 'participants' / OWNER / record['record_file']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
        self.assertEqual(json.loads(data), self.messages[1])
        self.assertFalse(json.loads((self.closed / 'result.json').read_text())['functional_passed'])
        self.assertNotIn('PASS', canonical(out[1]))

    def test_unique_prior_constraints_remain_verbatim(self):
        messages = copy.deepcopy(self.messages)
        messages[1] = user(self.old_text, requirements=['A prior non-identical manual-power boundary'])
        out, _ = self.project(messages)
        self.assertIn('A prior non-identical manual-power boundary', canonical(out[1]))

    def test_unknown_controller_like_or_unwrapped_user_not_archived(self):
        messages = [user('Generated-looking but unregistered human requirement'),
                    {'role': 'user', 'content': self.old_text}, user(self.current_text)]
        out, records = self.project(messages)
        self.assertEqual(out, messages)
        self.assertFalse(records)

    def test_appended_human_suffix_not_archived(self):
        messages = [user(self.old_text + '\nHuman exception: require approval.'), user(self.current_text)]
        out, records = self.project(messages)
        self.assertEqual(out, messages)
        self.assertFalse(records)

    def test_foreign_state_or_manifest_not_archived(self):
        messages = [user(self.old_text, owner='other'), user(self.current_text)]
        self.assertFalse(self.project(messages)[1])
        manifest = {**self.manifest, 'owner': 'other'}
        with self.assertRaises(ValueError): self.project(manifest=manifest)

    def test_active_phase_absent_or_foreign_snapshot_disables_archiving(self):
        for messages in ([user(self.old_text)], [user(self.old_text), user(self.current_text, owner='other')]):
            self.assertEqual(self.project(messages), (messages, []))

    def test_no_archive_or_no_manifest_no_change(self):
        self.assertEqual(self.project(archive=False), (self.messages, []))
        self.assertEqual(cc.project_closed_continuations(self.messages, self.archive, None), (self.messages, []))

    def test_mixed_content_and_partial_parallel_call_unchanged(self):
        mixed = user(self.old_text)
        mixed['content'].append({'type': 'image_url', 'image_url': {'url': 'local-test'}})
        call = {'role': 'assistant', 'tool_calls': [{'id': 'unreturned', 'type': 'function', 'function': {'name': 'read', 'arguments': '{}'}}]}
        messages = [mixed, user(self.current_text), call]
        self.assertEqual(self.project(messages), (messages, []))

    def test_ambiguous_identical_closed_messages_keep_original(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['closed_messages'].append({**manifest['closed_messages'][0], 'id': 'another-id'})
        self.assertEqual(self.project(manifest=manifest), (self.messages, []))

    def test_bad_registered_text_hash_keeps_original(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['closed_messages'][0]['text_sha256'] = '0' * 64
        self.assertEqual(self.project(manifest=manifest), (self.messages, []))

    def test_native_default_disabled_and_invalid_type_rejected(self):
        self.assertFalse(cc.enabled(None))
        self.assertFalse(cc.enabled({}))
        self.assertTrue(cc.enabled({'archive_closed_continuations': True}))
        for invalid in ('true', 1, None):
            with self.assertRaises(ValueError): cc.enabled({'archive_closed_continuations': invalid})

    def test_build_excludes_unclosed_and_current_attempts(self):
        unclosed = self.run / 'continuations/turn-003'
        unclosed.mkdir()
        (unclosed / 'attempt.json').write_text(canonical({'owner': OWNER, 'task': 'P01-native-test', 'continuation': True}))
        self.assertEqual(len(cc.build_manifest(self.root, OWNER, self.active, self.db)['closed_messages']), 1)

    def test_build_supports_actual_prelaunch_queued_active_intent(self):
        self.db.execute("UPDATE chat_messages SET status='QUEUED' WHERE id='current'")
        self.db.commit()
        manifest = cc.build_manifest(self.root, OWNER, self.active, self.db)
        self.assertEqual(manifest['active_message'], self.manifest['active_message'])

    def test_active_ack_transition_does_not_change_identity_or_archive_pending_history(self):
        store = self.install()
        for status in ('QUEUED', 'SENT', 'ACCEPTED'):
            self.db.execute('UPDATE chat_messages SET status=? WHERE id=?', (status, 'current'))
            self.db.commit()
            self.assertEqual(cc.load_manifest(store, OWNER), self.manifest)
        self.db.execute("UPDATE chat_messages SET status='QUEUED' WHERE id='old'")
        self.db.commit()
        with self.assertRaises(ValueError): cc.load_manifest(store, OWNER)

    def test_unknown_active_intent_is_not_replayed_or_authorized(self):
        self.db.execute("UPDATE chat_messages SET status='UNKNOWN' WHERE id='current'")
        self.db.commit()
        with self.assertRaises(ValueError): cc.build_manifest(self.root, OWNER, self.active, self.db)

    def test_build_requires_original_owner_and_exact_active_task(self):
        with self.assertRaises(ValueError): cc.build_manifest(self.root, 'other', self.active, self.db)
        (self.active / 'phase-task.json').write_text(canonical({'task': 'not-in-active-message'}))
        with self.assertRaises(ValueError): cc.build_manifest(self.root, OWNER, self.active, self.db)

    def test_verified_manifest_load_is_read_only(self):
        store = self.install()
        before = self.db_path.read_bytes()
        self.assertEqual(cc.load_manifest(store, OWNER), self.manifest)
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_unknown_owner_has_no_manifest(self):
        store = self.install()
        self.assertIsNone(cc.load_manifest(store, 'other'))

    def test_standalone_provider_without_organization_defaults_disabled(self):
        store = self.install()
        self.db.execute('DROP TABLE chat_contexts')
        self.db.commit()
        self.assertIsNone(cc.load_manifest(store, OWNER))

    def test_tampered_manifest_rejected_before_projection(self):
        store = self.install()
        (self.active / 'closed-continuation-context.json').write_text('{}')
        with self.assertRaises(ValueError): cc.load_manifest(store, OWNER)

    def test_missing_closure_rejected_before_projection(self):
        store = self.install()
        (self.closed / 'result.json').unlink()
        with self.assertRaises((ValueError, OSError)): cc.load_manifest(store, OWNER)

    def test_changed_closed_source_or_db_text_rejected(self):
        store = self.install()
        self.db.execute('UPDATE chat_messages SET text=? WHERE id=?', ('changed', 'old'))
        self.db.commit()
        with self.assertRaises(ValueError): cc.load_manifest(store, OWNER)

    def test_changed_active_phase_rejected(self):
        store = self.install()
        (self.active / 'phase-task.json').write_text(canonical({'task': 'changed'}))
        with self.assertRaises(ValueError): cc.load_manifest(store, OWNER)

    def test_closure_symlink_rejected(self):
        store = self.install()
        path = self.closed / 'result.json'
        other = self.root / 'external-result.json'
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
        with self.assertRaises(ValueError): cc.load_manifest(store, OWNER)

    def test_loader_rejects_rebound_foreign_attempt(self):
        self.manifest['closed_messages'][0]['attempt']['path'] = str(self.root / 'foreign/attempt.json')
        store = self.install()
        with self.assertRaises(ValueError): cc.load_manifest(store, OWNER)

    def test_no_pressure_without_manifest_keeps_unregistered_history(self):
        payload = {'model': 'deepseek-flash', 'messages': self.messages}
        old, _ = project_interactive(payload, self.archive, request_bytes=80000, target_bytes=60000)
        new, _ = project_interactive(payload, self.archive, request_bytes=80000, target_bytes=60000,
                                     closed_continuations=self.manifest)
        self.assertIn(self.old_text, canonical(old))
        self.assertNotIn(self.old_text, canonical(new))
        for index in (0, 2, 3):
            self.assertIn(self.messages[index], old['messages'])
            self.assertIn(self.messages[index], new['messages'])

    def test_pressure_keeps_current_core_human_and_tool_arguments(self):
        messages = copy.deepcopy(self.messages)
        for index in range(10):
            messages.extend([{'role': 'assistant', 'tool_calls': [{'id': str(index), 'type': 'function',
                'function': {'name': 'read', 'arguments': canonical({'path': 'actual-source.txt', 'offset': index})}}]},
                {'role': 'tool', 'tool_call_id': str(index), 'content': 'Evidence ' * 500}])
        payload = {'model': 'deepseek-flash', 'messages': messages}
        out, audit = project_interactive(payload, self.archive, request_bytes=30000, target_bytes=24000,
                                        closed_continuations=self.manifest)
        self.assertTrue(audit['fits'])
        self.assertTrue(any(r.get('kind') == 'closed_controller_continuation' for r in audit['archived_messages']))
        for index in (0, 2, 3): self.assertIn(messages[index], out['messages'])
        for message in out['messages']:
            if message.get('role') == 'assistant': self.assertIn(message, messages)

    def test_native_controller_and_provider_use_verified_manifest_before_dispatch(self):
        # This is an integration edge control, in addition to actual runtime tests.
        from bfworld.agentlab import literature_native, provider
        import inspect
        native = inspect.getsource(literature_native.run_native_tasks)
        self.assertLess(native.index('closed_history=build_manifest'), native.index('app.organization.bind'))
        self.assertLess(native.index('app.organization.bind'), native.index('receipt=launcher.launch'))
        model = inspect.getsource(provider.Provider.complete)
        self.assertLess(model.index('closed_continuations=load_manifest'), model.index('request_id='))


if __name__ == '__main__':
    unittest.main()
