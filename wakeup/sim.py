"""One coupled simulation. Run: python3 wakeup/sim.py [design.json]."""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

# Fixed engineering task. Times are evaluation truth, not detector inputs.
TASK = {
    "duration_s": 30.0,
    "background_Hz": 45.0,
    "background_peak_g": 0.15,
    "fault_Hz": 210.0,
    "fault_peak_g": 0.50,
    "fault_duration_s": 0.15,
    "fault_starts_s": [8.0, 14.0, 20.0, 26.0],
    "nuisance_Hz": 250.0,
    "nuisance_peak_g": 0.80,
    "nuisance_duration_s": 0.20,
    "nuisance_starts_s": [11.0, 23.0],
    "delivery_deadline_s": 0.25,
    "stress_limit_MPa": 40.0,
    "tip_travel_limit_mm": 1.5,
}
G = 9.80665


def beam(d):
    """Symmetric parallel bimorph, one cubic Rayleigh-Ritz bending mode."""
    L, b, hs, hp = (d[k] * 1e-3 for k in
                    ("length_mm", "width_mm", "substrate_mm", "piezo_layer_mm"))
    # Declared representative material constants, not a fitted commercial part.
    Es, Ep, rhos, rhop, eps, e31 = 200e9, 60e9, 7800, 7500, 1700 * 8.8541878128e-12, 11.4
    z = (hs + hp) / 2
    EI = Es * b * hs**3 / 12 + 2 * Ep * b * (hp**3 / 12 + hp * z**2)
    mb = b * L * (rhos * hs + 2 * rhop * hp)
    mt = d["tip_mass_g"] * 1e-3
    m, forcing_mass, k = mt + 33 / 140 * mb, mt + 3 / 8 * mb, 3 * EI / L**3
    cp, theta = 2 * eps * b * L / hp, 3 * b * e31 * z / L
    return {"m": m, "forcing_mass": forcing_mass, "k": k,
            "c": 2 * d["damping_ratio"] * np.sqrt(k * m), "cp": cp, "theta": theta,
            "stress_per_m": Ep * (hs / 2 + hp) * 3 / L**2,
            "short_circuit_Hz": np.sqrt(k / m) / (2 * np.pi),
            "open_circuit_Hz": np.sqrt((k + theta**2 / cp) / m) / (2 * np.pi),
            "beam_mass_g": mb * 1000}


def acceleration(t, task=TASK):
    a = task["background_peak_g"] * np.sin(2 * np.pi * task["background_Hz"] * t)
    for name in ("fault", "nuisance"):
        duration = task[f"{name}_duration_s"]
        for start in task[f"{name}_starts_s"]:
            u = t - start
            if 0 <= u < duration:
                edge = min(u / 0.005, (duration - u) / 0.005, 1.0)
                taper = 0.5 - 0.5 * np.cos(np.pi * edge)
                a += task[f"{name}_peak_g"] * taper * np.sin(2 * np.pi * task[f"{name}_Hz"] * u)
    return G * a


def simulate(design, task=TASK, *, rtol=2e-6, max_step=0.00025):
    started = time.perf_counter()
    h, w = beam(design["harvester"]), beam(design["trigger_beam"])
    c, f = design["circuit"], design["firmware"]
    modules = design.get("modules", dict(A=True, B=False, C=False, D=False))
    A, B, C, D = (modules[k] for k in "ABCD")
    regulated = "converter_input_R_ohm" in c
    wiring = design.get("connections", {})
    A = wiring.get("aux_resonator", A)
    detector = wiring.get("detector_source", "harvester" if f.get("wake_from_harvester", False) else "aux" if A else "none")
    harvest_wake = detector == "harvester"
    triggered, next_poll = wiring.get("mcu_gate", "envelope" if A or B or harvest_wake else "poll") == "envelope", 0.0
    Cs, Ce = c["storage_uF"] * 1e-6, c["envelope_nF"] * 1e-9
    # qh, qh_dot, vh, qw, qw_dot, vw, storage, envelope, sensor;
    # then energy terms: input, damping, rectifier, front-end, MCU, idle, clamp.
    y, t, phase, armed = np.zeros(16), 0.0, "OFF", True
    events, records, segments = [], [], []
    boot_at, brownouts, sequence = None, 0, 0

    def rhs(t, y, power, sampling):
        qh, uh, vh, qw, uw, vw, vs, ve, sensor = y[:9]
        a = acceleration(t, task)
        if regulated:
            # Representative regulated-input rectifier, not the original series resistor.
            ih = max(abs(vh)-2*c["bridge_diode_V"], 0)/c["converter_input_R_ohm"]
            storage_current = .65*max(abs(vh)-2*c["bridge_diode_V"], 0)*ih/max(vs, .1)
        else:
            ih = max((abs(vh)-max(vs, 0)-2*c["bridge_diode_V"])/c["bridge_series_ohm"], 0)
            storage_current = ih
        shunt = max(abs(vh)-c["shunt_threshold_V"], 0)/c["shunt_ohm"] if D else 0.
        source = vh if harvest_wake else vw
        ie = max((abs(source)-ve-2*c["envelope_diode_V"])/c["envelope_charge_ohm"], 0) if detector != "none" else 0.
        envelope_dot = (ie-ve/c["envelope_discharge_ohm"])/Ce
        if B:
            envelope_dot = (max(ve, 2*abs(a/G))-ve)/.002-ve/.04
        iq = c["reference_and_power_control_nA"] * 1e-9
        if vs >= c["comparator_supply_min_V"]:
            iq += c["comparator_nA"] * 1e-9
        il = power / (c["regulator_efficiency"] * max(vs, 0.1))
        leakage = max(vs, 0) / c["storage_leak_ohm"]
        extra = ((.5*A+180*B+2*C+.5*D)*1e-6+max(Ce*ve*envelope_dot, 0)*B)/max(vs, .1)
        clamp = max((vs - c["clamp_V"]) / c["clamp_ohm"], 0)
        vdot = (storage_current - il - iq - leakage - extra - clamp) / Cs
        if vs <= 0 and vdot < 0:
            vdot = 0.0
        return [uh, (-h["c"] * uh - h["k"] * qh + h["theta"] * vh - h["forcing_mass"] * a) / h["m"],
                (-h["theta"]*uh-np.sign(vh)*(ih+shunt+ie*harvest_wake))/h["cp"],
                uw, (-w["c"]*uw-w["k"]*qw+w["theta"]*vw-w["forcing_mass"]*a)/w["m"] if A else 0.,
                (-w["theta"]*uw-np.sign(vw)*ie*(detector == "aux")-vw/c["trigger_input_ohm"])/w["cp"] if A else 0.,
                vdot, envelope_dot,
                2 * np.pi * f["sensor_bandwidth_Hz"] * (a - sensor) if sampling else 0,
                -a * (h["forcing_mass"] * uh + A*w["forcing_mass"] * uw),
                h["c"] * uh**2 + w["c"] * uw**2,
                ih*abs(vh)-vs*storage_current+shunt*abs(vh),
                ie*(abs(source)-ve)+ve**2/c["envelope_discharge_ohm"]+A*vw**2/c["trigger_input_ohm"] if not B else 0.,
                vs * il, vs * (iq + leakage + extra), vs * clamp]

    def advance(end, power=0.0, sampling=False, stop=None):
        nonlocal t, y
        event = None
        if stop == "wake":
            def event(t, y):
                return min(y[7] - c["wake_high_V"], y[6] - c["start_V"])
            event.direction = 1
        elif stop == "rearm":
            def event(t, y):
                return y[7] - c["wake_low_V"]
            event.direction = -1
        elif stop == "brownout":
            def event(t, y):
                return y[6] - c["brownout_V"]
            event.direction = -1
        elif stop == "ready":
            def event(t, y):
                return y[6] - c["start_V"]
            event.direction = 1
        if event is not None:
            event.terminal = True
        sol = solve_ivp(lambda t, y: rhs(t, y, power, sampling), (t, min(end, task["duration_s"])), y,
                        method="LSODA", rtol=rtol,
                        atol=[1e-10, 1e-8, 1e-7, 1e-10, 1e-8, 1e-7, 1e-7, 1e-7, 1e-6] + [1e-11] * 7,
                        max_step=max_step, dense_output=True, events=event)
        if not sol.success:
            raise RuntimeError(sol.message)
        segments.append((phase, sol))
        t, y = float(sol.t[-1]), sol.y[:, -1].copy()
        return sol

    def work(name, duration, mW):
        nonlocal phase, brownouts
        phase = name
        events.append({"time_s": t, "event": name})
        sol = advance(t + duration, mW * 1e-3, name in ("SAMPLE", "PEEK"), "brownout")
        if sol.status == 1:
            brownouts += 1
            events.append({"time_s": t, "event": "BROWNOUT"})
            return None
        return sol

    while t < task["duration_s"] - 1e-9:
        phase = "OFF"
        if triggered and not armed:
            if y[7] > c["wake_low_V"]:
                advance(task["duration_s"], stop="rearm")
            armed = True
        if t >= task["duration_s"] - 1e-9:
            break
        if not triggered and next_poll > t:
            advance(next_poll)
        if t >= task["duration_s"] - 1e-9:
            break
        if not (y[6] >= c["start_V"] and (not triggered or y[7] >= c["wake_high_V"])):
            sol = advance(task["duration_s"], stop="wake" if triggered else "ready")
            if sol.status == 0:
                break
        armed = False
        wake_at = t
        next_poll = t + f.get("poll_s", .1)
        if boot_at is None:
            boot_at = t
        events.append({"time_s": t, "event": "WAKE", "storage_V": float(y[6])})
        if work("BOOT", f["boot_s"], f["boot_mW"]) is None:
            continue
        y[8] = 0.0  # The high-bandwidth accelerometer is powered only during acquisition.
        if f.get("peek_window_s", 0):
            peek_start = t
            peek = work("PEEK", f["peek_window_s"], f.get("peek_mW", f["sample_mW"]))
            if peek is None:
                continue
            pv = peek.sol(np.linspace(peek_start, t, 16))[8] / G
            prms = float(np.sqrt(np.mean(pv**2)))
            events.append({"time_s": t, "event": "PEEK_RESULT", "rms_g": prms})
            if prms < f.get("peek_threshold_g", .3):
                continue
        sample_start = t
        sol = work("SAMPLE", f["sample_count"] / f["sample_Hz"], f["sample_mW"])
        if sol is None:
            continue
        times = sample_start + np.arange(f["sample_count"]) / f["sample_Hz"]
        values = np.clip(sol.sol(times)[8] / G, -f["sensor_range_g"], f["sensor_range_g"])
        quantum = 2 * f["sensor_range_g"] / 2**f["adc_bits"]
        values = np.round(values / quantum) * quantum
        spectrum = np.abs(np.fft.rfft((values - values.mean()) * np.hanning(len(values))))**2
        frequencies = np.fft.rfftfreq(len(values), 1 / f["sample_Hz"])
        band = (frequencies >= f["target_band_Hz"][0]) & (frequencies <= f["target_band_Hz"][1])
        fraction = float(spectrum[band].sum() / max(spectrum.sum(), 1e-30))
        rms = float(np.sqrt(np.mean((values - values.mean())**2)))
        detected = fraction >= f["minimum_band_fraction"] and rms >= f["minimum_target_rms_g"]
        if work("INFER", f["infer_s"], f["infer_mW"]) is None:
            continue
        events.append({"time_s": t, "event": "CONFIRM" if detected else "REJECT",
                       "target_band_fraction": fraction, "rms_g": rms, "samples_g": values.tolist()})
        if detected:
            if work("SAVE", f["save_s"], f["save_mW"]+(5e-3/f["save_s"] if C else 0)) is None:
                continue
            sequence += 1  # Device-owned persistent counter, committed by SAVE.
            ok = True
            for name in ("tx", "ack"):
                if work(name.upper(), f[f"{name}_s"], f[f"{name}_mW"]) is None:
                    ok = False
                    break
            if ok:
                records.append({"sequence": sequence, "wake_s": wake_at, "received_s": t,
                                "target_band_fraction": fraction, "sample_rms_g": rms})
                events.append({"time_s": t, "event": "RECEIVED", "sequence": sequence})

    # Sample the actual solver trajectories; preserve the exact program events separately.
    ts, ys, modes = [], [], []
    for name, sol in segments:
        grid = np.arange(np.ceil(sol.t[0] * 1000) / 1000, sol.t[-1], 0.001)
        grid = np.unique(np.r_[grid, sol.t[-1]])
        ts.extend(grid.tolist()); ys.extend(sol.sol(grid).T.tolist()); modes.extend([name] * len(grid))
    trace = np.array(ys)
    matched, missed, latencies = set(), [], []
    for start in task["fault_starts_s"]:
        found = next((i for i, r in enumerate(records) if i not in matched and start <= r["received_s"] <= start + task["delivery_deadline_s"]), None)
        if found is None:
            missed.append(start)
        else:
            matched.add(found)
            latency = records[found]["received_s"] - start
            records[found]["fault_start_s"] = start
            records[found]["latency_s"] = latency
            latencies.append(latency)
    # Safety uses accepted solver nodes, not the coarser 1 ms exported waveform.
    peak_h = max(float(np.abs(sol.y[0]).max()) for _, sol in segments)
    peak_w = max(float(np.abs(sol.y[3]).max()) for _, sol in segments)
    peak_stress = max(peak_h * h["stress_per_m"], peak_w * w["stress_per_m"]) / 1e6
    peak_tip = max(peak_h, peak_w) * 1000
    stored = (0.5 * h["m"] * y[1]**2 + 0.5 * h["k"] * y[0]**2 + 0.5 * h["cp"] * y[2]**2
              + 0.5 * w["m"] * y[4]**2 + 0.5 * w["k"] * y[3]**2 + 0.5 * w["cp"] * y[5]**2
              + 0.5 * Cs * y[6]**2 + 0.5 * Ce * y[7]**2)
    residual = float(y[9] - sum(y[10:]) - stored)
    checks = {"all_faults_delivered_on_time": not missed, "no_false_reports": len(matched) == len(records),
              "no_brownouts": brownouts == 0, "stress_within_limit": peak_stress <= task["stress_limit_MPa"],
              "travel_within_limit": peak_tip <= task["tip_travel_limit_mm"]}
    ready = np.flatnonzero(trace[:, 6] >= c["start_V"])
    active = np.array(modes) != "OFF"
    return {"task": task, "design": design, "model": "Single cubic beam modes; actual rectifier, envelope, storage and program loads; optional regulated input and voltage shunt",
            "verdict": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "metrics": {"faults": len(task["fault_starts_s"]), "delivered_on_time": len(matched),
                        "missed_fault_starts_s": missed, "false_reports": len(records) - len(matched),
                        "wakeups": sum(e["event"] == "WAKE" for e in events), "brownouts": brownouts,
                        "cold_charge_ready_s": float(ts[ready[0]]) if len(ready) else None,
                        "first_wake_s": boot_at, "max_latency_s": max(latencies, default=None),
                        "minimum_active_storage_V": float(trace[active, 6].min()) if active.any() else None,
                        "peak_stress_MPa": peak_stress, "peak_tip_mm": peak_tip, "final_storage_V": float(y[6])},
            "energy_J": {"mechanical_input": float(y[9]), "mechanical_damping": float(y[10]),
                         "rectifier_loss": float(y[11]), "trigger_front_end_loss": float(y[12]),
                         "MCU_input": float(y[13]), "idle": float(y[14]), "clamp_loss": float(y[15]),
                         "rectified_to_storage": float(0.5 * Cs * y[6]**2 + sum(y[13:])),
                         "final_stored_all_domains": float(stored), "balance_residual": residual},
            "beam_parameters": {"harvester": h, "trigger": w}, "records": records, "events": events,
            "runtime_s": time.perf_counter() - started,
            "trace": {"t": ts, "y": trace, "phase": modes}}


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "design.json"
    result = simulate(json.loads(path.read_text()))
    trace = result.pop("trace")
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    with (root / "trace.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time_s", "acceleration_g", "harvester_tip_mm", "harvester_V", "trigger_tip_mm", "trigger_V", "storage_V", "envelope_V", "phase"])
        for t, y, mode in zip(trace["t"], trace["y"], trace["phase"]):
            writer.writerow([f"{t:.7f}", f"{acceleration(t) / G:.6g}", f"{y[0] * 1000:.6g}", f"{y[2]:.6g}",
                             f"{y[3] * 1000:.6g}", f"{y[5]:.6g}", f"{y[6]:.6g}", f"{y[7]:.6g}", mode])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ts, y = np.array(trace["t"]), trace["y"]
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True, layout="constrained")
    axes[0].plot(ts, [acceleration(t) / G for t in ts], color="#64748b", lw=0.6)
    axes[0].set_ylabel("Base acceleration (g)")
    axes[1].plot(ts, y[:, 6], color="#2563eb", label="Storage")
    axes[1].plot(ts, y[:, 7], color="#ea580c", label="Trigger envelope", lw=0.8)
    axes[1].axhline(result["design"]["circuit"]["start_V"], color="#2563eb", ls=":", lw=0.8)
    axes[1].set_ylabel("Voltage (V)"); axes[1].legend(loc="upper right")
    for r in result["records"]:
        axes[2].plot(r["received_s"], 1, "o", color="#16a34a")
        axes[2].annotate(str(r["sequence"]), (r["received_s"], 1), xytext=(4, 4), textcoords="offset points")
    for start in TASK["fault_starts_s"]:
        for ax in axes:
            ax.axvspan(start, start + TASK["fault_duration_s"], color="#f97316", alpha=0.18)
    for start in TASK["nuisance_starts_s"]:
        for ax in axes:
            ax.axvspan(start, start + TASK["nuisance_duration_s"], color="#94a3b8", alpha=0.20)
    axes[2].set(ylim=(0.6, 1.5), yticks=[1], yticklabels=["Delivered"], xlabel="Time (s)")
    fig.suptitle("Mechanical-analog wake-up node | orange: target, gray: nuisance | " + result["verdict"])
    fig.savefig(root / "waveforms.svg")
    plt.close(fig)
    print(json.dumps({k: result[k] for k in ("verdict", "metrics", "energy_J", "runtime_s")}, indent=2))
