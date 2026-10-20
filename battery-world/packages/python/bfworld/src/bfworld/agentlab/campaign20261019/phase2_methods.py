"""Pure phase-two method proposal and re-execution checks.

No provider, simulator, filesystem, executable candidate code or qualification
authority. The participant schema only proposes H or no update. Free-text
method meaning still needs an independent semantic audit; a legal envelope
alone never establishes that a model produced a genuine H change.
"""
from __future__ import annotations

import hashlib
import json
import re

SCHEMA = "bf-phase2-method-proposal-v1"
H_COMPONENTS = ("global_prompt", "skills", "observation_policy", "context_policy",
                "experiment_order", "organization")
D_FIELDS = frozenset(("device", "program", "firmware", "design_patch", "load", "timing",
                      "capacitance_f", "tx_not_before_s", "sample_period_s", "retry_s",
                      "ack_spacing_s", "off_v", "ready_v", "initial_energy", "threshold"))
H_FIELDS = frozenset((*H_COMPONENTS, "method_text"))
G_FIELDS = frozenset(("proposal_procedure", "selection_procedure", "improver"))
FORBIDDEN = frozenset(("world_patch", "task_patch", "evaluator", "acceptance", "budget",
                       "provider", "qualification", "hidden_labels", "service_criteria"))
PARITY_FIELDS = ("task_sha256", "sources_sha256", "information_sha256", "model_sha256",
                 "tools_sha256", "evaluator_sha256", "initial_cache_sha256")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _json_object(value):
    if not isinstance(value, dict):
        raise ValueError("OBJECT_REQUIRED")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("FINITE_JSON_REQUIRED") from exc
    if len(encoded.encode()) > 65536:
        raise ValueError("PROPOSAL_BYTE_LIMIT")


def _text(value, name, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise ValueError("INVALID_" + name.upper())
    return value.strip()


def tool_schema():
    """Parameters only; S0 owns the tool name, host, sources and operation lease."""
    common = {"schema_version": {"const": SCHEMA}, "changed_artifact": {"const": "H"}}
    proposal = {
        "type": "object", "additionalProperties": False,
        "required": ["hypothesis", "falsifier", "method_text", "changed_artifact"],
        "properties": {**common, "decision": {"const": "propose"},
            "hypothesis": {"type": "string", "minLength": 1, "maxLength": 4000},
            "falsifier": {"type": "string", "minLength": 1, "maxLength": 4000},
            "method_text": {"type": "string", "minLength": 1, "maxLength": 16000,
                            "description": "Method instructions consumed from task entry; not a device submission or acceptance decision."},
            "changes": {"type": "array", "minItems": 1, "maxItems": 6,
                "items": {"type": "object", "additionalProperties": False,
                          "required": ["artifact", "component"],
                          "properties": {"artifact": {"const": "H"}, "component": {"enum": list(H_COMPONENTS)}}}},
            "evidence_refs": {"type": "array", "maxItems": 16, "uniqueItems": True,
                "items": {"type": "string", "minLength": 1, "maxLength": 128,
                          "pattern": "^[A-Za-z0-9_.:-]+$"}}}}
    no_update = {"type": "object", "additionalProperties": False,
                 "required": ["decision", "reason"],
                 "properties": {**common, "decision": {"const": "no-update"},
                                "reason": {"type": "string", "minLength": 1, "maxLength": 4000}}}
    return {"type": "object", "oneOf": [proposal, no_update, {"type": "object", "maxProperties": 0}]}


def classify_change(change):
    """Classify a typed change, not the scientific meaning of arbitrary prose."""
    _json_object(change)
    if not change:
        return "NONE"
    if change.get("decision") == "no-update":
        if set(change) - {"schema_version", "decision", "changed_artifact", "reason"}:
            raise ValueError("NO_UPDATE_CANNOT_CARRY_CHANGE")
        return "NONE"
    if FORBIDDEN.intersection(change):
        return "FORBIDDEN"
    declared = change.get("changed_artifact")
    if declared is not None and declared not in ("H", "D", "G"):
        raise ValueError("UNKNOWN_ARTIFACT")
    kinds = {declared} if declared else set()
    keys = set(change)
    fields = change.get("changed_fields", [])
    if not isinstance(fields, list) or any(not isinstance(x, str) for x in fields):
        raise ValueError("INVALID_CHANGED_FIELDS")
    keys.update(fields)
    if keys.intersection(FORBIDDEN):
        return "FORBIDDEN"
    for names, artifact in ((D_FIELDS, "D"), (H_FIELDS, "H"), (G_FIELDS, "G")):
        if keys.intersection(names):
            kinds.add(artifact)
    changes = change.get("changes", [])
    if not isinstance(changes, list):
        raise ValueError("INVALID_CHANGES")
    for item in changes:
        if not isinstance(item, dict) or item.get("artifact") not in ("H", "D", "G"):
            raise ValueError("INVALID_TYPED_CHANGE")
        kinds.add(item["artifact"])
        component = item.get("component")
        if component in H_COMPONENTS:
            kinds.add("H")
        elif component in D_FIELDS:
            kinds.add("D")
        elif component in G_FIELDS:
            kinds.add("G")
        else:
            raise ValueError("UNSUPPORTED_CHANGE_COMPONENT")
    return next(iter(kinds)) if len(kinds) == 1 else ("MIXED" if kinds else "UNKNOWN")


def _device_only_text(text):
    try:
        obj = json.loads(text)
    except ValueError:
        obj = None
    if isinstance(obj, dict) and classify_change(obj) in ("D", "MIXED", "FORBIDDEN"):
        return True
    fields = "|".join(re.escape(x) for x in sorted(D_FIELDS))
    assignment = rf"(?:{fields})\s*[:=]\s*[-+0-9.eE]+"
    return re.fullmatch(rf"\s*{assignment}(?:\s*[,;\n]\s*{assignment})*\s*", text) is not None


def validate_method(proposal):
    """Normalize a proposal; never execute it, sign it or declare a retained H."""
    _json_object(proposal)
    if not proposal:
        proposal = {"decision": "no-update", "reason": "EMPTY_PROPOSAL"}
    decision = proposal.get("decision", "propose")
    if proposal.get("schema_version", SCHEMA) != SCHEMA:
        raise ValueError("UNSUPPORTED_SCHEMA")
    if proposal.get("changed_artifact", "H") != "H":
        raise ValueError("METHOD_REQUIRES_H_NOT_D_OR_G")
    if decision == "no-update":
        if set(proposal) - {"schema_version", "decision", "changed_artifact", "reason"}:
            raise ValueError("NO_UPDATE_CANNOT_CARRY_CHANGE")
        return {"schema_version": SCHEMA, "decision": "no-update", "changed_artifact": "H",
                "reason": _text(proposal.get("reason"), "reason"), "status": "NO_UPDATE"}
    if decision != "propose":
        raise ValueError("UNKNOWN_DECISION")
    allowed = {"schema_version", "decision", "changed_artifact", "hypothesis", "falsifier",
               "method_text", "changes", "evidence_refs"}
    if set(proposal) - allowed:
        raise ValueError("UNSUPPORTED_PROPOSAL_FIELD")
    if proposal.get("changed_artifact") != "H":
        raise ValueError("CHANGED_ARTIFACT_H_REQUIRED")
    hypothesis = _text(proposal.get("hypothesis"), "hypothesis")
    falsifier = _text(proposal.get("falsifier"), "falsifier")
    text = _text(proposal.get("method_text"), "method_text", 16000)
    if _device_only_text(text):
        raise ValueError("DEVICE_ONLY_TEXT_IS_NOT_H")
    changes = proposal.get("changes", [{"artifact": "H", "component": "global_prompt"}])
    if not isinstance(changes, list) or not 1 <= len(changes) <= 6:
        raise ValueError("INVALID_CHANGES")
    for item in changes:
        if (not isinstance(item, dict) or set(item) != {"artifact", "component"}
                or item["artifact"] != "H" or item["component"] not in H_COMPONENTS):
            raise ValueError("METHOD_CANNOT_INCLUDE_D_G_OR_UNSUPPORTED_H_COMPONENT")
    if len({x["component"] for x in changes}) != len(changes):
        raise ValueError("DUPLICATE_H_COMPONENT")
    refs = proposal.get("evidence_refs", [])
    if (not isinstance(refs, list) or len(refs) > 16
            or any(not isinstance(x, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", x) for x in refs)
            or len(set(refs)) != len(refs)):
        raise ValueError("INVALID_EVIDENCE_REFS")
    return {"schema_version": SCHEMA, "decision": "propose", "changed_artifact": "H",
            "hypothesis": hypothesis, "falsifier": falsifier, "method_text": text,
            "changes": [dict(x) for x in changes], "evidence_refs": list(refs),
            "method_sha256": digest(text), "impact_scope": "task-entry",
            "status": "PROPOSED_REQUIRES_EXTERNAL_SEMANTIC_AND_EXECUTION_AUDIT"}


def impact_scope(change):
    artifact = classify_change(change)
    if artifact == "H":
        return "task-entry"
    if artifact == "D":
        return "full-feedback-response"
    if artifact == "G":
        return "method-lineage-root"
    if artifact == "NONE":
        return "no-execution"
    raise ValueError("UNSUPPORTED_OR_MIXED_IMPACT_SCOPE")


def validate_reexecution(change, policy):
    """F1b decision restart and F1a response-cache scope are separate checks."""
    scope = impact_scope(change)
    _json_object(policy)
    if scope == "method-lineage-root":
        raise ValueError("G_OUTSIDE_PHASE2_METHOD_COMPARISON")
    if scope == "no-execution":
        return {"scope": scope, "status": "NO_UPDATE"}
    if scope == "task-entry" and policy.get("agent_decisions") != "fresh-task-entry":
        raise ValueError("GLOBAL_H_REQUIRES_FRESH_TASK_ENTRY")
    strategy = policy.get("response_strategy")
    if strategy == "exact-input-response":
        requested = policy.get("requested_input_sha256")
        cached = policy.get("cached_input_sha256")
        if (not isinstance(requested, str) or not re.fullmatch(r"[a-f0-9]{64}", requested)
                or cached != requested):
            raise ValueError("EXACT_INPUT_CACHE_IDENTITY_MISMATCH")
    elif strategy != "full-feedback-response":
        raise ValueError("FIXED_TRAJECTORY_OR_SUFFIX_REUSE_FORBIDDEN")
    return {"scope": scope, "response_strategy": strategy,
            "status": "STRUCTURALLY_VALID_REQUIRES_HOST_INPUT_VERIFICATION"}


def confirmation_gate(proposal, *, proposal_receipt_id, h0_receipt_id,
                      hprime_receipt_id, resolve_receipt):
    """Host-only facts gate. The resolver must independently verify S0 registries.

    Never expose resolver selection or receipt contents as participant inputs.
    This pure function cannot establish the resolver's authenticity. It emits
    eligibility/rejection facts, never a qualification or a retained method.
    """
    method = validate_method(proposal)
    if method["decision"] == "no-update":
        return {"status": "NO_UPDATE", "retained": False, "authority": "NONE"}
    if not callable(resolve_receipt):
        raise ValueError("TRUSTED_EXTERNAL_RESOLVER_REQUIRED")
    receipt_ids = (proposal_receipt_id, h0_receipt_id, hprime_receipt_id)
    if any(not isinstance(x, str) or not x for x in receipt_ids) or len(set(receipt_ids)) != 3:
        raise ValueError("DISTINCT_EXTERNAL_RECEIPTS_REQUIRED")
    records = [resolve_receipt(kind, identity) for kind, identity in
               zip(("method-proposal", "H0-design", "Hprime-design"), receipt_ids)]
    if any(not isinstance(x, dict) or x.get("externally_verified") is not True for x in records):
        raise ValueError("UNVERIFIED_EXTERNAL_RECEIPT")
    if len({x.get("evidence_kind") for x in records}) != 1 or records[0].get("evidence_kind") not in ("MOCK", "ACTUAL_PROVIDER"):
        raise ValueError("INCONSISTENT_EVIDENCE_KIND")
    proposal_record, baseline, revised = records
    failures = []
    if proposal_record.get("proposal_sha256") != digest(method):
        failures.append("PROPOSAL_INPUT_MISMATCH")
    if proposal_record.get("semantic_artifact") != "H":
        failures.append("NOT_AUDITED_AS_H")
    if proposal_record.get("method_author") != "participant-model":
        failures.append("NOT_MODEL_AUTHORED_METHOD")
    if proposal_record.get("source_scope") != "public-development":
        failures.append("INVALID_SOURCE_SCOPE")
    for row in records:
        if (row.get("usage_status") != "SETTLED" or row.get("costs_complete") is not True
                or not row.get("provider_request_ids") or not row.get("decision_trace_sha256")):
            failures.append("MISSING_DECISION_OR_SETTLED_COST_BINDING")
    for field in PARITY_FIELDS:
        value = baseline.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value) or revised.get(field) != value:
            failures.append("PARITY_" + field.upper())
    for field in ("episode_id", "owner", "context_id"):
        if not baseline.get(field) or not revised.get(field) or baseline[field] == revised[field]:
            failures.append("FRESH_" + field.upper())
    for row in (baseline, revised):
        if row.get("start_stage") != "task-entry" or row.get("initial_decision_messages") != 0:
            failures.append("NOT_FRESH_TASK_ENTRY")
        if row.get("actual_tool_inputs_bound") is not True or not row.get("execution_input_sha256"):
            failures.append("MISSING_ACTUAL_EXECUTION_BINDING")
        if (row.get("independent_complete_service") is not True
                or row.get("evaluation_input_sha256") != row.get("execution_input_sha256")):
            failures.append("INCOMPLETE_OR_MISBOUND_SERVICE")
        if row.get("feedback_scope_verified") is not True:
            failures.append("STALE_FEEDBACK_RESPONSE")
    if revised.get("method_sha256") != method["method_sha256"]:
        failures.append("HPRIME_NOT_CONSUMED")
    if not baseline.get("method_sha256") or baseline.get("method_sha256") == revised.get("method_sha256"):
        failures.append("NO_H_DIFFERENCE")
    if baseline.get("service_status") not in ("PASS", "FAIL", "UNKNOWN"):
        failures.append("BASELINE_SERVICE_NOT_RECORDED")
    if revised.get("service_status") != "PASS":
        failures.append("REVISED_FULL_SERVICE_NOT_PASS")
    evidence_kind = records[0]["evidence_kind"]
    return {"status": "REJECT" if failures else ("MOCK_CONTROL_PASS" if evidence_kind == "MOCK" else "ELIGIBLE_FOR_EXTERNAL_DECISION"),
            "failures": sorted(set(failures)), "retained": False, "authority": "NONE",
            "evidence_kind": evidence_kind, "method_benefit": "NOT_ESTABLISHED",
            "baseline_service_status": baseline.get("service_status"),
            "revised_service_status": revised.get("service_status")}
