#!/usr/bin/env python3
"""Read all actual costs and explicit v1.1 canonical attempt dispositions."""
import json
from pathlib import Path
import runpy

d = runpy.run_path(str(Path(__file__).with_name("execute_v11.py")))
OUT, PLAN, load, seal = d["OUT"], d["PLAN"], d["load"], d["seal"]
records = [load(p) for p in sorted((OUT / "episodes").glob("*/episode-result.json"))]
totals = d["r"].used_totals(records)
skips = [load(p) for p in sorted((OUT / "not-dispatched").glob("*.json"))]
cache = load(OUT / "physical-cache/index.json")
new = [v for v in cache.values() if v.get("origin") == "phase4-new-full-response"]
original_faults = set(d["recoveries"])

def row(result):
    spec = result["spec"]
    sub = result.get("external_result", {})
    return {"episode": result["episode"], "canonical_episode": spec.get("recovery_of", result["episode"]),
        "kind": spec["kind"], "stage": spec["stage"], "lineage": spec.get("lineage"),
        "arm": spec.get("arm"), "condition": spec.get("condition"), "child": spec.get("child"),
        "task": spec.get("world"), "slot": spec.get("slot"), "status": result["status"],
        "adapter_revision": result.get("adapter_revision", "1"), "recovery_of": spec.get("recovery_of"),
        "host_incident_overhead": result["episode"] in original_faults,
        "service": sub.get("execution", {}).get("complete_service"),
        "participant_judgment": sub.get("service_judgment"),
        "wrong_service_judgment": sub.get("wrong_service_judgment"),
        "proposal_decision": sub.get("proposal", {}).get("decision"), "usage": d["usage"](result),
        "result_path": str(OUT / "episodes" / result["episode"] / "episode-result.json"),
        "result_sha256": d["file_hash"](OUT / "episodes" / result["episode"] / "episode-result.json")}

rows = [row(r) for r in records]
canonical_specs = [s for s in d["protocol"]["episodes"] if not s.get("recovery_of")]
canonical_rows = [row(r) for s in canonical_specs if (r := d["get"](s["id"]))]
complete = len(canonical_rows) + len(skips) == 73 and len(rows) + len(skips) == 77
arms = {}
for lineage in (1, 2, 3):
    for arm in ("G0", "G1"):
        name = f"L{lineage}-{arm}"
        own = [x for x in rows if x["lineage"] == lineage and x["arm"] == arm]
        effective = [x for x in own if not x["host_incident_overhead"]]
        incident = [x for x in own if x["host_incident_overhead"]]
        allocated = {"requests": 0, "wall_s": 0, "usd": 0}
        if arm == "G1":
            a = load(OUT / "G1-formation-accounting.json")["allocations"][lineage - 1]
            allocated = {"requests": a["requests"], "wall_s": a["wall_s"], "usd": a["settled_upper_usd"]}
        finals = [x for x in effective if x["stage"] == "final"]
        arms[name] = {"actual_episodes": len(own), "effective_episodes": len(effective), "formation_share": allocated,
            "full_requests": sum(x["usage"]["requests"] for x in own) + allocated["requests"],
            "full_wall_s": sum(x["usage"]["wall_s"] for x in own) + allocated["wall_s"],
            "full_usd": sum(x["usage"]["usd"] for x in own) + allocated["usd"],
            "effective_requests": sum(x["usage"]["requests"] for x in effective) + allocated["requests"],
            "effective_usd": sum(x["usage"]["usd"] for x in effective) + allocated["usd"],
            "host_incident_requests": sum(x["usage"]["requests"] for x in incident),
            "host_incident_usd": sum(x["usage"]["usd"] for x in incident),
            "final_passes": sum(x["service"] == "PASS" for x in finals), "final_slots": len(finals),
            "final_wrong_judgments": sum(x["wrong_service_judgment"] is True for x in finals)}

incident_records = [r for r in records if r["episode"] in original_faults]
value = {"status": "ALL_PROSPECTIVE_CELLS_ACCOUNTED" if complete else "IN_PROGRESS",
    "amendment_id": d["protocol"]["amendment_id"], "protocol_sha256": d["file_hash"](PLAN / "protocol-v1.1.json"),
    "actual_episodes": len(rows), "effective_canonical_cells": len(canonical_rows),
    "registered_cells": 73, "registered_attempts": 77, "not_dispatched_cells": len(skips),
    "accounting": totals, "host_incident_overhead": d["r"].used_totals(incident_records),
    "new_scientific_executions": len(new),
    "incomplete_physical_executions": sum(v.get("status") == "STARTED" for v in new),
    "native_dispatches": sum(r.get("native_dispatches", 0) for r in records), "new_unknown_usage": [],
    "rows": rows, "canonical_rows": canonical_rows, "arms": arms, "not_dispatched": skips,
    "recovery_attempts": d["recoveries"], "default_H0_changed": False,
    "G1_formation_events": sum(r["spec"]["kind"] == "G" for r in records),
    "physical_qualification": "UNKNOWN", "full_end_to_end_cost": "UNKNOWN",
    "cost_boundary": "All actual participant requests, including all original host faults/censoring, are in global/full-arm costs. Effective costs exclude only those four incident attempts; no omitted proposals, siblings, selection tasks or G1 formation. Provider estimates are not invoices; Codex assistance is unpriced.",
    "lineage_boundary": "Three descendant-lineage pairs conditional on one shared G1 formation, not independent G1 training replicates or hardware trials."}
if complete:
    target = PLAN / "actual-results.json"
    if target.exists():
        assert load(target) == value
    else:
        seal(target, value)
print(json.dumps({k: value[k] for k in ("status", "actual_episodes", "effective_canonical_cells", "accounting",
    "host_incident_overhead", "new_scientific_executions", "arms")}, ensure_ascii=False), flush=True)
