import json
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from bfworld.agentlab import recursive, study
from bfworld.agentlab.launcher import seatbelt, NODE


class RecursiveBoundaryTests(unittest.TestCase):
    def test_immutable_source_module_rejects_os_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'harness').mkdir()
            for name in ['solver.ts','improver.ts']:(root/'harness'/name).write_text('original')
            code="const f=require('fs');let denied=false;try{f.writeFileSync('harness/solver.ts','bad')}catch(e){denied=e.code==='EPERM'||e.code==='EACCES'};f.writeFileSync('harness/improver.ts','allowed');if(!denied)process.exit(1)"
            proc=subprocess.run(['/usr/bin/sandbox-exec','-p',seatbelt(root,root,mutable=('improver.ts',)),NODE,'-e',code],cwd=root,capture_output=True,text=True,timeout=5)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual((root/'harness/solver.ts').read_text(),'original')
            self.assertEqual((root/'harness/improver.ts').read_text(),'allowed')

    def test_comparison_does_not_hide_missing_pairs(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(study, 'ROOT', Path(tmp)):
            harness = {k: 'frozen' for k in ['app_build_hash', 'pi_lock_hash', 'tools', 'thinking', 'session_caps', 'resource_hashes']}
            protocol = {'tasks': ['dev-01', 'dev-02'], 'repetitions': 2,
                        'task_bindings': {'dev-01': 'a', 'dev-02': 'b'}, 'world_binding': 'fixed', 'harness': harness}
            row = {'owner': 'pi-study-a-dev-01-r1', 'task_id': 'dev-01', 'outcome': 'PASS', 'cost_upper_bound_usd': .02}
            for arm in ['a', 'b']:
                study.save(Path(tmp) / (arm + '-protocol.json'), protocol)
                study.save(Path(tmp) / (arm + '-results.json'), [row])
            result = study.compare('a', 'b')
            self.assertFalse(result['complete_pairs'])
            self.assertEqual(len(result['pairs']), 4)
            protocol['task_bindings']['dev-01'] = 'changed'
            study.save(Path(tmp) / 'b-protocol.json', protocol)
            with self.assertRaisesRegex(ValueError, 'PROTOCOL_MISMATCH'):
                study.compare('a', 'b')

    def test_frozen_data_and_common_boundary_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.json'
            recursive.immutable(path, {'history': 'public-dev'})
            with self.assertRaisesRegex(ValueError, 'DRIFT'):
                recursive.immutable(path, {'history': 'transfer-feedback'})
        keys = ['world_binding', 'app_build_hash', 'pi_lock_hash', 'tools', 'thinking', 'session_caps', 'resource_hashes', 'model']
        baseline = dict.fromkeys(keys, 'same')
        for key in keys:
            with self.assertRaisesRegex(ValueError, 'BOUNDARY_MISMATCH'):
                recursive.compatible(baseline, {**baseline, key: 'changed'})

    def test_activation_checks_real_loaded_module_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(recursive, 'HOME_ROOT', Path(tmp)):
            out = Path(tmp) / 'sessions' / 'pi-test'
            out.mkdir(parents=True)
            event = {'type': 'harness_loaded', 'pid': 42, 'loaded': {'solver': 's', 'improver': 'u'}}
            (out / 'trace.jsonl').write_text(json.dumps(event) + '\n')
            receipt = {'owner': 'pi-test', 'harness': {'loaded_modules': event['loaded']}}
            self.assertEqual(recursive.verify_activation(receipt)['pid'], 42)
            (out / 'trace.jsonl').write_text(json.dumps(event)+'\n'+json.dumps({**event,'pid':43})+'\n')
            receipt['previous_attempts']=[{'status':'FAILED'}]
            self.assertEqual(recursive.verify_activation(receipt)['pids'],[42,43])
            receipt['harness']['loaded_modules'] = {'solver': 'stale', 'improver': 'u'}
            with self.assertRaisesRegex(ValueError, 'ACTIVATION_MISMATCH'):
                recursive.verify_activation(receipt)
