import base64
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from bfworld.agentlab.server import Workbench, handler
from bfworld.agentlab.store import identity
from bfworld.agentlab.trace_review import TraceReview, tool_calls


def event(seq, kind, **data):
    return {'seq': seq, 'data': {'type': kind, **data}}


class ToolAssociation(unittest.TestCase):
    def test_interleaved_same_name_uses_ids_and_does_not_duplicate_end_message(self):
        events = [event(1,'tool_execution_start',toolName='read',toolCallId='a',args={'path':'a'},time=1),
                  event(2,'tool_execution_start',toolName='read',toolCallId='b',args={'path':'b'}),
                  event(3,'tool_execution_end',toolName='read',toolCallId='b',result='B',time=2),
                  event(4,'tool_execution_end',toolName='read',toolCallId='a',result='A',time=3),
                  event(5,'message',message={'role':'toolResult','toolName':'read','toolCallId':'a','content':'A','isError':False})]
        calls, issues = tool_calls(events)
        self.assertEqual([], issues)
        self.assertEqual(['A','B'], [c['result'] for c in calls])
        self.assertEqual([4,5], calls[0]['result_sources'])
        self.assertEqual(2000, calls[0]['duration_ms'])
        self.assertIsNone(calls[1]['duration_ms'])

    def test_ambiguous_legacy_results_stay_unassociated(self):
        events=[event(1,'tool_execution_start',toolName='write',args={'path':'a'}),
                event(2,'tool_execution_start',toolName='write',args={'path':'b'}),
                event(3,'message',message={'role':'toolResult','toolName':'write','content':'unknown target'})]
        calls, issues=tool_calls(events)
        self.assertEqual([None,None],[c['result'] for c in calls])
        self.assertEqual('ambiguous-tool-result',issues[0]['kind'])
        self.assertEqual([1,2],issues[0]['candidate_starts'])

    def test_legacy_fallback_never_becomes_exact_start_identity(self):
        events=[event(1,'tool_execution_start',toolName='read',args={}),
                event(2,'tool_execution_end',toolName='read',toolCallId='id',result='ok'),
                event(3,'message',message={'role':'toolResult','toolName':'read','toolCallId':'id','content':'ok'})]
        calls,issues=tool_calls(events)
        self.assertEqual([],issues)
        self.assertEqual('ordered-name-single-candidate',calls[0]['correlation'])
        self.assertIsNone(calls[0]['duration_ms'])


class TraceSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.home=Path(self.tmp.name)
        self.app=Workbench(self.home/'state')
        self.review=TraceReview(self.app)
        self.owner='pi-trace-fixture'
        self.directory=self.home/'sessions'/self.owner;self.directory.mkdir(parents=True)
        (self.directory/'receipt.json').write_text(json.dumps({'owner':self.owner,'harness':{'identity':'fixture'}}))
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app))
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close()
        self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()

    def test_export_preserves_bytes_prefix_and_explicit_invalid_records(self):
        raw=b'{"type":"tool_execution_start","toolName":"read","args":{}}\nnot-json\n{"type":"text_delta","delta":"unfinished'
        path=self.directory/'trace.jsonl';path.write_bytes(raw)
        snapshot=self.review.snapshot(self.owner)
        self.assertEqual(raw,base64.b64decode(snapshot['raw_base64']))
        self.assertEqual(hashlib.sha256(raw).hexdigest(),snapshot['source']['sha256'])
        self.assertEqual(1,len(snapshot['events']))
        self.assertEqual('invalid-committed-event',snapshot['issues'][0]['kind'])
        self.assertGreater(snapshot['source']['pending_tail_bytes'],0)
        self.assertEqual(snapshot['snapshot_id'],identity({k:v for k,v in snapshot.items() if k!='snapshot_id'}))
        self.assertEqual(snapshot,self.review.snapshot(self.owner))
        self.assertEqual(raw,path.read_bytes())
        self.assertEqual(0,self.app.provider.status()['calls'])

    def test_growing_log_produces_distinct_snapshot_without_rewriting_prior_capture(self):
        p=self.directory/'trace.jsonl';p.write_text('{"type":"assistant_start"}\n')
        first=self.review.snapshot(self.owner)
        with p.open('a') as f:f.write('{"type":"turn_complete"}\n')
        second=self.review.snapshot(self.owner)
        self.assertEqual(1,len(first['events']));self.assertEqual(2,len(second['events']))
        self.assertNotEqual(first['snapshot_id'],second['snapshot_id'])

    def test_context_preflight_is_reviewable_without_counting_as_model_usage(self):
        from bfworld.agentlab.trace_analysis import analyze
        data={'projected_bytes':150000,'limit_bytes':128000,'fits':False}
        self.app.store.event(self.owner,self.owner,'model_context_rejected',data)
        snapshot=self.review.snapshot(self.owner)
        analysis=analyze(snapshot)
        self.assertEqual(data,json.loads(snapshot['model_context_rejections'][0]['data']))
        item=next(i for i in analysis['timeline'] if i['id'].startswith('context-rejected-'))
        self.assertFalse(item['detail']['dispatched'])
        self.assertEqual([],analysis['requests'])
        self.assertEqual(0,analysis['metrics']['charged_usd']['value'])

    def test_queued_conversation_exposes_real_block_without_starting_pi(self):
        (self.home/'paid-window-closed.json').write_text('{}')
        c=self.app.conversations.create('queued task',None,'trace-blocked')
        s=self.review.snapshot(c['id'])
        self.assertFalse(s['source']['exists']);self.assertIsNone(s['receipt'])
        self.assertTrue(any('PAID_WINDOW_CLOSED' in e['data'] for e in s['chat_events']))
        self.assertEqual(0,self.app.provider.status()['calls'])

    def test_operator_access_and_path_symlink_boundary(self):
        operator=(self.app.store.root/'operator.token').read_text()
        participant=self.app.store.issue('participant')
        def get(owner,token):
            request=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/api/developer/trace?session={owner}',headers={'Authorization':'Bearer '+token})
            try:
                with urllib.request.urlopen(request) as response:return response.status
            except urllib.error.HTTPError as exc:return exc.code
        self.assertEqual(403,get(self.owner,participant))
        self.assertEqual(200,get(self.owner,operator))
        self.assertEqual(403,get('pi-../../secrets',operator))
        self.assertEqual(403,get('pi-missing',operator))
        outside=self.home/'outside';outside.write_text('unrelated')
        (self.directory/'trace.jsonl').symlink_to(outside)
        with self.assertRaisesRegex(PermissionError,'PATH_DENIED'):self.review.snapshot(self.owner)
