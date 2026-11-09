"""Bounded public feedback and the shared full-candidate evaluation contract.

The host keeps each original public result in PublicObjects and provides its
immutable reference here. This module neither executes a consumer nor reads
hidden assessments. A compact Result retains the original execution identity,
Design/Problem, domain status, full public verdict and usage.
"""
from copy import deepcopy
import json

from ..pqe20261022.methods import ContractError, digest
from ..pqe20261022.public_projection import project_result

VERSION = "pqe-bold-gsu-v1"
MAX_COMPACT_RESULT_BYTES = 32768
MAX_CASES = 8
MAX_FULL_CANDIDATE_RESULTS = 4


def _json(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _small_scalar_map(value, *, limit=48):
    if not isinstance(value, dict):
        return {}
    out = {}
    for key in sorted(value):
        if len(out) >= limit:
            break
        item = value[key]
        if isinstance(key, str) and len(key) <= 80 and (
                item is None or isinstance(item, (bool, int, float)) or
                isinstance(item, str) and len(item) <= 160):
            out[key] = item
    return out


def compact_feedback(full_public, public_object_ref):
    """Project one PUBLIC Result into an isolated-hook-safe, reconstructible form.

    Never infer that missing activity rows mean zero events. The original full
    public Result remains available through public_object_ref on all methods.
    """
    if not public_object_ref or not isinstance(full_public, dict):
        raise ContractError("PUBLIC_RESULT_AND_OBJECT_REF_REQUIRED")
    result = project_result(full_public)
    if not result.get("result_sha256") or not result.get("execution_status"):
        raise ContractError("ORIGINAL_RESULT_IDENTITY_REQUIRED")
    facts = result.get("facts", {})
    if not isinstance(facts, dict):
        raise ContractError("PUBLIC_FACTS_OBJECT_REQUIRED")
    observed = {}
    for event in facts.get("activity", []) if isinstance(facts.get("activity"), list) else []:
        if isinstance(event, dict) and isinstance(event.get("action"), str):
            name = event["action"]
            observed[name] = observed.get(name, 0) + 1
    previous_projection = facts.get("projection", {}) if isinstance(facts.get("projection"), dict) else {}
    catalog = facts.get("detail_catalog", {}) if isinstance(facts.get("detail_catalog"), dict) else {}
    declared_counts = facts.get("activity_counts") if isinstance(facts.get("activity_counts"), dict) else None
    # A's unpaged original PUBLIC Results contain the complete activity list.
    # Paged results may contain only a sample, so an absent action is not zero.
    complete_activity = declared_counts is not None or (
        isinstance(facts.get("activity"), list) and not catalog and not previous_projection
    )
    projection = {
        "observed_activity_row_counts": observed or previous_projection.get("observed_activity_row_counts", {}),
        "activity_rows_complete": complete_activity,
        "observed_records_count": len(facts["records"]) if isinstance(facts.get("records"), list) else previous_projection.get("observed_records_count"),
        "observed_packets_count": len(facts["packets"]) if isinstance(facts.get("packets"), list) else previous_projection.get("observed_packets_count"),
        "observed_receiver_count": len(facts["receiver_records"]) if isinstance(facts.get("receiver_records"), list) else previous_projection.get("observed_receiver_count"),
        "other_public_scalar_facts": _small_scalar_map(facts),
    }
    totals = _small_scalar_map(catalog, limit=24)
    compact_facts = {
        "projection": projection,
        "detail_catalog": {"full_public_object_ref": _json(public_object_ref),
                           "original_result_sha256": result["result_sha256"],
                           "declared_totals": totals},
    }
    if complete_activity:
        compact_facts["activity_counts"] = _small_scalar_map(
            declared_counts if declared_counts is not None else observed, limit=48
        )
    for key in ("peak_handle_force_n", "minimum_tx_terminal_v"):
        if key in facts:
            compact_facts[key] = facts[key]
    if isinstance(facts.get("energy"), dict):
        compact_facts["energy"] = _small_scalar_map(facts["energy"], limit=24)
    if isinstance(facts.get("program_state"), dict):
        state = facts["program_state"]
        compact_facts["program_state"] = {
            "summary": _small_scalar_map(state, limit=20),
            "phase_energy_j": _small_scalar_map(state.get("phase_energy_j"), limit=8),
            "phase_esr_j": _small_scalar_map(state.get("phase_esr_j"), limit=8),
            "persistent_queue_count_observed": len(state.get("nvm", {}).get("queue", []))
            if isinstance(state.get("nvm"), dict) and isinstance(state["nvm"].get("queue"), list) else None,
        }
    result["facts"] = compact_facts
    size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode())
    if size > MAX_COMPACT_RESULT_BYTES:
        raise ContractError("COMPACT_PUBLIC_RESULT_OVERSIZE")
    return _json(result)


def compact_engineering_case(case_id, public_result, public_object_ref, *, family=None):
    if not isinstance(case_id, str) or not case_id or len(case_id) > 80:
        raise ContractError("PUBLIC_ENGINEERING_CASE_ID")
    result = compact_feedback(public_result, public_object_ref)
    return {"case_id": case_id, "family": family, "design": deepcopy(result.get("design", {})),
            "execution_status": result["execution_status"], "model_valid": result.get("model_valid"),
            "public_check": deepcopy(result.get("public_check", {})),
            "facts": deepcopy(result["facts"]), "result_sha256": result["result_sha256"],
            "public_object_ref": _json(public_object_ref)}


def frozen_case_summaries(cases):
    if not isinstance(cases, list) or len(cases) > MAX_CASES:
        raise ContractError("PUBLIC_ENGINEERING_CASE_CAP")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("design"), dict) or not case.get("result_sha256"):
            raise ContractError("PUBLIC_ENGINEERING_CASE_SHAPE")
        if case.get("case_id") in seen:
            raise ContractError("DUPLICATE_ENGINEERING_CASE_ID")
        seen.add(case.get("case_id"))
    encoded = _json(cases)
    if len(json.dumps(encoded, ensure_ascii=False, separators=(",", ":")).encode()) > 131072:
        raise ContractError("PUBLIC_ENGINEERING_CASES_OVERSIZE")
    return encoded


def validate_full_candidate_batch(candidates, batch, *, state):
    """Validate host-evaluated, original public outcomes before H-RANK sees them."""
    if not isinstance(candidates, list) or len(candidates) > MAX_FULL_CANDIDATE_RESULTS:
        raise ContractError("FULL_CANDIDATE_CAP")
    if not isinstance(batch, dict) or not isinstance(batch.get("results"), list):
        raise ContractError("HOST_FULL_EVALUATION_BATCH_REQUIRED")
    results = batch["results"]
    if len(results) != len(candidates):
        raise ContractError("FULL_EVALUATION_COUNT_MISMATCH")
    ids = [candidate["id"] for candidate in candidates]
    observed = []
    out = []
    for row in results:
        if not isinstance(row, dict) or row.get("candidate_id") not in ids:
            raise ContractError("FULL_EVALUATION_ID_MISMATCH")
        if row["candidate_id"] in observed:
            raise ContractError("DUPLICATE_FULL_EVALUATION")
        observed.append(row["candidate_id"])
        candidate = next(c for c in candidates if c["id"] == row["candidate_id"])
        if row.get("actual_input_digest") != digest(candidate["actual_input"]):
            raise ContractError("FULL_EVALUATION_ACTION_BINDING")
        usage = row.get("accounting")
        if (not isinstance(usage, dict) or type(usage.get("numerical_inputs")) is not int
                or usage["numerical_inputs"] not in {0, 1}
                or type(usage.get("tool_calls")) is not int or usage["tool_calls"] < 1):
            raise ContractError("FULL_EVALUATION_ACCOUNTING_REQUIRED")
        public_result = row.get("public_result")
        if (not isinstance(public_result, dict) or not public_result.get("result_sha256")
                or not public_result.get("execution_status") or not isinstance(public_result.get("public_check"), dict)):
            raise ContractError("FULL_EVALUATION_PUBLIC_RESULT_REQUIRED")
        if public_result.get("execution_status") in {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}:
            actual = candidate["actual_input"]
            expected_design = {**state.get("design", {}), **actual.get("design_patch", {})}
            expected_problem = {**state.get("problem", {}), **actual.get("problem_patch", {})}
            if public_result.get("design") != expected_design or public_result.get("problem") != expected_problem:
                raise ContractError("FULL_EVALUATION_CONSUMED_INPUT_MISMATCH")
            if public_result.get("task_id") != state.get("task", {}).get("task_id"):
                raise ContractError("FULL_EVALUATION_TASK_MISMATCH")
        out.append({"candidate_id": row["candidate_id"],
                    "public_result": compact_feedback(public_result, row.get("public_object_ref")),
                    "public_object_ref": _json(row["public_object_ref"]),
                    "actual_input_digest": row["actual_input_digest"],
                    "accounting": _json(usage)})
    if set(observed) != set(ids):
        raise ContractError("FULL_EVALUATION_MISSING_CANDIDATE")
    if not isinstance(batch.get("owner_budget_after"), dict):
        raise ContractError("POST_EVALUATION_OWNER_SNAPSHOT_REQUIRED")
    return out


FORMATION_GUIDANCE = (
    "The shared parent has executable H-GEN, H-RANK and H-UPDATE source, and all six H sites "
    "retain the same code/prompt/config/applicability/non-trigger edit rights. A proposed conditional "
    "change needs a source incident, predicted behavior, side effects, local screen and falsifier. "
    "It need not already have parent-versus-child task benefit; later Allocate and actual full tasks "
    "test that benefit. Legal no-update remains valid. Never rewrite an empty or invalid proposal. "
    "Software screens have no full_candidate_results and cannot certify service PASS."
)
