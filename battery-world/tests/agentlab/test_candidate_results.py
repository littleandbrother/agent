import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bfworld.agentlab.candidate_results import CandidateResults, sections
from bfworld.agentlab.paper_sessions import ReadOnlyStore, reader
from bfworld.agentlab.preview_publication import publish
from bfworld.agentlab.product_results import ProductResults
from bfworld.agentlab.store import canonical, identity


class CandidateResultsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.owner = 'pi-original'; (self.root / 'state').mkdir()
        with self.db() as db:
            db.executescript('''CREATE TABLE design_tasks(owner,task_id,current_design,intent,submission,environment,contract,revision,plan,status);
                CREATE TABLE design_snapshots(owner,design_id,value);
                CREATE TABLE design_events(owner,seq,kind,created);
                CREATE TABLE design_operations(owner,id,status,request,error,created);''')
        self.native = self.root / 'engineering' / 'eng-selected'; self.native.mkdir(parents=True)
        data = b'actual selected build fixture'; (self.native / 'project-firmware.hex').write_bytes(data)
        self.job = dict(status='SUCCEEDED', project_sha256='source-current', parameters={'project_path':'fw/project.json'},
                        result={'artifacts':[dict(name='project-firmware.hex', sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))]})
        self.app = SimpleNamespace(store=ReadOnlyStore(self.root / 'state'), engineering=SimpleNamespace(root=self.root/'engineering', get=self.get_job))
        self.cat = reader(ProductResults, self.app, _checked={})
        self.view = CandidateResults(self.cat)
        self.design = self.install('current')
        self.current = self.design['design_id']
        self.old = self.install('old')['design_id']
        self.acceptance = dict(full_product_passed=False, digital_engineering_status='FAIL',
            functional_gates=[dict(id='pcb_connectivity_drc',label='PCB',status='FAIL'),dict(id='delivery_version',label='交付',status='PASS')],physical_validation='NOT_TESTED')
        with self.db() as db:
            db.execute('INSERT INTO design_tasks VALUES(?,?,?,?,?,?,?,?,?,?)', (self.owner,'task-original',self.old,
                canonical({'working_design':self.current}),canonical({'design_id':self.current,'submission_id':'S-original','acceptance':self.acceptance}),
                canonical({'mode':'paper-native-v1','environment_id':'env'}),canonical({'goal':'fixture'}),1,'{}','CONTINUE'))
            db.execute('INSERT INTO design_events VALUES(?,?,?,?)',(self.owner,1,'submitted',1))

    def db(self):
        return sqlite3.connect(self.root / 'state/workbench.sqlite')

    def tearDown(self): self.tmp.cleanup()

    def get_job(self, owner, key):
        if owner != self.owner or key != 'eng-selected': raise PermissionError('foreign job')
        return self.job

    def install(self, label):
        content = {f'{label}/board.epcb2':b'native board '+label.encode(),f'{label}/sheet.esch2':b'native schematic '+label.encode(),
                   'fw/main.c':b'int main(void) {}'}
        value = dict(files={k:dict(sha256=hashlib.sha256(v).hexdigest(),bytes=len(v)) for k,v in content.items()},
            projects={'fw/project.json':dict(kind='firmware-nrf52832',project_sha256='source-current')},
            selected_jobs={'eng-selected':dict(project_sha256='source-current',result_sha256=identity(self.job['result']))},sources={})
        did = 'D-' + identity(value); value['design_id'] = did
        dest = self.root / 'design-lab' / self.owner / 'designs' / did; (dest/'inputs').mkdir(parents=True)
        (dest / 'snapshot.json').write_text(canonical(value))
        for name, data in content.items():
            path = dest/'inputs'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        with self.db() as db: db.execute('INSERT INTO design_snapshots VALUES(?,?,?)',(self.owner,did,canonical(value)))
        return value

    def image(self, text='preview', dependency=None):
        path = self.root/'render.svg'; path.write_text('<svg>'+text+'</svg>')
        key = dependency or f'candidate/{self.current}/input/current/board.epcb2'
        return dict(path=path,name='pcb.svg',label='PCB',sections=['pcb'],sources=[key])

    def test_current_projection_keeps_adopted_and_submitted_distinct(self):
        _, files, meta = self.view.collect(self.owner)
        self.assertEqual(self.current,meta['working_design_id']); self.assertEqual(self.old,meta['adopted_design_id'])
        self.assertEqual(self.current,meta['submitted_design_id']); self.assertFalse(meta['verdict']['passed'])
        self.assertEqual({'FAIL','PASS'},{g['status'] for g in meta['verdict']['stages']})
        self.assertTrue(all(self.current in f['id'] for f in files))
        self.assertTrue(any('/job/eng-selected/' in f['id'] for f in files)); self.assertFalse(any('/old/' in f['id'] for f in files))

    def test_selected_build_and_source_must_match(self):
        self.job['project_sha256']='different-source'
        with self.assertRaisesRegex(ValueError,'SELECTED_JOB_CHANGED'): self.view.collect(self.owner)

    def test_source_download_owner_and_path_isolation(self):
        key = f'candidate/{self.current}/input/current/board.epcb2'
        self.assertTrue(self.view.file(self.owner,key)[0].is_file())
        with self.assertRaises(PermissionError): self.view.file('foreign',key)
        with self.assertRaises(PermissionError): self.view.file(self.owner,f'candidate/{self.current}/input/../snapshot.json')

    def test_publication_is_idempotent_immutable_and_refreshes_version(self):
        before = self.view.version(self.owner)
        view = self.image(); a = publish(self.cat,self.owner,self.current,[view],renderer={'version':'1'})
        b = publish(self.cat,self.owner,self.current,[view],renderer={'version':'1'})
        self.assertEqual(a,b); self.assertNotEqual(before,self.view.version(self.owner))
        _, files, _ = self.view.collect(self.owner)
        derived = next(f for f in files if f.get('role')=='preview')
        self.assertEqual(['pcb'],derived['sections']); self.assertTrue(derived['integrity'])

    def test_historical_preview_remains_exact_after_new_publication(self):
        first = publish(self.cat,self.owner,self.current,[self.image('first')],renderer={'version':'1'})
        old = f"preview/{self.current}/{first['publication_id']}/pcb.svg"
        publish(self.cat,self.owner,self.current,[self.image('second')],renderer={'version':'2'})
        self.assertEqual('<svg>first</svg>',self.view.file(self.owner,old)[0].read_text())

    def test_tampered_native_dependency_hides_preview_and_refuses_download(self):
        publication = publish(self.cat,self.owner,self.current,[self.image()],renderer={})
        key = f'candidate/{self.current}/input/current/board.epcb2'
        source, _ = self.view.file(self.owner,key); source.write_bytes(b'tampered')
        _, files, meta = self.view.collect(self.owner)
        self.assertEqual(['PREVIEW_SOURCE_CHANGED'],meta['preview_errors'])
        self.assertFalse(any(f.get('role')=='preview' for f in files))
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):
            self.view.file(self.owner,f"preview/{self.current}/{publication['publication_id']}/pcb.svg")

    def test_tampered_derived_file_refuses_download(self):
        result = publish(self.cat,self.owner,self.current,[self.image()],renderer={})
        key = f"preview/{self.current}/{result['publication_id']}/pcb.svg"
        self.view.file(self.owner,key)[0].write_text('tampered')
        with self.assertRaisesRegex(ValueError,'FILE_INVALID'): self.view.file(self.owner,key)

    def test_wrong_candidate_and_missing_dependencies_rejected(self):
        with self.assertRaisesRegex(ValueError,'CURRENT_CANDIDATE_REQUIRED'):
            publish(self.cat,self.owner,self.old,[self.image()],renderer={})
        with self.assertRaisesRegex(ValueError,'NOT_IN_CANDIDATE'):
            publish(self.cat,self.owner,self.current,[self.image(dependency='candidate/'+self.old+'/input/old/board.epcb2')],renderer={})
        view = self.image(); view['name'] = '../escape.svg'
        with self.assertRaisesRegex(ValueError,'NAME_INVALID'): publish(self.cat,self.owner,self.current,[view],renderer={})

    def test_native_extensions_are_in_the_correct_sections(self):
        self.assertEqual(['schematic'],sections('native/sheet.esch2'))
        self.assertEqual(['pcb'],sections('native/board.epcb2'))
        self.assertEqual(['schematic','pcb'],sections('native/project.eprj3'))

    def test_federated_read_does_not_settle_waiting_operation(self):
        from bfworld.agentlab.design_lab import paper_candidate
        with self.db() as db: db.execute('INSERT INTO design_operations VALUES(?,?,?,?,?,?)',(self.owner,'pending','WAITING_NATIVE','{}',None,1))
        lab = SimpleNamespace(store=self.app.store,root=self.root/'design-lab',
            task=lambda owner:{**self.view.task(owner),'contract':{},'plan':{}},
            design=lambda owner,design:self.view.design(owner,design),
            app=SimpleNamespace(skills=SimpleNamespace(catalog=lambda owner:{'skills':[]})))
        with patch.object(paper_candidate,'selector',return_value={'decision':'fixture'}), patch.object(paper_candidate,'refresh',side_effect=AssertionError('read attempted mutation')):
            result = paper_candidate.frozen_view(lab,self.owner)
        self.assertEqual('WAITING_NATIVE',result['operations'][0]['status'])


if __name__ == '__main__': unittest.main()
