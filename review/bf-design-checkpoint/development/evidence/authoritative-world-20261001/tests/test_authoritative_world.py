import copy
import ctypes
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import authoritative_world as aw


class WorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = aw.load_world()
        cls.legacy = aw.load_world(ROOT / 'contracts/legacy-world-v1.json')
        cls.registry = aw.read_json(ROOT / 'contracts/source-registry.json')
        cls.sources = aw.source_identity(cls.registry)
        cls.tasks = aw.read_json(ROOT / 'contracts/tasks-v2.json')['tasks']
        cls.design = aw.migrate_upstream_spec({}, 'upstream-338d603')
        cls.model = {'model_version': 'TEST-ONLY-unqualified', 'applicability': 'synthetic_fixture_only',
                     'physical_qualified': False, 'source_hashes': {'fixture': 'a' * 64}}
        cls.solver = {'solver_version': 'TEST-ONLY', 'settings': {'step_s': 1e-5}, 'tool_hashes': {'fixture': 'b' * 64}}

    def keys(self, design=None, world=None, task=None, model=None, solver=None, sources=None):
        return aw.stage_keys(world or self.world, design or self.design, task or self.tasks[0],
                             model or self.model, solver or self.solver, sources or self.sources)

    def identity(self, **kwargs):
        return aw.make_run_identity(kwargs.get('world', self.world), kwargs.get('design', self.design),
            kwargs.get('task', self.tasks[0]), kwargs.get('model', self.model),
            kwargs.get('solver', self.solver), kwargs.get('sources', self.sources))

    def test_canonical_hash_order_and_nonfinite(self):
        self.assertEqual(aw.digest({'a': 1, 'b': 2}), aw.digest({'b': 2, 'a': 1}))
        with self.assertRaises(ValueError): aw.digest({'x': float('nan')})

    def test_source_snapshots_and_originals(self):
        self.assertEqual([], aw.verify_sources(check_originals=True))

    def test_registry_relocation_no_identity_change(self):
        r = copy.deepcopy(self.registry)
        for item in r['sources'].values(): item['original_path'] = '/new/place'; item['snapshot_path'] = 'elsewhere'
        self.assertEqual(aw.source_identity(r), self.sources)

    def test_source_tamper_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); shutil.copytree(ROOT / 'sources', root / 'sources')
            (root / 'sources/upstream_program.c').write_text('changed')
            self.assertIn('SOURCE_HASH_MISMATCH:upstream_program', aw.verify_sources(self.registry, root))

    def test_source_path_escape_rejected(self):
        r = copy.deepcopy(self.registry); r['sources']['upstream_program']['snapshot_path'] = '../program.c'
        self.assertIn('SOURCE_PATH_DENIED:upstream_program', aw.verify_sources(r))

    def test_unknowns_remain_null_and_not_qualified(self):
        self.assertGreaterEqual(len(self.world['unresolved_facts']), 12)
        self.assertTrue(all(x['value'] is None and x['status'] == 'unknown' for x in self.world['unresolved_facts']))
        self.assertFalse(self.world['qualification']['physical_qualified'])
        self.assertFalse(self.world['qualification']['requirements_owner_frozen'])

    def test_unknown_cannot_be_filled_without_new_version(self):
        w = copy.deepcopy(self.world); w['unresolved_facts'][0]['value'] = 1
        with self.assertRaises(aw.ContractError): aw.validate_world(w)

    def test_qualification_cannot_be_self_promoted(self):
        w = copy.deepcopy(self.world); w['qualification']['physical_qualified'] = True
        with self.assertRaises(aw.ContractError): aw.validate_world(w)

    def test_semantic_mutation_requires_new_contract(self):
        w = copy.deepcopy(self.world); w['input']['opening_s'] = 1.
        with self.assertRaises(aw.ContractError): aw.world_id(w)

    def test_legacy_and_canonical_distinct_worlds(self):
        self.assertNotEqual(aw.world_id(self.world), aw.world_id(self.legacy))
        self.assertEqual(1.7, self.legacy['program']['brownout_V'])
        self.assertNotIn('source_id', self.legacy['program'])

    def test_nominal_coordinate_agreement_only(self):
        for t in (0., .1, 1., 2., 4.):
            for q in (-.004, 0., .004):
                self.assertEqual(aw.geometry_at(self.world, .048, t, q), aw.geometry_at(self.legacy, .048, t, q))

    def test_nonnominal_geometry_difference_preserved(self):
        a = aw.geometry_at(self.world, .040, 1.); b = aw.geometry_at(self.legacy, .040, 1.)
        self.assertNotEqual(a['driver_world_m'], b['driver_world_m'])
        self.assertNotEqual(a['force_separation_m'], b['force_separation_m'])

    def test_upstream_formula_72_coordinates(self):
        checks = 0
        for gap in (.040, .048, .060):
            for degrees in (0., 5., 30., 65.):
                for q in (-.004, 0., .004):
                    angle = math.radians(degrees); t = degrees / 65 * 2
                    expected = [.904 - ((.904-gap)*math.cos(angle)-.045*math.sin(angle)), 0.,
                                (.904-gap)*math.sin(angle)+.045*math.cos(angle)-.075265-q]
                    result = aw.geometry_at(self.world, gap, t, q)['force_separation_m']
                    self.assertLess(max(abs(a-b) for a,b in zip(result, expected)), 3e-16)
                    # Independent old-family algebra as a migration negative control.
                    old = aw.geometry_at(self.legacy, gap, t, q)['force_separation_m']
                    old_expected = [.856+gap-(.856*math.cos(angle)-.045*math.sin(angle)), 0.,
                                    .856*math.sin(angle)+.045*math.cos(angle)-.075265-q]
                    self.assertLess(max(abs(a-b) for a,b in zip(old, old_expected)), 3e-16); checks += 2
        self.assertEqual(72, checks)

    def test_geometry_nonfinite_bool_and_domain_rejected(self):
        for gap,t,q in [(True,0,0),(.048,float('nan'),0),(.048,5,0),(.048,1,.009),(.01,1,0)]:
            with self.assertRaises(aw.ContractError): aw.geometry_at(self.world,gap,t,q)

    def test_prescribed_input_and_explicit_no_motion(self):
        normal = aw.input_at(self.world, 2.); zero = aw.input_at(self.world, 2., control='no_motion')
        self.assertEqual(math.radians(65), normal['angle_rad']); self.assertEqual(0, zero['angle_rad'])
        self.assertNotEqual(normal['input_id'], zero['input_id'])
        self.assertEqual(0, normal['external_electrical_input_A'])
        with self.assertRaises(aw.ContractError): aw.input_at(self.world,1,control='weak_motion')

    def test_initial_state_energy_counted_not_erased(self):
        state = aw.bind_initial_state(self.world,q0_m=.001,stiffness_N_m=100,force_at_q0_N=.1,force_artifact_sha256='c'*64)
        self.assertAlmostEqual(.00005,state['mechanical_J'])
        self.assertIsNone(state['auxiliary_J']); self.assertIsNone(state['preparation_reset_work_J'])
        self.assertFalse(state['physical_preparation_qualified'])

    def test_initial_state_nonequilibrium_and_unsupported_rejected(self):
        for q,f in [(.001,.2),(.009,.9)]:
            with self.assertRaises(aw.ContractError): aw.bind_initial_state(self.world,q0_m=q,stiffness_N_m=100,force_at_q0_N=f,force_artifact_sha256='c'*64)

    def test_upstream_migration_exact_noop(self):
        self.assertEqual(self.design, aw.migrate_upstream_spec(self.design,'upstream-338d603'))
        self.assertEqual(53.8,self.design['firmware']['boot_ms'])

    def test_migration_forbids_implicit_legacy_relabel(self):
        for family in ('legacy','cloud-moving-product','',None):
            with self.assertRaises(aw.ContractError): aw.migrate_upstream_spec({},family)

    def test_migration_rejects_unknown_field_and_bool(self):
        for spec in ({'silently_changed_world':True},{'mechanical':{'gap_mm':True}}):
            with self.assertRaises(Exception): aw.migrate_upstream_spec(spec,'upstream-338d603')

    def test_tasks_are_distinct_and_unadmitted(self):
        self.assertNotEqual(aw.task_id(self.tasks[0]),aw.task_id(self.tasks[1]))
        self.assertEqual('canonical_failure_snapshot_required',self.tasks[1]['starting_state']['type'])
        self.assertFalse(self.tasks[1]['qualification']['cross_domain_bottleneck_observed'])
        self.assertFalse(any(t['qualification']['evaluator_qualified'] for t in self.tasks))

    def test_task_attestation_noop_but_mission_changes_identity(self):
        t=copy.deepcopy(self.tasks[0]); t['status']='inspection'; t['reference_witness']={'untrusted':'reference'}
        self.assertEqual(aw.task_id(t),aw.task_id(self.tasks[0]))
        t['mission']['receiver_deadline_s']=5
        self.assertNotEqual(aw.task_id(t),aw.task_id(self.tasks[0]))

    def test_identity_schema(self):
        import jsonschema
        identity=self.identity()
        jsonschema.validate(identity,aw.read_json(ROOT/'contracts/identity.schema.json'))
        self.assertEqual(aw.digest({k:v for k,v in identity.items() if k!='run_identity'}),identity['run_identity'])

    def test_camera_noop_and_repeat_byte_identity(self):
        d=copy.deepcopy(self.design); d['presentation']['camera_deg']=99
        self.assertEqual(self.identity(),self.identity(design=d)); self.assertEqual(self.keys(),self.keys(design=d))
        self.assertEqual(aw.canonical(self.identity()),aw.canonical(self.identity()))

    def test_all_scientific_design_changes_invalidate(self):
        for group,key,value in [('mechanical','gap_mm',49),('circuit','cin_uF',48),('firmware','boot_ms',54),('link','seed',18)]:
            d=copy.deepcopy(self.design); d[group][key]=value
            self.assertTrue(all(a!=self.keys(design=d)[s] for s,a in self.keys().items()))
        d=copy.deepcopy(self.design);d['new_semantic_component']={'value':1}
        self.assertTrue(all(a!=self.keys(design=d)[s] for s,a in self.keys().items()))

    def test_source_model_solver_changes_invalidate_every_stage(self):
        sources=copy.deepcopy(self.sources);sources['new_evaluator_component']={'sha256':'d'*64}
        model=copy.deepcopy(self.model);model['model_version']='v2'
        solver=copy.deepcopy(self.solver);solver['tool_hashes']['mesh']='e'*64
        for kwargs in ({'sources':sources},{'model':model},{'solver':solver}):
            self.assertTrue(all(a!=self.keys(**kwargs)[s] for s,a in self.keys().items()))

    def test_task_change_invalidates_acceptance(self):
        t=copy.deepcopy(self.tasks[0]);t['mission']['receiver_deadline_s']=3
        self.assertNotEqual(self.keys()['acceptance'],self.keys(task=t)['acceptance'])

    def test_wrong_world_and_legacy_execution_rejected(self):
        t=copy.deepcopy(self.tasks[0]);t['world_id']='0'*64
        with self.assertRaises(aw.ContractError):self.identity(task=t)
        t['world_id']=aw.world_id(self.legacy)
        with self.assertRaises(aw.ContractError):self.identity(world=self.legacy,task=t)

    def test_missing_identity_and_fake_qualification_rejected(self):
        m=copy.deepcopy(self.model);m['physical_qualified']=True
        with self.assertRaises(aw.ContractError):self.identity(model=m)
        with self.assertRaises(aw.ContractError):self.identity(sources={'irrelevant':'foo'})
        with self.assertRaises(aw.ContractError):self.identity(solver={'solver_version':'v1'})

    def test_pinned_source_change_requires_new_world_version(self):
        sources=copy.deepcopy(self.sources);sources['upstream_program']['sha256']='d'*64
        with self.assertRaises(aw.ContractError):self.identity(sources=sources)

    def test_undeclared_excitation_or_energy_cannot_bind_task(self):
        for group,key,value in [('mechanical','opening_s',1.),('mechanical','angle_deg',70.),
                                ('circuit','initial_vin_V',1.),('circuit','diagnostic_input_A',.001)]:
            d=copy.deepcopy(self.design);d[group][key]=value
            with self.assertRaises(aw.ContractError):self.identity(design=d)

    def test_task_input_pointer_cannot_hide_changed_excitation(self):
        t=copy.deepcopy(self.tasks[0]);t['world']['input_id']='0'*64
        with self.assertRaises(aw.ContractError):self.identity(task=t)

    def test_no_motion_input_invalidates_every_stage_and_run(self):
        args=(self.world,self.design,self.tasks[0],self.model,self.solver,self.sources)
        a=aw.make_run_identity(*args);b=aw.make_run_identity(*args,input_control='no_motion')
        self.assertNotEqual(a['run_identity'],b['run_identity'])
        keys=aw.stage_keys(*args,input_control='no_motion')
        self.assertTrue(all(v!=keys[k] for k,v in self.keys().items()))
        with self.assertRaises(aw.ContractError):aw.validate_comparison([a,b])

    def test_realized_initial_state_binds_and_invalidates_every_stage(self):
        state=aw.bind_initial_state(self.world,q0_m=.001,stiffness_N_m=100,force_at_q0_N=.1,force_artifact_sha256='c'*64)
        args=(self.world,self.design,self.tasks[0],self.model,self.solver,self.sources)
        a=aw.make_run_identity(*args);b=aw.make_run_identity(*args,initial_state=state)
        self.assertEqual('recipe_only_not_run_evidence',a['initial_state_binding'])
        self.assertEqual('realized_computational_state',b['initial_state_binding'])
        self.assertNotEqual(a['run_identity'],b['run_identity'])
        keys=aw.stage_keys(*args,initial_state=state)
        self.assertTrue(all(v!=keys[k] for k,v in self.keys().items()))
        changed=copy.deepcopy(state);changed['auxiliary_J']=0.
        with self.assertRaises(aw.ContractError):aw.make_run_identity(*args,initial_state=changed)
        changed['initial_state_id']=aw.digest({k:v for k,v in changed.items() if k!='initial_state_id'})
        with self.assertRaises(aw.ContractError):aw.make_run_identity(*args,initial_state=changed)

    def test_comparison_no_mixed_world_source_task_model_solver_units(self):
        a=self.identity();b=copy.deepcopy(a)
        self.assertTrue(aw.validate_comparison([a,b])['comparable'])
        for field in ('world_id','source_id','input_id','task_contract_id','model_id','solver_id','experimental_unit'):
            b=copy.deepcopy(a);b[field]='different'
            with self.assertRaises(aw.ContractError):aw.validate_comparison([a,b])
        with self.assertRaises(aw.ContractError):aw.validate_comparison([a,a],formal=True)

    def test_continuation_requires_same_realized_state_and_checkpoint(self):
        args=(self.world,self.design,self.tasks[1],self.model,self.solver,self.sources)
        recipe=aw.make_run_identity(*args)
        with self.assertRaises(aw.ContractError):aw.validate_comparison([recipe,recipe])
        state=aw.bind_initial_state(self.world,q0_m=.001,stiffness_N_m=100,force_at_q0_N=.1,force_artifact_sha256='c'*64)
        realized=aw.make_run_identity(*args,initial_state=state)
        with self.assertRaises(aw.ContractError):aw.validate_comparison([realized,realized])
        bound=aw.make_run_identity(*args,initial_state=state,checkpoint_sha256='f'*64)
        self.assertTrue(aw.validate_comparison([bound,bound])['comparable'])
        for field in ('initial_state_id','continuation_checkpoint_id'):
            other=copy.deepcopy(bound);other[field]='e'*64
            with self.assertRaises(aw.ContractError):aw.validate_comparison([bound,other])

    def record(self,time=1.,**kw):
        return {'time_s':time,'payload_hex':b'BFD2\x01\x02\x03\x04\x05\x06\x07\x08'.hex(),
                'capture_id':'id','tx_completed':True,'origin':'synthetic_fixture',**kw}

    def test_receiver_dedups_capture_only_never_claims_action(self):
        r=self.record();events=aw.receive_completed_records(self.world,[r,r])
        self.assertEqual(1,events[0]['packets']);self.assertEqual('unknown',events[0]['direction'])
        self.assertFalse(events[0]['radio_duplicates_resolved'])
        self.assertFalse(events[0]['reboot_identity_available'])

    def test_receiver_incomplete_late_corrupt_and_capture_conflict(self):
        for r in (self.record(tx_completed=False),self.record(time=4.0001)):
            with self.assertRaises(aw.ContractError):aw.receive_completed_records(self.world,[r])
        self.assertEqual([],aw.receive_completed_records(self.world,[self.record(payload_hex='00')]))
        with self.assertRaises(ValueError):aw.receive_completed_records(self.world,[self.record(),self.record(time=1.1)])


class SharedProgramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.world=aw.load_world(); p=cls.world['program']['parameters']
        mapping={'INTERVAL_MS':'interval_ms','BOOT_MS':'boot_ms','INIT_MS':'init_ms','TX_MS':'tx_ms','BOOT_MA':'boot_mA','INIT_MA':'init_mA','TX_MA':'tx_mA'}
        header='\n'.join('#define '+k+' '+str(p[v]) for k,v in mapping.items())
        header+='\n#define SLEEP_MA '+str(p['sleep_uA']/1000)+'\n#define RESET_MA '+str(p['reset_uA']/1000)+'\n'
        (cls.root/'policy.h').write_text(header);shutil.copyfile(ROOT/'sources/upstream_program.c',cls.root/'program.c')
        subprocess.run(['cc','-O2','-shared','-fPIC','program.c','-o','program.so'],cwd=cls.root,check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(cls.root/'program.so'));cls.lib.bf_step.argtypes=[ctypes.c_double]*3;cls.lib.bf_step.restype=ctypes.c_int
        cls.lib.bf_current_mA.restype=ctypes.c_double

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):self.lib.bf_reset()
    def enter_tx(self):
        self.lib.bf_step(0,3.3,3.3);self.lib.bf_step(53.8,3.3,3.3);self.lib.bf_step(.1,3.3,3.3);self.lib.bf_step(13.,3.3,3.3)
        self.assertEqual(4,self.lib.bf_state())
    def test_no_power_no_packet_and_reset_current(self):
        for _ in range(100):self.assertEqual(0,self.lib.bf_step(10,0,0))
        self.assertEqual(0,self.lib.bf_state());self.assertAlmostEqual(.0003,self.lib.bf_current_mA())
    def test_complete_tx_only_emits_one_event(self):
        self.enter_tx();self.assertEqual(0,self.lib.bf_step(4.9,3.3,3.3));self.assertEqual(1,self.lib.bf_step(.2,3.3,3.3));self.assertEqual(5,self.lib.bf_state())
    def test_pgood_abort_precedes_completion(self):
        self.enter_tx();self.assertEqual(0,self.lib.bf_step(5.,3.3,0));self.assertEqual(2,self.lib.bf_state())
    def test_brownout_precedes_completion_and_clears_progress(self):
        self.enter_tx();self.assertEqual(0,self.lib.bf_step(5.,1.79,3.3));self.assertEqual(0,self.lib.bf_state());self.assertEqual(0,self.lib.bf_step(5.,3.3,3.3));self.assertEqual(1,self.lib.bf_state())
    def test_exact_payload_bytes(self):
        payload=(ctypes.c_uint8*12)();self.lib.bf_payload(payload)
        self.assertEqual(b'BFD2\x01\x02\x03\x04\x05\x06\x07\x08',bytes(payload))


if __name__=='__main__':unittest.main()
