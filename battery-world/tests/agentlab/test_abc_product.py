"""Guard the component/source boundary without running scientific trials."""
import copy
import json
from pathlib import Path
import unittest

from bfworld.agentlab.campaign20261019 import abc_product as product

APP = Path(__file__).resolve().parents[2]


class ProductBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((APP/'configs/studies/phase1-20261020/ar/service-contract.v1.json').read_text())['tasks']['ar-cold']
        self.catalogue = json.loads((APP/'configs/studies/abc-20261020/product/source-catalogue.json').read_text())
        # A guard-test input only, never supplied as the BF design or a result.
        self.candidate = {'schema_version': product.SCHEMA, 'concept_id': 'guard-fixture',
            'storage': {'part': 'GA209F', 'modules': 1, 'connection': 'single'},
            'controller': {'part': 'MSP430FR2433', 'mode': 'LPM3_XT1', 'rail_v': 2},
            'sensor': {'part': 'TMP117', 'mode': 'one_shot_shutdown', 'averaging': 1},
            'power_management': {'part': 'BQ25570', 'mode': 'full_operating'},
            'device': {'off_v': 2.3, 'ready_v': 2.4},
            'program': {'schema_version': 'bf-ar-rank-program-v1', 'sample_period_s': 60, 'ack_spacing_s': 1,
                        'retry_s': 60, 'rank': {'field': 'seq'}},
            'rationale': 'Guard fixture: no physical or scientific acceptance claim.'}

    def test_fixed_environment_activity_and_service_survive_materialization(self):
        before = copy.deepcopy(self.task)
        result = product.materialize(self.task, self.candidate, self.catalogue)
        self.assertEqual(self.task, before)
        self.assertEqual({k:v for k,v in result.items() if k not in ('device','program','model_id','implementation_profile')},
                         {k:v for k,v in before.items() if k not in ('device','program','model_id','implementation_profile')})
        for key in ('cap_initial_voltage_v','boot_storage_j','sense_storage_j','write_storage_j','tx_storage_j','clock_ppm','nvm_persistent'):
            self.assertEqual(result['device'][key], before['device'][key])
        self.assertTrue(result['implementation_profile']['source_domain_gaps'])

    def test_arbitrary_power_free_rtc_and_non_fifo_rejected(self):
        for change in ('power', 'mode', 'rail', 'fifo'):
            candidate = copy.deepcopy(self.candidate)
            if change == 'power': candidate['device']['sleep_power_w'] = 1e-12
            if change == 'mode': candidate['controller']['mode'] = 'LPM4.5_NO_RTC'
            if change == 'rail': candidate['controller']['rail_v'] = 3
            if change == 'fifo': candidate['program']['rank'] = {'const': 0}
            with self.assertRaises(ValueError): product.materialize(self.task, candidate, self.catalogue)

    def test_cold_exclusion_does_not_depend_on_favourable_current_projection(self):
        a = product.necessary_bounds({'ar-cold': self.task}, self.candidate, self.catalogue)['ar-cold']
        catalogue = copy.deepcopy(self.catalogue)
        catalogue['parts']['GA209F']['leakage_typ_a_at_test_point'] = 0
        b = product.necessary_bounds({'ar-cold': self.task}, self.candidate, catalogue)['ar-cold']
        self.assertTrue(a['cold_excluded_even_with_perfect_conversion_and_no_load'])
        self.assertEqual(a['minimum_charge_to_ready_j'], b['minimum_charge_to_ready_j'])
        self.assertEqual(a['source_port_energy_before_first_receive_j'], b['source_port_energy_before_first_receive_j'])


if __name__ == '__main__': unittest.main()
