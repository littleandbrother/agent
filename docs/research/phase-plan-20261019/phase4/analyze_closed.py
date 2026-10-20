#!/usr/bin/env python3
"""Finite descriptive analysis of closed phase4 receipts; no execution or selection."""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

PLAN = Path(__file__).resolve().parent


def read(name):
    return json.loads((PLAN / name).read_text())


def charge(rows):
    return {
        "episodes": len(rows),
        "requests": sum(r["usage"]["requests"] for r in rows),
        "settled_upper_usd": str(sum((Decimal(str(r["usage"]["usd"])) for r in rows), Decimal(0))),
        "summed_wall_s": sum(r["usage"]["wall_s"] for r in rows),
    }


def outcomes(rows):
    return {
        "cells": len(rows),
        "PASS": sum(r["service"] == "PASS" for r in rows),
        "submitted_FAIL": sum(r["service"] == "FAIL" for r in rows),
        "incomplete": sum(r["status"] != "ACTUAL_PROSPECTIVE_SUBMITTED" for r in rows),
        "nominal_service_judgment_disagreements": sum(r["wrong_service_judgment"] is True for r in rows),
    }


def main():
    actual, final = read("actual-results.json"), read("final-details.json")
    assert actual["status"] == "ALL_PROSPECTIVE_CELLS_ACCOUNTED"
    assert actual["actual_episodes"] == 77 and actual["effective_canonical_cells"] == 73
    assert len(final["rows"]) == 27
    stages = {}
    for stage in sorted({r["stage"] for r in actual["rows"]}):
        stages[stage] = charge([r for r in actual["rows"] if r["stage"] == stage])
    assert sum(v["requests"] for v in stages.values()) == actual["accounting"]["requests"]
    assert abs(sum((Decimal(v["settled_upper_usd"]) for v in stages.values()), Decimal(0)) - Decimal(str(actual["accounting"]["settled_upper_usd"]))) < Decimal("1e-12")
    arms, tasks = {}, {}
    for arm in ("H0", "G0", "G1"):
        finals = [r for r in final["rows"] if r["arm"] == arm]
        arms[arm] = {**outcomes(finals), "final_cost": charge(finals)}
        if arm == "H0":
            all_h0 = [r for r in actual["rows"] if r["stage"] in ("selection", "final") and not r["arm"]]
            arms[arm]["selection_plus_final_cost"] = charge(all_h0)
        else:
            prefix = [v for k, v in actual["arms"].items() if k.endswith("-" + arm)]
            arms[arm]["full_pipeline_cost_including_incident_and_formation"] = {
                "requests": sum(v["full_requests"] for v in prefix),
                "settled_upper_usd": str(sum((Decimal(str(v["full_usd"])) for v in prefix), Decimal(0))),
                "summed_wall_s": sum(v["full_wall_s"] for v in prefix),
            }
            arms[arm]["effective_pipeline_cost_excluding_only_four_host_incidents"] = {
                "requests": sum(v["effective_requests"] for v in prefix),
                "settled_upper_usd": str(sum((Decimal(str(v["effective_usd"])) for v in prefix), Decimal(0))),
            }
    for task in sorted({r["task"] for r in final["rows"]}):
        tasks[task] = {arm: outcomes([r for r in final["rows"] if r["task"] == task and r["arm"] == arm]) for arm in arms}
    incomplete = []
    for r in final["rows"]:
        if r["status"] != "ACTUAL_PROSPECTIVE_SUBMITTED":
            metadata = r.get("last_assistant_metadata") or {}
            incomplete.append({"episode": r["episode"], "last_assistant_metadata": metadata,
                               "response_token_censored": metadata.get("stop_reason") == "length"})
    formation = [r for r in actual["rows"] if r["kind"] == "G"]
    descendants = [r for r in actual["rows"] if r["kind"] == "H"]
    assert len(formation) == 1 and len(descendants) == 12
    selection = [r for r in actual["canonical_rows"] if r["stage"] == "selection"]
    assert len(selection) == 30
    value = {
        "status": "CLOSED_DESCRIPTIVE_ANALYSIS", "actual_episodes": 77, "canonical_cells": 73,
        "actual_results_sha256": hashlib.sha256((PLAN / "actual-results.json").read_bytes()).hexdigest(),
        "final_details_sha256": hashlib.sha256((PLAN / "final-details.json").read_bytes()).hexdigest(),
        "stages_all_actual": stages, "G1_formation_cost": charge(formation), "all_12_H_cost": charge(descendants),
        "selection_effective": outcomes(selection), "final_arms": arms, "final_tasks": tasks,
        "lineage_groups": final["groups"], "incomplete_final_cells": incomplete,
        "all_final_status_counts": dict(Counter(r["status"] for r in final["rows"])),
        "all_accounting": actual["accounting"], "host_incident_overhead": actual["host_incident_overhead"],
        "default_H0_changed": False,
        "actual_new_scientific_executions": actual["new_scientific_executions"],
        "analysis_new_provider_requests": 0, "analysis_new_scientific_executions": 0,
        "physical_qualification": "UNKNOWN", "AR_product_acceptance": "NOT_ACCEPTED",
        "interpretation": "Descriptive results from three descendant-lineage pairs conditional on one G1 formation. No global H or improver promotion; no independent G1-training replication, physical qualification, or demonstrated RSI. Incomplete cells remain in denominators and all cost totals.",
        "cost_boundary": "All actual requests at fixed registered usage rates, including four original host incidents and four recoveries, unselected children and selection cells, G1 formation and censored calls. Not invoices or full end-to-end costs; Codex assistance and historical acquisition remain unpriced.",
        "analysis_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    target = PLAN / "analysis-summary.json"
    if target.exists():
        assert json.loads(target.read_text()) == value
    else:
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: value[k] for k in ("status", "final_arms", "selection_effective", "all_accounting")}))


if __name__ == "__main__":
    main()
