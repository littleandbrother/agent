import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from bfworld.agentlab.server import Workbench
from bfworld.agentlab.solar_companion import definition, changed
from bfworld.agentlab import engineering_projects as projects
from bfworld.agentlab.product_authority import context_packet


class ProductAuthority(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'paid-window-closed.json').write_text('{}')
        self.app=Workbench(self.root/'state')
        self.owner=self.app.conversations.create('项目验收',None,'authority')['id']
        self.source=self.app.conversations.detail(self.owner)['messages'][0]['id']
        self.write(definition(),0,'initial')
        self.workspace=self.root/'participants'/self.owner;self.workspace.mkdir(parents=True,exist_ok=True)

    def tearDown(self):
        self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()

    def write(self,p,rev,op):
        return self.app.assemblies.write(self.owner,dict(source_message_id=self.source,operation_id=op,expected_revision=rev,payload=p))

    def project(self,kind,filename,source):
        (self.workspace/filename).write_text(source)
        spec=dict(schema_version='bf-engineering-project-v1',kind=kind,entrypoint=filename,files=[filename],interfaces={'units':'mm' if kind=='cadquery' else 'SI'})
        (self.workspace/'project.json').write_text(json.dumps(spec))
        return {'assembly_revision':1,'project_path':'project.json'}

    def run_project(self,params,op):
        j=self.app.engineering.submit(self.owner,dict(engine='engineering-project',parameters=params,operation_id=op),initiator='operator')
        until=time.monotonic()+90
        while j['status'] in ('QUEUED','RUNNING') and time.monotonic()<until:
            time.sleep(.1);j=self.app.engineering.get(self.owner,j['id'])
        self.assertEqual('SUCCEEDED',j['status'],str(j.get('error'))+' '+(self.app.engineering.root/j['id']/'process.log').read_text()[-5000:])
        return j

    def test_same_verdict_everywhere_no_synthetic_hardware(self):
        d=self.app.deliverables.inspect(self.owner)
        a=self.app.assemblies.projection(self.owner)
        self.assertEqual(d['verdict'],a['delivery'])
        self.assertEqual(d['verdict'],context_packet(self.app,self.owner)['delivery'])
        self.assertFalse(d['complete']);self.assertFalse(d['verdict']['auto_continue'])
        self.assertEqual('solar',d['profile'])
        self.assertEqual('not_applicable',next(t for t in d['tasks'] if t['id']=='magnetics')['applicability'])
        self.assertFalse(d['hardware_verified'])

    def test_scoped_invalidation(self):
        for t in ('requirements','cad','presentation','firmware'):
            self.app.deliverables.bind(self.owner,dict(action='bind',operation_id=t,task_id=t,revision=1,files=[],jobs=[]))
        self.write(changed(definition(),camera=-35),1,'camera')
        d=self.app.deliverables.inspect(self.owner)
        self.assertIn('presentation',d['stale_tasks']);self.assertNotIn('cad',d['stale_tasks']);self.assertNotIn('firmware',d['stale_tasks'])
        self.write(changed(definition(),width=100),2,'geometry')
        d=self.app.deliverables.inspect(self.owner)
        self.assertIn('cad',d['stale_tasks']);self.assertNotIn('requirements',d['stale_tasks'])

    def test_stage_contract_is_versioned_and_does_not_certify_product(self):
        body=dict(action='configure_stage',expected_revision=0,target_stage='concept',max_continuations=2,reason='Only scope this turn to a digital concept')
        d=self.app.deliverables.configure_stage(self.owner,body)
        self.assertTrue(d['verdict']['passed']);self.assertFalse(d['complete'])
        self.assertEqual(1,d['verdict']['stage_contract']['revision'])
        with self.assertRaisesRegex(ValueError,'CONFLICT'):self.app.deliverables.configure_stage(self.owner,body)
        d=self.app.deliverables.configure_stage(self.owner,{**body,'expected_revision':1,'target_stage':'hardware'})
        self.assertFalse(d['verdict']['passed']);self.assertFalse(d['hardware_verified'])

    def test_native_outline_changes_stale_mechanical_delivery_without_rerunning_power(self):
        for task in ('requirements','cad','spice','firmware','pcb-checks'):
            self.app.deliverables.bind(self.owner,dict(action='bind',operation_id=task,task_id=task,revision=1,files=[],jobs=[]))
        with self.app.store.connect() as db:
            db.execute('INSERT INTO eda_cli_jobs VALUES(?,?,?,?,?,?,?,?)',('native-outline',self.owner,'outline',
                json.dumps({'argv':['pcb','outline-set','--points','0,0;80,0;80,30;0,30'],'project':'bound-project'}),'SUCCEEDED',None,time.time(),time.time()))
        view=self.app.deliverables.inspect(self.owner)
        self.assertIn('cad',view['stale_tasks']);self.assertIn('pcb-checks',view['stale_tasks'])
        self.assertNotIn('spice',view['stale_tasks']);self.assertNotIn('firmware',view['stale_tasks'])
        self.assertEqual([],self.app.engineering.jobs(self.owner))

    def test_geometry_rom_changes_with_physics_not_camera(self):
        from bfworld.agentlab.beam_event import derive
        from bfworld.agentlab.assembly import identities
        a=self.app.assemblies.get(self.owner);a=copy.deepcopy(a)
        g=a['payload']['parts'][0]['geometry'];g.update(kind='box',size_mm=[50,10,1],fillet_mm=0,cutouts=[])
        a['hashes']=identities(a['payload'])
        mapping=dict(beam_part=a['payload']['parts'][0]['id'],axes=[0,1,2],young_pa=200e9,density_kg_m3=7800,tip_mass_kg=.001,damping_ratio=.02,material_source='declared numerical fixture, not measured')
        m,r=derive(a,mapping,{'coupling_n_v':.0001,'piezo_capacitance_f':1e-7})
        a2=copy.deepcopy(a);a2['payload']['parts'][0]['geometry']['size_mm'][0]=100;a2['hashes']=identities(a2['payload'])
        m2,r2=derive(a2,mapping,m)
        self.assertAlmostEqual(m['stiffness_n_m']/8,m2['stiffness_n_m'])
        self.assertNotEqual(r['geometry_hash'],r2['geometry_hash'])
        a3=copy.deepcopy(a);a3['payload']['presentation']['camera_deg']=-35;a3['hashes']=identities(a3['payload'])
        self.assertEqual((m,r),derive(a3,mapping,m))
        a2['payload']['parts'][0]['geometry']['cutouts']=[{}]
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_GEOMETRY'):derive(a2,mapping,m)

    @unittest.skipUnless(projects.SPICE.is_file(),'local ngspice unavailable')
    def test_geometry_drives_actual_coupled_solver(self):
        try:
            from .test_reference_event import fixture
        except ImportError:
            from test_reference_event import fixture
        p=definition();p['parts'][0]['geometry'].update(kind='box',size_mm=[50,10,1],fillet_mm=0,cutouts=[])
        self.write(p,1,'beam-definition')
        mapping=dict(beam_part=p['parts'][0]['id'],axes=[0,1,2],young_pa=200e9,density_kg_m3=7800,tip_mass_kg=.001,damping_ratio=.02,material_source='explicit numerical fixture; not calibrated')
        (self.workspace/'mapping.json').write_text(json.dumps(mapping))
        (self.workspace/'event.json').write_text(json.dumps(fixture()))
        j=self.app.engineering.submit(self.owner,dict(engine='beam-event',parameters=dict(assembly_revision=2,mapping_path='mapping.json',spec_path='event.json'),operation_id='beam-event'),initiator='operator')
        until=time.monotonic()+90
        while j['status'] in ('QUEUED','RUNNING') and time.monotonic()<until:
            time.sleep(.1);j=self.app.engineering.get(self.owner,j['id'])
        self.assertEqual('SUCCEEDED',j['status'],j.get('error'))
        result=j['result'];rom=result['geometry_rom']
        self.assertAlmostEqual(4000,rom['mechanics']['stiffness_n_m'])
        self.assertEqual(rom['mechanics'],j['event_spec']['mechanics'])
        self.assertTrue(result['checks']['transient_complete'])
        self.assertFalse(result['hardware_verified']);self.assertFalse(rom['calibrated'])
        report=json.loads(self.app.engineering.artifact(self.owner,j['id'],'geometry-rom.json').read_text())
        self.assertEqual(rom,report)

    def test_source_snapshot_changes_identity_and_forbids_escape(self):
        p=self.project('spice','main.cir','RC\nV1 a 0 1\nR1 a b 1k\nC1 b 0 1u\n.tran 10u 1m\n.end\n')
        a=projects.request(self.app,self.owner,p)
        (self.workspace/'main.cir').write_text('changed')
        b=projects.request(self.app,self.owner,p)
        self.assertNotEqual(a['project_sha256'],b['project_sha256'])
        self.assertIn('R1 a b',a['project']['sources']['main.cir'])
        (self.workspace/'main.cir').write_text('unsafe\n.control\nshell touch outside\n.endc\n.end')
        with self.assertRaisesRegex(ValueError,'DIRECTIVE_DENIED'):projects.request(self.app,self.owner,p)
        (self.workspace/'main.cir').unlink();(self.workspace/'main.cir').symlink_to(self.root/'paid-window-closed.json')
        with self.assertRaisesRegex(ValueError,'PATH_DENIED'):projects.request(self.app,self.owner,p)

    @unittest.skipUnless(projects.SPICE.is_file(),'local ngspice unavailable')
    def test_real_spice_and_tamper(self):
        p=self.project('spice','main.cir','RC transient\nV1 a 0 PULSE(0 1 0 1u 1u 1m 2m)\nR1 a b 1k\nC1 b 0 1u\n.tran 10u 1m\n.end\n')
        j=self.run_project(p,'spice')
        self.assertGreater(j['result']['independent_readback']['points'],10)
        self.assertFalse(j['result']['product_verified'])
        f=self.app.engineering.artifact(self.owner,j['id'],'project-trace.raw');f.write_text('tampered')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):self.app.engineering.artifact(self.owner,j['id'],f.name)

    @unittest.skipUnless(projects.CAD.is_file(),'local CadQuery unavailable')
    def test_real_authored_cad_and_sandbox(self):
        source='''import cadquery as cq
from pathlib import Path
try:
 Path("../forbidden").write_text("escape")
 raise RuntimeError("SANDBOX_FAILED")
except PermissionError: pass
cq.exporters.export(cq.Workplane("XY").box(23,11,7), "assembly.step")
'''
        j=self.run_project(self.project('cadquery','main.py',source),'cad')
        dims=j['result']['independent_readback']['bounds_mm']
        for a,b in zip(dims,[23,11,7]):self.assertAlmostEqual(a,b,4)
        self.assertFalse((self.app.engineering.root/j['id']/'forbidden').exists())

    @unittest.skipUnless(projects.GCC.is_file() and projects.CMSIS.is_dir(),'local MCU toolchain unavailable')
    def test_real_participant_firmware(self):
        parameters=self.project('firmware-stm32l031','main.c','extern unsigned value(void);int main(void){volatile unsigned x=value();for(;;){x++;}}\n')
        (self.workspace/'value.c').write_text('unsigned value(void){return 17;}\n')
        path=self.workspace/'project.json';spec=json.loads(path.read_text());spec['files'].append('value.c');path.write_text(json.dumps(spec))
        j=self.run_project(parameters,'firmware')
        r=j['result']['independent_readback'];self.assertTrue(r['memory_fit']);self.assertGreater(r['flash_bytes'],0)
        self.assertFalse(r['flashed']);self.assertFalse(r['pin_binding_verified'])

    @unittest.skipUnless(projects.GCC.is_file(),'local ARM compiler unavailable')
    def test_real_nrf_project_snapshot_build_and_export(self):
        parameters=self.project('firmware-nrf52832','main.c',
            'volatile unsigned counter=9; int main(void){for(;;){counter++;}}\n')
        with self.assertRaisesRegex(ValueError,'NRF_TARGET_REQUIRED'):
            projects.request(self.app,self.owner,parameters)
        path=self.workspace/'project.json';spec=json.loads(path.read_text())
        spec['interfaces'].update(target='nRF52832-QFAA',softdevice=False)
        path.write_text(json.dumps(spec))
        j=self.run_project(parameters,'nrf')
        report=j['result']['independent_readback']
        self.assertEqual('nRF52832-QFAA',report['target'])
        self.assertTrue(report['memory_fit']);self.assertFalse(report['radio_verified'])
        self.assertFalse(report['flashed']);self.assertGreater(report['flash_bytes'],0)
        for name in ('project-firmware.elf','project-firmware.hex','project-firmware.bin','project-firmware.map'):
            self.assertGreater(self.app.engineering.artifact(self.owner,j['id'],name).stat().st_size,0)
        import zipfile
        with zipfile.ZipFile(self.app.engineering.root/j['id']/'project-source.zip') as archive:
            self.assertIn('nrf52832.ld',archive.namelist())
            self.assertIn('startup_nrf52832.c',archive.namelist())
            self.assertIn('main.c',archive.namelist())


class CompilerReadScope(unittest.TestCase):
    @unittest.skipUnless(projects.GCC.is_file(),'local ARM compiler unavailable')
    def test_actual_standard_header_build_keeps_sibling_private_header_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'output';output.mkdir()
            secret=root/'private.h';secret.write_text('#define PRIVATE_VALUE 196608\n')
            source=output/'main.c'
            reads=[output,projects.GCC.parent,*projects.compiler_read_paths(projects.GCC)]
            command=['/usr/bin/sandbox-exec','-p',projects.sandbox(reads,output),str(projects.GCC),
                     '-mcpu=cortex-m4','-mthumb','-ffreestanding','-c',str(source),'-o',str(output/'main.o')]
            env={'PATH':str(projects.GCC.parent)+':/usr/bin:/bin','LANG':'C'}
            source.write_text('#include <stdint.h>\nuint32_t value(void){return 1;}\n')
            allowed=subprocess.run(command,cwd=output,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(0,allowed.returncode,allowed.stderr)
            source.write_text('#include <stdint.h>\n#include "'+str(secret)+'"\nuint32_t value(void){return PRIVATE_VALUE;}\n')
            denied=subprocess.run(command,cwd=output,env=env,capture_output=True,text=True,timeout=20)
            self.assertNotEqual(0,denied.returncode)
            self.assertIn('Operation not permitted',denied.stderr)


if __name__=='__main__':unittest.main()
