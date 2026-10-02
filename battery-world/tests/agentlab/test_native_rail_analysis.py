"""A no-op numerical control must not be labelled a convergence check."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().parents[2]/'scripts/analyze_native_rails.py'
spec=importlib.util.spec_from_file_location('rail_analysis',SCRIPT)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class RefinementContract(unittest.TestCase):
    def test_identical_decks_are_not_refinement_evidence(self):
        deck='.tran 0 4.0 0 5e-05 uic\n'
        result=module.refinement_identity(deck,deck)
        self.assertFalse(result['refinement_admitted'])

    def test_actual_half_step_and_decimal_horizon_are_supported(self):
        result=module.refinement_identity('.tran 0 4.0 0 5e-05 uic', '.tran 0 4.0 0 2.5e-05 uic')
        self.assertTrue(result['refinement_admitted'])

    def test_missing_step_is_not_accepted(self):
        result=module.refinement_identity('.tran 0 4', '.tran 0 4')
        self.assertFalse(result['refinement_admitted'])


if __name__=='__main__':unittest.main()
