import copy
import json
import tempfile
import unittest
import numpy as np
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from bfworld.agentlab import door_selfpower
from bfworld.agentlab.door_selfpower import contracts, extraction, pipeline
from bfworld.agentlab.door_system import contracts as old


class SelfPowerTests(unittest.TestCase):
    def test_audit_json_keeps_numpy_false_and_rejects_nonfinite_values(self):
        import importlib.util
        script=Path(__file__).resolve().parents[2]/'scripts/door_case/audit_selfpower.py'
        spec=importlib.util.spec_from_file_location('audit_json_boundary',script)
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        value={'checks':{'time_domain':np.bool_(True),'failed':np.bool_(False)},
               'peaks':[np.float64(1.2),np.int64(3)],'passed':np.bool_(False)}
        plain=audit.json_primitives(value)
        encoded=json.dumps(plain,allow_nan=False)
        self.assertEqual(json.loads(encoded),{'checks':{'time_domain':True,'failed':False},'peaks':[1.2,3],'passed':False})
        with self.assertRaises(ValueError):
            json.dumps(audit.json_primitives({'bad':np.float64(np.nan)}),allow_nan=False)

    def test_archive_readback_does_not_trust_receipt_flag(self):
        import importlib.util,lzma,hashlib
        script=Path(__file__).resolve().parents[2]/'scripts/door_case/audit_selfpower.py'
        spec=importlib.util.spec_from_file_location('archive_readback_control',script)
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=b'not scientific evidence; byte integrity fixture';compressed=lzma.compress(raw)
            (root/'system.raw.xz').write_bytes(compressed)
            receipt={'path':'system.raw.archive.json','archive_name':'system.raw.xz','readback_verified':True,
                     'archive_sha256':hashlib.sha256(compressed).hexdigest(),'original_sha256':hashlib.sha256(raw).hexdigest(),
                     'original_bytes':len(raw)}
            self.assertTrue(audit.verify_native_archive(root,receipt))
            receipt['original_sha256']='0'*64
            self.assertFalse(audit.verify_native_archive(root,receipt))
            receipt['original_sha256']=hashlib.sha256(raw).hexdigest();receipt['original_bytes']+=1
            self.assertFalse(audit.verify_native_archive(root,receipt))

    def test_terminal_screen_separates_collector_coil_and_each_parallel_die(self):
        from bfworld.agentlab.door_selfpower import ratings
        design=contracts.normalize({'extraction':{'diodes':'BAT46WJ-3P'}})
        t=np.array([0.,1.,2.,3.])
        v={f'v({n})':np.zeros(4) for n in ('pz1,pz2','vin','mcu','out','gate','base','env','rect','nb','lx','collector','port','pz2')}
        v.update({'i(lextract)':np.full(4,.61),'ic(qp)':np.full(4,-.54),'ic(qn)':np.zeros(4)})
        for name,anode,_ in ratings.diode_nodes(design):
            v['v('+anode+')']=np.zeros(4)
            v['i('+name+')']=np.full(4,.18 if name.startswith('dblock') else .1)
        observed=ratings.check(t,v,design)
        self.assertTrue(observed['collector_current_passed'])
        self.assertTrue(observed['coil_current_passed'])
        self.assertTrue(observed['passed'])
        self.assertEqual(len(observed['diodes']),20)
        v['ic(qp)'][:]=-.61
        for name,_,_ in ratings.diode_nodes(design):
            if name.startswith('dblock'):v['i('+name+')'][:]=.61/3
        v['i(lextract)'][:]=.5
        observed=ratings.check(t,v,design)
        self.assertFalse(observed['collector_current_passed'])
        self.assertFalse(observed['passed'])
        v['i(dtransfer_1)'][2]=.6
        observed=ratings.check(t,v,design)
        self.assertFalse(observed['diode_repetitive_current_covered'])
        self.assertTrue(any('dtransfer_1:' in x for x in observed['unqualified_limits']))

    def test_single_surge_does_not_qualify_repeated_microsecond_peaks(self):
        from bfworld.agentlab.door_selfpower.ratings import diode_facts
        t=np.array([0.,1e-6,2e-6,3e-6,4e-6,5e-6,6e-6])
        facts=diode_facts(t,np.array([0.,.6,0.,0.,.5,0.,0.]),np.ones(7),.25)
        self.assertFalse(facts['repetitive_peak_covered'])
        self.assertEqual(facts['pulse_count_over_screen'],2)
        self.assertAlmostEqual(facts['max_pulse_width_over_screen_s'],2e-6)

    def test_parallel_diodes_are_real_separate_branches_and_old_tasks_stay_sealed(self):
        from bfworld.agentlab.simulation_tasks import load_task,check_candidate
        from bfworld.agentlab.door_selfpower import ratings
        from bfworld.agentlab.door_selfpower.evaluation import evaluate
        design=contracts.normalize({'extraction':{'diodes':'BAT46WJ-3P'}})
        self.assertEqual(design['schema_version'],contracts.SCHEMA_V3)
        self.assertEqual(contracts.verify_design(design),design)
        net=extraction.interface('sece',profile='schottky-parallel')
        self.assertEqual(sum(line.startswith('Rbal_') for line in net.splitlines()),18)
        self.assertEqual(sum(line.startswith('D') for line in net.splitlines()),20)
        self.assertIn('Dtransfer_3 dtransfer_a3 vin BAT46WJ',net)
        old_task=load_task('door-selfpower-nominal-v4');new_task=load_task('door-selfpower-nominal-v5')
        with self.assertRaisesRegex(ValueError,'TASK_DESIGN_VALUE:extraction.diodes'):
            check_candidate(old_task,{'candidate':design,'confirmation':True})
        self.assertEqual(check_candidate(new_task,{'candidate':design,'confirmation':True}),design)
        for key in ('frozen','service','required_checks'):
            self.assertEqual(new_task['task'][key],old_task['task'][key])
        result={'rating_protocol':ratings.VERSION,'run_status':'completed','source_stable':True,
                'checks':dict.fromkeys(new_task['task']['required_checks'],True),'metrics':{}}
        legacy=contracts.normalize()
        self.assertIn('SELFPOWER_RATING_PROTOCOL_MISMATCH',evaluate(old_task,legacy,result,{})['input_violations'])
        self.assertNotIn('SELFPOWER_RATING_PROTOCOL_MISMATCH',evaluate(new_task,legacy,result,{})['input_violations'])
        with self.assertRaisesRegex(ValueError,'REQUIRES_SECE'):
            contracts.normalize({'extraction':{'topology':'seh','diodes':'BAT46WJ-3P'}})

    def test_independent_audit_reads_native_peaks_and_rejects_edited_summary(self):
        import importlib.util,lzma
        from bfworld.agentlab.door_selfpower import ratings
        script=Path(__file__).resolve().parents[2]/'scripts/door_case/audit_selfpower.py'
        spec=importlib.util.spec_from_file_location('terminal_audit_control',script)
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        design=contracts.normalize({'extraction':{'diodes':'BAT46WJ-3P'}})
        names=['ic(qp)','i(lextract)']+['i('+name+')' for name,_,_ in ratings.diode_nodes(design)]
        n=len(names)+1;data=np.zeros(3,dtype=[('t','<f8'),('v','<f4',(n-1,))]);data['t']=[0.,1.,6.5]
        data['v'][:,0]=-.54;data['v'][:,1]=.61
        report={'collector_peak_A':float(np.float32(.54)),'coil_peak_A':float(np.float32(.61)),'diodes':{}}
        for i,name in enumerate(names[2:],2):
            peak=.18 if name.startswith('i(dblock') else .1
            data['v'][:,i]=peak;report['diodes'][name[2:-1]]={'forward_peak_A':float(np.float32(peak))}
        header=f'Flags: real\nNo. Variables: {n}\nNo. Points: 3\nVariables:\n0 time time\n'+''.join(f'{i+1} {name} current\n' for i,name in enumerate(names))+'Binary:\n'
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'system.raw.xz').write_bytes(lzma.compress(header.encode('utf-16-le')+data.tobytes()))
            (root/'system.raw.archive.json').write_text(json.dumps({'archive_name':'system.raw.xz'}))
            (root/'rating-check.json').write_text(json.dumps(report))
            self.assertTrue(audit.independent_terminal_currents(root,design)['passed'])
            report['diodes']['dtransfer_1']['forward_peak_A']=.01
            (root/'rating-check.json').write_text(json.dumps(report))
            value=audit.independent_terminal_currents(root,design)
            self.assertFalse(value['passed']);self.assertFalse(value['checks']['reported_peaks_match'])

    def test_gate_observer_does_not_confuse_unpowered_voltage_peak_with_enable(self):
        from bfworld.agentlab.door_selfpower.solver import gate_observation
        design=contracts.normalize({'gate':'reserve-e96-5v43-2v98'})
        t=np.array([0.,1.,2.,3.]);v={'v(out)':np.array([0.,.15,3.3,3.3]),
          'v(vin)':np.array([0.,5.55,5.35,5.1]),'v(ctl_delay)':np.array([0.,0.,5.35,5.1]),
          'v(gate)':np.array([0.,.15,3.3,3.3])}
        before={k:a.copy() for k,a in v.items()};observed=gate_observation(t,v,design)
        self.assertEqual(observed['overall_VIN_peak_V'],5.55)
        self.assertEqual(observed['powered_VIN_peak_V'],5.35)
        self.assertEqual(observed['powered_control_peak_V'],5.35)
        self.assertEqual(observed['first_monitor_powered_s'],2.)
        self.assertIsNone(observed['first_gate_enabled_s'])
        self.assertTrue(all(np.array_equal(a,before[k]) for k,a in v.items()))

    def test_v4_qualified_gate_is_a_real_design_change_not_an_evaluation_change(self):
        from bfworld.agentlab.simulation_tasks import load_task,check_candidate
        old_task=load_task('door-selfpower-nominal-v3');new_task=load_task('door-selfpower-nominal-v4')
        design=contracts.normalize({'gate':'reserve-e96-5v16-2v98','gate_switch':'Si2333CDS','circuit':{'cout_uF':22.}})
        self.assertEqual(design['parts']['divider_ohm'],[1740000.,523000.,715000.])
        self.assertAlmostEqual(design['parts']['gate_thresholds_V']['high_V'],5.1646433566433565)
        for key in ('frozen','service','required_checks'):
            self.assertEqual(new_task['task'][key],old_task['task'][key])
        with self.assertRaisesRegex(ValueError,'TASK_DESIGN_VALUE:gate'):
            check_candidate(old_task,{'candidate':design,'confirmation':True})
        self.assertEqual(check_candidate(new_task,{'candidate':design,'confirmation':True}),design)

    def test_output_reserve_task_adds_real_divider_but_keeps_prior_tasks_frozen(self):
        from bfworld.agentlab.simulation_tasks import load_task,check_candidate
        old_task=load_task('door-selfpower-nominal-v2');new_task=load_task('door-selfpower-nominal-v3')
        design=contracts.normalize({'gate':'reserve-e96-5v43-2v98','gate_switch':'Si2333CDS','circuit':{'cout_uF':22.}})
        self.assertEqual(design['parts']['divider_ohm'],[1740000.,562000.,681000.])
        gate=design['parts']['gate_thresholds_V']
        self.assertAlmostEqual(gate['high_V'],5.431600587371513)
        self.assertAlmostEqual(gate['low_V'],2.9758004827031375)
        for key in ('frozen','service','required_checks'):
            self.assertEqual(new_task['task'][key],old_task['task'][key])
        with self.assertRaisesRegex(ValueError,'TASK_DESIGN_VALUE:gate'):
            check_candidate(old_task,{'candidate':design,'confirmation':True})
        self.assertEqual(check_candidate(new_task,{'candidate':design,'confirmation':True}),design)

    def test_timeout_containment_ignores_other_jobs_and_reused_pids(self):
        from bfworld.agentlab.door_selfpower import native_process
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);circuit=root/'system.cir'
            table=f'17 LTspice.exe -b {circuit}\n18 LTspice.exe -b {circuit}.other\n19 wine-host\n'
            self.assertEqual(native_process.job_pids(table,circuit),[17])
            wine='21 LTspice.exe -b Y:\\different\\system.cir\n'
            self.assertEqual(native_process.job_pids(wine,circuit),[])
            self.assertEqual(native_process.job_pids(wine,circuit,lambda pid,raw:False),[])
            self.assertEqual(native_process.job_pids(wine,circuit,lambda pid,raw:raw==circuit.resolve().with_suffix('.raw')),[21])
            with patch.object(native_process.subprocess,'check_output',side_effect=[table,'17 other-process\n']),\
                    patch.object(native_process.os,'kill') as kill:
                native_process.contain_timeout(root)
                kill.assert_not_called()
            receipt=json.loads((root/'timeout-containment.json').read_text())
            self.assertEqual(receipt['actions'][0]['action'],'identity-changed-not-signalled')

    def test_relaxed_tolerances_cannot_be_accepted_as_completed_native_run(self):
        from bfworld.agentlab.door_selfpower import solver
        from bfworld.agentlab.simulation_chain.contracts import ChainError
        with tempfile.TemporaryDirectory() as td,patch.object(solver,'command'),\
                patch.object(solver.d4,'read_raw') as raw:
            root=Path(td);(root/'system.log').write_text('Warning: Simulation tolerance relaxed\nTotal elapsed time: 1 seconds.\n')
            with self.assertRaisesRegex(ChainError,'relaxed requested tolerance'):solver.native_solve(root,6.5)
            raw.assert_not_called()

    def test_real_low_voltage_component_has_new_identity_without_old_identity_drift(self):
        legacy=contracts.normalize();explicit=contracts.normalize({'gate_switch':'BSS84'})
        self.assertEqual(legacy,explicit)
        self.assertEqual(legacy['schema_version'],contracts.SCHEMA)
        revised=contracts.normalize({'gate_switch':'Si2333CDS'})
        self.assertEqual(revised['schema_version'],contracts.SCHEMA_V2)
        self.assertNotEqual(revised['design_id'],legacy['design_id'])
        self.assertEqual(revised['base_design']['frozen'],legacy['base_design']['frozen'])
        self.assertEqual(revised,contracts.verify_design(revised))
        self.assertEqual(door_selfpower.validate({'candidate':revised})['candidate'],revised)
        drift=copy.deepcopy(revised);drift['parts']['load_switch_model']['Vds_limit_V']=100.
        with self.assertRaises(ValueError):contracts.verify_design(drift)
        for part in ('ideal','Si2333CDS-fitted',{},True):
            with self.assertRaises(ValueError):contracts.normalize({'gate_switch':part})

    def test_load_switch_vendor_hash_and_original_three_pin_subcircuit_required(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'Si2333CDS.spice.txt';path.write_text('.SUBCKT Si2333CDS D G S\n.ENDS\n')
            with patch.object(extraction,'SWITCH_SOURCE_ROOT',Path(td)):
                with self.assertRaisesRegex(ValueError,'VENDOR_MODEL_CHANGED'):extraction.energy_gate(load_switch='Si2333CDS')
                with patch.object(extraction,'SI2333_MODEL_HASH',hashlib.sha256(path.read_bytes()).hexdigest()):
                    text=extraction.energy_gate(load_switch='Si2333CDS')
                self.assertIn('Xpass mcu gate out Si2333CDS',text)
                self.assertNotIn('Mpass',text)
                self.assertIn('Bmonitor out 0 I=1.5e-06',text)
                self.assertIn(path.read_text(),text)
        with self.assertRaisesRegex(ValueError,'LOAD_SWITCH_INVALID'):extraction.load_switch_model('ideal')

    def test_new_task_admits_real_switch_without_changing_frozen_evaluation(self):
        from bfworld.agentlab.simulation_tasks import load_task,check_candidate
        a=load_task('door-selfpower-nominal-v1');b=load_task('door-selfpower-nominal-v2')
        revised=contracts.normalize({'gate_switch':'Si2333CDS'})
        self.assertEqual(a['task']['frozen'],b['task']['frozen'])
        self.assertEqual(a['task']['service'],b['task']['service'])
        self.assertEqual(a['task']['required_checks'],b['task']['required_checks'])
        with self.assertRaisesRegex(ValueError,'TASK_PROTECTED_FIELD:gate_switch'):
            check_candidate(a,{'candidate':revised,'confirmation':True})
        self.assertEqual(check_candidate(b,{'candidate':revised,'confirmation':True}),revised)
        self.assertEqual(check_candidate(a,{'candidate':contracts.normalize(),'confirmation':True}),contracts.normalize())

    def test_copied_native_logs_are_not_independent_cold_launches(self):
        import importlib.util
        import shutil
        script=Path(__file__).resolve().parents[2]/'scripts/door_case/audit_selfpower.py'
        spec=importlib.util.spec_from_file_location('selfpower_audit_control',script)
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        with tempfile.TemporaryDirectory() as td:
            original=Path(td)/'primary'
            for stage in ('joint','time-step'):
                directory=original/stage/'iteration-00';directory.mkdir(parents=True)
                (directory.parent/'coupling-iterations.json').write_text('[{"iteration":0}]')
                (directory/'system.log').write_text(
                    f'Circuit: {directory}/system.cir\nStart Time: Wed Oct 7 03:00:00 2026\n'
                    'Total elapsed time: 220.1 seconds.\n')
            self.assertTrue(audit.native_launch_identity(original)['passed'])
            copied=Path(td)/'copy';shutil.copytree(original,copied)
            checked=audit.native_launch_identity(copied)
            self.assertFalse(checked['passed'])
            self.assertTrue(all(not x['circuit_matches_run'] for x in checked['launches']))

    def test_unfinished_native_log_cannot_pass_cold_launch_audit(self):
        import importlib.util
        script=Path(__file__).resolve().parents[2]/'scripts/door_case/audit_selfpower.py'
        spec=importlib.util.spec_from_file_location('selfpower_audit_incomplete_control',script)
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for stage in ('joint','time-step'):
                directory=root/stage/'iteration-00';directory.mkdir(parents=True)
                (directory.parent/'coupling-iterations.json').write_text('[{"iteration":0}]')
                (directory/'system.log').write_text(
                    f'Circuit: {directory}/system.cir\nStart Time: Wed Oct 7 03:00:00 2026\n')
            self.assertFalse(audit.native_launch_identity(root)['passed'])

    def test_agreeing_peaks_cannot_hide_failed_fine_physics_or_coupling(self):
        valid={'peak_storage_V':6.3,'peak_tip_mm':7.8,'tx_completed':1,'received_events':1,
               'numerical_energy_passed':True,'drive_ledger':{'numerical_passed':True},
               'energy_ledger':{'energy_lower_bound_passed':True},'ratings':{'passed':True},
               'coupling_converged':True}
        self.assertTrue(pipeline.confirmation_check(valid,valid)['passed'])
        for parent,key,bad in ((None,'peak_tip_mm',8.01),(None,'numerical_energy_passed',False),
                               ('drive_ledger','numerical_passed',False),
                               ('energy_ledger','energy_lower_bound_passed',False),
                               ('ratings','passed',False),(None,'coupling_converged',False)):
            fine=copy.deepcopy(valid)
            (fine if parent is None else fine[parent])[key]=bad
            with self.subTest(parent=parent,key=key):
                step=pipeline.confirmation_check(valid,fine)
                self.assertTrue(step['TX_count_equal'] and step['RX_count_equal'])
                self.assertFalse(step['passed'])

    def test_missing_fine_evidence_and_event_or_step_disagreement_are_rejected(self):
        valid={'peak_storage_V':6.3,'peak_tip_mm':7.8,'tx_completed':1,'received_events':1,
               'numerical_energy_passed':True,'drive_ledger':{'numerical_passed':True},
               'energy_ledger':{'energy_lower_bound_passed':True},'ratings':{'passed':True},
               'coupling_converged':True}
        for key in ('ratings','drive_ledger','energy_ledger','numerical_energy_passed','coupling_converged'):
            fine=copy.deepcopy(valid);fine.pop(key)
            with self.subTest(missing=key):self.assertFalse(pipeline.confirmation_check(valid,fine)['passed'])
        for key,value in (('peak_storage_V',6.5),('tx_completed',0),('received_events',0)):
            fine=copy.deepcopy(valid);fine[key]=value
            with self.subTest(changed=key):self.assertFalse(pipeline.confirmation_check(valid,fine)['passed'])

    def test_reference_reuse_accepts_d4_or_nested_d5_and_rejects_frozen_drift(self):
        design=contracts.normalize({'mechanical':{'gap_mm':46.},'circuit':{'cin_uF':10.,'cout_uF':15.}})
        self.assertEqual(pipeline.reference_base(design),design['base_design'])
        self.assertEqual(pipeline.reference_base(design['base_design']),design['base_design'])
        broken=copy.deepcopy(design)
        broken['base_design']['circuit']['initial_storage_V']=1.
        with self.assertRaises(ValueError):pipeline.reference_base(broken)
        broken=copy.deepcopy(design['base_design'])
        broken['mechanical']['gap_mm']=45.
        with self.assertRaises(ValueError):pipeline.reference_base(broken)

    def test_low_storage_never_dispatches_native_and_is_not_design_failure(self):
        with tempfile.TemporaryDirectory() as td,patch.object(pipeline,'storage_observation',return_value={
                'ready':False,'free_bytes':100_000_000,'minimum_free_bytes':pipeline.MIN_FREE_BYTES}),\
                patch.object(pipeline.native,'cad') as cad,patch.object(pipeline.solver,'solve') as solve:
            out=Path(td)/'rejected';result=pipeline.run(contracts.normalize(),out,authority='operator-reference')
            self.assertEqual(result['run_status'],'environment_fail')
            self.assertEqual(result['qualification']['nominal_status'],'not_evaluable')
            self.assertFalse(result['qualification']['nominal_prediction_eligible'])
            cad.assert_not_called();solve.assert_not_called()
            self.assertEqual(json.loads((out/'result.json').read_text())['failure_kind'],'execution_resource')
            before=(out/'design-spec.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'ALREADY_EXISTS'):pipeline.run(contracts.normalize(),out)
            self.assertEqual((out/'design-spec.json').read_bytes(),before)

    def test_resource_and_physics_failures_remain_distinct(self):
        import errno
        from bfworld.agentlab.simulation_chain.contracts import ChainError
        disk=pipeline.failure_facts(OSError(errno.ENOSPC,'fixture no space'))
        self.assertEqual(disk['run_status'],'environment_fail')
        self.assertFalse(disk['design_infeasible'])
        physical=pipeline.failure_facts(ChainError('out_of_domain','fixture mechanical range'))
        self.assertEqual(physical['run_status'],'out_of_domain')
        self.assertNotIn('failure_kind',physical)

    def test_design_freedom_cannot_change_environment_model_or_energy(self):
        for value in ({'task':{'opening_s':.1}}, {'circuit':{'initial_vin_V':5}},
                      {'circuit':{'diagnostic_input_A':.001}}, {'mechanical':{'damping_ratio':.001}},
                      {'firmware':{'boot_mA':.01}}, {'extraction':{'dcr':0}},
                      {'gate':{'iq_A':0}}, {'extraction':{'envelope_pF':True}},
                      {'extraction':{'envelope_pF':float('nan')}}):
            with self.subTest(value=value),self.assertRaises(ValueError):contracts.normalize(value)

    def test_architecture_identity_preserves_sealed_task_and_actual_load(self):
        a=contracts.normalize();b=contracts.normalize({'extraction':{'topology':'direct'}})
        self.assertNotEqual(a['design_id'],b['design_id'])
        self.assertEqual(a['base_design']['frozen'],old.FROZEN)
        self.assertEqual(a['base_design']['frozen'],b['base_design']['frozen'])
        self.assertEqual(a,contracts.verify_design(a))
        for path in ('base_design','parts'):
            bad=copy.deepcopy(a)
            if path=='base_design':bad[path]['frozen']['model']['tx_mA']=.01
            else:bad[path]['coil']['dcr_ohm_max']=0
            with self.assertRaises(ValueError):contracts.verify_design(bad)
        once=contracts.normalize({'application':{'packet_policy':'one-shot'}})
        beacon=contracts.normalize({'application':{'packet_policy':'beacon'}})
        self.assertNotEqual(once['design_id'],beacon['design_id'])
        self.assertEqual(once['base_design']['frozen'],beacon['base_design']['frozen'])

    def test_compiled_d5_program_keeps_workload_brownout_and_pgood_semantics(self):
        from bfworld.agentlab.door_selfpower import firmware
        from bfworld.agentlab.door_system.solver import execute_program
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);design=contracts.normalize();receipt=firmware.build(p,design)
            self.assertEqual(receipt['brownout_V'],1.8)
            grid=np.linspace(0,.3,3001);supply=np.full(len(grid),3.3)
            # A deasserted PGOOD after INIT does not imply actual SoC brownout.
            good=np.where(grid<.058,3.3,0.)
            cur,states,events=execute_program(p,grid,supply,good)
            self.assertEqual(len(events),1)
            self.assertGreaterEqual(events[0]['time_s'],.0538+.013+.005)
            for state,expected in ((1,.410e-3),(3,1.596e-3),(4,3.659e-3)):
                self.assertTrue(np.all(cur[states==state]==expected))
            supply[(grid>=.069)&(grid<.071)]=1.79
            _,_,events=execute_program(p,grid,supply,good)
            self.assertEqual(len(events),0)

    def test_diode_identity_and_program_current_cannot_be_silently_changed(self):
        a=contracts.normalize({'extraction':{'diodes':'BAT46WJ'}})
        b=contracts.normalize({'extraction':{'diodes':'BAS21HY'}})
        self.assertNotEqual(a['design_id'],b['design_id'])
        for bad in ({'application':{'boot_ms':1}}, {'application':{'packet_policy':'skip-boot'}},
                    {'extraction':{'diodes':'ideal'}}):
            with self.assertRaises(ValueError):contracts.normalize(bad)

    def test_sampled_program_workload_exact_at_shifted_clock_and_completion_brownout(self):
        from bfworld.agentlab.door_selfpower import firmware
        from bfworld.agentlab.door_system.solver import execute_program
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);firmware.build(p,contracts.normalize())
            grid=np.linspace(0,3,30001);start=27873
            supply=np.where(np.arange(len(grid))>=start,3.3,0.)
            good=np.where(supply>0,3.3,0.)
            current,states,events=execute_program(p,grid,supply,good)
            self.assertEqual(len(events),1)
            self.assertEqual(int(np.sum(states==1)),538)
            self.assertEqual(int(np.sum(states==3)),130)
            self.assertEqual(int(np.sum(states==4)),50)
            complete=start+538+1+130+50
            self.assertAlmostEqual(events[0]['time_s'],grid[complete],places=12)
            active=(states==1)|(states==3)|(states==4)
            energy=float(np.sum(current[active])*1e-4*3.3)
            self.assertAlmostEqual(energy,3.3*(.410e-3*.0538+1.596e-3*.013+3.659e-3*.005),places=12)
            # Reset wins even at the exact required completion timestamp.
            supply[complete:]=1.79
            _,_,events=execute_program(p,grid,supply,good)
            self.assertEqual(events,[])

    def test_confirmation_cannot_be_disabled_by_agent(self):
        with self.assertRaises(ValueError):door_selfpower.validate({'confirmation':False})
        self.assertEqual(door_selfpower.validate({})['candidate'],contracts.normalize())

    def test_energy_reserve_divider_follows_datasheet(self):
        r1,r2,r3=extraction.reserve_divider(6.5,4.3)
        self.assertAlmostEqual(r1+r2+r3,3e6)
        self.assertAlmostEqual(1.24*3e6/r3,6.5)
        self.assertAlmostEqual(1.24*3e6/(r2+r3),4.3)
        for high,low in ((3.3,3.8),(8,9),(float('nan'),4.3)):
            with self.assertRaises(ValueError):extraction.reserve_divider(high,low)

    def test_gate_losses_and_supply_qualification_are_in_power_network(self):
        with patch.object(extraction,'local_model',return_value='.model BSS84 VDMOS(pchan)'):
            s=extraction.energy_gate()
        self.assertIn('Bmonitor out 0 I=1.5e-06',s)
        self.assertIn('if(V(out)>1.5',s)
        self.assertNotIn('Rpull out gate',s)
        self.assertIn('Mpass mcu gate out out BSS84',s)
        self.assertIn('Smonitor_high gate out ctl_high 0',s)
        self.assertIn('MIC841L',s)
        self.assertIn('Cmcu mcu 0 100n IC=0',s)
        self.assertNotIn('Vcontrol',s)

    def test_sece_has_no_permanent_coil_path_from_piezo_to_storage(self):
        s=extraction.interface('sece')
        self.assertIn('QP collector nb lx 2N5401',s)
        self.assertIn('Lextract lx 0',s)
        self.assertNotIn('Lextract lt lx',s)
        self.assertNotIn('Dblock rect lt',s)
        self.assertIn('Cenv env 0',s)

    def test_only_complete_qualified_results_can_pass(self):
        r={'run_status':'completed','checks':dict.fromkeys(('rom_domain','force_interpolation','energy_balance',
          'drive_balance','electrical_energy_lower_bound','component_ratings','program_power_fixed_point','time_step'),True),
          'metrics':{'cold_start_reached':True,'received_events':1}}
        self.assertEqual(pipeline.qualification(r)['nominal_status'],'satisfied')
        self.assertFalse(pipeline.qualification(r)['hardware_verified'])
        r['metrics']['received_events']=0
        self.assertEqual(pipeline.qualification(r)['nominal_status'],'unsatisfied')
        r['metrics']['received_events']=1;r['checks']['component_ratings']=False
        self.assertEqual(pipeline.qualification(r)['nominal_status'],'not_evaluable')
        r['checks']['component_ratings']=True;r['run_status']='numerical_fail'
        self.assertEqual(pipeline.qualification(r)['nominal_status'],'not_evaluable')

    def test_no_agent_reference_gate_default_and_hash_tampering(self):
        with tempfile.TemporaryDirectory() as td,patch.object(door_selfpower,'REFERENCE_ROOT',Path(td)/'reference-cases/door-selfpower-v1'):
            self.assertFalse(door_selfpower.reference_ready())
            root=Path(td)/'reference-cases/door-selfpower-v1';root.mkdir(parents=True)
            result=root/'result.json'
            result.write_text(json.dumps({'qualification':{'nominal_prediction_eligible':True,'nominal_status':'satisfied'},
                  'design_id':'same-test-design','model_calls':0,'source_stable':True,'execution_authority':'operator-reference'}))
            (root/'system-manifest.json').write_text(json.dumps({'source_dependencies':{}}))
            repeat=root/'repeat';repeat.mkdir();(repeat/'result.json').write_text(result.read_text())
            audit=root/'audit.json'
            audit.write_text(json.dumps({'passed':True,'cold_repeat':{'passed':True},'runs':[
                {'path':str(p),'result_sha256':door_selfpower.file_hash(p/'result.json'),
                 'passed':True,'executor_sha256':contracts.template_hash(),'design_id':'same-test-design'}
                for p in (root,repeat)]}))
            receipt={'result_path':str(result),'result_sha256':door_selfpower.file_hash(result),
                     'executor_sha256':contracts.template_hash(),'audit_path':str(audit),'audit_sha256':door_selfpower.file_hash(audit)}
            (root/'qualified-reference.json').write_text(json.dumps(receipt))
            self.assertTrue(door_selfpower.reference_ready())
            result.write_text(result.read_text()+' ')
            self.assertFalse(door_selfpower.reference_ready())

    def test_d5_task_evaluation_rejects_wrong_or_incomplete_packets(self):
        from bfworld.agentlab.simulation_tasks import load_task,check_candidate,evaluate
        binding=load_task('door-selfpower-nominal-v1');design=contracts.normalize()
        self.assertEqual(check_candidate(binding,{'candidate':design,'confirmation':True}),design)
        result={'run_status':'completed','source_stable':True,'checks':dict.fromkeys(binding['task']['required_checks'],True),
                'metrics':{'cold_start_reached':True}}
        packet={'capture_id':'real-complete','time_s':2.9,'payload_hex':binding['task']['service']['expected_payload_hex']}
        receiver={'transmitted':[packet],'delivered':[packet],'events':[{}]}
        self.assertEqual(evaluate(binding,design,result,receiver)['nominal_task_status'],'satisfied')
        receiver['transmitted']=[]
        self.assertEqual(evaluate(binding,design,result,receiver)['nominal_task_status'],'unsatisfied')
        receiver['transmitted']=[packet];result['checks']['component_ratings']=False
        self.assertEqual(evaluate(binding,design,result,receiver)['nominal_task_status'],'not_evaluable')
        changed=copy.deepcopy(binding);changed['task']['frozen']['model']['tx_mA']=.01
        from bfworld.agentlab.simulation_chain.contracts import digest
        changed['task_hash']=digest(changed['task'])
        with self.assertRaisesRegex(ValueError,'FROZEN_MISMATCH'):
            check_candidate(changed,{'candidate':design,'confirmation':True})

    def test_lossless_native_archive_roundtrip(self):
        import lzma,hashlib
        from bfworld.agentlab.door_selfpower.archive import archive_raw
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'system.raw';data=b'Title: native\nBinary:\n'+bytes(range(256))*71;p.write_bytes(data)
            record=archive_raw(p)
            self.assertFalse(p.exists())
            self.assertEqual(lzma.decompress(p.with_suffix('.raw.xz').read_bytes()),data)
            self.assertEqual(record['original_sha256'],hashlib.sha256(data).hexdigest())
            self.assertTrue(record['readback_verified'])

    def test_actual_e96_parts_and_thresholds_share_design_identity(self):
        gate=contracts.GATES['reserve-e96-6v1']
        design=contracts.normalize({'gate':'reserve-e96-6v1'})
        self.assertEqual(design['parts']['divider_ohm'],[1740000.,634000.,604000.])
        self.assertAlmostEqual(sum(gate['divider_ohm']),2978000.)
        self.assertAlmostEqual(gate['high_V'],6.113774834437086)
        self.assertAlmostEqual(gate['low_V'],2.98281098546042)
        with patch.object(extraction,'local_model',return_value='.model BSS84 VDMOS(pchan)'):
            text=extraction.energy_gate(**gate)
            self.assertIn('Rmon1 vin lth 1740000.0',text)
            self.assertIn('Rmon2 lth hth 634000.0',text)
            self.assertIn('Rmon3 hth 0 604000.0',text)
            with self.assertRaisesRegex(ValueError,'THRESHOLD_MISMATCH'):
                extraction.energy_gate(**{**gate,'high_V':6.5})

    def test_pushpull_revision_has_real_parts_and_no_static_pullup_drain(self):
        gate=contracts.GATES['reserve-e96-6v3']
        design=contracts.normalize({'gate':'reserve-e96-6v3'})
        self.assertEqual(design['parts']['divider_ohm'],[1780000.,619000.,590000.])
        self.assertIsNone(design['parts']['gate_pullup_ohm'])
        self.assertLessEqual(sum(gate['divider_ohm']),3e6)
        self.assertAlmostEqual(gate['high_V'],6.281966101694915)
        self.assertAlmostEqual(gate['low_V'],3.0656410256410256)
        self.assertEqual(design['base_design']['frozen'],old.FROZEN)

    def test_low_trip_revision_is_physical_divider_not_changed_mcu_brownout(self):
        design=contracts.normalize({'gate':'reserve-e96-6v3-2v96'})
        self.assertEqual(design['parts']['divider_ohm'],[1740000.,665000.,590000.])
        self.assertLessEqual(design['parts']['divider_total_ohm'],3e6)
        self.assertAlmostEqual(design['parts']['gate_thresholds_V']['high_V'],6.294576271186441)
        self.assertAlmostEqual(design['parts']['gate_thresholds_V']['low_V'],2.959203187250996)
        self.assertEqual(design['base_design']['frozen'],old.FROZEN)

    def test_d4_task_cannot_open_d5_architecture_seam(self):
        from bfworld.agentlab.engineering import validate
        from bfworld.agentlab.simulation_tasks import load_task,SimulationTasks
        p=validate('door-selfpower',{'candidate':{}})
        tasks=object.__new__(SimulationTasks)
        with patch.object(tasks,'binding',return_value=load_task('door-motion-structure-v2')):
            with self.assertRaisesRegex(ValueError,'TASK_ENGINE_NOT_ALLOWED'):
                tasks.guard('test-owner','door-selfpower',p)

    def test_catalog_exposes_no_agent_reference_block(self):
        from bfworld.agentlab.engineering import Engineering
        engine=object.__new__(Engineering)
        engine.app=SimpleNamespace()
        engine.eda=SimpleNamespace(catalog=lambda owner: {})
        engine.tasks=SimpleNamespace(binding=lambda owner: None)
        with patch.object(door_selfpower,'reference_ready',return_value=False), \
             patch.object(pipeline,'storage_observation',return_value={'ready':True}):
            value=next(x for x in engine.catalog()['engines'] if x['id']=='door-selfpower')
        self.assertFalse(value['runnable'])
        self.assertEqual(value['operator_runnable'],value['installed'])
        self.assertEqual(value['blocked_reason'],'SELFPOWER_NO_AGENT_REFERENCE_NOT_QUALIFIED')


    def test_catalog_blocks_operator_and_agent_on_low_disk_without_hiding_reference(self):
        from bfworld.agentlab.engineering import Engineering
        engine=object.__new__(Engineering)
        engine.app=SimpleNamespace()
        engine.eda=SimpleNamespace(catalog=lambda owner: {})
        engine.tasks=SimpleNamespace(binding=lambda owner: None)
        with patch.object(door_selfpower,'reference_ready',return_value=True), \
             patch.object(pipeline,'storage_observation',return_value={'ready':False,'free_bytes':135000000}):
            value=next(x for x in engine.catalog()['engines'] if x['id']=='door-selfpower')
        self.assertTrue(value['reference_ready'])
        self.assertFalse(value['runnable'])
        self.assertFalse(value['operator_runnable'])
        self.assertEqual(value['blocked_reason'],'SELFPOWER_STORAGE_UNAVAILABLE')
        self.assertEqual(value['storage']['free_bytes'],135000000)


if __name__=='__main__':unittest.main()
