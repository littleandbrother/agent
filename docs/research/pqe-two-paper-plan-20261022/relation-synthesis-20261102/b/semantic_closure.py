"""Versioned follow-up: actual candidate facts -> checks -> companion edits.

Frozen v1 is imported, never rewritten. Static companion closure admits a
conditional full probe; it never establishes coverage or physical service.
"""
from copy import deepcopy

from semantic_search import SemanticFactory, changed, digest
from bfworld.agentlab.pqe20261024debt.obligations import semantic_checks

VERSION = "public-contract-companion-expansion-v2"


def check_key(check):
    return digest([check["kind"], check["subject"]])


class ClosureEngine:
    def __init__(self, factory, design_facts_fn, *, max_nodes=48):
        self.factory, self.design_facts_fn = factory, design_facts_fn
        self.max_nodes = max_nodes
        self.cache = {}
        self.fact_calls = 0

    def inspect(self, design, reference=None):
        key = self.factory.semantic_key(design)
        if key not in self.cache:
            if len(self.cache) >= self.max_nodes:
                raise ValueError("BOUNDED_STATIC_FACT_NODE_CAP")
            facts = self.design_facts_fn(deepcopy(design))
            self.fact_calls += 1
            if facts.get("design_sha256") != digest(design):
                raise ValueError("ACTUAL_COMPONENT_FACT_DESIGN_BINDING")
            checks = semantic_checks(facts)
            obligations = []
            for c in checks:
                applicable, holds = c.get("applicable"), c.get("holds")
                status = ("INACTIVE" if applicable is False else "UNKNOWN_APPLICABILITY" if applicable is None else
                          "SATISFIED_STATIC_CONTRACT" if holds is True else
                          "UNMET_STATIC_COMPANION" if holds is False else "UNKNOWN_REQUIRES_OBSERVATION")
                obligations.append({"id": check_key(c), "status": status, "check": deepcopy(c),
                                    "is_physical_FAIL": False, "full_service": "UNKNOWN"})
            self.cache[key] = {"design": deepcopy(design), "design_sha256": key,
                               "actual_design_facts": deepcopy(facts), "actual_semantic_checks": checks,
                               "obligations": obligations, "facts_sha256": digest(facts),
                               "all_static_companions_satisfied": not any(o["status"] == "UNMET_STATIC_COMPANION" for o in obligations),
                               "coverage": "UNKNOWN", "energy": "UNKNOWN", "full_service": "UNKNOWN"}
        out = deepcopy(self.cache[key])
        old = {o["id"]: o for o in reference["obligations"]} if reference else {}
        out["new_obligations"] = [deepcopy(o) for o in out["obligations"]
            if o["status"] != "INACTIVE" and (o["id"] not in old or old[o["id"]]["status"] == "INACTIVE"
               or (o["status"] == "UNMET_STATIC_COMPANION" and old[o["id"]]["status"] != o["status"]))]
        return out

    def expand(self, candidate, *, parent_design, intent, max_depth=4, node_cap=12):
        reference = self.inspect(parent_design)
        initial = self.inspect(candidate, reference)
        root = {"id": "closure-" + digest([intent, initial["design_sha256"]])[:20],
                "parent_id": None, "depth": 0, "transition": None, "inspection": initial}
        nodes, queue, seen, leaves = [root], [root], {initial["design_sha256"]}, []
        while queue and len(nodes) < node_cap:
            current = queue.pop(0)
            inspection = current["inspection"]
            unmet = [o for o in inspection["obligations"] if o["status"] == "UNMET_STATIC_COMPANION"]
            if not unmet:
                leaves.append(current["id"])
            if current["depth"] >= max_depth:
                continue
            # No absent observation or dynamic UNKNOWN becomes static failure.
            # Optional release probes address the newly exposed capacity risk;
            # never/expiry remains a possible policy, not statically refuted.
            optional_release = (not unmet and self.factory.holder
                and inspection["design"].get("holding_component") != "off"
                and inspection["design"].get("read_source") == "holding_then_contact"
                and inspection["design"].get("clear_after") == "never")
            target = unmet[0] if unmet else next((o for o in inspection["obligations"]
                if o["check"]["kind"] == "DYNAMIC_CAPACITY" and o["status"] == "UNKNOWN_REQUIRES_OBSERVATION"), None)
            if not unmet and not optional_release:
                continue
            if target is None:
                continue
            fields = ["clear_after"] if optional_release else target["check"].get("dependencies", [])
            for field in fields:
                if field not in self.factory.space.active:
                    continue
                spec = self.factory.space.domain[field]
                # Logical companion completion uses only categorical contracts.
                # Dynamic energy/geometry is not solved by unmeasured axis edits.
                if not (spec.get("kind", spec.get("type")) in {"boolean", "bool", "enum"}
                        or any(k in spec for k in ("values", "choices", "enum"))):
                    continue
                for value in self.factory.space.values(field, inspection["design"][field]):
                    raw = {**inspection["design"], field: deepcopy(value)}
                    try:
                        norm = self.factory.normalize(raw, base_design=inspection["design"])
                        if not norm["design_patch"] or norm["semantic_key"] in seen:
                            continue
                        # A companion cannot discharge a newly introduced duty
                        # by silently removing that producer or release action.
                        if (self.factory.holder and inspection["design"].get("holding_component") != "off"
                                and norm["design"].get("holding_component") == "off"):
                            continue
                        nxt = self.inspect(norm["design"], inspection)
                    except (ValueError, TypeError) as exc:
                        if str(exc) == "BOUNDED_STATIC_FACT_NODE_CAP":
                            queue = []
                            break
                        continue
                    old_check = target["check"]
                    matching = next((o for o in nxt["obligations"] if o["id"] == target["id"]), None)
                    if not optional_release:
                        if matching is None or matching["status"] in {"INACTIVE", "UNKNOWN_APPLICABILITY"}:
                            continue
                        support_changed = matching["check"]["predicate"] != old_check["predicate"]
                        if matching["status"] != "SATISFIED_STATIC_CONTRACT" and not support_changed:
                            continue
                    seen.add(norm["semantic_key"])
                    transition = {"consumed_obligation_id": target["id"], "consumed_check": deepcopy(old_check),
                                  "patch": norm["design_patch"], "source_fact_ids": old_check["predicate"].get("from_fact_ids", []),
                                  "source_refs": old_check.get("refs", []),
                                  "kind": "OPTIONAL_DYNAMIC_CAPACITY_PROBE" if optional_release else "COMPANION_FROM_ACTUAL_UNMET_CHECK",
                                  "dynamic_obligation_resolved": False,
                                  "new_unmet": [o["id"] for o in nxt["obligations"] if o["status"] == "UNMET_STATIC_COMPANION"]}
                    node = {"id": "closure-" + digest([intent, norm["semantic_key"]])[:20],
                            "parent_id": current["id"], "depth": current["depth"] + 1,
                            "transition": transition, "inspection": nxt}
                    nodes.append(node)
                    queue.append(node)
                    if len(nodes) >= node_cap:
                        break
                if len(nodes) >= node_cap:
                    break
        # Include closed nodes at the bound even if not popped from the queue.
        leaves = list(dict.fromkeys(leaves + [n["id"] for n in nodes if n["inspection"]["all_static_companions_satisfied"]]))
        return {"schema": VERSION + ":chain", "intent": deepcopy(intent),
                "parent_inspection": reference, "nodes": nodes, "static_closed_node_ids": leaves,
                "full_service": "UNKNOWN", "dynamic_unknowns_permit_bounded_probe": True,
                "capacity_unknown_does_not_require_clear": True,
                "actual_fact_calls_cumulative": self.fact_calls}


class ClosureFactory(SemanticFactory):
    """Same common pool/archive; add bounded source-factual companion expansion."""
    def __init__(self, contract, initial_design, *, design_facts_fn=None, **kwargs):
        super().__init__(contract, initial_design, **kwargs)
        if design_facts_fn is None and self.holder:
            from bfworld.agentlab.pqe20261024debt.facts import design_facts
            tasks = contract.get("tasks", [])
            task = tasks[0] if tasks else contract
            design_facts_fn = lambda design: design_facts(design, task)
        self.engine = ClosureEngine(self, design_facts_fn) if design_facts_fn else None
        self.identity = digest({"version": VERSION, "base_factory": self.identity,
                                "facts_adapter": "source-bound injected" if design_facts_fn else "UNAVAILABLE"})

    def generate(self, parent_design, state, *, seed, round_index, relations_enabled=True, restart=False):
        common = super().generate(parent_design, state, seed=seed, round_index=round_index,
                                  relations_enabled=False, restart=restart)
        common.update(schema=VERSION + ":generation", relations_enabled=relations_enabled,
                      closure_chains=[], actual_fact_inspections=[], semantic_proposals=[],
                      static_companion_closure_is_service=False,
                      fact_adapter_status="AVAILABLE" if self.engine else "UNAVAILABLE")
        if not relations_enabled or state["all_pass"] or not state["complete_valid"]:
            return common
        if self.engine:
            # The node cap bounds one generation, rather than silently reducing
            # R's later scientific budget because an earlier memo filled up.
            self.engine.cache.clear()
        parent_inspection = self.engine.inspect(parent_design) if self.engine else None
        by_key = {c["semantic_key"]: c for c in common["candidates"]}
        for c in common["candidates"]:
            if self.engine:
                inspected = self.engine.inspect(c["design"], parent_inspection)
                common["actual_fact_inspections"].append(inspected)
        intents = []
        # v1's fixed holder macro is deliberately excluded. Other proposals are
        # conditional discriminating probes, never coverage-satisfaction checks.
        for rule in super()._rules(parent_design, state):
            if rule["rule"].startswith("powered_capture_handoff_"):
                continue
            intents.append(({**parent_design, **rule["patch"]}, {
                "kind": "DISCRIMINATING_PUBLIC_HYPOTHESIS", "rule": rule["rule"],
                "priority": rule["priority"], "consumed_pending": rule["consumed_pending"],
                "contract_refs": rule["contract_refs"], "prediction": rule["prediction"],
                "side_effects": rule["side_effects"], "expected_observations": rule["expected_observations"],
                "coverage_satisfied": False, "full_service": "UNKNOWN"}))
        if self.engine and self.holder and any(p["kind"] == "complete_service_coverage" for p in state["pending_service"]):
            producer = next((f for f in parent_inspection["actual_design_facts"].get("facts", [])
                if f.get("relation") == "produces" and f.get("object") == "holding_record"), None)
            if producer and producer.get("value", {}).get("requires_mcu_power") is False:
                for value in self.space.values("holding_component", parent_design["holding_component"]):
                    if value == "off":
                        continue
                    # Only the producer changes here. Every subsequent read,
                    # durability and release edit must come from actual checks.
                    intents.append(({**parent_design, "holding_component": value}, {
                        "kind": "INTRODUCE_PUBLIC_PRODUCER", "rule": "capture_frontend_companions",
                        "priority": 2, "consumed_pending": [p["id"] for p in state["pending_service"] if p["kind"] == "complete_service_coverage"],
                        "contract_refs": producer.get("source_refs", []), "producer_fact_id": producer["id"],
                        "prediction": "The declared non-MCU producer may retain a powered contact; its new duties must be checked from actual facts.",
                        "side_effects": ["Additional paid monitor/capture/read/clear loads; voltage, capacity and retention remain unknown."],
                        "expected_observations": ["paid capture/import/retention and original full service"],
                        "coverage_satisfied": False, "full_service": "UNKNOWN"}))
        for raw, intent in intents:
            try:
                normalized = self.normalize(raw, base_design=parent_design)
                chain = self.engine.expand(normalized["design"], parent_design=parent_design, intent=intent) if self.engine else None
            except (ValueError, TypeError) as exc:
                common["semantic_proposals"].append({"raw_proposal": raw, "intent": intent, "status": "STATIC_OR_FACT_REJECTED", "reason": str(exc)})
                continue
            if chain:
                common["closure_chains"].append(chain)
                choices = [n for n in chain["nodes"] if n["id"] in chain["static_closed_node_ids"]]
            else:
                # An unsupported fact adapter never earns companion-closure
                # credit. A separate full probe remains explicitly unqualified.
                choices = [{"id": None, "inspection": {"design": normalized["design"],
                            "all_static_companions_satisfied": None, "obligations": []}}]
            for node in choices:
                norm = self.normalize(node["inspection"]["design"], base_design=parent_design)
                if not norm["design_patch"]:
                    continue
                derivation = {"intent": intent, "closure_node_id": node["id"],
                              "actual_facts_sha256": node["inspection"].get("facts_sha256"),
                              "static_companion_closure": node["inspection"]["all_static_companions_satisfied"],
                              "new_applicable_obligations_at_this_edge": [o["id"] for o in node["inspection"].get("new_obligations", [])],
                              "introduced_component_duty": intent["kind"] == "INTRODUCE_PUBLIC_PRODUCER",
                              "remaining_unknown_obligations": [o["id"] for o in node["inspection"]["obligations"] if o["status"].startswith("UNKNOWN")],
                              "coverage_satisfied": False, "complete_service": "UNKNOWN"}
                record = {**norm, "id": "closure-proposal-" + digest([seed, round_index, intent, norm["design"]])[:20],
                          "origin": "ACTUAL_CONTRACT_COMPANION_SYNTHESIS", "status": "CANDIDATE",
                          "generation_order": len(common["generation_records"]), "derivations": [],
                          "closure_derivations": [derivation]}
                common["semantic_proposals"].append(deepcopy(record))
                common["generation_records"].append(deepcopy(record))
                if norm["semantic_key"] in by_key:
                    by_key[norm["semantic_key"]].setdefault("closure_derivations", []).append(derivation)
                else:
                    by_key[norm["semantic_key"]] = record
                    common["candidates"].append(record)
        common["actual_fact_calls_cumulative"] = self.engine.fact_calls if self.engine else 0
        return common

    def select(self, generation, *, seen_keys=(), parent_id=None):
        if not generation["relations_enabled"]:
            return super().select(generation, seen_keys=seen_keys, parent_id=parent_id)
        seen = set(seen_keys)
        candidates = [c for c in generation["candidates"] if c["semantic_key"] not in seen]
        if not candidates:
            return None
        ordinary = super().select({**generation, "relations_enabled": False, "rules_consumed": []},
                                  seen_keys=seen, parent_id=parent_id)
        order = {r["id"]: i for i, r in enumerate(ordinary["selection"]["ordering_after"])}
        rows = []
        for c in candidates:
            derivations = c.get("closure_derivations", [])
            priority = max((d["intent"]["priority"] for d in derivations), default=0)
            score = (priority, -len(c["design_patch"]) if priority else 0, -order.get(c["id"], len(order)))
            rows.append({"candidate": c, "score": score})
        rows.sort(key=lambda r: r["score"], reverse=True)
        chosen = deepcopy(rows[0]["candidate"])
        chosen.update(parent_id=parent_id, selection={"relations_enabled": True,
                      "ordering_before": [c["id"] for c in candidates],
                      "ordering_after": [{"id": r["candidate"]["id"], "score": r["score"]} for r in rows],
                      "consumed_derivations": deepcopy(chosen.get("closure_derivations", [])),
                      "coverage_satisfied": False, "full_service": "UNKNOWN",
                      "basis": "Actual source facts and unmet companions, or explicitly admitted conditional probe; static closure never proves service."})
        return chosen
