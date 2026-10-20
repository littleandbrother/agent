#!/usr/bin/env python3
"""Read back actual causal G/H parents before selection; no model/physics runs."""
from pathlib import Path
import runpy

d = runpy.run_path(str(Path(__file__).with_name("execute.py")))
OUT, PLAN = d["OUT"], d["PLAN"]
load, seal, file_hash, digest = d["load"], d["seal"], d["file_hash"], d["digest"]
formed = d["g1"]()
bound = {}
for name in ("G1-freeze.json", "G1-formation-accounting.json", "semantic-audit.json"):
    path = OUT / name
    bound[str(path)] = file_hash(path)
g = d["get"]("G1-formation")
if formed["eligible"]:
    submitted = OUT / "episodes/G1-formation/scientific/submission.json"
    assert g["external_result"] == load(submitted)
    assert formed["proposal_procedure"] == g["external_result"]["proposal"]["proposal_procedure"]
    bound[str(submitted)] = file_hash(submitted)
    bound[str(OUT / "episodes/G1-formation/episode-result.json")] = file_hash(OUT / "episodes/G1-formation/episode-result.json")
rows = []
for spec in d["protocol"]["episodes"]:
    if spec["stage"] != "proposal":
        continue
    result = d["get"](spec["id"])
    if result is None:
        notice = OUT / "not-dispatched" / (spec["id"] + ".json")
        assert notice.exists()
        bound[str(notice)] = file_hash(notice)
        rows.append({"episode": spec["id"], "status": load(notice)["status"]})
        continue
    root = OUT / "episodes" / spec["id"]
    packet = load(root / "participant-payload.json")
    procedure = d["parents"]["G0"]["proposal_procedure"] if spec["arm"] == "G0" else formed["proposal_procedure"]
    assert packet == d["proposal_payload"]("H", procedure), spec["id"]
    if result["status"] == "ACTUAL_PROSPECTIVE_SUBMITTED":
        submitted = root / "scientific/submission.json"
        assert result["external_result"] == load(submitted), spec["id"]
        d["semantic"](spec["id"])
        bound[str(submitted)] = file_hash(submitted)
    for name in ("episode-result.json", "participant-payload.json", "protocol.json", "provider-costs.json", "pi-public-trace.jsonl"):
        path = root / name
        bound[str(path)] = file_hash(path)
    assert result["fresh_task_entry"] and not result["accounting"]["unknown_or_missing_usage"]
    rows.append({"episode": spec["id"], "status": result["status"],
                 "H0_sha256": d["parents"]["H0"]["method_sha256"],
                 "assigned_G_procedure_sha256": digest(procedure),
                 "model_history_sha256": d["m"].MODEL_HISTORY_SHA256,
                 "proposed_H_sha256": result.get("external_result", {}).get("proposal", {}).get("method_sha256")})
assert len(rows) == 12
assert not any((OUT / "episodes" / s["id"]).exists() for s in d["protocol"]["episodes"] if s["stage"] == "final")
seal(PLAN / "parent-freeze.json", {"status": "ACTUAL_G_H_PARENTS_READ_BACK_BEFORE_SELECTION", "rows": rows,
     "bound_files": bound, "default_H0_changed": False, "final_results_consulted": False,
     "parent_scope": "Actual immutable proposal inputs, original submissions, provider costs and fresh-context traces; no manual rewrite or resampling.",
     "provider_requests_for_readback": 0, "scientific_executions_for_readback": 0})
print({"parent_rows": len(rows), "bound_files": len(bound), "status": "PASS"})
