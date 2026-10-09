import json
import sqlite3
import tempfile
import time
import unittest
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from bfworld.agentlab.server import Workbench,handler
from bfworld.agentlab.store import Store,canonical,identity
from bfworld.agentlab.organization import Organization
from bfworld.agentlab.paper_sessions import PaperSessions,ReadOnlyStore
from bfworld.agentlab.literature_campaign import digest
from bfworld.agentlab import budget_policy
from unittest.mock import patch


class PaperSessionsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();base=Path(self.temp.name)
        self.study=base/'study';self.source=Workbench(self.study/'runtime/state')
        self.source.stop.set();self.source.lock.close()
        self.production=Workbench(base/'production/state');self.production.stop.set();self.production.lock.close()
        self.folder=self.production.organization.create_folder('Ten paper Pi tasks')
        self.owners=['pi-chat-'+format(i,'016x') for i in range(1,11)]
        authority={'schema_version':'bf-ten-paper-continuation-authority-v1','direct_user_authorization':'Start ten original Pi tasks; temporarily defer usage reconciliation',
            'created':time.time()-10,'usd_cap_per_original_owner':30,'additional_wall_seconds_per_original_owner':21600,
            'defer_usage_reconciliation':True,'unknown_rows_and_full_reservations_preserved':True,'no_fee_reset':True,
            'owners':[{'paper_id':f'P{i:02}','owner':owner} for i,owner in enumerate(self.owners,1)]}
        path=self.study/'campaign/parallel-20261009';path.mkdir(parents=True)
        (path/'authorization.json').write_text(canonical(authority))
        with self.source.store.connect() as db:
            for i,owner in enumerate(self.owners,1):
                db.execute('INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?)',(owner,f'op{i}',f'Paper {i}',None,time.time(),time.time(),'RUNNING' if i==1 else 'IDLE',None,None))
            db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?)',('unknown',self.owners[0],time.time(),'hash',.12,0,'UNKNOWN',None,None,'retained'))
        self.registration={'schema_version':'bf-paper-session-registration-v1','study_root':str(self.study),
            'authorization_sha256':digest(path/'authorization.json'),'folder_id':self.folder['id'],'folder_name':self.folder['name'],
            'papers':[{'paper':f'P{i:02}','owner':owner,'title':f'P{i:02} title'} for i,owner in enumerate(self.owners,1)]}
        self.save_registration()
        (path/'READY.json').write_text(canonical({'status':'PASS','commands':{f'P{i:02}':{'phase':'delivery'} for i in range(1,11)}}))

    def tearDown(self):self.temp.cleanup()

    def save_registration(self):
        (self.production.store.root/'paper-sessions.json').write_text(canonical(self.registration))

    def router(self):return PaperSessions(self.production,self.study)

    def rows_hash(self):
        with self.source.store.connect() as db:
            return identity({table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in ['conversations','model_requests','engineering_jobs','product_result_index','chat_contexts']})

    def test_ten_original_ids_and_separate_folder(self):
        rows=self.router().list()
        self.assertEqual([r['id'] for r in rows],self.owners)
        self.assertEqual({r['folder_id'] for r in rows},{self.folder['id']})
        self.assertTrue(all(r['paper_session'] and not r['legacy'] for r in rows))

    def test_observer_keeps_active_status_unknown_fees_and_original_context(self):
        before=self.rows_hash();router=self.router();router.list()
        value=router.detail(self.owners[0]);router.view().results.inspect(self.owners[0])
        self.assertEqual(value['status'],'RUNNING');self.assertEqual(value['cost']['liability_usd'],.12)
        self.assertEqual(before,self.rows_hash())

    def test_wall_expiry_does_not_restore_cancelled_cost_or_token_limits(self):
        policy={'schema_version':'bf-model-unbounded-policy-v1','mode':'unbounded','authorized_by':'direct-user',
            'direct_user_authorization':'取消累计费用和token上限','scope':'owners','owners':self.owners,
            'cumulative_usd_cap':None,'cumulative_token_cap':None,'request_count_cap':None,'request_usd_cap':None,
            'fees_reset':False,'unknown_reservations_preserved':True}
        with self.source.store.connect() as db:budget_policy.install(db,policy)
        router=self.router();before=self.rows_hash()
        with patch('bfworld.agentlab.literature_continuation.time.time',return_value=time.time()+21601):
            value=router.detail(self.owners[0])
        self.assertFalse(value['readiness']['ready'])
        self.assertIn('PAPER_CONTINUATION_WINDOW_CLOSED',value['readiness']['reasons'])
        self.assertIsNone(value['cost']['cap_usd']);self.assertIsNone(value['readiness']['token_limit'])
        self.assertTrue(value['cost']['unbounded']);self.assertEqual(.12,value['cost']['liability_usd'])
        self.assertEqual(before,self.rows_hash())

    def test_reader_rejects_sql_mutations(self):
        reader=ReadOnlyStore(self.source.store.root)
        with reader.connect() as db:
            with self.assertRaises(sqlite3.OperationalError):db.execute("UPDATE conversations SET status='IDLE'")

    def test_registration_cannot_replace_a_paper_owner(self):
        self.registration['papers'][1]['owner']=self.owners[0];self.save_registration()
        with self.assertRaisesRegex(ValueError,'OWNER_SCOPE'):self.router()

    def test_tampered_authorization_rejected(self):
        p=self.study/'campaign/parallel-20261009/authorization.json';p.write_text(p.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'AUTHORITY_CHANGED'):self.router()

    def test_foreign_owner_and_arbitrary_path_are_not_federated(self):
        router=self.router()
        self.assertIsNone(router.target('/api/conversations/pi-chat-ffffffffffffffff',{}))
        with self.assertRaises(PermissionError):router.detail('pi-chat-ffffffffffffffff')
        with self.assertRaises(PermissionError):router.view().results.file(self.owners[0],'../../hidden.json')

    def test_idempotent_queue_does_not_dispatch_or_reset_costs(self):
        before=self.rows_hash();router=self.router();owner=self.owners[1]
        item=router.enqueue(owner,'same operation','Fix this paper only')
        self.assertEqual(item,router.enqueue(owner,'same operation','Fix this paper only'))
        self.assertEqual(router.detail(owner)['status'],'QUEUED')
        self.assertEqual(before,self.rows_hash())
        with self.assertRaisesRegex(ValueError,'OPERATION_CONFLICT'):router.enqueue(owner,'same operation','Different text')

    def test_existing_active_run_is_observed_without_duplicate_resume(self):
        router=self.router();item=router.enqueue(self.owners[0],'initial continuation')
        self.assertEqual(item['status'],'OBSERVING_EXISTING_RUN')
        self.assertEqual(router.detail(self.owners[0])['status'],'RUNNING')

    def test_expired_window_allows_reading_but_rejects_dispatch(self):
        p=self.study/'campaign/parallel-20261009/authorization.json';value=json.loads(p.read_text());value['created']=time.time()-21610;p.write_text(canonical(value))
        self.registration['authorization_sha256']=digest(p);self.save_registration();router=self.router()
        self.assertEqual(len(router.list()),10)
        with self.assertRaisesRegex(ValueError,'WINDOW_EXPIRED'):router.enqueue(self.owners[1],'cannot start')

    def test_stop_cancels_pending_and_preserves_source_journal(self):
        router=self.router();owner=self.owners[1];router.enqueue(owner,'pending')
        before=self.rows_hash();router.cancel_pending(owner)
        self.assertEqual(router.requests(owner)[0]['status'],'CANCELLED')
        router.cancel_pending(self.owners[0])
        self.assertEqual(before,self.rows_hash())
        self.assertEqual(router.requests(self.owners[0]),[])

    def test_live_results_read_without_an_index_writer(self):
        router=self.router();owner=self.owners[1];reader=router.view()
        first=reader.results.version(owner)['version']
        with self.source.store.connect() as db:
            db.execute("UPDATE conversations SET status='FAILED' WHERE id=?",(owner,))
            request={'engine':'engineering-project','design_revision':None,'project':{'manifest':{'kind':'cadquery','files':[]},'sources':{}}}
            db.execute('INSERT INTO engineering_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',('eng-fixture',owner,'fixture',identity(request),canonical(request),'SUCCEEDED',time.time(),time.time(),time.time(),canonical({'artifacts':[]}),None))
        self.assertNotEqual(first,reader.results.version(owner)['version'])
        self.assertEqual(router.detail(owner)['source_status'],'FAILED')
        before=self.rows_hash();catalog=reader.results.inspect(owner)
        self.assertIn('eng-fixture',[r['id'] for r in catalog['results']])
        self.assertEqual(before,self.rows_hash())

    def http_request(self,path,body=None,participant=False):
        router=self.router();server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.production,router))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        token=self.production.store.issue('test-participant') if participant else (self.production.store.root/'operator.token').read_text()
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
            data=canonical(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            try:
                with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.loads(response.read())
            except urllib.error.HTTPError as exc:return exc.code,json.loads(exc.read())
        finally:server.shutdown();server.server_close();thread.join()

    def test_http_sidebar_has_ten_original_sessions(self):
        status,value=self.http_request('/api/conversations')
        self.assertEqual(status,200);self.assertEqual(len(value['sessions']),10)
        self.assertEqual({r['id'] for r in value['sessions']},set(self.owners))
        self.assertEqual(len(value['folders']),1)

    def test_http_messages_queue_original_owner_without_dispatch(self):
        owner=self.owners[1];before=self.rows_hash()
        status,value=self.http_request('/api/conversations/'+owner+'/messages',{'operation_id':'user-msg','text':'Repair only P02'})
        self.assertEqual(status,202);self.assertEqual(value['owner'],owner)
        self.assertEqual(value['status'],'QUEUED');self.assertEqual(before,self.rows_hash())

    def test_http_operator_only_and_no_direct_product_mutation(self):
        status,_=self.http_request('/api/conversations/'+self.owners[0],participant=True)
        self.assertEqual(status,403)
        before=self.rows_hash();status,value=self.http_request('/api/product',{'session_id':self.owners[0],'action':'write'})
        self.assertEqual(status,403);self.assertIn('REQUIRES_PI_MESSAGE',value['error']);self.assertEqual(before,self.rows_hash())

    def test_unregistered_runtime_does_not_construct_a_source_workbench(self):
        (self.production.store.root/'paper-sessions.json').unlink()
        router=self.router();self.assertEqual(router.list(),[]);self.assertIsNone(router.view())


if __name__=='__main__':unittest.main()
