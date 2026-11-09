"""Optional same-parent proposals. Every scientific calculation is injected.

The actual model decides; this module cannot run a consumer or a provider.
"""
from copy import deepcopy
import hashlib
import json
import math
import random
import time

from bfworld.agentlab.pqe20261024debt.search import DomainSpace
from bfworld.agentlab.pqe20261024debt.obligations import semantic_checks

VERSION = "same-parent-joint-and-recursive-proposals-v1"
COMPLETE = {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def changed(before, after):
    return {k: deepcopy(v) for k, v in after.items() if before.get(k) != v}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _rows(result):
    rows = result.get("results", result.get("cases", [result]))
    if not isinstance(rows, list) or not rows:
        raise ValueError("PUBLIC_FAMILY_REQUIRED")
    return rows


def _status(result):
    return [r.get("public_check", {}).get("verdict", "UNKNOWN")
            if r.get("model_valid") is True and r.get("execution_status") in COMPLETE else "UNKNOWN"
            for r in _rows(result)]


class Strategy:
    def __init__(self, contract, initial_design, initial_public, *, fact_fn, calc_fn,
                 recursive=False, seed=314159, meter=None):
        self.contract = deepcopy(contract)
        self.initial_design = deepcopy(initial_design)
        self.space = DomainSpace(contract, initial_design)
        self.fact_fn, self.calc_fn, self.external_meter = fact_fn, calc_fn, meter
        self.recursive, self.seed = bool(recursive), seed
        self.holder = {"holding_component", "holding_capacity", "holding_overflow", "read_source", "clear_after"} <= set(self.space.domain)
        self.archive, self.generated, self.history = {}, {}, []
        self.cache, self.events, self.proposal_round = {}, [], 0
        self.cost = {"fact_api_calls": 0, "calc_api_calls": 0, "exact_strategy_cache_hits": 0,
                     "structural_validations": 0, "proposals": 0, "updates": 0,
                     "strategy_wall_s": 0., "full_dispatches": 0, "model_dispatches": 0}
        self.current_parent_id = None
        self._register(initial_public, initial=True)

    def _meter(self, kind, key, details=None):
        event = {"kind": kind, "key": key, "details": deepcopy(details), "ordinal": len(self.events) + 1}
        self.events.append(event)
        if self.external_meter is not None:
            self.external_meter(kind, key, details)

    def _normalize(self, raw, parent):
        self.cost["structural_validations"] += 1
        design = self.space.validate(raw)
        if not set(changed(parent, design)) <= set(self.space.active):
            raise ValueError("EDIT_OUTSIDE_PUBLIC_AUTHORITY")
        if self.holder:
            if design["holding_component"] == "off":
                design.update({k: deepcopy(self.initial_design[k]) for k in ("holding_capacity", "holding_overflow")})
                design.update(read_source="contact_only", clear_after="never")
            elif design["read_source"] == "contact_only":
                design["clear_after"] = "never"
        self.space.validate(design)
        return {"design": design, "raw_proposal": deepcopy(raw), "design_patch": changed(parent, design),
                "normalized_inactive_fields": changed(raw, design)}

    def _register(self, result, *, initial=False):
        design = result.get("design")
        if not isinstance(design, dict):
            raise ValueError("EVALUATED_PUBLIC_DESIGN_REQUIRED")
        norm = self._normalize(design, self.initial_design)
        if any(r.get("design", design) != design for r in _rows(result)):
            raise ValueError("FAMILY_MEMBER_DESIGN_BINDING")
        conditions = [r.get("condition_id", r.get("task_id")) for r in _rows(result)]
        if len(set(conditions)) != len(conditions) or None in conditions:
            raise ValueError("UNIQUE_CONDITIONS_REQUIRED")
        if not initial and set(conditions) != set(self.conditions):
            raise ValueError("UNCHANGED_COMPLETE_FAMILY_REQUIRED")
        if initial:
            self.conditions = conditions
            if design != self.initial_design:
                raise ValueError("INITIAL_PUBLIC_BINDING")
        # Archive the exact evaluated design/result pair. Normalization is a
        # proposal operation and cannot rewrite the observed parent or replace
        # an earlier observation when a design is evaluated again.
        key = digest(design)
        parent_id = "parent-" + digest([design, result])[:24]
        prior = self.current_parent_id
        adopted = self.generated.get(key)
        row = {"id": parent_id, "design": deepcopy(design), "public_result": deepcopy(result),
               "statuses": _status(result), "previous_current_parent_id": prior,
               "generated_candidate_adopted_exact": adopted["id"] if adopted else None,
               "origin": "COMMON_INITIAL" if initial else "REAL_MODEL_EVALUATED_DESIGN",
               "result_sha256": digest(result)}
        self.archive[parent_id] = row
        self.current_parent_id = parent_id
        return row

    def update(self, family_result):
        at = time.monotonic()
        row = self._register(family_result)
        self.cost["updates"] += 1
        receipt = {"schema": VERSION + ":update", "parent_id": row["id"],
                   "actual_design": deepcopy(row["design"]), "statuses": row["statuses"],
                   "generated_candidate_adopted_exact": row["generated_candidate_adopted_exact"],
                   "free_or_modified_model_proposal": row["generated_candidate_adopted_exact"] is None,
                   "previous_parent_retained": row["previous_current_parent_id"] in self.archive,
                   "automatic_restart": False, "archive_size": len(self.archive),
                   "full_service_PASS": all(s == "PASS" for s in row["statuses"])}
        self.history.append(deepcopy(receipt))
        self.cost["strategy_wall_s"] += time.monotonic() - at
        return receipt

    def _invoke(self, kind, design, parent):
        observed = parent["public_result"] if design == parent["design"] else None
        key = digest([kind, self.contract, design, observed])
        if key in self.cache:
            self.cost["exact_strategy_cache_hits"] += 1
            return deepcopy(self.cache[key])
        fn = self.fact_fn if kind == "facts" else self.calc_fn
        kwargs = {"public_result": observed, "meter": self._meter}
        if kind == "calc":
            kwargs["operation"] = "all"
        result = fn(self.contract, deepcopy(design), **kwargs)
        self.cost["fact_api_calls" if kind == "facts" else "calc_api_calls"] += 1
        if not isinstance(result, dict):
            raise ValueError("STRUCTURED_SOURCE_FACTS_REQUIRED")
        binding = result.get("design_sha256", result.get("binding", {}).get("design_sha256"))
        if binding != digest(design):
            raise ValueError("INJECTED_FACT_DESIGN_BINDING")
        # A reports exact memo accounting through the meter as well as a
        # convenience HIT/MISS label. The label is execution metadata, not a
        # scientific fact and cannot distinguish otherwise identical J pools.
        result = deepcopy(result)
        result.pop("memo", None)
        self.cache[key] = deepcopy(result)
        return result

    @staticmethod
    def _checks(facts):
        raw = facts.get("checks", facts.get("semantic_checks", facts.get("obligations")))
        if raw is None:
            raw = semantic_checks(facts)
        if not isinstance(raw, list):
            raise ValueError("ACTUAL_CHECK_LIST_REQUIRED")
        rows = []
        for item in raw:
            c = deepcopy(item.get("check", item))
            kind, subject = c.get("kind", c.get("type")), c.get("subject", c.get("id"))
            if not kind or subject is None:
                raise ValueError("CHECK_KIND_SUBJECT_REQUIRED")
            holds = c.get("holds")
            if type(holds) is not bool:
                holds = None
            rows.append({"id": digest([kind, subject]), "kind": kind, "subject": subject,
                         "holds": holds, "applicable": c.get("applicable", True),
                         "dependencies": c.get("dependencies", c.get("depends_on", [])),
                         "source_refs": c.get("refs", c.get("source_refs", [])),
                         "predicate": c.get("predicate"), "source_check": c,
                         "status": "INACTIVE" if c.get("applicable", True) is False else
                                   "UNMET_STATIC_COMPANION" if holds is False else
                                   "SUPPORTED_STATIC_CONTRACT" if holds is True else "UNKNOWN",
                         "physical_service": "UNKNOWN"})
        return rows

    def _inspect(self, design, parent, *, calculate=True):
        facts = self._invoke("facts", design, parent)
        calculations = self._invoke("calc", design, parent) if calculate else None
        return {"design_sha256": digest(design), "actual_facts": facts,
                "facts_sha256": digest(facts), "checks": self._checks(facts),
                "calculations": calculations,
                "calculation_sha256": digest(calculations) if calculations is not None else None,
                "prior_observation_applies_to_candidate": design == parent["design"],
                "full_service": "UNKNOWN"}

    @staticmethod
    def _changed_obligations(before, after, fields):
        old = {c["id"]: c for c in before["checks"]}
        return [deepcopy(c) for c in after["checks"] if c["applicable"] is not False and
                (c["id"] not in old or old[c["id"]]["applicable"] is False or
                 c["holds"] != old[c["id"]]["holds"] or
                 (set(fields) & set(c["dependencies"]) and c["holds"] is not True))]

    @staticmethod
    def _pending(parent):
        kinds = set()
        for r in _rows(parent["public_result"]):
            if r.get("public_check", {}).get("verdict") != "PASS":
                kinds.add("complete_service")
            view = r.get("relationship_view", {})
            for rel in view.get("relations", []) if isinstance(view, dict) else []:
                if rel.get("holds") is False and "identity" in rel.get("relation_kind", ""):
                    kinds.add("identity")
        return kinds

    def _joint_targets(self, parent, inspection):
        """Filled from public numeric inequalities, never cached repair values."""
        return self._numeric_targets(parent, inspection)

    def _numeric_targets(self, parent, inspection):
        # A's versioned numeric adapter is interpreted below. It supplies facts
        # and bounds, never a proposed design or natural-language action.
        calc = inspection["calculations"]
        constraints = deepcopy(calc.get("constraints", []))
        task_contracts = {t["task_id"]: t for t in self.contract.get("tasks", [])}

        def add(field, relation, value, row, path, *, assumptions=None):
            if field in self.space.domain and _finite(value):
                constraints.append({"field": field, "relation": relation, "value": value,
                    "task_id": row.get("task_id"), "calculation_sha256": inspection["calculation_sha256"],
                    "source_refs": [{"calculator": calc.get("schema"), "path": path,
                                     "source_sha256": calc.get("source_sha256", {})}],
                    "assumptions": deepcopy(assumptions), "full_service": "UNKNOWN",
                    "interpretation": "conditional numeric proposal; no feasibility certificate"})

        for row in calc.get("tasks", []):
            bounds = row.get("bounds", {})
            for field, interval in bounds.get("necessary_outer_intervals", {}).items():
                if isinstance(interval, list) and len(interval) == 2:
                    add(field, ">=", interval[0], row, "bounds.necessary_outer_intervals."+field+"[0]", assumptions=bounds.get("scope"))
                    add(field, "<=", interval[1], row, "bounds.necessary_outer_intervals."+field+"[1]", assumptions=bounds.get("scope"))
            # Every numerical load bound is computed by A on this exact
            # candidate. B only intersects the resulting field inequalities.
            for bound in row.get("loads", {}).get("conditional_design_bounds", []):
                add(bound.get("field"), bound.get("relation", ">="), bound.get("value"), row,
                    "loads.conditional_design_bounds", assumptions=bound.get("assumptions"))
            for index, chain in enumerate(row.get("loads", {}).get("conditional_phase_chains", [])):
                if chain.get("conditional_interval_nonempty") is True:
                    add("capacitance_f", ">=", chain.get("conditional_capacitance_lower_f"), row,
                        "loads.conditional_phase_chains["+str(index)+"].conditional_capacitance_lower_f",
                        assumptions=chain.get("assumptions"))
            energy = row.get("energy", {})
            if energy.get("zero_source_in_declared_dark_interval") is True:
                add("capacitance_f", ">=", energy.get("background_only_capacitance_lower_f"), row,
                    "energy.background_only_capacitance_lower_f", assumptions=energy.get("necessary_bound_assumptions"))
            cold = energy.get("cold_start", {})
            add("capacitance_f", "<=", cold.get("capacitance_upper_f"), row,
                "energy.cold_start.capacitance_upper_f", assumptions=cold.get("assumptions"))
            recovery = row.get("recovery", {})
            add("nvm_capacity_records", ">=", recovery.get("nominal_all_committed_count_upper"), row,
                "recovery.nominal_all_committed_count_upper", assumptions=recovery.get("scope"))
            task = task_contracts.get(row.get("task_id"), {})
            service = task.get("service", {})
            sample = service.get("continuous_new_sampling", {})
            add("sample_period_s", "<=", sample.get("maximum_spacing_s"), row,
                "public_task.service.continuous_new_sampling.maximum_spacing_s",
                assumptions="nominal powered sampling period; actual spacing remains UNKNOWN")
        return constraints

    def _endpoint_seed(self, design, inspection):
        # This is an explicit J search policy, not advice attributed to A:
        # test the public low-resistance/low-start-threshold corner while
        # retaining all other current-parent choices. It is a conditional
        # probe. Its coupled capacitance requirements are recomputed by A.
        # Neither a successful design nor a task-specific repair constant is
        # present here; G has identical access to these domain endpoints.
        trial, sources = deepcopy(design), []
        rows = inspection["calculations"].get("tasks", [])
        for row in rows:
            endpoints = row.get("loads", {}).get("public_domain_endpoint_points", {})
            for field in ("esr_ohm", "startup_v"):
                values = endpoints.get(field)
                if field not in self.space.active or not isinstance(values, list) or not values:
                    continue
                value = min(values)
                if field == "startup_v" and value <= trial.get("brownout_v", -math.inf):
                    continue
                if trial[field] != value:
                    trial[field] = value
                    sources.append({"field":field,"relation":"==","value":value,
                        "origin":"J_PUBLIC_DOMAIN_ENDPOINT_PROBE", "task_id":row.get("task_id"),
                        "source_refs":["loads.public_domain_endpoint_points."+field],
                        "interpretation":"strategy proposal; no physical necessity or service claim",
                        "full_service":"UNKNOWN"})
        return trial, sources

    def _merge(self, parent, constraints):
        design = deepcopy(parent["design"])
        combined, conflicts, provenance = {}, [], []
        for c in constraints:
            field = c.get("field")
            value = c.get("value", c.get("bound"))
            relation = c.get("relation", c.get("op", "=="))
            if field not in self.space.active or value is None:
                continue
            if c.get("applicable", True) is False or c.get("status") in {"UNAVAILABLE", "OUT_OF_DOMAIN"}:
                continue
            row = combined.setdefault(field, {"lower": None, "upper": None, "equal": None, "sources": []})
            row["sources"].append(deepcopy(c))
            if relation in {">=", "min", "lower_bound"} and _finite(value):
                row["lower"] = value if row["lower"] is None else max(row["lower"], value)
            elif relation in {"<=", "max", "upper_bound"} and _finite(value):
                row["upper"] = value if row["upper"] is None else min(row["upper"], value)
            elif relation in {"==", "equals"}:
                if row["equal"] is not None and row["equal"] != value:
                    conflicts.append({"field": field, "kind": "INCOMPATIBLE_EQUALITIES", "sources": row["sources"]})
                row["equal"] = value
        for field, b in combined.items():
            lower, upper = b["lower"], b["upper"]
            spec = self.space.domain[field]
            lower = max(spec["min"], lower) if lower is not None and "min" in spec else lower
            upper = min(spec["max"], upper) if upper is not None and "max" in spec else upper
            if lower is not None and upper is not None and lower > upper:
                conflicts.append({"field": field, "kind": "INCOMPATIBLE_BOUNDS", "sources": b["sources"]})
                continue
            if b["equal"] is not None and _finite(b["equal"]) and ((lower is not None and b["equal"] < lower) or (upper is not None and b["equal"] > upper)):
                conflicts.append({"field": field, "kind": "EQUALITY_BOUND_CONFLICT", "sources": b["sources"]})
                continue
            target = b["equal"] if b["equal"] is not None else design[field]
            if lower is not None:
                target = max(target, lower)
            if upper is not None:
                target = min(target, upper)
            if spec.get("kind", spec.get("type")) in {"integer", "int"} and _finite(target):
                target = int(math.ceil(target))
            design[field] = target
            provenance.extend(b["sources"])
        return design, provenance, conflicts

    def _candidate(self, raw, parent, parent_inspection, origin, derivations, chain=(), *, calculate=True):
        norm = self._normalize(raw, parent["design"])
        inspection = self._inspect(norm["design"], parent, calculate=calculate)
        fields = norm["design_patch"]
        changed_checks = self._changed_obligations(parent_inspection, inspection, fields)
        key = digest(norm["design"])
        return {**norm, "id": "candidate-" + digest([parent["id"], key])[:24],
                "parent_id": parent["id"], "origin": origin,
                "predicted_facts": inspection, "derivations": deepcopy(derivations),
                "closure_chain": deepcopy(list(chain)), "changed_obligations": changed_checks,
                "side_effects_recomputed": True, "empirical_status": "NOT_EVALUATED",
                "full_service": "UNKNOWN", "requires_model_choice": True}

    def _recursive(self, candidate, parent, parent_inspection):
        current = deepcopy(candidate)
        chain = [{"design": deepcopy(current["design"]), "facts_sha256": current["predicted_facts"]["facts_sha256"],
                  "changed_obligations": deepcopy(current["changed_obligations"]), "transition": None}]
        seen = {digest(current["design"])}
        attempts = []
        for depth in range(3):
            targets = [c for c in current["changed_obligations"] if c["applicable"] is True and c["holds"] is False]
            if not targets:
                break
            target = targets[0]
            advanced = None
            for field in target["dependencies"]:
                if field not in self.space.active:
                    continue
                spec = self.space.domain[field]
                if not (spec.get("kind", spec.get("type")) in {"boolean", "bool", "enum"} or any(k in spec for k in ("values", "choices", "enum"))):
                    continue
                for value in self.space.values(field, current["design"][field]):
                    try:
                        trial = self._candidate({**current["design"], field: value}, parent, parent_inspection,
                                                "RECURSIVE_COMPANION", current["derivations"], calculate=False)
                        if digest(trial["design"]) in seen:
                            continue
                        check = next((c for c in trial["predicted_facts"]["checks"] if c["id"] == target["id"]), None)
                        # Vacuously disabling a newly installed duty cannot earn
                        # companion credit. G remains free to reject that route.
                        improved = check is not None and check["applicable"] is True and (check["holds"] is True or check["predicate"] != target["predicate"])
                        attempts.append({"target": target["id"], "patch": changed(current["design"], trial["design"]),
                                         "facts_sha256": trial["predicted_facts"]["facts_sha256"], "improved_static_support": improved})
                        if improved:
                            trial["predicted_facts"] = self._inspect(trial["design"], parent, calculate=True)
                            advanced = trial
                            break
                    except (ValueError, TypeError) as exc:
                        attempts.append({"target": target["id"], "field": field, "value": value, "status": "REJECTED", "reason": str(exc)})
                if advanced:
                    break
            if advanced is None:
                break
            seen.add(digest(advanced["design"]))
            transition = {"consumed_actual_obligation": deepcopy(target),
                          "patch": changed(current["design"], advanced["design"]),
                          "kind": "CANDIDATE_FACTS_TO_COMPANION_RECHECK", "depth": depth + 1,
                          "dynamic_service_satisfied": False}
            chain.append({"design": deepcopy(advanced["design"]),
                          "facts_sha256": advanced["predicted_facts"]["facts_sha256"],
                          "changed_obligations": deepcopy(advanced["changed_obligations"]), "transition": transition})
            advanced["closure_chain"] = deepcopy(chain)
            current = advanced
        return (current if len(chain) > 1 else None), attempts

    def propose(self, parent_id=None):
        at = time.monotonic()
        parent = self.archive[parent_id or self.current_parent_id]
        round_index = self.proposal_round
        self.proposal_round += 1
        before_cost = deepcopy(self.cost)
        event_start = len(self.events)
        if all(s == "PASS" for s in parent["statuses"]):
            return {"schema": VERSION, "parent_id": parent["id"], "candidates": [],
                    "reason": "EXISTING_FULL_SERVICE_PASS", "model_decides": True}
        inspection = self._inspect(parent["design"], parent)
        constraints = self._joint_targets(parent, inspection)
        raw, provenance, conflicts = self._merge(parent, constraints)
        raw, endpoint_sources = self._endpoint_seed(raw, inspection)
        provenance.extend(endpoint_sources)
        common, rejections = [], []
        if raw != parent["design"]:
            try:
                joint = self._candidate(raw, parent, inspection, "SAME_PARENT_JOINT_RECALCULATED", provenance)
                # Recompute all affected bounds on the changed design and
                # preserve its other edits during a bounded fixed-point step.
                # A new conflict or UNKNOWN is retained as a probe, never PASS.
                recalc = []
                for _ in range(2):
                    candidate_bounds = self._numeric_targets(parent, joint["predicted_facts"])
                    candidate_parent = {**parent, "design": joint["design"]}
                    revised, revised_sources, revised_conflicts = self._merge(candidate_parent, candidate_bounds)
                    recalc.append({"design_sha256": digest(joint["design"]),
                                   "calculation_sha256": joint["predicted_facts"]["calculation_sha256"],
                                   "constraints": candidate_bounds, "conflicts": revised_conflicts,
                                   "new_patch": changed(joint["design"], revised)})
                    conflicts.extend(revised_conflicts)
                    if revised == joint["design"]:
                        break
                    joint = self._candidate(revised, parent, inspection,
                                            "SAME_PARENT_JOINT_RECALCULATED", provenance + revised_sources)
                joint["joint_recalculation_chain"] = recalc
                common.append(joint)
            except (ValueError, TypeError) as exc:
                rejections.append({"origin": "JOINT", "raw_proposal": raw, "reason": str(exc)})
        rng = random.Random(int(digest([self.seed, parent["id"], round_index, "common-general"])[:16], 16))
        for attempt in range(4):
            patch = self.space.random_patch(parent["design"], rng, width=min(2, len(self.space.active)))
            try:
                trial = self._candidate({**parent["design"], **patch}, parent, inspection, "COMMON_GENERAL_JOINT", [])
                if trial["design_patch"] and all(trial["design"] != c["design"] for c in common):
                    common.append(trial)
                    break
            except (ValueError, TypeError) as exc:
                rejections.append({"origin": "COMMON_GENERAL_JOINT", "raw_patch": patch, "reason": str(exc)})
        candidates = deepcopy(common)
        recursive_attempts = []
        if self.recursive:
            for c in common:
                addition, attempts = self._recursive(c, parent, inspection)
                recursive_attempts.extend(attempts)
                if addition and all(addition["design"] != x["design"] for x in candidates):
                    candidates.append(addition)
                    break
        candidates = candidates[:3]
        for c in candidates:
            self.generated[digest(c["design"])] = deepcopy(c)
        self.cost["proposals"] += 1
        self.cost["strategy_wall_s"] += time.monotonic() - at
        return {"schema": VERSION, "parent_id": parent["id"], "parent_design": deepcopy(parent["design"]),
                "round_index": round_index, "recursive": self.recursive,
                "common_candidates_sha256": digest(common), "common_candidates": common,
                "candidates": candidates, "joint_constraints": constraints, "joint_conflicts": conflicts,
                "pending_public_services": [{"condition_id": r.get("condition_id", r.get("task_id")),
                    "public_check": deepcopy(r.get("public_check", {})),
                    "observation_applies_only_to_parent": True} for r in _rows(parent["public_result"])
                    if r.get("public_check", {}).get("verdict") != "PASS"],
                "rejections": rejections, "recursive_attempts": recursive_attempts,
                "model_decides": True, "automatic_candidate_selected": None,
                "free_joint_edit_rights": True, "no_forced_component": True,
                "resource_events": deepcopy(self.events[event_start:]),
                "strategy_cost_delta": {k: self.cost[k] - before_cost[k] for k in self.cost},
                "full_service": "UNKNOWN"}

    def snapshot(self):
        return {"version": VERSION, "recursive": self.recursive, "seed": self.seed,
                "current_parent_id": self.current_parent_id, "archive": deepcopy(self.archive),
                "history": deepcopy(self.history), "resource_events": deepcopy(self.events),
                "strategy_cost": deepcopy(self.cost), "provider_or_consumer_dispatch": False}
