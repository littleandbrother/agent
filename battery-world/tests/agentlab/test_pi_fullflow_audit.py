import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest


module_path = Path(__file__).resolve().parents[2] / 'scripts/audit_pi_fullflow.py'
spec = importlib.util.spec_from_file_location('pi_fullflow_audit', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FullflowAuditTest(unittest.TestCase):
    def test_accounting_stays_owner_bound_and_omits_private_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'workbench/state'
            state.mkdir(parents=True)
            db = sqlite3.connect(state / 'workbench.sqlite')
            db.executescript('''
                CREATE TABLE conversations(id,title,status,error);
                CREATE TABLE model_requests(id,owner,status,reserved,charged,error,created);
                CREATE TABLE engineering_jobs(id,owner,status,created,started,ended,error,result);
                CREATE TABLE eda_cli_jobs(owner,status);
                CREATE TABLE chat_messages(id,conversation,operation,status,created);
                INSERT INTO conversations VALUES('pi-chat-a','candidate','RUNNING',NULL);
                INSERT INTO model_requests VALUES('paid','pi-chat-a','SETTLED',0.19,0.03,NULL,1);
                INSERT INTO model_requests VALUES('unknown','pi-chat-a','UNKNOWN',0.19,0,'transport',2);
                INSERT INTO model_requests VALUES('active','pi-chat-a','DISPATCHED',0.10,0,NULL,3);
                INSERT INTO model_requests VALUES('other','pi-chat-b','SETTLED',10,8,NULL,4);
                INSERT INTO eda_cli_jobs VALUES('pi-chat-a','FAILED');
            ''')
            db.commit()
            db.close()
            trace = root / 'workbench/sessions/pi-chat-a/trace.jsonl'
            trace.parent.mkdir(parents=True)
            trace.write_text('\n'.join(json.dumps(x) for x in [
                {'type': 'message', 'message': {'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 'PRIVATE_REASONING'}]}},
                {'type': 'tool_execution_start', 'toolName': 'bf_eda', 'args': {'secret': 'PRIVATE_ARGUMENT'}},
                {'type': 'tool_execution_end', 'toolName': 'bf_eda', 'isError': True},
            ]) + '\n{"type":')
            result = module.audit(root, 'pi-chat-a')
            self.assertAlmostEqual(result['model']['total_upper_usd'], .32)
            self.assertEqual(result['model']['request_count'], 3)
            self.assertEqual(result['tool_calls'], {'bf_eda': 1})
            self.assertEqual(result['tool_error_counts'], {'bf_eda': 1})
            self.assertNotIn('PRIVATE_', json.dumps(result))
            self.assertEqual(result['independent_engineering_acceptance'], 'not_decided_by_this_audit')
            with self.assertRaisesRegex(ValueError, 'OWNER_INVALID'):
                module.audit(root, '../pi-chat-b')
