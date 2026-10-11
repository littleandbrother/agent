import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from bfworld.agentlab import budget_policy
from bfworld.agentlab.provider import Provider
from bfworld.agentlab.store import Store
from bfworld.agentlab.literature_campaign import owner_budget, digest
from bfworld.agentlab.literature_continuation import load_authority, owner_window, AUTHORITY, BUDGET_AUTHORITY
from bfworld.agentlab.literature_native import continuation_deadline


def policy(owners=None):
    return {'schema_version': 'bf-model-unbounded-policy-v1', 'mode': 'unbounded',
            'authorized_by': 'direct-user', 'direct_user_authorization': '取消累计费用和token上限',
            'scope': 'owners' if owners is not None else 'interactive', 'owners': owners or [],
            'cumulative_usd_cap': None, 'cumulative_token_cap': None, 'request_count_cap': None,
            'request_usd_cap': None, 'fees_reset': False, 'unknown_reservations_preserved': True}


class UnboundedBudget(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Store(self.root/'state');self.provider=Provider(self.store)
        self.owner='pi-chat-1234567890abcdef';self.store.grant(self.owner,[],6,time.time()+600)
        key=self.root/'test-key';key.write_text('test-only')
        patcher=patch('bfworld.agentlab.provider.KEY_PATH',key);patcher.start();self.addCleanup(patcher.stop)
        with self.store.connect() as db:
            db.execute('CREATE TABLE chat_messages(id TEXT PRIMARY KEY,conversation TEXT,status TEXT)')
            db.execute('INSERT INTO chat_messages VALUES(?,?,?)',('message',self.owner,'QUEUED'))
            db.execute('INSERT INTO owner_model_caps VALUES(?,?)',(self.owner,30))
        self.provider.recovery.issue(self.owner,'message')
        self.payload={'model':'deepseek-flash','messages':[{'role':'user','content':'design'}],'max_tokens':4096}

    def enable(self, value=None):
        with self.store.connect() as db:budget_policy.install(db,value or policy([self.owner]))

    def call(self):
        response={'model':'deepseek-flash','usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}
        with patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(json.dumps(response).encode())) as opening:
            self.provider.complete(self.owner,self.payload)
        return json.loads(opening.call_args.args[0].data)

    def add_large_history(self):
        with self.store.connect() as db:
            for n in range(140):
                db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (f'old-{n}',self.owner,time.time(),'old',100.,100.,'SETTLED',json.dumps({'total_tokens':10**9}),None,None))
            db.execute('UPDATE model_limits SET total_usd=.001,request_usd=.0000001,max_tokens=1')

    def test_authorized_history_over_fees_tokens_and_128_calls_still_dispatches(self):
        self.enable();self.add_large_history()
        with self.store.connect() as db:before=[tuple(r) for r in db.execute('SELECT * FROM model_requests ORDER BY id')]
        self.call()
        with self.store.connect() as db:
            self.assertEqual(before,[tuple(r) for r in db.execute("SELECT * FROM model_requests WHERE id LIKE 'old-%' ORDER BY id")])
            self.assertEqual(30,db.execute('SELECT max_usd FROM owner_model_caps WHERE owner=?',(self.owner,)).fetchone()[0])
        current=self.provider.status(self.owner)
        self.assertIsNone(current['limits']['total_usd']);self.assertIsNone(current['limits']['max_tokens'])
        self.assertEqual(.001,current['configured_limits']['total_usd'])
        self.assertEqual(141,current['calls']);self.assertGreater(current['upper_bound_usd'],14000)

    def test_explicit_owner_can_override_its_old_research_cost_without_mutating_it(self):
        self.enable()
        with self.store.connect() as db:
            db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',('study',0,time.time()+600,.0000001,'deepseek-flash','original'))
            db.execute('INSERT INTO research_model_owners VALUES(?,?,?)',(self.owner,'study','task'))
        self.call()
        with self.store.connect() as db:self.assertEqual(.0000001,db.execute('SELECT max_usd FROM research_model_studies').fetchone()[0])

    def test_interactive_default_does_not_override_frozen_research_study(self):
        self.enable(policy())
        with self.store.connect() as db:
            db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',('study',0,time.time()+600,.0000001,'deepseek-flash','original'))
            db.execute('INSERT INTO research_model_owners VALUES(?,?,?)',(self.owner,'study','task'))
        with self.assertRaisesRegex(ValueError,'RESEARCH_MODEL_USD_BUDGET'):self.call()
        self.assertEqual(0,self.provider.status()['calls'])

    def test_interactive_default_applies_to_current_and_future_user_conversations(self):
        self.enable(policy());self.add_large_history();self.call()
        with self.store.connect() as db:
            self.assertIsNotNone(budget_policy.for_owner(db,'pi-chat-new'))
            self.assertIsNone(budget_policy.for_owner(db,'operator'))

    def test_scoped_unbounded_setting_does_not_release_other_owner(self):
        self.enable(policy(['pi-chat-other']));self.add_large_history()
        with self.assertRaisesRegex(ValueError,'CHAT_TURN_REQUEST_CAP'):self.call()

    def test_unknown_is_not_cleared_or_implicitly_excused_by_unbounded_cost(self):
        self.enable()
        with self.store.connect() as db:
            db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?)',('unknown',self.owner,0,'old',.11,0,'UNKNOWN',None,None,'lost output'))
            before=tuple(db.execute('SELECT * FROM model_requests').fetchone())
        with self.assertRaisesRegex(ValueError,'PROVIDER_USAGE_UNKNOWN_STOP'):self.call()
        with self.store.connect() as db:self.assertEqual(before,tuple(db.execute('SELECT * FROM model_requests').fetchone()))

    def test_expired_user_turn_remains_blocked(self):
        self.enable()
        with self.store.connect() as db:db.execute('UPDATE interactive_leases SET expires=0')
        with self.assertRaisesRegex(ValueError,'CHAT_TURN_WALL_BUDGET'):self.call()
        self.assertEqual(0,self.provider.status()['calls'])

    def test_model_output_limit_remains_bounded_per_request(self):
        self.enable();self.payload['max_tokens']=10**9
        body=self.call();self.assertEqual(8192,body['max_tokens'])

    def test_model_context_limit_remains_bounded_per_request(self):
        self.enable();self.payload['messages'][0]['content']='required '*100000
        with self.assertRaisesRegex(ValueError,'MODEL_CONTEXT_BYTE_LIMIT'):self.call()
        self.assertEqual(0,self.provider.status()['calls'])

    def test_malformed_authority_and_numeric_fake_unlimited_are_rejected(self):
        for key,value in [('direct_user_authorization',''),('fees_reset',True),('cumulative_usd_cap',10**12),('scope','all-research')]:
            bad=policy([self.owner]);bad[key]=value
            with self.assertRaises(ValueError):self.enable(bad)

    def test_no_policy_keeps_legacy_cap(self):
        with self.store.connect() as db:db.execute('UPDATE model_limits SET max_tokens=1')
        with self.assertRaisesRegex(ValueError,'MODEL_TOKEN_BUDGET'):self.call()

    def test_v2_direct_user_time_authority_supersedes_expired_lease_without_editing_it(self):
        value={**policy([self.owner]),'schema_version':'bf-model-unbounded-policy-v2',
               'wall_seconds':None,'wall_authorized_by':'direct-user','wall_unbounded':True,
               'wall_authorization_text':'持续运行 不设置时间限制','unknown_carryforward':{}}
        self.enable(value)
        with self.store.connect() as db:
            db.execute('UPDATE interactive_leases SET expires=0')
            db.execute('UPDATE grants SET expires=0 WHERE owner=?',(self.owner,))
            original=tuple(db.execute('SELECT * FROM interactive_leases').fetchone())
        (self.root/'paid-window-closed.json').write_text('{"historical":true}')
        self.call()
        with self.store.connect() as db:
            self.assertEqual(original,tuple(db.execute('SELECT * FROM interactive_leases').fetchone()))
            self.assertIsNone(self.provider.recovery.lease(db,self.owner)['expires'])
        self.assertIsNone(self.provider.status(self.owner)['limits']['expires'])
        self.assertTrue((self.root/'paid-window-closed.json').exists())

    def test_v2_explicit_historical_unknown_hash_is_preserved_and_new_unknown_still_blocks(self):
        from bfworld.agentlab.store import identity
        with self.store.connect() as db:
            db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?)',('unknown',self.owner,0,'old',.11,0,'UNKNOWN',None,None,'lost output'))
            row=dict(db.execute('SELECT * FROM model_requests').fetchone())
        value={**policy([self.owner]),'schema_version':'bf-model-unbounded-policy-v2',
               'wall_seconds':None,'wall_authorized_by':'direct-user','wall_unbounded':True,
               'wall_authorization_text':'持续运行 不设置时间限制','unknown_carryforward':{'unknown':identity(row)}}
        self.enable(value);self.call()
        with self.store.connect() as db:
            self.assertEqual(row,dict(db.execute('SELECT * FROM model_requests WHERE id=?',('unknown',)).fetchone()))
            db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?)',('new-unknown',self.owner,0,'new',.22,0,'UNKNOWN',None,None,'new lost output'))
        with self.assertRaisesRegex(ValueError,'USAGE_UNKNOWN'):self.call()

    def test_v2_time_without_exact_direct_authorization_is_rejected(self):
        value={**policy([self.owner]),'schema_version':'bf-model-unbounded-policy-v2',
               'wall_seconds':None,'wall_authorized_by':'direct-user','wall_unbounded':True,
               'wall_authorization_text':'please continue'}
        with self.assertRaisesRegex(ValueError,'TIME_AUTH'):self.enable(value)

    def test_unbounded_owner_projection_preserves_liability_and_unknowns(self):
        rows=[{'id':'u','owner':self.owner,'charged':0,'reserved':2,'status':'UNKNOWN'}]
        result=owner_budget(rows,self.owner,cap=None)
        self.assertEqual(2,result['liability_usd']);self.assertEqual(['u'],result['unknown_requests'])
        self.assertIsNone(result['remaining_usd']);self.assertFalse(result['exhausted'])


class OriginalAuthorityAmendment(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.target=self.root/'campaign/native-runs/P01-original';self.target.mkdir(parents=True)
        self.original={'usd_cap':30,'expires':10};(self.target/'authorization.json').write_text(json.dumps(self.original))
        self.owners=[{'paper_id':f'P{i:02}','owner':f'pi-chat-{i}',
            'original_authorization':{'path':str((self.target/'authorization.json').relative_to(self.root)),
            'sha256':digest(self.target/'authorization.json')}} for i in range(1,11)]
        self.scope={'schema_version':'bf-ten-paper-continuation-authority-v1','direct_user_authorization':'继续十篇',
            'created':100,'usd_cap_per_original_owner':30,'additional_wall_seconds_per_original_owner':21600,
            'defer_usage_reconciliation':True,'unknown_rows_and_full_reservations_preserved':True,
            'no_fee_reset':True,'owners':self.owners}
        file=self.root/AUTHORITY;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(json.dumps(self.scope))
        self.amendment={**policy([r['owner'] for r in self.owners]),'original_authority_sha256':digest(file),'wall_window_changed':False}

    def save_amendment(self):
        (self.root/BUDGET_AUTHORITY).write_text(json.dumps(self.amendment))

    def test_append_only_amendment_changes_effective_cap_not_original_authority(self):
        original_bytes=(self.root/AUTHORITY).read_bytes();self.save_amendment()
        scope=load_authority(self.root,now=101);window=owner_window(self.root,scope,'P01','pi-chat-1',self.target,101)
        self.assertIsNone(window['usd_cap']);self.assertEqual(21700,continuation_deadline(self.original,101,window))
        self.assertEqual(original_bytes,(self.root/AUTHORITY).read_bytes())
        self.assertEqual(self.original,json.loads((self.target/'authorization.json').read_text()))

    def test_foreign_owner_amendment_and_changed_wall_window_are_rejected(self):
        for key,value in [('owners',['pi-chat-other']),('wall_window_changed',True),('original_authority_sha256','wrong')]:
            bad=copy.deepcopy(self.amendment);bad[key]=value
            (self.root/BUDGET_AUTHORITY).write_text(json.dumps(bad))
            with self.assertRaises(ValueError):load_authority(self.root,now=101)

    def test_unbounded_money_does_not_extend_existing_time_authorization(self):
        self.save_amendment()
        with self.assertRaisesRegex(ValueError,'WINDOW_EXPIRED'):load_authority(self.root,now=21700)

    def test_null_cap_without_real_policy_is_not_a_renewal(self):
        with self.assertRaisesRegex(ValueError,'NATIVE_RENEWAL'):
            continuation_deadline(self.original,101,{'usd_cap':None,'fees_reset':False,'expires':21700})


if __name__=='__main__':unittest.main()
