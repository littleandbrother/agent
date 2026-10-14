"""An unknown native edit needs closed-generation evidence, not a retry."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

APP = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_unknown_recovery', APP/'scripts/eda/reconcile_native_unknown.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class NativeUnknownRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root/'proof'
        self.folder.mkdir()
        local = self.root/'local'
        local.mkdir()
        self.path = local/'P01.eprj3'
        self.sources = []
        for name in ('P01.eprj3', 'sch/P1.esch2', 'pcb/PCB1.epcb2'):
            p = local/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('preserved-' + name)
            if name.endswith('.esch2'):
                p.write_text('{"type":"DOCHEAD"}||{"docType":"SCH_PAGE","uuid":"sheet"}|\n'
                             '{"type":"ATTR","id":"stored"}||{"key":"Name","value":"R3"}|\n')
            self.sources.append({'path': name, 'sha256': recovery.digest(p)})
        self.proof = {'schema_version': 'bf-native-unknown-generation-reconciliation-v1',
                      'actor': 'Codex operator recovery', 'paper': 'P01', 'owner': 'pi-original',
                      'project': 'runtime', 'request_id': 'req_379', 'action': 'schematic.power.connect_pin',
                      'old_session': 'old', 'new_session': 'new', 'local_project': str(self.path),
                      'document': 'sheet', 'persisted_sources': self.sources, 'evidence': {}}
        self.blocked = {'runtime': {'request_id': 'req_379', 'action': self.proof['action'],
                                   'at': '2026-10-12T17:31:25Z', 'error': 'NATIVE_EXECUTION_UNKNOWN'}}
        self.base_time = 1791826320
        source = {'sessionId': 'old', 'headless': True, 'origin': 'cli', 'path': str(self.path), 'status': 'alive'}
        foreign = {'sessionId': 'foreign', 'headless': True, 'origin': 'cli', 'path': '/other.eprj3', 'status': 'alive'}
        target = dict(source, sessionId='new')
        context = {'projectUuid': 'runtime', 'documentUuid': 'sheet', 'environment': {'host': 'desktop'}}
        self.scene = {'ok': True, 'context': context,
                      'result': {'components': [{'id': 'R3', 'pins': [{'primitiveId': 'pin1', 'id': '1', 'net': ''}]}],
                                 'wires': [{'id': 'wire', 'points': [[0, 0], [1, 0], [1, 1]]}],
                                 'wiresAvailable': True, 'pagePrimitives': {'components': [{'id': 'R3', 'x': 10}],
                                     'attributes': [{'primitiveId': 'stored', 'X': 10, 'Value': 'R3'}]},
                                 'connectivitySummary': {'wires': 1}}}
        self.record('old_sessions', [source, foreign], self.base_time)
        self.record('close', {'sessionId': 'old', 'status': 'closed', 'headless': True}, self.base_time+10)
        self.record('new_sessions', [target, foreign], self.base_time+20)
        self.record('project_read', {'ok': True, 'result': {'uuid': 'runtime'}, 'context': context}, self.base_time+21)
        self.record('before_read', self.scene, self.base_time+1)
        self.record('after_read', self.scene, self.base_time+22)
        self.record('after_read_again', self.scene, self.base_time+23)
        directory = self.root/'campaign/eda/P01'
        directory.mkdir(parents=True)
        binding = {'paper_id': 'P01', 'owner': 'pi-original', 'local_project': str(self.path),
                   'project_uuid': 'creation', 'writable': True}
        p = directory/'binding.json'; p.write_text(json.dumps(binding))
        self.proof['binding_sha256'] = recovery.digest(p)
        alias = {'paper_id': 'P01', 'owner': 'pi-original', 'local_project': str(self.path),
                 'binding_record_sha256': recovery.digest(p), 'created_project_uuid': 'creation', 'runtime_project_uuid': 'runtime'}
        p = directory/'alias.json'; p.write_text(json.dumps(alias))
        self.proof.update(alias_name=p.name, alias_sha256=recovery.digest(p))
        p = self.root/'campaign/parallel-20261009/pi-session-index.json'
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'sessions': [{'paper_id': 'P01', 'owner': 'pi-original'}]}))

    def record(self, name, value, created):
        p = self.folder/(name+'.json')
        p.write_text(json.dumps({'created': created, 'exit_code': 0,
                                 'stdout': json.dumps({'ok': True, 'value': copy.deepcopy(value)})}))
        self.proof['evidence'][name] = {'path': p.name, 'sha256': recovery.digest(p)}

    def value(self, name):
        return json.loads(json.loads((self.folder/(name+'.json')).read_text())['stdout'])['value']

    def validate(self):
        recovery.validate_campaign_binding(self.root, self.proof)
        return recovery.validate_evidence(self.blocked, self.proof, self.folder)

    def test_exact_generation_recovery_preserves_original_unknown(self):
        before = copy.deepcopy(self.blocked)
        record = self.validate()
        self.assertEqual(self.blocked, before)
        self.assertFalse(record['original_outcome_rewritten'])
        self.assertFalse(record['unknown_action_replayed'])

    def test_elapsed_time_and_readback_cannot_replace_close_ack(self):
        self.record('close', {'sessionId': 'old', 'status': 'alive', 'headless': True}, self.base_time+10)
        with self.assertRaisesRegex(ValueError, 'CLOSE_ACK'):
            self.validate()

    def test_old_generation_must_be_closed(self):
        self.record('new_sessions', self.value('new_sessions') + [self.value('old_sessions')[0]], self.base_time+20)
        with self.assertRaisesRegex(ValueError, 'SAME_LOCAL_CLI'):
            self.validate()

    def test_closed_session_history_is_retained(self):
        old = self.value('old_sessions')[0]
        old['status'] = 'closed'
        self.record('new_sessions', self.value('new_sessions') + [old], self.base_time+20)
        self.assertFalse(self.validate()['original_outcome_rewritten'])

    def test_foreign_sessions_are_untouched(self):
        new = self.value('new_sessions'); new[1]['status'] = 'closed'
        self.record('new_sessions', new, self.base_time+20)
        with self.assertRaisesRegex(ValueError, 'FOREIGN_NATIVE_SESSION_CHANGED'):
            self.validate()

    def test_foreign_owner_is_rejected(self):
        self.proof['owner'] = 'another-owner'
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_CAMPAIGN_OWNER'):
            self.validate()

    def test_fresh_project_identity_is_required(self):
        current = self.value('project_read'); current['result']['uuid'] = 'foreign'
        self.record('project_read', current, self.base_time+21)
        with self.assertRaisesRegex(ValueError, 'FRESH_EXACT_PROJECT'):
            self.validate()

    def test_geometry_and_net_changes_are_not_ignored(self):
        for change in ('net', 'position', 'point_order'):
            with self.subTest(change=change):
                scene = copy.deepcopy(self.scene)
                if change == 'net': scene['result']['components'][0]['pins'][0]['net'] = 'VDD'
                elif change == 'position': scene['result']['pagePrimitives']['components'][0]['x'] = 20
                else: scene['result']['wires'][0]['points'].reverse()
                self.record('after_read', scene, self.base_time+22)
                with self.assertRaisesRegex(ValueError, 'SCENE_MISMATCH'):
                    self.validate()

    def test_partial_inventory_cannot_clear_quarantine(self):
        scene = copy.deepcopy(self.scene); scene['result']['components'] = []
        self.record('after_read', scene, self.base_time+22)
        with self.assertRaisesRegex(ValueError, 'COMPLETE_NATIVE_READBACK'):
            self.validate()

    def test_metadata_only_and_changed_native_sources_fail(self):
        self.proof['persisted_sources'] = [self.sources[0]]
        with self.assertRaisesRegex(ValueError, 'PERSISTED_NATIVE_SOURCES_REQUIRED'):
            self.validate()
        self.proof['persisted_sources'] = self.sources
        (self.path.parent/'sch/P1.esch2').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            self.validate()

    def test_stale_or_corrupt_evidence_is_rejected(self):
        self.record('after_read', self.scene, self.base_time)
        with self.assertRaisesRegex(ValueError, 'POST_CLOSE_READ'):
            self.validate()
        self.record('after_read', self.scene, self.base_time+22)
        (self.folder/'after_read.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_HASH_MISMATCH'):
            self.validate()

    def test_only_derived_pin_label_layout_is_normalized(self):
        original = copy.deepcopy(self.scene)
        original['result']['pagePrimitives']['attributes'].append(
            {'primitiveId': 'renderer-old', 'ParentPrimitiveId': 'pin1', 'Key': 'Pin Number',
             'Value': '1', 'X': 2, 'Y': 3, 'AlignMode': 7})
        new = copy.deepcopy(original)
        new['result']['pagePrimitives']['attributes'][1].update(primitiveId='renderer-new', Y=5, AlignMode=9)
        self.record('before_read', original, self.base_time+1)
        self.record('after_read', new, self.base_time+22)
        self.record('after_read_again', new, self.base_time+23)
        self.validate()
        for kind in ('stored-position', 'derived-value', 'foreign-parent'):
            with self.subTest(kind=kind):
                wrong = copy.deepcopy(new)
                if kind == 'stored-position': wrong['result']['pagePrimitives']['attributes'][0]['X'] = 20
                elif kind == 'derived-value': wrong['result']['pagePrimitives']['attributes'][1]['Value'] = '2'
                else: wrong['result']['pagePrimitives']['attributes'][1]['ParentPrimitiveId'] = 'nonexistent-pin'
                self.record('after_read', wrong, self.base_time+22)
                with self.assertRaises(ValueError):
                    self.validate()

    def test_device_metadata_values_remain_exact(self):
        original = copy.deepcopy(self.scene)
        original['result']['components'][0]['primitiveId'] = 'R3'
        original['result']['pagePrimitives']['attributes'].append(
            {'primitiveId': 'metadata-old', 'ParentPrimitiveId': 'R3', 'Key': '3D Model', 'Value': 'model-A', 'X': None})
        new = copy.deepcopy(original)
        new['result']['pagePrimitives']['attributes'][1]['primitiveId'] = 'metadata-new'
        self.record('before_read', original, self.base_time+1)
        self.record('after_read', new, self.base_time+22)
        self.record('after_read_again', new, self.base_time+23)
        self.validate()
        new['result']['pagePrimitives']['attributes'][1]['Value'] = 'model-B'
        self.record('after_read', new, self.base_time+22)
        with self.assertRaisesRegex(ValueError, 'SCENE_MISMATCH'):
            self.validate()


if __name__ == '__main__':
    unittest.main()
