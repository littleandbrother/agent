"""Partial-node co-design search. Science and provider authority stay in S0.

``step()`` returns one whole-design evaluation request; ``update(result)``
accepts its unchanged public family result. Pure logical counterfactuals use
only the injected design_facts function. No simulator or provider is imported.
"""
from copy import deepcopy
from dataclasses import dataclass, field
import math
import random

from .obligations import (digest, changed_fields, derive_obligations,
                          closure_delta, unresolved)
from .certificates import build_certificate, covers_design

VERSION = "codebt-partial-search-v2-public-causal"
DEFAULT_LIMITS = {"max_evaluated_designs": 6, "beam_width": 8,
                  "max_nodes": 256, "max_logic_expansions": 24,
                  "max_fact_checks": 512, "max_diagnostics": 6,
                  "max_model_requests": 12, "max_model_candidates": 6,
                  "max_children_per_expansion": 24,
                  "max_domain_counterfactuals": 14}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class DomainSpace:
    """Common authorized edit space, shared by all three controllers."""
    def __init__(self, contract, initial, active_variables=None, validate_fn=None):
        self.contract = deepcopy(contract)
        self.validate_fn = validate_fn
        self.domain = deepcopy(contract.get("design_domain", {}))
        if not self.domain:
            raise ValueError("PUBLIC_DESIGN_DOMAIN_REQUIRED")
        self.active = sorted(active_variables if active_variables is not None else
                             contract.get("active_variables", self.domain))
        if not set(self.active) <= set(self.domain):
            raise ValueError("ACTIVE_DOMAIN_MISMATCH")
        self.validate(initial)

    def validate(self, design):
        if not isinstance(design, dict) or set(design) != set(self.domain):
            raise ValueError("COMPLETE_COMMON_DESIGN_REQUIRED")
        for key, spec in self.domain.items():
            value = design[key]
            kind = spec.get("kind", spec.get("type"))
            choices = spec.get("values", spec.get("choices", spec.get("enum")))
            if choices is not None:
                if value not in choices:
                    raise ValueError("DESIGN_ENUM:" + key)
            elif kind in {"boolean", "bool"}:
                if type(value) is not bool:
                    raise ValueError("DESIGN_BOOLEAN:" + key)
            elif kind == "mechanism":
                if not isinstance(value, dict) or set(value) - set(spec["editable"]):
                    raise ValueError("DESIGN_MECHANISM:" + key)
                for subkey, val in value.items():
                    bounds = spec["editable"][subkey]
                    lo, hi = (bounds["min"], bounds["max"]) if isinstance(bounds, dict) else bounds
                    if not _number(val) or not lo <= val <= hi:
                        raise ValueError("DESIGN_MECHANISM_DOMAIN:" + key)
            elif "min" in spec and "max" in spec:
                if not _number(value) or not spec["min"] <= value <= spec["max"]:
                    raise ValueError("DESIGN_NUMBER:" + key)
                if kind in {"integer", "int"} and type(value) is not int:
                    raise ValueError("DESIGN_INTEGER:" + key)
            else:
                raise ValueError("UNSUPPORTED_PUBLIC_DOMAIN:" + key)
        if self.validate_fn is not None:
            self.validate_fn(deepcopy(design))
        return deepcopy(design)

    def apply(self, design, patch):
        if not isinstance(patch, dict) or not set(patch) <= set(self.active):
            raise ValueError("EDIT_OUTSIDE_AUTHORIZED_DOMAIN")
        return self.validate({**deepcopy(design), **deepcopy(patch)})

    def values(self, key, current):
        spec = self.domain[key]
        values = spec.get("proposal_values", spec.get("values", spec.get("choices", spec.get("enum"))))
        kind = spec.get("kind", spec.get("type"))
        if values is None and kind in {"boolean", "bool"}:
            values = [False, True]
        if values is None and kind == "mechanism":
            values = []
            for subkey, bounds in spec["editable"].items():
                lo, hi = (bounds["min"], bounds["max"]) if isinstance(bounds, dict) else bounds
                for val in (lo, (lo + hi) / 2, hi):
                    values.append({**current, subkey: val})
        if values is None and "min" in spec:
            lo, hi = spec["min"], spec["max"]
            if kind in {"integer", "int"}:
                values = list(range(lo, hi + 1)) if hi - lo <= 8 else [lo, (lo + hi) // 2, hi]
            else:
                values = [lo, (lo + hi) / 2, hi]
        unique = {digest(v): deepcopy(v) for v in values or [] if v != current}
        return list(unique.values())

    def single_patches(self, design):
        return [{key: value} for key in self.active for value in self.values(key, design[key])]

    def random_patch(self, design, rng, *, width=None):
        keys = list(self.active)
        if not keys:
            return {}
        width = min(len(keys), width or rng.randint(2, min(5, len(keys)))) if len(keys) > 1 else 1
        patch = {}
        for key in rng.sample(keys, width):
            spec, old = self.domain[key], design[key]
            kind = spec.get("kind", spec.get("type"))
            choices = spec.get("values", spec.get("choices", spec.get("enum")))
            if choices is not None or kind in {"boolean", "bool", "mechanism"}:
                options = self.values(key, old)
                if options:
                    patch[key] = deepcopy(rng.choice(options))
            elif kind in {"int", "integer"}:
                patch[key] = rng.randint(spec["min"], spec["max"])
            else:
                patch[key] = rng.uniform(spec["min"], spec["max"])
        return {k: v for k, v in patch.items() if v != design[k]}


def family_result(result, design, conditions=()):
    """Validate public result identity and score only complete service facts."""
    if not isinstance(result, dict) or result.get("design") != design:
        raise ValueError("EVALUATED_DESIGN_BINDING_REQUIRED")
    rows = result.get("results", result.get("cases"))
    if rows is None:
        rows = [result]
    if not isinstance(rows, list) or not rows:
        raise ValueError("NONEMPTY_PUBLIC_RESULT_FAMILY_REQUIRED")
    ids = [row.get("condition_id", row.get("task_id")) for row in rows]
    if conditions and (len(ids) != len(conditions) or set(ids) != set(conditions)):
        raise ValueError("COMPLETE_SAME_CONDITION_FAMILY_REQUIRED")
    statuses = []
    for row in rows:
        if row.get("design", design) != design:
            raise ValueError("FAMILY_MEMBER_DESIGN_MISMATCH")
        complete = row.get("execution_status") in {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}
        verdict = row.get("public_check", {}).get("verdict", "UNKNOWN")
        valid = row.get("model_valid") is True
        statuses.append("PASS" if complete and valid and verdict == "PASS" else
                        "FAIL" if complete and valid and verdict == "FAIL" else "UNKNOWN")
    refs = [row.get("result_sha256") for row in rows if row.get("result_sha256")]
    compact_rows = [{k: deepcopy(row[k]) for k in
                     ("condition_id", "task_id", "execution_status", "model_valid", "public_check",
                      "result_sha256", "input_sha256", "public_object_ref") if k in row} for row in rows]
    return {"all_pass": all(s == "PASS" for s in statuses), "statuses": statuses,
            "pass_count": statuses.count("PASS"), "valid_count": sum(s != "UNKNOWN" for s in statuses),
            "refs": refs, "rows": compact_rows,
            "observations": public_observations(result, design, conditions)}


def public_observations(result, design, conditions=()):
    """Bind the common host's public predicates to their actual family rows.

    Missing, invalid or incomplete execution cannot become a causal failure.
    Legacy same-design obligation readbacks remain supported. No evaluator is
    imported and no failure string is translated into a diagnosis here.
    """
    members = result.get("results", result.get("cases", [result]))
    by_condition = {row.get("condition_id", row.get("task_id")): row for row in members}
    raw = list(result.get("predicate_observations", []))
    for row in members:
        raw.extend(row.get("predicate_observations", []))
    accepted = {}
    for original in raw:
        if not isinstance(original, dict) or original.get("design_sha256") != digest(design):
            continue
        row = deepcopy(original)
        if "predicate_id" in row:
            member = by_condition.get(row.get("condition_id"))
            if (member is None or (conditions and row["condition_id"] not in conditions)
                    or row.get("result_sha256") != member.get("result_sha256")):
                continue
            if (member.get("execution_status") not in {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}
                    or member.get("model_valid") is not True):
                row.update(holds=None, reason="INCOMPLETE_OR_INVALID_PUBLIC_EXECUTION")
        accepted[digest(row)] = row
    return list(accepted.values())


def planner_format_error(payload):
    return payload.get("status") in {"JSON_SYNTAX_ERROR", "INVALID_PLANNER_OUTPUT",
                                      "FORMAT_ERROR", "STRUCTURED_FORMAT_ERROR"}


def call_planner(planner, request, *, fixture_mode=False, model_identity=None):
    """One injected, externally accounted callback; never constructs a provider."""
    response = planner(deepcopy(request))
    usage = response.get("usage", {}) if isinstance(response, dict) else {}
    expected = {"SOFTWARE_FIXTURE"} if fixture_mode else {"KNOWN", "SETTLED"}
    if usage.get("status") not in expected:
        raise ValueError("PROVIDER_USAGE_NOT_SETTLED")
    if not fixture_mode:
        if not usage.get("model_identity") or (model_identity and usage["model_identity"] != model_identity):
            raise ValueError("MODEL_IDENTITY_MISMATCH")
        if any(not _number(usage.get(k)) or usage[k] < 0 for k in ("input_tokens", "output_tokens", "cost")):
            raise ValueError("PROVIDER_USAGE_NOT_SETTLED")
    if not isinstance(response.get("payload"), dict):
        raise ValueError("INVALID_PLANNER_PAYLOAD")
    return deepcopy(response)


@dataclass
class SearchNode:
    id: str
    design: dict
    pending_diff: dict
    obligations: list
    evidence: list
    scope: dict
    parent: object
    anchor: str
    depth: int = 0
    origin: str = "DOMAIN_COUNTERFACTUAL"
    delta: dict = field(default_factory=dict)
    expanded: bool = False
    evaluated: bool = False
    service: dict = field(default_factory=dict)

    @property
    def open_obligations(self):
        return unresolved(self.obligations)

    def to_dict(self):
        return {**deepcopy({k: v for k, v in self.__dict__.items() if k != "obligations"}),
                "obligations": [o.to_dict() for o in self.obligations],
                "open_obligations": [o.to_dict() for o in self.open_obligations]}


def expand_snapshot_obligation(snapshot, row):
    """Read back interned source references/history with content-hash checks."""
    row = deepcopy(row)
    def resolve(key, pool, prefix):
        value = deepcopy(snapshot[pool][key])
        if key != prefix + digest(value):
            raise ValueError("SNAPSHOT_REFERENCE_HASH_MISMATCH")
        return value
    row["invalidations"] = [resolve(record["invalidation_ref"], "invalidation_records",
                                    "codebt-invalidation:")
                            if "invalidation_ref" in record else record
                            for record in row["invalidations"]]
    for owner, field in [(row, "evidence_refs")] + [
            (record, "previous_evidence_refs") for record in row["invalidations"]
            if "previous_evidence_refs" in record]:
        expanded = []
        for ref in owner[field]:
            expanded.extend(resolve(ref, "evidence_ref_sets", "codebt-evidence-set:")
                            if ref in snapshot.get("evidence_ref_sets", {}) else [ref])
        owner[field] = expanded
    return row


class DebtSearch:
    def __init__(self, initial_design, contract, facts_fn, planner=None,
                 certificate_facts=(), limits=None, *, scope=None, initial_result=None,
                 active_variables=None, certificate_scope=None, certificate_checker=None,
                 model_identity=None, fixture_mode=False, seed=20261024, use_obligations=True,
                 validate_fn=None):
        self.space = DomainSpace(contract, initial_design, active_variables, validate_fn)
        self.contract, self.facts_fn, self.planner = deepcopy(contract), facts_fn, planner
        self.scope = deepcopy(scope or {})
        self.scope.setdefault("contract_sha256", digest(contract))
        self.conditions = list(self.scope.get("conditions", []))
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        for key, value in self.limits.items():
            if type(value) is not int or value <= 0 or value > DEFAULT_LIMITS[key]:
                raise ValueError("FINITE_LIMIT_CANNOT_ENLARGE:" + key)
        self.model_identity, self.fixture_mode = model_identity, fixture_mode
        self.use_obligations = bool(use_obligations)
        self.rng = random.Random(seed)
        self.initial_design = deepcopy(initial_design)
        self.nodes, self.by_design, self.transitions, self.callbacks = {}, {}, [], []
        self.frontier, self.pending, self.best = [], None, None
        self.evaluations, self.fact_checks, self.expansions, self.diagnostics = 0, 0, 0, 0
        self.model_requests, self.termination = 0, None
        self.last_model_epoch, self.owner_budget = -1, {}
        self.certificate = (build_certificate(certificate_scope, certificate_facts,
                                             verify_fact=certificate_checker)
                            if certificate_scope else {"status": "UNKNOWN", "reason": "NO_DECLARED_CERTIFICATE_SCOPE"})
        root = self._node(initial_design, None, "INITIAL")
        root.anchor = root.id
        self.root_id = root.id
        if initial_result is not None:
            root.service = family_result(initial_result, root.design, self.conditions)
            root.evidence.extend(root.service["refs"])
            if self.use_obligations:
                root.obligations = derive_obligations(
                    root.design, self._facts(root.design), scope=self.scope,
                    previous=root.obligations, previous_design=root.design,
                    observations=root.service["observations"])
            if root.service["all_pass"]:
                self.best, self.termination = root.id, "INITIAL_COMPLETE_SERVICE_PASS"
        self.frontier = [root.id]

    def _facts(self, design):
        if self.fact_checks >= self.limits["max_fact_checks"]:
            raise ValueError("FACT_CHECK_CAP")
        self.fact_checks += 1
        facts = deepcopy(self.facts_fn(deepcopy(design)))
        if not isinstance(facts, dict) or facts.get("design_sha256", digest(design)) != digest(design):
            raise ValueError("PUBLIC_FACT_DESIGN_BINDING")
        return facts

    def _node(self, design, parent, origin):
        design = self.space.validate(design)
        identity = digest(design)
        if identity in self.by_design:
            return None
        if len(self.nodes) >= self.limits["max_nodes"]:
            return None
        prior = self.nodes[parent] if parent else None
        anchor = self.nodes[prior.anchor] if prior and prior.anchor else prior
        diff = {k: deepcopy(design[k]) for k in changed_fields(prior.design if prior else self.initial_design, design)}
        facts = self._facts(design)
        obs = derive_obligations(design, facts, scope=self.scope,
                                 previous=prior.obligations if prior else (), trigger_diff=diff,
                                 previous_design=prior.design if prior else None) if self.use_obligations else []
        nid = "node-" + identity[:24]
        node = SearchNode(nid, deepcopy(design),
                          {k: deepcopy(design[k]) for k in changed_fields(anchor.design if anchor else self.initial_design, design)},
                          obs, deepcopy(prior.evidence if prior else []), deepcopy(self.scope),
                          parent, anchor.id if anchor else nid, (prior.depth + 1) if prior else 0,
                          origin, closure_delta(prior.obligations, obs) if prior else {})
        self.nodes[nid], self.by_design[identity] = node, nid
        self.transitions.append({"event": "GENERATE_NODE", "node": nid, "parent": parent,
                                 "diff": diff, "delta": deepcopy(node.delta),
                                 "obligation_bindings": [{"id": o.id, "status": o.status,
                                     "from_fact_ids": o.predicate.get("from_fact_ids", []),
                                     "ledger_sha256": digest(o.to_dict())} for o in obs],
                                 "origin": origin})
        return node

    def _public_experiments(self, node):
        changed = set(node.pending_diff)
        return [o for o in node.obligations
                if o.predicate.get("public_observation", {}).get("holds") is False
                and o.predicate["public_observation"].get("design_sha256") != digest(node.design)
                and changed.intersection(o.dependencies)]

    def _rank(self, node):
        # Full service evidence precedes scoped public hypotheses and edit cost.
        # Opening a relation or closing a newly invented static obligation earns
        # no positive progress. Static support only prioritizes a diagnostic for
        # a *pre-existing public failure*, never predicts full service success.
        anchor_service = self.nodes[node.anchor].service
        service = node.service or anchor_service
        experiments = self._public_experiments(node)
        supported = sum(o.predicate.get("static_support") is True for o in experiments)
        static_open = sum(o.status == "OPEN" and not o.type.startswith("PUBLIC_")
                          for o in node.obligations)
        return (service.get("pass_count", 0), service.get("valid_count", 0),
                supported, bool(experiments), -len(node.pending_diff), -static_open,
                node.origin == "MODEL_JOINT_PROPOSAL", -node.depth)

    def _retain(self, nodes):
        candidates = {n.id: n for n in nodes if n is not None}
        ranked = sorted(candidates.values(), key=lambda n: (self._rank(n), n.id), reverse=True)
        keep = ranked[:self.limits["beam_width"]]
        self.frontier = [n.id for n in keep]
        for node in keep:
            self.transitions.append({"event": "SELECT_RETAIN_PARTIAL" if node.open_obligations else "SELECT_RETAIN_CLOSED",
                                     "node": node.id, "open_ids": [o.id for o in node.open_obligations],
                                     "selection_basis": {"concrete_closure": node.delta.get("satisfied", []),
                                                         "new_relations": node.delta.get("opened", []),
                                                         "public_experiments": [o.id for o in self._public_experiments(node)],
                                                         "rank": list(self._rank(node)),
                                                         "opened_and_self_closure_are_not_progress": True,
                                                         "service_is_not_implied": True}})

    def _model_patches(self, parent):
        if (self.planner is None or self.model_requests >= self.limits["max_model_requests"]
                or self.last_model_epoch == self.evaluations):
            return []
        self.last_model_epoch = self.evaluations
        request = {"schema": VERSION, "site": "H-GEN", "condition": "DEBT_SEARCH",
                   "context": {"node": parent.to_dict(), "initial_design": self.initial_design,
                               "public_contract": self.contract,
                               "design_facts": self._facts(parent.design),
                               "retained_nodes": [self.nodes[k].to_dict() for k in self.frontier],
                               "evaluated_history": [n.to_dict() for n in self.nodes.values() if n.evaluated]},
                   "instruction": "Propose legal joint design_patch objects using public semantics and evidence. Retain useful partial ideas and offer alternative completions or discriminating diagnostics. No task/evaluator edits. Return {candidates:[{id,design_patch,reason,diagnostic_question?}]}; a scoped STOPPED response is allowed.",
                   "owner_budget": deepcopy(self.owner_budget),
                   "quota": {"evaluated_designs_left": self.limits["max_evaluated_designs"] - self.evaluations,
                             "controller_model_callbacks_left": self.limits["max_model_requests"] - self.model_requests}}
        self.model_requests += 1
        record = {"request": deepcopy(request)}
        self.callbacks.append(record)
        try:
            response = call_planner(self.planner, request, fixture_mode=self.fixture_mode,
                                    model_identity=self.model_identity)
            record["response"] = response
        except Exception as exc:
            record["error"] = type(exc).__name__ + ":" + str(exc)
            self.termination = "MODEL_CALLBACK_BLOCKED"
            return []
        raw = response["payload"].get("candidates", [])
        if planner_format_error(response["payload"]):
            self.termination = "MODEL_FORMAT_ERROR"
            record["conclusion"] = deepcopy(response["payload"])
            return []
        if response["payload"].get("status") == "STOPPED":
            self.termination = "MODEL_SCOPED_STOP"
            record["conclusion"] = deepcopy(response["payload"])
            return []
        if not isinstance(raw, list) or len(raw) > self.limits["max_model_candidates"]:
            self.termination = "MODEL_CANDIDATE_CONTRACT"
            return []
        patches = []
        for candidate in raw:
            if not isinstance(candidate, dict):
                continue
            if "design" in candidate:
                try:
                    design = self.space.validate(candidate["design"])
                    patches.append({k: deepcopy(design[k]) for k in changed_fields(parent.design, design)})
                except ValueError as exc:
                    self.transitions.append({"event": "REJECT_MODEL_CANDIDATE", "reason": str(exc)})
            else:
                patches.append(candidate.get("design_patch", candidate.get("actual_input", {}).get("design_patch", {})))
        return patches

    def _counterfactuals(self, parent):
        """Round-robin public dependencies before bounded unrestricted edits.

        OPEN dependencies localize a missing relationship. UNKNOWN facts alone
        do not identify a repair, so their search rotates across the whole
        authorized domain. No field name or proposed repair value is special.
        """
        public_failures = [o for o in parent.obligations
                           if o.predicate.get("public_observation", {}).get("holds") is False]
        open_rows = public_failures or [o for o in parent.open_obligations if o.status == "OPEN"]
        relevant = sorted({key for o in open_rows for key in o.dependencies}
                          & set(self.space.active))
        other = [key for key in self.space.active if key not in relevant]
        if other:
            offset = (self.expansions - 1) % len(other)
            other = other[offset:] + other[:offset]
        def interleave(keys):
            lists = [[{key: value} for value in self.space.values(key, parent.design[key])]
                     for key in keys]
            return [row[i] for i in range(max((len(row) for row in lists), default=0))
                    for row in lists if i < len(row)]
        primary = interleave(relevant or other)
        # A few unrestricted counterfactuals remain possible even while OPEN.
        secondary = interleave(other)[:3] if relevant else []
        cap = self.limits["max_domain_counterfactuals"]
        return (primary[:max(0, cap - len(secondary))] + secondary)[:cap]

    def _expand(self, parent):
        parent.expanded = True
        self.expansions += 1
        patches = [(p, "MODEL_JOINT_PROPOSAL") for p in self._model_patches(parent)]
        if self.termination:
            return []
        # The same public edit domain is available to ordinary search. These
        # counterfactuals discover relations, not a field-name repair template.
        patches += [(p, "DOMAIN_COUNTERFACTUAL") for p in self._counterfactuals(parent)]
        patches += [(self.space.random_patch(parent.design, self.rng), "JOINT_EXPLORATION")
                    for _ in range(4)]
        children = []
        for patch, origin in patches:
            if (len(children) >= self.limits["max_children_per_expansion"] or
                    self.fact_checks >= self.limits["max_fact_checks"]):
                break
            if not patch:
                continue
            try:
                design = self.space.apply(parent.design, patch)
                if digest(design) in self.by_design:
                    continue
                if covers_design(self.certificate, design, conditions=self.conditions or None):
                    self.transitions.append({"event": "CERTIFICATE_PRUNE", "parent": parent.id,
                                             "design_sha256": digest(design),
                                             "certificate_sha256": self.certificate["certificate_sha256"],
                                             "scope": self.certificate["scope"]})
                    continue
                child = self._node(design, parent.id, origin)
                if child:
                    children.append(child)
            except ValueError as exc:
                self.transitions.append({"event": "REJECT_LOGICAL_CANDIDATE", "parent": parent.id,
                                         "patch": deepcopy(patch), "reason": str(exc)})
        return children

    def _action(self, node, diagnostic=False):
        anchor = self.nodes[node.anchor]
        patch = {k: deepcopy(node.design[k]) for k in changed_fields(anchor.design, node.design)}
        question = ([{"obligation_id": o.id, "predicate": o.predicate,
                      "scope": o.scope} for o in node.open_obligations if o.status == "UNKNOWN"]
                    if diagnostic else [])
        request = {"status": "ACTION", "schema": VERSION, "request_id": "eval-" + node.id,
                   "node_id": node.id, "design": deepcopy(node.design), "base_design": deepcopy(anchor.design),
                   "conditions": list(self.conditions), "diagnostic": diagnostic,
                   "diagnostic_question": question,
                   "decision": {"selected_id": node.id,
                                "actual_input": {"operation": "edit", "design_patch": patch,
                                                 "problem_patch": {"active_variables": list(self.space.active)}},
                                "selection_basis": {"closure_delta": node.delta,
                                                     "public_experiments": [o.id for o in self._public_experiments(node)],
                                                     "rank": list(self._rank(node)),
                                                     "static_support_requires_full_diagnostic": True,
                                                     "evidence_refs": node.evidence,
                                                     "logical_closure_is_not_service_PASS": True}}}
        self.pending = deepcopy(request)
        if diagnostic:
            self.diagnostics += 1
        self.transitions.append({"event": "SELECT_COMPLETE_DIAGNOSTIC" if diagnostic else "SELECT_COMPLETE_EVALUATION",
                                 "node": node.id, "request": deepcopy(request)})
        return request

    def step(self, budget_snapshot=None):
        if budget_snapshot is not None:
            self.owner_budget = deepcopy(budget_snapshot)
        if self.pending is not None:
            raise ValueError("UPDATE_PENDING_WHOLE_DESIGN_FIRST")
        if self.termination:
            return self.stop()
        if self.evaluations >= self.limits["max_evaluated_designs"]:
            self.termination = "EVALUATED_DESIGN_CAP"
            return self.stop()
        while self.expansions < self.limits["max_logic_expansions"]:
            available = [self.nodes[k] for k in self.frontier if not self.nodes[k].expanded]
            if not available:
                self.termination = "BOUNDED_FRONTIER_EXHAUSTED"
                return self.stop()
            parent = max(available, key=lambda n: (self._rank(n), n.id))
            children = self._expand(parent)
            if self.termination:
                return self.stop()
            retained = [self.nodes[k] for k in self.frontier if not self.nodes[k].expanded]
            self._retain(retained + children)
            ranked = [self.nodes[k] for k in self.frontier
                      if not self.nodes[k].evaluated and
                      not any(o.status == "REFUTED" for o in self.nodes[k].obligations)]
            chosen = ranked[0] if ranked else None
            if chosen and not chosen.open_obligations:
                return self._action(chosen)
            # Retain and expand OPEN relationships first. UNKNOWN receives a
            # bounded full diagnostic only after a static completion attempt.
            diagnostic = [self.nodes[k] for k in self.frontier
                          if not self.nodes[k].evaluated
                          and (self.nodes[k].depth >= 2 or self._public_experiments(self.nodes[k]))
                          and self.nodes[k].open_obligations
                          and all(o.status == "UNKNOWN" for o in self.nodes[k].open_obligations)]
            if chosen in diagnostic and self.diagnostics < self.limits["max_diagnostics"]:
                return self._action(chosen, True)
        self.termination = "LOGICAL_EXTENSION_CAP"
        return self.stop()

    def update(self, result):
        if self.pending is None or self.termination:
            raise ValueError("NO_PENDING_COMPLETE_EVALUATION")
        request = self.pending
        if result.get("request_id", request["request_id"]) != request["request_id"]:
            raise ValueError("RESULT_REQUEST_BINDING")
        node = self.nodes[request["node_id"]]
        summary = family_result(result, node.design, self.conditions)
        old = node.obligations
        facts = self._facts(node.design)
        node.obligations = derive_obligations(node.design, facts, scope=self.scope,
                                              previous=old, previous_design=node.design,
                                              observations=summary["observations"]) if self.use_obligations else []
        node.delta = closure_delta(old, node.obligations)
        node.service, node.evaluated, node.expanded = summary, True, False
        node.evidence.extend(summary["refs"])
        node.pending_diff, node.anchor = {}, node.id
        self.evaluations += 1
        self.pending = None
        self.transitions.append({"event": "UPDATE_COMPLETE_RESULT", "node": node.id,
                                 "service": deepcopy(summary), "delta": deepcopy(node.delta),
                                 "retained_after_zero_service": summary["pass_count"] == 0})
        if summary["all_pass"]:
            self.best, self.termination = node.id, "COMPLETE_SERVICE_PASS"
        elif any(o.type.startswith("PUBLIC_") and o.status == "OPEN" for o in node.obligations):
            # Reserve the next bounded experiment for the just-observed gap.
            # Older branches remain fully recoverable in nodes and this event;
            # they cannot keep winning on stale, untested static predictions.
            prior_frontier = list(self.frontier)
            self._retain([node])
            self.transitions.append({"event": "FOCUS_PUBLIC_FAILURE", "node": node.id,
                "public_open_ids": [o.id for o in node.obligations
                                    if o.type.startswith("PUBLIC_") and o.status == "OPEN"],
                "recoverable_prior_frontier": prior_frontier,
                "scope": deepcopy(self.scope), "adoption_requires_full_PASS": True})
        else:
            self._retain([node] + [self.nodes[k] for k in self.frontier if k != node.id])
        return {"status": "STOPPED" if self.termination else "UPDATED", "node_id": node.id,
                "service": summary, "open_obligations": [o.to_dict() for o in node.open_obligations]}

    def stop(self):
        return {"status": "STOPPED", "reason": self.termination,
                "retained_design": deepcopy(self.nodes[self.best].design if self.best else self.initial_design),
                "adopted": self.best is not None,
                "scope": deepcopy(self.scope), "global_infeasibility_claim": False}

    def snapshot(self):
        # Nodes and invalidation histories repeatedly cite the same immutable
        # source-reference sets. Intern only these references in the saved
        # view; live nodes and exact callback requests/responses stay intact.
        evidence_ref_sets = {}
        invalidation_records = {}
        def compact_obligation(row):
            row = deepcopy(row)
            def intern(refs):
                if not refs:
                    return []
                key = "codebt-evidence-set:" + digest(refs)
                evidence_ref_sets.setdefault(key, deepcopy(refs))
                return [key]
            row["evidence_refs"] = intern(row["evidence_refs"])
            for invalidation in row["invalidations"]:
                if "previous_evidence_refs" in invalidation:
                    invalidation["previous_evidence_refs"] = intern(invalidation["previous_evidence_refs"])
            records = []
            for invalidation in row["invalidations"]:
                key = "codebt-invalidation:" + digest(invalidation)
                invalidation_records.setdefault(key, deepcopy(invalidation))
                records.append({"invalidation_ref": key})
            row["invalidations"] = records
            return row
        nodes = []
        for node in self.nodes.values():
            row = node.to_dict()
            row["obligations"] = [compact_obligation(o) for o in row["obligations"]]
            row["open_obligations"] = [compact_obligation(o) for o in row["open_obligations"]]
            nodes.append(row)
        return {"schema": VERSION, "limits": self.limits, "scope": self.scope,
                "use_obligations": self.use_obligations,
                "initial_design": self.initial_design, "nodes": nodes,
                "evidence_ref_sets": evidence_ref_sets,
                "invalidation_records": invalidation_records,
                "frontier": list(self.frontier), "pending": deepcopy(self.pending),
                "transitions": deepcopy(self.transitions), "callbacks": deepcopy(self.callbacks),
                "certificate": deepcopy(self.certificate), "evaluations": self.evaluations,
                "fact_checks": self.fact_checks, "logic_expansions": self.expansions,
                "model_callbacks": self.model_requests, "diagnostics": self.diagnostics,
                "termination": self.termination}
