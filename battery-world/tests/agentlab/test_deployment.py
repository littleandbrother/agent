import json,subprocess,tempfile,time,unittest,zipfile
from pathlib import Path
from bfworld.agentlab.server import Workbench
from bfworld.agentlab.solar_companion import definition,changed
from bfworld.agentlab import deployment,tinyml,product_build
from bfworld.agentlab.progress import project


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'paid-window-closed.json').write_text('{}');self.app=Workbench(self.root/'state')
        self.owner=self.app.conversations.create('产品部署测试',None,'deploy-test')['id']
        self.source=self.app.conversations.detail(self.owner)['messages'][0]['id']
        self.app.assemblies.write(self.owner,dict(source_message_id=self.source,operation_id='first',expected_revision=0,payload=definition()))
    def tearDown(self):
        self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()
    def submit(self,engine,params,op):
        j=self.app.engineering.submit(self.owner,dict(engine=engine,parameters={'assembly_revision':1,**params},operation_id=op),'operator')
        until=time.monotonic()+45
        while j['status'] in ('RUNNING','QUEUED') and time.monotonic()<until:
            time.sleep(.1);j=self.app.engineering.get(self.owner,j['id'])
        self.assertEqual('SUCCEEDED',j['status'],j.get('error'));return j
    def test_missing_progress_and_structured_failure_have_source(self):
        self.app.conversations.event(self.owner,'fixture-error',dict(type='tool_execution_end',toolName='bf_product',toolCallId='call-1',isError=True,result={'content':[{'type':'text','text':'PRODUCT_FILE_REVISION_REQUIRED'}]}))
        p=project(self.app,self.owner);self.assertEqual(1,p['revision']);self.assertEqual('sessions',p['failures'][0]['module'])
        self.assertTrue(p['failures'][0]['seq']);self.assertEqual('unmeasured',p['stages'][-1]['state'])
    def test_dataset_path_and_budget_boundaries(self):
        for p in [dict(assembly_revision=1),dict(assembly_revision=True,demo=True),dict(assembly_revision=1,demo=True,epochs=9999),dict(assembly_revision=1,demo=True,architectures=[[1024]])]:
            with self.assertRaises(ValueError):tinyml.validate(p)
        for path in ['/etc/passwd','../other/data.json','.pi/session.json']:
            with self.assertRaises(ValueError):tinyml.request(self.app,self.owner,{'assembly_revision':1,'dataset_path':path})
    @unittest.skipUnless(deployment.GCC.is_file() and product_build.CAD.is_file(),'local ARM and numpy toolchain required')
    def test_real_nas_integer_export_target_build_stale_and_corrupt(self):
        j=self.submit('tinyml-nas',dict(demo=True,epochs=40,architectures=[[4],[8,4]]),'nas')
        r=j['result'];m=r['metrics'];root=self.app.engineering.root/j['id']
        self.assertEqual(2,len(r['nas']['candidates']));self.assertTrue(m['host_profile']['parity_passed'])
        self.assertGreater(m['winner']['parameters'],0);self.assertTrue(r['build']['memory_fit'])
        self.assertIsNone(m['latency_ms_mcu']);self.assertIsNone(m['power_mw_mcu']);self.assertFalse(m['measured_on_mcu'])
        self.assertEqual('synthetic-fixture',m['source_kind'])
        plan=subprocess.run(['python3',str(root/'flash_mcu.py')],capture_output=True,text=True,timeout=10)
        self.assertEqual(0,plan.returncode,plan.stderr);self.assertFalse(json.loads(plan.stdout)['flashed'])
        with zipfile.ZipFile(root/'deployment.zip') as z:self.assertIsNone(z.testzip());self.assertIn('model.c',z.namelist())
        d=project(self.app,self.owner);self.assertFalse(d['deployments'][0]['stale']);self.assertTrue(d['deployments'][0]['integrity'])
        self.app.assemblies.write(self.owner,dict(source_message_id=self.source,operation_id='change',expected_revision=1,payload=changed(definition(),width=100)))
        self.assertTrue(project(self.app,self.owner)['deployments'][0]['stale'])
        (root/'model.c').write_text('corrupt')
        self.assertFalse(project(self.app,self.owner)['deployments'][0]['integrity'])
        bad=subprocess.run(['python3',str(root/'flash_mcu.py')],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(0,bad.returncode);self.assertIn('DEPLOYMENT_FILE_CHANGED',bad.stderr)
    @unittest.skipUnless(deployment.GCC.is_file(),'local ARM toolchain required')
    def test_actual_firmware_build_uses_product_pulse_and_preserves_no_flash(self):
        j=self.submit('mcu-firmware',{},'firmware');r=j['result']
        self.assertEqual(definition()['energy']['pulse_ms'],r['build']['pulse_ms']);self.assertTrue(r['build']['target_compiled']);self.assertFalse(r['flashed'])
        same=self.app.engineering.submit(self.owner,dict(engine='mcu-firmware',parameters={'assembly_revision':1},operation_id='firmware'),'operator')
        self.assertEqual(j['id'],same['id'])
