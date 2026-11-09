"""PQE Stage 1 methods: public-state decisions and externally screened programs.

No solver, provider, hidden evaluator or task-specific repair is imported here.
The code loader is a bounded, capability-reduced software-test host, NOT an OS
security sandbox. Model-authored code needs the owner's isolated host before
real formation. Fixture callbacks never constitute an Agent or learning run.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import sys
from typing import Callable
from .public_projection import project_result, project_embedded_results

SCHEMA = "pqe-methods-v1"
H_SITES = ("H-GEN", "H-RANK", "H-EXP", "H-UPDATE", "H-REFORM", "H-STOP")
G_SITES = ("G-EXTRACT", "G-ATTRIBUTE", "G-PROPOSE", "G-ALLOCATE")
FUNCTIONS = {s: s.lower().replace("-", "_") for s in H_SITES + G_SITES}
OPERATIONS = {"edit", "observe", "verify", "restructure", "report", "select", "refine"}
PROBLEM_FIELDS = {"active_variables", "groups", "fixed_choices", "assumptions", "local_objective"}
FIXED_OPERATION_ORDER = ("observe", "edit", "verify", "restructure", "refine", "select", "report")
UPDATE_FIELDS = {"hypotheses", "invalidated", "next_evidence", "strategy"}
TASK_FIELDS = {"schema_version", "task_id", "description", "service", "services",
               "design_domain", "components", "integration", "duration_s", "budget",
               "allowed_operations", "model_domain", "public_inputs", "initial", "motion",
               "sensor", "geometry", "gateway_windows", "material_sources"}
RESULT_FIELDS = {"schema_version", "execution_status", "model_valid", "domain_errors",
                 "design", "problem", "facts", "public_check", "usage", "task_id",
                 "task_sha256", "input_sha256", "result_sha256", "sources"}
EDIT_FIELDS = {"code", "prompts", "config", "applicability", "non_trigger_conditions"}
PATCH_FIELDS = {"parent_program", "parent_sha256", "target_sites", "source_incidents", "applicability",
                "non_trigger_conditions", "change", "predicted_behavior_change",
                "side_effects", "behavior_tests", "full_task_test_plan", "falsifier"}
PROTOCOLS = {
    "strong_generic": "Solve the full service task using all legal tools and design or problem revisions. Plan, inspect feedback, and choose the most useful affordable action. You may write code, observe, or restructure.",
    "ordinary_feedback": "Use the same design/problem representation, full public history and all legal actions. Decide the next action directly from ordinary execution feedback; place the action you commit to first in candidates. The first legal candidate is selected without a separate model ranking call. No prescribed causal-attribution procedure. You may observe, restructure, or write code.",
    "full_h": "Generate finite executable alternatives with scoped predictions or UNKNOWN, competing explanations and observation branches. Select an affordable discriminating action or local repair. Reform active variables only when evidence motivates it; preserve uncertainty and consider stopping.",
    "fixed_sequence": "Use the same legal actions, representation and evidence access. Selection follows the fixed priority observe, edit, verify, restructure, refine, select, report among your submitted legal candidates, with submitted order breaking ties. This priority restarts at each decision; it does not require submitting every operation or remove any legal action.",
}


class ContractError(ValueError):
    """An artifact or request violates the shared, method-independent contract."""


def _json(value):
    return json.loads(json.dumps(value, allow_nan=False, sort_keys=True))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _path(obj, path, default=None):
    for part in path.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return default
        obj = obj[part]
    return obj


def _public_result(result):
    return _json(project_result(result))


def public_state(state):
    """Project Task, not the private event truth or evaluator, into method context.

    Typed Results in evidence/history share the same public boundary. This is
    not a classifier that can detect secrets hidden in arbitrary prose.
    """
    out = {k: deepcopy(state[k]) for k in (
        "design", "problem", "evidence", "history", "hypotheses", "invalidated",
        "next_evidence", "strategy", "applicability", "last_result") if k in state}
    out["task"] = {k: deepcopy(v) for k, v in state.get("task", {}).items() if k in TASK_FIELDS}
    if "last_result" in out:
        out["last_result"] = _public_result(out["last_result"])
    return _json(project_embedded_results(out))


def seed_program(kind="H", condition="H0"):
    sites = H_SITES if kind == "H" else G_SITES
    if kind not in {"H", "G"} or condition not in (
            {"H0", "H1", "H2", "H3", "H4"} if kind == "H" else {"G0", "G1", "G2"}):
        raise ContractError("CONDITION_KIND")
    return {"schema": SCHEMA, "program_id": f"{kind}-seed-v1", "kind": kind,
            "condition": condition, "generation_index": 0, "artifact_version": "1",
            "parent_program": None, "editable_sites": list(sites), "code": {},
            "prompts": {}, "config": {}, "applicability": {}, "non_trigger_conditions": {},
            "origin": "DEVELOPER_SEED", "adoption": "NOT_EVALUATED"}


def _bounded_range(*args):
    r = range(*args)
    if len(r) > 1000:
        raise ContractError("HOOK_RANGE_LIMIT")
    return r


SAFE_BUILTINS = {"len": len, "min": min, "max": max, "sum": sum, "abs": abs,
                 "all": all, "any": any, "sorted": sorted, "enumerate": enumerate,
                 "zip": zip, "range": _bounded_range, "dict": dict, "list": list,
                 "tuple": tuple, "set": set, "str": str, "int": int, "float": float,
                 "bool": bool, "isinstance": isinstance}
SAFE_ATTRIBUTES = {"get", "items", "keys", "values", "copy", "append", "extend",
                   "update", "pop", "sort", "count", "index", "startswith", "endswith"}


def _compile_hook(site, source):
    if not isinstance(source, str) or len(source.encode()) > 65536:
        raise ContractError("HOOK_SOURCE_LIMIT")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ContractError("HOOK_SYNTAX") from exc
    if len(list(ast.walk(tree))) > 5000 or not tree.body:
        raise ContractError("HOOK_AST_LIMIT")
    # No top-level computation, closures over host objects, imports or I/O.
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or (node.name != FUNCTIONS[site] and
                                                     not node.name.startswith("helper_")):
            raise ContractError("HOOK_TOP_LEVEL")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
                             ast.ClassDef, ast.AsyncFunctionDef, ast.While, ast.With,
                             ast.Try, ast.Raise, ast.Delete, ast.Yield, ast.YieldFrom)):
            raise ContractError("HOOK_CAPABILITY")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ContractError("HOOK_PRIVATE_NAME")
        if isinstance(node, ast.Attribute) and node.attr not in SAFE_ATTRIBUTES:
            raise ContractError("HOOK_ATTRIBUTE")
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.args.defaults or
                                                 node.args.kw_defaults or node.returns):
            raise ContractError("HOOK_DEFINITION_EFFECT")
        if isinstance(node, ast.arg) and node.annotation:
            raise ContractError("HOOK_ANNOTATION")
    namespace = {"__builtins__": SAFE_BUILTINS}
    exec(compile(tree, f"<pqe:{site}>", "exec"), namespace)
    fn = namespace.get(FUNCTIONS[site])
    if not callable(fn) or fn.__code__.co_argcount != 2:
        raise ContractError("HOOK_SIGNATURE_REQUIRES_CTX_ASK")
    return fn


@dataclass
class LoadedProgram:
    artifact: dict
    hooks: dict
    calls: list
    hook_runner: Callable | None = None

    def invoke(self, site, context, ask, default):
        ctx = _json(context)
        when = self.artifact.get("applicability", {}).get(site, {})
        unless = self.artifact.get("non_trigger_conditions", {}).get(site, {})
        missing = object()
        trigger = (all(_path(ctx, k, missing) == v for k, v in when.items()) and
                   not any(_path(ctx, k, missing) == v for k, v in unless.items()))
        config = self.artifact.get("config", {}).get(site, {}) if trigger else {}
        prompt = self.artifact.get("prompts", {}).get(site, "") if trigger else ""
        ctx.update(site_config=config, site_prompt=prompt)
        fn = self.hooks.get(site) if trigger else None
        call = {"site": site, "program_id": self.artifact["program_id"],
                "loaded": site in self.hooks, "triggered": bool(fn), "applicable": trigger,
                "effective_prompt_sha256": digest(prompt), "effective_config_sha256": digest(config),
                "context_sha256": digest(ctx), "isolated": bool(fn and self.hook_runner),
                "code_sha256": hashlib.sha256(self.artifact["code"][site].encode()).hexdigest() if fn else None}
        self.calls.append(call)
        if fn is None:
            return _json(default(ctx))
        if self.hook_runner is not None:
            result = self.hook_runner(site, self.artifact["code"][site], ctx, ask)
            if not isinstance(result, dict):
                raise ContractError("HOOK_RESULT_NOT_OBJECT")
            call["result_sha256"] = digest(result)
            return _json(result)
        old_trace, steps = sys.gettrace(), 0

        def bounded_trace(frame, event, arg):
            nonlocal steps
            if frame.f_code.co_filename.startswith("<pqe:") and event in {"line", "call"}:
                steps += 1
                if steps > 10000:
                    raise ContractError("HOOK_STEP_LIMIT")
            return bounded_trace

        try:
            sys.settrace(bounded_trace)
            result = fn(ctx, ask)
        finally:
            sys.settrace(old_trace)
        if not isinstance(result, dict):
            raise ContractError("HOOK_RESULT_NOT_OBJECT")
        return _json(result)


def load_program(artifact, *, hook_runner=None):
    p = _json(artifact)
    base = seed_program(p.get("kind"), p.get("condition"))
    if (p.get("schema") != SCHEMA or not p.get("program_id") or
            type(p.get("generation_index")) is not int or p["generation_index"] < 0 or
            not isinstance(p.get("artifact_version"), str) or not p["artifact_version"]):
        raise ContractError("PROGRAM_IDENTITY")
    sites = set(base["editable_sites"])
    if set(p.get("editable_sites", [])) != sites:
        raise ContractError("EDIT_SCOPE_MISMATCH")
    for field in EDIT_FIELDS:
        if not isinstance(p.get(field, {}), dict) or set(p.get(field, {})) - sites:
            raise ContractError("EDIT_OUTSIDE_SITES")
    for field in ("applicability", "non_trigger_conditions"):
        if any(not isinstance(v, dict) for v in p.get(field, {}).values()):
            raise ContractError("CONDITIONS_MUST_BE_PATH_EQUALITIES")
    hooks = {site: _compile_hook(site, src) for site, src in p.get("code", {}).items()}
    return LoadedProgram(p, hooks, [], hook_runner)


def _validate_value(name, value, spec):
    kind = spec.get("kind")
    if kind == "number" and (not _finite(value) or not spec["min"] <= value <= spec["max"]):
        raise ContractError("DESIGN_DOMAIN:" + name)
    if kind == "boolean" and type(value) is not bool:
        raise ContractError("DESIGN_TYPE:" + name)
    if kind == "mechanism":
        allowed = spec.get("editable", {})
        if not isinstance(value, dict) or set(value) - set(allowed):
            raise ContractError("MECHANISM_DOMAIN")
        for key, v in value.items():
            if not _finite(v) or not allowed[key][0] <= v <= allowed[key][1]:
                raise ContractError("MECHANISM_DOMAIN:" + key)


def common_contract_check(state, actual, quota):
    """Cheap method-independent permission check; adapter remains authority."""
    if not isinstance(actual, dict) or set(actual) - {"operation", "design_patch", "problem_patch", "dt_s"}:
        raise ContractError("ACTION_FIELDS_OUTSIDE_CONTRACT")
    task = state["task"]
    operation = actual.get("operation")
    if operation not in OPERATIONS or operation not in task.get("allowed_operations", OPERATIONS):
        raise ContractError("UNKNOWN_OPERATION")
    ppatch, dpatch = actual.get("problem_patch", {}), actual.get("design_patch", {})
    if not isinstance(ppatch, dict) or set(ppatch) - PROBLEM_FIELDS or not isinstance(dpatch, dict):
        raise ContractError("PROBLEM_CANNOT_EDIT_TASK_OR_EVALUATOR")
    domain = task.get("design_domain", {})
    problem = {**state.get("problem", {}), **ppatch}
    if (not isinstance(problem.get("active_variables", []), list) or
            not isinstance(problem.get("groups", []), list) or
            any(not isinstance(g, list) for g in problem.get("groups", [])) or
            not isinstance(problem.get("fixed_choices", {}), dict)):
        raise ContractError("PROBLEM_FIELD_TYPES")
    active = set(problem.get("active_variables", []))
    if not active <= set(domain) or any(not set(g) <= active for g in problem.get("groups", [])):
        raise ContractError("PROBLEM_ACTIVE_DOMAIN")
    if not set(dpatch) <= active:
        raise ContractError("EDIT_OUTSIDE_ACTIVE_VARIABLES")
    if operation in {"observe", "verify", "report", "select"} and dpatch:
        raise ContractError("READ_ACTION_HAS_EDIT")
    design = {**state.get("design", {}), **dpatch}
    for name, value in dpatch.items():
        _validate_value(name, value, domain[name])
    for name, value in problem.get("fixed_choices", {}).items():
        if name not in domain or design.get(name) != value:
            raise ContractError("FIXED_CHOICE_CHANGED_WITHOUT_REFORM")
    if "dt_s" in actual and actual["dt_s"] not in task.get("integration", {}).get("allowed_dt_s", []):
        raise ContractError("UNREGISTERED_REFINEMENT")
    if quota.get("remaining_actions", 0) < 1:
        raise ContractError("ACTION_BUDGET_EXHAUSTED")
    return _json(actual)


class _Method:
    def __init__(self, kind, protocol, planner, program, fixture_mode):
        self.protocol, self.planner, self.fixture_mode = protocol, planner, fixture_mode
        self.program = program if isinstance(program, LoadedProgram) else load_program(program or seed_program(kind, kind + "0"))
        if self.program.artifact["kind"] != kind:
            raise ContractError("PROGRAM_KIND")
        self.usage_ledger, self.blocked = [], False
        self.quota = {}

    @property
    def evidence_class(self):
        return "SOFTWARE_FIXTURE" if self.fixture_mode else "METHOD_EXECUTION"

    def _ask(self, site, payload):
        if self.blocked:
            return {"status": "MISSING_USAGE", "reason": "prior callback usage unresolved"}
        if self.planner is None:
            return {"status": "PLANNER_UNAVAILABLE"}
        spent = sum(r.get("usage", {}).get("cost", 0) or 0 for r in self.usage_ledger)
        reserve = self.quota.get("model_call_reserve", 0)
        if not self.fixture_mode and (
                len(self.usage_ledger) >= self.quota.get("model_calls_remaining", 0) or
                not _finite(reserve) or reserve <= 0 or
                spent + reserve > self.quota.get("model_cost_remaining", 0)):
            return {"status": "MODEL_BUDGET_UNAVAILABLE"}
        request = {"schema": SCHEMA, "site": site, "protocol": self.protocol,
                   "instruction": PROTOCOLS.get(self.protocol, self.protocol),
                   "program_id": self.program.artifact["program_id"], "context": _json(payload)}
        try:
            response = self.planner(_json(request))
        except Exception as exc:
            self.usage_ledger.append({"site": site, "status": "TOOL_ERROR",
                                      "error": type(exc).__name__, "reserve": reserve,
                                      "usage": {"status": "SOFTWARE_FIXTURE" if self.fixture_mode else "UNKNOWN"}})
            self.blocked = not self.fixture_mode
            return {"status": "TOOL_ERROR"}
        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        self.usage_ledger.append({"site": site, "reserve": reserve, "usage": _json(usage)})
        valid = usage.get("status") == ("SOFTWARE_FIXTURE" if self.fixture_mode else "KNOWN")
        if not self.fixture_mode:
            valid = valid and bool(usage.get("model_identity")) and all(
                _finite(usage.get(k)) and usage[k] >= 0 for k in ("cost", "input_tokens", "output_tokens"))
        if not valid:
            self.blocked = True
            return {"status": "MISSING_USAGE"}
        if not self.fixture_mode and usage["cost"] > reserve:
            self.blocked = True
            return {"status": "MODEL_BUDGET_EXCEEDED"}
        payload = response.get("payload")
        if not isinstance(payload, dict):
            return {"status": "INVALID_PLANNER_OUTPUT"}
        return _json(payload)

    def _invoke(self, site, ctx, default):
        try:
            return self.program.invoke(site, ctx, self._ask, default)
        except Exception as exc:
            return {"status": "HOOK_ERROR", "error": str(exc)}


class Harness(_Method):
    def __init__(self, protocol="full_h", planner=None, program=None, fixture_mode=False):
        if protocol not in PROTOCOLS:
            raise ContractError("UNKNOWN_H_PROTOCOL")
        super().__init__("H", protocol, planner, program, fixture_mode)

    @property
    def selection_uses_model(self):
        return self.protocol not in {"fixed_sequence", "ordinary_feedback"} or "H-RANK" in self.program.hooks

    def generate(self, state, quota):
        self.quota = _json(quota)
        state = public_state(state)
        ctx = {"state": state, "quota": self.quota}
        start = len(self.program.calls)
        stop = self._invoke("H-STOP", ctx, lambda c: {
            "stop": c["state"].get("applicability") == "OUT_OF_SCOPE" or c["quota"].get("remaining_actions", 0) < 1,
            "reason": "scope or remaining quota", "scope": "current state only"})
        if "status" in stop and stop["status"] != "OK":
            return {**stop, "candidates": [], "calls": self.program.calls[start:]}
        if stop.get("stop"):
            return {"status": "STOPPED", "candidates": [], "stop": stop,
                    "calls": self.program.calls[start:], "evidence_class": self.evidence_class}
        generated = self._invoke("H-GEN", ctx, lambda c: self._ask("H-GEN", c))
        if generated.get("status", "OK") != "OK":
            return {**generated, "candidates": [], "calls": self.program.calls[start:]}
        exp = self._invoke("H-EXP", {**ctx, "generated": generated},
                           lambda c: {"candidates": c["generated"].get("experiment_candidates", [])})
        reform = self._invoke("H-REFORM", {**ctx, "generated": generated},
                              lambda c: {"candidate_patches": c["generated"].get("problem_reforms", {})})
        for output in (exp, reform):
            if output.get("status", "OK") != "OK":
                return {**output, "candidates": [], "calls": self.program.calls[start:]}
        if (not isinstance(generated.get("candidates", []), list) or
                not isinstance(exp.get("candidates", []), list) or
                not isinstance(reform.get("candidate_patches", {}), dict)):
            return {"status": "INVALID_PLANNER_OUTPUT", "candidates": [], "calls": self.program.calls[start:]}
        candidates, rejected, seen = [], [], set()
        raw = generated.get("candidates", []) + exp.get("candidates", [])
        max_candidates = min(int(quota.get("max_candidates", 16)), 64)
        if len(raw) > max_candidates:
            return {"status": "CANDIDATE_CAP_EXCEEDED", "candidates": [], "calls": self.program.calls[start:]}
        for candidate in raw:
            try:
                c = _json(candidate)
                required = {"id", "target", "operation", "expected_state_change", "prediction_or_unknown",
                            "observation_branches", "affected_constraints", "cost_bound", "validity_conditions"}
                if not required <= set(c) or not isinstance(c["id"], str) or c["id"] in seen:
                    raise ContractError("CANDIDATE_FIELDS_OR_ID")
                seen.add(c["id"])
                actual = c.get("actual_input", {"operation": c["operation"],
                                                "design_patch": c.get("design_patch", {}),
                                                "problem_patch": c.get("problem_change", {})})
                if actual.get("operation") != c["operation"]:
                    raise ContractError("OPERATION_MISMATCH")
                patch = reform.get("candidate_patches", {}).get(c["id"], {})
                if set(patch) - PROBLEM_FIELDS:
                    raise ContractError("REFORM_CANNOT_EDIT_TASK")
                actual["problem_patch"] = {**actual.get("problem_patch", {}), **patch}
                c["actual_input"] = common_contract_check(state, actual, quota)
                if not _finite(c["cost_bound"]) or c["cost_bound"] < 0 or c["cost_bound"] > quota.get("remaining_cost", 0):
                    raise ContractError("CANDIDATE_COST_BOUND")
                candidates.append(c)
            except (ValueError, KeyError, TypeError) as exc:
                rejected.append({"id": candidate.get("id") if isinstance(candidate, dict) else None,
                                 "reason": str(exc)})
        return {"status": "READY" if candidates else "INSUFFICIENT_EVIDENCE", "candidates": candidates,
                "rejected": rejected, "calls": self.program.calls[start:], "evidence_class": self.evidence_class}

    def select(self, state, batch, quota):
        self.quota = _json(quota)
        state = public_state(state)
        empty = {"status": batch.get("status", "INSUFFICIENT_EVIDENCE"), "selected_id": None,
                 "actual_input": None, "resource_reservation": 0, "evidence_class": self.evidence_class}
        candidates = batch.get("candidates", [])
        if not candidates or self.blocked:
            return {**empty, "status": "MISSING_USAGE" if self.blocked else empty["status"]}
        ctx = {"state": state, "candidates": candidates, "quota": self.quota}

        def default(c):
            if self.protocol == "fixed_sequence":
                order = c["site_config"].get("operation_order", list(FIXED_OPERATION_ORDER))
                chosen = min(c["candidates"], key=lambda x: order.index(x["operation"]) if x["operation"] in order else len(order))
                return {"selected_id": chosen["id"], "selection_basis": "declared fixed sequence",
                        "expected_discrimination_or_gain": "UNKNOWN"}
            if self.protocol == "ordinary_feedback":
                return {"selected_id": c["candidates"][0]["id"],
                        "selection_basis": "ordinary feedback: model committed first candidate",
                        "expected_discrimination_or_gain": "UNKNOWN"}
            return self._ask("H-RANK", c)

        selected = self._invoke("H-RANK", ctx, default)
        if selected.get("status", "OK") != "OK":
            return {**empty, **selected}
        c = next((x for x in candidates if x["id"] == selected.get("selected_id")), None)
        if c is None or not selected.get("selection_basis"):
            return {**empty, "status": "INVALID_SELECTION"}
        try:
            actual = common_contract_check(state, c["actual_input"], quota)
            if (not _finite(c["cost_bound"]) or c["cost_bound"] < 0 or
                    c["cost_bound"] > quota.get("remaining_cost", 0)):
                raise ContractError("CANDIDATE_COST_BOUND")
        except (KeyError, ContractError) as exc:
            return {**empty, "status": "CONTRACT_REJECTED", "reason": str(exc)}
        return {"status": "READY", "selected_id": c["id"], "selection_basis": selected["selection_basis"],
                "expected_discrimination_or_gain": selected.get("expected_discrimination_or_gain", "UNKNOWN"),
                "resource_reservation": c["cost_bound"], "actual_input": actual,
                "selected_candidate": _json(c), "alternatives": _json(candidates),
                "selection_control": {
                    "policy": "model_rank" if self.selection_uses_model else self.protocol,
                    "candidate_order": [x["id"] for x in candidates],
                    "selected_position": next(i for i, x in enumerate(candidates) if x["id"] == c["id"]),
                    "operation_order": self.program.artifact.get("config", {}).get("H-RANK", {}).get(
                        "operation_order", list(FIXED_OPERATION_ORDER)) if self.protocol == "fixed_sequence" else None},
                "evidence_class": self.evidence_class}

    def update(self, state, decision, result, independent_assessment=None):
        new = public_state(state)
        result = _public_result(result)
        if independent_assessment is not None and independent_assessment.get("visibility") != "PUBLIC":
            raise ContractError("ASSESSMENT_MUST_BE_PUBLIC_PROJECTION")
        new["last_result"] = result
        record = {"incident_id": digest({"decision": decision, "result": result}),
                  "time": {"history_index": len(new.get("history", []))}, "learning_value": "UNASSESSED",
                  "visible_before": public_state({k: v for k, v in state.items() if k != "history"}),
                  "decision": _json(decision), "result": result,
                  "provenance": self.evidence_class, "allowed_for_learning": False}
        new.setdefault("history", []).append(record)
        status = result.get("execution_status", "INCOMPLETE")
        if status not in {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}:
            new["update_status"] = "TOOL_ERROR" if status in {"ERROR", "TOOL_ERROR"} else "INCOMPLETE"
            return new
        # Consumer-confirmed state, even a physically failing executed design.
        for key in ("design", "problem"):
            if key in result:
                new[key] = deepcopy(result[key])
        if result.get("model_valid") is not True:
            new["update_status"] = "DOMAIN_UNKNOWN"
            return new
        ctx = {"state": new, "decision": decision, "result": result,
               "public_assessment": independent_assessment}

        def default(c):
            if self.protocol != "full_h":
                return {"hypotheses": c["state"].get("hypotheses", []), "next_evidence": "ordinary feedback available"}
            return _prediction_update(c["state"], c["decision"], c["result"])

        patch = self._invoke("H-UPDATE", ctx, default)
        if patch.get("status", "OK") != "OK":
            new["update_status"] = patch["status"]
            return new
        if set(patch) - UPDATE_FIELDS:
            new["update_status"] = "UPDATE_CONTRACT_REJECTED"
            new["update_error"] = {"code": "UPDATE_FIELDS_OUTSIDE_CONTRACT", "fields": sorted(set(patch) - UPDATE_FIELDS)}
            return new
        new.update(patch)
        new["update_status"] = "UPDATED"
        return new


def _prediction_update(state, decision, result):
    hypotheses = deepcopy(state.get("hypotheses", []))
    invalidated = deepcopy(state.get("invalidated", []))
    prediction = decision.get("selected_candidate", {}).get("prediction_or_unknown")
    if not isinstance(prediction, dict) or not prediction.get("hypothesis_id") or not prediction.get("scope"):
        return {"hypotheses": hypotheses, "invalidated": invalidated, "next_evidence": "UNRESOLVED"}
    missing = object()
    observed = _path(result, prediction.get("metric", ""), missing)
    expected, op = prediction.get("value"), prediction.get("operator")
    supported = None
    if observed is not missing:
        if op == "eq":
            supported = observed == expected
        elif op in {"le", "ge"} and _finite(observed) and _finite(expected):
            supported = observed <= expected if op == "le" else observed >= expected
    label = "UNRESOLVED" if supported is None else "CONSISTENT" if supported else "REFUTED"
    item = {"id": prediction["hypothesis_id"], "scope": prediction["scope"], "status": label,
            "unique_cause": False, "evidence_result": result.get("result_sha256")}
    hypotheses = [h for h in hypotheses if not (h.get("id") == item["id"] and h.get("scope") == item["scope"])] + [item]
    if label == "REFUTED":
        invalidated.append({"prediction": item["id"], "scope": item["scope"],
                            "dependent_strategies": prediction.get("dependent_strategies", [])})
    return {"hypotheses": hypotheses, "invalidated": invalidated, "next_evidence": "UNRESOLVED"}


def _eligible(history, fixture_mode):
    return [deepcopy(h) for h in history if h.get("allowed_for_learning") is True and
            h.get("incident_id") and h.get("visible_before") is not None and
            isinstance(h.get("decision"), dict) and isinstance(h.get("result"), dict) and
            ((fixture_mode and h.get("provenance") == "SOFTWARE_FIXTURE") or
             (not fixture_mode and h.get("provenance") == "PUBLIC_EXECUTION" and h.get("record_ref")))]


def materialize_patch(parent, patch, incidents, *, fixture_mode=False, prompt_only=False):
    """Build a candidate, never adopt it. Same edit-space check for H2 and H4."""
    load_program(parent)
    if (not PATCH_FIELDS <= set(patch) or patch["parent_program"] != parent["program_id"] or
            patch["parent_sha256"] != digest(parent)):
        raise ContractError("PATCH_FIELDS_OR_PARENT")
    ids = {i["incident_id"] for i in incidents}
    if not patch["source_incidents"] or not set(patch["source_incidents"]) <= ids:
        raise ContractError("PATCH_SOURCE_INCIDENTS")
    for field in ("predicted_behavior_change", "side_effects", "behavior_tests", "full_task_test_plan", "falsifier"):
        if not patch[field]:
            raise ContractError("PATCH_EVIDENCE_PLAN:" + field)
    change = deepcopy(patch["change"])
    if set(change) - EDIT_FIELDS or (prompt_only and set(change) - {"prompts"}):
        raise ContractError("PATCH_EDIT_SPACE")
    changed_sites = set().union(*(set(v) for v in change.values())) if change else set()
    sites = set(parent["editable_sites"])
    if not changed_sites or changed_sites != set(patch["target_sites"]) or not changed_sites <= sites:
        raise ContractError("PATCH_TARGET_SITES")
    if set(patch["applicability"]) - changed_sites or set(patch["non_trigger_conditions"]) - changed_sites:
        raise ContractError("PATCH_SCOPE_SITES")
    child = deepcopy(parent)
    for field, changes in change.items():
        child.setdefault(field, {}).update(changes)
    child["applicability"].update(patch["applicability"])
    child["non_trigger_conditions"].update(patch["non_trigger_conditions"])
    child.update(parent_program=parent["program_id"], generation_index=parent["generation_index"] + 1,
                 artifact_version=str(int(parent["artifact_version"]) + 1) if parent["artifact_version"].isdigit() else parent["artifact_version"] + ".1",
                 origin="SOFTWARE_FIXTURE" if fixture_mode else "PROPOSED_FROM_EXPERIENCE",
                 adoption="NOT_EVALUATED", source_incidents=patch["source_incidents"])
    child["program_id"] = parent["kind"] + "-candidate-" + digest(child)[:16]
    load_program(child)
    return child


class Improver(_Method):
    """G0 may produce H children; G1/G2 may propose their own G descendants."""
    def __init__(self, protocol="attribution", planner=None, program=None, fixture_mode=False):
        if protocol not in {"attribution", "general_program", "gepa_prompt_only", "stop_selfmod"}:
            raise ContractError("UNKNOWN_G_PROTOCOL")
        super().__init__("G", protocol, planner, program, fixture_mode)

    def extract(self, history):
        incidents = _eligible(history, self.fixture_mode)
        if not incidents:
            return {"status": "INSUFFICIENT_EVIDENCE", "incidents": [], "no_update": True}
        output = self._invoke("G-EXTRACT", {"incidents": incidents},
                              lambda c: {"incidents": c["incidents"][:64]})
        selected = output.get("incidents", [])
        source = {i["incident_id"]: i for i in incidents}
        if any(i.get("incident_id") not in source or i != source[i["incident_id"]] for i in selected):
            return {"status": "INCIDENT_FABRICATION_REJECTED", "incidents": [], "no_update": True}
        return {**output, "status": output.get("status", "READY" if selected else "INSUFFICIENT_EVIDENCE"),
                "incidents": selected, "evidence_class": self.evidence_class}

    def attribute(self, extracted, parent):
        incidents = extracted.get("incidents", [])
        if not incidents:
            return {"status": "INSUFFICIENT_EVIDENCE", "incidents": [], "no_update": True}
        ctx = {"incidents": incidents, "parent": parent,
               "distinguish": ["H_OR_G_DEFECT", "CONSUMER_GAP", "TASK_UNDERSPECIFIED", "ENGINEERING_INFEASIBILITY", "UNRESOLVED"],
               "required": "competing explanations, support/refutation, missing discrimination, target sites"}
        default = (lambda c: self._ask("G-ATTRIBUTE", c)) if self.protocol == "attribution" else (
            lambda c: {"explanations": [], "approach": "general trajectory reflection without imposed attribution"})
        output = self._invoke("G-ATTRIBUTE", ctx, default)
        if self.protocol == "attribution" and output.get("status", "OK") in {"OK", "READY"}:
            explanations = output.get("explanations", [])
            required = {"kind", "support", "refutation", "missing_discrimination", "target_sites"}
            valid = isinstance(explanations, list) and all(
                isinstance(e, dict) and required <= set(e) and
                e["kind"] in ctx["distinguish"] and
                set(e["target_sites"]) <= set(parent["editable_sites"])
                for e in explanations)
            if not valid:
                output = {"status": "ATTRIBUTION_CONTRACT_REJECTED", "explanations": []}
            elif not any(e["kind"] == "H_OR_G_DEFECT" and e["support"] and e["target_sites"] for e in explanations):
                output = {**output, "status": "INSUFFICIENT_EVIDENCE", "no_update": True}
        return {**output, "status": output.get("status", "READY"), "incidents": incidents}

    def propose(self, attribution, parent, quota):
        self.quota = _json(quota)
        if self.blocked:
            return {"status": "MISSING_USAGE", "programs": [], "no_update": True}
        incidents = attribution.get("incidents", [])
        if not _eligible(incidents, self.fixture_mode) or attribution.get("status") not in {"READY", "OK"}:
            return {"status": "INSUFFICIENT_EVIDENCE", "programs": [], "no_update": True}
        if parent["kind"] == "G" and self.program.artifact["condition"] == "G0":
            return {"status": "FIXED_G_CANNOT_SELF_MODIFY", "programs": [], "no_update": True}
        ctx = {"parent": parent, "attribution": attribution, "quota": quota,
               "allowed_sites": parent["editable_sites"],
               "allowed_fields": ["prompts"] if self.protocol == "gepa_prompt_only" else sorted(EDIT_FIELDS),
               "patch_required_fields": sorted(PATCH_FIELDS),
               "instruction": "Propose executable changes, including code/control-flow when useful. No task-ID or private-parameter rules. No update is valid; do not change evaluator, authorization, accounting or adoption rules."}
        output = self._invoke("G-PROPOSE", ctx, lambda c: self._ask("G-PROPOSE", c))
        if self.blocked:
            return {"status": "MISSING_USAGE", "programs": [], "no_update": True}
        programs, rejected = [], []
        patches = output.get("patches", [])
        if not isinstance(patches, list) or len(patches) > quota.get("max_proposals", 4):
            return {"status": "PROPOSAL_CAP_EXCEEDED", "programs": [], "no_update": True}
        for patch in patches:
            try:
                child = materialize_patch(parent, patch, incidents, fixture_mode=self.fixture_mode,
                                          prompt_only=self.protocol == "gepa_prompt_only")
                programs.append({"program": child, "patch": patch})
            except (ValueError, TypeError, KeyError) as exc:
                rejected.append({"reason": str(exc), "patch_sha256": digest(patch)})
        return {"status": "PROPOSED" if programs else output.get("status", "NO_UPDATE"),
                "programs": programs, "rejected": rejected, "no_update": not programs,
                "evidence_class": self.evidence_class}

    def allocate(self, proposals, evaluations, quota):
        self.quota = _json(quota)
        if self.blocked:
            return {"status": "MISSING_USAGE", "program_id": None, "next": "STOP"}
        programs = proposals.get("programs", [])
        if not programs:
            return {"status": "RETAIN_PARENT", "program_id": None, "next": "STOP"}
        ctx = {"programs": programs, "evaluations": evaluations, "quota": quota}

        def default(c):
            for item in c["programs"]:
                pid = item["program"]["program_id"]
                rows = [e for e in c["evaluations"] if e.get("program_id") == pid]
                if any(e.get("outcome") in {"FAIL", "ERROR"} for e in rows):
                    continue
                phases = {e.get("phase") for e in rows if e.get("outcome") == "PASS"}
                if {"local", "selection"} <= phases:
                    return {"status": "AWAIT_EXTERNAL_CONFIRMATION", "program_id": pid, "next": "HELD_OUT_AND_ADOPTION"}
                if c["quota"].get("evaluation_calls_remaining", 0) > 0:
                    return {"status": "SCREEN", "program_id": pid, "next": "selection" if "local" in phases else "local"}
            return {"status": "RETAIN_PARENT", "program_id": None, "next": "STOP"}

        output = self._invoke("G-ALLOCATE", ctx, default)
        ids = {x["program"]["program_id"] for x in programs}
        if output.get("program_id") not in ids | {None} or output.get("next") not in {"local", "selection", "HELD_OUT_AND_ADOPTION", "STOP"}:
            return {"status": "ALLOCATION_REJECTED", "program_id": None, "next": "STOP"}
        # A loaded G can allocate screenings, never bypass external confirmation.
        if output.get("status") not in {"SCREEN", "RETAIN_PARENT", "AWAIT_EXTERNAL_CONFIRMATION"}:
            return {"status": "ALLOCATION_REJECTED", "program_id": None, "next": "STOP"}
        pid, phase = output.get("program_id"), output.get("next")
        rows = [e for e in evaluations if e.get("program_id") == pid]
        passed = {e.get("phase") for e in rows if e.get("outcome") == "PASS"}
        failed = any(e.get("outcome") in {"FAIL", "ERROR"} for e in rows)
        invalid = (output["status"] == "SCREEN" and (
            pid is None or phase not in {"local", "selection"} or failed or
            quota.get("evaluation_calls_remaining", 0) < 1 or
            (phase == "selection" and "local" not in passed)))
        invalid = invalid or (output["status"] == "AWAIT_EXTERNAL_CONFIRMATION" and (
            phase != "HELD_OUT_AND_ADOPTION" or failed or not {"local", "selection"} <= passed))
        invalid = invalid or (output["status"] == "RETAIN_PARENT" and (pid is not None or phase != "STOP"))
        if invalid:
            return {"status": "ALLOCATION_REJECTED", "program_id": None, "next": "STOP"}
        return output

    def improve(self, parent, history, quota, evaluate=None):
        """Finite, callable improvement adapter; evaluation callable stays external."""
        self.quota = _json(quota)
        extracted = self.extract(history)
        attribution = self.attribute(extracted, parent)
        proposals = self.propose(attribution, parent, quota)
        evaluations = []
        remaining = int(quota.get("evaluation_calls_remaining", 0))
        allocation = self.allocate(proposals, evaluations, {**quota, "evaluation_calls_remaining": remaining})
        while evaluate is not None and allocation.get("status") == "SCREEN" and remaining > 0:
            candidate = next(x["program"] for x in proposals["programs"] if x["program"]["program_id"] == allocation["program_id"])
            phase = allocation["next"]
            try:
                row = _json(evaluate(deepcopy(candidate), phase))
            except Exception as exc:
                row = {"outcome": "ERROR", "error": type(exc).__name__, "usage": {"status": "UNKNOWN"}}
            row.update(program_id=candidate["program_id"], phase=phase)
            evaluations.append(row)
            remaining -= 1
            expected = "SOFTWARE_FIXTURE" if self.fixture_mode else "KNOWN"
            if row.get("usage", {}).get("status") != expected:
                self.blocked = True
                allocation = {"status": "MISSING_USAGE", "program_id": None, "next": "STOP"}
                break
            allocation = self.allocate(proposals, evaluations, {**quota, "evaluation_calls_remaining": remaining})
        return {"extracted": extracted, "attribution": attribution, "proposals": proposals,
                "evaluations": evaluations, "allocation": allocation, "parent_retained": True,
                "adopted_program": None, "evidence_class": self.evidence_class,
                "usage_ledger": deepcopy(self.usage_ledger)}

    def self_modify(self, history, quota, evaluate=None):
        """STOP-style self-application to G code; returned child is not self-adopted."""
        return self.improve(self.program.artifact, history, quota, evaluate)


GEPA_PIN = "8f287de942f41a6d1e0e7e5b2d576247c4bedee9"
STOP_PIN = "0d6780c54306b2486dd36e9c4ae9b49aceb27ea4"


def run_gepa(parent, history, quota, *, engine=None, evaluator=None, config=None,
             usage_reader=None, fixture_mode=False, prompt_only=False):
    """Bridge the pinned official optimize_anything API, not a renamed prompt toy.

    engine is gepa.optimize_anything.optimize_anything (or a labelled fixture).
    config is an owner-built OptimizeAnythingConfig, with engine='gepa' and a
    finite max_evals. No test_set is supplied: official test calls outside the
    optimizer budget must not bypass the BF common ledger or held-out boundary.
    """
    if not _eligible(history, fixture_mode):
        return {"status": "INSUFFICIENT_EVIDENCE", "parent_retained": True}
    if engine is None or evaluator is None or config is None:
        return {"status": "BACKEND_UNAVAILABLE", "parent_retained": True}
    if not fixture_mode and usage_reader is None:
        return {"status": "USAGE_READER_REQUIRED", "parent_retained": True}
    max_evals = getattr(config, "max_evals", None)
    if (getattr(config, "engine", None) != "gepa" or type(max_evals) is not int or
            not 0 < max_evals <= quota.get("evaluation_calls_remaining", 0)):
        raise ContractError("GEPA_ENGINE_OR_BUDGET")
    fields = {"prompts"} if prompt_only else EDIT_FIELDS
    seed = {k: deepcopy(parent.get(k, {})) for k in sorted(fields)}
    evaluations = []
    halted = False

    def decode(text):
        change = json.loads(text)
        if not isinstance(change, dict) or set(change) != fields:
            raise ContractError("GEPA_EDIT_SPACE")
        child = deepcopy(parent)
        child.update(change)
        child.update(parent_program=parent["program_id"], generation_index=parent["generation_index"] + 1,
                     artifact_version=parent["artifact_version"] + ".gepa", adoption="NOT_EVALUATED",
                     origin="SOFTWARE_FIXTURE" if fixture_mode else "GEPA_PROPOSAL")
        child["program_id"] = parent["kind"] + "-gepa-" + digest(child)[:16]
        load_program(child)
        return child

    def score(text, example=None):
        nonlocal halted
        if halted:
            raise ContractError("MISSING_USAGE")
        if len(evaluations) >= max_evals:
            raise ContractError("GEPA_EVALUATION_CAP")
        try:
            candidate = decode(text)
        except (ValueError, TypeError, KeyError) as exc:
            evaluations.append({"status": "INVALID_PROGRAM", "reason": str(exc), "cost": 0})
            return 0.0, {"error": str(exc)}
        row = _json(evaluator(candidate, example))
        evaluations.append(row)
        if row.get("usage", {}).get("status") != ("SOFTWARE_FIXTURE" if fixture_mode else "KNOWN"):
            halted = True
            raise ContractError("MISSING_USAGE")
        if not _finite(row.get("score")):
            raise ContractError("EVALUATION_SCORE")
        return row["score"], row.get("public_feedback", {})

    try:
        result = engine(seed_candidate=json.dumps(seed, sort_keys=True), evaluator=score,
                        objective="Improve complete-task service under the common total budget; keep the same authorized program sites.",
                        background=json.dumps({"history": _eligible(history, fixture_mode), "editable_sites": parent["editable_sites"]}),
                        config=config)
        if halted:
            return {"status": "MISSING_USAGE", "parent_retained": True, "evaluations": evaluations}
        usage = {"status": "SOFTWARE_FIXTURE"} if fixture_mode else _json(usage_reader(result))
        if usage.get("status") != ("SOFTWARE_FIXTURE" if fixture_mode else "KNOWN"):
            return {"status": "MISSING_USAGE", "parent_retained": True, "evaluations": evaluations, "usage": usage}
        best = result.best_candidate if hasattr(result, "best_candidate") else result["best_candidate"]
        candidate = decode(best)
    except Exception as exc:
        return {"status": "MISSING_USAGE" if halted else "BACKEND_ERROR", "error": str(exc),
                "parent_retained": True, "evaluations": evaluations}
    return {"status": "AWAIT_EXTERNAL_CONFIRMATION", "candidate": candidate, "evaluations": evaluations,
            "usage": usage, "parent_retained": True, "adopted_program": None,
            "upstream_pin": GEPA_PIN, "scope": "prompt_only" if prompt_only else "all_program_sites",
            "evidence_class": "SOFTWARE_FIXTURE" if fixture_mode else "METHOD_EXECUTION"}
