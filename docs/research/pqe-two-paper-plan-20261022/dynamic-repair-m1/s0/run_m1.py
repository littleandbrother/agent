"""Bounded developer engineering chain through the unchanged public consumer.

No model backend is imported or called. Prediction is never an independent PASS.
All full dynamic inputs, including failed/timeout attempts, use one serial ledger.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
BASE = ROOT / "docs/research/pqe-two-paper-plan-20261022"
HERE = Path(__file__).resolve().parent
OUT = HERE.parent
SOURCE = APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import adapter
from bfworld.agentlab.pqe20261022.executor import identity
from bfworld.agentlab.pqe20261022.methods import common_contract_check
from bfworld.agentlab.pqe20261022.public_projection import scientific_source_identity, project_result

PACKAGE = "BF-PQE-DYNAMIC-REPAIR-M1-20261023-001"
DB = Path("/Users/depengsu/.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite")
METHOD_FILES = (SOURCE / "dynamic_relations.py", SOURCE / "dynamic_methods.py")


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    return {"path": str(path), "sha256": sha(path)}


def checked(ref):
    if sha(ref["path"]) != ref["sha256"]:
        raise ValueError("BOUND_FILE_CHANGED:" + ref["path"])
    return read(ref["path"])


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n")


def provider_snapshot():
    with sqlite3.connect("file:" + str(DB) + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        row = dict(db.execute("SELECT * FROM model_requests WHERE id=?",
                             ("llm-1de4d60d9bc93d257392",)).fetchone())
        return {"total": db.execute("SELECT count(*) FROM model_requests").fetchone()[0],
                "inflight": db.execute("SELECT count(*) FROM model_requests WHERE status='DISPATCHED'").fetchone()[0],
                "historical_unknown_sha256": hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()}


def capacity():
    fs = os.statvfs(ROOT)
    free = fs.f_bavail * fs.f_frsize
    used = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    if free < 10_800_000_000 or used >= 80_000_000:
        raise ValueError("STORAGE_RESOURCE_GATE")
    return {"at": now(), "available_bytes": free, "retained_logical_bytes": used,
            "estimated_peak_additional_bytes": 800_000_000,
            "retained_cap_bytes": 80_000_000}


def frozen_inputs():
    path = OUT / "shared/frozen-inputs.json"
    if path.exists():
        return read(path)
    old = read(BASE / "stage3-update-continue/shared/protocol.json")
    common = checked(old["common_input"])
    original = checked(old["external_failure"])
    task = checked(old["old_task"])
    if identity(task) != original["task_sha256"]:
        raise ValueError("ORIGINAL_TASK_IDENTITY")
    value = {"package": PACKAGE, "created_at": now(), "old_protocol": bind(BASE / "stage3-update-continue/shared/protocol.json"),
             "common_input": old["common_input"], "task": old["old_task"],
             "initial_failure": old["external_failure"], "scientific_source": old["scientific_source"],
             "original_source_bindings": old["source_bindings"],
             "physical_initialization": "Each candidate runs the complete unchanged Task from original physical initial state, not prior waveform/charge/state replay.",
             "visibility": "Method receives only the original public state plus public executed results; host raw/assessment stay in S0.",
             "initial_provider_snapshot": provider_snapshot(), "initial_capacity": capacity(),
             "new_experiment_model_requests": 0, "new_usd": 0}
    save(path, value)
    return value


def validate(frozen, attempt=None):
    for p, h in frozen["original_source_bindings"].items():
        if sha(p) != h:
            raise ValueError("OLD_METHOD_OR_SCIENCE_CHANGED:" + p)
    if scientific_source_identity(adapter.source_identity()) != frozen["scientific_source"]:
        raise ValueError("SCIENTIFIC_CONSUMER_CHANGED")
    if attempt:
        for ref in [attempt["caller"], *attempt["new_method_sources"]]:
            if sha(ref["path"]) != ref["sha256"]:
                raise ValueError("NEW_METHOD_CHANGED_DURING_ATTEMPT:" + ref["path"])


def cache_match(task, design, dt_s, frozen):
    # Only exact candidates already autonomously/programmatically submitted are
    # looked up. Cache contents never serve as a candidate parameter table.
    paths = sorted((BASE / "stage3-e3lc/s0").glob("episodes/scope-*/actions/*/public-result.json"))
    paths += sorted((BASE / "stage3-e3lc/s0").glob("opt/*/*/public-result.json"))
    paths += sorted((BASE / "stage3-decision-consequence/s0/executions").glob("*/public-result.json"))
    paths += sorted((BASE / "stage3-update-continue/s0/episodes").glob("*/actions/*/public-result.json"))
    paths += sorted(HERE.glob("attempts/*/actions/*/public-result.json"))
    for path in paths:
        p = read(path)
        if (p.get("task_sha256") == identity(task) and p.get("design") == design and
                scientific_source_identity(p["sources"]) == frozen["scientific_source"]):
            raw = path.parent / "raw.json"
            if raw.exists() and read(raw)["dt_s"] == dt_s:
                return path
    return None


def child(input_file):
    job = read(input_file)
    frozen = read(OUT / "shared/frozen-inputs.json")
    attempt = read(job["attempt_file"])
    validate(frozen, attempt)
    task = checked(frozen["task"])
    public = adapter.execute(task, job["design"], job["problem"], job["decision"],
                             job["output_dir"],
                             task_resolver=lambda ident: task if ident == task["task_id"] else None)
    validate(frozen, attempt)
    print(json.dumps({"public_check": public["public_check"], "model_valid": public["model_valid"]}))


def execute(decision, state, task, frozen, attempt, folder, ledger):
    common_contract_check(state, decision["actual_input"], {"remaining_actions": 12})
    actual = decision["actual_input"]
    design = {**state["design"], **actual.get("design_patch", {})}
    problem = {**state["problem"], **actual.get("problem_patch", {})}
    adapter.validate_design(task, design)
    dt = actual.get("dt_s", task["integration"]["dt_s"])
    cached = cache_match(task, design, dt, frozen)
    item = {"at": now(), "decision_sha256": identity(decision), "design_sha256": identity(design),
            "exact_cache": cached is not None, "full_dynamic_inputs": 0}
    if cached:
        public = read(cached)
        public["problem"] = deepcopy(problem)
        public = project_result(public)
        source_dir = cached.parent
        folder.mkdir(parents=True, exist_ok=False)
        save(folder / "reuse.json", {"source_public_result": bind(cached), "current_problem": problem,
                                     "same_task_design_dt_and_science": True})
        save(folder / "public-result.json", public)
    else:
        capacity()
        if ledger["full_dynamic_inputs"] >= 12 or ledger["full_dynamic_wall_s"] >= 1800:
            raise ValueError("GLOBAL_FULL_DYNAMIC_CAP")
        # Reservation precedes execution; killed/failed attempts remain counted.
        ledger["full_dynamic_inputs"] += 1
        item["full_dynamic_inputs"] = 1
        job = {"design": state["design"], "problem": state["problem"], "decision": decision,
               "output_dir": str(folder), "attempt_file": str(folder.parents[1] / "binding.json")}
        input_file = folder.parent / (folder.name + "-input.json")
        save(input_file, job)
        save(HERE / "resource-ledger.json", ledger)
        start = time.monotonic()
        proc = subprocess.Popen([sys.executable, "-B", __file__, "_execute", str(input_file)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        try:
            stdout, stderr = proc.communicate(timeout=min(120, 1800 - ledger["full_dynamic_wall_s"]))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, stderr = proc.communicate()
            item["error"] = "FULL_DYNAMIC_TIMEOUT"
        item["wall_s"] = time.monotonic() - start
        ledger["full_dynamic_wall_s"] += item["wall_s"]
        ledger["attempts"].append(item)
        save(HERE / "resource-ledger.json", ledger)
        if proc.returncode or item.get("error"):
            save(folder.parent / (folder.name + "-error.json"), {**item, "stderr_tail": stderr[-4000:]})
            raise ValueError(item.get("error", "FULL_DYNAMIC_ERROR:" + stderr[-1000:]))
        public = read(folder / "public-result.json")
        source_dir = folder
    raw, assessment = read(source_dir / "raw.json"), read(source_dir / "assessment.json")
    raw_hash = raw["result_sha256"]
    if (identity({k: v for k, v in raw.items() if k != "result_sha256"}) != raw_hash
            or public["result_sha256"] != raw_hash or public["design"] != design
            or public["task_sha256"] != identity(task)
            or assessment["verdict"] != public["public_check"]["verdict"]):
        raise ValueError("INDEPENDENT_RESULT_BINDING_FAILED")
    item.update(public_result=bind(folder / "public-result.json"), raw=bind(source_dir / "raw.json"),
                assessment=bind(source_dir / "assessment.json"), model_valid=raw["model_valid"],
                domain_errors=raw["domain_errors"], public_check=public["public_check"],
                activity_counts=dict(Counter(x["action"] for x in raw["activity"])),
                minimum_tx_terminal_v=raw["minimum_tx_terminal_v"],
                records=len(raw["records"]), packets=len(raw["packets"]))
    save(folder / "readback.json", item)
    validate(frozen, attempt)
    return public, item


def charge_scores(method, before, ledger):
    spent = method.analytic_score_count - before
    reserved = sum(ledger["worker_analytic_reserved"].values())
    if spent < 0 or ledger["cheap_scores_S0"] + spent + reserved > 128:
        raise ValueError("GLOBAL_CHEAP_SCORE_CAP")
    ledger["cheap_scores_S0"] += spent
    save(HERE / "resource-ledger.json", ledger)
    return spent


def run(revision_reason=None):
    from bfworld.agentlab.pqe20261022.dynamic_methods import DynamicRepairHarness
    frozen = frozen_inputs()
    validate(frozen)
    ledger = read(HERE / "resource-ledger.json")
    if (HERE / "batch-result.json").exists() and read(HERE / "batch-result.json").get("status") == "PASS_FINITE_ENGINEERING_CHAIN":
        raise ValueError("ALREADY_COMPLETE_NO_REPEAT")
    attempts = sorted((HERE / "attempts").glob("*/binding.json"))
    if attempts:
        if not revision_reason or ledger["algorithm_revisions"] >= 2:
            raise ValueError("REVISION_REASON_OR_CAP")
        prior = read(attempts[-1])
        if [sha(p) for p in METHOD_FILES] == [r["sha256"] for r in prior["new_method_sources"]]:
            raise ValueError("NO_CHANGED_ALGORITHM_NO_REPEAT")
        ledger["algorithm_revisions"] += 1
    target = HERE / "attempts" / f"{len(attempts) + 1:02d}"
    target.mkdir(parents=True, exist_ok=False)
    attempt = {"package": PACKAGE, "at": now(), "revision_reason": revision_reason,
               "caller": bind(__file__), "new_method_sources": [bind(p) for p in METHOD_FILES],
               "frozen_inputs": bind(OUT / "shared/frozen-inputs.json"), "capacity": capacity()}
    save(target / "binding.json", attempt)
    save(HERE / "resource-ledger.json", ledger)
    lock = HERE / "active.lock"
    with lock.open("x") as stream:
        stream.write(str(os.getpid()))
    rows, status, error = [], "FINITE_CONDITIONAL_EXIT", None
    try:
        task, common = checked(frozen["task"]), checked(frozen["common_input"])
        method = DynamicRepairHarness()
        method.quota = {"remaining_actions": 12, "remaining_cost": 12, "max_candidates": 64,
                        "analytic_scores_left": 128 - sum(ledger["worker_analytic_reserved"].values())
                        - ledger["cheap_scores_S0"]}
        if not attempts:
            state = deepcopy(common["state_before_external"])
            before_count = method.analytic_score_count
            state = method.update(state, common["external_decision"], checked(frozen["initial_failure"]))
            charge_scores(method, before_count, ledger)
            save(target / "external-update.json", {"state_after": state, "loaded_program_calls": method.program.calls})
        else:
            state = read(HERE / "state-current.json")
        save(HERE / "state-current.json", state)
        for step in range(1, 4):
            validate(frozen, attempt)
            worker_reserved = sum(ledger["worker_analytic_reserved"].values())
            quota = {"remaining_actions": 12 - ledger["full_dynamic_inputs"], "remaining_cost": 12,
                     "max_candidates": 64,
                     "analytic_scores_left": 128 - worker_reserved - ledger["cheap_scores_S0"]}
            before_count = method.analytic_score_count
            before_state = deepcopy(state)
            batch = method.generate(state, quota)
            decision = method.select(state, batch, quota)
            spent = charge_scores(method, before_count, ledger)
            row = {"step": step, "state_before": before_state, "generate": batch, "select": decision,
                   "new_cheap_scores": spent}
            if decision.get("status") != "READY":
                row["finite_stop"] = decision.get("status")
                rows.append(row)
                break
            result, consequence = execute(decision, state, task, frozen, attempt,
                                           target / "actions" / f"{step:02d}", ledger)
            before_count = method.analytic_score_count
            state = method.update(state, decision, result)
            update_scores = charge_scores(method, before_count, ledger)
            row.update(result=result, consequence=consequence, state_after=state)
            row["update_cheap_scores"] = update_scores
            rows.append(row)
            save(target / "chain.json", {"rows": rows, "loaded_program_calls": method.program.calls})
            save(HERE / "state-current.json", state)
            print(json.dumps({"step": step, "actual_input": decision["actual_input"],
                              "public_check": result["public_check"],
                              "new_dynamic": consequence["full_dynamic_inputs"], "cheap_scores": spent}), flush=True)
            if result["model_valid"] and result["public_check"]["verdict"] == "PASS":
                status = "PASS_FINITE_ENGINEERING_CHAIN"
                before_count = method.analytic_score_count
                retention = method.generate(state, {**quota, "analytic_scores_left":
                    128 - worker_reserved - ledger["cheap_scores_S0"]})
                retention_scores = charge_scores(method, before_count, ledger)
                save(target / "pass-retention.json", {"state_sha256": identity(state),
                     "result_sha256": result["result_sha256"], "generated": retention,
                     "new_cheap_scores": retention_scores,
                     "retains_pass_without_new_action": not retention.get("candidates")})
                if retention.get("candidates"):
                    raise ValueError("PASS_CONTROL_UNNECESSARY_NEW_ACTION")
                break
        validate(frozen, attempt)
    except Exception as exc:
        status, error = "STOPPED_WITH_RETAINED_FAILURE", repr(exc)
    finally:
        lock.unlink(missing_ok=True)
        save(target / "chain.json", {"rows": rows, "loaded_program_calls": method.program.calls if 'method' in locals() else [],
                                      "status": status, "error": error})
        save(HERE / "batch-result.json", {"package": PACKAGE, "status": status, "error": error,
             "attempt": bind(target / "binding.json"), "chain": bind(target / "chain.json"),
             "completed_at": now(), "resource_ledger": bind(HERE / "resource-ledger.json"),
             "provider_before": frozen["initial_provider_snapshot"], "provider_after": provider_snapshot(),
             "storage": capacity(), "autonomous_agent_episode": False,
             "claim_boundary": "Developer-fixed engineering execution in the exposed computational Task; no automatic H learning, efficacy, transfer or hardware claim."})
    print(json.dumps({"package": PACKAGE, "status": status, "error": error}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["run", "_execute"], nargs="?", default="run")
    parser.add_argument("input_file", nargs="?")
    parser.add_argument("--revision-reason")
    args = parser.parse_args()
    if args.mode == "_execute":
        child(args.input_file)
    else:
        run(args.revision_reason)
