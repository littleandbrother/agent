"""Native source acquisition: opt-in, owner isolation and exact source bytes.

Only temporary SQLite/blob fixtures and mocked public responses are used.
No Workbench, provider, engineering worker or physical solver is started.
"""
import contextlib
import ast
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bfworld.agentlab import literature_native, references
from bfworld.agentlab.store import canonical

reference_candidate = os.environ.get('BF_REFERENCE_AUTH_CANDIDATE')
if reference_candidate:
    spec = importlib.util.spec_from_file_location(
        'bfworld.agentlab.reference_authority_candidate', reference_candidate)
    references = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(references)

candidate = os.environ.get('BF_NATIVE_REFERENCE_CANDIDATE')
if candidate:
    spec = importlib.util.spec_from_file_location(
        'bfworld.agentlab.native_reference_candidate', candidate)
    literature_native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(literature_native)


class TemporaryReferenceStore:
    def __init__(self, root):
        self.root = root / 'state'
        self.root.mkdir()
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            'CREATE TABLE chat_contexts(owner TEXT,config TEXT);'
            'CREATE TABLE grants(owner TEXT,expires REAL);'
            'CREATE TABLE interactive_leases(owner TEXT,message_id TEXT,created REAL,expires REAL);'
            'CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);'
            'CREATE TABLE reference_records(id TEXT PRIMARY KEY,owner TEXT,kind TEXT,created REAL,payload TEXT);')

    @contextlib.contextmanager
    def connect(self):
        yield self.connection


class NativeReferenceCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = TemporaryReferenceStore(self.root)
        self.addCleanup(self.store.connection.close)
        self.events = []
        self.service = references.References.__new__(references.References)
        self.service.store = self.store
        self.service.root = self.root / 'references'
        (self.service.root / 'blobs').mkdir(parents=True)
        self.service.app = SimpleNamespace(
            engineering=SimpleNamespace(event=lambda *args: self.events.append(args)),
            products=SimpleNamespace(context=lambda owner: {'proposal': {'revision': 1}}))
        self.owner = 'pi-chat-original-fixture'

    def policy(self, **changes):
        value = {'schema_version':'bf-model-unbounded-policy-v2','mode':'unbounded',
                 'authorized_by':'direct-user','direct_user_authorization':'取消累计费用与 token 上限',
                 'fees_reset':False,'unknown_reservations_preserved':True,
                 'cumulative_usd_cap':None,'cumulative_token_cap':None,
                 'request_count_cap':None,'request_usd_cap':None,
                 'scope':'owners','owners':[self.owner],
                 'wall_seconds':None,'wall_authorized_by':'direct-user',
                 'wall_authorization_text':'持续运行 不设置时间限制',
                 'wall_unbounded':True,'wall_owners':[self.owner],
                 'unknown_carryforward':{}}
        value.update(changes)
        self.store.connection.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',
                                      ('model_unbounded_policy', canonical(value)))
        return value

    def rows(self):
        return {table:[tuple(row) for row in self.store.connection.execute('SELECT * FROM '+table)]
                for table in ('chat_contexts','grants','interactive_leases','settings','reference_records')}

    def enable(self, tools=None, expires=None, owner=None):
        owner = owner or self.owner
        tools = tools if tools is not None else literature_native.native_phase_tools(True, True)
        self.store.connection.execute('INSERT INTO chat_contexts VALUES(?,?)',
                                      (owner, canonical({'tools': tools})))
        self.store.connection.execute('INSERT INTO grants VALUES(?,?)',
                                      (owner, time.time() + 60 if expires is None else expires))

    def acquire(self):
        raw = b'/* isolated primary-source fixture, not a target design */\n#define VDD_MIN 3\n'
        meta = {'content_type': 'text/plain', 'final_url': 'https://example.org/vendor.h'}
        with patch.object(references, 'fetch_public', return_value=(raw, meta)):
            source = self.service.action(self.owner, {'action': 'fetch', 'url': meta['final_url']})
        return raw, source

    def test_default_and_other_phases_never_implicitly_enable_research(self):
        self.assertFalse(literature_native.native_reference_enabled(None))
        for phase in ('eda', 'firmware', 'delivery', 'engineering-review'):
            self.assertFalse(literature_native.native_reference_enabled({'phase': phase}))
            self.assertFalse(literature_native.native_route_allowed('/api/references', phase, True))
        self.assertNotIn('bf_reference', literature_native.native_phase_tools(True))

    def test_explicit_capability_adds_only_existing_reference_tool_and_route(self):
        enabled = literature_native.native_reference_enabled({'allow_reference_research': True})
        parent = literature_native.native_phase_tools(True, False)
        current = literature_native.native_phase_tools(True, enabled)
        self.assertEqual(parent + ['bf_reference'], current)
        self.assertTrue(literature_native.native_route_allowed('/api/references', 'engineering-review', True, enabled))
        for route in ('/api/measurements/import', '/api/submit', '/api/design-lab', '/api/fees', '/api/operator'):
            self.assertFalse(literature_native.native_route_allowed(route, 'engineering-review', True, enabled))
        self.assertFalse(literature_native.native_route_allowed('/api/references/source', 'eda', True, enabled))

    def test_nonboolean_activation_rejects_instead_of_truthy_enabling(self):
        for value in ('true', 1, 0, None, [], {}, 'false'):
            with self.assertRaisesRegex(ValueError, 'NATIVE_REFERENCE_CAPABILITY_INVALID'):
                literature_native.native_reference_enabled({'allow_reference_research': value})
        self.assertFalse(literature_native.native_reference_enabled({'allow_reference_research': False}))

    def test_eda_resolution_and_other_engineering_routes_are_independent(self):
        self.assertNotIn('bf_eda', literature_native.native_phase_tools(False, True))
        self.assertTrue(literature_native.native_route_allowed('/api/references', 'firmware', False, True))
        self.assertFalse(literature_native.native_route_allowed('/api/eda-cli', 'firmware', False, True))
        self.assertTrue(literature_native.native_route_allowed('/api/eda-cli', 'eda', False, False))
        self.assertTrue(literature_native.native_route_allowed('/api/engineering', 'firmware', False, False))

    def test_existing_service_authorizes_only_enabled_owner_and_live_grant(self):
        self.enable()
        self.service.authorize(self.owner)
        for owner in ('foreign', 'operator'):
            with self.assertRaisesRegex(PermissionError, 'REFERENCE_TOOL_NOT_ENABLED'):
                self.service.authorize(owner)
        self.enable(owner='disabled', tools=literature_native.native_phase_tools(True, False))
        self.enable(owner='expired', expires=time.time() - 1)
        for owner in ('disabled', 'expired'):
            with self.assertRaisesRegex(PermissionError, 'REFERENCE_TOOL_NOT_ENABLED'):
                self.service.authorize(owner)

    def test_expired_grant_uses_explicit_wall_authority_without_mutating_history(self):
        self.enable(expires=time.time() - 3600)
        self.store.connection.execute('INSERT INTO interactive_leases VALUES(?,?,?,?)',
                                      (self.owner,'historical-message',1,2))
        self.policy()
        before = self.rows()
        self.service.authorize(self.owner)
        result = literature_native.native_reference_preflight(
            SimpleNamespace(references=self.service), self.owner, True)
        self.assertEqual('AUTHORIZED', result['status'])
        self.assertFalse(result['source_acquisition_verified'])
        self.assertEqual(before, self.rows())
        self.assertEqual([], self.events)

    def test_financial_authority_alone_does_not_override_expired_time(self):
        self.enable(expires=time.time() - 1)
        self.policy(schema_version='bf-model-unbounded-policy-v1')
        with self.assertRaisesRegex(PermissionError,'REFERENCE_TOOL_NOT_ENABLED'):
            self.service.authorize(self.owner)

    def test_foreign_and_excluded_wall_owner_do_not_inherit_authority(self):
        self.enable(expires=time.time() - 1)
        for changes in ({'owners':['pi-chat-foreign']},
                        {'wall_owners':['pi-chat-foreign']}):
            self.policy(**changes)
            with self.assertRaisesRegex(PermissionError,'REFERENCE_TOOL_NOT_ENABLED'):
                self.service.authorize(self.owner)

    def test_wall_authority_does_not_replace_grant_or_tool_permission(self):
        self.policy()
        self.store.connection.execute('INSERT INTO chat_contexts VALUES(?,?)',
                                      (self.owner,canonical({'tools':['bf_reference']})))
        with self.assertRaisesRegex(PermissionError,'REFERENCE_TOOL_NOT_ENABLED'):
            self.service.authorize(self.owner)
        self.store.connection.execute('DELETE FROM chat_contexts')
        self.enable(tools=['bf_engineering'],expires=time.time()-1)
        with self.assertRaisesRegex(PermissionError,'REFERENCE_TOOL_NOT_ENABLED'):
            self.service.authorize(self.owner)

    def test_invalid_wall_authority_is_rejected_and_history_is_unchanged(self):
        self.enable(expires=time.time() - 1)
        self.policy(wall_authorization_text='inferred permission')
        before = self.rows()
        with self.assertRaisesRegex(ValueError,'MODEL_UNBOUNDED_TIME_AUTH_REQUIRED'):
            self.service.authorize(self.owner)
        self.assertEqual(before, self.rows())

    def test_disabled_source_preflight_has_no_tool_or_network_dependency(self):
        result = literature_native.native_reference_preflight(SimpleNamespace(),self.owner,False)
        self.assertEqual('DISABLED',result['status'])
        for invalid in ('true',1,None):
            with self.assertRaisesRegex(ValueError,'NATIVE_REFERENCE_CAPABILITY_INVALID'):
                literature_native.native_reference_preflight(SimpleNamespace(),self.owner,invalid)

    def test_failed_source_preflight_propagates_before_any_launch(self):
        self.enable(expires=time.time() - 1)
        with self.assertRaisesRegex(PermissionError,'REFERENCE_TOOL_NOT_ENABLED'):
            literature_native.native_reference_preflight(
                SimpleNamespace(references=self.service),self.owner,True)
        self.assertEqual([],self.events)
        self.assertEqual([],self.rows()['reference_records'])

    def test_actual_dispatch_installs_context_then_checks_sources_before_launcher(self):
        # Verify the mandatory production dispatch edge, not a second mock
        # dispatch implementation which could accidentally test itself.
        tree = ast.parse(inspect.getsource(literature_native.run_native_tasks))
        calls = [(node.lineno,ast.unparse(node.func)) for node in ast.walk(tree)
                 if isinstance(node,ast.Call)]
        bind = [line for line,name in calls if name=='app.organization.bind']
        source = [line for line,name in calls if name=='native_reference_preflight']
        launch = [line for line,name in calls if name=='launcher.launch']
        self.assertEqual(1,len(bind));self.assertEqual(1,len(source));self.assertEqual(1,len(launch))
        self.assertLess(bind[0],source[0]);self.assertLess(source[0],launch[0])

    def test_operator_inventory_uses_existing_connection_without_workbench_or_writes(self):
        script = os.environ.get('BF_MAINLINE_PREFLIGHT_CANDIDATE') or str(
            Path(__file__).resolve().parents[2] / 'scripts/design_lab/p01_mainline_preflight.py')
        spec = importlib.util.spec_from_file_location('bf_reference_preflight_inventory',script)
        module = importlib.util.module_from_spec(spec)
        # Loading an unpromoted candidate must resolve its matching candidate
        # imports without modifying production source or starting a Workbench.
        with patch.dict(sys.modules,{'bfworld.agentlab.references':references,
                                   'bfworld.agentlab.literature_native':literature_native}):
            spec.loader.exec_module(module)
        # Use the same candidate implementations as the mandatory dispatch.
        with patch.object(module,'References',references.References), \
             patch.object(module,'native_reference_preflight',literature_native.native_reference_preflight):
            self.enable(expires=time.time()-1)
            self.policy()
            before = self.rows()
            self.store.connection.execute('PRAGMA query_only=ON')
            result = module.source_capability_inventory(
                self.store.connection,self.owner,{'allow_reference_research':True})
            self.assertEqual('AUTHORIZED',result['status'])
            self.assertTrue(result['installed_tool'])
            self.assertEqual(before,self.rows())
            disabled = module.source_capability_inventory(self.store.connection,self.owner,{})
            self.assertEqual('DISABLED',disabled['status'])
            self.assertEqual(before,self.rows())

    def test_materialization_and_reads_preserve_exact_raw_hash_and_scope(self):
        self.enable()
        raw, source = self.acquire()
        saved = self.service.action(self.owner, {'action': 'materialize', 'reference_id': source['id'], 'file_path': 'vendor/header.h'})
        self.assertEqual(raw, (self.root / 'participants' / self.owner / 'vendor/header.h').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), saved['sha256'])
        self.assertEqual('external-untrusted-data', saved['content_trust'])
        self.assertEqual('acquired-not-reproduced', saved['evidence_level'])
        self.assertEqual(raw.decode(), self.service.read(self.owner, source['id'])['text'])
        with self.assertRaisesRegex(PermissionError, 'REFERENCE_NOT_FOUND'):
            self.service.read('foreign', source['id'])
        with self.assertRaisesRegex(PermissionError, 'REFERENCE_NOT_FOUND'):
            self.service.materialize('foreign', source['id'], 'vendor/header.h')

    def test_conflicting_and_escaping_paths_do_not_overwrite_design(self):
        raw, source = self.acquire()
        workspace = self.root / 'participants' / self.owner
        workspace.mkdir(parents=True)
        design = workspace / 'design.c'
        design.write_bytes(b'original Pi design')
        for name in ('design.c', '../foreign/design.c', str(self.root / 'absolute.h')):
            with self.assertRaises(ValueError):
                self.service.materialize(self.owner, source['id'], name)
        (workspace / 'escape').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.service.materialize(self.owner, source['id'], 'escape/outside.h')
        self.assertEqual(b'original Pi design', design.read_bytes())
        self.assertFalse((self.root / 'outside.h').exists())

    def test_changed_blob_fails_and_does_not_create_target(self):
        raw, source = self.acquire()
        blob = self.service.root / 'blobs' / source['raw_sha256']
        blob.write_bytes(b'changed vendor source')
        with self.assertRaisesRegex(ValueError, 'REFERENCE_BLOB_TAMPER'):
            self.service.materialize(self.owner, source['id'], 'vendor/header.h')
        self.assertFalse((self.root / 'participants' / self.owner / 'vendor/header.h').exists())

    def test_source_adoption_is_interpretation_not_acceptance(self):
        raw, source = self.acquire()
        body = {'action': 'adopt', 'reference_id': source['id'], 'proposal_revision': 1,
                **{key: 'fixture interpretation, independently unverified' for key in
                   ('application', 'locator', 'assumptions', 'differences', 'required_checks')}}
        adopted = self.service.action(self.owner, body)
        self.assertEqual('participant-interpretation-not-validation', adopted['evidence_level'])
        self.assertNotIn('full_product_passed', adopted)
        with self.assertRaisesRegex(ValueError, 'REFERENCE_PROPOSAL_REVISION_STALE'):
            self.service.action(self.owner, {**body, 'proposal_revision': 2})

    def test_private_networks_and_credentials_remain_denied(self):
        for address in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1'):
            with patch.object(socket, 'getaddrinfo', return_value=[(None, None, None, None, (address, 443))]):
                with self.assertRaisesRegex(ValueError, 'PRIVATE_NETWORK'):
                    references.public_target('https://example.org/vendor.pdf')
        for url in ('file:///etc/passwd', 'https://user:secret@example.org', 'http://example.org:8768'):
            with self.assertRaises(ValueError):
                references.public_target(url)

    def test_retrieval_failure_keeps_original_facts(self):
        with patch.object(references, 'fetch_public', side_effect=ValueError('REFERENCE_HTTP_403')):
            with self.assertRaisesRegex(ValueError, 'REFERENCE_HTTP_403'):
                self.service.action(self.owner, {'action': 'fetch', 'url': 'https://example.org/vendor.pdf'})
        failures = self.service.projection(self.owner)['records']
        self.assertEqual(1, len(failures))
        self.assertEqual('failure', failures[0]['kind'])
        self.assertEqual('REFERENCE_HTTP_403', failures[0]['error'])
        self.assertEqual('https://example.org/vendor.pdf', failures[0]['request']['url'])


if __name__ == '__main__':
    unittest.main()
