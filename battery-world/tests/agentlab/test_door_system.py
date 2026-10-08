import copy
import json
import tempfile
import unittest
from pathlib import Path
from bfworld.agentlab.door_system import contracts, model

class DoorSystemTests(unittest.TestCase):
    def test_environment_model_diagnostic_numeric_and_boolean_edits_rejected(self):
        for candidate in ({'task': {'opening_s': .1}}, {'mechanical': {'damping_ratio': .001}},
                          {'circuit': {'diagnostic_input_A': .001}}, {'firmware': {'tx_mA': .1}},
                          {'solver': {'reltol': .1}}, {'mechanical': {'polarity': 0}},
                          {'circuit': {'cin_uF': True}}, {'circuit': {'cin_uF': float('nan')}}):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError): contracts.normalize(candidate)

    def test_real_bracket_changes_identity_without_relaxing_task(self):
        baseline = contracts.normalize(); modified = contracts.normalize({'mechanical': {'closed_dz_mm': 0}})
        self.assertNotEqual(baseline['design_id'], modified['design_id'])
        self.assertEqual(baseline['frozen'], modified['frozen'])
        self.assertEqual(contracts.verify_design(modified), modified)
        tampered = copy.deepcopy(modified); tampered['frozen']['model']['boot_mA'] = .1
        with self.assertRaises(ValueError): contracts.verify_design(tampered)

    def test_coordinate_binding_and_cycle_continuity(self):
        import numpy as np
        d = contracts.normalize(); dx, dz = model.coordinates(0, d['mechanical'])
        self.assertAlmostEqual(dx*1000, 48); self.assertAlmostEqual(dz*1000, -30.265)
        f = d['frozen']; angles = model.angle_path(np.array([0, 2, 2.5, 4.5, 6.5]), f)
        np.testing.assert_allclose(angles, np.deg2rad([65, 0, 0, 65, 65]))
        centered = contracts.normalize({'mechanical': {'closed_dz_mm': 0}})
        self.assertAlmostEqual(model.coordinates(0, centered['mechanical'])[1], 0)

    def test_potential_derivative_reciprocity_and_physical_polarity(self):
        import numpy as np
        for polarity in (-1, 1):
            mech = contracts.normalize({'mechanical': {'polarity': polarity, 'closed_dz_mm': 0}})['mechanical']
            for angle, q in ((0, .003), (.06, -.001), (.8, .002)):
                force, _ = model.field_energy(angle, q, mech)
                eps = 1e-7
                derivative = -(model.field_energy(angle, q+eps, mech)[1]-model.field_energy(angle, q-eps, mech)[1])/(2*eps)
                self.assertTrue(np.isclose(force[2], derivative, rtol=1e-5, atol=1e-8))

    def test_initial_state_has_no_undeclared_preload_or_supply(self):
        d = contracts.normalize()
        self.assertEqual(d['frozen']['task']['initial_vin_V'], 0)
        self.assertEqual(d['frozen']['task']['diagnostic_input_A'], 0)
        self.assertNotIn('q0', d['mechanical'])

    def test_task_engine_boundary_and_new_candidate_evaluation(self):
        from bfworld.agentlab.simulation_tasks import load_task,check_candidate,evaluate
        binding=load_task('door-motion-structure-v2');d=contracts.normalize()
        self.assertEqual(d,check_candidate(binding,{'candidate':d,'confirmation':True}))
        binding['task']['frozen']['model']['tx_mA']=.1
        with self.assertRaises(ValueError):check_candidate(binding,{'candidate':d,'confirmation':True})
        binding=load_task('door-motion-structure-v2')
        from bfworld.agentlab.door_system.evaluation import CHECKS
        r={'run_status':'completed','checks':dict.fromkeys(CHECKS,True),'metrics':{'cold_start_reached':True}}
        packet={'capture_id':'real','time_s':1.,'payload_hex':'424644320102030405060708'}
        receive={'transmitted':[packet],'delivered':[packet]}
        e=evaluate(binding,d,r,receive)
        self.assertEqual('satisfied',e['nominal_task_status']);self.assertFalse(e['product_verified']);self.assertFalse(e['design_ranking_eligible'])
        receive['transmitted']=[]
        self.assertEqual('unsatisfied',evaluate(binding,d,r,receive)['nominal_task_status'])
        r['checks']['drive_balance']=False
        self.assertEqual('not_evaluable',evaluate(binding,d,r,receive)['nominal_task_status'])

    def test_old_task_cannot_open_structure_engine(self):
        from bfworld.agentlab.engineering import validate
        p=validate('door-system',{'candidate':{'mechanical':{'closed_dz_mm':0}}})
        self.assertEqual(0,p['candidate']['mechanical']['closed_dz_mm'])
        from bfworld.agentlab.simulation_tasks import load_task,check_candidate
        from bfworld.agentlab.simulation_chain.contracts import ChainError
        with self.assertRaises(ChainError):check_candidate(load_task(),p)

    def test_generated_figures_and_operator_runs_do_not_count_as_agent_80_percent(self):
        from bfworld.agentlab.paper_reproduction import seal,evaluate
        plan={'schema_version':'bf-paper-reproduction-task-v1','source_papers':['paper'],'scope':'simulation only',
              'tasks':[{'id':'cad','tier':'simulation','eligible':True,'source_locator':'Fig1','acceptance':'native readback'}]}
        ph=seal(plan)
        r=evaluate(plan,ph,[{'task_id':'cad','status':'generated','actor':'agent','evidence':[]}])
        self.assertEqual(0,r['autonomous_fraction'])
        with self.assertRaises(ValueError):evaluate(plan,ph,[{'task_id':'cad','status':'passed','actor':'agent','evidence':[]}])
        plan['tasks'][0]['eligible']=False
        with self.assertRaises(ValueError):evaluate(plan,ph,[])

    def test_participant_flags_and_fake_trace_cannot_create_autonomous_pass(self):
        import hashlib
        from bfworld.agentlab.paper_reproduction import seal,evaluate
        plan={'schema_version':'bf-paper-reproduction-task-v1','source_papers':['paper'],'scope':'simulation only',
              'tasks':[{'id':'cad','tier':'simulation','eligible':True,'source_locator':'Fig1','acceptance':'native readback'}]}
        ph=seal(plan)
        with tempfile.TemporaryDirectory() as td:
            evidence=Path(td)/'cad.json';evidence.write_text('{}')
            ev=[{'path':str(evidence),'sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}]
            rec={'task_id':'cad','status':'passed','actor':'agent','independent_check':True,'evidence':ev,
                 'executor_receipt_sha256':'a'*64,'agent_trace_sha256':'b'*64,'human_candidate_edits':0}
            with self.assertRaises(ValueError):evaluate(plan,ph,[rec])
            receipt=Path(td)/'check.json';receipt.write_text(json.dumps({'plan_sha256':ph,'task_id':'cad','status':'passed',
                'actor':'agent','evidence':ev,'validator_id':'independent-cad-readback','human_candidate_edits':0}))
            rec['executor_receipt_sha256']=hashlib.sha256(receipt.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):evaluate(plan,ph,[rec],{rec['executor_receipt_sha256']:receipt})

if __name__ == '__main__': unittest.main()
