"""Four whole designs, frozen before the eight original M2 executions."""
from copy import deepcopy

PARENT_SOURCE = "docs/research/pqe-two-paper-plan-20261022/service-repair-m3/s0/engineering/02/public-result.json"
PARENT_SOURCE_SHA256 = "92725ab0c62a41f0edd15a77c2377a0f596b3196ec87cf30dfef19bad2f01e06"


def cases(parent):
    common = {"firmware_policy": "fixed_retry_v1", "backoff_max_s": 1.0,
              "tx_reserve_v": .025}
    baseline = {**deepcopy(parent), **common}
    joint = {**deepcopy(baseline), "capacitance_f": .00043331042229505213,
             "esr_ohm": .1, "startup_v": 1.9, "tx_gate_v": 2.0368970612101864,
             "mechanism": {"stroke_m": .0085, "cam_base_radius_m": .006867665249893994}}
    save_first = {**deepcopy(baseline), "capacitance_f": .00033,
                  "esr_ohm": .1, "startup_v": 1.9, "tx_gate_v": 2.12,
                  "debounce_s": .06, "retry_s": .85, "persistent_queue": True,
                  "mechanism": {"stroke_m": .0083, "cam_base_radius_m": .007}}
    adaptive = {**deepcopy(joint), "firmware_policy": "voltage_history_backoff_v1",
                "retry_s": .425, "backoff_max_s": 1.0, "tx_reserve_v": .025,
                "persistent_queue": True}
    return [
        {"id": "original-parent", "design": baseline,
         "hypothesis": "Retained M3 engineering02 parent applied unchanged to both original M2 conditions establishes the baseline; no outcome-dependent parent selection."},
        {"id": "joint-source-supply", "design": joint,
         "hypothesis": "Known public M1 full joint geometry/storage/threshold design may repair cold-start service; fixed retry can still spend energy before link recovery. No single-parameter causal attribution."},
        {"id": "save-first", "design": save_first,
         "hypothesis": "Legal near-envelope mechanism plus moderate storage, low startup, durable early SAVE, reserved TX gate and slower fixed retry may preserve identities and energy across recovery; original SAVE priority and paid actions unchanged."},
        {"id": "persistent-adaptive", "design": adaptive,
         "hypothesis": "Joint supply plus voltage-reserved TX and observed no-ACK exponential backoff may avoid repeated unavailable-link energy loss while paid ACK releases the next queued record. No future schedule input."},
    ]
