"""Necessary outer bounds only; no loaded trace reuse or feasibility oracle.

Calling this function is a separately counted cheap numeric check. It is not
called by imports, describe_contract, design_facts or offline logic checks.
"""
from copy import deepcopy
from fractions import Fraction
import math

from ..pqe20261022.door_model import DEFAULT_MECHANISM
from ..pqe20261022.executor import identity
from .task import validate_design

VERSION = "codebt-necessary-bounds-v1"


def describe_bounds():
    return {"version": VERSION, "status": "UNEVALUATED",
        "source_equation": "P_bus=V*max((abs(K*L*sin(2theta)*omega)-V-D)/R,0)",
        "source_upper_equation": "P_bus <= max(K*L_max*abs(delta_deg)/(45*T)-D,0)^2/(4*R)",
        "proof": "sin magnitude <=1 and pi<4; maximize V*(E-D-V)/R over every V>=0. Fraction arithmetic retains exact input floats. Dropping all loads/losses enlarges available energy.",
        "necessary_startup": ".5*C*startup_min^2 <= E_initial_upper + sum(segment_duration*P_upper)",
        "necessary_tx_terminal": "ESR <= (V_clamp-brownout_min)/I_tx",
        "scope": "Declared continuous source with original fixed K/R/D; full authorized stroke interval and every bus/load trajectory, including added holder loads. At least one required powered delivery and no initial chemical energy. Numerical-kernel error qualification is separate.",
        "unknown": ["actual loaded source energy", "retention voltage coverage", "complete service", "feasibility inside outer intervals"],
        "source_refs": ["pqe20261022.door_model:source_step", "pqe20261024debt.consumer:_midpoint_step",
                        "pqe20261024debt.task:DESIGN_DOMAIN"]}


def necessary_bounds(design, task=None):
    """Return scoped parameter outer intervals; no search or scientific solve."""
    if task is None:
        return {"schema": "codebt-necessary-bounds-v1", "status": "UNKNOWN",
                "reason": "A frozen task/domain is required", "certificate": None,
                "equations": describe_bounds()}
    validate_design(task, design)
    base = {"schema": "codebt-necessary-bounds-v1", "version": VERSION,
            "task_sha256": identity(task), "design_sha256": identity(design),
            "equations": describe_bounds(), "full_service": "UNKNOWN",
            "source_trace_used": False}
    if (not task.get("required_delivery_present") or task["initial"].get("mechanical_stored_j", 0.) != 0
            or task["initial"].get("battery_or_chemical_store_j", 0.) != 0):
        return {**base, "status": "UNKNOWN", "reason": "Necessary-delivery/no-other-store assumptions not established",
                "certificate": None}
    domain = task["design_domain"]
    stroke_max = Fraction(domain["mechanism"]["editable"]["stroke_m"][1])
    k, resistance, diode = (Fraction(DEFAULT_MECHANISM[x]) for x in
        ("generator_constant_vs_per_m", "coil_resistance_ohm", "rectifier_drop_v"))
    upper = Fraction(0)
    for segment in task["motion"]:
        duration = Fraction(segment["end_s"])-Fraction(segment["start_s"])
        if duration <= 0:
            raise ValueError("BOUND_MOTION_DURATION")
        omega = abs(Fraction(segment["end_deg"])-Fraction(segment["start_deg"]))/duration/45
        upper += duration*max(k*stroke_max*omega-diode, 0.)**2/(4*resistance)
    c_min, c_max = (Fraction(domain["capacitance_f"][key]) for key in ("min", "max"))
    initial_upper = c_max*Fraction(task["initial"]["capacitor_v"])**2/2
    c_upper = 2*(upper+initial_upper)/Fraction(domain["startup_v"]["min"])**2
    r_upper = (Fraction(task["components"]["max_v"])-Fraction(domain["brownout_v"]["min"]))/Fraction(task["components"]["tx_a"])
    exact = {"capacitance_f": [c_min, min(c_max, c_upper)],
             "esr_ohm": [Fraction(domain["esr_ohm"]["min"]), min(Fraction(domain["esr_ohm"]["max"]), r_upper)]}
    intervals = {key: [math.nextafter(float(lo), -math.inf), math.nextafter(float(hi), math.inf)] for key, (lo, hi) in exact.items()}
    empty = [name for name, (lo, hi) in exact.items() if lo > hi]
    scope = {"family_id": task.get("family_id"), "condition_id": task.get("condition_id"),
             "mode": {key: design[key] for key in ("holding_component", "read_source", "clear_after", "persistent_queue", "firmware_policy")},
             "covered_variable_domain": deepcopy(domain), "service": deepcopy(task["service"]),
             "assumptions": describe_bounds()["scope"], "source_upper_covers_all_loads": True}
    certificate = None
    if empty:
        certificate = {"kind": "EMPTY_NECESSARY_OUTER_INTERVAL", "excluded_fields": empty,
                       "scope": scope, "exact_intervals": {k: [str(x) for x in v] for k, v in exact.items()},
                       "equation_refs": describe_bounds()["source_refs"],
                       "numerical_kernel_applicability": "UNKNOWN; do not promote as an implemented-solver certificate without error qualification"}
    excluded_point = [key for key, (lo, hi) in exact.items() if not lo <= Fraction(design[key]) <= hi]
    return {**base, "status": "ANALYTIC_SUBDOMAIN_EXCLUDED" if certificate else "NECESSARY_ONLY",
            "scope": scope, "source_energy_upper_j": math.nextafter(float(upper), math.inf),
            "initial_energy_upper_j": math.nextafter(float(initial_upper), math.inf),
            "exact_source_energy_upper": str(upper),
            "necessary_outer_intervals": intervals, "point_outside_outer_intervals": excluded_point,
            "analytic_certificate": certificate, "certificate": None,
            "numerical_certificate_status": "UNKNOWN_UNQUALIFIED_KERNEL_ERROR",
            "limitation": "A nonempty interval is not evidence of feasibility. Missing voltage/identity/service facts remain UNKNOWN."}
