"""One pre-frozen M2 comparison. No retries, task replacement or method tuning.

Only this host invokes the original full consumer or the registered Pi broker.
Full public artifacts remain canonical; transcripts page repeated public lists.
"""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
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

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
BASE = ROOT / "docs/research/pqe-two-paper-plan-20261022"
HERE = Path(__file__).resolve().parent
OUT = HERE.parent
SOURCE = APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import adapter, pilot as p
from bfworld.agentlab.pqe20261022.executor import identity
from bfworld.agentlab.pqe20261022.methods import common_contract_check
from bfworld.agentlab.pqe20261022.episode_methods import planner_instructions
from bfworld.agentlab.pqe20261022.public_projection import (
    is_public_result, project_result, scientific_source_identity)
from bfworld.agentlab.historical_usage import new_batch_usage_blockers

PACKAGE = "BF-PQE-DYNAMIC-DECISION-M2-20261023-001"
PROTOCOL = OUT / "shared/protocol.json"
DB = p.DATABASE
R11 = "llm-1de4d60d9bc93d257392"
LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=3,
              candidates=3, wall_s=900, output_tokens=32768,
              generated_tokens=65536, usd=5, bytes=25000000)
TOTAL = dict(requests=24, tool_calls=48, numerical_inputs=20,
             usd=10, retained_bytes=80000000)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def bind(path):
    path = Path(path)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def checked(ref):
    if bind(ref["path"])["sha256"] != ref["sha256"]:
        raise ValueError("FROZEN_INPUT_CHANGED:" + str(ref["path"]))
    return read(ref["path"])


def load_task(entry):
    catalog = checked(entry["task"])
    task = catalog[entry["task_key"]] if entry.get("task_key") else catalog
    if identity(task) != entry["task_canonical_sha256"]:
        raise ValueError("CANONICAL_TASK_IDENTITY_CHANGED")
    packet = checked(entry["public_input"])
    generated = p.public_task(task)
    frozen = packet["task"]
    public_keys_equal = all(generated.get(key) == value for key, value in frozen.items() if key != "public_inputs")
    public_inputs_equal = all(generated.get("public_inputs", {}).get(key) == value
                              for key, value in frozen.get("public_inputs", {}).items())
    if (not public_keys_equal or not public_inputs_equal or task["initial_design"] != packet["initial_design"]
            or task["initial_problem"] != packet["initial_problem"]):
        raise ValueError("COMMON_PUBLIC_TASK_INPUT_MISMATCH")
    return deepcopy(task)


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def compact_embedded(value):
    """Same public paging for all transcript projections; no hidden assessment."""
    if isinstance(value, dict):
        if is_public_result(value):
            return p.compact_result(value)
        return {key: compact_embedded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [compact_embedded(item) for item in value]
    return value


def record(path, value):
    save(path, compact_embedded(value))


def capacity(reserve=0):
    fs = os.statvfs(ROOT)
    free = fs.f_bavail * fs.f_frsize
    used = sum(path.stat().st_size for path in OUT.rglob("*") if path.is_file())
    if free < 10800000000 or used + reserve >= TOTAL["retained_bytes"]:
        raise ValueError("STORAGE_RESOURCE_GATE")
    return {"at": now(), "available_bytes": free, "retained_logical_bytes": used,
            "peak_additional_bytes": 800000000, "retained_cap_bytes": 80000000}


def provider_snapshot():
    with sqlite3.connect("file:" + str(DB) + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        row = dict(db.execute("SELECT * FROM model_requests WHERE id=?", (R11,)).fetchone())
        return {"total": db.execute("SELECT count(*) FROM model_requests").fetchone()[0],
                "inflight": db.execute("SELECT count(*) FROM model_requests WHERE status='DISPATCHED'").fetchone()[0],
                "historical_unknown_sha256": hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest(),
                "statuses": dict(db.execute("SELECT status,count(*) FROM model_requests GROUP BY status").fetchall())}


def validate(protocol):
    for path, expected in protocol["source_bindings"].items():
        if bind(path)["sha256"] != expected:
            raise ValueError("FROZEN_SOURCE_CHANGED:" + path)
    for task in protocol["tasks"]:
        if task["status"] == "READY":
            load_task(task)
    checked(protocol["task_manifest"])
    checked(protocol["method_receipt"])
    checked(protocol["public_materials"])
    if provider_snapshot()["historical_unknown_sha256"] != protocol["provider_before"]["historical_unknown_sha256"]:
        raise ValueError("R11_HISTORICAL_ROW_CHANGED")


def freeze():
    if PROTOCOL.exists():
        raise ValueError("M2_ALREADY_FROZEN_NO_REPLACEMENT")
    manifest = read(OUT / "shared/tasks.json")
    methods = read(OUT / "shared/methods.json")
    assert len(manifest["tasks"]) == 2
    assert methods["status"] == "FROZEN_READY"
    old = read(BASE / "stage3-update-continue/shared/protocol.json")
    bindings = dict(old["source_bindings"])
    for path in [SOURCE / "dynamic_methods.py", SOURCE / "dynamic_relations.py",
                 SOURCE / "m2_methods.py", Path(__file__), Path(old["sdk_entry"])]:
        bindings[str(path)] = bind(path)["sha256"]
    protocol = {"package": PACKAGE, "frozen_at": now(),
                "task_manifest": bind(OUT / "shared/tasks.json"),
                "method_receipt": bind(OUT / "shared/methods.json"),
                "public_materials": manifest["public_materials"],
                "tasks": manifest["tasks"], "source_bindings": bindings,
                "scientific_source": old["scientific_source"],
                "apparatus_source": adapter.source_identity(),
                "same_backend": old["same_backend"], "model_identity": old["model_identity"],
                "sdk_entry": old["sdk_entry"], "limits_per_G_episode": LIMITS,
                "total_caps": TOTAL, "maximum_evaluations_per_track": 3,
                "maximum_generation_rounds_per_track": 3, "cheap_scores_per_track": 24,
                "maximum_cheap_scores": 144, "full_dynamic_seconds_each": 120,
                "full_dynamic_seconds_total": 1800,
                "order": [{"task": row["id"], "condition": condition,
                           "episode": row["id"] + "-" + condition.lower()}
                          for row in manifest["tasks"] for condition in ["G", "F", "U"]],
                "provider_before": provider_snapshot(), "capacity": capacity(),
                "public_paging": "Existing compact_result on outgoing model and transcript only; canonical full public Result available via public_detail/phase tools equally.",
                "common_controls": "Executed valid PASS stops; errors retain; exact valid failed point not re-executed. Re-GEN after rejection is common, at most3 generation rounds total, repeated unexecuted batch stops.",
                "claim_boundary": "Two developer mechanism tasks, manually fixed M1 and phase-consumption ablation; no automatic H formation, held-out transfer, stable efficacy, RSI or hardware claim."}
    if protocol["provider_before"]["inflight"]:
        raise ValueError("PROVIDER_REQUEST_ALREADY_INFLIGHT")
    validate(protocol)
    save(PROTOCOL, protocol)
    save(HERE / "resource-ledger.json", {"package": PACKAGE, "full_dynamic_inputs": 0,
         "initial_inputs": 0, "full_dynamic_wall_s": 0, "cheap_scores": 0,
         "evaluations_including_reuse": 0, "cache_reuses": 0,
         "tracks": {}, "attempts": [], "algorithm_revisions": 0,
         "native_inputs": 0, "hardware_runs": 0})
    return protocol


def configure(protocol):
    p.OUT, p.PACKAGE, p.LIMITS, p.TOTAL_CAPS = OUT, PACKAGE, dict(LIMITS), dict(TOTAL)
    p.CELLS = [(cell["episode"], cell["task"], "strong_generic")
               for cell in protocol["order"] if cell["condition"] == "G"]
    p.SDK = Path(protocol["sdk_entry"])


@contextmanager
def runtime_scope():
    installed, prior = False, None
    with p.dbconnect() as db:
        if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
            raise ValueError("PROVIDER_REQUEST_ALREADY_INFLIGHT")
        if db.execute("SELECT 1 FROM research_model_owners WHERE protocol=?", (PACKAGE,)).fetchone():
            raise ValueError("M2_OWNERS_EXIST_NO_RETRY")
    try:
        with p.dbconnect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            prior = row["value"] if row else None
            db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
            installed = True
        save(HERE / "runtime-registration.json", {"at": now(), "scope_before": prior,
             "temporary_scope": "per-owner", "study_usd_cap": 10,
             "per_episode_usd_cap": 5, "authorized_episodes": 2})
        yield
    finally:
        if installed:
            with p.dbconnect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
                if not current or current["value"] != json.dumps("per-owner"):
                    raise ValueError("CONCURRENT_BUDGET_SCOPE_CHANGE")
                if prior is None:
                    db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
                else:
                    db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'", (prior,))
                owners = [row[0] for row in db.execute("SELECT owner FROM research_model_owners WHERE protocol=?", (PACKAGE,))]
                for owner in owners:
                    db.execute("UPDATE grants SET expires=? WHERE owner=?", (time.time(), owner))
                    db.execute("DELETE FROM principals WHERE owner=?", (owner,))
                    db.execute("UPDATE conversations SET status='IDLE',updated=? WHERE id=?", (time.time(), owner))
                db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))
            save(HERE / "runtime-closeout.json", {"at": now(), "scope_restored_to": prior,
                 "closed_owners": owners, "provider_after": provider_snapshot(),
                 "history_rows_deleted": 0})


class ModelEpisode(p.Episode):
    """Only new USD5/12-call budget wrapper; original transport stays unchanged."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        save(self.root / "owner.json", {"owner": self.owner, "episode": self.ident,
             "finite_usd": 5, "grant_wall_s": 900, "no_unbounded_authorization": True})

    def ready(self, paid=False):
        if self.fatal:
            raise ValueError(self.fatal)
        budget = self.budget()
        if budget["wall_s"] >= 900:
            raise ValueError("EPISODE_WALL_CAP")
        capacity()
        if sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file()) >= LIMITS["bytes"]:
            raise ValueError("EPISODE_OUTPUT_CAP")
        with p.dbconnect() as db:
            if new_batch_usage_blockers(db, self.owner):
                self.fatal = "NEW_USAGE_UNKNOWN_STOP"
                raise ValueError(self.fatal)
        if self.tools > 24:
            raise ValueError("EPISODE_TOOL_CAP")
        if paid and (budget["model_requests"] >= 12 or budget["output_tokens"] >= 65536
                     or budget["spent_usd"] + .19 > 5):
            raise ValueError("EPISODE_MODEL_CAP")
        return budget


def child(input_file):
    job = read(input_file)
    protocol = read(PROTOCOL)
    validate(protocol)
    task = load_task(job["task_entry"])
    public = adapter.execute(task, job["design"], job["problem"], job["decision"],
             job["output_dir"], task_resolver=lambda ident: deepcopy(task) if ident == task["task_id"] else None)
    validate(protocol)
    print(json.dumps({"public_check": public["public_check"], "model_valid": public["model_valid"]}), flush=True)


def execute(task_entry, state, decision, folder, ledger, cache, protocol, initial=False):
    validate(protocol)
    task = load_task(task_entry)
    actual = common_contract_check(state, decision["actual_input"], {"remaining_actions": 24})
    design = {**state["design"], **actual.get("design_patch", {})}
    problem = {**state["problem"], **actual.get("problem_patch", {})}
    adapter.validate_design(task, design)
    dt = actual.get("dt_s", task["integration"]["dt_s"])
    key = p.execution_cache_key(task, design, dt, protocol["apparatus_source"])
    item = {"at": now(), "task": task_entry["id"], "initial": initial,
            "decision_sha256": identity(decision), "design_sha256": identity(design),
            "cache_key": key, "reused": key in cache, "full_dynamic_inputs": 0}
    if key in cache:
        source_dir = cache[key]
        public = checked(bind(source_dir / "public-result.json"))
        public["problem"] = deepcopy(problem)
        public["usage"] = {"paid_model_requests": 0, "numerical_inputs": 0, "reused": True, "wall_s": 0}
        folder.mkdir(parents=True, exist_ok=False)
        save(folder / "reuse.json", {"source_public_result": bind(source_dir / "public-result.json"),
             "key": key, "current_problem": problem, "same_task_design_dt_and_science": True})
        save(folder / "public-result.json", public)
        ledger["cache_reuses"] += 1
    else:
        capacity(reserve=2000000)
        if ledger["full_dynamic_inputs"] >= 20 or ledger["full_dynamic_wall_s"] >= 1800:
            raise ValueError("GLOBAL_FULL_DYNAMIC_CAP")
        if initial and ledger["initial_inputs"] >= 2:
            raise ValueError("COMMON_INITIAL_CAP")
        ledger["full_dynamic_inputs"] += 1
        ledger["initial_inputs"] += int(initial)
        item["full_dynamic_inputs"] = 1
        job = {"task_entry": task_entry, "design": state["design"], "problem": state["problem"],
               "decision": decision, "output_dir": str(folder)}
        input_file = folder.parent / (folder.name + "-input.json")
        save(input_file, job)
        save(HERE / "resource-ledger.json", ledger)
        started = time.monotonic()
        proc = subprocess.Popen([sys.executable, "-B", __file__, "_execute", str(input_file)],
               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
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
        item["wall_s"] = time.monotonic() - started
        ledger["full_dynamic_wall_s"] += item["wall_s"]
        ledger["attempts"].append(item)
        save(HERE / "resource-ledger.json", ledger)
        if proc.returncode or item.get("error"):
            save(folder.parent / (folder.name + "-error.json"), {**item, "exit_code": proc.returncode,
                 "stderr_tail": stderr[-4000:]})
            raise ValueError(item.get("error", "FULL_DYNAMIC_ERROR:" + stderr[-1200:]))
        public = read(folder / "public-result.json")
        source_dir = folder
        cache[key] = folder
    raw, assessment = read(source_dir / "raw.json"), read(source_dir / "assessment.json")
    if (identity({k: v for k, v in raw.items() if k != "result_sha256"}) != raw["result_sha256"]
            or public["result_sha256"] != raw["result_sha256"] or public["design"] != design
            or public["task_sha256"] != identity(task)
            or assessment["verdict"] != public["public_check"]["verdict"]):
        raise ValueError("INDEPENDENT_RESULT_BINDING_FAILED")
    if not initial:
        ledger["evaluations_including_reuse"] += 1
    item.update(public_result=bind(folder / "public-result.json"), raw=bind(source_dir / "raw.json"),
                assessment=bind(source_dir / "assessment.json"), model_valid=raw["model_valid"],
                domain_errors=raw["domain_errors"], public_check=public["public_check"],
                activity_counts=dict(Counter(x["action"] for x in raw["activity"])),
                minimum_tx_terminal_v=raw["minimum_tx_terminal_v"],
                records=len(raw["records"]), packets=len(raw["packets"]))
    save(folder / "readback.json", item)
    save(HERE / "resource-ledger.json", ledger)
    validate(protocol)
    return public, item


def passed(result):
    return result.get("model_valid") is True and result.get("public_check", {}).get("verdict") == "PASS"


def run_track(cell, entry, initial, protocol, ledger, cache):
    from bfworld.agentlab.pqe20261022.m2_methods import M2Harness, M2GenericHarness
    task = load_task(entry)
    root = HERE / "episodes" / cell["episode"]
    ep, method = None, None
    started = time.monotonic()
    rows, error, status = [], None, "FINITE_EVIDENCE_STOP"
    counted_scores, evaluations, formal_tools = 0, 0, 0
    failures, emitted_batches = set(), set()
    state = p.episode_initial_state(task, task["initial_design"], task["initial_problem"])
    state["task"] = deepcopy(checked(entry["public_input"])["task"])
    state["evidence"].append({"origin": "COMMON_PUBLIC_ENGINEERING_MATERIALS",
                              "materials": checked(protocol["public_materials"])})
    external = {"status": "READY", "selected_id": "common-initial",
                "actual_input": {"operation": "verify", "design_patch": {}, "problem_patch": {}},
                "origin": "COMMON_INITIAL_NOT_AGENT_SELECTED"}

    def score_count():
        return int(getattr(method, "analytic_score_count", 0))

    def public_tools():
        return int(getattr(method, "public_tool_call_count", 0))

    def sync_scores():
        nonlocal counted_scores
        current = score_count()
        delta = current - counted_scores
        if delta < 0 or current > 24 or ledger["cheap_scores"] + delta > 144:
            raise ValueError("CHEAP_SCORE_ACCOUNTING_CAP")
        ledger["cheap_scores"] += delta
        counted_scores = current
        ledger["tracks"][cell["episode"]] = {"cheap_scores": current,
             "evaluations_including_reuse": evaluations, "public_tool_calls": public_tools(),
             "formal_tool_calls": formal_tools}
        save(HERE / "resource-ledger.json", ledger)
        if formal_tools + public_tools() > 24:
            raise ValueError("TRACK_TOOL_CAP")
        if ep:
            ep.tools = formal_tools + public_tools()

    def quota():
        sync_scores()
        q = {"remaining_actions": max(0, 3 - evaluations), "remaining_cost": max(0, 3 - evaluations),
             "max_candidates": 64, "analytic_scores_left": 24 - score_count(),
             "public_tool_calls_left": 24 - formal_tools - public_tools(),
             "model_call_reserve": .19, "model_calls_remaining": 12,
             "model_cost_remaining": 5}
        if ep:
            b = ep.ready()
            # _Method counts its usage_ledger cumulatively, so these are total
            # episode envelopes; the broker separately enforces remaining caps.
            q.update(output_tokens_remaining=65536 - b["output_tokens"])
        return q

    def model_call(request):
        sync_scores()
        b = ep.ready(paid=True)
        request = compact_embedded(deepcopy(request))
        instructions = planner_instructions(request)
        instructions = instructions.replace("All four conditions", "All three conditions")
        instructions = instructions.replace("Keep at most 4 finite candidates.", "Keep at most64 finite candidates within the declared budget.")
        instructions = instructions.replace("total candidates including observations must be <=4.", "total candidates including observations must be <=64.")
        request.update(episode_id=cell["episode"], condition="strong_generic",
             json_instructions=instructions + " Alternatively, the declared PUBLIC_TOOLS JSON in context.public_tool_instruction is an available host-tool request at this same site; return to the ordinary candidate/selection schema after reading its factual results.")
        request["max_output_tokens"] = min(32768, 65536 - b["output_tokens"])
        response = ep.planner(request)
        if response.get("usage", {}).get("model_identity") != protocol["model_identity"]:
            ep.fatal = "MODEL_IDENTITY_MISMATCH"
            response["payload"] = {"status": "MODEL_IDENTITY_MISMATCH"}
        if response.get("provider_status") != "COMPLETE":
            response["payload"] = {"status": "TOOL_ERROR", "reason": response.get("error")}
        return response

    try:
        if cell["condition"] == "G":
            ep = ModelEpisode(cell["episode"], task["task_id"], "strong_generic", protocol,
                              {}, task_resolver=lambda ident: deepcopy(task) if ident == task["task_id"] else None)
            ep.start_server()
            method = M2GenericHarness(model_call)
        else:
            root.mkdir(parents=True, exist_ok=False)
            method = M2Harness(feedback_enabled=cell["condition"] == "U")
        method.quota = quota()
        state = method.update(state, deepcopy(external), deepcopy(initial))
        sync_scores()
        record(root / "external-update.json", {"input_public_result": bind(HERE / "initial" / entry["id"] / "public-result.json"),
               "decision": external, "state_after": state, "full_state_sha256": identity(state),
               "autonomous_numerical_or_model_charge": 0})
        if initial.get("model_valid") is True and initial["public_check"]["verdict"] == "FAIL":
            failures.add(identity(initial["design"]))
        last = initial
        for generation in range(1, 4):
            validate(protocol)
            if passed(last):
                status = "PASS_RETAINED"
                break
            if last.get("execution_status") in {"TOOL_ERROR", "ERROR"}:
                status = "TOOL_ERROR_RETAINED"
                break
            if evaluations >= 3:
                status = "CANDIDATE_EVALUATION_CAP"
                break
            before = deepcopy(state)
            q = quota()
            batch = method.generate(state, q)
            sync_scores()
            decision = method.select(state, batch, quota())
            sync_scores()
            row = {"generation": generation, "state_before": before, "full_state_before_sha256": identity(before),
                   "generate": batch, "select": decision, "cheap_scores_cumulative": score_count()}
            rows.append(row)
            if decision.get("status") != "READY":
                row["finite_stop"] = decision.get("status")
                rejected = batch.get("rejected") or decision.get("rejected") or []
                batch_key = identity({"batch": batch.get("candidates", []), "rejected": rejected})
                if rejected and batch_key not in emitted_batches and generation < 3 and not getattr(method, "blocked", False):
                    emitted_batches.add(batch_key)
                    state.setdefault("strategy", {}).setdefault("public_rejections", []).append({"generation": generation,
                         "batch_rejections": rejected, "selection": decision})
                    row["common_regeneration"] = True
                    record(root / "chain.json", {"rows": rows})
                    continue
                status = str(decision.get("status", "FINITE_EVIDENCE_STOP"))
                break
            actual = decision["actual_input"]
            proposed = {**state["design"], **actual.get("design_patch", {})}
            if identity(proposed) in failures:
                row["common_rejection"] = "Exact previously executed valid failed point; no family exclusion"
                state.setdefault("strategy", {}).setdefault("public_rejections", []).append({"actual_input": actual,
                    "reason": row["common_rejection"]})
                record(root / "chain.json", {"rows": rows})
                continue
            formal_tools += 1
            evaluations += 1
            sync_scores()
            result, consequence = execute(entry, state, decision,
                 root / "actions" / f"{evaluations:02d}", ledger, cache, protocol)
            row.update(result=result, consequence=consequence)
            state = method.update(state, decision, deepcopy(result))
            sync_scores()
            row.update(state_after=state, full_state_after_sha256=identity(state))
            last = result
            if result.get("model_valid") is True and result["public_check"]["verdict"] == "FAIL":
                failures.add(identity(result["design"]))
            record(root / "chain.json", {"rows": rows, "loaded_program_calls": method.program.calls,
                   "method_decisions": getattr(method, "decisions", []),
                   "analytic_score_log": getattr(method, "analytic_score_log", []),
                   "public_tool_call_log": getattr(method, "public_tool_call_log", [])})
            print(json.dumps({"episode": cell["episode"], "evaluation": evaluations,
                  "public_check": result["public_check"], "model_valid": result["model_valid"],
                  "reused": consequence["reused"], "cheap_scores": score_count()}), flush=True)
            if passed(result):
                status = "PASS_RETAINED"
                break
        else:
            status = "CANDIDATE_EVALUATION_CAP" if evaluations >= 3 else "GENERATION_ROUND_CAP"
        record(root / "stop.json", {"status": status, "valid_PASS_retained": passed(last),
               "new_actions_after_PASS": 0, "last_result_sha256": last.get("result_sha256")})
    except Exception as exc:
        error, status = type(exc).__name__ + ":" + str(exc), "TOOL_ERROR_RETAINED"
    finally:
        if method is not None:
            try:
                sync_scores()
            except Exception as exc:
                error = error or type(exc).__name__ + ":" + str(exc)
                status = "TOOL_ERROR_RETAINED"
            record(root / "chain.json", {"rows": rows,
                   "loaded_program_calls": method.program.calls,
                   "method_decisions": getattr(method, "decisions", []),
                   "analytic_score_log": getattr(method, "analytic_score_log", []),
                   "public_tool_call_log": getattr(method, "public_tool_call_log", [])})
        account = None
        if ep:
            ep.close()
            account = p.ledger(DB, ep.owner)
            save(root / "provider-costs.json", account)
        result = {**cell, "status": status, "error": error, "wall_s": time.monotonic() - started,
                  "evaluations_including_reuse": evaluations, "cheap_scores": score_count() if method else 0,
                  "formal_tools": formal_tools, "public_tools": public_tools() if method else 0,
                  "last_design": state.get("design"),
                  "last_public_check": state.get("last_result", {}).get("public_check"),
                  "last_model_valid": state.get("last_result", {}).get("model_valid"),
                  "accounting": {k: v for k, v in account.items() if k != "rows"} if account else None,
                  "owner": ep.owner if ep else None,
                  "provider_fatal": ep.fatal if ep else None,
                  "initial_result": bind(HERE / "initial" / entry["id"] / "public-result.json")}
        save(root / "episode-result.json", result)
    print(json.dumps({k: result[k] for k in ["episode", "status", "error", "evaluations_including_reuse", "cheap_scores", "last_public_check"]}), flush=True)
    return result


def run():
    protocol = read(PROTOCOL) if PROTOCOL.exists() else freeze()
    validate(protocol)
    configure(protocol)
    with (HERE / "run-claim.json").open("x") as stream:
        json.dump({"at": now(), "pid": os.getpid(), "protocol": bind(PROTOCOL), "retry": False}, stream)
    lock = HERE / "active.lock"
    with lock.open("x") as stream:
        stream.write(str(os.getpid()))
    ledger = read(HERE / "resource-ledger.json")
    rows, initials, cache, error = [], {}, {}, None
    try:
        # All Task/Design/method identities above were frozen before any result.
        for entry in protocol["tasks"]:
            if entry["status"] != "READY":
                continue
            task = load_task(entry)
            state = p.episode_initial_state(task, task["initial_design"], task["initial_problem"])
            decision = {"status": "READY", "selected_id": "common-initial",
                        "actual_input": {"operation": "verify", "design_patch": {}, "problem_patch": {}}}
            try:
                result, consequence = execute(entry, state, decision, HERE / "initial" / entry["id"],
                                               ledger, cache, protocol, initial=True)
                initials[entry["id"]] = result
                print(json.dumps({"initial": entry["id"], "public_check": result["public_check"],
                      "model_valid": result["model_valid"]}), flush=True)
            except Exception as exc:
                save(HERE / "initial" / (entry["id"] + "-error.json"), {"error": repr(exc), "at": now()})
        with runtime_scope():
            paid_dispatch_blocked = False
            for cell in protocol["order"]:
                entry = next(row for row in protocol["tasks"] if row["id"] == cell["task"])
                if entry["id"] not in initials:
                    row = {**cell, "status": "NOT_EXECUTED", "reason": entry.get("reason", "Common initial unavailable; see retained error")}
                elif paid_dispatch_blocked and cell["condition"] == "G":
                    row = {**cell, "status": "NOT_EXECUTED_NEW_USAGE_STOP"}
                else:
                    row = run_track(cell, entry, initials[entry["id"]], protocol, ledger, cache)
                    if row.get("provider_fatal"):
                        paid_dispatch_blocked = True
                rows.append(row)
                save(HERE / "batch-result.json", {"package": PACKAGE, "status": "RUNNING", "tracks": rows})
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
    finally:
        lock.unlink(missing_ok=True)
        validate(protocol)
        save(HERE / "batch-result.json", {"package": PACKAGE,
             "status": "COMPLETE_FINITE_SIX_TRACKS" if len(rows) == 6 and not error else "FINITE_STOP_RETAINED",
             "error": error, "tracks": rows, "completed_at": now(),
             "resource_ledger": bind(HERE / "resource-ledger.json"),
             "provider_before": protocol["provider_before"], "provider_after": provider_snapshot(),
             "capacity": capacity(), "claim_boundary": protocol["claim_boundary"]})
    print(json.dumps({"package": PACKAGE, "tracks": len(rows), "error": error,
                      "full_dynamic_inputs": ledger["full_dynamic_inputs"],
                      "cheap_scores": ledger["cheap_scores"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["run", "_execute"], nargs="?", default="run")
    parser.add_argument("input_file", nargs="?")
    args = parser.parse_args()
    if args.mode == "_execute":
        child(args.input_file)
    else:
        run()
