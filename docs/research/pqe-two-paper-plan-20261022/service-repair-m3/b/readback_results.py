"""Audit saved public M3 artifacts only; no method, predictor or consumer imports."""
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
SRC = APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022"
READS = {}


def bind(path):
    data = path.read_bytes()
    info = {"path": str(path.relative_to(ROOT)), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}
    READS[info["path"]] = info
    return info


def read(path):
    assert path.name not in {"raw.json", "assessment.json"}
    bind(path)
    return json.loads(path.read_text())


frozen = {
    "m3_methods.py": "d6bbdcf90825e4d2a18fd36ae5fd4aee9d83c14648557af2e690566ea5e7ea73",
    "service_relations.py": "291d49a653f3ba95498b1a85efbcaac75dacbf35b37429005f767062e4b67709",
    "dynamic_methods.py": "b14312f24bb3e0c0ac57036a68f54b2eb4930a432b85a5b0ee28bc89dc7f7033",
    "dynamic_relations.py": "a6e75e19511b90f08e645b549f62e2784d0ffc1167714b18199637b08d415cea",
    "m2_methods.py": "6368f921ffb3afacd8c0c25ca5c32dfdbe1bb7c10c4d1fec6eeeca24188e118e",
    "decision_methods.py": "7e116f64705b0c4748b8e0cc109599e1740ca95b3f24336bbc5306122cd534fb",
    "episode_methods.py": "c4aeb3bf17e5f11076c9147a75d194e3ec0dcfe850592b58d744f1b5889b25c8",
    "methods.py": "260da9338be02a906070e78ca8ee4dc97c13839a524b9627835cdd87d07d5750",
    "decision_facts.py": "0b8996c2ee52325dc433eed3c054caf242e30105c48d1530b6ef21f2587f9a37",
}
for name, expected in frozen.items():
    assert bind(SRC / name)["sha256"] == expected, name

batch = read(S0 / "batch-result.json")
ledger = read(S0 / "resource-ledger.json")
derived = read(S0 / "action-ledger-reconstruction.json")
chain = read(S0 / "episodes/m3-u/chain.json")
assert batch["status"] == "COMPLETE_FINITE_TWO_TRACKS"
assert len(chain["rows"]) == 2 and len(derived["actions"]) == 3
assert derived["science_model_cheap_reruns"] == 0
assert batch["tracks"][1]["error"] == "ValueError:LOCAL_PUBLIC_PROJECTION_BYTES_CAP_PRE_FORWARD"
assert ledger["full_dynamic_inputs"] == 5 and ledger["cheap_scores"] == 22
assert ledger["native_inputs"] == ledger["hardware_runs"] == 0
assert ledger["post_participant_result_revisions"] == 0
assert batch["provider_before"]["historical_unknown_sha256"] == batch["provider_after"]["historical_unknown_sha256"]
assert batch["provider_before"]["statuses"]["UNKNOWN"] == batch["provider_after"]["statuses"]["UNKNOWN"] == 1

actions = []
for number in range(1, 4):
    prefix = S0 / f"episodes/m3-u/actions/{number:02d}"
    inp = read(prefix.with_name(prefix.name + "-input.json"))
    decision_file = read(prefix / "decision.json")
    result = read(prefix / "public-result.json")
    receipt = read(prefix / "readback.json")
    decision = inp["decision"]
    assert decision == decision_file["decision"]
    actual = {**inp["design"], **decision["actual_input"]["design_patch"]}
    assert actual == result["design"] == decision_file["actual_design"]
    if actions:
        assert inp["design"] == actions[-1]["actual_design"]
    assert actual["mechanism"] == {"cam_base_radius_m": 0.008, "stroke_m": 0.006}
    assert result["model_valid"] and result["domain_errors"] == []
    assert result["public_check"] == receipt["public_check"]
    assert result["public_check"]["verdict"] == "FAIL"
    assert bind(prefix / "public-result.json")["sha256"] == receipt["public_result"]["sha256"]
    assert bind(prefix / "public-result.json")["sha256"] == derived["actions"][number-1]["public_result"]["sha256"]
    assert bind(prefix.with_name(prefix.name + "-input.json"))["sha256"] == derived["actions"][number-1]["input"]["sha256"]
    facts = result["facts"]
    counts = dict(Counter(row["action"] for row in facts["activity"]))
    assert counts == receipt["activity_counts"]
    assert counts["save_commit"] == len(facts["records"]) == 6
    assert counts.get("tx_begin", 0) == len(facts["packets"]) == len(facts["receiver_records"]) == 0
    assert len(facts["program_state"]["nvm"]["queue"]) == 6
    assert receipt["timely_matches"] == 0
    pred = decision["selected_candidate"]["service_prediction"]
    service = pred["service_prediction"]
    metrics = pred["selection_metrics"]
    assert pred["service_feedback"]["consumed"] is True
    assert service["conditional_timely_windows"] == metrics["conditional_ack_completed_windows"] == service["unknown_windows"] == 0
    assert len(service["windows"]) == 6
    assert {w["status"] for w in service["windows"]} == {"GATE_NOT_REACHED_BY_DEADLINE_IN_MODEL"}
    assert all(w["attempts"] == [] for w in service["windows"])
    bound = next(x["value"]["bus_upper_v"] for x in pred["relations"] if x["relation_id"] == "passive_bus_upper_bound")
    maximum = max(row["capacitor_v"] for row in facts["trace"])
    assert maximum < actual["tx_gate_v"]
    alternatives = []
    for candidate in decision["alternatives"]:
        m = candidate["service_prediction"]["selection_metrics"]
        assert m["conditional_timely_windows"] == m["conditional_ack_completed_windows"] == m["unknown_windows"] == 0
        alternatives.append({"id": candidate["id"], "metrics": m})
    actions.append({"evaluation": number, "selected_id": decision["selected_id"],
                    "actual_input": decision["actual_input"], "actual_design": actual,
                    "public_result": bind(prefix / "public-result.json"),
                    "model_valid": True, "public_check": result["public_check"],
                    "activity_counts": counts, "timely": 0, "final_queue": 6,
                    "max_sampled_capacitor_v": maximum, "passive_bus_upper_bound_v": bound,
                    "gate_above_passive_upper_bound": actual["tx_gate_v"] > bound,
                    "selected_prediction_metrics": metrics,
                    "selected_window_status": "GATE_NOT_REACHED_BY_DEADLINE_IN_MODEL",
                    "service_feedback": pred["service_feedback"],
                    "selection_basis": decision["selection_basis"],
                    "priority": decision["expected_discrimination_or_gain"]["priority"],
                    "alternatives": alternatives})
assert len({json.dumps(a["actual_design"], sort_keys=True) for a in actions}) == 3
assert [a["gate_above_passive_upper_bound"] for a in actions] == [False, True, True]
assert actions[2]["actual_input"]["design_patch"] == {"retry_s": 0.01}

gchain = read(S0 / "episodes/m3-g/chain.json")
tool_counts = dict(Counter(x["request"]["name"] for x in gchain["public_tool_call_log"]))
assert tool_counts == {"public_object": 5, "public_detail": 2, "service_facts": 1}
assert all(x["status"] == "OK" for x in gchain["public_tool_call_log"])
cost = read(S0 / "episodes/m3-g/provider-costs.json")
assert cost["requests"] == 3 and cost["unknown_or_missing_usage"] == []
assert all(x["status"] == "SETTLED" for x in cost["rows"])
third = read(S0 / "episodes/m3-g/callbacks/03/callback-result.json")
assert third["dispatch_facts"]["forwarded"] is True and third["error"] == "PI_STOP_REASON"
pi_path = S0 / "episodes/m3-g/callbacks/03/pi-public.jsonl"
bind(pi_path)
pi = [json.loads(line) for line in pi_path.read_text().splitlines()]
assistant = next(x for x in pi if x["type"] == "assistant_public")
assert assistant["content"] == [] and assistant["stopReason"] == "length"
usage = [json.loads(row["usage"]) for row in cost["rows"]]
assert usage[2]["completion_tokens"] == usage[2]["completion_tokens_details"]["reasoning_tokens"] == 32768
assert batch["tracks"][0]["evaluations_including_reuse"] == batch["tracks"][0]["cheap_scores"] == 0

engineering = []
for number in [1, 2]:
    path = S0 / f"engineering/{number:02d}/public-result.json"
    result, receipt = read(path), read(path.with_name("readback.json"))
    assert result["model_valid"] and len(result["facts"]["receiver_records"]) == 5
    assert receipt["timely_matches"] == 3 and result["public_check"]["verdict"] == "FAIL"
    engineering.append({"public_result": bind(path), "model_valid": True,
                        "received_independently_counted": 5, "S0_public_readback_timely": 3,
                        "public_check": result["public_check"]})

out = {"package": batch["package"], "at": datetime.now(timezone.utc).isoformat(),
       "status": "SAVED_PUBLIC_ARTIFACT_READBACK_PASS", "worker": "B",
       "claim": "Manual service-policy formation changed actions, without timely-service gain in three executed choices.",
       "actions": actions, "generic": {"tool_counts": tool_counts, "evaluations": 0, "cheap_scores": 0,
          "settled_requests": 3, "prompt_tokens": sum(x["prompt_tokens"] for x in usage),
          "completion_tokens": sum(x["completion_tokens"] for x in usage),
          "third_stop_reason": assistant["stopReason"], "third_public_content_count": 0,
          "third_completion_tokens": 32768, "third_reasoning_tokens": 32768,
          "rate_estimate_usd": cost["cache_aware_rate_estimate_usd"],
          "estimate_not_invoice": True, "comparison_complete": False},
       "serialization_boundary": {"original_chain_rows": 2, "completed_canonical_actions": 3,
          "original_error_retained": batch["tracks"][1]["error"],
          "derived_index_only": True, "third_full_state_not_claimed": True},
       "engineering_review_after_method_freeze": engineering,
       "frozen_sources": frozen, "S0_resource_ledger": bind(S0 / "resource-ledger.json"),
       "historical_unknown_unchanged": True,
       "worker_new_calls": {"model": 0, "predictor": 0, "dynamic_consumer": 0, "native": 0, "tests": 0},
       "private_raw_or_assessment_files_read": False,
       "available_bytes_at_audit": shutil.disk_usage(ROOT).free,
       "sources": sorted(READS.values(), key=lambda x: x["path"])}
dest = B / "FINAL-CHAIN-READBACK.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": out["status"], "output": str(dest), "bytes": dest.stat().st_size,
                  "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()}, ensure_ascii=False))
