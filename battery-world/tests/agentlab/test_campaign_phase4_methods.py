"""Eight local contract controls. MOCK receipts never establish actual G1."""
from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from bfworld.agentlab.campaign20261019 import phase4_methods as m


ROOT = Path(__file__).resolve().parents[2]


def g_mock():
    return {"changed_artifact": "G", "hypothesis": "MOCK: alphabet review may improve a toy spelling procedure.",
            "falsifier": "MOCK: the toy descendant repeats the same spelling error.",
            "proposal_procedure": "MOCK: ask a toy method proposer to compare two spelling explanations before proposing its alphabet review procedure."}


def h_mock(index=1):
    return {"changed_artifact": "H", "hypothesis": "MOCK: inspect a toy alphabet first.",
            "falsifier": "MOCK: a toy spelling still violates the alphabet.",
            "method_text": f"MOCK toy spelling procedure {index}: inspect the alphabet before spelling."}


def usage(q=1, wall=1, usd="0.01"):
    return {"requests": q, "wall_s": wall, "usd": usd, "status": "SETTLED"}


def candidate(index, *, passes=2, wrong=0, proposal_q=1, d_q=1):
    return {"descendant_index": index, "proposal": h_mock(index), "proposal_status": "SUBMITTED",
            "semantic_H_eligible": True, "proposal_usage": usage(proposal_q),
            "selection": [{"task_id": task, "service_status": "PASS" if i < passes else "FAIL",
                           "wrong_service_judgment": i < wrong, "usage": usage(d_q)}
                          for i, task in enumerate(m.SELECTION_TASKS)]}


def formation_receipt(raw):
    parents = m.frozen_parent_methods()
    return {"evidence_kind": "ACTUAL_PROVIDER", "author": "participant-model",
            "semantic_component": "proposal_procedure_only", "usage_status": "SETTLED",
            "history_sha256": m.HISTORY_SHA256, "model_history_sha256": m.MODEL_HISTORY_SHA256,
            "H0_sha256": parents["H0"]["method_sha256"],
            "G0_sha256": parents["G0"]["procedure_sha256"], "proposal_sha256": m.digest(raw),
            "automatic_retry": False, "reported_models": ["deepseek-flash"], "unknown_usage": [],
            "formation_event_count": 1, "formation_event_id": "MOCK-formation-001",
            "registered_formation_event_id": "MOCK-formation-001",
            "provider_request_ids": ["MOCK-request-1", "MOCK-request-2"], "requests": 2,
            "wall_s": 5, "usd": "0.03", "model_configuration_sha256": "a" * 64}


class Phase4MethodContractTests(unittest.TestCase):
    def test_g_schema_cannot_submit_H_D_change_budget_or_select_itself(self):
        schema = m.g_proposal_schema()
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for raw in [g_mock(), {}, {"decision": "no-update", "reason": "MOCK insufficient evidence"}]:
            validator.validate(raw)
            self.assertIn(m.validate_improver(raw)["decision"], ("propose", "no-update"))
        bad = [{**g_mock(), "changed_artifact": "H"}, {**g_mock(), "changed_artifact": "D"}]
        bad += [{**g_mock(), key: "MOCK forbidden"} for key in
                ("H0", "method_text", "design_patch", "selection_procedure", "budget", "model",
                 "evaluator", "retained", "service_criteria")]
        bad += [{**g_mock(), "proposal_procedure": text} for text in
                ('{"capacitance_f": 0.000001}', "capacitance_f=1;tx_not_before_s=2", "\x00")]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                m.validate_improver(raw)
        unchanged = {**g_mock(), "proposal_procedure": m.frozen_parent_methods()["G0"]["proposal_procedure"]}
        self.assertEqual(m.validate_improver(unchanged)["decision"], "no-update")
        with self.assertRaises(ValueError):
            m.validate_improver({**unchanged, "hypothesis": ""})

    def test_one_shared_actual_formation_requires_authorship_bound_history_and_settlement(self):
        raw = g_mock()
        receipt = formation_receipt(raw)  # MOCK structural projection, never real evidence.
        result = m.formation_gate(raw, receipt=receipt)
        self.assertEqual(result["independent_G1_formation_events"], 1)
        self.assertEqual(result["descendant_lineage_pairs"], 3)
        self.assertFalse(result["retained"])
        self.assertEqual(result["qualification_authority"], "NONE")
        for key, value in [("author", "Codex"), ("semantic_component", "method_text"),
                           ("formation_event_count", 3), ("formation_event_count", True),
                           ("registered_formation_event_id", "other"), ("history_sha256", "0" * 64),
                           ("model_history_sha256", "0" * 64),
                           ("H0_sha256", "0" * 64), ("proposal_sha256", "0" * 64),
                           ("usage_status", "UNKNOWN"), ("unknown_usage", ["MOCK-unresolved"]),
                           ("automatic_retry", True), ("requests", 0), ("wall_s", 401),
                           ("provider_request_ids", ["MOCK-request-1"]),
                           ("reported_models", ["ambiguous"]), ("model_configuration_sha256", "")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.formation_gate(raw, receipt={**receipt, key: value})
        abstention = {"decision": "no-update", "reason": "MOCK retain G0"}
        no_update = m.formation_gate(abstention, receipt=formation_receipt(abstention))
        self.assertEqual(no_update["status"], "NO_UPDATE")
        self.assertEqual(sum(x["requests"] for x in no_update["allocation"]), 2)

    def test_frozen_history_preserves_entire_real_public_traces_and_original_failure(self):
        raw = m.history_packet_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), m.HISTORY_SHA256)
        packet = m.public_history_packet()
        self.assertEqual(len(packet["episodes"]), 4)
        self.assertEqual([x["phase"] for x in packet["episodes"]], [2, 3, 3, 3])
        self.assertEqual(packet["episodes"][0]["retained_episode_status"], "INCOMPLETE_OR_STOPPED")
        self.assertEqual(packet["episodes"][0]["charged_usage"]["requests"], 9)
        for episode in packet["episodes"]:
            self.assertEqual(m.digest(episode["public_trace"]), episode["public_trace_canonical_sha256"])
            self.assertEqual(episode["public_trace"][-1]["type"], "bf_episode_complete")
            self.assertEqual(set(episode["participant_input"]), {"goal", "instruction", "tool", "limits"})
            self.assertEqual(set(episode["source_files"]), {"protocol.json", "pi-public-trace.jsonl", "episode-result.json"})
        participant_bytes = json.dumps([{k: e[k] for k in ("participant_input", "public_trace")}
                                        for e in packet["episodes"]], ensure_ascii=False).encode()
        for forbidden in (b"p4-", b"stage4-", b"phase4/", b"O0", b"unexposed-waveform"):
            self.assertFalse(forbidden in participant_bytes, "Unexpected future identifier " + repr(forbidden))
        parents = m.frozen_parent_methods()
        conditions = json.loads((ROOT / "configs/studies/phase3-20261020/methods/conditions.json").read_text())
        reflection = next(c for c in conditions["conditions"] if c["id"] == "ordinary_reflection")
        self.assertEqual(parents["G0"]["proposal_procedure"], reflection["proposal_instruction"])
        self.assertEqual(parents["H0"]["method_text"], conditions["common"]["base_design_instruction"])
        config = json.loads((m.CONFIG / "protocol.json").read_text())
        self.assertEqual(config["selection_tasks"], list(m.SELECTION_TASKS))
        self.assertEqual(config["arm_slots"], list(m.ARM_SLOTS))
        self.assertEqual(config["public_history_sha256"], m.HISTORY_SHA256)
        model_bytes = m.model_history_packet_bytes()
        self.assertLessEqual(len(model_bytes), 80000)
        self.assertEqual(hashlib.sha256(model_bytes).hexdigest(), m.MODEL_HISTORY_SHA256)
        self.assertEqual((m.CONFIG / "model-history.json").read_bytes(), model_bytes)
        model = m.model_history_packet()
        wrapped = json.dumps({"model_history": model, "frozen_parents": parents},
                             ensure_ascii=False, separators=(",", ":")).encode()
        self.assertLessEqual(len(wrapped), 96000)
        self.assertEqual(config["model_history_sha256"], m.MODEL_HISTORY_SHA256)
        self.assertEqual(model["complete_host_packet_sha256"], m.HISTORY_SHA256)
        self.assertEqual(len(model["episodes"]), 4)
        for original, projected in zip(packet["episodes"], model["episodes"]):
            self.assertEqual(projected["charged_usage"], original["charged_usage"])
            self.assertEqual(projected["retained_episode_status"], original["retained_episode_status"])
            tools = [(i, r) for i, r in enumerate(original["public_trace"]) if r["type"] == "bf_tool_fact"]
            self.assertEqual(len(projected["all_tool_calls"]), len(tools))
            for (index, tool), call in zip(tools, projected["all_tool_calls"]):
                self.assertEqual(call["original_trace_index"], index)
                self.assertEqual(call["input"], tool["input"])
                self.assertEqual(call["ok"], tool["ok"])
                self.assertEqual(call["original_result_sha256"], m.digest(tool["result"]))
                ref = call["projected_result_ref"]
                self.assertEqual(m.digest(model["projected_tool_results"][ref]), ref)

    def test_mutating_one_return_or_config_bytes_cannot_warm_or_change_other_arm(self):
        first = m.public_history_packet()
        first["episodes"][0]["public_trace"].clear()
        self.assertTrue(m.public_history_packet()["episodes"][0]["public_trace"])
        parents = m.frozen_parent_methods()
        parents["H0"]["method_text"] = "MOCK changed"
        self.assertNotEqual(m.frozen_parent_methods()["H0"]["method_text"], "MOCK changed")
        with patch.object(Path, "read_bytes", return_value=b"MOCK altered bytes"):
            for function in (m.history_packet_bytes, m.public_history_packet, m.frozen_parent_methods,
                             m.model_history_packet_bytes, m.model_history_packet):
                with self.subTest(function=function), self.assertRaises(ValueError):
                    function()
        with patch.object(m, "_project_model_history", return_value={"MOCK": "x" * 80001}):
            with self.assertRaisesRegex(ValueError, "MODEL_HISTORY_EXCEEDS_80000_BYTES"):
                m.model_history_packet_bytes()

    def test_selection_uses_pass_then_error_then_complete_requests_then_stable_index(self):
        pairs = [([candidate(1, passes=1, proposal_q=1), candidate(2, passes=2, proposal_q=8)], 2),
                 ([candidate(1, wrong=1), candidate(2, wrong=0, proposal_q=8)], 2),
                 ([candidate(1, proposal_q=1, d_q=5), candidate(2, proposal_q=8, d_q=1)], 2),
                 ([candidate(2), candidate(1)], 1)]
        for rows, expected in pairs:
            with self.subTest(expected=expected):
                result = m.select_descendant(rows)
                self.assertEqual(result["selected_descendant_index"], expected)
                self.assertEqual(result["selected_H_text"], m.frozen_parent_methods()["H0"]["method_text"] +
                                 "\n\n" + h_mock(expected)["method_text"])
                self.assertFalse(result["final_results_consulted"])
                self.assertFalse(result["default_H0_changed"])

    def test_final_feedback_duplicate_tasks_and_unknown_cost_cannot_drive_selection(self):
        attacks = []
        row = candidate(1); row["final_results"] = {"service": "PASS"}; attacks.append(row)
        row = candidate(1); row["selection"][0]["task_id"] = "MOCK-final-input"; attacks.append(row)
        row = candidate(1); row["selection"][1]["task_id"] = m.SELECTION_TASKS[0]; attacks.append(row)
        row = candidate(1); row["selection"][0]["final_test_PASS"] = True; attacks.append(row)
        row = candidate(1); row["proposal_usage"]["status"] = "UNKNOWN"; attacks.append(row)
        row = candidate(1); del row["selection"][0]["usage"]; attacks.append(row)
        row = candidate(1); row["proposal_usage"]["requests"] = True; attacks.append(row)
        row = candidate(1); row["selection"][0]["usage"]["requests"] = 13; attacks.append(row)
        for row in attacks:
            with self.subTest(row=row), self.assertRaises(ValueError):
                m.select_descendant([row, candidate(2)])

    def test_invalid_no_update_and_failed_siblings_remain_charged_with_explicit_H0_fallback(self):
        first = candidate(1, proposal_q=3)
        first.update(proposal={"decision": "no-update", "reason": "MOCK abstain"}, selection=[])
        second = candidate(2, proposal_q=8)
        second.update(proposal={"changed_artifact": "D", "capacitance_f": 1},
                      proposal_status="INVALID", semantic_H_eligible=False, selection=[])
        originals = deepcopy([first, second])
        result = m.select_descendant([first, second])
        self.assertEqual(result["status"], "H0_FALLBACK_NO_ADMISSIBLE_DESCENDANT")
        self.assertIsNone(result["selected_descendant_index"])
        self.assertEqual(result["selected_H_text"], m.frozen_parent_methods()["H0"]["method_text"])
        self.assertEqual(result["total_selection_charged_requests"], 11)
        self.assertEqual(result["raw_rows"], originals)
        self.assertEqual([first, second], originals)
        failed = candidate(1); failed["proposal_status"] = "CENSORED"
        self.assertEqual(m.select_descendant([failed, candidate(2, passes=0)])["selected_descendant_index"], 2)
        for rows in ([first], [first, first], [first, second, candidate(1)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                m.select_descendant(rows)

    def test_formation_and_all_arm_costs_conserve_without_free_failed_work_or_retries(self):
        shares = m.formation_allocation(8, "400", "0.1")
        self.assertEqual([r["requests"] for r in shares], [3, 3, 2])
        with localcontext() as ctx:
            ctx.prec = 50
            self.assertEqual(sum(Decimal(r["wall_s"]) for r in shares), Decimal(400))
            self.assertEqual(sum(Decimal(r["usd"]) for r in shares), Decimal("0.1"))
        all_work = [{"slot": slot, "usage": usage(8 if slot.endswith("-proposal") else 12,
                                                400 if slot.endswith("-proposal") else 800,
                                                "0.5")} for slot in m.ARM_SLOTS]
        base = m.arm_budget("G0", 1, usage_rows=all_work)
        self.assertEqual(base["total_requests"], 100)
        self.assertEqual(Decimal(base["total_wall_s"]), 6400)
        revised = m.arm_budget("G1", 1, usage_rows=all_work,
                               formation_actual={"requests": 8, "wall_s": 400, "usd": "0.1"})
        self.assertEqual(revised["total_requests"], 103)
        self.assertGreater(Decimal(revised["total_usd"]), Decimal(base["total_usd"]))
        costly = deepcopy(all_work)
        for row in costly: row["usage"]["usd"] = "1.12"
        with self.assertRaises(ValueError): m.arm_budget("G0", 1, usage_rows=costly)
        with self.assertRaises(ValueError): m.arm_budget("G1", 1, usage_rows=all_work)
        with self.assertRaises(ValueError): m.arm_budget("G0", 1, usage_rows=[all_work[0], all_work[0]])
        with self.assertRaises(ValueError): m.arm_budget("G0", 1, usage_rows=all_work,
                                                       formation_actual={"requests": 8, "wall_s": 400, "usd": "0.1"})
        for args in [(9, 1, 0), (1, 401, 0), (True, 1, 0), (None, 1, 0),
                     (1, float("nan"), 0), (1, 1, None), (1, 1, -1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                m.formation_allocation(*args)


if __name__ == "__main__":
    unittest.main()
