"""Negative controls for observation fidelity and local engineering capabilities."""
import base64
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from bfworld.agentlab.server import Workbench, handler
from bfworld.agentlab.trace_review import TraceReview
from bfworld.agentlab.trace_analysis import analyze,compare
from bfworld.agentlab.engineering import validate
from bfworld.agentlab.engineering import Engineering
from bfworld.agentlab.provider import MODEL


class TraceEngineering(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.app=Workbench(self.home/'state')
        self.owner=self.app.conversations.create('Trace engineering fixture',None,'trace-engineering-fixture',defer_dispatch=True)['id']
        self.directory=self.home/'sessions'/self.owner;self.directory.mkdir(parents=True)
        (self.directory/'receipt.json').write_text(json.dumps({'owner':self.owner,'harness':{'identity':'test','model':'fixture'},'started':1,'ended':9}))
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app));self.app.conversations.port=self.server.server_port
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.token=(self.app.store.root/'operator.token').read_text()

    def tearDown(self):
        for cid in list(self.app.conversations.processes):self.app.conversations.stop(cid)
        deadline=time.time()+10
        while self.app.conversations.starting and time.time()<deadline:time.sleep(.05)
        self.server.shutdown();self.server.server_close();self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()

    def request(self,path,body=None,token=None):
        request=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,
            data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+(token or self.token),'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)

    def trace(self):
        return TraceReview(self.app).snapshot(self.owner)

    def test_timed_untimed_skill_mcp_and_partial_usage_are_source_bound(self):
        events=[{'type':'input_accepted','message_id':'m1','time':1},
            {'type':'tool_execution_start','toolName':'read','toolCallId':'a','args':{'path':'guide/SKILL.md'}},
            {'type':'tool_execution_end','toolName':'read','toolCallId':'a','result':'guide','time':3},
            {'type':'tool_execution_start','toolName':'mcp__blender__get_scene_info','toolCallId':'b','time':4,'args':{}},
            {'type':'tool_execution_end','toolName':'mcp__blender__get_scene_info','toolCallId':'b','time':5,'result':{'objects':[]}},
            {'type':'message','message':{'role':'assistant','stopReason':'length'}},
            {'type':'turn_error','error':'MODEL_OUTPUT_TRUNCATED','time':8}]
        raw=('\n'.join(json.dumps(x) for x in events)+'\n'+ '{"partial"').encode();(self.directory/'trace.jsonl').write_bytes(raw)
        with self.app.store.connect() as db:
            db.execute("INSERT INTO model_requests VALUES('r1',?,2,'h',.1,.01,'SETTLED',?,NULL,NULL)",(self.owner,json.dumps({'prompt_tokens':100,'completion_tokens':1,'total_tokens':101})))
            db.execute("INSERT INTO model_requests VALUES('r2',?,6,'h2',.1,0,'UNKNOWN',NULL,NULL,'TLS')",(self.owner,))
            db.execute('INSERT INTO model_request_context VALUES(?,?,?,?,?)',('r1',self.owner,'m1',2,'{}'))
        snap=self.trace();a=analyze(snap)
        calls=[x for x in a['timeline'] if x['lane']=='tools']
        self.assertEqual(['skill','mcp'],[x['category'] for x in calls]);self.assertIsNone(calls[0]['time']);self.assertIsNone(calls[0]['duration_ms'])
        self.assertEqual(1000,calls[1]['duration_ms']);self.assertEqual(1,a['coverage']['timed_tools'])
        self.assertEqual(1,a['metrics']['input_tokens']['known']);self.assertEqual(2,a['metrics']['input_tokens']['total'])
        self.assertAlmostEqual(.11,a['metrics']['cost_upper_bound_usd'])
        self.assertIn('output-truncated',[f['kind'] for f in a['findings']]);self.assertEqual(snap['source']['sha256'],a['source']['trace_sha256'])
        self.assertEqual(raw,base64.b64decode(snap['raw_base64']));self.assertEqual(raw,(self.directory/'trace.jsonl').read_bytes())
        result=compare(a,a);self.assertIsNone(result['attribution']);self.assertIsNone(result['metrics'][0]['delta'])

    def test_recorded_completed_does_not_manufacture_success(self):
        (self.directory/'trace.jsonl').write_text('{"type":"turn_complete","time":2}\n')
        a=analyze(self.trace());self.assertNotIn('verified',a);self.assertNotIn('outcome',a)
        self.assertEqual(0,a['coverage']['tools']);self.assertEqual([],a['requests'])
        self.assertEqual(200,self.request('/api/developer/trace-analysis?session='+self.owner)[0])
        stranger=self.app.store.issue('stranger')
        self.assertEqual(403,self.request('/api/developer/trace-analysis?session='+self.owner,token=stranger)[0])

    def test_parameter_rejection_idempotence_busy_and_foreign_artifacts(self):
        for p in ({'height_mm':float('nan')},{'length_mm':True},{'length_mm':2},{'wall_mm':6,'height_mm':15},{'script':'evil'}):
            with self.assertRaises(ValueError):validate('blender',p)
        with self.assertRaises(ValueError):validate('comsol',{'length_mm':10,'thickness_mm':2})
        with patch.object(self.app.engineering,'run') as execute:
            body={'engine':'blender','operation_id':'one','parameters':{}}
            a=self.app.engineering.submit(self.owner,body);b=self.app.engineering.submit(self.owner,body)
            self.assertEqual(a['id'],b['id'])
            with self.assertRaisesRegex(ValueError,'CONFLICT'):self.app.engineering.submit(self.owner,{**body,'parameters':{'length_mm':90}})
            with self.assertRaisesRegex(ValueError,'BUSY'):self.app.engineering.submit('other',{**body,'operation_id':'second'})
            deadline=time.time()+2
            while execute.call_count<1 and time.time()<deadline:time.sleep(.01)
            self.assertEqual(1,execute.call_count)
        with self.assertRaises(PermissionError):self.app.engineering.get('other',a['id'])
        with self.assertRaises(PermissionError):self.app.engineering.artifact(self.owner,a['id'],'../../state/operator.token')
        stranger=self.app.store.issue('other')
        self.assertEqual(403,self.request('/api/engineering',token=stranger)[0])
        self.assertEqual(403,self.request('/api/engineering',{'action':'skill','skill_id':'blender-enclosure'},stranger)[0])

    def test_skill_read_is_versioned_and_does_not_run_solver(self):
        s=self.app.engineering.skill(self.owner,'blender-enclosure')
        self.assertEqual('read_not_execution',s['status']);self.assertEqual(64,len(s['sha256']))
        self.assertEqual([],self.app.engineering.jobs())
        snap=self.trace()
        self.assertEqual(s['sha256'],snap['capability_events'][0]['data']['sha256'])
        a=analyze(snap)
        self.assertEqual('skill',a['timeline'][0]['category']);self.assertEqual('skill_read',a['timeline'][0]['label'])

    def test_retry_preserves_original_revision_and_restart_does_not_replay(self):
        body={'engine':'blender','operation_id':'stable-retry','design_revision':1}
        with patch.object(self.app.products,'context',return_value={'proposal':{'revision':1}}),patch.object(self.app.engineering,'run') as execute:
            job=self.app.engineering.submit(self.owner,body)
            deadline=time.time()+2
            while execute.call_count<1 and time.time()<deadline:time.sleep(.01)
            self.assertEqual(1,execute.call_count)
        with patch.object(self.app.products,'context',return_value={'proposal':{'revision':2}}):
            self.assertEqual(job['id'],self.app.engineering.submit(self.owner,body)['id'])
            with self.assertRaisesRegex(ValueError,'STALE'):
                self.app.engineering.submit(self.owner,{**body,'operation_id':'new'})
        self.app.engineering.event(self.owner,job['id'],'process_spawned',{'pid':12345})
        restarted=Engineering(self.app)
        self.assertEqual('UNKNOWN',restarted.get(self.owner,job['id'])['status'])
        with patch('bfworld.agentlab.engineering.os.killpg'):
            with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'):
                restarted.submit(self.owner,{'engine':'blender','operation_id':'after-restart'})
        self.assertEqual(job['id'],restarted.submit(self.owner,body)['id'])

    def test_artifact_tamper_and_setup_failure_stay_failures(self):
        with patch.object(self.app.engineering,'run'):
            job=self.app.engineering.submit(self.owner,{'engine':'blender','operation_id':'setup-failure'})
        directory=self.app.engineering.root/job['id'];directory.mkdir()
        self.app.engineering.run(job['id'],self.owner)
        self.assertEqual('FAILED',self.app.engineering.get(self.owner,job['id'])['status'])
        (directory/'model.glb').write_bytes(b'changed')
        with self.app.store.connect() as db:
            db.execute('UPDATE engineering_jobs SET result=? WHERE id=?',(json.dumps({'artifacts':[{'name':'model.glb','sha256':'0'*64}]}),job['id']))
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):
            self.app.engineering.artifact(self.owner,job['id'],'model.glb')

    def test_real_pi_registers_engineering_and_reads_skill_without_paid_provider(self):
        requests=[]
        def fake(owner,payload,on_chunk=None):
            requests.append(payload);step=len(requests)
            name='bf_engineering';args={'action':'inspect'} if step==1 else {'action':'skill','skill_id':'blender-enclosure'}
            base={'id':'fixture-'+str(step),'object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
            delta={'role':'assistant','tool_calls':[{'index':0,'id':'call-'+str(step),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]} if step<3 else {'role':'assistant','content':'已读取尺寸模板，尚未执行渲染。'}
            on_chunk({**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]})
            on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if step<3 else 'stop'}]})
            on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':5,'total_tokens':25}})
            return {'model':MODEL,'usage':{'prompt_tokens':20,'completion_tokens':5,'total_tokens':25}}
        self.app.provider.complete=fake
        c=self.app.conversations.create('读取工程能力和 Blender Skill',None,'engineering-tools')
        end=time.time()+25
        while c['id'] in self.app.conversations.starting and time.time()<end:time.sleep(.05)
        d=self.app.conversations.detail(c['id'])
        self.assertEqual('IDLE',d['status'],d['error']);self.assertEqual(3,len(requests))
        self.assertIn('bf_engineering',{t['function']['name'] for t in requests[0]['tools']})
        self.assertEqual(1,len(self.app.engineering.events(c['id'])))
        self.assertEqual('participant',self.app.engineering.events(c['id'])[0]['data']['initiator'])
        schema=next(t for t in requests[0]['tools'] if t['function']['name']=='bf_engineering')
        self.assertIn('jlceda',json.dumps(schema));self.assertIn('parameters',json.dumps(schema))
        s=TraceReview(self.app).snapshot(c['id']);a=analyze(s,[],self.app.engineering.events(c['id']))
        self.assertIn('bf_engineering',a['registered_tools']);self.assertEqual(2,a['coverage']['timed_tools'])
        self.assertEqual(0,self.app.provider.status()['calls']);self.assertEqual([],self.app.engineering.jobs())

    def test_operator_cannot_label_manual_job_as_agent(self):
        import sys
        with patch.object(self.app.engineering,'run'),patch('bfworld.agentlab.engineering.BLENDER',Path(sys.executable)):
            code,j=self.request('/api/engineering',{'action':'run','engine':'blender','operation_id':'operator-source','initiator':'participant'})
            self.assertEqual(202,code,j)
            self.assertEqual('operator',j['initiator']);self.assertIsNone(j['turn_id'])


if __name__=='__main__':unittest.main()
