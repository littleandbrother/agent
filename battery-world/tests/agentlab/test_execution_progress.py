import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from bfworld.agentlab.execution_progress import paper_acceptance, slim_revisions, public_artifact


class PublicProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.owner='pi-original';self.paper='P01'
        self.scope={'owner':self.owner,'paper':self.paper,'scope':'scoped-digital',
                    'review_roots':['campaign/reviews/P01'],'required_gates':[{'id':'mission','label':'核心任务'}]}
        self.put('campaign/acceptance/P01/scope-v1.json',self.scope)
        self.put('runtime/participants/pi-original/source.c', 'source', raw=True)
        self.put('runtime/participants/pi-original/report.md', 'report', raw=True)
        report=self.put('sealed/native-report.json',{'assembly_revision':2,'assembly_physical_hash':'physical'})
        self.native={'owner':self.owner,'paper':self.paper,'artifacts':[report],
          'evaluation':{'status':'PASS','native_checks':[{'job_id':'eng-a','project_sha256':'project',
                'assembly_revision':1,'assembly_physical_hash':'previous-physical',
                'project_source_sha256':{'source.c':hashlib.sha256(b'source').hexdigest()}}]},
          'delivery_integrity':{'status':'PASS','verified_files':[{'path':'source.c','sha256':hashlib.sha256(b'source').hexdigest()},
           {'path':'report.md','sha256':hashlib.sha256(b'report').hexdigest()}]}}
        source=self.put('sealed/result.json',self.native)
        sealed=self.put('sealed/acceptance.json',{'papers':[{'owner':self.owner,'paper':self.paper,'source_result':source,'issues':[]}]})
        self.put('campaign/acceptance/current.json',sealed)
        self.assembly={'current':{'revision':2,'hashes':{'physical_hash':'physical'}}}

    def put(self,name,value,raw=False):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value if raw else json.dumps(value))
        return {'path':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

    def gate(self,status='PASS'):
        self.put('campaign/reviews/P01/digital-gates/mission.json',{
            'schema_version':'bf-paper-digital-gate-review-v1','owner':self.owner,'paper':self.paper,
            'actor':'independent-checker','gate_id':'mission','status':status,'created':2,
            'bindings':[{'job_id':'eng-a','project_sha256':'project'}]})

    def view(self):return paper_acceptance(self.root,self.owner,self.paper,self.assembly)

    def test_file_gate_is_not_full_acceptance(self):
        v=self.view();self.assertTrue(v['stage_delivery_passed']);self.assertFalse(v['full_product_passed']);self.assertEqual('NOT_CHECKED',v['functional_gates'][0]['status'])

    def test_exact_valid_review_and_current_report_allow_scoped_digital_only(self):
        self.gate();v=self.view();self.assertTrue(v['full_product_passed']);self.assertFalse(v['physical_verified'])
        # An exactly reused earlier job may legitimately predate the current
        # assembly; the frozen delivery report, not every job's old revision,
        # binds the selected same-version product.
        self.assertTrue(v['current_sources_valid'])

    def test_live_source_change_invalidates_old_green(self):
        self.gate();(self.root/'runtime/participants/pi-original/source.c').write_text('modified')
        v=self.view();self.assertEqual('STALE',v['functional_gates'][0]['status']);self.assertFalse(v['full_product_passed'])

    def test_live_delivery_text_change_does_not_erase_valid_local_function(self):
        self.gate();(self.root/'runtime/participants/pi-original/report.md').write_text('changed')
        v=self.view();self.assertEqual('STALE',v['file_integrity']);self.assertEqual('PASS',v['functional_gates'][0]['status']);self.assertFalse(v['full_product_passed'])

    def test_changed_assembly_blocks_full_current_acceptance(self):
        self.gate();self.assembly['current']['revision']=3
        self.assertFalse(self.view()['current_sources_valid'])

    def test_hash_drift_fails_closed(self):
        (self.root/'sealed/result.json').write_text('{}')
        with self.assertRaises(ValueError):self.view()

    def test_wrong_owner_scope_is_rejected(self):
        self.scope['owner']='foreign';self.put('campaign/acceptance/P01/scope-v1.json',self.scope)
        with self.assertRaisesRegex(ValueError,'OWNER_MISMATCH'):self.view()

    def test_revision_sequence_is_not_fabricated_parent_or_restore(self):
        rows=slim_revisions({'revisions':[{'revision':1,'payload':{}}], 'current':{'revision':2,'payload':{}}})
        self.assertIsNone(rows[1]['parent_id']);self.assertEqual('assembly-1',rows[1]['timeline_predecessor']);self.assertFalse(rows[1]['rollback_supported'])

    def test_artifact_endpoint_rejects_unlisted_and_other_owner(self):
        papers=SimpleNamespace(has=lambda o:o==self.owner,root=self.root)
        with patch('bfworld.agentlab.execution_progress.snapshot',return_value={'public_artifacts':[]}):
            with self.assertRaises(PermissionError):public_artifact(None,papers,self.owner,'../secret.json')
        with self.assertRaises(PermissionError):public_artifact(None,papers,'foreign','anything')


if __name__=='__main__':unittest.main()
