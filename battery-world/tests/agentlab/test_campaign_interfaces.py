"""Qualification of the frozen public BFA-046 model and evidence boundaries."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from bfworld.agentlab.campaign20261019 import interfaces as i


PROJECT = Path(__file__).resolve().parents[2]
PROTOCOL = PROJECT / "configs/studies/parallel-20261019/interfaces/protocol.json"


class InterfaceQualification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = i.load_protocol(PROTOCOL)
        cls.clamp, cls.memory = cls.protocol["pairs"]
        cls.temp = tempfile.TemporaryDirectory(prefix="bf-interface-unit-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.runtime = Path(cls.temp.name).resolve()

    def test_both_current_pass_with_identical_realized_trajectories(self):
        for pair in self.protocol["pairs"]:
            outputs = [i.evaluate(pair, w, i.changed_design(pair, {})) for w in pair["worlds"]]
            self.assertEqual([x["verdict"] for x in outputs], ["PASS", "PASS"])
            self.assertEqual(outputs[0]["trace"], outputs[1]["trace"])
            self.assertEqual(i.current_facts(pair, outputs[0]), i.current_facts(pair, outputs[1]))

    def test_one_common_legal_patch_diverges(self):
        for pair in self.protocol["pairs"]:
            design = i.changed_design(pair, pair["patch"])
            outputs = [i.evaluate(pair, w, design) for w in pair["worlds"]]
            self.assertEqual([x["verdict"] for x in outputs], ["FAIL", "PASS"])

    def test_clamp_is_unexcited_before_capacitance_change(self):
        for world in self.clamp["worlds"]:
            current = i.analytic_clamp(self.clamp, world, self.clamp["design"])
            self.assertEqual(current["spill_energy_uj"], 0)
            self.assertLess(current["trace"][1]["voltage_v"], world["clamp_v"])
        low, high = [i.analytic_clamp(self.clamp, w, self.clamp["patch"]) for w in self.clamp["worlds"]]
        self.assertAlmostEqual(low["spill_energy_uj"], 22.0)
        self.assertAlmostEqual(high["spill_energy_uj"], 0.0)
        self.assertEqual([low["delivered_energy_uj"], high["delivered_energy_uj"]], [16.0, 30.0])

    def test_reset_alters_memory_without_altering_event_or_tx_window(self):
        task = copy.deepcopy(self.memory["task"])
        responses = [i.event_memory(self.memory, w, self.memory["patch"]) for w in self.memory["worlds"]]
        self.assertEqual(task, self.memory["task"])
        self.assertEqual([r["received"] for r in responses], [[], ["event-1"]])
        self.assertEqual([e["time_s"] for e in responses[0]["trace"]],
                         [e["time_s"] for e in responses[1]["trace"]])

    def test_two_independent_implementations_and_step_refinement(self):
        for pair in self.protocol["pairs"]:
            for world in pair["worlds"]:
                for patch in [{}, pair["patch"]]:
                    design = i.changed_design(pair, patch)
                    primary = i.evaluate(pair, world, design)
                    for step in pair["numeric_steps_s"]:
                        reference = i.evaluate(pair, world, design, reference=True, step_s=step)
                        self.assertLess(i.check_agreement(primary, reference), i.TOL)

    def test_independent_reference_detects_same_verdict_wrong_energy(self):
        expected = i.analytic_clamp(self.clamp, self.clamp["worlds"][0], self.clamp["design"])
        forged = copy.deepcopy(expected)
        forged["spill_energy_uj"] += 1
        with self.assertRaises(i.AuditError):
            i.check_agreement(expected, forged)

    def test_independent_reference_detects_wrong_state_transition(self):
        expected = i.event_memory(self.memory, self.memory["worlds"][0], self.memory["patch"])
        forged = copy.deepcopy(expected)
        forged["trace"][2]["pending"] = "event-1"
        with self.assertRaises(i.AuditError):
            i.check_agreement(expected, forged)

    def test_legal_domain_rejects_requirement_edits_and_nonfinite_values(self):
        for bad in [{"service_energy_uj": 1}, {"capacitance_uf": 0}, {"capacitance_uf": 100},
                    {"capacitance_uf": True}, {"capacitance_uf": math.nan}, {"capacitance_uf": math.inf}]:
            with self.assertRaises(i.DomainError):
                i.changed_design(self.clamp, bad)
        for bad in [[[0, 4]], [[2, 2]], [[2, 3], [3.2, 3.5]], [[2]], "off"]:
            with self.assertRaises(i.DomainError):
                i.changed_design(self.memory, {"power_off_intervals": bad})

    def test_enriched_static_is_sufficient_on_both_public_domain_grids(self):
        labels = set()
        for pair in self.protocol["pairs"]:
            for world in pair["worlds"]:
                current = i.evaluate(pair, world, pair["design"])
                for design in i._domain_designs(pair):
                    facts = i.sufficient_facts(pair, world, current)
                    facts["proposed_change"] = design
                    verdict = i.judge_facts(facts)
                    labels.add(verdict)
                    self.assertEqual(verdict, i.evaluate(pair, world, design, reference=True)["verdict"])
        self.assertEqual(labels, {"PASS", "FAIL"})

    def test_additive_static_negative_control(self):
        control = self.protocol["negative_control"]
        for cost in [10, 30, 40, 45, 50]:
            self.assertEqual(i.static_additive(control, cost), i.numeric_additive(control, cost))
        self.assertEqual(i.static_additive(control, 30), "PASS")
        self.assertEqual(i.static_additive(control, 50), "FAIL")

    def test_ablation_means_missing_information_in_this_encoding(self):
        for pair in self.protocol["pairs"]:
            key = "clamp_v" if pair is self.clamp else "retains_pending"
            for world in pair["worlds"]:
                current = i.evaluate(pair, world, pair["design"])
                facts = i.sufficient_facts(pair, world, current)
                self.assertNotEqual(i.judge_facts(facts), "UNKNOWN")
                del facts[key]
                self.assertEqual(facts, i.current_facts(pair, current))
                self.assertEqual(i.judge_facts(facts), "UNKNOWN")

    def test_equal_information_and_identical_summary_in_both_formats(self):
        for pair in self.protocol["pairs"]:
            for world in pair["worlds"]:
                current = i.evaluate(pair, world, pair["design"])
                for facts in [i.current_facts(pair, current), i.sufficient_facts(pair, world, current)]:
                    outputs = [i.parse_packet(i.format_packet(facts, "same summary", form), form)
                               for form in ["free-text", "structured"]]
                    self.assertEqual(outputs[0], outputs[1])
                    self.assertEqual(outputs[0], (facts, "same summary"))
                    self.assertEqual(i.judge_facts(outputs[0][0]), i.judge_facts(outputs[1][0]))

    def test_duplicate_prose_fact_is_rejected(self):
        raw = b'The shared summary is "x".\nThe fact x has value 1.\nThe fact x has value 2.\n'
        with self.assertRaises(i.AuditError):
            i.parse_packet(raw, "free-text")

    def test_observation_costs_hashes_budget_and_strong_baselines(self):
        pair, world = self.clamp, self.clamp["worlds"][0]
        current = i.evaluate(pair, world, pair["design"])
        base = i.current_facts(pair, current)
        with tempfile.TemporaryDirectory(prefix="test-observe-", dir=self.runtime) as folder:
            catalog = i.observation_sources(Path(folder), pair, world, current)
            for operation in catalog:
                receipt = i.acquire_observation(catalog[operation], base, 100000)
                i.verify_observation_audit(receipt)
                self.assertGreater(receipt["wall_ns"], 0)
                self.assertEqual(receipt["read_bytes"], Path(catalog[operation]["source"]).stat().st_size)
                self.assertEqual(receipt["model_runs"], int(operation == "executable-dynamic"))
                self.assertEqual(i.judge_facts(receipt["facts"]), "UNKNOWN" if operation == "uninformative" else "FAIL")
            self.assertEqual(i.select_observation(catalog, "clamp", 100000)["operation"], "mechanism-spec")
            self.assertIsNone(i.select_observation(catalog, "clamp", 0)["operation"])
            exhausted = i.acquire_observation(catalog["mechanism-spec"], base, 0)
            self.assertEqual(exhausted["status"], "BUDGET_EXHAUSTED")
            self.assertEqual(exhausted["read_bytes"], 0)
            i.verify_observation_audit(exhausted)
            path = Path(catalog["mechanism-spec"]["source"])
            path.write_bytes(path.read_bytes() + b"tampered")
            with self.assertRaises(i.AuditError):
                i.acquire_observation(catalog["mechanism-spec"], base, 100000)

    def test_selector_uses_catalogue_metadata_without_outcome_access(self):
        catalogue = {"large": {"operation": "large", "coverage": ["clamp_v"], "bytes": 200, "declared_model_runs": 0},
                     "small": {"operation": "small", "coverage": ["clamp_v"], "bytes": 20, "declared_model_runs": 0},
                     "irrelevant": {"operation": "irrelevant", "coverage": [], "bytes": 1, "declared_model_runs": 0}}
        self.assertEqual(i.select_observation(catalogue, "clamp", 200)["operation"], "small")
        self.assertEqual(i.select_observation(catalogue, "memory", 200)["status"], "BUDGET_EXHAUSTED")

    def test_new_executable_is_human_specified_and_independently_checked(self):
        with tempfile.TemporaryDirectory(prefix="test-construct-", dir=self.runtime) as folder:
            result = i.construct_observation(Path(folder), self.clamp)
            self.assertEqual(result["qualification_model_runs"], 20)
            self.assertEqual(len(result["fresh_process_executions"]), 2)
            self.assertIn("researcher", result["human_intervention"])
            self.assertEqual([r["result"]["energy_headroom_uj"] for r in result["fresh_process_executions"]], [-14.0, 8.0])
            self.assertEqual(i.digest((Path(folder) / "generated_headroom.py").read_bytes()), result["definition"]["program_sha256"])

    def test_construction_rejects_undeclared_inputs_and_arbitrary_code(self):
        for expression in [{"op": "field", "name": "private_verdict"},
                           {"op": "field", "name": "__import__('os')"},
                           {"op": "execute", "args": []}, {"op": "mul", "args": []}]:
            with self.assertRaises(i.DomainError):
                i.render_expression(expression)

    def test_seal_tamper_is_rejected_before_consuming_results(self):
        with tempfile.TemporaryDirectory(prefix="test-seal-", dir=self.runtime) as folder:
            root = Path(folder)
            (root / "result.json").write_text("{}")
            i.write_json(root / "seal.json", {"files": {"result.json": {"sha256": "0" * 64, "bytes": 2}}})
            with self.assertRaises(i.AuditError):
                i.verify_run(root)

    def test_protocol_preserves_zero_paid_boundary_and_public_exposure(self):
        self.assertEqual(self.protocol["partition"], "public-development")
        self.assertEqual(self.protocol["formal_test"], "NOT_CREATED")
        self.assertEqual(self.protocol["cost_cap"]["paid_model_requests"], 0)
        self.assertEqual(self.protocol["cost_cap"]["native_dispatches"], 0)


if __name__ == "__main__":
    unittest.main()
