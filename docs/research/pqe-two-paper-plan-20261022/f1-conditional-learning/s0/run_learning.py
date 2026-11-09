"""Thin finite owner around the existing F1 drivers, Pi transport and consumer.

Old frozen packages remain unchanged. New tasks enter only after formation.
No descendant is repaired or reformed after an experimental model response.
"""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time

HERE = Path(__file__).resolve().parent
OUT, BASE = HERE.parent, HERE.parent.parent
ROOT = BASE.parents[2]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
PKG = APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022"
PACKAGE = "BF-PQE-F1-CONDITIONAL-LEARNING-20261023-001"
PROTOCOL = OUT / "shared/protocol.json"
sys.path.insert(0, str(BASE / "service-repair-m3/s0"))
spec = importlib.util.spec_from_file_location("learning_complete_consumer", BASE / "service-repair-m3/s0/run_m3.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
now, read, bind, checked, save = host.now, host.read, host.bind, host.checked, host.save
p, adapter, identity = host.p, host.adapter, host.identity
from public_projection import PublicObjects, encoded
from bfworld.agentlab.pqe20261022 import f1first as f1
from bfworld.agentlab.pqe20261022.m3_methods import M3GenericHarness, SERVICE_TOOLS
from bfworld.agentlab.historical_usage import new_batch_usage_blockers

LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=3, candidates=3,
              wall_s=900, output_tokens=65536, generated_tokens=131072, usd=5, bytes=12000000)
TOTAL = dict(requests=144, tool_calls=288, numerical_inputs=34, usd=60, retained_bytes=150000000)
PLAN = [("form-h2", "formation", "H2"), ("form-h4", "formation", "H4")]
PLAN += [(role + "-" + c.lower(), role, c) for role in ("t1", "t2") for c in ("H0", "H1", "H2", "H3", "H4")]


def capacity():
    fs = os.statvfs(ROOT)
    available = fs.f_bavail * fs.f_frsize
    retained = sum(x.stat().st_size for x in OUT.rglob("*") if x.is_file())
    if available < 11000000000 or retained >= 150000000:
        raise ValueError("LEARNING_STORAGE_GATE")
    return {"at": now(), "available_bytes": available, "retained_logical_bytes": retained,
            "deleted_bytes": 0, "new_backups_environments_worktrees": 0}


def validate(protocol, **unused):
    for path, expected in protocol["source_bindings"].items():
        if bind(path)["sha256"] != expected:
            raise ValueError("FROZEN_DIRECT_SOURCE_CHANGED:" + path)
    for ref in protocol["public_bindings"].values():
        checked(ref)
    if host.provider_snapshot()["historical_unknown_sha256"] != protocol["provider_before"]["historical_unknown_sha256"]:
        raise ValueError("R11_ORIGINAL_ROW_CHANGED")


def configure(protocol):
    p.OUT, p.PACKAGE, p.LIMITS, p.TOTAL_CAPS, p.CELLS = OUT, PACKAGE, LIMITS, TOTAL, PLAN
    p.SDK = Path(protocol["model_contract"]["sdk_entry"])
    # Only the existing callback transport uses p.APP at this entry. Scientific
    # adapter.APP and every source file retain their original identities.
    p.APP = OUT / "shared/runtime"
    p.validate_wire = validate_wire
    p.callback_payload = callback_payload
    f1.OUT = OUT
    host.PROTOCOL, host.PACKAGE, host.OUT, host.LIMITS = PROTOCOL, PACKAGE, OUT, LIMITS
    host.__file__, host.validate, host.capacity = str(Path(__file__).resolve()), validate, capacity


def validate_wire(body, output_cap=65536):
    if body.get("model") != "deepseek-flash" or body.get("stream") is not True:
        raise ValueError("PINNED_MODEL_STREAM_REQUIRED")
    if body.get("tools") or body.get("tool_choice") not in (None, "none", "auto"):
        raise ValueError("MODEL_NATIVE_TOOLS_DENIED")
    if any(m.get("role") == "tool" or m.get("tool_calls") for m in body.get("messages", [])):
        raise ValueError("MODEL_TOOL_HISTORY_DENIED")
    output = body.get("max_tokens", body.get("max_completion_tokens"))
    if (type(output_cap) is not int or not 1 <= output_cap <= 65536
            or type(output) is not int or not 1 <= output <= output_cap):
        raise ValueError("COMMON_OUTPUT_GRANT")
    if "max_tokens" in body and "max_completion_tokens" in body and body["max_tokens"] != body["max_completion_tokens"]:
        raise ValueError("AMBIGUOUS_OUTPUT_CAP")
    if len(encoded(body)) > 400000:
        raise ValueError("PUBLIC_WIRE_BYTES_CAP_PRE_FORWARD")
    return {k: v for k, v in {**body, "temperature": .2, "max_tokens": output}.items() if k != "max_completion_tokens"}


def callback_payload(request, output_cap):
    if len(encoded(request)) > 240000:
        raise ValueError("PUBLIC_PROJECTED_BYTES_CAP_PRE_FORWARD")
    forming = request.get("site", "").startswith("G-")
    instruction = ("Real accountable method formation. Restricted H source is allowed only in declared patch.code JSON strings. "
                   if forming else "Real accountable BF design-method callback. Return validated JSON actions, not executable code outside the loaded H. ")
    instruction += ("Return exactly one JSON object using the supplied site contract. No Markdown. No filesystem, shell, native tools, credentials or hidden evaluator. "
        "Only supplied public facts and declared PUBLIC_TOOLS are available. Public paging references resolve through public_object. "
        "No update, uncertainty, scoped rejection and supported stop are valid. Do not change science, permissions, quotas, accounting or adoption.")
    return {"instruction": instruction, "request": request, "max_output_tokens": output_cap}


@contextmanager
def runtime_scope():
    with p.dbconnect() as db:
        if db.execute("SELECT 1 FROM research_model_owners WHERE protocol=?", (PACKAGE,)).fetchone():
            raise ValueError("PACKAGE_ALREADY_DISPATCHED_NO_RETRY")
        previous = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        previous = previous["value"] if previous else None
        db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
    save(HERE / "runtime-open.json", {"at": now(), "prior_scope": previous, "study_usd": 60, "owners_max": 12})
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
            owners = [x[0] for x in db.execute("SELECT owner FROM research_model_owners WHERE protocol=?", (PACKAGE,))]
            for owner in owners:
                db.execute("UPDATE grants SET expires=? WHERE owner=?", (time.time(), owner))
                db.execute("DELETE FROM principals WHERE owner=?", (owner,))
                db.execute("UPDATE conversations SET status='IDLE',updated=? WHERE id=?", (time.time(), owner))
            db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))
        save(HERE / "runtime-closeout.json", {"at": now(), "scope_restored": previous,
            "owners": owners, "provider_after": host.provider_snapshot(), "history_rows_deleted": 0})


class LearningEpisode(f1.F1Episode):
    start_server = host.ModelEpisode.start_server

    def __init__(self, ident, task, condition, protocol, cache, role, objects):
        super().__init__(ident, task, condition, protocol, cache, task_role=role)
        self.objects, self.role = objects, role
        self.public_catalog = []
        self.public_tools = M3GenericHarness(lambda request: None, public_reader=self.public_read)
        self.public_tools._known_result = self.known_result
        self.driver, self.cheap_calls, self.evaluations = None, 0, 0
        self.local_ledger = {"full_dynamic_inputs": 0, "full_dynamic_wall_s": 0,
            "evaluations_including_reuse": 0, "cache_reuses": 0, "categories": {}, "attempts": []}
        save(self.root / "owner.json", {"owner": self.owner, "episode": ident, "finite_usd": 5,
            "grant_wall_s": 900, "no_unbounded_authorization": True, "role": role})

    def known_result(self, state, identifier=None):
        identifier = self.last_full.get("result_sha256") if identifier in (None, "last") and self.last_full else identifier
        obj = self.objects.results.get(identifier)
        if not obj:
            raise ValueError("KNOWN_CURRENT_PUBLIC_RESULT_REQUIRED")
        value = self.objects._get(obj)
        if value.get("task_id") != self.task.get("task_id"):
            raise ValueError("HISTORY_IS_READABLE_NOT_CURRENT_TASK_PREDICTION_INPUT")
        return value

    def public_read(self, arguments):
        args = deepcopy(arguments)
        key = args.get("object_id", args.get("public_object_ref"))
        for source in self.public_catalog:
            if key != source["source_id"]:
                continue
            section = args.get("section", "")
            for view in source["views"]:
                prefix = view["original_pointer"]
                if section == prefix or not prefix or section.startswith(prefix + "/"):
                    args.update(object_id=view["object_id"], section=section[len(prefix):])
                    return self.objects.read(args)
            raise ValueError("PUBLIC_SOURCE_SECTION_NOT_ALLOWED")
        return self.objects.read(args)

    def ready(self, paid=False):
        if self.fatal:
            raise ValueError(self.fatal)
        budget = self.budget()
        capacity()
        if budget["wall_s"] >= 900 or sum(x.stat().st_size for x in self.root.rglob("*") if x.is_file()) >= 12000000:
            raise ValueError("EPISODE_WALL_OR_STORAGE_CAP")
        with p.dbconnect() as db:
            if new_batch_usage_blockers(db, self.owner):
                self.fatal = "NEW_USAGE_UNKNOWN_STOP"
                raise ValueError(self.fatal)
        if self.tools > 24:
            raise ValueError("COMBINED_TOOL_CAP")
        if paid and (budget["model_requests"] >= 12 or budget["output_tokens"] >= 131072 or budget["spent_usd"] + .19 > 5):
            raise ValueError("EPISODE_MODEL_CAP")
        if paid:
            with p.dbconnect() as db:
                rows = db.execute("SELECT mr.charged FROM model_requests mr JOIN research_model_owners ro ON ro.owner=mr.owner WHERE ro.protocol=?", (PACKAGE,)).fetchall()
                if len(rows) >= 144 or sum(r[0] or 0 for r in rows) + .19 > 60:
                    raise ValueError("GLOBAL_MODEL_CAP")
        return budget

    def resolve_frozen_task(self, task_id):
        if self.role not in ("t1", "t2") or task_id != self.task["task_id"]:
            raise ValueError("CURRENT_ROLE_TASK_ONLY")
        return deepcopy(self.task)

    def audit(self, path, value):
        # Content-addressed references preserve the exact public object shape.
        # There is no model-prompt cap on the audit graph or complete chain.
        def walk(v):
            if isinstance(v, dict):
                if v.get("result_sha256") and "facts" in v:
                    ident = self.objects.register(v)
                    return {"audit_public_object": ident, "sha256": self.objects.objects[ident]["sha256"]}
                return {k: walk(x) for k, x in v.items()}
            return [walk(x) for x in v] if isinstance(v, list) else v
        save(path, walk(value))
        self.objects.save_index()

    def planner(self, request):
        validate(self.protocol)
        context, total_usage, ids, calls = deepcopy(request), dict(cost=0, input_tokens=0, output_tokens=0), [], []
        site_cap = request["max_output_tokens"]
        while True:
            remaining = site_cap - total_usage["output_tokens"]
            if remaining <= 0:
                response = {"payload": {"status": "OUTPUT_TOKEN_BUDGET_EXHAUSTED"}, "provider_status": "COMPLETE"}
                break
            body = self.objects.project(deepcopy(context))
            body.update(max_output_tokens=min(remaining, p.output_allowance(self.budget()["output_tokens"], LIMITS)),
                        shared_public_tools=deepcopy(SERVICE_TOOLS), shared_public_catalog=self.public_catalog)
            if self.role == "formation" and ids:
                self.driver._consume_unit("PUBLIC_TOOL_CONTINUATION_CALLBACK")
            before = p.ledger(p.DATABASE, self.owner)
            self.dispatch_stage, self.call_relays = "TRUSTED_LOCAL_PREFLIGHT", 0
            try:
                response = p.Episode.planner(self, body)
            except Exception as exc:
                after = p.ledger(p.DATABASE, self.owner)
                rows = [x for x in after["rows"] if x["id"] not in {r["id"] for r in before["rows"]}]
                local = not rows and getattr(self, "dispatch_stage", "TRUSTED_LOCAL_PREFLIGHT") == "TRUSTED_LOCAL_PREFLIGHT"
                save(self.root / "local-planner-error.json", {"error": type(exc).__name__ + ":" + str(exc),
                    "classification": "LOCAL_TOOL_NOT_EXECUTED" if local else "NEW_PROVIDER_USAGE_UNKNOWN_STOP",
                    "provider_rows": len(rows), "forwarded": bool(getattr(self, "call_relays", 0))})
                return {"payload": {"status": "TOOL_ERROR"}, "provider_status": "TOOL_ERROR",
                        "usage": {"status": "NOT_DISPATCHED" if local else "UNKNOWN", "model_identity": p.MODEL_IDENTITY}, "error": str(exc)}
            usage = response.get("usage", {})
            if usage.get("status") != "KNOWN":
                after = p.ledger(p.DATABASE, self.owner)
                new_rows = [r for r in after["rows"] if r["id"] not in {x["id"] for x in before["rows"]}]
                if not new_rows and not self.call_relays and self.dispatch_stage == "TRUSTED_LOCAL_PREFLIGHT":
                    self.fatal = "LOCAL_TOOL_NOT_EXECUTED"
                    response["usage"] = {"status": "NOT_DISPATCHED", "model_identity": p.MODEL_IDENTITY}
                    response["classification"] = "LOCAL_TOOL_NOT_EXECUTED"
                return response
            for k in total_usage:
                total_usage[k] += usage[k]
            ids += response.get("request_ids", [])
            payload = response.get("payload", {})
            if response.get("provider_status") != "COMPLETE" or payload.get("status") != "PUBLIC_TOOLS":
                break
            tool_requests = payload.get("tool_calls")
            if not isinstance(tool_requests, list) or not 1 <= len(tool_requests) <= 24 - self.tools:
                response["payload"] = {"status": "INVALID_PUBLIC_TOOL_REQUEST"}
                break
            state = self.driver.state if self.role != "formation" else {"task": {}, "history": self.driver.history}
            results = []
            for call in tool_requests:
                if self.role == "formation":
                    self.driver._consume_unit("PUBLIC_TOOL_REQUEST", name=call.get("name"))
                if self.role == "formation" and call.get("name") != "public_object":
                    results.append({"id": call.get("id"), "status": "TOOL_ERROR", "error": "Formation has public-history paging only; no task/prediction solver."})
                    self.tools += 1
                    continue
                is_cheap = call.get("name") in {"predict_candidate", "engineering_relations"}
                if is_cheap:
                    if self.cheap_calls >= 12:
                        raise ValueError("EPISODE_CHEAP_CAP")
                    self.cheap_calls += 1
                self.public_tools._budget({"analytic_scores_left": 12 - self.cheap_calls + int(is_cheap), "public_tool_calls_left": 24 - self.tools})
                results.append(self.public_tools._tool(state, call))
                self.tools += 1
            calls.append({"requests": tool_requests, "results": results})
            save(self.root / "public-tool-log.json", calls)
            if any(x.get("status") != "OK" for x in results):
                response["payload"] = {"status": "TOOL_ERROR", "public_tool_results": results}
                break
            context = {**request, "public_tool_results": calls}
        response["usage"] = {"status": "KNOWN", "model_identity": p.MODEL_IDENTITY, **total_usage, "request_ids": ids}
        response["request_ids"] = ids
        return response

    def consume(self, decision):
        self.ready()
        if decision["actual_input"].get("operation") in {"report", "select"}:
            self.tools += 1
            if self.tools > 24:
                raise ValueError("COMBINED_TOOL_CAP")
            folder = self.root / "nonexecuting-action"
            public = adapter.execute(self.task, self.design, self.problem, decision, str(folder), task_resolver=self.resolve_frozen_task)
            save(self.root / "nonexecuting-action.json", public)
            return public
        if self.evaluations >= 3:
            raise ValueError("THREE_EVALUATED_CANDIDATE_CAP")
        self.tools += 1
        if self.tools > 24:
            raise ValueError("COMBINED_TOOL_CAP")
        global_ledger = read(HERE / "resource-ledger.json")
        if global_ledger["full_dynamic_inputs"] >= 34 or global_ledger["full_dynamic_wall_s"] >= 3960:
            raise ValueError("GLOBAL_COMPLETE_CONSUMER_CAP")
        entry = next(e for e in self.protocol["tasks"] if e["role"] == self.role)
        state = {"task": self.driver.state["task"], "design": self.design, "problem": self.problem}
        host.HERE = self.root
        folder = self.root / "actions" / f"{self.evaluations + 1:02d}"
        before = {k: self.local_ledger[k] for k in ("full_dynamic_inputs", "full_dynamic_wall_s", "cache_reuses")}
        prior_attempts = len(self.local_ledger["attempts"])
        try:
            public, consequence = host.execute(entry, state, decision, folder, self.local_ledger,
                self.cache, self.protocol, self.ident)
        finally:
            # A failed/timeout consumer still spent its original input and wall
            # allowance. Never erase that cost by omitting the global update.
            attempts = len(self.local_ledger["attempts"]) - prior_attempts
            self.evaluations += attempts
            self.numerical = self.local_ledger["full_dynamic_inputs"]
            for key in before:
                global_ledger[key] += self.local_ledger[key] - before[key]
            global_ledger["candidate_evaluations"] += attempts
            save(HERE / "resource-ledger.json", global_ledger)
        self.objects.register(public, path=folder / "public-result.json")
        self.last_full, self.design, self.problem = public, deepcopy(public["design"]), deepcopy(public["problem"])
        self.actions.append({"number": self.evaluations, "actual_input": decision["actual_input"],
            "path": str(folder), "public_check": public["public_check"], "usage": public["usage"],
            "candidate_evaluation": True, "readback": bind(folder / "readback.json")})
        return public


def public_objects(ident, protocol, include_history):
    objects = PublicObjects(HERE / "episodes" / ident / "public-objects")
    catalog = []
    if include_history:
        for name, ref in checked(protocol["public_bindings"]["catalog"])["sources"].items():
            if bind(ref["path"])["sha256"] != ref["sha256"]:
                raise ValueError("PUBLIC_HISTORY_SOURCE_CHANGED")
            is_lines = ref.get("format") == "PUBLIC_JSONL"
            value = [json.loads(line) for line in Path(ref["path"]).read_text().splitlines() if line.strip()] if is_lines else checked(ref)
            views = []
            for pointer in ref["allowed_json_pointers"]:
                part = objects._section(value, pointer)
                oid = objects.register(part, path=ref["path"] if pointer == "" and not is_lines else None)
                views.append({"original_pointer": pointer, "object_id": oid})
            catalog.append({"source_id": name, "views": views})
    return objects, catalog


def snapshot(ep):
    b = ep.ready()
    return {"provider_requests_remaining": 12 - b["model_requests"], "tool_calls_remaining": 24 - ep.tools,
            "new_numerical_inputs_remaining": 3 - ep.numerical, "reserve_usd_remaining": 5 - b["spent_usd"],
            "wall_s_remaining": 900 - b["wall_s"], "output_tokens_remaining": 131072 - b["output_tokens"]}


def one_episode(ident, role, condition, protocol, cache, formed):
    from bfworld.agentlab.pqe20261022.conditional_learning_methods import ConditionalFormationDriver, ConditionalEpisodeDriver
    parent = checked(protocol["public_bindings"]["parent"])["program"]
    history = checked(protocol["public_bindings"]["history"])
    if role != "formation" and condition in {"H2", "H4"} and not formed.get(condition, {}).get("selected_candidate"):
        value = {"episode": ident, "role": role, "condition": condition, "status": "NOT_EXECUTED_NO_QUALIFIED_DESCENDANT",
                 "provider_requests": 0, "candidate_evaluations": 0, "reason": "Retained formation error/no-update, never substitute parent as descendant success."}
        save(HERE / "skipped" / (ident + ".json"), value)
        return value
    task, initial = {"task_id": "NO_TARGET_METHOD_FORMATION", "initial_design": {}, "initial_problem": {}}, None
    if role != "formation":
        entry = next(e for e in protocol["tasks"] if e["role"] == role)
        if entry.get("status") != "READY":
            value = {"episode": ident, "role": role, "condition": condition, "status": "NOT_INCLUDED_INITIAL_QUALIFICATION", "provider_requests": 0}
            save(HERE / "skipped" / (ident + ".json"), value)
            return value
        task, initial = host.load_task(entry), checked(entry["initial_public_result"])
    # Constructor creates the episode root; the registry folder is lazy-created afterwards.
    ep = LearningEpisode(ident, task, condition, protocol, cache, role, None)
    ep.objects, ep.public_catalog = public_objects(ident, protocol, condition != "H0")
    error, formation = None, None
    try:
        ep.start_server()
        limits = dict(output_tokens_per_request=65536, output_tokens_total=131072, reserve_usd=5, new_numerical_inputs=3)
        if role == "formation":
            driver = ConditionalFormationDriver(condition, ep.planner, parent=parent, history=history,
                episode_id=ident, model_identity=p.MODEL_IDENTITY, request_reserve_usd=.19, limits=limits)
            ep.driver = driver
            formation = driver.run()
            ep.audit(ep.root / "formation.json", formation)
            # Exact executable program is separately frozen, never reconstructed from a projected audit.
            save(ep.root / "selected-program.json", formation["selected_program"])
            formed[condition] = formation
        else:
            program = checked(protocol["public_bindings"]["h3"])["program"] if condition == "H3" else formed[condition]["selected_program"] if condition in {"H2", "H4"} else parent
            state = p.episode_initial_state(task, task["initial_design"], task["initial_problem"])
            state["last_result"] = deepcopy(initial)
            ep.objects.register(initial, path=entry["initial_public_result"]["path"])
            ep.last_full = initial
            driver = ConditionalEpisodeDriver("strong_generic", ep.planner, episode_id=ident, initial_state=state,
                model_identity=p.MODEL_IDENTITY, request_reserve_usd=.19, limits=limits,
                max_contract_corrections=2, program=program, common_history=[] if condition == "H0" else history,
                expected_methods_sha256=protocol["source_bindings"][str(PKG / "methods.py")], isolated_program=True)
            ep.driver = driver
            driver.apply_initial_update(snapshot(ep))
            ep.audit(ep.root / "initial-update.json", driver.transcript())
            while ep.evaluations < 3:
                action = driver.next(snapshot(ep))
                if action["status"] != "ACTION":
                    break
                result = ep.consume(action["decision"])
                driver.update(result)
                if result.get("execution_status") == "NO_EXECUTION":
                    driver.finish("REPORTED_WITHOUT_COMPLETE_CANDIDATE")
                    break
                if result["model_valid"] and result["public_check"]["verdict"] == "PASS":
                    driver.finish("ORIGINAL_COMPLETE_SERVICE_PASS")
                    break
            if ep.evaluations >= 3 and driver.termination is None:
                driver.finish("THREE_EVALUATED_CANDIDATE_CAP")
            ep.audit(ep.root / "method-transcript.json", driver.transcript())
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
        if ep.driver is not None:
            ep.audit(ep.root / "retained-driver-error.json", ep.driver.transcript())
    finally:
        ep.close()
    account = p.ledger(p.DATABASE, ep.owner)
    save(ep.root / "provider-costs.json", account)
    value = {"package": PACKAGE, "episode": ident, "role": role, "condition": condition,
        "owner": ep.owner, "status": "RETAINED_ERROR" if error or ep.fatal else "FINITE_ATTEMPT_COMPLETE",
        "error": error, "fatal": ep.fatal, "wall_s": time.monotonic() - ep.started,
        "accounting": {k: v for k, v in account.items() if k != "rows"}, "actions": ep.actions,
        "candidate_evaluations": ep.evaluations, "new_full_dynamic_inputs": ep.numerical,
        "cheap_relation_calls": ep.cheap_calls, "explicit_tools": ep.tools,
        "program_calls": getattr(getattr(getattr(ep.driver, "harness", None), "program", None), "calls", []),
        "service_origin": "LAST_CANDIDATE" if ep.actions else "INITIAL_ONLY" if initial else "NO_TASK_FORMATION",
        "last_public_check": ep.last_full["public_check"] if ep.last_full else None,
        "selected_descendant": bool(formation and formation.get("selected_candidate"))}
    save(ep.root / "episode-result.json", value)
    print(json.dumps({"event": "LEARNING_EPISODE_COMPLETE", "episode": ident, "status": value["status"],
        "error": error, "actions": len(ep.actions), "service": value["last_public_check"],
        "requests": account["requests"], "selected_descendant": value["selected_descendant"]}), flush=True)
    return value


def run():
    protocol = read(PROTOCOL)
    configure(protocol)
    validate(protocol)
    if (HERE / "run-started.json").exists():
        raise ValueError("PACKAGE_ALREADY_STARTED_NO_REPLACEMENTS")
    save(HERE / "run-started.json", {"at": now(), "package": PACKAGE})
    cache, formed, rows = {}, {}, []
    # Initial qualifications are reused exactly; no task content enters formation driver.
    for entry in protocol["tasks"]:
        if entry.get("status") == "READY":
            public = checked(entry["initial_public_result"])
            task = host.load_task(entry)
            cache[p.execution_cache_key(task, public["design"], task["integration"]["dt_s"], protocol["apparatus_source"])] = Path(entry["initial_public_result"]["path"]).parent
    with runtime_scope():
        for ident, role, condition in PLAN:
            validate(protocol)
            row = one_episode(ident, role, condition, protocol, cache, formed)
            rows.append(row)
            save(HERE / "batch-result.json", {"package": PACKAGE, "at": now(), "rows": rows, "complete": False})
            if role == "formation" and ident == "form-h4":
                save(HERE / "formed-program-freeze.json", {"at": now(), "conditions": {
                    c: {"qualified_descendant": bool(v.get("selected_candidate")), "program": bind(HERE / "episodes" / ("form-" + c.lower()) / "selected-program.json")}
                    for c, v in formed.items()}, "no_task_feedback_seen": True})
            with p.dbconnect() as db:
                missing = [r for r in db.execute("SELECT id FROM model_requests WHERE status='UNKNOWN' OR (status='SETTLED' AND usage IS NULL)") if r[0] != "llm-1de4d60d9bc93d257392"]
                if missing:
                    raise ValueError("NEW_USAGE_UNKNOWN_STOP_ALL_DEPENDENT_DISPATCH")
    save(HERE / "batch-result.json", {"package": PACKAGE, "at": now(), "rows": rows,
        "complete": True, "provider_after": host.provider_snapshot(), "postflight": capacity()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["run", "_execute"])
    parser.add_argument("input", nargs="?")
    args = parser.parse_args()
    if args.phase == "_execute":
        configure(read(PROTOCOL))
        host.child(args.input)
    else:
        run()
