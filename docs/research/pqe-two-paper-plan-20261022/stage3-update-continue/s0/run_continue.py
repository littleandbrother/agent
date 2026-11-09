"""One shared external failure, two original frozen-method continuations."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import adapter, pilot as p
from bfworld.agentlab.pqe20261022 import decision as old
from bfworld.agentlab.pqe20261022.decision_methods import DecisionEpisodeDriver
from bfworld.agentlab.pqe20261022.executor import identity
from bfworld.agentlab.pqe20261022.methods import common_contract_check, digest
from bfworld.agentlab.pqe20261022.public_projection import scientific_source_identity

HERE = Path(__file__).resolve().parent
OUT, BASE = HERE.parent, HERE.parent.parent
PACKAGE = "BF-PQE-S3-UPDATE-CONTINUE-20261023-001"
PROTOCOL = OUT / "shared/protocol.json"
CONSOLE = sys.stdout
LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=3, candidates=3,
              wall_s=900, output_tokens=32768, generated_tokens=65536, usd=4,
              bytes=25000000)
TOTAL = dict(requests=24, tool_calls=48, numerical_inputs=6, usd=10,
             retained_bytes=60000000)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    return {"path": str(path), "sha256": sha(path)}


def checked(ref):
    if sha(ref["path"]) != ref["sha256"]:
        raise ValueError("FROZEN_INPUT_CHANGED:" + ref["path"])
    return read(ref["path"])


def prepare():
    if PROTOCOL.exists():
        raise ValueError("ALREADY_BOUND_NO_NEW_BATCH_OR_REPLACEMENT")
    previous = read(APP / "studies/pqe20261022/decision/shared/protocol.json")
    frozen = read(BASE / "stage3-decision-consequence/s0/frozen-inputs.json")
    case = next(x for x in frozen["cases"] if x["case"] == "common_initial_r2_pool")
    transcript = checked(frozen["r2_transcript"])
    state = deepcopy(transcript["initial_state"])
    task = checked(case["task"])
    public_path = BASE / "stage3-decision-consequence/s0/executions/common_initial_r2_pool/public-result.json"
    public = read(public_path)
    if digest(state) != case["public_state_sha256"] or identity(task) != case["task_sha256"]:
        raise ValueError("ORIGINAL_CAUSAL_PREFIX_CHANGED")
    if p.public_task(task) != state["task"]:
        raise ValueError("PUBLIC_TASK_PREFIX_MISMATCH")
    if (public["execution_status"] != "COMPLETE" or public["model_valid"] is not True
            or public["public_check"]["verdict"] != "FAIL"
            or public["design"] != case["updated_design"]
            or public["problem"] != case["updated_problem"]):
        raise ValueError("SAVED_EXTERNAL_FAILURE_MISMATCH")
    if (public["design"] != {**state["design"], **case["actual_input"].get("design_patch", {})}
            or public["problem"] != {**state["problem"], **case["actual_input"].get("problem_patch", {})}):
        raise ValueError("EXTERNAL_EXECUTION_INPUT_BINDING_MISMATCH")
    if common_contract_check(state, case["actual_input"], {"remaining_actions": 1}) != case["actual_input"]:
        raise ValueError("EXTERNAL_ACTION_CONTRACT_CHANGED")
    if scientific_source_identity(adapter.source_identity()) != previous["scientific_source"]:
        raise ValueError("FROZEN_SCIENCE_CHANGED")
    for path, expected in previous["source_bindings"].items():
        if sha(path) != expected:
            raise ValueError("FROZEN_METHOD_OR_SCIENCE_CHANGED:" + path)
    inputs = {"task": task, "state_before_external": state,
              "external_decision": {"status": "READY", "selected_id": case["selected_candidate"]["id"],
                  "selected_candidate": case["selected_candidate"], "actual_input": case["actual_input"],
                  "origin": "COMMON_EXTERNALLY_SUPPLIED_ALREADY_EXECUTED_ACTION", "agent_selected": False},
              "external_public_result": bind(public_path),
              "source_transcript": frozen["r2_transcript"],
              "causal_prefix_rule": "Exact original predecision state plus only this external failure. No later candidate/success, supervisor diagnosis or private assessment supplied.",
              "external_execution_charged_once_in_previous_package": True}
    p.save(OUT / "shared/common-input.json", inputs)
    cells = [["update-generic", task["task_id"], "strong_generic"],
             ["update-fixed-h", task["task_id"], "improved_full_h"]]
    protocol = {"package": PACKAGE, "bound_at": old.now(), "cells": cells,
                "limits_per_episode": LIMITS, "total_caps": TOTAL,
                "authorized_usd_per_episode": 5, "effective_original_driver_usd_cap": 4,
                "effective_driver_note": "Reuse original unchanged driver ceiling, conservatively inside authorized USD5; no method/budget implementation widening.",
                "contract_correction_limit": previous["contract_correction_limit"],
                "max_candidate_evaluations": 3, "same_backend": previous["same_backend"],
                "model_identity": previous["model_identity"], "sdk_entry": previous["sdk_entry"],
                "scientific_source": previous["scientific_source"],
                "apparatus_source": previous["apparatus_source"],
                "source_bindings": previous["source_bindings"],
                "caller": bind(__file__), "common_input": bind(OUT / "shared/common-input.json"),
                "external_failure": bind(public_path), "old_task": case["task"],
                "no_initial_or_reference_or_native_inputs": True, "no_h_g_formation": True,
                "claim_boundary": "Exposed development-state feedback diagnostic; external first action not autonomously selected by either arm; frozen H, no unseen transfer/learning/statistics/hardware claim."}
    p.save(PROTOCOL, protocol)
    return protocol


def configure(protocol):
    if protocol["package"] != PACKAGE or protocol["limits_per_episode"] != LIMITS or protocol["total_caps"] != TOTAL:
        raise ValueError("ORIGINAL_PACKAGE_RESOURCES_CHANGED")
    if sha(__file__) != protocol["caller"]["sha256"]:
        raise ValueError("FROZEN_CALLER_CHANGED")
    for path, expected in protocol["source_bindings"].items():
        if sha(path) != expected:
            raise ValueError("FROZEN_SOURCE_CHANGED:" + path)
    inputs = checked(protocol["common_input"])
    checked(protocol["external_failure"])
    p.OUT, p.PACKAGE, p.LIMITS = OUT, PACKAGE, dict(LIMITS)
    p.CELLS, p.TOTAL_CAPS = [tuple(x) for x in protocol["cells"]], dict(TOTAL)
    p.SDK = Path(protocol["sdk_entry"])
    return inputs


@contextmanager
def runtime_scope():
    prior, installed = None, False
    with p.dbconnect() as db:
        if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
            raise ValueError("PROVIDER_REQUEST_ALREADY_INFLIGHT")
        if db.execute("SELECT 1 FROM research_model_owners WHERE protocol=?", (PACKAGE,)).fetchone():
            raise ValueError("ORIGINAL_PACKAGE_ALREADY_HAS_OWNERS_NO_RETRY")
    try:
        with p.dbconnect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            prior = row["value"] if row else None
            db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
            installed = True
        p.save(HERE / "runtime-registration.json", {"at": old.now(), "scope_before": prior,
               "temporary_scope": "per-owner", "study_usd_cap": 10})
        yield
    finally:
        if installed:
            with p.dbconnect() as db:
                current = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
                if not current or current["value"] != json.dumps("per-owner"):
                    raise ValueError("CONCURRENT_BUDGET_SCOPE_CHANGE")
                if prior is None:
                    db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
                else:
                    db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'", (prior,))
                db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))


def run(protocol):
    inputs = configure(protocol)
    task = inputs["task"]
    original_state = inputs["state_before_external"]
    external = checked(inputs["external_public_result"])
    compact = p.compact_result(external)
    with (HERE / "run-claim.json").open("x") as stream:
        json.dump({"at": old.now(), "pid": os.getpid(), "protocol": bind(PROTOCOL), "retry": False}, stream)
    lock = HERE / "active.lock"
    with lock.open("x") as stream:
        stream.write(str(os.getpid()))
    cache = {}
    paths = sorted((BASE / "stage3-e3lc/s0").glob("episodes/scope-*/actions/*/public-result.json"))
    paths += sorted((BASE / "stage3-e3lc/s0").glob("opt/*/*/public-result.json"))
    paths += sorted((BASE / "stage3-decision-consequence/s0/executions").glob("*/public-result.json"))
    for path in paths:
        saved = read(path)
        if (saved.get("task_sha256") == identity(task)
                and scientific_source_identity(saved["sources"]) == protocol["scientific_source"]):
            raw = read(path.parent / "raw.json") if (path.parent / "raw.json").exists() else None
            if raw:
                cache[p.execution_cache_key(task, saved["design"], raw["dt_s"], saved["sources"])] = path.parent

    def resolve(task_id):
        if task_id != task["task_id"]:
            raise ValueError("ONLY_ORIGINAL_FROZEN_TASK")
        return deepcopy(task)

    class ContinuedEpisode(p.Episode):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.design, self.problem = deepcopy(external["design"]), deepcopy(external["problem"])

        def consume(self, decision):
            result = super().consume(decision)
            live = {"at": old.now(), "episode": self.ident, "autonomous_action_number": self.tools,
                    "actual_input": decision["actual_input"], "public_check": result["public_check"],
                    "model_valid": result.get("model_valid"), "usage": result["usage"]}
            p.save(HERE / "live-progress.json", live)
            print(json.dumps(live), file=CONSOLE, flush=True)
            return result

    def driver_factory(condition, planner_callback, **kwargs):
        driver = DecisionEpisodeDriver(condition, planner_callback, **kwargs)
        before = deepcopy(driver.state)
        calls = len(driver.harness.program.calls)
        callbacks = len(driver.callback_records)
        driver.harness.quota = driver._quota()
        after = driver.harness.update(driver.state, deepcopy(inputs["external_decision"]), deepcopy(compact))
        driver.state = after
        if after.get("update_status") != "UPDATED" or after["design"] != external["design"] or after["problem"] != external["problem"]:
            raise ValueError("COMMON_EXTERNAL_UPDATE_NOT_CONSUMED")
        if before != original_state or driver.tool_calls or driver.numerical_inputs or driver.pending:
            raise ValueError("EXTERNAL_ACTION_IMPROPERLY_COUNTED_AS_AUTONOMOUS")
        p.save(HERE / "episodes" / kwargs["episode_id"] / "external-update.json", {
            "origin": "COMMON_EXTERNALLY_EXECUTED_FAILURE_NOT_AGENT_SELECTED",
            "state_before_sha256": digest(before), "decision": inputs["external_decision"],
            "result": inputs["external_public_result"], "consumed_compact_result_sha256": digest(compact),
            "actual_update_site_calls": driver.harness.program.calls[calls:],
            "actual_update_callbacks": driver.callback_records[callbacks:], "state_after": after,
            "autonomous_tool_or_numerical_calls_charged": 0,
            "update_provider_requests": len(driver.callback_records) - callbacks})
        return driver

    rows, error = [], None
    try:
        with runtime_scope():
            for cell in protocol["cells"]:
                configure(protocol)
                with redirect_stdout(io.StringIO()):
                    row = p.run_cell(tuple(cell), protocol, cache, task_resolver=resolve,
                        driver_factory=driver_factory, episode_factory=ContinuedEpisode,
                        initial_state_factory=lambda *args: deepcopy(original_state),
                        initial_observation_factory=lambda *args, **kwargs: deepcopy(external))
                rows.append(row)
                p.save(HERE / "batch-result.json", {"package": PACKAGE, "status": "RUNNING", "episodes": rows})
                print(json.dumps({"episode": row["episode"], "status": row["status"],
                    "last_service": row["last_public_service"], "accounting": row["accounting"],
                    "termination": row["termination"]}), file=CONSOLE, flush=True)
                if old.dependency_stop(row):
                    break
    except BaseException as exc:
        error = type(exc).__name__ + ":" + str(exc)
        raise
    finally:
        lock.unlink()
        result = {"package": PACKAGE, "status": "COMPLETE_TWO_ORIGINAL_CONTINUATIONS" if
            len(rows) == 2 and not error and not old.dependency_stop(rows[-1]) else "STOPPED_ORIGINAL_CONTINUATIONS",
            "episodes": rows, "error": error, "completed_at": old.now(),
            "not_run": [c for c in protocol["cells"] if c[0] not in {x["episode"] for x in rows}],
            "shared_external_failure_new_inputs": 0, "shared_external_failure_new_cost": 0,
            "new_h_g_formation": 0, "no_method_or_science_source_changes": True}
        p.save(HERE / "batch-result.json", result)
    return result


if __name__ == "__main__":
    if sys.argv[1:] != ["run"]:
        raise SystemExit("Use original finite command: run")
    protocol = prepare()
    print(json.dumps({"bound_original_package": PACKAGE, "protocol": bind(PROTOCOL),
                      "episodes": 2, "max_new_science": 6}), flush=True)
    run(protocol)
