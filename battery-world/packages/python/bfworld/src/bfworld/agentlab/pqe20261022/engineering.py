"""One connected model representation consumed by the door solver and exports."""
from copy import deepcopy
import hashlib
import json
import math

from .door_model import DEFAULT_MECHANISM, DOMAIN
from .door_program import PROGRAM_VERSION

MODEL_VERSION = "pqe-door-engineering-model-v2"
NODES = ["0", "emf", "rect_in", "bus", "vdd"]
TOPOLOGY = {
    "G1": ("kinematic_emf", ["emf", "0"]),
    "Rcoil": ("resistor", ["emf", "rect_in"]),
    "BR1": ("constant_drop_blocking_rectifier", ["rect_in", "bus", "0"]),
    "Cstore": ("capacitor", ["bus", "0"]),
    "Rleak": ("resistor", ["bus", "0"]),
    "CLAMP": ("ideal_voltage_limit", ["bus", "0"]),
    "Rbranch": ("load_branch_series_resistor", ["bus", "vdd"]),
    "PROGRAM": ("state_dependent_current_load", ["vdd", "0"]),
    "SUPERVISOR": ("voltage_observer", ["bus", "vdd", "0"]),
}


def model_identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def build_engineering_model(task, design):
    m = {**DEFAULT_MECHANISM, **design["mechanism"]}
    comp = deepcopy(task["components"])
    values = {
        "G1": {"generator_constant_vs_per_m": m["generator_constant_vs_per_m"]},
        "Rcoil": {"resistance_ohm": m["coil_resistance_ohm"]},
        "BR1": {"drop_v": m["rectifier_drop_v"]},
        "Cstore": {"capacitance_f": design["capacitance_f"]},
        "Rleak": {"resistance_ohm": comp["leakage_ohm"]},
        "CLAMP": {"maximum_v": comp["max_v"]},
        "Rbranch": {"resistance_ohm": design["esr_ohm"]},
        "PROGRAM": {"version": PROGRAM_VERSION,
                    "loads": {k: comp[k] for k in ("boot_a", "boot_s", "write_a", "write_s", "tx_a", "tx_s", "idle_a")},
                    "parameters": {k: design[k] for k in ("debounce_s", "persistent_queue", "retry_s")}},
        "SUPERVISOR": {k: design[k] for k in ("startup_v", "brownout_v", "tx_gate_v")},
    }
    return {"schema_version": MODEL_VERSION, "task_sha256": model_identity(task),
            "design_sha256": model_identity(design), "nodes": list(NODES),
            "elements": [{"id": key, "kind": kind, "nodes": nodes, "parameters": values[key]}
                         for key, (kind, nodes) in TOPOLOGY.items()],
            "mechanical": {k: m[k] for k in ("stroke_m", "cam_base_radius_m", "follower_coulomb_n", "follower_viscous_n_s_per_m")},
            "domain": deepcopy(DOMAIN), "load_provenance": comp.get("provenance"),
            "scope": "Constructed reciprocal cam/generator and blocking rectifier. Rbranch is load-branch resistance, not a full capacitor ESR network. Fixed motion, no inductance/inertia/native solver or calibrated chip."}


def consume_engineering_model(model, task=None, design=None):
    """Validate connected topology, then extract the actual numerical inputs.

    Explicit exports may be consumed directly. The action adapter additionally
    binds them to its Task/Design, preventing a hidden parameter override.
    """
    if model.get("schema_version") != MODEL_VERSION or model.get("nodes") != NODES:
        raise ValueError("ENGINEERING_MODEL_VERSION_OR_NODES")
    elements = model.get("elements", [])
    if len(elements) != len(TOPOLOGY) or len({e["id"] for e in elements}) != len(elements):
        raise ValueError("ENGINEERING_ELEMENT_IDENTITY")
    by_id = {e["id"]: e for e in elements}
    if set(by_id) != set(TOPOLOGY):
        raise ValueError("ENGINEERING_MISSING_CONNECTION")
    for key, (kind, nodes) in TOPOLOGY.items():
        if by_id[key]["kind"] != kind or by_id[key]["nodes"] != nodes:
            raise ValueError("ENGINEERING_TOPOLOGY:" + key)
    if (task is None) != (design is None):
        raise ValueError("BOTH_TASK_AND_DESIGN_REQUIRED")
    if task is not None and model != build_engineering_model(task, design):
        raise ValueError("ENGINEERING_TASK_DESIGN_BINDING")
    p = {key: e["parameters"] for key, e in by_id.items()}
    if p["PROGRAM"]["version"] != PROGRAM_VERSION:
        raise ValueError("PROGRAM_VERSION_MISMATCH")
    mechanism = {**model["mechanical"],
                 "generator_constant_vs_per_m": p["G1"]["generator_constant_vs_per_m"],
                 "coil_resistance_ohm": p["Rcoil"]["resistance_ohm"],
                 "rectifier_drop_v": p["BR1"]["drop_v"]}
    resolved_design = {"capacitance_f": p["Cstore"]["capacitance_f"],
                       "esr_ohm": p["Rbranch"]["resistance_ohm"],
                       **p["SUPERVISOR"], **p["PROGRAM"]["parameters"],
                       "mechanism": mechanism}
    components = {"max_v": p["CLAMP"]["maximum_v"],
                  "leakage_ohm": p["Rleak"]["resistance_ohm"],
                  **p["PROGRAM"]["loads"], "provenance": model.get("load_provenance")}
    for key, value in {**mechanism, **components, **resolved_design}.items():
        if key in {"mechanism", "provenance", "persistent_queue"}:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("ENGINEERING_NONPHYSICAL_PARAMETER:" + key)
    if (resolved_design["capacitance_f"] <= 0 or components["leakage_ohm"] <= 0
            or mechanism["coil_resistance_ohm"] <= 0
            or type(resolved_design["persistent_queue"]) is not bool
            or not 0 < resolved_design["brownout_v"] < resolved_design["startup_v"] <= components["max_v"]):
        raise ValueError("ENGINEERING_POWER_OR_STORAGE_DOMAIN")
    return {"design": resolved_design, "components": components, "mechanism": mechanism,
            "model_sha256": model_identity(model), "program_version": PROGRAM_VERSION}
