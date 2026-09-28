import json
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from bfworld.agentlab.panorama import Panorama
from bfworld.agentlab.server import Workbench, handler


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.repo=self.root/'source';self.repo.mkdir()
        self.source=self.repo/'main.py';self.source.write_text('x = 1\n')
        self.modules=[dict(id='core',title='Core',paths=[('test','main.py')])]
        self.p=Panorama(self.root/'state',{'test':self.repo},self.modules)

    def tearDown(self):self.tmp.cleanup()

    def test_uncommitted_edit_delete_and_historical_bytes(self):
        first=self.p.scan();self.assertEqual(first['id'],self.p.scan()['id'])
        self.source.write_text('x = 2\n');second=self.p.scan()
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual('x = 1\n',self.p.file(first['id'],'test:main.py')['content'])
        change=self.p.projection(second['id'],first['id'])
        self.assertEqual('modified',change['changes'][0]['kind'])
        self.assertIsNone(change['actor'])
        self.source.unlink();third=self.p.scan()
        deleted=self.p.file(third['id'],'test:main.py',second['id'])
        self.assertFalse(deleted['exists']);self.assertIn('-x = 2',deleted['diff'])
        with self.assertRaises(ValueError):self.p.file(third['id'],'test:main.py')

    def test_symlink_and_unlisted_file_denied(self):
        secret=self.root/'private.py';secret.write_text('not exposed')
        self.source.unlink();self.source.symlink_to(secret)
        snap=self.p.scan()
        self.assertEqual({},snap['manifest']['files'])
        self.assertEqual('symlink',snap['manifest']['skipped'][0]['reason'])
        with self.assertRaises(ValueError):self.p.file(snap['id'],'../../private.py')
        with self.assertRaises(ValueError):self.p.read_snapshot('../latest')

    def test_source_corruption_never_falls_back_to_current(self):
        first=self.p.scan();sha=first['manifest']['files']['test:main.py']['sha256']
        (self.p.root/'blobs'/sha).write_text('wrong')
        with self.assertRaisesRegex(ValueError,'CORRUPT'):self.p.file(first['id'],'test:main.py')

    def test_cloud_history_and_source_do_not_block_or_imply_deletion(self):
        first=self.p.scan()
        self.source.write_text('x = 2\n');second=self.p.scan()
        cloud_snapshot=self.p.root/'snapshots'/(first['id']+'.json')
        cloud_paths={self.source.resolve(),cloud_snapshot.resolve()}
        original_read=Path.read_bytes
        def guarded_read(path, *args, **kwargs):
            if path.resolve() in cloud_paths:
                raise AssertionError('must not read cloud placeholder bytes')
            return original_read(path, *args, **kwargs)
        with patch('bfworld.agentlab.panorama.is_cloud_file', side_effect=lambda p: Path(p).resolve() in cloud_paths), patch.object(Path, 'read_bytes', guarded_read):
            view=self.p.projection()
            self.assertEqual([first['id']],view['unavailable_snapshots'])
            self.assertEqual(second['id'],view['baseline'])
            with self.assertRaisesRegex(ValueError,'CLOUD_FILE_UNAVAILABLE'):
                self.p.read_snapshot(first['id'])
            self.p.scan()
            view=self.p.projection()
            self.assertEqual('unavailable',view['changes'][0]['kind'])
            self.assertEqual('cloud_placeholder',view['skipped'][0]['reason'])

    def test_check_actual_output_and_stale_after_edit(self):
        check=self.p.run_check([sys.executable,'-c','print("real check")'],self.repo,'check')
        self.assertEqual(0,check['exit_code'])
        self.assertEqual('current',self.p.checks(check['snapshot'])[0]['freshness'])
        self.assertIn('real check',self.p.check_log(check['id'])['text'])
        self.source.write_text('x = 3\n');now=self.p.scan()
        self.assertEqual('stale',self.p.checks(now['id'])[0]['freshness'])
        failed=self.p.run_check([sys.executable,'-c','raise SystemExit(2)'],self.repo,'failure')
        self.assertEqual('failed',failed['result'])

    def test_edit_during_check_invalidates_pass(self):
        check=self.p.run_check([sys.executable,'-c',"from pathlib import Path;Path('main.py').write_text('changed')"],self.repo,'mutation')
        self.assertEqual('passed',check['result'])
        self.assertNotEqual(check['snapshot'],check['end_snapshot'])
        self.assertEqual('stale',self.p.checks(check['end_snapshot'])[0]['freshness'])


class PanoramaHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.app=Workbench(root/'state')
        repo=root/'source';repo.mkdir();(repo/'one.py').write_text('x=1')
        self.app.panorama=Panorama(root/'state',{'test':repo},[dict(id='one',paths=[('test','one.py')])])
        self.operator=(self.app.store.root/'operator.token').read_text()
        self.participant=self.app.store.issue('participant')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()

    def req(self,path,body=None,token=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+(token or self.operator),'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)

    def test_operator_only_and_no_execution_endpoint(self):
        self.assertEqual(403,self.req('/api/developer/panorama',token=self.participant)[0])
        self.assertEqual(403,self.req('/api/developer/panorama/scan',{},self.participant)[0])
        code,snap=self.req('/api/developer/panorama/scan',{})
        self.assertEqual(200,code)
        self.assertEqual(200,self.req('/api/developer/panorama')[0])
        self.assertEqual(200,self.req('/api/developer/panorama/file?snapshot='+snap['snapshot']+'&file=test%3Aone.py')[0])
        self.assertEqual(404,self.req('/api/developer/panorama/run',{'command':['bad']})[0])
        self.req('/api/developer/panorama/scan',{})
        with self.app.store.connect() as db:
            self.assertEqual(0,db.execute('select count(*) from jobs').fetchone()[0])
            self.assertEqual(0,db.execute('select count(*) from model_requests').fetchone()[0])


if __name__=='__main__':unittest.main()
