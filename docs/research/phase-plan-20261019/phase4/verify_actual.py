#!/usr/bin/env python3
"""One final source, causal-parent, cache and accounting readback; no reruns."""
from decimal import Decimal
import hashlib
from pathlib import Path
import runpy
import sqlite3

d = runpy.run_path(str(Path(__file__).with_name("execute_v11.py")))
OUT, PLAN, ROOT = d["OUT"], d["PLAN"], d["ROOT"]
load, seal, digest, file_hash = d["load"], d["seal"], d["digest"], d["file_hash"]
encoded = d["r"].encoded
result = load(PLAN / "actual-results.json")
assert result["status"] == "ALL_PROSPECTIVE_CELLS_ACCOUNTED"
from bfworld.agentlab.campaign20261019.phase4 import bindings_match
bindings_match(d["protocol"]["bound_files"])
bindings_match(load(PLAN / "parent-freeze.json")["bound_files"])
preserved = load(PLAN / "v1-source-preservation.json")
for old_path, meta in preserved["files"].items():
    assert file_hash(meta["archive_path"]) == meta["sha256"]
assert file_hash(d["protocol"]["previous_protocol"]["path"]) == d["protocol"]["previous_protocol"]["sha256"]
assert len(result["canonical_rows"]) + len(result["not_dispatched"]) == 73
selected = load(OUT / "selected-methods.json")
freeze = load(OUT / "final-selection-freeze.json")
assert freeze["status"] == "ALL_SIX_ARMS_FROZEN" and freeze["all_final_episodes_not_started"]
assert freeze["selected_methods_sha256"] == digest(selected) and len(selected) == 6
records = {x["episode"]: load(x["result_path"]) for x in result["rows"]}
assert len(records) + len(result["not_dispatched"]) == 77
assert set(records) <= {s["id"] for s in d["protocol"]["episodes"]}
ids, owners, used_keys = set(), set(), set()
dbpath = Path(d["protocol"]["provider_database"])
with sqlite3.connect(dbpath.as_uri() + "?mode=ro", uri=True) as db:
    db.row_factory = sqlite3.Row
    for record in records.values():
        root = OUT / "episodes" / record["episode"]
        spec = record["spec"]
        assert spec in d["protocol"]["episodes"]
        if record.get("owner"):
            assert record["owner"] not in owners
            owners.add(record["owner"])
        cost = load(root / "provider-costs.json")
        assert not cost["unknown_or_missing_usage"]
        actual = [dict(x) for x in db.execute(
            "SELECT id,status,reserved,charged,usage,response_hash,error FROM model_requests WHERE owner=? ORDER BY created,rowid",
            (record.get("owner"),))]
        assert actual == cost["rows"]
        for row in actual:
            assert row["id"] not in ids and row["status"] in ("SETTLED", "NOT_SENT")
            ids.add(row["id"])
        charge = sum((Decimal(str(x["charged"] or 0)) for x in actual if x["status"] == "SETTLED"), Decimal(0))
        assert abs(charge - Decimal(str(record["accounting"]["settled_charge_upper_bound_usd"]))) < Decimal("1e-12")
        if record["status"] == "ACTUAL_PROSPECTIVE_SUBMITTED":
            assert record["fresh_task_entry"] and record["reported_models"] == ["deepseek-flash"]
            assert record["trace_audit"]["model_submitted"] and not record["trace_audit"]["unmatched_executed_inputs"]
            assert record["external_result"] == load(root / "scientific/submission.json")
        if spec.get("recovery_of"):
            original_root = OUT / "episodes" / spec["recovery_of"]
            assert load(root / "participant-payload.json") == load(original_root / "participant-payload.json")
            assert record["initial_cache_sha256"] == load(original_root / "episode-result.json")["initial_cache_sha256"]
            limits = load(root / "protocol.json")["limits"]
            assert limits["model_requests"] == 12 and limits["wall_seconds"] == 800 and limits["candidates"] == 2
        if spec["stage"] == "final":
            assert load(root / "attempt.json")["started_unix"] >= (OUT / "final-selection-freeze.json").stat().st_mtime
        if spec["kind"] == "D":
            payload = load(root / "participant-payload.json")
            method = d["H0"]
            if spec["stage"] == "O-transfer":
                case = load(d["protocol"]["O_tasks"][spec["world"]]["input_path"])
                if spec["condition"] == "fixed-periodic": method += "\n\n" + d["o"].fixed_periodic(case)["method_text"]
                if spec["condition"] == "rich-state": method += "\n\n" + d["o"].rich_state(case)["method_text"]
            elif spec.get("arm") and spec["stage"] == "selection":
                parent = d["descendant"](spec)
                method += "\n\n" + parent["external_result"]["proposal"]["method_text"]
            elif spec.get("arm") and spec["stage"] == "final":
                method = selected[spec["arm_id"]]["selected_H_text"]
            assert payload["instruction"] == d["d_payload"](spec, method)["instruction"]
            overlay = OUT / "groups" / spec["id"] / "job-overlay.json"
            if overlay.exists():
                data = load(overlay)
                assert len(data["executed"]) <= 2
                assert data["initial_cache_sha256"] == file_hash(OUT / "initial-cache.json")
                used_keys.update(x["execution_key"] for x in data["executed"].values())
    h = hashlib.sha256()
    for row in db.execute("SELECT * FROM model_requests ORDER BY rowid LIMIT ?", (d["protocol"]["prior_ledger_prefix"]["rows"],)):
        h.update(encoded(dict(row)) + b"\n")
    assert h.hexdigest() == d["protocol"]["prior_ledger_prefix"]["sha256"]
assert len(ids) == result["accounting"]["requests"]
cache = load(OUT / "physical-cache/index.json")
cache_files = set()
for key in used_keys:
    entry = cache[key]
    assert entry.get("status") != "STARTED"
    bindings_match(entry["artifacts"])
    cache_files.update(entry["artifacts"])
    assert file_hash(entry["result_path"]) == entry["result_sha256"]
    old = load(entry["result_path"])
    if not old.get("raw_path"):
        historical = load(d["r"].HIST / "seal.json")
        hashes = {x["path"]: x["sha256"] for x in historical["files"]}
        for name in ("input.json", "observations.json", "trace.csv"):
            rel = "cases/" + old["world"] + "/" + name
            assert file_hash(d["r"].HIST / rel) == hashes[rel]
for name, value in selected.items():
    choice = load(OUT / "selections" / (name + ".json"))
    assert value["selected_H_text"] == choice["selected_H_text"]
    assert value["selected_H_sha256"] == digest(value["selected_H_text"])
    metrics = [x for x in choice["candidate_metrics"] if x["eligible"]]
    winner = min(metrics, key=lambda x: (-x["complete_service_passes"], x["wrong_service_judgments"], x["total_charged_requests"], x["descendant_index"])) if metrics else None
    assert choice["selected_descendant_index"] == (winner["descendant_index"] if winner else None)
    assert choice["final_results_consulted"] is False and choice["default_H0_changed"] is False
protected_before = load(ROOT / "docs/storage-deep-clean-20261020/protected-before.json")
local = Path.home() / ".local/share"
protected = {}
for label, path in {
    "production": local / "bf-agent-runtime/workbench/state/workbench.sqlite",
    "v2": local / "bf-agent-architecture-v2/workbench/state/workbench.sqlite",
    "historical": local / "bf-agent-runtime/reference-cases/literature-rsi-20261008/runtime/state/workbench.sqlite",
    "campaign": dbpath,
}.items():
    protected[label] = {}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        for table, meta in protected_before[label].items():
            if table == "status_counts": continue
            assert table in ("conversations", "model_requests", "design_projects")
            h, count = hashlib.sha256(), 0
            for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid LIMIT ?", (meta["rows"],)):
                h.update(encoded(dict(row)) + b"\n")
                count += 1
            assert count == meta["rows"] and h.hexdigest() == meta["sha256"], (label, table)
            protected[label][table] = {"rows": count, "sha256": h.hexdigest()}
receipt = {"status": "PASS", "actual_episodes": len(records),
    "registered_cells": 73, "registered_attempts": 77, "cache_amendment": d["protocol"]["amendment_id"], "provider_requests": len(ids), "used_physical_responses": len(used_keys),
    "cached_files_read_back": len(cache_files), "new_scientific_executions": result["new_scientific_executions"],
    "new_unknown_usage": 0, "old_unknown_records_preserved": 24, "prior_S0_prefix_unchanged": True,
    "protected": protected, "all_six_selections_frozen_before_final": True,
    "actual_H_and_final_payload_derivation": "PASS", "zero_new_models_or_science_for_readback": True,
    "verification_code_sha256": file_hash(Path(__file__))}
receipt_path = PLAN / "preservation-final.json"
if receipt_path.exists():
    assert load(receipt_path) == receipt
else:
    seal(receipt_path, receipt)
print({"status": "PASS", "actual_episodes": len(records), "requests": len(ids), "physical_keys": len(used_keys)})
