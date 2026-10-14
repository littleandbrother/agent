import copy
import json
from pathlib import Path
import unittest

from test_design_repository import RepositoryCase, OWNER, OTHER
from bfworld.agentlab.store import canonical
from bfworld.agentlab.design_lab.repository_actions import materialize, task
from bfworld.agentlab.design_lab.repository_contracts import check, fingerprint, reuse_gates


SOURCES = {
 'project-fw-s132/main.c': '#define APP_ADV_INTERVAL 300\n#define MIN_CONN_INTERVAL MSEC_TO_UNITS(100, UNIT_1_25_MS)\n#define MAX_CONN_INTERVAL MSEC_TO_UNITS(200, UNIT_1_25_MS)\n.sample_period_ms = 5000,\n.adv_period_ms = 5000,',
 'project-chain/load-timeline.json': canonical({'actual_radio_timing': {'advertising_period_ms':187.5,
     'connection_period_range_ms':[100,200], 'connection_period_ms_used':100, 'sample_period_ms':5000}}),
 'project-chain/interface-params.json': canonical({'load_timing':{'actual_advertising_period_ms':187.5,
     'current_amplitudes_origin':'assumption'}, 'manual_action':{'manual_action_energy':0},
     'regulator':{'v_out_v':1.8}, 'storage':{'initial_v':4.2}, 'sece':{'resolved':False,'unresolved':['switching']}})}


class IntegrationCase(unittest.TestCase):
    imported = RepositoryCase.imported
    def setUp(self):
        RepositoryCase.setUp(self)
        self.imported_value = self.imported(); self.pid = self.imported_value['project_id']
        base = self.repo.system(self.pid, self.imported_value['submitted'])
        with self.store.connect() as db:
            for path, text in SOURCES.items():
                file = self.root/'fixture'/path; file.parent.mkdir(parents=True,exist_ok=True); file.write_text(text)
                base['files'][path] = self.repo.asset(db,file)
            base = self.repo._save_system(db, OWNER, {k:v for k,v in base.items() if k!='id'})
            db.execute('UPDATE design_projects SET submitted=? WHERE id=?',(base['id'],self.pid))
        self.base = base
        for domain,owner in [('power',OTHER),('firmware','pi-chat-d1234567890abcde')]:
            value={'id':'PT-'+domain,'project_id':self.pid,'owner':owner,'lead':OWNER,'role':domain,
                   'base_system':base['id'],'question':'fixture','completion':'source check','contract_ids':[],
                   'branch':domain+'/fixture','status':'QUEUED','submission':None}
            with self.store.connect() as db:
                db.execute('INSERT INTO design_professional_tasks VALUES(?,?,?,?,?,?)',
                           (value['id'],self.pid,owner,domain,'QUEUED',canonical(value)))
                db.execute('INSERT INTO design_branch_heads VALUES(?,?,?,?,?)',(self.pid,domain,value['branch'],None,0))
            materialize(self.repo,value)
        self.fw='pi-chat-d1234567890abcde'

    def action(self, owner, action, **kw):
        return self.repo.handle(owner,{'action':'repository_'+action,'project_id':self.pid,**kw})

    def domain(self, domain):
        owner=self.fw if domain=='firmware' else OTHER
        path='interfaces/'+domain+'.json'
        base=check(lambda p:SOURCES[p],self.base['files'])
        facts=base['facts']['firmware'] if domain=='firmware' else {k:base['facts'][k] for k in ('rail_v','storage_initial_v','manual_admission','sece_resolved')}
        content=canonical({'interface':facts,'sources':[{'path':p,'sha256':self.base['files'][p]['sha256'],'locator':'fixture'} for p in SOURCES]})
        self.action(owner,'write',operation_id='write-'+domain,path=path,content=content,expected_sha256=None)
        return self.action(owner,'commit',operation_id='commit-'+domain,paths=[path],expected_revision=0,rationale='source-bound declaration')

    def integrated(self):
        commits={d:self.domain(d)['id'] for d in ['power','firmware']}
        c=self.action(OWNER,'contract',operation_id='contract',domain_commits=commits,rationale='compare source facts')
        return self.action(OWNER,'integrate',operation_id='integrate',base_system=self.base['id'],
                           domain_commits=commits,contracts={'power-firmware':c['id']},expected_revision=1,rationale='fixture integration')

    def test_reopened_task_retains_files_and_prior_receipt(self):
        original=task(self.repo,OTHER)
        root=materialize(self.repo,original)
        code=root/'project-chain/load-timeline.json'
        code.write_text('interrupted working data')
        revised={**original,'question':'new public question','status':'QUEUED','previous_submission':'DC-old'}
        materialize(self.repo,revised)
        self.assertEqual('interrupted working data',code.read_text())
        self.assertEqual(revised,json.loads((root/'CURRENT-TASK.json').read_text()))
        self.assertEqual(2,len(list((root/'task-history').glob('*.json'))))

    def test_failed_startup_does_not_report_queued(self):
        from bfworld.agentlab.design_lab.repository_controller import state
        self.lab.controllers={}
        with self.store.connect() as db:
            db.execute("CREATE TABLE model_requests(id TEXT,owner TEXT,status TEXT,charged REAL,reserved REAL,usage TEXT)")
            db.execute("ALTER TABLE conversations ADD COLUMN status TEXT DEFAULT 'IDLE'")
            db.execute("ALTER TABLE conversations ADD COLUMN error TEXT")
            db.execute("UPDATE conversations SET status='FAILED',error='startup failed' WHERE id=?",(OTHER,))
        self.assertEqual('FAILED',state(self.repo,OWNER,OTHER)['status'])

    def test_declaration_cannot_change_unrelated_geometry_or_pcb_inputs(self):
        result=self.integrated();s=self.repo.system(self.pid,result['system_commit'])
        for gate in ['geometry_fit','pcb_connectivity_drc','schematic_bom_pins','source_domain']:
            if gate in self.base['validations']:
                self.assertEqual(self.base['validations'][gate]['status'],s['validations'][gate]['status'])

    def test_declaration_missing_field_and_wrong_source_rejected(self):
        facts=check(lambda p:SOURCES[p],self.base['files'])['facts']
        declaration={'interface':facts['firmware'],'sources':[{'path':'project-fw-s132/main.c','sha256':'wrong'}]}
        self.assertEqual('FAIL',check(lambda p:SOURCES[p],self.base['files'],{'firmware':declaration})['status'])
        del declaration['interface']['advertising_ms']
        self.assertEqual('UNEVALUABLE',check(lambda p:SOURCES[p],self.base['files'],{'firmware':declaration})['status'])

    def test_write_retry_and_compare_swap(self):
        body={'operation_id':'write','path':'interfaces/power.json','content':'{}','expected_sha256':None}
        one=self.action(OTHER,'write',**body)
        self.assertEqual(one,self.action(OTHER,'write',**body))
        with self.assertRaisesRegex(ValueError,'REVISION_CONFLICT'):
            self.action(OTHER,'write',**{**body,'operation_id':'stale','content':'new'})

    def test_specialist_cannot_write_other_domain_or_integrate(self):
        with self.assertRaisesRegex(PermissionError,'DOMAIN_WRITE_SCOPE'):
            self.action(OTHER,'write',operation_id='scope',path='project-fw-s132/main.c',content='changed',expected_sha256=None)
        with self.assertRaisesRegex(PermissionError,'LEAD_REQUIRED'):
            self.action(OTHER,'integrate',operation_id='lead')

    def test_branch_compare_swap(self):
        self.domain('firmware')
        with self.assertRaisesRegex(ValueError,'BRANCH_REVISION_CONFLICT'):
            self.action(self.fw,'commit',operation_id='stale',paths=['interfaces/firmware.json'],expected_revision=0,rationale='stale')

    def test_partial_commit_inherits_parent_sources_and_execution_need(self):
        path='project-fw-s132/main.c';first=self.base['files'][path]['sha256']
        changed=SOURCES[path]+'\n// new source in first commit\n'
        self.action(self.fw,'write',operation_id='first-source',path=path,content=changed,expected_sha256=first)
        a=self.action(self.fw,'commit',operation_id='source-commit',paths=[path],expected_revision=0,rationale='change source')
        self.action(self.fw,'write',operation_id='second-declaration',path='interfaces/firmware.json',content='{}',expected_sha256=None)
        b=self.action(self.fw,'commit',operation_id='partial-commit',paths=['interfaces/firmware.json'],expected_revision=1,rationale='add declaration')
        self.assertEqual(a['files'][path],b['files'][path])
        self.assertEqual(a['id'],b['parent'])
        self.assertEqual('RECHECK_REQUIRED',b['target_build'])
        self.assertEqual({path,'interfaces/firmware.json'},{c['path'] for c in b['cumulative_changes']})

    def test_exact_reuse_and_selective_invalidation(self):
        r=self.integrated();s=self.repo.system(self.pid,r['system_commit'])
        self.assertEqual('PASS',s['validations']['firmware_event_logic']['status'])
        self.assertEqual('UNEVALUABLE',s['validations']['geometry_fit']['status'])
        self.assertEqual('RECHECK_REQUIRED',s['validations']['power_load_chain']['status'])
        self.assertEqual(self.base['jobs'],s['jobs'])

    def test_source_check_and_injected_timing_negative(self):
        refs={k:{'sha256':str(i)} for i,k in enumerate(SOURCES)}
        r=check(lambda p:SOURCES[p],refs);self.assertEqual('PASS',r['status'])
        self.assertEqual('policy-radio-duty',r['issues'][0]['id'])
        bad=dict(SOURCES); d=json.loads(bad['project-chain/load-timeline.json'])
        d['actual_radio_timing']['advertising_period_ms']=5000
        bad['project-chain/load-timeline.json']=canonical(d)
        self.assertEqual('FAIL',check(lambda p:bad[p],refs)['status'])
        self.assertEqual('UNEVALUABLE',check(lambda p:'garbage',refs)['status'])

    def test_real_validation_binding_and_product_gate(self):
        r=self.integrated();s=r['system_commit']
        v=self.action(OWNER,'validate',operation_id='validate',system_id=s,scope='interface')
        self.assertEqual('PASS',v['status']);self.assertEqual(s,v['immutable_input'])
        with self.assertRaisesRegex(ValueError,'PRODUCT_GATES_NOT_PASSED'):
            self.action(OWNER,'decide',operation_id='adopt',system_id=s,expected_revision=2,decision='ADOPT_PASSED',rationale='bad')
        d=self.action(OWNER,'decide',operation_id='review',system_id=s,expected_revision=2,decision='RETAIN_FOR_REVIEW',rationale='keep review package')
        self.assertFalse(d['product_passed'])

    def test_contract_cannot_bind_other_commit(self):
        power=self.domain('power');fw=self.domain('firmware')
        with self.assertRaisesRegex(ValueError,'DOMAIN_IDENTITY_CONFLICT'):
            self.action(OWNER,'contract',operation_id='wrong',domain_commits={'power':fw['id'],'firmware':power['id']},rationale='wrong')

    def test_changed_code_requires_new_build(self):
        root=self.repo.root/'workspaces/PT-firmware'
        from bfworld.agentlab.design_lab.repository import file_hash
        p=root/'project-fw-s132/main.c'
        self.action(self.fw,'write',operation_id='code',path='project-fw-s132/main.c',content=p.read_text()+'\n// change',expected_sha256=file_hash(p))
        fw=self.action(self.fw,'commit',operation_id='code-commit',paths=['project-fw-s132/main.c'],expected_revision=0,rationale='fixture change')
        power=self.domain('power')
        with self.assertRaisesRegex(ValueError,'NEW_INPUT_EXECUTION_REQUIRED'):
            self.action(OWNER,'contract',operation_id='build',domain_commits={'power':power['id'],'firmware':fw['id']},rationale='unbuilt')

    def test_review_release_exact_file_manifest(self):
        r=self.integrated();s=r['system_commit']
        self.action(OWNER,'validate',operation_id='v',system_id=s,scope='interface')
        rel=self.action(OWNER,'release',operation_id='release',system_id=s,rationale='complete review fixture')
        import zipfile,hashlib
        with zipfile.ZipFile(self.repo.root/'releases'/(rel['id']+'.zip')) as z:
            for path,ref in rel['files'].items():self.assertEqual(ref['sha256'],hashlib.sha256(z.read('engineering/'+path)).hexdigest())
        self.assertEqual('NOT_TESTED',rel['physical'])

    def test_restore_preserves_history_and_new_commit(self):
        r=self.integrated();s=r['system_commit']
        self.action(OWNER,'validate',operation_id='v',system_id=s,scope='interface')
        d=self.action(OWNER,'decide',operation_id='restore',system_id=s,expected_revision=2,decision='RESTORE',rationale='explicit restore')
        self.assertNotEqual(s,d['to_design'])
        self.assertEqual(s,self.repo.system(self.pid,d['to_design'])['restored_from'])
        self.assertEqual(5,len(self.repo.view(self.pid,OWNER)['systems']))
