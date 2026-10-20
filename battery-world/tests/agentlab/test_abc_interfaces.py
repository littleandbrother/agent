"""Negative controls for the B thin adapter. All executors here are fixtures."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = Path(os.environ.get("ABC_SOURCE_ROOT", str(ROOT)))
sys.path.insert(0, str(SOURCE_ROOT/"packages/python/bfworld/src"))
NAME = "bfworld.agentlab.campaign20261019.abc_interfaces"
LOADER = importlib.util.spec_from_file_location(NAME, ROOT/"packages/python/bfworld/src/bfworld/agentlab/campaign20261019/abc_interfaces.py")
adapter = importlib.util.module_from_spec(LOADER)
sys.modules[NAME] = adapter
LOADER.loader.exec_module(adapter)
FREEZE = ROOT/"project/features/BFA-069-abc-interfaces/frozen-families.json"
OUT = ROOT/"docs/research/abc-cycle-20261020/interfaces"


class ABCInterfacesTest(unittest.TestCase):
    def setUp(self):
        OUT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix=".test-", dir=OUT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec = {"frozen_families": str(FREEZE), "frozen_families_sha256": hashlib.sha256(FREEZE.read_bytes()).hexdigest(),
                     "source_root": str(SOURCE_ROOT), "case": "development-cross-source", "condition": "observation_refinement", "stage": "development"}
        adapter.prepare_episode(self.spec, self.root)
        self.handler = adapter.create_handler(self.root, self.spec)
        self.sources = self.handler({"action": "acquire"})["sources"]

    def request(self):
        return json.loads((OUT/"first-legal-request.json").read_text())

    def preflight(self, request):
        return adapter.preflight(request, self.sources, self.handler.context_id)

    def rejected(self, request, code, field):
        result = self.preflight(request)
        self.assertEqual(result["status"], "REJECTED", result)
        self.assertEqual(result["errors"][0]["code"], code, result)
        self.assertEqual(result["errors"][0]["field"], field, result)
        self.assertEqual(result["scientific_executions"], 0)

    def test_cross_source_conditions_are_legal_without_science(self):
        result = self.preflight(self.request())
        self.assertEqual(result["status"], "LEGAL", result)
        self.assertEqual(result["observation"]["type"], "boolean")
        self.assertEqual(set(result["source_bindings"]), {"component_record", "excitation_record"})
        self.assertEqual(result["scientific_executions"], 0)
        self.assertFalse((self.root/"host/executions").exists())

    def test_prefixes_normalize_in_expression_domain_and_consumer(self):
        request = self.request()
        request["expression"] = {"op": "add", "args": [
            {"source_id": "component_record", "field": "/current/capacitance_f", "units": "uF"}, {"constant": 5, "units": "uF"}]}
        request["output_units"] = "uF"
        request["consumer"] = {"input_type": "number", "units": "F", "branches": [{"equals": 15e-6, "decision": "adopt"}]}
        result = self.preflight(request)
        self.assertEqual(result["status"], "LEGAL", result)
        self.assertEqual(result["observation"]["value"], 15)
        self.assertEqual(result["consumer_input"]["value"], 15e-6)

    def test_incompatible_source_unit_has_exact_field(self):
        request = self.request()
        request["expression"] = {"source_id": "component_record", "field": "/current/capacitance_f", "units": "s"}
        self.rejected(request, "INCOMPATIBLE_SOURCE_UNIT", "expression.units")

    def test_operator_unit_error_has_exact_arguments(self):
        request = self.request()
        request["expression"] = {"op": "gt", "args": [
            {"source_id": "component_record", "field": "/current/capacitance_f"}, {"constant": 1, "units": "s"}]}
        self.rejected(request, "INCOMPATIBLE_DIMENSIONS", "expression.args")

    def test_cross_task_source_and_inapplicable_condition_rejected(self):
        self.sources["excitation_record"]["context_id"] = "another-candidate"
        self.rejected(self.request(), "SOURCE_CONTEXT_MISMATCH", "sources.excitation_record")
        self.sources = self.handler({"action": "acquire"})["sources"]
        request = self.request()
        request["domain"][1]["equals"] = 200
        self.rejected(request, "SOURCE_CONDITION_NOT_APPLICABLE", "domain.1.equals")

    def test_boolean_number_requires_explicit_conversion(self):
        request = self.request()
        request["consumer"] = {"input_type": "number", "units": "s", "branches": [{"equals": .002, "decision": "adopt"}]}
        self.rejected(request, "CONSUMER_TYPE_MISMATCH", "consumer.input_type")
        request["consumer"]["conversion"] = {"kind": "boolean_map", "true": 2, "false": 1, "units": "ms"}
        result = self.preflight(request)
        self.assertEqual(result["status"], "LEGAL", result)
        self.assertEqual(result["consumer_input"], {"value": .002, "type": "number", "units": "s"})
        request["consumer"]["branches"][0]["equals"] = True
        self.rejected(request, "BRANCH_TYPE_MISMATCH", "consumer.branches.0.equals")

    def test_payload_and_unit_registry_mutations_rejected(self):
        self.sources["component_record"]["payload"]["current"]["capacitance_f"] = 99e-6
        self.rejected(self.request(), "SOURCE_HASH_MISMATCH", "sources.component_record")
        self.sources = self.handler({"action": "acquire"})["sources"]
        self.sources["component_record"]["field_units"]["/current/capacitance_f"] = "s"
        self.rejected(self.request(), "SOURCE_UNIT_REGISTRY_CHANGED", "sources.component_record")
        path = self.root/"public/sources/component_record.json"
        record = json.loads(path.read_text())
        record["payload"]["current"]["capacitance_f"] = 99e-6
        record["source_sha256"] = adapter.digest(record["payload"])
        path.write_bytes(adapter.canonical(record))
        result = self.handler({"action": "acquire", "source_ids": ["component_record"]})
        self.assertEqual(result["errors"][0]["code"], "SOURCE_RECORD_BINDING_CHANGED")

    def test_fixture_consumption_is_bound_but_cannot_be_scientific_evidence(self):
        calls = []
        def fixture(task):
            calls.append(task)
            return {"input_sha256": adapter.digest(task), "execution_key": "fixture-only-"+adapter.digest(task),
                    "origin": "test-fixture", "execution_fidelity": "fixture", "energy": {},
                    "reference": {"verdicts": {k: "PASS" for k in adapter.SERVICE_KEYS}}}
        handler = adapter.create_handler(self.root, self.spec, executor=fixture)
        handler({"action": "acquire"})
        result = handler({"action": "submit", "request": self.request(), "prediction": "UNKNOWN"})
        self.assertTrue(result["used_observation"])
        frozen = json.loads(FREEZE.read_text())["cases"]["development-cross-source"]
        self.assertEqual(calls, [frozen["intervention"]])
        self.assertEqual(result["executed_input_sha256"], adapter.digest(frozen["intervention"]))
        submission = json.loads((self.root/"host/submission.json").read_text())
        self.assertEqual(submission["consumer"]["consumer_input"]["type"], "boolean")
        handler.execute("retain")
        with self.assertRaisesRegex(adapter.InputError, "FIXTURE_NOT_SCIENTIFIC_EVIDENCE"):
            adapter.independent_check(self.root, self.spec)

    def test_rejection_never_reaches_executor_and_missing_results_stay_unknown(self):
        calls = []
        handler = adapter.create_handler(self.root, self.spec, executor=lambda task: calls.append(task))
        handler({"action": "acquire"})
        request = self.request()
        request["consumer"]["input_type"] = "number"
        result = handler({"action": "submit", "request": request, "prediction": "PASS"})
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(calls, [])
        self.assertEqual(adapter.independent_check(self.root, self.spec)["status"], "NOT_EVALUATED")

    def test_frozen_18_have_equal_information_and_permissions(self):
        bank = json.loads(FREEZE.read_text())
        self.assertEqual(bank["formal_count"], 18)
        self.assertEqual(len({a["episode_id"] for a in bank["formal_attempts"]}), 18)
        self.assertEqual({a["case"] for a in bank["formal_attempts"]}, {"storage-connection", "reset-placement", "package-response"})
        views = {}
        for i, attempt in enumerate(bank["formal_attempts"]):
            spec = {**self.spec, **attempt}
            target = self.root/str(i)
            result = adapter.prepare_episode(spec, target)
            task = json.loads(Path(result["participant_task"]).read_text())
            self.assertEqual(result["participant_input"]["task"], task)
            self.assertEqual(result["participant_input"]["common_instruction"], result["prompt"])
            view = {"task": task, "tool": result["tool"], "sources": {p.name: p.read_bytes() for p in (target/"public/sources").iterdir()}}
            if attempt["case"] in views:
                self.assertEqual(view, views[attempt["case"]])
            views[attempt["case"]] = view
            self.assertNotIn("truth", task)
            self.assertTrue(result["no_scientific_execution"])
        adapter.prepare_episode(self.spec, self.root)  # Idempotent preparation.
        changed = copy.deepcopy(self.spec)
        changed["condition"] = "complete_information"
        with self.assertRaises(ValueError):
            adapter.prepare_episode(changed, self.root)

    def test_five_original_failures_remain_immutable(self):
        preflight = json.loads((OUT/"development-preflight.json").read_text())
        protected = [p for p in preflight["protected_readonly"] if "p3-failure-gateway-" in p["path"]]
        self.assertEqual(len(protected), 5)
        for item in protected:
            path = ROOT/"papers/interface-sufficiency-20261019/final/data/raw"/Path(item["path"]).name
            if not path.exists():
                path = Path(item["path"])  # Read the original sealed B artifact; never copy it.
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])


if __name__ == "__main__":
    unittest.main()
