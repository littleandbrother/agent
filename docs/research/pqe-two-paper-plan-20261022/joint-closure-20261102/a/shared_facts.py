"""Common, outcome-blind facts and bounded calculators; never a consumer.

API v1.  An operation is all/storage/loads/source/energy/clock/recovery/bounds.
Results are JSON values. Conditional arithmetic is not a service certificate.
Only public task contracts are read; no result file, host task or evaluator is
opened. meter(kind,key,details) is called before new analytic/geometry work.
"""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from bfworld.agentlab.pqe20261022 import door_model, lcpv20261023 as lc
from bfworld.agentlab.pqe20261024debt import facts as door_facts
from bfworld.agentlab.pqe20261024debt import task as door_task
from bfworld.agentlab.pqe20261024debt import bounds as door_bounds

VERSION = "bfa101-shared-facts-v2"
OPERATIONS = ("all", "storage", "loads", "source", "energy", "clock", "recovery", "bounds")
_MEMO = OrderedDict()
_MEMO_LIMIT = 48


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def source_identity():
    # Include every original module actually used, not another group's results.
    from bfworld.agentlab.pqe20261023bold import consumer as bold
    from bfworld.agentlab.pqe20261022 import adapter as original_adapter
    from bfworld.agentlab.pqe20261024debt import holding
    from bfworld.coupled import engine
    modules = (door_model, lc, door_facts, door_task, door_bounds, bold,
               original_adapter, holding, engine)
    paths = [Path(__file__).resolve()] + [Path(m.__file__).resolve() for m in modules]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def _emit(meter, kind, key, details=None):
    if meter is not None:
        meter(kind, key, details)


def _tasks(contract):
    tasks = contract.get("tasks")
    if tasks is None and "task_id" in contract:
        tasks = [contract]
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 3:
        raise ValueError("PUBLIC_TASK_LIST_REQUIRED_MAX_THREE")
    if any(not isinstance(t, dict) or "task_id" not in t for t in tasks):
        raise ValueError("PUBLIC_TASK_CONTRACT_REQUIRED_NO_PATH_LOADING")
    return tasks


def _family(contract, tasks):
    kinds = {"LC" if "Profile" in t.get("public_inputs", {}) else "DOOR"
             if "motion" in t and "holding_component" in t.get("design_domain", {})
             else "UNKNOWN" for t in tasks}
    if len(kinds) != 1 or "UNKNOWN" in kinds:
        raise ValueError("UNSUPPORTED_OR_MIXED_WORLD")
    family = kinds.pop()
    declared = str(contract.get("world_kind", family)).upper()
    if ("LC" in declared or "COLD" in declared) and family != "LC":
        raise ValueError("WORLD_BINDING")
    if "DOOR" in declared and family != "DOOR":
        raise ValueError("WORLD_BINDING")
    return family


def _geometry(design, meter):
    # Same exact key as the original bounded cache; no patching or extra probe.
    f = door_model.source_step
    payload = json.dumps({"mechanism": design["mechanism"],
                          "defaults": door_model.DEFAULT_MECHANISM,
                          "domain": door_model.DOMAIN}, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    key = (f, getattr(f, "__code__", None), payload)
    hit = key in door_task._STATIC_GEOMETRY_CACHE
    _emit(meter, "geometry_hit" if hit else "geometry_miss", identity(payload),
          {"source": "original static_geometry_facts", "actual_miss": not hit})
    return door_task.static_geometry_facts(design["mechanism"])


def _validate(tasks, design, family, meter):
    _emit(meter, "structural", identity({"tasks": tasks, "design": design}),
          {"family": family, "task_count": len(tasks)})
    # Pure syntax/domain checks precede any geometry or analytic charge.
    identity(design)
    for t in tasks:
        domain = t["design_domain"]
        if set(design) != set(domain):
            raise ValueError("DESIGN_FIELDS_OUTSIDE_TASK")
        for name, spec in domain.items():
            v, kind = design[name], spec["kind"]
            if kind in ("number", "integer"):
                if type(v) not in (int, float) or not math.isfinite(v):
                    raise ValueError("NONFINITE_OR_NONNUMERIC:"+name)
                if kind == "integer" and type(v) is not int:
                    raise ValueError("INTEGER:"+name)
                if not spec["min"] <= v <= spec["max"]:
                    raise ValueError("DOMAIN:"+name)
            elif kind == "boolean" and type(v) is not bool:
                raise ValueError("BOOLEAN:"+name)
            elif kind == "enum" and v not in spec["values"]:
                raise ValueError("ENUM:"+name)
            elif kind == "mechanism":
                if not isinstance(v, dict) or set(v)-set(spec["editable"]):
                    raise ValueError("MECHANISM_FIELDS")
                for field, value in v.items():
                    lo, hi = spec["editable"][field]
                    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
                        raise ValueError("MECHANISM_DOMAIN:"+field)
        if not design["brownout_v"] < design["startup_v"]:
            raise ValueError("THRESHOLD_ORDER")
        if family == "LC":
            profile = t["public_inputs"]["Profile"]
            if (profile["pv"]["parallel_strings"] != 1 or profile["pv"]["cell_temperature_c"] != 25
                    or profile["pmic"]["maximum_step_s"] != 1):
                raise ValueError("LC_FROZEN_MODEL_DOMAIN")
            if not design["startup_v"] < profile["pmic"]["maximum_voltage_v"]:
                raise ValueError("LC_VOLTAGE_DOMAIN")
    if family == "DOOR":
        _geometry(design, meter)
        for t in tasks:
            door_task.validate_design(t, design)


def _base(contract, design, public_result):
    tasks = _tasks(contract)
    family = _family(contract, tasks)
    return tasks, family, {
        "schema": VERSION, "family": family,
        "family_id": contract.get("family_id"),
        "contract_sha256": identity(contract), "design_sha256": identity(design),
        "task_sha256": {t["task_id"]: identity(t) for t in tasks},
        "source_sha256": source_identity(),
        # Binding only: no unbound result or hidden annotation becomes a fact.
        "public_result_sha256": identity(public_result) if public_result is not None else None,
        "scope": {"public_task_only": True, "static_only": True,
                  "full_service": "UNKNOWN", "certificate": None,
                  "future_observations": False, "full_execution": False},
    }


def _fact(identifier, kind, subject, relation, obj, value, fields, ref):
    return {"id": identifier, "kind": kind, "subject": subject, "relation": relation,
            "object": obj, "value": value, "depends_on": list(fields), "source_refs": [ref]}


def candidate_facts(contract, design, public_result=None, *, meter=None):
    tasks, family, base = _base(contract, design, public_result)
    _validate(tasks, design, family, meter)
    if family == "DOOR":
        original = door_facts.design_facts(design, tasks[0])
        return {**base, "facts": original["facts"], "loads": original["loads"],
                "component_contract": door_facts.describe_contract(),
                "active_fields": list(tasks[0]["design_domain"])}
    d = design
    p = tasks[0]["public_inputs"]["Profile"]
    ref = "bfworld.agentlab.pqe20261022.lcpv20261023:simulate"
    allfields = list(d)
    facts = [
        _fact("storage.reservoir", "capacity", "capacitor", "bounded_by", "energy_thresholds",
              {"capacitance_f": d["capacitance_f"], "startup_v": d["startup_v"],
               "brownout_v": d["brownout_v"], "maximum_v": p["pmic"]["maximum_voltage_v"],
               "initial_energy_j": 0, "trajectory": "UNKNOWN"},
              ("capacitance_f", "startup_v", "brownout_v", "esr_ohm", "area_cm2"), ref),
        _fact("pv.production", "production", "pv_pmic", "produces", "loaded_bus_power",
              {"area_cm2": d["area_cm2"], "equation": "Pbus=eta*Vin*I_diode(Vin,area,public_irradiance)",
               "off_vin": p["pmic"]["cold_input_v"], "on_vin": "offset+Vstore/reflection_divisor",
               "fixed_power_source": False, "actual_loaded_energy": "UNKNOWN"},
              ("area_cm2", "capacitance_f", "esr_ohm", "startup_v", "brownout_v"), ref+"/pv_point"),
        _fact("supply.connection", "load", "all_operations", "connected_to", "shared_storage_bus",
              {"background_is_storage_power": True, "background_divide_by_efficiency": False,
               "phase_output_j_requires_input_current_esr_conversion_guard": True,
               "load_observation": "UNKNOWN"}, allfields, ref+"/start"),
        _fact("clock.continuation", "reset", "absolute_time", "survives_reset", "mcu_brownout",
              {"survives": False, "requires_continuous_power": True,
               "resync_requires_actual_gateway_and_paid_sync": True,
               "persistent_records_supply_clock": False, "independent_rtc": False,
               "actual_sync_and_coverage": "UNKNOWN"},
              ("capacitance_f", "area_cm2", "esr_ohm", "startup_v", "brownout_v", "persistent_records"), ref+"/off/complete"),
        _fact("sample.production", "production", "powered_sense", "produces", "new_quantized_sample",
              {"period_s": d["sample_period_s"], "requires_paid_sense": True,
               "retrospective_missing_samples": False, "actual_spacing": "UNKNOWN",
               "scheduler_priority": ["actual_gateway_sync", "due_sense", "due_pending_tx"]},
              ("sample_period_s", "capacitance_f", "area_cm2", "esr_ohm", "startup_v", "brownout_v"), ref),
        _fact("queue.handoff", "handoff", "sample", "available_after", "paid_save_commit",
              {"destination": "nvm_image" if d["persistent_records"] else "ram_image",
               "atomic": True, "survives_mcu_reset": d["persistent_records"],
               "interrupted_write_discarded": True, "complete_service": "UNKNOWN"},
              ("persistent_records", "nvm_capacity_records", "sample_period_s", "capacitance_f", "esr_ohm"), ref+"/complete"),
        _fact("queue.capacity", "capacity", "memory", "bounded_by", "all_committed_records",
              {"capacity": d["nvm_capacity_records"], "ack_frees_memory_slot": False,
               "ack_removes_pending_only": True, "full_image_blocks_new_commit": True,
               "actual_occupancy": "UNKNOWN"},
              ("nvm_capacity_records", "sample_period_s", "persistent_records"), ref+"/complete"),
        _fact("receiver.handoff", "handoff", "receiver", "available_after", "complete_valid_crc_frame",
              {"gateway_required": True, "receiver_acceptance_precedes_ack": True,
               "sequence_dedup": True, "ack_drop_first_n": tasks[0]["public_inputs"]["fixed_program_semantics"]["ack_drop_first_n"],
               "pending_removal_after": "paid_ack_commit", "actual_delivery": "UNKNOWN"},
              ("retry_s", "ack_spacing_s", "persistent_records", "sample_period_s", "capacitance_f", "esr_ohm", "area_cm2"), ref+"/complete"),
        _fact("queue.retry", "timing", "pending_fifo", "bounded_by", "actual_transmit_complete",
              {"after_ack_s": d["ack_spacing_s"], "after_no_ack_s": d["retry_s"],
               "selection": "fixed_public_FIFO_rank", "future_gateway_access": False,
               "actual_fresh_and_history_latency": "UNKNOWN"},
              ("retry_s", "ack_spacing_s", "sample_period_s", "nvm_capacity_records"), ref),
        _fact("darkness.coverage", "dynamic", "continuous_sampling_and_clock", "requires", "powered_coverage",
              {"task_services": {t["task_id"]: t["service"] for t in tasks},
               "gap_marker_satisfies_continuous_sampling": False, "static_energy_is_service": False,
               "complete_service": "UNKNOWN"}, allfields, ref),
    ]
    loads = [{"operation": op, "output_j": p["load"][op+"_j"],
              "duration_s": p["load"][op+"_s"], "guard": "constant-power ESR/dropout/reserve",
              "depends_on": ["capacitance_f", "esr_ohm", "startup_v", "brownout_v"],
              "source_refs": [ref+"/start"]} for op in ("boot", "sense", "save", "tx", "ack", "sync")]
    loads += [{"operation": op, "storage_w": p["load"][op+"_background_w"],
               "divide_by_efficiency": False, "source_refs": [ref]} for op in ("powered", "off")]
    checks = []
    for kind, subject, holds, deps, predicate in (
        ("PAID_LOAD", "lc_shared_storage_bus", True, allfields,
         {"implemented": "original shared storage equation; phase ESR/conversion guards; direct background"}),
        ("RELIABLE_HANDOFF", "lc_sample_to_committed_image", True,
         ["persistent_records", "nvm_capacity_records", "capacitance_f", "esr_ohm"],
         {"atomic_paid_SAVE_before_pending_TX": True, "actual_commit_and_reset_survival": "UNKNOWN"}),
        ("RESET_REENTRY", "lc_image_if_mcu_reset", d["persistent_records"],
         ["persistent_records"], {"if_mcu_reset": "committed sequence, image and pending queue survive"}),
        ("DYNAMIC_CAPACITY", "lc_all_committed_image", None,
         ["sample_period_s", "nvm_capacity_records", "persistent_records"],
         {"actual_occupancy_within_capacity": "UNKNOWN", "ack_reclaims_memory": False}),
        ("DYNAMIC_ENERGY", "lc_continuous_power_and_clock", None, allfields,
         {"actual_loaded_source_supply_covers_background_and_paid_activities": "UNKNOWN"}),
        ("DYNAMIC_EVIDENCE", "lc_recovery_fresh_and_history", None, allfields,
         {"actual_FIFO_recovery_and_fresh_deadlines": "UNKNOWN"}),
    ):
        checks.append({"kind": kind, "subject": subject, "holds": holds,
                       "applicable": True, "dependencies": deps,
                       "predicate": predicate, "source_refs": [ref],
                       "scope": "current program semantics, conditional on the stated event; never full service"})
    return {**base, "facts": facts, "loads": loads, "checks": checks, "active_fields": allfields,
            "component_contract": {"profile": deepcopy(p), "clock": tasks[0]["public_inputs"]["clock_contract"],
                                   "program": tasks[0]["public_inputs"]["fixed_program_semantics"]}}


def _storage(d, vmax):
    c, on, off = d["capacitance_f"], d["startup_v"], d["brownout_v"]
    return {"capacitance_f": c, "startup_energy_j": .5*c*on**2,
            "brownout_energy_j": .5*c*off**2, "maximum_energy_j": .5*c*vmax**2,
            "startup_to_brownout_j": .5*c*(on**2-off**2),
            "maximum_to_brownout_j": .5*c*(vmax**2-off**2),
            "equation": "E=.5*C*V^2; actual state/trajectory UNKNOWN"}


def _segments(t):
    optical = t["public_inputs"]["optical_environment"]
    cuts = {0., float(t["duration_s"]), float(t["service"]["cold_start_first_valid_receive_deadline_s"])}
    for name in ("irradiance_schedule_w_m2", "uniform_shading_transmission"):
        for row in optical[name]:
            if len(row) != 3 or not all(type(x) in (int, float) and math.isfinite(x) for x in row):
                raise ValueError("OPTICAL_SCHEDULE")
            cuts.update(float(x) for x in row[:2] if 0 <= x <= t["duration_s"])
    cuts = sorted(cuts)
    if len(cuts)-1 > 128:
        raise ValueError("BOUNDED_ANALYTIC_SEGMENT_LIMIT")
    return list(zip(cuts, cuts[1:]))


def _lc_numeric(t, d, sections):
    public = t["public_inputs"]
    p, service = public["Profile"], t["service"]
    load, pmic = p["load"], p["pmic"]
    vmax, c, off = pmic["maximum_voltage_v"], d["capacitance_f"], d["brownout_v"]
    result = {"task_id": t["task_id"], "status": "CONDITIONAL_NUMERIC_ONLY", "full_service": "UNKNOWN"}
    if "storage" in sections:
        result["storage"] = _storage(d, vmax)
    if "loads" in sections:
        rows = []
        for voltage in (off, d["startup_v"], vmax):
            for op in ("boot", "sense", "save", "tx", "ack", "sync"):
                j, duration = load[op+"_j"], load[op+"_s"]
                power = j/duration
                current = lc.input_current(voltage, power, d["esr_ohm"], load["efficiency"])
                terminal = voltage-current*d["esr_ohm"]
                drawn = voltage*current*duration
                collapsed = voltage**2 < 4*d["esr_ohm"]*power/load["efficiency"]
                reserve = .5*c*(voltage**2-off**2)-drawn
                rows.append({"phase": op, "storage_v": voltage, "output_j": j, "duration_s": duration,
                             "input_current_a": current, "terminal_v": terminal, "storage_drawn_j": drawn,
                             "collapsed": collapsed, "dropout": terminal < load["output_v"]+load["dropout_v"],
                             "reserve_margin_j": reserve,
                             "can_start_at_declared_state": not collapsed and terminal >= load["output_v"]+load["dropout_v"] and reserve >= 0,
                             "actual_phase_state": "UNKNOWN"})
        result["loads"] = {"phase_points": rows, "powered_background_storage_w": load["powered_background_w"],
                           "off_background_storage_w": load["off_background_w"],
                           "background_divide_by_efficiency": False,
                           "leakage_equation_w": "Vstore^2/Rleak", "leakage_ohm": load["leakage_ohm"],
                           "phase_source": "original coupled.engine.input_current and LC start guards"}
    if "source" in sections or "energy" in sections or "bounds" in sections:
        rows, cold_energy = [], 0.
        deadline = service["cold_start_first_valid_receive_deadline_s"]
        for a, b in _segments(t):
            points = []
            for voltage, powered in ((0., False), (off, True), (d["startup_v"], True), (vmax, True)):
                point = lc.pv_point({"optical_environment": public["optical_environment"]}, p, d, a, voltage, powered)
                points.append({"storage_v": voltage, "powered": powered, **point})
            cold = points[0]["bus_power_w"]
            cold_energy += max(0., min(b, deadline)-a)*cold if a < deadline else 0.
            vin_max = max(pmic["cold_input_v"], pmic["operating_input_offset_v"]+vmax/pmic["storage_reflection_divisor"])
            envelope = math.nextafter(vin_max*points[0]["photocurrent_a"]*pmic["conversion_efficiency"], math.inf)
            rows.append({"public_scenario_interval_s": [a, b], "points": points,
                         "all_legal_storage_voltage_bus_upper_w": envelope,
                         "envelope_basis": "0<=Idiode<=Iph; 0<=Vstore<=Vmax; Vin<=Vinmax; excludes loads",
                         "point_samples_are_energy_upper_bound": False})
        if "source" in sections:
            result["source"] = {"declared_scenario_points": rows, "actual_future_observation": False,
                                "trajectory_harvest_j": "UNKNOWN", "old_loaded_trace_used": False}
        if "energy" in sections or "bounds" in sections:
            dark_a, dark_b = service["dark_interval_s"]
            dark_duration = dark_b-dark_a
            bg = dark_duration*load["powered_background_w"]
            dark_zero = all(row["points"][0]["photocurrent_a"] == 0 for row in rows
                            if max(dark_a, row["public_scenario_interval_s"][0]) < min(dark_b, row["public_scenario_interval_s"][1]))
            gap_max = service["dark_sampling_maximum_spacing_s"]
            interior = max(0, math.ceil(dark_duration/gap_max)-1)
            result["energy"] = {
                "dark_interval_s": [dark_a, dark_b], "dark_duration_s": dark_duration,
                "zero_source_in_declared_dark_interval": dark_zero,
                "background_only_required_j": bg,
                "background_only_capacitance_lower_f": 2*bg/(vmax**2-off**2) if dark_zero else None,
                "background_only_margin_j": .5*c*(vmax**2-off**2)-bg if dark_zero else None,
                "necessary_bound_assumptions": ["continuous powered coverage throughout declared zero-source dark interval",
                                                 "starts dark at no more than Vmax", "no alternate source/store", "other loads and leakage omitted"],
                "minimum_interior_samples_with_endpoint_coverage": interior,
                "minimum_interior_sense_save_output_j": interior*(load["sense_j"]+load["save_j"]),
                "sample_count_scope": "at most maximum spacing; both interval endpoints may supply boundary coverage; open interior only",
                "conditional_nominal_dark": {
                    "sample_count": math.ceil(dark_duration/d["sample_period_s"]),
                    "sense_save_output_j": math.ceil(dark_duration/d["sample_period_s"])*(load["sense_j"]+load["save_j"]),
                    "continuous_no_ack_tx_count": math.ceil(dark_duration/d["retry_s"]),
                    "no_ack_tx_output_j": math.ceil(dark_duration/d["retry_s"])*load["tx_j"],
                    "scope": "separate conditional activity terms; no exact scheduler prediction, retry duty requires pending records and no ACK; output energy excludes ESR/conversion"},
                "cold_start": {"deadline_s": deadline,
                               "off_mode_potential_bus_energy_j": math.nextafter(cold_energy, math.inf),
                               "startup_required_j": .5*c*d["startup_v"]**2,
                               "capacitance_upper_f": math.nextafter(2*cold_energy/d["startup_v"]**2, math.inf),
                               "assumptions": "zero-energy OFF until first boot, public declared illumination, original fixed OFF input; drops background/leakage/boot/receive loads",
                               "service_certificate": None},
                "actual_loaded_harvest_j": "UNKNOWN", "certificate": None,
                "numerical_error_qualification": "UNKNOWN; constructed-kernel arithmetic only"}
    if "clock" in sections:
        clock = public["clock_contract"]
        age = max(0., service["dark_interval_s"][1]-service["dark_interval_s"][0])
        radius = age*clock["rate_bound_ppm"]/1e6+.001
        result["clock"] = {"conditional_since_actual_sync_s": age, "interval_radius_s": radius,
                           "nominal_midpoint_error_s": age*clock["nominal_rate_error_ppm"]/1e6,
                           "interval_width_s": 2*radius, "continuous_power_and_actual_sync_required": True,
                           "after_reset_interval": ["last_known_gap_lower", None],
                           "persistent_records_supply_clock": False, "actual_sync_at": "UNKNOWN"}
    if "recovery" in sections:
        n = max(0, math.floor(t["duration_s"]/d["sample_period_s"])+1)
        windows = sorted(t["gateway_windows"])
        gaps, last = [], 0.
        for a, b in windows:
            if a > last:
                gaps.append([last, a])
            last = max(last, b)
        if last < t["duration_s"]:
            gaps.append([last, t["duration_s"]])
        longest = max((b-a for a, b in gaps), default=0.)
        q = math.floor(longest/d["sample_period_s"])+1 if longest else 0
        cadence = max(load["tx_s"]+load["ack_s"], load["tx_s"]+d["ack_spacing_s"])
        result["recovery"] = {
            "nominal_all_committed_count_upper": n, "capacity_records": d["nvm_capacity_records"],
            "nominal_image_headroom_records": d["nvm_capacity_records"]-n,
            "ack_reclaims_memory": False, "actual_occupancy": "UNKNOWN",
            "declared_gateway_gap_intervals_s": gaps, "longest_declared_gap_s": longest,
            "conditional_gap_arrivals_upper": q, "successful_ack_cycle_nominal_s": cadence,
            "conditional_drain_time_s": q*cadence,
            "conditional_drain_tx_ack_output_j": q*(load["tx_j"]+load["ack_j"]),
            "history_budget_s": service["recovery_delay_s"],
            "fresh_sample_max_delay_s": service["new_sample_receive_max_delay_s"],
            "no_ack_retry_s": d["retry_s"],
            "scope": "public contract scenario arithmetic; continuous powered, commits on period grid, valid link/ACK, no competing sense/sync, phase delays or lost ACK. Actual retained queue/latency UNKNOWN; not a future beacon observation",
            "full_service": "UNKNOWN"}
    return result


def _door_numeric(t, d, sections):
    comp = t["components"]
    out = {"task_id": t["task_id"], "status": "CONDITIONAL_NUMERIC_ONLY", "full_service": "UNKNOWN"}
    if "storage" in sections:
        out["storage"] = _storage(d, comp["max_v"])
    if "loads" in sections:
        facts = door_facts.design_facts(d, t)
        rows = []
        for voltage in (d["startup_v"], d["tx_gate_v"], comp["max_v"]):
            for op, current, duration in (("boot", comp["boot_a"], comp["boot_s"]),
                                           ("save", comp["write_a"], comp["write_s"]),
                                           ("tx", comp["tx_a"], comp["tx_s"]),
                                           ("ack", comp["write_a"], comp["write_s"])):
                terminal = voltage-current*d["esr_ohm"]
                charge = current*duration
                margin = terminal-d["brownout_v"]
                rows.append({"phase": op, "storage_v": voltage, "current_a": current,
                             "duration_s": duration, "load_energy_at_declared_v_j": voltage*current*duration,
                             "terminal_v": terminal, "brownout_margin_v": margin,
                             "phase_charge_c": charge, "peak_esr_drop_v": current*d["esr_ohm"],
                             "capacitive_drop_v_no_source": charge/d["capacitance_f"],
                             "end_terminal_v_no_source": terminal-charge/d["capacitance_f"],
                             "conditional_capacitance_lower_f_no_source": charge/margin if margin > 0 else None,
                             "conditional_capacitance_interval_nonempty": margin > 0,
                             "conditional_equation": "Vterminal_end=Vstart-I*ESR-I*dt/C; C>=I*dt/(Vstart-Vbrownout-I*ESR), denominator>0",
                             "assumptions": "constant stated core current/duration, no source, no leakage or additional holder/idle load, starts at stated voltage; not a service or universal necessary bound",
                             "additional_holder_loads_excluded_from_this_point": True})
        chains = []
        phases = [("boot", comp["boot_a"], comp["boot_s"]),
                  ("save", comp["write_a"], comp["write_s"]),
                  ("tx", comp["tx_a"], comp["tx_s"]),
                  ("ack", comp["write_a"], comp["write_s"])]
        for voltage in (d["startup_v"], d["tx_gate_v"], comp["max_v"]):
            charge, requirements, nonempty = 0., [], True
            for op, current, duration in phases:
                charge += current*duration
                headroom = voltage-d["brownout_v"]-current*d["esr_ohm"]
                nonempty = nonempty and headroom > 0
                requirements.append({"phase_end": op, "cumulative_charge_c": charge,
                                     "headroom_v": headroom,
                                     "conditional_capacitance_lower_f": charge/headroom if headroom > 0 else None})
            chains.append({"start_storage_v": voltage, "phase_sequence": [x[0] for x in phases],
                           "phase_ends": requirements, "total_charge_c": charge,
                           "conditional_capacitance_lower_f": max(x["conditional_capacitance_lower_f"] for x in requirements) if nonempty else None,
                           "conditional_interval_nonempty": nonempty,
                           "assumptions": "hypothetical immediate contiguous BOOT/SAVE/TX/ACK; no source, idle/debounce, leakage or holder IO; actual scheduling/extra loads/gateway unknown; not service guarantee"})
        out["loads"] = {"phase_points": rows, "holder_loads": facts["loads"],
                         "conditional_phase_chains": chains,
                         "public_domain_endpoint_points": {"capacitance_f": [t["design_domain"]["capacitance_f"][x] for x in ("min", "max")],
                                                           "esr_ohm": [t["design_domain"]["esr_ohm"][x] for x in ("min", "max")],
                                                           "startup_v": [t["design_domain"]["startup_v"][x] for x in ("min", "max")],
                                                           "tx_gate_v": [t["design_domain"]["tx_gate_v"][x] for x in ("min", "max")]},
                         "idle_a": comp["idle_a"], "leakage_ohm": comp["leakage_ohm"],
                         "equation": "C*dV/dt=source(theta,omega,V)-I_mcu-I_holder-V/Rleak; point load_j=V*I*dt",
                         "actual_voltage_and_activity_duty": "UNKNOWN"}
    if "source" in sections:
        rows = []
        for index, seg in enumerate(t["motion"]):
            if index >= 32:
                raise ValueError("BOUNDED_MOTION_SEGMENT_LIMIT")
            theta = (seg["start_deg"]+seg["end_deg"])/2
            omega = (seg["end_deg"]-seg["start_deg"])/(seg["end_s"]-seg["start_s"])
            points = [{"storage_v": v, **door_model.source_step(theta, omega, v, d["mechanism"])}
                      for v in (d["brownout_v"], d["startup_v"], comp["max_v"])]
            rows.append({"public_motion_segment_index": index, "theta_deg": theta,
                         "omega_deg_s": omega, "points": points})
        out["source"] = {"declared_midpoint_source_points": rows,
                         "actual_loaded_source_energy_j": "UNKNOWN", "old_loaded_trace_used": False,
                         "point_samples_are_energy_upper_bound": False,
                         "equation": "I=max((abs(K*L*sin(2theta)*omega_rad_s)-Vbus-D)/R,0); Pbus=Vbus*I"}
    if "bounds" in sections or "energy" in sections:
        bound = door_bounds.necessary_bounds(d, t)
        # Existing exact algebra is useful; it grants no physical/kernel exclusion authority.
        out["bounds"] = {k: bound[k] for k in ("status", "source_energy_upper_j", "initial_energy_upper_j",
                                               "necessary_outer_intervals", "point_outside_outer_intervals",
                                               "scope", "numerical_certificate_status", "full_service") if k in bound}
        out["bounds"]["certificate"] = None
    if "clock" in sections:
        out["clock"] = {"absolute_device_time": "UNAVAILABLE", "independent_rtc": False, "full_service": "UNKNOWN"}
    if "recovery" in sections:
        out["recovery"] = {"persistent_queue": d["persistent_queue"], "retry_s": d["retry_s"],
                           "holding_capacity": d["holding_capacity"], "clear_after": d["clear_after"],
                           "actual_voltage_retention_identity_delivery": "UNKNOWN",
                           "placement_globally_correct": "UNKNOWN", "full_service": "UNKNOWN"}
    return out


def calculate(contract, design, operation="all", *, public_result=None, meter=None):
    if operation not in OPERATIONS:
        return {"schema": VERSION, "operation": operation, "status": "UNKNOWN",
                "reason": "UNSUPPORTED_OPERATION", "supported_operations": list(OPERATIONS), "certificate": None}
    tasks, family, base = _base(contract, design, public_result)
    _validate(tasks, design, family, meter)
    # Numerical values ignore public_result completely; observed results cannot
    # turn a static prediction into an observation or create a different oracle.
    key = identity({k: v for k, v in {**base, "operation": operation}.items() if k != "public_result_sha256"})
    if key in _MEMO:
        _MEMO.move_to_end(key)
        _emit(meter, "memo_hit", key, {"operation": operation, "family": family})
        return {**deepcopy(_MEMO[key]), "public_result_sha256": base["public_result_sha256"], "memo": "HIT"}
    _emit(meter, "cheap_numeric", key, {"operation": operation, "family": family,
                                       "task_count": len(tasks), "bounded_analytic_bundle": True,
                                       "full_execution": False})
    sections = set(OPERATIONS)-{"all"} if operation == "all" else {operation}
    function = _lc_numeric if family == "LC" else _door_numeric
    out = {**base, "operation": operation, "status": "CONDITIONAL_NUMERIC_ONLY", "memo_key": key,
           "tasks": [function(t, design, sections) for t in tasks],
           "applicability": {"constructed_source_model": True, "static_input_bound_only": True,
                             "physical_qualification": "UNKNOWN", "full_service": "UNKNOWN",
                             "service_certificate": None}}
    # These are explicit conditional mathematical inequalities, not selected
    # edits, a candidate design or a full-service repair prescription.
    constraints = []
    for task_index, (task, values) in enumerate(zip(tasks, out["tasks"])):
        if family == "LC" and "energy" in values:
            energy = values["energy"]
            if energy["zero_source_in_declared_dark_interval"]:
                constraints.append({"field": "capacitance_f", "relation": ">=",
                                    "bound": energy["background_only_capacitance_lower_f"],
                                    "status": "NECESSARY_CONDITIONAL", "applicable": True,
                                    "task_id": task["task_id"], "design_sha256": base["design_sha256"],
                                    "assumptions": energy["necessary_bound_assumptions"],
                                    "source_ref": "#/tasks/"+str(task_index)+"/energy/background_only_capacitance_lower_f",
                                    "equation": "C >= 2*Tdark*Pbackground/(Vmax^2-Vbrownout^2)",
                                    "certificate": None})
            constraints.append({"field": "capacitance_f", "relation": "<=",
                                "bound": energy["cold_start"]["capacitance_upper_f"],
                                "status": "NECESSARY_CONDITIONAL", "applicable": True,
                                "task_id": task["task_id"], "design_sha256": base["design_sha256"],
                                "assumptions": energy["cold_start"]["assumptions"],
                                "equation": "C <= 2*Eoff_bus_potential_before_deadline/Vstartup^2",
                                "certificate": None})
        elif family == "DOOR" and "bounds" in values:
            for field, interval in values["bounds"].get("necessary_outer_intervals", {}).items():
                for relation, bound in ((">=", interval[0]), ("<=", interval[1])):
                    constraints.append({"field": field, "relation": relation, "bound": bound,
                                        "status": "NECESSARY_CONDITIONAL", "applicable": True,
                                        "task_id": task["task_id"], "design_sha256": base["design_sha256"],
                                        "assumptions": values["bounds"].get("scope"),
                                        "certificate": None})
    out["constraints"] = constraints
    _MEMO[key] = deepcopy(out)
    if len(_MEMO) > _MEMO_LIMIT:
        _MEMO.popitem(last=False)
    return {**out, "memo": "MISS"}
