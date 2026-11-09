"""F1 first formation: same parent/history/edit rights, external adoption.

This module never imports a task registry, scientific tool, provider or ledger.
S0 owns the callback and the independent selection/confirmation executions.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from .methods import (ContractError, EDIT_FIELDS, H_SITES, Improver, PATCH_FIELDS,
                      UPDATE_FIELDS, common_contract_check, digest, load_program, seed_program)
from .episode_methods import EpisodeDriver
from .restricted_worker import run_isolated_hook

CONDITIONS = {"H0": "fixed_parent", "H1": "same_history_parent", "H2": "general_program",
              "H3": "developer_fixed_rules", "H4": "attribution"}
FIXTURE_KINDS = ("APPLICABLE", "NOT_APPLICABLE", "INSUFFICIENT_EVIDENCE", "TOOL_ERROR")


def load_f1_program(artifact):
    return load_program(artifact, hook_runner=run_isolated_hook)


def formation_instructions(request):
    common = ("Return exactly one JSON object without Markdown fences. You form an H program, not a task solution. "
        "Use only supplied reviewed public incidents; no target/selection/confirmation task is supplied. "
        "The fixed parent, scientific semantics, permissions, accounting, quotas and adoption rules are immutable. "
        "Do not embed task IDs, remembered repair constants or future answers in executable rules. "
        "H2 and H4 have exactly the same six sites, code/prompt/config/equality-condition edit space and budgets. "
        "A valid no-update is allowed. JSON syntax correction never authorizes semantic repair or extra proposals. ")
    site = request["site"]
    if site == "G-ATTRIBUTE":
        schema = ("Return {status:'OK',explanations:[{kind,support,refutation,missing_discrimination,target_sites}]}. "
            "kind must be H_OR_G_DEFECT, CONSUMER_GAP, TASK_UNDERSPECIFIED, ENGINEERING_INFEASIBILITY or UNRESOLVED. "
            "Compare competing explanations, including evidence against an H defect. support/refutation must cite incidents. "
            "If no supported H defect warrants a change, retain uncertainty and no update.")
    elif site == "G-PROPOSE":
        schema = ("Return {status:'OK',patches:[...]} with at most TWO raw proposals; invalid proposals also consume this cap. "
            "Each patch must contain exactly the required fields " + json.dumps(sorted(PATCH_FIELDS)) + ". "
            "parent_program and parent_sha256 must bind the supplied parent (parent_sha256 is provided in context). "
            "source_incidents is a nonempty subset of supplied incident_id values. target_sites is a nonempty subset of "
            + json.dumps(list(H_SITES)) + ". change maps any of " + json.dumps(sorted(EDIT_FIELDS)) +
            " to dictionaries keyed by those sites. applicability and non_trigger_conditions map site to dotted-context-path "
            "equalities; empty maps mean unconditional. predicted_behavior_change, side_effects, behavior_tests, "
            "full_task_test_plan and falsifier must be nonempty and conditional. "
            "prompts are site-specific strings, config is JSON supplied as ctx.site_config. "
            "code values are Python SOURCE STRINGS in this JSON, defining exactly h_gen/h_rank/h_exp/h_update/h_reform/h_stop(ctx, ask) "
            "for the named site, with optional helper_ functions. No imports, private names, arbitrary attributes, IO, "
            "network, subprocess, exceptions, while or decorators. Use dict/list/get and finite bounded loops. "
            "ask('H-GEN',ctx) (or the current site) calls the same accountable model interface, returning its payload. "
            "Only the CURRENT site may be asked; deterministic functions need no callback. "
            "H-GEN returns candidate output/STOPPED exactly as the solve contract; H-RANK selects a supplied candidate; "
            "H-EXP returns {candidates:[]}; H-REFORM returns {candidate_patches:{}}; H-UPDATE only returns optional "
            "hypotheses/invalidated/next_evidence/strategy, never Design or an action; H-STOP returns {stop,reason,scope}. "
            "The contexts include state/quota; RANK also candidates; EXP/REFORM also generated; UPDATE also decision/result. "
            "Prompts/config actually enter the corresponding requests and deterministic branches; code runs in a separate "
            "capability-restricted process. Never claim that AST checks alone are an OS sandbox. "
            "No patch is adopted merely by being generated or passing four software behavior inputs.")
        if request.get("protocol") == "general_program":
            schema += " Perform strong general trajectory reflection and propose useful executable program revisions; no imposed engineering attribution taxonomy."
        else:
            schema += " Use extracted incidents and competing engineering attribution to propose a conditional H change or no update."
    else:
        raise ContractError("UNEXPECTED_FORMATION_CALLBACK_SITE")
    return common + schema


def _fixture_context(kind):
    task = {"task_id": "behavior-input", "allowed_operations": ["observe", "edit", "verify", "report"],
            "design_domain": {"x": {"kind": "number", "min": 0, "max": 1}}}
    result = {"execution_status": "COMPLETE", "model_valid": True, "domain_errors": [],
              "design": {"x": .5}, "problem": {"active_variables": ["x"], "fixed_choices": {}, "groups": [["x"]]},
              "facts": {}, "public_check": {"verdict": "FAIL"}, "usage": {"numerical_inputs": 0}}
    if kind == "NOT_APPLICABLE":
        result["public_check"]["verdict"] = "PASS"
    elif kind == "INSUFFICIENT_EVIDENCE":
        result["public_check"] = {"verdict": "UNKNOWN"}
    elif kind == "TOOL_ERROR":
        result.update(execution_status="TOOL_ERROR", model_valid=False,
                      public_check={"verdict": "UNKNOWN"})
    state = {"task": task, "design": result["design"], "problem": result["problem"],
             "last_result": result, "history": [], "evidence": [], "hypotheses": [],
             "applicability": "IN_SCOPE" if kind != "NOT_APPLICABLE" else "OUT_OF_SCOPE"}
    candidate = {"id": "public-probe", "target": "current", "operation": "verify",
        "expected_state_change": "no Design change", "prediction_or_unknown": "UNKNOWN", "observation_branches": [],
        "affected_constraints": [], "cost_bound": 1, "validity_conditions": [],
        "actual_input": {"operation": "verify", "design_patch": {}, "problem_patch": {}}}
    return {"state": state, "quota": {"remaining_actions": 2, "remaining_cost": 2, "max_candidates": 4,
                "wall_s_left": 30}, "generated": {"candidates": [candidate]}, "candidates": [candidate],
            "decision": {"selected_id": candidate["id"], "actual_input": candidate["actual_input"]}, "result": result}


def _fixture_default(site, ctx):
    if site == "H-GEN": return {"status": "OK", "candidates": ctx["generated"]["candidates"]}
    if site == "H-RANK": return {"selected_id": ctx["candidates"][0]["id"], "selection_basis": "public fixture only"}
    if site == "H-EXP": return {"candidates": []}
    if site == "H-REFORM": return {"candidate_patches": {}}
    if site == "H-UPDATE": return {"hypotheses": [], "next_evidence": "UNKNOWN"}
    return {"stop": ctx["state"].get("applicability") == "OUT_OF_SCOPE", "reason": "local software input", "scope": "current input"}


def _check_fixture(site, value, ctx):
    if not isinstance(value, dict): raise ContractError("FIXTURE_NOT_OBJECT")
    if value.get("status", "OK") not in {"OK", "READY", "STOPPED"}:
        raise ContractError("FIXTURE_HOOK_STATUS:" + str(value.get("status")))
    if site == "H-GEN" and value.get("status") == "STOPPED":
        conclusion = value.get("conclusion", {})
        if conclusion.get("verdict") not in {"PASS", "FAIL", "UNKNOWN"} or not conclusion.get("basis") or not conclusion.get("scope"):
            raise ContractError("FIXTURE_TERMINAL_CONTRACT")
        if conclusion["verdict"] != "UNKNOWN" and any(x in conclusion["scope"].lower() for x in ("global", "all legal", "legal domain", "全域")):
            raise ContractError("FIXTURE_UNSUPPORTED_GLOBAL")
        if ctx["result"]["public_check"]["verdict"] == "UNKNOWN" and conclusion["verdict"] == "PASS":
            raise ContractError("FIXTURE_WRONG_ADOPTION")
    elif site in {"H-GEN", "H-EXP"}:
        candidates = value.get("candidates", [])
        if not isinstance(candidates, list) or len(candidates) > 4: raise ContractError("FIXTURE_CANDIDATE_CAP")
        for candidate in candidates:
            common_contract_check(ctx["state"], candidate["actual_input"], ctx["quota"])
    elif site == "H-RANK":
        if value.get("selected_id") not in [c["id"] for c in ctx["candidates"]] or not value.get("selection_basis"):
            raise ContractError("FIXTURE_SELECTION")
    elif site == "H-UPDATE":
        if set(value) - UPDATE_FIELDS: raise ContractError("FIXTURE_UPDATE_AUTHORITY")
    elif site == "H-REFORM":
        patches = value.get("candidate_patches", {})
        if not isinstance(patches, dict): raise ContractError("FIXTURE_REFORM")
        for key, patch in patches.items():
            if key not in [c["id"] for c in ctx["candidates"]]: raise ContractError("FIXTURE_REFORM_CANDIDATE")
            common_contract_check(ctx["state"], {"operation": "restructure", "design_patch": {}, "problem_patch": patch}, ctx["quota"])
    elif site == "H-STOP":
        if type(value.get("stop")) is not bool or not value.get("scope") or not value.get("reason"):
            raise ContractError("FIXTURE_STOP")
        if value["stop"] and any(x in value["scope"].lower() for x in ("global", "all legal", "legal domain", "全域")):
            raise ContractError("FIXTURE_UNSUPPORTED_GLOBAL")


def screen_program(program, consume=None):
    """Four public behavior inputs, never a target task or physical evaluation."""
    loaded = load_f1_program(program)
    local_units = []
    if consume is None:
        def consume(kind, **detail):
            if len(local_units) >= 24:
                raise ContractError("FORMATION_TOOL_OR_CALLBACK_CAP")
            local_units.append({"kind": kind, **detail})
    rows = []
    for kind in FIXTURE_KINDS:
        ctx = _fixture_context(kind)
        asks, outputs = [], {}
        try:
            consume("LOCAL_FIXTURE_INPUT", program_id=program["program_id"], kind_name=kind)
            for site in H_SITES:
                def ask(requested_site, payload):
                    if requested_site != site: raise ContractError("FIXTURE_ASK_SITE")
                    entry = {"site": site, "payload_sha256": digest(payload), "usage": {"status": "NOT_EXECUTED"}}
                    asks.append(entry)
                    consume("LOCAL_FIXTURE_ASK", program_id=program["program_id"], kind_name=kind, site=site)
                    entry["usage"] = {"status": "SOFTWARE_FIXTURE", "provider_requests": 0}
                    return _fixture_default(site, {**ctx, **payload})
                value = loaded.invoke(site, ctx, ask, lambda c: _fixture_default(site, c))
                _check_fixture(site, value, ctx)
                outputs[site] = value
            rows.append({"kind": kind, "outcome": "PASS", "input_sha256": digest(ctx), "outputs": outputs, "asks": asks})
        except Exception as exc:
            rows.append({"kind": kind, "outcome": "ERROR", "error": str(exc), "input_sha256": digest(ctx), "outputs": outputs, "asks": asks})
    return {"program_id": program["program_id"], "phase": "local",
            "outcome": "PASS" if all(x["outcome"] == "PASS" for x in rows) else "ERROR",
            "fixtures": rows, "actual_invocations": loaded.calls,
            "usage": {"status": "SOFTWARE_FIXTURE", "provider_requests": 0, "numerical_inputs": 0},
            "claim_boundary": "Software behavior/permissions only; no engineering feasibility or benefit."}


class FormationDriver(EpisodeDriver):
    def __init__(self, condition, planner_callback, *, parent, history, episode_id,
                 model_identity, request_reserve_usd, limits=None, fixture_mode=False):
        if condition not in {"H2", "H4"}: raise ContractError("FORMATION_CONDITION")
        load_f1_program(parent)
        if any(i.get("allowed_for_learning") is not True for i in history):
            raise ContractError("FORMATION_HISTORY_PERMISSION")
        current_hash = hashlib.sha256(Path(__file__).with_name("methods.py").read_bytes()).hexdigest()
        super().__init__("strong_generic", planner_callback, episode_id=episode_id, initial_state={"task": {}},
            model_identity=model_identity, request_reserve_usd=request_reserve_usd, limits=limits,
            fixture_mode=fixture_mode, max_contract_corrections=2, expected_methods_sha256=current_hash)
        self.condition, self.parent, self.history = condition, deepcopy(parent), deepcopy(history)
        self.harness = Improver(CONDITIONS[condition], self._callback, fixture_mode=fixture_mode)
        self.format_feedback = []
        self.formation_units = []
        self.ran = False

    def _consume_unit(self, kind, **detail):
        if len(self.formation_units) >= 24:
            raise ContractError("FORMATION_TOOL_OR_CALLBACK_CAP")
        if time.monotonic() - self.started_at >= self.limits["wall_s"]:
            raise ContractError("FORMATION_WALL_CAP")
        self.formation_units.append({"index":len(self.formation_units), "kind":kind, **detail})

    def _instructions(self, request):
        return formation_instructions(request)

    def _callback(self, request):
        self._consume_unit("ACCOUNTABLE_MODEL_CALLBACK", site=request["site"])
        request = deepcopy(request)
        if "parent" in request.get("context", {}):
            request["context"]["parent_sha256"] = digest(self.parent)
        if self.format_feedback:
            request["context"]["formation_format_feedback"] = deepcopy(self.format_feedback)
        return super()._callback(request)

    def _stage(self, fn):
        while True:
            reason = self._stop_reason(self._quota(), needs_action=False)
            if reason: return {"status": reason, "incidents": [], "programs": []}
            self.harness.quota = self._quota()
            callback_start = len(self.callback_records)
            output = fn()
            if len(self.callback_records) == callback_start: return output
            last = self.callback_records[-1]
            payload = last.get("response", {}).get("payload", {})
            if payload.get("status") != "JSON_SYNTAX_ERROR": return output
            response = last["response"]
            valid = (response.get("provider_status") == "COMPLETE" and response.get("usage", {}).get("status") == "KNOWN"
                     and bool(response.get("error")) and payload.get("syntax_error", {}).get("kind") == "JSONDecodeError")
            if not valid or len(self.format_feedback) >= 2: return output
            self.format_feedback.append({"code": "JSON_SYNTAX_ERROR", "syntax_error": payload["syntax_error"],
                "original_output_sha256": payload.get("original_output_sha256"), "source_callback_index": len(self.callback_records)-1,
                "no_semantic_repair": True})

    def run(self):
        if self.ran: raise ContractError("FORMATION_ALREADY_RUN")
        self.ran = True
        extracted = self.harness.extract(self.history)
        attribution = self._stage(lambda: self.harness.attribute(extracted, self.parent))
        proposals = self._stage(lambda: self.harness.propose(attribution, self.parent, {**self._quota(), "max_proposals": 2}))
        raw = [{"callback_index": n, "payload": deepcopy(c.get("consumed_payload"))}
               for n,c in enumerate(self.callback_records) if c["request"]["site"] == "G-PROPOSE"]
        original_count = sum(len(x["payload"].get("patches", [])) if isinstance(x["payload"], dict) and isinstance(x["payload"].get("patches"), list)
            else int(isinstance(x["payload"], dict) and x["payload"].get("status") != "JSON_SYNTAX_ERROR") for x in raw)
        evaluations = []
        if original_count <= 2 and not self.harness.blocked:
            for item in proposals.get("programs", []):
                # Common ID memorization guard; no target instances are inspected.
                text = json.dumps({k:item["patch"][k] for k in ("change", "applicability", "non_trigger_conditions")})
                if "DOOR-DEV-" in text or "DOOR-CONFIRM-" in text or "DOOR-SELECT-" in text:
                    evaluations.append({"program_id":item["program"]["program_id"], "phase":"local", "outcome":"ERROR",
                        "error":"TASK_ID_MEMORIZATION", "fixtures":[], "usage":{"status":"SOFTWARE_FIXTURE"}})
                else:
                    evaluations.append(screen_program(item["program"], consume=self._consume_unit))
        allocation = self.harness.allocate(proposals, evaluations,
            {**self._quota(), "evaluation_calls_remaining": 1 if original_count <= 2 else 0})
        selected = next((x["program"] for x in proposals.get("programs", [])
            if x["program"]["program_id"] == allocation.get("program_id") and allocation.get("status") == "SCREEN"
            and allocation.get("next") == "selection"), None)
        return {"schema":"pqe-f1first-formation-v1", "condition":self.condition, "episode_id":self.episode_id,
            "parent_sha256":digest(self.parent), "common_history_sha256":digest(self.history),
            "extracted":extracted, "attribution":attribution, "proposals":proposals,
            "raw_proposals":raw, "raw_proposal_count":original_count, "max_raw_proposals":2,
            "local_evaluations":evaluations, "allocation":allocation,
            "tools_or_callbacks":{"limit":24,"consumed":len(self.formation_units),"events":self.formation_units,
                "counting_rule":"One unit per accountable model callback, per local behavior input and per emulated fixture ask. Deterministic site invokes are internal computation and separately retained, not broker tools. Fixture asks dispatch no provider."},
            "selected_program":deepcopy(selected or self.parent), "selected_candidate":selected is not None,
            "parent_retained":selected is None, "adoption":"EXTERNAL_SELECTION_NOT_YET_RUN",
            "callback_records":deepcopy(self.callback_records), "usage_ledger":deepcopy(self.harness.usage_ledger),
            "format_feedback":self.format_feedback, "methods_sha256":self.methods_sha256,
            "wall_s":time.monotonic()-self.started_at,
            "claim_boundary":"Automatic proposed H only; local fixtures are software evidence, not learning benefit or adoption."}
