import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from bfworld.agentlab.server import Workbench,handler
from bfworld.agentlab.provider import MODEL

class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
        self.app=Workbench(self.home/'state');self.org=self.app.organization;self.chat=self.app.conversations
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app));self.chat.port=self.server.server_port
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.requests=[];self.started=threading.Event();self.delay=.02
        def fake(owner,payload,on_chunk=None):
            self.requests.append(payload);self.started.set()
            base={'id':'fixture','object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
            for text in ['local ','answer']:
                time.sleep(self.delay)
                on_chunk({**base,'choices':[{'index':0,'delta':{'role':'assistant','content':text},'finish_reason':None}]})
            on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})
            on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}})
            return {'model':MODEL,'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}}
        self.app.provider.complete=fake
    def tearDown(self):
        for cid in list(self.chat.processes):self.chat.stop(cid)
        end=time.time()+10
        while self.chat.starting and time.time()<end:time.sleep(.05)
        self.server.shutdown();self.server.server_close();self.app.stop.set();self.app.thread.join(2);self.app.lock.close();self.tmp.cleanup()
    def blocked(self,text='initial',folder=None,op='first'):
        (self.home/'paid-window-closed.json').write_text('{}')
        return self.chat.create(text,'dev-01',op,folder)
    def wait(self,cid):
        end=time.time()+15
        while time.time()<end:
            if cid not in self.chat.starting and not self.chat.recalls.pending(cid):return self.chat.detail(cid)
            time.sleep(.05)
        self.fail('conversation timeout '+str(self.chat.get(cid)))
    def test_rename_move_recycle_and_folder_order_preserve_legacy_receipt(self):
        f=self.org.create_folder('Project A');g=self.org.create_folder('Project B')
        c=self.blocked(folder=f['id']);self.org.change_entry(c['id'],{'action':'rename','name':'Renamed'})
        self.org.change_entry(c['id'],{'action':'move','folder_id':g['id']})
        self.assertEqual('Renamed',self.chat.list()[0]['title']);self.assertEqual(g['id'],self.chat.detail(c['id'])['folder_id'])
        self.org.mutate_folder(g['id'],{'action':'reorder','direction':'up'});self.assertEqual(g['id'],self.org.folders()[0]['id'])
        self.org.change_entry(c['id'],{'action':'delete'});self.assertEqual([],self.chat.list());self.assertEqual(1,len(self.chat.list(True)))
        self.org.change_entry(c['id'],{'action':'restore'});self.assertEqual(1,len(self.chat.list()))
        self.org.mutate_folder(g['id'],{'action':'delete'});self.assertIsNone(self.org.metadata(c['id'])['folder_id'])
        path=self.home/'sessions/pi-legacy/receipt.json';path.parent.mkdir(parents=True);raw=json.dumps({'owner':'pi-legacy','task_id':'dev-01','harness':{'label':'H0'},'started':1,'mode':'solve','status':'COMPLETED'})
        path.write_text(raw)
        self.org.change_entry('pi-legacy',{'action':'rename','name':'Original trial'})
        self.org.change_entry('pi-legacy',{'action':'move','folder_id':f['id']})
        self.org.change_entry('pi-legacy',{'action':'delete'})
        self.assertEqual(raw,path.read_text());self.assertTrue(any(x['id']=='pi-legacy' for x in self.chat.list(True)))
        with self.assertRaises(ValueError):self.org.change_entry('../../escape',{'action':'rename','name':'bad'})
    def test_shared_memory_isolation_revision_and_tool_validation(self):
        a=self.org.create_folder('A');b=self.org.create_folder('B')
        c=self.blocked(folder=a['id']);d=self.blocked(folder=a['id'],op='second');e=self.blocked(folder=b['id'],op='third')
        for item in [c,d,e]:self.org.bind(item['id'],self.org.context(item['id']))
        self.org.memory(c['id'],{'memory':'shared sentinel','expected_revision':0})
        self.assertEqual('shared sentinel',self.org.memory(d['id'])['memory']);self.assertEqual('',self.org.memory(e['id'])['memory'])
        with self.assertRaises(ValueError):self.org.memory(c['id'],{'memory':'stale','expected_revision':0})
        with self.assertRaises(PermissionError):self.org.memory('foreign')
        with self.assertRaises(ValueError):self.org.configure(a['id'],{**a['config'],'tools':['secret_tool']},1)
        self.org.change_entry(d['id'],{'action':'move','folder_id':b['id']})
        with self.assertRaises(PermissionError):self.org.memory(d['id'])
    def test_actual_pi_two_sessions_share_memory_prompt_and_tool_registration(self):
        seed=self.app.developer.seed()['payload'];seed['prompts']['solver_append']='HARNESS_SHARED_SENTINEL'
        revision=self.app.developer.save(seed)['id'];self.assertEqual('VALIDATED',self.app.developer.validate(revision)['status'])
        folder=self.org.create_folder('Shared');self.org.configure(folder['id'],{**folder['config'],'harness_revision':revision,'memory':'MEMORY_A_123','prompt':'PROMPT_A_456','tools':['read','bf_memory']},0)
        for op in ['one','two']:
            c=self.chat.create('fixture '+op,'dev-01',op,folder['id']);d=self.wait(c['id']);self.assertEqual('IDLE',d['status'])
        self.assertEqual(2,len(self.requests))
        projection=self.app.developer.projection(c['id'])['session']
        self.assertEqual(['read','bf_memory'],projection['shared_context']['tools'])
        self.assertEqual('MEMORY_A_123',projection['shared_context']['memory'])
        self.assertIn('PROMPT_A_456',projection['contexts'][-1]['prompt'])
        for request in self.requests:
            self.assertIn('HARNESS_SHARED_SENTINEL',json.dumps(request));self.assertIn('MEMORY_A_123',json.dumps(request));self.assertIn('PROMPT_A_456',json.dumps(request))
            self.assertEqual({'read','bf_memory'},{t['function']['name'] for t in request['tools']})
        with self.app.store.connect() as db:self.assertEqual(0,db.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0])
    def test_real_pi_memory_tool_write_is_read_by_next_folder_session(self):
        f=self.org.create_folder('Agent shared notes');original=self.app.provider.complete;issued=[]
        def provider(owner,payload,on_chunk=None):
            if issued:return original(owner,payload,on_chunk)
            issued.append(owner);self.requests.append(payload)
            base={'id':'fixture-tool','object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
            args=json.dumps({'action':'write','memory':'AGENT_WRITTEN_SHARED_NOTE','expected_revision':0})
            on_chunk({**base,'choices':[{'index':0,'delta':{'role':'assistant','tool_calls':[{'index':0,'id':'memory-call','type':'function','function':{'name':'bf_memory','arguments':args}}]},'finish_reason':None}]})
            on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls'}]})
            on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}})
            return {'model':MODEL,'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}}
        self.app.provider.complete=provider
        c=self.chat.create('Write a shared note','dev-01','one',f['id']);self.wait(c['id'])
        self.assertEqual('AGENT_WRITTEN_SHARED_NOTE',self.org.folder(f['id'])['config']['memory'])
        d=self.chat.create('Read shared note','dev-01','two',f['id']);self.wait(d['id'])
        self.assertIn('AGENT_WRITTEN_SHARED_NOTE',json.dumps(self.requests[-1]['messages']))

    def test_queued_recall_cannot_retry_and_does_not_dispatch(self):
        c=self.blocked();d=self.chat.detail(c['id']);mid=d['messages'][0]['id']
        self.chat.recalls.request(c['id'],mid);d=self.wait(c['id'])
        self.assertEqual('WITHDRAWN',d['messages'][0]['status']);self.assertEqual('COMPLETE',d['recalls'][0]['status'])
        with self.assertRaises(ValueError):self.chat.retry(c['id'])
        self.assertEqual([],self.requests)
    def test_recall_branches_actual_pi_context_and_retains_raw_history(self):
        c=self.chat.create('KEEP_FIRST','dev-01','one');cid=c['id'];self.wait(cid)
        self.chat.send(cid,'REMOVE_SECOND','two');d=self.wait(cid);mid=d['messages'][1]['id']
        pointer=self.home/'participants'/cid/'.pi/chat-session-path';session=Path(pointer.read_text());before=session.read_bytes()
        self.chat.recalls.request(cid,mid);d=self.wait(cid);self.assertEqual('COMPLETE',d['recalls'][0]['status'])
        self.assertTrue(session.read_bytes().startswith(before))
        self.chat.send(cid,'AFTER_RECALL','three');d=self.wait(cid)
        payload=json.dumps(self.requests[-1]['messages']);self.assertIn('KEEP_FIRST',payload);self.assertIn('AFTER_RECALL',payload);self.assertNotIn('REMOVE_SECOND',payload)
        self.assertEqual('WITHDRAWN',d['messages'][1]['status'])
    def test_running_recall_stops_and_removes_current_input(self):
        self.delay=.5;c=self.chat.create('REMOVE_RUNNING','dev-01','one');cid=c['id'];self.assertTrue(self.started.wait(10))
        mid=self.chat.detail(cid)['messages'][0]['id'];self.chat.recalls.request(cid,mid);d=self.wait(cid)
        self.assertEqual('COMPLETE',d['recalls'][0]['status']);self.assertEqual('WITHDRAWN',d['messages'][0]['status'])
        self.delay=.02;self.chat.send(cid,'NEW_AFTER_STOP','two');self.wait(cid)
        self.assertNotIn('REMOVE_RUNNING',json.dumps(self.requests[-1]['messages']))

if __name__=='__main__':unittest.main()
