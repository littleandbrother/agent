#!/usr/bin/env python3
"""One preregistered Phase 4 episode over the existing SDK and paid gateway."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import urllib.request

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[2]
PLAN = ROOT / "docs/research/phase-plan-20261019/phase4"
OUT = Path.home() / ".local/share/bf-phase4-20261020"
PROFILE = Path.home() / ".local/share/bf-campaign-20261019-s0/profile.json"
HIST = Path.home() / ".local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001"
HARNESS = Path.home() / ".local/share/bf-phase1-20261020/a/ar-service/pi-episode-001/harness"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.campaign20261019.phase1 import (
    BFPhaseGateway, digest, encoded, file_hash, ledger, output_bytes, seal, tool_definition,
)
from bfworld.agentlab.campaign20261019.phase4 import (
    DesignHost, ProposalHost, ResponseStore, bindings_match, bounded_allowance,
    executor_admission, load, require_final_freeze, used_totals,
)
from jsonschema import ValidationError


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def configure():
    profile = load(PROFILE)
    for key, value in profile["paths"].items():
        os.environ["BF_" + key] = value
    os.environ.update(BF_RUNTIME_ROOT=profile["runtime_root"], BF_RUNTIME_CONFIG=profile["configuration"],
                      BF_DEVELOPMENT_PROFILE=str(PROFILE), PYTHONDONTWRITEBYTECODE="1",
                      PI_CODING_AGENT_DIR=str(Path(profile["home"]) / "pi-config"))
    return profile


def results():
    return [load(q) for q in sorted((OUT / "episodes").glob("*/episode-result.json"))]


def formation_share(spec):
    if spec.get("arm") != "G1":
        return {"requests": 0, "wall_s": 0, "settled_upper_usd": 0}
    formation = load(OUT / "G1-formation-accounting.json")
    return formation["allocations"][spec["lineage"] - 1]


class Gateway(BFPhaseGateway):
    def ready(self, *, paid=False):
        super().ready(paid=paid)
        if not paid:
            return True
        state = load(PLAN.parent / "phase-state.json")
        if state.get("current_phase") != 4 or not state.get("paid_dispatch_allowed"):
            self.stop("PHASE4_DISPATCH_HELD")
        plan = load(PLAN / "protocol.json")
        closed = results()
        totals = used_totals(closed)
        current = ledger(self.protocol["provider_database"], self.protocol["owner"])
        own = {"requests": current["requests"], "wall_s": time.time() - self.started,
               "settled_upper_usd": current["settled_charge_upper_bound_usd"]}
        if totals["requests"] + own["requests"] >= 860:
            self.stop("PHASE4_REQUEST_CAP")
        if totals["wall_s"] + own["wall_s"] >= 54400:
            self.stop("PHASE4_WALL_CAP")
        # A conservative one-dollar reservation covers the pinned byte/token caps.
        if totals["settled_upper_usd"] + own["settled_upper_usd"] + 1 > 100:
            self.stop("PHASE4_DOLLAR_RESERVE")
        if output_bytes(OUT) >= 500_000_000:
            self.stop("PHASE4_RETAINED_OUTPUT_CAP")
        home = Path(self.protocol["provider_database"]).parents[1]
        if output_bytes(home) - plan["provider_home_initial_bytes"] >= 150_000_000:
            self.stop("PROVIDER_WORKBENCH_GROWTH_CAP")
        spec = self.protocol["spec"]
        if spec.get("arm_id"):
            related = used_totals(x for x in closed if x["spec"].get("arm_id") == spec["arm_id"])
            allocation = formation_share(spec)
            if related["settled_upper_usd"] + allocation["settled_upper_usd"] + own["settled_upper_usd"] + 1 > 10:
                self.stop("LINEAGE_ARM_DOLLAR_RESERVE")
        return True

    def tool(self, body):
        with self.lock:
            self.ready()
            if self.tool_calls >= self.protocol["limits"]["tool_calls"]:
                raise ValueError("EPISODE_TOOL_LIMIT")
            self.tool_calls += 1
            self.event("tool_started", {"number": self.tool_calls, "input": body})
            try:
                self.validator.validate(body)
                value = self.handler(body)
                if len(encoded(value)) > self.protocol["limits"]["tool_response_bytes"]:
                    raise ValueError("TOOL_RESPONSE_BOUND")
                self.event("tool_completed", {"number": self.tool_calls, "output": value})
                return value
            except Exception as error:
                self.event("tool_failed", {"number": self.tool_calls,
                                           "error": type(error).__name__ + ": " + str(error)[:1500]})
                if isinstance(error, ValidationError):
                    self.syntax_rejections = getattr(self, "syntax_rejections", 0) + 1
                    if self.syntax_rejections > 2:
                        self.stop("SYNTAX_REJECTION_CAP")
                raise


def definition(kind, proposal_schema=None, candidate_schema=None):
    actions = ["inspect", "acquire", "check", "submit"] if kind == "D" else ["inspect", "acquire", "propose", "submit"]
    properties = {"action": {"enum": actions}, "source_id": {"type": "string"},
                  "reason": {"type": "string", "maxLength": 4000}}
    conditions = [{"if": {"properties": {"action": {"const": "acquire"}}}, "then": {"required": ["source_id"]}}]
    if kind == "D":
        properties.update(candidate=candidate_schema, service_judgment={"enum": ["PASS", "FAIL", "UNKNOWN"]})
        conditions += [{"if": {"properties": {"action": {"enum": ["check", "submit"]}}}, "then": {"required": ["candidate"]}},
                       {"if": {"properties": {"action": {"const": "submit"}}}, "then": {"required": ["service_judgment"]}}]
    else:
        properties["proposal"] = proposal_schema
        conditions += [{"if": {"properties": {"action": {"enum": ["propose", "submit"]}}}, "then": {"required": ["proposal"]}}]
    return tool_definition("bf_phase4", "Read frozen BF facts and submit only the assigned artifact. Independent qualification and complete service are host-side. No file, shell or native access.",
                           {"type": "object", "additionalProperties": False, "required": ["action"],
                            "properties": properties, "allOf": conditions})


def run_episode(spec, payload, *, engine=None, proposal_schema=None, normalize=None):
    """The registered driver supplies only frozen/actual parent payloads."""
    start = time.monotonic()
    state = load(PLAN.parent / "phase-state.json")
    if state["current_phase"] != 4 or not state.get("paid_dispatch_allowed"):
        raise ValueError("PHASE4_NOT_ENABLED")
    plan = load(PLAN / "protocol.json")
    if spec not in plan["episodes"]:
        raise ValueError("UNREGISTERED_EPISODE")
    holders = executor_admission(load(PLAN / "idle-slots.json"), time.time())
    if shutil.disk_usage(ROOT).free < 10_900_000_000:
        raise ValueError("STORAGE_RESERVE")
    selected = load(OUT / "selected-methods.json") if (OUT / "selected-methods.json").exists() else {}
    freeze = load(OUT / "final-selection-freeze.json") if (OUT / "final-selection-freeze.json").exists() else None
    require_final_freeze(spec, freeze, selected)
    bindings_match(plan["bound_files"])
    component_path = PLAN / ("component-o-freeze.json" if spec["stage"] == "O-transfer" else "component-method-freeze.json")
    component = load(component_path)
    bindings_match(component["bound_files"])
    profile = configure()
    database = Path(profile["home"]) / "state/workbench.sqlite"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("SELECT count(*) FROM model_requests WHERE status NOT IN ('SETTLED','NOT_SENT')").fetchone()[0]:
            raise ValueError("PROVIDER_USAGE_UNRESOLVED")
    request_cap, wall_cap = bounded_allowance(spec, results(), formation_share(spec))
    built = load(HARNESS / "manifest.json")
    if file_hash(HARNESS / "dist/phase1/episode.js") != built["compiled_sha256"]:
        raise ValueError("EXISTING_SDK_IDENTITY_DRIFT")
    if spec["kind"] == "D":
        if engine is None:
            raise ValueError("FROZEN_ENGINE_REQUIRED")
        tool = definition("D", candidate_schema=engine.inspect(spec["world"])["candidate_schema"])
    else:
        if not callable(normalize) or not proposal_schema:
            raise ValueError("PROPOSAL_CONTRACT_REQUIRED")
        tool = definition(spec["kind"], proposal_schema=proposal_schema)
    runner = load_module("phase4_existing_sdk", APP / "scripts/campaign_phase1.py")
    root = OUT / "episodes" / spec["id"]
    if root.exists():
        raise FileExistsError("ACTUAL_ATTEMPT_NO_AUTOMATIC_RETRY")
    # Every precondition above is checked before claiming a real participant.
    root.mkdir(parents=True)
    seal(root / "attempt.json", {"spec": spec, "protocol_sha256": file_hash(PLAN / "protocol.json"),
                                "started_unix": time.time(), "automatic_retry": False})
    seal(root / "participant-payload.json", payload)
    service = "http://127.0.0.1:8980"
    operator = (Path(profile["home"]) / "state/operator.token").read_text().strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api(path, body):
        request = urllib.request.Request(service + path, data=encoded(body),
                    headers={"Authorization": "Bearer " + operator, "Content-Type": "application/json"})
        with opener.open(request, timeout=30) as response:
            return json.load(response)
    owner, token, gateway = None, None, None
    result = {"episode": spec["id"], "spec": spec, "status": "START_FAILURE", "native_dispatches": 0,
              "initial_cache_sha256": file_hash(OUT / "initial-cache.json")}
    try:
        owner = api("/api/conversations", {"text": payload["goal"], "operation_id": spec["id"], "defer_dispatch": True})["id"]
        seal(root / "owner.json", {"owner": owner, "episode": spec["id"], "fresh_model_context": True})
        authority = api("/api/design-lab", {"action": "method_authorize", "session_id": owner,
                 "task_id": "method-study-" + spec["id"], "wall_authorization_text": "持续运行 不设置时间限制",
                 "model_profile": "engineering-reasoning-compact-v2"})
        token = authority.pop("participant_token")
        seal(root / "authority.json", authority)
        bound = {**plan["bound_files"], **component["bound_files"],
                 str(PLAN / "protocol.json"): file_hash(PLAN / "protocol.json"),
                 str(component_path): file_hash(component_path),
                 str(root / "participant-payload.json"): file_hash(root / "participant-payload.json")}
        for path in payload.get("parent_files", []):
            bound[path] = file_hash(path)
        if spec["stage"] == "final":
            bound[str(OUT / "final-selection-freeze.json")] = file_hash(OUT / "final-selection-freeze.json")
            bound[str(OUT / "selected-methods.json")] = file_hash(OUT / "selected-methods.json")
        protocol = {"schema_version": "bf-phase4-actual-episode-v1", "id": spec["id"], "spec": spec,
                    "mode": "public-development", "partition": spec["stage"], "owner": owner,
                    "tool": tool, "harness": str(HARNESS), "output_root": str(root),
                    "provider_service": service, "provider_database": str(database),
                    "allowed_reported_models": ["deepseek-flash"], "identity_scope": "Provider alias only; pinned weights UNKNOWN",
                    "bound_files": bound, "candidate_fields": [], "candidate_actions": [],
                    "limits": {"model_requests": request_cap, "wall_seconds": wall_cap, "candidates": 2,
                               "reserve_bytes": 10_000_000_000, "peak_remaining_bytes": 900_000_000,
                               "output_bytes": 100_000_000, "tool_calls": 40, "tool_response_bytes": 96_000,
                               "model_request_bytes": 2_000_000, "model_response_bytes": 64_000_000,
                               "max_output_tokens": 32768}, "automatic_retry": False, "native_dispatches": 0}
        seal(root / "protocol.json", protocol)
        result.update(owner=owner, protocol_sha256=digest(protocol))
        lease = root / "slot-lease.json"
        seal(lease, {"status": "GRANTED", "episode": spec["id"], "expires": time.time() + wall_cap,
                     "holders": holders, "other_executor_status": "idle"})
        if spec["kind"] == "D":
            store = ResponseStore(OUT, OUT / "initial-cache.json", spec["id"], engine, maximum=150)
            host = DesignHost(root / "scientific", store, spec["world"])
        else:
            host = ProposalHost(root / "scientific", spec["kind"], payload["facts"], proposal_schema, normalize)
        gateway = Gateway(protocol, root / "gateway", host, provider_token=token, lease_path=lease)
        result.update(runner.invoke(root, HARNESS, {"workspace": str(root / "participant"),
                     "service": gateway.start(), "token": gateway.token, "owner": owner,
                     "goal": payload["goal"], "instruction": payload["instruction"],
                     "episodeId": spec["id"], "tool": tool}, timeout=wall_cap))
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)[:2000]
    finally:
        if gateway:
            gateway.close()
        token = None
        result["wall_seconds_total"] = time.monotonic() - start
        account = ledger(database, owner) if owner else {
            "requests": 0, "unknown_or_missing_usage": [], "settled_charge_upper_bound_usd": 0,
            "rows": [], "scope": "No participant provider dispatch was invoked before owner allocation failed"}
        seal(root / "provider-costs.json", account)
        result["accounting"] = {k: v for k, v in account.items() if k != "rows"}
    try:
        result["trace_audit"] = runner.audit_participant(root, tool["name"])
        starts = [json.loads(line) for line in (root / "pi-public-trace.jsonl").read_text().splitlines()
                  if json.loads(line).get("type") == "bf_episode_loaded"]
        result["fresh_task_entry"] = len(starts) == 1 and starts[0].get("resume_messages") == 0
        result["reported_models"] = sorted(gateway.models_seen) if gateway else []
        submitted = root / "scientific/submission.json"
        accepted = (result.get("exit_code") == 0 and submitted.exists() and result["trace_audit"]["model_submitted"]
                    and result["fresh_task_entry"] and result["reported_models"]
                    and not account["unknown_or_missing_usage"] and not gateway.stopped)
        result["status"] = "ACTUAL_PROSPECTIVE_SUBMITTED" if accepted else "INCOMPLETE_OR_STOPPED"
        if accepted:
            result["external_result"] = load(submitted)
    except Exception as error:
        result["status"] = "TRACE_AUDIT_FAILED"
        result["trace_error"] = type(error).__name__ + ": " + str(error)[:1000]
    seal(root / "episode-result.json", result)
    print(json.dumps({"episode": spec["id"], "status": result["status"], "owner": owner,
                      "requests": account["requests"], "upper_usd": account["settled_charge_upper_bound_usd"],
                      "service": result.get("external_result", {}).get("execution", {}).get("complete_service"),
                      "wall_s": result["wall_seconds_total"]}, ensure_ascii=False), flush=True)
    if account["unknown_or_missing_usage"]:
        raise ValueError("NEW_USAGE_UNRESOLVED_STOP_DEPENDENT_EXECUTION")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true")
    args = parser.parse_args()
    if not args.describe:
        parser.error("Use the frozen phase4 driver; this module does not invent episode payloads.")
    print(json.dumps({"runner": "one exact registered episode", "automatic_retry": False,
                      "existing_environment_and_SDK": True, "paid_calls_in_describe": 0}))
