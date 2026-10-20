"""Pure phase3 method contracts; no model, file, simulator or evaluator execution.

The frozen phase2 typed classifier is reused without modification. Historical
result references below are host-only controls, never extra participant facts.
S0 owns proposal validation/hosting, actual runs and independent event evaluation.
"""
from __future__ import annotations

import math

from .phase2_methods import classify_change


CONDITIONS = ("fixed_h", "ordinary_reflection", "proposed_method")
STRATEGIES = ("frozen-trajectory", "dependency-recompute", "scope-recompute",
              "full-feedback")


def impact_scope(change):
    """Conservative scope for this coupled apparatus; no outcome is consulted."""
    kind = classify_change(change)
    if kind == "H":
        return "task-entry"
    if kind == "D":
        return "full-feedback-response"
    if kind == "NONE":
        return "no-execution"
    raise ValueError("UNSUPPORTED_PHASE3_CHANGE_" + kind)


def comparison_registry(change):
    """Register four comparisons, without pretending to execute algorithms.

    Dependency and scope strategies conservatively collapse to a full physical
    feedback response here. A changed H additionally restarts Agent decisions.
    A previously obtained complete response may be read only under independently
    verified exact-input identity; equal initial caches are a separate requirement.
    """
    scope = impact_scope(change)
    rows = []
    for strategy in STRATEGIES:
        negative = strategy == "frozen-trajectory"
        rows.append({
            "strategy": strategy,
            "changed_artifact": classify_change(change),
            "required_scope": scope,
            "agent_decisions": "fresh-task-entry" if scope == "task-entry" else "not-an-H-restart",
            "response_scope": ("retained-old-trajectory" if negative else
                               "no-execution" if scope == "no-execution" else "full-feedback-response"),
            "eligible_as_changed_input_service": not negative and scope != "no-execution",
            "control_only": negative,
            "input_identity_audit_required": not negative and scope != "no-execution",
            "execution_status": "REGISTRATION_ONLY",
            "service_status": "NOT_EVALUATED",
            "historical_evidence_refs": (["f1a-unchanged", "f1a-threshold-mismatch"] if negative else
                                         ["bf-complete-feedback-negative-control", "bf-ordered-state"]),
            "registration_new_scientific_executions": 0,
            "qualification_authority": "NONE",
        })
    return rows


def remaining_budget(condition, *, total_requests, total_wall_s,
                     proposal_requests=0, proposal_wall_s=0, distinct_D=0):
    """Facts about one shared group budget, including failed/acquisition work.

    Totals are host-supplied complete accounting. Unknown/missing accounting is
    rejected, not converted to zero. No request reservation or paid dispatch is
    performed here. Proposal subcaps do not grant additional design budget.
    """
    if condition not in CONDITIONS:
        raise ValueError("UNKNOWN_CONDITION")
    for name, value in (("total_requests", total_requests),
                        ("proposal_requests", proposal_requests), ("distinct_D", distinct_D)):
        if type(value) is not int or value < 0:
            raise ValueError("INVALID_" + name.upper())
    for name, value in (("total_wall_s", total_wall_s), ("proposal_wall_s", proposal_wall_s)):
        if (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError("INVALID_" + name.upper())
    proposal_cap = 0 if condition == "fixed_h" else 8
    proposal_wall_cap = 0 if condition == "fixed_h" else 400
    if (total_requests > 24 or total_wall_s > 1200 or distinct_D > 2
            or proposal_requests > proposal_cap or proposal_wall_s > proposal_wall_cap
            or proposal_requests > total_requests or proposal_wall_s > total_wall_s):
        raise ValueError("GROUP_OR_PROPOSAL_BUDGET_VIOLATION")
    return {
        "condition": condition, "remaining_group_requests": 24 - total_requests,
        "remaining_group_wall_s": 1200 - total_wall_s,
        "remaining_proposal_requests": min(proposal_cap - proposal_requests, 24 - total_requests),
        "remaining_proposal_wall_s": min(proposal_wall_cap - proposal_wall_s, 1200 - total_wall_s),
        "remaining_distinct_D": 2 - distinct_D,
        "total_includes_proposal_acquisition_design_confirmation_and_failures": True,
        "dispatch_authority": "NONE",
    }


def ordered_event_requirements():
    """Requirements for S0's new evaluator, not an evaluation of a supplied trace."""
    return {
        "schema_version": "bf-phase3-ordered-event-requirements-v1",
        "required_facts": ["event_origin_id", "event_source_sha256", "capture_id",
                           "capture_order", "reset_orders", "delivery_order",
                           "delivered_event_origin_id", "delivered_capture_id",
                           "pending_state_lineage", "postreset_recapture_orders"],
        "order": "Use (time_s, sequence) or a proven total trace order; equal timestamps without action order are UNKNOWN.",
        "pending_across_reset_witness": "Same captured pending event: capture < intervening reset < delivery, with source/capture identity and pending-state lineage preserved; a new event or postreset reacquisition cannot substitute for the pre-reset pending state.",
        "delivery_before_any_reset": "DELIVERED_BEFORE_RESET; no cross-reset pending-state witness, even if a later brownout occurs.",
        "reset_before_capture": "No cross-reset pending-state witness for this capture.",
        "no_reset": "Cross-reset retention NOT_ESTABLISHED; service is evaluated separately.",
        "missing_identity_or_order": "UNKNOWN; never infer pending-state retention from frame counts or success-and-any-reset.",
        "service_boundary": "Evaluate the same frozen task and complete feedback independently. Retention is a separate diagnostic unless the predeclared task explicitly requires it.",
        "legacy_labels": "Preserve raw labels for provenance; do not use them as ordered pending-state retention verdicts.",
        "source_binding": "Bind the raw response, source identity, evaluator version and actual consumed inputs. Do not rerun an already valid full response merely to relabel temporal order.",
        "qualification_authority": "S0 independent evaluator only",
        "new_scientific_executions": 0,
    }
