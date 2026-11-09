"""Minimal common budget/transport increment over the sealed LC execution host."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import importlib.util
import http.server
import json
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
OUT, BASE = HERE.parent, HERE.parent.parent
spec = importlib.util.spec_from_file_location("sealed_lc_execution_runtime", BASE / "lc-service-learning/s0/runtime.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
ROOT, APP = old.ROOT, old.APP
PKG = APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261024train"
PACKAGE = "BF-PQE-TRAINING-EXECUTION-20261024-001"
PROTOCOL = OUT / "shared/protocol.json"
p, host, legacy = old.p, old.host, old.legacy
read, save, bind, checked, identity, now = old.read, old.save, old.bind, old.checked, old.identity, old.now
task, lc_context, sources, cache_key = old.task, old.lc_context, old.sources, old.cache_key
adapter = old.adapter
SOLVE, FORMATION = deepcopy(old.SOLVE), deepcopy(old.FORMATION)
TOTAL = {**old.TOTAL, "numerical_inputs": 40}
PLAN = deepcopy(old.PLAN)
_configure, _full = old.configure, old.full_execute
capacity, validate, execute_child = old.capacity, old.validate, old.execute_child
runtime_scope = old.runtime_scope
for name in ("HERE", "OUT", "BASE", "PKG", "PACKAGE", "PROTOCOL", "SOLVE", "FORMATION", "TOTAL", "PLAN"):
    setattr(old, name, globals()[name])


def configure(protocol, formation=False):
    return _configure(protocol, formation)


def full_execute(entry, state, decision, folder, cache, category):
    actual = decision["actual_input"]
    design = {**deepcopy(state["design"]), **actual.get("design_patch", {})}
    if actual["operation"] not in {"select", "report"} and cache_key(entry, design, actual.get("dt_s")) not in cache:
        resource = read(HERE / "resource-ledger.json")
        if resource["full_dynamic_inputs"] >= 40 or resource["full_dynamic_wall_s"] >= 4680:
            raise ValueError("TRAINING_PACKAGE_COMPLETE_INPUT_OR_WALL_CAP")
    return _full(entry, state, decision, folder, cache, category)


old.configure, old.full_execute = configure, full_execute


class LCEpisode(old.LCEpisode):
    def __init__(self, *args, **kwargs):
        self.subscope = None
        super().__init__(*args, **kwargs)
        self.absolute_deadline = self.started + self.limits["wall_s"]
        self.nested_solves = []
        self.software_check = False

    def _remaining(self, budget):
        result = dict(provider_requests_remaining=self.limits["model_requests"] - budget["model_requests"],
            tool_calls_remaining=self.limits["tool_calls"] - self.tools,
            new_numerical_inputs_remaining=self.limits["numerical_inputs"] - self.numerical,
            reserve_usd_remaining=self.limits["usd"] - budget["spent_usd"],
            wall_s_remaining=self.absolute_deadline - time.monotonic(),
            output_tokens_remaining=self.limits["generated_tokens"] - budget["output_tokens"])
        if self.subscope is not None:
            sub = self.subscope
            used = dict(provider_requests_remaining=budget["model_requests"] - sub["base"]["model_requests"],
                tool_calls_remaining=self.tools - sub["base_tools"],
                new_numerical_inputs_remaining=self.numerical - sub["base_numerical"],
                reserve_usd_remaining=budget["spent_usd"] - sub["base"]["spent_usd"],
                wall_s_remaining=time.monotonic() - sub["started"],
                output_tokens_remaining=budget["output_tokens"] - sub["base"]["output_tokens"])
            names = {"provider_requests_remaining": "provider_requests", "tool_calls_remaining": "tool_calls",
                "new_numerical_inputs_remaining": "new_numerical_inputs", "reserve_usd_remaining": "reserve_usd",
                "wall_s_remaining": "wall_s", "output_tokens_remaining": "output_tokens_total"}
            result = {key: min(value, sub["limits"][names[key]] - used[key]) for key, value in result.items()}
        return {key: max(0, value) for key, value in result.items()}

    def ready(self, paid=False):
        budget = super().ready(paid=paid)
        if self.subscope is not None:
            remaining = self._remaining(budget)
            if remaining["wall_s_remaining"] <= 0:
                raise ValueError("NESTED_SOLVE_ABSOLUTE_DEADLINE")
            if paid and (remaining["provider_requests_remaining"] <= 0 or remaining["output_tokens_remaining"] <= 0
                         or remaining["reserve_usd_remaining"] < .19):
                raise ValueError("NESTED_SOLVE_FINITE_MODEL_CAP")
        return budget

    def snapshot(self):
        return self._remaining(self.ready())

    def consume_one(self, *args, **kwargs):
        remaining = self.snapshot()
        if remaining["wall_s_remaining"] < 120:
            raise ValueError("FULL_EXECUTION_DEADLINE_RESERVE_UNAVAILABLE")
        return super().consume_one(*args, **kwargs)

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
                    owner.ready(paid=True)
                    remaining = owner.snapshot()
                    grant = min(owner.callback_output_cap, remaining["output_tokens_remaining"])
                    body = p.validate_wire(json.loads(self.rfile.read(length)), grant)
                    if body["max_tokens"] != owner.callback_output_cap or owner.call_relays >= 1:
                        raise ValueError("SINGLE_OUTPUT_GRANT_OR_ONE_CALL_BOUNDARY")
                    owner.call_relays += 1
                    owner.model_calls += 1
                    save(owner.root / "callbacks" / f"{owner.callback_index:02d}" / "wire-public.json", body)
                    owner.dispatch_stage = "FORWARD_ATTEMPT_STARTED"
                    request = urllib.request.Request(p.SERVICE + self.path, data=p.encoded(body),
                        headers={"Authorization": "Bearer " + owner.token, "Content-Type": "application/json"})
                    deadline = time.monotonic() + remaining["wall_s_remaining"]
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,
                            timeout=max(1, min(310, remaining["wall_s_remaining"]))) as response:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.end_headers()
                        for line in response:
                            if time.monotonic() >= deadline:
                                raise ValueError("NESTED_OR_PARENT_ABSOLUTE_FORWARD_DEADLINE")
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

    @contextmanager
    def nested_solve(self, task_id, actions_max):
        if self.subscope is not None:
            raise ValueError("NESTED_RECURSION_NOT_AUTHORIZED")
        before = self.snapshot()
        reserve = (dict(requests=1, tools=1, usd=.19, output=65536, wall=60)
                   if self.role == "formation" else dict(requests=0, tools=0, usd=0, output=0, wall=0))
        limits = dict(provider_requests=int(min(12, before["provider_requests_remaining"] - reserve["requests"])),
            tool_calls=int(min(24, before["tool_calls_remaining"] - reserve["tools"])),
            new_numerical_inputs=int(min(actions_max, before["new_numerical_inputs_remaining"])),
            wall_s=min(900, before["wall_s_remaining"] - reserve["wall"]),
            output_tokens_per_request=65536,
            output_tokens_total=int(min(131072, before["output_tokens_remaining"] - reserve["output"])),
            reserve_usd=min(5, before["reserve_usd_remaining"] - reserve["usd"]))
        if any(value <= 0 for value in limits.values()) or limits["reserve_usd"] < .19:
            raise ValueError("INSUFFICIENT_NESTED_SOLVE_BUDGET_FEEDBACK_RESERVED")
        limits["output_tokens_per_request"] = min(65536, limits["output_tokens_total"])
        self.subscope = dict(task_id=task_id, started=time.monotonic(), base=self.budget(),
            base_tools=self.tools, base_numerical=self.numerical, limits=limits)
        receipt = dict(task_id=task_id, owner=self.owner, parent_absolute_deadline=self.absolute_deadline,
            before=before, limits=deepcopy(limits), revision_opportunity_reserved=reserve,
            same_owner_and_ledger=True)
        try:
            yield limits
        finally:
            receipt["subsolve_remaining_after"] = self._remaining(self.budget())
            self.subscope = None
            receipt["parent_remaining_after"] = self.snapshot()
            self.nested_solves.append(receipt)
            self.audit(self.root / "nested-solve-budgets.json", self.nested_solves)

    def planner(self, request):
        try:
            validate(self.protocol)
        except Exception as exc:
            self.fatal = "FROZEN_VALIDATION_STOP:" + str(exc)
            raise
        context, usage, ids, calls = deepcopy(request), dict(cost=0, input_tokens=0, output_tokens=0), [], []
        cap = request["max_output_tokens"]
        feedback = request.get("context", {}).get("revision_feedback", {}).get("actual_full_training")
        if (self.role == "formation" and not self.software_check and isinstance(feedback, dict)
                and feedback.get("full_inputs", 0) > 0 and not (HERE / "milestone-ready.json").exists()):
            save(HERE / "milestone-ready.json", dict(at=now(), episode=self.ident,
                code_to_actual_full_training_to_formation_feedback=True,
                training_full_inputs=feedback["full_inputs"], request_site=request.get("site"),
                feedback_sha256=identity(feedback), owner=self.owner))
        while True:
            remaining = min(cap - usage["output_tokens"], self.snapshot()["output_tokens_remaining"])
            if remaining <= 0:
                response = dict(payload={"status": "OUTPUT_TOKEN_BUDGET_EXHAUSTED"}, provider_status="COMPLETE")
                break
            complete = {**deepcopy(context), "max_output_tokens": min(remaining, 65536),
                "shared_public_tools": deepcopy(legacy.SERVICE_TOOLS), "shared_public_catalog": self.public_catalog}
            try:
                body = self.objects.project(complete)
                if len(p.encoded(p.callback_payload(body, body["max_output_tokens"]))) > 240000:
                    raise ValueError("LOCAL_PUBLIC_PAYLOAD_CAP_PRE_FORWARD")
            except Exception as exc:
                save(self.root / "local-planner-error.json", dict(error=str(exc), classification="LOCAL_TOOL_NOT_EXECUTED",
                    trusted_pre_forward=True, new_unsettled_provider_rows=0, known_prior_request_ids=ids))
                return dict(payload={"status": "TOOL_ERROR"}, provider_status="LOCAL_TOOL_NOT_EXECUTED", error=str(exc),
                    usage=dict(status="KNOWN" if ids else "NOT_DISPATCHED", model_identity=p.MODEL_IDENTITY, **usage), request_ids=ids)
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
            if not isinstance(requests, list) or not 1 <= len(requests) <= self.snapshot()["tool_calls_remaining"]:
                response["payload"] = {"status": "INVALID_PUBLIC_TOOL_REQUEST"}
                break
            results = []
            for call in requests:
                if self.role == "formation":
                    self.driver._consume_unit("PUBLIC_TOOL_REQUEST", name=call.get("name"))
                if call.get("name") == "public_object":
                    try:
                        result = dict(id=call.get("id"), status="OK", result=self.public_read(call.get("arguments", {})))
                    except Exception as exc:
                        result = dict(id=call.get("id"), status="TOOL_ERROR", error=str(exc))
                elif self.current_solver is not None:
                    cheap = call.get("name") in {"predict_candidate", "engineering_relations"}
                    resource = read(HERE / "resource-ledger.json")
                    if cheap:
                        if self.cheap_calls >= 12 or resource["cheap_checks"] + resource["cheap_screen_reserved"] >= 96:
                            raise ValueError("FINITE_CHEAP_CAP")
                        self.cheap_calls += 1
                        resource["cheap_checks"] += 1
                        save(HERE / "resource-ledger.json", resource)
                    self.public_tools._budget({"analytic_scores_left": 12 - self.cheap_calls + int(cheap),
                        "public_tool_calls_left": self.snapshot()["tool_calls_remaining"]})
                    result = self.public_tools._tool(self.current_solver.state, call)
                else:
                    result = dict(id=call.get("id"), status="TOOL_ERROR", error="Formation public paging only; counted host training executes full science.")
                self.tools += 1
                results.append(result)
            calls.append(dict(requests=requests, results=results))
            save(self.root / "public-tool-log.json", calls)
            context = {**request, "public_tool_results": calls}
        response["usage"] = dict(status="KNOWN", model_identity=p.MODEL_IDENTITY, **usage, request_ids=ids)
        response["request_ids"] = ids
        return response
