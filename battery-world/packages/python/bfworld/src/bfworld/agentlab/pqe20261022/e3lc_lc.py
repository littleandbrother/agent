"""One current LC H0 entry through the existing paid episode and consumer.

Import, freeze and observation do not run science. Only a selected, validated
non-detail action may call the unchanged constructed-world consumer. The public
Task is a declared prose/material projection; the host Task stays frozen.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

from . import e3lc, pilot as p, lcpv20261023 as consumer
from .episode_methods import EpisodeDriver
from .executor import identity
from .methods import common_contract_check, public_state
from .public_projection import project_result

OUT, STUDY, PACKAGE = e3lc.OUT, e3lc.STUDY, e3lc.PACKAGE
SRC = Path(__file__).resolve().parent
SUPPORT = OUT / "a"
PRIVATE = STUDY / "lcpv-private"
PROTOCOL = OUT / "s0/lc-protocol.json"
REGISTRY = PRIVATE / "registry.json"
LIMITS = {**e3lc.LIMITS, "bytes": 120_000_000}
FACT_LISTS = ("trace", "activity", "records", "packets", "receiver_records")
PAGE_ROWS, COMPACT_BYTES = 4, 20_000


@lru_cache(maxsize=1)
def support():
    """Load A's existing helpers without replacing unrelated common modules."""
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    absent = object()
    prior = {name: sys.modules.get(name, absent) for name in ("common", "lc_host")}
    try:
        sys.modules["common"] = load("_pqe_e3lc_common", SUPPORT / "common.py")
        host = load("_pqe_e3lc_host", SUPPORT / "lc_host.py")
        sys.modules["lc_host"] = host
        view = load("_pqe_e3lc_view", SUPPORT / "lc_public_view.py")
        return host, view
    finally:
        for name, value in prior.items():
            if value is absent:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def participant_task(public=None):
    host, view = support()
    public = host.load_public() if public is None else public
    task = view.participant_task(public)
    # The unchanged driver allowlists Task fields. Put current LC-only material
    # under public_inputs explicitly instead of falling back to door material.
    task["public_inputs"] = {key: deepcopy(task[key]) for key in (
        "target", "optical_environment", "thermal_contract", "clock_contract",
        "fixed_program_semantics", "observations", "domain_scope",
        "allowed_for_learning", "exposure", "consumer_contract_task_id", "instance_id")}
    task["public_inputs"].update(
        Profile=deepcopy(public["Profile"]), design_fields=list(public["design_fields"]),
        program_fields=list(public["program_fields"]),
        feedback_access={"lists": list(FACT_LISTS), "detail_page_rows": PAGE_ROWS,
            "target": "detail:<list>:<offset>",
            "scope": "Current retained result only; detail observe/verify has no simulation or candidate evaluation. Sampled lists keep exact counts; final memory/pending are sampled with exact counts."})
    task["gateway_windows"] = deepcopy(task["gateway_windows_s"])
    task["integration"] = {"dt_s": 1.0, "allowed_dt_s": [1.0],
        "scope": "Frozen constructed one-second consumer; refinement cannot change integration or evaluator."}
    task["allowed_operations"] = ["edit", "observe", "verify", "restructure", "report", "select", "refine"]
    task = public_state({"task": task})["task"]
    task["initial_design"] = deepcopy(public["Design"])
    task["initial_problem"] = deepcopy(public["Problem"])
    return task


def _verify_bindings(protocol):
    if (protocol["package"] != PACKAGE or protocol["limits_per_episode"] != LIMITS
            or protocol["max_candidate_evaluations"] != 6
            or protocol["model_identity"] != p.MODEL_IDENTITY
            or protocol["allowed_for_learning"] is not False):
        raise ValueError("LC_FROZEN_PROTOCOL_OR_LIMITS_CHANGED")
    for path, expected in protocol["source_bindings"].items():
        if e3lc.sha(path) != expected:
            raise ValueError("LC_FROZEN_SOURCE_CHANGED:" + path)
    for ref in protocol["current_bindings"].values():
        if e3lc.binding(ref["path"]) != ref:
            raise ValueError("LC_CURRENT_ARTIFACT_CHANGED")
    host, view = support()
    public = host.load_public()
    if (identity(public["Task"]) != protocol["task_identity"]["original_public_Task_sha256"]
            or identity(view.participant_task(public)) != protocol["task_identity"]["prose_view_Task_sha256"]
            or identity(participant_task(public)) != protocol["task_identity"]["driver_Task_sha256"]
            or host.scientific_sources() != protocol["scientific_source"]):
        raise ValueError("LC_CURRENT_TASK_OR_SCIENCE_CHANGED")
    return public


def initial_observation(protocol, task_id=None, *, task_resolver=None):
    """Read the exact new initial only, with LC-specific identity checks."""
    public = _verify_bindings(protocol)
    host, _ = support()
    if task_id != public["Task"]["task_id"]:
        raise ValueError("LC_CURRENT_TASK_ONLY")
    registry = e3lc.read(REGISTRY)
    inputs = e3lc.read(registry["initial_input_path"])
    initial = e3lc.read(registry["initial_public_result_path"])
    assessment = e3lc.read(registry["initial_assessment_path"])
    if (inputs != host.bind_inputs(public["Design"])
            or initial["task_id"] != task_id
            or initial["task_sha256"] != identity(public["Task"])
            or initial["design"] != public["Design"] or initial["problem"] != public["Problem"]
            or initial["consumer_input_sha256"] != identity(inputs)
            or initial["input_sha256"] != identity(public["Design"])
            or initial["sources"] != {Path(k).name: v for k, v in protocol["scientific_source"].items()}
            or initial["result_sha256"] != assessment["raw_result_sha256"]
            or initial["public_check"]["verdict"] != assessment["verdict"]
            or initial.get("allowed_for_learning") is not False
            or host.exact_cache_key(public["Design"]) != registry["initial_exact_cache_key"]):
        raise ValueError("LC_INITIAL_BINDING_MISMATCH")
    if task_resolver is not None and task_resolver(task_id) != participant_task(public):
        raise ValueError("LC_PARTICIPANT_TASK_CHANGED")
    return project_result(initial)


def resolve(protocol):
    def resolver(task_id):
        public = support()[0].load_public()
        task = participant_task(public)
        if task_id != task["task_id"] or identity(task) != protocol["task_identity"]["driver_Task_sha256"]:
            raise ValueError("LC_CURRENT_TASK_ONLY")
        return task
    return resolver


def _sample(rows, count):
    if len(rows) <= count:
        return deepcopy(rows)
    indices = [0] if count == 1 else sorted({round(i * (len(rows) - 1) / (count - 1)) for i in range(count)})
    return [deepcopy(rows[i]) for i in indices]


def compact_result(result, target=""):
    """Bound repeated public wire data, retaining complete host result pages."""
    full = project_result(result)
    compact = deepcopy(full)
    facts, original = compact.setdefault("facts", {}), full.get("facts", {})
    facts["detail_catalog"] = {name: {"count": len(original.get(name, [])),
        "page_size": PAGE_ROWS, "target": "detail:" + name + ":<offset>"} for name in FACT_LISTS}
    if "activity" in original:
        facts["activity_counts"] = dict(Counter(row.get("action", "?") for row in original["activity"]))
    facts["projection"] = "Evenly sampled public lists and final memory/pending, with exact counts. Detail pages contain up to four exact rows of the current retained result; no new execution."
    if target:
        match = re.fullmatch(r"detail:(trace|activity|records|packets|receiver_records):(\d+)", target)
        if not match:
            raise ValueError("LC_PUBLIC_DETAIL_TARGET_INVALID")
        name, offset = match.group(1), int(match.group(2))
        rows = original.get(name, [])
        if offset > len(rows):
            raise ValueError("LC_PUBLIC_DETAIL_OFFSET")
        facts["requested_detail"] = {"list": name, "offset": offset,
            "rows": deepcopy(rows[offset:offset + PAGE_ROWS]), "total": len(rows)}
    for count in (8, 4, 2, 1):
        for name in FACT_LISTS:
            if name in original:
                facts[name] = _sample(original[name], count)
        state = facts.get("program_state", {})
        for name in ("memory", "pending"):
            rows = original.get("program_state", {}).get(name)
            if isinstance(rows, list):
                state[name] = _sample(rows, min(count, 4))
                state[name + "_count"] = len(rows)
        if len(p.encoded(compact)) <= COMPACT_BYTES:
            return compact
    raise ValueError("LC_COMPACT_PUBLIC_BYTES_CAP")


def initial_state(task, design, problem, initial=None):
    state = {"task": public_state({"task": task})["task"], "design": deepcopy(design),
        "problem": deepcopy(problem), "history": [], "evidence": []}
    if initial is not None:
        if initial["task_id"] != task["task_id"] or initial["design"] != design or initial["problem"] != problem:
            raise ValueError("LC_INITIAL_OBSERVATION_INPUT_MISMATCH")
        compact = compact_result(initial)
        record = {"origin": "DEVELOPER_PROVIDED_INITIAL_OBSERVATION", "agent_selected": False,
            "charged_to": "one frozen LC initial input; outside this episode candidate quota",
            "allowed_for_learning": False, "result": compact}
        state.update(last_result=compact, history=[deepcopy(record)], evidence=[deepcopy(record)])
    return state


class LCEpisode(p.Episode):
    """Keep inherited planner, broker, ledger, ready(paid=...), and close."""
    def consume(self, decision):
        self.ready()
        self.tools += 1
        if self.tools > p.LIMITS["tool_calls"]:
            raise ValueError("EPISODE_TOOL_CAP")
        output = self.root / "actions" / f"{self.tools:02d}"
        p.save(output / "attempt.json", {"decision": decision, "at": e3lc.now()})
        try:
            actual = common_contract_check({"task": self.task, "design": self.design,
                "problem": self.problem}, decision["actual_input"], {"remaining_actions": 25 - self.tools})
            host, _ = support()
            public_task = _verify_bindings(self.protocol)
            if (identity(self.task) != self.protocol["task_identity"]["driver_Task_sha256"]
                    or identity(public_task["Task"]) != self.protocol["task_identity"]["original_public_Task_sha256"]
                    or host.scientific_sources() != self.protocol["scientific_source"]):
                raise ValueError("LC_FROZEN_TASK_OR_EVALUATOR_CHANGED")
            design = {**self.design, **actual.get("design_patch", {})}
            problem = {**self.problem, **actual.get("problem_patch", {})}
            host.validate_flat(public_task, design)
            op = actual["operation"]
            target = decision.get("selected_candidate", {}).get("target", "")
            detail = target.startswith("detail:")
            evaluation = op not in {"report", "select"} and not detail
            if detail:
                if op not in {"observe", "verify"} or actual.get("problem_patch") or self.last_full is None:
                    raise ValueError("LC_DETAIL_REQUIRES_CURRENT_READ_ONLY_RESULT")
                if self.last_full["design"] != self.design:
                    raise ValueError("LC_DETAIL_CURRENT_DESIGN_MISMATCH")
                public = deepcopy(self.last_full)
                public["usage"] = {"paid_model_requests": 0, "numerical_inputs": 0, "detail_only": True, "wall_s": 0}
            elif op in {"report", "select"}:
                public = {"schema_version": "pqe-public-result-v2", "execution_status": "NO_EXECUTION",
                    "operation": op, "task_id": self.task["task_id"],
                    "task_sha256": self.protocol["task_identity"]["original_public_Task_sha256"],
                    "design": deepcopy(self.design), "problem": deepcopy(self.problem), "model_valid": None,
                    "domain_errors": [], "facts": {}, "public_check": {"verdict": "UNKNOWN", "failures": [],
                        "unknown": ["NO_EXECUTION"]}, "usage": {"paid_model_requests": 0, "numerical_inputs": 0}}
            else:
                if sum(a.get("candidate_evaluation", False) for a in self.actions) >= 6:
                    raise ValueError("CANDIDATE_EVALUATION_CAP")
                candidate = identity(design)
                if candidate not in self.candidates and len(self.candidates) >= 6:
                    raise ValueError("EPISODE_CANDIDATE_CAP")
                self.candidates.add(candidate)
                # Computing a key binds the autonomously selected legal input;
                # it neither searches a cache nor suggests a candidate.
                inputs = host.bind_inputs(design)
                key = host.exact_cache_key(design)
                p.save(output / "input.json", inputs)
                if key in self.cache:
                    previous = Path(self.cache[key])
                    prior = e3lc.read(previous / "public-result.json")
                    if previous == Path(e3lc.read(REGISTRY)["initial_raw_path"]).parent:
                        if e3lc.sha(previous / "public-result.json") != self.protocol["initial_observation"]["public_result_sha256"]:
                            raise ValueError("LC_INITIAL_CACHE_CHANGED")
                    else:
                        receipt = e3lc.read(previous / "execution-binding.json")
                        if receipt["exact_key"] != key or receipt["public_result_sha256"] != e3lc.sha(previous / "public-result.json"):
                            raise ValueError("LC_EXACT_CACHE_CHANGED")
                    if (prior["design"] != design or prior["task_sha256"] != identity(public_task["Task"])
                            or prior["sources"] != {Path(k).name: v for k, v in self.protocol["scientific_source"].items()}):
                        raise ValueError("LC_EXACT_CACHE_BINDING_MISMATCH")
                    public = deepcopy(prior)
                    public["problem"] = deepcopy(problem)
                    public["usage"] = {"paid_model_requests": 0, "numerical_inputs": 0, "reused": True, "wall_s": 0}
                    p.save(output / "reused.json", {"source": str(previous), "exact_key": key,
                        "candidate_evaluation_charged": True})
                else:
                    if self.numerical >= 6:
                        raise ValueError("EPISODE_NUMERICAL_CAP")
                    # Retain an attempted dispatch even when consumer/evaluator
                    # fails. A failure never becomes a free retry.
                    self.numerical += 1
                    p.save(output / "dispatch.json", {"exact_key": key, "new_input_ordinal": self.numerical,
                        "consumer_input_sha256": identity(inputs), "started_at": e3lc.now()})
                    started = time.monotonic()
                    raw = consumer.simulate(inputs)
                    p.save(output / "raw.json", raw)
                    _verify_bindings(self.protocol)
                    assessment = host.evaluate(inputs, raw)
                    p.save(output / "assessment.json", assessment)
                    _verify_bindings(self.protocol)
                    public = host.public_result(design, inputs, raw, assessment,
                        problem=problem, wall_s=time.monotonic() - started)
                p.save(output / "public-result.json", public)
                p.save(output / "execution-binding.json", {"exact_key": key,
                    "consumer_input_sha256": identity(inputs), "public_result_sha256": e3lc.sha(output / "public-result.json")})
                # Reuse points to the one original complete artifact, avoiding
                # repeated full public-result copies inside a reuse chain.
                if not public["usage"].get("reused"):
                    self.cache[key] = output
                self.design, self.problem, self.last_full = design, problem, public
            compact = compact_result(public, target if detail else "")
            p.save(output / "public-compact.json", compact)
            self.actions.append({"number": self.tools, "operation": op, "selected_id": decision.get("selected_id"),
                "target": target, "candidate_evaluation": evaluation, "actual_input": actual,
                "path": str(output), "public_check": compact["public_check"], "usage": compact["usage"]})
            return compact
        except Exception as exc:
            self.fatal = "TOOL_ERROR"
            p.save(output / "error.json", {"type": type(exc).__name__, "message": str(exc),
                "attempted_new_inputs": self.numerical, "no_retry": True})
            raise


def freeze():
    if PROTOCOL.exists():
        raise ValueError("LC_ALREADY_FROZEN")
    door = e3lc.read(e3lc.PROTOCOL)
    host, view = support()
    public, registry = host.load_public(), e3lc.read(REGISTRY)
    if registry["package"] != PACKAGE or registry["allowed_for_learning"] is not False:
        raise ValueError("LC_CURRENT_REGISTRY_REQUIRED")
    freeze_path = PRIVATE / "freeze.json"
    frozen = e3lc.read(freeze_path)
    current = {"registry": e3lc.binding(REGISTRY), "freeze": e3lc.binding(freeze_path),
        "public": e3lc.binding(registry["public_task_path"]), "host_Task": e3lc.binding(registry["host_task_path"]),
        "erratum": e3lc.binding(SUPPORT / "LC-PUBLIC-METADATA-ERRATUM.json"),
        "door_protocol": e3lc.binding(e3lc.PROTOCOL)}
    for name in ("input", "raw", "assessment", "public_result"):
        path = registry["initial_" + name + "_path"]
        expected = registry["initial_" + name + ("_sha256" if name == "public_result" else "_file_sha256")]
        if e3lc.sha(path) != expected:
            raise ValueError("LC_NEW_INITIAL_ARTIFACT_CHANGED")
        current["initial_" + name] = e3lc.binding(path)
    paths = [SRC / name for name in ("e3lc_lc.py", "e3lc.py", "pilot.py", "episode_methods.py",
        "methods.py", "public_projection.py", "executor.py")]
    paths += [SUPPORT / name for name in ("common.py", "lc_host.py", "lc_public_view.py")]
    paths += [Path(registry["evaluator_path"]), e3lc.APP / "tests/test_pqe_e3lc_lc.py",
        e3lc.APP / "scripts/pqe_e3lc.py", e3lc.APP / "scripts/pqe_pi_callback.mjs", Path(door["sdk_entry"])]
    paths += [Path(path) for path in host.scientific_sources()]
    available = shutil.disk_usage(OUT).free
    if available < 11_000_000_000:
        raise ValueError("LC_STORAGE_HEADROOM_REQUIRED")
    protocol = {"package": PACKAGE, "pathway": "current-LC-default-H0", "frozen_at": e3lc.now(),
        "allowed_for_learning": False, "limits_per_episode": LIMITS, "max_candidate_evaluations": 6,
        "contract_correction_limit": 2, "model_identity": p.MODEL_IDENTITY,
        "same_backend": deepcopy(door["same_backend"]), "sdk_entry": door["sdk_entry"],
        "scientific_source": host.scientific_sources(), "source_bindings": {str(path): e3lc.sha(path) for path in paths},
        "current_bindings": current, "task_identity": {
            "original_public_Task_sha256": identity(public["Task"]),
            "prose_view_Task_sha256": identity(view.participant_task(public)),
            "driver_Task_sha256": identity(participant_task(public)),
            "host_Task_sha256": frozen["host_task_sha256"],
            "consumer_contract_task_id": frozen["consumer_contract_task_id"], "instance_id": public["Task"]["task_id"]},
        "initial_observation": {"public_result_path": registry["initial_public_result_path"],
            "public_result_sha256": registry["initial_public_result_sha256"], "actual_initial_numerical_inputs": 1},
        "cell": ["lcpv-h0", public["Task"]["task_id"], "strong_generic"],
        "driver": {"condition": "strong_generic", "program": None, "generated_H": False},
        "storage": {"available_before_bytes": available, "estimated_peak_additional_bytes": 1_000_000_000,
            "episode_retained_cap_bytes": 120_000_000, "package_retained_cap_bytes": 250_000_000,
            "output_directory": str(OUT), "new_backups": False},
        "no_retry": "One claimed H0 episode; six evaluated candidates including exact cache reuse; failed calls and missing usage stop, no replacement.",
        "claim_boundary": "One new LC development episode in the unchanged constructed one-second world; not learning, unseen transfer, physical calibration, native or hardware acceptance."}
    initial_observation(protocol, public["Task"]["task_id"], task_resolver=resolve(protocol))
    p.save(PROTOCOL, protocol)
    return {"protocol": e3lc.binding(PROTOCOL), "task_identity": protocol["task_identity"],
        "episodes": 1, "scientific_inputs_dispatched": 0, "provider_requests": 0}


def configure(protocol):
    _verify_bindings(protocol)
    p.OUT, p.PACKAGE, p.LIMITS = OUT, PACKAGE, dict(LIMITS)
    p.SDK = Path(protocol["sdk_entry"])
    p.CELLS = [tuple(protocol["cell"])]
    p.CONTRACT_CORRECTIONS = 2
    p.TOTAL_CAPS = {"requests": 108, "tool_calls": 216, "numerical_inputs": 79,
        "usd": 36, "retained_bytes": 250_000_000}


def run():
    protocol = e3lc.read(PROTOCOL)
    configure(protocol)
    claim, lock = OUT / "s0/lc-run-claim.json", OUT / "s0/active.lock"
    with claim.open("x") as stream:
        json.dump({"at": e3lc.now(), "pid": os.getpid(), "protocol_sha256": e3lc.sha(PROTOCOL)}, stream)
    registry = e3lc.read(REGISTRY)
    cache = {registry["initial_exact_cache_key"]: Path(registry["initial_raw_path"]).parent}
    rows, error, locked = [], None, False
    try:
        with lock.open("x") as stream:
            stream.write(str(os.getpid()))
        locked = True
        with e3lc.runtime_scope("lc"):
            rows.append(p.run_cell(tuple(protocol["cell"]), protocol, cache,
                task_resolver=resolve(protocol), driver_factory=EpisodeDriver,
                episode_factory=LCEpisode, initial_state_factory=initial_state,
                initial_observation_factory=initial_observation))
    except BaseException as exc:
        error = type(exc).__name__ + ":" + str(exc)
        raise
    finally:
        if locked:
            lock.unlink()
        result = {"status": "FINITE_LC_COMPLETE" if rows and not error and not e3lc.dependency_stop(rows[0]) else "FINITE_LC_STOPPED",
            "episodes": rows, "outer_error": error, "completed_at": e3lc.now(),
            "not_run": [] if rows else [protocol["cell"]], "allowed_for_learning": False,
            "attempted_new_scientific_inputs": sum(r["actual_new_numerical_inputs"] for r in rows),
            "completed_new_scientific_inputs": sum(a.get("usage", {}).get("numerical_inputs", 0) for r in rows for a in r["actions"]),
            "evaluated_candidates_including_cache": sum(a.get("candidate_evaluation", False) for r in rows for a in r["actions"]),
            "native_calls": 0, "hardware_runs": 0}
        p.save(OUT / "s0/lc-batch-result.json", result)
    return result
