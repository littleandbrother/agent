"""Cheap public DOOR facts shared by every comparison condition.

No simulation, evaluation, provider, file access, candidate ranking or action
recommendation. A necessary-condition PASS is not coupled-model validity.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .door_model import DEFAULT_MECHANISM, DOMAIN, MODEL_ID, source_step
from .methods import common_contract_check

SCHEMA = "pqe-decision-facts-v1"


def _number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _check(name, status, value, bound, source, conditions=(), necessary=True):
    return dict(name=name, status=status, necessary=necessary, value=value,
                bound=bound, source=source, conditions=list(conditions))


def _relation(name, value, source, conditions=(), status="KNOWN"):
    return dict(name=name, status=status, value=value, source=source,
                conditions=list(conditions))


def _motion_bound(task):
    """Analytic maximum of |sin(2 theta) omega| on linear public segments."""
    motion = task.get("motion")
    if not isinstance(motion, list):
        return None
    maximum = 0.0
    for seg in motion:
        if not isinstance(seg, dict):
            return None
        values = [seg.get(k) for k in ("start_s", "end_s", "start_deg", "end_deg")]
        if not all(_number(x) for x in values):
            return None
        start, end, a, b = values
        if end <= start or not 0 <= a <= 90 or not 0 <= b <= 90:
            return None
        sine = max(abs(math.sin(2 * math.radians(a))),
                   abs(math.sin(2 * math.radians(b))))
        if min(a, b) <= 45 <= max(a, b):
            sine = 1.0
        maximum = max(maximum, sine * abs(math.radians((b - a) / (end - start))))
    return maximum


def _temporal_relation(task, design):
    sensor, motion = task.get("sensor", {}), task.get("motion")
    offsets = sensor.get("bounce_offsets_s")
    opened, closed = sensor.get("open_deg"), sensor.get("closed_deg")
    if (not isinstance(offsets, list) or not offsets or
            not all(_number(v) and v >= 0 for v in offsets) or
            not _number(opened) or not _number(closed) or
            not 0 <= closed < opened <= 90 or _motion_bound(task) is None):
        return _relation("debounce_public_window", None, "Task.sensor/Task.motion",
                         ["Public sensor and complete linear motion required."], "UNKNOWN")
    crossings = []
    for seg in motion:
        a, b = seg["start_deg"], seg["end_deg"]
        threshold = opened if b > a else closed
        if (a < threshold <= b) or (b <= threshold < a):
            crossings.append(seg["start_s"] + (threshold - a) / (b - a)
                             * (seg["end_s"] - seg["start_s"]))
    crossings.sort()
    gap = min((b - a for a, b in zip(crossings, crossings[1:])), default=None)
    burst = max(offsets) - min(offsets)
    debounce = design.get("debounce_s")
    return _relation("debounce_public_window", {
        "bounce_burst_s": burst, "minimum_threshold_crossing_gap_s": gap,
        "candidate_debounce_s": debounce,
        "exceeds_burst": debounce > burst if _number(debounce) else None,
        "ends_before_next_burst": (debounce + max(offsets) < gap
                                    if _number(debounce) and gap is not None else None),
    }, "Task.sensor/Task.motion; door_program.DoorProgram.begin_step", [
        "Threshold crossings are derived from prescribed linear motion, not hidden service labels.",
        "Window comparisons assume powered observation; resets/BOOT/SAVE/TX can delay or lose capture.",
        "These comparisons do not establish service success or uniquely identify a failure cause.",
    ])


def candidate_facts(state, actual_input):
    """Return JSON facts for one existing-consumer action without executing it.

    Top-level design/problem patches replace values, exactly as in adapter;
    a mechanism mapping replaces the prior mapping, then model defaults fill
    omitted mechanism fields. The permission check has no episode quota role.
    """
    out = {"schema": SCHEMA, "domain_checks": [], "relations": [],
           "unknowns": ["coupled_startup", "activity_completion", "received_events",
                        "full_service_feasibility", "dynamic_rating_validity"],
           "sources": ["methods.common_contract_check", "door_model.source_step",
                       "engineering.build_engineering_model", "door_program.DoorProgram"],
           "claim_boundary": "Public necessary conditions and conditional algebra only."}
    checks, relations = out["domain_checks"], out["relations"]
    if not isinstance(state, dict) or not isinstance(state.get("task"), dict):
        checks.append(_check("action_contract", "UNKNOWN", None, None,
                             "methods.common_contract_check", ["Complete public state required."]))
        return out
    try:
        common_contract_check(state, actual_input, {"remaining_actions": 1})
    except (ValueError, TypeError, KeyError) as exc:
        checks.append(_check("action_contract", "FAIL", str(exc), "permitted action",
                             "methods.common_contract_check"))
        return out
    checks.append(_check("action_contract", "PASS", "permitted by common check",
                         "adapter remains authoritative", "methods.common_contract_check",
                         ["No resource/dispatch authorization is inferred."]))
    task = state["task"]
    evaluates_design = actual_input["operation"] not in {"observe", "select", "report"}
    design = {**deepcopy(state.get("design", {})),
              **deepcopy(actual_input.get("design_patch", {}))}
    required = ("capacitance_f", "startup_v", "brownout_v", "esr_ohm", "mechanism")
    if (not all(_number(design.get(k)) for k in required[:-1]) or
            not isinstance(design.get("mechanism"), dict) or design["capacitance_f"] <= 0):
        checks.append(_check("public_design_values", "UNKNOWN", None, None,
                             "Task.design_domain", ["Complete numeric public design required."]))
        return out
    components = task.get("components", {})
    start, brown, cap = design["startup_v"], design["brownout_v"], design["capacitance_f"]
    max_v = components.get("max_v")
    ordered = brown < start <= max_v if _number(max_v) else None
    checks.append(_check("power_threshold_order", "UNKNOWN" if ordered is None else
                         "PASS" if ordered else "FAIL", {"brownout_v": brown, "startup_v": start},
                         {"brownout_lt_startup_le_max_v": max_v}, "adapter.validate_design"))
    # Restrict source algebra to the declared public consumer; no Task-ID branches.
    source = task.get("public_inputs", {}).get("source_model", {})
    if source.get("kind") != "constructed continuous cam and reciprocal electromagnetic generator":
        checks.append(_check("door_geometry", "UNKNOWN", None, None, "door_model.source_step",
                             ["Declared existing DOOR source model required."]))
        return out
    m = {**DEFAULT_MECHANISM, **design["mechanism"]}
    static = source_step(0.0, 0.0, 0.0, m)  # zero-motion algebra, no integration
    geometry = static.get("geometry")
    if geometry is None:
        checks.append(_check("source_parameters", "FAIL", static.get("domain_errors"),
                             "frozen model coefficient domain", "door_model.source_step",
                             necessary=evaluates_design))
        return out
    for name, value, bound, tolerance in (
        ("cam_diameter_m", geometry["cam_diameter_m"], DOMAIN["envelope_width_m"], 1e-12),
        ("generator_travel_length_m", geometry["generator_travel_envelope_m"][0], DOMAIN["envelope_length_m"], 1e-12),
        ("assembly_depth_m", geometry["assembly_depth_m"], DOMAIN["envelope_depth_m"], 1e-12),
        ("maximum_pressure_angle_deg", geometry["maximum_pressure_angle_deg"], DOMAIN["maximum_pressure_angle_deg"], 0.0),
    ):
        checks.append(_check(name, "PASS" if value <= bound + tolerance else "FAIL",
                             value, {"maximum": bound, "comparison_tolerance": tolerance},
                             "door_model.source_step/DOMAIN",
                             [MODEL_ID, "Condition of an evaluated design, not a restriction on cached observation."],
                             necessary=evaluates_design))
    relations.append(_relation("capacitor_threshold_storage", {
        "startup_charge_c": cap * start, "startup_energy_j": 0.5 * cap * start * start,
        "energy_startup_to_brownout_j": 0.5 * cap * (start * start - brown * brown),
    }, "engineering: Cstore and supervisor thresholds", [
        "Ideal capacitor algebra; neither available harvested energy nor activity sufficiency is inferred."]))
    relations.append(_relation("source_bus_feedback", {
        "current_a": "max((abs(K*stroke*sin(2*theta)*omega)-Vbus-Vrect)/Rcoil,0)",
        "harvested_charge_invariant_across_capacitance": False,
        "cam_base_radius_enters_electrical_emf": False,
    }, "door_model.source_step", [
        "Prescribed motion and fixed source coefficients; base radius still affects geometry and pressure angle.",
        "Changing C changes Vbus(t), source current, bus power and integrated charge; no fixed-Q extrapolation."]))
    peak = _motion_bound(task)
    initial_v = task.get("initial", {}).get("capacitor_v")
    if peak is not None and _number(initial_v) and initial_v >= 0:
        emf = m["generator_constant_vs_per_m"] * m["stroke_m"] * peak
        ceiling = max(initial_v, max(0.0, emf - m["rectifier_drop_v"]))
        relations.append(_relation("passive_source_voltage_upper_bound", {
            "maximum_emf_v": emf, "capacitor_voltage_upper_bound_v": ceiling,
        }, "Task.motion/initial; door_model.source_step", [
            "Piecewise linear prescribed motion, passive blocking bridge, nonnegative loads/leakage, no other energy source.",
            "Upper bound only; capacitance, source impedance and finite motion may prevent reaching it."]))
        checks.append(_check("startup_below_passive_upper_bound", "PASS" if start <= ceiling + 1e-12 else "FAIL",
                             start, {"maximum": ceiling}, "door_model.source_step; Task.motion/initial",
                             ["Same passive-source assumptions as voltage upper bound; PASS is not reachable startup."],
                             necessary=evaluates_design))
    else:
        relations.append(_relation("passive_source_voltage_upper_bound", None,
                                   "Task.motion/initial", ["Complete motion and initial capacitor voltage required."], "UNKNOWN"))
    loads = {}
    for phase, stem in (("boot", "boot"), ("save_ack_each", "write"), ("tx", "tx")):
        current, duration = components.get(stem + "_a"), components.get(stem + "_s")
        if _number(current) and _number(duration):
            loads[phase] = {"current_a": current, "duration_s": duration,
                            "charge_c_if_completed": current * duration,
                            "load_branch_drop_v": current * design["esr_ohm"]}
    relations.append(_relation("load_branch_and_phase_charge", loads or None,
                               "Task.components; engineering: Rbranch; door_program", [
        "esr_ohm is load-branch resistance only, not full net capacitor-current ESR.",
        "Phase energy and completion depend on coupled Vbus(t); SAVE and ACK each incur write cost.",
    ], "KNOWN" if loads else "UNKNOWN"))
    relations.append(_temporal_relation(task, design))
    return out
