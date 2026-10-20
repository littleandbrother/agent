"""New phase3 contract controls only; no provider or scientific execution."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from bfworld.agentlab.campaign20261019 import phase3_methods as m


ROOT = Path(__file__).resolve().parents[2]


class Phase3MethodContractTests(unittest.TestCase):
    def test_changed_coupled_device_never_uses_old_trajectory_as_new_service(self):
        rows = m.comparison_registry({"changed_artifact": "D", "changed_fields": ["timing"]})
        self.assertEqual(len(rows), 4)
        self.assertTrue(rows[0]["control_only"])
        self.assertFalse(rows[0]["eligible_as_changed_input_service"])
        for row in rows[1:]:
            self.assertEqual(row["response_scope"], "full-feedback-response")
            self.assertEqual(row["required_scope"], "full-feedback-response")

    def test_global_method_restarts_decisions_even_with_valid_physical_cache(self):
        for row in m.comparison_registry({"changed_artifact": "H"}):
            self.assertEqual(row["agent_decisions"], "fresh-task-entry")
            self.assertEqual(row["required_scope"], "task-entry")
        self.assertEqual(m.impact_scope({}), "no-execution")

    def test_mixed_unknown_and_scientific_semantic_edits_fail_closed(self):
        for change in [{"changed_artifact": "H", "capacitance_f": 1},
                       {"changed_artifact": "D", "evaluator": "changed"},
                       {"changed_artifact": "G"}, {"unclassified": True}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.comparison_registry(change)

    def test_proposal_subcap_is_inside_total_budget_for_both_methods(self):
        for condition in ("ordinary_reflection", "proposed_method"):
            result = m.remaining_budget(condition, total_requests=8, total_wall_s=400,
                                        proposal_requests=8, proposal_wall_s=400)
            self.assertEqual(result["remaining_group_requests"], 16)
            self.assertEqual(result["remaining_group_wall_s"], 800)
            self.assertEqual(result["remaining_proposal_requests"], 0)

    def test_acquisition_failures_and_confirmation_cannot_reset_total(self):
        result = m.remaining_budget("proposed_method", total_requests=24, total_wall_s=1200,
                                    proposal_requests=8, proposal_wall_s=400, distinct_D=2)
        self.assertEqual(result["remaining_group_requests"], 0)
        self.assertEqual(result["remaining_group_wall_s"], 0)
        self.assertEqual(result["remaining_distinct_D"], 0)
        for values in [dict(total_requests=25, total_wall_s=1200),
                       dict(total_requests=24, total_wall_s=1201),
                       dict(total_requests=8, total_wall_s=400, proposal_requests=9),
                       dict(total_requests=8, total_wall_s=400, proposal_wall_s=401),
                       dict(total_requests=1, total_wall_s=1, distinct_D=3)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                m.remaining_budget("proposed_method", **values)

    def test_fixed_method_has_no_proposal_and_subtotals_cannot_exceed_totals(self):
        for condition, values in [
            ("fixed_h", dict(total_requests=1, total_wall_s=1, proposal_requests=1)),
            ("fixed_h", dict(total_requests=1, total_wall_s=1, proposal_wall_s=1)),
            ("ordinary_reflection", dict(total_requests=1, total_wall_s=1, proposal_requests=2)),
            ("proposed_method", dict(total_requests=1, total_wall_s=1, proposal_wall_s=2))]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                m.remaining_budget(condition, **values)

    def test_unknown_nonfinite_boolean_or_negative_accounting_is_not_zero(self):
        for values in [dict(total_requests=None, total_wall_s=0),
                       dict(total_requests=True, total_wall_s=0),
                       dict(total_requests=-1, total_wall_s=0),
                       dict(total_requests=0, total_wall_s=float("nan")),
                       dict(total_requests=0, total_wall_s=float("inf")),
                       dict(total_requests=0, total_wall_s=True)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                m.remaining_budget("fixed_h", **values)

    def test_conditions_and_pure_budget_share_caps_and_only_process_differs(self):
        config = json.loads((ROOT / "configs/studies/phase3-20261020/methods/conditions.json").read_text())
        self.assertEqual({c["id"] for c in config["conditions"]}, set(m.CONDITIONS))
        for condition in config["conditions"]:
            initial = m.remaining_budget(condition["id"], total_requests=0, total_wall_s=0)
            self.assertEqual(condition["group_total_requests_cap"], initial["remaining_group_requests"])
            self.assertEqual(condition["group_total_wall_seconds_cap"], initial["remaining_group_wall_s"])
            self.assertEqual(condition["proposal_requests_cap"], initial["remaining_proposal_requests"])
            self.assertEqual(condition["proposal_wall_seconds_cap"], initial["remaining_proposal_wall_s"])
            text = str(condition["proposal_instruction"])
            self.assertNotIn("capacitance_f=", text)
            self.assertNotIn("tx_not_before_s=", text)

    def test_cli_is_relocatable_and_runs_only_new_contract(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/campaign_phase3_methods.py"),
                                 "budget", "--condition", "ordinary_reflection", "--usage-json",
                                 '{"total_requests":8,"total_wall_s":400,"proposal_requests":8,"proposal_wall_s":400}'],
                                cwd="/", capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["remaining_group_requests"], 16)


if __name__ == "__main__":
    unittest.main()
