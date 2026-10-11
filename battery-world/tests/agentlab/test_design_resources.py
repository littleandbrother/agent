import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from bfworld.agentlab.store import Store,identity,canonical
from bfworld.agentlab.skill_resources import SkillResources,freeze_resources,active_records
from bfworld.agentlab.design_lab.resources import bundle
from bfworld.agentlab.context import project_interactive

OWNER='pi-chat-0123456789abcdef'


class DesignResources(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        home=Path(self.tmp.name);self.store=Store(home/'state');self.harness=home/'harness'
        methods=bundle();freeze_resources(self.harness/'resources',methods)
        manifest={'schema_version':'bf-design-controller-v1','resource_manifest':methods[0]}
        manifest['harness_id']='H-'+identity(manifest)
        (self.harness/'manifest.json').write_text(canonical(manifest))
        with self.store.connect() as db:
            db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY,harness TEXT)')
            db.execute('INSERT INTO conversations VALUES(?,?)',(OWNER,str(self.harness)))
        self.app=SimpleNamespace(store=self.store,conversations=SimpleNamespace(get=lambda o:{'id':o}))
        self.skills=SkillResources(self.app)

    def test_exact_catalog_load_and_restart_protect_same_skill_versions(self):
        catalog=self.skills.catalog(OWNER)
        self.assertEqual(2,len(catalog['skills']));self.assertTrue(catalog['frozen'])
        for item in catalog['skills']:
            loaded=self.skills.action(OWNER,{'action':'activate','skill_id':item['id']})
            self.assertEqual(item['sha256'],loaded['sha256'])
        SkillResources(self.app)
        records=active_records(self.store,OWNER);self.assertEqual(2,len(records))
        payload={'model':'deepseek-flash','messages':[{'role':'system','content':'core'},
                    {'role':'user','content':'keep original task'},
                    {'role':'assistant','content':'old completed fact'*8000},
                    {'role':'user','content':'resume original task'}]}
        result,audit=project_interactive(payload,request_bytes=40000,target_bytes=25000,active_skills=records,compact_state=True)
        self.assertEqual(2,len(audit['active_skills']))
        for record in records:self.assertIn(record['content'],json.dumps(result,ensure_ascii=False).replace('\\n','\n'))

    def test_wrong_ID_never_activates_default(self):
        with self.assertRaisesRegex(ValueError,'SKILL_NOT_FOUND.*available='):
            self.skills.action(OWNER,{'action':'activate','skill_id':'missing'})
        self.assertEqual([],active_records(self.store,OWNER))

    def test_mutable_document_and_harness_manifest_rejected(self):
        p=self.harness/'resources/bf-design-task-control-v1/SKILL.md';p.write_text('tampered')
        with self.assertRaisesRegex(ValueError,'RESOURCE_CONTENT_TAMPER'):self.skills.catalog(OWNER)


if __name__=='__main__':unittest.main()
