import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from bfworld.agentlab.store import Store
from bfworld.agentlab.design_lab.service import DesignLab
from bfworld.agentlab.design_lab.qualification import sources

OWNER='pi-chat-abcdef0123456789'
ENV=Path(__file__).resolve().parents[2]/'docs/agentlab/refactor-r0-r2-20261011/environment.json'


class OperatorRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'state')
        with self.store.connect() as db:
            db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY,status TEXT)')
            db.execute('INSERT INTO conversations VALUES(?,?)',(OWNER,'IDLE'))
            db.execute('CREATE TABLE model_requests(id TEXT PRIMARY KEY,status TEXT,reserved REAL,charged REAL)')
            db.execute('INSERT INTO model_requests VALUES("old-liability","UNKNOWN",1.5,0)')
        self.lab=DesignLab(SimpleNamespace(store=self.store),start_worker=False)
        env=json.loads(ENV.read_text())
        with patch('bfworld.agentlab.design_lab.baseline.environment',return_value=env):
            view=self.lab.configure(OWNER,env,sources(env,True))
        self.original=view['current_design']
        base=dict(self.lab.design(OWNER,self.original)['sources']);base['program.c']+='\n/* UI restoration test candidate; not a scientific run. */\n'
        self.candidate=self.lab.freeze(OWNER,base,self.original)['design_id']
        self.lab.adopt(OWNER,self.candidate,1,'select candidate for no-model safety test')

    def test_safe_restore_appends_new_adoption_and_retains_history_liability(self):
        view=self.lab.adopt(OWNER,self.original,2,'user explicitly restores original',operator=True)
        self.assertEqual(self.original,view['current_design']);self.assertEqual(3,view['revision'])
        self.assertEqual(self.original,self.lab.design(OWNER,self.candidate)['parent'])
        with self.store.connect() as db:
            self.assertEqual(2,db.execute('SELECT COUNT(*) FROM design_adoptions').fetchone()[0])
            self.assertEqual(('old-liability','UNKNOWN',1.5,0),tuple(db.execute('SELECT * FROM model_requests').fetchone()))

    def test_running_conversation_rejects_operator_restore_but_pi_adoption_semantics_remain(self):
        with self.store.connect() as db:db.execute('UPDATE conversations SET status="RUNNING" WHERE id=?',(OWNER,))
        with self.assertRaisesRegex(ValueError,'REQUIRES_IDLE'):
            self.lab.adopt(OWNER,self.original,2,'unsafe restore',operator=True)
        self.assertEqual(self.candidate,self.lab.task(OWNER)['current_design'])
        self.lab.adopt(OWNER,self.original,2,'actual Pi decision in own active task')

    def test_outstanding_or_unknown_operation_rejects_restore(self):
        op=self.lab.run(OWNER,'unexecuted',self.candidate)
        for status in ('QUEUED','RUNNING','UNKNOWN'):
            with self.store.connect() as db:db.execute('UPDATE design_operations SET status=? WHERE id=?',(status,op['id']))
            with self.assertRaisesRegex(ValueError,'REQUIRES_IDLE'):
                self.lab.adopt(OWNER,self.original,2,'unsafe pending restore',operator=True)

    def test_revision_drift_rejects_without_erasing_history(self):
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):
            self.lab.adopt(OWNER,self.original,1,'stale view',operator=True)
        self.assertEqual(2,self.lab.task(OWNER)['revision'])


if __name__=='__main__':unittest.main()
