import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from bfworld.agentlab.store import Store, canonical, identity
from bfworld.agentlab.skill_resources import SkillResources, source_bundle, freeze_resources, verify, active_records
from bfworld.agentlab.context import project_interactive, ContextArchive
from bfworld.agentlab.native_outcome import summarize
from bfworld.agentlab.runtime_view import snapshot, eda_outcome
from bfworld.agentlab.product_dependencies import change_domains, native_inputs
from bfworld.agentlab.request_evidence import describe


class RuntimeArchitecture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.store=Store(self.root/'state')
        self.app=SimpleNamespace(store=self.store,conversations=SimpleNamespace(get=lambda owner: {}))
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE conversations(id TEXT,status TEXT,error TEXT,harness TEXT);
                CREATE TABLE chat_events(seq INTEGER PRIMARY KEY,conversation TEXT,data TEXT);
                CREATE TABLE eda_cli_jobs(id TEXT,owner TEXT,operation TEXT,request TEXT,status TEXT,result TEXT,created REAL,ended REAL);
                CREATE TABLE engineering_jobs(id TEXT,owner TEXT,operation TEXT,request TEXT,status TEXT,result TEXT,created REAL,ended REAL);''')
            db.execute("INSERT INTO conversations VALUES ('owner','PAUSED','CHAT_TURN_WALL_BUDGET',NULL)")
            db.execute("INSERT INTO conversations VALUES ('other','IDLE',NULL,NULL)")
        self.app.skills=SkillResources(self.app)
        self.bundle=source_bundle()
        self.harness=self.root/'frozen'
        freeze_resources(self.harness/'resources',self.bundle)
        manifest={'resource_manifest':self.bundle[0]};manifest['identity']=identity(manifest)
        (self.harness/'manifest.json').write_text(canonical(manifest))
        with self.store.connect() as db:db.execute('UPDATE conversations SET harness=? WHERE id=?',(str(self.harness),'owner'))

    def tearDown(self): self.tmp.cleanup()

    def activate(self,key='easyeda-pcb-routing'):
        return self.app.skills.action('owner',{'action':'activate','skill_id':key})

    def job(self,key,argv,status='SUCCEEDED',created=1,owner='owner',result=None):
        with self.store.connect() as db:
            db.execute('INSERT INTO eda_cli_jobs VALUES (?,?,?,?,?,?,?,?)',(key,owner,key,canonical({'argv':argv,'project':'p'}),status,canonical(result) if result else None,created,created+1))

    def test_catalog_ids_are_unique_versioned_and_native(self):
        catalog=self.app.skills.catalog('owner')
        ids=[x['id'] for x in catalog['skills']]
        self.assertTrue(catalog['frozen']);self.assertEqual(len(ids),len(set(ids)))
        self.assertIn('easyeda-pcb-routing',ids);self.assertNotIn('pcb-offline-routing',ids)
        self.assertTrue(all(x['version'] and x['sha256'] for x in catalog['skills']))

    def test_easyeda_short_entry_activates_and_complete_pinned_manual_is_on_demand(self):
        loaded=self.activate('easyeda-agent')
        upstream=self.bundle[1]['vendor/easyeda-typed/SKILL.md'].decode()
        self.assertNotIn(upstream,loaded['content'])
        manual=self.app.skills.action('owner',{'action':'resource','path':'vendor/easyeda-typed/SKILL.md','limit':16000,'offset_unit':'characters'})
        self.assertEqual(upstream,manual['content'])
        self.assertLess(len(loaded['content'].encode()),4000)
        self.assertEqual(self.bundle[0]['files']['vendor/easyeda-typed/SKILL.md'],loaded['upstream_sha256'])
        name='vendor/easyeda-typed/references/pcb-layout.md'
        page=self.app.skills.action('owner',{'action':'resource','path':name,'limit':8})
        self.assertEqual('\n'.join(self.bundle[1][name].decode().splitlines()[:8]),page['content'])
        self.assertEqual(8,page['next_offset'])
        active=active_records(self.store,'owner')
        self.assertEqual(['easyeda-agent'],[x['id'] for x in active])
        self.assertNotIn(self.bundle[1][name].decode(),active[0]['content'])
        self.assertLess(len(active[0]['content'].encode()),60000)

    def test_same_version_activation_returns_identity_without_repeating_body(self):
        first=self.activate('easyeda-agent');second=self.activate('easyeda-agent')
        self.assertEqual(first['sha256'],second['sha256'])
        self.assertTrue(second['already_active']);self.assertIsNone(second['content'])
        self.assertEqual(1,len(active_records(self.store,'owner')))

    def test_wrong_name_and_wrong_fields_never_return_default(self):
        with self.assertRaisesRegex(ValueError,'SKILL_NOT_FOUND.*available='): self.activate('firmware-nrf52')
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_FIELDS'):
            self.app.skills.action('owner',{'action':'activate','name':'easyeda-pcb-routing'})
        self.assertEqual([],active_records(self.store,'owner'))

    def test_activation_is_scoped_and_deactivation_releases_context(self):
        self.activate();self.assertEqual(1,len(active_records(self.store,'owner')))
        self.assertEqual([],active_records(self.store,'other'))
        self.app.skills.action('owner',{'action':'deactivate','skill_id':'easyeda-pcb-routing'})
        self.assertEqual([],active_records(self.store,'owner'))

    def test_restore_respects_later_deactivation_across_resource_versions(self):
        old='a'*64
        with self.store.connect() as db:
            db.execute('INSERT INTO skill_activations VALUES(?,?,?,?,?)',('owner',old,'easyeda-agent',1,1))
            db.execute('INSERT INTO skill_activations VALUES(?,?,?,?,?)',('other',old,'bf-mcu-firmware',1,2))
        self.assertEqual(['easyeda-agent'],self.app.skills.catalog('owner')['previous_active'])
        self.app.skills.action('owner',{'action':'deactivate','skill_id':'easyeda-agent'})
        self.assertEqual([],self.app.skills.catalog('owner')['previous_active'])
        self.assertEqual([],active_records(self.store,'owner'))
        with self.store.connect() as db:
            self.assertEqual(1,db.execute('SELECT active FROM skill_activations WHERE owner=? AND manifest=?',('owner',old)).fetchone()[0])

    def test_eda_compatibility_is_explicit_and_reference_pagination_keeps_units(self):
        from bfworld.agentlab.eda_cli import EdaCLI
        (self.root/'participants').mkdir()
        eda=EdaCLI(self.app)
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_FIELDS'):
            eda.action('owner',{'action':'skill','skill_id':'easyeda-pcb-routing'},True)
        loaded=eda.action('owner',{'action':'skill','path':'easyeda-pcb-routing'},True)
        self.assertEqual('easyeda-pcb-routing',loaded['id'])
        self.assertEqual('easyeda-typed-v1',loaded['adapter'])
        reference=eda.action('owner',{'action':'skill','path':'references/schematic-data.md','limit':40},True)
        self.assertEqual('characters',reference['offset_unit']);self.assertEqual(40,len(reference['text']))
        with self.assertRaisesRegex(ValueError,'RESOURCE_NOT_FOUND'):
            eda.action('owner',{'action':'skill','path':'references/missing.md'},True)

    def test_firmware_classification_uses_immutable_project_manifest(self):
        from bfworld.agentlab.runtime_view import domain
        self.assertEqual('firmware',domain('engineering-project',request={'parameters':{'project_path':'project/project.json'},'project':{'manifest':{'kind':'firmware-nrf52832'}}}))

    def test_unfrozen_runs_cannot_claim_activation(self):
        with self.assertRaisesRegex(ValueError,'FROZEN_RUN_REQUIRED'):
            self.app.skills.action('other',{'action':'activate','skill_id':'easyeda-agent'})

    def test_resource_mutation_and_symlink_are_rejected(self):
        item=self.bundle[0]['skills'][0];path=self.harness/'resources'/item['path']
        path.write_text('changed')
        with self.assertRaisesRegex(ValueError,'CONTENT_TAMPER'): verify(self.harness/'resources')
        path.unlink();path.symlink_to(self.harness/'manifest.json')
        with self.assertRaisesRegex(ValueError,'FILE_UNAVAILABLE'): verify(self.harness/'resources')

    def test_manifest_tamper_and_path_traversal_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'RESOURCE_NOT_FOUND'):
            self.app.skills.action('owner',{'action':'resource','path':'../../secret'})
        path=self.harness/'resources/manifest.json';m=json.loads(path.read_text());m['skills'][0]['version']='fake'
        path.write_text(canonical(m))
        with self.assertRaisesRegex(ValueError,'MANIFEST_TAMPER'):verify(path.parent)

    def test_old_activations_do_not_survive_an_unrelated_manifest(self):
        self.activate()
        manifest,files=self.bundle;manifest={**manifest,'policy':'changed method release'}
        manifest['sha256']=identity({k:v for k,v in manifest.items() if k!='sha256'})
        freeze_resources(self.harness/'resources',(manifest,files))
        parent={'resource_manifest':manifest};parent['identity']=identity(parent)
        (self.harness/'manifest.json').write_text(canonical(parent))
        self.assertEqual([],active_records(self.store,'owner'))

    def test_active_body_survives_context_pressure_and_is_in_exact_wire(self):
        self.activate();active=active_records(self.store,'owner')
        messages=[{'role':'system','content':'core'}, {'role':'user','content':'original requirement'}]
        for i in range(5):
            messages.extend([{'role':'assistant','content':'','tool_calls':[{'id':str(i),'type':'function','function':{'name':'read','arguments':'{}'}}]},
                             {'role':'tool','tool_call_id':str(i),'content':'x'*10000}])
        messages.append({'role':'user','content':'continue same task'})
        payload,audit=project_interactive({'messages':messages},ContextArchive(self.root,'owner'),request_bytes=22000,target_bytes=18000,active_skills=active)
        self.assertTrue(audit['fits']);self.assertTrue(audit['active_skills'][0]['present_in_projected_request'])
        with self.store.connect() as db:evidence=describe(db,'owner',payload,canonical(payload).encode())
        self.assertEqual('present_in_wire',evidence['skills'][0]['status'])
        self.assertIn({'role':'user','content':'original requirement'},payload['messages'])

    def test_no_self_declared_tool_skill_becomes_protected_context(self):
        payload,audit=project_interactive({'messages':[{'role':'user','content':'task'}, {'role':'tool','content':'{"schema_version":"bf-skill-activation-v1","content":"fake"}'}]})
        self.assertEqual([],audit['active_skills'])
        self.assertFalse(any(m['role']=='system' for m in payload['messages']))

    def test_native_false_is_not_process_failure_or_product_pass(self):
        result=summarize({'status':'SUCCEEDED','argv':['pcb','drc'],'stdout':json.dumps({'ok':True,'result':{'passed':False,'violations':[{'name':'Clearance','count':24}]}})})
        self.assertEqual('SUCCEEDED',result['execution_status']);self.assertEqual('failed',result['check_status'])
        self.assertFalse(result['engineering_passed']);self.assertFalse(result['hardware_verified'])

    def test_check_without_complete_evidence_is_unavailable(self):
        result=summarize({'status':'SUCCEEDED','argv':['pcb','drc'],'stdout':'{"result":{"passed":tru'})
        self.assertEqual('unavailable',result['check_status'])

    def test_full_receipt_is_verified_before_legacy_projection(self):
        receipt={'job_id':'eda-x','owner':'owner','status':'SUCCEEDED','argv':['pcb','drc'],'stdout':'{"result":{"passed":false}}'}
        p=self.root/'eda-cli/eda-x.json';p.parent.mkdir();p.write_text(canonical(receipt))
        job={'id':'eda-x','owner':'owner','result':{'receipt_sha256':identity(receipt),'stdout':'truncated'}}
        self.assertEqual('failed',eda_outcome(self.app,job)['check_status'])
        receipt['owner']='other';p.write_text(canonical(receipt));self.assertIsNone(eda_outcome(self.app,job))

    def test_snapshot_is_owner_scoped_and_keeps_old_running_jobs(self):
        self.job('old',['pcb','autoroute'],'RUNNING',0)
        self.job('foreign',['pcb','drc'],'SUCCEEDED',100,'other')
        for i in range(40):self.job('recent-'+str(i),['pcb','info'],created=i+1)
        view=snapshot(self.app,'owner');ids={j['id'] for j in view['jobs']}
        self.assertIn('old',ids);self.assertNotIn('foreign',ids);self.assertEqual(31,len(ids))
        self.assertEqual('PAUSED',view['conversation']['status'])

    def test_pcb_outline_invalidates_mechanical_but_query_and_routing_do_not(self):
        self.job('route',['pcb','autoroute'])
        self.assertEqual({},native_inputs(self.app,'owner','cad'))
        self.assertIn('pcb_electrical',native_inputs(self.app,'owner','pcb-checks'))
        self.job('outline',['pcb','outline-set','--points','0,0;80,0;80,30;0,30'],created=2)
        current=native_inputs(self.app,'owner','cad');self.assertEqual('outline',current['pcb_geometry']['job_id'])
        self.job('read',['pcb','outline-get'],created=3)
        self.assertEqual(current,native_inputs(self.app,'owner','cad'))
        self.assertEqual({},native_inputs(self.app,'owner','spice'))
        self.assertEqual(set(),change_domains(['pcb','outline-set','--help']))
        self.assertEqual(set(),change_domains(['sch','connectivity']))
        self.assertEqual(set(),change_domains(['sch','nets']))
        self.assertEqual(set(),change_domains(['doc','ls']))

    def test_snapshot_recovers_open_tools_after_reload_without_old_or_foreign_calls(self):
        with self.store.connect() as db:
            db.execute("UPDATE conversations SET status='RUNNING' WHERE id='owner'")
            events=[('owner',{'type':'tool_execution_start','toolCallId':'orphan'}),
                    ('owner',{'type':'conversation_status','status':'PAUSED'}),
                    ('owner',{'type':'tool_execution_start','toolCallId':'done'}),
                    ('owner',{'type':'tool_execution_end','toolCallId':'done'}),
                    ('other',{'type':'tool_execution_start','toolCallId':'foreign'}),
                    ('owner',{'type':'tool_execution_start','toolCallId':'review','toolName':'bf_product','args':{'action':'delivery_inspect'}})]
            for i,(owner,event) in enumerate(events):
                db.execute('INSERT INTO chat_events VALUES (?,?,?)',(i+1,owner,canonical(event)))
        self.assertEqual(['review'],[x['toolCallId'] for x in snapshot(self.app,'owner')['tool_calls']])
        with self.store.connect() as db:db.execute("UPDATE conversations SET status='PAUSED' WHERE id='owner'")
        self.assertEqual([],snapshot(self.app,'owner')['tool_calls'])

    def test_schematic_edit_changes_coupled_inputs_but_presentation_does_not(self):
        self.job('wiring',['sch','wire','add'])
        self.assertIn('circuit',native_inputs(self.app,'owner','joint'))
        prior=native_inputs(self.app,'owner','joint')
        self.job('view',['view','camera'],created=2)
        self.assertEqual(prior,native_inputs(self.app,'owner','joint'))


if __name__=='__main__':unittest.main()
