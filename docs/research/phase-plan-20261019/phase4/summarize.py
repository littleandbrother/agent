#!/usr/bin/env python3
"""Read closed actual records, not live provider outputs or new simulations."""
import json
from pathlib import Path
import runpy

d = runpy.run_path(str(Path(__file__).with_name("execute.py")))
OUT, PLAN, load, seal = d["OUT"], d["PLAN"], d["load"], d["seal"]
records = [load(p) for p in sorted((OUT / "episodes").glob("*/episode-result.json"))]
totals = d["r"].used_totals(records)
skips = [load(p) for p in sorted((OUT / "not-dispatched").glob("*.json"))]
cache = load(OUT / "physical-cache/index.json")
new = [v for v in cache.values() if v.get("origin") == "phase4-new-full-response"]
rows = []
for result in records:
    spec = result["spec"]
    sub = result.get("external_result", {})
    usage = d["usage"](result)
    rows.append({"episode": result["episode"], "kind": spec["kind"], "stage": spec["stage"],
        "lineage": spec.get("lineage"), "arm": spec.get("arm"), "condition": spec.get("condition"),
        "child": spec.get("child"), "task": spec.get("world"), "slot": spec.get("slot"),
        "status": result["status"], "service": sub.get("execution", {}).get("complete_service"),
        "participant_judgment": sub.get("service_judgment"),
        "wrong_service_judgment": sub.get("wrong_service_judgment"),
        "proposal_decision": sub.get("proposal", {}).get("decision"), "usage": usage,
        "result_path": str(OUT / "episodes" / result["episode"] / "episode-result.json"),
        "result_sha256": d["file_hash"](OUT / "episodes" / result["episode"] / "episode-result.json")})
complete = len(rows) + len(skips) == len(d["protocol"]["episodes"])
arms = {}
for lineage in (1, 2, 3):
    for arm in ("G0", "G1"):
        name = f"L{lineage}-{arm}"
        own = [x for x in rows if x["lineage"] == lineage and x["arm"] == arm]
        allocated = {"requests": 0, "wall_s": 0, "usd": 0}
        if arm == "G1" and (OUT / "G1-formation-accounting.json").exists():
            a = load(OUT / "G1-formation-accounting.json")["allocations"][lineage - 1]
            allocated = {"requests": a["requests"], "wall_s": a["wall_s"], "usd": a["settled_upper_usd"]}
        finals = [x for x in own if x["stage"] == "final"]
        arms[name] = {"actual_episodes": len(own), "formation_share": allocated,
            "full_requests": sum(x["usage"]["requests"] for x in own) + allocated["requests"],
            "full_wall_s": sum(x["usage"]["wall_s"] for x in own) + allocated["wall_s"],
            "full_usd": sum(x["usage"]["usd"] for x in own) + allocated["usd"],
            "final_passes": sum(x["service"] == "PASS" for x in finals), "final_slots": len(finals),
            "final_wrong_judgments": sum(x["wrong_service_judgment"] is True for x in finals)}
value = {"status": "ALL_PROSPECTIVE_CELLS_ACCOUNTED" if complete else "IN_PROGRESS",
    "actual_episodes": len(rows), "not_dispatched_cells": len(skips), "registered_cells": 73,
    "accounting": totals, "new_scientific_executions": len(new),
    "incomplete_physical_executions": sum(v.get("status") == "STARTED" for v in new),
    "native_dispatches": 0, "new_unknown_usage": [], "rows": rows, "arms": arms,
    "not_dispatched": skips, "default_H0_changed": False, "G1_formation_events": 1 if d["get"]("G1-formation") else 0,
    "physical_qualification": "UNKNOWN", "full_end_to_end_cost": "UNKNOWN",
    "cost_boundary": "All actual participant provider proposal/selection/design/failure/confirmation calls included; Codex assistance unpriced, provider rate estimates not invoices.",
    "lineage_boundary": "Three fresh descendant-lineage pairs conditional on one shared G1 formation; not three independent G1 training events or hardware trials."}
if complete:
    seal(PLAN / "actual-results.json", value)
print(json.dumps({k: v for k, v in value.items() if k in ("status", "actual_episodes", "not_dispatched_cells", "accounting", "new_scientific_executions", "arms")}, ensure_ascii=False), flush=True)
