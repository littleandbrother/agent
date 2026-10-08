import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from bfworld.agentlab.store import Store
from bfworld.agentlab.provider import Provider
from scripts.export_request_evidence import audit

class ProviderBudget(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name));self.provider=Provider(self.store)
        self.payload={'model':'deepseek-flash','messages':[{'role':'user','content':'hi'}],'max_tokens':10}
    def tearDown(self):self.tmp.cleanup()
    def response(self,usage=True):
        result={'model':'deepseek-flash','choices':[{'message':{'content':'ok'}}]}
        if usage:result['usage']={'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}
        return io.BytesIO(json.dumps(result).encode())
    def test_settlement_and_strict_budget(self):
        with patch('urllib.request.OpenerDirector.open',return_value=self.response()):
            self.provider.complete('operator',self.payload)
        self.assertEqual('SETTLED',self.provider.status()['requests'][0]['status'])
        self.assertAlmostEqual(.0000054,self.provider.status()['upper_bound_usd'])
        with self.store.connect() as db:db.execute('UPDATE model_limits SET total_usd=.00001')
        with self.assertRaisesRegex(ValueError,'USD_BUDGET'):self.provider.complete('operator',self.payload)
        self.assertEqual(1,self.provider.status()['calls'])

    def test_reasoning_stream_envelope_may_exceed_legacy_two_megabytes(self):
        with self.store.connect() as db:
            db.execute('INSERT INTO settings VALUES(?,?)', ('model_profile:operator',json.dumps('engineering-reasoning-v1')))
        chunk={'id':'response-x','model':'deepseek-flash','choices':[{'index':0,'delta':{'reasoning_content':'x'*600},'finish_reason':None}]}
        terminal={'id':'response-x','model':'deepseek-flash','choices':[{'index':0,'delta':{},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':8000,'total_tokens':8010}}
        raw=(b'data: '+json.dumps(chunk).encode()+b'\n\n')*3200+b'data: '+json.dumps(terminal).encode()+b'\n\ndata: [DONE]\n\n'
        self.assertGreater(len(raw),2000000)
        with patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(raw)):
            self.provider.complete('operator',{**self.payload,'max_tokens':32768},on_chunk=lambda _:None)
        self.assertEqual('SETTLED',self.provider.status()['requests'][0]['status'])

    def test_operator_reasoning_profile_keeps_reasoning_and_is_owner_scoped(self):
        with self.store.connect() as db:
            db.execute('INSERT INTO settings VALUES(?,?)', ('model_profile:operator',json.dumps('engineering-reasoning-v1')))
        messages=[{'role':'user','content':'design'},
                  {'role':'assistant','content':'','reasoning_content':'retained reasoning',
                   'tool_calls':[{'id':'c1','type':'function','function':{'name':'read','arguments':'{}'}}]},
                  {'role':'tool','tool_call_id':'c1','content':'facts'}]
        with patch('urllib.request.OpenerDirector.open',return_value=self.response()) as opening:
            self.provider.complete('operator',{**self.payload,'messages':messages,'max_tokens':65536})
        body=json.loads(opening.call_args.args[0].data)
        self.assertEqual({'type':'enabled'},body['thinking'])
        self.assertEqual('high',body['reasoning_effort'])
        self.assertEqual(32768,body['max_tokens'])
        self.assertEqual(messages,body['messages'])
        self.store.grant('other',[],6,time.time()+60)
        with patch('urllib.request.OpenerDirector.open',return_value=self.response()) as opening:
            self.provider.complete('other',{**self.payload,'thinking':{'type':'enabled'},'max_tokens':65536})
        body=json.loads(opening.call_args.args[0].data)
        self.assertEqual({'type':'disabled'},body['thinking'])
        self.assertEqual(8192,body['max_tokens'])

    def test_reasoning_profile_still_respects_request_usd_ceiling(self):
        with self.store.connect() as db:
            db.execute('INSERT INTO settings VALUES(?,?)', ('model_profile:operator',json.dumps('engineering-reasoning-v1')))
            db.execute('UPDATE model_limits SET request_usd=.04')
        with self.assertRaisesRegex(ValueError,'MODEL_USD_BUDGET'):
            self.provider.complete('operator',{**self.payload,'max_tokens':32768})
        self.assertEqual(0,self.provider.status()['calls'])

    def test_forced_tool_choice_thinking_rejected_before_network_or_reservation(self):
        with self.store.connect() as db:
            db.execute('INSERT INTO settings VALUES(?,?)', ('model_profile:operator',json.dumps('engineering-reasoning-v1')))
        for choice in ('required',{'type':'function','function':{'name':'read'}}):
            with self.assertRaisesRegex(ValueError,'THINKING_TOOL_CHOICE_UNSUPPORTED'):
                self.provider.complete('operator',{**self.payload,'tool_choice':choice})
        self.assertEqual(0,self.provider.status()['calls'])

    def test_context_profile_preserves_current_reasoning_tool_round_trip(self):
        from bfworld.agentlab.context import project_interactive
        from bfworld.agentlab.model_profile import ENGINEERING
        messages=[{'role':'user','content':'task'},
                  {'role':'assistant','content':'','reasoning_content':'r'*10000,
                   'tool_calls':[{'id':'x','type':'function','function':{'name':'read','arguments':'{}'}}]},
                  {'role':'tool','tool_call_id':'x','content':'d'*130000}]
        body,audit=project_interactive({'messages':messages}, request_bytes=ENGINEERING['request_bytes'],target_bytes=ENGINEERING['target_bytes'])
        self.assertTrue(audit['fits'])
        self.assertEqual(messages,body['messages'])

    def test_evidence_is_exact_final_wire_and_never_added_to_model_payload(self):
        with patch('urllib.request.OpenerDirector.open',return_value=self.response()) as opening:
            self.provider.complete('operator',self.payload)
        raw=opening.call_args.args[0].data
        with self.store.connect() as db:
            row=db.execute('SELECT e.*,r.request_hash FROM model_request_evidence e JOIN model_requests r ON r.id=e.request_id').fetchone()
        self.assertEqual(raw,row['wire'].encode())
        receipt=json.loads(row['receipt'])
        self.assertEqual(row['request_hash'],receipt['wire_sha256'])
        self.assertEqual('unknown',receipt['method']['status'])
        self.assertEqual(self.payload['messages'],json.loads(raw)['messages'])
        self.assertNotIn('receipt',json.loads(raw))
        with self.store.connect() as db:
            report=audit(db,['operator'])
            self.assertEqual(1,report['counts']['with_wire_receipt'])
            self.assertFalse(report['integrity_errors'])
            db.execute("UPDATE model_request_evidence SET wire='{}'")
        with self.store.connect() as db:
            self.assertEqual('WIRE_IDENTITY_MISMATCH',audit(db,['operator'])['integrity_errors'][0]['error'])
            db.execute('DELETE FROM model_request_evidence')
        with self.store.connect() as db:
            report=audit(db,['operator'])
            self.assertEqual(1,report['counts']['historical_unknown'])
            self.assertEqual('unknown',report['requests'][0]['method']['status'])
    def test_unknown_usage_stops_future_dispatch_and_restart(self):
        with patch('urllib.request.OpenerDirector.open',return_value=self.response(False)):
            with self.assertRaisesRegex(ValueError,'USAGE_MISSING'):self.provider.complete('operator',self.payload)
        self.assertEqual('UNKNOWN',self.provider.status()['requests'][0]['status'])
        with self.assertRaisesRegex(ValueError,'UNKNOWN_STOP'):Provider(self.store).complete('operator',self.payload)
    def test_wrong_model_and_oversize_rejected_before_dispatch(self):
        with self.assertRaisesRegex(ValueError,'MODEL_ID'):self.provider.complete('operator',{**self.payload,'model':'other'})
        with self.assertRaisesRegex(ValueError,'BYTE_LIMIT'):self.provider.complete('operator',{**self.payload,'messages':['x'*128001]})
        self.assertEqual(0,self.provider.status()['calls'])
    def test_interactive_default_owner_cap_and_explicit_override(self):
        owner='pi-chat-0123456789abcdef'
        self.store.grant(owner,[],6,time.time()+60)
        with self.store.connect() as db:
            db.execute("INSERT INTO settings VALUES('interactive_default_owner_usd','0.00001')")
        with self.assertRaisesRegex(ValueError,'MODEL_OWNER_USD_BUDGET'):
            self.provider.complete(owner,self.payload)
        self.assertEqual(0,self.provider.status()['calls'])
        with self.store.connect() as db:
            db.execute('INSERT INTO owner_model_caps VALUES(?,?)',(owner,1.))
            self.assertIsNone(self.provider.owner_cap(db,'operator'))
        with patch('urllib.request.OpenerDirector.open',return_value=self.response()):
            self.provider.complete(owner,self.payload)
        self.assertEqual('SETTLED',self.provider.status()['requests'][0]['status'])
    def test_more_budget_never_releases_unknown_usage(self):
        with patch('urllib.request.OpenerDirector.open',return_value=self.response(False)):
            with self.assertRaisesRegex(ValueError,'USAGE_MISSING'):self.provider.complete('operator',self.payload)
        with self.store.connect() as db:
            db.execute('UPDATE model_limits SET total_usd=10,max_tokens=50000000')
        with self.assertRaisesRegex(ValueError,'UNKNOWN_STOP'):
            self.provider.complete('operator',self.payload)
    def test_stream_delivers_chunks_and_settles_even_when_reader_disconnects(self):
        chunks=[{'model':'deepseek-flash','choices':[{'delta':{'content':'real chunk'}}]},
                {'model':'deepseek-flash','choices':[],'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}]
        wire=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n'
        seen=[]
        def receive(chunk):
            seen.append(chunk)
            raise BrokenPipeError()
        with patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(wire.encode())):
            self.provider.complete('operator',self.payload,on_chunk=receive)
        self.assertEqual(chunks,seen)
        self.assertEqual('SETTLED',self.provider.status()['requests'][0]['status'])
    def test_truncated_stream_holds_unknown_usage_and_blocks_retry(self):
        wire='data: '+json.dumps({'model':'deepseek-flash','choices':[{'delta':{'content':'partial'}}]})+'\n\n'
        with patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(wire.encode())):
            with self.assertRaisesRegex(ValueError,'STREAM_TRUNCATED'):
                self.provider.complete('operator',self.payload,on_chunk=lambda c:None)
        self.assertEqual('UNKNOWN',self.provider.status()['requests'][0]['status'])
        with self.assertRaisesRegex(ValueError,'UNKNOWN_STOP'):
            self.provider.complete('operator',self.payload)

    def test_terminal_usage_is_settled_even_without_done_output_still_fails(self):
        c={'model':'deepseek-flash','choices':[],
           'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}
        with patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(('data: '+json.dumps(c)+'\n\n').encode())):
            with self.assertRaisesRegex(ValueError,'STREAM_TRUNCATED'):
                self.provider.complete('operator',self.payload,on_chunk=lambda c:None)
        row=self.provider.status()['requests'][0]
        self.assertEqual('SETTLED',row['status'])
        self.assertIn('STREAM_TRUNCATED',row['error'])

    def test_provider_keepalive_over_90_seconds_can_finish_inside_bound(self):
        clock=[0.]
        class SlowResponse(io.BytesIO):
            def __iter__(self):
                yield b': keepalive\n';clock[0]=100.
                yield b': keepalive\n'
                yield ('data: '+json.dumps({'id':'provider-id','model':'deepseek-flash','choices':[],
                    'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}})+'\n').encode()
                yield b'data: [DONE]\n'
        with patch('urllib.request.OpenerDirector.open',return_value=SlowResponse()),patch('bfworld.agentlab.provider.time.monotonic',side_effect=lambda:clock[0]):
            self.provider.complete('operator',self.payload,on_chunk=lambda c:None)
        self.assertEqual('SETTLED',self.provider.status()['requests'][0]['status'])

    def test_stream_wall_limit_still_holds_reservation_without_usage(self):
        clock=[0.]
        class TooSlow(io.BytesIO):
            def __iter__(self):
                clock[0]=301.;yield b': keepalive\n'
        with patch('urllib.request.OpenerDirector.open',return_value=TooSlow()),patch('bfworld.agentlab.provider.time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ValueError,'PROVIDER_STREAM_TIME_LIMIT'):
                self.provider.complete('operator',self.payload,on_chunk=lambda c:None)
        self.assertEqual('UNKNOWN',self.provider.status()['requests'][0]['status'])

    def test_explicit_study_continuation_retains_unknown_and_scope(self):
        with patch('urllib.request.OpenerDirector.open',return_value=self.response(False)):
            with self.assertRaises(ValueError):self.provider.complete('operator',self.payload)
        original=self.provider.status()['requests'][0]
        now=time.time()
        with self.store.connect() as db:
            db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',('pilot',now,now+60,.5,'deepseek-flash','original'))
            db.execute('INSERT INTO research_model_owners VALUES(?,?,?)',('operator','pilot','one'))
            db.execute('INSERT INTO research_usage_continuations VALUES(?,?,?,?)',('pilot',now,now+60,'explicit continuation'))
        with patch('urllib.request.OpenerDirector.open',return_value=self.response()):self.provider.complete('operator',self.payload)
        after=self.provider.status()
        self.assertEqual(original,after['requests'][0])
        self.assertGreater(after['upper_bound_usd'],original['reserved'])
        self.store.grant('outsider',[],6,now+60)
        with self.assertRaisesRegex(ValueError,'UNKNOWN_STOP'):self.provider.complete('outsider',self.payload)
        with self.store.connect() as db:db.execute('UPDATE research_model_studies SET max_usd=?',(original['reserved']+.00001,))
        with self.assertRaisesRegex(ValueError,'RESEARCH_MODEL_USD_BUDGET'):self.provider.complete('operator',self.payload)
        with self.store.connect() as db:db.execute('UPDATE research_usage_continuations SET expires=0')
        with self.assertRaisesRegex(ValueError,'UNKNOWN_STOP'):self.provider.complete('operator',self.payload)

    def test_authorized_study_accepts_slow_keepalive_without_cancelling(self):
        now=time.time()
        with self.store.connect() as db:
            db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',('slow',now,now+3600,.5,'deepseek-flash','original'))
            db.execute('INSERT INTO research_model_owners VALUES(?,?,?)',('operator','slow','one'))
            db.execute('INSERT INTO research_usage_continuations VALUES(?,?,?,?)',('slow',now,now+3600,'continue'))
        clock=[0.]
        class Slow(io.BytesIO):
            def __iter__(self):
                clock[0]=600.;yield b': keepalive\n'
                yield ('data: '+json.dumps({'model':'deepseek-flash','choices':[],
                    'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}})+'\n').encode()
                yield b'data: [DONE]\n'
        with patch('urllib.request.OpenerDirector.open',return_value=Slow()),patch('bfworld.agentlab.provider.time.monotonic',side_effect=lambda:clock[0]):
            self.provider.complete('operator',self.payload,on_chunk=lambda c:None)
        self.assertEqual('SETTLED',self.provider.status()['requests'][0]['status'])

    def test_upstream_sse_error_is_terminal_and_keeps_unknown_reservation(self):
        seen=[]
        wire=b': keepalive\n\ndata: {"error":{"code":"upstream_failed"}}\n\n'
        with patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(wire)) as opening:
            with self.assertRaisesRegex(ValueError,'PROVIDER_STREAM_ERROR'):
                self.provider.complete('operator',self.payload,on_chunk=seen.append)
        self.assertEqual([None],seen)
        self.assertEqual(1,opening.call_count,'Never silently repeat a possibly billed completion')
        row=self.provider.status()['requests'][0]
        self.assertEqual('UNKNOWN',row['status']);self.assertGreater(row['reserved'],0)
        self.assertIsNone(row['usage'])

    def test_upstream_read_idle_timeout_is_not_success_or_zero_usage(self):
        class Idle(io.BytesIO):
            def __iter__(self):
                yield b': keepalive\n'
                raise TimeoutError('The read operation timed out')
        seen=[]
        with patch('urllib.request.OpenerDirector.open',return_value=Idle()) as opening:
            with self.assertRaisesRegex(TimeoutError,'read operation'):
                self.provider.complete('operator',self.payload,on_chunk=seen.append)
        self.assertEqual([None],seen);self.assertEqual(1,opening.call_count)
        row=self.provider.status()['requests'][0]
        self.assertEqual('UNKNOWN',row['status']);self.assertEqual(0,row['charged'])
        self.assertGreater(row['reserved'],0);self.assertIsNone(row['usage'])

if __name__=='__main__':unittest.main()
