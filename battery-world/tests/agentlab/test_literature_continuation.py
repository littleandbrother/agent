import copy,json,sqlite3,tempfile,unittest
from pathlib import Path
from bfworld.agentlab.literature_campaign import digest
from bfworld.agentlab.store import identity
from bfworld.agentlab.literature_continuation import validate_authority,owner_window,prior_requests_allowed,retained_unknowns,renew_owner
from bfworld.agentlab.literature_native import continuation_deadline,native_route_allowed

class ContinuationTests(unittest.TestCase):
    def test_actual_pi_eda_endpoint_is_available_only_in_bound_eda_phase(self):
        self.assertTrue(native_route_allowed('/api/eda-cli','eda'))
        for phase in (None,'firmware','delivery','engineering-review'):
            self.assertFalse(native_route_allowed('/api/eda-cli',phase))
    def test_native_http_route_cannot_expose_operator_configuration(self):
        for route in ('/api/settings','/api/provider','/api/organization','/api/tasks'):
            self.assertFalse(native_route_allowed(route,'eda'))
    def test_existing_native_engineering_routes_remain_available(self):
        for route in ('/api/engineering','/api/assembly','/api/product','/v1/chat/completions'):
            self.assertTrue(native_route_allowed(route,'delivery'))
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.target=self.root/'campaign/native-runs/P01-original';self.target.mkdir(parents=True)
        self.original={'usd_cap':30,'expires':10};(self.target/'authorization.json').write_text(json.dumps(self.original))
        self.scope={'schema_version':'bf-ten-paper-continuation-authority-v1','direct_user_authorization':'继续十篇；暂不让usage阻塞',
                    'created':100,'usd_cap_per_original_owner':30,'additional_wall_seconds_per_original_owner':21600,
                    'defer_usage_reconciliation':True,'unknown_rows_and_full_reservations_preserved':True,'no_fee_reset':True,
                    'authority_file':'operator.json','authority_sha256':'operator-sha','owners':[{'paper_id':f'P{i:02}', 'owner':f'pi-chat-{i}',
                    'original_authorization':{'path':str((self.target/'authorization.json').relative_to(self.root)), 'sha256':digest(self.target/'authorization.json')}} for i in range(1,11)]}
        self.unknown={'id':'unknown','owner':'pi-chat-2','status':'UNKNOWN','reserved':.11,'charged':0,'usage':None}
    def test_original_deadline_needs_new_explicit_authority(self):
        with self.assertRaises(ValueError):continuation_deadline(self.original,101)
        window=owner_window(self.root,self.scope,'P01','pi-chat-1',self.target,101)
        self.assertEqual(21700,continuation_deadline(self.original,101,window));self.assertEqual(10,window['original_expires'])
        self.assertEqual(self.original,json.loads((self.target/'authorization.json').read_text()))
    def test_expired_or_future_authority_cannot_dispatch(self):
        for now in (99,21700):
            with self.assertRaisesRegex(ValueError,'WINDOW_EXPIRED'):validate_authority(self.scope,now)
    def test_monetary_reset_and_changed_duration_rejected(self):
        for key,value in [('usd_cap_per_original_owner',60),('no_fee_reset',False),('additional_wall_seconds_per_original_owner',43200),('defer_usage_reconciliation',False)]:
            scope=copy.deepcopy(self.scope);scope[key]=value
            with self.assertRaises(ValueError):validate_authority(scope,101)
    def test_each_paper_has_distinct_original_owner(self):
        scope=copy.deepcopy(self.scope);scope['owners'][1]['owner']='pi-chat-1'
        with self.assertRaisesRegex(ValueError,'TEN_ORIGINAL_OWNERS'):validate_authority(scope,101)
    def test_foreign_owner_or_paper_cannot_renew(self):
        with self.assertRaisesRegex(ValueError,'ORIGINAL_OWNER'):owner_window(self.root,self.scope,'P01','pi-chat-2',self.target,101)
    def test_changed_original_authorization_cannot_renew(self):
        (self.target/'authorization.json').write_text('{"usd_cap":30,"expires":11}')
        with self.assertRaisesRegex(ValueError,'AUTHORIZATION_CHANGED'):owner_window(self.root,self.scope,'P01','pi-chat-1',self.target,101)
    def test_unknown_keeps_full_reservation_and_null_usage(self):
        before=copy.deepcopy(self.unknown)
        records=retained_unknowns([self.unknown],[],self.scope,101)
        self.assertEqual(.11,records[0]['retained_reservation_usd']);self.assertEqual(before,self.unknown)
    def test_foreign_unknown_is_not_covered_by_temporary_policy(self):
        self.unknown['owner']='another-task'
        with self.assertRaisesRegex(ValueError,'NOT_AUTHORIZED'):retained_unknowns([self.unknown],[],self.scope,101)
    def test_changed_historical_unknown_cannot_be_excused_by_scope(self):
        old=[{'id':'unknown','original_row_sha256':identity(self.unknown)}];self.unknown['reserved']=.12
        with self.assertRaisesRegex(ValueError,'LIABILITY_CHANGED'):retained_unknowns([self.unknown],old,self.scope,101)
    def test_missing_authority_still_blocks_unknown(self):
        with self.assertRaises(ValueError):retained_unknowns([self.unknown],[],None,101)
        self.assertFalse(prior_requests_allowed([self.unknown],None,'pi-chat-2'))
    def test_inflight_request_cannot_be_resumed_as_missing_usage(self):
        self.assertTrue(prior_requests_allowed([self.unknown],self.scope,'pi-chat-2'))
        self.unknown['status']='DISPATCHED';self.assertFalse(prior_requests_allowed([self.unknown],self.scope,'pi-chat-2'))
    def test_authorized_window_does_not_change_fee_rows_or_caps(self):
        db=sqlite3.connect(':memory:');self.addCleanup(db.close);db.row_factory=sqlite3.Row
        db.executescript('CREATE TABLE research_model_owners(owner,protocol);CREATE TABLE owner_model_caps(owner,max_usd);CREATE TABLE research_model_studies(protocol,expires,authorization);CREATE TABLE research_usage_continuations(protocol PRIMARY KEY,created,expires,authorization);CREATE TABLE research_usage_carryforwards(protocol,request_id,original_row_hash,authorization,created,PRIMARY KEY(protocol,request_id));CREATE TABLE model_limits(id,total_usd,expires);CREATE TABLE model_requests(id,status,reserved,charged,usage);')
        db.execute('INSERT INTO research_model_owners VALUES(?,?)',('pi-chat-1','original-study'))
        db.execute('INSERT INTO owner_model_caps VALUES(?,?)',('pi-chat-1',30))
        db.execute('INSERT INTO research_model_studies VALUES(?,?,?)',('original-study',10,'original-auth'))
        db.execute('INSERT INTO model_limits VALUES(1,300,10)')
        db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?)',('unknown','UNKNOWN',.11,0,None))
        before=[tuple(r) for r in db.execute('SELECT * FROM model_requests')]
        window=owner_window(self.root,self.scope,'P01','pi-chat-1',self.target,101)
        records=retained_unknowns([self.unknown],[],self.scope,101)
        renew_owner(db,'pi-chat-1',window,records,self.scope)
        self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM model_requests')])
        self.assertEqual(30,db.execute('SELECT max_usd FROM owner_model_caps').fetchone()[0])
        self.assertEqual(300,db.execute('SELECT total_usd FROM model_limits').fetchone()[0])
        self.assertEqual(21700,db.execute('SELECT expires FROM research_model_studies').fetchone()[0])
        self.assertEqual(identity(self.unknown),db.execute('SELECT original_row_hash FROM research_usage_carryforwards').fetchone()[0])
        renew_owner(db,'pi-chat-1',window,records,self.scope)
        self.assertEqual(1,db.execute('SELECT count(*) FROM research_usage_carryforwards').fetchone()[0])

if __name__=='__main__':unittest.main()
