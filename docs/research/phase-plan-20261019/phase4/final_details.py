#!/usr/bin/env python3
"""Finite paper table from closed actual results; no models or simulations."""
import json
from pathlib import Path
import runpy
import zlib

d = runpy.run_path(str(Path(__file__).with_name("execute_v11.py")))
OUT, PLAN, load, seal = d["OUT"], d["PLAN"], d["load"], d["seal"]
source = load(PLAN / "actual-results.json")
assert source["status"] == "ALL_PROSPECTIVE_CELLS_ACCOUNTED"
rows = []
for ref in source["canonical_rows"]:
    if ref["stage"] != "final":
        continue
    record = load(ref["result_path"])
    sub = record.get("external_result", {})
    execution = sub.get("execution", {})
    row = {**ref, "arm": ref["arm"] or "H0", "design": execution.get("design"),
        "execution_key": execution.get("execution_key"), "reused_physical_response": execution.get("reused"),
        "initial_cache_hit": execution.get("job_accounting", {}).get("initial_cache_hit"),
        "energy": execution.get("energy", {}).get("verdict"), "reference": execution.get("reference"),
        "query_service": execution.get("query_service"), "reasons": execution.get("reasons"),
        "physical_qualification": execution.get("physical_qualification", "UNKNOWN"),
        "participant_reason": sub.get("reason")}
    group = OUT / "groups" / record["episode"] / "job-overlay.json"
    row["checked_designs"] = [x["candidate"] for x in load(group)["executed"].values()] if group.exists() else []
    if execution.get("per_event") is not None:
        raw = json.loads(zlib.decompress(Path(execution["raw_path"]).read_bytes()))
        packets = {p["seq"]: p for p in raw["packets"]}
        event_rows = []
        for event in execution["per_event"]:
            value = dict(event)
            if event["matched_seq"] is not None:
                decoded = d["o"]._decode(packets[event["matched_seq"]]["hex"])
                value["encoded_stamp_s"] = decoded["stamp_s"] if decoded["known"] else None
                value["absolute_stamp_error_s"] = abs(decoded["stamp_s"] - event["time_s"]) if decoded["known"] else None
            event_rows.append(value)
        row["O_events"] = {"expected": execution["expected_event_count"],
            "matched": execution["matched_event_count"], "accepted_packets": execution["accepted_packets"],
            "pass_count": sum(x["verdict"] == "PASS" for x in event_rows),
            "keepalive_gaps": execution["keepalive_gaps"], "per_event": event_rows}
    if record["status"] != "ACTUAL_PROSPECTIVE_SUBMITTED":
        summaries = []
        for session in (OUT / "episodes" / record["episode"] / "participant/.pi/phase1-sessions").glob("*.jsonl"):
            for line in session.read_text().splitlines():
                msg = json.loads(line).get("message", {})
                if msg.get("role") == "assistant":
                    summaries.append({"stop_reason": msg.get("stopReason"), "error": msg.get("errorMessage"),
                        "usage": msg.get("usage"), "content_types": [x.get("type") for x in msg.get("content", [])]})
        row["last_assistant_metadata"] = summaries[-1] if summaries else None
    rows.append(row)
assert len(rows) == 27
groups = {}
for lineage in (1, 2, 3):
    for arm in ("H0", "G0", "G1"):
        own = [r for r in rows if r["lineage"] == lineage and r["arm"] == arm]
        assert len(own) == 3
        groups[f"L{lineage}-{arm}"] = {"passes": sum(r["service"] == "PASS" for r in own),
            "submitted_failures": sum(r["service"] == "FAIL" for r in own),
            "incomplete": sum(r["status"] != "ACTUAL_PROSPECTIVE_SUBMITTED" for r in own),
            "judgment_disagreements": sum(r["wrong_service_judgment"] is True for r in own),
            "final_requests": sum(r["usage"]["requests"] for r in own),
            "final_usd": sum(r["usage"]["usd"] for r in own),
            "final_wall_s": sum(r["usage"]["wall_s"] for r in own)}
value = {"status": "CLOSED_FINAL27_READBACK", "actual_results_sha256": d["file_hash"](PLAN / "actual-results.json"),
    "rows": rows, "groups": groups, "default_H0_changed": False,
    "costs": {"all_attempts": source["accounting"], "host_incident_overhead": source["host_incident_overhead"],
              "full_and_effective_G_arms": source["arms"]},
    "judgment_boundary": "Nominal service three-way self-judgment disagreement is reported only where a submission exists. Missing submissions are separate, not zero-error successes. Physical qualification remains UNKNOWN.",
    "new_provider_requests": 0, "new_simulations": 0,
    "verification_code_sha256": d["file_hash"](Path(__file__))}
target = PLAN / "final-details.json"
if target.exists():
    assert load(target) == value
else:
    seal(target, value)
print(json.dumps({"status": value["status"], "groups": groups}, ensure_ascii=False))
