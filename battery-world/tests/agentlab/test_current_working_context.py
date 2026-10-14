"""Preserve working call/results before eviction under genuine byte pressure."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from bfworld.agentlab import context as parent
from bfworld.agentlab.store import canonical, identity

candidate = os.environ.get('BF_CURRENT_CONTEXT_CANDIDATE')
if candidate:
    spec = importlib.util.spec_from_file_location('bfworld.agentlab.working_context_candidate',candidate)
    current = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(current)
else:
    current = parent


def calls(payload):
    return {call['id']:call for message in payload['messages']
            for call in message.get('tool_calls',[])}


def episode(count=20, protected=175000, reply=7000):
    messages = [{'role':'system','content':'Frozen apparatus and method.\n'+'s'*50000},
                {'role':'user','content':'Keep the original owner, fees and successful inputs.\n'+'u'*(protected-50000)}]
    for i in range(count):
        key = 'public-call-'+str(i)
        messages += [{'role':'assistant','content':None,
                      'tool_calls':[{'id':key,'type':'function','function':{'name':'read',
                                     'arguments':canonical({'path':'working/result-'+str(i)+'.json'})}}]},
                     {'role':'tool','tool_call_id':key,
                      'content':'Input v'+str(i)+'; result remains independently unverified.\n'+'x'*reply}]
    return {'model':'deepseek-flash','thinking':{'type':'enabled'},'max_tokens':32768,
            'tools':[{'type':'function','function':{'name':'read','parameters':{'type':'object'}}}],
            'messages':messages}


class CurrentWorkingContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = current.ContextArchive(self.root,'pi-chat-original-fixture')

    def project(self,payload,archive=True,**kwargs):
        return current.project_interactive(payload,self.archive if archive else None,
                                           request_bytes=256000,target_bytes=220000,**kwargs)

    def test_completed_current_work_retains_all_call_arguments_before_eviction(self):
        payload = episode()
        result,audit = self.project(payload)
        self.assertTrue(audit['fits'])
        self.assertEqual(calls(payload),calls(result))
        self.assertEqual([],audit['bounded_turn_omitted_call_ids'])
        self.assertEqual(20,len(audit['current_turn_retained_call_ids']))
        self.assertEqual(payload['messages'][:2],[m for m in result['messages'] if m['role']=='user' or
                                                m['role']=='system' and m['content'].startswith('Frozen apparatus')])
        for key in ('model','thinking','tools','max_tokens'):
            self.assertEqual(payload[key],result[key])

    def test_archived_public_results_have_exact_readable_source_bytes(self):
        payload = episode()
        result,audit = self.project(payload)
        originals = {m['tool_call_id']:m for m in payload['messages'] if m['role']=='tool'}
        evidence = [a for a in audit['archived_messages'] if a.get('before_current_turn_eviction')]
        self.assertTrue(evidence)
        for record in evidence:
            file = self.root/'participants/pi-chat-original-fixture'/record['record_file']
            raw = file.read_bytes()
            restored = json.loads(raw)
            self.assertEqual(record['sha256'],identity(restored))
            self.assertEqual(canonical(restored).encode(),raw)
            self.assertEqual(originals[restored['tool_call_id']],restored)

    def test_partial_parallel_batch_and_unreturned_call_are_not_spilled_or_removed(self):
        payload = episode()
        unresolved = {'role':'assistant','content':None,'tool_calls':[
            {'id':key,'type':'function','function':{'name':'read','arguments':'{}'}}
            for key in ('partial-returned','partial-unreturned')]}
        returned = {'role':'tool','tool_call_id':'partial-returned','content':'Exact partial evidence. '+'p'*9000}
        payload['messages'] += [unresolved,returned]
        result,audit = self.project(payload)
        self.assertTrue(audit['fits'])
        self.assertIn(unresolved,result['messages']);self.assertIn(returned,result['messages'])
        self.assertNotIn('partial-returned',audit['omitted_tool_call_ids'])
        self.assertNotIn('partial-unreturned',audit['omitted_tool_call_ids'])

    def test_old_completed_history_evicts_before_new_current_work(self):
        old = episode(count=15,protected=20000,reply=7000)
        new = episode(count=8,protected=175000,reply=7000)
        for m in old['messages'][2:]:
            for call in m.get('tool_calls',[]):call['id']='old-'+call['id']
            if m.get('tool_call_id'):m['tool_call_id']='old-'+m['tool_call_id']
        payload = {**new,'messages':old['messages'][2:]+new['messages']}
        result,audit = self.project(payload)
        self.assertTrue(audit['fits'])
        self.assertTrue(set(calls(new)).issubset(calls(result)))
        self.assertTrue(any(key.startswith('old-') for key in audit['omitted_tool_call_ids']))
        self.assertEqual([],audit['bounded_turn_omitted_call_ids'])

    def test_utf8_evidence_roundtrips_and_preview_is_explicitly_partial(self):
        payload = episode(reply=3000)
        for m in payload['messages']:
            if m['role']=='tool':m['content']='器件输入未变；仿真不可冒充物理验证。'*500
        result,audit = self.project(payload)
        self.assertTrue(audit['fits'])
        for message in result['messages']:
            if message['role']=='tool':
                value = json.loads(message['content'])
                self.assertTrue(value['preview']['partial'])
                self.assertEqual('archived_not_deleted',value['context_projection'])

    def test_small_fitting_request_is_not_archived_or_rewritten(self):
        payload = episode(count=2,protected=5000,reply=500)
        result,audit = self.project(payload)
        self.assertEqual(payload,result)
        self.assertEqual([],audit['archived_messages'])
        self.assertEqual([],audit['bounded_turn_omitted_call_ids'])

    def test_without_archive_original_pairing_and_cap_fallback_remain(self):
        payload = episode()
        result,audit = self.project(payload,archive=False)
        self.assertTrue(audit['fits'])
        self.assertEqual([],audit['archived_messages'])
        self.assertGreaterEqual(len(calls(result)),2)
        for key,call in calls(result).items():self.assertEqual(calls(payload)[key],call)

    def test_many_tiny_replies_fallback_drops_only_complete_pairs(self):
        payload = episode(count=180,reply=200)
        result,audit = self.project(payload)
        self.assertTrue(audit['fits'])
        returned = {m['tool_call_id'] for m in result['messages'] if m['role']=='tool'}
        self.assertEqual(set(calls(result)),returned)
        self.assertGreaterEqual(len(returned),2)
        self.assertEqual(payload['messages'][-4:],result['messages'][-4:])

    def test_protected_requirements_exceeding_cap_refuse_without_truncation(self):
        payload = episode(count=0,protected=270000)
        result,audit = self.project(payload)
        self.assertFalse(audit['fits'])
        self.assertEqual(payload,result)

    def test_frozen_active_method_survives_evidence_spilling(self):
        payload = episode()
        method = {'id':'fixture-method','content':'Fixed method; no case answer.\n'+'m'*3000,
                  'version':'v1','sha256':'a'*64,'manifest_sha256':'b'*64}
        result,audit = self.project(payload,active_skills=[method])
        self.assertTrue(audit['fits'])
        self.assertTrue(audit['active_skills'][0]['present_in_projected_request'])
        self.assertTrue(any(method['content'] in m.get('content','') for m in result['messages']
                            if isinstance(m.get('content'),str)))

    def test_fallback_preserves_original_payload_and_does_not_reexecute_tools(self):
        payload = episode(count=60)
        original = copy.deepcopy(payload)
        result,audit = self.project(payload)
        self.assertTrue(audit['fits'])
        self.assertEqual(original,payload)
        self.assertTrue(set(calls(result)).issubset(calls(payload)))
        self.assertEqual(set(calls(result)),{m['tool_call_id'] for m in result['messages'] if m['role']=='tool'})

    def test_tagged_startup_copied_human_text_deduplicates_only_when_verbatim_present(self):
        payload = episode(count=6,protected=10000,reply=50000)
        human = 'Exact active requirement; preserve sources, owner and fees.\n'+'h'*9500
        payload['messages'][1]['content'] = human
        state = {'messages':[{'id':'known-user-input','text':human}],
                 'assembly':{'revision':1},'engineering':{'jobs':[]},
                 'instruction':'Distinct apparatus instruction remains exact.'}
        prefix = '启动事实快照（操作前 inspect 核对）：'
        plain = 'Frozen core rule remains exact.\n'
        payload['messages'][0]['content'] = plain+prefix+canonical(state)+'\n'
        result,audit = self.project(payload)
        self.assertEqual(payload['messages'][1],next(m for m in result['messages'] if m['role']=='user'))
        system = next(m for m in result['messages'] if m['role']=='system' and m['content'].startswith(plain))
        restored = json.loads(system['content'].splitlines()[1][len(prefix):])
        self.assertTrue(restored['human_messages_preserved_in_user_history'])
        self.assertEqual(state['instruction'],restored['instruction'])
        self.assertTrue(any(r['kind']=='product_state' for r in audit['archived_messages']))
        self.assertFalse(audit['bounded_turn_omitted_call_ids'])

    def test_distinct_copied_human_text_and_untagged_system_are_never_deduplicated(self):
        payload = episode(count=6,protected=10000,reply=50000)
        prefix = '启动事实快照（操作前 inspect 核对）：'
        unique = {'messages':[{'text':'Distinct source requirement.\n'+'h'*9500}]}
        payload['messages'][0]['content'] = 'Unique core.\n'+prefix+canonical(unique)+'\n'
        result,audit = self.project(payload)
        self.assertIn(payload['messages'][0],result['messages'])
        self.assertFalse(any(r['kind']=='product_state' for r in audit['archived_messages']))
        payload['messages'][0]['content'] = 'Untagged system '+canonical(unique)
        result,audit = self.project(payload)
        self.assertIn(payload['messages'][0],result['messages'])
        self.assertFalse(any(r['kind']=='product_state' for r in audit['archived_messages']))


if __name__=='__main__':unittest.main()
