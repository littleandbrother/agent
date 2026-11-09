"""Read only completed public M4 files; no method/predictor/solver imports."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[5]
B = Path(__file__).resolve().parent
S0 = B.parent / "s0"
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
SOURCES = {}


def bind(path):
    data = path.read_bytes()
    info = {"path": str(path.relative_to(ROOT)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    SOURCES[info["path"]] = info
    return info


def read(path):
    assert path.name not in {"raw.json", "assessment.json"}
    bind(path)
    return json.loads(path.read_text())


interface = read(B / "INTERFACE-RECEIPT.json")
assert bind(ROOT / interface["module"]["path"])["sha256"] == interface["module"]["sha256"]
assert bind(ROOT / interface["frozen_M3"]["path"])["sha256"] == interface["frozen_M3"]["sha256"]
assert bind(ROOT / interface["A_facts_source_at_check"]["path"])["sha256"] == interface["A_facts_source_at_check"]["sha256"]
index = read(S0 / "chain/index.json")
for value in index.values():
    if isinstance(value, dict) and {"path", "sha256", "bytes"} <= value.keys():
        actual = bind(Path(value["path"]))
        assert actual["sha256"] == value["sha256"] and actual["bytes"] == value["bytes"]
initial = read(S0 / "chain/initial-state.json")
after = read(S0 / "chain/candidate-state-after.json")
final = read(S0 / "chain/final-state.json")
selected = read(S0 / "chain/selected.json")
transcript = read(S0 / "chain/method-transcript.json")
candidate = read(S0 / "candidate/01/public-result.json")
regression = read(S0 / "regression/01/public-result.json")
ledger = read(S0 / "resource-ledger.json")
read(S0 / "result.json")
mem0 = initial["strategy"]["executable_select"]
mem1 = after["strategy"]["executable_select"]
mem2 = final["strategy"]["executable_select"]
assert selected["status"] == "READY" and selected["selection_basis"] == "DISCRIMINATING_EXPERIMENT"
assert selected["actual_input"]["design_patch"] == {"retry_s": .85}
assert selected["expected_discrimination_or_gain"]["service_verdict"] == "UNKNOWN"
assert selected["expected_discrimination_or_gain"]["WAIT_margin_used_as_gain"] is False
assert initial["design"]["retry_s"] == .65
assert candidate["design"] == {**initial["design"], "retry_s": .85} == regression["design"]
assert candidate["model_valid"] is True and candidate["public_check"]["verdict"] == "PASS"
assert regression["model_valid"] is True and regression["public_check"]["verdict"] == "FAIL"
assert candidate["public_check"]["received_count"] == 6 and regression["public_check"]["received_count"] == 0
counts = dict(Counter(x["action"] for x in candidate["facts"]["activity"]))
rcounts = dict(Counter(x["action"] for x in regression["facts"]["activity"]))
assert counts["save_commit"] == counts["ack_commit"] == 6 and counts["wire_complete"] == 12
assert len(candidate["facts"]["program_state"]["nvm"]["queue"]) == 0
assert rcounts["save_commit"] == 6 and rcounts.get("tx_begin", 0) == 0
assert len(regression["facts"]["program_state"]["nvm"]["queue"]) == 6
assert mem0["trajectory_facts"]["summary"]["timely_public_window_records"] == 3
execution = mem1["candidate_execution"]
assert execution["scientific_observation"] is True and execution["design"] == candidate["design"]
assert execution["result"]["result_sha256"] == candidate["result_sha256"]
assert execution["trajectory_facts"]["scope"]["result_sha256"] == candidate["result_sha256"]
assert execution["trajectory_facts"]["summary"]["timely_public_window_records"] == 6
assert execution["trajectory_facts"]["summary"]["complete_public_event_lists"] is True
assert mem1["adoption_status"] == "PENDING_REGRESSION"
assert mem2["adoption_status"] == "RETAIN_PARENT_REGRESSION_NOT_PASSED"
assert mem2["candidate_execution"] == execution and mem2["regression_result"]["result_sha256"] == regression["result_sha256"]
assert initial["design"] == after["design"] == final["design"] == mem2["parent_design"]
assert mem0["parent_result"] == mem2["parent_result"]
sites = [row["site"] for row in transcript["calls"] if row.get("loaded")]
assert sites.count("H-UPDATE") == 2 and "H-GEN" in sites and "H-RANK" in sites
assert ledger["full_dynamic_inputs"] == 2 and ledger["cache_reuses"] == 0
assert ledger["cheap_scores"] == 1 and ledger["provider_requests"] == ledger["provider_usd"] == 0
assert ledger["native_inputs"] == ledger["hardware_runs"] == ledger["post_participant_result_revisions"] == 0
for row in ledger["attempts"]:
    assert bind(Path(row["public_result"]["path"]))["sha256"] == row["public_result"]["sha256"]
out = {"package": ledger["package"], "at": datetime.now(timezone.utc).isoformat(),
       "status": "FINAL_PUBLIC_READBACK_PASS", "real_loaded_hook_sites": sites,
       "choice": {"basis": selected["selection_basis"], "actual_input": selected["actual_input"],
                  "service_verdict_before_execution": "UNKNOWN"},
       "candidate": {"public_result": bind(S0 / "candidate/01/public-result.json"),
                     "public_check": candidate["public_check"], "timely_public_records": 6,
                     "activity_counts": counts, "final_queue": 0,
                     "minimum_tx_terminal_v": candidate["facts"]["minimum_tx_terminal_v"]},
       "regression": {"public_result": bind(S0 / "regression/01/public-result.json"),
                      "public_check": regression["public_check"], "activity_counts": rcounts, "final_queue": 6},
       "adoption": {"after_candidate": mem1["adoption_status"], "final": mem2["adoption_status"],
                    "parent_retry_s": .65, "executed_candidate_retry_s": .85,
                    "candidate_evidence_preserved": True, "parent_tested_on_regression_task_in_this_package": False},
       "accounting": {k: ledger[k] for k in ["full_dynamic_inputs", "full_dynamic_wall_s", "cache_reuses",
                                            "cheap_scores", "provider_requests", "provider_usd", "post_participant_result_revisions"]},
       "worker_new_predictor_full_model_test_calls_during_final_readback": 0,
       "private_raw_or_assessment_read": False, "available_bytes": shutil.disk_usage(ROOT).free,
       "sources": sorted(SOURCES.values(), key=lambda row: row["path"]),
       "claim_boundary": "One exposed-task engineering repair and failed prescribed regression, with parent retention; no relative-parent degradation inference, learned H, transfer, superiority or hardware claim."}
path = B / "FINAL-CHAIN-READBACK.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": out["status"], "output": bind(path)}))
