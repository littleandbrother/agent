import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import urllib.request
import urllib.error
from bfworld.agentlab.server import Workbench,handler
from bfworld.agentlab.provider import MODEL

class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Workbench(Path(self.tmp.name)/'state')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app));self.app.conversations.port=self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.token=(self.app.store.root/'operator.token').read_text()
    def tearDown(self):
        for cid in list(self.app.conversations.processes):self.app.conversations.stop(cid)
        deadline=time.time()+5
        while self.app.conversations.starting and time.time()<deadline:time.sleep(.05)
        self.server.shutdown();self.server.server_close();self.app.stop.set();self.app.thread.join(2);self.app.lock.close();self.tmp.cleanup()
    def req(self,path,body=None,headers=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,data=json.dumps(body).encode() if body is not None else None,
            headers=headers or {'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_cookie_bootstrap_host_origin_and_participant_boundary(self):
        with urllib.request.urlopen('http://127.0.0.1:'+str(self.server.server_port)+'/') as response:
            cookie=response.headers['Set-Cookie'];self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        self.assertEqual(200,self.req('/api/conversations',headers={'Cookie':cookie.split(';')[0]})[0])
        self.assertEqual(403,self.req('/api/conversations',headers={'Host':'evil.test'})[0])
        self.assertEqual(403,self.req('/api/conversations',{'text':'hello','operation_id':'x'},headers={'Cookie':cookie.split(';')[0],'Origin':'http://evil.test'})[0])
        alice=self.app.store.issue('alice')
        self.assertEqual(403,self.req('/api/conversations',headers={'Authorization':'Bearer '+alice})[0])
        for path,body in [('/api/organization',None),('/api/folders',{'name':'denied'}),('/api/sidebar/invalid',{'action':'delete'}),('/api/folder-memory',None)]:
            self.assertEqual(403,self.req(path,body,headers={'Authorization':'Bearer '+alice})[0])

    def test_provider_keepalive_is_forwarded_as_sse_comment(self):
        def fake(owner,payload,on_chunk=None):
            on_chunk(None)
            on_chunk({'model':MODEL,'choices':[{'delta':{'content':'ready'},'finish_reason':'stop'}]})
            return {'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
        self.app.provider.complete=fake
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/v1/chat/completions',
            data=json.dumps({'model':MODEL,'stream':True,'messages':[]}).encode(),
            headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response: wire=response.read().decode()
        self.assertTrue(wire.startswith(': upstream keepalive\n\n'))
        self.assertIn('ready',wire)
        self.assertTrue(wire.endswith('data: [DONE]\n\n'))

    def test_queued_followup_clears_previous_turn_failure_without_erasing_trace(self):
        (self.app.store.root.parent/'paid-window-closed.json').write_text('{}')
        _,conversation=self.req('/api/conversations',{'text':'original','operation_id':'failed-followup'})
        cid=conversation['id'];chat=self.app.conversations
        folder=chat.home/'sessions'/cid;folder.mkdir(parents=True,exist_ok=True)
        path=folder/'trace.jsonl'
        failure={'type':'turn_error','error':'PROVIDER_STREAM_ERROR'}
        path.write_text(json.dumps(failure)+'\n')
        chat.ingest(cid)
        self.assertEqual('FAILED',chat.get(cid)['status'])
        with path.open('a') as stream:stream.write(json.dumps({'type':'assistant_start','id':'followup'})+'\n')
        chat.ingest(cid)
        self.assertEqual('RUNNING',chat.get(cid)['status'])
        self.assertIsNone(chat.get(cid)['error'])
        with path.open('a') as stream:stream.write(json.dumps({'type':'chat_idle'})+'\n')
        chat.ingest(cid)
        self.assertEqual('IDLE',chat.get(cid)['status'])
        errors=[e['data'] for e in chat.events(cid) if e['data']['type']=='turn_error']
        self.assertEqual([failure],errors)
    def test_closed_window_persists_one_session_and_message_without_dispatch(self):
        (self.app.store.root.parent/'paid-window-closed.json').write_text('{}')
        body={'text':'设计一个计算任务','operation_id':'op','task_id':'dev-01'}
        status,c=self.req('/api/conversations',body);self.assertEqual(201,status);self.assertEqual('BLOCKED',c['status'])
        self.assertEqual(c['id'],self.req('/api/conversations',body)[1]['id'])
        self.assertEqual(400,self.req('/api/conversations',{**body,'text':'different'})[0])
        message={'text':'补充要求','operation_id':'follow'}
        self.req('/api/conversations/'+c['id']+'/messages',message);self.req('/api/conversations/'+c['id']+'/messages',message)
        d=self.req('/api/conversations/'+c['id'])[1];self.assertEqual(2,len(d['messages']));self.assertTrue(all(m['status']=='QUEUED' for m in d['messages']))
        self.assertEqual(1,len(self.req('/api/conversations')[1]['sessions']))
        seed=self.app.developer.seed(c['id'])
        self.assertIsNone(seed['payload']['source_session'])
        self.assertIn('solver.ts',seed['payload']['sources'])
        with self.app.store.connect() as db:self.assertEqual(0,db.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0])
        events=self.app.conversations.events(c['id']);cursor=events[-1]['seq'];self.assertEqual([],self.app.conversations.events(c['id'],cursor))

    def test_historical_terminal_events_do_not_close_resumed_process(self):
        from unittest.mock import Mock
        (self.app.store.root.parent/'paid-window-closed.json').write_text('{}')
        _,conversation=self.req('/api/conversations',{'text':'resume','operation_id':'old-idle'})
        cid=conversation['id'];chat=self.app.conversations
        folder=chat.home/'sessions'/cid;folder.mkdir(parents=True,exist_ok=True)
        path=folder/'trace.jsonl'
        path.write_text(json.dumps({'type':'turn_error','error':'old crash'})+'\n'+json.dumps({'type':'chat_idle'})+'\n')
        proc=Mock();proc.poll.return_value=None;proc.stdin=io.BytesIO()
        chat.processes[cid]=proc;chat.state(cid,'STARTING')
        try:
            chat.ingest(cid,execution_state=False)
            self.assertEqual('STARTING',chat.get(cid)['status'])
            self.assertEqual(b'',proc.stdin.getvalue())
            self.assertTrue(any(e['data'].get('error')=='old crash' for e in chat.events(cid)))
            with path.open('a') as stream:stream.write(json.dumps({'type':'turn_error','error':'new failure'})+'\n')
            chat.ingest(cid)
            self.assertEqual('FAILED',chat.get(cid)['status'])
            self.assertEqual('new failure',chat.get(cid)['error'])
        finally:
            chat.processes.pop(cid,None)

    def test_recovery_keeps_pending_input_and_does_not_renew_on_duplicate_or_retry(self):
        closed=self.app.store.root.parent/'paid-window-closed.json';closed.write_text('{}')
        body={'text':'继续','operation_id':'recover','model_cap_usd':.05}
        _,c=self.req('/api/conversations',body)
        cid=c['id']
        self.app.conversations.state(cid,'BLOCKED','MODEL_WALL_BUDGET')
        with self.app.store.connect() as db:
            db.execute('UPDATE model_limits SET expires=0')
            db.execute('UPDATE interactive_leases SET expires=0 WHERE owner=?',(cid,))
            before=[dict(r) for r in db.execute('SELECT * FROM chat_messages')]
        closed.unlink()
        self.app.conversations.reconcile_blocks()
        self.assertEqual('IDLE',self.app.conversations.get(cid)['status'])
        self.assertEqual(0,self.app.provider.status()['calls'])
        self.assertFalse(self.app.conversations.starting)
        self.req('/api/conversations',body)
        self.assertEqual(400,self.req('/api/conversations',{**body,'model_cap_usd':None})[0])
        self.app.conversations.retry(cid)
        self.assertEqual('CHAT_TURN_WALL_BUDGET',self.app.conversations.get(cid)['error'])
        with self.app.store.connect() as db:
            self.assertEqual(before,[dict(r) for r in db.execute('SELECT * FROM chat_messages')])
            self.assertEqual(0,db.execute('SELECT expires FROM interactive_leases WHERE owner=?',(cid,)).fetchone()[0])
            self.assertEqual(0,db.execute('SELECT expires FROM model_limits').fetchone()[0])

    def test_long_reload_includes_latest_reply_and_resumes_live_without_trace_loss(self):
        (self.app.store.root.parent/'paid-window-closed.json').write_text('{}')
        _,c=self.req('/api/conversations',{'text':'first message','operation_id':'long-history'})
        cid=c['id'];chat=self.app.conversations
        chat.event(cid,'assistant-start',{'type':'assistant_start','id':'old'})
        # A realistic stream exceeds the raw endpoint page size before its reply.
        with self.app.store.connect() as db:
            db.executemany('INSERT INTO chat_events(conversation,source,data,created) VALUES(?,?,?,?)',[(cid,'token-'+str(i),json.dumps({'type':'text_delta','id':'old','delta':'x'}),time.time()) for i in range(2100)])
        chat.event(cid,'reply',{'type':'message','id':'old','message':{'role':'assistant','content':[{'type':'text','text':'latest complete answer'}],'stopReason':'stop'}})
        chat.event(cid,'active-start',{'type':'assistant_start','id':'live'})
        chat.event(cid,'active-one',{'type':'text_delta','id':'live','delta':'现在'})
        chat.event(cid,'active-two',{'type':'text_delta','id':'live','delta':'继续'})
        with self.app.store.connect() as db:before=[tuple(r) for r in db.execute('SELECT seq,data FROM chat_events WHERE conversation=? ORDER BY seq',(cid,))]
        detail=self.req('/api/conversations/'+cid)[1];snapshot=detail['events']
        self.assertLess(len(snapshot),20)
        self.assertIn('latest complete answer',json.dumps(snapshot))
        self.assertEqual(['现在继续'],[e['data']['delta'] for e in snapshot if e['data']['type']=='text_delta'])
        self.assertEqual(before[-1][0],detail['event_cursor'])
        self.assertEqual([],chat.events(cid,detail['event_cursor']))
        with self.app.store.connect() as db:self.assertEqual(before,[tuple(r) for r in db.execute('SELECT seq,data FROM chat_events WHERE conversation=? ORDER BY seq',(cid,))])
        chat.event(cid,'active-three',{'type':'text_delta','id':'live','delta':'执行'})
        self.assertEqual(['执行'],[e['data']['delta'] for e in chat.events(cid,detail['event_cursor'])])
        # Full raw history remains page-addressable for audit/export.
        first=chat.events(cid);second=chat.events(cid,first[-1]['seq'])
        self.assertEqual(len(before)+1,len(first)+len(second))
    def test_actual_product_pi_loads_policy_and_current_context_without_paid_model(self):
        requests=[]
        def fake(owner,payload,on_chunk=None):
            requests.append(payload)
            base={'id':'fixture-product','object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
            on_chunk({**base,'choices':[{'index':0,'delta':{'role':'assistant','content':'产品上下文已读取。'},'finish_reason':None}]})
            on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})
            on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}})
            return {'model':MODEL,'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}}
        self.app.provider.complete=fake
        _,c=self.req('/api/conversations',{'text':'说明当前状态即可','operation_id':'product-policy'})
        end=time.time()+20
        while time.time()<end:
            events=self.app.conversations.events(c['id'])
            if any(e['data']['type']=='turn_complete' for e in events):break
            time.sleep(.1)
        loaded=next(e['data'] for e in events if e['data']['type']=='harness_loaded')
        packet=next(e['data']['packet'] for e in events if e['data']['type']=='product_context_snapshot')
        self.assertEqual(loaded['source']['loaded_modules']['product'],loaded['loaded']['product'])
        self.assertEqual(c['id'],packet['owner']);self.assertIn(packet['sha256'],json.dumps(requests))
        self.assertEqual(1,len(requests),'A question must not trigger automatic engineering continuation')
        self.assertTrue(any(e['data']['type']=='turn_complete' for e in events))

    def test_actual_pi_stream_and_mid_turn_message_without_external_provider(self):
        requests=[];stream_started=threading.Event()
        def fake(owner,payload,on_chunk=None):
            requests.append(payload)
            base={'id':'fixture','object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
            for text in ['local ', 'stream ', 'fixture']:
                on_chunk({**base,'choices':[{'index':0,'delta':{'role':'assistant','content':text},'finish_reason':None}]})
                stream_started.set();time.sleep(.2)
            on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})
            on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}})
            return {'model':MODEL,'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}}
        self.app.provider.complete=fake
        _,c=self.req('/api/conversations',{'text':'first fixture message','task_id':'dev-01','operation_id':'first'})
        self.assertTrue(stream_started.wait(12))
        self.req('/api/conversations/'+c['id']+'/messages',{'text':'mid-turn sentinel','operation_id':'second'})
        deadline=time.time()+15
        while time.time()<deadline:
            d=self.app.conversations.detail(c['id'])
            if len(requests)>=2 and c['id'] not in self.app.conversations.starting:break
            time.sleep(.1)
        types=[e['data']['type'] for e in d['events']]
        self.assertIn('text_delta',types);self.assertIn('turn_complete',types)
        self.assertTrue(any(e['data'].get('delivery')=='steer' for e in d['events']))
        self.assertTrue(all(m['status']=='ACCEPTED' for m in d['messages']),d['messages'])
        self.assertIn('mid-turn sentinel',json.dumps(requests))
        self.req('/api/conversations/'+c['id']+'/messages',{'text':'resumed conversation','operation_id':'third'})
        deadline=time.time()+12
        while time.time()<deadline:
            if len(requests)>=3 and c['id'] not in self.app.conversations.starting:break
            time.sleep(.1)
        self.assertGreaterEqual(len(requests),3)
        self.assertIn('first fixture message',json.dumps(requests[-1]['messages']))
        self.assertIn('mid-turn sentinel',json.dumps(requests[-1]['messages']))
        self.assertEqual(1,len(self.app.conversations.list()))
        with self.app.store.connect() as db:self.assertEqual(0,db.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0])

    def test_actual_pi_deadline_pauses_saves_and_resumes_existing_session(self):
        calls=[]
        def fake(owner,payload,on_chunk=None):
            calls.append(payload)
            base={'id':'deadline-fixture','object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
            if len(calls)==1:
                delta={'role':'assistant','tool_calls':[{'index':0,'id':'wait-fixture','type':'function',
                    'function':{'name':'bash','arguments':json.dumps({'command':'sleep 30','timeout':40})}}]}
                finish='tool_calls'
            else:
                delta={'role':'assistant','content':'已从原会话恢复'};finish='stop'
            on_chunk({**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]})
            on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':finish}]})
            on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}})
            return {'model':MODEL}
        self.app.provider.complete=fake
        _,c=self.req('/api/conversations',{'text':'等待工程结果的原任务','operation_id':'deadline-original'})
        cid=c['id'];deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if any(e['data']['type']=='tool_execution_start' for e in self.app.conversations.events(cid)):break
            time.sleep(.1)
        else:self.fail('actual Pi never started its waiting tool')
        with self.app.store.connect() as db:
            lease=dict(db.execute('SELECT * FROM interactive_leases WHERE owner=?',(cid,)).fetchone())
            self.assertEqual(1800,lease['expires']-lease['created'])
            self.assertEqual(lease['expires'],db.execute('SELECT expires FROM grants WHERE owner=?',(cid,)).fetchone()[0])
            # Accelerate only this isolated fixture's deadline, never production.
            db.execute('UPDATE interactive_leases SET expires=0 WHERE owner=?',(cid,))
        deadline=time.monotonic()+15
        while cid in self.app.conversations.starting and time.monotonic()<deadline:time.sleep(.1)
        self.assertNotIn(cid,self.app.conversations.starting)
        self.assertEqual('PAUSED',self.app.conversations.get(cid)['status'])
        self.assertEqual('CHAT_TURN_WALL_BUDGET',self.app.conversations.get(cid)['error'])
        home=self.app.store.root.parent
        receipt=json.loads((home/'sessions'/cid/'receipt.json').read_text())
        self.assertEqual('PAUSED',receipt['status']);self.assertFalse(receipt['deadline_shutdown']['forced_kill'])
        self.assertEqual(0,receipt['exit_code'])
        pointer=home/'participants'/cid/'.pi/chat-session-path';session_path=pointer.read_text()
        history=Path(session_path).read_bytes()
        self.assertIn('等待工程结果的原任务',history.decode())
        self.req('/api/conversations/'+cid+'/messages',{'text':'继续原任务，仅检查恢复','operation_id':'deadline-resume'})
        deadline=time.monotonic()+15
        while cid in self.app.conversations.starting and time.monotonic()<deadline:time.sleep(.1)
        self.assertEqual('IDLE',self.app.conversations.get(cid)['status'])
        self.assertEqual(session_path,pointer.read_text());self.assertTrue(Path(session_path).read_bytes().startswith(history))
        self.assertIn('等待工程结果的原任务',json.dumps(calls[-1]['messages'],ensure_ascii=False))
        self.assertIn('已从原会话恢复',json.dumps(self.app.conversations.detail(cid)['events'],ensure_ascii=False))
        self.assertEqual(2,len(calls))
        with self.app.store.connect() as db:self.assertEqual(0,db.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0])

    def test_model_ingress_accepts_history_but_rejects_unbounded_bodies(self):
        body={'model':MODEL,'messages':[{'role':'tool','content':'x'*140000}]}
        with patch.object(self.app.provider,'complete',return_value={'fixture':True}) as provider:
            self.assertEqual(200,self.req('/v1/chat/completions',body)[0])
            provider.assert_called_once()
            self.assertEqual(400,self.req('/api/conversations',body)[0])
            oversized={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','Content-Length':str(2*1024*1024+1)}
            self.assertEqual(400,self.req('/v1/chat/completions',{},headers=oversized)[0])

    def test_unfinished_product_executes_bounded_continuations_without_false_completion(self):
        calls=[]
        def fake(owner,payload,on_chunk=None):
            calls.append(payload)
            base={'id':'unfinished-fixture','object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
            on_chunk({**base,'choices':[{'index':0,'delta':{'role':'assistant','content':'准备下一步'},'finish_reason':None}]})
            on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})
            on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}})
            return {'model':MODEL}
        self.app.provider.complete=fake
        closed=self.app.store.root.parent/'paid-window-closed.json';closed.write_text('{}')
        _,c=self.req('/api/conversations',{'text':'执行完整产品任务','operation_id':'unfinished-goal'})
        self.app.assemblies.set_goal(c['id'],{'goal':{'required_roles':['housing'],'min_parts':1,'file_kinds':['source'],'max_continuations':12}})
        closed.unlink();self.app.conversations.retry(c['id'])
        deadline=time.time()+25
        while time.time()<deadline:
            d=self.app.conversations.detail(c['id'])
            if c['id'] not in self.app.conversations.starting:break
            time.sleep(.1)
        self.assertEqual(13,len(calls))
        self.assertNotEqual('required',calls[0].get('tool_choice'))
        self.assertTrue(all(p.get('tool_choice')=='required' for p in calls[1:]))
        # The watcher may finish between detail() and the starting-set check.
        d=self.app.conversations.detail(c['id'])
        self.assertEqual('PRODUCT_DELIVERY_INCOMPLETE',d['error'])
        self.assertEqual('FAILED',d['status'])
        self.assertNotIn('turn_complete',[e['data']['type'] for e in d['events']])
        self.assertEqual(12,len([e for e in d['events'] if e['data']['type']=='delivery_continuation']))
        with self.app.store.connect() as db:self.assertEqual(0,db.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0])

    def test_product_model_revision_error_explains_correct_field_without_native_dispatch(self):
        calls=[]
        def fake(owner,payload,on_chunk=None):
            calls.append(payload)
            base={'id':'revision-fixture','object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
            if len(calls)==1:
                delta={'role':'assistant','tool_calls':[{'index':0,'id':'revision-test','type':'function',
                    'function':{'name':'bf_engineering','arguments':json.dumps({'action':'run','engine':'product-model',
                        'operation_id':'wrong-field','design_revision':10,'parameters':{'assembly_revision':10}})}}]}
                finish='tool_calls'
            else:
                self.assertIn('PRODUCT_MODEL_OMIT_DESIGN_REVISION',json.dumps(payload['messages']))
                delta={'role':'assistant','content':'已定位版本字段错误'};finish='stop'
            on_chunk({**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]})
            on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':finish}]})
            on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}})
            return {'model':MODEL}
        self.app.provider.complete=fake
        _,c=self.req('/api/conversations',{'text':'检查装配版本字段','operation_id':'revision-fixture'})
        deadline=time.time()+15
        while time.time()<deadline:
            if c['id'] not in self.app.conversations.starting:break
            time.sleep(.1)
        self.assertEqual(2,len(calls))
        self.assertEqual([],self.app.engineering.jobs(c['id']))
        self.assertIn('turn_complete',[e['data']['type'] for e in self.app.conversations.detail(c['id'])['events']])

    def test_actual_pi_length_stop_is_failed_and_never_completed(self):
        def fake(owner,payload,on_chunk=None):
            self.assertEqual(8192,payload['max_tokens'])
            system='\n'.join(str(m.get('content','')) for m in payload['messages'] if m['role']=='system')
            self.assertIn('本会话尚未绑定科学基准，是产品工程任务',system)
            self.assertNotIn('Finish within 24 model requests',system)
            base={'id':'length-fixture','object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
            on_chunk({**base,'choices':[{'index':0,'delta':{'role':'assistant','content':'已'},'finish_reason':None}]})
            on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':'length'}]})
            on_chunk({**base,'choices':[],'usage':{'prompt_tokens':36727,'completion_tokens':1,'total_tokens':36728}})
            return {'model':MODEL}
        self.app.provider.complete=fake
        _,c=self.req('/api/conversations',{'text':'length fixture','operation_id':'length-fixture'})
        deadline=time.time()+12
        while time.time()<deadline:
            d=self.app.conversations.detail(c['id'])
            if c['id'] not in self.app.conversations.starting:break
            time.sleep(.1)
        self.assertEqual('FAILED',d['status'])
        self.assertEqual('MODEL_OUTPUT_TRUNCATED',d['error'])
        types=[e['data']['type'] for e in d['events']]
        self.assertIn('turn_error',types)
        self.assertNotIn('turn_complete',types)

if __name__=='__main__':unittest.main()
