"""Finite, accounted transport and original-consumer broker. No decision rules."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import hashlib
import http.server
import importlib.util
import json
import os
import signal
import stat as stat_module
import subprocess
import sys
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
OUT, BASE = HERE.parent, HERE.parent.parent
ROOT = BASE.parents[2]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
PKG = APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261024lc"
PACKAGE = "BF-PQE-LC-SERVICE-LEARNING-20261024-001"
PROTOCOL = OUT / "shared/protocol.json"
spec = importlib.util.spec_from_file_location("lc_existing_transport", BASE / "f1-conditional-learning/s0/run_learning.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
p, host = legacy.p, legacy.host
read, save, bind, checked, identity, now = legacy.read, legacy.save, legacy.bind, legacy.checked, legacy.identity, legacy.now
from bfworld.agentlab.pqe20261024lc import adapter
from bfworld.agentlab.pqe20261022.methods import common_contract_check
from bfworld.agentlab.historical_usage import new_batch_usage_blockers

SOLVE = dict(model_requests=12, tool_calls=24, numerical_inputs=4, candidates=4,
             wall_s=900, output_tokens=65536, generated_tokens=131072, usd=5, bytes=60000000)
FORMATION = dict(model_requests=24, tool_calls=48, numerical_inputs=8, candidates=8,
                 wall_s=1800, output_tokens=65536, generated_tokens=262144, usd=10, bytes=90000000)
TOTAL = dict(requests=120, tool_calls=240, numerical_inputs=50, usd=50, retained_bytes=150000000)
PLAN = [("form-h2", "formation", "H2"), ("form-h4", "formation", "H4")]
PLAN += [(role + "-" + c.lower(), role, c) for role in ("t1", "t2") for c in ("H1", "H2", "H4")]


def capacity():
    stat = os.statvfs(ROOT)
    free = stat.f_bavail * stat.f_frsize
    files = [x.stat() for x in OUT.rglob("*") if x.is_file()]
    size = sum(x.st_size for x in files)
    allocated = sum(max(4096, x.st_blocks * 512) for x in files)
    if free < 11000000000 or allocated >= TOTAL["retained_bytes"]:
        raise ValueError("LC_STORAGE_CAP")
    return dict(at=now(), available_bytes=free, retained_logical_bytes=size,
                retained_allocated_upper_bound_bytes=allocated, retained_cap_metric="allocated_upper_bound",
                reclaimed_bytes=0, new_backups_environments_worktrees=0)


def compact_completed(folder):
    """Preserve completed owned outputs in place; never compact live/old inputs."""
    folder = Path(folder).resolve()
    if not folder.is_relative_to(HERE / "episodes"):
        raise ValueError("OWNED_COMPLETED_OUTPUT_REQUIRED")
    compressor = Path("/Users/depengsu/.local/share/bf-agent-runtime/maintenance-tools/applesauce-v0.5.30/applesauce")
    if bind(compressor)["sha256"] != "930a613509fa1db336f3810a59c7c1747d2241630ebac8629bef651896ff0a8b":
        raise ValueError("PINNED_COMPRESSOR_CHANGED")
    for name in ("raw.json", "public-result.json"):
        path = folder / name
        before = path.lstat()
        if before.st_size < 1000000 or before.st_flags & 0x20:
            continue
        if (not stat_module.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_flags & 0x40000000 or path.is_symlink()):
            raise ValueError("RESIDENT_SINGLE_LINK_COMPLETED_OUTPUT_REQUIRED")
        opened = subprocess.run(["lsof", "-nP", str(path)], capture_output=True, text=True, timeout=15)
        if opened.returncode != 1 or opened.stdout.strip():
            raise ValueError("COMPLETED_OUTPUT_OPEN_OR_HANDLE_CHECK_FAILED")
        original = bind(path)
        subprocess.run([str(compressor), "compress", "--verify", "--quiet", str(path)],
                       check=True, capture_output=True, timeout=120)
        after = path.lstat()
        if (bind(path) != original or
                (before.st_size, before.st_mode, before.st_uid, before.st_gid, before.st_mtime_ns) !=
                (after.st_size, after.st_mode, after.st_uid, after.st_gid, after.st_mtime_ns)):
            raise ValueError("COMPLETED_COMPACTION_READBACK_STOP")
        with (HERE / "completed-compaction.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(at=now(), original=original, full_readback_equal=True,
                allocated_before=before.st_blocks*512, allocated_after=after.st_blocks*512,
                persistent_copies=0)) + "\n")


def validate(protocol, **unused):
    for path, expected in protocol["source_bindings"].items():
        if bind(path)["sha256"] != expected:
            raise ValueError("FROZEN_DIRECT_SOURCE_CHANGED:" + path)
    if host.provider_snapshot()["historical_unknown_sha256"] != protocol["provider_before"]["historical_unknown_sha256"]:
        raise ValueError("R11_ORIGINAL_ROW_CHANGED")
    for ref in protocol["public_bindings"].values():
        checked(ref)
    for entry in protocol["tasks"] + protocol["training_tasks"]:
        for key in ("task", "initial_public_result", "lc_public", "lc_host_task"):
            if key in entry:
                checked(entry[key])


def configure(protocol, formation=False):
    limits = FORMATION if formation else SOLVE
    legacy.HERE, legacy.OUT, legacy.PACKAGE, legacy.PROTOCOL = HERE, OUT, PACKAGE, PROTOCOL
    legacy.LIMITS, legacy.TOTAL, legacy.PLAN = limits, TOTAL, PLAN
    legacy.capacity, legacy.validate = capacity, validate
    legacy.configure(protocol)
    # Reuse the already registered, tool-free SDK adaptation. No new runtime copy.
    p.APP = BASE / "f1-conditional-learning/shared/runtime"
    host.LIMITS = limits
    return limits


def task(entry):
    return checked(entry["task"])


def lc_context(entry):
    return {"public": checked(entry["lc_public"]), "host_task": checked(entry["lc_host_task"])} if entry["world"] == "LC-PV" else None


def sources(entry):
    return adapter.source_identity()["lc" if entry["world"] == "LC-PV" else "door"]


def cache_key(entry, design, dt=None):
    t = task(entry)
    return identity({"task": t, "design": design, "dt_s": t["integration"]["dt_s"] if dt is None else dt,
                     "consumer": sources(entry), "lc_inputs": lc_context(entry)})


def execute_child(path):
    job = read(path)
    entry, t = job["entry"], task(job["entry"])
    result = adapter.execute(t, job["design"], job["problem"], job["decision"], job["output_dir"],
                            task_resolver=lambda ident: deepcopy(t) if ident == t["task_id"] else None,
                            lc_context=lc_context(entry))
    print(json.dumps({"task_id": t["task_id"], "public_check": result["public_check"]}), flush=True)


def full_execute(entry, state, decision, folder, cache, category):
    t = task(entry)
    actual = common_contract_check(state, decision["actual_input"], {"remaining_actions": 1})
    design = {**deepcopy(state["design"]), **actual.get("design_patch", {})}
    problem = {**deepcopy(state["problem"]), **actual.get("problem_patch", {})}
    adapter.validate_design(t, design)
    key = cache_key(entry, design, actual.get("dt_s"))
    ledger = read(HERE / "resource-ledger.json")
    row = dict(at=now(), category=category, cache_key=key, task_id=t["task_id"],
               decision=deepcopy(decision), reused=key in cache, new_full_dynamic_inputs=0, wall_s=0)
    if actual["operation"] in {"select", "report"}:
        public = adapter.execute(t, state["design"], state["problem"], decision, folder,
                                 task_resolver=lambda ident: deepcopy(t) if ident == t["task_id"] else None,
                                 lc_context=lc_context(entry))
        if public.get("execution_status") != "NO_EXECUTION":
            raise ValueError("NONEXECUTION_CONTRACT_BINDING_STOP")
        row.update(reused=False, execution_status="NO_EXECUTION", public_result=bind(folder / "public-result.json"))
        ledger["attempts"].append(row)
        save(folder / "readback.json", row)
        save(HERE / "resource-ledger.json", ledger)
        return public, row, folder
    if key in cache:
        original = Path(cache[key])
        public = read(original / "public-result.json")
        public["problem"] = problem
        public["usage"] = dict(paid_model_requests=0, numerical_inputs=0, reused=True, wall_s=0)
        folder.mkdir(parents=True, exist_ok=False)
        save(folder / "reuse.json", {"original": bind(original / "public-result.json"), "cache_key": key, "current_problem": problem})
        ledger["cache_reuses"] += 1
    else:
        capacity()
        if ledger["full_dynamic_inputs"] >= 50 or ledger["full_dynamic_wall_s"] >= 5880:
            raise ValueError("LC_COMPLETE_INPUT_OR_WALL_CAP")
        ledger["full_dynamic_inputs"] += 1
        row["new_full_dynamic_inputs"] = 1
        save(HERE / "resource-ledger.json", ledger)
        input_path = folder.parent / (folder.name + "-dispatch.json")
        save(input_path, dict(entry=entry, design=state["design"], problem=state["problem"], decision=decision, output_dir=str(folder)))
        started = time.monotonic()
        proc = subprocess.Popen([sys.executable, "-B", str(HERE / "run_lc_learning.py"), "_execute", str(input_path)],
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
            row["error"] = "FULL_DYNAMIC_TIMEOUT"
        row["wall_s"] = time.monotonic() - started
        ledger["full_dynamic_wall_s"] += row["wall_s"]
        if proc.returncode or row.get("error"):
            row.update(exit_code=proc.returncode, stderr_tail=stderr[-4000:])
            ledger["attempts"].append(row)
            save(HERE / "resource-ledger.json", ledger)
            raise ValueError(row.get("error", "FULL_DYNAMIC_ERROR:" + stderr[-1500:]))
        original = folder
        public = read(folder / "public-result.json")
        cache[key] = str(folder)
    raw, evaluation = read(original / "raw.json"), read(original / "assessment.json")
    if (identity({k: v for k, v in raw.items() if k != "result_sha256"}) != raw["result_sha256"]
            or public["result_sha256"] != raw["result_sha256"] or public["design"] != design
            or public["task_sha256"] != identity(t) or evaluation["verdict"] != public["public_check"]["verdict"]):
        raise ValueError("COMPLETE_RESULT_BINDING_STOP")
    row.update(public_result=bind(original / "public-result.json"), raw=bind(original / "raw.json"),
               assessment=bind(original / "assessment.json"), public_check=public["public_check"], model_valid=public["model_valid"])
    ledger["candidate_evaluations"] += 1
    ledger["attempts"].append(row)
    save(folder / "readback.json", row)
    save(HERE / "resource-ledger.json", ledger)
    if not row["reused"]:
        compact_completed(original)
    return public, row, original


@contextmanager
def runtime_scope():
    with p.dbconnect() as db:
        if db.execute("SELECT 1 FROM research_model_owners WHERE protocol=?", (PACKAGE,)).fetchone():
            raise ValueError("PACKAGE_ALREADY_DISPATCHED_NO_RETRY")
        previous = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        previous = previous["value"] if previous else None
        db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps("per-owner"),))
    save(HERE / "runtime-open.json", dict(at=now(), prior_scope=previous, study_usd=50, owners_max=8))
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
            owners = [row[0] for row in db.execute("SELECT owner FROM research_model_owners WHERE protocol=?", (PACKAGE,))]
            for owner in owners:
                db.execute("UPDATE grants SET expires=? WHERE owner=?", (time.time(), owner))
                db.execute("DELETE FROM principals WHERE owner=?", (owner,))
                db.execute("UPDATE conversations SET status='IDLE',updated=? WHERE id=?", (time.time(), owner))
            db.execute("UPDATE research_model_studies SET expires=? WHERE protocol=?", (time.time(), PACKAGE))
        save(HERE / "runtime-closeout.json", dict(at=now(), scope_restored=previous, owners=owners,
                                                 provider_after=host.provider_snapshot(), history_rows_deleted=0))


class LCEpisode(legacy.LearningEpisode):
    def __init__(self, ident, t, condition, protocol, cache, role):
        self.limits = configure(protocol, role == "formation")
        super().__init__(ident, t, condition, protocol, cache, role, None)
        self.current_solver = None
        save(self.root / "owner.json", dict(owner=self.owner, episode=ident, finite_usd=self.limits["usd"],
             grant_wall_s=self.limits["wall_s"], no_unbounded_authorization=True, role=role))

    def ready(self, paid=False):
        if self.fatal:
            raise ValueError(self.fatal)
        b = self.budget()
        capacity()
        if b["wall_s"] >= self.limits["wall_s"]:
            raise ValueError("EPISODE_WALL_CAP")
        if sum(max(4096, x.stat().st_blocks * 512) for x in self.root.rglob("*") if x.is_file()) >= self.limits["bytes"]:
            raise ValueError("EPISODE_STORAGE_CAP")
        with p.dbconnect() as db:
            if new_batch_usage_blockers(db, self.owner):
                self.fatal = "NEW_USAGE_UNKNOWN_STOP"
                raise ValueError(self.fatal)
            rows = db.execute("SELECT mr.charged FROM model_requests mr JOIN research_model_owners ro ON ro.owner=mr.owner WHERE ro.protocol=?", (PACKAGE,)).fetchall()
        if self.tools > self.limits["tool_calls"]:
            raise ValueError("COMBINED_TOOL_CAP")
        if paid and (b["model_requests"] >= self.limits["model_requests"] or b["output_tokens"] >= self.limits["generated_tokens"]
                     or b["spent_usd"] + .19 > self.limits["usd"] or len(rows) >= 120 or sum(x[0] or 0 for x in rows) + .19 > 50):
            raise ValueError("FINITE_MODEL_CAP")
        return b

    def snapshot(self):
        b = self.ready()
        return {"provider_requests_remaining": self.limits["model_requests"] - b["model_requests"],
                "tool_calls_remaining": self.limits["tool_calls"] - self.tools,
                "new_numerical_inputs_remaining": max(0, self.limits["numerical_inputs"] - self.evaluations),
                "reserve_usd_remaining": self.limits["usd"] - b["spent_usd"],
                "wall_s_remaining": self.limits["wall_s"] - b["wall_s"],
                "output_tokens_remaining": self.limits["generated_tokens"] - b["output_tokens"]}

    def start_server(self):
        owner = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                try:
                    owner.dispatch_stage = "TRUSTED_LOCAL_PREFLIGHT"
                    if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != "Bearer " + owner.access_token:
                        raise ValueError("BROKER_ROUTE_OR_AUTH_DENIED")
                    length = int(self.headers.get("Content-Length", "0"))
                    owner.actual_wire_bytes = length
                    if not 0 < length <= 400000:
                        raise ValueError("BODY_CAP")
                    budget = owner.ready(paid=True)
                    grant = min(owner.callback_output_cap, p.output_allowance(budget["output_tokens"], owner.limits))
                    body = p.validate_wire(json.loads(self.rfile.read(length)), grant)
                    if body["max_tokens"] != owner.callback_output_cap or owner.call_relays >= 1:
                        raise ValueError("SINGLE_OUTPUT_GRANT_OR_ONE_CALL_BOUNDARY")
                    owner.call_relays += 1
                    owner.model_calls += 1
                    save(owner.root / "callbacks" / f"{owner.callback_index:02d}" / "wire-public.json", body)
                    owner.dispatch_stage = "FORWARD_ATTEMPT_STARTED"
                    request = urllib.request.Request(p.SERVICE + self.path, data=p.encoded(body),
                        headers={"Authorization": "Bearer " + owner.token, "Content-Type": "application/json"})
                    deadline = max(1, owner.limits["wall_s"] - (time.monotonic() - owner.started))
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=min(310, deadline)) as response:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.end_headers()
                        for line in response:
                            if line.startswith(b"data:") and line.strip() != b"data: [DONE]":
                                data = json.loads(line[5:])
                                if data.get("model") and data["model"] != "deepseek-flash":
                                    owner.fatal = "RESPONSE_MODEL_MISMATCH"
                                    raise ValueError(owner.fatal)
                            self.wfile.write(line)
                            self.wfile.flush()
                        owner.dispatch_stage = "FORWARDED_RESPONSE_COMPLETE"
                except Exception as exc:
                    owner.relay_error = type(exc).__name__ + ":" + str(exc)[:400]
                    try:
                        self.send_error(400, owner.relay_error)
                    except OSError:
                        pass
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def paid_callback(self, request):
        budget = self.ready(paid=True)
        before = p.ledger(p.DATABASE, self.owner)
        self.callback_output_cap = request["max_output_tokens"]
        if not 1 <= self.callback_output_cap <= p.output_allowance(budget["output_tokens"], self.limits):
            raise ValueError("CALLBACK_OUTPUT_GRANT_INVALID")
        self.callback_index = 1 + len(list((self.root / "callbacks").glob("*"))) if (self.root / "callbacks").exists() else 1
        folder = self.root / "callbacks" / f"{self.callback_index:02d}"
        folder.mkdir(parents=True, exist_ok=False)
        self.call_relays, self.relay_error, self.actual_wire_bytes = 0, None, None
        self.dispatch_stage = "TRUSTED_LOCAL_PREFLIGHT"
        payload = p.callback_payload(request, self.callback_output_cap)
        save(folder / "input-public.json", payload)
        if len(p.encoded(payload)) > 240000:
            raise ValueError("LOCAL_PUBLIC_PAYLOAD_CAP_PRE_FORWARD")
        config = dict(sdk_entry=str(p.SDK), workspace=str(folder / "participant"),
                      service="http://127.0.0.1:" + str(self.server.server_port), token=self.access_token, **payload)
        with (folder / "pi-public.jsonl").open("w") as stdout, (folder / "stderr.log").open("w") as stderr:
            proc = subprocess.Popen(["/opt/homebrew/bin/node", str(p.APP / "scripts/pqe_pi_callback.mjs")],
                cwd=folder, env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin", "LANG": "en_US.UTF-8"},
                stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                proc.communicate(p.encoded(config) + b"\n", timeout=max(1, self.limits["wall_s"] - (time.monotonic() - self.started)))
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                self.fatal = "EPISODE_WALL_CAP"
        after = p.ledger(p.DATABASE, self.owner)
        old = {x["id"] for x in before["rows"]}
        rows = [x for x in after["rows"] if x["id"] not in old]
        settled = len(rows) == 1 and rows[0]["status"] == "SETTLED" and bool(rows[0]["usage"])
        usage = dict(status="UNKNOWN", model_identity=p.MODEL_IDENTITY, request_ids=[x["id"] for x in rows])
        if settled:
            raw = json.loads(rows[0]["usage"])
            usage.update(status="KNOWN", cost=rows[0]["charged"], input_tokens=raw["prompt_tokens"], output_tokens=raw["completion_tokens"])
            if usage["output_tokens"] > self.callback_output_cap or budget["output_tokens"] + usage["output_tokens"] > self.limits["generated_tokens"]:
                self.fatal = "PROVIDER_OUTPUT_CAP_EXCEEDED"
        elif rows or self.call_relays:
            self.fatal = "PROVIDER_USAGE_NOT_SETTLED"
        else:
            usage["status"] = "NOT_DISPATCHED"
        records = [json.loads(line) for line in (folder / "pi-public.jsonl").read_text().splitlines() if line.strip()]
        loaded = [x for x in records if x.get("type") == "pqe_pi_loaded"]
        answers = [x for x in records if x.get("type") == "assistant_public"]
        answer, error, status = dict(status="INVALID_PLANNER_OUTPUT"), self.relay_error, "COMPLETE"
        try:
            if proc.returncode or len(loaded) != 1 or loaded[0]["tools"] or loaded[0]["history_messages"]:
                raise ValueError("PI_PROCESS_OR_CONTEXT_BOUNDARY")
            if len(answers) != 1 or answers[0].get("stopReason") != "stop" or any(x["type"] != "text" for x in answers[0]["content"]):
                raise ValueError("PI_STOP_OR_TOOL_BOUNDARY")
            text = "".join(x["text"] for x in answers[0]["content"])
            try:
                answer = json.loads(text)
            except json.JSONDecodeError as exc:
                # Feedback to the SAME formation episode; no host extraction or repair.
                answer = {"status": "JSON_SYNTAX_ERROR", "syntax_error": {"line": exc.lineno, "column": exc.colno, "position": exc.pos},
                          "original_output_sha256": hashlib.sha256(text.encode()).hexdigest()}
            if not isinstance(answer, dict):
                raise ValueError("JSON_OBJECT_REQUIRED")
        except (ValueError, KeyError) as exc:
            error, status = str(exc), "PARSE_OR_TRANSPORT_ERROR"
        if self.relay_error or not settled:
            status = "PARSE_OR_TRANSPORT_ERROR" if usage["status"] != "NOT_DISPATCHED" else "LOCAL_TOOL_NOT_EXECUTED"
        result = dict(payload=answer, usage=usage, request_ids=usage["request_ids"], provider_status=status, error=error,
                      granted_max_output_tokens=self.callback_output_cap, output_budget_before=budget["output_tokens"],
                      output_budget_after=self.budget()["output_tokens"], dispatch_facts={"stage": self.dispatch_stage,
                      "forwarded": bool(self.call_relays), "actual_wire_bytes": self.actual_wire_bytes, "provider_rows": len(rows)})
        save(folder / "callback-result.json", result)
        print(json.dumps(dict(event="LC_MODEL_CALLBACK", episode=self.ident, site=request.get("site"), usage=usage["status"], error=error)), flush=True)
        return result

    def planner(self, request):
        try:
            validate(self.protocol)
        except Exception as exc:
            self.fatal = "FROZEN_VALIDATION_STOP:" + str(exc)
            raise
        context, usage, ids, calls = deepcopy(request), dict(cost=0, input_tokens=0, output_tokens=0), [], []
        cap = request["max_output_tokens"]
        while True:
            remaining = cap - usage["output_tokens"]
            if remaining <= 0:
                response = dict(payload={"status": "OUTPUT_TOKEN_BUDGET_EXHAUSTED"}, provider_status="COMPLETE")
                break
            body = self.objects.project(deepcopy(context))
            body.update(max_output_tokens=min(remaining, p.output_allowance(self.budget()["output_tokens"], self.limits)),
                        shared_public_tools=deepcopy(legacy.SERVICE_TOOLS), shared_public_catalog=self.public_catalog)
            if self.role == "formation" and ids:
                self.driver._consume_unit("PUBLIC_TOOL_CONTINUATION_CALLBACK")
            response = self.paid_callback(body)
            new_usage = response.get("usage", {})
            if new_usage.get("status") != "KNOWN":
                return response
            for key in usage:
                usage[key] += new_usage[key]
            ids += response.get("request_ids", [])
            payload = response.get("payload", {})
            if response.get("provider_status") != "COMPLETE" or payload.get("status") != "PUBLIC_TOOLS":
                break
            requests = payload.get("tool_calls")
            if not isinstance(requests, list) or not 1 <= len(requests) <= self.limits["tool_calls"] - self.tools:
                response["payload"] = {"status": "INVALID_PUBLIC_TOOL_REQUEST"}
                break
            results = []
            for call in requests:
                if self.role == "formation":
                    self.driver._consume_unit("PUBLIC_TOOL_REQUEST", name=call.get("name"))
                # Full training is an explicit counted host callback, never a native tool.
                if call.get("name") == "public_object":
                    try:
                        result = dict(id=call.get("id"), status="OK", result=self.public_read(call.get("arguments", {})))
                    except Exception as exc:
                        result = dict(id=call.get("id"), status="TOOL_ERROR", error=str(exc))
                elif self.current_solver is not None:
                    cheap = call.get("name") in {"predict_candidate", "engineering_relations"}
                    resource = read(HERE / "resource-ledger.json")
                    if cheap:
                        if self.cheap_calls >= 12 or resource.get("cheap_checks", 0) + resource.get("cheap_screen_reserved", 0) >= 96:
                            raise ValueError("FINITE_CHEAP_CAP")
                        self.cheap_calls += 1
                        resource["cheap_checks"] = resource.get("cheap_checks", 0) + 1
                        save(HERE / "resource-ledger.json", resource)
                    self.public_tools._budget({"analytic_scores_left": 12 - self.cheap_calls + int(cheap),
                                               "public_tool_calls_left": self.limits["tool_calls"] - self.tools})
                    result = self.public_tools._tool(self.current_solver.state, call)
                else:
                    result = dict(id=call.get("id"), status="TOOL_ERROR", error="Formation public paging only; full science runs through the counted training callback.")
                self.tools += 1
                results.append(result)
            calls.append(dict(requests=requests, results=results))
            save(self.root / "public-tool-log.json", calls)
            context = {**request, "public_tool_results": calls}
        response["usage"] = dict(status="KNOWN", model_identity=p.MODEL_IDENTITY, **usage, request_ids=ids)
        response["request_ids"] = ids
        return response

    def consume_one(self, entry, driver, folder):
        self.ready()
        if self.tools >= self.limits["tool_calls"] or self.evaluations >= self.limits["candidates"]:
            raise ValueError("EPISODE_ACTION_CAP")
        self.tools += 1
        self.evaluations += 1
        before = read(HERE / "resource-ledger.json")["full_dynamic_inputs"]
        try:
            public, receipt, original = full_execute(entry, {"task": driver.state["task"], "design": driver.state["design"], "problem": driver.state["problem"]},
                                                     driver.pending, folder, self.cache, self.ident)
        except Exception as exc:
            if any(token in str(exc) for token in ("BINDING_STOP", "READBACK_STOP", "COMPRESSOR_CHANGED")):
                self.fatal = str(exc)
            raise
        finally:
            self.numerical += read(HERE / "resource-ledger.json")["full_dynamic_inputs"] - before
        oid = self.objects.register(read(original / "public-result.json"), path=original / "public-result.json")
        self.objects.save_index()
        if public.get("execution_status") != "NO_EXECUTION":
            self.last_full = public
        row = dict(number=len(self.actions) + 1, task_id=task(entry)["task_id"], actual_input=deepcopy(driver.pending["actual_input"]),
                   public_check=public["public_check"], public_object_ref=oid, receipt=receipt)
        self.actions.append(row)
        save(self.root / "executed-actions.json", self.actions)
        return public, oid, receipt
