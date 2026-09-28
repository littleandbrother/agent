import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from bfworld.agentlab.server import Workbench,handler
from bfworld.agentlab.experiments import BASELINE_DESIGN,BASELINE_POLICY

class HTTPBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Workbench(Path(self.tmp.name)/'state')
        self.app.store.grant('alice',['dev-01'],2,time.time()+60)
        self.app.store.grant('bob',['dev-01'],1,time.time()+60)
        self.alice=self.app.store.issue('alice');self.bob=self.app.store.issue('bob')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()
    def req(self,path,body=None,token=None,origin=None):
        headers={'Content-Type':'application/json','Authorization':'Bearer '+(token or self.alice)}
        if origin:headers['Origin']=origin
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,
            data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_authenticated_real_experiment_and_artifact_boundary(self):
        self.assertEqual(403,self.req('/api/state',token='bad')[0])
        files={'design.json':json.dumps(BASELINE_DESIGN),'policy.py':BASELINE_POLICY}
        self.assertEqual(403,self.req('/api/snapshots',{'files':files},origin='http://attacker.test')[0])
        _,snap=self.req('/api/snapshots',{'files':files})
        body={'task_id':'dev-01','operation_id':'op-1','snapshot_id':snap['snapshot_id']}
        _,job=self.req('/api/jobs',body)
        self.assertEqual(job['id'],self.req('/api/jobs',body)[1]['id'])
        self.assertEqual(403,self.req('/api/jobs/'+job['id'],token=self.bob)[0])
        self.assertEqual(job['id'],self.req('/api/operations/op-1')[1]['id'])
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            _,result=self.req('/api/jobs/'+job['id'])
            if result['status'] not in ('QUEUED','RUNNING'):break
            time.sleep(.05)
        self.assertEqual('SUCCEEDED',result['status'])
        self.assertEqual('FAIL',result['result']['design_status'])
        self.assertEqual(403,self.req('/api/jobs/'+job['id']+'/artifact?name=run.private.json')[0])
        self.assertEqual(1,self.req('/api/budget')[1]['remaining_experiments'])
    def test_real_cancellation_confirmed_by_worker(self):
        files={'design.json':json.dumps(BASELINE_DESIGN),'policy.py':"def plan(obs):\n import time\n time.sleep(1)\n return {'action':'wait','duration_s':.1}\n"}
        _,snap=self.req('/api/snapshots',{'files':files})
        _,job=self.req('/api/jobs',{'task_id':'dev-01','operation_id':'cancel','snapshot_id':snap['snapshot_id']})
        self.req('/api/jobs/'+job['id']+'/cancel',{})
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            _,value=self.req('/api/jobs/'+job['id'])
            if value['status']=='CANCELLED':break
            time.sleep(.05)
        self.assertEqual('CANCELLED',value['status'])
        self.assertTrue(self.req('/api/jobs/'+job['id']+'/cancel',{})[1]['terminal_confirmed'])

    def test_closed_paid_window_rejects_before_creating_session(self):
        closed=self.app.store.root.parent/'paid-window-closed.json'
        closed.write_text(json.dumps({'reason':'MODEL_TOKEN_BUDGET'}))
        token=(self.app.store.root/'operator.token').read_text()
        status,value=self.req('/api/solve',{'task_id':'dev-01'},token=token)
        self.assertEqual(status,400)
        self.assertEqual(value['error'],'PAID_WINDOW_CLOSED')
        state=self.req('/api/state',token=token)[1]
        self.assertEqual(state['model']['closed']['reason'],'MODEL_TOKEN_BUDGET')
        self.assertNotIn('requests',state['model'])
        with self.app.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)

    def test_reference_case_is_operator_only_and_hash_bound(self):
        from bfworld.agentlab.pluck_case import digest
        root=self.app.store.root.parent/'reference-cases/pluck-v1';root.mkdir(parents=True)
        artifact=root/'result.json';artifact.write_text('{"hardware_verified":false}')
        (root/'receipt.json').write_text(json.dumps({'artifacts':[{'path':'result.json','sha256':digest(artifact)}]}))
        self.assertEqual(403,self.req('/api/reference-case')[0])
        self.assertEqual(403,self.req('/api/reference-case/artifact?name=result.json')[0])
        token=(self.app.store.root/'operator.token').read_text()
        self.assertTrue(self.req('/api/reference-case',token=token)[1]['artifact_integrity'])
        self.assertEqual((200,{'hardware_verified':False}),self.req('/api/reference-case/artifact?name=result.json',token=token))
        self.assertEqual(400,self.req('/api/reference-case/artifact?name=../../private.json',token=token)[0])
        artifact.write_text('{"hardware_verified":true}')
        self.assertFalse(self.req('/api/reference-case',token=token)[1]['artifact_integrity'])
        self.assertEqual(400,self.req('/api/reference-case/artifact?name=result.json',token=token)[0])

if __name__=='__main__':unittest.main()
