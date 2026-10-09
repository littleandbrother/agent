import copy,unittest
from bfworld.agentlab.assembly_contract import contract
from bfworld.agentlab.assembly import validate,ROLES,KINDS

class AssemblyInterfaceChecks(unittest.TestCase):
    def test_actual_role_and_shape_sets(self):
        x=contract();self.assertEqual(set(x['roles']),ROLES);self.assertEqual(set(x['geometry_kinds']),KINDS)
        validate(x['minimal_valid_example'])

    def test_reported_minimum_and_unknown_role(self):
        x=contract();example=copy.deepcopy(x['minimal_valid_example']);example['parts'][0]['geometry']['size_mm'][2]=.03
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_VECTOR_INVALID'):validate(example)
        example['parts'][0]['geometry']['size_mm'][2]=x['geometry_required']['size_mm']['minimum'];validate(example)
        example['parts'][0]['role']='electrode'
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_PART_ROLE'):validate(example)

    def test_claimed_paper_basis_not_a_valid_interface_basis(self):
        x=contract()['minimal_valid_example'];x['parts'][0]['source']['basis']='paper'
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_PART_SOURCE_REQUIRED'):validate(x)

if __name__=='__main__':unittest.main()
