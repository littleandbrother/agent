"""Current-instance binding to the existing qualified constructed LC consumer.

No new physics, evaluator or controller.  The private host task is supplied by
the trusted runner, never recovered from an action or exposed through a hook.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import time
from types import FunctionType

from ..pqe20261022 import e3lc_lc, lcpv20261023
from ..pqe20261022.methods import common_contract_check


def source_identity():
    host, _ = e3lc_lc.support()
    paths = [Path(__file__), Path(host.__file__), host.REVIEW,
             Path(e3lc_lc.__file__), e3lc_lc.SUPPORT / "lc_public_view.py"]
    return {**lcpv20261023.dependency_identity(),
            **{str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def participant_task(public):
    return e3lc_lc.participant_task(deepcopy(public))


def validate_design(task, design):
    host, _ = e3lc_lc.support()
    host.validate_flat({"Task": task}, design)


def bind_inputs(task, design, context):
    host, _ = e3lc_lc.support()
    public, original = deepcopy(context["public"]), deepcopy(context["host_task"])
    if participant_task(public) != task:
        raise ValueError("BOLD_LC_PUBLIC_INSTANCE_BINDING")
    if (original["task_id"] != "LC-PV-STRICT-24H-v1"
            or original["instance_id"] != task["task_id"]
            or original.get("allowed_for_learning") is not False):
        raise ValueError("BOLD_LC_CONSUMER_INSTANCE_BINDING")
    # Public schedules and service values are the actual executed inputs.  Air
    # truth and the independent assessment stay exclusively in this host.
    for key in ("duration_s", "gateway_windows_s", "optical_environment"):
        if original[key] != public["Task"][key]:
            raise ValueError("BOLD_LC_PUBLIC_SCHEDULE_MISMATCH:" + key)
    for key, value in public["Task"]["service"].items():
        if key not in {"history", "new_sample_receive_scope"} and original["service"].get(key) != value:
            raise ValueError("BOLD_LC_PUBLIC_SERVICE_MISMATCH:" + key)
    host.validate_flat(public, design)
    inputs = {"schema": "pqe-lcpv-constructed-input-v1", "name": task["task_id"],
              "Task": original, "Profile": public["Profile"],
              "Design": {k: deepcopy(design[k]) for k in public["design_fields"]},
              "Program": {**public["Task"]["fixed_program_semantics"],
                          **{k: deepcopy(design[k]) for k in public["program_fields"]}},
              "purpose": "BOLD pre-frozen independent prospective development condition; unchanged consumer and strict evaluator."}
    lcpv20261023.validate(inputs)
    return inputs


def execute(task, design, problem, decision, output_dir=None, *, task_resolver=None, context=None):
    if context is None or task_resolver is None or task_resolver(task["task_id"]) != task:
        raise ValueError("BOLD_LC_TRUSTED_CURRENT_INSTANCE_REQUIRED")
    host, _ = e3lc_lc.support()
    actual = common_contract_check({"task": task, "design": design, "problem": problem},
                                  decision.get("actual_input", {}), {"remaining_actions": 1})
    updated = {**deepcopy(design), **actual.get("design_patch", {})}
    new_problem = {**deepcopy(problem), **actual.get("problem_patch", {})}
    inputs = bind_inputs(task, updated, context)
    sources = source_identity()
    output = Path(output_dir) if output_dir else None

    def save(name, value):
        if output:
            with (output / name).open("x") as stream:
                json.dump(value, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                stream.write("\n")

    if output:
        output.mkdir(parents=True, exist_ok=False)
    save("decision.json", {"task_sha256": lcpv20261023.identity(task), "decision": decision,
                           "actual_design": updated, "problem": new_problem,
                           "consumer_input_sha256": lcpv20261023.identity(inputs), "sources": sources})
    if actual["operation"] in {"select", "report"}:
        public = {"schema_version": "pqe-public-result-v2", "world_kind": "LC-PV",
                  "execution_status": "NO_EXECUTION", "operation": actual["operation"],
                  "task_id": task["task_id"], "design": updated, "problem": new_problem,
                  "model_valid": None, "facts": {},
                  "public_check": {"verdict": "UNKNOWN", "failures": [], "unknown": ["NO_NEW_ASSESSMENT"]},
                  "usage": {"paid_model_requests": 0, "numerical_inputs": 0, "wall_s": 0}}
        save("public-result.json", public)
        return public
    save("input.json", inputs)
    started = time.monotonic()
    raw = lcpv20261023.simulate(inputs)
    assessment = host.evaluate(inputs, raw)
    # Rebind only the current public-instance loader.  The original projection
    # body, independent review and loaded PV/supply/record semantics are reused.
    public_fn = FunctionType(host.public_result.__code__,
                             {**host.public_result.__globals__, "load_public": lambda: deepcopy(context["public"])},
                             host.public_result.__name__, host.public_result.__defaults__)
    public_fn.__kwdefaults__ = host.public_result.__kwdefaults__
    public = public_fn(updated, inputs, raw, assessment, problem=new_problem, wall_s=time.monotonic() - started)
    public["task_sha256"] = lcpv20261023.identity(task)
    public["sources"] = sources
    if source_identity() != sources:
        raise ValueError("BOLD_LC_SCIENTIFIC_SOURCE_CHANGED_DURING_EXECUTION")
    save("raw.json", raw)
    save("assessment.json", assessment)
    save("public-result.json", public)
    return public
