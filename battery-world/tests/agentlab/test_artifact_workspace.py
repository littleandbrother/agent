import hashlib
import json
import time
import unittest
from tests.agentlab import test_product_results as fixture
from bfworld.agentlab.store import canonical,identity
from bfworld.agentlab.studio_delivery import StudioDelivery


class ArtifactWorkspaceTest(unittest.TestCase):
    setUp=fixture.ProductResultsTest.setUp
    tearDown=fixture.ProductResultsTest.tearDown
    write=fixture.ProductResultsTest.write
    job=fixture.ProductResultsTest.job
    def native(self, owner=None):
        owner=owner or self.owner;key='eda-fixture'
        receipt=dict(owner=owner,job_id=key,status='SUCCEEDED',argv=['pcb','drc'],stdout=canonical({'result':{'passed':False,'violations':[{'name':'Connection','count':36}]}}))
        root=self.app.results.eda.root;root.mkdir(parents=True,exist_ok=True);(root/(key+'.json')).write_text(canonical(receipt))
        with self.app.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS eda_cli_jobs(id TEXT PRIMARY KEY,owner TEXT,operation TEXT,request TEXT,status TEXT,result TEXT,created REAL,ended REAL)')
            db.execute('INSERT INTO eda_cli_jobs VALUES(?,?,?,?,?,?,?,?)',(key,owner,key,canonical({'argv':['pcb','drc'],'project':'p'}),'SUCCEEDED',canonical({'receipt_sha256':identity(receipt)}),time.time(),time.time()))
        return key

    def test_latest_includes_actual_unbound_firmware_and_latest_failure(self):
        old=self.job('firmware-nrf52832',{'project-firmware.hex':'old'},bound=False)
        new=self.job('firmware-nrf52832',{'project-firmware.hex':'new'},bound=False)
        failed=self.job('firmware-nrf52832',{'failure.log':'failure'},status='FAILED',bound=False)
        c=self.app.results.inspect(self.owner)
        self.assertNotIn(old,c['latest_result_ids']);self.assertIn(new,c['latest_result_ids']);self.assertIn(failed,c['latest_result_ids'])
        self.assertTrue(all(f['domain']=='firmware' for f in c['files']))
        d=StudioDelivery(self.app.results).inspect(self.owner,'latest')
        self.assertEqual(set(c['latest_file_ids']),{f['id'] for f in d['files']});self.assertIsNone(d['verdict'])
        self.assertFalse(StudioDelivery(self.app.results).inspect(self.owner,'assembly')['files'])

    def test_native_receipt_failure_identity_and_tamper(self):
        key=self.native();c=self.app.results.inspect(self.owner);r=next(r for r in c['results'] if r['id']==key)
        self.assertEqual('SUCCEEDED',r['status']);self.assertEqual('FAIL',r['design_status']);self.assertFalse(r['checks']['native_check_passed'])
        self.assertEqual(['pcb'],r['files'][0]['sections']);self.assertFalse(r['hardware_verified'])
        f=r['files'][0];p,_=self.app.results.file(self.owner,f['id']);self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),f['sha256'])
        other=self.app.conversations.create('other',None,'other')['id']
        with self.assertRaises(PermissionError):self.app.results.file(other,f['id'])
        p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'INVALID'):self.app.results.file(self.owner,f['id'])
        changed=self.app.results.inspect(self.owner);self.assertNotEqual(c['snapshot_sha256'],changed['snapshot_sha256'])
        self.assertIsNone(next(r for r in changed['results'] if r['id']==key)['design_status'])

    def test_version_ignores_projection_writes_but_observes_jobs_and_owner(self):
        before=self.app.results.version(self.owner);self.app.results.inspect(self.owner)
        self.assertEqual(before,self.app.results.version(self.owner))
        other=self.app.conversations.create('other',None,'other')['id'];unchanged=self.app.results.version(other)
        self.job();after=self.app.results.version(self.owner)
        self.assertNotEqual(before,after);self.assertEqual(unchanged,self.app.results.version(other))
        self.native();self.assertNotEqual(after,self.app.results.version(self.owner))

    def test_native_export_is_explicit_owner_scoped_and_not_creation_hash_attested(self):
        key=self.native();exports=self.app.store.root.parent/'participants'/self.owner/'.easyeda/artifacts'
        exports.mkdir(parents=True);native=exports/'schematic.enet';native.write_text('native fixture')
        receipt_file=self.app.results.eda.root/(key+'.json');receipt=json.loads(receipt_file.read_text())
        receipt['stdout']=canonical({'result':{'artifactPath':str(native)}})
        receipt_file.write_text(canonical(receipt))
        with self.app.store.connect() as db:db.execute('UPDATE eda_cli_jobs SET result=? WHERE id=?',(canonical({'receipt_sha256':identity(receipt)}),key))
        c=self.app.results.inspect(self.owner);f=next(f for f in c['files'] if f['name']=='schematic.enet')
        self.assertEqual('receipt_path_and_current_file_sha256',f['integrity_basis'])
        self.assertEqual(native,self.app.results.file(self.owner,f['id'])[0])
        other=exports.parent.parent.parent/'other/.easyeda/artifacts';other.mkdir(parents=True);foreign=other/'secret.enet';foreign.write_text('foreign')
        self.assertEqual({},self.app.results.eda.exports(self.owner,{'stdout':canonical({'result':{'artifactPath':str(foreign)}})}))
        link=exports/'escape.enet';link.symlink_to(foreign)
        self.assertEqual({},self.app.results.eda.exports(self.owner,{'stdout':canonical({'result':{'artifactPath':str(link)}})}))
