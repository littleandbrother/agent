"""Finite whole-design LC configurations over unchanged qualified consumers.

No split store, retained clock, adaptive scheduling or physics is introduced.
The optional bounds are one-sided prerequisites, never full-service forecasts.
"""
from copy import deepcopy
import math

from ..pqe20261023bold import lc_adapter
from ..pqe20261022 import lcpv20261023


def execute_lc(task, design, problem, decision, output_dir, task_resolver, context):
    return lc_adapter.execute(task, design, problem, decision, output_dir,
                              task_resolver=task_resolver, context=context)


def participant_task(public):
    return lc_adapter.participant_task(public)


def scientific_identity():
    return lc_adapter.source_identity()


def cases(parent):
    base = deepcopy(parent)
    common = {"esr_ohm": .1, "startup_v": 2.3, "brownout_v": 2.2,
              "persistent_records": True, "nvm_capacity_records": 4096,
              "ack_spacing_s": 0.0}
    return [
        {"id": "original-parent", "design": base,
         "hypothesis": "Original default LC design in both preselected conditions; use original complete results only after exact scientific-input/source/evaluator comparison."},
        {"id": "energy-start-dark", "design": {**base, **common, "area_cm2": 50.0,
            "capacitance_f": .024, "sample_period_s": 59.0, "retry_s": 50.0},
         "hypothesis": "Double source area with moderate single storage and lower startup, maintained power through darkness,59s sampling slack and FIFO drain without ACK spacing. Retry before the next sample after the fixed first dropped ACK."},
        {"id": "time-record-continuity", "design": {**base, **common, "area_cm2": 50.0,
            "capacitance_f": .028, "sample_period_s": 55.0, "retry_s": 45.0},
         "hypothesis": "More dark-energy margin and5s sampling slack aim to maintain powered clock/samples continuously; persistent records are not a substitute for a powered clock. Low branch loss and full-area source counter startup delay."},
        {"id": "recovery-service", "design": {**base, **common, "area_cm2": 48.0,
            "capacitance_f": .026, "sample_period_s": 45.0, "retry_s": 30.0},
         "hypothesis": "Whole source/store/power configuration supports denser sampling and earlier retry, with zero inter-ACK gap for original FIFO history/fresh deadlines. Increased dark activity cost must be paid; no scheduler change."},
    ]


def necessary_bounds(context, design):
    """One declared inexpensive calculation for one fixed design/condition.

    OFF input voltage is fixed in the original model, so integration until the
    cold-start deadline bounds available pre-boot energy without carrying an
    old loaded trajectory across designs. Ignoring leakage/background/boot is
    optimistic and cannot certify the first actual receiver event.
    """
    task, profile = context["host_task"], context["public"]["Profile"]
    deadline = task["service"]["cold_start_first_valid_receive_deadline_s"]
    edges = {0.0, float(deadline)}
    for field in ("irradiance_schedule_w_m2", "uniform_shading_transmission"):
        edges.update(float(t) for row in task["optical_environment"][field]
                     for t in row[:2] if 0 < t < deadline)
    times = sorted(edges)
    energy = 0.0
    for lo, hi in zip(times, times[1:]):
        point = lcpv20261023.pv_point(task, profile, design, (lo+hi)/2, 0.0, False)
        energy += point["bus_power_w"] * (hi-lo)
    dark = task["service"]["dark_interval_s"]
    duration = dark[1]-dark[0]
    # At least floor(T/60) acquisitions are required for the unchanged60s
    # coverage service. Use only output-energy/efficiency, omit TX and all
    # positive leakage/ESR/sync costs for a valid optimistic necessary bound.
    count = math.floor(duration / task["service"]["dark_sampling_maximum_spacing_s"])
    load = profile["load"]
    minimum = duration*load["powered_background_w"] + count*(load["sense_j"]+load["save_j"])/load["efficiency"]
    maximum_store_budget = .5*design["capacitance_f"]*(profile["pmic"]["maximum_voltage_v"]**2-design["brownout_v"]**2)
    return {"cold_off_bus_energy_upper_j": energy,
            "startup_stored_energy_j": .5*design["capacitance_f"]*design["startup_v"]**2,
            "cold_capacitance_upper_f_at_this_area_and_startup": 2*energy/design["startup_v"]**2,
            "dark_continuous_power_minimum_j": minimum,
            "maximum_dark_usable_storage_j": maximum_store_budget,
            "optimistic_dark_capacitance_lower_f_at_this_brownout": 2*minimum/(profile["pmic"]["maximum_voltage_v"]**2-design["brownout_v"]**2),
            "violates_cold_necessary_bound": .5*design["capacitance_f"]*design["startup_v"]**2 > energy,
            "violates_dark_necessary_bound": maximum_store_budget < minimum,
            "exclusion_scope": "This fixed design and these source/voltage/service assumptions only. Passing necessary bounds remains UNKNOWN for full service; actual pre-dark voltage, TX/ACK/sync/retry, ESR and scheduling require complete execution.",
            "source_point_evaluations": len(times)-1, "full_simulations": 0}
