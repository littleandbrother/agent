"""Independent read-only tests. Original task bytes are never modified."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('independent_method_contract', ROOT/'changed/src/method_contract.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
FIELDS = ('architecture_changes','mechanical_changes','circuit_changes','firmware_changes','cross_domain_changes')

def parameter_task():
    return {'allowed_design':{'all_main_arms':['A','B'],'candidate_components':['bounded_numeric_parameters'], 'permissions_per_arm':{
        name:{**{field:False for field in FIELDS},'same_tool_access':True} for name in ['A','B']}}}

class CapabilityGateIndependentTest(unittest.TestCase):
    def test_canonical_frozen_tasks_remain_blocked(self):
        tasks_path = ROOT.parent/'inputs/integration/authority-inputs/authoritative-world/contracts/tasks-v2.json'
        payload = json.loads(tasks_path.read_text())
        for task in payload['tasks']:
            with self.subTest(task=task['task_id']):
                result=module.capability_admission(task)
                self.assertFalse(result['capability_compatible'])
                self.assertFalse(result['execution_authorized'])
                self.assertFalse(result['scientific_qualified'])
                self.assertIn('PROVIDER_ARCHITECTURE_NOT_IMPLEMENTED',result['blockers'])
                self.assertIn('PROVIDER_CANDIDATE_SOURCES_NOT_IMPLEMENTED',result['blockers'])
    def test_restricted_baseline_mismatch_is_rejected(self):
        t=parameter_task();t['allowed_design']['permissions_per_arm']['B']['architecture_changes']=True
        with self.assertRaisesRegex(ValueError,'TASK_ARM_FREEDOM_MISMATCH'):
            module.capability_admission(t)
    def test_missing_and_malformed_permissions_are_rejected(self):
        for t in [{},{'allowed_design':{}},{'allowed_design':{'permissions_per_arm':{}}}]:
            with self.subTest(t=t), self.assertRaises(ValueError):module.capability_admission(t)
        t=parameter_task();t['allowed_design']['permissions_per_arm']['A']['architecture_changes']='false'
        with self.assertRaises(ValueError):module.capability_admission(t)
    def test_artifact_backed_known_components_require_source_support(self):
        for component in ['beam_and_piezo_geometry','magnet_geometry_and_mount','passive_mechanical_release','rectifier_and_power_topology','firmware_policy_and_payload']:
            with self.subTest(component=component):
                t=parameter_task();t['allowed_design']['candidate_components']=[component]
                self.assertFalse(module.capability_admission(t)['capability_compatible'])
    def test_real_storage_components_require_source_support(self):
        t=parameter_task();t['allowed_design']['candidate_components']=['real_storage_components']
        self.assertFalse(module.capability_admission(t)['capability_compatible'])
    def test_unknown_component_does_not_silently_pass(self):
        t=parameter_task();t['allowed_design']['candidate_components']=['unrecognized_firmware_implementation']
        try: result=module.capability_admission(t)
        except ValueError:return
        self.assertFalse(result['capability_compatible'])
    def test_all_declared_arms_need_permissions(self):
        t=parameter_task();del t['allowed_design']['permissions_per_arm']['B']
        with self.assertRaises(ValueError):module.capability_admission(t)

if __name__=='__main__':unittest.main()
