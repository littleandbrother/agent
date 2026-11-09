"""Typed public Result boundary; no solver, provider or prose classification."""
from copy import deepcopy
import hashlib
import json

PROJECTION_VERSION = "pqe-public-projection-v1"
RESULT_FIELDS = {
    "schema_version", "execution_status", "operation", "model_valid", "domain_errors",
    "design", "problem", "facts", "public_check", "usage", "task_id", "task_sha256",
    "input_sha256", "result_sha256", "sources", "program_version", "engineering_model_sha256",
}
FACT_FIELDS = {
    "trace", "activity", "records", "packets", "energy", "receiver_records",
    "peak_handle_force_n", "minimum_tx_terminal_v", "program_state", "tool_error",
    "activity_counts", "detail_catalog", "projection", "requested_detail",
}
CHECK_FIELDS = {"verdict", "failures", "unknown", "received_count"}
SCIENTIFIC_SOURCE_FILES = (
    "door_model.py", "door_program.py", "engineering.py", "executor.py", "evaluator.py",
)


def _digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def is_public_result(value):
    return isinstance(value, dict) and str(value.get("schema_version", "")).startswith("pqe-public-result-")


def project_result(result):
    """Keep permitted feedback and original execution identity, in a new object.

    In particular, the complete host receiver_identity block and its diagnostic
    explanation have no public field. A projection is not a new scientific run.
    """
    if not isinstance(result, dict):
        raise TypeError("PUBLIC_RESULT_OBJECT_REQUIRED")
    out = {k: deepcopy(v) for k, v in result.items() if k in RESULT_FIELDS}
    if "facts" in out:
        out["facts"] = {k: deepcopy(v) for k, v in out["facts"].items() if k in FACT_FIELDS}
    if "public_check" in out:
        out["public_check"] = {k: deepcopy(v) for k, v in out["public_check"].items() if k in CHECK_FIELDS}
    provenance = result.get("public_projection", {})
    if provenance.get("version") == PROJECTION_VERSION:
        out["public_projection"] = {k: provenance[k] for k in
            ("version", "source_result_sha256", "source_public_sha256") if k in provenance}
    else:
        out["public_projection"] = {"version": PROJECTION_VERSION,
            "source_result_sha256": result.get("result_sha256"),
            "source_public_sha256": _digest(result)}
    return out


def project_embedded_results(value):
    """Project typed Results also inside history, evidence and callback payloads."""
    if is_public_result(value):
        return project_result(value)
    if isinstance(value, dict):
        return {k: project_embedded_results(v) for k, v in value.items()}
    if isinstance(value, list):
        return [project_embedded_results(v) for v in value]
    return deepcopy(value)


def scientific_source_identity(sources):
    """Exact consumer/evaluator bindings; adapter projection is tracked separately."""
    return {name: sources[name] for name in SCIENTIFIC_SOURCE_FILES}
