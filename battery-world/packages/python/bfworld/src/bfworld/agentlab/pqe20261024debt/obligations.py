"""Derive scoped program/energy obligations from public design semantics.

No task names, repair values, preferred clear phase or successful designs occur
here.  Both durable SAVE and receiver ACK can establish reliable handoff when
the facts declare them so.  Logical closure is never a service verdict.
"""
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json

VERSION = "codebt-obligations-v2-public-causal"
STATUSES = {"OPEN", "SATISFIED", "REFUTED", "UNKNOWN"}
PUBLIC_OBSERVATION_SCHEMA = "codebt-public-observation-v1"
PUBLIC_PREDICATES = {"capture_coverage": "PUBLIC_CAPTURE_COVERAGE",
                     "sequence_identity": "PUBLIC_SEQUENCE_IDENTITY"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def changed_fields(before, after):
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def _refs(row):
    value = row.get("refs", row.get("evidence_refs", row.get("source_refs", [])))
    return deepcopy(value) if isinstance(value, list) else [deepcopy(value)]


def _deps(*rows):
    return sorted({k for row in rows for k in row.get("dependencies", row.get("depends_on", []))})


def _and(values):
    return False if False in values else None if None in values else True


def _or(values):
    return True if True in values else None if None in values else False


def _truth(row, key, default=None):
    value = row.get(key, default)
    return value if type(value) is bool else None


def _check(kind, subject, holds, *, predicate, rows, applicable=True, hard_refuted=False):
    refs = {digest(ref): deepcopy(ref) for row in rows for ref in _refs(row)}
    return {"kind": kind, "subject": subject, "holds": holds,
            "predicate": {**predicate, "from_fact_ids": sorted(r["id"] for r in rows if r.get("id"))}, "applicable": applicable,
            "hard_refuted": hard_refuted,
            "dependencies": _deps(*rows),
            "refs": list(refs.values())}


def _relation_checks(view):
    """A's factual subject/relation/object list; no design-field repair map."""
    facts = view["facts"]
    if not isinstance(facts, list):
        raise ValueError("PUBLIC_FACT_LIST_REQUIRED")
    out = []
    producers = [f for f in facts if f.get("relation") == "produces"]
    readers = [f for f in facts if f.get("relation") == "reads"]
    destinations = [f for f in facts if f.get("relation") == "available_after"]
    clears = [f for f in facts if f.get("relation") == "clear_trigger"]
    identities = [f for f in facts if f.get("relation") == "identity_storage"]
    connections = [f for f in facts if f.get("relation") == "connected_to"]
    for producer in producers:
        value = producer.get("value", {})
        active = _truth(value, "enabled")
        matches = [r for r in readers if r.get("object") == producer.get("object")]
        consumed = _or([_truth(r.get("value", {}), "enabled") for r in matches])
        out.append(_check("CONSUMPTION", producer["object"], consumed,
                          predicate={"any_enabled_reader_for": producer["object"]},
                          rows=[producer] + matches, applicable=active))
        # Retained identities are a program obligation only for the newly
        # active producer. False means a missing companion, not impossibility.
        for identity in identities:
            storage = identity.get("value", {})
            durable_keys = [v for k, v in storage.items() if k.endswith("committed_seq_survives_reset")]
            durable = _or([v if type(v) is bool else None for v in durable_keys]) if durable_keys else None
            out.append(_check("RESET_IDENTITY", producer["object"], durable,
                              predicate={"committed_identity_survives_reset": identity["subject"]},
                              rows=[producer, identity], applicable=active))
    for clear in clears:
        value = clear.get("value", {})
        enabled = _truth(value, "enabled")
        trigger = value.get("trigger")
        paths = [f for f in destinations if f.get("object") == trigger]
        reliable = _or([_and([_truth(p.get("value", {}), "enabled", True),
                              _truth(p.get("value", {}), "survives_mcu_reset")]) for p in paths])
        out.append(_check("RELIABLE_HANDOFF", clear["object"], reliable,
                          predicate={"durable_destination_at_clear_trigger": clear["subject"]},
                          rows=[clear] + paths, applicable=enabled))
    # Capacity/retention are real constraints, but static facts alone give no
    # event count or voltage coverage. Never invent overflow or a need to clear.
    for fact in facts:
        value = fact.get("value", {})
        if fact.get("kind") in {"capacity", "timing"}:
            applicable = _or([_truth(p.get("value", {}), "enabled") for p in producers
                              if p.get("object") == fact.get("subject")])
            out.append(_check("DYNAMIC_" + fact["kind"].upper(), fact["subject"], None,
                              predicate={"observed_within_declared_limit": fact["id"]},
                              rows=[fact], applicable=applicable))
        if fact.get("relation") == "observed":
            keys = [k for k in value if k not in {"status", "complete_service"}]
            for key in keys:
                out.append(_check("DYNAMIC_EVIDENCE", fact["subject"] + ":" + key,
                                  _truth(value, key), predicate={"observed": key}, rows=[fact]))
    for load in view.get("loads", []):
        enabled = _truth(load, "enabled")
        connected = _or([_truth(f.get("value", {}), "implemented") for f in connections])
        label = str(load.get("component")) + ":" + str(load.get("operation"))
        out.append(_check("PAID_LOAD", label, connected,
                          predicate={"operation_load_in_shared_supply": label},
                          rows=[load] + connections, applicable=enabled))
    return out


def semantic_checks(facts):
    """Convert a public component/program graph into necessary logical checks.

    Generic graph shape:
      states: id, produced/enabled, dependencies, refs
      operations: id, enabled, reads[], clears[], dependencies, refs
      handoffs: id, state_id, reliable, before_clear, enabled, refs
      resets: id, state_id, relevant, replay_safe (bool/None), refs
      loads: id, enabled, accounted, energy_evidence_valid (bool/None), refs
    Facts describe what the current configuration does, never a next edit.
    Optional ``predicates`` are current-design fact predicates supplied by a
    public contract, with id/type/holds/dependencies/refs; they carry no action.
    """
    if not isinstance(facts, dict):
        raise ValueError("DESIGN_FACTS_MUST_BE_OBJECT")
    if "facts" in facts:
        return _relation_checks(facts)
    out = []
    operations = facts.get("operations", [])
    for state in facts.get("states", []):
        sid = state["id"]
        active = _and([_truth(state, "enabled", True), _truth(state, "produced", True)])
        readers = [op for op in operations if sid in op.get("reads", [])]
        # A complete declared operation list establishes no reader; an omitted
        # list is UNKNOWN rather than proving absence.
        reader_truth = (_or([_truth(op, "enabled") for op in readers])
                        if readers or "operations" in facts else None)
        out.append(_check("CONSUMPTION", sid, reader_truth,
                          predicate={"any_enabled_operation_reads": sid},
                          rows=[state] + readers, applicable=active))
        clears = [op for op in operations if sid in op.get("clears", [])]
        clear_enabled = _or([_truth(op, "enabled") for op in clears])
        paths = [p for p in facts.get("handoffs", []) if p.get("state_id") == sid]
        reliability = (_or([_and([_truth(p, "enabled", True), _truth(p, "reliable"),
                                 _truth(p, "before_clear")]) for p in paths])
                       if paths or "handoffs" in facts else None)
        out.append(_check("RELIABLE_HANDOFF", sid, reliability,
                          predicate={"reliable_receiver_before_clear": sid},
                          rows=[state] + clears + paths,
                          applicable=_and([active, clear_enabled])))
    for reset in facts.get("resets", []):
        out.append(_check("RESET_REENTRY", reset.get("state_id", reset["id"]),
                          _truth(reset, "replay_safe"),
                          predicate={"reset_reentry_preserves_identity": reset["id"]},
                          rows=[reset], applicable=_truth(reset, "relevant", True)))
    for load in facts.get("loads", []):
        out.append(_check("PAID_LOAD", load["id"], _truth(load, "accounted"),
                          predicate={"load_in_supply_equation": load["id"]},
                          rows=[load], applicable=_truth(load, "enabled", True)))
        if "energy_evidence_valid" in load:
            out.append(_check("ENERGY_EVIDENCE", load["id"],
                              _truth(load, "energy_evidence_valid"),
                              predicate={"energy_evidence_matches_load": load["id"]},
                              rows=[load], applicable=_truth(load, "enabled", True)))
    for row in facts.get("predicates", []):
        if not row.get("id") or not row.get("type"):
            raise ValueError("PUBLIC_PREDICATE_ID_AND_TYPE_REQUIRED")
        out.append(_check(row["type"], row["id"], _truth(row, "holds"),
                          predicate=deepcopy(row.get("predicate", {"public_predicate": row["id"]})),
                          rows=[row], applicable=_truth(row, "applicable", True),
                          hard_refuted=row.get("hard_refuted") is True))
    return out


def _identity_support(facts):
    values = [value for row in facts.get("facts", [])
              if row.get("relation") == "identity_storage"
              for key, value in row.get("value", {}).items()
              if key.endswith("committed_seq_survives_reset")]
    return _or([v if type(v) is bool else None for v in values]) if values else None


def _public_checks(design, facts, observations, scope):
    """Current public observations only; no hidden evaluator or repair hints."""
    checks = []
    for observation in observations:
        pid = observation.get("predicate_id")
        if (observation.get("schema") != PUBLIC_OBSERVATION_SCHEMA or pid not in PUBLIC_PREDICATES
                or observation.get("design_sha256") != digest(design)
                or not observation.get("result_sha256") or not _refs(observation)
                or not observation.get("condition_id")
                or (scope.get("conditions") and observation["condition_id"] not in scope["conditions"])):
            continue
        relevant = [row for row in facts.get("facts", [])
                    if row.get("relation") == ("identity_storage" if pid == "sequence_identity" else "observed")]
        fact = {"id": "public:" + pid + ":" + observation["condition_id"],
                "depends_on": _deps(*relevant), "refs": _refs(observation)}
        check = _check(PUBLIC_PREDICATES[pid], observation["condition_id"],
                       _truth(observation, "holds"),
                       predicate={"public_predicate": pid, "condition_id": observation["condition_id"]},
                       rows=[fact] + relevant)
        check["predicate"]["public_observation"] = deepcopy(observation)
        check["predicate"]["support_at_observation"] = (_identity_support(facts)
                                                        if pid == "sequence_identity" else None)
        check["predicate"]["static_support"] = None
        checks.append(check)
    return checks


@dataclass
class Obligation:
    id: str
    type: str
    subject: str
    trigger_diff: dict
    dependencies: list
    predicate: dict
    evidence_refs: list
    scope: dict
    status: str
    checked_design_sha256: str
    invalidations: list = field(default_factory=list)

    def to_dict(self):
        return deepcopy(self.__dict__)


def derive_obligations(design, facts, *, scope, previous=(), trigger_diff=None,
                       previous_design=None, observations=()):
    """Recompute predicates and invalidate every changed dependency binding.

    Observations are optional public, same-design predicate readbacks with
    obligation_id/holds/refs/design_sha256. A full FAIL by itself cannot refute
    a particular obligation, and PASS cannot close unknown logical relations.
    """
    old = {o.id if isinstance(o, Obligation) else o["id"]:
           o.to_dict() if isinstance(o, Obligation) else deepcopy(o) for o in previous}
    changed = changed_fields(previous_design or {}, design) if previous_design is not None else []
    triggers = deepcopy(trigger_diff or {})
    observations = list(observations)
    observed = {o.get("obligation_id"): o for o in observations
                if o.get("design_sha256") == digest(design) and _refs(o)}
    checks = semantic_checks(facts) + _public_checks(design, facts, observations, scope)
    rows = []
    stable_scope = {k: v for k, v in scope.items() if k not in {"design_sha256", "result_sha256"}}
    for check in checks:
        oid = "obl-" + digest({"scope": stable_scope, "type": check["kind"],
                                "subject": check["subject"],
                                "predicate": {k: v for k, v in check["predicate"].items()
                                              if k not in {"from_fact_ids", "public_observation",
                                                           "support_at_observation", "static_support"}}})[:24]
        applicable, holds = check["applicable"], check["holds"]
        refs = deepcopy(check["refs"])
        if oid in observed:
            holds = _truth(observed[oid], "holds")
            refs += _refs(observed[oid])
        if not refs:
            status = "UNKNOWN"
        elif applicable is False:
            status = "SATISFIED"  # Vacuous closure is bound to these facts.
        elif applicable is None or holds is None:
            status = "UNKNOWN"
        elif holds is True:
            status = "SATISFIED"
        elif check["hard_refuted"]:
            status = "REFUTED"
        else:
            status = "OPEN"
        prior = old.get(oid, {})
        invalidations = deepcopy(prior.get("invalidations", []))
        impacted = sorted(set(changed) & set(prior.get("dependencies", check["dependencies"])))
        if impacted:
            invalidations.append({"changed_fields": impacted,
                                  "previous_design_sha256": prior.get("checked_design_sha256"),
                                  "previous_status": prior.get("status"),
                                  "previous_evidence_refs": deepcopy(prior.get("evidence_refs", []))})
        # Applicability is reporting metadata, not a different logical ID.
        # Disabling a producer can vacuously discharge a predicate, but cannot
        # earn the concrete completion progress used to rank extensions.
        predicate = {**deepcopy(check["predicate"]), "applicable": applicable}
        trigger = (triggers if status in {"OPEN", "UNKNOWN"} and
                   prior.get("status") == "SATISFIED" else prior.get("trigger_diff", triggers))
        rows.append(Obligation(oid, check["kind"], check["subject"],
                               deepcopy(trigger),
                               check["dependencies"], predicate, refs,
                               deepcopy(scope), status, digest(design), invalidations))
    # A check disappearing from a partial projection is not proof it closed.
    present = {o.id for o in rows}
    for oid, prior in old.items():
        if oid not in present:
            impacted = sorted(set(changed) & set(prior.get("dependencies", [])))
            if prior["type"] in PUBLIC_PREDICATES.values():
                # A parent's observation is an explanation for a scoped trial,
                # never an observed verdict for an unexecuted child design.
                predicate = prior["predicate"]
                original = predicate.get("public_observation", {})
                predicate["static_support"] = (
                    original.get("holds") is False
                    and predicate.get("support_at_observation") is False
                    and _identity_support(facts) is True
                    if predicate.get("public_predicate") == "sequence_identity" else None)
                if impacted:
                    prior.setdefault("invalidations", []).append({
                        "changed_fields": impacted,
                        "previous_design_sha256": prior["checked_design_sha256"],
                        "previous_status": prior["status"],
                        "previous_evidence_refs": deepcopy(prior["evidence_refs"])})
            prior.update(status="UNKNOWN", checked_design_sha256=digest(design))
            if prior["type"] not in PUBLIC_PREDICATES.values():
                prior.setdefault("invalidations", []).append({"reason": "PREDICATE_NOT_IN_CURRENT_PUBLIC_VIEW"})
            rows.append(Obligation(**prior))
    return rows


def closure_delta(before, after):
    """Concrete IDs improved, worsened and invalidated; no service ranking."""
    b = {o.id: o for o in before}
    a = {o.id: o for o in after}
    return {"satisfied": sorted(k for k, v in a.items()
                                 if v.status == "SATISFIED" and v.predicate.get("applicable") is not False
                                 and k in b and b[k].status != "SATISFIED"),
            "opened": sorted(k for k, v in a.items()
                             if v.status in {"OPEN", "UNKNOWN"} and
                             (k not in b or b[k].status == "SATISFIED")),
            "refuted": sorted(k for k, v in a.items() if v.status == "REFUTED"),
            "invalidated": sorted(k for k, v in a.items() if k in b and
                                  len(v.invalidations) > len(b[k].invalidations))}


def unresolved(obligations):
    return [o for o in obligations if o.status in {"OPEN", "UNKNOWN"}]
