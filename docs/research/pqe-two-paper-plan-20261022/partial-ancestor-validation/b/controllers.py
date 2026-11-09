"""Frozen public-domain candidate factory and G/D/R/A controller conditions.

Pure controller code: no consumer, private qualification, evaluator or provider
is imported. Every expansion parent has an actual complete public family result.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import random

from bfworld.agentlab.pqe20261024debt.search import DomainSpace

VERSION = "partial-ancestor-controllers-v1"
SEEDS = (314159, 271828, 161803)
STAGES = ("produced", "read", "saved", "wire", "received", "ack", "clear")
STAGE_ALIASES = {"capture": "produced", "captured": "produced", "production": "produced",
                 "holding_capture": "produced", "read_commit": "read", "save_commit": "saved",
                 "wire_complete": "wire", "transmitted": "wire", "receive": "received",
                 "accepted": "received", "acknowledged": "ack", "ack_commit": "ack",
                 "cleared": "clear", "clear_commit": "clear"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def changed(before, after):
    return {key: deepcopy(after[key]) for key in after if before.get(key) != after[key]}


def rng_for(seed, *parts):
    return random.Random(int(digest([seed, *parts])[:16], 16))


class CandidateFactory:
    """One full-design factory shared unchanged by all conditions.

    Existing CODEBT inactive-field semantics are explicit and source-bound in
    ``contract_identity``. Other domains get no speculative normalization.
    Every enabled component receives a complete, domain-validated parameter map.
    """
    def __init__(self, contract, initial_design, *, active_variables=None,
                 validate_fn=None, pool_cap=32):
        if type(pool_cap) is not int or not 1 <= pool_cap <= 32:
            raise ValueError("FACTORY_POOL_CAP")
        self.contract = deepcopy(contract)
        self.initial_design = deepcopy(initial_design)
        self.space = DomainSpace(contract, initial_design, active_variables, validate_fn)
        self.pool_cap = pool_cap
        domain = self.space.domain
        self.holder_rules = ({"holding_component", "holding_capacity", "holding_overflow",
                              "read_source", "clear_after"} <= set(domain)
                             and "off" in domain["holding_component"].get("values", []))
        self.normalization_rules = ({
            "holder_off": {key: deepcopy(initial_design[key]) for key in
                           ("holding_capacity", "holding_overflow")},
            "holder_off_program": {"read_source": "contact_only", "clear_after": "never"},
            "contact_only_clear": "never",
            "source": "pqe20261024debt.consumer off route; HoldingDoorProgram read/clear guards",
            "claim": "Semantic identity only for declared inactive fields; no active-field repair."}
            if self.holder_rules else {})
        self.identity = digest({"version": VERSION, "contract": contract,
                                "active_variables": self.space.active, "pool_cap": pool_cap,
                                "normalization_rules": self.normalization_rules})
        self.initial_design = self.normalize(initial_design)["design"]

    def normalize(self, full_design, *, base_design=None):
        raw = self.space.validate(full_design)
        base = deepcopy(base_design if base_design is not None else self.initial_design)
        # A complete object is not authority to edit an inactive task variable.
        if not set(changed(base, raw)) <= set(self.space.active):
            raise ValueError("FULL_OBJECT_EDITS_OUTSIDE_ACTIVE_VARIABLES")
        design = deepcopy(raw)
        if self.holder_rules:
            if design["holding_component"] == "off":
                design.update(deepcopy(self.normalization_rules["holder_off"]))
                design.update(deepcopy(self.normalization_rules["holder_off_program"]))
            elif design["read_source"] == "contact_only":
                design["clear_after"] = "never"
        # Only representation of physically inactive fields may leave the
        # active set. Actual executable changes must still be authorized.
        self.space.validate(design)
        patch = changed(self.canonical(base), design)
        if not set(patch) <= set(self.space.active):
            raise ValueError("CANONICAL_PATCH_OUTSIDE_TASK_AUTHORITY")
        return {"schema": "partial-ancestor-full-candidate-v1", "raw_proposal": raw,
                "design": design, "semantic_key": digest(design),
                "raw_patch": changed(base, raw), "design_patch": patch,
                "normalized_inactive_fields": changed(raw, design),
                "empirical_status": "UNKNOWN", "factory_identity": self.identity,
                "inactive_only": bool(changed(base, raw)) and not patch}

    def canonical(self, design):
        design = deepcopy(design)
        if self.holder_rules:
            if design["holding_component"] == "off":
                design.update(deepcopy(self.normalization_rules["holder_off"]))
                design.update(deepcopy(self.normalization_rules["holder_off_program"]))
            elif design["read_source"] == "contact_only":
                design["clear_after"] = "never"
        return design

    def semantic_key(self, design):
        return digest(self.canonical(design))

    def generate(self, parent_design, *, seed, round_index, restart=False, relationships=()):
        """Same seeded proposals for the same parent, round and shared facts.

        Relations are recorded as shared inputs; only R/A selection uses their
        meaning. The factory never emits a unique complete-repair macro.
        """
        parent = deepcopy(parent_design)
        rng = rng_for(seed, "factory", round_index, self.semantic_key(parent))
        patches = [(patch, "AXIS_DOMAIN") for patch in self.space.single_patches(parent)]
        rng.shuffle(patches)
        # Give joint proposals an equal, fixed pool reservation. Sampling all
        # fields can jump straight to a full design in every condition.
        joint = []
        for index in range(16):
            width = len(self.space.active) if index < 4 else None
            joint.append((self.space.random_patch(parent, rng, width=width),
                          "FULL_DOMAIN_RESTART" if index < 4 else "JOINT_MUTATION"))
        rng.shuffle(joint)
        proposals = []
        for index in range(max(len(patches), len(joint))):
            if index < len(joint):proposals.append(joint[index])
            if index < len(patches):proposals.append(patches[index])
        proposals = proposals[:self.pool_cap]
        candidates, records, seen = [], [], {}
        for index, (patch, origin) in enumerate(proposals):
            raw = {**deepcopy(parent), **deepcopy(patch)}
            row = {"proposal_id": "p-" + digest([seed, round_index, index, raw])[:20],
                   "parent_semantic_key": self.semantic_key(parent),
                   "origin": origin, "raw_proposal": raw}
            try:
                candidate = self.normalize(raw, base_design=parent)
                row.update(candidate)
                if not candidate["design_patch"]:
                    row["status"] = "SEMANTIC_NOOP_FILTERED"
                elif candidate["semantic_key"] in seen:
                    row.update(status="POOL_DUPLICATE_FILTERED", duplicate_of=seen[candidate["semantic_key"]])
                else:
                    row["status"] = "CANDIDATE"
                    candidate.update(id=row["proposal_id"], origin=origin)
                    candidates.append(candidate)
                    seen[candidate["semantic_key"]] = candidate["id"]
            except (ValueError, TypeError) as exc:
                row.update(status="STATIC_REJECTED", reason=str(exc))
            records.append(row)
        return {"factory_identity": self.identity, "seed": seed, "round_index": round_index,
                "restart": restart, "parent_semantic_key": self.semantic_key(parent),
                "shared_relationships_sha256": digest(list(relationships)),
                "candidates": candidates, "generation_records": records,
                "raw_proposals": len(proposals), "static_checks": len(proposals)}


def _has_private_key(value):
    if isinstance(value, dict):
        return any(key == "observer_epoch" or _has_private_key(item) for key, item in value.items())
    return isinstance(value, list) and any(_has_private_key(item) for item in value)


def relationship_rows(result, condition_id):
    """Consume the host's common public projection, never derive hidden truth."""
    view = result.get("relationship_view", result.get("relationships", []))
    rows = view.get("relations", []) if isinstance(view, dict) else view
    if not isinstance(rows, list):
        raise ValueError("PUBLIC_RELATION_LIST_REQUIRED")
    out = []
    for original in rows:
        if not isinstance(original, dict) or not original.get("refs"):
            continue
        row = deepcopy(original)
        if _has_private_key(row) or "observer_epoch" in json.dumps(row.get("record_key")):
            raise ValueError("PRIVATE_OBSERVER_IDENTITY_FORBIDDEN")
        row.setdefault("condition_id", condition_id)
        if row["condition_id"] != condition_id:
            raise ValueError("PUBLIC_RELATION_CONDITION_BINDING")
        if row.get("design_sha256", digest(result["design"])) != digest(result["design"]):
            raise ValueError("PUBLIC_RELATION_DESIGN_BINDING")
        if row.get("result_sha256", result.get("result_sha256")) != result.get("result_sha256"):
            raise ValueError("PUBLIC_RELATION_RESULT_BINDING")
        row.setdefault("evidence_kind", "UNKNOWN")
        row.setdefault("holds", None)
        row.setdefault("relation_id", "rel-" + digest(row)[:24])
        row["stage"] = STAGE_ALIASES.get(row.get("stage"), row.get("stage"))
        out.append(row)
    return out


def summarize(result, design, conditions, factory):
    if (not isinstance(result, dict) or not isinstance(result.get("design"), dict)
            or set(result["design"]) != set(factory.space.domain)
            or factory.semantic_key(result["design"]) != factory.semantic_key(design)):
        raise ValueError("WHOLE_DESIGN_RESULT_BINDING")
    rows = result.get("results", result.get("cases", [result]))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("PUBLIC_FAMILY_ROWS_REQUIRED")
    ids = [row.get("condition_id", row.get("task_id")) for row in rows]
    if not rows or len(ids) != len(conditions) or set(ids) != set(conditions):
        raise ValueError("COMPLETE_UNCHANGED_CONDITION_FAMILY_REQUIRED")
    statuses, received, relations, refs, compact = [], 0, [], [], []
    for row, cid in zip(rows, ids):
        if factory.semantic_key(row.get("design", result["design"])) != factory.semantic_key(design):
            raise ValueError("MEMBER_DESIGN_BINDING")
        complete = row.get("execution_status") in {"COMPLETE", "COMPLETED", "OK", "SUCCESS"}
        valid = row.get("model_valid") is True
        verdict = row.get("public_check", {}).get("verdict", "UNKNOWN")
        status = verdict if complete and valid and verdict in {"PASS", "FAIL"} else "UNKNOWN"
        statuses.append(status)
        count = row.get("public_check", {}).get("received_count")
        if type(count) is int and count >= 0:received += count
        if complete and valid:
            member = {**row, "design": row.get("design", result["design"])}
            relations.extend(relationship_rows(member, cid))
        if row.get("result_sha256"):refs.append(row["result_sha256"])
        compact.append({"condition_id": cid, "execution_status": row.get("execution_status"),
                        "model_valid": row.get("model_valid"), "public_check": deepcopy(row.get("public_check")),
                        "result_sha256": row.get("result_sha256"),
                        "public_object_ref": row.get("public_object_ref")})
    evidence = {stage: set() for stage in STAGES}
    for row in relations:
        stage, record = row.get("stage"), row.get("record_key")
        if (row.get("evidence_kind") in {"execution", "runtime"} and row.get("holds") is True
                and stage in evidence and record is not None):
            evidence[stage].add(digest([row["condition_id"], record]))
    capabilities = [len(evidence[stage]) for stage in STAGES]
    return {"all_pass": all(status == "PASS" for status in statuses), "statuses": statuses,
            "complete_valid": all(status != "UNKNOWN" for status in statuses),
            "condition_pass_count": statuses.count("PASS"), "received_count": received,
            "capabilities": capabilities, "relationships": relations,
            "behavior_signature": digest([statuses, received, capabilities]), "refs": refs,
            "members": compact}


def targets(summary):
    return [row for row in summary["relationships"]
            if row.get("evidence_kind") in {"execution", "runtime"}
            and row.get("holds") is False and row.get("refs")]


@dataclass
class Node:
    id: str
    design: dict
    semantic_key: str
    parent: object
    summary: dict
    slot: int
    low_score: bool
    gained_stages: list
    useful_failed: bool
    selected_by: dict

    def to_dict(self):return deepcopy(self.__dict__)


class DeterministicController:
    def __init__(self, condition, factory, initial_result, *, scope, seed,
                 max_slots=6, count_initial=True, archive_capacity=8):
        if condition not in {"D", "R", "A", "G"}:raise ValueError("CONDITION")
        if seed not in SEEDS:raise ValueError("PREREGISTERED_SEED_REQUIRED")
        if not 1 <= max_slots <= 6 or archive_capacity != 8:raise ValueError("COMMON_CAPACITY_REQUIRED")
        self.condition, self.factory, self.seed = condition, factory, seed
        self.scope = deepcopy(scope)
        self.conditions = list(scope["conditions"])
        self.max_slots, self.archive_capacity = max_slots, archive_capacity
        self.slots = int(count_initial)
        self.count_initial = bool(count_initial)
        self.round = 0
        self.nodes, self.by_semantic, self.events = {}, {}, []
        self.pending, self.termination, self.winner = None, None, None
        self.raw_proposals, self.static_checks, self.expansions = 0, 0, 0
        summary = summarize(initial_result, factory.initial_design, self.conditions, factory)
        key = factory.semantic_key(factory.initial_design)
        self.root_id = "node-" + key[:24]
        root = Node(self.root_id, deepcopy(factory.initial_design), key, None, summary,
                    0, False, [], False, {"kind": "SHARED_INITIAL"})
        self.nodes[root.id], self.by_semantic[key] = root, root.id
        self.archive = [root.id]
        if summary["all_pass"]:self.winner, self.termination = root.id, "INITIAL_COMPLETE_SERVICE_PASS"
        elif not summary["complete_valid"]:self.termination = "INITIAL_TOOL_OR_DOMAIN_UNKNOWN"

    def _eligible(self, node):
        return node.id == self.root_id or not (self.condition == "A" and node.low_score)

    def _fitness(self, node):
        s = node.summary
        return (s["condition_pass_count"], s["received_count"], *s["capabilities"])

    def _parent(self):
        allowed = [self.nodes[key] for key in self.archive if self._eligible(self.nodes[key])]
        blocked = [key for key in self.archive if not self._eligible(self.nodes[key])]
        self.events.append({"event": "PARENT_ELIGIBILITY", "round": self.round,
                            "eligible": [node.id for node in allowed], "forbidden": blocked,
                            "initial_exception": self.root_id})
        restart = self.round % 3 == 0
        if restart:return self.nodes[self.root_id], True, {"kind": "COMMON_RESTART"}
        rng = rng_for(self.seed, "parent", self.round)
        if self.condition in {"R", "A"}:
            useful = [node for node in allowed if node.useful_failed and targets(node.summary)]
            if useful:
                rng.shuffle(useful)
                parent = max(useful, key=lambda n: (len(n.gained_stages), self._fitness(n)))
                return parent, False, {"kind": "EXECUTION_GROUNDED_FAILED_ANCESTOR",
                    "gained_stages": parent.gained_stages,
                    "relation_refs": [row["relation_id"] for row in targets(parent.summary)]}
        # Same diverse/elite fallback: alternate elite and seeded behavioral
        # exploration; all archived failed behaviors remain available in D/R.
        ordered = sorted(allowed, key=lambda n: n.id)
        if self.round % 2:
            best = max(self._fitness(n) for n in ordered)
            elite = [n for n in ordered if self._fitness(n) == best]
            parent = rng.choice(elite)
        else:parent = rng.choice(ordered)
        return parent, False, {"kind": "COMMON_DIVERSE_ELITE_PARENT"}

    def _retain(self):
        nodes = list(self.nodes.values())
        # A common Pareto and behavior archive; A's only difference is _eligible.
        nondominated = [n for n in nodes if not any(
            all(a >= b for a, b in zip(self._fitness(other), self._fitness(n)))
            and self._fitness(other) != self._fitness(n) for other in nodes)]
        selected = [self.nodes[self.root_id]]
        represented = {selected[0].summary["behavior_signature"]}
        ordered = sorted(nodes, key=lambda n: (n in nondominated, self._fitness(n), -n.slot), reverse=True)
        for novel_first in (True, False):
            for node in ordered:
                novel = node.summary["behavior_signature"] not in represented
                if node.id in {n.id for n in selected} or (novel_first and not novel):continue
                selected.append(node);represented.add(node.summary["behavior_signature"])
                if len(selected) >= self.archive_capacity:break
            if len(selected) >= self.archive_capacity:break
        self.archive = [node.id for node in selected]
        self.events.append({"event": "COMMON_ARCHIVE", "nodes": self.archive,
                            "rule": "Pareto/capability and behavior diversity, initial retained",
                            "capacity": self.archive_capacity})

    def _candidate_rank(self, candidate, parent):
        patch = set(candidate["design_patch"])
        existing = [self.nodes[key].design for key in self.archive]
        novelty = min(sum(value != prior[key] for key, value in candidate["design"].items()) for prior in existing)
        tie = int(digest([self.seed, "candidate", self.round, candidate["semantic_key"]])[:16], 16)
        if self.condition in {"R", "A"}:
            relations = targets(parent.summary)
            covered = {row["relation_id"] for row in relations
                       if patch.intersection(row.get("depends_on", row.get("affected_fields", [])))}
            # Runtime-supported targets only. No new static obligations, task
            # names, candidate successes or preferred read/clear value occur here.
            return (bool(covered), len(covered), -len(patch), novelty, tie)
        return (novelty, len(patch) >= 2, tie)

    def _submit(self, raw_design, parent, basis, *, origin="FREE_JOINT_SUBMISSION"):
        if self.pending:raise ValueError("UPDATE_PENDING_FIRST")
        if self.termination:return self.stop()
        if self.slots >= self.max_slots:
            self.termination = "SLOT_CAP";return self.stop()
        self.slots += 1
        try:normalized = self.factory.normalize(raw_design, base_design=parent.design)
        except (ValueError, TypeError) as exc:
            row = {"status": "STATIC_REJECTED", "reason": str(exc), "slot": self.slots,
                   "raw_proposal": deepcopy(raw_design), "parent_id": parent.id}
            self.events.append({"event": "SUBMISSION_STATIC_REJECTED", **row})
            self.round += 1
            return row
        reuse = self.by_semantic.get(normalized["semantic_key"])
        request_id = "request-" + digest([self.scope, self.condition, self.seed, self.slots,
                                          normalized["semantic_key"]])[:24]
        action = {"status": "ACTION", "schema": VERSION, "request_id": request_id,
            "parent_id": parent.id, "design": normalized["design"], "base_design": deepcopy(parent.design),
            "conditions": self.conditions, "raw_proposal": normalized["raw_proposal"],
            "normalization": normalized, "slot": self.slots, "semantic_reuse_of": reuse,
            "decision": {"selected_id": normalized["semantic_key"], "actual_input": {
                "operation": "edit", "design_patch": normalized["design_patch"],
                "problem_patch": {"active_variables": list(self.factory.space.active)}},
                "selection_basis": deepcopy(basis)}}
        self.pending = deepcopy(action)
        self.events.append({"event": "SELECT_CHILD", "expanded_parent": parent.id,
            "request_id": request_id, "child_semantic_key": normalized["semantic_key"],
            "design_patch": normalized["design_patch"], "origin": origin,
            "semantic_reuse_of": reuse, "slot": self.slots, "selection_basis": deepcopy(basis)})
        return action

    def step(self, budget_snapshot=None):
        if self.condition == "G":raise ValueError("G_MODEL_MUST_SELECT_FACTORY_OR_FREE_DESIGN")
        if self.pending:raise ValueError("UPDATE_PENDING_FIRST")
        if self.termination:return self.stop()
        if self.slots >= self.max_slots:
            self.termination = "SLOT_CAP";return self.stop()
        parent, restart, basis = self._parent()
        if not self._eligible(parent):raise AssertionError("FORBIDDEN_PARENT_BEFORE_GENERATION")
        pool = self.factory.generate(parent.design, seed=self.seed, round_index=self.round,
            restart=restart, relationships=parent.summary["relationships"])
        self.expansions += 1
        self.raw_proposals += pool["raw_proposals"];self.static_checks += pool["static_checks"]
        self.events.append({"event": "EXPAND_PARENT", "parent": parent.id,
            "parent_low_score": parent.low_score, "parent_useful_failed": parent.useful_failed,
            "round": self.round, "basis": basis, "pool": deepcopy(pool)})
        candidates = pool["candidates"]
        if not candidates:
            self.termination = "BOUNDED_FACTORY_EXHAUSTED";return self.stop()
        novel = [c for c in candidates if c["semantic_key"] not in self.by_semantic]
        chosen = max(novel or candidates, key=lambda c: self._candidate_rank(c, parent))
        basis = {**basis, "relationship_targets": [row["relation_id"] for row in targets(parent.summary)],
                 "candidate_rank": self._candidate_rank(chosen, parent),
                 "unexecuted_candidate_status": "UNKNOWN"}
        return self._submit(chosen["raw_proposal"], parent, basis, origin=chosen["origin"])

    def update(self, result):
        if self.pending is None or self.termination:raise ValueError("NO_PENDING_SUBMISSION")
        action = self.pending
        if result.get("request_id", action["request_id"]) != action["request_id"]:
            raise ValueError("RESULT_REQUEST_BINDING")
        summary = summarize(result, action["design"], self.conditions, self.factory)
        parent = self.nodes[action["parent_id"]]
        duplicate = action["semantic_reuse_of"]
        if duplicate:
            nid = duplicate
            self.events.append({"event": "SEMANTIC_REUSE_NO_NEW_NODE", "node": nid,
                "request_id": action["request_id"], "slot": self.slots, "result_refs": summary["refs"]})
        else:
            gained = [stage for stage, new, old in zip(STAGES, summary["capabilities"], parent.summary["capabilities"])
                      if new > old]
            low = (summary["complete_valid"] and not summary["all_pass"]
                   and summary["condition_pass_count"] <= parent.summary["condition_pass_count"])
            useful = bool(gained) and bool(targets(summary)) and not summary["all_pass"]
            key = self.factory.semantic_key(action["design"]);nid = "node-" + key[:24]
            node = Node(nid, deepcopy(action["design"]), key, parent.id, summary,
                        self.slots, low, gained, useful,
                        deepcopy(action["decision"]["selection_basis"]))
            self.nodes[nid], self.by_semantic[key] = node, nid
        self.events.append({"event": "COMPLETE_CHILD_RESULT", "request_id": action["request_id"],
            "expanded_parent": parent.id, "child": nid, "slot": self.slots,
            "result_refs": summary["refs"], "statuses": summary["statuses"],
            "condition_pass_count": summary["condition_pass_count"],
            "semantic_duplicate": duplicate is not None,
            "low_score": self.nodes[nid].low_score, "useful_failed": self.nodes[nid].useful_failed,
            "gained_stages": self.nodes[nid].gained_stages})
        self.pending = None;self.round += 1
        self._retain()
        if summary["all_pass"]:self.winner, self.termination = nid, "COMPLETE_SERVICE_PASS"
        elif not summary["complete_valid"]:self.termination = "TOOL_OR_DOMAIN_UNKNOWN"
        return {"status": "STOPPED" if self.termination else "UPDATED", "node_id": nid,
                "summary": summary, "low_score": self.nodes[nid].low_score,
                "useful_failed": self.nodes[nid].useful_failed}

    def stop(self):
        if self.winner:chosen = self.nodes[self.winner]
        else:
            # Preregistered final choice: actual condition PASS, then public
            # receiver count, then smallest change, earliest observed slot.
            chosen = max(self.nodes.values(), key=lambda n: (
                n.summary["condition_pass_count"], n.summary["received_count"],
                -len(changed(self.factory.initial_design, n.design)), -n.slot))
        return {"status": "STOPPED", "reason": self.termination,
            "final_design": deepcopy(chosen.design), "final_node_id": chosen.id,
            "adopted": self.winner is not None, "all_condition_PASS": chosen.summary["all_pass"],
            "final_submission_kind": "ORIGINAL_PARENT_RETAINED" if chosen.id == self.root_id else "EVALUATED_CANDIDATE",
            "eligible_for_holdout": chosen.id != self.root_id, "slots": self.slots,
            "global_infeasibility_claim": False}

    def ancestor_chains(self):
        result = []
        for event in self.events:
            if event["event"] != "COMPLETE_CHILD_RESULT" or event["semantic_duplicate"]:continue
            node = self.nodes[event["child"]];line = []
            while node:
                line.append({"node": node.id, "parent": node.parent, "slot": node.slot,
                    "low_score": node.low_score, "useful_failed": node.useful_failed,
                    "gained_stages": node.gained_stages, "result_refs": node.summary["refs"],
                    "statuses": node.summary["statuses"]})
                node = self.nodes.get(node.parent)
            result.append({"child": event["child"], "request_id": event["request_id"],
                           "lineage": line, "all_pass": self.nodes[event["child"]].summary["all_pass"]})
        return result

    def snapshot(self):
        return {"schema": VERSION, "condition": self.condition, "seed": self.seed,
            "scope": deepcopy(self.scope), "factory_identity": self.factory.identity,
            "slots": self.slots, "max_slots": self.max_slots, "count_initial": self.count_initial,
            "archive_capacity": self.archive_capacity, "archive": list(self.archive),
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "events": deepcopy(self.events), "pending": deepcopy(self.pending),
            "termination": self.termination, "winner": self.winner,
            "expansions": self.expansions, "raw_proposals": self.raw_proposals,
            "static_checks": self.static_checks, "ancestor_chains": self.ancestor_chains()}


class FreeJointInterface(DeterministicController):
    """G's tools expose shared sampling and unrestricted legal full submission.

    B never calls a model or chooses a candidate for G. Host accounting, paging,
    DSML normalization and paid callback admission remain S0-owned.
    """
    def __init__(self, factory, initial_result, *, scope, seed, **kwargs):
        self.model_final_node = None
        super().__init__("G", factory, initial_result, scope=scope, seed=seed, **kwargs)

    def candidate_tool(self, *, parent_id=None):
        parent = self.nodes[parent_id or self.root_id]
        pool = self.factory.generate(parent.design, seed=self.seed, round_index=self.round,
                                     restart=self.round % 3 == 0,
                                     relationships=parent.summary["relationships"])
        self.raw_proposals += pool["raw_proposals"];self.static_checks += pool["static_checks"]
        self.events.append({"event": "G_SHARED_FACTORY_TOOL", "parent": parent.id, "pool": deepcopy(pool)})
        return pool

    def submit(self, full_design, *, parent_id=None):
        parent = self.nodes[parent_id or self.root_id]
        return self._submit(full_design, parent, {"kind": "EXTERNAL_MODEL_FREE_JOINT_SELECTION"})

    def finalize(self, full_design):
        if self.pending:raise ValueError("UPDATE_PENDING_FIRST")
        normalized = self.factory.normalize(full_design)
        key = normalized["semantic_key"]
        if key not in self.by_semantic:raise ValueError("UNTESTED_FINAL_NOT_ADMITTED")
        node = self.nodes[self.by_semantic[key]]
        self.model_final_node = node.id
        return {"status": "FINAL_SUBMITTED", "final_design": deepcopy(node.design),
                "final_node_id": node.id, "adopted": node.summary["all_pass"],
                "all_condition_PASS": node.summary["all_pass"],
                "slots": self.slots, "reason": self.termination,
                "eligible_for_holdout": node.id != self.root_id,
                "final_submission_kind": "EVALUATED_CANDIDATE" if node.id != self.root_id else "ORIGINAL_PARENT_RETAINED"}

    def stop(self):
        # An observed complete PASS terminates every condition. Otherwise only
        # the external model can select G's final evaluated design.
        selected = self.model_final_node or self.winner
        if selected is None:
            return {"status": "FINAL_SELECTION_REQUIRED", "reason": self.termination,
                    "slots": self.slots, "model_must_select_evaluated_design": True,
                    "eligible_for_holdout": False}
        node = self.nodes[selected]
        return {"status": "STOPPED", "reason": self.termination,
                "final_design": deepcopy(node.design), "final_node_id": node.id,
                "adopted": node.summary["all_pass"], "all_condition_PASS": node.summary["all_pass"],
                "final_submission_kind": "EVALUATED_CANDIDATE" if node.id != self.root_id else "ORIGINAL_PARENT_RETAINED",
                "eligible_for_holdout": node.id != self.root_id, "slots": self.slots,
                "global_infeasibility_claim": False}
