import copy
import unittest
from scripts.build_studio import build_payload
from scripts.validate_studio import validate_payload,StudioError
from bfworld.kernel.canonical import canonical_hash

def reseal(p):
    p.pop('content_hash');p['content_hash']=canonical_hash(p)

class StudioProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.payload=build_payload()
    def test_all_source_samples_retained(self):
        report=validate_payload(self.payload)
        self.assertEqual(report['original_samples'],report['projected_samples'])
        self.assertEqual(report['payload_hash'],self.payload['content_hash'])
    def test_missing_peak_sample_rejected(self):
        p=copy.deepcopy(self.payload);rows=p['phases'][0]['rows']
        rows.remove(max(rows,key=lambda r:r['capacitor_voltage_v']));reseal(p)
        with self.assertRaisesRegex(StudioError,'raw samples omitted'):validate_payload(p)
    def test_voltage_linear_fill_cannot_be_mislabeled_as_energy(self):
        p=copy.deepcopy(self.payload)
        p['phases'][0]['rows'][100]['energy_fill']=.5;reseal(p)
        with self.assertRaisesRegex(StudioError,'energy fill misbound'):validate_payload(p)
    def test_unimplemented_receiver_cannot_be_promoted(self):
        p=copy.deepcopy(self.payload);p['components'][-1]['status']='implemented';reseal(p)
        with self.assertRaisesRegex(StudioError,'absent component promoted'):validate_payload(p)
    def test_missing_visual_source_rejected(self):
        p=copy.deepcopy(self.payload);p['visual_bindings']['shaft.rotation']='made_up';reseal(p)
        with self.assertRaisesRegex(StudioError,'visual source missing'):validate_payload(p)
    def test_verdict_cannot_be_replaced_by_view(self):
        # build_payload reuses summary dictionaries; JSON materialization breaks
        # those aliases. Copy through JSON to test the actual portable boundary.
        import json
        p=json.loads(json.dumps(self.payload));p['phases'][0]['summary']['passed']=True;reseal(p)
        with self.assertRaisesRegex(StudioError,'projected verdict changed'):validate_payload(p)
    def test_coupled_sample_tamper_rejected(self):
        p=copy.deepcopy(self.payload);p['coupled']['cases'][0]['run']['rows'][200]['storage_voltage_v']=99;reseal(p)
        with self.assertRaisesRegex(StudioError,'coupled sample changed'):validate_payload(p)
    def test_coupled_fill_not_voltage_fraction(self):
        p=copy.deepcopy(self.payload);p['coupled']['cases'][0]['run']['rows'][100]['energy_fill']=.5;reseal(p)
        with self.assertRaisesRegex(StudioError,'coupled energy misbound'):validate_payload(p)
    def test_rejected_knowledge_cannot_look_promoted(self):
        p=copy.deepcopy(self.payload);p['learning']['reference_qualified_knowledge']=1;reseal(p)
        with self.assertRaisesRegex(StudioError,'knowledge study projection changed'):validate_payload(p)
