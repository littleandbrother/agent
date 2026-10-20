import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from bfworld.agentlab.store import Store, canonical
from bfworld.agentlab.design_lab.service import DesignLab
from bfworld.agentlab.design_lab.repository import Repository, file_hash, name

OWNER='pi-chat-a1234567890abcde'
ORIGINAL='pi-chat-b1234567890abcde'
OTHER='pi-chat-c1234567890abcde'


class RepositoryCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.store=Store(self.root/'runtime/state')
        with self.store.connect() as db:
            db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY)')
            db.executemany('INSERT INTO conversations VALUES(?)',[(OWNER,),(OTHER,)])
        self.lab=DesignLab(SimpleNamespace(store=self.store,engineering=SimpleNamespace(lock=threading.Lock())),start_worker=False)
        baseline=self.root/'baseline';baseline.mkdir()
        pins={}
        def save(logical,text):
            p=baseline/logical;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            pins[logical]={'sha256':file_hash(p),'bytes':p.stat().st_size}
        ids={'adopted_design':'D-adopted','submitted_design':'D-submitted'}
        for role,key in ids.items():
            prefix=f'private/design-lab/{ORIGINAL}/designs/{key}/'
            save(prefix+'inputs/firmware/说明.md','original firmware '+role)
            snapshot={'schema_version':'bf-paper-design-snapshot-v1','design_id':key,
                'files':{'firmware/说明.md':pins[prefix+'inputs/firmware/说明.md']},'selected_jobs':{}}
            save(prefix+'snapshot.json',canonical(snapshot))
        gates=[]
        for key,status in [('firmware_event_logic','PASS'),('power_load_chain','FAIL'),('geometry_fit','UNEVALUABLE')]:
            logical='campaign/campaign/reviews/'+key+'.json'
            save(logical,canonical({'id':key,'status':status}))
            gates.append({'id':key,'label':key,'status':status,'evidence':{'path':'campaign/reviews/'+key+'.json','sha256':pins[logical]['sha256']}})
        manifest={'files':pins,'p01':{'owner':ORIGINAL,**ids,'gates':gates,'physical':'NOT_TESTED',
            'digital_status':'REPAIR_REQUIRED','submission_id':'S-frozen'}}
        (baseline/'manifest.json').write_text(canonical(manifest))
        self.profile={'id':'E-v2','baseline':{'path':str(baseline),'manifest_sha256':file_hash(baseline/'manifest.json')},
            'protected_owners':[ORIGINAL]}
        self.repo=Repository(self.lab,self.profile);self.lab.repository=self.repo
        self.body={'action':'repository_import','operation_id':'import-one'}

    def imported(self):
        return self.repo.handle(OWNER,self.body,True)

    def test_submitted_and_adopted_remain_distinct(self):
        x=self.imported();view=self.repo.view(x['project_id'],OWNER)
        self.assertNotEqual(x['submitted'],x['adopted'])
        self.assertEqual(x['adopted'],view['project']['adopted'])
        self.assertEqual(x['submitted'],view['project']['submitted'])
        by_id={s['id']:s for s in view['systems']}
        self.assertEqual('D-submitted',by_id[x['submitted']]['origin_design_id'])
        self.assertEqual('D-adopted',by_id[x['adopted']]['origin_design_id'])

    def test_original_gate_statuses_and_physical_kept(self):
        x=self.imported();s=self.repo.system(x['project_id'],x['submitted'])
        self.assertEqual({'firmware_event_logic':'PASS','power_load_chain':'FAIL','geometry_fit':'UNEVALUABLE'},
                         {k:v['status'] for k,v in s['validations'].items()})
        self.assertEqual('NOT_TESTED',s['physical']);self.assertEqual('REPAIR_REQUIRED',s['digital_status'])

    def test_no_fabricated_domain_history(self):
        x=self.imported();view=self.repo.view(x['project_id'],OWNER)
        self.assertEqual([],view['domain_commits']);self.assertEqual([],view['contracts'])
        self.assertTrue(all(not s['history_fabricated'] for s in view['systems']))

    def test_idempotent_retry_has_one_journal_operation(self):
        x=self.imported();self.assertEqual(x,self.imported())
        with self.store.connect() as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM design_operations').fetchone()[0])

    def test_same_operation_different_request_rejected(self):
        self.imported()
        with self.assertRaisesRegex(ValueError,'OPERATION_CONFLICT'):
            self.repo.handle(OWNER,{**self.body,'different':True},True)

    def test_original_owner_protected(self):
        with self.assertRaisesRegex(PermissionError,'ORIGINAL_OWNER_PROTECTED'):
            self.repo.handle(ORIGINAL,self.body,True)

    def test_operator_required_for_migration(self):
        with self.assertRaisesRegex(PermissionError,'OPERATOR_REQUIRED'):self.repo.handle(OWNER,self.body,False)

    def test_other_owner_has_no_read_access(self):
        x=self.imported()
        with self.assertRaisesRegex(PermissionError,'PROJECT_NOT_OWNED'):self.repo.view(x['project_id'],OTHER)

    def test_actual_blob_readback_and_unicode(self):
        x=self.imported();p,ref=self.repo.artifact(x['project_id'],OWNER,x['submitted'],'firmware/说明.md')
        self.assertEqual('original firmware submitted_design',p.read_text())
        self.assertEqual(ref['sha256'],file_hash(p));self.assertEqual(0o400,p.stat().st_mode&0o777)

    def test_read_pagination_and_bad_range(self):
        x=self.imported();body={'action':'repository_read','project_id':x['project_id'],'system_id':x['submitted'],'path':'firmware/说明.md'}
        r=self.repo.handle(OWNER,{**body,'offset':0,'limit':8})
        self.assertEqual('original',r['content']);self.assertEqual(8,r['next_offset'])
        for bad in [{'offset':-1},{'limit':500000},{'offset':'0'}]:
            with self.assertRaisesRegex(ValueError,'READ_RANGE'):self.repo.handle(OWNER,{**body,**bad})

    def test_changed_frozen_source_rejected_atomically(self):
        p=self.root/'baseline/private/design-lab'/ORIGINAL/'designs/D-submitted/inputs/firmware/说明.md'
        p.write_text('changed')
        with self.assertRaisesRegex(ValueError,'BASELINE_ASSET_CHANGED'):self.imported()
        with self.store.connect() as db:
            self.assertEqual(0,db.execute('SELECT count(*) FROM design_projects').fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM design_operations').fetchone()[0])

    def test_changed_manifest_rejected(self):
        p=self.root/'baseline/manifest.json';p.write_text(p.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'BASELINE_MANIFEST_CHANGED'):self.imported()

    def test_changed_db_object_rejected(self):
        x=self.imported()
        with self.store.connect() as db:
            value=json.loads(db.execute('SELECT value FROM design_system_commits WHERE id=?',(x['submitted'],)).fetchone()['value'])
            value['digital_status']='PASS';db.execute('UPDATE design_system_commits SET value=? WHERE id=?',(canonical(value),x['submitted']))
        with self.assertRaisesRegex(ValueError,'OBJECT_TAMPER'):self.repo.system(x['project_id'],x['submitted'])

    def test_no_parallel_legacy_adoption_path(self):
        x=self.imported()
        self.assertEqual(x['project_id'],self.repo.bound(OWNER))
        self.assertEqual('bf-system-commit-v2',self.lab.design(OWNER,x['adopted'])['schema_version'])
        with self.assertRaisesRegex(ValueError,'REQUIRES_TYPED_ACTION'):
            self.lab.handle(OWNER,{'action':'adopt','design_id':x['submitted'],'expected_revision':1,'rationale':'test'})

    def test_path_escapes_rejected(self):
        for value in ['../x','/etc/passwd','x/../y','x\\y','x\x00y','x//y']:
            with self.subTest(value=value),self.assertRaises(ValueError):name(value)
