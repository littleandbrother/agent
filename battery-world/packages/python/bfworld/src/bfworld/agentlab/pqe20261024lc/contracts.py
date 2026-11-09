"""Public training feedback contracts; no scientific or provider authority."""
from copy import deepcopy

from ..pqe20261022.methods import ContractError, digest

VERSION = "pqe-lc-service-learning-v1"


def validate_training_feedback(value, *, remaining_full, frozen_tasks):
    """Accept only accounted, task-bound original consumer feedback."""
    if not isinstance(value, dict) or value.get("status") not in {"COMPLETE", "PARTIAL", "STOPPED"}:
        raise ContractError("TRAINING_EXECUTION_STATUS_REQUIRED")
    count = value.get("full_inputs")
    if type(count) is not int or not 0 <= count <= remaining_full:
        raise ContractError("TRAINING_FULL_INPUT_CAP_OR_UNKNOWN")
    rows = value.get("task_results")
    if not isinstance(rows, list) or not isinstance(value.get("execution_refs"), list):
        raise ContractError("TRAINING_PUBLIC_RESULTS_AND_REFS_REQUIRED")
    task_ids = {t["task_id"] for t in frozen_tasks}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("task_id") not in task_ids or row["task_id"] in seen:
            raise ContractError("TRAINING_TASK_ID_MISMATCH")
        seen.add(row["task_id"])
        if (row.get("initial_verdict") not in {"PASS", "FAIL", "UNKNOWN"} or
                row.get("final_verdict") not in {"PASS", "FAIL", "UNKNOWN"} or
                type(row.get("model_valid")) is not bool or
                type(row.get("correct_stop")) is not bool or
                not isinstance(row.get("result_sha256"), str) or
                not row.get("public_object_ref")):
            raise ContractError("TRAINING_TASK_PUBLIC_BINDING_REQUIRED")
    if not isinstance(value.get("owner_budget_after"), dict):
        raise ContractError("TRAINING_OWNER_BUDGET_REQUIRED")
    return deepcopy(value)


def service_selection(rows, frozen_tasks):
    """Only full service/correct stop can justify keeping one trained child."""
    by_id = {row["task_id"]: row for row in rows}
    if not by_id or any(task["task_id"] not in by_id for task in frozen_tasks):
        return {"eligible": False, "reason": "INCOMPLETE_FROZEN_TRAINING_COMPARISON"}
    improved = []
    for task in frozen_tasks:
        task_id = task["task_id"]
        row = by_id[task_id]
        parent_pass = (task.get("parent_final_verdict") == "PASS" or
                       task.get("parent_correct_stop") is True)
        child_pass = row["model_valid"] and (row["final_verdict"] == "PASS" or row["correct_stop"])
        # A parent that correctly stops on an already-PASS task is a control.
        # A gratuitous action with an eventual PASS is still a regression.
        if task.get("parent_correct_stop") is True:
            child_pass = row["model_valid"] and row["correct_stop"]
        if parent_pass and not child_pass:
            return {"eligible": False, "reason": "REGRESSION_ON_PARENT_PASS", "task_id": task_id}
        if not parent_pass and child_pass:
            improved.append(task_id)
    return {"eligible": bool(improved),
            "reason": "FULL_SERVICE_OR_CORRECT_STOP_GAIN" if improved else "NO_FULL_SERVICE_GAIN",
            "improved_task_ids": improved,
            "selection_basis": "full public service or correct stop; received count excluded"}


def version_binding(*, condition, proposal_index, revision_index, program, patch, tasks):
    if condition not in {"H2", "H4"} or proposal_index not in {0, 1} or revision_index not in {0, 1}:
        raise ContractError("TRAINING_VERSION_INDEX")
    return {"condition": condition, "proposal_index": proposal_index,
            "revision_index": revision_index, "program_sha256": digest(program),
            "program_id": program["program_id"],
            "source_incidents": deepcopy(patch["source_incidents"]),
            "training_task_ids": [t["task_id"] for t in tasks]}
