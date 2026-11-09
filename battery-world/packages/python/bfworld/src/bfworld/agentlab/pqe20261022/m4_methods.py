"""Finite M4 selection correction; saved diagnostics and original-run facts only.

No predictor, solver, provider, file reads, parameter search or state simulator.
The host supplies the explicitly public proposal and owns full-run accounting.
"""
from copy import deepcopy

from .methods import Harness, ContractError, common_contract_check, digest, load_program, public_state, seed_program
from .m3_methods import M3ServiceHarness
from .dynamic_methods import SUCCESS, _number

VERSION = "H-executable-select-m4-v1"
REGRESSION_TASK_ID = "DOOR-M2-START-TX-20261023-v1"


def extract_trajectory_facts(task, design, result):
    from .trajectory_service_facts import extract_trajectory_facts as extract
    return extract(task, design, result)


def _program():
    p = seed_program()
    p.update(program_id=VERSION, origin="DEVELOPER_FIXED_SELECTION_CORRECTION", adoption="M4_DEVELOPMENT_ONLY")
    sites = {"H-STOP": ("h_stop", "M4-STOP"), "H-GEN": ("h_gen", "M4-GENERATE"),
             "H-RANK": ("h_rank", "M4-SELECT"), "H-UPDATE": ("h_update", "M4-UPDATE")}
    p["code"] = {s: f'def {name}(ctx, ask):\n    return ask("{target}", ctx)\n'
                 for s, (name, target) in sites.items()}
    p["config"] = {s: {"version": VERSION, "model_callbacks": 0} for s in sites}
    return load_program(p)


def _receipt(result):
    return {k: deepcopy(result[k]) for k in ("task_id", "task_sha256", "input_sha256", "result_sha256",
            "execution_status", "model_valid", "domain_errors", "design", "public_check") if k in result}


def _pass6(result):
    check = result.get("public_check", {})
    return (result.get("execution_status") in SUCCESS and result.get("model_valid") is True
            and check.get("verdict") == "PASS" and check.get("received_count") == 6
            and not check.get("failures") and not check.get("unknown")
            and len(result.get("facts", {}).get("receiver_records", [])) == 6)


def _experiment(candidate):
    e = candidate.get("experiment", {})
    return (isinstance(e, dict) and bool(e.get("rationale"))
            and isinstance(e.get("hypotheses"), list) and bool(e["hypotheses"])
            and isinstance(e.get("branches"), list) and len(e["branches"]) >= 2
            and bool(e.get("conditions")))


def _assessment(state, candidate):
    """Read supplied diagnostics; WAIT margin is never a selection coordinate."""
    design = {**state["design"], **candidate["actual_input"].get("design_patch", {})}
    p = candidate.get("service_prediction", {})
    if not isinstance(p, dict):
        p = {}
    if p.get("prediction_status") in {"ERROR", "TOOL_ERROR", "PARSE_OR_TRANSPORT_ERROR"}:
        return {"status": "TOOL_ERROR", "reason": "No scientific observation or rejection follows a predictor error."}
    scope = p.get("scope", {})
    bound = scope.get("task_sha256") == digest(state["task"]) and scope.get("design_sha256") == digest(design)
    if bound:
        failures = [c for c in p.get("necessary_checks", []) if c.get("necessary") is True and c.get("status") == "FAIL"]
        for relation in p.get("relations", []):
            upper = relation.get("value", {}).get("bus_upper_v") if isinstance(relation.get("value"), dict) else None
            if (relation.get("relation_id") == "passive_bus_upper_bound" and relation.get("kind") == "NECESSARY"
                    and relation.get("status") == "KNOWN" and _number(upper) and design.get("tx_gate_v", 0) > upper):
                failures.append({"name": "TX_GATE_ABOVE_PASSIVE_BUS_UPPER_BOUND", "upper_v": upper,
                                 "gate_v": design["tx_gate_v"], "conditions": relation.get("conditions", [])})
        if failures:
            return {"status": "REJECT_CANDIDATE_NECESSARY", "failures": failures, "scope": "This candidate only, not a family/domain."}
    service, metrics = p.get("service_prediction", {}), p.get("selection_metrics", {})
    windows = service.get("windows", [])
    attempts = [a for w in windows for a in w.get("attempts", [])]
    tx_margins = [a["minimum_terminal_margin_v"] for a in attempts if _number(a.get("minimum_terminal_margin_v"))]
    timely = service.get("conditional_timely_windows")
    unknown = service.get("unknown_windows")
    memory = state.get("strategy", {}).get("executable_select", {})
    baseline = memory.get("trajectory_facts", {}).get("summary", {}).get("timely_public_window_records")
    baseline = baseline if _number(baseline) else None
    supported = (bound and baseline is not None and _number(timely) and timely > baseline
                 and unknown == 0 and len(windows) == 6 and bool(attempts)
                 and sum(w.get("timely") is True for w in windows) == timely
                 and len(tx_margins) == len(attempts) and min(tx_margins) >= 0
                 and all(w.get("attempts") and w.get("ack_completed") is True for w in windows if w.get("timely") is True))
    diagnostics = {"prediction_bound": bound, "conditional_timely": timely,
                   "baseline_observed_timely": baseline, "modeled_attempts": len(attempts),
                   "minimum_modeled_TX_margin_v": min(tx_margins) if tx_margins else None,
                   "WAIT_margin_used_as_gain": False, "service_verdict": "UNKNOWN"}
    if supported:
        return {**diagnostics, "status": "CONDITIONAL_SUPPORTED_IMPROVEMENT_FOR_EXECUTION",
                "scope": "Isolated conditional opportunity only; no adoption/full-service prediction."}
    if _experiment(candidate):
        return {**diagnostics, "status": "DISCRIMINATING_EXPERIMENT", "experiment": deepcopy(candidate["experiment"]),
                "scope": "Test declared explanations; not predicted success or an adopted design."}
    return {**diagnostics, "status": "NO_SUPPORTED_IMPROVEMENT",
            "reason": "Unfavorable or incomplete conditional diagnostics supply no improvement or explicit experiment; retain parent."}


class M4Harness(M3ServiceHarness):
    def __init__(self, development_candidate=None):
        super().__init__()
        self.program = _program()
        self.development_candidate = deepcopy(development_candidate)
        self._proposal_emitted = False

    def _budget(self, quota):
        return super()._budget({**quota, "analytic_scores_left": min(4, quota.get("analytic_scores_left", 0))})

    def _predict(self, *args, **kwargs):
        raise ContractError("M4_READS_SUPPLIED_PREDICTIONS_ONLY")

    def _ask(self, site, ctx):
        if site == "M4-STOP":
            executed = ctx["state"].get("strategy", {}).get("executable_select", {}).get("candidate_execution")
            return {"stop": bool(executed) or ctx["quota"].get("remaining_actions", 0) < 1,
                    "reason": "One candidate only; preserve parent and every execution consequence."}
        if site == "M4-GENERATE":
            return self._generate(ctx)
        if site == "M4-SELECT":
            return self._select(ctx)
        if site == "M4-UPDATE":
            return self._update_service(ctx)
        raise ContractError("M4_UNEXPECTED_HOOK")

    def _generate(self, ctx):
        artifact = self.development_candidate or {}
        proposal = artifact.get("proposal", artifact)
        if self._proposal_emitted or artifact.get("status") == "NO_SUPPORTED_CANDIDATE" or not proposal.get("actual_input"):
            return {"status": "NO_SUPPORTED_IMPROVEMENT", "parent_retained": True, "reason": "No unused justified public development proposal."}
        experiment = {k: deepcopy(proposal.get(k)) for k in ("rationale", "hypotheses", "branches", "conditions")}
        candidate = {"id": proposal.get("id", "public-development-experiment"), "target": "original full six-event service",
                     "operation": proposal["actual_input"]["operation"], "actual_input": deepcopy(proposal["actual_input"]),
                     "expected_state_change": proposal.get("rationale", "UNKNOWN"), "prediction_or_unknown": "UNKNOWN",
                     "observation_branches": deepcopy(proposal.get("branches", [])),
                     "affected_constraints": ["original complete service", "startup", "energy", "deadline", "regression"],
                     "cost_bound": 1, "validity_conditions": deepcopy(proposal.get("conditions", [])),
                     "experiment": experiment, "development_proposal_sha256": digest(artifact),
                     "source_refs": deepcopy(proposal.get("source_refs", [])),
                     "adoption_criteria": "Actual valid fullPASS6, then original task1 valid fullPASS6; otherwise retain parent.",
                     "service_prediction": deepcopy(proposal.get("service_prediction", proposal.get("prediction", {})))}
        if not _experiment(candidate):
            return {"status": "NO_SUPPORTED_IMPROVEMENT", "parent_retained": True, "reason": "Public proposal lacks explicit hypotheses/branches/conditions."}
        self._proposal_emitted = True
        self.decisions.append({"site": "Generate", "proposal_sha256": digest(artifact), "actual_input": candidate["actual_input"]})
        return {"status": "OK", "candidates": [candidate]}

    def _select(self, ctx):
        assessments, choices = [], []
        for candidate in ctx["candidates"]:
            try:
                common_contract_check(ctx["state"], candidate["actual_input"], ctx["quota"])
                assessment = _assessment(ctx["state"], candidate)
            except (ContractError, KeyError, TypeError, ValueError) as exc:
                assessment = {"status": "CONTRACT_REJECTED", "reason": str(exc)}
            assessments.append({"id": candidate.get("id"), **assessment})
            if assessment["status"] in {"CONDITIONAL_SUPPORTED_IMPROVEMENT_FOR_EXECUTION", "DISCRIMINATING_EXPERIMENT"}:
                choices.append((candidate, assessment))
        self.decisions.append({"site": "Select", "assessments": assessments, "prediction_recomputations": 0})
        if not choices:
            return {"status": "NO_SUPPORTED_IMPROVEMENT", "parent_retained": True, "assessments": assessments,
                    "reason": "No supported improvement or explicit discriminating experiment; no global infeasibility claim."}
        # Conditional support precedes declared experiments; submitted order breaks ties, never WAIT voltage.
        chosen, assessment = next((row for row in choices if row[1]["status"] == "CONDITIONAL_SUPPORTED_IMPROVEMENT_FOR_EXECUTION"), choices[0])
        return {"selected_id": chosen["id"], "selection_basis": assessment["status"], "expected_discrimination_or_gain": assessment}

    def _update_service(self, ctx):
        state, result = ctx["state"], ctx["result"]
        strategy = deepcopy(state.get("strategy", {}))
        memory = strategy["executable_select"]
        facts = extract_trajectory_facts(state["task"], state["design"], result)
        is_candidate = bool(ctx["decision"].get("selected_id") and ctx["decision"].get("actual_input"))
        if is_candidate:
            memory["candidate_execution"] = {"design": deepcopy(state["design"]), "result": _receipt(result),
                "trajectory_facts": facts, "scientific_observation": facts.get("status") == "PUBLIC_TRAJECTORY_FACTS",
                "decision": deepcopy(ctx["decision"])}
            memory["adoption_status"] = ("PENDING_REGRESSION" if _pass6(result) and facts.get("status") == "PUBLIC_TRAJECTORY_FACTS"
                                         else "RETAIN_PARENT")
        else:
            memory.update(parent_result=_receipt(result), trajectory_facts=facts, adoption_status="RETAIN_PARENT")
        memory["scope"] = "One observed candidate only; failed result does not exclude a family."
        self.decisions.append({"site": "Update", "trajectory_facts_sha256": digest(facts),
                               "candidate_execution": is_candidate, "adoption_status": memory["adoption_status"]})
        return {"strategy": strategy, "next_evidence": {"trajectory_facts_sha256": digest(facts),
                "adoption_status": memory["adoption_status"], "no_further_candidate_in_package": is_candidate}}

    def update(self, state, decision, result, independent_assessment=None):
        base = public_state(state)
        strategy = base.setdefault("strategy", {})
        memory = strategy.setdefault("executable_select", {"version": VERSION,
            "parent_design": deepcopy(base["design"]), "parent_problem": deepcopy(base.get("problem", {})),
            "parent_result": _receipt(base.get("last_result", {})), "adoption_status": "RETAIN_PARENT"})
        candidate = bool(decision.get("selected_id") and decision.get("actual_input"))
        expected = {**memory["parent_design"], **decision.get("actual_input", {}).get("design_patch", {})} if candidate else memory["parent_design"]
        if result.get("execution_status") in SUCCESS and result.get("design") != expected:
            raise ContractError("M4_RESULT_DOES_NOT_BIND_SELECTED_OR_PARENT_DESIGN")
        updated = Harness.update(self, base, decision, result, independent_assessment)
        memory = updated["strategy"]["executable_select"]
        if candidate and updated.get("update_status") != "UPDATED":
            memory["candidate_execution"] = {"design": deepcopy(expected), "result": _receipt(updated["last_result"]),
                "scientific_observation": False, "decision": deepcopy(decision), "status": updated.get("update_status")}
            memory["adoption_status"] = "RETAIN_PARENT"
        updated["design"] = deepcopy(memory["parent_design"])
        updated["problem"] = deepcopy(memory["parent_problem"])
        return updated

    def finalize_adoption(self, state, regression_public_result=None):
        new = public_state(state)
        memory = new.get("strategy", {}).get("executable_select", {})
        candidate = memory.get("candidate_execution", {})
        regression = regression_public_result
        if memory.get("adoption_status") == "PENDING_REGRESSION" and regression is not None:
            memory["regression_result"] = _receipt(regression)
            if (_pass6(regression) and regression.get("task_id") == REGRESSION_TASK_ID
                    and regression.get("design") == candidate.get("design")):
                memory.update(parent_design=deepcopy(candidate["design"]), parent_result=deepcopy(candidate["result"]),
                              trajectory_facts=deepcopy(candidate["trajectory_facts"]), adoption_status="ADOPTED_AFTER_REGRESSION")
            else:
                memory["adoption_status"] = "RETAIN_PARENT_REGRESSION_NOT_PASSED"
        new["design"] = deepcopy(memory.get("parent_design", new["design"]))
        new["problem"] = deepcopy(memory.get("parent_problem", new.get("problem", {})))
        return new
