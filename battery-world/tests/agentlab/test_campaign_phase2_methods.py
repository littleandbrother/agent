"""MOCK structural controls only: no provider or BF scientific execution."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator

from bfworld.agentlab.campaign20261019 import phase2_methods as m

ROOT = Path(__file__).resolve().parents[2]


def proposal():
    # Deliberately outside BF: never supply this fixture as a real H-prime.
    return {"changed_artifact": "H", "hypothesis": "MOCK: a toy spelling policy may expose an invalid word.",
            "falsifier": "MOCK: the revised toy controller never consumes the policy.",
            "method_text": "MOCK: compare a toy word to its declared alphabet before spelling it.",
            "changes": [{"artifact": "H", "component": "global_prompt"}],
            "evidence_refs": ["MOCK:toy-failure"]}


def registry(kind="MOCK"):
    method = m.validate_method(proposal())
    shared = {field: m.digest(["MOCK", field]) for field in m.PARITY_FIELDS}
    shared.update(externally_verified=True, evidence_kind=kind, usage_status="SETTLED",
                  costs_complete=True, start_stage="task-entry", initial_decision_messages=0,
                  actual_tool_inputs_bound=True, independent_complete_service=True,
                  feedback_scope_verified=True, service_status="PASS")
    rows = {"proposal": {"externally_verified": True, "evidence_kind": kind,
                        "proposal_sha256": m.digest(method), "semantic_artifact": "H",
                        "method_author": "participant-model", "source_scope": "public-development",
                        "usage_status": "SETTLED", "costs_complete": True,
                        "provider_request_ids": ["MOCK:proposal-request"],
                        "decision_trace_sha256": m.digest("MOCK:proposal-trace")}}
    for role in ("h0", "hprime"):
        row = {**shared, "episode_id": "MOCK:" + role, "owner": "MOCK:owner:" + role,
               "context_id": "MOCK:context:" + role, "decision_trace_sha256": m.digest(["MOCK", role]),
               "provider_request_ids": ["MOCK:request:" + role],
               "execution_input_sha256": m.digest(["MOCK", "input", role]),
               "evaluation_input_sha256": m.digest(["MOCK", "input", role]),
               "method_sha256": method["method_sha256"] if role == "hprime" else m.digest("MOCK:H0")}
        rows[role] = row
    return rows


def gate(rows, value=None):
    return m.confirmation_gate(value or proposal(), proposal_receipt_id="proposal",
                              h0_receipt_id="h0", hprime_receipt_id="hprime",
                              resolve_receipt=lambda kind, identity: copy.deepcopy(rows[identity]))


class Phase2MethodProposalTests(unittest.TestCase):
    def test_four_required_fields_and_no_self_acceptance_in_schema(self):
        schema = m.tool_schema()
        required = schema["oneOf"][0]["required"]
        self.assertEqual(set(required), {"hypothesis", "falsifier", "method_text", "changed_artifact"})
        self.assertFalse(schema["oneOf"][0]["additionalProperties"])
        self.assertNotIn("acceptance", schema["oneOf"][0]["properties"])

    def test_tool_json_schema_accepts_only_declared_input_branches(self):
        validator = Draft202012Validator(m.tool_schema())
        validator.check_schema(m.tool_schema())
        for raw in (proposal(), {}, {"decision": "no-update", "reason": "MOCK: abstain"}):
            with self.subTest(raw=raw):self.assertEqual(list(validator.iter_errors(raw)), [])
        for raw in ({**proposal(), "changed_artifact": "D"}, {**proposal(), "qualification": "PASS"}):
            self.assertTrue(list(validator.iter_errors(raw)))

    def test_normalization_is_detached_and_carries_no_acceptance(self):
        raw = proposal(); result = m.validate_method(raw)
        self.assertEqual(result["impact_scope"], "task-entry")
        result["changes"][0]["component"] = "skills"
        self.assertEqual(raw["changes"][0]["component"], "global_prompt")
        self.assertIn("REQUIRES_EXTERNAL", result["status"])

    def test_required_nonempty_hypothesis_falsifier_and_method(self):
        for field in ("hypothesis", "falsifier", "method_text", "changed_artifact"):
            raw = proposal(); del raw[field]
            with self.subTest(field=field), self.assertRaises(ValueError):m.validate_method(raw)
        for value in (None, "", "  ", "\x00", 1):
            raw = {**proposal(), "falsifier": value}
            with self.subTest(value=value), self.assertRaises(ValueError):m.validate_method(raw)

    def test_d_or_g_declared_as_method_rejected(self):
        for artifact in ("D", "G"):
            with self.subTest(artifact=artifact), self.assertRaisesRegex(ValueError, "REQUIRES_H"):
                m.validate_method({**proposal(), "changed_artifact": artifact})

    def test_d_only_text_and_disguised_device_patch_rejected(self):
        for text in ('{"capacitance_f":0.00001}', "capacitance_f=1e-5; tx_not_before_s=0.004"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "DEVICE_ONLY"):
                m.validate_method({**proposal(), "method_text": text})
        with self.assertRaises(ValueError):m.validate_method({**proposal(), "design_patch": {"capacitance_f": 1e-5}})
        raw = {**proposal(), "changes": [{"artifact": "H", "component": "capacitance_f"}]}
        with self.assertRaises(ValueError):m.validate_method(raw)

    def test_no_update_and_empty_do_not_create_a_method(self):
        for raw in ({}, {"decision": "no-update", "reason": "MOCK: insufficient evidence"}):
            result = m.validate_method(raw)
            self.assertEqual(result["status"], "NO_UPDATE")
            self.assertNotIn("method_sha256", result)
            self.assertEqual(m.impact_scope(raw), "no-execution")
        with self.assertRaises(ValueError):m.validate_method({"decision": "no-update", "reason": "MOCK", "method_text": "MOCK change"})

    def test_unbounded_nonfinite_and_unsupported_input_rejected(self):
        for raw in ([], {**proposal(), "budget": 0}, {**proposal(), "hypothesis": "x" * 4001},
                    {**proposal(), "evidence_refs": ["../evaluator"]}, {**proposal(), "x": float("nan")}):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(ValueError):m.validate_method(raw)

    def test_typed_artifacts_and_mixed_claims(self):
        for change, expected in (({"method_text": "MOCK"}, "H"), ({"device": {}}, "D"),
                                 ({"selection_procedure": "MOCK"}, "G"), ({"untyped": "MOCK"}, "UNKNOWN"),
                                 ({"changed_artifact": "H", "load": 1}, "MIXED"),
                                 ({"world_patch": {}}, "FORBIDDEN")):
            with self.subTest(change=change):self.assertEqual(m.classify_change(change), expected)
        with self.assertRaises(ValueError):m.impact_scope({"changed_artifact": "H", "device": {}})
        with self.assertRaises(ValueError):m.impact_scope({"decision": "no-update", "device": {}})

    def test_global_h_restarts_task_entry_and_g_has_separate_root(self):
        self.assertEqual(m.impact_scope({"changed_artifact": "H"}), "task-entry")
        self.assertEqual(m.impact_scope({"changed_artifact": "G"}), "method-lineage-root")
        with self.assertRaisesRegex(ValueError, "FRESH_TASK_ENTRY"):
            m.validate_reexecution({"changed_artifact": "H"}, {"agent_decisions": "old-trace", "response_strategy": "full-feedback-response"})

    def test_load_and_timing_changes_invalidate_full_feedback(self):
        for field in ("load", "timing", "capacitance_f", "tx_not_before_s"):
            self.assertEqual(m.impact_scope({"changed_fields": [field]}), "full-feedback-response")
        for strategy in ("fixed-trajectory", "dependent-suffix", "old-decisions"):
            with self.subTest(strategy=strategy), self.assertRaisesRegex(ValueError, "REUSE_FORBIDDEN"):
                m.validate_reexecution({"changed_artifact": "D"}, {"response_strategy": strategy})

    def test_exact_response_cache_never_replaces_fresh_h_decisions(self):
        key = m.digest("MOCK:complete-consumed-input")
        policy = {"agent_decisions": "fresh-task-entry", "response_strategy": "exact-input-response",
                  "requested_input_sha256": key, "cached_input_sha256": key}
        result = m.validate_reexecution({"changed_artifact": "H"}, policy)
        self.assertEqual(result["scope"], "task-entry")
        with self.assertRaises(ValueError):m.validate_reexecution({"changed_artifact": "H"}, {**policy, "agent_decisions": "replay"})
        with self.assertRaises(ValueError):m.validate_reexecution({"changed_artifact": "D"}, {**policy, "cached_input_sha256": m.digest("MOCK:old-load")})

    def test_mock_pass_cannot_become_retained_or_real(self):
        result = gate(registry())
        self.assertEqual(result["status"], "MOCK_CONTROL_PASS")
        self.assertFalse(result["retained"])
        self.assertEqual(result["authority"], "NONE")

    def test_trusted_resolver_is_required_out_of_band(self):
        with self.assertRaisesRegex(ValueError, "RESOLVER_REQUIRED"):
            m.confirmation_gate(proposal(), proposal_receipt_id="a", h0_receipt_id="b", hprime_receipt_id="c", resolve_receipt=None)
        rows = registry(); rows["hprime"]["externally_verified"] = False
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_EXTERNAL"):
            gate(rows)
        with self.assertRaises(ValueError):m.validate_method({**proposal(), "qualification": "PASS"})

    def test_only_external_semantic_audit_can_confirm_h(self):
        for field,value,failure in (("semantic_artifact", "D", "NOT_AUDITED_AS_H"),
                                    ("method_author", "researcher", "NOT_MODEL_AUTHORED_METHOD"),
                                    ("source_scope", "hidden-final", "INVALID_SOURCE_SCOPE")):
            rows = registry(); rows["proposal"][field] = value
            with self.subTest(field=field):self.assertIn(failure, gate(rows)["failures"])

    def test_task_information_source_model_tool_evaluator_cache_parity(self):
        for field in m.PARITY_FIELDS:
            rows = registry(); rows["hprime"][field] = m.digest(["MOCK", "extra", field])
            with self.subTest(field=field):self.assertIn("PARITY_" + field.upper(), gate(rows)["failures"])

    def test_old_owners_contexts_or_initial_decisions_are_not_fresh(self):
        for field in ("episode_id", "owner", "context_id"):
            rows = registry(); rows["hprime"][field] = rows["h0"][field]
            self.assertIn("FRESH_" + field.upper(), gate(rows)["failures"])
        rows = registry(); rows["hprime"]["initial_decision_messages"] = 1
        self.assertIn("NOT_FRESH_TASK_ENTRY", gate(rows)["failures"])

    def test_actual_consumption_and_new_h_hash_required(self):
        for field,value,failure in (("method_sha256", m.digest("MOCK:wrong-H"), "HPRIME_NOT_CONSUMED"),
                                    ("actual_tool_inputs_bound", False, "MISSING_ACTUAL_EXECUTION_BINDING"),
                                    ("feedback_scope_verified", False, "STALE_FEEDBACK_RESPONSE"),
                                    ("evaluation_input_sha256", m.digest("MOCK:stale-D"), "INCOMPLETE_OR_MISBOUND_SERVICE")):
            rows = registry(); rows["hprime"][field] = value
            with self.subTest(field=field):self.assertIn(failure, gate(rows)["failures"])

    def test_failed_unknown_or_incomplete_service_forces_rejection(self):
        for status in ("FAIL", "UNKNOWN", None):
            rows = registry(); rows["hprime"]["service_status"] = status
            with self.subTest(status=status):self.assertEqual(gate(rows)["status"], "REJECT")
        rows = registry(); rows["hprime"]["independent_complete_service"] = False
        self.assertEqual(gate(rows)["status"], "REJECT")

    def test_unknown_improver_or_design_costs_cannot_disappear(self):
        for role in ("proposal", "h0", "hprime"):
            rows = registry(); rows[role]["usage_status"] = "UNKNOWN"
            with self.subTest(role=role):self.assertIn("MISSING_DECISION_OR_SETTLED_COST_BINDING", gate(rows)["failures"])

    def test_no_update_requires_no_confirmation_callback(self):
        result = m.confirmation_gate({}, proposal_receipt_id=None, h0_receipt_id=None,
                                     hprime_receipt_id=None, resolve_receipt=None)
        self.assertEqual(result["status"], "NO_UPDATE")
        self.assertFalse(result["retained"])

    def test_cli_process_schema_and_d_only_rejection(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/campaign_phase2_methods.py")]
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(command + ["schema"], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["value"], m.tool_schema())
        result = subprocess.run(command + ["validate"], input=json.dumps({**proposal(), "changed_artifact": "D"}), capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
