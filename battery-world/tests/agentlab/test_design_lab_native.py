import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from bfworld.agentlab.store import Store
from bfworld.agentlab.design_lab import builder, contracts, coupled_c, case_c
from bfworld.agentlab.design_lab.service import DesignLab
from bfworld.agentlab.door_selfpower.contracts import normalize


class DependencyBinding(unittest.TestCase):
    def setUp(self):
        self.components = {n: {'source': n} for n in builder.COMPONENTS}
        self.candidate = builder.candidate(self.components, 'E-model')
        self.plan = builder.plan(self.candidate, {})

    def test_unchanged_all_stages_reuse(self):
        new = builder.plan(self.candidate, {}, self.plan)
        self.assertEqual({'REUSE_EXACT'}, {v['action'] for v in new['stages'].values()})

    def test_program_change_keeps_mechanics_but_invalidates_joint_and_delivery(self):
        changed = copy.deepcopy(self.components)
        changed['firmware'] = {'source': 'new binary'}
        plan = builder.plan(builder.candidate(changed, 'E-model'), {}, self.plan)
        self.assertEqual('REUSE_EXACT', plan['stages']['mechanical_model']['action'])
        self.assertEqual('REBUILD_REQUIRED', plan['stages']['target_build']['action'])
        self.assertEqual('REBUILD_REQUIRED', plan['stages']['joint_execution']['action'])
        self.assertEqual('REBUILD_REQUIRED', plan['stages']['delivery']['action'])

    def test_backend_change_invalidates_transitive_dependents(self):
        plan = builder.plan(self.candidate, {'circuit_model': 'new solver'}, self.plan)
        self.assertEqual('REUSE_EXACT', plan['stages']['target_build']['action'])
        self.assertEqual('REBUILD_REQUIRED', plan['stages']['receiver']['action'])

    def test_geometry_or_rom_changes_invalidate_source_netlist_and_sensor_inputs(self):
        for component in ('geometry','physical_bindings'):
            changed=copy.deepcopy(self.components);changed[component]={'source':'new physical model'}
            plan=builder.plan(builder.candidate(changed,'E-model'),{},self.plan)
            for stage in ('mechanical_model','circuit_model','sensor_model','joint_execution','delivery'):
                self.assertEqual('REBUILD_REQUIRED',plan['stages'][stage]['action'])
            self.assertEqual('REUSE_EXACT',plan['stages']['target_build']['action'])

    def test_altered_identity_rejected(self):
        value = copy.deepcopy(self.candidate)
        value['components']['circuit']['source'] = 'fake'
        with self.assertRaisesRegex(ValueError, 'IDENTITY'):
            builder.plan(value, {})

    def test_cache_checks_real_files_and_exact_inputs(self):
        with tempfile.TemporaryDirectory() as path:
            path = Path(path)
            (path / 'artifact.txt').write_text('built')
            builder.publish_cache(path, 'input-1', ['artifact.txt'])
            with self.assertRaisesRegex(ValueError, 'INPUT'):
                builder.verified_cache(path, 'input-2')
            (path / 'artifact.txt').write_text('stale')
            with self.assertRaisesRegex(ValueError, 'DRIFT'):
                builder.verified_cache(path, 'input-1')

    def test_model_domain_and_installation_cannot_replace_qualification(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path);(root/'model').write_text('source')
            descriptor={'id':'ROM','version':'v1','files':{'model':contracts.sha(root/'model')},
                'interface':{'ports':['force','velocity']},'units':{'force':'N'},'initial_state':{'electric_J':0},
                'domain':{'tip_mm':[-8,8]},'calibration':{'physical':'NOT_TESTED'},
                'qualification':{'status':'INSTALLED'},'supported_actions':['circuit']}
            with self.assertRaisesRegex(ValueError,'NOT_QUALIFIED'):
                builder.verify_asset(root,descriptor,require_qualified=True)
            descriptor['qualification']['status']='PASS'
            for point in ({'tip_mm':9},{'tip_mm':float('nan')},{'unmodeled_gap_mm':1}):
                with self.assertRaises(ValueError):builder.verify_asset(root,descriptor,operating_point=point)
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED'):
                builder.verify_asset(root,descriptor,action='new-beam')
            self.assertEqual('ROM',builder.verify_asset(root,descriptor,operating_point={'tip_mm':4},action='circuit')['asset_id'])


class PhaseRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'state')
        self.owner = 'pi-chat-1234567890abcdef'
        with self.store.connect() as db:
            db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY)')
            db.execute('INSERT INTO conversations VALUES(?)', (self.owner,))
        app = SimpleNamespace(store=self.store, engineering=SimpleNamespace(lock=threading.Lock()))
        self.lab = DesignLab(app, start_worker=False)
        self.old_env = {'root': self.tmp.name, 'environment_id': 'E-old'}
        with patch('bfworld.agentlab.design_lab.baseline.environment', return_value=self.old_env):
            self.lab.configure(self.owner, self.old_env, {'program.c': 'old'})
        self.old = self.lab.task(self.owner)
        self.env = {'root': self.tmp.name, 'environment_id': 'E-new', 'mode': 'native-coupled-C',
                    'native_model': {'physical_design': normalize()}}

    def phase(self):
        with patch.object(coupled_c, 'verify_environment'):
            return self.lab.configure(self.owner, self.env, {'program.c': 'new', 'device.json': '{}'}, new_phase=True)

    def test_new_phase_preserves_old_exact_task_and_source(self):
        self.phase()
        self.assertEqual(self.old, self.lab.task_version(self.owner, self.old['task_id']))
        self.assertEqual('old', self.lab.design(self.owner, self.old['current_design'])['sources']['program.c'])
        self.assertNotEqual(self.old['task_id'], self.lab.task(self.owner)['task_id'])
        self.assertEqual(self.owner, self.lab.view(self.owner)['owner'])

    def test_exact_pi_source_retains_authorship_across_operator_phase_binding(self):
        self.lab.event(self.owner,'design_frozen',{'design_id':self.old['current_design'],'source_author':'Pi'})
        with patch.object(coupled_c,'verify_environment'):
            self.lab.configure(self.owner,self.env,{'program.c':'old'},new_phase=True)
        frozen=[v['data'] for v in self.lab.events(self.owner)['events'] if v['kind']=='design_frozen'][-1]
        self.assertEqual('Pi',frozen['source_author'])
        self.assertTrue(frozen['source_provenance']['byte_exact_sources_retained'])
        self.assertFalse(any(v['kind']=='external_intervention' for v in self.lab.events(self.owner)['events']))

    def test_changed_operator_phase_source_cannot_inherit_pi_authorship(self):
        self.lab.event(self.owner,'design_frozen',{'design_id':self.old['current_design'],'source_author':'Pi'})
        self.phase()
        events=self.lab.events(self.owner)['events']
        frozen=[v['data'] for v in events if v['kind']=='design_frozen'][-1]
        self.assertEqual('Codex operator phase source',frozen['source_author'])
        self.assertFalse(frozen['source_provenance']['byte_exact_sources_retained'])
        self.assertTrue(any(v['kind']=='external_intervention' for v in events))

    def test_old_phase_cannot_supply_new_phase_run_adoption_or_parent(self):
        self.phase()
        for call in [lambda: self.lab.run(self.owner, 'new-run', self.old['current_design']),
                     lambda: self.lab.adopt(self.owner, self.old['current_design'], 1, 'wrong'),
                     lambda: self.lab.freeze(self.owner, {'program.c': 'bad'}, self.old['current_design'])]:
            with self.assertRaisesRegex(ValueError, 'ANOTHER_PHASE'):
                call()

    def test_unknown_operation_prevents_phase_rebinding(self):
        job = self.lab.run(self.owner, 'run', self.old['current_design'])
        with self.store.connect() as db:
            db.execute("UPDATE design_operations SET status='UNKNOWN' WHERE id=?", (job['id'],))
        with self.assertRaisesRegex(ValueError, 'DRAINED'):
            self.phase()

    def test_unsupported_device_geometry_or_self_verdict_rejected(self):
        task = coupled_c.contract(self.env)
        for device in [{'mechanical': {'beam_length': 99}}, {'passed': True}, {'circuit': {'secret': 5}}]:
            with self.assertRaises(ValueError):
                coupled_c.snapshot(task, {'program.c': 'x', 'device.json': json.dumps(device)}, self.env)

    def test_changed_supported_circuit_has_new_physical_identity(self):
        task = coupled_c.contract(self.env)
        a = coupled_c.snapshot(task, {'program.c': 'x'}, self.env)
        b = coupled_c.snapshot(task, {'program.c': 'x', 'device.json': '{"circuit":{"cin_uF":10,"cout_uF":15}}'}, self.env)
        self.assertEqual(a['dimensions']['application'], b['dimensions']['application'])
        self.assertNotEqual(a['dimensions']['physical'], b['dimensions']['physical'])


class HostConditionalABI(unittest.TestCase):
    def test_host_only_file_access_is_rejected_even_when_arm_object_is_pure(self):
        source='''#include <stdint.h>
void bf_reset(void){} int bf_state(void){return 0;}
int bf_step(double a,double b,double c){return 0;}
double bf_current_mA(void){return 0.0003;}
void bf_event(uint32_t id,uint8_t kind){}
void bf_payload(uint8_t*p){for(int i=0;i<12;i++)p[i]=0;}
#if !defined(__arm__)
#include <stdio.h>
int bf_host_only(void){return fopen("forbidden.txt","w")?1:0;}
#endif
'''
        with tempfile.TemporaryDirectory() as directory:
            design={'design_id':'negative-host-conditional','environment_id':'fixture-ABI',
                    'sources':{'program.c':source}}
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED_HOST_EXTERNAL:fopen'):
                case_c.build(design,Path(directory)/'build')
            self.assertFalse((Path(directory)/'build/forbidden.txt').exists())


if __name__ == '__main__':
    unittest.main()
