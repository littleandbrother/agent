import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from bfworld.agentlab.store import Store
from bfworld.agentlab.provider import Provider

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

if __name__=='__main__':unittest.main()
