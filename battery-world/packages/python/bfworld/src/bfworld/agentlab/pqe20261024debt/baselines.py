"""Unrestricted joint-edit Agent and seeded mixed-search controls.

Both share the new public design domain and whole-family evaluator protocol.
Neither is artificially limited to one-field mutation or greedy replacement.
"""
from copy import deepcopy
import random

from .search import DomainSpace, call_planner, family_result, planner_format_error
from .obligations import digest, changed_fields

VERSION = "codebt-joint-controls-v2-public-causal"

class _Control:
    def __init__(self, initial_design, contract, *, scope=None, initial_result=None,
                 active_variables=None, max_evaluated_designs=6, validate_fn=None):
        if type(max_evaluated_designs) is not int or not 1 <= max_evaluated_designs <= 6:
            raise ValueError("FINITE_COMMON_EVALUATED_DESIGN_CAP")
        self.space = DomainSpace(contract, initial_design, active_variables, validate_fn)
        self.initial_design, self.contract = deepcopy(initial_design), deepcopy(contract)
        self.scope = deepcopy(scope or {})
        self.conditions = list(self.scope.get("conditions", []))
        self.max_evaluated_designs = max_evaluated_designs
        self.pending, self.termination, self.best = None, None, None
        self.history, self.retained, self.callbacks, self.transitions = [], [], [], []
        self.evaluations, self.model_requests = 0, 0
        self.owner_budget = {}
        if initial_result is not None:
            summary = family_result(initial_result, initial_design, self.conditions)
            self.retained.append({"id": "initial", "design": deepcopy(initial_design),
                                  "service": summary, "external_initial": True})
            if summary["all_pass"]:
                self.best, self.termination = deepcopy(initial_design), "INITIAL_COMPLETE_SERVICE_PASS"

    def _gate(self, budget_snapshot=None):
        if budget_snapshot is not None:
            self.owner_budget = deepcopy(budget_snapshot)
        if self.pending is not None:
            raise ValueError("UPDATE_PENDING_WHOLE_DESIGN_FIRST")
        if self.evaluations >= self.max_evaluated_designs:
            self.termination = self.termination or "EVALUATED_DESIGN_CAP"
        return self.termination is None

    def _action(self, design, base, *, origin, selected_id=None):
        design = self.space.validate(design)
        identity = digest(design)
        if any(digest(h["design"]) == identity for h in self.history):
            raise ValueError("EXACT_DESIGN_ALREADY_EVALUATED")
        patch = {k: deepcopy(design[k]) for k in changed_fields(base, design)}
        if not patch:
            raise ValueError("NO_DESIGN_CHANGE")
        request = {"status": "ACTION", "schema": VERSION, "request_id": "eval-" + identity[:24],
                   "node_id": "control-" + identity[:24], "design": deepcopy(design),
                   "base_design": deepcopy(base), "conditions": list(self.conditions),
                   "decision": {"selected_id": selected_id or identity[:24],
                                "actual_input": {"operation": "edit", "design_patch": patch,
                                                 "problem_patch": {"active_variables": list(self.space.active)}},
                                "selection_basis": origin}}
        self.pending = deepcopy(request)
        self.transitions.append({"event": "SELECT_JOINT_DESIGN", "origin": origin,
                                 "changed_fields": list(patch), "request": deepcopy(request)})
        return request

    def update(self, result):
        if self.pending is None or self.termination:
            raise ValueError("NO_PENDING_COMPLETE_EVALUATION")
        request = self.pending
        if result.get("request_id", request["request_id"]) != request["request_id"]:
            raise ValueError("RESULT_REQUEST_BINDING")
        summary = family_result(result, request["design"], self.conditions)
        entry = {"id": request["node_id"], "design": deepcopy(request["design"]),
                 "service": summary, "request": deepcopy(request),
                 "predicate_observations": deepcopy(summary["observations"])}
        self.history.append(entry)
        self.retained.append(deepcopy(entry))
        # Keep multiple failed alternatives, not only a last/current optimum.
        self.retained = sorted(self.retained, key=lambda e: (
            e["service"]["pass_count"], e["service"]["valid_count"], e["id"]), reverse=True)[:6]
        self.evaluations += 1
        self.pending = None
        if summary["all_pass"]:
            self.best, self.termination = deepcopy(request["design"]), "COMPLETE_SERVICE_PASS"
        self.transitions.append({"event": "UPDATE_COMPLETE_RESULT", "service": summary,
                                 "retained_candidate_ids": [e["id"] for e in self.retained]})
        return {"status": "STOPPED" if self.termination else "UPDATED", "service": summary}

    def stop(self):
        return {"status": "STOPPED", "reason": self.termination,
                "retained_design": deepcopy(self.best or self.initial_design),
                "adopted": self.best is not None, "scope": deepcopy(self.scope),
                "global_infeasibility_claim": False}

    def snapshot(self):
        return {"schema": VERSION, "controller": type(self).__name__, "scope": self.scope,
                "initial_design": self.initial_design, "history": deepcopy(self.history),
                "retained": deepcopy(self.retained), "callbacks": deepcopy(self.callbacks),
                "transitions": deepcopy(self.transitions), "pending": deepcopy(self.pending),
                "evaluations": self.evaluations, "model_callbacks": self.model_requests,
                "termination": self.termination}


class GenericJointAgent(_Control):
    def __init__(self, initial_design, contract, planner, *, facts_fn=None,
                 model_identity=None, fixture_mode=False, max_model_requests=12, **kwargs):
        super().__init__(initial_design, contract, **kwargs)
        if type(max_model_requests) is not int or not 1 <= max_model_requests <= 12:
            raise ValueError("FINITE_COMMON_MODEL_CAP")
        self.planner, self.facts_fn = planner, facts_fn
        self.model_identity, self.fixture_mode = model_identity, fixture_mode
        self.max_model_requests = max_model_requests
        self.alternatives = []

    def step(self, budget_snapshot=None):
        if not self._gate(budget_snapshot):
            return self.stop()
        if self.planner is None or self.model_requests >= self.max_model_requests:
            self.termination = "PLANNER_UNAVAILABLE_OR_CAP"
            return self.stop()
        base = deepcopy(self.history[-1]["design"] if self.history else self.initial_design)
        facts = self.facts_fn(deepcopy(base)) if self.facts_fn else None
        request = {"schema": VERSION, "site": "H-GEN", "condition": "STRONG_GENERIC_JOINT",
                   "context": {"task_scope": self.scope, "design": base,
                               "public_contract": self.contract, "design_facts": facts,
                               "history": deepcopy(self.history), "retained": deepcopy(self.retained),
                               "unexecuted_alternatives": deepcopy(self.alternatives)},
                   "instruction": "Solve complete service with all authorized fields and public facts. You may jointly edit multiple hardware/program/parameter fields, retain alternative designs, restart, or plan several steps. No one-field or greedy constraint. Return {candidates:[{id,design_patch,reason}],selected_id}; candidates can include full design instead. Or return scoped STOPPED with basis. All candidate evaluations use the same full condition family.",
                   "owner_budget": deepcopy(self.owner_budget),
                   "quota": {"evaluated_designs_left": self.max_evaluated_designs - self.evaluations,
                             "controller_model_callbacks_left": self.max_model_requests - self.model_requests}}
        record = {"request": deepcopy(request)}
        self.callbacks.append(record)
        self.model_requests += 1
        try:
            response = call_planner(self.planner, request, fixture_mode=self.fixture_mode,
                                    model_identity=self.model_identity)
            record["response"] = response
        except Exception as exc:
            record["error"] = type(exc).__name__ + ":" + str(exc)
            self.termination = "MODEL_CALLBACK_BLOCKED"
            return self.stop()
        payload = response["payload"]
        if planner_format_error(payload):
            self.termination = "MODEL_FORMAT_ERROR"
            record["conclusion"] = deepcopy(payload)
            return self.stop()
        if payload.get("status") == "STOPPED":
            self.termination = "MODEL_SCOPED_STOP"
            record["conclusion"] = deepcopy(payload)
            return self.stop()
        raw = payload.get("candidates", [])
        if not isinstance(raw, list) or len(raw) > 6:
            self.termination = "MODEL_CANDIDATE_CONTRACT"
            return self.stop()
        options = []
        for index, item in enumerate(raw):
            try:
                if not isinstance(item, dict):
                    raise ValueError("MODEL_CANDIDATE_MUST_BE_OBJECT")
                design = (self.space.validate(item["design"]) if "design" in item else
                          self.space.apply(base, item.get("design_patch", item.get("actual_input", {}).get("design_patch", {}))))
                options.append({"id": item.get("id", str(index)), "design": design,
                                "reason": item.get("reason", "model joint proposal")})
            except (ValueError, TypeError, KeyError) as exc:
                self.transitions.append({"event": "REJECT_MODEL_CANDIDATE", "reason": str(exc)})
        # Previously unexecuted alternatives remain accessible and executable.
        options += deepcopy(self.alternatives)
        selected = payload.get("selected_id")
        options.sort(key=lambda e: e["id"] != selected if selected is not None else False)
        for item in options:
            if any(h["design"] == item["design"] for h in self.history) or item["design"] == base:
                continue
            self.alternatives = [deepcopy(e) for e in options if e["id"] != item["id"]][:6]
            return self._action(item["design"], base, origin=item["reason"], selected_id=item["id"])
        self.termination = "NO_NEW_LEGAL_MODEL_DESIGN"
        return self.stop()

    def snapshot(self):
        return {**super().snapshot(), "unexecuted_alternatives": deepcopy(self.alternatives)}


class MixedJointSearch(_Control):
    """Frozen seeded population retention, joint mutation and periodic restart."""
    def __init__(self, initial_design, contract, *, seed=20261024, **kwargs):
        super().__init__(initial_design, contract, **kwargs)
        self.seed, self.rng = seed, random.Random(seed)

    def step(self, budget_snapshot=None):
        if not self._gate(budget_snapshot):
            return self.stop()
        restart = self.evaluations % 2 == 0
        if restart or not self.retained:
            base = deepcopy(self.initial_design)
        else:
            # Rank-biased parent choice retains non-best candidates as well.
            population = self.retained
            weights = list(range(len(population), 0, -1))
            base = deepcopy(self.rng.choices(population, weights=weights, k=1)[0]["design"])
        for _ in range(32):
            patch = self.space.random_patch(base, self.rng,
                                            width=len(self.space.active) if restart else None)
            try:
                return self._action(self.space.apply(base, patch), base,
                                    origin="SEEDED_DOMAIN_RESTART" if restart else "SEEDED_JOINT_MUTATION_WITH_RETENTION")
            except ValueError:
                continue
        self.termination = "BOUNDED_UNIQUE_PROPOSAL_CAP"
        return self.stop()

    def snapshot(self):
        return {**super().snapshot(), "seed": self.seed,
                "algorithm": "all-field restart every second evaluation; 2..5-field joint mutation otherwise; six retained evaluated candidates; rank-biased parent sampling"}
