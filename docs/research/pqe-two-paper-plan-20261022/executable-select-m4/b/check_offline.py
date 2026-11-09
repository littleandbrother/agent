"""Saved-pool replay and minimal software controls; no predictor/full/model call."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / "docs/research/pqe-two-paper-plan-20261022"
HERE = Path(__file__).resolve().parent
SRC = ROOT / "workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src"
sys.path.insert(0, str(SRC))
from bfworld.agentlab.pqe20261022 import m4_methods as m4

packet = json.loads((BASE / "dynamic-decision-m2/a/public/task-02-input.json").read_text())
parent_path = BASE / "service-repair-m3/s0/engineering/02/public-result.json"
parent = json.loads(parent_path.read_text())
state = {"task": packet["task"], "design": parent["design"], "problem": parent["problem"],
         "history": [], "evidence": [], "strategy": {}, "last_result": parent}
quota = {"remaining_actions": 1, "remaining_cost": 1, "max_candidates": 6, "analytic_scores_left": 4}
checks, replays = {}, []

for number in [1, 2]:
    path = BASE / f"service-repair-m3/s0/episodes/m3-u/actions/{number:02d}-input.json"
    saved = json.loads(path.read_text())
    replay_state = {**deepcopy(state), "design": saved["design"], "strategy": {}}
    h = m4.M4Harness()
    before = m4.digest(saved["decision"]["alternatives"])
    choice = h.select(replay_state, {"status": "READY", "candidates": saved["decision"]["alternatives"]}, quota)
    assert choice["status"] == "NO_SUPPORTED_IMPROVEMENT" and choice["selected_id"] is None
    assert h.analytic_score_count == 0 and not h.usage_ledger
    assert before == m4.digest(saved["decision"]["alternatives"])
    assessments = h.decisions[-1]["assessments"]
    assert all(a.get("minimum_modeled_TX_margin_v") is None for a in assessments if a["status"] != "REJECT_CANDIDATE_NECESSARY")
    replays.append({"source": str(path.relative_to(ROOT)), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "saved_pool_sha256": before, "count": len(saved["decision"]["alternatives"]),
                    "selection_status": choice["status"], "assessments": assessments,
                    "new_predictions": 0, "new_scientific_runs": 0})
assert [x["count"] for x in replays] == [6, 5]
assert any(a["status"] == "REJECT_CANDIDATE_NECESSARY" for a in replays[1]["assessments"])
checks["saved_6_plus_5_keep_parent_without_rescoring"] = True

# Actual A extractor, only the already public frozen parent trajectory.
h = m4.M4Harness()
initial = h.update(state, {"source": "explicit previously executed development parent"}, parent)
memory = initial["strategy"]["executable_select"]
assert memory["trajectory_facts"]["status"] == "PUBLIC_TRAJECTORY_FACTS"
assert memory["trajectory_facts"]["summary"]["timely_public_window_records"] == 3
assert memory["trajectory_facts"]["summary"]["tx_count"] == 17
assert memory["parent_design"] == parent["design"] and "candidate_execution" not in memory
checks["original_continuous_parent_facts_enter_real_Update"] = True

proposal = {"status": "READY", "proposal": {"id": "SOFTWARE-CONTROL-ONLY", "actual_input": {
    "operation": "edit", "design_patch": {"retry_s": .64}, "problem_patch": {}},
    "rationale": "SOFTWARE ONLY: distinguish powered retry expenditure from unreachable gate.",
    "hypotheses": ["SOFTWARE hypothetical expenditure explanation"],
    "branches": ["Hypothesis supported: retain observed evidence", "Hypothesis refuted: retain parent"],
    "conditions": ["SOFTWARE ONLY; no physical forecast or consumer run"]}}
h = m4.M4Harness(proposal)
batch = h.generate(initial, quota)
choice = h.select(initial, batch, quota)
assert batch["status"] == choice["status"] == "READY"
assert choice["selection_basis"] == "DISCRIMINATING_EXPERIMENT"
assert choice["expected_discrimination_or_gain"]["service_verdict"] == "UNKNOWN"
assert h.analytic_score_count == 0 and not h.usage_ledger
checks["unknown_with_explicit_hypotheses_and_branches_can_execute_without_adoption"] = True

c = deepcopy(batch["candidates"][0])
c.pop("experiment")
design = {**parent["design"], **c["actual_input"]["design_patch"]}
pred = {"scope": {"task_sha256": m4.digest(packet["task"]), "design_sha256": m4.digest(design)},
        "necessary_checks": [], "relations": [], "service_prediction": {
            "conditional_timely_windows": 6, "unknown_windows": 0,
            "windows": [{"timely": True, "ack_completed": True, "attempts": [{"minimum_terminal_margin_v": .1}]} for _ in range(6)]}}
c["service_prediction"] = pred
def select(candidate):
    harness = m4.M4Harness()
    return harness.select(initial, {"status": "READY", "candidates": [candidate]}, quota)
assert select(c)["selection_basis"] == "CONDITIONAL_SUPPORTED_IMPROVEMENT_FOR_EXECUTION"
unfavorable = deepcopy(c)
unfavorable["service_prediction"]["service_prediction"] = {"conditional_timely_windows": 0, "unknown_windows": 0,
    "windows": [{"timely": False, "attempts": [], "minimum_terminal_margin_v": 100} for _ in range(6)]}
assert select(unfavorable)["status"] == "NO_SUPPORTED_IMPROVEMENT"
necessary = deepcopy(c)
necessary["service_prediction"]["relations"] = [{"relation_id": "passive_bus_upper_bound", "kind": "NECESSARY",
    "status": "KNOWN", "value": {"bus_upper_v": parent["design"]["tx_gate_v"]-.1}, "conditions": ["SOFTWARE bound"]}]
assert select(necessary)["assessments"][0]["status"] == "REJECT_CANDIDATE_NECESSARY"
tool = deepcopy(c)
tool["service_prediction"]["prediction_status"] = "TOOL_ERROR"
assert select(tool)["assessments"][0]["status"] == "TOOL_ERROR"
checks["supported_unfavorable_necessary_and_tool_error_are_distinct"] = True

# Synthetic results below contain no old sampled voltage/trace under a new design.
mock_extractions = []
def mock_extract(task, design, result):
    mock_extractions.append(result["result_sha256"])
    return {"status": "PUBLIC_TRAJECTORY_FACTS", "summary": {"timely_public_window_records": 6 if result["public_check"]["verdict"] == "PASS" else 4},
            "scope": "SOFTWARE FIXTURE; no science"}
m4.extract_trajectory_facts = mock_extract
def fixture(verdict):
    return {"schema_version": "pqe-public-result-software-fixture", "execution_status": "COMPLETE",
            "task_id": packet["task"]["task_id"], "model_valid": True, "design": design,
            "public_check": {"verdict": verdict, "received_count": 6 if verdict == "PASS" else 4,
                "failures": [] if verdict == "PASS" else ["MISSED_OR_LATE_EVENT"], "unknown": []},
            "facts": {"receiver_records": [{"seq": i} for i in range(6 if verdict == "PASS" else 4)]},
            "result_sha256": "SOFTWARE-"+verdict}
partial = h.update(initial, choice, fixture("FAIL"))
assert partial["design"] == parent["design"] and partial["last_result"]["design"] == design
assert partial["strategy"]["executable_select"]["adoption_status"] == "RETAIN_PARENT"
assert partial["strategy"]["executable_select"]["candidate_execution"]["result"]["public_check"]["received_count"] == 4
pending = h.update(initial, choice, fixture("PASS"))
assert pending["design"] == parent["design"] and pending["strategy"]["executable_select"]["adoption_status"] == "PENDING_REGRESSION"
regression = fixture("PASS")
regression["task_id"] = m4.REGRESSION_TASK_ID
adopted = h.finalize_adoption(pending, regression)
assert adopted["design"] == design and adopted["strategy"]["executable_select"]["adoption_status"] == "ADOPTED_AFTER_REGRESSION"
regression["public_check"]["verdict"] = "FAIL"
retained = h.finalize_adoption(pending, regression)
assert retained["design"] == parent["design"] and retained["strategy"]["executable_select"]["candidate_execution"]
error = fixture("FAIL")
error["execution_status"] = "TOOL_ERROR"
before = len(mock_extractions)
errored = h.update(initial, choice, error)
assert len(mock_extractions) == before and errored["design"] == parent["design"]
assert errored["strategy"]["executable_select"]["candidate_execution"]["scientific_observation"] is False
checks["partial_pending_regression_adoption_and_tool_error_keep_execution_separate_from_parent"] = True

def bind(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
out = {"package": "BF-PQE-EXECUTABLE-SELECT-M4-20261023-001", "status": "OFFLINE_SEMANTICS_PASS",
       "checks": checks, "saved_pool_replays": replays,
       "real_shared_predictor_calls": 0, "real_full_dynamic_calls": 0, "real_model_calls": 0,
       "software_mock_result_extractions": len(mock_extractions),
       "existing_parent_continuous_facts_extraction": 1,
       "loaded_hook_sites": sorted({x["site"] for x in h.program.calls}),
       "sources": [bind(parent_path), bind(SRC/'bfworld/agentlab/pqe20261022/m3_methods.py'),
                   bind(SRC/'bfworld/agentlab/pqe20261022/m4_methods.py'),
                   bind(SRC/'bfworld/agentlab/pqe20261022/trajectory_service_facts.py')],
       "claim_boundary": "Saved-pool/software semantics only; synthetic support/adoption controls are not scientific outcomes."}
(HERE/'OFFLINE-RECEIPT.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
(HERE/'cheap-ledger.json').write_text(json.dumps({"package": out["package"], "cap": 4, "consumed": 0, "new_cheap_relation_calls": 0,
    "rows": [], "saved_pool_candidates_read": 11, "software_mock_results_not_science": True},indent=2)+'\n')
print(json.dumps({"status":out["status"],"checks":len(checks),"new_predictor_full_model_calls":0,
                  "receipt":bind(HERE/'OFFLINE-RECEIPT.json')}))
