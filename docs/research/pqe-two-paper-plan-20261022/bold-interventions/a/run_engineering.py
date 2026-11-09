"""Frozen eight-cell engineering batch and one separately bounded DOOR initial.

No model, cheap scorer, hook or auxiliary scientific probe is called. A child
process enforces each complete-consumer wall limit and is never retried.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

A = Path(__file__).resolve().parent
ROOT = A.parents[4]
CAN = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(CAN / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261023bold import consumer
from bfworld.agentlab.pqe20261022.executor import identity


def load(path):
    return json.loads(Path(path).read_text())


def bind(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def save(path, value, exclusive=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def checked(ref):
    actual = bind(ref["path"])
    if actual != ref:
        raise ValueError("FILE_BINDING_CHANGED:" + ref["path"])
    return load(ref["path"])


def frozen():
    freeze = load(A / "ENGINEERING-FREEZE.json")
    if consumer.source_identity() != freeze["shared_sources"]:
        raise RuntimeError("FROZEN_CONSUMER_CHANGED")
    checked(freeze["engineering_case_source"]) if False else None
    if bind(freeze["engineering_case_source"]["path"]) != freeze["engineering_case_source"]:
        raise RuntimeError("FROZEN_CASE_SOURCE_CHANGED")
    return freeze, checked(freeze["tasks"])


def readback(output, label):
    raw, assessment, public = [load(output / name) for name in
                                ("raw.json", "assessment.json", "public-result.json")]
    decision = load(output / "decision.json")
    assert identity({k: v for k, v in raw.items() if k != "result_sha256"}) == raw["result_sha256"]
    assert raw["result_sha256"] == public["result_sha256"]
    assert raw["design"] == public["design"] == decision["actual_design"]
    assert raw["task_sha256"] == public["task_sha256"] == decision["task_sha256"]
    assert public["sources"] == consumer.source_identity() == decision["sources"]
    assert assessment["verdict"] == public["public_check"]["verdict"]
    for key in ("trace", "activity", "records", "packets", "energy", "program_state"):
        assert public["facts"][key] == raw[key]
    activity = Counter(row["action"] for row in raw["activity"])
    phases = raw["program_state"]["phase_energy_j"]
    assert sum(phases.values()) <= raw["energy"]["load_j"] + 1e-10
    match_seq = {row["seq"] for row in assessment["matches"]}
    valid_arrivals = [row["time_s"] for row in assessment["receiver_records"] if row["seq"] in match_seq]
    row = {"cell": label, "status": "COMPLETE", "task_id": public["task_id"],
           "task_sha256": raw["task_sha256"], "design": raw["design"],
           "design_sha256": raw["design_sha256"], "model_valid": raw["model_valid"],
           "domain_errors": raw["domain_errors"], "verdict": assessment["verdict"],
           "failures": assessment["failures"], "unknown": assessment["unknown"],
           "truth_count": len(assessment["truth"]), "timely_count": len(assessment["matches"]),
           "first_valid_delivery_s": min(valid_arrivals) if valid_arrivals else None,
           "first_received_s": min((x["time_s"] for x in assessment["receiver_records"]), default=None),
           "save_count": len(raw["records"]),
           "unique_saved_sequence_count": len({x["seq"] for x in raw["records"]}),
           "saved_sequence_order": [x["seq"] for x in raw["records"]],
           "received_count": len(assessment["receiver_records"]),
           "tx_attempts": activity.get("tx_begin", 0), "ack_count": activity.get("ack_commit", 0),
           "brownout_count": activity.get("brownout", 0),
           "brownout_modes": dict(Counter(x["during"] for x in raw["activity"] if x["action"] == "brownout")),
           "tx_supply_energy_j": phases["TX"], "phase_supply_energy_j": phases,
           "phase_branch_loss_j": raw["program_state"]["phase_esr_j"],
           "energy_j": raw["energy"], "remaining_queue": raw["remaining_queue"],
           "queue_count": len(raw["remaining_queue"]),
           "peak_handle_force_n": raw["peak_handle_force_n"],
           "minimum_tx_terminal_v": raw["minimum_tx_terminal_v"],
           "mechanical_residual_j": assessment["mechanical_residual_j"],
           "storage_residual_j": assessment["storage_residual_j"],
           "energy_tolerance_j": assessment["energy_tolerance_j"],
           "adaptive_backoff_events": activity.get("adaptive_backoff", 0),
           "consumer_wall_s": public["usage"]["wall_s"], "new_full_inputs": 1,
           "binding": {name: bind(output / name) for name in
                       ("decision.json", "raw.json", "assessment.json", "public-result.json")}}
    save(output / "readback.json", row)
    return row


def execute_cell(index):
    freeze, tasks = frozen()
    case_index, task_index = divmod(index, 2)
    case = freeze["cases"][case_index]
    task = list(tasks.values())[task_index]
    label = f"{index+1:02d}-{case['id']}-t{task_index+1}"
    decision = {"selected_id": case["id"], "actual_input": {
        "operation": "edit", "design_patch": deepcopy(case["design"]), "problem_patch": {}}}
    output = A / "engineering" / label
    consumer.execute(task, task["initial_design"], task["initial_problem"], decision,
                     output_dir=output, task_resolver=lambda task_id: tasks[task_id])
    row = readback(output, label)
    print(json.dumps(row, ensure_ascii=False))


def child_initial():
    frozen()
    freeze = load(A / "host/TASK-FREEZE.json")
    task = checked(freeze["door"])
    output = A / "host/door-initial"
    decision = {"selected_id": "shared-initial-only", "actual_input": {"operation": "observe"}}
    consumer.execute(task, task["initial_design"], task["initial_problem"], decision,
                     output_dir=output, task_resolver=lambda task_id: task if task_id == task["task_id"] else None)
    print(json.dumps(readback(output, "door-common-initial"), ensure_ascii=False))


def run_child(mode, index=None):
    command = [sys.executable, "-B", str(Path(__file__).resolve()), mode]
    if index is not None:
        command.append(str(index))
    started = time.monotonic()
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=120,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        if done.returncode:
            result = {"status": "TOOL_ERROR", "returncode": done.returncode,
                      "stderr": done.stderr[-8000:], "stdout": done.stdout[-2000:],
                      "new_full_inputs_reserved": 1, "retry": False}
        else:
            result = json.loads(done.stdout)
    except subprocess.TimeoutExpired as exc:
        result = {"status": "WALL_LIMIT", "wall_limit_s": 120,
                  "new_full_inputs_reserved": 1, "retry": False,
                  "stderr": str(exc.stderr or "")[-2000:]}
    result["wall_s"] = time.monotonic() - started
    return result


def engineering_batch():
    freeze, tasks = frozen()
    entry = A / "ENGINEERING-LEDGER.json"
    free = shutil.disk_usage(ROOT).free
    assert free >= 11_000_000_000
    ledger = {"package": freeze["package"], "at_utc": datetime.now(timezone.utc).isoformat(),
              "freeze": bind(A / "ENGINEERING-FREEZE.json"), "script": bind(__file__),
              "complete": False, "reserved_inputs": 0, "full_inputs": 0,
              "wall_s": 0.0, "consumer_wall_s": 0.0, "model_calls": 0, "cheap_calls": 0,
              "available_before_bytes": free, "rows": []}
    save(entry, ledger)
    for index in range(8):
        frozen()
        assert ledger["wall_s"] < 4080
        ledger["reserved_inputs"] += 1
        save(entry, ledger, exclusive=False)
        result = run_child("--cell", index)
        ledger["rows"].append(result)
        ledger["wall_s"] += result["wall_s"]
        ledger["consumer_wall_s"] += result.get("consumer_wall_s", 0.0)
        ledger["full_inputs"] += result.get("new_full_inputs", 0)
        save(entry, ledger, exclusive=False)
        print(json.dumps({key: result.get(key) for key in
                         ("cell", "status", "verdict", "timely_count", "save_count",
                          "received_count", "tx_attempts", "queue_count", "wall_s")}), flush=True)
    ledger["complete"] = True
    ledger["available_after_bytes"] = shutil.disk_usage(ROOT).free
    ledger["retained_A_bytes"] = sum(p.stat().st_size for p in A.rglob("*") if p.is_file())
    assert ledger["retained_A_bytes"] < 80_000_000
    save(entry, ledger, exclusive=False)
    save(A / "ENGINEERING-RESULTS.json", {
        "schema": "bold-A-engineering-results-v1", "package": freeze["package"],
        "freeze": ledger["freeze"], "ledger": bind(entry), "rows": ledger["rows"],
        "full_inputs": ledger["full_inputs"], "reserved_inputs": ledger["reserved_inputs"],
        "wall_s": ledger["wall_s"], "consumer_wall_s": ledger["consumer_wall_s"],
        "model_calls": 0, "cheap_calls": 0, "post_result_revision": 0,
        "scope": "One fixed four-design/two-condition constructed-world development comparison. Joint changes do not isolate individual causes; no hardware or automatic-learning claim."})


def initial():
    frozen()
    output = A / "host/DOOR-INITIAL-RECEIPT.json"
    claim = output.with_name("DOOR-INITIAL-CLAIM.json")
    save(claim, {"at_utc": datetime.now(timezone.utc).isoformat(), "reserved_inputs": 1,
                 "wall_limit_s": 120, "frozen": bind(A / "host/TASK-FREEZE.json"),
                 "no_retry": True, "available_before_bytes": shutil.disk_usage(ROOT).free})
    result = run_child("--initial")
    save(output, result)
    print(json.dumps({"status": result["status"], "receipt": bind(output),
                      "new_full_inputs": result.get("new_full_inputs", 0)}))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "engineering":
        engineering_batch()
    elif mode == "initial-door":
        initial()
    elif mode == "--cell":
        execute_cell(int(sys.argv[2]))
    elif mode == "--initial":
        child_initial()
    else:
        raise ValueError("UNKNOWN_RUN_MODE")
