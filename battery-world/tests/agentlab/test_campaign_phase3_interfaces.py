"""Local projection/serialization checks only; no scientific execution."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from bfworld.agentlab.campaign20261019 import phase3_interfaces as p


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/studies/phase3-20261020/interfaces"


class Phase3InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.facts = {"device": {"capacitance_f": 1e-5, "state": "volatile"},
                      "waveform": [[0, 1], [1, 0]], "laws": ["MOCK state rule"],
                      "edge/field~": {"0": [True, 1, 1.0, None, {}, []]},
                      "unicode": "查询 | ` <x>\nline", "missing_measurement": None}
        self.common = {"task": {"id": "MOCK", "deadline_s": 1},
                       "legal_design_space": {"capacitance_f": [1e-6, 1e-4]},
                       "units": {"capacitance_f": "F"}, "assumptions": ["MOCK"]}
        self.average = {"mean_power_w": 1e-4, "total_energy_j": 1e-4}
        self.tools = {"design": {"name": "mock_design", "actions": ["check", "submit"]},
                      "model_response": {"name": "mock_response"},
                      "observation": {"name": "mock_observe", "actions": ["sources", "acquire", "propose", "submit"]}}

    def packet(self, condition="rich-static"):
        return p.project_condition(self.facts, condition, common=self.common,
                                   average_energy=self.average, tool_catalog=self.tools)

    def test_strong_static_and_raw_preserve_every_public_fact(self):
        for condition in ["rich-static", "complete-raw", "executable-response"]:
            with self.subTest(condition=condition):
                packet = self.packet(condition)
                self.assertEqual(p.canonical(packet["facts"]), p.canonical(self.facts))
                packet["facts"]["waveform"].clear()
                self.assertEqual(len(self.facts["waveform"]), 2)

    def test_coarse_and_live_start_match_and_permissions_are_explicit(self):
        coarse, live, executable = [self.packet(c) for c in ["average-energy", "live-e5", "executable-response"]]
        self.assertEqual(coarse["facts"], live["facts"])
        self.assertEqual(coarse["facts"], self.average)
        self.assertEqual(coarse["common"], live["common"])
        self.assertEqual(set(coarse["tools"]), {"design"})
        self.assertEqual(set(live["tools"]), {"design", "observation"})
        self.assertEqual(set(executable["tools"]), {"design", "model_response"})
        self.assertEqual(coarse["budget"], live["budget"])
        self.assertEqual(live["budget"], p.BUDGET)

    def test_equal_information_table_preserves_types_and_empty_containers(self):
        packet = self.packet()
        json_text, table = [p.encode_packet(packet, f) for f in ["json", "table"]]
        self.assertNotEqual(json_text, table)
        self.assertEqual(p.decode_packet(table, "table"), packet)
        self.assertEqual(p.canonical(p.decode_packet(table, "table")), p.canonical(packet))
        receipt = p.validate_equal_information(json_text, table)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["model_format_benefit"], "NOT_TESTED")
        self.assertEqual(receipt["scientific_execution"], "NOT_RUN")

    def test_e4_rejects_changed_fact_tool_budget_or_common_task(self):
        original = self.packet()
        for change in ["facts", "tools", "budget", "common"]:
            bad = copy.deepcopy(original)
            if change == "facts": bad["facts"]["edge/field~"]["0"][0] = 1
            if change == "tools": bad["tools"]["design"]["actions"].append("acquire")
            if change == "budget": bad["budget"]["provider_requests"] += 1
            if change == "common": bad["common"]["task"]["deadline_s"] += 1
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "MISMATCH"):
                p.validate_equal_information(p.encode_packet(original, "json"), p.encode_packet(bad, "table"))

    def test_duplicate_table_rows_and_json_keys_are_rejected(self):
        table = p.encode_packet(self.packet(), "table")
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            p.decode_packet(table + "\n" + table.splitlines()[2], "table")
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            p.decode_packet('{"condition":"rich-static","condition":"average-energy"}', "json")

    def test_table_structure_and_nonfinite_json_are_rejected(self):
        table = p.encode_packet(self.packet(), "table")
        with self.assertRaises(ValueError):
            p.decode_packet(table.replace("| pointer_json |", "| note |", 1), "table")
        with self.assertRaises(ValueError):
            p.decode_packet('{"value":NaN}', "json")
        with self.assertRaises(ValueError):
            p.encode_packet({"a": float("inf")}, "json")

    def test_private_answers_and_missing_tool_roles_are_rejected(self):
        for key in ["expected", "required_fields", "target_expression", "answer_key"]:
            bad = copy.deepcopy(self.facts); bad["nested"] = {key: "MOCK"}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "METADATA"):
                p.project_condition(bad, "rich-static", common=self.common,
                                    average_energy=self.average, tool_catalog=self.tools)
        with self.assertRaisesRegex(ValueError, "TOOL_ROLE_MISSING"):
            p.project_condition(self.facts, "live-e5", common=self.common,
                                average_energy=self.average, tool_catalog={"design": self.tools["design"]})

    def test_changed_physical_input_changes_source_binding(self):
        old = self.packet()["full_public_facts_sha256"]
        self.facts["device"]["capacitance_f"] *= 2
        self.assertNotEqual(self.packet()["full_public_facts_sha256"], old)

    def test_registered_conditions_are_five_plus_separate_e4_pair(self):
        config = json.loads((CONFIG / "conditions.json").read_bytes())
        report = p.validate_conditions(config)
        self.assertEqual((report["conditions"], report["e4_arms"], report["tasks"]), (5, 2, 4))
        self.assertEqual(config["group_budget"]["provider_requests"], 24)
        self.assertEqual(config["group_budget"]["wall_s"], 1200)
        config["conditions"][1]["tool_roles"].append("observation")
        with self.assertRaisesRegex(ValueError, "PERMISSIONS_CHANGED"):
            p.validate_conditions(config)

    def test_derived_case_catalog_binding_and_digital_boundary(self):
        case = json.loads((CONFIG / "derived-case.json").read_bytes())
        source = Path(case["source"]["path"])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), case["source"]["sha256"])
        catalog = json.loads(source.read_bytes())
        parent = next(x for x in catalog["cases"] if x["id"] == "C-lite")
        self.assertEqual(hashlib.sha256(p.canonical(parent)).hexdigest(), case["source"]["case_canonical_sha256"])
        self.assertEqual(case["measured_physical_data"], [])
        self.assertTrue(case["missing_measurements"])
        self.assertEqual(case["status"], "PREREGISTERED_DIGITAL_DERIVATION_NOT_EXECUTED")
        self.assertEqual(case["bf_engine_input"]["device"]["event_latch"], "volatile")
        self.assertEqual(case["task"]["query"]["issued_s"], 2)
        self.assertEqual(case["task"]["receiver"]["deadline_s"], 7)
        self.assertEqual(case["provider_requests"], 0)
        self.assertEqual(case["scientific_executions"], 0)


if __name__ == "__main__":
    unittest.main()
