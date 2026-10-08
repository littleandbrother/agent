"""All session generations share a results catalog; fixtures are not engineering evidence."""
import hashlib
import json
import time
import unittest
import zipfile
from bfworld.agentlab.store import canonical,identity
from tests.agentlab import test_product_results as fixtures


class SystemResultsTest(unittest.TestCase):
    setUp=fixtures.ProductResultsTest.setUp
    tearDown=fixtures.ProductResultsTest.tearDown
    write=fixtures.ProductResultsTest.write
    job=fixtures.ProductResultsTest.job
    # Reuse fixture constructors, without re-running inherited test cases.
    def legacy(self,op='legacy',raw=None):
        owner=self.app.conversations.create('renamed magnetic task', 'dev-01',op)['id']
        raw=raw or dict(design_status='PASS',design={'capacitance_f':.001,'clamp_v':3.45},policy='def decide(obs): return {}',
            channels=[{'time_s':0,'storage_voltage_v':2.4},{'time_s':1,'storage_voltage_v':3.45}],
            summary={'maximum_storage_v':3.45},checks={'electrical_safe':True},fidelity='F1 fixture',description='fixture simulation, no hardware',artifacts=['public-result.json'],run_id='fixture')
        key='job-'+op
        with self.app.store.connect() as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,owner,op,identity({}),canonical({'task_id':'dev-01'}),'SUCCEEDED',time.time(),time.time(),canonical(raw),None,0))
        return owner,key

    def test_legacy_results_are_visible_without_creating_product(self):
        owner,key=self.legacy();a=self.app.results.inspect(owner)
        self.assertFalse(self.app.products.exists(owner));self.assertEqual('benchmark',a['phase']);self.assertIsNone(a['verdict'])
        self.assertEqual(4,len(a['files']));self.assertEqual('PASS',a['results'][0]['design_status'])
        self.assertTrue(all(f['applicability']['state']=='unbound' for f in a['files']))
        self.assertFalse(a['results'][0]['hardware_verified'])
        series=next(f for f in a['files'] if f['role']=='data')
        self.assertEqual([[0,2.4],[1,3.45]],self.app.results.series(owner,series['id'])['rows'])
        self.assertEqual(a,self.app.results.inspect(owner))

    def test_legacy_export_exact_inventory_and_cross_owner(self):
        owner,key=self.legacy();a=self.app.results.inspect(owner);r=self.app.results.package(owner,a['snapshot_sha256'])
        path=self.app.results.archive(owner,r['snapshot_sha256'])
        with zipfile.ZipFile(path) as z:
            self.assertEqual(a,json.loads(z.read('成果清单.json')))
            for f in a['files']:self.assertEqual(f['sha256'],hashlib.sha256(z.read(f['archive_path'])).hexdigest())
        with self.assertRaises(PermissionError):self.app.results.file(self.owner,a['files'][0]['id'])
        with self.assertRaises(PermissionError):self.app.results.archive(self.owner,r['snapshot_sha256'])
        with self.assertRaises(ValueError):self.app.results.package(owner,'0'*64)
        with self.assertRaises(PermissionError):self.app.results.file(owner,'record/../../operator.token')

    def test_proposal_only_and_withdrawn_not_empty_or_promoted(self):
        owner=self.app.conversations.create('new idea',None,'proposal')['id'];mid=self.app.conversations.detail(owner)['messages'][0]['id']
        p={k:k for k in ['title','purpose','form','service','installation','energy']};p.update(assumptions=['assumed'],acceptance=['measure'],limits=['no hardware'])
        self.app.products.write(owner,{'source_message_id':mid,'operation_id':'p','kind':'proposal','payload':p})
        a=self.app.results.inspect(owner);self.assertEqual('proposal',a['phase']);self.assertIsNone(a['verdict']);self.assertEqual('proposal',a['results'][0]['applicability']['state'])
        self.assertEqual('proposal',a['results'][0]['presentations'][0]['kind'])
        with self.app.store.connect() as db:db.execute("UPDATE chat_messages SET status='WITHDRAWN' WHERE id=?",(mid,))
        self.assertEqual('stale',self.app.results.inspect(owner)['results'][0]['applicability']['state'])

    def test_independent_engineering_and_typed_presentations(self):
        # A result without an assembly snapshot remains discoverable with any filename.
        key=self.job('comsol',{'solver-table.csv':'mesh,displacement_m\ncoarse,0.001\nfine,0.002\n','custom-view.svg':'<svg/>','arbitrary.glb':'fixture'},bound=False)
        a=self.app.results.inspect(self.owner);r=next(r for r in a['results'] if r['id']==key)
        self.assertEqual({'series','image','model'},{p['kind'] for p in r['presentations']})
        self.assertEqual('unbound',r['applicability']['state'])
        table=self.app.results.series(self.owner,key+'/solver-table.csv');self.assertTrue(table['table']);self.assertEqual(['fine','0.002'],table['rows'][1])
        # Mixed engineering/BOM tables preserve source spelling, including numeric-looking part identifiers.

    def test_empty_deleted_and_unknown(self):
        owner=self.app.conversations.create('connection only',None,'empty')['id']
        a=self.app.results.inspect(owner);self.assertEqual('empty',a['phase']);self.assertEqual([],a['files']);self.assertIsNone(a['verdict'])
        with self.assertRaises(PermissionError):self.app.results.inspect('missing-owner')
        with self.app.store.connect() as db:db.execute('INSERT INTO sidebar_entries VALUES(?,?,NULL,1,?)',(owner,'deleted',time.time()))
        with self.assertRaises(PermissionError):self.app.results.inspect(owner)

    def test_materialized_record_tamper_and_no_private_data(self):
        owner,key=self.legacy();a=self.app.results.inspect(owner);f=a['files'][0]
        p,_=self.app.results.file(owner,f['id']);p.write_bytes(b'tampered')
        self.assertFalse(self.app.results.inspect(owner)['files'][0]['integrity'])
        with self.assertRaises(ValueError):self.app.results.file(owner,f['id'])
        with self.assertRaises(PermissionError):self.app.results.file(owner,'record/'+key+'/run.private.json')
        with self.assertRaises(ValueError):self.app.results.package(owner,self.app.results.inspect(owner)['snapshot_sha256'])

    def test_all_session_types_index_counts(self):
        old,_=self.legacy();new=self.app.conversations.create('new product',None,'new-empty')['id'];self.job(bound=False)
        for owner,phase,count in [(old,'benchmark',4),(new,'empty',0),(self.owner,'assembly',2)]:
            a=self.app.results.inspect(owner);self.assertEqual(phase,a['phase']);self.assertEqual(count,sum(d['files'] for d in a['coverage']))

# unittest discovers base TestCase imports as well; use only this class here.
