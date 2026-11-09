"""Versioned thin action adapter in the existing bfworld runtime namespace."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

from .executor import execute_design, identity
from .evaluator import evaluate
from .public_projection import project_result

APP = Path(__file__).resolve().parents[7]
SHARED = APP / "studies/pqe20261022/shared"
OPERATIONS = {"edit", "restructure", "refine", "observe", "verify", "select", "report"}


def source_identity():
    root = Path(__file__).parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("door_model.py", "door_program.py", "engineering.py",
                         "executor.py", "evaluator.py", "adapter.py")}


def load_task(task_id):
    catalog = json.loads((SHARED / "door-tasks.json").read_text())
    return deepcopy(catalog[task_id])


def validate_design(task, design):
    allowed = task["design_domain"]
    if set(design) != set(allowed):
        raise ValueError("DESIGN_FIELDS_OUTSIDE_CONTRACT")
    for key, spec in allowed.items():
        value = design[key]
        if spec["kind"] == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not spec["min"] <= value <= spec["max"]:
                raise ValueError("DESIGN_DOMAIN:" + key)
        elif spec["kind"] == "boolean":
            if type(value) is not bool:
                raise ValueError("DESIGN_TYPE:" + key)
        elif spec["kind"] == "mechanism":
            if not isinstance(value, dict) or set(value) - set(spec["editable"]):
                raise ValueError("MECHANISM_PERMISSION")
            for name, number in value.items():
                limits = spec["editable"][name]
                if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not limits[0] <= number <= limits[1]:
                    raise ValueError("MECHANISM_DOMAIN:" + name)
    if not design["brownout_v"] < design["startup_v"] <= task["components"]["max_v"]:
        raise ValueError("POWER_THRESHOLDS")


def execute(task, design, problem, decision, output_dir=None, *, engineering_model=None, task_resolver=None):
    """All methods use this consumer. A decision cannot replace service/truth.

    Public Result omits per-event truth and hidden final labels. Full assessment
    is written only to the host output directory; a runner must not expose it.
    """
    # A resolver is an explicit trusted-host capability, never an action field.
    # F1 resolves just its current role from the hash-bound private registry.
    frozen = (task_resolver or load_task)(task["task_id"])
    if identity(task) != identity(frozen):
        raise ValueError("FROZEN_TASK_MISMATCH")
    actual = decision.get("actual_input", {})
    if set(actual) - {"operation", "design_patch", "problem_patch", "dt_s"}:
        raise ValueError("ACTION_FIELDS_OUTSIDE_CONTRACT")
    operation = actual.get("operation")
    if operation not in OPERATIONS:
        raise ValueError("UNKNOWN_OPERATION")
    new_problem = deepcopy(problem)
    patch_p = actual.get("problem_patch", {})
    if set(patch_p) - {"active_variables", "groups", "fixed_choices", "assumptions", "local_objective"}:
        raise ValueError("PROBLEM_CANNOT_EDIT_EVALUATOR_OR_TASK")
    new_problem.update(patch_p)
    legal = set(task["design_domain"])
    active = set(new_problem.get("active_variables", []))
    if not active <= legal:
        raise ValueError("PROBLEM_ACTIVE_DOMAIN")
    groups = new_problem.get("groups", [])
    if any(not set(g) <= active for g in groups):
        raise ValueError("PROBLEM_GROUP_DOMAIN")
    design_patch = actual.get("design_patch", {})
    if operation in {"observe", "verify", "report", "select"} and design_patch:
        raise ValueError("READ_OR_SELECTION_ACTION_HAS_EDIT")
    if not set(design_patch) <= active:
        raise ValueError("EDIT_OUTSIDE_ACTIVE_VARIABLES")
    updated = {**deepcopy(design), **deepcopy(design_patch)}
    for name, value in new_problem.get("fixed_choices", {}).items():
        if name not in legal or updated[name] != value:
            raise ValueError("FIXED_CHOICE_CHANGED_WITHOUT_REFORM")
    validate_design(task, updated)
    dt = actual.get("dt_s", task["integration"]["dt_s"])
    if dt not in task["integration"]["allowed_dt_s"]:
        raise ValueError("UNREGISTERED_REFINEMENT")
    sources = source_identity()
    started = time.monotonic()
    receipt = {"task_sha256": identity(task), "parent_design_sha256": identity(design),
               "problem": new_problem, "decision": deepcopy(decision), "actual_design": updated,
               "sources": sources, "phase": "BEFORE_EXECUTION"}
    output = Path(output_dir) if output_dir else None
    if output:
        output.mkdir(parents=True, exist_ok=False)
        (output / "decision.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
    if operation in {"select", "report"}:
        # Selection/reporting cannot self-certify the design or spend an
        # unrequested simulation. The last independently assessed result stays
        # authoritative in the episode host; this action records only intent.
        public = {"schema_version": "pqe-public-result-v1", "execution_status": "NO_EXECUTION",
                  "operation": operation, "task_id": task["task_id"], "design": updated,
                  "problem": new_problem, "model_valid": None, "facts": {},
                  "public_check": {"verdict": "UNKNOWN", "failures": [], "unknown": ["NO_NEW_ASSESSMENT"]},
                  "usage": {"paid_model_requests": 0, "numerical_inputs": 0, "wall_s": time.monotonic() - started}}
        public = project_result(public)
        if output:
            (output / "public-result.json").write_text(json.dumps(public, indent=2) + "\n")
        return public
    raw = execute_design(task, updated, dt_s=dt, engineering_model=engineering_model)
    assessment = evaluate(task, updated, raw)
    if source_identity() != sources:
        raise RuntimeError("APPARATUS_CHANGED_DURING_EXECUTION")
    public = {"schema_version": "pqe-public-result-v2", "execution_status": raw["execution_status"],
              "task_id": task["task_id"], "task_sha256": identity(task), "input_sha256": identity(updated),
              "design": updated, "problem": new_problem, "sources": sources,
              "model_valid": raw["model_valid"], "domain_errors": raw["domain_errors"],
              "program_version": raw["program_version"],
              "engineering_model_sha256": raw["engineering_model_sha256"],
              "facts": {"trace": raw["trace"], "activity": raw["activity"], "records": raw["records"],
                        "packets": raw["packets"], "energy": raw["energy"],
                        "receiver_records": assessment["receiver_records"],
                        "peak_handle_force_n": raw["peak_handle_force_n"],
                        "minimum_tx_terminal_v": raw["minimum_tx_terminal_v"],
                        "program_state": raw["program_state"]},
              "public_check": {"verdict": assessment["verdict"], "failures": assessment["failures"],
                               "unknown": assessment["unknown"], "received_count": len(assessment["receiver_records"])},
              "usage": {"paid_model_requests": 0, "numerical_inputs": 1, "wall_s": time.monotonic() - started},
              "result_sha256": raw["result_sha256"]}
    public = project_result(public)
    if output:
        for name, value in [("raw.json", raw), ("assessment.json", assessment), ("public-result.json", public)]:
            (output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return public
