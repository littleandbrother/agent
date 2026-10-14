"""A/B isolation contracts; no solver, provider or production Workbench."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from bfworld.agentlab import environment_profile as ep
from bfworld.agentlab import baseline


class DevelopmentProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root/'v2-source'
        self.runtime = self.root/'v2-runtime'
        self.source.mkdir(); self.runtime.mkdir()
        self.home = self.runtime/'workbench'
        self.base = self.root/'baseline'
        self.base.mkdir(); (self.base/'manifest.json').write_text('{}')
        self.path = self.runtime/'profile.json'
        self.value = {'schema_version': ep.SCHEMA, 'kind': 'Architecture V2', 'id': 'v2-fixture',
                      'source_root': str(self.source), 'runtime_root': str(self.runtime), 'home': str(self.home),
                      'pi_root': str(self.source/'pi-bf-aiot'), 'configuration': str(self.runtime/'runtime.json'),
                      'protected_roots': [str(self.root/'production'), str(self.base)],
                      'protected_owners': ['pi-chat-original'], 'port': 8870, 'production_port': 8768,
                      'shared_native_lock': str(self.root/'host-native.lock'),
                      'baseline': {'path': str(self.base), 'manifest_sha256': ep.sha256(self.base/'manifest.json')},
                      'native_project_uuids': [], 'protected_native_project_uuids': ['original-eda'],
                      'capabilities': {'model': False, 'native': False, 'agent': False},
                      'eda': {'transport': 'easyeda-typed-v1'},
                      'paths': {'HOME': str(self.home), 'PI_ROOT': str(self.source/'pi-bf-aiot'),
                                'PROVIDER_KEY_FILE': str(self.home/'secrets/deepseek.key'),
                                'EDA_LOCAL_PROJECT_ROOT': str(self.runtime/'native-projects'),
                                'NATIVE_LOCK': str(self.root/'host-native.lock')}}
        self.environ = {'BF_RUNTIME_ROOT': str(self.runtime), 'BF_RUNTIME_CONFIG': self.value['configuration'],
                        'BF_HOME': str(self.home), 'BF_PI_ROOT': self.value['pi_root'], 'BF_DEVELOPMENT_PROFILE': str(self.path),
                        'PI_CODING_AGENT_DIR': str(self.home/'pi-config')}

    def tearDown(self):
        self.tmp.cleanup()

    def validate(self):
        self.path.write_text(json.dumps(self.value))
        ref = {'path': str(self.path), 'sha256': ep.sha256(self.path)}
        config = {'schema_version': 'bf-runtime-layout-v1', 'paths': self.value['paths'],
                  'eda': self.value['eda'], 'development_profile': ref}
        return ep.validate(ref, config, self.environ, self.source)

    def test_explicit_isolated_profile(self):
        p = self.validate()
        self.assertEqual(p['home'], str(self.home))
        self.assertFalse(self.home.exists())

    def test_all_four_paths_are_mandatory(self):
        for name in ep.MANDATORY:
            with self.subTest(name=name):
                old = self.environ.pop('BF_'+name)
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_PATH_REQUIRED'):
                    self.validate()
                self.environ['BF_'+name] = old

    def test_production_env_override(self):
        self.environ['BF_HOME'] = str(self.root/'production')
        with self.assertRaisesRegex(ValueError, 'PATH_MISMATCH'):
            self.validate()

    def test_tool_override_rejected(self):
        self.environ['BF_NATIVE_LOCK'] = str(self.runtime/'different.lock')
        with self.assertRaisesRegex(ValueError, 'OVERRIDE_CHANGED'):
            self.validate()

    def test_pi_global_state_rejected(self):
        self.environ['PI_CODING_AGENT_DIR'] = str(self.root/'production/pi-config')
        with self.assertRaisesRegex(ValueError, 'PI_STATE_SCOPE'):
            self.validate()

    def test_protected_directory_collision(self):
        self.value['protected_roots'].append(str(self.runtime.parent))
        with self.assertRaisesRegex(ValueError, 'PRODUCTION_COLLISION'):
            self.validate()

    def test_symlink_alias_rejected(self):
        alias = self.root/'runtime-alias'; alias.symlink_to(self.runtime, target_is_directory=True)
        self.environ['BF_RUNTIME_ROOT'] = str(alias)
        with self.assertRaisesRegex(ValueError, 'PATH_SYMLINK'):
            self.validate()

    def test_profile_tamper_rejected(self):
        p = self.validate(); ref = {'path': p['path'], 'sha256': p['sha256']}
        self.path.write_text(self.path.read_text()+' ')
        with self.assertRaisesRegex(ValueError, 'PROFILE_CHANGED'):
            ep.validate(ref, {}, self.environ, self.source)

    def test_configuration_tamper_rejected(self):
        p = self.validate(); ref = {'path': p['path'], 'sha256': p['sha256']}
        config = {'schema_version': 'bf-runtime-layout-v1', 'paths': p['paths'], 'eda': {'host': 'web'}, 'development_profile': ref}
        with self.assertRaisesRegex(ValueError, 'CONFIGURATION_CHANGED'):
            ep.validate(ref, config, self.environ, self.source)

    def test_wrong_source_and_port(self):
        p = self.validate(); ref = {'path': p['path'], 'sha256': p['sha256']}
        with self.assertRaisesRegex(ValueError, 'SOURCE_MISMATCH'):
            ep.validate(ref, {}, self.environ, self.root)
        self.value['port'] = 8768
        with self.assertRaisesRegex(ValueError, 'PORT_COLLISION'):
            self.validate()

    def test_original_native_identity_not_qualified(self):
        self.value['native_project_uuids'] = ['original-eda']
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_NATIVE_PROJECT_REJECTED'):
            self.validate()

    def test_shared_lock_is_mandatory(self):
        self.value['shared_native_lock'] = str(self.runtime/'other.lock')
        with self.assertRaisesRegex(ValueError, 'SHARED_LOCK_REQUIRED'):
            self.validate()

    def test_baseline_manifest_tamper(self):
        (self.base/'manifest.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, 'BASELINE_CHANGED'):
            self.validate()

    def test_empty_runtime_and_restart_keep_identity(self):
        p = self.validate(); root = self.home/'state'
        ep.workbench_root(p, root)
        old = (root/'development-runtime.json').read_bytes()
        ep.workbench_root(p, root)
        self.assertEqual((root/'development-runtime.json').read_bytes(), old)

    def test_foreign_state_root_has_no_write(self):
        p = self.validate(); foreign = self.root/'production/state'
        with self.assertRaisesRegex(ValueError, 'STATE_ROOT_MISMATCH'):
            ep.workbench_root(p, foreign)
        self.assertFalse(foreign.exists())

    def test_imported_database_rejected(self):
        p = self.validate(); root = self.home/'state'; root.mkdir(parents=True)
        with sqlite3.connect(root/'workbench.sqlite') as db:
            db.execute('CREATE TABLE conversations(id TEXT)')
        with self.assertRaisesRegex(ValueError, 'HISTORICAL_DATABASE_REJECTED'):
            ep.workbench_root(p, root)

    def test_original_owner_in_existing_database_rejected(self):
        p = self.validate(); root = self.home/'state'; ep.workbench_root(p, root)
        with sqlite3.connect(root/'workbench.sqlite') as db:
            db.execute('CREATE TABLE conversations(id TEXT)')
            db.execute("INSERT INTO conversations VALUES('pi-chat-original')")
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_OWNER_REJECTED'):
            ep.workbench_root(p, root)

    def test_original_billing_in_existing_database_rejected(self):
        p = self.validate(); root = self.home/'state'; ep.workbench_root(p, root)
        with sqlite3.connect(root/'workbench.sqlite') as db:
            db.execute('CREATE TABLE model_requests(owner TEXT)')
            db.execute("INSERT INTO model_requests VALUES('pi-chat-original')")
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_LEDGER_REJECTED'):
            ep.workbench_root(p, root)

    def test_capabilities_are_disabled(self):
        p = self.validate()
        for capability in ['agent', 'model', 'native']:
            with self.subTest(capability=capability):
                with self.assertRaisesRegex(PermissionError, 'CAPABILITY_DISABLED'):
                    ep.require(p, capability)

    def test_native_project_allowlist(self):
        p = self.validate(); p['capabilities']['native'] = True; p['native_project_uuids'] = ['dev-project']
        ep.project(p, 'dev-project')
        with self.assertRaisesRegex(PermissionError, 'PROJECT_NOT_QUALIFIED'):
            ep.project(p, 'original-eda')

    def test_baseline_without_profile_compatibility(self):
        ep.require(None, 'native'); ep.project(None, 'original-eda'); ep.workbench_root(None, self.root/'unused')
        self.assertFalse((self.root/'unused').exists())


class BaselineAuditTests(unittest.TestCase):
    def test_read_only_source_and_unknown_preservation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'history.sqlite'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE model_requests(id TEXT,owner TEXT,reserved REAL,charged REAL,status TEXT)')
                db.execute("INSERT INTO model_requests VALUES('r1','pi-chat-original',0.123,0,'UNKNOWN')")
            before = baseline.logical_state(path); baseline.quiescent(path)
            with baseline.readonly(path) as db:
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute('UPDATE model_requests SET reserved=0')
            summary = baseline.database_summary(path, ['pi-chat-original'])
            self.assertEqual(summary['unknown'][0]['reserved'], .123)
            self.assertEqual(baseline.logical_state(path), before)

    def test_active_dispatch_stops_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'active.sqlite'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE model_requests(status TEXT)')
                db.execute("INSERT INTO model_requests VALUES('DISPATCHED')")
            with self.assertRaisesRegex(ValueError, 'ACTIVE_WRITER'):
                baseline.quiescent(path)

    def test_mutated_backup_file_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root/'file').write_text('stable')
            value = {'schema_version': 'bf-baseline-manifest-v1', 'files': {'file': {'sha256': baseline.digest(root/'file'), 'bytes': 6}}, 'database_fingerprints': {}}
            (root/'manifest.json').write_text(json.dumps(value))
            self.assertEqual(baseline.verify(root)['status'], 'PASS')
            (root/'file').write_text('mutated')
            with self.assertRaisesRegex(ValueError, 'FILE_CHANGED'):
                baseline.verify(root)


if __name__ == '__main__':
    unittest.main()
