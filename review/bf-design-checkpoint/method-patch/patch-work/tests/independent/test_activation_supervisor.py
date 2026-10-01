"""Cross-language readback of actual pure Node import/entrypoint evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('independent_supervisor_contract',ROOT/'changed/src/method_contract.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ActivationSupervisorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run=subprocess.run(['node','--experimental-strip-types',str(HERE/'activation.fixture.mjs'),'bf_design'],capture_output=True,text=True,check=True)
        cls.record=json.loads(run.stdout)
        (HERE/'activation-supervisor-fixture.json').write_text(json.dumps(cls.record,ensure_ascii=False,indent=2)+'\n')
    def verify(self,value=None,**extra):
        r=copy.deepcopy(value or self.record)
        expected={k:r['expected'][k] for k in ['pid','author_pid','nonce','packet_id','exit_code']};expected.update(extra)
        return module.verify_activation(r['events'],r['binding'],**expected)
    def test_real_import_and_invocation_verify_across_languages(self):
        result=self.verify();self.assertTrue(result['post_import']);self.assertTrue(result['invoked']);self.assertFalse(result['execution_authorized']);self.assertFalse(result['scientific_success'])
    def test_import_only_and_reversed_order_do_not_verify(self):
        for events in [self.record['events'][:1],list(reversed(self.record['events']))]:
            r=copy.deepcopy(self.record);r['events']=events
            with self.assertRaises(ValueError):self.verify(r)
    def test_modified_prompt_fails(self):
        r=copy.deepcopy(self.record);r['events'][1]['output']+='Forged conclusion'
        with self.assertRaisesRegex(ValueError,'METHOD_ACTIVATION_OUTPUT_TAMPER'):self.verify(r)
    def test_foreign_nonce_packet_pid_fail(self):
        for field in ['nonce','packet_id','pid']:
            r=copy.deepcopy(self.record);r['events'][1][field]='foreign'
            with self.subTest(field=field), self.assertRaises(ValueError):self.verify(r)
    def test_invalid_process_identity_fails(self):
        for field,value in [('pid',0),('nonce',''),('packet_id','not-a-hash'),('exit_code',1),('author_pid',self.record['expected']['pid'])]:
            r=copy.deepcopy(self.record);r['expected'][field]=value
            if field in ['pid','nonce','packet_id']:
                for row in r['events']:row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.verify(r)
    def test_valid_supervisor_pid_is_required(self):
        for author_pid in [None,0,-1,'123']:
            with self.subTest(author_pid=author_pid),self.assertRaises(ValueError):self.verify(author_pid=author_pid)

if __name__=='__main__':unittest.main()
