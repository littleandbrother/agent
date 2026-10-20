import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from test_design_repository import OWNER, OTHER
from test_repository_task_profiles import TaskProfileTests, curve_definition
from bfworld.agentlab.design_lab.repository_task_execution import current_execution
from bfworld.agentlab.design_lab.repository_node_realization import validate_manifest, import_native, VERSION
from bfworld.agentlab.design_lab.repository import file_hash


class NodeLineageTests(TaskProfileTests):
    def derivative(self, source, files=None):
        return self.repo.handle(OTHER,{'action':'repository_task_create','operation_id':'engineering-phase',
            'definition':curve_definition(.01),'source_project':source['project_id'],'source_system':source['id'],
            'files':files or {'notes/phase.md':'A new phase, preserving the sealed experiment.'}},True)

    def test_explicit_phase_reuses_original_execution_and_rechecks_requirements(self):
        source=self.create_curve(); tx=self.action('task_execute','original-execution',system_id=source['id'])
        child=self.derivative(source)
        actual=self.repo.handle(OTHER,{'action':'repository_task_execute','system_id':child['id'],'operation_id':'reuse'})
        self.assertTrue(actual['reused']);self.assertEqual(tx['id'],actual['id'])
        self.assertEqual(source['project_id'],actual['project_id'])
        checked=self.repo.handle(OTHER,{'action':'repository_validate','system_id':child['id'],'operation_id':'check'})
        self.assertEqual('FAIL',checked['result']['gates']['curve_accuracy']['status'])
        with self.repo.store.connect() as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM design_task_executions').fetchone()[0])

    def test_changed_input_cannot_reuse_inherited_execution(self):
        source=self.create_curve();self.action('task_execute','original',system_id=source['id'])
        child=self.derivative(source,{'observation.csv':'x,y\n1,2\n2,3\n'})
        self.assertIsNone(current_execution(self.repo,self.repo.system(child['project_id'],child['id'])))

    def test_no_global_reuse_without_explicit_lineage(self):
        source=self.create_curve();self.action('task_execute','original',system_id=source['id'])
        child=self.repo.handle(OTHER,{'action':'repository_task_create','operation_id':'unrelated','definition':curve_definition(),
            'files':{'reference.csv':'x,y\n1,2\n2,3\n','observation.csv':'x,y\n1,2.1\n2,3.1\n'}},True)
        self.assertIsNone(current_execution(self.repo,self.repo.system(child['project_id'],child['id'])))

    def test_inherited_artifact_mutation_is_rejected(self):
        source=self.create_curve();tx=self.action('task_execute','original',system_id=source['id']);child=self.derivative(source)
        artifact=self.repo.root/'blobs'/tx['artifacts']['samples.json']['sha256'];artifact.chmod(0o600);artifact.write_text('bad')
        with self.assertRaisesRegex(ValueError,'ARTIFACT_CHANGED'):
            current_execution(self.repo,self.repo.system(child['project_id'],child['id']))


class NodeGeometryTests(unittest.TestCase):
    def fixture(self):
        return {'schema_version':VERSION,'mechanical':{'clamp_length_mm':10,'base_thickness_mm':3,
            'motion_clearance_mm':2,'board_size_mm':[50,32,1.6],'board_origin_mm':[0,40,3]},
            'target':{'module':'E73-2G4M04S1B','mcu':'nRF52832-QFAA','pgood_gpio':'P0.11',
                'sensing':'internal TEMP','protocol':'BLE manufacturer data','supply_v':2.5},
            'judgment':'固定自由梁根部和板级接口。','assumptions':['电流待测'],'issues':['检查装配']}

    def test_board_cannot_intrude_into_beam_swept_volume(self):
        m=self.fixture();self.assertEqual(m,validate_manifest(m,{'width_m':.03}))
        m['mechanical']['board_origin_mm'][1]=29
        with self.assertRaisesRegex(ValueError,'INTERFERENCE'):validate_manifest(m,{'width_m':.03})

    def test_supply_identity_and_finite_geometry_are_enforced(self):
        m=self.fixture();m['target']['supply_v']=3.3
        with self.assertRaisesRegex(ValueError,'TARGET_ADAPTER'):validate_manifest(m,{'width_m':.03})
        m=self.fixture();m['mechanical']['clamp_length_mm']=float('nan')
        with self.assertRaisesRegex(ValueError,'GEOMETRY_RANGE'):validate_manifest(m,{'width_m':.03})


class NodeDeliveryRecoveryTests(unittest.TestCase):
    def state(self, realization, phase='node-engineering-realization'):
        from contextlib import ExitStack
        from bfworld.agentlab.design_lab.repository_task_state import state
        task={'id':'TD-node','phase':phase,'intent':'product','scope':{},'standards':{}}
        system={'id':'SC-node','files':{}}
        project={'id':'PR-node','submitted':'SC-node','adopted':'SC-old'}
        db=SimpleNamespace(execute=lambda *args:[])
        class Connection:
            def __enter__(self): return db
            def __exit__(self,*args): pass
        repo=SimpleNamespace(project=lambda *a:project,system=lambda *a:system,
            store=SimpleNamespace(connect=Connection),root=Path('/unused'))
        base='bfworld.agentlab.design_lab.'
        with ExitStack() as stack:
            for target,value in [
                ('repository_task_state.system_definition',task),
                ('repository_task_state.system_profile',{'adapter':'piezo-feedback-v1','report':'task-report-v1','roles':[]}),
                ('repository_task_state.check_files',None),
                ('repository_task_execution.pending_execution',None),
                ('repository_task_execution.current_execution',{'id':'TX-original','status':'SUCCEEDED'}),
                ('repository_validation.qualification',{'gates':{'service':{'status':'PASS'}}}),
                ('repository_task_reports.required',(Path('TR-complete'),{})),
                ('repository_node_realization.current',realization),
                ('repository_node_realization.native_bundle',{'id':'NN-native'}),
            ]: stack.enter_context(patch(base+target,return_value=value))
            return state(repo,OWNER,{'project_id':'PR-node'})

    def test_report_does_not_hide_unfinished_realization(self):
        result=self.state(None)
        self.assertEqual('READY_TO_REALIZE',result['stage'])
        self.assertEqual('TR-complete',result['report_id'])
        self.assertIn('task_realize',result['allowed_actions'])
        self.assertTrue(result['engineering_realization']['native_binding'].startswith('NN-'))

    def test_registered_realization_can_continue_same_version_delivery(self):
        result=self.state({'id':'NR-node','target':{'status':'BUILT'},'outputs':{'native/project.epro2':{}}})
        self.assertEqual('READY_TO_DELIVER',result['stage'])
        self.assertEqual('BUILT',result['engineering_realization']['target_status'])
        self.assertEqual(['native/project.epro2'],result['engineering_realization']['artifacts'])

    def test_reference_tasks_do_not_gain_engineering_actions(self):
        result=self.state(None,phase='reference')
        self.assertNotIn('task_realize',result['allowed_actions'])
        self.assertEqual('READY_TO_DELIVER',result['stage'])


class NodeNativeBindingTests(unittest.TestCase):
    """Replay measured native facts, then inject cross-version/pin/export faults."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/'native';self.source.mkdir()
        app=Path(__file__).resolve().parents[2]
        fixture=json.loads((app/'configs/reference_cases/node-engineering/native-binding-fixture.json').read_text())
        self.receipt={'system_id':'SC-engineering','project_id':'PR-node','design_sha256':'design',
            'manifest_sha256':'manifest','native_project_uuid':fixture['project_uuid'],
            'schematic_document':fixture['schematic_document'],'pcb_document':fixture['pcb_document']}
        def readback(file,document,value):
            self.write(file,{'ok':True,'context':{'projectUuid':fixture['project_uuid'],'documentUuid':document},'result':value})
        readback('schematic-readback.json',fixture['schematic_document'],{'components':fixture['schematic_components']})
        readback('pcb-readback.json',fixture['pcb_document'],{'components':fixture['pcb_components']})
        readback('pcb-drc.json',fixture['pcb_document'],{'passed':True,'violations':[]})
        self.write('pcb-dump.json',{'outline':fixture['outline']});self.write('geometry.json',fixture['geometry'])
        for f in ('pcb-tracks.json','pcb-vias.json'): self.write(f,{})
        for f in ('schematic.svg','pcb.svg','pcb-bottom.svg','bom.csv'): (self.source/f).write_text('native output')
        self.archive()
        self.pin()
        self.root=Path(self.tmp.name)/'repository';(self.root/'blobs').mkdir(parents=True)
        manifest={'mechanical':{'board_size_mm':[50,32,1.6]}}
        path=self.root/'blobs/manifest';path.write_text(json.dumps(manifest));sha=file_hash(path)
        path.rename(path.with_name(sha));self.receipt['manifest_sha256']=sha;self.pin()
        self.system={'id':'SC-engineering','project_id':'PR-node','task_definition':{'phase':'node-engineering-realization'},
            'files':{'design.json':{'sha256':'design'},'notes/engineering-realization.json':{'sha256':sha}}}
        self.repo=SimpleNamespace(root=self.root,leader=lambda project,owner:{'id':'PR-node'},system=lambda project,system:self.system,
            asset=lambda db,path,sha:{'sha256':sha},mutate=lambda owner,body,apply:apply(None))
        self.body={'project_id':'PR-node','system_id':'SC-engineering'}

    def write(self,file,value): (self.source/file).write_text(json.dumps(value))

    def archive(self,wrong=False):
        with zipfile.ZipFile(self.source/'project.epro2','w') as z:
            z.writestr('project2.json','{}')
            docs=[('SCH_PAGE',self.receipt['schematic_document']),('PCB','wrong' if wrong else self.receipt['pcb_document'])]
            z.writestr('node.epru','\n'.join('{"type":"DOCHEAD"}||'+json.dumps({'docType':kind,'uuid':doc})+'|' for kind,doc in docs))

    def pin(self):
        self.receipt['files']={p.name:{'sha256':file_hash(p)} for p in self.source.iterdir() if p.name!='receipt.json'}
        self.write('receipt.json',self.receipt)

    def imported(self):
        return import_native(self.repo,OWNER,self.body,self.source)

    def test_actual_pin_map_and_both_native_documents_import(self):
        result=self.imported()
        self.assertTrue(result['pin_net_match']);self.assertTrue(result['native_drc_passed'])
        self.assertEqual(10,result['part_count'])

    def test_foreign_candidate_is_refused(self):
        self.receipt['system_id']='SC-old';self.pin()
        with self.assertRaisesRegex(ValueError,'INPUT_MISMATCH'):self.imported()

    def test_export_must_contain_the_read_back_documents(self):
        self.archive(wrong=True);self.pin()
        with self.assertRaisesRegex(ValueError,'ARCHIVE_DOCUMENT_MISMATCH'):self.imported()

    def test_network_change_survives_hash_checks_but_is_rejected(self):
        file='pcb-readback.json';data=json.loads((self.source/file).read_text())
        module=next(c for c in data['result']['components'] if c['designator']=='U2')
        next(p for p in module['pads'] if str(p['padNumber'])=='27')['net']='WRONG_PGOOD'
        self.write(file,data);self.pin()
        with self.assertRaisesRegex(ValueError,'PIN_NET_MISMATCH:U2'):self.imported()

    def test_missing_persistent_identity_is_rejected(self):
        file='schematic-readback.json';data=json.loads((self.source/file).read_text())
        data['result']['components'][0]['uniqueId']='';self.write(file,data);self.pin()
        with self.assertRaisesRegex(ValueError,'PART_IDENTITY'):self.imported()

    def test_tampered_drawing_is_rejected(self):
        (self.source/'schematic.svg').write_text('changed after receipt')
        with self.assertRaisesRegex(ValueError,'NATIVE_TAMPER'):self.imported()


if __name__=='__main__':unittest.main()
