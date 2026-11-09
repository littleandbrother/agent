"""Finite BOLD owner: existing provider transport, versioned common consumers.

The engineering owner runs its pre-frozen eight inputs.  This host never repeats
them; it imports their receipts and executes only the reserved method inputs.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT, BASE = HERE.parent, HERE.parent.parent
ROOT = BASE.parents[2]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
PKG = APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261023bold"
PACKAGE = "BF-PQE-BOLD-INTERVENTIONS-20261023-001"
PROTOCOL = OUT / "shared/protocol.json"
sys.path.insert(0, str(BASE / "service-repair-m3/s0"))
spec = importlib.util.spec_from_file_location("bold_frozen_transport", BASE / "f1-conditional-learning/s0/run_learning.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
host, p = legacy.host, legacy.p
now, read, bind, checked, save, identity = legacy.now, legacy.read, legacy.bind, legacy.checked, legacy.save, legacy.identity
PublicObjects = legacy.PublicObjects
from bfworld.agentlab.pqe20261023bold import adapter, lc_adapter
from bfworld.agentlab.pqe20261022.methods import common_contract_check
from bfworld.agentlab.historical_usage import new_batch_usage_blockers

LIMITS = {**legacy.LIMITS, "numerical_inputs": 4, "candidates": 4, "bytes": 55000000}
TOTAL = {**legacy.TOTAL, "requests": 96, "tool_calls": 192, "usd": 40}
PLAN = [("form-h2", "formation", "H2"), ("form-h4", "formation", "H4")]
PLAN += [(role + "-" + c.lower(), role, c) for role in ("t1", "t2") for c in ("H1", "H2", "H4")]


def capacity():
    fs = os.statvfs(ROOT)
    available = fs.f_bavail * fs.f_frsize
    retained = sum(x.stat().st_size for x in OUT.rglob("*") if x.is_file())
    if available < 11000000000 or retained >= 150000000:
        raise ValueError("BOLD_STORAGE_CAP")
    return {"at": now(), "available_bytes": available, "retained_logical_bytes": retained,
            "reclaimed_bytes": 0, "new_backups_environments_worktrees": 0}


def load_task(entry):
    return checked(entry["task"])


def lc_context(entry):
    return {"public": checked(entry["lc_public"]), "host_task": checked(entry["lc_host_task"])} if entry.get("world") == "LC-PV" else None


def world_sources(protocol, entry):
    return protocol["apparatus_source"]["lc" if entry["world"] == "LC-PV" else "door"]


def validate(protocol, **unused):
    for path, digest in protocol.get("source_bindings", {}).items():
        if bind(path)["sha256"] != digest:
            raise ValueError("BOLD_FROZEN_DIRECT_SOURCE_CHANGED:" + path)
    for ref in protocol.get("public_bindings", {}).values():
        checked(ref)
    expected = protocol.get("provider_before", {}).get("historical_unknown_sha256")
    if expected and host.provider_snapshot()["historical_unknown_sha256"] != expected:
        raise ValueError("R11_ORIGINAL_ROW_CHANGED")


def configure(protocol):
    legacy.HERE, legacy.OUT, legacy.PACKAGE, legacy.PROTOCOL = HERE, OUT, PACKAGE, PROTOCOL
    legacy.LIMITS, legacy.TOTAL, legacy.PLAN = LIMITS, TOTAL, PLAN
    legacy.capacity, legacy.validate = capacity, validate
    legacy.configure(protocol)
    p.APP = BASE / "f1-conditional-learning/shared/runtime"
    host.LIMITS = LIMITS


def cache_key(task, design, entry, sources, dt_s=None):
    return identity({"task": task, "design": design, "dt_s": task["integration"]["dt_s"] if dt_s is None else dt_s,
                     "consumer": sources, "lc_inputs": lc_context(entry)})


def child(path):
    job = read(path)
    task = load_task(job["entry"])
    context = lc_context(job["entry"])
    result = adapter.execute(task, job["design"], job["problem"], job["decision"], job["output_dir"],
                             task_resolver=lambda ident: deepcopy(task) if ident == task["task_id"] else None,
                             lc_context=context)
    print(json.dumps({"task_id": task["task_id"], "public_check": result["public_check"]}), flush=True)


def full_execute(entry, state, decision, folder, resource, cache, *, sources, category):
    """Every new original complete input is counted before its child process."""
    task = load_task(entry)
    actual = common_contract_check(state, decision["actual_input"], {"remaining_actions": 1})
    design = {**deepcopy(state["design"]), **actual.get("design_patch", {})}
    problem = {**deepcopy(state["problem"]), **actual.get("problem_patch", {})}
    adapter.validate_design(task, design)
    key = cache_key(task, design, entry, sources, actual.get("dt_s", task["integration"]["dt_s"]))
    attempt = {"at": now(), "category": category, "cache_key": key, "design_sha256": identity(design),
               "task_id": task["task_id"], "decision": deepcopy(decision), "reused": key in cache,
               "new_full_dynamic_inputs": 0, "wall_s": 0}
    if key in cache:
        original = Path(cache[key])
        public = read(original / "public-result.json")
        public["problem"] = problem
        public["usage"] = {"paid_model_requests": 0, "numerical_inputs": 0, "reused": True, "wall_s": 0}
        folder.mkdir(parents=True, exist_ok=False)
        save(folder / "reuse.json", {"original": bind(original / "public-result.json"), "cache_key": key,
                                    "current_problem": problem})
        resource["cache_reuses"] += 1
    else:
        capacity()
        if resource["full_dynamic_inputs"] >= 34 or resource["full_dynamic_wall_s"] >= 3960:
            raise ValueError("BOLD_COMPLETE_INPUT_OR_WALL_CAP")
        resource["full_dynamic_inputs"] += 1
        attempt["new_full_dynamic_inputs"] = 1
        save(HERE / "resource-ledger.json", resource)
        job = {"entry": entry, "design": state["design"], "problem": state["problem"],
               "decision": decision, "output_dir": str(folder)}
        input_file = folder.parent / (folder.name + "-input.json")
        save(input_file, job)
        started = time.monotonic()
        proc = subprocess.Popen([sys.executable, "-B", __file__, "_execute", str(input_file)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                stdout, stderr = proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, stderr = proc.communicate()
            attempt["error"] = "FULL_DYNAMIC_TIMEOUT"
        attempt["wall_s"] = time.monotonic() - started
        resource["full_dynamic_wall_s"] += attempt["wall_s"]
        if proc.returncode or attempt.get("error"):
            attempt.update(exit_code=proc.returncode, stderr_tail=stderr[-4000:])
            resource["attempts"].append(attempt)
            save(HERE / "resource-ledger.json", resource)
            raise ValueError(attempt.get("error", "FULL_DYNAMIC_ERROR:" + stderr[-1500:]))
        original = folder
        public = read(folder / "public-result.json")
        cache[key] = str(folder)
    raw, assessment = read(original / "raw.json"), read(original / "assessment.json")
    if (identity({k: v for k, v in raw.items() if k != "result_sha256"}) != raw["result_sha256"]
            or public["result_sha256"] != raw["result_sha256"] or public["design"] != design
            or public["task_sha256"] != identity(task) or assessment["verdict"] != public["public_check"]["verdict"]):
        raise ValueError("BOLD_COMPLETE_RESULT_BINDING_STOP")
    attempt.update(public_result=bind(original / "public-result.json"), raw=bind(original / "raw.json"),
                   assessment=bind(original / "assessment.json"), public_check=public["public_check"],
                   model_valid=public["model_valid"], domain_errors=public["domain_errors"])
    resource["candidate_evaluations"] += 1
    resource["attempts"].append(attempt)
    save(folder / "readback.json", attempt)
    save(HERE / "resource-ledger.json", resource)
    return public, attempt, original


@contextmanager
def runtime_scope():
    with p.dbconnect() as db:
        if db.execute("SELECT 1 FROM research_model_owners WHERE protocol=?", (PACKAGE,)).fetchone():
            raise ValueError("BOLD_PACKAGE_ALREADY_DISPATCHED_NO_RETRY")
        previous = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        previous = previous["value"] if previous else None
        db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
    save(HERE / "runtime-open.json", {"at": now(), "prior_scope": previous, "study_usd": 40, "owners_max": 8})
    try:
        yield
    finally:
        with p.dbconnect() as db:
            current = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            if not current or current["value"] != json.dumps("per-owner"):
                raise ValueError("CONCURRENT_BUDGET_SCOPE_CHANGE")
            if previous is None:
                db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
            else:
                db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'", (previous,))
            owners = [r[0] for r in db.execute("SELECT owner FROM research_model_owners WHERE protocol=?", (PACKAGE,))]
            for owner in owners:
                db.execute("UPDATE grants SET expires=? WHERE owner=?", (time.time(), owner))
                db.execute("DELETE FROM principals WHERE owner=?", (owner,))
                db.execute("UPDATE conversations SET status='IDLE',updated=? WHERE id=?", (time.time(), owner))
            db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))
        save(HERE / "runtime-closeout.json", {"at": now(), "scope_restored": previous,
             "owners": owners, "provider_after": host.provider_snapshot(), "history_rows_deleted": 0})


class BoldEpisode(legacy.LearningEpisode):
    def ready(self, paid=False):
        if self.fatal:
            raise ValueError(self.fatal)
        budget = self.budget()
        capacity()
        if budget["wall_s"] >= 900 or sum(x.stat().st_size for x in self.root.rglob("*") if x.is_file()) >= LIMITS["bytes"]:
            raise ValueError("BOLD_EPISODE_WALL_OR_STORAGE_CAP")
        with p.dbconnect() as db:
            if new_batch_usage_blockers(db, self.owner):
                self.fatal = "NEW_USAGE_UNKNOWN_STOP"
                raise ValueError(self.fatal)
            if paid:
                rows = db.execute("SELECT mr.charged FROM model_requests mr JOIN research_model_owners ro ON ro.owner=mr.owner WHERE ro.protocol=?", (PACKAGE,)).fetchall()
                if len(rows) >= 96 or sum(r[0] or 0 for r in rows) + .19 > 40:
                    raise ValueError("BOLD_GLOBAL_MODEL_CAP")
        if self.tools > 24:
            raise ValueError("COMBINED_TOOL_CAP")
        if paid and (budget["model_requests"] >= 12 or budget["output_tokens"] >= 131072 or budget["spent_usd"] + .19 > 5):
            raise ValueError("BOLD_EPISODE_MODEL_CAP")
        return budget

    def full_evaluator(self, request):
        from bfworld.agentlab.pqe20261022.methods import digest
        candidates = request["candidates"]
        if self.evaluations + len(candidates) > 4:
            raise ValueError("BOLD_FOUR_EVALUATED_CANDIDATES_CAP")
        entry = next(e for e in self.protocol["tasks"] if e["role"] == self.role)
        resource = read(HERE / "resource-ledger.json")
        rows = []
        for candidate in candidates:
            self.ready()
            if self.tools >= 24:
                raise ValueError("BOLD_COMBINED_TOOL_CAP")
            self.tools += 1
            self.evaluations += 1
            before = resource["full_dynamic_inputs"]
            folder = self.root / "candidates" / f"{self.evaluations:02d}"
            try:
                public, receipt, original = full_execute(entry,
                    {"task": self.task, "design": self.design, "problem": self.problem},
                    {"selected_id": candidate["id"], "actual_input": candidate["actual_input"]},
                    folder, resource, self.cache, sources=world_sources(self.protocol, entry),
                    category=self.ident)
            finally:
                self.numerical += resource["full_dynamic_inputs"] - before
                save(HERE / "resource-ledger.json", resource)
            # The canonical original PUBLIC object retains its exact bytes.
            # A cache receipt records the current Problem/usage view separately.
            original_public = read(original / "public-result.json")
            oid = self.objects.register(original_public, path=original / "public-result.json")
            self.objects.save_index()
            self.screened = getattr(self, "screened", {})
            self.screened[candidate["id"]] = {"result": public, "ref": oid, "receipt": receipt,
                                               "actual_input": deepcopy(candidate["actual_input"])}
            rows.append({"candidate_id": candidate["id"], "actual_input_digest": digest(candidate["actual_input"]),
                         "public_result": public, "public_object_ref": oid,
                         "accounting": {"numerical_inputs": receipt["new_full_dynamic_inputs"],
                                        "tool_calls": 1, "cache_reuse": receipt["reused"]}})
        return {"results": rows, "owner_budget_after": snapshot(self)}

    def consume_selected(self, decision):
        from bfworld.agentlab.pqe20261022.methods import digest
        self.ready()
        pre = decision.get("pre_evaluation", {})
        item = self.screened.get(decision["selected_id"])
        if (not item or digest(decision["actual_input"]) != digest(item["actual_input"])
                or pre.get("result_sha256") != item["result"]["result_sha256"]
                or pre.get("public_object_ref") != item["ref"]):
            raise ValueError("BOLD_SELECTED_EXACT_INPUT_BINDING_STOP")
        if self.tools >= 24:
            raise ValueError("BOLD_COMBINED_TOOL_CAP")
        self.tools += 1
        result = deepcopy(item["result"])
        result["usage"] = {"paid_model_requests": 0, "numerical_inputs": 0, "reused": True,
                           "wall_s": 0, "basis": "ALREADY_COUNTED_FULL_CANDIDATE_EVALUATION"}
        self.last_full, self.design, self.problem = result, deepcopy(result["design"]), deepcopy(result["problem"])
        row = {"number": len(self.actions) + 1, "actual_input": decision["actual_input"],
               "selected_id": decision["selected_id"], "public_check": result["public_check"],
               "public_object_ref": item["ref"], "pre_evaluation": pre,
               "full_evaluation_receipt": item["receipt"], "new_full_dynamic_inputs": 0}
        self.actions.append(row)
        save(self.root / "selected-actions.json", self.actions)
        return result, item["ref"]


def snapshot(ep):
    b = ep.ready()
    return {"provider_requests_remaining": 12 - b["model_requests"], "tool_calls_remaining": 24 - ep.tools,
            "new_numerical_inputs_remaining": max(0, 4 - ep.evaluations),
            "reserve_usd_remaining": 5 - b["spent_usd"], "wall_s_remaining": 900 - b["wall_s"],
            "output_tokens_remaining": 131072 - b["output_tokens"]}


def public_objects(ident, protocol):
    objects = PublicObjects(HERE / "episodes" / ident / "public-objects")
    catalog = []
    sources = checked(protocol["public_bindings"]["catalog"])
    for name, ref in sources.get("sources", sources).items():
        value = checked(ref)
        oid = objects.register(value, path=ref["path"])
        catalog.append({"source_id": name, "views": [{"original_pointer": "", "object_id": oid}]})
    return objects, catalog


def one_episode(ident, role, condition, protocol, cache, formed):
    from bfworld.agentlab.pqe20261023bold.drivers import BoldFormationDriver, BoldEpisodeDriver
    parent = checked(protocol["public_bindings"]["parent"])["program"]
    history = checked(protocol["public_bindings"]["history"])
    if role != "formation" and condition in {"H2", "H4"} and not formed.get(condition, {}).get("selected_candidate"):
        row = {"episode": ident, "role": role, "condition": condition,
               "status": "NOT_EXECUTED_NO_QUALIFIED_DESCENDANT", "provider_requests": 0,
               "candidate_evaluations": 0, "new_full_dynamic_inputs": 0}
        save(HERE / "skipped" / (ident + ".json"), row)
        return row
    task, initial = {"task_id": "NO_TARGET_METHOD_FORMATION", "initial_design": {}, "initial_problem": {}}, None
    if role != "formation":
        entry = next(e for e in protocol["tasks"] if e["role"] == role)
        task, initial = load_task(entry), checked(entry["initial_public_result"])
    ep = BoldEpisode(ident, task, condition, protocol, cache, role, None)
    ep.objects, ep.public_catalog = public_objects(ident, protocol)
    error = formation = None
    try:
        ep.start_server()
        limits = {"output_tokens_per_request": 65536, "output_tokens_total": 131072,
                  "reserve_usd": 5, "new_numerical_inputs": 4}
        if role == "formation":
            driver = BoldFormationDriver(condition, ep.planner, parent=parent, history=history,
                episode_id=ident, model_identity=p.MODEL_IDENTITY, request_reserve_usd=.19, limits=limits)
            ep.driver = driver
            formation = driver.run()
            ep.audit(ep.root / "formation.json", formation)
            save(ep.root / "selected-program.json", formation["selected_program"])
            formed[condition] = formation
        else:
            program = formed[condition]["selected_program"] if condition in {"H2", "H4"} else parent
            state = p.episode_initial_state(task, task["initial_design"], task["initial_problem"])
            state["last_result"] = deepcopy(initial)
            initial_ref = ep.objects.register(initial, path=entry["initial_public_result"]["path"])
            ep.last_full = initial
            driver = BoldEpisodeDriver("strong_generic", ep.planner, episode_id=ident, initial_state=state,
                initial_public_object_ref=initial_ref, model_identity=p.MODEL_IDENTITY,
                request_reserve_usd=.19, limits=limits, max_contract_corrections=2, program=program,
                common_history=history, expected_methods_sha256=protocol["source_bindings"][str(legacy.PKG / "methods.py")],
                isolated_program=True, full_evaluator=ep.full_evaluator)
            ep.driver = driver
            driver.apply_initial_update(snapshot(ep))
            ep.audit(ep.root / "initial-update.json", driver.transcript())
            while ep.evaluations < 4:
                action = driver.next(snapshot(ep))
                if action["status"] != "ACTION":
                    break
                result, ref = ep.consume_selected(action["decision"])
                driver.update(result, public_object_ref=ref)
                if result["model_valid"] and result["public_check"]["verdict"] == "PASS":
                    driver.finish("ORIGINAL_COMPLETE_SERVICE_PASS")
                    break
            if ep.evaluations >= 4 and driver.termination is None:
                driver.finish("FOUR_EVALUATED_CANDIDATE_CAP")
            ep.audit(ep.root / "method-transcript.json", driver.transcript())
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
        if ep.driver is not None:
            ep.audit(ep.root / "retained-driver-error.json", ep.driver.transcript())
    finally:
        ep.close()
    account = p.ledger(p.DATABASE, ep.owner)
    save(ep.root / "provider-costs.json", account)
    row = {"package": PACKAGE, "episode": ident, "role": role, "condition": condition,
           "owner": ep.owner, "status": "RETAINED_ERROR" if error or ep.fatal else "FINITE_ATTEMPT_COMPLETE",
           "error": error, "fatal": ep.fatal, "wall_s": time.monotonic() - ep.started,
           "accounting": {k: v for k, v in account.items() if k != "rows"}, "actions": ep.actions,
           "candidate_evaluations": ep.evaluations, "new_full_dynamic_inputs": ep.numerical,
           "cheap_relation_calls": ep.cheap_calls, "explicit_tools": ep.tools,
           "program_calls": getattr(getattr(getattr(ep.driver, "harness", None), "program", None), "calls", []),
           "service_origin": "SELECTED_CANDIDATE" if ep.actions else "INITIAL_ONLY" if initial else "NO_TASK_FORMATION",
           "last_public_check": ep.last_full["public_check"] if ep.last_full else None,
           "termination": getattr(ep.driver, "termination", None),
           "selected_descendant": bool(formation and formation.get("selected_candidate"))}
    save(ep.root / "episode-result.json", row)
    print(json.dumps({"event": "BOLD_EPISODE_COMPLETE", "episode": ident, "status": row["status"],
         "error": error, "service": row["last_public_check"], "requests": account["requests"],
         "selected_descendant": row["selected_descendant"]}), flush=True)
    return row


def run():
    protocol = read(PROTOCOL)
    configure(protocol)
    validate(protocol)
    if (HERE / "run-started.json").exists():
        with p.dbconnect() as db:
            dispatched = db.execute("SELECT 1 FROM research_model_owners WHERE protocol=?", (PACKAGE,)).fetchone()
        if dispatched or not (HERE / "pre-dispatch-repair.json").exists():
            raise ValueError("BOLD_STARTED_NO_REPLACEMENTS")
    else:
        save(HERE / "run-started.json", {"at": now(), "package": PACKAGE})
    cache, formed, rows = {}, {}, []
    for entry in protocol["tasks"]:
        task, initial = load_task(entry), checked(entry["initial_public_result"])
        key = cache_key(task, initial["design"], entry, world_sources(protocol, entry))
        cache[key] = str(Path(entry["initial_public_result"]["path"]).parent)
    with runtime_scope():
        for ident, role, condition in PLAN:
            validate(protocol)
            row = one_episode(ident, role, condition, protocol, cache, formed)
            rows.append(row)
            save(HERE / "batch-result.json", {"package": PACKAGE, "at": now(), "rows": rows, "complete": False})
            if ident == "form-h4":
                save(HERE / "formed-program-freeze.json", {"at": now(), "no_task_feedback_seen": True,
                     "conditions": {c: {"qualified_descendant": bool(v.get("selected_candidate")),
                         "program": bind(HERE / "episodes" / ("form-" + c.lower()) / "selected-program.json")}
                         for c, v in formed.items()}})
            with p.dbconnect() as db:
                missing = list(db.execute("SELECT id FROM model_requests WHERE (status='UNKNOWN' OR (status='SETTLED' AND usage IS NULL)) AND id!='llm-1de4d60d9bc93d257392'"))
                if missing:
                    raise ValueError("NEW_USAGE_UNKNOWN_STOP_ALL_DEPENDENT_DISPATCH")
    save(HERE / "batch-result.json", {"package": PACKAGE, "at": now(), "rows": rows, "complete": True,
         "provider_after": host.provider_snapshot(), "postflight": capacity()})


def initial_lc():
    """The one authorized common initial LC input; not a qualification sweep."""
    freeze = read(OUT / "a/host/TASK-FREEZE.json")
    public, host_task = checked(freeze["lc_public"]), checked(freeze["lc"])
    task = lc_adapter.participant_task(public)
    task_path = HERE / "host/lc-driver-task.json"
    if task_path.exists():
        raise ValueError("BOLD_LC_INITIAL_ALREADY_PREPARED_NO_RETRY")
    save(task_path, task)
    entry = {"role": "t2", "world": "LC-PV", "task": bind(task_path),
             "lc_public": freeze["lc_public"], "lc_host_task": freeze["lc"]}
    resource_path = HERE / "resource-ledger.json"
    resource = read(resource_path) if resource_path.exists() else {
        "package": PACKAGE, "full_dynamic_inputs": 0, "full_dynamic_wall_s": 0,
        "candidate_evaluations": 0, "cache_reuses": 0, "attempts": []}
    # Source identity is LC-only here: A's new door consumer is still being
    # implemented and no door code is used by this initial execution.
    result, receipt, _ = full_execute(entry, {"task": task, "design": task["initial_design"],
        "problem": task["initial_problem"]}, {"actual_input": {"operation": "observe", "design_patch": {}, "problem_patch": {}}},
        HERE / "host/lc-initial", resource, {}, sources=lc_adapter.source_identity(), category="INITIAL_LC")
    entry.update(initial_public_result=receipt["public_result"], status="READY")
    save(HERE / "host/lc-entry.json", entry)
    print(json.dumps({"event": "BOLD_LC_INITIAL_COMPLETE", "public_check": result["public_check"],
                      "full_wall_s": receipt["wall_s"], "new_inputs": 1}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["initial-lc", "run", "_execute"])
    parser.add_argument("input", nargs="?")
    args = parser.parse_args()
    child(args.input) if args.phase == "_execute" else run() if args.phase == "run" else initial_lc()
