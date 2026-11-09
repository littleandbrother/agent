"""One bounded developer-method comparison over the existing dynamic consumer."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import time

from . import pilot as p
from .executor import identity
from .public_projection import project_result, scientific_source_identity

APP, BASE = p.APP, p.BASE
SRC = Path(__file__).resolve().parent
OUT = BASE / "stage3-decision"
STUDY = APP / "studies/pqe20261022/decision"
PROTOCOL = STUDY / "shared/protocol.json"
PACKAGE = "BF-PQE-S3-DECISION-20261023-001"
CONDITIONS = ("strong_generic", "full_h", "improved_full_h")
LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=3, candidates=3,
              wall_s=900, output_tokens=32768, generated_tokens=131072, usd=4,
              bytes=20000000)
TOTAL = dict(requests=72, tool_calls=144, numerical_inputs=20, usd=24,
             retained_bytes=150000000)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding(path):
    return {"path": str(path), "sha256": sha(path)}


def now():
    return datetime.now(timezone.utc).isoformat()


def plan(rows):
    if len(rows) != 2 or {r["role"] for r in rows} != {"local", "tradeoff"}:
        raise ValueError("TWO_PROSPECTIVE_MECHANISMS_REQUIRED")
    by_role = {r["role"]: r for r in rows}
    return [[role + "-c" + str(i), by_role[role]["task_id"], CONDITIONS[i]]
            for role, order in (("local", (0, 1, 2)), ("tradeoff", (2, 1, 0)))
            for i in order]


def resolver(registry):
    def resolve(task_id):
        matches = [r for r in registry["tasks"] if r["task_id"] == task_id]
        if len(matches) != 1:
            raise ValueError("ONLY_FROZEN_CURRENT_TASKS")
        row = matches[0]
        if sha(row["task_path"]) != row["task_file_sha256"]:
            raise ValueError("FROZEN_TASK_FILE_CHANGED")
        task = read(row["task_path"])
        if identity(task) != row["task_sha256"]:
            raise ValueError("FROZEN_TASK_CONTENT_CHANGED")
        return task
    return resolve


def prepare_inputs():
    """Freeze the two prospective inputs, then execute each initial input once.

    No result-dependent task replacement, hidden reference scan or retry. An
    interrupted claim remains evidence rather than silently restarting a solve.
    """
    gate = read(OUT / "s0/behavior-review.json")
    if gate["status"] != "SUPPORTED_ENGINEERING_ACTION_DELTA":
        raise ValueError("ACTUAL_BEHAVIOR_REQUIRED_BEFORE_INITIAL_EXECUTION")
    proposals_path = OUT / "a/task-proposals.json"
    proposals = read(proposals_path)
    rows = proposals["tasks"]
    roles = {"local-repair-control": "local",
             "startup-storage-mechanism-tradeoff": "tradeoff"}
    if len(rows) != 2 or {r["role"] for r in rows} != set(roles):
        raise ValueError("TWO_PROSPECTIVE_TASKS_REQUIRED")
    free = os.statvfs(APP)
    if free.f_bavail * free.f_frsize < 11000000000:
        raise ValueError("STORAGE_PEAK_NOT_AVAILABLE")
    old = read(APP / "studies/pqe20261022/e3lc/shared/protocol.json")
    if scientific_source_identity(p.adapter.source_identity()) != old["scientific_source"]:
        raise ValueError("SCIENTIFIC_SOURCE_CHANGED")
    STUDY.joinpath("inputs").mkdir(parents=True, exist_ok=True)
    selection_path = STUDY / "inputs/prospective-selection.json"
    with selection_path.open("x") as f:
        json.dump({"at": now(), "proposals": binding(proposals_path),
                   "rule": "Two complete exposed development inputs, fixed by mechanism before initial checks; no replacement.",
                   "tasks": [{"role": roles[r["role"]], "task_sha256": identity(r["Task"]),
                              "justification": r["construction_justification"]} for r in rows]},
                  f, indent=2)
    registry = {"package": PACKAGE, "selection": binding(selection_path),
                "tasks": [], "new_initial_inputs": 0}
    for row in rows:
        role, task = roles[row["role"]], deepcopy(row["Task"])
        if task["initial_design"] != row["Design"] or task["initial_problem"] != row["Problem"]:
            raise ValueError("INITIAL_FIELDS_DIFFER_FROM_PROPOSAL")
        task_path = STUDY / "inputs" / (role + "-task.json")
        with task_path.open("x") as f:
            json.dump(task, f, indent=2, ensure_ascii=False, allow_nan=False)
        root = OUT / "s0/initial" / role
        claim = root.parent / (role + "-claim.json")
        claim.parent.mkdir(parents=True, exist_ok=True)
        with claim.open("x") as f:
            json.dump({"at": now(), "task_sha256": identity(task), "retry": False}, f)
        public = p.adapter.execute(task, task["initial_design"], task["initial_problem"],
            {"origin": "SHARED_PROSPECTIVE_INITIAL", "agent_selected": False,
             "actual_input": {"operation": "verify", "design_patch": {}, "problem_patch": {}}},
            root, task_resolver=lambda ident, t=task: t if ident == t["task_id"] else None)
        registry["new_initial_inputs"] += public["usage"]["numerical_inputs"]
        registry["tasks"].append({"role": role, "task_id": task["task_id"],
            "task_path": str(task_path), "task_file_sha256": sha(task_path),
            "task_sha256": identity(task), "initial_raw_path": str(root / "raw.json"),
            "initial_public_result_path": str(root / "public-result.json"),
            "initial_public_result_sha256": sha(root / "public-result.json"),
            "initial_verdict": public["public_check"]["verdict"],
            "control_interpretation": "UNNECESSARY_MODIFICATION_CONTROL" if public["public_check"]["verdict"] == "PASS" else "EXPOSED_DEVELOPMENT_FAILURE",
            "exposure": row["exposure"], "source_public_state": row["source_public_state"]})
        p.save(STUDY / "inputs/registry.json", registry)
        if public["execution_status"] != "COMPLETE" or public["model_valid"] is not True:
            raise ValueError("INITIAL_INPUT_INCOMPLETE_OR_DOMAIN_INVALID_NO_REPLACEMENT")
    return {"registry": binding(STUDY / "inputs/registry.json"),
            "new_initial_inputs": registry["new_initial_inputs"],
            "initial_verdicts": {r["role"]: r["initial_verdict"] for r in registry["tasks"]}}


def configure(protocol):
    if protocol["package"] != PACKAGE or protocol["limits_per_episode"] != LIMITS:
        raise ValueError("DECISION_PROFILE_MISMATCH")
    if protocol["total_caps"] != TOTAL:
        raise ValueError("DECISION_TOTAL_CAP_CHANGED")
    for path, expected in protocol["source_bindings"].items():
        if sha(path) != expected:
            raise ValueError("FROZEN_SOURCE_CHANGED:" + path)
    for item in protocol["shared_bindings"].values():
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("FROZEN_SHARED_INPUT_CHANGED")
    ref = protocol["input_registry"]
    if sha(ref["path"]) != ref["sha256"]:
        raise ValueError("FROZEN_INPUT_REGISTRY_CHANGED")
    registry = read(ref["path"])
    if protocol["plan"] != plan(registry["tasks"]):
        raise ValueError("PROSPECTIVE_ORDER_CHANGED")
    p.OUT, p.PACKAGE, p.LIMITS = OUT, PACKAGE, dict(LIMITS)
    p.CELLS = [tuple(c) for c in protocol["plan"]]
    p.TOTAL_CAPS, p.CONTRACT_CORRECTIONS = dict(TOTAL), 2
    p.SDK = Path(protocol["sdk_entry"])
    return registry


def freeze():
    if PROTOCOL.exists():
        raise ValueError("ALREADY_FROZEN_NO_REPLACEMENT")
    gate = read(OUT / "s0/behavior-review.json")
    check = read(OUT / "s0/entry-check.json")
    if gate["status"] != "SUPPORTED_ENGINEERING_ACTION_DELTA" or check["status"] != "PASS_NEW_PATH_ONLY":
        raise ValueError("ACTUAL_BEHAVIOR_AND_DIRECT_ENTRY_REQUIRED")
    registry_path = STUDY / "inputs/registry.json"
    registry = read(registry_path)
    if registry["new_initial_inputs"] > 2:
        raise ValueError("INITIAL_ALLOWANCE_EXCEEDED")
    old = read(APP / "studies/pqe20261022/e3lc/shared/protocol.json")
    shared = {name: binding(STUDY / "shared" / name) for name in
              ("conditions.json", "common-history.json", "public-materials.json")}
    source_names = ("decision.py", "decision_methods.py", "decision_facts.py", "pilot.py",
                    "episode_methods.py", "methods.py", "adapter.py", "door_model.py",
                    "door_program.py", "engineering.py", "executor.py", "evaluator.py",
                    "public_projection.py")
    paths = [SRC / n for n in source_names] + [APP / "scripts/pqe_decision.py",
             APP / "scripts/pqe_pi_callback.mjs", Path(old["sdk_entry"])]
    protocol = {"package": PACKAGE, "frozen_at": now(), "limits_per_episode": LIMITS,
        "total_caps": TOTAL, "max_candidate_evaluations": 3, "contract_correction_limit": 2,
        "scientific_source": old["scientific_source"], "apparatus_source": old["scientific_source"],
        "same_backend": old["same_backend"], "model_identity": p.MODEL_IDENTITY,
        "sdk_entry": old["sdk_entry"], "input_registry": binding(registry_path),
        "shared_bindings": shared, "source_bindings": {str(x): sha(x) for x in paths},
        "behavior_gate": binding(OUT / "s0/behavior-review.json"),
        "entry_check": binding(OUT / "s0/entry-check.json"), "plan": plan(registry["tasks"]),
        "initial_observations": {row["task_id"]: {
            "public_result_path": row["initial_public_result_path"],
            "public_result_sha256": row["initial_public_result_sha256"]} for row in registry["tasks"]},
        "cache_policy": "Exact Task/Design/dt/scientific-source only, after autonomous submission; each reuse counts in the3-evaluation cap.",
        "claim_boundary": "Developer fixed-H mechanism pilot;2DOOR development tasks,1context per condition; no learning/G/RSI/unseen-transfer/statistical/hardware claim.",
        "no_retry": "Each planned episode once; new tool or missing-usage error stops dependent dispatch; no replacement or budget transfer.",
        "output_feedback": "Existing common field-contract feedback, at most2 corrections. New parse/transport errors stop; no new syntax-rescue adapter."}
    configure(protocol)
    p.save(PROTOCOL, protocol)
    return {"protocol": binding(PROTOCOL), "episodes": len(protocol["plan"])}


def initial_state(task, design, problem, initial=None):
    state = p.episode_initial_state(task, design, problem, initial)
    history = read(STUDY / "shared/common-history.json")
    materials = read(STUDY / "shared/public-materials.json")
    if not isinstance(history, list):
        raise ValueError("COMMON_HISTORY_LIST_REQUIRED")
    state["history"] = deepcopy(history) + state["history"]
    state["evidence"].append({"origin": "COMMON_PUBLIC_MODEL_MATERIALS", "materials": materials})
    return state


def seed_initial_cache(protocol, registry):
    cache = {}
    resolve = resolver(registry)
    for row in registry["tasks"]:
        task = resolve(row["task_id"])
        public = p.initial_observation(protocol, row["task_id"], task_resolver=resolve)
        raw = read(row["initial_raw_path"])
        if raw["design"] != task["initial_design"] or raw["result_sha256"] != public["result_sha256"]:
            raise ValueError("INITIAL_RAW_INPUT_IDENTITY_CHANGED")
        key = p.execution_cache_key(task, public["design"], raw["dt_s"], public["sources"])
        cache[key] = Path(row["initial_public_result_path"]).parent
    return cache


@contextmanager
def runtime_scope():
    prior, installed = None, False
    try:
        with p.dbconnect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
                raise ValueError("OTHER_PROVIDER_REQUEST_ACTIVE")
            row = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            prior = row["value"] if row else None
            db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
            installed = True
        p.save(OUT / "s0/runtime-registration.json", {"at": now(), "budget_scope_before": prior,
               "temporary_scope": "per-owner", "study_usd_cap": 24})
        yield
    finally:
        if installed:
            with p.dbconnect() as db:
                current = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
                if not current or current["value"] != json.dumps("per-owner"):
                    raise ValueError("CONCURRENT_SCOPE_CHANGE")
                if prior is None:
                    db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
                else:
                    db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'", (prior,))
                db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))


def dependency_stop(row):
    return bool(row.get("error") or row.get("fatal") or
        row.get("accounting", {}).get("unknown_or_missing_usage") or
        (row.get("termination") or {}).get("reason") in {
            "TOOL_ERROR", "MISSING_USAGE", "MODEL_IDENTITY_MISMATCH", "TOOL_USAGE_UNKNOWN",
            "CONSUMED_INPUT_MISMATCH", "PARSE_OR_TRANSPORT_ERROR", "HOOK_ERROR"})


def run():
    from .decision_methods import DecisionEpisodeDriver
    protocol = read(PROTOCOL)
    registry = configure(protocol)
    cache = seed_initial_cache(protocol, registry)
    claim, lock = OUT / "s0/run-claim.json", OUT / "s0/active.lock"
    with claim.open("x") as f:
        json.dump({"at": now(), "pid": os.getpid(), "protocol_sha256": sha(PROTOCOL)}, f)
    with lock.open("x") as f:
        f.write(str(os.getpid()))
    rows, outer_error = [], None
    try:
        with runtime_scope():
            for cell in protocol["plan"]:
                # Canonical results already persist in the existing consumer;
                # keep the execution console compact, without another full log.
                with redirect_stdout(io.StringIO()):
                    row = p.run_cell(tuple(cell), protocol, cache,
                        task_resolver=resolver(registry), driver_factory=DecisionEpisodeDriver,
                        initial_state_factory=initial_state)
                row["completed_new_scientific_inputs"] = sum(a.get("usage", {}).get("numerical_inputs", 0) for a in row.get("actions", []))
                row["exact_result_reuses"] = sum(bool(a.get("usage", {}).get("reused")) for a in row.get("actions", []))
                rows.append(row)
                p.save(OUT / "s0/batch-result.json", {"status": "RUNNING", "episodes": rows})
                print(json.dumps({"episode": row["episode"], "status": row["status"],
                    "last_service": row["last_public_service"], "accounting": row["accounting"],
                    "termination": row["termination"]}), flush=True)
                if dependency_stop(row):
                    break
    except BaseException as exc:
        outer_error = type(exc).__name__ + ":" + str(exc)
        raise
    finally:
        lock.unlink()
        result = {"package": PACKAGE, "status": "FINITE_DECISION_COMPLETE" if
            len(rows) == 6 and not outer_error and not dependency_stop(rows[-1]) else "FINITE_DECISION_STOPPED",
            "episodes": rows, "outer_error": outer_error, "completed_at": now(),
            "not_run": [c for c in protocol["plan"] if c[0] not in {row["episode"] for row in rows}],
            "shared_initial_new_inputs": registry["new_initial_inputs"]}
        p.save(OUT / "s0/batch-result.json", result)
    return result


def readback():
    return {p.name: read(p) for p in (OUT / "s0").glob("*-result.json")}
