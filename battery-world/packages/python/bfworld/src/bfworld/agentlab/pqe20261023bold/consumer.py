"""New shared firmware version; original physical solver/evaluator code reused.

Function objects have independent globals. No old module is monkeypatched and
no executor tree is copied. Original Task/Design authority and public projection
are retained by the original adapter function.
"""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
from types import FunctionType

from ..pqe20261022 import adapter as original_adapter
from ..pqe20261022 import engineering as original_engineering
from ..pqe20261022 import executor as original_executor
from .firmware import DoorProgram, POLICIES, PROGRAM_VERSION

VERSION = "pqe-door-bold-consumer-v1"
EXTRA_DOMAIN = {
    "firmware_policy": {"kind": "enum", "values": list(POLICIES)},
    "backoff_max_s": {"kind": "number", "min": .01, "max": 1.0},
    "tx_reserve_v": {"kind": "number", "min": 0.0, "max": .2},
}
DEFAULT_EXTRA = {"firmware_policy": "fixed_retry_v1", "backoff_max_s": 1.0,
                 "tx_reserve_v": .025}


def extend_task(task):
    task = deepcopy(task)
    for key, spec in EXTRA_DOMAIN.items():
        if key in task["design_domain"] and task["design_domain"][key] != spec:
            raise ValueError("BOLD_EXTENSION_CONTRACT_MISMATCH:" + key)
        task["design_domain"][key] = deepcopy(spec)
        task["initial_design"].setdefault(key, DEFAULT_EXTRA[key])
    problem = task["initial_problem"]
    for key in EXTRA_DOMAIN:
        if key not in problem["active_variables"]:
            problem["active_variables"].append(key)
    problem["groups"] = [list(problem["active_variables"])]
    return task


def _base_design(design):
    return {key: deepcopy(value) for key, value in design.items() if key not in EXTRA_DOMAIN}


def validate_design(task, design):
    if set(design) != set(task["design_domain"]):
        raise ValueError("DESIGN_FIELDS_OUTSIDE_CONTRACT")
    if any(task["design_domain"].get(k) != v for k, v in EXTRA_DOMAIN.items()):
        raise ValueError("BOLD_COMMON_DOMAIN_REQUIRED")
    base_task = deepcopy(task)
    base_task["design_domain"] = {k: v for k, v in task["design_domain"].items() if k not in EXTRA_DOMAIN}
    original_adapter.validate_design(base_task, _base_design(design))
    if design["firmware_policy"] not in POLICIES:
        raise ValueError("FIRMWARE_POLICY_DOMAIN")
    for name in ("backoff_max_s", "tx_reserve_v"):
        value, domain = design[name], EXTRA_DOMAIN[name]
        if type(value) not in (int, float) or not math.isfinite(value) or not domain["min"] <= value <= domain["max"]:
            raise ValueError("BOLD_DESIGN_DOMAIN:" + name)
    if design["firmware_policy"] == "voltage_history_backoff_v1":
        if not design["persistent_queue"] or design["backoff_max_s"] < design["retry_s"]:
            raise ValueError("ADAPTIVE_REQUIRES_PERSISTENT_QUEUE_AND_BACKOFF_ORDER")


def source_identity():
    result = original_adapter.source_identity()
    base = Path(original_adapter.__file__).parent
    result["public_projection.py"] = hashlib.sha256((base / "public_projection.py").read_bytes()).hexdigest()
    for name in ("consumer.py", "firmware.py"):
        result["bold/" + name] = hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
    return result


def build_engineering_model(task, design):
    return {"schema_version": "pqe-door-bold-engineering-v1",
            "task_sha256": original_executor.identity(task),
            "design_sha256": original_executor.identity(design),
            "base": original_engineering.build_engineering_model(task, _base_design(design)),
            "firmware": {"version": PROGRAM_VERSION,
                         "parameters": {k: deepcopy(design[k]) for k in EXTRA_DOMAIN}},
            "scope": "Original connected mechanical/electrical/load model with a common observable-state firmware extension; no source, cost or evaluator relaxation."}


def consume_engineering_model(model, task=None, design=None):
    if task is None or design is None or model != build_engineering_model(task, design):
        raise ValueError("BOLD_ENGINEERING_TASK_DESIGN_BINDING")
    resolved = original_engineering.consume_engineering_model(model["base"], task, _base_design(design))
    resolved["design"].update(deepcopy(model["firmware"]["parameters"]))
    resolved["model_sha256"] = original_executor.identity(model)
    resolved["program_version"] = PROGRAM_VERSION
    return resolved


def _bind(function, **overrides):
    namespace = {**function.__globals__, **overrides}
    bound = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = deepcopy(function.__kwdefaults__)
    return bound


execute_design = _bind(original_executor.execute_design, DoorProgram=DoorProgram,
                      PROGRAM_VERSION=PROGRAM_VERSION,
                      build_engineering_model=build_engineering_model,
                      consume_engineering_model=consume_engineering_model)
_execute = _bind(original_adapter.execute, execute_design=execute_design,
                 validate_design=validate_design, source_identity=source_identity)


def execute(task, design, problem, decision, output_dir=None, task_resolver=None):
    if task_resolver is None:
        raise ValueError("BOLD_TRUSTED_FROZEN_TASK_RESOLVER_REQUIRED")
    return _execute(task, design, problem, decision, output_dir,
                    task_resolver=task_resolver)
