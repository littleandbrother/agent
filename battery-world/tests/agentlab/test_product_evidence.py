import copy
import unittest
from bfworld.agentlab.product_evidence import check_interfaces, source_identity
from bfworld.agentlab.freerouting import route_rules


class ProductEvidenceTests(unittest.TestCase):
    def fixture(self):
        pins={'U2':{'6':'BUTTON','14':'LED_L_DRV','15':'LED_R_DRV','23':'SWDIO','24':'SWCLK','2':''}}
        p={'parts':[{'id':'main_pcb','geometry':{'size_mm':[50,24,1.6],'center_mm':[0,0,24]}},
                    {'id':'pcb_U2','geometry':{'center_mm':[0,0,25],'rotation_deg':[0,0,0]}}],
           'energy':{'pulse_ms':100,'supply_v':3}}
        c=[{'ref':'U2','x':25/.0254,'y':12/.0254,'rotation':0}]
        return p,c,pins

    def test_real_contract_requires_matching_pins_and_placements(self):
        p,c,pins=self.fixture();expected=copy.deepcopy(pins);expected['U2']['2']=None
        self.assertEqual(1,check_interfaces(p,c,pins,expected)['component_count'])
        p['parts'][1]['geometry']['center_mm'][0]=1
        with self.assertRaisesRegex(ValueError,'PLACEMENT_MISMATCH'):check_interfaces(p,c,pins,expected)

    def test_correct_render_does_not_hide_firmware_or_net_mismatch(self):
        p,c,pins=self.fixture();expected=copy.deepcopy(pins);pins['U2']['14']='wrong'
        with self.assertRaisesRegex(ValueError,'PIN_MAP_MISMATCH'):check_interfaces(p,c,pins,expected)
        with self.assertRaisesRegex(ValueError,'FIRMWARE_PIN_CONFLICT'):check_interfaces(p,c,pins,pins)
        pins['U2']['14']='LED_L_DRV';p['energy']['pulse_ms']=400
        with self.assertRaisesRegex(ValueError,'SERVICE_CONFLICT'):check_interfaces(p,c,pins,pins)

    def test_export_timestamp_is_not_physical_identity(self):
        header='{"type":"DOCHEAD"}||{"version":1}|\n'
        body='{"type":"LINE","id":"a"}||{"width":6.1}|'
        self.assertEqual(source_identity(header+body),source_identity(header.replace('1','2')+body))
        self.assertNotEqual(source_identity(header+body),source_identity(header+body.replace('6.1','10')))

    def test_routing_clearance_never_reduced(self):
        s='(layer TopLayer)(layer BottomLayer)(rule(width 10))(rule(clear 8))(rule(clearance 4.02))'
        r=route_rules(s,6.1,6.5)
        self.assertIn('(width 6.1)',r);self.assertIn('(clear 8.0)',r);self.assertIn('(clearance 6.5)',r)
        for width,clearance in [(None,7),(6,float('nan')),(3,7),(6,4)]:
            with self.assertRaisesRegex(ValueError,'RULE_RANGE'):route_rules(s,width,clearance)


if __name__=='__main__':unittest.main()
