"""Sourcing negatives: a catalogue identity is neither equivalence nor release."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.door_case.procurement import build_bom, module_pads


class ProcurementTest(unittest.TestCase):
    def test_module_pin_identity_and_no_corner_pad_collision(self):
        pads=module_pads()
        self.assertEqual({str(i) for i in range(44)},{p['num'] for p in pads})
        # Independent axis-aligned copper clearance for rotated corner pads.
        corners=[(15,16),(27,28)]
        for i,j in corners:
            a,b=pads[i],pads[j]
            dx=max(0,abs(a['centerX']-b['centerX'])-(a['defaultPad']['width']+b['defaultPad']['width'])/2)*.0254
            dy=max(0,abs(a['centerY']-b['centerY'])-(a['defaultPad']['height']+b['defaultPad']['height'])/2)*.0254
            self.assertGreater((dx*dx+dy*dy)**.5,.1651)

    def test_stock_and_mpn_fail_closed_and_never_grant_manufacturing_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'electronics';(out/'pcb').mkdir(parents=True)
            stock=root/'procurement/20261003';stock.mkdir(parents=True)
            parts=[dict(ref='J1',lcsc='C124375',attrs={'Manufacturer Part':'B-2100S02P-A110'})]
            (out/'pcb/board.json').write_text(json.dumps(dict(design='fixture',components=parts)))
            item=dict(componentCode='C124375',componentModelEn='B-2100S02P-A110',stockCount=0,
                      componentBrandEn='fixture',componentSpecificationEn='2.54 mm',describe='fixture',lcscGoodsUrl='https://www.lcsc.com/fixture')
            def write():
                (stock/'C124375-jlc.json').write_text(json.dumps(dict(checked_at='fixture',response=[item])))
            write()
            with self.assertRaisesRegex(ValueError,'INSUFFICIENT_STOCK'):build_bom(root,out)
            item.update(stockCount=3,componentModelEn='different part');write()
            with self.assertRaisesRegex(ValueError,'MPN_MISMATCH'):build_bom(root,out)
            item['componentModelEn']='B-2100S02P-A110';write()
            receipt=build_bom(root,out)
            self.assertTrue(receipt['catalogue_available_for_one_board'])
            self.assertFalse(receipt['manufacturing_released'])
            self.assertFalse(receipt['assembly_qualified']);self.assertFalse(receipt['purchase_placed'])
