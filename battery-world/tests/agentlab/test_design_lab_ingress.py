"""Authenticated raw history reaches the unchanged bounded provider projector."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import http.client
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from bfworld.agentlab.server import Workbench,handler
from bfworld.agentlab.context import project_interactive,REQUEST_BYTES,ContextArchive


class PreservedHistoryIngressTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Workbench(Path(self.tmp.name)/'state')
        self.app.store.grant('long-owner',['dev-01'],1,time.time()+60);self.token=self.app.store.issue('long-owner')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app))
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()
    def request(self,path,body):
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=20) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def body(self):
        return {'messages':[{'role':'user','content':'Keep original requirements'},
          {'role':'assistant','content':'historical-output '*1100000},
          {'role':'user','content':'Current exact task'}]}
    def test_long_authenticated_sdk_history_is_projected_not_deleted(self):
        with self.app.store.connect() as db:db.execute('INSERT INTO interactive_leases VALUES(?,?,?,?)',('long-owner','message',time.time(),time.time()+60))
        original=self.body();seen=[]
        def local_project(owner,payload):
            self.assertEqual('long-owner',owner);self.assertEqual(original,payload)
            wire,audit=project_interactive(payload,ContextArchive(self.app.store.root.parent,owner))
            self.assertLessEqual(len(json.dumps(wire).encode()),REQUEST_BYTES)
            self.assertEqual('Current exact task',wire['messages'][-1]['content']);seen.append(audit)
            return {'id':'mock-local-projection','choices':[]}
        with patch.object(self.app.provider,'complete',side_effect=local_project):
            self.assertEqual(200,self.request('/v1/chat/completions',original)[0])
        self.assertTrue(seen);self.assertTrue(list((self.app.store.root.parent/'participants/long-owner/context-records').glob('*.json')))
        self.assertEqual('historical-output '*1100000,original['messages'][1]['content'])
    def test_noninteractive_ingress_allowance_does_not_expand(self):
        with patch.object(self.app.provider,'complete') as provider:
            # The server rejects Content-Length before reading the body; a
            # client sending the rejected 18MiB body at once can get EPIPE.
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
            conn.putrequest('POST','/v1/chat/completions')
            conn.putheader('Authorization','Bearer '+self.token)
            conn.putheader('Content-Length',18*1024*1024)
            conn.endheaders();response=conn.getresponse();body=json.load(response);conn.close()
            self.assertEqual(400,response.status);self.assertEqual('REQUEST_SIZE',body['error']);provider.assert_not_called()
    def test_tool_mutation_endpoint_does_not_receive_large_history_allowance(self):
        with self.app.store.connect() as db:db.execute('INSERT INTO interactive_leases VALUES(?,?,?,?)',('long-owner','message',time.time(),time.time()+60))
        status,body=self.request('/api/assembly',{'text':'x'*130000})
        self.assertEqual(400,status);self.assertEqual('REQUEST_SIZE',body['error'])


if __name__=='__main__':unittest.main()
