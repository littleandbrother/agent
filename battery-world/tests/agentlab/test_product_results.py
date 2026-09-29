import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
import zipfile
from bfworld.agentlab.server import Workbench
from bfworld.agentlab.solar_companion import definition, changed
from bfworld.agentlab.store import canonical, identity


class ProductResultsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'paid-window-closed.json').write_text('{}')
        self.app=Workbench(self.root/'state')
        self.owner=self.app.conversations.create('成果工作区测试',None,'results')['id']
        self.source=self.app.conversations.detail(self.owner)['messages'][0]['id']
        self.write(definition(),0,'initial')

    def tearDown(self):
        self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()

    def write(self,p,rev,op):
        return self.app.assemblies.write(self.owner,dict(source_message_id=self.source,operation_id=op,expected_revision=rev,payload=p))

    def job(self,kind='cadquery',outputs=None,status='SUCCEEDED',bound=True):
        key='eng-'+str(time.time_ns());root=self.app.engineering.root/key;root.mkdir(parents=True)
        artifacts=[]
        for name,content in (outputs or {'project-assembly.step':'fixture bytes, not native evidence','project-source.zip':'fixture'}).items():
            b=content.encode();(root/name).write_bytes(b);artifacts.append(dict(name=name,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b)))
        request=dict(engine='engineering-project',project={'manifest':{'kind':kind,'interfaces':{'units':'mm'}},'sources':{'src/main.py':'# immutable fixture'}},parameters={},scope='fixture',design_revision=None)
        if bound:request['assembly']=self.app.assemblies.get(self.owner)
        result=dict(kind=kind,artifacts=artifacts,readback_passed=True,independent_readback={'bounds_mm':[10,20,30]},scope='fixture, not hardware')
        with self.app.store.connect() as db:db.execute('INSERT INTO engineering_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,self.owner,key,identity(request),canonical(request),status,time.time(),None,None,canonical(result),None))
        return key

    def test_index_is_idempotent_and_rebuildable(self):
        key=self.job();a=self.app.results.inspect(self.owner);b=self.app.results.inspect(self.owner)
        self.assertEqual(a,b);self.assertEqual(2,len(a['files']))
        self.assertFalse(a['verdict']['passed'])
        with self.app.store.connect() as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM product_result_index').fetchone()[0]);db.execute('DELETE FROM product_result_index')
        self.assertEqual(a,self.app.results.inspect(self.owner))
        self.assertEqual(['src/main.py'],self.app.results.source(self.owner,key)['files'])

    def test_camera_reuses_cad_firmware_and_preserves_origin(self):
        self.job();self.job('firmware-stm32l031',{'project-firmware.elf':'fixture'})
        self.write(changed(definition(),camera=-35),1,'camera')
        a=self.app.results.inspect(self.owner)
        self.assertTrue(all(f['created_revision']==1 and f['applicability']['state']=='reused' for f in a['files']))
        self.write(changed(definition(),width=100),2,'width')
        a=self.app.results.inspect(self.owner)
        self.assertTrue(all(f['applicability']['state']=='stale' for f in a['files'] if f['domain']=='mechanical'))
        self.assertTrue(all(f['applicability']['state']=='reused' for f in a['files'] if f['domain']=='firmware'))

    def test_history_never_includes_future_result_as_current(self):
        self.job();self.write(changed(definition(),camera=-35),1,'camera');self.job()
        a=self.app.results.inspect(self.owner,1)
        self.assertEqual({'current','future'},{r['applicability']['state'] for r in a['results']})
        self.assertIsNone(a['verdict']);self.assertEqual([],a['blockers'])
        self.assertNotEqual(a['results'][0]['design_inputs']['presentation'],a['results'][1]['design_inputs']['presentation'])

    def test_unbound_not_promoted_and_tamper_rejected(self):
        key=self.job(bound=False);a=self.app.results.inspect(self.owner)
        self.assertEqual('unbound',a['files'][0]['applicability']['state'])
        p,_=self.app.results.file(self.owner,key+'/project-assembly.step');p.write_text('tampered')
        self.assertFalse(next(f for f in self.app.results.inspect(self.owner)['files'] if f['name']=='project-assembly.step')['integrity'])
        with self.assertRaisesRegex(ValueError,'INVALID'):self.app.results.file(self.owner,key+'/project-assembly.step')
        with self.assertRaisesRegex(ValueError,'INVALID'):self.app.deliverables.package(self.owner)

    def test_cross_owner_and_path_escape(self):
        key=self.job();other=self.app.conversations.create('其他任务',None,'other')['id']
        with self.assertRaises(PermissionError):self.app.results.file(other,key+'/project-assembly.step')
        with self.assertRaises(PermissionError):self.app.results.source(other,key,'src/main.py')
        with self.assertRaises(PermissionError):self.app.results.file(self.owner,key+'/../input.json')
        self.assertEqual([],self.app.results.inspect(other)['files'])

    def test_zip_exactly_matches_all_files_and_retains_failures(self):
        self.job();self.job('spice',{'project-trace.raw':'failed output'},status='FAILED')
        a=self.app.results.inspect(self.owner)
        with self.assertRaisesRegex(ValueError,'CHANGED'):self.app.deliverables.package(self.owner,'wrong')
        record=self.app.deliverables.package(self.owner,a['snapshot_sha256']);path,_=self.app.assemblies.file(self.owner,record['id'])
        with zipfile.ZipFile(path) as z:
            manifest=json.loads(z.read('成果清单.json'));self.assertEqual(a,manifest)
            expected={f['archive_path'] for f in a['files']};self.assertEqual(expected,{n for n in z.namelist() if n.startswith('成果/')})
            self.assertTrue(any('/failed/' in n for n in expected))
            for f in a['files']:self.assertEqual(f['sha256'],hashlib.sha256(z.read(f['archive_path'])).hexdigest())
        # Export does not recursively become another input to its own inventory.
        self.assertEqual(a,self.app.results.inspect(self.owner))
        self.assertEqual(record['id'],self.app.deliverables.package(self.owner,a['snapshot_sha256'])['id'])

    def test_real_numeric_series_and_nonfinite_rejection(self):
        raw='Title: fixture\nFlags: real\nNo. Variables: 2\nNo. Points: 3\nVariables:\n0 time time\n1 v(out) voltage\nValues:\n0 0\n0\n1 0.001\n0.5\n2 0.002\n1\n'
        key=self.job('spice',{'project-trace.raw':raw})
        s=self.app.results.series(self.owner,key+'/project-trace.raw')
        self.assertEqual(['s','V'],s['units']);self.assertEqual([[0,0],[.001,.5],[.002,1]],s['rows'])
        key=self.job('spice',{'channels.csv':'time_s,vout_v\n0,nan\n'})
        with self.assertRaisesRegex(ValueError,'NONFINITE'):self.app.results.series(self.owner,key+'/channels.csv')

    def test_blockers_distinguish_platform_gap(self):
        a=self.app.results.inspect(self.owner);self.assertTrue(all(b['state']=='missing_files' for b in a['blockers']))
        self.assertFalse(any(b['id']=='magnetics' for b in a['blockers']))

    def test_cached_zip_tamper_is_detected(self):
        self.job();catalog=self.app.results.inspect(self.owner);self.app.deliverables.package(self.owner)
        dest=next((self.app.store.root/'product-assemblies'/self.owner/'delivery-packages').glob('*.zip'))
        with zipfile.ZipFile(dest) as z:content={n:z.read(n) for n in z.namelist()}
        content[catalog['files'][0]['archive_path']]=b'edited after packaging'
        with zipfile.ZipFile(dest,'w') as z:
            for name,value in content.items():z.writestr(name,value)
        with self.assertRaisesRegex(ValueError,'ZIP_HASH_MISMATCH'):self.app.deliverables.package(self.owner)

    def test_http_owner_isolation_and_pdf_embedding_scope(self):
        from http.server import ThreadingHTTPServer
        import threading
        import urllib.request
        import urllib.error
        from bfworld.agentlab.server import handler
        key=self.job(outputs={'report.pdf':'pdf fixture bytes'})
        other=self.app.conversations.create('other',None,'http-other')['id'];token=self.app.store.issue(other)
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,auth):
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,headers={'Authorization':'Bearer '+auth})
            return urllib.request.urlopen(req,timeout=5)
        try:
            with request('/api/results?session='+self.owner,token) as r:
                a=json.load(r);self.assertEqual(other,a['owner']);self.assertEqual([],a['files'])
            for url in ['/api/results/file?session='+self.owner+'&id='+key+'/report.pdf','/api/results/source?session='+self.owner+'&result='+key+'&name=src/main.py']:
                with self.assertRaises(urllib.error.HTTPError) as caught:request(url,token)
                self.assertEqual(403,caught.exception.code)
            operator=(self.app.store.root/'operator.token').read_text().strip()
            with request('/api/results/file?session='+self.owner+'&id='+key+'/report.pdf',operator) as r:
                self.assertEqual('application/pdf',r.headers['Content-Type']);self.assertIn("frame-ancestors 'self'",r.headers['Content-Security-Policy'])
        finally:server.shutdown();server.server_close();thread.join(2)
