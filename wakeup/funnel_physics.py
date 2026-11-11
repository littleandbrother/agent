"""Shared factual interface to the unchanged full transient node."""
import copy
import fcntl
import hashlib
import json
import signal
import threading
from pathlib import Path

import numpy as np

from sim import G, acceleration, simulate

CACHE = Path(__file__).with_name("funnel") / "cache"
LOCK = threading.Lock()  # LSODA is not reentrant within a process.
STAGES = ("WAKE", "BOOT", "PEEK", "SAMPLE", "INFER", "CONFIRM", "REJECT", "SAVE", "TX", "ACK", "RECEIVED", "BROWNOUT")
TRACE_COLUMNS = ("time_s", "acceleration_g", "harvester_tip_mm", "harvester_V", "trigger_tip_mm", "trigger_V", "storage_V", "envelope_V")
EXECUTION_LIMIT_S = 120
EXECUTION_TIMEOUT = "TOOL_ERROR: full numerical execution exceeded 120s; no scientific result"


def _execution_timeout(signum, frame):
    raise RuntimeError(EXECUTION_TIMEOUT)


def public_task(task):
    from funnel_tasks import public_task as task_spec
    return copy.deepcopy(task_spec(task))


def design(task, x):
    from funnel_tasks import design_for
    return design_for(task, x)


def _response(times, values, drive, mask, hz):
    if np.count_nonzero(mask) < 3:
        return dict(amplitude_V=None, phase_vs_acceleration_deg=None)
    phase = np.exp(-2j * np.pi * hz * times[mask])
    v, a = 2 * np.mean(values[mask] * phase), 2 * np.mean(drive[mask] * phase)
    return dict(amplitude_V=float(abs(v)), phase_vs_acceleration_deg=float(np.angle(v / a, deg=True)) if abs(a) > 1e-14 else None)


def evaluate(task, x):
    """One true full-design evaluation; no hidden factors or reference solution in output."""
    d, env = design(task, x), task["private"]["task"]
    ident = hashlib.sha256(json.dumps([d, env], sort_keys=True).encode()).hexdigest()[:24]
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (ident + ".json")
    with LOCK, (CACHE/(ident+".lock")).open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            return json.loads(path.read_text()) | dict(cost=dict(full=0, numeric=0), reused=True)
        error_path = CACHE/(ident+".execution-error.json")
        if error_path.exists():
            raise RuntimeError(json.loads(error_path.read_text())["error"])
        previous_handler = signal.signal(signal.SIGALRM, _execution_timeout)
        signal.setitimer(signal.ITIMER_REAL, EXECUTION_LIMIT_S)
        try:
            actual = simulate(d, env)
        except RuntimeError as error:
            if str(error) == EXECUTION_TIMEOUT:
                error_path.write_text(json.dumps(dict(evaluation_id=ident, status="TOOL_ERROR", error=str(error),
                    limit_s=EXECUTION_LIMIT_S, scientific_result=None, origin="worker_numerical_timeout"))+"\n")
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
        result = _facts(ident, actual, env)
        path.write_text(json.dumps(result, separators=(",", ":")) + "\n")
        return result


def _facts(ident, actual, env):
    metrics, events, records = actual["metrics"], actual["events"], actual["records"]
    times = np.asarray(actual["trace"]["t"])
    y = np.asarray(actual["trace"]["y"])
    drive = np.array([acceleration(s, env) for s in times])
    first = env["fault_starts_s"][0]
    background = (times >= min(4., first * .5)) & (times < first - min(1., first * .1))
    target = np.zeros(len(times), dtype=bool)
    for start in env["fault_starts_s"]:
        edge = min(.01, env["fault_duration_s"] * .1)
        target |= (times >= start + edge) & (times < start + env["fault_duration_s"] - edge)
    base = dict(max_storage_V=float(y[:, 6].max()), storage_before_first_event_V=float(np.interp(first-.001, times, y[:, 6])),
        main_peak_voltage_V=float(abs(y[:, 2]).max()), aux_peak_voltage_V=float(abs(y[:, 5]).max()),
        envelope_peak_V=float(y[:, 7].max()), cold_charge_ready_s=metrics["cold_charge_ready_s"],
        stages={k: sum(e["event"] == k for e in events) for k in STAGES})
    windows = []
    for start in env["fault_starts_s"]:
        end = start + env["delivery_deadline_s"]
        mask = (times >= start-.01) & (times <= end)
        event_list = [{k: v for k, v in e.items() if k != "samples_g"} for e in events if start-.01 <= e["time_s"] <= end]
        windows.append(dict(start_s=start, deadline_s=end,
            stored_supply_before_V=float(np.interp(start-.001, times, y[:, 6])),
            stored_supply_after_V=float(np.interp(end, times, y[:, 6])),
            minimum_stored_supply_V=float(y[mask, 6].min()) if mask.any() else None,
            maximum_envelope_V=float(y[mask, 7].max()) if mask.any() else None,
            events=event_list,
            received_s=[r["received_s"] for r in records if start <= r["received_s"] <= end]))
    diagnostic = dict(main_background_response=_response(times, y[:, 2], drive, background, env["background_Hz"]),
        aux_target_response=_response(times, y[:, 5], drive, target, env["fault_Hz"]),
        energy_J=actual["energy_J"], minimum_active_storage_V=metrics["minimum_active_storage_V"], event_windows=windows,
        measurement="Measured response cross-phase, actual program events and supply from this full transient. No hidden calibration factors.")
    # Keep actual sampled voltages at 5 ms globally and original 1 ms around service windows.
    take = np.r_[True, np.diff(np.floor(times/.005)) > 0]
    for start in env["fault_starts_s"]:
        take |= (times >= start-.01) & (times <= start+env["delivery_deadline_s"])
    sampled = np.column_stack((times[take], drive[take]/G, y[take, 0]*1000, y[take, 2], y[take, 3]*1000, y[take, 5], y[take, 6], y[take, 7]))
    np.savez_compressed(CACHE/(ident+".npz"), samples=sampled)
    return dict(evaluation_id=ident, pass_=actual["verdict"] == "PASS", checks=actual["checks"],
        terminal={k: metrics[k] for k in ("faults", "delivered_on_time", "false_reports", "brownouts", "peak_stress_MPa", "peak_tip_mm")},
        slack=dict(delivery=metrics["delivered_on_time"]/metrics["faults"]-1, false_reports=-metrics["false_reports"],
            brownouts=-metrics["brownouts"], stress=1-metrics["peak_stress_MPa"]/env["stress_limit_MPa"],
            travel=1-metrics["peak_tip_mm"]/env["tip_travel_limit_mm"]),
        measurements=base, diagnostic=diagnostic, records=records,
        cost=dict(full=1, numeric=0), fidelity="full transient", runtime_s=actual["runtime_s"], reused=False)


def compute_bounds(task, x=None):
    """Necessary envelopes; nonnegative margin never certifies a feasible design."""
    from funnel_tasks import envelope
    return envelope(task)  # Outcome-independent public physical scope, never the hidden witness.


def feedback(task, x, result, arm="A"):
    out = {k: copy.deepcopy(result[k]) for k in ("evaluation_id", "pass_", "checks", "terminal", "slack", "measurements", "fidelity")}
    out["current_design"] = copy.deepcopy(x)
    if arm in ("B", "D"):
        out["diagnostic"] = copy.deepcopy(result["diagnostic"])
    if arm in ("C", "D"):
        out["bounds"] = compute_bounds(task, x)
    return out


def inspect_diagnostics(evaluation_id):
    return json.loads((CACHE/(evaluation_id+".json")).read_text())["diagnostic"]


def trace(evaluation_id, start_s=0., end_s=None, offset=0, limit=200):
    samples = np.load(CACHE/(evaluation_id+".npz"))["samples"]
    mask = samples[:, 0] >= start_s
    if end_s is not None:
        mask &= samples[:, 0] <= end_s
    selected = samples[mask]
    return dict(columns=TRACE_COLUMNS, samples=selected[offset:offset+limit].tolist(), total_rows=len(selected),
        next_offset=offset+limit if offset+limit < len(selected) else None,
        resolution="Actual solver samples: approximately 5 ms globally, original approximately 1 ms around delivery windows. No interpolation of hidden states.")
