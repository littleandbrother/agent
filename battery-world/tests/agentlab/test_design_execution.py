"""Real no-model compiled C -> service checks -> adoption -> ZIP readback."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from bfworld.agentlab.store import Store
from bfworld.agentlab.design_lab.service import DesignLab
from bfworld.agentlab.design_lab.qualification import sources

OWNER='pi-chat-abcdef0123456789'
ENV=Path(__file__).resolve().parents[2]/'docs/agentlab/refactor-r0-r2-20261011/environment.json'


class RealExecution(unittest.TestCase):
    def test_actual_service_binding_adoption_package_and_tamper(self):
        env=json.loads(ENV.read_text())
        with tempfile.TemporaryDirectory() as home:
            store=Store(Path(home)/'state')
            with store.connect() as db:
                db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY)')
                db.execute('INSERT INTO conversations VALUES(?)',(OWNER,))
            lab=DesignLab(SimpleNamespace(store=store,engineering=SimpleNamespace(lock=threading.Lock())),start_worker=False)
            with patch('bfworld.agentlab.design_lab.baseline.environment',return_value=env):
                view=lab.configure(OWNER,env,sources(env,True))
            design=view['current_design']
            job=lab.run(OWNER,'compiled-reference',design)
            lab.execute(OWNER,job['id'])
            inspected=lab.inspect_check(OWNER,job['id'])
            self.assertTrue(inspected['acceptance']['scoped_passed'])
            self.assertFalse(inspected['acceptance']['full_product_passed'])
            self.assertEqual(0,inspected['execution']['new_native_solver_calls'])
            self.assertEqual(job['id'],lab.run(OWNER,'renamed-recovery',design)['id'])
            lab.adopt(OWNER,design,1,'No-Agent test only; select actual executed reference')
            submission=lab.submit(OWNER,job['id'],'No-Agent service qualification, not Pi evidence')
            self.assertTrue(Path(submission['package_path']).is_file())
            self.assertEqual(Path(submission['package_path']),lab.delivery(OWNER))
            with Path(submission['package_path']).open('ab') as stream:stream.write(b'TAMPER')
            with self.assertRaisesRegex(ValueError,'ZIP_TAMPER'):lab.delivery(OWNER)


if __name__=='__main__':unittest.main()
