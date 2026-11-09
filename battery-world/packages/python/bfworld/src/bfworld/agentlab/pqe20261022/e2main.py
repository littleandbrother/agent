"""Finite E2 main matrix using the existing Pi driver, consumer and accounting."""
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
OUT = BASE / "stage3-e2main"
STUDY = APP / "studies/pqe20261022/e2main"
PROTOCOL = STUDY / "shared/protocol.json"
PACKAGE = "BF-PQE-S3-E2MAIN-20261023-001"
ROLES = ("d04", "d05", "d10", "d16")
CONDITIONS = ("strong_generic", "fixed_sequence", "ordinary_feedback", "full_h")
LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=6, candidates=6,
              wall_s=900, output_tokens=32768, generated_tokens=131072, usd=4, bytes=12000000)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding(path):
    return {"path": str(path), "sha256": sha(path)}


def now():
    return datetime.now(timezone.utc).isoformat()


def role_inputs(protocol, role):
    ref = protocol["private_registry"]
    if sha(ref["path"]) != ref["sha256"]:
        raise ValueError("E2MAIN_REGISTRY_CHANGED")
    row = read(ref["path"])["roles"][role]
    if row.get("eligibility") == "MODEL_UNSUPPORTED":
        return None, None, row
    if sha(row["task_path"]) != row["task_file_sha256"]:
        raise ValueError("E2MAIN_TASK_FILE_CHANGED")
    task = read(row["task_path"])
    if row.get("task_json_key"):
        task = task[row["task_json_key"]]
    if identity(task) != row["task_sha256"]:
        raise ValueError("E2MAIN_TASK_CONTENT_CHANGED")
    if sha(row["initial_public_result_path"]) != row["initial_public_result_sha256"]:
        raise ValueError("E2MAIN_INITIAL_CHANGED")
    initial = project_result(read(row["initial_public_result_path"]))
    if (initial["task_sha256"] != identity(task)
            or initial["design"] != task["initial_design"]
            or initial["problem"] != task["initial_problem"]
            or scientific_source_identity(initial["sources"]) != protocol["scientific_source"]):
        raise ValueError("E2MAIN_INITIAL_BINDING_MISMATCH")
    return task, initial, row


def resolver(protocol, role):
    def resolve(task_id):
        task, _, _ = role_inputs(protocol, role)
        if task is None or task_id != task["task_id"]:
            raise ValueError("E2MAIN_TASK_NOT_AUTHORIZED_FOR_CELL")
        return task
    return resolve


def plan(protocol):
    cells = []
    for repeat in (1, 2):
        for index, role in enumerate(ROLES):
            row = read(protocol["private_registry"]["path"])["roles"][role]
            task_id = row.get("task_id", role.upper()+"-MODEL-UNSUPPORTED")
            rotation = (index + repeat - 1) % 4
            for j in range(4):
                condition = CONDITIONS[(j + rotation) % 4]
                ident = f"{role}-r{repeat}-b{CONDITIONS.index(condition)}"
                cells.append([ident, role, task_id, condition, repeat])
    return cells


def configure(protocol):
    if protocol["package"] != PACKAGE or protocol["plan"] != plan(protocol):
        raise ValueError("E2MAIN_PLAN_CHANGED")
    if protocol["limits_per_episode"] != LIMITS:
        raise ValueError("E2MAIN_LIMITS_CHANGED")
    for path, expected in protocol["source_bindings"].items():
        if sha(path) != expected:
            raise ValueError("E2MAIN_FROZEN_SOURCE_CHANGED:"+path)
    for ref in protocol["shared_bindings"].values():
        if sha(ref["path"]) != ref["sha256"]:
            raise ValueError("E2MAIN_SHARED_INPUT_CHANGED")
    p.OUT, p.PACKAGE, p.LIMITS = OUT, PACKAGE, dict(LIMITS)
    p.CELLS = [(c[0], c[2], c[3]) for c in protocol["plan"]]
    p.CONTRACT_CORRECTIONS = 2
    p.SDK = Path(protocol["sdk_entry"])
    p.TOTAL_CAPS = dict(requests=384, tool_calls=768, numerical_inputs=196,
                        usd=128, retained_bytes=400000000)


def freeze():
    if PROTOCOL.exists():
        raise ValueError("E2MAIN_ALREADY_FROZEN")
    registry = STUDY / "private/registry.json"
    entry = OUT / "s0/entry-check.json"
    if read(entry)["status"] != "PASS_NEW_ENTRY_ONLY":
        raise ValueError("E2MAIN_ENTRY_NOT_RELEASED")
    old = read(APP / "studies/pqe20261022/shared/e2dev-protocol.json")
    refs = {name: binding(STUDY / "shared" / name) for name in (
        "task-freeze-public.json", "task-public-materials.json", "conditions.json")}
    paths = [SRC / n for n in ("e2main.py", "pilot.py", "adapter.py", "methods.py",
        "episode_methods.py", "public_projection.py", "door_model.py", "door_program.py",
        "engineering.py", "executor.py", "evaluator.py")]
    paths += [APP / "scripts/pqe_e2main.py", APP / "scripts/pqe_pi_callback.mjs", Path(old["sdk_entry"])]
    protocol = {"package": PACKAGE, "frozen_at": now(), "private_registry": binding(registry),
        "limits_per_episode": LIMITS, "source_bindings": {str(x): sha(x) for x in paths},
        "scientific_source": old["scientific_source"], "apparatus_source": old["scientific_source"],
        "same_backend": old["same_backend"], "sdk_entry": old["sdk_entry"],
        "shared_bindings": refs, "contract_correction_limit": 2, "entry_check": binding(entry),
        "total_caps": {"episodes": 32, "usd": 128, "door_new_scientific_inputs": 196,
            "lcpv_new_scientific_inputs": 4, "all_new_scientific_inputs": 200, "native": 0,
            "retained_bytes": 500000000, "peak_additional_bytes": 1500000000},
        "model_identity": p.MODEL_IDENTITY, "initial_observations": {},
        "max_candidate_evaluations": 6,
        "claim_boundary": "Four fixed tasks and two independent model contexts; D16 control separate. No learned H, mechanism attribution E3, OPT, F2/F3 transfer or hardware.",
        "no_retry_rescue_or_task_replacement": True}
    protocol["plan"] = plan(protocol)
    for role in ROLES:
        task, initial, row = role_inputs(protocol, role)
        if task is not None:
            if row.get("task_id") != task["task_id"]:
                raise ValueError("REGISTRY_TASK_ID_REQUIRED")
            protocol["initial_observations"][task["task_id"]] = {
                "public_result_path": row["initial_public_result_path"],
                "public_result_sha256": row["initial_public_result_sha256"]}
    configure(protocol)
    p.save(PROTOCOL, protocol)
    return protocol


def cache_initials(protocol):
    cache = {}
    for role in ROLES:
        task, initial, row = role_inputs(protocol, role)
        if task is None:
            continue
        folder = Path(row["initial_public_result_path"]).parent
        raw = read(row.get("initial_raw_path", folder / "raw.json"))
        if raw["result_sha256"] != initial["result_sha256"] or raw["design"] != initial["design"]:
            raise ValueError("E2MAIN_RAW_INITIAL_MISMATCH")
        cache[p.execution_cache_key(task, initial["design"], raw["dt_s"], initial["sources"])] = folder
    return cache


def dependency_stop(row):
    return bool(row.get("error") or row.get("fatal") or row.get("accounting", {}).get("unknown_or_missing_usage")
                or (row.get("termination") or {}).get("reason") in
                {"TOOL_ERROR", "MISSING_USAGE", "MODEL_IDENTITY_MISMATCH"})


def enrich(row, cell):
    row = deepcopy(row)
    row.update(role=cell[1], independent_context=cell[4],
        reserved_or_attempted_numerical_inputs=row.get("actual_new_numerical_inputs", 0),
        completed_new_scientific_inputs=sum(x.get("usage", {}).get("numerical_inputs", 0) for x in row.get("actions", [])),
        exact_result_reuses=sum(bool(x.get("usage", {}).get("reused")) for x in row.get("actions", [])),
        service_origin="LAST_CONSUMER_RESULT" if row.get("actions") else "INITIAL_ONLY",
        interpretation="Prospectively frozen finite fixed-method comparison; no H/G learning or hardware claim.")
    return row


def write_result(protocol, rows, **extra):
    done = {r["episode"] for r in rows}
    missing = [{"episode": c[0], "role": c[1], "condition": c[3], "independent_context": c[4],
                "status": "NOT_RUN_DEPENDENT_STOP"} for c in protocol["plan"] if c[0] not in done]
    totals = {"actual_episodes": sum("owner" in r for r in rows),
        "actual_requests": sum(r.get("accounting", {}).get("requests", 0) for r in rows),
        "episode_new_scientific_inputs": sum(r.get("completed_new_scientific_inputs", 0) for r in rows),
        "exact_result_reuses": sum(r.get("exact_result_reuses", 0) for r in rows),
        "estimated_usd": sum(r.get("accounting", {}).get("settled_charge_upper_bound_usd", 0) for r in rows),
        "unsettled_reserved_usd": sum(r.get("accounting", {}).get("unsettled_reserved_usd", 0) for r in rows),
        "unknown_or_missing_usage": [x for r in rows for x in r.get("accounting", {}).get("unknown_or_missing_usage", [])]}
    result = {"package": PACKAGE, "updated_at": now(), "protocol_sha256": sha(PROTOCOL),
              "episodes": rows+missing, "totals": totals, **extra}
    p.save(OUT / "s0/batch-result.json", result)
    return result


def run():
    protocol = read(PROTOCOL)
    configure(protocol)
    cache, rows, prior, installed, outer_error = cache_initials(protocol), [], None, False, None
    claim, lock = OUT / "s0/run-claim.json", OUT / "s0/active.lock"
    with claim.open("x") as f:
        json.dump({"at": now(), "pid": os.getpid(), "protocol_sha256": sha(PROTOCOL)}, f)
    with lock.open("x") as f:
        f.write(str(os.getpid()))
    try:
        with p.dbconnect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
                raise ValueError("OTHER_PROVIDER_REQUEST_ACTIVE")
            old = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            prior = old["value"] if old else None
            db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
            installed = True
        p.save(OUT / "s0/runtime-registration.json", {"at": now(), "budget_scope_before": prior,
            "temporary_budget_scope": "per-owner", "finite_owner_cap_usd": 4, "study_cap_usd": 128})
        for cell in protocol["plan"]:
            ident, role, task_id, condition, repeat = cell
            task, _, registry_row = role_inputs(protocol, role)
            if task is None:
                rows.append({"episode": ident, "role": role, "condition": condition,
                    "independent_context": repeat, "status": "NOT_RUN_MODEL_UNSUPPORTED",
                    "reason": registry_row["reason"]})
                write_result(protocol, rows, status="RUNNING")
                continue
            row = p.run_cell((ident, task_id, condition), protocol, cache,
                             task_resolver=resolver(protocol, role))
            row = enrich(row, cell)
            p.save(OUT / "s0/episodes" / ident / "main-cell-result.json", row)
            rows.append(row)
            write_result(protocol, rows, status="RUNNING")
            first = OUT / "s0/first-task-block.json"
            block = [r for r in rows if r.get("role") == role and r.get("independent_context") == repeat]
            if len(block) == 4 and not first.exists():
                p.save(first, {"at": now(), "role": role, "independent_context": repeat, "episodes": block})
            if dependency_stop(row):
                break
    except BaseException as exc:
        outer_error = type(exc).__name__+":"+str(exc)
        raise
    finally:
        if installed:
            with p.dbconnect() as db:
                current = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
                if not current or current["value"] != json.dumps("per-owner"):
                    raise ValueError("E2MAIN_CONCURRENT_BUDGET_SCOPE_CHANGE")
                if prior is None:
                    db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
                else:
                    db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'", (prior,))
                db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))
        lock.unlink()
        complete = len(rows) == len(protocol["plan"]) and outer_error is None and not (rows and dependency_stop(rows[-1]))
        write_result(protocol, rows, status="FINITE_MATRIX_COMPLETE" if complete else "FINITE_MATRIX_STOPPED",
                     outer_error=outer_error, budget_scope_restored=installed, completed_at=now())
    return rows


def summarize():
    protocol = read(PROTOCOL)
    configure(protocol)
    rows = []
    for cell in protocol["plan"]:
        path = OUT / "s0/episodes" / cell[0] / "main-cell-result.json"
        if path.exists():
            rows.append(read(path))
        elif role_inputs(protocol, cell[1])[0] is None:
            rows.append({"episode": cell[0], "role": cell[1], "condition": cell[3],
                         "independent_context": cell[4], "status": "NOT_RUN_MODEL_UNSUPPORTED"})
    return write_result(protocol, rows, status="READBACK_COMPLETE")
