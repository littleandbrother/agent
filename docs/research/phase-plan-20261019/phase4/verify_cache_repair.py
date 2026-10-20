#!/usr/bin/env python3
"""Qualified readback of existing data only; no paid calls or simulation."""
import copy
import json
from pathlib import Path
import runpy
import tempfile
import zlib

d = runpy.run_path(str(Path(__file__).with_name("execute.py")))
OUT, PLAN = d["OUT"], d["PLAN"]
load, seal, file_hash = d["load"], d["seal"], d["file_hash"]
spec = next(s for s in d["protocol"]["episodes"] if s["id"] == "L1-G0-h1-selection-b-pulse-fast")
engine = d["engine"](spec)
world, candidate = spec["world"], {"capacitance_f": 22e-6, "tx_not_before_s": 0}
entry = load(OUT / "initial-cache.json")[engine.key(world, candidate)]
original = load(entry["result_path"])
raw = engine.raw(world, original)
assessed = engine.assess(world, candidate, raw)
historical = engine.historical / "cases" / world
old = load(historical / "result.json")
assert assessed["energy"] == old["energy"]
assert assessed["reference"] == old["reference"]
assert assessed["complete_service"] == "PASS"
reference_task, reference_result, reference_energy = engine.checker.read_case(historical)
assert reference_task == engine.execution_input(world, candidate)
assert assessed["energy"] == reference_energy and assessed["reference"] == reference_result
checks = [{"name": "exact_historical_22uF_TX0_enters_assess", "status": "PASS",
           "service": assessed["complete_service"], "energy": assessed["energy"]["verdict"],
           "trace_steps": len(raw["trace"]), "reference_unchanged": True}]

effective_keys = ("complete_service", "energy", "reference", "ordered_event_state", "query_service", "evaluator_version")
reused = []
for path in sorted((OUT / "episodes").glob("*/episode-result.json")):
    result = load(path)
    if result["spec"]["stage"] != "selection" or result["status"] != "ACTUAL_PROSPECTIVE_SUBMITTED":
        continue
    prior = result["external_result"]["execution"]
    e = d["engine"](result["spec"])
    unchanged_raw = json.loads(zlib.decompress(Path(prior["raw_path"]).read_bytes()))
    loaded_raw = e.raw(result["spec"]["world"], prior)
    assert loaded_raw == unchanged_raw
    after = e.assess(result["spec"]["world"], prior["design"], loaded_raw)
    assert all(after[k] == prior[k] for k in effective_keys)
    reused.append({"episode": result["episode"], "result_sha256": file_hash(path),
                   "raw_sha256": file_hash(prior["raw_path"]), "service": prior["complete_service"]})
assert len(reused) == 5
checks.append({"name": "compressed_raw_and_all_five_valid_selections_unchanged", "status": "PASS", "episodes": reused})

def rejects(label, operation, expected):
    try:
        operation()
    except ValueError as error:
        assert expected in str(error), str(error)
        checks.append({"name": label, "status": "PASS", "host_error": str(error)})
    else:
        raise AssertionError("Expected host error: " + label)

with tempfile.TemporaryDirectory(prefix="bf-p4-trace-readback-") as temp:
    tmp = Path(temp)
    case = tmp / "cases" / world
    case.mkdir(parents=True)
    source_rows = [r for r in load(engine.historical / "seal.json")["files"]
                   if r["path"] in (f"cases/{world}/{n}" for n in ("input.json", "observations.json", "trace.csv"))]
    (tmp / "seal.json").write_text(json.dumps({"files": source_rows}))
    for name in ("input.json", "observations.json"):
        (case / name).symlink_to(historical / name)
    broken = copy.copy(engine)
    broken.historical = tmp
    rejects("missing_trajectory", lambda: broken.raw(world, original), "HISTORICAL_SOURCE_MISSING:trace.csv")
    (case / "trace.csv").symlink_to(historical / "trace.csv")
    bad_rows = copy.deepcopy(source_rows)
    next(r for r in bad_rows if r["path"].endswith("trace.csv"))["sha256"] = "0" * 64
    (tmp / "seal.json").write_text(json.dumps({"files": bad_rows}))
    rejects("wrong_trajectory_binding", lambda: broken.raw(world, original), "HISTORICAL_SOURCE_BINDING_MISMATCH:trace.csv")
    (tmp / "seal.json").write_text(json.dumps({"files": source_rows}))
    wrong = copy.deepcopy(original)
    wrong["design"]["capacitance_f"] = 20e-6
    rejects("wrong_exact_input", lambda: broken.raw(world, wrong), "HISTORICAL_EXACT_INPUT_MISMATCH")
rejects("wrong_world", lambda: engine.raw("b-volatile-reset", original), "HISTORICAL_RESPONSE_WORLD_MISMATCH")

seal(PLAN / "cache-repair-qualification.json", {
    "status": "PASS", "amendment_id": "phase4-cache-trace-amendment-20261020-001",
    "checks": checks, "new_provider_requests": 0, "new_simulations": 0,
    "temporary_copy_policy": "Only tiny manifest and symlinks in automatically removed temporary directory",
    "adapter_sha256": file_hash(d["APP"] / "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase4.py"),
})
print(json.dumps({"status": "PASS", "checks": len(checks), "reused_valid_selections": len(reused),
                  "new_provider_requests": 0, "new_simulations": 0}))
