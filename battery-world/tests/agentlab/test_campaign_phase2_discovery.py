"""Pure MOCK contract checks; none is an E5 result or physical execution."""
import copy
import json
import unittest

from bfworld.agentlab.campaign20261019 import phase2_discovery as d


def selection(**updates):
    value = {"hypothesis": "MOCK selection fixture, not an Agent discovery",
             "mode": "selection", "source_id": "mock-record", "field": "/flag",
             "units": "1", "domain": {"constraints": []}}
    value.update(updates)
    return value


def construction(ast=None, **updates):
    value = selection(mode="construction", units="J")
    del value["field"]
    value["ast"] = ast or {"op": "add", "args": [
        {"field": "/alpha", "units": "J"}, {"field": "/beta", "units": "J"}]}
    value.update(updates)
    return value


class DiscoveryContract(unittest.TestCase):
    def test_modes_and_raw_json_compatibility(self):
        source = {"flag": True, "alpha": 2.0, "beta": 3.0}
        for proposal, mode, value, kind in [
            (selection(), "selection", True, "boolean"),
            (construction(), "construction", 5.0, "number"),
        ]:
            with self.subTest(mode=mode):
                safe = d.validate_proposal(proposal)
                result = d.evaluate_proposal(safe, source)
                self.assertEqual((result["mode"], result["value"], result["type"]), (mode, value, kind))
                self.assertEqual(result["status"], "OBSERVED")
                self.assertEqual(result["unit_status"], "DECLARED_ONLY")
                self.assertEqual(result["qualification"], "EXTERNAL_REQUIRED")
                self.assertEqual(result["real_consumer"], "NOT_EXECUTED")
                self.assertEqual(result["discovery_claim"], "NOT_ESTABLISHED")
                self.assertEqual(result["evaluation"]["scientific_executions"], 0)
                self.assertEqual(result["evaluation"]["provider_requests"], 0)

    def test_construction_cannot_be_field_or_constant_only(self):
        for ast in [{"field": "/alpha", "units": "J"}, {"constant": 1, "units": "J"}]:
            with self.subTest(ast=ast), self.assertRaisesRegex(ValueError, "CONSTRUCTION_MUST_USE_SOURCE_AND_OPERATOR"):
                d.validate_proposal(construction(ast))
        mixed = construction(); mixed["field"] = "/alpha"
        with self.assertRaises(ValueError):
            d.validate_proposal(mixed)

    def test_code_and_authority_injection_rejected(self):
        for op in ["python", "eval", "__import__", "open"]:
            bad = construction(); bad["ast"]["op"] = op
            with self.subTest(op=op), self.assertRaises(ValueError):
                d.validate_proposal(bad)
        for key in ["qualification", "consumer", "expected", "actor", "costs"]:
            bad = selection(); bad[key] = "PASS"
            with self.subTest(key=key), self.assertRaises(ValueError):
                d.validate_proposal(bad)

    def test_ast_depth_and_node_caps(self):
        node = {"field": "/alpha", "units": "J"}
        for _ in range(8):
            node = {"op": "neg", "args": [node]}
        with self.assertRaisesRegex(ValueError, "AST_RESOURCE_LIMIT"):
            d.validate_proposal(construction(node))
        node = {"field": "/alpha", "units": "J"}
        for _ in range(6):
            node = {"op": "add", "args": [copy.deepcopy(node), copy.deepcopy(node)]}
        with self.assertRaisesRegex(ValueError, "AST_RESOURCE_LIMIT"):
            d.validate_proposal(construction(node))

    def test_invalid_dimensions_and_nonfinite_values(self):
        bad = construction(); bad["ast"]["args"][1]["units"] = "s"
        with self.assertRaisesRegex(ValueError, "INCOMPATIBLE_DIMENSIONS"):
            d.validate_proposal(bad)
        with self.assertRaisesRegex(ValueError, "OUTPUT_UNIT_MISMATCH"):
            d.validate_proposal(construction(units="s"))
        for value in [float("nan"), float("inf"), 10 ** 1000]:
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                d.evaluate_proposal(selection(field="/alpha"), {"alpha": value})

    def test_independent_unit_mapping_and_conversion(self):
        result = d.evaluate_proposal(selection(field="/alpha", units="J"),
                                     {"alpha": 2500}, field_units={"/alpha": "mJ"})
        self.assertEqual(result["value"], 2.5)
        self.assertEqual(result["unit_status"], "CHECKED_AGAINST_SUPPLIED_MAPPING")
        self.assertEqual(result["qualification"], "EXTERNAL_REQUIRED")
        bad = d.evaluate_proposal(selection(field="/alpha", units="J"),
                                  {"alpha": 2}, field_units={"/alpha": "s"})
        self.assertEqual((bad["status"], bad["reason"]), ("UNKNOWN", "SOURCE_UNIT_MISMATCH"))

    def test_missing_null_uninformative_and_out_of_domain(self):
        for source in [{}, {"flag": None}]:
            with self.subTest(source=source):
                result = d.evaluate_proposal(selection(), source)
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertIsNone(result["value"])
        spec = selection(field="/alpha", units="J", domain={"constraints": [
            {"field": "/alpha", "lower": 0, "upper": 1, "units": "J"}]})
        result = d.evaluate_proposal(spec, {"alpha": 2})
        self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "OUT_OF_DOMAIN"))

    def test_numeric_domain_failure_is_unknown(self):
        ast = {"op": "div", "args": [{"field": "/alpha", "units": "J"},
                                      {"constant": 0, "units": "1"}]}
        result = d.evaluate_proposal(construction(ast), {"alpha": 1})
        self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "DIVISION_BY_ZERO"))
        ast = {"op": "sqrt", "args": [{"field": "/alpha", "units": "J^2"}]}
        result = d.evaluate_proposal(construction(ast), {"alpha": -1})
        self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "SQRT_DOMAIN"))

    def test_vector_reduction_and_scalar_output_boundary(self):
        ast = {"op": "mean", "args": [{"field": "/series", "units": "J"}]}
        result = d.evaluate_proposal(construction(ast), {"series": [1, 2, 3]})
        self.assertEqual(result["value"], 2)
        result = d.evaluate_proposal(selection(field="/series", units="J"), {"series": [1, 2]})
        self.assertEqual(result["reason"], "SCALAR_CONSUMER_OUTPUT_REQUIRED")
        with self.assertRaisesRegex(ValueError, "VECTOR_RESOURCE_LIMIT"):
            d.evaluate_proposal(selection(), {"flag": [0] * (d.MAX_VECTOR + 1)})

    def test_typed_equality_and_json_pointer(self):
        ast = {"op": "eq", "args": [{"field": "/flag", "units": "1"},
                                     {"constant": 1, "units": "1"}]}
        result = d.evaluate_proposal(construction(ast, units="1"), {"flag": True})
        self.assertEqual(result["reason"], "STRICT_TYPE_MISMATCH")
        result = d.evaluate_proposal(selection(field="/a~1b/~0/0"), {"a/b": {"~": ["item"]}})
        self.assertEqual((result["value"], result["type"]), ("item", "string"))

    def test_source_labels_and_malformed_spec_rejected(self):
        with self.assertRaisesRegex(ValueError, "EVALUATOR_METADATA_IN_SOURCE"):
            d.evaluate_proposal(selection(), {"flag": True, "nested": {"expected_verdict": "PASS"}})
        for spec in [selection(mode=[]), selection(field="../../secret"), selection(units="unsupported")]:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                d.validate_proposal(spec)

    def test_tampered_acquisition_and_unknown_costs_retained(self):
        raw = b'{"flag": true}'
        costs = {"wall_s": 1.2, "bytes_read": len(raw), "model_requests": 1,
                 "scientific_executions": 0, "billing_status": "UNKNOWN", "cost_usd": None}
        bound = d.bind_acquisition("mock-record", raw, d.digest(raw), costs)
        self.assertEqual(bound["status"], "OBSERVED")
        self.assertNotEqual(bound["source_bytes_sha256"], bound["payload_sha256"])
        tampered = d.bind_acquisition("mock-record", raw + b" ", d.digest(raw), costs)
        self.assertEqual((tampered["status"], tampered["reason"]), ("REJECTED", "SOURCE_HASH_MISMATCH"))
        for row in [bound, tampered, d.bind_acquisition("mock-record", None, d.digest(raw), costs, status="FAILED")]:
            self.assertEqual(row["costs"], costs)
            self.assertEqual(row["qualification"], "EXTERNAL_REQUIRED")
            self.assertEqual(row["consumer"], "NOT_EXECUTED")

    def test_host_request_and_bounded_typed_policy(self):
        design = {"capacitance_f": 0.001, "tx_not_before_s": 0}
        policy = [{"equals": True, "design": design}, {"equals": 1, "design": design}]
        request = {"action": "submit", "spec": selection(), "policy": policy}
        self.assertEqual(len(d.validate_request(request)["policy"]), 2)
        for bad in [policy * 2, [policy[0], policy[0]]]:
            with self.assertRaises(ValueError):
                d.validate_policy(bad)
        with self.assertRaisesRegex(ValueError, "DESIGN_OUT_OF_DOMAIN"):
            d.validate_policy(policy, legal_domain={"capacitance_f": [0.002, 0.003], "tx_not_before_s": [0, 1]})
        with self.assertRaises(ValueError):
            d.validate_request({"action": "acquire", "source_id": "mock-record", "qualification": "PASS"})
        with self.assertRaises(ValueError):
            d.validate_request({"action": []})

    def test_initial_schema_is_generic_and_bounded(self):
        schema = d.tool_schema()
        self.assertEqual(schema["properties"]["action"]["enum"], ["sources", "acquire", "propose", "submit"])
        self.assertEqual(schema["properties"]["policy"]["maxItems"], 3)
        serialized = json.dumps(schema)
        for forbidden in ["examples", "default", "target_relation", "expected_verdict", "/alpha", "/beta", "\\Z"]:
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(d.validate_request({"action": "sources"}), {"action": "sources"})


if __name__ == "__main__":
    unittest.main()
