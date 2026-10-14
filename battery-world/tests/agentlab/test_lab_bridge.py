import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

from bfworld.agentlab.lab_bridge import LabBridge, static_file
from bfworld.agentlab.design_lab.repository_view import trace


class LabBridgeCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.cfg={'schema_version':'bf-lab-read-bridge-v1','upstream':'http://127.0.0.1:8870',
          'operator_token':'/Users/depengsu/.local/share/bf-agent-architecture-v2/workbench/state/operator.token',
          'profile_sha256':'fixed','projects':[{'project':'PR-1','owner':'pi-1'}]}
        self.file=self.root/'bridge.json';self.file.write_text(json.dumps(self.cfg))
        with patch('bfworld.agentlab.lab_bridge.Path.is_file',return_value=True):self.bridge=LabBridge(self.file)
        self.token=self.root/'token';self.token.write_text('test-token');self.bridge.token_path=self.token

    def response(self,value):
        response=MagicMock();response.__enter__.return_value=response
        response.status=200;response.headers={'Content-Type':'application/json'}
        response.read.return_value=json.dumps(value).encode();return response

    def test_scoped_get_hides_upstream_credentials(self):
        with patch('bfworld.agentlab.lab_bridge.urlopen',return_value=self.response({'environment':{'profile_sha256':'fixed'}})) as network:
            status,data,kind=self.bridge.get('/api/design-repository?project=PR-1&owner=pi-1')
            request=network.call_args.args[0]
            self.assertEqual('GET',request.get_method());self.assertEqual(200,status)
            self.assertNotIn(b'test-token',data);self.assertEqual('Bearer test-token',request.headers['Authorization'])

    def test_wrong_owner_and_non_read_route_do_not_reach_service(self):
        with patch('bfworld.agentlab.lab_bridge.urlopen') as network:
            for url in ['/api/design-lab','/api/design-repository?project=PR-1&owner=pi-2',
                        '/api/design-repository?project=PR-1&owner=pi-1&owner=pi-2']:
                with self.assertRaises((ValueError,PermissionError)):self.bridge.get(url)
            network.assert_not_called()

    def test_project_list_and_environment_identity(self):
        with patch('bfworld.agentlab.lab_bridge.urlopen',return_value=self.response({'projects':[
            {'id':'PR-1','owner':'pi-1'},{'id':'PR-2','owner':'pi-2'}]})):
            value=json.loads(self.bridge.get('/api/design-repository/projects')[1]);self.assertEqual(1,len(value['projects']))
        with patch('bfworld.agentlab.lab_bridge.urlopen',return_value=self.response({'environment':{'profile_sha256':'other'}})):
            with self.assertRaisesRegex(ValueError,'ENVIRONMENT_CHANGED'):
                self.bridge.get('/api/design-repository?project=PR-1&owner=pi-1')

    def test_offline_lab_does_not_change_studio(self):
        from urllib.error import URLError
        with patch('bfworld.agentlab.lab_bridge.urlopen',side_effect=URLError('offline')) as network:
            self.assertEqual(503,self.bridge.get('/api/design-repository/projects')[0]);self.assertEqual(1,network.call_count)

    def test_only_code_assets_are_served(self):
        (self.root/'architecture-v2').mkdir();(self.root/'architecture-v2/index.html').write_text('Lab')
        self.assertEqual('index.html',static_file(self.root,'/lab')[0].name)
        for path in ['/lab/v2/assets/cropped.png','/lab/v2/../../secret']:
            with self.assertRaises(FileNotFoundError):static_file(self.root,path)
        self.assertIsNone(static_file(self.root,'/'))

    def test_non_loopback_upstream_rejected(self):
        self.cfg['upstream']='https://example.com';self.file.write_text(json.dumps(self.cfg))
        with self.assertRaisesRegex(ValueError,'LOOPBACK_ONLY'):LabBridge(self.file)


class PublicTraceCase(unittest.TestCase):
    def test_trace_is_project_scoped_and_removes_reasoning(self):
        with tempfile.TemporaryDirectory() as directory:
            database=Path(directory)/'trace.sqlite'
            def connect():
                db=sqlite3.connect(database);db.row_factory=sqlite3.Row;return db
            with connect() as db:
                db.execute('CREATE TABLE chat_events(seq INTEGER,conversation TEXT,data TEXT,created REAL)')
                db.execute('INSERT INTO chat_events VALUES(?,?,?,?)',(1,'pi-1',json.dumps({'type':'message',
                    'message':{'role':'assistant','content':[{'type':'thinking','thinking':'private-thought'},
                        {'type':'text','text':'public-result'},{'type':'toolCall','name':'bf_repository',
                         'arguments':{'action':'read','token':'secret'}}]}}),1))
                db.execute('INSERT INTO chat_events VALUES(?,?,?,?)',(2,'pi-1',json.dumps({'type':'message',
                    'message':{'role':'user','content':'public instruction in legacy string format'}}),2))
            repo=SimpleNamespace(store=SimpleNamespace(connect=connect),view=lambda p,o:{'project':{'owner':'pi-1'},'professional_tasks':[]})
            value=trace(repo,'PR-1','pi-1','pi-1');raw=json.dumps(value)
            self.assertIn('public-result',raw);self.assertNotIn('private-thought',raw);self.assertNotIn('secret',raw)
            beginning=trace(repo,'PR-1','pi-1','pi-1',after=0)
            self.assertEqual('public instruction in legacy string format',beginning['records'][-1]['text'])
            with self.assertRaisesRegex(PermissionError,'TRACE_PROJECT_SCOPE'):trace(repo,'PR-1','pi-1','other')
