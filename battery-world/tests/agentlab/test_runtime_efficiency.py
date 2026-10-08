import gzip
import hashlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from bfworld.agentlab.audit_checkpoint import (
    Checkpoints, archive_matches, atomic_json, inspect_archive)


class CheckpointTests(unittest.TestCase):
    def test_hardlinks_share_read_but_wrong_binding_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); a = root/'a.gz'; b = root/'b.gz'
            payload = b'bounded raw sample'*10000
            a.write_bytes(gzip.compress(payload)); os.link(a, b)
            cp = Checkpoints(root/'cache', 'checker-v1'); calls = []
            def check(p):
                def inspect():
                    calls.append(p); return inspect_archive(p)
                return cp.run('readback', [p], inspect)
            with ThreadPoolExecutor(2) as pool:
                values = list(pool.map(check, (a, b)))
            self.assertEqual(len(calls), 1)
            binding = {**values[0], 'readback_verified': True}
            self.assertTrue(archive_matches(values[1], binding))
            self.assertFalse(archive_matches(values[1], {**binding, 'original_sha256': 'wrong'}))
            self.assertEqual(values[0]['original_sha256'], hashlib.sha256(payload).hexdigest())
            self.assertEqual(values[0]['archive_sha256'], hashlib.sha256(a.read_bytes()).hexdigest())

    def test_changed_input_checker_and_context_invalidate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'input'; p.write_text('a')
            cp=Checkpoints(root/'cache','v1');calls=[]
            def op(): calls.append(1); return p.read_text()
            self.assertEqual(cp.run('x',[p],op),'a')
            cp.run('x',[p],op); self.assertEqual(len(calls),1)
            p.write_text('b'); self.assertEqual(cp.run('x',[p],op),'b')
            Checkpoints(root/'cache','v2').run('x',[p],op)
            cp.run('x',[p],op,context='new-rule')
            self.assertEqual(len(calls),4)

    def test_output_error_does_not_repeat_expensive_check(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'input';p.write_text('stable')
            cp=Checkpoints(root/'cache','v1');calls=[]
            def operation():calls.append(1);return {'passed':False}
            result=cp.run('x',[p],operation)
            with self.assertRaises(TypeError):atomic_json(root/'report.json',{'bad':object()})
            self.assertFalse((root/'report.json').exists())
            result=Checkpoints(root/'cache','v1').run('x',[p],operation)
            atomic_json(root/'report.json',result)
            self.assertEqual(len(calls),1)
            self.assertIs(json.loads((root/'report.json').read_text())['passed'],False)

    def test_failed_or_partial_check_is_never_cached(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'bad.gz';p.write_bytes(b'not gzip')
            cp=Checkpoints(root/'cache','v1')
            for _ in range(2):
                with self.assertRaises(gzip.BadGzipFile):
                    cp.run('read',[p],lambda:inspect_archive(p))
            self.assertEqual(cp.hits,0)
            self.assertEqual(list((root/'cache').glob('*.json')),[])

    def test_input_mutation_during_check_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'input';p.write_text('before')
            def mutate():p.write_text('after');return True
            with self.assertRaisesRegex(ValueError,'CHANGED_DURING'):
                Checkpoints(root/'cache','v1').run('x',[p],mutate)

    def test_whole_audit_resume_invalidates_external_dependency(self):
        from scripts.door_case import audit_selfpower as a
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); dep=root/'model.lib';dep.write_text('model-v1')
            runs=[root/'primary',root/'repeat']
            for p in runs:
                p.mkdir();(p/'system-manifest.json').write_text(json.dumps(
                    {'source_dependencies':{str(dep):'expected'}}))
            calls=[]
            def fake_run(path, checkpoints):
                calls.append(path)
                return {'path':str(path),'result_sha256':'fixture','design_id':'same',
                        'executor_sha256':'same','passed':True,
                        'metrics':dict(peak_tip_mm=1,peak_piezo_V=1,peak_storage_V=1,
                                       peak_supply_V=1,tx_completed=1,received_events=1),
                        'native_execution':{'passed':True,'launches':[{'started_local':path.name}]}}
            with patch.object(a,'audit_run',side_effect=fake_run):
                a.audit(*runs,root/'first.json')
                a.audit(*runs,root/'second.json')
                self.assertEqual(len(calls),2)
                dep.write_text('model-v2')
                a.audit(*runs,root/'changed.json')
                self.assertEqual(len(calls),4)


class LocalRuntimeTests(unittest.TestCase):
    def test_default_runtime_is_resident_and_env_override_wins(self):
        from bfworld.agentlab import runtime_config as c
        self.assertNotIn('/Documents/',str(c.RUNTIME_ROOT))
        with patch.dict(os.environ, {'BF_CAD_PYTHON':'/tmp/isolated-python'}):
            self.assertEqual(c.configured('CAD_PYTHON','/invalid'),Path('/tmp/isolated-python'))

    def test_scientific_executor_not_changed_by_runtime_maintenance(self):
        from bfworld.agentlab.door_selfpower.contracts import template_hash
        self.assertEqual(template_hash(), 'e2f4b26558cdea18f6017ef93dce00fa63ea58e82c33449399ec6baaa4bf4d5d')


if __name__ == '__main__':
    unittest.main()
