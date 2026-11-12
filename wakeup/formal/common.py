"""One full physical consumer; compact measurements, never next-step advice."""
import copy
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
sys.path.insert(0, str(HERE.parent))
from sim import TASK, G, beam, simulate


def baseline():
    return json.loads((HERE.parent / "design.json").read_text())


def full(design, task=TASK, **resolution):
    return simulate(copy.deepcopy(design), copy.deepcopy(task), **resolution)


def response(part, frequency, acceleration_g, load=0.):
    """Harmonic screening only. It is not the nonlinear transient consumer."""
    b = beam(part)
    omega = 2 * np.pi * frequency
    admittance = load + 1j * omega * b["cp"]
    q = -b["forcing_mass"] * G * acceleration_g / (
        b["k"] - b["m"] * omega**2 + 1j * omega * b["c"]
        + 1j * omega * b["theta"]**2 / admittance)
    v = -1j * omega * b["theta"] * q / admittance
    return q, v


def measurements(result):
    t, y = np.asarray(result["trace"]["t"]), np.asarray(result["trace"]["y"])
    env = result["task"]
    counts = Counter(e["event"] for e in result["events"])
    first = env["fault_starts_s"][0]
    quiet_end = min(env["fault_starts_s"] + env["nuisance_starts_s"]) - .01
    phases = {}
    # Least-squares phase on actually measured voltage, with a fixed reference sine.
    for label, column, freq, lo, hi in (
        ("main", 2, env["background_Hz"], max(0., quiet_end-1.), quiet_end),
        ("aux", 5, env["fault_Hz"], first+.01, first+env["fault_duration_s"]-.01)):
        mask = (t >= lo) & (t <= hi)
        tt = t[mask]
        origin = first if label == "aux" else 0.
        basis = np.array([np.sin(2*np.pi*freq*(tt-origin)), np.cos(2*np.pi*freq*(tt-origin)), np.ones(len(tt))]).T
        fit = np.linalg.lstsq(basis, y[mask, column], rcond=None)[0]
        phases[label] = dict(amplitude_V=float(np.hypot(*fit[:2])),
                             phase_deg=float(np.degrees(np.arctan2(fit[1], fit[0]))) if np.hypot(*fit[:2]) > 1e-8 else None,
                             reference="background sine at absolute clock; target sine relative to event start",
                             window_s=[lo, hi])
    windows = []
    for start in env["fault_starts_s"]:
        mask = (t >= start-.01) & (t <= start+env["delivery_deadline_s"])
        windows.append(dict(start_s=start, storage_before_V=float(np.interp(start-.001, t, y[:, 6])),
            minimum_storage_V=float(y[mask, 6].min()), envelope_max_V=float(y[mask, 7].max()),
            events=[{k: e[k] for k in ("time_s", "event")} for e in result["events"]
                    if start-.01 <= e["time_s"] <= start+env["delivery_deadline_s"]]))
    return dict(stages={k: counts[k] for k in ("WAKE", "BOOT", "SAMPLE", "INFER", "CONFIRM", "REJECT", "SAVE", "TX", "ACK", "BROWNOUT")},
        storage_before_first_event_V=float(np.interp(first-.01, t, y[:, 6])),
        main_peak_voltage_V=float(abs(y[:, 2]).max()), aux_peak_voltage_V=float(abs(y[:, 5]).max()),
        envelope_peak_V=float(y[:, 7].max()), t_ready_s=result["metrics"]["cold_charge_ready_s"],
        phase=phases, windows=windows)


def project(result, level):
    """Strict cumulative formal feedback. The evaluator retains the other facts."""
    m, checks = result["metrics"], result["checks"]
    out = dict(pass_=result["verdict"] == "PASS", delivered_on_time=m["delivered_on_time"],
               expected=m["faults"], false_alarms=m["false_reports"],
               safety=dict(stress=checks["stress_within_limit"], travel=checks["travel_within_limit"]))
    if level == 0:
        return out
    facts = measurements(result)
    out["stage_counts"] = {k: facts["stages"][k] for k in ("WAKE", "CONFIRM", "REJECT", "BROWNOUT")}
    if level == 1:
        return out
    out["node_measurements"] = dict(storage_before_event_V=facts["storage_before_first_event_V"],
        main_peak_V=facts["main_peak_voltage_V"], aux_peak_V=facts["aux_peak_voltage_V"],
        envelope_peak_V=facts["envelope_peak_V"], t_ready_s=facts["t_ready_s"])
    if level == 2:
        return out
    out["loaded_phase"] = dict(harvester=facts["phase"]["main"], trigger=facts["phase"]["aux"])
    out["event_windows"] = facts["windows"]
    return out


def compact(result):
    return {k: result[k] for k in ("verdict", "checks", "metrics", "energy_J", "runtime_s")} | {
        "measurements": measurements(result)}


def run(design, task=TASK, **resolution):
    return compact(full(design, task, **resolution))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
