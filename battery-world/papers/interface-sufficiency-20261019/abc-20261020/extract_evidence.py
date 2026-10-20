#!/usr/bin/env python3
"""Extract small paper views from sealed ABC receipts; never import an evaluator."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import zlib


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n")


def extract(root, paper):
    source = root/"docs/research/abc-cycle-20261020"
    data = paper/"data"
    data.mkdir(exist_ok=True)
    manifest = []
    def read(path):
        path = Path(path)
        manifest.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)})
        return json.loads(path.read_text())
    report_path = source/"shared/B-formal18-v1.json"
    assert sha(report_path) == "a9826ad1e510ba4eb433d917f3e672d15a74dcadadd0ccaef0263ce9438225c5"
    report = read(report_path)
    index = read(source/"RESULT-INDEX.json")
    audit = read(source/"shared/final-input-audit.json")
    review = read(source/"reviews/ABC-BC-formal-core-v1.json")
    first = read(source/"shared/B-first-legal-consumption-v1.json")
    product = read(source/"shared/A-finite-negative-v1.json")
    methods = read(source/"shared/C-formal24-v1.json")
    rows = [r for r in index["rows"] if r["package"] == "interfaces" and r["stage"] == "formal"]
    assert len(rows) == 18 and report["finished_attempts"] == 18
    assert index["finished_model_episodes"] == index["planned_model_episodes"] == 48
    arms = ("complete_information", "fixed_rule", "observation_refinement")
    fields = ("episode_id", "task_id", "arm", "status", "requests", "charge_upper_usd", "wall_s",
              "context_payload_bytes", "actual_artifact_submitted", "coverage", "prediction_correct",
              "decision_correct", "selected_service", "real_typed_consumer", "scientific_executions",
              "exact_input_cache_reuses", "evaluated_input_count")
    csvrows = []
    for row in rows:
        value = {k: row[k] for k in fields}
        value.update({k: row["costs"][k] for k in ("acquisition_read_bytes", "preflight_calls", "rejected_actions", "tool_wall_s")})
        value.update({"input_tokens": row["tokens"]["input"], "output_tokens": row["tokens"]["output"],
                      "reasoning_tokens": row["tokens"]["reasoning"], "cached_input_tokens": row["tokens"]["cached_input"]})
        value.update({"result_path": row["result_path"], "result_sha256": row["result_sha256"]})
        csvrows.append(value)
    with (data/"formal-episodes.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(csvrows[0])); writer.writeheader(); writer.writerows(csvrows)
    for arm in arms:
        subset = [r for r in rows if r["arm"] == arm]
        assert len(subset) == 6
        expected = report["arms"][arm]
        for key in ("requests", "scientific_executions", "exact_input_cache_reuses", "evaluated_input_count"):
            assert sum(r[key] for r in subset) == expected[key]
        for key in ("real_typed_consumer", "prediction_correct", "decision_correct"):
            assert sum(r[key] for r in subset) == expected[key]
        assert all(r["actual_artifact_submitted"] and r["selected_service"] == "PASS" for r in subset)
        assert sum(r["costs"]["acquisition_read_bytes"] for r in subset) == expected["acquisition_read_bytes"]
        assert abs(sum(r["charge_upper_usd"] for r in subset)-expected["charge_upper_usd"]) < 1e-12
    mechanisms, trace_by_key, trace_sources, consumed = {}, {}, {}, []
    for family in ("storage-connection", "reset-placement", "package-response"):
        row = next(r for r in rows if r["task_id"] == family and r["arm"] == "complete_information" and r["episode_id"].endswith("r1"))
        result = read(row["result_path"])
        assert sha(row["result_path"]) == row["result_sha256"]
        ep = Path(row["result_path"]).parent
        actual_spec = read(ep/"attempt.json")["spec"]
        freeze = read(actual_spec["frozen_families"])
        assert sha(actual_spec["frozen_families"]) == actual_spec["frozen_families_sha256"]
        case = freeze["cases"][family]
        mechanism = {"case": case, "roles": {}}
        for decision in ("retain", "adopt"):
            key = result["independent_result"]["execution_keys"][decision]
            execution = next(read(p) for p in sorted((ep/"host/executions").glob("*.json")) if json.loads(p.read_text())["execution_key"] == key)
            path = Path(execution["raw_path"])
            raw = json.loads(zlib.decompress(path.read_bytes()))
            assert raw["input_sha256"] == execution["input_sha256"]
            role = "current" if decision == "retain" else "intervention"
            assert raw["task"] == case[role]
            mechanism["roles"][decision] = {"execution_key": key, "input_sha256": execution["input_sha256"],
                "truth": result["independent_result"]["truth"][decision], "reference": execution["reference"],
                "energy": execution["energy"], "activity": raw["run"]["activity"]}
            trace_by_key[key] = raw["run"]["trace"]
            trace_sources[key] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}
        mechanisms[family] = mechanism
    for row in rows:
        if row["real_typed_consumer"]:
            result = read(row["result_path"])
            consumer = result["independent_result"]["submission"]["consumer"]
            consumed.append({"episode_id": row["episode_id"], "arm": row["arm"], "task_id": row["task_id"], "consumer": consumer})
    with (data/"saved-traces.csv").open("w", newline="") as f:
        writer = csv.writer(f); writer.writerow(("execution_key", "time_s", "voltage_v", "loaded_v", "source_w", "event_captured", "powered"))
        for key, trace in sorted(trace_by_key.items()):
            for row in trace:
                writer.writerow((key, *(row[k] for k in ("time_s", "voltage_v", "loaded_v", "source_w", "event_captured", "powered"))))
    dump(data/"mechanisms.json", mechanisms)
    dump(data/"typed-consumers.json", consumed)
    summary = {"B": report["arms"], "B_accounting": report["accounting"], "audit": audit,
        "development_rehearsal": {k: first[k] for k in ("model_requests", "model_cost_usd", "conclusion", "physical_qualification")},
        "development_result": {k: first["independent_result"][k] for k in ("truth", "coverage", "prediction_correct", "decision_correct", "selected_service", "real_typed_consumer")},
        "A": {k: product[k] for k in ("status", "concepts", "actual_candidate_inputs", "new_original_service_task_executions", "engineering_acceptance", "physical_qualification", "conclusion")},
        "A_case_service": {k: v["all_applicable_computational_services"] for k, v in product["original_service_result"]["cases"].items()},
        "C": methods["arms"], "cycle_accounting": index["completed_accounting_only"],
        "cycle_finished_episodes": index["finished_model_episodes"], "core_review": review["decision"],
        "scientific_runs_by_this_script": 0}
    dump(data/"aggregate.json", summary)
    dump(data/"source-manifest.json", {"sources": list({v["path"]: v for v in manifest}.values()), "saved_trace_sources": trace_sources,
        "scope": "Read-only extraction from sealed results. No simulator, qualifier, consumer, evaluator, SDK, or provider is imported or invoked. Old final/data is not copied."})
    print(json.dumps({"formal_rows": len(rows), "unique_saved_trace_inputs": len(trace_by_key), "typed_receipts": len(consumed), "new_scientific_runs": 0}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--paper", type=Path, default=Path(__file__).resolve().parent)
    args = p.parse_args(); extract(args.root.resolve(), args.paper.resolve())
