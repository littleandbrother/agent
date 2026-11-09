"""Finite F1-FIRST integration of the existing accounted Pi/DOOR apparatus.

Target objects remain host-side. Formation receives only the frozen parent and
reviewed public experience. Phase claims are never replaced or retried.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import time

from . import pilot as p
from .executor import identity
from .public_projection import project_result, scientific_source_identity

PACKAGE = "BF-PQE-S3-F1FIRST-20261023-001"
APP = p.APP
SHARED = APP / "studies/pqe20261022/f1first/shared"
PRIVATE = APP / "studies/pqe20261022/f1first/private"
OUT = p.BASE / "stage3-f1first"
V1_PROTOCOL = SHARED / "f1first-protocol.json"
V2_PROTOCOL = SHARED / "f1first-protocol-v2.json"
PROTOCOL = SHARED / "f1first-protocol-v3.json"
AMENDMENT = p.BASE / "F1FIRST_冻结任务执行桥修复与配对续行_修订001.md"
PREDISPATCH_AMENDMENT = p.BASE / "F1FIRST_调用签名兼容与零派发恢复_修订002.md"
SRC = Path(__file__).parent
LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=6, candidates=6,
              wall_s=900, output_tokens=32768, generated_tokens=131072,
              usd=4, bytes=12000000)
PLAN = [("form-h2", "formation", "H2"), ("form-h4", "formation", "H4")]
PLAN += [("select-" + c.lower(), "selection", c) for c in ("H1", "H2", "H4")]
PLAN += [("t1-" + c.lower(), "t1", c) for c in ("H0", "H1", "H2", "H3", "H4")]
PLAN += [("t2-" + c.lower(), "t2", c) for c in ("H2", "H3", "H4", "H0", "H1")]
V1_PLAN = list(PLAN)
PLAN = V1_PLAN[:2] + [(i, "selection-v1-tool-error", c) for i, _, c in V1_PLAN[2:5]]
PLAN += [("select-v2-" + c.lower(), "selection-v2-local-predispatch", c) for c in ("H1", "H2", "H4")]
PLAN += [("select-v2-paid-" + c.lower(), "selection", c) for c in ("H1", "H2", "H4")]
PLAN += V1_PLAN[5:]
ADOPTION = {
    "frozen_before_formation": True,
    "local": "Common load/permissions and at most four answer-free behavior inputs; Allocate chooses at most one candidate before selection feedback.",
    "scope": "Any unsupported global exclusion or erroneous adoption in the child rejects it; parent complete PASS must not regress.",
    "service": "Adopt a locally screened child only if selection completes full service and independent scope review passes. A child PASS when parent not PASS is a conditional adoption.",
    "tie": "When both PASS and scope is sound, adopt only if formation plus selection model cost is strictly less than H1 selection cost; otherwise retain parent. Both not PASS or insufficient evidence retains parent.",
    "cost": "Record all formation/rejected proposals/fixtures/selection/confirmation costs; never claim amortization from this single selection.",
    "no_reformation": True,
    "no_confirmation_feedback_to_adoption": True,
}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding(path):
    return {"path": str(path), "sha256": sha(path)}


def now():
    return datetime.now(timezone.utc).isoformat()


def shared_program(name):
    value = read(SHARED / name)
    return value.get("program", value)


def common_history():
    document = read(SHARED / "common-history.json")
    if isinstance(document, list):
        return document
    incidents = deepcopy(document["incidents"])
    for incident in incidents:
        cost = document.get("source_episode_costs", {}).get(incident.get("source_episode_cost_ref"), {})
        incident["source_episode_cost"] = {key: cost[key] for key in ("scope", "requests", "estimated_usd") if key in cost}
    return incidents


def configure(protocol):
    p.OUT, p.PACKAGE, p.LIMITS = OUT, PACKAGE, dict(LIMITS)
    p.CELLS = list(PLAN)
    p.CONTRACT_CORRECTIONS = 2
    p.TOTAL_CAPS = {"requests": 216, "tool_calls": 432, "numerical_inputs": 82,
                    "usd": 72, "retained_bytes": 150000000}
    external_retained = sum(x.stat().st_size for x in SHARED.parent.rglob("*") if x.is_file())
    p.TOTAL_CAPS["retained_bytes"] -= external_retained
    entry = protocol["entry_check"]
    if sha(entry["path"]) != entry["sha256"] or read(entry["path"])["status"] != "PASS_WITH_PRESERVED_INITIAL_FAILURE":
        raise ValueError("F1_DIRECT_ENTRY_CHECK_NOT_RELEASED")
    for path, expected in protocol["source_bindings"].items():
        if sha(path) != expected:
            raise ValueError("FROZEN_F1_SOURCE_CHANGED:" + path)
    for name, ref in protocol["shared_bindings"].items():
        if sha(ref["path"]) != ref["sha256"]:
            raise ValueError("FROZEN_F1_SHARED_CHANGED:" + name)
    for key in ("original_protocol", "amendment", "bridge_validation", "bridge_software_check",
                "previous_execution_protocol", "predispatch_amendment", "predispatch_check"):
        ref = protocol[key]
        if sha(ref["path"]) != ref["sha256"]:
            raise ValueError("F1_V2_BINDING_CHANGED:" + key)
    for ref in protocol["original_attempt_bindings"]:
        if sha(ref["path"]) != ref["sha256"]:
            raise ValueError("F1_ORIGINAL_ATTEMPT_CHANGED")
    for ident in ("select-v2-h1", "select-v2-h2", "select-v2-h4"):
        root = OUT / "s0/episodes" / ident
        row, trace = read(root / "episode-result.json"), read(root / "method-transcript.json")
        if (row["accounting"]["requests"] != 0 or row["actions"]
                or trace["callback_records"][0].get("error", {}).get("message") != "F1Episode.ready() got an unexpected keyword argument 'paid'"):
            raise ValueError("PRESERVED_LOCAL_ZERO_DISPATCH_PROOF_CHANGED")
        if p.ledger(p.DATABASE, row["owner"])["requests"]:
            raise ValueError("LOCAL_ABORT_OWNER_HAS_PROVIDER_DISPATCH")
    if protocol["package"] != PACKAGE or protocol["plan"] != [list(c) for c in PLAN]:
        raise ValueError("F1_FINITE_PLAN_CHANGED")
    if protocol["adoption"] != ADOPTION or protocol["limits_per_episode"] != LIMITS:
        raise ValueError("F1_ADOPTION_OR_LIMITS_CHANGED")


def registry(protocol):
    ref = protocol["private_registry"]
    if sha(ref["path"]) != ref["sha256"]:
        raise ValueError("FROZEN_PRIVATE_REGISTRY_CHANGED")
    return read(ref["path"])


def role_inputs(protocol, role):
    row = registry(protocol)["roles"][role]
    task_path = Path(row["task_path"])
    if sha(task_path) != row["task_file_sha256"]:
        raise ValueError("FROZEN_TARGET_TASK_CHANGED")
    task = read(task_path)
    if row.get("task_json_key"):
        task = task[row["task_json_key"]]
    if identity(task) != row["task_sha256"]:
        raise ValueError("FROZEN_TARGET_TASK_ID_CHANGED")
    initial_path = Path(row["initial_public_result_path"])
    if sha(initial_path) != row["initial_public_result_sha256"]:
        raise ValueError("FROZEN_TARGET_INITIAL_CHANGED")
    initial = project_result(read(initial_path))
    if (initial["task_sha256"] != identity(task)
            or scientific_source_identity(initial["sources"]) != protocol["scientific_source"]):
        raise ValueError("TARGET_INITIAL_SCIENTIFIC_BINDING")
    if (initial["design"] != task["initial_design"]
            or initial["problem"] != task["initial_problem"]):
        raise ValueError("TARGET_INITIAL_STATE_BINDING")
    return task, initial, row


class F1Episode(p.Episode):
    """Same transport, ledger and consumer, with a frozen host-supplied Task."""

    def __init__(self, ident, task, condition, protocol, cache, *, task_role=None, host_only=False):
        self.ident, self.condition, self.protocol, self.cache = ident, condition, protocol, cache
        self.task = deepcopy(task)
        self.design, self.problem = deepcopy(task["initial_design"]), deepcopy(task["initial_problem"])
        self.host_only, self.task_role = host_only, task_role
        self.task_resolver = self.resolve_frozen_task
        self.root = OUT / "s0/task-bridge-validation" if host_only else OUT / "s0/episodes" / ident
        self.root.mkdir(parents=True, exist_ok=False)
        self.started = time.monotonic()
        self.owner, self.token = ("HOST_ONLY_BRIDGE_NO_MODEL_GRANT", None) if host_only else p.register_owner(ident)
        self.model_calls = self.tools = self.numerical = 0
        self.candidates, self.last_full, self.actions = set(), None, []
        self.fatal = self.server = self.thread = None
        self.callback_cap, self.call_relays = 1, 0
        self.access_token = secrets.token_urlsafe(32)
        p.save(self.root / "owner.json", {"owner": self.owner, "episode": ident,
               "finite_usd": 0 if host_only else 4, "grant_wall_s": 0 if host_only else 900,
               "unbounded_authorization": False, "host_only": host_only})

    def resolve_frozen_task(self, task_id):
        if self.task_role not in ("selection", "t1", "t2"):
            raise ValueError("F1_ROLE_HAS_NO_SCIENTIFIC_TASK")
        task, _, _ = role_inputs(self.protocol, self.task_role)
        if task_id != task["task_id"]:
            raise ValueError("F1_TASK_NOT_REGISTERED_FOR_CURRENT_ROLE")
        return task

    def ready(self, paid=False):
        if not self.host_only:
            return super().ready(paid=paid)
        if paid:
            raise ValueError("HOST_ONLY_BRIDGE_PAID_DENIED")
        if self.model_calls or self.tools >= 1 or self.numerical >= 1:
            raise ValueError("HOST_ONLY_BRIDGE_ONCE_CAP")
        if os.statvfs(OUT).f_bavail * os.statvfs(OUT).f_frsize < 11000000000:
            raise ValueError("F1_STORAGE_RESERVE")
        return {"model_requests": 0, "tool_calls": self.tools, "numerical_inputs": self.numerical,
                "spent_usd": 0, "wall_s": time.monotonic()-self.started, "output_tokens": 0}

    def planner(self, *args, **kwargs):
        if self.host_only:
            raise ValueError("HOST_ONLY_BRIDGE_HAS_NO_MODEL_CAPABILITY")
        return super().planner(*args, **kwargs)


def account_result(ep, condition, role, error, details):
    account = p.ledger(p.DATABASE, ep.owner)
    p.save(ep.root / "provider-costs.json", account)
    driver_stop = (details.get("termination") or {}).get("reason")
    stopped = bool(error or ep.fatal or driver_stop in {"TOOL_ERROR", "MISSING_USAGE", "MODEL_IDENTITY_MISMATCH"})
    result = {"package": PACKAGE, "episode": ep.ident, "condition": condition,
              "role": role, "owner": ep.owner, "status": "STOPPED_WITH_ERROR" if stopped else "COMPLETED_FINITE_ATTEMPT",
              "error": error, "fatal": ep.fatal, "wall_s": time.monotonic() - ep.started,
              "accounting": {k: v for k, v in account.items() if k != "rows"},
              "actual_tools": ep.tools,
              "reserved_or_attempted_numerical_inputs": ep.numerical,
              "actual_new_numerical_inputs": sum(a.get("usage", {}).get("numerical_inputs", 0) for a in ep.actions),
              "actions": ep.actions, "last_design": ep.design, "last_problem": ep.problem,
              "last_public_service_origin": "LAST_CONSUMER_RESULT" if ep.actions else "INITIAL_ONLY",
              "last_public_service": ep.last_full["public_check"] if ep.last_full else None,
              "native_calls": 0, "hardware_runs": 0, **details}
    p.save(ep.root / "episode-result.json", result)
    print(json.dumps({"event": "F1_EPISODE_COMPLETE", "episode": ep.ident,
          "status": result["status"], "error": error, "fatal": ep.fatal,
          "candidate_service": result.get("candidate_service"), "service_origin": result["last_public_service_origin"],
          "accounting": result["accounting"]}, ensure_ascii=False), flush=True)
    return result


def run_formation(condition, protocol):
    from .f1first_methods import FormationDriver
    parent = shared_program("parent-h0.json")
    history = common_history()
    ident = "form-" + condition.lower()
    stub = {"task_id": "NO_TARGET_METHOD_FORMATION", "initial_design": {}, "initial_problem": {}}
    ep = F1Episode(ident, stub, condition, protocol, {})
    error, receipt = None, None
    try:
        ep.start_server()
        driver = FormationDriver(condition, ep.planner, parent=parent, history=history,
            episode_id=ident, model_identity=p.MODEL_IDENTITY, request_reserve_usd=.19,
            limits={"output_tokens_per_request": 32768, "output_tokens_total": 131072})
        receipt = driver.run()
        p.save(ep.root / "formation.json", receipt)
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
    finally:
        ep.close()
    return account_result(ep, condition, "formation", error, {"formation_path": str(ep.root / "formation.json") if receipt else None})


def formation_program(condition):
    path = OUT / "s0/episodes" / ("form-" + condition.lower()) / "formation.json"
    if not path.exists():
        return shared_program("parent-h0.json"), {"parent_retained": True, "reason": "FORMATION_FAILED_NO_RECEIPT"}
    f = read(path)
    return f.get("selected_program") or shared_program("parent-h0.json"), f


def cache_from_initials(protocol):
    cache = {}
    for role in ("selection", "t1", "t2"):
        task, initial, row = role_inputs(protocol, role)
        key = p.execution_cache_key(task, initial["design"], row["dt_s"], initial["sources"])
        cache[key] = Path(row["initial_public_result_path"]).parent
    bridge = read(protocol["bridge_validation"]["path"])
    task, _, row = role_inputs(protocol, "selection")
    public_path = Path(bridge["public_result"]["path"])
    if sha(public_path) != bridge["public_result"]["sha256"]:
        raise ValueError("F1_BRIDGE_CACHE_CHANGED")
    value = read(public_path)
    cache[p.execution_cache_key(task, value["design"], row["dt_s"], value["sources"])] = public_path.parent
    for path in sorted((OUT / "s0/episodes").glob("*/actions/*/public-result.json")):
        value = read(path)
        if value.get("execution_status") == "NO_EXECUTION" or (path.parent / "reused.json").exists():
            continue
        role = next((role for role in ("selection", "t1", "t2") if role_inputs(protocol, role)[0]["task_id"] == value.get("task_id")), None)
        if role is None:
            raise ValueError("NON_PROTOCOL_CACHE_RESULT")
        task, _, row = role_inputs(protocol, role)
        raw = read(path.parent / "raw.json")
        key = p.execution_cache_key(task, value["design"], raw["dt_s"], value["sources"])
        cache[key] = path.parent
    return cache


def condition_program(condition, role):
    if condition in ("H0", "H1"):
        return shared_program("parent-h0.json"), "FIXED_PARENT"
    if condition == "H3":
        return shared_program("h3-fixed-rules.json"), "DEVELOPER_FIXED_RULES"
    if role == "selection":
        program, formed = formation_program(condition)
        return program, "SELECTED_CHILD" if program["parent_program"] else "RETAINED_PARENT"
    adoption = read(OUT / "s0/adoption-v2-paid.json")
    row = adoption["conditions"][condition]
    program = read(row["program_path"])
    if sha(row["program_path"]) != row["program_sha256"]:
        raise ValueError("ADOPTED_PROGRAM_CHANGED")
    if row.get("program_selector"):
        program = program[row["program_selector"]]
    return program, row["status"]


def run_solve(ident, role, condition, protocol, cache):
    from .episode_methods import EpisodeDriver
    task, initial, _ = role_inputs(protocol, role)
    program, program_status = condition_program(condition, role)
    history = common_history()
    ep = F1Episode(ident, task, condition, protocol, cache, task_role=role)
    error, driver = None, None
    try:
        ep.start_server()
        state = p.episode_initial_state(task, ep.design, ep.problem, initial)
        ep.last_full = initial
        driver = EpisodeDriver("strong_generic", ep.planner, episode_id=ident, initial_state=state,
            model_identity=p.MODEL_IDENTITY, request_reserve_usd=.19,
            limits={"output_tokens_per_request": 32768, "output_tokens_total": 131072,
                    "new_numerical_inputs": 6}, max_contract_corrections=2,
            program=program, common_history=[] if condition == "H0" else history,
            expected_methods_sha256=protocol["source_bindings"][str(SRC / "methods.py")],
            isolated_program=True)
        while True:
            b = ep.ready()
            action = driver.next({"provider_requests_remaining": 12 - b["model_requests"],
                "tool_calls_remaining": 24 - b["tool_calls"], "new_numerical_inputs_remaining": 6 - b["numerical_inputs"],
                "reserve_usd_remaining": 4 - b["spent_usd"], "wall_s_remaining": 900 - b["wall_s"],
                "output_tokens_remaining": 131072 - b["output_tokens"]})
            p.save(ep.root / "method-transcript.json", driver.transcript())
            if action["status"] != "ACTION":
                break
            try:
                result = ep.consume(action["decision"])
            except (ValueError, KeyError, TypeError) as exc:
                result = {"schema_version": "pqe-public-result-v1", "execution_status": "TOOL_ERROR",
                    "task_id": task["task_id"], "design": ep.design, "problem": ep.problem,
                    "model_valid": None, "facts": {"tool_error": str(exc)},
                    "public_check": {"verdict": "UNKNOWN", "failures": [], "unknown": ["TOOL_ERROR"]},
                    "usage": {"numerical_inputs": 0, "paid_model_requests": 0}}
                p.save(ep.root / "tool-errors" / (f"{ep.tools:02d}.json"), {"decision": action["decision"], "result": result})
            driver.update(result)
            p.save(ep.root / "method-transcript.json", driver.transcript())
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
        if driver:
            driver.finish(error)
    finally:
        ep.close()
    transcript = driver.transcript() if driver else None
    if transcript:
        p.save(ep.root / "method-transcript.json", transcript)
    return account_result(ep, condition, role, error, {"task_id": task["task_id"],
        "program": program["program_id"], "program_sha256": identity(program),
        "program_status": program_status, "common_history_available": condition != "H0",
        "termination": transcript.get("termination") if transcript else None,
        "candidate_service": candidate_service({"last_public_service": ep.last_full["public_check"] if ep.last_full else None,
            "actions": ep.actions, "termination": transcript.get("termination") if transcript else None}),
        "model_conclusion": transcript.get("model_conclusion") if transcript else None})


def dependency_stop(row):
    return bool(row.get("error") or row.get("fatal") or row.get("dependency_stop") or row.get("accounting", {}).get("unknown_or_missing_usage")
                or (row.get("termination") or {}).get("reason") in {"TOOL_ERROR", "MISSING_USAGE", "MODEL_IDENTITY_MISMATCH"})


def run_cells(selected, protocol, cache):
    results = []
    for ident, role, condition in selected:
        result = run_formation(condition, protocol) if role == "formation" else run_solve(ident, role, condition, protocol, cache)
        results.append(result)
        if dependency_stop(result):
            break
        if role == "selection" and len(results) == 1:
            entered = bool(result["accounting"]["requests"] and any(
                a.get("usage", {}).get("numerical_inputs") or a.get("usage", {}).get("reused")
                for a in result.get("actions", [])))
            if not entered:
                result["dependency_stop"] = "FIRST_SELECTION_HAS_NOT_REACHED_ACCOUNTED_CONSUMER"
                break
    return results


def run_phase(phase):
    protocol = read(PROTOCOL)
    configure(protocol)
    if phase not in ("formation", "selection", "confirmation"):
        raise ValueError("F1_UNKNOWN_PHASE")
    if phase == "formation":
        raise ValueError("F1_V2_FORMATION_REDISPATCH_FORBIDDEN")
    for ident, role, _ in PLAN:
        required = phase == "selection" and role == "formation" or phase == "confirmation" and role in ("formation", "selection")
        if required:
            result = read(OUT / "s0/episodes" / ident / "episode-result.json")
            if dependency_stop(result):
                raise ValueError("DEPENDENT_F1_DISPATCH_STOP")
    if phase == "confirmation" and not (OUT / "s0/adoption-v2-paid.json").exists():
        raise ValueError("F1_EXTERNAL_ADOPTION_REQUIRED")
    selected = [c for c in PLAN if (c[1] == phase or phase == "confirmation" and c[1] in ("t1", "t2"))]
    claim = OUT / "s0" / (phase + "-v2-paid-claim.json")
    with claim.open("x") as f:
        json.dump({"at": now(), "phase": phase, "pid": os.getpid(), "protocol_sha256": sha(PROTOCOL), "plan": selected}, f)
    lock = OUT / "s0/active.lock"
    installed, prior, results = False, None, []
    with lock.open("x") as f:
        f.write(str(os.getpid()))
    try:
        free = os.statvfs(OUT).f_bavail * os.statvfs(OUT).f_frsize
        if free < 11000000000:
            raise ValueError("F1_STORAGE_RESERVE")
        with p.dbconnect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
                raise ValueError("OTHER_PROVIDER_REQUEST_ACTIVE")
            row = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            prior = row["value"] if row else None
            db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
            installed = True
            db.execute("UPDATE research_model_studies SET max_usd=?,expires=? WHERE protocol=?", (72, time.time()+len(selected)*900+300, PACKAGE))
        p.save(OUT / "s0" / (phase + "-v2-paid-runtime-before.json"), {"at": now(), "budget_scope_before": prior, "available_bytes": free})
        cache = {} if phase == "formation" else cache_from_initials(protocol)
        results = run_cells(selected, protocol, cache)
    finally:
        if installed:
            with p.dbconnect() as db:
                row = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
                if not row or row["value"] != json.dumps("per-owner"):
                    raise ValueError("F1_CONCURRENT_BUDGET_SCOPE_CHANGE")
                if prior is None:
                    db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
                else:
                    db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'", (prior,))
        if phase == "confirmation":
            with p.dbconnect() as db:
                db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))
        lock.unlink()
        p.save(OUT / "s0" / (phase + "-v2-paid-result.json"), {"package": PACKAGE, "phase": phase,
            "completed_at": now(), "results": results, "budget_scope_restored": installed,
            "unexecuted": [c[0] for c in selected if c[0] not in {x["episode"] for x in results}]})
    return results


def adopt(scope_review_path):
    """Apply the preformation rule to three finished selection attempts only."""
    protocol = read(PROTOCOL)
    configure(protocol)
    destination = OUT / "s0/adoption-v2-paid.json"
    if destination.exists():
        raise ValueError("F1_ADOPTION_ALREADY_FROZEN")
    if any((OUT / "s0/episodes" / ident).exists() for ident, role, _ in PLAN if role in ("t1", "t2")):
        raise ValueError("F1_CONFIRMATION_ALREADY_EXPOSED")
    scope = read(scope_review_path)
    rows = {c: read(OUT / "s0/episodes" / ("select-v2-paid-" + c.lower()) / "episode-result.json") for c in ("H1", "H2", "H4")}
    for c, row in rows.items():
        if dependency_stop(row):
            raise ValueError("F1_ADOPTION_DEPENDENT_USAGE_STOP")
        ref = scope["conditions"][c]["episode_result"]
        if ref["sha256"] != sha(ref["path"]):
            raise ValueError("F1_SELECTION_SCOPE_SOURCE_CHANGED")
    def passed(row):
        return candidate_service(row).get("verdict") == "PASS"
    def cost(row):
        return row["accounting"]["settled_charge_upper_bound_usd"] + row["accounting"]["unsettled_reserved_usd"]
    parent, conditions = rows["H1"], {}
    prior_costs = {c: cost(read(OUT / "s0/episodes" / ("select-"+c.lower()) / "episode-result.json")) for c in rows}
    parent_total = cost(parent) + prior_costs["H1"]
    for c in ("H2", "H4"):
        program, formation = formation_program(c)
        child = bool(program.get("parent_program")) and not formation.get("parent_retained", False)
        evidence = scope["conditions"][c]
        formation_cost = cost(read(OUT / "s0/episodes" / ("form-" + c.lower()) / "episode-result.json"))
        all_cost = formation_cost + cost(rows[c]) + prior_costs[c]
        scope_sound = evidence["unsupported_global_exclusions"] == 0 and evidence["erroneous_adoptions"] == 0
        adopt_child = False
        if not child:
            reason = "NO_VALID_ALLOCATED_CHILD_RETAIN_PARENT"
        elif not scope_sound:
            reason = "INDEPENDENT_SCOPE_OR_ADOPTION_ERROR_RETAIN_PARENT"
        elif not passed(rows[c]):
            reason = "NO_FULL_SELECTION_SERVICE_RETAIN_PARENT"
        elif not passed(parent):
            reason, adopt_child = "CONDITIONAL_FULL_SERVICE_GAIN_ON_ONE_SELECTION", True
        elif all_cost < parent_total - 1e-12:
            reason, adopt_child = "SAME_FULL_SERVICE_LOWER_FORMATION_PLUS_SELECTION_COST", True
        else:
            reason = "NO_COST_ADVANTAGE_INCLUDING_FORMATION_RETAIN_PARENT"
        path = OUT / "s0/episodes" / ("form-" + c.lower()) / "formation.json" if adopt_child else SHARED / "parent-h0.json"
        conditions[c] = {"status": "CONDITIONALLY_ADOPTED_CHILD" if adopt_child else "RETAINED_PARENT",
            "reason": reason, "program_path": str(path), "program_sha256": sha(path),
            "program_selector": "selected_program" if adopt_child else "program",
            "formation_usd": formation_cost, "selection_usd": cost(rows[c]),
            "prior_tool_aborted_selection_usd": prior_costs[c],
            "formation_plus_all_selection_usd": all_cost, "parent_H1_all_selection_usd": parent_total,
            "selection_full_service": passed(rows[c]), "parent_full_service": passed(parent),
            "scope_review": evidence, "one_selection_is_not_stable_transfer_or_amortization": True}
    result = {"package": PACKAGE, "at": now(), "rule": ADOPTION,
        "execution_protocol": binding(PROTOCOL), "supersedes_tool_only_adoption": binding(OUT / "s0/adoption.json"),
        "scope_review": binding(Path(scope_review_path)), "conditions": conditions,
        "confirmation_not_seen": True, "no_method_reformation_or_developer_patch": True}
    p.save(destination, result)
    return result


def candidate_service(row):
    """An inherited initial verdict cannot turn a tool abort into science."""
    termination = row.get("termination") or {}
    if termination.get("reason") in {"TOOL_ERROR", "MISSING_USAGE", "MODEL_IDENTITY_MISMATCH"}:
        return {"verdict": "UNKNOWN", "unknown": [termination["reason"]], "failures": []}
    return row.get("last_public_service") or {"verdict": "UNKNOWN", "unknown": ["NO_ASSESSMENT"]}


def summarize():
    protocol = read(PROTOCOL)
    configure(protocol)
    rows = []
    for ident, role, condition in PLAN:
        path = OUT / "s0/episodes" / ident / "episode-result.json"
        row = read(path) if path.exists() else {"episode": ident, "role": role,
            "condition": condition, "status": "NOT_RUN_DEPENDENT_STOP"}
        if role == "selection-v1-tool-error":
            row = deepcopy(row)
            row["raw_host_numerical_counter"] = row.get("actual_new_numerical_inputs")
            row["completed_new_numerical_inputs"] = 0
            row["service_result_origin"] = "INITIAL_ONLY"
            row["candidate_service"] = {"verdict": "UNKNOWN", "unknown": ["TOOL_ERROR_BEFORE_EXECUTION"]}
            row["interpretation"] = "V1_TOOL_ABORTED_NO_CANDIDATE_SCIENCE_ORIGINAL_FILE_UNCHANGED"
        elif role == "selection-v2-local-predispatch":
            row = deepcopy(row)
            row["service_result_origin"] = "INITIAL_ONLY"
            row["candidate_service"] = {"verdict": "UNKNOWN", "unknown": ["LOCAL_PRE_DISPATCH_ERROR"]}
            row["interpretation"] = "ORIGINAL_DRIVER_UNKNOWN_RETAINED_ZERO_BROKER_REQUESTS_PROVEN"
        rows.append(row)
    records = [r for r in rows if "accounting" in r]
    unknown = []
    for row in records:
        identities = row["accounting"]["unknown_or_missing_usage"]
        if not isinstance(identities, list):
            raise ValueError("USAGE_IDENTITY_LIST_CONTRACT")
        unknown.extend(identities)
    totals = {"host_startups": len(records), "planned_max_host_startups": 21,
        "model_capable_episodes": sum(r["episode"] not in {"select-v2-h1", "select-v2-h2", "select-v2-h4"} for r in records),
        "max_model_capable_episodes": 18, "local_zero_dispatch_attempts": 3,
        "retained_local_driver_unknown_usage_rows": 3,
        "local_driver_symbolic_reserves_usd": .57,
        "local_driver_reserves_are_not_provider_debt": True,
        "requests": sum(r["accounting"].get("requests", 0) for r in records),
        "episode_new_coupled_inputs": sum(a.get("usage", {}).get("numerical_inputs", 0) for r in records for a in r.get("actions", [])),
        "reserved_or_attempted_episode_inputs": sum(r.get("reserved_or_attempted_numerical_inputs", r.get("actual_new_numerical_inputs", 0)) for r in records),
        "exact_result_reuses": sum(bool(a.get("usage", {}).get("reused")) for r in records for a in r.get("actions", [])),
        "private_initial_inputs": 3, "bridge_validation_inputs": 1,
        "estimated_usd": sum(r["accounting"].get("settled_charge_upper_bound_usd", 0) for r in records),
        "unsettled_reserved_usd": sum(r["accounting"].get("unsettled_reserved_usd", 0) for r in records),
        "unknown_or_missing_usage": unknown, "unknown_or_missing_usage_count": len(unknown),
        "native_calls": 0, "hardware_runs": 0, "G_self_modification": 0}
    totals["all_new_coupled_inputs"] = 4 + totals["episode_new_coupled_inputs"]
    assert totals["host_startups"] <= 21 and totals["model_capable_episodes"] <= 18 and totals["requests"] <= 216
    assert totals["all_new_coupled_inputs"] <= 82 and totals["estimated_usd"] + totals["unsettled_reserved_usd"] <= 72
    result = {"package": PACKAGE, "at": now(), "episodes": rows, "totals": totals,
        "protocol_sha256": sha(PROTOCOL), "adoption": read(OUT / "s0/adoption-v2-paid.json") if (OUT / "s0/adoption-v2-paid.json").exists() else None,
        "claim_boundary": protocol["claim_boundary"]}
    p.save(OUT / "s0/batch-result-v2-paid.json", result)
    return result


def freeze(private_registry_path):
    if PROTOCOL.exists():
        raise ValueError("F1_PROTOCOL_ALREADY_FROZEN")
    entry = OUT / "s0/ENTRY-CHECK-SUMMARY.json"
    if read(entry)["status"] != "PASS_WITH_PRESERVED_INITIAL_FAILURE":
        raise ValueError("F1_DIRECT_ENTRY_CHECK_NOT_RELEASED")
    shared = {name: binding(SHARED / name) for name in (
        "parent-h0.json", "common-history.json", "history-review.json", "h3-fixed-rules.json",
        "role-freeze-public.json", "exposure-amendment.json")}
    original = read(V1_PROTOCOL)
    if str(Path(private_registry_path).resolve()) != str(Path(original["private_registry"]["path"]).resolve()):
        raise ValueError("V2_PRIVATE_REGISTRY_REPLACEMENT")
    scientific = original["scientific_source"]
    source_paths = [SRC / f for f in ("f1first.py", "pilot.py", "methods.py", "episode_methods.py",
        "f1first_methods.py", "restricted_worker.py", "public_projection.py", "adapter.py",
        "door_model.py", "door_program.py", "engineering.py", "executor.py", "evaluator.py")]
    source_paths += [APP / "scripts/pqe_pi_callback.mjs", APP / "scripts/pqe_f1first.py",
                     APP / "tests/test_pqe_f1first.py", APP / "tests/test_pqe_f1first_task_bridge.py", p.SDK]
    allowed = {str(SRC / n) for n in ("f1first.py", "pilot.py", "adapter.py")} | {str(APP / "scripts/pqe_f1first.py")}
    changed = {path: {"before": expected, "after": sha(path)} for path, expected in original["source_bindings"].items() if sha(path) != expected}
    if set(changed) - allowed:
        raise ValueError("V2_SOURCE_CHANGE_OUTSIDE_AMENDMENT")
    prior_execution = read(V2_PROTOCOL)
    entry_changes = {path: {"before": expected, "after": sha(path)}
        for path, expected in prior_execution["source_bindings"].items() if sha(path) != expected}
    if set(entry_changes) - {str(SRC / "f1first.py"), str(APP / "tests/test_pqe_f1first_task_bridge.py")}:
        raise ValueError("PREDISPATCH_FIX_OUTSIDE_NARROW_SCOPE")
    bridge = OUT / "s0/task-bridge-validation/receipt.json"
    software = OUT / "s0/task-bridge-check.json"
    if read(bridge)["status"] != "PASS" or read(software)["status"] != "PASS":
        raise ValueError("V2_DIRECT_BRIDGE_NOT_RELEASED")
    protocol = {"package": PACKAGE, "frozen_at": now(), "plan": [list(c) for c in PLAN],
        "limits_per_episode": LIMITS, "total_caps": {"episodes": 18, "host_startups": 21, "local_zero_dispatch": 3, "requests": 216,
            "usd": 72, "new_coupled_inputs": 82, "private_initials": 3, "bridge_validation": 1, "native": 0,
            "retained_bytes": 150000000, "peak_additional_bytes": 1000000000},
        "source_bindings": {str(x): sha(x) for x in source_paths},
        "apparatus_source": scientific, "scientific_source": scientific,
        "shared_bindings": shared, "private_registry": binding(Path(private_registry_path)),
        "entry_check": binding(entry),
        "version": "v3-paid-entry-compatible", "original_protocol": binding(V1_PROTOCOL),
        "previous_execution_protocol": binding(V2_PROTOCOL),
        "predispatch_amendment": binding(PREDISPATCH_AMENDMENT),
        "predispatch_check": binding(OUT / "s0/paid-readiness-check.json"),
        "predispatch_changed_source_bindings": entry_changes,
        "amendment": binding(AMENDMENT), "changed_source_bindings": changed,
        "bridge_validation": binding(bridge), "bridge_software_check": binding(software),
        "original_attempt_bindings": [binding(x) for ident in ("form-h2", "form-h4", "select-h1", "select-h2", "select-h4")
            for x in [OUT / "s0/episodes" / ident / "episode-result.json",
                OUT / "s0/episodes" / ident / ("formation.json" if ident.startswith("form-") else "method-transcript.json")]]
            + [binding(OUT / "s0/adoption.json")]
            + [binding(OUT / "s0/episodes" / ident / name)
               for ident in ("select-v2-h1", "select-v2-h2", "select-v2-h4")
               for name in ("episode-result.json", "method-transcript.json", "provider-costs.json")],
        "adoption": ADOPTION, "contract_correction_limit": 2, "model_identity": p.MODEL_IDENTITY,
        "roles": "selection D06; prospective t1 D01 and t2 D16; target instances excluded from formation",
        "claim_boundary": "First finite F1 mechanism/formation pilot; no formal E2/E3, stable transfer, G self-modification or hardware.",
        "no_retries_reformation_replacement": True,
        "version_exception": "Three new paid-entry selection identities follow three proven local zero-dispatch attempts; all original attempts retained; no formation retry or further repair.",
        "parent_attempts": {"select-v2-paid-"+c: "select-v2-"+c for c in ("h1", "h2", "h4")}}
    if read(protocol["predispatch_check"]["path"])["status"] != "PASS":
        raise ValueError("PAID_ENTRY_DIRECT_CHECK_NOT_RELEASED")
    configure(protocol)
    for role in ("selection", "t1", "t2"):
        role_inputs(protocol, role)
    p.save(PROTOCOL, protocol)
    return protocol


def validate_bridge():
    """One original autonomous action through the actual host consumer, no model."""
    original = read(V1_PROTOCOL)
    p.OUT, p.PACKAGE, p.LIMITS = OUT, PACKAGE, dict(LIMITS)
    for role in ("selection", "t1", "t2"):
        role_inputs(original, role)
    task, _, _ = role_inputs(original, "selection")
    source = OUT / "s0/episodes/select-h1/tool-errors/01.json"
    decision = read(source)["decision"]
    ep = F1Episode("bridge-validation", task, "HOST_ONLY", original, {}, task_role="selection", host_only=True)
    result = ep.consume(decision)
    action = ep.root / "actions/01"
    public = read(action / "public-result.json")
    if (public["usage"]["numerical_inputs"] != 1 or not (action / "raw.json").exists()
            or scientific_source_identity(public["sources"]) != original["scientific_source"]
            or public["task_sha256"] != identity(task)):
        raise ValueError("V2_REAL_BRIDGE_RECEIPT_INVALID")
    receipt = {"status": "PASS", "at": now(), "original_action": binding(source),
        "original_protocol": binding(V1_PROTOCOL), "amendment": binding(AMENDMENT),
        "task_sha256": identity(task), "actual_design": public["design"],
        "public_check": public["public_check"], "public_result": binding(action / "public-result.json"),
        "raw_result": binding(action / "raw.json"), "new_numerical_inputs": 1,
        "provider_requests": 0, "native": 0, "not_feedback_to_v2_models": True}
    p.save(ep.root / "receipt.json", receipt)
    return receipt
