import array
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from bfworld.agentlab.design_lab.repository_load import normalize_timeline, load_binding
from bfworld.agentlab.design_lab.repository_validation import power_review, native_review_reuse


def windows():
    return {'timeline': {'t_stop_s': 1.}, 'emission': {'edge_quantum_s': .000001},
        'referral': {'factor_k': .5, 'leak_a': 1e-6},
        'declared_amplitudes_1v8': {'quiescent_a': 1e-5, 'boot_a': .0026,
            'advertising_a': .003, 'connection_a': .005, 'notify_a': .006,
            'cdc_convert_a': .00018},
        'radio_domain_facts': {'advertising_interval_ms': 187.5, 'connection_min_ms': 100.,
            'connection_max_ms': 200., 'sample_ms': 5000., 'policy_advertising_ms': 5000.},
        'windows_ms': {'boot': [[0., 10.]],
            'advertising': {'count': 1, 'windows': [[20., 21.]]},
            'connection_event': {'count': 2, 'first_ms': 100., 'last_ms': 200.,
                'period_ms': 100., 'pulse_ms': 2.},
            'notify': {'count': 1, 'windows': [[200., 202.]]},
            'cdc_convert': {'count': 1, 'windows': [[188., 200.]]},
            'sample_request': {'instants_ms': [200.]}},
        'window_charge': {'referred_load_only_c': .00003658,
            'window_charge_storage_rail_referred_c': .00003758}}


class LoadBindingCase(unittest.TestCase):
    def test_windows_are_integrated_with_overlap_and_half_open_edges(self):
        original=windows(); model=normalize_timeline(original)
        self.assertNotIn('pwl_time_value_referred_to_storage_rail_a', original)
        points=dict(model['pwl_time_value_referred_to_storage_rail_a'])
        self.assertEqual(18,len(points))
        self.assertAlmostEqual(.001305,points[0.])
        self.assertAlmostEqual(.000005,points[.01])
        self.assertAlmostEqual(.000095,points[.188])
        self.assertAlmostEqual(.005505,points[.2])
        self.assertAlmostEqual(.000005,points[.202])
        pairs=list(points.items())
        charge=sum((t1-t0)*(i0+i1)/2 for (t0,i0),(t1,i1) in zip(pairs,pairs[1:]))
        # Hand ledger: (26+3+20+12+2.16+10) uC * 0.5; leakage is separate.
        self.assertAlmostEqual(.00003658,charge,delta=2e-9)
        self.assertEqual(.00003658,model['window_charge_storage_rail_c'])
        self.assertEqual([.2],model['events_covered']['sample_and_notify_2byte_s'])

    def test_radio_alias_conflict_is_explicit(self):
        model=windows(); model['actual_radio_timing']={'advertising_period_ms': 5000}
        with self.assertRaisesRegex(ValueError,'RADIO_ALIASES_DISAGREE'):
            normalize_timeline(model)

    def test_shifted_declared_windows_do_not_match_solver_load(self):
        first=normalize_timeline(windows()); shifted=windows()
        shifted['windows_ms']['notify']['windows']=[[300.,302.]]
        result=load_binding(normalize_timeline(shifted),'unused',first['pwl_time_value_referred_to_storage_rail_a'])
        self.assertEqual('FAIL',result['status']);self.assertFalse(result['pwl_equal'])

    def test_compact_binding_accepts_exact_bytes_without_inventing_vector(self):
        circuit='Iload mcu_rail 0 PWL(0 1e-5 1 1e-5)\n'
        model={'emitted_expansion':{'pwl_file_sha256':hashlib.sha256(circuit.encode()).hexdigest(),
            'pwl_source_name':'Iload','pwl_points':2}}
        result=load_binding(model,circuit,[[0,1e-5],[1,1e-5]])
        self.assertEqual('PASS',result['status']);self.assertIsNone(result['pwl_equal'])
        self.assertEqual('FAIL',load_binding(model,circuit+'* change\n',[[0,1e-5],[1,1e-5]])['status'])
        self.assertEqual('FAIL',load_binding(model,circuit,[[0,1e-5]])['status'])

    def test_missing_witness_is_unevaluable(self):
        result=load_binding({},'unused',[[0,1e-5],[1,1e-5]])
        self.assertEqual('UNEVALUABLE',result['status']);self.assertIsNone(result['pwl_equal'])

    def test_expanded_numeric_mismatch_and_nonfinite_values_fail(self):
        points=[[0,.001],[1,.002]]
        self.assertEqual('PASS',load_binding({'pwl_time_value_referred_to_storage_rail_a':points},'',points)['status'])
        for bad in ([[0,.003],[1,.002]],[[0,float('nan')],[1,.002]],'bad'):
            self.assertEqual('FAIL',load_binding({'pwl_time_value_referred_to_storage_rail_a':bad},'',points)['status'])

    def test_invalid_window_count_and_time_grid_rejected(self):
        for key,change,error in [
            ('advertising',{'count':2,'windows':[[20.,21.]]},'WINDOW_COUNT'),
            ('connection_event',{'count':2,'first_ms':100.,'last_ms':201.,'period_ms':100.,'pulse_ms':2.},'CONNECTION_LAST'),
            ('notify',{'count':1,'windows':[[202.0005,203.]]},'EDGE_QUANTUM'),
            ('boot',[[0.,float('inf')]],'FINITE_NUMBER')]:
            with self.subTest(key=key):
                model=windows();model['windows_ms'][key]=change
                with self.assertRaisesRegex(ValueError,error):normalize_timeline(model)

    def test_legacy_event_alias_is_retained(self):
        old={'events_covered':{'sample_and_notify_s':[.3,5.3]}}
        self.assertEqual([.3,5.3],normalize_timeline(old)['events_covered']['sample_and_notify_2byte_s'])

    def test_compact_check_preserves_actual_supply_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'blobs').mkdir()
            def blob(value):
                data=json.dumps(value).encode();sha=hashlib.sha256(data).hexdigest()
                (root/'blobs'/sha).write_bytes(data);return {'sha256':sha}
            circuit='Iload mcu_rail 0 PWL(0 1e-5 1 1e-5)\n'
            model={'actual_radio_timing':{'advertising_period_ms':187.5,'connection_period_ms_used':100,'sample_period_ms':5000},
                'window_charge_storage_rail_c':1e-5,'emitted_expansion':{
                    'pwl_file_sha256':hashlib.sha256(circuit.encode()).hexdigest(),'pwl_source_name':'Iload','pwl_points':2}}
            system={'files':{'project-chain/interface-params.json':blob({'regulator':{'v_out_v':1.8}}),
                             'project-chain/load-timeline.json':blob(model)}}
            raw=b'No. Points: 2\nNo. Variables: 4\nVariables:\n0 time time\n1 v(supply_1v8) voltage\n2 v(storage_rail) voltage\n3 v(mcu_rail) voltage\nBinary:\n'
            raw+=array.array('d',[0.,1.8,4.2,1.8,1.,.16,.4,-3.]).tobytes()
            sha=hashlib.sha256(raw).hexdigest();(root/'blobs'/sha).write_bytes(raw)
            job={'job_id':'test-trace','consumed_sources':{},'record':{'artifacts':{'project-trace.raw':{'sha256':sha}}},
                 'request':{'project':{'manifest':{'entrypoint':'chain_joint.cir'},'sources':{'chain_joint.cir':circuit}}}}
            result=power_review(SimpleNamespace(root=root),system,job,{'status':'PASS'})
            self.assertEqual('FAIL',result['status']);self.assertEqual('PASS',result['load_binding']['status'])
            self.assertIsNone(result['load_pwl_equal'])
            self.assertEqual(['supply falls below the declared operating voltage',
                             'manual admission produces a negative MCU rail'],result['findings'])

    def test_native_review_reuse_ignores_load_changes_and_retains_drc_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'blobs').mkdir()
            def blob(data):
                if not isinstance(data,bytes):data=json.dumps(data).encode()
                sha=hashlib.sha256(data).hexdigest();(root/'blobs'/sha).write_bytes(data);return {'sha256':sha}
            native='public-round3-facts-20261014/PCB1.epcb2'
            path='public-round3-facts-20261014/independent-reviews/pcb_connectivity_drc.json'
            ref=blob(b'\x00\xff saved native board')
            report={'actor':'independent-checker','gate_id':'pcb_connectivity_drc','status':'FAIL',
                'supporting_sources':[{'path':native,**ref}],'findings':{'fresh_drc_counts':{'Connection Error':50}},'bindings':[]}
            original={'id':'SC-original','files':{native:ref,path:blob(report)},'jobs':{}}
            current=copy.deepcopy(original);current['files']['project-chain/chain_joint.cir']=blob(b'new load')
            repo=SimpleNamespace(root=root)
            result=native_review_reuse(repo,current,'pcb_connectivity_drc',original)
            self.assertEqual('FAIL',result['status'])
            self.assertEqual(50,result['findings']['fresh_drc_counts']['Connection Error'])
            self.assertEqual('SC-original',result['exact_native_evidence_reuse']['original_system'])
            current['files'][native]=blob(b'changed native board')
            self.assertEqual('RECHECK_REQUIRED',native_review_reuse(repo,current,'pcb_connectivity_drc',original)['status'])

    def test_changed_native_review_cannot_regrade_same_board(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'blobs').mkdir()
            native='public-round3-facts-20261014/PCB1.epcb2'
            path='public-round3-facts-20261014/independent-reviews/pcb_connectivity_drc.json'
            original={'id':'SC-original','files':{native:{'sha256':'saved-board'},path:{'sha256':'original-review'}}}
            current=copy.deepcopy(original);current['files'][path]={'sha256':'different-review'}
            with self.assertRaisesRegex(ValueError,'ORIGINAL_NATIVE_REVIEW_CHANGED'):
                native_review_reuse(SimpleNamespace(root=root),current,'pcb_connectivity_drc',original)


if __name__=='__main__':unittest.main()
