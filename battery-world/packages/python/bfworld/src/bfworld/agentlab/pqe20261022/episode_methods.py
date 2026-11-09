"""Trusted, fixed Stage 2 driver around the frozen Stage 1 Harness.

Only JSON crosses the planner boundary. The owner supplies the clean initial
state, real provider/ledger callback and public broker results. This module
dispatches no engineering tools, loads no generated code and adopts no H/G.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from .methods import Harness, ContractError, OPERATIONS, PROTOCOLS, UPDATE_FIELDS, digest, public_state

FROZEN_METHODS_SHA256 = "766266cec7c1850852666ba253b6853d5409cc82057f558a8d9d93c1f923da5e"
DEFAULT_LIMITS = {"provider_requests": 12, "tool_calls": 24, "new_numerical_inputs": 6,
                  "wall_s": 900, "output_tokens_per_request": 4096,
                  "output_tokens_total": 49152, "reserve_usd": 4}
MAX_LIMITS = {**DEFAULT_LIMITS, "output_tokens_per_request": 32768, "output_tokens_total": 131072}
SUCCESS = {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}
OUTPUT_PROTOCOL = "pqe-common-output-feedback-v2-e2dev"


def _copy(value):
    return json.loads(json.dumps(value, allow_nan=False))


def planner_instructions(request):
    """Common response schema plus the declared, fixed condition instruction."""
    common = (
        "Return exactly one JSON object, without Markdown fences or executable code. "
        "You control only authorized Design/Problem actions through the given broker. "
        "No shell, files, imports, external tools, hidden truth or evaluator modification. "
        "All four conditions may use every legal action and all supplied public materials. "
        "Use complete service constraints; a local observation is not a proof of global feasibility. "
        "Do not invent results, usage or successful executions. UNKNOWN is valid. "
        "cost_bound is the number of broker actions reserved, normally 1; it is not USD. "
        "Public trace/activity may be explicitly sampled rather than complete. Read facts.detail_catalog "
        "for total counts and page sizes. To inspect an available full page, use an observe candidate "
        "with target='detail:trace:0' or target='detail:activity:64' (offsets in steps of 64), "
        "and actual_input={operation:'observe',design_patch:{},problem_patch:{}}. Preserve the exact target. "
        "A detail page or exact cached input uses a broker call but no new numerical input. "
        "An ordinary observe without an exact cached input executes the current design and consumes a "
        "new numerical input. The broker decides cache eligibility after you declare the action. "
    )
    site = request.get("site")
    if site == "H-GEN":
        schema = (
            "Produce {\"status\":\"OK\",\"candidates\":[...]}. Keep at most 4 finite candidates. "
            "Each candidate has id (unique string), target, operation, expected_state_change, "
            "prediction_or_unknown, observation_branches (array), affected_constraints (array), "
            "cost_bound (nonnegative number), validity_conditions (array), and actual_input. "
            "actual_input={operation,design_patch:{...},problem_patch:{...}}; optional dt_s must be registered. "
            "Operations are edit, observe, verify, restructure, refine, select, report. "
            "Observe/verify/report/select do not edit Design. Design patches must be inside the resulting "
            "Problem.active_variables and Task.design_domain; fixed_choices must agree. "
            "Problem patches may change active_variables, groups, fixed_choices, assumptions, local_objective, "
            "but cannot change the Task, service or evaluator. Groups alone do not expand active variables. "
            "prediction_or_unknown can be \"UNKNOWN\" or {hypothesis_id,metric,operator,value,scope,dependent_strategies}; "
            "metric is a public Result dotted path, operator eq/le/ge, scope explicitly local. "
            "An observation branch states a possible observation and the next decision it would distinguish. "
            "Optionally experiment_candidates uses the same candidate schema, and problem_reforms maps "
            "candidate IDs to legal Problem patches; total candidates including observations must be <=4. "
            "If finished or unable to continue within scope/budget, return "
            "{\"status\":\"STOPPED\",\"conclusion\":{\"verdict\":\"PASS|FAIL|UNKNOWN\",\"basis\":\"...\",\"scope\":\"...\"}} "
            "instead of candidates. A report candidate may carry the same conclusion field. "
            "A conclusion is your assessment of the current design, not an independent evaluation. "
        )
    elif site == "H-RANK":
        schema = (
            "Choose exactly one supplied candidate; return {selected_id,selection_basis,"
            "expected_discrimination_or_gain}. selected_id must match its id. "
            "Do not alter its actual_input or fabricate gain: use \"UNKNOWN\" when unsupported. "
            "Consider remaining budget and all service constraints. "
        )
    elif site == "H-UPDATE":
        schema = (
            "The supplied tool result has already executed. Return only a state patch with optional "
            "hypotheses, invalidated, next_evidence, strategy fields. Do not return an action, repeat the "
            "tool or change Design/Problem. This response cannot cause another scientific execution. "
        )
    elif site == "H-EXP":
        schema = "Return {candidates:[...]} with the same finite candidate schema as H-GEN."
    elif site == "H-REFORM":
        schema = "Return {candidate_patches:{candidate_id:legal Problem patch}} only."
    elif site == "H-STOP":
        schema = "Return {stop:boolean,reason:string,scope:string}; stop is local, never an independent verdict."
    else:
        raise ContractError("UNEXPECTED_PLANNER_SITE")
    return common + schema + "Declared decision program: " + request.get("instruction", "")


def scope_effect(before, actual_input):
    """Record an operational scope change separately from grouping metadata."""
    old = before.get("problem", {})
    new = {**old, **actual_input.get("problem_patch", {})}
    old_active, new_active = set(old.get("active_variables", [])), set(new.get("active_variables", []))
    old_fixed, new_fixed = old.get("fixed_choices", {}), new.get("fixed_choices", {})
    fixed_changed = sorted(k for k in set(old_fixed) | set(new_fixed)
                           if k not in old_fixed or k not in new_fixed or old_fixed[k] != new_fixed[k])
    added, removed = sorted(new_active - old_active), sorted(old_active - new_active)
    groups_changed = old.get("groups", []) != new.get("groups", [])
    patch_keys = set(actual_input.get("design_patch", {}))
    return {"active_variables_added": added, "active_variables_removed": removed,
            "fixed_choices_changed": fixed_changed, "groups_changed": groups_changed,
            "candidate_scope_changed": bool(added or removed or fixed_changed),
            "new_scope_exercised_by_selected_edit": sorted(patch_keys & (set(added) | set(fixed_changed))),
            "group_labels_only": groups_changed and not (added or removed or fixed_changed)}


class EpisodeDriver:
    def __init__(self, condition, planner_callback, *, episode_id, initial_state,
                 model_identity, request_reserve_usd, limits=None, fixture_mode=False,
                 max_contract_corrections=0, program=None, common_history=None,
                 expected_methods_sha256=None, isolated_program=False):
        if condition not in PROTOCOLS:
            raise ContractError("CONDITION_NOT_IN_PILOT")
        if type(max_contract_corrections) is not int or not 0 <= max_contract_corrections <= 2:
            raise ContractError("CONTRACT_CORRECTION_LIMIT_MUST_BE_INTEGER_0_TO_2")
        self.max_contract_corrections = max_contract_corrections
        self.consecutive_contract_errors, self.contract_feedback = 0, []
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        if set(self.limits) != set(DEFAULT_LIMITS) or any(
                not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 < v <= MAX_LIMITS[k]
                for k, v in self.limits.items()):
            raise ContractError("LIMITS_MUST_BE_FINITE_AND_NOT_ENLARGED")
        if any(type(self.limits[k]) is not int for k in (
                "provider_requests", "tool_calls", "new_numerical_inputs", "output_tokens_per_request", "output_tokens_total")):
            raise ContractError("COUNT_LIMITS_MUST_BE_INTEGERS")
        if not model_identity or not isinstance(request_reserve_usd, (int, float)) or not 0 < request_reserve_usd <= self.limits["reserve_usd"]:
            raise ContractError("MODEL_IDENTITY_AND_REQUEST_RESERVE_REQUIRED")
        actual_hash = hashlib.sha256(Path(__file__).with_name("methods.py").read_bytes()).hexdigest()
        if actual_hash != (expected_methods_sha256 or FROZEN_METHODS_SHA256):
            raise ContractError("FROZEN_METHODS_CHANGED")
        self.methods_sha256 = actual_hash
        self.condition, self.episode_id = condition, episode_id
        self.model_identity, self.request_reserve_usd = model_identity, request_reserve_usd
        self.fixture_mode, self.planner_callback = fixture_mode, planner_callback
        initial_state = _copy(initial_state)
        if common_history is not None:
            if not isinstance(common_history, list) or any(h.get("allowed_for_learning") is not True
                    or h.get("provenance") not in {"PUBLIC_EXECUTION", "SOFTWARE_FIXTURE"}
                    for h in common_history):
                raise ContractError("COMMON_HISTORY_NOT_REVIEWED")
            initial_state["history"] = _copy(common_history)
        self.common_history_sha256 = digest(common_history or [])
        self.generated_program_supplied = program is not None
        self.initial_state = public_state(initial_state)
        self.state = deepcopy(self.initial_state)
        self.started_at = time.monotonic()
        self.steps, self.callback_records = [], []
        self.pending, self.termination, self.model_conclusion = None, None, None
        self.tool_calls, self.numerical_inputs = 0, 0
        self.owner_budget = {}
        self.owner_snapshot_base = {}
        self.output_snapshot_base_used = 0
        if isolated_program:
            from .restricted_worker import run_isolated_hook
            from .methods import load_program, seed_program
            program = load_program(program or seed_program(), hook_runner=run_isolated_hook)
        self.harness = Harness(condition, self._callback if planner_callback is not None else None,
                               program=program, fixture_mode=fixture_mode)

    def _instructions(self, request):
        return planner_instructions(request)

    def _callback(self, request):
        used_before = self._output_tokens_used()
        authorized_tokens = min(self.limits["output_tokens_per_request"], self._quota()["output_tokens_left"])
        if authorized_tokens <= 0:
            # Public next() checks this before each site; never dispatch zero.
            raise ContractError("OUTPUT_TOKEN_BUDGET_EXHAUSTED")
        request = _copy(request)
        request.update(episode_id=self.episode_id, condition=self.condition,
                       max_output_tokens=authorized_tokens,
                       json_instructions=self._instructions(request))
        record = {"request": request, "request_sha256": digest(request),
                  "output_budget": {"authorized_tokens": authorized_tokens, "used_before": used_before,
                                    "total_limit": self.limits["output_tokens_total"]},
                  "wall_elapsed_before_s": time.monotonic() - self.started_at}
        self.callback_records.append(record)
        try:
            response = _copy(self.planner_callback(_copy(request)))
        except Exception as exc:
            record["error"] = {"type": type(exc).__name__, "message": str(exc)}
            # Transport/serialization failure cannot be represented as free usage.
            response = {"payload": {"status": "TOOL_ERROR"}, "usage": {"status": "UNKNOWN"}}
        record["response"] = deepcopy(response)
        if not isinstance(response, dict):
            response = {"payload": {"status": "INVALID_PLANNER_OUTPUT"}, "usage": {"status": "UNKNOWN"}}
        usage = response.get("usage", {})
        payload = response.get("payload")
        reported_tokens = usage.get("output_tokens")
        valid_tokens = type(reported_tokens) is int and reported_tokens >= 0
        record["output_budget"].update(reported_tokens=reported_tokens,
                                       used_after=used_before + reported_tokens if valid_tokens else None)
        if usage.get("status") == "KNOWN" and usage.get("model_identity") != self.model_identity:
            payload = {"status": "MODEL_IDENTITY_MISMATCH"}
        elif not valid_tokens:
            payload = {"status": "INVALID_OUTPUT_USAGE"}
        elif used_before + reported_tokens > self.limits["output_tokens_total"]:
            payload = {"status": "OUTPUT_TOKEN_TOTAL_LIMIT_EXCEEDED"}
        elif reported_tokens > authorized_tokens:
            payload = {"status": "OUTPUT_TOKEN_LIMIT_EXCEEDED"}
        elif response.get("provider_status", "COMPLETE") not in {"COMPLETE", "COMPLETED", "OK"}:
            payload = {"status": "INVALID_PLANNER_OUTPUT", "provider_status": response["provider_status"]}
        elif not isinstance(payload, dict):
            payload = {"status": "INVALID_PLANNER_OUTPUT"}
        record["consumed_payload"] = deepcopy(payload)
        record["wall_elapsed_after_s"] = time.monotonic() - self.started_at
        return {**response, "payload": payload}

    def _output_tokens_used(self):
        # Sum original usage, including failed/over-limit responses; never clamp it.
        return sum(row["usage"]["output_tokens"] for row in self.harness.usage_ledger
                   if type(row.get("usage", {}).get("output_tokens")) is int
                   and row["usage"]["output_tokens"] >= 0)

    def _quota(self):
        model_used = len(self.harness.usage_ledger)
        model_cost = sum(r.get("usage", {}).get("cost", 0) or 0 for r in self.harness.usage_ledger)
        elapsed = time.monotonic() - self.started_at
        def owner_left(key, used, default):
            if key not in self.owner_budget:
                return default
            return self.owner_budget[key] - (used - self.owner_snapshot_base[key])
        output_used = self._output_tokens_used()
        output_left = self.limits["output_tokens_total"] - output_used
        if "output_tokens_remaining" in self.owner_budget:
            # One snapshot may cover both Generate and Rank. Spend its allowance
            # once rather than granting the same remainder again at each site.
            output_left = min(output_left, self.owner_budget["output_tokens_remaining"] -
                              (output_used - self.output_snapshot_base_used))
        available_tools = min(self.limits["tool_calls"] - self.tool_calls,
                              owner_left("tool_calls_remaining", self.tool_calls, self.limits["tool_calls"]))
        available_requests = min(self.limits["provider_requests"] - model_used,
                                 owner_left("provider_requests_remaining", model_used, self.limits["provider_requests"]))
        available_usd = min(self.limits["reserve_usd"] - model_cost,
                            owner_left("reserve_usd_remaining", model_cost, self.limits["reserve_usd"]))
        # Frozen Harness compares its cumulative ledger with the supplied grant.
        return {"remaining_actions": max(0, available_tools), "remaining_cost": max(0, available_tools),
                "max_candidates": 4, "model_calls_remaining": model_used + max(0, available_requests),
                "model_cost_remaining": model_cost + max(0, available_usd),
                "model_call_reserve": self.request_reserve_usd,
                "provider_requests_left": max(0, available_requests),
                "output_tokens_left": max(0, output_left),
                "usd_left": max(0, available_usd),
                "new_numerical_inputs_left": max(0, min(self.limits["new_numerical_inputs"] - self.numerical_inputs,
                    owner_left("new_numerical_inputs_remaining", self.numerical_inputs, self.limits["new_numerical_inputs"]))),
                "wall_s_left": max(0, min(self.limits["wall_s"] - elapsed,
                    owner_left("wall_s_remaining", elapsed, self.limits["wall_s"])))}

    def _contract_errors(self, site, output, batch=None):
        """Classify complete, accounted public output; never parse/repair raw text."""
        if not self.max_contract_corrections or not self.callback_records:
            return []
        record = self.callback_records[-1]
        response = record.get("response", {})
        payload = response.get("payload") if isinstance(response, dict) else None
        if (record["request"]["site"] != site or not isinstance(payload, dict) or
                response.get("provider_status", "COMPLETE") not in SUCCESS or
                self.harness.blocked or record.get("consumed_payload") != payload):
            return []
        usage = response.get("usage", {})
        if usage.get("status") != ("SOFTWARE_FIXTURE" if self.fixture_mode else "KNOWN"):
            return []
        if payload.get("status") == "JSON_SYNTAX_ERROR":
            diagnostic = payload.get("syntax_error", {})
            original_hash = payload.get("original_output_sha256")
            if (output.get("status") != "JSON_SYNTAX_ERROR" or
                    response.get("provider_status") != "COMPLETE" or
                    not isinstance(response.get("error"), str) or not response["error"] or
                    diagnostic.get("kind") != "JSONDecodeError" or
                    any(type(diagnostic.get(k)) is not int or diagnostic[k] < minimum
                        for k, minimum in (("line", 1), ("column", 1), ("position", 0))) or
                    not isinstance(original_hash, str) or len(original_hash) != 64 or
                    any(c not in "0123456789abcdef" for c in original_hash)):
                return []
            return [{"code": "JSON_SYNTAX_ERROR", "fields": ["complete_output"],
                     "candidate_id": None, "syntax_error": _copy(diagnostic)}]
        if payload.get("status", "OK") != "OK":
            return []
        fields = {
            "READ_ACTION_HAS_EDIT": ["actual_input.operation", "actual_input.design_patch"],
            "ACTION_FIELDS_OUTSIDE_CONTRACT": ["actual_input"],
            "UNKNOWN_OPERATION": ["actual_input.operation"],
            "PROBLEM_CANNOT_EDIT_TASK_OR_EVALUATOR": ["actual_input.problem_patch", "actual_input.design_patch"],
            "PROBLEM_FIELD_TYPES": ["actual_input.problem_patch"],
            "PROBLEM_ACTIVE_DOMAIN": ["actual_input.problem_patch.active_variables", "actual_input.problem_patch.groups"],
            "EDIT_OUTSIDE_ACTIVE_VARIABLES": ["actual_input.design_patch", "actual_input.problem_patch.active_variables"],
            "FIXED_CHOICE_CHANGED_WITHOUT_REFORM": ["actual_input.design_patch", "actual_input.problem_patch.fixed_choices"],
            "UNREGISTERED_REFINEMENT": ["actual_input.dt_s"],
            "CANDIDATE_FIELDS_OR_ID": ["candidate", "id"],
            "OPERATION_MISMATCH": ["operation", "actual_input.operation"],
            "REFORM_CANNOT_EDIT_TASK": ["problem_reforms", "actual_input.problem_patch"],
            "CANDIDATE_COST_BOUND": ["cost_bound"],
        }
        def error(code, candidate_id=None):
            prefix, _, detail = code.partition(":")
            field = fields.get(prefix, ["candidate"])
            if prefix in {"DESIGN_DOMAIN", "DESIGN_TYPE", "MECHANISM_DOMAIN"}:
                field = ["actual_input.design_patch" + ("." + detail if detail else "")]
            return {"code": code, "fields": field, "candidate_id": candidate_id}
        if site == "H-GEN":
            rejected = output.get("rejected", [])
            if rejected:
                return [error(item["reason"], item.get("id")) for item in rejected]
            if output.get("status") == "CANDIDATE_CAP_EXCEEDED":
                return [{"code": "CANDIDATE_CAP_EXCEEDED", "fields": ["candidates", "experiment_candidates"],
                         "candidate_id": None}]
            if output.get("status") == "INVALID_PLANNER_OUTPUT":
                return [{"code": "CANDIDATE_CONTAINER_TYPE", "fields": [key], "candidate_id": None}
                        for key, kind, default in (("candidates", list, []), ("experiment_candidates", list, []),
                                                   ("problem_reforms", dict, {}))
                        if not isinstance(payload.get(key, default), kind)]
        elif site == "H-UPDATE" and output.get("status") == "UPDATE_CONTRACT_REJECTED":
            return [{"code": "UPDATE_FIELDS_OUTSIDE_CONTRACT", "fields": sorted(set(payload) - UPDATE_FIELDS),
                     "candidate_id": None}]
        elif site == "H-RANK" and output.get("status") == "INVALID_SELECTION":
            errors = []
            if payload.get("selected_id") not in [c["id"] for c in batch["candidates"]]:
                errors.append({"code": "SELECTED_ID_NOT_IN_CANDIDATES", "fields": ["selected_id"],
                               "candidate_id": payload.get("selected_id")})
            if not payload.get("selection_basis"):
                errors.append({"code": "SELECTION_BASIS_REQUIRED", "fields": ["selection_basis"],
                               "candidate_id": payload.get("selected_id")})
            return errors
        elif site == "H-RANK" and output.get("status") == "CONTRACT_REJECTED":
            return [error(output["reason"], payload.get("selected_id"))]
        return []

    def _record_contract_error(self, site, output, errors, step, batch=None):
        """Append factual public evidence; never turn it into a scientific Result."""
        record = self.callback_records[-1]
        payload = record["response"]["payload"]
        identities = []
        for key in ("candidates", "experiment_candidates"):
            if isinstance(payload.get(key), list):
                identities.extend({"collection": key, "index": n,
                                   "id": c.get("id") if isinstance(c, dict) else None,
                                   "sha256": digest(c)} for n, c in enumerate(payload[key]))
        self.consecutive_contract_errors += 1
        reason = self._stop_reason(self._quota(), needs_action=site != "H-UPDATE")
        if reason is None and self.consecutive_contract_errors > self.max_contract_corrections:
            reason = "CONTRACT_CORRECTION_LIMIT_EXCEEDED"
        syntax = payload.get("status") == "JSON_SYNTAX_ERROR"
        fact = {"kind": "OUTPUT_SYNTAX_ERROR" if syntax else "ACTION_CONTRACT_ERROR",
                "origin": "PUBLIC_JSON_PARSE_DIAGNOSTIC" if syntax else "FIXED_CONTRACT_VALIDATION", "site": site,
                "output_protocol": OUTPUT_PROTOCOL,
                "execution_status": "NO_EXECUTION", "numerical_inputs": 0, "scientific_result": False,
                "prior_action_already_executed": site == "H-UPDATE", "additional_tool_executions": 0,
                "allowed_for_learning": False, "validation_status": output.get("status"), "errors": errors,
                "source_callback_index": len(self.callback_records) - 1,
                "source_request_sha256": record["request_sha256"], "original_payload_sha256": digest(payload),
                "original_candidate_identities": identities, "original_selected_id": payload.get("selected_id"),
                "supplied_candidate_identities": [{"id": c["id"], "sha256": digest(c)}
                                                  for c in (batch or {}).get("candidates", [])],
                "allowed_operations": sorted(OPERATIONS & set(self.state["task"].get("allowed_operations", OPERATIONS))),
                "design_patch_forbidden_operations": ["observe", "verify", "report", "select"],
                "max_candidates": self._quota()["max_candidates"],
                "consecutive_errors": self.consecutive_contract_errors,
                "max_contract_corrections": self.max_contract_corrections, "correction_available": reason is None}
        if syntax:
            fact.update(syntax_error=_copy(payload["syntax_error"]),
                        original_output_sha256=payload["original_output_sha256"])
        fact["public_return_contract"] = planner_instructions(record["request"]).split("Declared decision program: ")[0]
        self.contract_feedback.append(_copy(fact))
        self.state.setdefault("evidence", []).append(_copy(fact))
        step.setdefault("contract_feedback", []).append(_copy(fact))
        if reason:
            self.finish(reason)
        return reason is None

    def _stop_reason(self, quota, *, needs_model=True, needs_action=True):
        if self.harness.blocked:
            return "MISSING_USAGE"
        if needs_model and quota["output_tokens_left"] <= 0:
            return "OUTPUT_TOKEN_BUDGET_EXHAUSTED"
        if quota["wall_s_left"] <= 0:
            return "WALL_BUDGET_EXHAUSTED"
        if needs_model and quota["provider_requests_left"] <= 0:
            return "MODEL_REQUEST_BUDGET_EXHAUSTED"
        if needs_model and not self.fixture_mode and quota["usd_left"] < self.request_reserve_usd:
            return "MODEL_COST_BUDGET_EXHAUSTED"
        if needs_action and quota["remaining_actions"] <= 0:
            return "TOOL_BUDGET_EXHAUSTED"
        return None

    def _take_conclusion(self, value):
        if not isinstance(value, dict) or value.get("verdict") not in {"PASS", "FAIL", "UNKNOWN"} or not value.get("basis") or not value.get("scope"):
            return False
        self.model_conclusion = {**_copy(value), "origin": "MODEL_SELF_ASSESSMENT",
                                 "independent_evaluation": False}
        return True

    def next(self, budget_snapshot=None):
        if self.pending is not None:
            raise ContractError("UPDATE_OR_FINISH_PENDING_DECISION_FIRST")
        if self.termination is not None:
            return {"status": "STOPPED", "reason": self.termination["reason"], "decision": None,
                    "step": len(self.steps)}
        if budget_snapshot is not None:
            if "output_tokens_remaining" in budget_snapshot and (
                    type(budget_snapshot["output_tokens_remaining"]) is not int or
                    budget_snapshot["output_tokens_remaining"] < 0):
                raise ContractError("OUTPUT_TOKEN_REMAINDER_MUST_BE_NONNEGATIVE_INT")
            self.owner_budget = _copy(budget_snapshot)
            self.owner_snapshot_base = {
                "provider_requests_remaining": len(self.harness.usage_ledger),
                "reserve_usd_remaining": sum(r.get("usage", {}).get("cost", 0) or 0 for r in self.harness.usage_ledger),
                "tool_calls_remaining": self.tool_calls, "new_numerical_inputs_remaining": self.numerical_inputs,
                "wall_s_remaining": time.monotonic() - self.started_at}
            self.output_snapshot_base_used = self._output_tokens_used()
        quota = self._quota()
        reason = self._stop_reason(quota)
        if reason:
            self.finish(reason)
            return self.next()
        step = {"step": len(self.steps), "state_before": _copy(self.state), "quota_before": quota,
                "generate": None, "select": None, "result": None, "update": None}
        self.steps.append(step)
        start = len(self.harness.program.calls)
        batch = self.harness.generate(self.state, quota)
        step["generate"] = _copy(batch)
        if batch.get("status") == "STOPPED" and "conclusion" in batch:
            valid = self._take_conclusion(batch["conclusion"])
            step["site_calls"] = _copy(self.harness.program.calls[start:])
            self.finish("MODEL_STOPPED" if valid else "INVALID_TERMINAL_CONCLUSION")
            return self.next()
        errors = self._contract_errors("H-GEN", batch)
        if errors:
            step["site_calls"] = _copy(self.harness.program.calls[start:])
            self._record_contract_error("H-GEN", batch, errors, step)
            return self.next()
        if batch.get("status") != "READY":
            step["site_calls"] = _copy(self.harness.program.calls[start:])
            self.finish(batch.get("status", "INVALID_PLANNER_OUTPUT"))
            return self.next()
        while True:
            reason = self._stop_reason(self._quota(), needs_model=self.harness.selection_uses_model)
            if reason:
                step["site_calls"] = _copy(self.harness.program.calls[start:])
                self.finish(reason)
                return self.next()
            decision = self.harness.select(self.state, batch, self._quota())
            step["select"] = _copy(decision)
            if self.max_contract_corrections:
                step.setdefault("select_attempts", []).append(_copy(decision))
            step["site_calls"] = _copy(self.harness.program.calls[start:])
            errors = self._contract_errors("H-RANK", decision, batch)
            if errors:
                if self._record_contract_error("H-RANK", decision, errors, step, batch):
                    continue
                return self.next()
            if decision.get("status") != "READY" or decision.get("actual_input") is None:
                self.finish(decision.get("status", "INVALID_SELECTION"))
                return self.next()
            break
        if self._quota()["wall_s_left"] <= 0:
            self.finish("WALL_BUDGET_EXHAUSTED_AFTER_SELECTION")
            return self.next()
        step["scope_effect"] = scope_effect(self.state, decision["actual_input"])
        step["pre_action_predictions"] = [
            {"candidate_id": c["id"], "prediction_or_unknown": c["prediction_or_unknown"],
             "observation_branches": c["observation_branches"]} for c in batch["candidates"]]
        step["unselected_ids"] = [c["id"] for c in batch["candidates"] if c["id"] != decision["selected_id"]]
        step["decision_sha256_before_execution"] = digest(decision)
        self.pending = _copy(decision)
        return {"status": "ACTION", "decision": _copy(decision), "step": step["step"]}

    def update(self, public_result):
        if self.pending is None or self.termination is not None:
            raise ContractError("NO_PENDING_DECISION")
        result, decision = _copy(public_result), self.pending
        step = self.steps[-1]
        step["result"] = result
        step["result_sha256"] = digest(result)
        self.tool_calls += 1
        usage = result.get("usage", {})
        inputs = usage.get("numerical_inputs")
        if type(inputs) is not int or inputs < 0:
            self.finish("TOOL_USAGE_UNKNOWN")
            return {"status": "STOPPED", "reason": "TOOL_USAGE_UNKNOWN"}
        self.numerical_inputs += inputs
        actual = decision["actual_input"]
        if result.get("execution_status") in SUCCESS:
            expected_design = {**self.state.get("design", {}), **actual.get("design_patch", {})}
            expected_problem = {**self.state.get("problem", {}), **actual.get("problem_patch", {})}
            if result.get("design") != expected_design or result.get("problem") != expected_problem:
                self.finish("CONSUMED_INPUT_MISMATCH")
                return {"status": "STOPPED", "reason": "CONSUMED_INPUT_MISMATCH"}
        start = len(self.harness.program.calls)
        # Retry only the model's UPDATE output against the same completed tool
        # result and pre-action state. Each attempt builds one history record;
        # only the final state is committed. No external tool is called here.
        while True:
            self.harness.quota = self._quota()
            callback_start = len(self.callback_records)
            new_state = self.harness.update(self.state, decision, result)
            update_output = {"status": new_state.get("update_status")}
            errors = self._contract_errors("H-UPDATE", update_output) if len(self.callback_records) > callback_start else []
            step.setdefault("update_attempts", []).append(_copy(update_output))
            if not errors:
                break
            retry = self._record_contract_error("H-UPDATE", update_output, errors, step)
            new_state["evidence"] = _copy(self.state.get("evidence", []))
            if not retry:
                break
        step["site_calls"].extend(_copy(self.harness.program.calls[start:]))
        step["update"] = {"status": new_state.get("update_status"), "design": new_state.get("design"),
                          "problem": new_state.get("problem"), "hypotheses": new_state.get("hypotheses", []),
                          "invalidated": new_state.get("invalidated", []), "next_evidence": new_state.get("next_evidence")}
        self.state, self.pending = new_state, None
        if (new_state.get("update_status") == "UPDATED" and result.get("execution_status") in SUCCESS
                and result.get("model_valid") is True):
            self.consecutive_contract_errors = 0
        if self.numerical_inputs > self.limits["new_numerical_inputs"]:
            self.finish("NUMERICAL_BUDGET_EXCEEDED")
        elif new_state.get("update_status") in {"TOOL_ERROR", "INCOMPLETE"} and result.get("execution_status") != "NO_EXECUTION":
            self.finish(new_state["update_status"])
        elif new_state.get("update_status") not in {"UPDATED", "DOMAIN_UNKNOWN", "INCOMPLETE"}:
            self.finish(new_state.get("update_status", "INVALID_UPDATE"))
        elif actual["operation"] == "report":
            self._take_conclusion(decision.get("selected_candidate", {}).get("conclusion"))
            self.finish("MODEL_REPORT")
        return {"status": "STOPPED" if self.termination else "UPDATED", "update_status": new_state.get("update_status"),
                "design": _copy(new_state.get("design", {})), "problem": _copy(new_state.get("problem", {}))}

    def finish(self, reason):
        if self.termination is None:
            self.termination = {"reason": reason, "wall_elapsed_s": time.monotonic() - self.started_at,
                                "selected_action_unexecuted": self.pending is not None and self.steps[-1]["result"] is None}
            self.pending = None
        return self.transcript()

    def transcript(self):
        return _copy({"schema": "pqe-episode-transcript-v1", "output_protocol": OUTPUT_PROTOCOL,
                      "episode_id": self.episode_id,
                      "condition": self.condition, "model_identity": self.model_identity,
                      "evidence_class": "SOFTWARE_FIXTURE" if self.fixture_mode else "REAL_CALLBACK_DRIVER",
                      "limits": self.limits, "request_reserve_usd": self.request_reserve_usd,
                      "contract_corrections": {"maximum": self.max_contract_corrections,
                                               "consecutive_errors": self.consecutive_contract_errors,
                                               "feedback": self.contract_feedback},
                      "output_budget": {"used": self._output_tokens_used(),
                                        "remaining": self._quota()["output_tokens_left"],
                                        "total_limit": self.limits["output_tokens_total"]},
                      "frozen_methods_sha256": self.methods_sha256, "initial_state": self.initial_state,
                      "common_history_sha256": self.common_history_sha256,
                      "loaded_program_sha256": digest(self.harness.program.artifact),
                      "steps": self.steps, "callback_records": self.callback_records,
                      "usage_ledger": self.harness.usage_ledger,
                      "counts": {"callback_attempts": len(self.callback_records), "tool_calls": self.tool_calls,
                                 "new_numerical_inputs": self.numerical_inputs},
                      "final_state": self.state, "model_conclusion": self.model_conclusion,
                      "termination": self.termination,
                      "independent_final_evaluation": "S0_OWNED_NOT_GIVEN_TO_PLANNER",
                      "h_g_formation": False, "generated_code_loaded": bool(self.harness.program.hooks)})
