"""Constructed, quasistatic cam/linear-generator source; not an ECO 200 fit.

SI internally; angles/speeds at the API are degrees and degrees/second.  The
prescribed door motion supplies all energy.  No spring, inertia, inductance,
precharge, or hidden source state is present.  See the Stage1 A engineering spec
for assumptions, primary sources, geometry, and domain.  Invalid results must
not qualify a design, even when finite diagnostic powers are returned.
"""
from __future__ import annotations

import math
from collections.abc import Mapping


MODEL_ID = "pqe-door-continuous-cam-em-v1"

# These are constructed-model coefficients, not manufacturer measurements.
# K_e and K_f share one SI value so electrical and mechanical ports are reciprocal.
DEFAULT_MECHANISM = {
    "stroke_m": 0.008,
    "cam_base_radius_m": 0.007,
    "generator_constant_vs_per_m": 500.0,
    "coil_resistance_ohm": 1500.0,
    "rectifier_drop_v": 0.30,
    "follower_coulomb_n": 0.05,
    "follower_viscous_n_s_per_m": 0.20,
}

# Frozen model domain, not participant-editable fields in mechanism.
DOMAIN = {
    "angle_min_deg": 0.0,
    "angle_max_deg": 90.0,
    "maximum_speed_deg_s": 120.0,
    "maximum_bus_v": 5.5,
    "maximum_emf_v": 10.0,
    "maximum_current_a": 0.006,
    "maximum_copper_loss_w": 0.060,
    "maximum_handle_force_n": 0.5,
    "maximum_pressure_angle_deg": 40.0,
    "handle_radius_m": 0.4,
    "door_width_m": 0.45,
    "door_height_m": 0.6,
    "envelope_length_m": 0.060,
    "envelope_width_m": 0.035,
    "envelope_depth_m": 0.020,
}


def _number(value):
    # JSON numbers only; booleans must not silently become physical coefficients.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _invalid(errors):
    # Structural/nonfinite errors have no physical result.  Numeric zeros keep
    # the caller's diagnostic ledger finite; valid=False is authoritative.
    return {
        "model_id": MODEL_ID, "valid": False, "domain_errors": errors,
        "current_a": 0.0, "emf_v": 0.0, "signed_emf_v": 0.0,
        "mechanical_power_w": 0.0, "bus_power_w": 0.0,
        "copper_loss_w": 0.0, "rectifier_loss_w": 0.0, "other_loss_w": 0.0,
        "handle_force_n": 0.0, "reaction_torque_nm": 0.0,
        "displacement_m": 0.0, "velocity_m_s": 0.0,
        "power_balance_residual_w": 0.0, "physical_values_available": False,
    }


def source_step(theta_deg, omega_deg_s, v_bus_v, mechanism=None) -> dict:
    """Return instantaneous rectified source current and required drive power.

    A captured radial cam gives x=L/2*(1-cos(2*theta)); an equivalent linear
    generator gives e=K*dx/dt and opposing force K*i.  A blocking bridge feeds
    the supplied bus: i=max((abs(e)-Vbus-Vrect)/R, 0).  Coulomb plus viscous
    follower loss is explicit.  Returned handle force is the added mechanism
    reaction at radius0.4m, not the total door/hinge/inertial force.

    A partial mechanism mapping overrides DEFAULT_MECHANISM.  Unknown keys,
    malformed inputs, geometry/rating breaches, and outward boundary motion
    fail closed.  Finite rating breaches retain their un-clipped diagnostics.
    """
    errors = []
    if mechanism is not None and not isinstance(mechanism, Mapping):
        return _invalid(["mechanism_not_a_mapping"])
    m = dict(DEFAULT_MECHANISM)
    if mechanism is not None:
        unknown = set(mechanism) - set(m)
        if unknown:
            return _invalid(["unknown_mechanism_fields:" + ",".join(sorted(map(str, unknown)))])
        m.update(mechanism)
    values = {"theta_deg": theta_deg, "omega_deg_s": omega_deg_s, "v_bus_v": v_bus_v, **m}
    for key, value in values.items():
        if not _number(value):
            errors.append("nonfinite_or_nonnumeric:" + key)
    if errors:
        return _invalid(errors)
    # Broad coefficient limits are declared simulation bounds, not a claim
    # that every winding/material combination in this box is manufacturable.
    for key, low, high in (
        ("stroke_m", 0.001, 0.020), ("cam_base_radius_m", 0.001, 0.030),
        ("generator_constant_vs_per_m", 1.0, 1000.0),
        ("coil_resistance_ohm", 1.0, 1e6), ("rectifier_drop_v", 0.0, 2.0),
        ("follower_coulomb_n", 0.0, 50.0),
        ("follower_viscous_n_s_per_m", 0.0, 100.0),
    ):
        if not low <= m[key] <= high:
            errors.append("coefficient_out_of_domain:" + key)
    if not 0.0 <= theta_deg <= 90.0:
        errors.append("angle_out_of_domain")
    if abs(omega_deg_s) > DOMAIN["maximum_speed_deg_s"]:
        errors.append("speed_out_of_domain")
    if not 0.0 <= v_bus_v <= DOMAIN["maximum_bus_v"]:
        errors.append("bus_voltage_out_of_domain")
    if (theta_deg == 0 and omega_deg_s < 0) or (theta_deg == 90 and omega_deg_s > 0):
        errors.append("outward_motion_at_angular_boundary")
    if errors:
        return _invalid(errors)

    stroke = m["stroke_m"]
    base = m["cam_base_radius_m"]
    # Two axial layers: 3mm cam, 1mm separation, 14mm generator, 2mm covers.
    # Body length40mm + travel + two2mm clearances.  Cam has a2mm radial rim.
    geometry = {
        "cam_diameter_m": 2 * (base + stroke + 0.002),
        "generator_travel_envelope_m": [0.040 + stroke + 0.004, 0.028, 0.014],
        "assembly_depth_m": 0.003 + 0.001 + 0.014 + 0.002,
        "maximum_pressure_angle_deg": math.degrees(math.atan(stroke / math.sqrt(base * (base + stroke)))),
    }
    if (geometry["cam_diameter_m"] > DOMAIN["envelope_width_m"] + 1e-12
            or geometry["generator_travel_envelope_m"][0] > DOMAIN["envelope_length_m"] + 1e-12
            or geometry["assembly_depth_m"] > DOMAIN["envelope_depth_m"] + 1e-12):
        errors.append("assembly_envelope_exceeded")
    if geometry["maximum_pressure_angle_deg"] > DOMAIN["maximum_pressure_angle_deg"]:
        errors.append("cam_pressure_angle_exceeded")

    theta = math.radians(theta_deg)
    omega = math.radians(omega_deg_s)
    displacement = stroke * (1 - math.cos(2 * theta)) / 2
    slope = 0.0 if theta_deg in (0, 90) else stroke * math.sin(2 * theta)
    velocity = slope * omega
    speed = abs(velocity)
    k = m["generator_constant_vs_per_m"]
    signed_emf = k * velocity
    emf = abs(signed_emf)
    current = max(0.0, (emf - v_bus_v - m["rectifier_drop_v"]) / m["coil_resistance_ohm"])
    friction = m["follower_coulomb_n"] + m["follower_viscous_n_s_per_m"] * speed if speed > 0 else 0.0
    force = k * current + friction
    reaction_torque = -math.copysign(force * abs(slope), omega) if omega else 0.0
    handle_force = abs(reaction_torque) / DOMAIN["handle_radius_m"]
    mechanical_power = force * speed
    bus_power = v_bus_v * current
    copper_loss = m["coil_resistance_ohm"] * current * current
    rectifier_loss = m["rectifier_drop_v"] * current
    other_loss = friction * speed
    residual = mechanical_power - (bus_power + copper_loss + rectifier_loss + other_loss)
    for value, limit, code in (
        (emf, DOMAIN["maximum_emf_v"], "emf_rating_exceeded"),
        (current, DOMAIN["maximum_current_a"], "current_rating_exceeded"),
        (copper_loss, DOMAIN["maximum_copper_loss_w"], "copper_rating_exceeded"),
        (handle_force, DOMAIN["maximum_handle_force_n"], "handle_force_limit_exceeded"),
    ):
        if value > limit + 1e-12:
            errors.append(code)
    if abs(residual) > 1e-12:
        errors.append("power_balance_error")
    return {
        "model_id": MODEL_ID, "valid": not errors, "domain_errors": errors,
        "physical_values_available": True, "current_a": current,
        "emf_v": emf, "signed_emf_v": signed_emf,
        "mechanical_power_w": mechanical_power, "bus_power_w": bus_power,
        "copper_loss_w": copper_loss, "rectifier_loss_w": rectifier_loss,
        "other_loss_w": other_loss, "handle_force_n": handle_force,
        "reaction_torque_nm": reaction_torque, "follower_opposing_force_n": force,
        "displacement_m": displacement, "velocity_m_s": velocity,
        "cam_slope_m_per_rad": slope,
        "pressure_angle_deg": math.degrees(math.atan(abs(slope) / (base + displacement))),
        "power_balance_residual_w": residual, "geometry": geometry,
        "stored_mechanical_energy_j": 0.0,
    }
