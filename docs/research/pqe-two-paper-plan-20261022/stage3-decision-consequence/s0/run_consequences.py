"""Two exact saved-action consequences. No model/episode/provider entry point."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import adapter, pilot
from bfworld.agentlab.pqe20261022.executor import identity
from bfworld.agentlab.pqe20261022.methods import digest, common_contract_check
from bfworld.agentlab.pqe20261022.public_projection import scientific_source_identity

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
BASE = OUT.parent
PACKAGE = "BF-PQE-S3-DECISION-CONSEQUENCE-20261023-001"
CASES = ("common_initial_r2_pool", "after_r2_first_failure")


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    return {"path": str(path), "sha256": sha(path)}


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def checked(ref):
    if sha(ref["path"]) != ref["sha256"]:
        raise ValueError("FROZEN_INPUT_CHANGED:" + ref["path"])
    return read(ref["path"])


def freeze():
    path = HERE / "frozen-inputs.json"
    if path.exists():
        raise ValueError("ALREADY_FROZEN_NO_REPLACEMENT")
    old = read(APP / "studies/pqe20261022/decision/shared/protocol.json")
    gate = checked(old["behavior_gate"])
    behavior = checked(gate["behavior"])
    for ref in behavior["source_bindings"]:
        if sha(ref["path"]) != ref["sha256"]:
            raise ValueError("FROZEN_METHOD_CHANGED")
    r2 = checked(behavior["source_public_bindings"]["r2"])
    steps = [s for s in r2["steps"] if s.get("result")]
    e3 = read(APP / "studies/pqe20261022/e3lc/shared/protocol.json")
    registry = checked(e3["private_registry"])
    task_ref = registry["roles"]["scope"]
    task = checked({"path": task_ref["task_path"], "sha256": task_ref["task_file_sha256"]})
    if identity(task) != task_ref["task_sha256"]:
        raise ValueError("ORIGINAL_CONSUMER_TASK_CHANGED")
    sources = adapter.source_identity()
    if scientific_source_identity(sources) != old["scientific_source"]:
        raise ValueError("ORIGINAL_SCIENCE_CHANGED")
    rows = []
    for name, state, step, action_no in (
        (CASES[0], r2["initial_state"], steps[0], "01"),
        (CASES[1], steps[1]["state_before"], steps[1], "02"),
    ):
        action = next(r for r in behavior["rows"] if r["case"] == name)
        if digest(state) != action["public_state_sha256"] or pilot.public_task(task) != state["task"]:
            raise ValueError("PUBLIC_STATE_RESTORE_MISMATCH")
        if action["old_actual_input"] != step["select"]["actual_input"]:
            raise ValueError("ORIGINAL_ACTION_MISMATCH")
        actual = deepcopy(action["new_actual_input"])
        if common_contract_check(state, actual, {"remaining_actions": 1}) != actual:
            raise ValueError("CANONICAL_ACTION_CHANGED")
        parent = Path(behavior["source_public_bindings"]["r2"]["path"]).parent
        prior = parent / "actions" / action_no / "public-result.json"
        if read(prior)["result_sha256"] != step["result"]["result_sha256"]:
            raise ValueError("ORIGINAL_RESULT_BINDING_MISMATCH")
        rows.append({"case": name, "task": {"path": task_ref["task_path"], "sha256": task_ref["task_file_sha256"]},
            "task_sha256": identity(task), "public_state_sha256": action["public_state_sha256"],
            "design": state["design"], "problem": state["problem"],
            "actual_input": actual, "selected_candidate": action["new_candidate"],
            "updated_design": {**state["design"], **actual.get("design_patch", {})},
            "updated_problem": {**state["problem"], **actual.get("problem_patch", {})},
            "original_actual_input": action["old_actual_input"], "original_public_result": bind(prior)})
    manifest = {"package": PACKAGE, "behavior": gate["behavior"],
        "r2_transcript": behavior["source_public_bindings"]["r2"], "script": bind(__file__),
        "method_bindings": behavior["source_bindings"], "source_identity": sources,
        "cases": rows, "provider_requests": 0, "episodes": 0, "usd": 0,
        "new_numerical_inputs_cap": 2, "per_input_wall_s": 120, "execution_wall_s_total": 600,
        "physical_initialization": "Each design executes the complete original frozen Task schedule from its physical initial state; no previous source waveform, final voltage or firmware snapshot is replayed."}
    save(path, manifest)
    return {"frozen": bind(path), "cases": list(CASES)}


def validate(manifest):
    if sha(__file__) != manifest["script"]["sha256"] or adapter.source_identity() != manifest["source_identity"]:
        raise ValueError("FROZEN_EXECUTION_PATH_CHANGED")
    checked(manifest["behavior"])
    for ref in manifest["method_bindings"]:
        if sha(ref["path"]) != ref["sha256"]:
            raise ValueError("FROZEN_METHOD_CHANGED")


def cache_match(case, sources):
    """Lookup only the original Task's saved public action cache, no scans."""
    old = BASE / "stage3-e3lc/s0"
    paths = sorted(old.glob("episodes/scope-*/actions/*/public-result.json"))
    paths += sorted(old.glob("opt/*/*/public-result.json"))
    for path in paths:
        public = read(path)
        if (public.get("task_sha256") != case["task_sha256"] or
                public.get("design") != case["updated_design"] or
                scientific_source_identity(public["sources"]) != scientific_source_identity(sources)):
            continue
        raw_path = path.parent / "raw.json"
        if not raw_path.exists():
            continue
        raw = read(raw_path)
        task = checked(case["task"])
        if raw["dt_s"] == case["actual_input"].get("dt_s", task["integration"]["dt_s"]):
            return path
    return None


def child(case_path):
    manifest = read(HERE / "frozen-inputs.json")
    validate(manifest)
    case = checked(read(case_path))
    task = checked(case["task"])
    public = adapter.execute(task, case["design"], case["problem"],
        {"selected_id": case["selected_candidate"]["id"],
         "selected_candidate": case["selected_candidate"], "actual_input": case["actual_input"],
         "origin": "FROZEN_SAVED_FIXED_H_ACTION_CONSEQUENCE_NOT_NEW_AGENT_EPISODE"},
        HERE / "executions" / case["case"], task_resolver=lambda ident: task if ident == task["task_id"] else None)
    print(json.dumps({"case": case["case"], "status": public["execution_status"], "public_check": public["public_check"]}))


def run():
    manifest = read(HERE / "frozen-inputs.json")
    validate(manifest)
    with (HERE / "run-claim.json").open("x") as f:
        json.dump({"pid": os.getpid(), "frozen": bind(HERE / "frozen-inputs.json"), "retry": False}, f)
    started, rows = time.monotonic(), []
    for case in manifest["cases"]:
        validate(manifest)
        case_path = HERE / "inputs" / (case["case"] + ".json")
        save(case_path, case)
        launch_path = HERE / "inputs" / (case["case"] + "-binding.json")
        save(launch_path, bind(case_path))
        cached = cache_match(case, manifest["source_identity"])
        record = {"case": case["case"], "input": bind(case_path), "new_numerical_inputs": 0,
                  "exact_reuse": cached is not None, "original_public_result": case["original_public_result"]}
        before = time.monotonic()
        if cached is None:
            timeout = min(120, 600 - (before - started))
            if timeout <= 0:
                raise ValueError("TOTAL_EXECUTION_TIME_CAP")
            record["new_numerical_inputs"] = 1
            proc = subprocess.Popen([sys.executable, "-B", __file__, "_execute", str(launch_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    stdout, stderr = proc.communicate()
                record["status"] = "EXECUTION_TIMEOUT_UNKNOWN"
            if proc.returncode or record.get("status"):
                record.setdefault("status", "TOOL_ERROR_UNKNOWN")
                record["error"] = stderr[-4000:]
            cached = HERE / "executions" / case["case"] / "public-result.json"
        if cached.exists() and not record.get("status"):
            public = read(cached)
            raw_path = cached.parent / "raw.json"
            raw, assessment = read(raw_path), read(cached.parent / "assessment.json")
            result_sha = raw.pop("result_sha256")
            if (identity(raw) != result_sha or public["result_sha256"] != result_sha or
                    public["task_sha256"] != case["task_sha256"] or public["design"] != case["updated_design"] or
                    public["public_check"]["verdict"] != assessment["verdict"]):
                raise ValueError("ACTUAL_INPUT_OR_SAVED_RESULT_MISMATCH")
            record.update(status="COMPLETE_SAVED_ACTION_CONSEQUENCE", public_result=bind(cached),
                raw=bind(raw_path), independent_assessment=bind(cached.parent / "assessment.json"),
                model_valid=public["model_valid"], domain_errors=public["domain_errors"],
                service=public["public_check"], activity_counts=dict(Counter(e["action"] for e in public["facts"]["activity"])),
                source_bus_j=public["facts"]["energy"]["source_bus_j"], load_j=public["facts"]["energy"]["load_j"],
                record_count=len(public["facts"]["records"]), packet_count=len(public["facts"]["packets"]))
        record["wall_s"] = time.monotonic() - before
        rows.append(record)
        save(HERE / "batch-result.json", {"package": PACKAGE, "status": "RUNNING", "cases": rows})
        print(json.dumps(record, ensure_ascii=False), flush=True)
    validate(manifest)
    final = {"package": PACKAGE, "status": "FINITE_TWO_ACTIONS_COMPLETE", "cases": rows,
        "wall_s": time.monotonic() - started, "new_numerical_inputs": sum(r["new_numerical_inputs"] for r in rows),
        "exact_reuses": sum(r["exact_reuse"] for r in rows), "provider_requests": 0,
        "episodes": 0, "usd": 0, "new_method_selection": False,
        "claim_boundary": "Two saved fixed-H actions on exposed development states; no autonomous discovery, baseline superiority, unseen transfer or physical claim."}
    save(HERE / "batch-result.json", final)
    return final


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "run", "readback", "_execute"))
    parser.add_argument("input", nargs="?")
    args = parser.parse_args()
    if args.command == "_execute":
        child(args.input)
    elif args.command == "readback":
        print(json.dumps(read(HERE / "batch-result.json"), ensure_ascii=False))
    else:
        print(json.dumps(globals()[args.command](), ensure_ascii=False))
