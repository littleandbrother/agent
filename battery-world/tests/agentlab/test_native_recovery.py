import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.recover_native_job import completed_result, digest


class NativeRecovery(unittest.TestCase):
    def test_recovery_requires_original_input_terminal_result_and_readable_archive(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            (p/'input.json').write_text(json.dumps({'template_sha256':'executor', 'parameters':{'candidate':{'design_id':'candidate'}}}))
            expected = {'input_sha256':digest(p/'input.json')}
            result = {'design_id':'candidate','executor_sha256':'executor','source_stable':True,'run_status':'completed'}
            (p/'system-manifest.json').write_text(json.dumps({'executor_sha256':'executor','design_id':'candidate'}))
            (p/'result.json').write_text(json.dumps(result))
            (p/'process.log').write_text('Started\n'+json.dumps(result)+'\n')
            with zipfile.ZipFile(p/'engineering-evidence.zip','w') as z:z.writestr('result.json',json.dumps(result))
            self.assertEqual(result,completed_result(p,expected))
            (p/'process.log').write_text('Started, still packaging\n')
            with self.assertRaises((ValueError,KeyError)):completed_result(p,expected)
            (p/'process.log').write_text(json.dumps(result)+'\n')
            (p/'input.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'INPUT_CHANGED'):completed_result(p,expected)

    def test_unqualified_or_foreign_result_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            (p/'input.json').write_text(json.dumps({'template_sha256':'e', 'parameters':{'candidate':{'design_id':'d'}}}))
            for result, error in [({'design_id':'other','executor_sha256':'e','source_stable':True},'DESIGN_MISMATCH'),
                                  ({'design_id':'d','executor_sha256':'other','source_stable':True},'EXECUTOR_MISMATCH'),
                                  ({'design_id':'d','executor_sha256':'e','source_stable':False},'SOURCE_NOT_STABLE')]:
                (p/'system-manifest.json').write_text(json.dumps({'executor_sha256':result['executor_sha256'],'design_id':result['design_id']}))
                (p/'result.json').write_text(json.dumps(result));(p/'process.log').write_text(json.dumps(result)+'\n')
                with self.assertRaisesRegex(ValueError,error):completed_result(p,{'input_sha256':digest(p/'input.json')})
