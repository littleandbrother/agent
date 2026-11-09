"""One versioned, observable-state firmware branch over the original program.

All electrical loads and atomic SAVE/ACK transitions are inherited. Phase
energy is a passive integral of the existing solver's midpoint supply current.
"""
from copy import deepcopy

from ..pqe20261022.door_program import DoorProgram as OriginalDoorProgram

PROGRAM_VERSION = "pqe-door-bold-program-v1"
POLICIES = ("fixed_retry_v1", "voltage_history_backoff_v1")


class DoorProgram(OriginalDoorProgram):
    def __init__(self, design, components):
        super().__init__(design, components)
        self.policy = design["firmware_policy"]
        self.consecutive_misses = 0
        self.sampled_capacitor_v = 0.0
        self.phase_energy_j = {k: 0.0 for k in ("BOOT", "SAVE", "TX", "ACK")}
        self.phase_esr_j = dict(self.phase_energy_j)

    def effective_tx_gate(self):
        if self.policy == "fixed_retry_v1":
            return self.design["tx_gate_v"]
        c = self.components
        charge = c["tx_a"] * c["tx_s"] + c["write_a"] * c["write_s"]
        return max(self.design["tx_gate_v"], self.design["brownout_v"]
                   + self.design["tx_reserve_v"] + self.design["esr_ohm"] * c["tx_a"]
                   + charge / self.design["capacitance_f"])

    def begin_step(self, capacitor_v, contact):
        self.sampled_capacitor_v = capacitor_v
        # Only the existing TX eligibility threshold changes. Original current
        # contact sampling and SAVE priority remain in the inherited function.
        original_gate = self.design["tx_gate_v"]
        self.design["tx_gate_v"] = self.effective_tx_gate()
        try:
            return super().begin_step(capacitor_v, contact)
        finally:
            self.design["tx_gate_v"] = original_gate

    def advance(self, elapsed_s, terminal_v, gateway_available=False):
        before = self.mode
        current = self.current_a
        end_capacitor_v = terminal_v + current * self.design["esr_ohm"]
        if before in self.phase_energy_j:
            midpoint = (self.sampled_capacitor_v + end_capacitor_v) / 2
            self.phase_energy_j[before] += midpoint * current * elapsed_s
            self.phase_esr_j[before] += current * current * self.design["esr_ohm"] * elapsed_s
        # The only gateway argument is the original actual completed-TX ACK
        # channel. It is never used to schedule TX or anticipate recovery.
        super().advance(elapsed_s, terminal_v, gateway_available)
        if self.policy == "fixed_retry_v1":
            return
        if before == "TX" and self.mode == "IDLE":
            self.consecutive_misses += 1
            delay = min(self.design["backoff_max_s"],
                        self.design["retry_s"] * 2 ** min(self.consecutive_misses, 4))
            low_voltage = end_capacitor_v < self.effective_tx_gate()
            if low_voltage:
                delay = min(self.design["backoff_max_s"], delay * 1.25)
            self.retry_due_s = self.uptime_s + delay
            self._event("adaptive_backoff", observed_capacitor_v=end_capacitor_v,
                        completed_unacknowledged_tx=self.consecutive_misses,
                        low_voltage=low_voltage, delay_s=delay)
        elif before == "ACK" and self.mode == "IDLE":
            self.consecutive_misses = 0
            self.retry_due_s = self.uptime_s
            self._event("adaptive_ack_reset")

    def reset(self, reason):
        super().reset(reason)
        # No new persistent state or unpaid write. The inherited paid image
        # keeps record identities/queue; powered retry state restarts on boot.
        self.consecutive_misses = 0

    def snapshot(self):
        value = super().snapshot()
        value.update(program_version=PROGRAM_VERSION, firmware_policy=self.policy,
                     consecutive_misses=self.consecutive_misses,
                     phase_energy_j=deepcopy(self.phase_energy_j),
                     phase_esr_j=deepcopy(self.phase_esr_j),
                     phase_energy_scope="Exact original midpoint load integral for dynamic BOOT/SAVE/TX/ACK, including interrupted steps; IDLE remains original full-run load ledger.")
        return value
