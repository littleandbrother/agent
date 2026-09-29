import hashlib,json,unittest
from tests.agentlab import test_product_results as fixtures

class EngineeringCasesTest(unittest.TestCase):
    setUp=fixtures.ProductResultsTest.setUp
    tearDown=fixtures.ProductResultsTest.tearDown
    write=fixtures.ProductResultsTest.write

    def manifest(self):
        self.base=self.root/'case';self.base.mkdir(exist_ok=True)
        (self.base/'motion.mp4').write_bytes(b'fixture-not-real-video')
        return dict(schema_version='bf-engineering-case-v1',id='fixture',version='D2',authority='operator-assisted',hardware_verified=False,autonomous_agent_verified=False,design_sha256='a'*64,groups=[dict(id='animation',domain='mechanical',title='fixture animation',kind='blender',scope='fixture only',files=[dict(path='motion.mp4',sha256=hashlib.sha256((self.base/'motion.mp4').read_bytes()).hexdigest())])])

    def test_owner_isolation_and_immutable_source_snapshot(self):
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m)
        self.app.results.cases.publish(self.owner,self.base,m)
        a=self.app.results.inspect(self.owner);f=next(f for f in a['files'] if f['id'].startswith('case/'))
        self.assertEqual('case',f['applicability']['state']);self.assertEqual(['D2'],a['engineering_cases']);self.assertFalse(a['verdict']['passed'])
        r=next(r for r in a['results'] if r['source_type']=='engineering-case');self.assertEqual('video',r['presentations'][0]['kind']);self.assertFalse(r['autonomous_agent_verified'])
        (self.base/'motion.mp4').write_bytes(b'mutated original')
        path,_=self.app.results.file(self.owner,f['id']);self.assertEqual(b'fixture-not-real-video',path.read_bytes())
        other=self.app.conversations.create('other',None,'case-other')['id']
        with self.assertRaises(PermissionError):self.app.results.file(other,f['id'])
        path.write_bytes(b'mutated snapshot')
        with self.assertRaises(ValueError):self.app.results.file(self.owner,f['id'])

    def test_hash_path_claim_and_version_fail_closed(self):
        m=self.manifest();m['groups'][0]['files'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'HASH'):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.manifest();m['groups'][0]['files'][0]['path']='../secret'
        with self.assertRaises(PermissionError):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.manifest();m['autonomous_agent_verified']=True
        with self.assertRaisesRegex(ValueError,'CLAIM'):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m);m['groups'][0]['title']='silently changed'
        with self.assertRaisesRegex(ValueError,'IMMUTABLE'):self.app.results.cases.publish(self.owner,self.base,m)
