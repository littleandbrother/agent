import json
from pathlib import Path
import tempfile
import unittest
from bfworld.agentlab.design_lab import native_witness as w
from bfworld.agentlab.design_lab.contracts import sha,sealed
from bfworld.agentlab.store import identity


class NativeWitnessControls(unittest.TestCase):
    def fixture(self,root):
        folder=root/'changed-TX-6ms';folder.mkdir()
        trace=folder/'program.csv';trace.write_text('immutable fixture observation\n')
        raw=folder/'fixture.raw.xz';raw.write_bytes(b'fixture archive, not native physics')
        execution={'power_fixed_point':True,'native_checks':{'time_step':True},
                   'observations':{'program.csv':sha(trace)},
                   'native_dependencies':[{'path':str(raw),'sha256':sha(raw),'readback_verified':True}]}
        execution['execution_id']='X-'+identity(execution)
        sealed(folder/'execution.json',execution)
        sealed(root/'qualification.json',{'passed':True,'new_native_solver_calls':2})
        return {'producer_root':str(root),'producer_files':{
            'qualification.json':sha(root/'qualification.json'),
            'changed-TX-6ms/execution.json':sha(folder/'execution.json')}}

    def test_actual_all_observations_and_archives_are_checked(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cert=self.fixture(root)
            folder,value=w.original(cert)
            self.assertEqual(root/'changed-TX-6ms',folder)
            self.assertTrue(value['power_fixed_point'])

    def test_changed_native_observation_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cert=self.fixture(root)
            (root/'changed-TX-6ms/program.csv').write_text('changed')
            with self.assertRaisesRegex(ValueError,'ARTIFACT_DRIFT'):w.original(cert)

    def test_changed_native_archive_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cert=self.fixture(root)
            (root/'changed-TX-6ms/fixture.raw.xz').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'RAW_DRIFT'):w.original(cert)

    def test_zero_original_native_calls_do_not_qualify_changed_load(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cert=self.fixture(root)
            (root/'qualification.json').write_text(json.dumps({'passed':True,'new_native_solver_calls':0}))
            cert['producer_files']['qualification.json']=sha(root/'qualification.json')
            with self.assertRaisesRegex(ValueError,'NOT_QUALIFIED'):w.original(cert)

    def test_failed_native_gate_cannot_be_relabelled_success(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cert=self.fixture(root);p=root/'changed-TX-6ms/execution.json'
            value=json.loads(p.read_text());value['native_checks']['time_step']=False
            value.pop('execution_id');value['execution_id']='X-'+identity(value)
            p.write_text(json.dumps(value));cert['producer_files']['changed-TX-6ms/execution.json']=sha(p)
            with self.assertRaisesRegex(ValueError,'EXECUTION_INVALID'):w.original(cert)

    def test_path_escape_and_symlink_refuse(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'real';p.write_text('data');link=root/'alias';link.symlink_to(p)
            for name in ('../real','/real','alias'):
                with self.subTest(name=name),self.assertRaises(ValueError):w.bound(root,name,sha(p))

    def test_missing_duplicate_archive_pointer_still_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'raw';p.write_text('actual bytes')
            items=[{'path':str(x),'sha256':sha(p),'readback_verified':True}for x in (p,root/'missing')]
            with self.assertRaisesRegex(ValueError,'PROVENANCE'):w.verify_archives(items)

    def test_same_claimed_digest_does_not_hide_second_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);good=root/'good';bad=root/'bad'
            good.write_bytes(b'original native bytes');bad.write_bytes(b'different bytes')
            items=[{'path':str(p),'sha256':sha(good),'readback_verified':True} for p in (good,bad)]
            with self.assertRaisesRegex(ValueError,'RAW_DRIFT'):w.verify_archives(items)

    def test_model_and_clock_changes_invalidate_cache(self):
        env={'native_model':{'rom':{'sha256':'rom'},'force':{'sha256':'force'},
                             'force_domain':{'sha256':'domain'},'source_dependencies':{'vendor':'v1'}}}
        self.assertNotEqual(w.model_identity(env,{'clock':100}),w.model_identity(env,{'clock':50}))
        old=w.model_identity(env,{'clock':100});env['native_model']['force']['sha256']='other'
        self.assertNotEqual(old,w.model_identity(env,{'clock':100}))

    def test_missing_producer_code_cannot_authorize_native_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'certificate.json'
            sealed(p,{'producer_kernel':{'path':str(root/'missing.py'),'sha256':'missing'}})
            with self.assertRaisesRegex(ValueError,'PRODUCER_KERNEL_DRIFT'):
                w.reuse({'path':str(p),'sha256':sha(p)},None,None,None,root,None,None)

    def test_frozen_legacy_and_native_skill_bundles_are_separate(self):
        from bfworld.agentlab.design_lab.resources import bundle
        old,old_files=bundle();new,new_files=bundle(native=True)
        self.assertEqual(2,len(old['skills']));self.assertEqual(3,len(new['skills']))
        self.assertEqual('1.0.0',old['plugins'][0]['version'])
        self.assertEqual('1.1.0',new['plugins'][0]['version'])
        for name,data in old_files.items():self.assertEqual(data,new_files[name])


if __name__=='__main__':unittest.main()
