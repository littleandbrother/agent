"""Recovery preserves registration and never replaces an Agent result."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from run_organization_pilot import preflight_failure, read_trial_final


class PilotReceiptTests(unittest.TestCase):
    def setUp(self):
        self.value={'entry':{'owner':'same-owner','key':'same-trial'},
            'metrics':{'model_calls':0,'actual_design_changes':0,
                       'candidate_evaluations':0,'workers':[]},
            'state':{'status':'FAILED','error':"CalledProcessError: ['git', 'rev-parse', 'HEAD']"}}

    def test_only_zero_call_preflight_can_recover(self):
        self.assertTrue(preflight_failure(self.value))
        for field,value in [('model_calls',1),('actual_design_changes',1),
                            ('candidate_evaluations',1),('workers',['worker'])]:
            altered=copy.deepcopy(self.value);altered['metrics'][field]=value
            with self.subTest(field=field):self.assertFalse(preflight_failure(altered))

    def test_design_and_provider_errors_are_not_preflight(self):
        for error in ('MODEL_REQUEST_FAILED','TASK_EXECUTION_UNKNOWN_RECONCILE_REQUIRED','bad design'):
            value=copy.deepcopy(self.value);value['state']['error']=error
            self.assertFalse(preflight_failure(value))
        self.value['state']['error']='ERR_INVALID_PACKAGE_CONFIG /node_modules/package.json'
        self.assertTrue(preflight_failure(self.value))

    def test_original_receipt_is_kept_and_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);path=folder/'final.json'
            path.write_text(json.dumps(self.value));raw=path.read_bytes()
            self.assertEqual(self.value,read_trial_final(folder))
            final=copy.deepcopy(self.value);final['metrics']['model_calls']=7
            final['preflight_recovery']={'original_final_sha256':hashlib.sha256(raw).hexdigest()}
            (folder/'recovery-final.json').write_text(json.dumps(final))
            self.assertEqual(final,read_trial_final(folder));self.assertEqual(raw,path.read_bytes())
            final['entry']['owner']='new-owner'
            (folder/'recovery-final.json').write_text(json.dumps(final))
            with self.assertRaisesRegex(ValueError,'REGISTRATION_CHANGED'):read_trial_final(folder)

    def test_paid_trial_and_changed_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);path=folder/'final.json'
            path.write_text(json.dumps(self.value))
            final=copy.deepcopy(self.value)
            final['preflight_recovery']={'original_final_sha256':'0'*64}
            (folder/'recovery-final.json').write_text(json.dumps(final))
            with self.assertRaisesRegex(ValueError,'REGISTRATION_CHANGED'):read_trial_final(folder)
            self.value['metrics']['model_calls']=1
            path.write_text(json.dumps(self.value))
            with self.assertRaisesRegex(ValueError,'ZERO_CALL'):read_trial_final(folder)


if __name__=='__main__':unittest.main()
