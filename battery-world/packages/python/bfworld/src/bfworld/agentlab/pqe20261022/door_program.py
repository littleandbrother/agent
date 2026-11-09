"""Consumed, powered door program with explicit atomic commit semantics.

This is a constructed software model, not a qualified NVM device. SAVE and ACK
each pay the declared write current and duration before one atomic NVM update.
An interrupted write leaves the previous image intact. Volatile mode pays the
same conservative load, but has no retained image. There is no unpowered clock.
"""
from binascii import crc_hqx
from copy import deepcopy

PROGRAM_VERSION = "pqe-door-program-v2"


def encode_frame(seq, direction):
    body = seq.to_bytes(4, "big") + bytes([direction])
    return (body + crc_hqx(body, 65535).to_bytes(2, "big")).hex()


def empty_image():
    return {"seq": 0, "last_direction": 0, "queue": []}


class DoorProgram:
    """Only current contact, supply and powered elapsed time enter the device.

    The environment supplies gateway availability at TX completion. Absolute
    world time and independent service truth are deliberately absent from this
    interface. Host-only events can be timestamped by the environment afterward.
    """

    def __init__(self, design, components):
        self.design = deepcopy(design)
        self.components = deepcopy(components)
        self.persistent = design["persistent_queue"]
        self.nvm = empty_image() if self.persistent else None
        self.ram = empty_image()
        self.mode = "OFF"
        self.remaining_s = 0.0
        self.uptime_s = 0.0
        self.retry_due_s = 0.0
        self.stable_raw = self.stable_since_s = None
        self.pending = None
        self.events = []
        self.boot_count = 0  # Host observation only; never used by decisions.

    @property
    def queue(self):
        return self.ram["queue"]

    @property
    def remaining_queue(self):
        image = self.nvm if self.persistent and self.mode == "OFF" else self.ram
        return deepcopy(image["queue"])

    @property
    def current_a(self):
        key = {"OFF": None, "BOOT": "boot_a", "IDLE": "idle_a",
               "SAVE": "write_a", "ACK": "write_a", "TX": "tx_a"}[self.mode]
        return self.components[key] if key else 0.0

    def _event(self, action, **fields):
        self.events.append({"action": action, "uptime_s": self.uptime_s, **fields})

    def drain_events(self):
        events, self.events = self.events, []
        return events

    def snapshot(self):
        return {"program_version": PROGRAM_VERSION, "mode": self.mode,
                "persistent": self.persistent, "nvm": deepcopy(self.nvm),
                "ram": deepcopy(self.ram), "pending": deepcopy(self.pending),
                "remaining_s": self.remaining_s, "uptime_s": self.uptime_s,
                "retry_due_s": self.retry_due_s, "stable_raw": self.stable_raw,
                "stable_since_s": self.stable_since_s}

    def reset(self, reason):
        self._event("brownout", during=self.mode, reason=reason,
                    queue_length=len(self.queue))
        self.mode, self.remaining_s = "OFF", 0.0
        self.ram = empty_image()
        self.pending = None
        self.stable_raw = self.stable_since_s = None
        self.uptime_s = self.retry_due_s = 0.0

    def begin_step(self, capacitor_v, contact):
        if contact not in (0, 1):
            raise ValueError("CURRENT_CONTACT_MUST_BE_BINARY")
        if self.mode == "OFF" and capacitor_v >= self.design["startup_v"]:
            self.ram = deepcopy(self.nvm) if self.persistent else empty_image()
            self.uptime_s = self.retry_due_s = 0.0
            self.mode, self.remaining_s = "BOOT", self.components["boot_s"]
            self.boot_count += 1
            self._event("boot", boot=self.boot_count)
        if self.mode == "OFF":
            return 0.0
        if contact != self.stable_raw:
            self.stable_raw, self.stable_since_s = contact, self.uptime_s
        if (self.mode == "IDLE" and contact != self.ram["last_direction"]
                and self.uptime_s - self.stable_since_s + 1e-10 >= self.design["debounce_s"]):
            self.pending = {"seq": self.ram["seq"] + 1, "direction": contact}
            self.mode, self.remaining_s = "SAVE", self.components["write_s"]
            self._event("capture", direction=contact)
        elif (self.mode == "IDLE" and self.queue
              and self.uptime_s + 1e-12 >= self.retry_due_s
              and capacitor_v >= self.design["tx_gate_v"]):
            self.mode, self.remaining_s = "TX", self.components["tx_s"]
            self._event("tx_begin", seq=self.queue[0]["seq"])
        return self.current_a

    def advance(self, elapsed_s, terminal_v, gateway_available=False):
        if elapsed_s < 0:
            raise ValueError("NEGATIVE_POWERED_TIME")
        if self.mode == "OFF":
            return
        self.uptime_s += elapsed_s
        if terminal_v < self.design["brownout_v"]:
            self.reset("LOAD_TERMINAL_UVLO")
            return
        if self.mode == "IDLE":
            return
        self.remaining_s -= elapsed_s
        if self.remaining_s > 1e-10:
            return
        if self.mode == "SAVE":
            self.ram["seq"] = self.pending["seq"]
            self.ram["last_direction"] = self.pending["direction"]
            self.queue.append(deepcopy(self.pending))
            if self.persistent:
                self.nvm = deepcopy(self.ram)
            self._event("save_commit", record=deepcopy(self.pending), durable=self.persistent)
            self.pending = None
        elif self.mode == "ACK":
            acknowledged = self.queue.pop(0)
            if self.persistent:
                self.nvm = deepcopy(self.ram)
            self._event("ack_commit", record=deepcopy(acknowledged), durable=self.persistent)
        elif self.mode == "TX":
            record = deepcopy(self.queue[0])
            self._event("wire_complete", record=record,
                        hex=encode_frame(record["seq"], record["direction"]))
            self.retry_due_s = self.uptime_s + self.design["retry_s"]
            if gateway_available:
                self.mode, self.remaining_s = "ACK", self.components["write_s"]
                self._event("ack_begin", record=record)
                return
        elif self.mode == "BOOT":
            self._event("boot_complete")
        self.mode, self.remaining_s = "IDLE", 0.0

    def elapse_idle(self, elapsed_s):
        """Analytic no-motion integration calls this only for powered idle."""
        if self.mode != "IDLE" or elapsed_s < 0:
            raise ValueError("ANALYTIC_IDLE_REQUIRES_IDLE")
        self.uptime_s += elapsed_s

    def invalidate_contact_sample(self):
        # The next environment sample is a current level, never old edge history.
        self.stable_raw = self.stable_since_s = None
