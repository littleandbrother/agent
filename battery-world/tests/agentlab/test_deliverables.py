import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from bfworld.agentlab.server import Workbench
from bfworld.agentlab.solar_companion import definition, changed
from bfworld.agentlab.deliverables import contract, dependent_ids, missing_roles


class DeliverablesTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'paid-window-closed.json').write_text('{}')
        self.app=Workbench(self.root/'state')
        self.owner=self.app.conversations.create('数字交付检查',None,'delivery')['id']
        self.source=self.app.conversations.detail(self.owner)['messages'][0]['id']
        self.write(definition(),0,'initial')

    def tearDown(self):
        self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.temp.cleanup()

    def write(self,p,rev,op):
        return self.app.assemblies.write(self.owner,dict(source_message_id=self.source,operation_id=op,expected_revision=rev,payload=p))

    def publish(self,name='requirements.json'):
        base=self.root/'participants'/self.owner;base.mkdir(parents=True,exist_ok=True)
        (base/name).write_text('{"passed":true,"invented":"not evidence"}')
        return self.app.assemblies.register(self.owner,dict(revision=1,path=name,kind='document'))['id']

    def bind(self,task='requirements',files=None,op='bind'):
        return self.app.deliverables.bind(self.owner,dict(action='bind',operation_id=op,task_id=task,revision=1,files=files or [],jobs=[]))

    def test_no_self_certification_and_owner_isolation(self):
        key=self.publish();result=self.bind(files=[key]);r=result['tasks'][0]
        self.assertEqual('partial',r['delivery_status']);self.assertEqual('not_run',r['validation_status'])
        self.assertFalse(result['complete'])
        bad=dict(action='bind',operation_id='forged',task_id='requirements',revision=1,files=[key],jobs=[],passed=True)
        with self.assertRaisesRegex(ValueError,'SCHEMA'):self.app.deliverables.bind(self.owner,bad)
        other=self.app.conversations.create('其他',None,'other')['id']
        self.app.assemblies.write(other,dict(source_message_id=self.app.conversations.detail(other)['messages'][0]['id'],operation_id='init',expected_revision=0,payload=definition()))
        with self.assertRaises(PermissionError):self.app.deliverables.bind(other,{k:v for k,v in bad.items() if k!='passed'})

    def test_dependency_edit_and_tamper_invalidate_descendants(self):
        key=self.publish();self.bind(files=[key]);self.bind('interfaces',op='interface')
        key2=self.publish('changed.json');self.bind(files=[key2],op='new')
        status={t['id']:t for t in self.app.deliverables.inspect(self.owner)['tasks']}
        self.assertEqual('stale',status['interfaces']['delivery_status'])
        saved,_=self.app.assemblies.file(self.owner,key2);saved.write_text('tampered')
        d=self.app.deliverables.inspect(self.owner)
        self.assertIn('joint',d['stale_tasks']);self.assertEqual('invalid',d['tasks'][0]['delivery_status'])

    def test_geometry_edit_stales_camera_does_not(self):
        self.bind('cad',files=[self.publish()]);self.write(changed(definition(),camera=-35),1,'camera')
        self.assertEqual([],self.app.deliverables.inspect(self.owner)['stale_tasks'])
        self.write(changed(definition(),width=100),2,'geometry')
        self.assertIn('release',self.app.deliverables.inspect(self.owner)['stale_tasks'])

    def test_partial_package_is_honest_and_exact(self):
        key=self.publish();self.bind(files=[key]);r=self.app.deliverables.package(self.owner)
        path,_=self.app.assemblies.file(self.owner,r['id'])
        with zipfile.ZipFile(path) as z:
            self.assertIsNone(z.testzip());snap=json.loads(z.read('版本清单与验收报告/验收.json'))
            self.assertFalse(snap['complete']);self.assertEqual(30,len(snap['tasks']))
            self.assertEqual(12,len([n for n in z.namelist() if n.endswith('/')]))

    def test_contract_dependency_graph_is_closed_and_acyclic(self):
        tasks=contract()['tasks'];ids={t['id'] for t in tasks};done=set()
        for _ in tasks:
            done|={t['id'] for t in tasks if set(t['depends_on'])<=done}
        self.assertEqual(ids,done)
        self.assertTrue({'joint','matrix','system-acceptance','release'}<=set(dependent_ids(['firmware'])))

    def test_duplicate_file_cannot_fill_multiple_required_roles(self):
        roles=[{'role':'bom','extensions':['.csv']},{'role':'placement','extensions':['.csv']}]
        self.assertEqual(1,len(missing_roles(roles,[{'name':'one.csv'}])))
        key=self.publish()
        with self.assertRaisesRegex(ValueError,'REFERENCE_SCHEMA'):self.bind(files=[key,key])

    def test_package_rejects_workspace_escape(self):
        key=self.publish();self.bind(files=[key])
        outside=self.root/'outside';outside.mkdir()
        (self.root/'participants'/self.owner/'delivery-packages').symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(PermissionError,'PATH_DENIED'):self.app.deliverables.package(self.owner)
        self.assertEqual([],list(outside.iterdir()))
