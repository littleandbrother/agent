"""One affected-path M3 check: old FIRST public prefix, mock predictors/model.

No real shared predictor, numerical consumer, provider or private result reads.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / "docs/research/pqe-two-paper-plan-20261022"
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import m3_methods as m3
from bfworld.agentlab.pqe20261022.methods import public_state

HERE = Path(__file__).resolve().parent
sources = [BASE / "dynamic-decision-m2/a/public/task-02-input.json",
           BASE / "dynamic-decision-m2/s0/initial/m2-02/public-result.json",
           BASE / "dynamic-decision-m2/s0/episodes/m2-02-f/actions/01/public-result.json"]
packet, initial, first = [json.loads(p.read_text()) for p in sources]
state = {"task": packet["task"], "design": packet["initial_design"],
         "problem": packet["initial_problem"], "history": [], "evidence": [],
         "hypotheses": [], "invalidated": [], "strategy": {}}
quota = {"remaining_actions": 3, "remaining_cost": 3, "max_candidates": 6,
         "analytic_scores_left": 24, "public_tool_calls_left": 24,
         "model_calls_remaining": 12, "model_cost_remaining": 5,
         "model_call_reserve": 0.19, "output_tokens_left": 65536}
mock_calls = []
mode = "quiet"
original_retry = first["design"]["retry_s"]


def mock_predict(task, design, service_facts=None):
    mock_calls.append({"mode": mode, "design_sha256": m3.digest(design),
                       "service_facts_sha256": m3.digest(service_facts)})
    if mode == "quiet":
        best = design["retry_s"] > original_retry
    elif mode == "fast":
        best = design["retry_s"] < original_retry
    else:
        best = False
    return {"schema": "MOCK_SOFTWARE_ONLY", "prediction_status": "CONDITIONAL",
        "service_verdict": "UNKNOWN", "score": -1, "necessary_failures": [],
        "phase_predictions": [{"phase": "BOOT", "startup_margin_v": .1}],
        "repair_intervals": {}, "service_prediction": {
            "conditional_timely_windows": (6 if best else 2) if mode != "unknown" else None,
            "unknown_windows": 0 if mode != "unknown" else 6,
            "conditions": ["MOCK; isolated record, uninterrupted power, no inherited queue"]},
        "selection_metrics": {"conditional_ack_completed_windows": 6,
                              "minimum_isolated_terminal_margin_v": .1 if mode != "unknown" else None},
        "unknowns": ["MOCK software behavior, not physical/service prediction"]}


m3.predict_candidate = mock_predict
checks, runs = {}, []
for setting in ["quiet", "fast", "unknown"]:
    mode = setting
    h = m3.M3ServiceHarness()
    prefix = h.update(deepcopy(state), {"source": "shared initial public state"}, deepcopy(initial))
    continued = h.update(prefix, {"source": "externally supplied FIRST failure"}, deepcopy(first))
    memory, consumed = h._service(public_state(continued))
    assert consumed and memory["facts"]["status"] == "PUBLIC_OBSERVATION"
    assert memory["facts"]["summary"]["timely_public_window_records"] == 0
    assert memory["observations"]["delivery_issue_observed"]
    assert len(memory["observations"]["definitely_late_records"]) == 3
    assert len(memory["observations"]["unreceived_records"]) == 3
    assert len(memory["observations"]["final_public_queue"]) == 3
    batch = h.generate(continued, quota)
    choice = h.select(continued, batch, quota)
    assert batch["status"] == choice["status"] == "READY", (batch, choice)
    assert any("retry_s" in c["actual_input"]["design_patch"] for c in batch["candidates"])
    assert any("tx_gate_v" in c["actual_input"]["design_patch"] for c in batch["candidates"])
    assert any("capacitance_f" in c["actual_input"]["design_patch"] for c in batch["candidates"])
    assert all("mechanism" not in c["actual_input"]["design_patch"] for c in batch["candidates"])
    assert h.usage_ledger == [] and h.analytic_score_count <= 7
    assert {c["site"] for c in h.program.calls} >= {"H-GEN", "H-RANK", "H-UPDATE"}
    if setting == "unknown":
        assert choice["selection_basis"] == "DISCRIMINATING_EXECUTION_OF_UNRESOLVED_SERVICE"
        assert choice["expected_discrimination_or_gain"]["conditional_timely_records"] is None
    stale = deepcopy(continued)
    stale["strategy"].pop("service_repair")
    before = len(mock_calls)
    no_state = m3.M3ServiceHarness().generate(stale, quota)
    assert no_state["status"] == "INSUFFICIENT_EVIDENCE" and len(mock_calls) == before
    passed = deepcopy(continued)
    passed["last_result"]["public_check"]["verdict"] = "PASS"  # software-only stop control
    before = len(mock_calls)
    stopped = h.generate(passed, {**quota, "analytic_scores_left": 0})
    assert stopped["status"] == "STOPPED" and len(mock_calls) == before
    runs.append({"mock_mode": setting, "generated": [
        {"id": c["id"], "actual_input": c["actual_input"]} for c in batch["candidates"]],
        "selected_id": choice["selected_id"], "actual_input": choice["actual_input"],
        "selection_basis": choice["selection_basis"],
        "assessment": choice["expected_discrimination_or_gain"],
        "mock_prediction_count": h.analytic_score_count,
        "loaded_hook_sites": [c["site"] for c in h.program.calls]})
assert runs[0]["actual_input"] != runs[1]["actual_input"]
checks.update(service_failures_consumed_despite_no_phase_failure_gate=True,
    real_Update_Generate_Select_hooks=True, remove_service_memory_removes_proposals_without_score=True,
    changed_mock_delivery_prediction_changes_selected_action=True,
    unknown_uses_declared_discriminating_execution_not_edit_count_utility=True,
    retry_gate_storage_pool_uses_current_geometry=True, actual_PASS_stops_without_scoring=True)

# Conditional energy/BOOT diagnostics can overrule a high diagnostic count.
adverse = mock_predict(state["task"], first["design"])
adverse["service_prediction"].update(conditional_timely_windows=6, unknown_windows=0)
adverse["selection_metrics"].update(conditional_ack_completed_windows=6, minimum_isolated_terminal_margin_v=-.1)
assessed = m3._decision_assessment(adverse, {"design_patch": {"retry_s": .2}}, memory)
assert assessed["electrical_adverse_prediction"] and assessed["priority"][0] == 0
checks["electrical_adverse_prediction_not_promoted_by_timely_count"] = True

mode = "quiet"
model_calls, reader_calls = [], []
candidate = deepcopy(batch["candidates"][0])


def reader(arguments):
    reader_calls.append(deepcopy(arguments))
    return {"version": "M3-public-objects-v1", "visibility": "PUBLIC_ONLY", "object_id": "mock-public-object",
            "section": "records", "offset": 0, "rows": [{"seq": 1}], "next_offset": 1}


def model(request):
    model_calls.append(deepcopy(request))
    if request["site"] == "H-GEN" and not request["context"].get("public_tool_results"):
        payload = {"status": "PUBLIC_TOOLS", "tool_calls": [
            {"id": "facts", "name": "service_facts", "arguments": {}},
            {"id": "prediction", "name": "predict_candidate", "arguments": {"design": {**continued["design"], **candidate["actual_input"]["design_patch"]}}},
            {"id": "page", "name": "public_object", "arguments": {"object_id": "mock-public-object", "section": "records", "offset": 0}}]}
    elif request["site"] == "H-GEN":
        results = request["context"]["public_tool_results"]
        assert results[0]["result"]["summary"]["service_failure_observed"]
        assert results[1]["result"]["service_verdict"] == "UNKNOWN"
        assert results[2]["result"]["next_offset"] == 1
        payload = {"status": "OK", "candidates": [candidate]}
    else:
        payload = {"selected_id": candidate["id"], "selection_basis": "Fixture model chooses its supplied candidate"}
    return {"payload": payload, "usage": {"status": "SOFTWARE_FIXTURE", "cost": 0,
                                            "input_tokens": 0, "output_tokens": 0}}


g = m3.M3GenericHarness(model, fixture_mode=True, public_reader=reader)
gs = g.update(deepcopy(state), {}, deepcopy(initial))
gs = g.update(gs, {}, deepcopy(first))
gb = g.generate(gs, quota)
gc = g.select(gs, gb, quota)
assert gb["status"] == gc["status"] == "READY", (gb, gc)
assert len(model_calls) == 3 and len(reader_calls) == 1
assert g.tool_call_count == 3 and g.analytic_score_count == 1
assert len(g.usage_ledger) == 3 and not g.blocked
checks.update(generic_same_shared_service_tool_and_mock_predictor=True,
    public_object_injected_reader_page_preserved_and_counted=True,
    original_payload_usage_callback_contract_preserved=True)

def bind(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

output = {"package": "BF-PQE-SERVICE-REPAIR-M3-20261023-001", "status": "OFFLINE_BEHAVIOR_PASS",
    "scope": "Software behavior on old initial+FIRST public prefix only; every predictor/model callback is a mock.",
    "real_model_calls": 0, "real_shared_predictor_calls": 0, "real_full_dynamic_calls": 0,
    "later_M2_candidate_or_success_or_A_reference_reads": 0,
    "public_prefix_bindings": [bind(p) for p in sources],
    "checks": checks, "fixed_mock_runs": runs,
    "mock_predictor_calls": len(mock_calls), "mock_model_callbacks": len(model_calls),
    "generic_explicit_tools": g.tool_call_count, "generic_mock_scores": g.analytic_score_count,
    "observed_service_summary_from_A_extractor": memory["facts"]["summary"],
    "participant_source": bind(APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022/m3_methods.py"),
    "A_extractor_source_at_offline_check": bind(APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022/service_relations.py")}
target = HERE / "OFFLINE-BEHAVIOR.json"
target.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
print(json.dumps({"status": output["status"], "checks": len(checks), "mock_predictions": len(mock_calls),
                  "mock_model_callbacks": len(model_calls), "artifact": bind(target)}))
