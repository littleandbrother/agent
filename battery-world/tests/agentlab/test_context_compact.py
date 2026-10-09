import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from bfworld.agentlab.context import ContextArchive, _RequestSize, project_interactive
from bfworld.agentlab.model_profile import COMPACT, DEFAULT, ENGINEERING, for_owner, named
from bfworld.agentlab.store import canonical


class CompactContext(unittest.TestCase):
    def snapshot(self, human='原始要求：84毫米板框，复用eng-known，不重复仿真。'):
        state={'messages':[{'text':human}], 'assembly':{'revision':5,'physical_hash':'frozen'},
               'engineering':[{'id':'eng-known','status':'SUCCEEDED'}], 'large':['事实'*12000]}
        system='Exact original rules\n启动事实快照（操作前 inspect 核对）：'+canonical(state)+'\nExact budget rule'
        return human,state,system

    def test_projection_is_explicit_and_baseline_keeps_new_snapshot(self):
        human,state,system=self.snapshot()
        payload={'messages':[{'role':'system','content':system},{'role':'user','content':human}]}
        with tempfile.TemporaryDirectory() as root:
            value,audit=project_interactive(payload,ContextArchive(root,'owner'))
            self.assertEqual(payload,value)
            self.assertEqual([],audit['archived_messages'])

    def test_exact_state_archive_and_live_job_survive_compaction(self):
        human,state,system=self.snapshot()
        payload={'messages':[{'role':'system','content':system},{'role':'user','content':human}]}
        original=canonical(payload)
        with tempfile.TemporaryDirectory() as root:
            value,audit=project_interactive(payload,ContextArchive(root,'owner'),compact_state=True)
            self.assertEqual(original,canonical(payload))
            self.assertIn(payload['messages'][-1],value['messages'])
            reduced=next(m['content'] for m in value['messages'] if 'Exact original rules' in str(m.get('content')))
            self.assertTrue(reduced.startswith('Exact original rules\n'))
            self.assertTrue(reduced.endswith('\nExact budget rule'))
            self.assertIn('eng-known',reduced)
            self.assertLess(audit['projected_bytes'],audit['source_bytes'])
            item=audit['archived_messages'][0]
            self.assertEqual(state,json.loads((Path(root)/'participants/owner'/item['record_file']).read_text()))

    def test_copied_human_requirement_without_user_duplicate_stays_inline(self):
        human,state,system=self.snapshot('Exact critical human requirement '+ '约束'*26000)
        payload={'messages':[{'role':'system','content':system},{'role':'user','content':'继续'}]}
        with tempfile.TemporaryDirectory() as root:
            value,audit=project_interactive(payload,ContextArchive(root,'owner'),compact_state=True,
                                            request_bytes=160000,target_bytes=120000)
            self.assertIn(human,canonical(value))
            self.assertFalse(audit['fits'])
            self.assertEqual(1,len(audit['archived_messages']))

    def test_active_method_and_recent_or_unresolved_tool_pairs_remain(self):
        human,state,system=self.snapshot()
        messages=[{'role':'system','content':system},{'role':'user','content':human}]
        for i in range(6):
            messages.extend([{'role':'assistant','tool_calls':[{'id':str(i)}]},
                             {'role':'tool','tool_call_id':str(i),'content':'旧事实'*10000}])
        messages.extend([{'role':'assistant','tool_calls':[{'id':'waiting-a'},{'id':'waiting-b'}]},
                         {'role':'tool','tool_call_id':'waiting-a','content':'未完成的并行回读'}])
        skill={'id':'frozen-method','version':'v1','sha256':'abc','manifest_sha256':'def','content':'Exact independently frozen method'}
        with tempfile.TemporaryDirectory() as root:
            value,audit=project_interactive({'messages':messages},ContextArchive(root,'owner'),compact_state=True,
                    request_bytes=160000,target_bytes=120000,active_skills=[skill])
            self.assertTrue(audit['fits'])
            self.assertTrue(audit['active_skills'][0]['present_in_projected_request'])
            self.assertIn(messages[1],value['messages'])
            for m in messages[-6:]:
                if m.get('tool_calls'):self.assertIn(m,value['messages'])
            self.assertIn(messages[-1],value['messages'])
            kept={c['id'] for m in value['messages'] for c in m.get('tool_calls',[])}
            self.assertTrue({'4','5','waiting-a','waiting-b'}<=kept)

    def test_exact_utf8_size_matches_full_serialization(self):
        for n in range(50):
            payload={'tools':[{'name':'read','values':['字'*n]}],
                     'messages':[{'role':'user','content':'中文要求\n"80 mm"'+('x'*i)} for i in range(n%7)]}
            self.assertEqual(len(canonical(payload).encode()),_RequestSize(payload)(payload['messages']))

    def test_invalid_strategy_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'CONTEXT_STRATEGY_INVALID'):
            project_interactive({'messages':[]},compact_state='yes')


class ProfileIsolation(unittest.TestCase):
    def test_compact_keeps_model_reasoning_and_output_configuration(self):
        for key in ('thinking','reasoning_effort','max_output_tokens'):
            self.assertEqual(ENGINEERING[key],COMPACT[key])
        self.assertLess(COMPACT['target_bytes'],ENGINEERING['target_bytes'])

    def test_profile_is_explicit_and_owner_scoped(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
        db.execute('INSERT INTO settings VALUES(?,?)',('model_profile:canary',json.dumps(COMPACT['version'])))
        self.assertEqual(COMPACT,for_owner(db,'canary'))
        self.assertEqual(DEFAULT,for_owner(db,'unconfigured'))
        db.execute('INSERT INTO settings VALUES(?,?)',('model_profile:baseline',json.dumps(ENGINEERING['version'])))
        self.assertEqual(ENGINEERING,for_owner(db,'baseline'))
        db.close()

    def test_invalid_profile_and_return_value_mutation_do_not_change_registry(self):
        for value in ('legacy-v1','unknown',{},None,False):
            with self.assertRaisesRegex(ValueError,'MODEL_PROFILE_INVALID'):named(value)
        value=named(COMPACT['version']);value['thinking']='disabled'
        self.assertEqual('enabled',named(COMPACT['version'])['thinking'])


if __name__=='__main__':
    unittest.main()
