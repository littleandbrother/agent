import hashlib
import json
import unittest
import zipfile
from bfworld.agentlab.studio_delivery import StudioDelivery
from tests.agentlab import test_engineering_cases as fixtures


class StudioDeliveryTest(unittest.TestCase):
    setUp = fixtures.EngineeringCasesTest.setUp
    tearDown = fixtures.EngineeringCasesTest.tearDown
    write = fixtures.EngineeringCasesTest.write
    manifest = fixtures.EngineeringCasesTest.manifest

    def seed(self):
        m = self.manifest()
        m['title'] = 'Test <product>'
        m['groups'][0]['design_status'] = 'FAIL'
        m['groups'][0]['scope'] = 'fixture cold start failed'
        self.app.results.cases.publish(self.owner, self.base, m)
        self.delivery = StudioDelivery(self.app.results)
        return self.delivery.inspect(self.owner, 'case:fixture:D2')

    def request(self, snap, **kw):
        return dict(selection=snap['selection'], revision=snap['revision'], snapshot_sha256=snap['snapshot_sha256'], **kw)

    def test_selected_version_retains_failure_without_promoting_assembly(self):
        a = self.seed()
        self.assertEqual(1, len(a['files']))
        self.assertIsNone(a['verdict'])
        self.assertEqual('FAIL', a['results'][0]['design_status'])
        self.assertIn('case:fixture:D2', [o['id'] for o in a['options']])
        self.assertFalse(a['results'][0]['hardware_verified'])

    def test_export_scope_hashes_index_and_immutable_readback(self):
        a = self.seed()
        m = self.manifest();m['version'] = 'D3'
        self.app.results.cases.publish(self.owner, self.base, m)
        # An independent candidate does not invalidate an unchanged D2 export.
        b = self.delivery.inspect(self.owner, 'case:fixture:D2')
        self.assertEqual(a['snapshot_sha256'], b['snapshot_sha256'])
        record = self.delivery.package(self.owner, self.request(b))
        path = self.delivery.archive(self.owner, record['id'])
        with zipfile.ZipFile(path) as z:
            manifest = json.loads(z.read('交付清单.json'))
            self.assertIn('未通过', z.read('打开我.html').decode())
            self.assertEqual(1, len(manifest['files']))
            f = manifest['files'][0]
            self.assertIn('/D2/', f['export_path'])
            self.assertEqual(f['sha256'], hashlib.sha256(z.read(f['export_path'])).hexdigest())
        other = self.app.conversations.create('other', None, 'studio-other')['id']
        with self.assertRaises(PermissionError):self.delivery.archive(other, record['id'])

    def test_missing_report_and_stale_snapshot_are_visible(self):
        a = self.seed()
        with self.assertRaisesRegex(ValueError, 'REPORT_NOT_AVAILABLE'):
            self.delivery.package(self.owner, self.request(a, purpose='report'))
        req=self.request(a);req['snapshot_sha256']='0'*64
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT_CHANGED'):self.delivery.package(self.owner, req)
        path,_=self.app.results.file(self.owner,a['files'][0]['id']);path.write_bytes(b'corrupt')
        b=self.delivery.inspect(self.owner,'case:fixture:D2')
        with self.assertRaisesRegex(ValueError,'FILES_MISSING'):self.delivery.package(self.owner,self.request(b))
        record=self.delivery.package(self.owner,self.request(b,allow_partial=True))
        self.assertEqual(1,record['omitted']);self.assertEqual(0,record['files'])

    def test_html_and_archive_tamper_fail_closed(self):
        a=self.seed();record=self.delivery.package(self.owner,self.request(a,purpose='summary'))
        path=self.delivery.archive(self.owner,record['id'])
        with zipfile.ZipFile(path) as z:data={n:z.read(n) for n in z.namelist()}
        data['打开我.html']=b'claimed pass'
        with zipfile.ZipFile(path,'w') as z:
            for n,b in data.items():z.writestr(n,b)
        with self.assertRaisesRegex(ValueError,'INDEX_INVALID'):self.delivery.archive(self.owner,record['id'])

    def test_report_relative_dependencies_are_preserved(self):
        m=self.manifest();m['groups'][0]['files']=[]
        for name in ['report/main.tex','report/main.pdf','figures/view.png','mechanical/large.blend']:
            p=self.base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(r'\includegraphics{../figures/view.png}' if name.endswith('.tex') else 'fixture '+name)
            m['groups'][0]['files'].append(dict(path=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        self.app.results.cases.publish(self.owner,self.base,m)
        self.delivery=StudioDelivery(self.app.results);a=self.delivery.inspect(self.owner,'case:fixture:D2')
        record=self.delivery.package(self.owner,self.request(a,purpose='report'))
        with zipfile.ZipFile(self.delivery.archive(self.owner,record['id'])) as z:
            self.assertIn('工程/fixture/D2/report/main.tex',z.namelist())
            self.assertIn('工程/fixture/D2/figures/view.png',z.namelist())
            self.assertNotIn('工程/fixture/D2/mechanical/large.blend',z.namelist())
        self.assertEqual(3, a['purposes']['report']['files'])
        self.assertEqual(4, a['purposes']['engineering']['files'])
        self.assertEqual(0, a['purposes']['summary']['files'])

    def test_markdown_report_exports_without_pdf_or_historical_report(self):
        m = self.manifest(); m['groups'][0]['files'] = []
        for name in ['P01-first-version-report.md', 'history/P01-first-version-report-initial.md', 'firmware/main.c']:
            p = self.base / name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('# current report' if name.endswith('.md') else 'int main(void){}')
            m['groups'][0]['files'].append(dict(path=name, sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        self.app.results.cases.publish(self.owner, self.base, m)
        delivery = StudioDelivery(self.app.results); snap = delivery.inspect(self.owner, 'case:fixture:D2')
        self.assertTrue(snap['purposes']['report']['available'])
        self.assertEqual(1, snap['purposes']['report']['files'])
        result = delivery.package(self.owner, self.request(snap, purpose='report'))
        with zipfile.ZipFile(delivery.archive(self.owner, result['id'])) as z:
            self.assertIn('工程/fixture/D2/P01-first-version-report.md', z.namelist())
            self.assertNotIn('工程/fixture/D2/history/P01-first-version-report-initial.md', z.namelist())
            self.assertNotIn('工程/fixture/D2/firmware/main.c', z.namelist())

    def test_cross_owner_scope_cannot_be_requested(self):
        self.seed();other=self.app.conversations.create('other',None,'scope-other')['id']
        with self.assertRaisesRegex(ValueError,'SELECTION_NOT_FOUND'):self.delivery.inspect(other,'case:fixture:D2')

    def test_http_routes_cannot_override_principal_and_archive_stays_private(self):
        from http.server import ThreadingHTTPServer
        from bfworld.agentlab.server import handler
        import threading
        import urllib.request
        import urllib.error
        a=self.seed()
        record=self.delivery.package(self.owner,self.request(a))
        other=self.app.conversations.create('other',None,'http-other')['id']
        token=self.app.store.issue(other)
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,auth,body=None):
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Authorization':'Bearer '+auth,'Content-Type':'application/json'})
            return urllib.request.urlopen(req,timeout=5)
        try:
            with request('/api/studio/delivery?session='+self.owner,token) as response:
                data=json.load(response);self.assertEqual(other,data['owner']);self.assertEqual([],data['files'])
            with self.assertRaises(urllib.error.HTTPError) as caught:
                request('/api/studio/archive?session='+self.owner+'&id='+record['id'],token)
            self.assertEqual(403,caught.exception.code)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                request('/api/studio/package',token,self.request(a,session_id=self.owner))
            self.assertEqual(400,caught.exception.code)
            operator=(self.app.store.root/'operator.token').read_text().strip()
            with request('/api/studio/archive?session='+self.owner+'&id='+record['id'],operator) as response:
                self.assertEqual('application/zip',response.headers['Content-Type'])
                self.assertEqual(self.delivery.archive(self.owner,record['id']).read_bytes(),response.read())
        finally:server.shutdown();server.server_close();thread.join(2)

    def test_missing_dependency_is_explicit_without_including_unrelated_files(self):
        m=self.manifest();m['groups'][0]['files']=[]
        for name, text in [('report/main.pdf','fixture pdf'),('report/main.tex',r'\input{missing}'),('unrelated.json','{}')]:
            p=self.base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            m['groups'][0]['files'].append(dict(path=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        self.app.results.cases.publish(self.owner,self.base,m)
        delivery=StudioDelivery(self.app.results);snap=delivery.inspect(self.owner,'case:fixture:D2')
        self.assertEqual(2,snap['purposes']['report']['files'])
        self.assertTrue(any('missing' in w for w in snap['purposes']['report']['warnings']))
        result=delivery.package(self.owner,self.request(snap,purpose='report'))
        with zipfile.ZipFile(delivery.archive(self.owner,result['id'])) as z:
            self.assertTrue(json.loads(z.read('交付清单.json'))['snapshot']['purposes']['report']['warnings'])

    def test_report_export_not_blocked_by_unrelated_missing_engineering_file(self):
        m=self.manifest();m['groups'][0]['files']=[]
        for name in ['report/main.pdf','geometry.step']:
            p=self.base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
            m['groups'][0]['files'].append(dict(path=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        self.app.results.cases.publish(self.owner,self.base,m)
        delivery=StudioDelivery(self.app.results);snap=delivery.inspect(self.owner,'case:fixture:D2')
        geometry=next(f for f in snap['files'] if f['name']=='geometry.step')
        path,_=self.app.results.file(self.owner,geometry['id']);path.write_bytes(b'corrupt')
        snap=delivery.inspect(self.owner,'case:fixture:D2')
        self.assertEqual(0,len(snap['purposes']['report']['missing']))
        result=delivery.package(self.owner,self.request(snap,purpose='report'))
        self.assertEqual(1,result['files']);self.assertEqual(0,result['omitted'])
        with self.assertRaisesRegex(ValueError,'FILES_MISSING'):
            delivery.package(self.owner,self.request(snap,purpose='engineering'))
