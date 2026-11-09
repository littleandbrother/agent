"""Finite scope intervention using the existing paid loop and scientific world."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from . import pilot as p
from .executor import identity
from .public_projection import project_result, scientific_source_identity

APP, BASE = p.APP, p.BASE
SRC = Path(__file__).resolve().parent
OUT = BASE / "stage3-e3lc"
STUDY = APP / "studies/pqe20261022/e3lc"
PROTOCOL = STUDY / "shared/protocol.json"
PACKAGE = "BF-PQE-S3-E3LC-20261023-001"
CONDITIONS = ("strong_generic", "full_h", "full_h_no_active_reform", "strong_generic_scope_matched")
LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=6, candidates=6,
              wall_s=900, output_tokens=32768, generated_tokens=131072, usd=4, bytes=20000000)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding(path):
    return {"path": str(path), "sha256": sha(path)}


def now():
    return datetime.now(timezone.utc).isoformat()


def door_inputs(protocol):
    ref = protocol["private_registry"]
    if sha(ref["path"]) != ref["sha256"]:
        raise ValueError("E3_REGISTRY_CHANGED")
    registry = read(ref["path"])
    if registry["eligibility"] != "ELIGIBLE":
        return None, None, registry
    row = registry["roles"]["scope"]
    if sha(row["task_path"]) != row["task_file_sha256"]:
        raise ValueError("E3_TASK_CHANGED")
    task = read(row["task_path"])
    if row.get("task_json_key"):
        task = task[row["task_json_key"]]
    if identity(task) != row["task_sha256"]:
        raise ValueError("E3_TASK_IDENTITY_CHANGED")
    if sha(row["initial_public_result_path"]) != row["initial_public_result_sha256"]:
        raise ValueError("E3_INITIAL_CHANGED")
    initial = project_result(read(row["initial_public_result_path"]))
    if (initial["task_sha256"] != identity(task) or initial["design"] != task["initial_design"]
            or initial["problem"] != task["initial_problem"]
            or scientific_source_identity(initial["sources"]) != protocol["scientific_source"]):
        raise ValueError("E3_INITIAL_BINDING_MISMATCH")
    return task, initial, registry


def resolve(protocol):
    def task_resolver(task_id):
        task, _, _ = door_inputs(protocol)
        if task is None or task["task_id"] != task_id:
            raise ValueError("E3_CURRENT_TASK_ONLY")
        return task
    return task_resolver


def matched_problem(task, protocol):
    problem = deepcopy(task["initial_problem"])
    active = protocol["scope_intervention"]["expanded_active_variables"]
    if not set(problem["active_variables"]) <= set(active) <= set(task["design_domain"]):
        raise ValueError("E3_MATCHED_SCOPE_NOT_AUTHORIZED")
    problem["active_variables"] = list(active)
    problem["fixed_choices"] = {k: v for k, v in problem.get("fixed_choices", {}).items() if k not in active}
    return problem


def plan(task):
    if task is None:
        return []
    return [[f"scope-r{repeat}-c{index}", task["task_id"], CONDITIONS[index], repeat]
            for repeat, order in ((1, (0, 1, 2, 3)), (2, (3, 2, 1, 0))) for index in order]


def configure(protocol):
    if protocol["package"] != PACKAGE or protocol["limits_per_episode"] != LIMITS:
        raise ValueError("E3_PROTOCOL_OR_LIMITS_CHANGED")
    for path, expected in protocol["source_bindings"].items():
        if sha(path) != expected:
            raise ValueError("E3_FROZEN_SOURCE_CHANGED:" + path)
    for ref in protocol["shared_bindings"].values():
        if sha(ref["path"]) != ref["sha256"]:
            raise ValueError("E3_PUBLIC_INPUT_CHANGED")
    task, _, _ = door_inputs(protocol)
    if protocol["plan"] != plan(task):
        raise ValueError("E3_PLAN_CHANGED")
    p.OUT, p.PACKAGE, p.LIMITS = OUT, PACKAGE, dict(LIMITS)
    p.CELLS = [tuple(c[:3]) for c in protocol["plan"]] + [("lcpv-h0", "LC-DEV", "strong_generic")]
    p.CONTRACT_CORRECTIONS = 2
    p.SDK = Path(protocol["sdk_entry"])
    p.TOTAL_CAPS = dict(requests=108, tool_calls=216, numerical_inputs=79, usd=36, retained_bytes=250000000)


def freeze():
    if PROTOCOL.exists():
        raise ValueError("E3_ALREADY_FROZEN")
    entry = OUT / "s0/entry-check.json"
    if read(entry)["status"] != "PASS_NEW_ENTRY_ONLY":
        raise ValueError("E3_ENTRY_NOT_RELEASED")
    old = read(APP / "studies/pqe20261022/e2main/shared/protocol.json")
    protocol = {"package": PACKAGE, "frozen_at": now(), "private_registry": binding(STUDY / "private/registry.json"),
        "limits_per_episode": LIMITS, "scientific_source": old["scientific_source"],
        "apparatus_source": old["scientific_source"], "same_backend": old["same_backend"],
        "sdk_entry": old["sdk_entry"], "model_identity": p.MODEL_IDENTITY,
        "contract_correction_limit": 2, "max_candidate_evaluations": 6, "entry_check": binding(entry),
        "shared_bindings": {"conditions": binding(STUDY / "shared/conditions.json")},
        "scope_intervention": {}, "initial_observations": {},
        "claim_boundary": "One constructed mechanism task, two independent model contexts, no learned H or F2/F3 claim.",
        "total_caps": {"episodes": 9, "usd": 36, "scientific_inputs": 79, "native": 0,
                       "retained_bytes": 250000000, "peak_additional_bytes": 1000000000}}
    task, initial, registry = door_inputs(protocol)
    protocol["eligibility"] = registry["eligibility"]
    protocol["plan"] = plan(task)
    if task is not None:
        for name in ("task-public.json", "task-materials.json"):
            protocol["shared_bindings"][name] = binding(STUDY / "shared" / name)
        active = registry["expanded_active_variables"]
        protocol["scope_intervention"] = {"expanded_active_variables": active,
            "different_initial_problem_declared": True, "reference_values_exposed": False}
        matched_problem(task, protocol)
        row = registry["roles"]["scope"]
        protocol["initial_observations"][task["task_id"]] = {
            "public_result_path": row["initial_public_result_path"],
            "public_result_sha256": row["initial_public_result_sha256"]}
    paths = [SRC / name for name in ("e3lc.py", "e3lc_methods.py", "pilot.py", "adapter.py", "methods.py",
        "episode_methods.py", "public_projection.py", "door_model.py", "door_program.py", "engineering.py", "executor.py", "evaluator.py")]
    paths += [APP / "scripts/pqe_e3lc.py", APP / "scripts/pqe_pi_callback.mjs", Path(old["sdk_entry"])]
    protocol["source_bindings"] = {str(path): sha(path) for path in paths}
    configure(protocol)
    p.save(PROTOCOL, protocol)
    return {"protocol": binding(PROTOCOL), "eligibility": registry["eligibility"], "door_cells": len(protocol["plan"])}


@contextmanager
def runtime_scope(label):
    prior, installed = None, False
    try:
        with p.dbconnect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
                raise ValueError("OTHER_PROVIDER_REQUEST_ACTIVE")
            old = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            prior = old["value"] if old else None
            db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
            # Same finite study and total cap across the two independently admitted pathways.
            db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time() + 8500, PACKAGE))
            installed = True
        p.save(OUT / "s0" / (label + "-runtime-registration.json"), {"at": now(), "budget_scope_before": prior,
            "temporary_budget_scope": "per-owner", "study_cap_usd": 36})
        yield
    finally:
        if installed:
            with p.dbconnect() as db:
                current = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
                if not current or current["value"] != json.dumps("per-owner"):
                    raise ValueError("E3_CONCURRENT_BUDGET_SCOPE_CHANGE")
                if prior is None:
                    db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
                else:
                    db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'", (prior,))
                db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))


def dependency_stop(row):
    return bool(row.get("error") or row.get("fatal") or row.get("accounting", {}).get("unknown_or_missing_usage")
                or (row.get("termination") or {}).get("reason") in {"TOOL_ERROR", "MISSING_USAGE", "MODEL_IDENTITY_MISMATCH"})


def run():
    from .e3lc_methods import E3LCEpisodeDriver
    protocol = read(PROTOCOL)
    configure(protocol)
    task, initial, registry = door_inputs(protocol)
    claim, lock = OUT / "s0/door-run-claim.json", OUT / "s0/active.lock"
    with claim.open("x") as f:
        json.dump({"at": now(), "pid": os.getpid(), "protocol_sha256": sha(PROTOCOL)}, f)
    if task is None:
        result = {"status": "NOT_RUN_ELIGIBILITY_NOT_ESTABLISHED", "reason": registry.get("reason"), "episodes": []}
        p.save(OUT / "s0/door-batch-result.json", result)
        return result
    row = registry["roles"]["scope"]
    folder = Path(row["initial_raw_path"]).parent
    raw = read(row["initial_raw_path"])
    cache = {p.execution_cache_key(task, initial["design"], raw["dt_s"], initial["sources"]): folder}
    rows, error = [], None
    with lock.open("x") as f:
        f.write(str(os.getpid()))
    try:
        with runtime_scope("door"):
            for cell in protocol["plan"]:
                class ScopeEpisode(p.Episode):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        if cell[2] == "strong_generic_scope_matched":
                            self.problem = matched_problem(self.task, protocol)

                def observation(*args, **kwargs):
                    result = p.initial_observation(*args, **kwargs)
                    if cell[2] == "strong_generic_scope_matched":
                        result["problem"] = matched_problem(task, protocol)
                    return result

                result = p.run_cell(tuple(cell[:3]), protocol, cache, task_resolver=resolve(protocol),
                    driver_factory=E3LCEpisodeDriver, episode_factory=ScopeEpisode,
                    initial_observation_factory=observation)
                result["independent_context"] = cell[3]
                result["completed_new_scientific_inputs"] = sum(x.get("usage", {}).get("numerical_inputs", 0) for x in result.get("actions", []))
                result["exact_result_reuses"] = sum(bool(x.get("usage", {}).get("reused")) for x in result.get("actions", []))
                rows.append(result)
                p.save(OUT / "s0/door-batch-result.json", {"status": "RUNNING", "episodes": rows})
                if dependency_stop(result):
                    break
    except BaseException as exc:
        error = type(exc).__name__ + ":" + str(exc)
        raise
    finally:
        lock.unlink()
        result = {"status": "FINITE_DOOR_COMPLETE" if len(rows) == 8 and not error and not dependency_stop(rows[-1]) else "FINITE_DOOR_STOPPED",
            "episodes": rows, "outer_error": error, "completed_at": now(),
            "not_run": [c for c in protocol["plan"] if c[0] not in {r["episode"] for r in rows}]}
        p.save(OUT / "s0/door-batch-result.json", result)
    return result


def readback():
    """Read saved finite results; never rewrite a sealed result or dispatch."""
    paths = [OUT / "s0" / name for name in ("door-batch-result.json", "lc-batch-result.json", "opt-result.json")]
    return {path.name: read(path) for path in paths if path.exists()}
