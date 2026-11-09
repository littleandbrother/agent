"""One finite M3 engineering package. No source tuning after participant freeze."""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import http.server
import importlib.util
import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
BASE = ROOT / "docs/research/pqe-two-paper-plan-20261022"
HERE = Path(__file__).resolve().parent
OUT = HERE.parent
PKG = APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import adapter, pilot as p
from bfworld.agentlab.pqe20261022.executor import identity
from bfworld.agentlab.pqe20261022.methods import common_contract_check
from bfworld.agentlab.pqe20261022.episode_methods import planner_instructions
from bfworld.agentlab.historical_usage import new_batch_usage_blockers
from public_projection import PublicObjects, encoded, dispatch_classification

spec = importlib.util.spec_from_file_location("m2_readonly_helpers", BASE / "dynamic-decision-m2/s0/run_m2.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
now, read, bind, checked, save = old.now, old.read, old.bind, old.checked, old.save
load_task, provider_snapshot = old.load_task, old.provider_snapshot
PACKAGE = "BF-PQE-SERVICE-REPAIR-M3-20261023-001"
PROTOCOL = OUT / "shared/protocol.json"
LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=3, candidates=3,
              wall_s=900, output_tokens=32768, generated_tokens=65536, usd=5, bytes=35000000)
TOTAL = dict(requests=12, tool_calls=24, numerical_inputs=10, usd=5, retained_bytes=80000000)


def capacity():
    fs = os.statvfs(ROOT)
    available = fs.f_bavail * fs.f_frsize
    size = sum(x.stat().st_size for x in OUT.rglob("*") if x.is_file())
    if available < 10800000000 or size >= 80000000:
        raise ValueError("STORAGE_RESOURCE_GATE")
    return {"at": now(), "available_bytes": available, "retained_logical_bytes": size,
            "deleted_bytes": 0, "new_backups": 0, "peak_additional_bytes": 800000000}


def configure(protocol):
    p.OUT, p.PACKAGE, p.LIMITS, p.TOTAL_CAPS = OUT, PACKAGE, dict(LIMITS), dict(TOTAL)
    p.SDK = Path(protocol["sdk_entry"])
    p.CELLS = [("m3-g", protocol["tasks"][1]["task_key"], "strong_generic")]


def validate(protocol, *, participant=False):
    for path, expected in protocol["source_bindings"].items():
        if bind(path)["sha256"] != expected:
            raise ValueError("FROZEN_SOURCE_CHANGED:" + path)
    if participant:
        freeze = read(HERE / "participant-freeze.json")
        for path, expected in freeze["source_bindings"].items():
            if bind(path)["sha256"] != expected:
                raise ValueError("PARTICIPANT_SOURCE_CHANGED:" + path)
    for entry in protocol["tasks"]:
        load_task(entry)
    for name in ["common_start", "common_before", "common_decision", "common_result"]:
        checked(protocol[name])
    if provider_snapshot()["historical_unknown_sha256"] != protocol["provider_before"]["historical_unknown_sha256"]:
        raise ValueError("R11_HISTORICAL_ROW_CHANGED")


@contextmanager
def runtime_scope():
    installed, prior = False, None
    try:
        with p.dbconnect() as db:
            if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
                raise ValueError("PROVIDER_ALREADY_INFLIGHT")
            if db.execute("SELECT 1 FROM research_model_owners WHERE protocol=?", (PACKAGE,)).fetchone():
                raise ValueError("M3_OWNER_EXISTS_NO_RETRY")
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            prior = row["value"] if row else None
            db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
            installed = True
        save(HERE / "runtime-registration.json", {"at": now(), "scope_before": prior,
             "temporary_scope": "per-owner", "study_usd_cap": 5,
             "per_episode_usd_cap": 5, "authorized_episodes": 1})
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
                owners = [x[0] for x in db.execute("SELECT owner FROM research_model_owners WHERE protocol=?", (PACKAGE,))]
                for owner in owners:
                    db.execute("UPDATE grants SET expires=? WHERE owner=?", (time.time(), owner))
                    db.execute("DELETE FROM principals WHERE owner=?", (owner,))
                    db.execute("UPDATE conversations SET status='IDLE',updated=? WHERE id=?", (time.time(), owner))
                db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))
            save(HERE / "runtime-closeout.json", {"at": now(), "scope_restored_to": prior,
                 "closed_owners": owners, "provider_after": provider_snapshot(), "history_rows_deleted": 0})


class LocalToolNotExecuted(RuntimeError):
    pass


class ModelEpisode(p.Episode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        save(self.root / "owner.json", {"owner": self.owner, "episode": self.ident,
             "finite_usd": 5, "grant_wall_s": 900, "no_unbounded_authorization": True})

    def ready(self, paid=False):
        if self.fatal:
            raise ValueError(self.fatal)
        budget = self.budget()
        capacity()
        if budget["wall_s"] >= 900:
            raise ValueError("EPISODE_WALL_CAP")
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

    def start_server(self):
        host = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                try:
                    host.dispatch_stage = "TRUSTED_LOCAL_PREFLIGHT"
                    if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != "Bearer " + host.access_token:
                        raise ValueError("BROKER_ROUTE_OR_AUTH_DENIED")
                    length = int(self.headers.get("Content-Length", "0"))
                    host.actual_wire_bytes = length
                    # Same400000 hard limit; this checks actual SDK serialization
                    # before any dispatch, reservation or provider network call.
                    if not 0 < length <= 400000:
                        raise ValueError("BODY_CAP")
                    budget = host.ready(paid=True)
                    grant = min(host.callback_output_cap, p.output_allowance(budget["output_tokens"], LIMITS))
                    body = p.validate_wire(json.loads(self.rfile.read(length)), grant)
                    if body["max_tokens"] != host.callback_output_cap:
                        raise ValueError("SDK_OUTPUT_GRANT_MISMATCH")
                    if host.call_relays >= 1:
                        raise ValueError("ONE_PROVIDER_CALL_PER_PI_CALLBACK")
                    host.call_relays += 1
                    host.model_calls += 1
                    folder = host.root / "callbacks" / f"{host.callback_index:02d}"
                    save(folder / "wire-public.json", body)
                    host.dispatch_stage = "FORWARD_ATTEMPT_STARTED"
                    request = urllib.request.Request(p.SERVICE + self.path, data=p.encoded(body),
                        headers={"Authorization": "Bearer " + host.token, "Content-Type": "application/json"})
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,
                            timeout=min(310, max(1, 900 - (time.monotonic() - host.started)))) as response:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.end_headers()
                        for line in response:
                            if line.startswith(b"data:") and line.strip() != b"data: [DONE]":
                                data = json.loads(line[5:])
                                if data.get("model") and data["model"] != "deepseek-flash":
                                    host.fatal = "RESPONSE_MODEL_MISMATCH"
                                    raise ValueError(host.fatal)
                            self.wfile.write(line)
                            self.wfile.flush()
                        host.dispatch_stage = "FORWARDED_RESPONSE_COMPLETE"
                except Exception as exc:
                    host.relay_error = type(exc).__name__ + ":" + str(exc)[:400]
                    try:
                        self.send_error(400, host.relay_error)
                    except OSError:
                        pass
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def planner(self, request):
        budget = self.ready(paid=True)
        before = p.ledger(p.DATABASE, self.owner)
        self.callback_output_cap = request["max_output_tokens"]
        if not 1 <= self.callback_output_cap <= p.output_allowance(budget["output_tokens"], LIMITS):
            raise ValueError("CALLBACK_OUTPUT_GRANT_INVALID")
        self.callback_index = 1 + len(list((self.root / "callbacks").glob("*"))) if (self.root / "callbacks").exists() else 1
        folder = self.root / "callbacks" / f"{self.callback_index:02d}"
        folder.mkdir(parents=True)
        self.call_relays, self.relay_error = 0, None
        self.actual_wire_bytes, self.dispatch_stage = None, "TRUSTED_LOCAL_PREFLIGHT"
        # Avoid old deduplicate_public_results re-expanding projected references
        # into a full prompt registry. Only the new bounded public graph is sent.
        instruction = p.callback_payload({"site": request.get("site")}, self.callback_output_cap)["instruction"]
        payload = {"instruction": instruction + " Read public_object_ref through the declared public_object host tool; full public data is outside this prompt, never hidden scientific truth.",
                   "request": request, "max_output_tokens": self.callback_output_cap}
        save(folder / "input-public.json", payload)
        preflight_bytes = len(p.encoded(payload))
        if preflight_bytes > 240000:
            save(folder / "dispatch-facts.json", {"stage": self.dispatch_stage, "payload_bytes": preflight_bytes,
                 "forwarded": False, "classification": "LOCAL_TOOL_NOT_EXECUTED"})
            raise LocalToolNotExecuted("SERIALIZED_PUBLIC_PAYLOAD_CAP_PRE_FORWARD")
        config = {"sdk_entry": str(p.SDK), "workspace": str(folder / "participant"),
                  "service": "http://127.0.0.1:" + str(self.server.server_port), "token": self.access_token, **payload}
        with (folder / "pi-public.jsonl").open("w") as stdout, (folder / "stderr.log").open("w") as stderr:
            proc = subprocess.Popen(["/opt/homebrew/bin/node", str(APP / "scripts/pqe_pi_callback.mjs")],
                cwd=folder, env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin", "LANG": "en_US.UTF-8"},
                stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                proc.communicate(p.encoded(config) + b"\n", timeout=max(1, 900 - (time.monotonic() - self.started)))
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                self.fatal = "EPISODE_WALL_CAP"
        after = p.ledger(p.DATABASE, self.owner)
        previous = {x["id"] for x in before["rows"]}
        rows = [x for x in after["rows"] if x["id"] not in previous]
        settled = len(rows) == 1 and rows[0]["status"] == "SETTLED" and bool(rows[0]["usage"])
        classification = dispatch_classification(trusted_pre_forward=self.dispatch_stage == "TRUSTED_LOCAL_PREFLIGHT",
            forwarded=self.call_relays > 0, request_rows=len(rows), usage_known=settled)
        facts = {"stage": self.dispatch_stage, "actual_sdk_wire_bytes": self.actual_wire_bytes,
                 "payload_bytes": preflight_bytes, "forwarded": self.call_relays > 0,
                 "provider_row_count": len(rows), "classification": classification,
                 "request_ids": [x["id"] for x in rows], "relay_error": self.relay_error}
        save(folder / "dispatch-facts.json", facts)
        if classification == "LOCAL_TOOL_NOT_EXECUTED":
            save(folder / "callback-result.json", {"payload": {"status": "TOOL_NOT_EXECUTED"},
                 "usage": {"status": "NOT_DISPATCHED"}, "provider_status": classification,
                 "error": self.relay_error, "dispatch_facts": facts})
            raise LocalToolNotExecuted(self.relay_error or "SDK_LOCAL_PRE_FORWARD_FAILURE")
        usage = {"status": "UNKNOWN", "model_identity": p.MODEL_IDENTITY, "request_ids": [x["id"] for x in rows]}
        if settled:
            raw = json.loads(rows[0]["usage"])
            usage.update(status="KNOWN", cost=rows[0]["charged"], input_tokens=raw["prompt_tokens"], output_tokens=raw["completion_tokens"])
            if usage["output_tokens"] > self.callback_output_cap or budget["output_tokens"] + usage["output_tokens"] > 65536:
                self.fatal = "PROVIDER_OUTPUT_CAP_EXCEEDED"
            if rows[0]["error"] and rows[0]["error"].startswith(("PROVIDER_RESERVATION", "PROVIDER_TOKEN")):
                self.fatal = rows[0]["error"]
        else:
            self.fatal = "PROVIDER_USAGE_NOT_SETTLED"
        records = [json.loads(line) for line in (folder / "pi-public.jsonl").read_text().splitlines() if line.strip()]
        loaded = [v for v in records if v.get("type") == "pqe_pi_loaded"]
        answers = [v for v in records if v.get("type") == "assistant_public"]
        answer, error, status = {"status": "INVALID_PLANNER_OUTPUT"}, self.relay_error, "COMPLETE"
        try:
            if proc.returncode:
                raise ValueError("PI_PROCESS_EXIT:" + str(proc.returncode))
            if len(loaded) != 1 or loaded[0]["tools"] or loaded[0]["history_messages"]:
                raise ValueError("PI_CONTEXT_OR_TOOL_BOUNDARY")
            if len(answers) != 1 or answers[0].get("stopReason") != "stop":
                raise ValueError("PI_STOP_REASON")
            if any(v["type"] != "text" for v in answers[0]["content"]):
                raise ValueError("MODEL_TOOL_OUTPUT_DENIED")
            answer = json.loads("".join(v["text"] for v in answers[0]["content"]))
            if not isinstance(answer, dict):
                raise ValueError("JSON_OBJECT_REQUIRED")
        except (ValueError, KeyError) as exc:
            error, status = str(exc), "PARSE_OR_TRANSPORT_ERROR"
        if self.relay_error:
            status = "PARSE_OR_TRANSPORT_ERROR"
        result = {"payload": answer, "usage": usage, "request_ids": facts["request_ids"],
                  "provider_status": status, "error": error, "dispatch_facts": facts,
                  "granted_max_output_tokens": self.callback_output_cap,
                  "output_budget_before": budget["output_tokens"], "output_budget_after": self.budget()["output_tokens"]}
        save(folder / "callback-result.json", result)
        print(json.dumps({"episode": self.ident, "callback": self.callback_index,
                          "site": request.get("site"), "usage": usage["status"], "error": error}), flush=True)
        return result


def freeze_engineering():
    if PROTOCOL.exists():
        raise ValueError("M3_PROTOCOL_ALREADY_FROZEN")
    m2 = read(BASE / "dynamic-decision-m2/shared/protocol.json")
    common = read(OUT / "shared/common-start.json")
    bindings = dict(m2["source_bindings"])
    for path in [Path(__file__), HERE / "public_projection.py"]:
        bindings[str(path)] = bind(path)["sha256"]
    protocol = {"package": PACKAGE, "frozen_at": now(), "source_bindings": bindings,
                "tasks": read(OUT / "shared/tasks.json")["tasks"],
                "common_start": bind(OUT / "shared/common-start.json"),
                "common_before": common["before"], "common_decision": common["first_decision"],
                "common_result": common["first_public_result"],
                "scientific_source": m2["scientific_source"], "apparatus_source": adapter.source_identity(),
                "sdk_entry": m2["sdk_entry"], "same_backend": m2["same_backend"],
                "model_identity": m2["model_identity"], "provider_before": provider_snapshot(),
                "limits": LIMITS, "total_caps": TOTAL, "capacity": capacity(),
                "engineering_requests": bind(OUT / "a/engineering-requests.json"),
                "engineering_source": bind(PKG / "service_relations.py"),
                "order": ["m3-g", "m3-u"], "maximum_cheap_scores": 60,
                "claim_boundary": "Seen-task developer service-model/method formation and bounded original-consumer consequences; no isolated Update causality, learned H, held-out transfer, RSI, global infeasibility or physical qualification."}
    if protocol["provider_before"]["inflight"]:
        raise ValueError("PROVIDER_ALREADY_INFLIGHT")
    validate(protocol)
    save(PROTOCOL, protocol)
    save(HERE / "resource-ledger.json", {"package": PACKAGE, "full_dynamic_inputs": 0,
         "full_dynamic_wall_s": 0, "cheap_scores": 0, "A_cheap_scores": 0,
         "evaluations_including_reuse": 0, "cache_reuses": 0, "tracks": {}, "attempts": [],
         "categories": {}, "native_inputs": 0, "hardware_runs": 0,
         "post_participant_result_revisions": 0})
    return protocol


def exact_cache(protocol):
    cache = {}
    task_map = {entry["task_canonical_sha256"]: load_task(entry) for entry in protocol["tasks"]}
    source = BASE / "dynamic-decision-m2/s0"
    for folder in list((source / "initial").glob("*")) + list((source / "episodes").glob("*/actions/*")):
        if not (folder / "raw.json").exists():
            continue
        public = read(folder / "public-result.json")
        task = task_map.get(public["task_sha256"])
        if task is None:
            continue
        raw = read(folder / "raw.json")
        if raw["result_sha256"] != identity({k: v for k, v in raw.items() if k != "result_sha256"}):
            raise ValueError("PRIOR_CACHE_HASH_FAILED")
        key = p.execution_cache_key(task, public["design"], task["integration"]["dt_s"], protocol["apparatus_source"])
        cache[key] = folder
    return cache


def execute(entry, state, decision, folder, ledger, cache, protocol, category):
    validate(protocol, participant=category != "A")
    task = load_task(entry)
    actual = common_contract_check(state, decision["actual_input"], {"remaining_actions": 24})
    design = {**state["design"], **actual.get("design_patch", {})}
    problem = {**state["problem"], **actual.get("problem_patch", {})}
    adapter.validate_design(task, design)
    dt = actual.get("dt_s", task["integration"]["dt_s"])
    key = p.execution_cache_key(task, design, dt, protocol["apparatus_source"])
    category_limit = 2 if category in {"A", "regression"} else 3
    if ledger["categories"].get(category, 0) >= category_limit:
        raise ValueError("CATEGORY_EVALUATION_CAP")
    ledger["categories"][category] = ledger["categories"].get(category, 0) + 1
    attempt = {"at": now(), "category": category, "task": entry["id"], "cache_key": key,
               "design_sha256": identity(design), "decision_sha256": identity(decision),
               "reused": key in cache, "full_dynamic_inputs": 0}
    ledger["attempts"].append(attempt)
    if key in cache:
        original = cache[key]
        public = read(original / "public-result.json")
        public["problem"] = deepcopy(problem)
        public["usage"] = {"paid_model_requests": 0, "numerical_inputs": 0, "reused": True, "wall_s": 0}
        folder.mkdir(parents=True, exist_ok=False)
        save(folder / "reuse.json", {"source_public_result": bind(original / "public-result.json"),
             "key": key, "current_problem": problem, "same_task_design_dt_scientific_source": True})
        save(folder / "public-result.json", public)
        ledger["cache_reuses"] += 1
    else:
        capacity()
        if ledger["full_dynamic_inputs"] >= 10 or ledger["full_dynamic_wall_s"] >= 1080:
            raise ValueError("GLOBAL_FULL_DYNAMIC_CAP")
        ledger["full_dynamic_inputs"] += 1
        attempt["full_dynamic_inputs"] = 1
        job = {"task_entry": entry, "design": state["design"], "problem": state["problem"],
               "decision": decision, "output_dir": str(folder), "category": category}
        input_file = folder.parent / (folder.name + "-input.json")
        save(input_file, job)
        save(HERE / "resource-ledger.json", ledger)
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
        ledger["full_dynamic_wall_s"] += attempt["wall_s"]
        save(HERE / "resource-ledger.json", ledger)
        if proc.returncode or attempt.get("error"):
            save(folder.parent / (folder.name + "-error.json"), {**attempt,
                 "exit_code": proc.returncode, "stderr_tail": stderr[-4000:]})
            raise ValueError(attempt.get("error", "FULL_DYNAMIC_ERROR:" + stderr[-1500:]))
        public = read(folder / "public-result.json")
        original = folder
        cache[key] = folder
    raw, assessment = read(original / "raw.json"), read(original / "assessment.json")
    if (identity({k: v for k, v in raw.items() if k != "result_sha256"}) != raw["result_sha256"]
            or public["result_sha256"] != raw["result_sha256"] or public["design"] != design
            or public["task_sha256"] != identity(task) or assessment["verdict"] != public["public_check"]["verdict"]):
        raise ValueError("INDEPENDENT_RESULT_BINDING_FAILED")
    ledger["evaluations_including_reuse"] += 1
    attempt.update(public_result=bind(folder / "public-result.json"), raw=bind(original / "raw.json"),
        assessment=bind(original / "assessment.json"), model_valid=raw["model_valid"], domain_errors=raw["domain_errors"],
        public_check=public["public_check"], timely_matches=len(assessment.get("matches", [])),
        activity_counts=dict(Counter(x["action"] for x in raw["activity"])),
        minimum_tx_terminal_v=raw["minimum_tx_terminal_v"], records=len(raw["records"]), packets=len(raw["packets"]))
    save(folder / "readback.json", attempt)
    save(HERE / "resource-ledger.json", ledger)
    validate(protocol, participant=category != "A")
    return public, attempt


def child(path):
    job, protocol = read(path), read(PROTOCOL)
    validate(protocol, participant=job["category"] != "A")
    task = load_task(job["task_entry"])
    public = adapter.execute(task, job["design"], job["problem"], job["decision"], job["output_dir"],
                             task_resolver=lambda ident: deepcopy(task) if ident == task["task_id"] else None)
    validate(protocol, participant=job["category"] != "A")
    print(json.dumps({"public_check": public["public_check"], "model_valid": public["model_valid"]}), flush=True)


def engineering():
    protocol = freeze_engineering()
    configure(protocol)
    ledger = read(HERE / "resource-ledger.json")
    cache = exact_cache(protocol)
    state = checked(protocol["common_before"])
    initial = checked(protocol["common_result"])
    state.update(design=initial["design"], problem=initial["problem"], last_result=initial)
    request = checked(protocol["engineering_requests"])
    candidates = request["candidates"]
    if len(candidates) > 2:
        raise ValueError("A_ENGINEERING_CAP")
    rows = []
    for index, candidate in enumerate(candidates, 1):
        if not candidate.get("prediction"):
            raise ValueError("A_PREDECLARED_PREDICTION_REQUIRED")
        decision = {"status": "READY", "selected_id": candidate["id"], "actual_input": candidate["actual_input"]}
        result, consequence = execute(protocol["tasks"][1], deepcopy(state), decision,
            HERE / "engineering" / f"{index:02d}", ledger, cache, protocol, "A")
        rows.append({"id": candidate["id"], "predeclared": candidate,
                     "public_result": consequence["public_result"], "consequence": consequence})
        save(HERE / "engineering-result.json", {"package": PACKAGE, "rows": rows, "participant_visibility": "HOST_ONLY_NO_CONFIG_LEAK"})
        print(json.dumps({"engineering": candidate["id"], "public_check": result["public_check"],
                          "timely_matches": consequence["timely_matches"]}), flush=True)


def freeze_participants():
    protocol = read(PROTOCOL)
    validate(protocol)
    if (HERE / "participant-freeze.json").exists():
        raise ValueError("PARTICIPANTS_ALREADY_FROZEN")
    offline = read(HERE / "offline-path-check.json")
    receipt = read(OUT / "b/INTERFACE-RECEIPT.json")
    if offline.get("status") != "PASS":
        raise ValueError("OFFLINE_AFFECTED_PATH_CHECK_REQUIRED")
    bindings = {str(path): bind(path)["sha256"] for path in [PKG / "service_relations.py", PKG / "m3_methods.py",
        HERE / "run_m3.py", HERE / "public_projection.py"]}
    save(HERE / "participant-freeze.json", {"package": PACKAGE, "at": now(), "source_bindings": bindings,
        "B_receipt": bind(OUT / "b/INTERFACE-RECEIPT.json"), "A_API": bind(OUT / "a/API-SHAPE.json"),
        "offline_check": bind(HERE / "offline-path-check.json"),
        "common_start": protocol["common_start"], "post_result_revisions": 0,
        "scope": "New shared tools and new fixed method freeze before either participant result; engineering reference configurations excluded."})


def passed(result):
    return result.get("model_valid") is True and result.get("public_check", {}).get("verdict") == "PASS"


def run_track(condition, protocol, ledger, cache):
    from bfworld.agentlab.pqe20261022.m3_methods import M3ServiceHarness, M3GenericHarness
    ident = "m3-" + condition.lower()
    root = HERE / "episodes" / ident
    task = load_task(protocol["tasks"][1])
    state = checked(protocol["common_before"])
    initial = checked(protocol["common_result"])
    external = checked(protocol["common_decision"])
    objects = PublicObjects(HERE / "public-objects" / ident)
    common = checked(protocol["common_start"])
    for ref in [common["initial_public_result"], common["first_public_result"]]:
        objects.register(checked(ref), path=ref["path"])
    ep, method, error = None, None, None
    status, rows, scores_seen, evaluations, formal_tools = "FINITE_EVIDENCE_STOP", [], 0, 0, 0
    failures, emitted = set(), set()
    started = time.monotonic()

    def score_count():
        return int(getattr(method, "analytic_score_count", 0))

    def tool_count():
        return int(getattr(method, "public_tool_call_count", 0))

    def sync():
        nonlocal scores_seen
        current = score_count()
        delta = current - scores_seen
        if delta < 0 or current > 24 or ledger["cheap_scores"] + delta > 60:
            raise ValueError("CHEAP_SCORE_CAP")
        ledger["cheap_scores"] += delta
        scores_seen = current
        ledger["tracks"][ident] = {"cheap_scores": current, "evaluations_including_reuse": evaluations,
            "public_tools": tool_count(), "formal_tools": formal_tools}
        save(HERE / "resource-ledger.json", ledger)
        if tool_count() + formal_tools > 24:
            raise ValueError("COMBINED_TOOL_CAP")
        if ep:
            ep.tools = tool_count() + formal_tools

    def quota():
        sync()
        if time.monotonic() - started >= 900:
            raise ValueError("TRACK_WALL_CAP")
        q = {"remaining_actions": max(0, 3 - evaluations), "remaining_cost": max(0, 3 - evaluations),
             "max_candidates": 64, "analytic_scores_left": 24 - score_count(),
             "public_tool_calls_left": 24 - formal_tools - tool_count(),
             "model_call_reserve": .19, "model_calls_remaining": 12, "model_cost_remaining": 5}
        if ep:
            q["output_tokens_remaining"] = 65536 - ep.ready()["output_tokens"]
        return q

    def record(path, value):
        # Only public facts here. Private assessment stays in independent readback.
        save(path, objects.project(value))

    def model_call(request):
        sync()
        budget = ep.ready(paid=True)
        request = objects.project(deepcopy(request))
        instructions = planner_instructions(request).replace("All four conditions", "Both conditions")
        instructions = instructions.replace("Keep at most 4 finite candidates.", "Keep at most64 candidates within the finite budget.")
        instructions = instructions.replace("total candidates including observations must be <=4.", "total candidates including observations must be <=64.")
        request.update(episode_id=ident, condition="strong_generic", json_instructions=instructions +
            " PUBLIC_TOOLS at the same site may request the declared shared service/phase/engineering/prediction/public_object tools. Original facts are fully readable by object_id/section/offset; pages have row and byte limits. They provide facts/conditional predictions only. Select your own legal action. Do not treat UNKNOWN as PASS.")
        request["max_output_tokens"] = min(32768, 65536 - budget["output_tokens"])
        response = ep.planner(request)
        if response.get("usage", {}).get("model_identity") != protocol["model_identity"]:
            ep.fatal = "MODEL_IDENTITY_MISMATCH"
            response["payload"] = {"status": "MODEL_IDENTITY_MISMATCH"}
        if response.get("provider_status") != "COMPLETE":
            response["payload"] = {"status": "TOOL_ERROR", "reason": response.get("error")}
        return response

    last = initial
    try:
        if condition == "G":
            ep = ModelEpisode(ident, task["task_id"], "strong_generic", protocol, {},
                task_resolver=lambda key: deepcopy(task) if key == task["task_id"] else None)
            ep.start_server()
            method = M3GenericHarness(model_call, public_reader=objects.read)
        else:
            method = M3ServiceHarness()
        method.quota = quota()
        state = method.update(state, deepcopy(external), deepcopy(initial))
        sync()
        record(root / "external-update.json", {"input_public_result": protocol["common_result"],
            "decision": external, "state_after": state, "full_state_sha256": identity(state),
            "autonomous_numerical_or_model_charge": 0})
        failures.add(identity(initial["design"]))
        for generation in range(1, 4):
            validate(protocol, participant=True)
            if passed(last):
                status = "PASS_RETAINED"
                break
            if evaluations >= 3:
                status = "CANDIDATE_EVALUATION_CAP"
                break
            before = deepcopy(state)
            batch = method.generate(state, quota())
            sync()
            decision = method.select(state, batch, quota())
            sync()
            row = {"generation": generation, "state_before": before,
                   "generate": batch, "select": decision, "cheap_scores_cumulative": score_count()}
            rows.append(row)
            if decision.get("status") != "READY":
                row["finite_stop"] = decision.get("status")
                rejected = batch.get("rejected") or decision.get("rejected") or []
                key = identity({"candidates": batch.get("candidates", []), "rejected": rejected})
                if rejected and key not in emitted and generation < 3 and not getattr(method, "blocked", False):
                    emitted.add(key)
                    state.setdefault("strategy", {}).setdefault("public_rejections", []).append({"generation": generation,
                        "rejections": rejected, "selection": decision})
                    row["common_regeneration"] = True
                    record(root / "chain.json", {"rows": rows})
                    continue
                status = str(decision.get("status", "FINITE_EVIDENCE_STOP"))
                break
            proposed = {**state["design"], **decision["actual_input"].get("design_patch", {})}
            if identity(proposed) in failures:
                row["common_rejection"] = "Exact prior public valid FAIL point; no domain exclusion."
                state.setdefault("strategy", {}).setdefault("public_rejections", []).append({"actual_input": decision["actual_input"], "reason": row["common_rejection"]})
                record(root / "chain.json", {"rows": rows})
                continue
            formal_tools += 1
            evaluations += 1
            sync()
            result, consequence = execute(protocol["tasks"][1], state, decision,
                root / "actions" / f"{evaluations:02d}", ledger, cache, protocol, ident)
            objects.register(result, path=root / "actions" / f"{evaluations:02d}" / "public-result.json")
            # The assessment and its deadline matches remain host-only; public
            # transcripts/object pages must never register those private facts.
            row.update(result=result, consequence={"public_result": consequence["public_result"],
                                                   "reused": consequence["reused"]})
            state = method.update(state, decision, deepcopy(result))
            sync()
            row["state_after"] = state
            last = result
            if result.get("model_valid") is True and result["public_check"]["verdict"] == "FAIL":
                failures.add(identity(result["design"]))
            record(root / "chain.json", {"rows": rows, "loaded_program_calls": method.program.calls,
                "method_decisions": getattr(method, "decisions", []), "analytic_score_log": getattr(method, "analytic_score_log", []),
                "public_tool_call_log": getattr(method, "public_tool_call_log", [])})
            print(json.dumps({"episode": ident, "evaluation": evaluations, "public_check": result["public_check"],
                "model_valid": result["model_valid"], "timely_matches": consequence["timely_matches"],
                "reused": consequence["reused"], "cheap_scores": score_count()}), flush=True)
            if passed(result):
                status = "PASS_RETAINED"
                break
        else:
            status = "CANDIDATE_EVALUATION_CAP" if evaluations >= 3 else "GENERATION_ROUND_CAP"
    except Exception as exc:
        error, status = type(exc).__name__ + ":" + str(exc), "TOOL_ERROR_RETAINED"
    finally:
        if method is not None:
            try:
                sync()
                record(root / "chain.json", {"rows": rows, "loaded_program_calls": method.program.calls,
                    "method_decisions": getattr(method, "decisions", []), "analytic_score_log": getattr(method, "analytic_score_log", []),
                    "public_tool_call_log": getattr(method, "public_tool_call_log", [])})
            except Exception as exc:
                error = error or type(exc).__name__ + ":" + str(exc)
                status = "TOOL_ERROR_RETAINED"
        if ep:
            ep.close()
            save(root / "provider-costs.json", p.ledger(p.DATABASE, ep.owner))
        objects.save_index()
        save(root / "stop.json", {"status": status, "error": error, "valid_PASS_retained": passed(last),
            "last_result_sha256": last.get("result_sha256"), "new_actions_after_PASS": 0})
        result = {"episode": ident, "condition": condition, "status": status, "error": error,
            "wall_s": time.monotonic() - started, "evaluations_including_reuse": evaluations,
            "cheap_scores": score_count() if method else 0, "formal_tools": formal_tools,
            "public_tools": tool_count() if method else 0, "last_design": last.get("design"),
            "last_public_check": last.get("public_check"), "provider_fatal": ep.fatal if ep else None,
            "owner": ep.owner if ep else None}
        save(root / "track-result.json", result)
    return result


def run():
    protocol = read(PROTOCOL)
    validate(protocol, participant=True)
    if (HERE / "run-claim.json").exists():
        raise ValueError("M3_RUN_ALREADY_CLAIMED_NO_RETRY")
    configure(protocol)
    save(HERE / "run-claim.json", {"at": now(), "package": PACKAGE, "protocol": bind(PROTOCOL),
         "participant_freeze": bind(HERE / "participant-freeze.json"), "order": protocol["order"]})
    ledger, cache = read(HERE / "resource-ledger.json"), exact_cache(protocol)
    # A calculations are independent formation cost and never participant quota.
    a_ledger = read(OUT / "a/cheap-ledger.json")
    a_count = a_ledger.get("total_calls", a_ledger.get("cheap_scores", a_ledger.get("count", a_ledger.get("total", 0))))
    if type(a_count) is not int or not 0 <= a_count <= 12:
        raise ValueError("A_CHEAP_LEDGER_REQUIRED")
    ledger["A_cheap_scores"] = a_count
    ledger["cheap_scores"] += a_count
    rows, error = [], None
    try:
        with runtime_scope():
            for condition in ["G", "U"]:
                row = run_track(condition, protocol, ledger, cache)
                rows.append(row)
                save(HERE / "batch-result.json", {"package": PACKAGE, "status": "RUNNING", "tracks": rows})
                if row.get("provider_fatal") in {"PROVIDER_USAGE_NOT_SETTLED", "NEW_USAGE_UNKNOWN_STOP"}:
                    rows.append({"episode": "m3-u", "condition": "U", "status": "NOT_EXECUTED_NEW_USAGE_STOP"})
                    break
            for row in rows:
                if row.get("evaluations_including_reuse", 0) < 1:
                    continue
                last = HERE / "episodes" / row["episode"] / "actions" / f"{row['evaluations_including_reuse']:02d}"
                consequence = read(last / "readback.json")
                if consequence["model_valid"] and consequence["timely_matches"] > 0:
                    # Host-only independent regression, never returned for tuning.
                    task1 = load_task(protocol["tasks"][0])
                    design = row["last_design"]
                    regression_state = p.episode_initial_state(task1, design, task1["initial_problem"])
                    decision = {"status": "READY", "selected_id": row["episode"] + "-conditional-regression",
                        "actual_input": {"operation": "verify", "design_patch": {}, "problem_patch": {}}}
                    result, item = execute(protocol["tasks"][0], regression_state, decision,
                        HERE / "regressions" / row["episode"], ledger, cache, protocol, "regression")
                    row["conditional_regression"] = item
                    print(json.dumps({"regression": row["episode"], "public_check": result["public_check"]}), flush=True)
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
    finally:
        validate(protocol, participant=True)
        save(HERE / "batch-result.json", {"package": PACKAGE,
            "status": "COMPLETE_FINITE_TWO_TRACKS" if len(rows) == 2 and not error else "FINITE_STOP_RETAINED",
            "error": error, "tracks": rows, "completed_at": now(),
            "resource_ledger": bind(HERE / "resource-ledger.json"), "provider_before": protocol["provider_before"],
            "provider_after": provider_snapshot(), "capacity": capacity(), "claim_boundary": protocol["claim_boundary"]})
    print(json.dumps({"package": PACKAGE, "tracks": len(rows), "error": error,
        "full_dynamic_inputs": ledger["full_dynamic_inputs"], "cheap_scores": ledger["cheap_scores"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["engineering", "freeze-participants", "run", "_execute"])
    parser.add_argument("input_file", nargs="?")
    args = parser.parse_args()
    if args.mode == "engineering":
        engineering()
    elif args.mode == "freeze-participants":
        freeze_participants()
    elif args.mode == "_execute":
        child(args.input_file)
    else:
        run()
