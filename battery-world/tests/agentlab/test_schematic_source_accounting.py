import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

path=Path(__file__).resolve().parents[2]/'scripts/door_case/audit_schematic_mapping.py'
spec=importlib.util.spec_from_file_location('schematic_accounting',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class SchematicAccounting(unittest.TestCase):
    def test_native_pass_cannot_hide_missing_elements_or_wrong_rail(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.cir';native=root/'native.enet';mapping=root/'map.json'
            source.write_text('* fixture\n.func foo(x) {x}\nCcap vin cap 1u\nCvin2 vin2 0 4.7u\nXU 0 cap vin vin2 PMIC\n.model test D(Is=1e-12)\n')
            native.write_text(json.dumps({'components':{'1':{'props':{'Designator':'C1'},'pinInfoMap':{'1':{'net':'VIN'},'2':{'net':'VIN'}}}}}))
            result=module.audit(source,native)
            self.assertEqual(['Ccap','Cvin2','XU'],result['unmapped'])
            data={'source_sha256':module.sha(source),'native_sha256':module.sha(native),
                  'net_aliases':{'vin':'VIN','cap':'CAP'},'instances':{'Ccap':{'ref':'C1','pins':['1','2']}},'exclusions':{}}
            mapping.write_text(json.dumps(data));result=module.audit(source,native,mapping)
            self.assertIn('connectivity_mismatch:Ccap',result['errors'])
            self.assertIn('XU',result['unmapped']);self.assertFalse(result['engineering_passed'])
            data['exclusions']['XU']='Declared behavioral model: physical realization still requires independent review.'
            data['native_sha256']='wrong';mapping.write_text(json.dumps(data));result=module.audit(source,native,mapping)
            self.assertIn('native_sha256_mismatch',result['errors'])
            self.assertFalse(result['declared_exclusions'][0]['independently_accepted'])


if __name__=='__main__':unittest.main()
