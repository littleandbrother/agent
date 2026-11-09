"""Public state and constraint-consuming synthesis. No science/provider execution.

The common DomainSpace supplies permissions, not predictions. Every prediction
below is a prospective, explicitly conditional program/engineering hypothesis.
"""
from copy import deepcopy
import hashlib
import json
import math
import random

from bfworld.agentlab.pqe20261024debt.search import DomainSpace

VERSION = "public-service-semantic-synthesis-v1"
PRIVATE = frozenset(("observer_epoch", "observer_event_id", "hidden_truth",
                     "event_truth", "truth_event_id", "sample_index", "created_s"))
STAGES = ("capture", "save", "tx", "receive", "ack", "clear")
COMPLETE = {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}
SOURCE = "bfworld.agentlab."


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def public_copy(value):
    if isinstance(value, dict):
        return {k: public_copy(v) for k, v in value.items() if k not in PRIVATE}
    if isinstance(value, list):
        return [public_copy(v) for v in value]
    return deepcopy(value)


def changed(before, after):
    return {k: deepcopy(v) for k, v in after.items() if before.get(k) != v}


def members(result):
    rows = result.get("results", result.get("cases", [result]))
    if not isinstance(rows, list) or not rows:
        raise ValueError("NONEMPTY_PUBLIC_FAMILY_REQUIRED")
    return rows


def build_state(family_result, prior_result=None, public_contract=None):
    """Absence is an obligation/UNKNOWN cause, never a refuted physical fact."""
    result = public_copy(family_result)
    design = result.get("design")
    if not isinstance(design, dict):
        raise ValueError("PUBLIC_DESIGN_REQUIRED")
    contract = public_copy(public_contract or {})
    conditions, observations, supported, refuted, pending = [], [], [], [], []
    total = dict.fromkeys(STAGES, 0)
    statuses, received = [], 0
    for row in members(result):
        if row.get("design", design) != design:
            raise ValueError("PUBLIC_MEMBER_DESIGN_BINDING")
        cid = row.get("condition_id", row.get("task_id"))
        if cid is None or cid in conditions:
            raise ValueError("UNIQUE_PUBLIC_CONDITIONS_REQUIRED")
        conditions.append(cid)
        valid = row.get("model_valid") is True
        complete = row.get("execution_status") in COMPLETE
        verdict = row.get("public_check", {}).get("verdict", "UNKNOWN")
        status = verdict if valid and complete and verdict in {"PASS", "FAIL"} else "UNKNOWN"
        statuses.append(status)
        facts = row.get("facts", {})
        facts = facts if isinstance(facts, dict) else {}
        activity = facts.get("activity", [])
        activity = activity if isinstance(activity, list) else []
        stage_refs = {s: [] for s in STAGES}
        action_stage = {"capture": "capture", "sample": "capture", "save_commit": "save",
                        "wire_complete": "tx", "ack_commit": "ack", "holding_clear_commit": "clear"}
        for i, event in enumerate(activity):
            stage = action_stage.get(event.get("action")) if isinstance(event, dict) else None
            if stage:
                stage_refs[stage].append("#/facts/activity/" + str(i))
        # LC and DOOR expose accepted receiver records, not truth identifiers.
        receivers = facts.get("receiver_records", [])
        if isinstance(receivers, list):
            stage_refs["receive"] = ["#/facts/receiver_records/" + str(i) for i in range(len(receivers))]
        counts = {s: len(refs) for s, refs in stage_refs.items()}
        for s, count in counts.items():
            total[s] += count
            if count:
                supported.append({"condition_id": cid, "relation": "observed_" + s,
                                  "status": "SUPPORTED_OBSERVATION", "count": count,
                                  "source_refs": stage_refs[s], "result_sha256": row.get("result_sha256")})
        count = row.get("public_check", {}).get("received_count")
        received += count if type(count) is int and count >= 0 else 0
        view = row.get("relationship_view", {})
        relation_rows = view.get("relations", []) if isinstance(view, dict) else []
        for rel in relation_rows:
            bound = (rel.get("design_sha256") == digest(design)
                     and rel.get("result_sha256") == row.get("result_sha256")
                     and rel.get("condition_id") == cid)
            if bound and valid and complete and rel.get("holds") is False and rel.get("evidence_kind") in {"runtime", "execution"}:
                refuted.append({"condition_id": cid, "relation": rel.get("relation_kind"),
                                "status": "REFUTED_BY_EXPLICIT_OBSERVATION",
                                "source_refs": rel.get("refs", []), "relation_id": rel.get("relation_id"),
                                "result_sha256": row.get("result_sha256")})
        domain = {"condition_id": cid, "model_valid": row.get("model_valid"),
                  "execution_status": row.get("execution_status"),
                  "domain_errors": row.get("domain_errors", []), "status": status}
        observations.append({"condition_id": cid, "model_domain": domain,
                             "counts": counts, "source_refs": stage_refs,
                             "public_check": row.get("public_check", {}),
                             "result_sha256": row.get("result_sha256")})

        def owe(kind, refs, observation):
            item = {"condition_id": cid, "kind": kind, "status": "PENDING_SERVICE",
                    "cause_status": "UNKNOWN", "observation": observation,
                    "source_refs": refs, "result_sha256": row.get("result_sha256"),
                    "absence_is_physical_failure": False}
            item["id"] = "pending-" + digest(item)[:20]
            pending.append(item)

        if valid and complete and status != "PASS":
            if counts["save"] > counts["tx"]:
                owe("saved_to_wire", stage_refs["save"], "Public SAVE occurrences exceed completed wire frames; queue/energy/eligibility/timing causes remain unresolved.")
            if counts["tx"] > counts["receive"]:
                owe("wire_to_receiver", stage_refs["tx"], "Public wire frames exceed observed accepted receiver records; link, identity and timing remain unresolved.")
            if status == "FAIL":
                owe("complete_service_coverage", ["#/public_check"], "Original full service failed; observed records alone do not reveal all required physical events or the cause.")
            for rel in refuted:
                if rel["condition_id"] == cid and rel.get("relation") and "identity" in rel["relation"]:
                    owe("identity_retention", rel["source_refs"], "Explicit cross-reset numeric identity conflict between distinct public capture origins.")
            if facts.get("program_state", {}).get("clock_synchronized") is False:
                owe("clock_uncertainty", ["#/facts/program_state/clock_synchronized"], "No current synchronization observed; unpowered absolute time is unavailable.")
            if any(e.get("action") == "capacity_blocked" for e in activity if isinstance(e, dict)):
                owe("record_capacity", ["#/facts/activity"], "Explicit capacity-blocked operation observed.")
    progress = []
    if prior_result is not None:
        prior = build_state(prior_result, public_contract=contract)
        old = {(r["condition_id"], r["relation"]) for r in prior["refuted_relations"]}
        now = {(r["condition_id"], r["relation"]) for r in refuted}
        for cid, rel in sorted(old - now):
            progress.append({"kind": "prior_conflict_no_longer_observed", "condition_id": cid,
                             "relation": rel, "status": "LOCAL_OBSERVATIONAL_PROGRESS",
                             "global_repair_proven": False, "requires_stage_count_gain": False,
                             "prior_public_state_sha256": prior["state_sha256"]})
        for stage in STAGES:
            if total[stage] > prior["stage_counts"][stage]:
                progress.append({"kind": "observed_stage_gain", "stage": stage,
                                 "before": prior["stage_counts"][stage], "after": total[stage]})
    state = {"schema": VERSION + ":state", "design": design, "condition_ids": conditions,
             "observations": observations, "stage_counts": total, "received_count": received,
             "statuses": statuses, "all_pass": all(s == "PASS" for s in statuses),
             "complete_valid": all(s != "UNKNOWN" for s in statuses),
             "supported_relations": supported, "refuted_relations": refuted,
             "pending_service": pending, "progress": progress,
             "raw_public_facts_sha256": digest(result), "public_contract_sha256": digest(contract),
             "scope": {"seen_development_if_prefix": True, "absence_is_not_loss": True,
                       "physical_causes": "UNKNOWN unless explicitly observed", "hidden_truth": False}}
    state["state_sha256"] = digest(state)
    return state


class SemanticFactory:
    def __init__(self, contract, initial_design, *, active_variables=None, validate_fn=None, pool_cap=32):
        self.contract = public_copy(contract)
        self.initial_design = deepcopy(initial_design)
        self.space = DomainSpace(self.contract, initial_design, active_variables, validate_fn)
        if type(pool_cap) is not int or not 4 <= pool_cap <= 32:
            raise ValueError("COMMON_POOL_CAP_4_TO_32")
        self.pool_cap = pool_cap
        self.holder = {"holding_component", "holding_capacity", "holding_overflow", "read_source", "clear_after"} <= set(self.space.domain)
        self.identity = digest({"version": VERSION, "contract": self.contract,
                                "initial": initial_design, "active": self.space.active, "pool_cap": pool_cap})
        self.initial_design = self.canonical(initial_design)

    def canonical(self, design):
        design = deepcopy(design)
        if self.holder:
            if design["holding_component"] == "off":
                for k in ("holding_capacity", "holding_overflow"):
                    design[k] = deepcopy(self.initial_design[k])
                design.update(read_source="contact_only", clear_after="never")
            elif design["read_source"] == "contact_only":
                design["clear_after"] = "never"
        return design

    def semantic_key(self, design):
        return digest(self.canonical(design))

    def normalize(self, design, *, base_design=None):
        base = deepcopy(base_design if base_design is not None else self.initial_design)
        raw = self.space.validate(design)
        if not set(changed(base, raw)) <= set(self.space.active):
            raise ValueError("EDITS_OUTSIDE_ACTIVE_VARIABLES")
        canonical = self.canonical(raw)
        self.space.validate(canonical)
        patch = changed(self.canonical(base), canonical)
        if not set(patch) <= set(self.space.active):
            raise ValueError("CANONICAL_PATCH_OUTSIDE_AUTHORITY")
        return {"raw_proposal": raw, "design": canonical, "design_patch": patch,
                "raw_patch": changed(base, raw), "normalized_inactive_fields": changed(raw, canonical),
                "semantic_key": digest(canonical), "inactive_only": bool(changed(base, raw)) and not patch,
                "empirical_status": "UNKNOWN"}

    def _bound(self, key, value):
        spec = self.space.domain[key]
        value = min(spec["max"], max(spec["min"], value))
        return int(math.ceil(value)) if spec.get("kind", spec.get("type")) in {"integer", "int"} else value

    def _rules(self, parent, state):
        """Emit predicates and algebra, not a cached repair or field-match score."""
        if state["all_pass"] or not state["complete_valid"]:
            return []
        rules = []
        domain = self.space.domain
        kinds = {p["kind"] for p in state["pending_service"]}
        tasks = self.contract.get("tasks", [])
        first_task = tasks[0] if tasks else self.contract
        components = first_task.get("components", {})
        sources = ["public_contract:design_domain", "public_state:pending_service"]

        def add(rule, kind, patch, prediction, effects, expected, predicate, priority, refs):
            patch = {k: deepcopy(v) for k, v in patch.items() if k in self.space.active and parent.get(k) != v}
            if not patch:
                return
            rules.append({"rule": rule, "pending_kind": kind, "patch": patch,
                          "consumed_pending": [p["id"] for p in state["pending_service"] if p["kind"] == kind],
                          "contract_refs": sources + refs, "prediction": prediction,
                          "side_effects": effects, "expected_observations": expected,
                          "predicate": predicate, "priority": priority, "complete_service": "UNKNOWN",
                          "discriminating_full_probe_allowed": True})

        if "identity_retention" in kinds and "persistent_queue" in domain:
            add("durable_sequence_and_queue", "identity_retention", {"persistent_queue": True},
                "Paid SAVE retains seq, last_direction and queue across MCU reset; distinct capture identities may cease to collide.",
                ["Paid NVM SAVE/restore changes energy and capture behavior; sequence-only causality is not claimed."],
                ["Compare public distinct capture origins and numeric seq across observed resets; count gain is unnecessary."],
                {"kind": "equals", "values": {"persistent_queue": True}}, 5,
                [SOURCE + "pqe20261022.door_program:DoorProgram.reset/advance"])

        if "saved_to_wire" in kinds and {"esr_ohm", "capacitance_f", "tx_gate_v", "brownout_v"} <= set(domain):
            tx_a, tx_s = components.get("tx_a"), components.get("tx_s")
            write_a, write_s = components.get("write_a"), components.get("write_s")
            if all(isinstance(x, (int, float)) and x > 0 for x in (tx_a, tx_s, write_a, write_s)):
                esr = domain["esr_ohm"]["min"]
                reserve = parent.get("tx_reserve_v", 0.)
                charge = tx_a * tx_s + write_a * write_s
                headroom = parent["tx_gate_v"] - parent["brownout_v"] - reserve - esr * tx_a
                if headroom > 0:
                    cap = self._bound("capacitance_f", max(parent["capacitance_f"], math.nextafter(charge / headroom, math.inf)))
                    add("tx_charge_headroom", "saved_to_wire", {"esr_ohm": esr, "capacitance_f": cap},
                        "Reducing series drop and sizing charge storage to the declared TX+write load may permit complete frames from the existing gate; missing TX cause is still UNKNOWN.",
                        ["Larger C delays boot and changes harvested source loading.", "Lower ESR reduces resistive loss; service and link availability remain unknown."],
                        ["At least one completed wire frame for an existing saved record, or explicit repeated interruption/gate evidence refuting this probe."],
                        {"kind": "tx_charge", "charge_c": charge, "tx_a": tx_a, "reserve_v": reserve}, 6,
                        ["public_contract:tasks/0/components", SOURCE + "pqe20261023bold.firmware:DoorProgram.effective_tx_gate"])

        if "complete_service_coverage" in kinds and "startup_v" in domain:
            lower = max(domain["startup_v"]["min"], math.nextafter(parent.get("brownout_v", 0.), math.inf))
            add("earlier_powered_sampling", "complete_service_coverage", {"startup_v": self._bound("startup_v", lower)},
                "Lower legal boot threshold permits earlier powered sampling; it may expose capture opportunities absent at the present threshold, without asserting missing events or a known cause.",
                ["Less voltage reserve at boot may increase brownouts and paid reboot load."],
                ["Compare boot timing, capture/SAVE occurrences and original complete service; additional brownouts can refute the benefit."],
                {"kind": "upper_bound", "field": "startup_v", "value": lower}, 3,
                [SOURCE + ("pqe20261022.lcpv20261023:simulate" if "sample_period_s" in domain else "pqe20261022.door_program:DoorProgram.begin_step"), "public_contract:startup/brownout domain"])

        if self.holder and "complete_service_coverage" in kinds:
            enabled = next((v for v in domain["holding_component"].get("values", []) if v != "off"), None)
            if enabled and "holding_then_contact" in domain["read_source"].get("values", []):
                for clear, durable in (("save", True), ("ack", parent.get("persistent_queue", False))):
                    patch = {"holding_component": enabled, "read_source": "holding_then_contact", "clear_after": clear,
                             "persistent_queue": durable}
                    add("powered_capture_handoff_" + clear, "complete_service_coverage", patch,
                        "A paid independently powered capture/read path may retain a contact until MCU import. Clear follows " + ("durable SAVE; ACK is not required for holder release." if clear == "save" else "actual receiver-confirmed ACK; no future gateway oracle."),
                        ["Adds monitor/capture/read/clear loads and bounded FIFO pressure.", "Voltage loss can erase holder state; NVM and receiver acceptance provide different guarantees."],
                        ["Observe holder capture, paid read, SAVE durability and matching clear; compare overflow, reset and original service."],
                        {"kind": "equals", "values": patch}, 2,
                        [SOURCE + "pqe20261024debt.facts:describe_contract", SOURCE + "pqe20261024debt.consumer:HoldingDoorProgram"])

        # Existing LC contracts expose different state and actions. No holder,
        # independent RTC, ideal air or constructed DOOR field is invented.
        if "sample_period_s" in domain and "complete_service_coverage" in kinds:
            service = first_task.get("service", {})
            # A legal domain maximum does not establish a service cadence.
            # Without an explicit numeric service interval this rule is a no-op.
            period = next((service[k] for k in ("required_sample_period_s", "sample_period_s", "maximum_sample_interval_s", "max_sample_period_s")
                           if isinstance(service.get(k), (int, float))), parent["sample_period_s"])
            add("lc_sample_energy_service_boundary", "complete_service_coverage",
                {"sample_period_s": self._bound("sample_period_s", period)},
                "Use the largest contract-permitted sample interval to reduce acquisition load while retaining the stated service cadence; exact deadline satisfaction remains unknown.",
                ["Later acquisitions change queue timing and receiver age checks."],
                ["Compare actual sample intervals, committed records, energy and unchanged full service."],
                {"kind": "equals", "values": {"sample_period_s": self._bound("sample_period_s", period)}}, 3,
                [SOURCE + "pqe20261022.lcpv20261023:simulate", "public_contract:service"])
        if "record_capacity" in kinds and "nvm_capacity_records" in domain:
            cap = domain["nvm_capacity_records"]["max"]
            add("lc_capacity_after_observed_block", "record_capacity", {"nvm_capacity_records": cap},
                "More legal NVM slots may prevent the explicitly observed capacity block; no delivery improvement is assumed.",
                ["More retained history can increase drain time."], ["capacity_blocked count and pending/received records"],
                {"kind": "equals", "values": {"nvm_capacity_records": cap}}, 4,
                [SOURCE + "pqe20261022.lcpv20261023:complete/save"])
        if "saved_to_wire" in kinds and "area_cm2" in domain:
            patch = {"area_cm2": domain["area_cm2"]["max"]}
            if "persistent_records" in domain:
                patch["persistent_records"] = True
            add("lc_retention_and_supply_probe", "saved_to_wire", patch,
                "Larger permitted PV area increases source current under the same public optical input; durable records preserve the pending queue across power loss. Scheduling/link causes remain unresolved.",
                ["Larger area is a structural cost; supply and thermal dynamics still use the original consumer."],
                ["Compare completed frames, pending durable records, supply energy and full deadlines."],
                {"kind": "equals", "values": patch}, 5,
                [SOURCE + "pqe20261022.lcpv20261023:pv/complete"])
        return rules

    def generate(self, parent_design, state, *, seed, round_index, relations_enabled=True, restart=False):
        if self.semantic_key(parent_design) != self.semantic_key(state["design"]):
            raise ValueError("STATE_PARENT_BINDING")
        parent = deepcopy(parent_design)
        rng = random.Random(int(digest([seed, "common-generation", round_index, self.semantic_key(parent)])[:16], 16))
        before = digest(rng.getstate())
        axis = [(p, "AXIS_DOMAIN") for p in self.space.single_patches(parent)]
        rng.shuffle(axis)
        joint = [(self.space.random_patch(parent, rng, width=len(self.space.active) if i < 4 else None),
                  "FULL_DOMAIN_RESTART" if i < 4 else "JOINT_MUTATION") for i in range(16)]
        rng.shuffle(joint)
        common = []
        for i in range(max(len(axis), len(joint))):
            if i < len(joint):
                common.append((joint[i][0], joint[i][1], None))
            if i < len(axis):
                common.append((axis[i][0], axis[i][1], None))
        common = common[:self.pool_cap]
        after = digest(rng.getstate())
        rules = self._rules(parent, state) if relations_enabled else []
        proposals = common + [(r["patch"], "RELATION_DERIVED", r) for r in rules]
        records, candidates, seen = [], [], {}
        for index, (patch, origin, rule) in enumerate(proposals):
            raw = {**deepcopy(parent), **deepcopy(patch)}
            proposal_id = "proposal-" + digest([seed, round_index, index, raw])[:20]
            row = {"id": proposal_id, "origin": origin, "raw_proposal": raw,
                   "consumption": deepcopy(rule), "generation_order": index}
            try:
                normalized = self.normalize(raw, base_design=parent)
                row.update(normalized)
                key = normalized["semantic_key"]
                if not normalized["design_patch"]:
                    row["status"] = "SEMANTIC_NOOP_FILTERED"
                elif key in seen:
                    row.update(status="DUPLICATE_WITH_PROVENANCE", duplicate_of=seen[key]["id"])
                    if rule:
                        seen[key]["derivations"].append(deepcopy(rule))
                else:
                    row["status"] = "CANDIDATE"
                    candidate = {**deepcopy(row), "derivations": [deepcopy(rule)] if rule else []}
                    candidates.append(candidate)
                    seen[key] = candidate
            except (ValueError, TypeError) as exc:
                row.update(status="STATIC_REJECTED", reason=str(exc))
            records.append(row)
        return {"schema": VERSION + ":generation", "factory_identity": self.identity,
                "seed": seed, "round_index": round_index, "restart": restart,
                "relations_enabled": relations_enabled, "state_sha256": state["state_sha256"],
                "raw_public_facts_sha256": state["raw_public_facts_sha256"],
                "common_rng_before_sha256": before, "common_rng_after_sha256": after,
                "common_raw_proposals": [r["raw_proposal"] for r in records[:len(common)]],
                "rules_consumed": rules, "generation_records": records, "candidates": candidates,
                "static_proposals": len(proposals), "scientific_inputs": 0, "model_requests": 0}

    @staticmethod
    def _satisfies(design, rule):
        p = rule["predicate"]
        if p["kind"] == "equals":
            return all(design.get(k) == v for k, v in p["values"].items())
        if p["kind"] == "upper_bound":
            return design[p["field"]] <= p["value"]
        if p["kind"] == "tx_charge":
            margin = design["tx_gate_v"] - design["brownout_v"] - p["reserve_v"] - design["esr_ohm"] * p["tx_a"]
            return margin > 0 and design["capacitance_f"] * margin >= p["charge_c"] - 1e-15
        return False

    def _distance(self, a, b):
        distance = 0.
        for k in self.space.active:
            spec = self.space.domain[k]
            if "min" in spec and "max" in spec:
                distance += abs(a[k] - b[k]) / max(1e-15, spec["max"] - spec["min"])
            else:
                distance += float(a[k] != b[k])
        return distance

    def select(self, generation, *, seen_keys=(), parent_id=None):
        candidates = [c for c in generation["candidates"] if c["semantic_key"] not in set(seen_keys)]
        if not candidates:
            return None
        # Distance is a common novelty criterion against the registered initial;
        # relation constraint satisfaction and minimal effective changes are the
        # sole semantic terms. Hashes bind data and seed RNG, never rank candidates.
        ranked = []
        for c in candidates:
            constraints = [r for r in generation["rules_consumed"] if self._satisfies(c["design"], r)]
            semantic = max((r["priority"] for r in constraints), default=0)
            novelty = self._distance(c["design"], self.initial_design)
            mode = generation["round_index"] % 3
            desired = ("JOINT_MUTATION", "FULL_DOMAIN_RESTART", "AXIS_DOMAIN")[mode]
            general = (int(c["origin"] == desired), novelty, -c["generation_order"])
            score = (semantic, -len(c["design_patch"]), *general) if semantic else (0, 0, *general)
            ranked.append({"candidate": c, "score": score, "satisfied_rules": [r["rule"] for r in constraints]})
        ranked.sort(key=lambda r: r["score"], reverse=True)
        chosen = ranked[0]
        c = deepcopy(chosen["candidate"])
        c.update(parent_id=parent_id, selection={"relations_enabled": generation["relations_enabled"],
                 "satisfied_rules": chosen["satisfied_rules"], "score": chosen["score"],
                 "consumed_constraints": [deepcopy(r) for r in generation["rules_consumed"] if r["rule"] in chosen["satisfied_rules"]],
                 "ordering_before": [x["id"] for x in candidates],
                 "ordering_after": [{"id": x["candidate"]["id"], "score": x["score"],
                                      "satisfied_rules": x["satisfied_rules"]} for x in ranked],
                 "scope": "Constraint satisfaction is a conditional prediction, not empirical service."})
        return c


class DeterministicController:
    """D/R differ only in relation consumption during generation and selection."""
    def __init__(self, condition, factory, initial_result, *, scope=None, seed=314159,
                 max_new_candidates=6, **kwargs):
        if condition not in {"D", "R", "OFF", "ON", "G"}:
            raise ValueError("CONDITION_D_R_G_REQUIRED")
        if type(max_new_candidates) is not int or not 1 <= max_new_candidates <= 6:
            raise ValueError("SIX_NEW_CANDIDATES_MAX")
        self.condition, self.factory = condition, factory
        self.relations_enabled = condition in {"R", "ON"}
        self.scope, self.seed = deepcopy(scope or {}), seed
        self.max_new_candidates, self.slots = max_new_candidates, 0
        state = build_state(initial_result, public_contract=factory.contract)
        if factory.semantic_key(state["design"]) != factory.semantic_key(factory.initial_design):
            raise ValueError("COMMON_INITIAL_BINDING")
        self.conditions = state["condition_ids"]
        self.root_id = "node-" + factory.semantic_key(state["design"])[:24]
        self.nodes = {self.root_id: {"id": self.root_id, "design": state["design"], "state": state,
                                    "parent_id": None, "slot": 0, "expansions": 0}}
        self.seen = {factory.semantic_key(state["design"])}
        self.pending, self.history, self.generations = None, [], []
        self.winner = self.root_id if state["all_pass"] else None
        self.termination = "INITIAL_COMPLETE_SERVICE_PASS" if self.winner else (
            None if state["complete_valid"] else "INITIAL_TOOL_OR_DOMAIN_UNKNOWN")

    @staticmethod
    def _fitness(node):
        s = node["state"]
        return (s["statuses"].count("PASS"), s["received_count"], s["stage_counts"]["save"])

    def _parent(self):
        nodes = list(self.nodes.values())
        # Same outcome/behavior-diversity archive and failed-parent access for D/R.
        # No low-score node is deleted. Alternation includes deterministic restart.
        if self.slots % 3 == 1:
            return self.nodes[self.root_id]
        if self.slots % 3 == 2:
            return min(nodes, key=lambda n: (n["expansions"], -self.factory._distance(n["design"], self.factory.initial_design), n["slot"]))
        return max(nodes, key=lambda n: (self._fitness(n), -n["expansions"], -n["slot"]))

    def step(self, budget_snapshot=None):
        if self.pending:
            raise ValueError("EVALUATION_PENDING")
        if self.termination or self.slots >= self.max_new_candidates:
            return None
        parent = self._parent()
        generation = self.factory.generate(parent["design"], parent["state"], seed=self.seed,
                   round_index=self.slots, relations_enabled=self.relations_enabled, restart=self.slots % 3 == 1)
        self.generations.append(generation)
        selected = self.factory.select(generation, seen_keys=self.seen, parent_id=parent["id"])
        if selected is None:
            self.termination = "NO_UNSEEN_LEGAL_CANDIDATE"
            return None
        return self._submit(selected, parent)

    def _submit(self, selected, parent):
        action = {**deepcopy(selected), "request_id": "request-" + digest([self.seed, self.slots + 1, selected["design"]])[:20],
                  "slot": self.slots + 1, "parent_id": parent["id"], "operation": "evaluate",
                  "budget_semantics": "Six new designs; common initial excluded.", "condition": self.condition}
        self.pending = action
        parent["expansions"] += 1
        return deepcopy(action)

    def update(self, result):
        if not self.pending:
            raise ValueError("NO_PENDING_EVALUATION")
        action = self.pending
        if self.factory.semantic_key(result.get("design", {})) != self.factory.semantic_key(action["design"]):
            raise ValueError("EVALUATION_DESIGN_BINDING")
        parent = self.nodes[action["parent_id"]]
        # Prior state is used for progress without inventing a second observation.
        state = build_state(result, public_contract=self.factory.contract)
        if set(state["condition_ids"]) != set(self.conditions) or len(state["condition_ids"]) != len(self.conditions):
            raise ValueError("SAME_COMPLETE_CONDITION_FAMILY_REQUIRED")
        old_refuted = {(r["condition_id"], r["relation"]) for r in parent["state"]["refuted_relations"]}
        now_refuted = {(r["condition_id"], r["relation"]) for r in state["refuted_relations"]}
        state["progress"] = [{"kind": "prior_conflict_no_longer_observed", "condition_id": cid,
                              "relation": rel, "requires_stage_count_gain": False,
                              "global_repair_proven": False} for cid, rel in sorted(old_refuted - now_refuted)]
        state["progress"].extend({"kind": "observed_stage_gain", "stage": s,
                                  "before": parent["state"]["stage_counts"][s], "after": state["stage_counts"][s]}
                                 for s in STAGES if state["stage_counts"][s] > parent["state"]["stage_counts"][s])
        state.pop("state_sha256")
        state["state_sha256"] = digest(state)
        key = self.factory.semantic_key(action["design"])
        self.slots += 1
        nid = "node-" + key[:24]
        self.nodes[nid] = {"id": nid, "design": action["design"], "state": state,
                           "parent_id": parent["id"], "slot": self.slots, "expansions": 0}
        self.seen.add(key)
        self.history.append({"slot": self.slots, "node_id": nid, "parent_id": parent["id"],
                             "design": action["design"], "selection": action.get("selection"),
                             "consumption": action.get("derivations", []), "state": state})
        self.pending = None
        if state["all_pass"]:
            self.winner, self.termination = nid, "COMPLETE_SERVICE_PASS"
        elif not state["complete_valid"]:
            self.termination = "TOOL_OR_DOMAIN_UNKNOWN"
        elif self.slots >= self.max_new_candidates:
            self.termination = "NEW_CANDIDATE_BUDGET_EXHAUSTED"
        return deepcopy(self.history[-1])

    def stop(self):
        chosen = self.nodes[self.winner] if self.winner else max(self.nodes.values(), key=self._fitness)
        return {"condition": self.condition, "termination": self.termination or "FINITE_STOP",
                "adopted": self.winner is not None, "all_condition_PASS": self.winner is not None,
                "design": deepcopy(chosen["design"]), "final_node_id": chosen["id"],
                "new_evaluated_designs": self.slots, "initial_evaluations_charged_to_slots": 0,
                "paid_model_requests": 0, "algorithm_identity": "deterministic developer algorithm"}

    def snapshot(self):
        return {"schema": VERSION + ":controller", "condition": self.condition, "seed": self.seed,
                "scope": self.scope, "slots": self.slots, "max_new_candidates": self.max_new_candidates,
                "initial_excluded": True, "root_id": self.root_id, "nodes": deepcopy(list(self.nodes.values())),
                "history": deepcopy(self.history), "generations": deepcopy(self.generations),
                "pending": deepcopy(self.pending), "termination": self.termination, "winner": self.winner,
                "paid_model_requests": 0}


class FreeJointInterface(DeterministicController):
    """Common legal full-object submission. G receives no semantic suggestions."""
    def __init__(self, factory, initial_result, *, scope=None, seed=314159, **kwargs):
        super().__init__("G", factory, initial_result, scope=scope, seed=seed, **kwargs)

    def submit(self, full_design, *, parent_id=None):
        if self.pending:
            raise ValueError("EVALUATION_PENDING")
        if self.termination or self.slots >= self.max_new_candidates:
            raise ValueError("SCIENTIFIC_CANDIDATE_BUDGET_CLOSED")
        parent = self.nodes[parent_id or self.root_id]
        candidate = self.factory.normalize(full_design, base_design=parent["design"])
        if candidate["semantic_key"] in self.seen or not candidate["design_patch"]:
            raise ValueError("ALREADY_EVALUATED_OR_INACTIVE_ONLY_DESIGN")
        candidate.update(origin="FREE_JOINT_SUBMISSION", derivations=[], selection={"free_full_design": True})
        return self._submit(candidate, parent)

    def candidate_tool(self, *, parent_id=None):
        parent = self.nodes[parent_id or self.root_id]
        return self.factory.generate(parent["design"], parent["state"], seed=self.seed,
                round_index=self.slots, relations_enabled=False)

    def finalize(self, full_design):
        key = self.factory.semantic_key(full_design)
        node = next((n for n in self.nodes.values() if self.factory.semantic_key(n["design"]) == key), None)
        if node is None:
            raise ValueError("FINAL_DESIGN_MUST_HAVE_FULL_EVALUATION")
        return {"design": deepcopy(node["design"]), "final_node_id": node["id"],
                "adopted": node["state"]["all_pass"], "all_condition_PASS": node["state"]["all_pass"],
                "new_evaluated_designs": self.slots}
