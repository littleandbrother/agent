"""Thin, host-owned adapter for the new prospective event-holder apparatus.

The old action permissions, receiver, evaluator and public projection execute
unchanged. Function bindings have private globals; no old module is patched.
"""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from types import FunctionType

from ..pqe20261022 import adapter as original

VERSION = "codebt-door-adapter-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def source_identity():
    from ..pqe20261023bold import consumer as old_consumer
    result = old_consumer.source_identity()
    here = Path(__file__).parent
    for name in ("adapter.py", "consumer.py", "holding.py", "task.py", "facts.py", "bounds.py"):
        result["codebt/" + name] = hashlib.sha256((here / name).read_bytes()).hexdigest()
    return result


def validate_design(task, design):
    from .task import validate_design as validate
    return validate(task, design)


def prepare(task, design, problem, decision, *, task_resolver):
    """Pure permission check. Model capability never expands task authority."""
    if task_resolver is None or digest(task_resolver(task["task_id"])) != digest(task):
        raise ValueError("CODEBT_TRUSTED_FROZEN_TASK_REQUIRED")
    actual = decision.get("actual_input", {})
    if set(actual) - {"operation", "design_patch", "problem_patch", "dt_s"}:
        raise ValueError("ACTION_FIELDS_OUTSIDE_CONTRACT")
    operation = actual.get("operation")
    if operation not in original.OPERATIONS:
        raise ValueError("UNKNOWN_OPERATION")
    patch_p = actual.get("problem_patch", {})
    if set(patch_p) - {"active_variables", "groups", "fixed_choices", "assumptions", "local_objective"}:
        raise ValueError("PROBLEM_CANNOT_EDIT_EVALUATOR_OR_TASK")
    updated_problem = {**deepcopy(problem), **deepcopy(patch_p)}
    active = set(updated_problem.get("active_variables", []))
    if not active <= set(task["design_domain"]):
        raise ValueError("PROBLEM_ACTIVE_DOMAIN")
    if any(not set(g) <= active for g in updated_problem.get("groups", [])):
        raise ValueError("PROBLEM_GROUP_DOMAIN")
    patch = actual.get("design_patch", {})
    if operation in {"observe", "verify", "select", "report"} and patch:
        raise ValueError("READ_OR_SELECTION_ACTION_HAS_EDIT")
    if not set(patch) <= active:
        raise ValueError("EDIT_OUTSIDE_ACTIVE_VARIABLES")
    updated = {**deepcopy(design), **deepcopy(patch)}
    if any(k not in task["design_domain"] or updated[k] != v
           for k, v in updated_problem.get("fixed_choices", {}).items()):
        raise ValueError("FIXED_CHOICE_CHANGED_WITHOUT_REFORM")
    validate_design(task, updated)
    dt = actual.get("dt_s", task["integration"]["dt_s"])
    if dt not in task["integration"]["allowed_dt_s"]:
        raise ValueError("UNREGISTERED_REFINEMENT")
    return updated, updated_problem, dt


def _bind(function, **overrides):
    bound = FunctionType(function.__code__, {**function.__globals__, **overrides},
                         function.__name__, function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = deepcopy(function.__kwdefaults__)
    return bound


def bind_consumer(raw_executor, evaluator):
    """Host capability also permits a zero-science fixture through this path."""
    def run(task, design, problem, decision, *, task_resolver):
        captured = {}

        def record_raw(*args, **kwargs):
            captured["raw"] = raw_executor(*args, **kwargs)
            return captured["raw"]

        def record_assessment(*args, **kwargs):
            captured["assessment"] = evaluator(*args, **kwargs)
            return captured["assessment"]

        execute = _bind(original.execute, execute_design=record_raw,
                        evaluate=record_assessment, validate_design=validate_design,
                        source_identity=source_identity)
        public = execute(task, design, problem, decision, output_dir=None,
                         task_resolver=task_resolver)
        return public, captured
    return run


def _write_gzip(path, value):
    # A single canonical compressed artifact; no uncompressed backup is made.
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        if digest(json.load(stream)) != digest(value):
            raise RuntimeError("COMPRESSED_ARTIFACT_READBACK_MISMATCH")


def execute(task, design, problem, decision, output_dir=None, *, task_resolver):
    from . import consumer, facts
    from ..pqe20261022.evaluator import evaluate
    updated, updated_problem, _ = prepare(task, design, problem, decision,
                                          task_resolver=task_resolver)
    public, captured = bind_consumer(consumer.execute_design, evaluate)(
        task, design, problem, decision, task_resolver=task_resolver)
    base_public_sha256 = digest(public)
    if "raw" in captured:
        public["facts"]["energy"]["holding_operation_j"] = deepcopy(
            captured["raw"].get("holding_loads", {}))
        public["facts"]["energy"]["holding_operation_j_is_subset_of_load_j"] = True
    public["schema_version"] = "pqe-public-result-codebt-v1"
    # Public static relationships add neither hidden truth nor a repair hint.
    public["component_contract"] = facts.design_facts(updated, task)
    public["adapter_version"] = VERSION
    public["codebt_projection"] = {
        "version": VERSION, "base_public_sha256": base_public_sha256,
        "component_contract_sha256": digest(public["component_contract"]),
        "raw_result_sha256": public.get("result_sha256"),
        "extra_energy_fields_are_diagnostic_subsets": True}
    if output_dir is not None:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=False)
        receipt = {"task_sha256": digest(task), "parent_design_sha256": digest(design),
                   "actual_design": updated, "problem": updated_problem,
                   "decision": deepcopy(decision), "sources": source_identity()}
        (folder / "decision.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
        for name, value in captured.items():
            _write_gzip(folder / (name + ".json.gz"), value)
        (folder / "public-result.json").write_text(json.dumps(public, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False)+"\n")
    return public
