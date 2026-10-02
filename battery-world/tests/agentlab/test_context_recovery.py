import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from bfworld.agentlab.context import ContextArchive, PRODUCT_STATE_PREFIX, project_interactive
from bfworld.agentlab.provider import Provider
from bfworld.agentlab.store import Store
from bfworld.agentlab.store import canonical, identity


class ContextProjection(unittest.TestCase):
    def test_removes_completed_old_tool_details_preserves_users_text_and_active_pairs(self):
        source={'model':'deepseek-flash','messages':[
            {'role':'system','content':'Rules'}, {'role':'user','content':'Keep original constraints'},
            {'role':'assistant','content':'Checking','tool_calls':[{'id':'old','function':{'name':'read','arguments':'{}'}}]},
            {'role':'tool','tool_call_id':'old','content':'x'*140000},
            {'role':'assistant','content':'Past answer with limitations'}, {'role':'user','content':'Continue'},
            {'role':'assistant','tool_calls':[{'id':'current'}]}, {'role':'tool','tool_call_id':'current','content':'Current evidence'}]}
        original=json.dumps(source)
        projected,audit=project_interactive(source)
        self.assertEqual(original,json.dumps(source))
        self.assertEqual(['old'],audit['omitted_tool_call_ids'])
        self.assertLess(audit['projected_bytes'],2000)
        self.assertEqual(source['messages'][-3:],projected['messages'][-3:])
        self.assertIn({'role':'assistant','content':'Checking'},projected['messages'])
        self.assertIn(source['messages'][0],projected['messages'])
        self.assertIn(source['messages'][1],projected['messages'])
        self.assertIn(source['messages'][4],projected['messages'])

    def test_large_current_turn_drops_only_completed_older_pairs(self):
        messages=[{'role':'system','content':'Rules'}, {'role':'user','content':'Current request'}]
        for i in range(6):
            messages.extend([{'role':'assistant','tool_calls':[{'id':str(i),'function':{'name':'read','arguments':'{}'}}]},
                             {'role':'tool','tool_call_id':str(i),'content':'x'*30000}])
        messages.append({'role':'assistant','tool_calls':[{'id':'pending'}]})
        payload={'messages':messages};original=json.dumps(payload)
        result,audit=project_interactive(payload)
        self.assertLess(audit['projected_bytes'],104000)
        self.assertFalse(audit['current_turn_preserved'])
        self.assertEqual(original,json.dumps(payload))
        self.assertEqual(messages[-5:],result['messages'][-5:])
        self.assertIn(messages[1],result['messages'])

    def test_incomplete_parallel_exchange_is_not_deleted(self):
        payload={'messages':[{'role':'assistant','tool_calls':[{'id':'a'},{'id':'b'}]},
                             {'role':'tool','tool_call_id':'a','content':'ok'}, {'role':'user','content':'What happened?'}]}
        value,audit=project_interactive(payload)
        self.assertEqual(payload,value);self.assertEqual([],audit['omitted_tool_call_ids'])

    def test_old_assistant_prose_is_bounded_and_auditable_without_losing_requirements(self):
        messages=[{'role':'system','content':'Rules'}, {'role':'user','content':'Original dimensions and budget'}]
        for i in range(24):
            messages.append({'role':'assistant','content':str(i)+'x'*8000})
        messages += [{'role':'user','content':'Fix actual physical defects'},
                     {'role':'assistant','tool_calls':[{'id':'last'}]},
                     {'role':'tool','tool_call_id':'last','content':'Measured evidence'},
                     {'role':'assistant','tool_calls':[{'id':'pending'}]}]
        payload={'messages':messages};before=canonical(payload)
        result,audit=project_interactive(payload)
        self.assertLess(audit['projected_bytes'],104000)
        self.assertEqual(before,canonical(payload))
        for m in messages[:2]+messages[-8:]:self.assertIn(m,result['messages'])
        self.assertTrue(audit['omitted_assistant_messages'])
        for item in audit['omitted_assistant_messages']:
            self.assertEqual(identity(messages[item['source_index']]),item['sha256'])

    def test_protected_user_content_is_never_truncated_to_force_a_fit(self):
        payload={'messages':[{'role':'user','content':'x'*140000}]}
        result,audit=project_interactive(payload)
        self.assertEqual(payload,result)
        self.assertGreater(audit['projected_bytes'],128000)

    def test_recent_large_tool_results_are_readable_exactly_and_pairs_survive(self):
        messages = [{'role':'system','content':'Do not change the acceptance rules'},
                    {'role':'user','content':'保留尺寸 84 mm，检查当前版本'}]
        for i in range(2):
            messages += [{'role':'assistant','tool_calls':[{'id':str(i),'function':{'name':'read','arguments':'{"path":"assembly.json"}'}}]},
                         {'role':'tool','tool_call_id':str(i),'content':'真实尺寸与读回结果'*12000}]
        source = {'messages':messages}; before = canonical(source)
        with tempfile.TemporaryDirectory() as root:
            result, audit = project_interactive(source, ContextArchive(root, 'chat'))
            self.assertTrue(audit['fits'])
            self.assertLess(audit['projected_bytes'],104000)
            self.assertEqual(before,canonical(source))
            self.assertEqual(messages[:2],result['messages'][1:3])
            for message in messages:
                if message.get('tool_calls'):self.assertIn(message,result['messages'])
            self.assertEqual(['0','1'],[m['tool_call_id'] for m in result['messages'] if m['role']=='tool'])
            for item in audit['archived_messages']:
                saved = Path(root)/'participants/chat'/item['record_file']
                self.assertEqual(messages[item['source_index']],json.loads(saved.read_text()))
                self.assertEqual(identity(json.loads(saved.read_text())),item['sha256'])
            again, audit2 = project_interactive(source, ContextArchive(root,'chat'))
            self.assertEqual(result,again);self.assertEqual(audit,audit2)

    def test_only_tagged_state_json_is_archived_inside_system_prompt(self):
        state = {'assembly':{'parts':['真实零件'*20000]},'current_revision':14}
        prefix = 'Original rules: preserve units, budget and acceptance.\n'
        suffix = '\nStop when answered.\nFolder instructions: do not change requirements.'
        prompt = prefix+PRODUCT_STATE_PREFIX+canonical(state)+suffix
        payload = {'messages':[{'role':'system','content':prompt},{'role':'user','content':'继续当前任务'}]}
        with tempfile.TemporaryDirectory() as root:
            result,audit = project_interactive(payload,ContextArchive(root,'chat'))
            reduced = result['messages'][1]['content']
            self.assertTrue(audit['fits'])
            self.assertTrue(reduced.startswith(prefix+PRODUCT_STATE_PREFIX))
            self.assertTrue(reduced.endswith(suffix))
            self.assertEqual(payload['messages'][-1],result['messages'][-1])
            item = audit['archived_messages'][0]
            self.assertEqual(state,json.loads((Path(root)/'participants/chat'/item['record_file']).read_text()))
            self.assertEqual(identity(payload['messages'][0]),item['source_message_sha256'])

    def test_large_recent_assistant_content_is_archived_not_silently_dropped(self):
        m = {'role':'assistant','content':'历史解释'*25000}
        with tempfile.TemporaryDirectory() as root:
            result,audit = project_interactive({'messages':[{'role':'user','content':'保留要求'},m]},ContextArchive(root,'chat'))
            self.assertTrue(audit['fits'])
            item = audit['archived_messages'][0]
            self.assertEqual(m,json.loads((Path(root)/'participants/chat'/item['record_file']).read_text()))
            self.assertIn('archived_not_deleted',result['messages'][-1]['content'])

    def test_archive_never_trims_rules_users_or_incomplete_parallel_calls(self):
        for messages in [
            [{'role':'system','content':'规则'*100000}],
            [{'role':'user','content':PRODUCT_STATE_PREFIX+canonical({'requirements':'完整要求'*20000})}],
            [{'role':'system','content':PRODUCT_STATE_PREFIX+'invalid JSON '+'x'*150000}],
            [{'role':'assistant','tool_calls':[{'id':'a'},{'id':'b'}]},
             {'role':'tool','tool_call_id':'a','content':'x'*150000}]
        ]:
            with self.subTest(role=messages[0]['role']),tempfile.TemporaryDirectory() as root:
                payload={'messages':messages}
                result,audit=project_interactive(payload,ContextArchive(root,'chat'))
                self.assertEqual(payload,result);self.assertFalse(audit['fits'])
                self.assertEqual([],audit['archived_messages'])

    def test_archive_rejects_changed_or_symlinked_records(self):
        with tempfile.TemporaryDirectory() as root:
            archive=ContextArchive(root,'chat');value={'data':'Original'}
            record=archive(value);path=Path(root)/'participants/chat'/record['record_file']
            path.chmod(0o600);path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'CONFLICT'):archive(value)
            path.unlink();path.symlink_to(Path(root)/'unrelated')
            with self.assertRaisesRegex(ValueError,'CONFLICT'):archive(value)
            path.unlink();path.parent.rmdir();path.parent.symlink_to(Path(root))
            with self.assertRaisesRegex(ValueError,'SYMLINK'):archive(value)
            with self.assertRaisesRegex(ValueError,'OWNER_INVALID'):ContextArchive(root,'../other')


class TurnBudget(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=Store(self.root/'state');self.provider=Provider(self.store)
        self.key=self.root/'key';self.key.write_text('test-only')
        self.key_patch=patch('bfworld.agentlab.provider.KEY_PATH',self.key);self.key_patch.start()
        with self.store.connect() as db:db.execute('CREATE TABLE chat_messages(id TEXT PRIMARY KEY,conversation TEXT,status TEXT)')
        self.store.grant('chat',[],6,time.time()+600)
        self.payload={'model':'deepseek-flash','messages':[{'role':'user','content':'hello'}],'max_tokens':4096}

    def tearDown(self):self.key_patch.stop();self.temp.cleanup()

    def message(self,mid):
        with self.store.connect() as db:db.execute('INSERT INTO chat_messages VALUES(?,?,?)',(mid,'chat','QUEUED'))
        self.provider.recovery.issue('chat',mid)

    def test_wire_evidence_records_projection_not_discarded_source_messages(self):
        self.message('wire-check')
        self.payload['messages']=[{'role':'user','content':'Earlier'},
            {'role':'assistant','tool_calls':[{'id':'old'}]},
            {'role':'tool','tool_call_id':'old','content':'x'*140000},
            {'role':'user','content':'Continue'},
            {'role':'assistant','tool_calls':[{'id':'recent'}]},
            {'role':'tool','tool_call_id':'recent','content':'Current feedback'}]
        self.complete()
        with self.store.connect() as db:
            row=db.execute('SELECT wire,receipt FROM model_request_evidence').fetchone()
        self.assertNotIn('old',[m.get('tool_call_id') for m in json.loads(row['wire'])['messages']])
        receipt=json.loads(row['receipt'])
        self.assertEqual(['recent'],[item['tool_call_id'] for item in receipt['feedback']])
        self.assertEqual(140000,len(self.payload['messages'][2]['content']))

    def complete(self):
        result={'model':'deepseek-flash','usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}
        with patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(json.dumps(result).encode())):
            self.provider.complete('chat',self.payload)

    def test_quota_is_per_new_user_message_not_reset_by_duplicate_or_restart(self):
        self.message('first')
        before=self.provider.status()['limits']
        with self.store.connect() as db:
            for n in range(128):
                db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?)',(f'old-{n}','chat',time.time(),'',0,0,'SETTLED',json.dumps({'total_tokens':12}),None,None))
        with self.assertRaisesRegex(ValueError,'CHAT_TURN_REQUEST_CAP'):self.complete()
        self.provider.recovery.issue('chat','first')
        with self.assertRaisesRegex(ValueError,'CHAT_TURN_REQUEST_CAP'):self.complete()
        self.message('second');self.complete()
        with self.store.connect() as db:
            record=dict(db.execute('SELECT * FROM model_request_context').fetchone())
            self.assertEqual('second',record['message_id'])
            self.assertEqual(4096,json.loads(record['projection'])['max_output_tokens'])
        self.assertEqual(before,self.provider.status()['limits'])
        self.assertEqual(129,self.provider.status()['calls'])

    def test_tiny_interactive_output_is_rejected_without_billable_dispatch(self):
        self.message('first');self.payload['max_tokens']=1
        with patch('urllib.request.OpenerDirector.open') as transport:
            with self.assertRaisesRegex(ValueError,'OUTPUT_BUDGET_TOO_SMALL'):self.complete()
            transport.assert_not_called()
        self.assertEqual(0,self.provider.status()['calls'])

    def test_oversized_protected_context_records_preflight_failure_without_dispatch(self):
        self.message('first');self.payload['messages'][0]['content']='要求'*70000
        with patch('urllib.request.OpenerDirector.open') as transport:
            with self.assertRaisesRegex(ValueError,'MODEL_CONTEXT_BYTE_LIMIT'):
                self.provider.complete('chat',self.payload)
            transport.assert_not_called()
        self.assertEqual(0,self.provider.status()['calls'])
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM events WHERE kind='model_context_rejected'").fetchone()
            self.assertFalse(json.loads(row['data'])['fits'])

    def test_provider_archives_large_recent_results_before_billable_dispatch(self):
        self.message('first')
        self.payload['messages'] += [
            {'role':'assistant','tool_calls':[{'id':'read','type':'function','function':{'name':'read','arguments':'{}'}}]},
            {'role':'tool','tool_call_id':'read','content':'计算结果'*40000}]
        before=canonical(self.payload)
        response={'model':'deepseek-flash','usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}
        with patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(json.dumps(response).encode())) as transport:
            self.provider.complete('chat',self.payload)
            sent=transport.call_args.args[0].data
            self.assertLess(len(sent),128000)
            self.assertIn('context-records/',sent.decode())
        self.assertEqual(before,canonical(self.payload))
        with self.store.connect() as db:
            projection=json.loads(db.execute('SELECT projection FROM model_request_context').fetchone()[0])
            self.assertEqual('tool',projection['archived_messages'][0]['kind'])
            self.assertTrue(projection['fits'])

    def test_batch_quota_and_cumulative_tokens_remain_enforced(self):
        with self.store.connect() as db:
            for n in range(24):db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?)',(f'b-{n}','operator',0,'',0,0,'SETTLED',json.dumps({'total_tokens':12}),None,None))
        with self.assertRaisesRegex(ValueError,'SESSION_REQUEST_CAP'):self.provider.complete('operator',self.payload)
        self.message('first')
        with self.store.connect() as db:db.execute('UPDATE model_limits SET max_tokens=100')
        with self.assertRaisesRegex(ValueError,'MODEL_TOKEN_BUDGET'):self.complete()
        self.assertEqual(24,self.provider.status()['calls'])
