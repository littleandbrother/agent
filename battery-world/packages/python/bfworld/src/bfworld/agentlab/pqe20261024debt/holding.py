"""Finite powered event retention, with no zero-energy capture or host truth.

Every coefficient below is an explicit constructed assumption, not a measured
device parameter. Currents are loads at the common load-branch terminal.
Operation charge is I*dt; source energy is integrated as Vbus*I*dt by consumer.
"""
from copy import deepcopy
import math

VERSION = "codebt-paid-holder-v1"
PROFILE = {"voltage_min_v": 1., "voltage_max_v": 3.3, "monitor_a": 2e-7,
           "capture_a": 2e-5, "capture_s": .002, "debounce_s": .06,
           "retention_s": 60., "read_a": .0005, "read_s": .002,
           "clear_a": .0005, "clear_s": .002,
           "provenance": "Declared constructed low-power FIFO; all currents, timings, limits and retention are assumptions."}


class EventHolding:
    def __init__(self, capacity=2, overflow="drop_new", enabled=True):
        if type(capacity) is not int or not 1 <= capacity <= 4 or overflow not in ("drop_new", "overwrite_oldest"):
            raise ValueError("HOLDING_DOMAIN")
        self.capacity, self.overflow, self.enabled = capacity, overflow, enabled
        self.powered = False
        self.clock_s = 0.
        self.records = []
        self.token_counter = 0
        self.raw = self.stable_since_s = None
        self.last_direction = 0
        self.capture = None
        self.events = []
        self.audit_epoch = 0  # Observer label only: never returned by read/peek.
        self.audit_order = 0

    def next_audit_order(self):
        self.audit_order += 1
        return self.audit_order

    def _event(self, action, **value):
        self.events.append({"action": "holding_"+action, "holder_clock_s": self.clock_s,
                            "observer_epoch": self.audit_epoch,
                            "device_event_order": self.next_audit_order(), **value})

    def drain_events(self):
        result, self.events = self.events, []
        return result

    def _valid_voltage(self, voltage):
        return math.isfinite(voltage) and PROFILE["voltage_min_v"] <= voltage <= PROFILE["voltage_max_v"]

    def power_loss(self, reason="VOLTAGE_DOMAIN"):
        if self.powered:
            self._event("reset", reason=reason, lost=deepcopy(self.records), interrupted=deepcopy(self.capture))
            self.audit_epoch += 1
        self.powered = False
        self.clock_s = 0.
        self.records = []
        self.token_counter = 0
        self.raw = self.stable_since_s = None
        self.last_direction = 0
        self.capture = None

    def prepare(self, voltage, contact):
        if contact not in (0, 1):
            raise ValueError("HOLDING_BINARY_CONTACT_REQUIRED")
        if not self.enabled or not self._valid_voltage(voltage):
            self.power_loss()
            return
        if not self.powered:
            self.powered = True
            self._event("power_on")
        if contact != self.raw:
            self.raw, self.stable_since_s = contact, self.clock_s
        if (self.capture is None and contact != self.last_direction and
                self.clock_s-self.stable_since_s >= PROFILE["debounce_s"]-1e-12):
            self.last_direction = contact
            self.capture = {"direction": contact, "remaining_s": PROFILE["capture_s"]}
            self._event("capture_begin", direction=contact)

    @property
    def current_a(self):
        return (PROFILE["monitor_a"] + (PROFILE["capture_a"] if self.capture else 0.)) if self.powered else 0.

    @property
    def busy(self):
        """Powered contact qualification/capture status, no hidden event truth."""
        return self.powered and (self.capture is not None or self.raw != self.last_direction)

    def advance(self, elapsed_s, terminal_v):
        if elapsed_s < 0:
            raise ValueError("HOLDING_NEGATIVE_TIME")
        if not self.powered:
            return
        if not self._valid_voltage(terminal_v):
            self.power_loss("INTERRUPTED_VOLTAGE_DOMAIN")
            return
        self.clock_s += elapsed_s
        expired = [r for r in self.records if self.clock_s-r["captured_at_s"] >= PROFILE["retention_s"]-1e-12]
        for record in expired:
            self.records.remove(record)
            self._event("expired", record=deepcopy(record))
        if self.capture:
            self.capture["remaining_s"] -= elapsed_s
            if self.capture["remaining_s"] <= 1e-12:
                direction = self.capture["direction"]
                self.capture = None
                if len(self.records) >= self.capacity:
                    if self.overflow == "drop_new":
                        self._event("overflow_drop_new", direction=direction)
                        return
                    self._event("overflow_overwrite", record=deepcopy(self.records.pop(0)))
                self.token_counter += 1
                record = {"token": self.token_counter, "direction": direction,
                          "captured_at_s": self.clock_s, "assigned_seq": None, "read_seen": False}
                self.records.append(record)
                self._event("capture_commit", record=deepcopy(record))

    def peek(self):
        """Observer/test helper. MCU control uses ready pins and paid read only."""
        if not self.powered or not self.records:
            return None
        return {k: self.records[0][k] for k in ("token", "direction", "assigned_seq")}

    @property
    def ready(self):
        return self.powered and bool(self.records)

    @property
    def unread_ready(self):
        return self.ready and not self.records[0]["read_seen"]

    def latch_read_transaction(self):
        """Internal transaction latch; payload becomes visible only at commit."""
        return self.records[0]["token"] if self.ready else None

    def read_commit(self, token, proposed_seq):
        """Called only after paid MCU read completes; claim lives in holder domain."""
        record = self.records[0] if self.powered and self.records else None
        if record is None or record["token"] != token:
            self._event("read_invalidated", token=token)
            return None
        if type(proposed_seq) is not int or proposed_seq < 1 or proposed_seq >= 2**32:
            raise ValueError("HOLDING_SEQUENCE_DOMAIN")
        if record["assigned_seq"] is None:
            record["assigned_seq"] = proposed_seq
        record["read_seen"] = True
        value = {k: record[k] for k in ("token", "direction", "assigned_seq")}
        self._event("read_commit", record=deepcopy(value))
        return value

    def clear_commit(self, assigned_seq):
        """Called after paid clear; cannot clear a different or unclaimed slot."""
        record = self.records[0] if self.powered and self.records else None
        if record is None or record["assigned_seq"] != assigned_seq:
            self._event("clear_invalidated", assigned_seq=assigned_seq)
            return False
        self.records.pop(0)
        self._event("clear_commit", record=deepcopy(record))
        return True

    def next_boundary_s(self):
        if not self.powered:
            return math.inf
        options = [r["captured_at_s"]+PROFILE["retention_s"]-self.clock_s for r in self.records]
        if self.capture:
            options.append(self.capture["remaining_s"])
        elif self.raw is not None and self.raw != self.last_direction:
            options.append(PROFILE["debounce_s"]-(self.clock_s-self.stable_since_s))
        return max(0., min(options)) if options else math.inf

    def snapshot(self):
        return {"version": VERSION, "powered": self.powered, "records": deepcopy(self.records),
                "clock_s": self.clock_s, "capture": deepcopy(self.capture),
                "observer_epoch": self.audit_epoch,
                "identity_scope": "token resets on holder loss; assigned_seq exists only after paid read; observer epoch is never device input"}
