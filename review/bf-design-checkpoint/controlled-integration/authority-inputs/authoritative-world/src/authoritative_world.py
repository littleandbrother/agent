"""Versioned computational contracts; never a physical qualification authority.

All identities are SHA256 of sorted, compact, UTF-8 JSON with nonfinite values
forbidden. World, participant design, model, solver, task and program identities
remain distinct. A frozen specification may still contain documented unknowns.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "bf-authoritative-development-world-v1"


class ContractError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text())


def write_json(path: Path | str, value: Any) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   indent=2, allow_nan=False) + "\n")


def finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ContractError("NONFINITE_OR_NONNUMERIC:" + label)
    return float(value)


def validate_world(world: dict) -> dict:
    import jsonschema
    try:
        canonical(world)
        jsonschema.Draft202012Validator(read_json(ROOT / "contracts/world.schema.json")).validate(world)
    except (ValueError, TypeError, jsonschema.ValidationError) as exc:
        raise ContractError("WORLD_SCHEMA:" + str(exc)) from exc
    if world["qualification"]["physical_qualified"] or world["qualification"]["formal_trial_admitted"]:
        raise ContractError("SPECIFICATION_IS_NOT_QUALIFICATION")
    for item in world["unresolved_facts"]:
        if item["status"] != "unknown" or item["value"] is not None:
            raise ContractError("UNKNOWN_FACT_OVERWRITTEN:" + item["id"])
    return world


def load_world(path: Path | str | None = None) -> dict:
    return validate_world(read_json(path or ROOT / "contracts/world-v1.json"))


def world_id(world: dict) -> str:
    validate_world(world)
    return digest(world)


def task_id(task: dict) -> str:
    # Qualification/evidence can attest to an unchanged task, never rewrite it.
    return digest({k: v for k, v in task.items()
                   if k not in ("reference_witness", "qualification", "status")})


def geometry_at(world: dict, gap_m: float, time_s: float, q_m: float = 0.) -> dict:
    validate_world(world)
    gap = finite(gap_m, "gap_m")
    time = finite(time_s, "time_s")
    q = finite(q_m, "q_m")
    geometry, excitation = world["geometry"], world["input"]
    if not geometry["parameter_support_gap_m"][0] <= gap <= geometry["parameter_support_gap_m"][1]:
        raise ContractError("GAP_OUTSIDE_IMPLEMENTED_PARAMETER_SUPPORT")
    if not 0 <= time <= excitation["observation_s"]:
        raise ContractError("TIME_OUTSIDE_WORLD")
    if abs(q) > geometry["rom_absolute_deflection_limit_m"]:
        raise ContractError("ROM_OUT_OF_DOMAIN")
    angle = excitation["opening_angle_rad"] * min(time / excitation["opening_s"], 1.)
    c, s = math.cos(angle), math.sin(angle)
    nominal_tip = geometry["nominal_tip_world_m"]
    nominal_driver = geometry["nominal_driver_world_m"]
    if geometry["family"] == "upstream-moving-driver":
        driver_x, tip_x = nominal_tip[0] - gap, nominal_tip[0]
    else:
        driver_x, tip_x = nominal_driver[0], nominal_driver[0] + gap
    driver = [driver_x * c - nominal_driver[1] * s, driver_x * s + nominal_driver[1] * c, nominal_driver[2]]
    tip = [tip_x, nominal_tip[1] + q, nominal_tip[2]]
    return {"angle_rad": angle, "driver_world_m": driver, "tip_world_m": tip,
            "force_separation_m": [tip[0] - driver[0], driver[2] - tip[2], driver[1] - tip[1]],
            "scope": "declared_computational_coordinates_not_measured_installation"}


def verify_sources(registry: dict | None = None, root: Path = ROOT,
                   check_originals: bool = False) -> list[str]:
    registry = registry or read_json(root / "contracts/source-registry.json")
    errors = []
    if not registry.get("sources"):
        return ["EMPTY_SOURCE_REGISTRY"]
    for name, source in registry["sources"].items():
        relative = Path(source["snapshot_path"])
        path = root / relative
        if relative.is_absolute() or ".." in relative.parts or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            errors.append("SOURCE_PATH_DENIED:" + name)
            continue
        if not path.is_file():
            errors.append("SOURCE_MISSING:" + name)
        elif path.stat().st_size != source["bytes"] or file_hash(path) != source["sha256"]:
            errors.append("SOURCE_HASH_MISMATCH:" + name)
        if check_originals:
            original = Path(source["original_path"])
            if not original.is_file() or file_hash(original) != source["sha256"]:
                errors.append("ORIGINAL_SOURCE_CHANGED_OR_MISSING:" + name)
    return errors


def source_identity(registry: dict) -> dict:
    # Relocating a snapshot never changes the source identity.
    return {k: {"sha256": v["sha256"], "bytes": v["bytes"], "role": v["role"]}
            for k, v in registry["sources"].items()}


def scientific_design(design: dict) -> dict:
    if not isinstance(design, dict):
        raise ContractError("DESIGN_MUST_BE_OBJECT")
    canonical(design)
    return {k: v for k, v in design.items() if k != "presentation"}


def make_run_identity(world: dict, design: dict, task: dict, model: dict,
                      solver: dict, sources: dict, *, input_control: str = "prescribed",
                      initial_state: dict | None = None, checkpoint_sha256: str | None = None) -> dict:
    wid = world_id(world)
    if world["geometry"]["family"] != "upstream-moving-driver":
        raise ContractError("LEGACY_WORLD_REQUIRES_ITS_OWN_EXECUTION_ADAPTER")
    if task.get("world_id") != wid:
        raise ContractError("TASK_WORLD_MISMATCH")
    if task.get("world", {}).get("world_id") != wid or task["world"].get("input_id") != digest(world["input"]):
        raise ContractError("TASK_INPUT_CONTRACT_MISMATCH")
    mechanical, circuit = design.get("mechanical", {}), design.get("circuit", {})
    if mechanical.get("opening_s", 2.) != world["input"]["opening_s"] or mechanical.get("angle_deg", 65.) != 65.:
        raise ContractError("DESIGN_CHANGED_FROZEN_EXCITATION")
    if circuit.get("initial_vin_V", 0.) != 0. or circuit.get("diagnostic_input_A", 0.) != 0.:
        raise ContractError("DIAGNOSTIC_ENERGY_OUTSIDE_CANONICAL_TASK")
    required = ("model_version", "applicability", "physical_qualified", "source_hashes")
    if any(k not in model for k in required) or model["physical_qualified"] is not False:
        raise ContractError("MODEL_CONTRACT_MISSING_OR_UNSUPPORTED_QUALIFICATION")
    if not solver.get("solver_version") or not solver.get("settings") or not solver.get("tool_hashes"):
        raise ContractError("SOLVER_IDENTITY_INCOMPLETE")
    if not sources or not sources.get("upstream_program"):
        raise ContractError("SOURCE_IDENTITY_MISSING")
    for name, expected in world["source_bindings"].items():
        if name not in sources or not isinstance(sources[name], dict) or sources[name].get("sha256") != expected:
            raise ContractError("SOURCE_WORLD_MISMATCH:" + name)
    input_id = input_at(world, 0., control=input_control)["input_id"]
    if initial_state is not None:
        expected = initial_state.get("initial_state_id")
        if expected != digest({k: v for k, v in initial_state.items() if k != "initial_state_id"}):
            raise ContractError("INITIAL_STATE_ID_MISMATCH")
        # Reconstruct through the declared binder, preserving unresolved values.
        rebound = bind_initial_state(world, q0_m=initial_state["q0_m"], stiffness_N_m=initial_state["stiffness_N_m"],
                                     force_at_q0_N=initial_state["force_at_q0_N"], force_artifact_sha256=initial_state["force_artifact_sha256"],
                                     equilibrium_tolerance_N=initial_state["equilibrium_tolerance_N"])
        if rebound != initial_state:
            raise ContractError("INITIAL_STATE_NOT_BOUND_TO_WORLD")
    result = {"schema": "bf-run-identity-v1", "world_id": wid,
              "design_id": digest(scientific_design(design)), "task_contract_id": task_id(task),
              "model_id": digest(model), "solver_id": digest(solver),
              "program_id": digest({"semantics": world["program"], "design": design.get("firmware", {}),
                                    "source": sources.get("upstream_program")}),
              "source_id": digest(sources), "experimental_unit": task["experimental_unit"]}
    result["input_id"] = input_id
    result["initial_state_id"] = initial_state["initial_state_id"] if initial_state is not None else digest(world["initial_state"])
    result["initial_state_binding"] = "realized_computational_state" if initial_state is not None else "recipe_only_not_run_evidence"
    if checkpoint_sha256 is not None and (len(checkpoint_sha256) != 64 or any(c not in "0123456789abcdef" for c in checkpoint_sha256)):
        raise ContractError("INVALID_CHECKPOINT_IDENTITY")
    result["continuation_checkpoint_id"] = checkpoint_sha256
    result["run_identity"] = digest(result)
    return result


def stage_keys(world: dict, design: dict, task: dict, model: dict, solver: dict,
               sources: dict, *, input_control: str = "prescribed",
               initial_state: dict | None = None, checkpoint_sha256: str | None = None) -> dict[str, str]:
    identity = make_run_identity(world, design, task, model, solver, sources,
                                 input_control=input_control, initial_state=initial_state, checkpoint_sha256=checkpoint_sha256)
    # Conservative full-world/model/source binding prevents stale reuse. Presentation
    # is intentionally absent. Fine-grained optimization needs a separately reviewed DAG.
    common = {"world_id": identity["world_id"], "model_id": identity["model_id"],
              "source_id": identity["source_id"], "design_id": identity["design_id"],
              "solver_id": identity["solver_id"], "input_id": identity["input_id"],
              "initial_state_id": identity["initial_state_id"], "continuation_checkpoint_id": identity["continuation_checkpoint_id"]}
    def key(stage, **dependencies):
        return digest({"cache_schema": "bf-authoritative-cache-v1", "stage": stage, **common, **dependencies})
    geometry = key("geometry", mechanical=design.get("mechanical", {}))
    force = key("force", geometry=geometry)
    program = key("program", program_id=identity["program_id"])
    power = key("power", force=force, program=program, circuit=design.get("circuit", {}), solver_id=identity["solver_id"])
    receiver = key("receiver", power=power, link=design.get("link", {}))
    acceptance = key("acceptance", receiver=receiver, task_contract_id=identity["task_contract_id"])
    return dict(geometry=geometry, force=force, program=program, power=power, receiver=receiver, acceptance=acceptance)


def validate_comparison(records: list[dict], *, formal: bool = False) -> dict:
    if len(records) < 2:
        raise ContractError("COMPARISON_NEEDS_TWO_RECORDS")
    fields = ("world_id", "task_contract_id", "model_id", "solver_id", "source_id", "input_id", "experimental_unit")
    for field in fields:
        if any(not r.get(field) for r in records) or len({r[field] for r in records}) != 1:
            raise ContractError("MIXED_OR_MISSING_COMPARISON_IDENTITY:" + field)
    if records[0]["experimental_unit"] == "same_state_continuation":
        if any(r.get("initial_state_binding") != "realized_computational_state" for r in records):
            raise ContractError("CONTINUATION_REQUIRES_REALIZED_STATE")
        for field in ("initial_state_id", "continuation_checkpoint_id"):
            if any(not r.get(field) for r in records) or len({r[field] for r in records}) != 1:
                raise ContractError("CONTINUATION_STATE_OR_CHECKPOINT_MISMATCH:" + field)
    if formal:
        raise ContractError("FORMAL_RANKING_NOT_ADMITTED_BY_DEVELOPMENT_WORLD")
    return {"comparable": True, "scope": "same_world_development_comparison_only", "formal_ranking_allowed": False}


def migrate_upstream_spec(spec: dict, source_family: str) -> dict:
    if source_family != "upstream-338d603":
        raise ContractError("EXPLICIT_UPSTREAM_FAMILY_REQUIRED_NO_LEGACY_RELABELLING")
    if verify_sources():
        raise ContractError("SOURCE_VERIFICATION_FAILED")
    # Exact pinned validator retains existing strict field/range handling.
    import importlib.util
    path = ROOT / "sources/upstream_contracts.py"
    module_spec = importlib.util.spec_from_file_location("pinned_contracts", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.validate(copy.deepcopy(spec))


def input_at(world: dict, time_s: float, *, control: str = "prescribed") -> dict:
    """Exposed control names are explicit; controls get separate execution identity."""
    validate_world(world)
    time = finite(time_s, "time_s")
    if not 0 <= time <= world["input"]["observation_s"]:
        raise ContractError("TIME_OUTSIDE_WORLD")
    if control not in ("prescribed", "no_motion"):
        raise ContractError("UNDEFINED_INPUT_CONTROL")
    angle = 0. if control == "no_motion" else world["input"]["opening_angle_rad"] * min(time / world["input"]["opening_s"], 1.)
    return {"angle_rad": angle, "external_electrical_input_A": 0.,
            "control": control, "input_id": digest({"input": world["input"], "control": control})}


def bind_initial_state(world: dict, *, q0_m: float, stiffness_N_m: float,
                       force_at_q0_N: float, force_artifact_sha256: str,
                       equilibrium_tolerance_N: float = 1e-9) -> dict:
    """Validate and bind a provider-computed equilibrium, not invent an initial state.

    This is a residual check, not root existence/uniqueness or physical preparation
    qualification. A model provider must return the actual root and artifact.
    """
    validate_world(world)
    q, stiffness, force, tol = [finite(v, label) for v, label in [
        (q0_m, "q0_m"), (stiffness_N_m, "stiffness_N_m"),
        (force_at_q0_N, "force_at_q0_N"), (equilibrium_tolerance_N, "equilibrium_tolerance_N")]]
    if abs(q) > world["geometry"]["rom_absolute_deflection_limit_m"] or stiffness <= 0 or tol <= 0:
        raise ContractError("INITIAL_STATE_OUT_OF_DOMAIN")
    if not isinstance(force_artifact_sha256, str) or len(force_artifact_sha256) != 64 or any(c not in "0123456789abcdef" for c in force_artifact_sha256):
        raise ContractError("FORCE_ARTIFACT_IDENTITY_REQUIRED")
    if abs(stiffness * q - force) > tol:
        raise ContractError("INITIAL_STATE_NOT_EQUILIBRIUM")
    state = {**world["initial_state"], "q0_m": q, "mechanical_J": .5 * stiffness * q * q,
             "stiffness_N_m": stiffness, "force_at_q0_N": force,
             "force_artifact_sha256": force_artifact_sha256, "equilibrium_tolerance_N": tol,
             "physical_preparation_qualified": False}
    return {**state, "initial_state_id": digest(state)}


def receive_completed_records(world: dict, records: list[dict]) -> list[dict]:
    """Shared decoder/grouping semantics only, not RF delivery or action attribution.

    Every supplied record must explicitly attest completed TX. This adapter does
    not invent that attestation, infer transmit completion, or qualify the sender.
    """
    validate_world(world)
    if world["geometry"]["family"] != "upstream-moving-driver":
        raise ContractError("LEGACY_WORLD_REQUIRES_ITS_OWN_EXECUTION_ADAPTER")
    if verify_sources():
        raise ContractError("SOURCE_VERIFICATION_FAILED")
    for record in records:
        if record.get("tx_completed") is not True:
            raise ContractError("RECEIVER_REQUIRES_COMPLETE_TX")
        time = finite(record.get("time_s"), "record.time_s")
        if not 0 <= time <= world["mission"]["receiver_deadline_s"]:
            raise ContractError("RECEIVER_RECORD_OUTSIDE_DEADLINE")
    namespace = {"__name__": "frozen_receiver_adapter"}
    code = (ROOT / "sources/upstream_receiver.py").read_text().replace("BFP1", "BFD2")
    exec(compile(code, "frozen_receiver_adapter", "exec"), namespace)
    return namespace["group"](records, silence_s=world["receiver"]["silence_s"])


def verify_freeze(root: Path = ROOT, *, check_originals: bool = False) -> dict:
    receipt = read_json(root / "FREEZE-RECEIPT.json")
    world = load_world(root / "contracts/world-v1.json")
    errors = verify_sources(root=root, check_originals=check_originals)
    if world_id(world) != receipt["world_id"]:
        errors.append("WORLD_ID_MISMATCH")
    for filename, expected in receipt["contract_files"].items():
        if file_hash(root / filename) != expected:
            errors.append("FROZEN_CONTRACT_CHANGED:" + filename)
    manifest = read_json(root / "FILE-MANIFEST.json")
    if file_hash(root / "FILE-MANIFEST.json") != receipt["artifact_manifest_sha256"]:
        errors.append("ARTIFACT_MANIFEST_CHANGED")
    for item in manifest["files"]:
        p = root / item["path"]
        if not p.is_file() or file_hash(p) != item["sha256"]:
            errors.append("ARTIFACT_CHANGED_OR_MISSING:" + item["path"])
    return {"verified": not errors, "errors": errors, "world_id": receipt["world_id"],
            "computational_spec_frozen": True, "physical_qualified": False,
            "formal_trial_admitted": False, "scope": "identity_integrity_only"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["verify", "identity", "geometry"])
    parser.add_argument("--originals", action="store_true")
    parser.add_argument("--gap-mm", type=float, default=48.)
    parser.add_argument("--time-s", type=float, default=0.)
    args = parser.parse_args()
    if args.action == "verify":
        result = verify_freeze(check_originals=args.originals)
    elif args.action == "identity":
        result = {"world_id": world_id(load_world())}
    else:
        result = geometry_at(load_world(), args.gap_mm / 1000, args.time_s)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 2 if result.get("verified") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
