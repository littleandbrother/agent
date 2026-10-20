#!/usr/bin/env python3
"""Bounded public A/R tool and separate immutable-artifact consumer.

No provider, native runtime, shell, arbitrary participant paths or hidden tasks.
The trusted host binds an output root and an S0 lease out of band. A participant
can inspect facts, check at most three candidates, and submit a proposal; only
an external invocation can create an independent acceptance receipt.
"""
from __future__ import annotations

import argparse
import collections
import copy
import csv
from decimal import Decimal
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/python/bfworld/src"))
from bfworld.agentlab.campaign20261019 import ar_service as world
from bfworld.agentlab import environment_profile

CONFIG = ROOT / "configs/studies/phase1-20261020/ar"
CONTRACT = CONFIG / "service-contract.v1.json"
CONTRACT_SHA256 = "53c29aba7b95e178ad76594ae9c240c21b91d6af5d8929e5aec8f2a7aa64853b"
CHECKER_ID = "ar-service-independent-v2"
RUNTIME = Path("/Users/depengsu/.local/share/bf-phase1-20261020/a/ar-service")
SOURCE_PATHS = (
    "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/ar.py",
    "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/ar_service.py",
    "scripts/campaign_reference.py", "scripts/campaign_ar_service.py",
    "configs/studies/phase1-20261020/ar/service-contract.v1.json",
    "configs/studies/phase1-20261020/ar/original-candidate.v1.json",
)
spec = importlib.util.spec_from_file_location("ar_legacy_reference", ROOT / "scripts/campaign_reference.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def dump(path: Path, value) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if path.is_relative_to(RUNTIME):
        reserve = 0 if path.name == "FAILED.json" else 4096
        if tree_bytes(RUNTIME) + len(data) + reserve > 220000000:
            raise RuntimeError("RETAINED_OUTPUT_CAP")
    with path.open("xb") as f:
        f.write(data)


def read_json(path: Path):
    def reject(value):
        raise ValueError("NONFINITE_JSON:" + value)
    return json.loads(path.read_text(), parse_constant=reject)


def load_contract() -> dict:
    if sha(CONTRACT) != CONTRACT_SHA256:
        raise ValueError("FROZEN_CONTRACT_DRIFT")
    c = read_json(CONTRACT)
    for entry in [c["source_conditions"], *c["parameter_provenance"]]:
        if sha(ROOT / entry["path"]) != entry["sha256"]:
            raise ValueError("FROZEN_APPARATUS_DRIFT:" + entry["path"])
    if sha(Path(c["baseline_manifest"]["path"])) != c["baseline_manifest"]["sha256"]:
        raise ValueError("BASELINE_MANIFEST_DRIFT")
    return c


def validate_profile() -> dict:
    pointer = read_json(ROOT.parent / ".bf-development-profile.json")
    profile = read_json(Path(pointer["path"]))
    env = {"BF_RUNTIME_ROOT": profile["runtime_root"], "BF_RUNTIME_CONFIG": profile["configuration"],
           "BF_HOME": profile["home"], "BF_PI_ROOT": profile["pi_root"],
           "PI_CODING_AGENT_DIR": str(Path(profile["home"]) / "pi-config"),
           "BF_DEVELOPMENT_PROFILE": pointer["path"]}
    validated = environment_profile.validate(pointer, read_json(Path(profile["configuration"])), env, ROOT.parent)
    if validated["sha256"] != load_contract()["preparation_profile_reference"]["sha256"]:
        raise ValueError("PREPARATION_PROFILE_DRIFT")
    return {"id": validated["id"], "sha256": validated["sha256"], "capabilities": validated["capabilities"],
            "runtime_root": validated["runtime_root"], "validation": "PASS"}


def tree_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink()) if path.exists() else 0


def output_guard(path: Path, *, whole_phase=False) -> dict:
    c = load_contract()["resource_caps"]
    if not path.is_absolute() or path != path.resolve() or not path.is_relative_to(RUNTIME):
        raise ValueError("ISOLATED_OUTPUT_SCOPE")
    existing = path.parent
    while not existing.exists():
        existing = existing.parent
    free = shutil.disk_usage(existing).free
    minimum = c["reserve_bytes"] + c["estimated_peak_additional_bytes"]
    if whole_phase:
        minimum = max(minimum, c["whole_phase_pre_batch_minimum_free_bytes"])
    if free < minimum:
        raise RuntimeError("STORAGE_HEADROOM_REQUIRED:" + str(free))
    if tree_bytes(RUNTIME) >= c["retained_output_cap_bytes"] - 1048576:
        raise RuntimeError("RETAINED_OUTPUT_CAP")
    return {"free_bytes": free, "required_free_bytes": minimum,
            "owner_retained_bytes_before": tree_bytes(RUNTIME), "estimated_peak_additional_bytes": c["estimated_peak_additional_bytes"]}


def original_candidate() -> dict:
    return read_json(CONFIG / "original-candidate.v1.json")


def expected_task(frozen: dict, candidate: dict) -> dict:
    """Independent input binding, without using the producer's materializer."""
    expected = copy.deepcopy(frozen)
    for key in ("capacitance_f", "off_v", "ready_v"):
        expected["device"][key] = candidate["device"][key]
    expected["device"]["sample_period_s"] = candidate["program"]["sample_period_s"]
    expected["device"]["upload_period_s"] = candidate["program"]["ack_spacing_s"]
    expected["program"] = copy.deepcopy(candidate["program"])
    expected["model_id"] = "ar-service-program-v2"
    return expected


def energy_bounds(contract=None) -> dict:
    """Necessary inequalities only; not an optimization or a proposed device.

    Most optimistic legal thresholds and full charge are allowed. Transmission,
    events, boot and early reception costs are omitted, weakening both bounds.
    After a dark brownout there is no source to reach the larger ready threshold;
    continuous sampling therefore requires power until at least end-period.
    """
    c = contract or load_contract()
    cold, history = c["tasks"]["ar-cold"], c["tasks"]["ar-history-nvm"]
    D = lambda x: Decimal(str(x))
    d = cold["device"]
    deadline = D(cold["required_first_receive_s"])
    optimistic_net = sum(max(D(0), min(deadline, D(s["end_s"])) - D(s["start_s"]))
                         * max(D(0), D(s["power_w"]) * D(d["harvest_efficiency"]) - D(d["off_power_w"]))
                         for s in cold["source_segments"] if D(s["start_s"]) < deadline)
    off_min = D(c["legal_design_space"]["device"]["off_v"]["minimum"])
    cap_upper = 2 * optimistic_net / off_min ** 2
    usable_per_f = (D(d["cap_voltage_max_v"]) ** 2 - off_min ** 2) / 2
    intervals = []
    for segment in history["source_segments"]:
        if segment["power_w"] != 0:
            continue
        length, period = D(segment["end_s"] - segment["start_s"]), D(history["required_sample_period_s"])
        powered_seconds = max(D(0), length - period)
        interior_samples = max(0, int(length // period) - 1)
        minimum_j = powered_seconds * D(d["sleep_power_w"]) + interior_samples * (D(d["sense_storage_j"]) + D(d["write_storage_j"]))
        intervals.append({"start_s": segment["start_s"], "end_s": segment["end_s"],
                          "powered_seconds_lower_bound": float(powered_seconds),
                          "interior_new_samples_lower_bound": interior_samples,
                          "minimum_storage_energy_j": float(minimum_j),
                          "capacitance_lower_bound_f": float(minimum_j / usable_per_f)})
    lower = max((r["capacitance_lower_bound_f"] for r in intervals), default=0)
    return {"schema_version": "bf-ar-necessary-bounds-v1", "contract_sha256": CONTRACT_SHA256,
            "startup": {"deadline_s": float(deadline), "optimistic_net_charge_j": float(optimistic_net),
                        "ready_voltage_infimum_v": float(off_min), "capacitance_upper_bound_f": float(cap_upper)},
            "dark_intervals": intervals, "usable_storage_per_f_j": float(usable_per_f),
            "bounds_overlap": lower <= float(cap_upper),
            "scope": "Necessary bounds for frozen zero-precharge, single-capacitor v2 legal space only. No wake-capable off-state sampler, extra source or physical generality.",
            "omitted_nonnegative_costs": ["boot", "transmission", "event writes", "ESR", "temperature uncertainty"],
            "author": "Codex-provided analytical tool; not a BF/Pi-authored D or method discovery"}


def coverage(samples: list[float], start: float, end: float, period: float) -> dict:
    """Check maximum inter-sample spacing, including both service boundaries."""
    samples = sorted(set(samples))
    previous = max((t for t in samples if t <= start), default=start)
    interior = [t for t in samples if start < t < end]
    following = min((t for t in samples if t >= end), default=end)
    points = [previous, *interior, following]
    if start in samples and points[0] != start:
        points.insert(1, start)
    missing = []
    maximum = 0.0
    for a, b in zip(points, points[1:]):
        if b > start and a < end:
            maximum = max(maximum, b - a)
            if b - a > period + 1e-7:
                missing.append([max(start, a + period), min(end, b)])
    return {"maximum_spacing_s": maximum, "missing_intervals_s": missing,
            "new_samples": sum(start <= t < end for t in samples), "period_limit_s": period,
            "start_s": start, "end_s": end}


def independent_rank(node: dict, fields: dict) -> float:
    """Postorder stack interpreter, independent of the recursive producer."""
    todo, values = [(node, False)], []
    while todo:
        n, reduce = todo.pop()
        if "const" in n:
            values.append(n["const"])
        elif "field" in n:
            values.append(fields[n["field"]])
        elif not reduce:
            todo.append((n, True))
            todo.extend((child, False) for child in reversed(n["args"]))
        else:
            count = len(n["args"])
            args = values[-count:]
            del values[-count:]
            op = n["op"]
            if op == "if":
                values.append(args[1] if args[0] else args[2])
                continue
            x, y = args
            if op == "+": result = x + y
            elif op == "-": result = x - y
            elif op == "*": result = x * y
            elif op == "min": result = min(x, y)
            elif op == "max": result = max(x, y)
            elif op == "lt": result = int(x < y)
            elif op == "le": result = int(x <= y)
            elif op == "eq": result = int(x == y)
            else: raise ValueError("INDEPENDENT_PROGRAM_OPERATOR")
            values.append(result)
    if len(values) != 1 or not math.isfinite(values[0]):
        raise ValueError("INDEPENDENT_PROGRAM_RESULT")
    return values[0]


def activity_audit(task: dict, run: dict) -> dict:
    """Tie every energy impulse and selected record to saved actions/records."""
    d = task["device"]
    rows = run["trace"]
    errors = []
    records = collections.defaultdict(list)
    actions = collections.defaultdict(list)
    packets = collections.defaultdict(list)
    evictions = collections.defaultdict(list)
    for rec in run["records"]: records[float(rec["created_s"])].append(rec)
    for a in run["activity"]: actions[float(a["time_s"])].append(a)
    for p in run["packets"]: packets[float(p["time_s"])].append(p)
    for e in run["evictions"]: evictions[float(e["time_s"])].append(e)
    arrivals = {(float(r["time_s"]), r["seq"]): r for r in run["receiver"]}
    pending, memory = {}, {}
    sync = None
    previous_powered = False
    expected_seq = 1
    all_times = set(float(r["time_s"]) for r in rows)
    if any(t not in all_times for group in (records, actions, packets, evictions) for t in group):
        errors.append("activity outside trace chronology")
    for index, row in enumerate(rows):
        t = float(row["time_s"])
        if abs(t - (index + 1) * task["dt_s"]) > 1e-9 or float(row["dt_s"]) != task["dt_s"]:
            errors.append("trace chronology")
        acts, recs, pkts = actions[t], records[t], packets[t]
        counts = collections.Counter(a["action"] for a in acts)
        expected = {"boot_j": counts["boot"] * d["boot_storage_j"],
                    "sense_j": sum(r["kind"] == 0 for r in recs) * d["sense_storage_j"],
                    "write_j": len(recs) * d["write_storage_j"], "tx_j": len(pkts) * d["tx_storage_j"]}
        before_background = float(row["start_j"]) + float(row["harvest_j"]) - float(row["spill_j"])
        if abs(float(row["spill_j"]) - max(0., float(row["start_j"]) + float(row["harvest_j"]) - d["capacitance_f"] * d["cap_voltage_max_v"] ** 2 / 2)) > 1e-10:
            errors.append("independent storage clamp")
        expected["background_j"] = min(before_background, (d["sleep_power_w"] if previous_powered else d["off_power_w"]) * task["dt_s"])
        for key, value in expected.items():
            if abs(float(row[key]) - value) > 1e-10:
                errors.append("activity energy:" + key)
        if counts["commit"] != len(recs) or counts["sample"] != sum(r["kind"] == 0 for r in recs) or counts["tx"] != len(pkts):
            errors.append("action/record/packet counts")
        for a in acts:
            if a["action"] == "brownout":
                if not d["clock_persistent"]: sync = None
                if not d["nvm_persistent"]: memory.clear(); pending.clear()
            elif a["action"] == "clock-sync":
                sync = t
        for r in recs:
            if r["seq"] != expected_seq:
                errors.append("sequence continuity")
            expected_seq += 1
            if r["kind"] in (0, 1):
                expected_known = sync is not None
                stamp = t + ((t - sync) * d["clock_ppm"] / 1e6 if sync is not None else 0) - d["stamp_age_fault_s"]
                if bool(r["time_known"]) != expected_known or (expected_known and any(abs(x - stamp) > 1e-8 for x in r["time_interval_s"])):
                    errors.append("independent clock basis")
                if not expected_known and r["time_interval_s"][1] is not None:
                    errors.append("unknown clock has exact upper time")
            memory[r["seq"]] = r
            pending[r["seq"]] = r
        for ev in evictions[t]:
            memory.pop(ev["seq"], None); pending.pop(ev["seq"], None)
        for packet in pkts:
            voltage = math.sqrt(max(0, 2 * (float(row["stored_j"]) + float(row["tx_j"])) / d["capacitance_f"])) - d["esr_ohm"] * d["tx_peak_output_a"]
            if abs(voltage - packet["loaded_v"]) > 1e-8 or voltage < d["output_v"] + d["dropout_v"]:
                errors.append("independent TX ESR/dropout")
            if packet["seq"] not in pending:
                errors.append("TX outside pending records")
            elif "program" in task:
                def fields(rec):
                    known = sync is not None and rec["time_known"]
                    local = t + (t - sync) * d["clock_ppm"] / 1e6 if sync is not None else 0
                    return {"seq": rec["seq"], "kind": rec["kind"], "age_known": int(known),
                            "age_s": max(0., local - rec["time_interval_s"][0]) if known else 0.}
                scores = {s: independent_rank(task["program"]["rank"], fields(r)) for s, r in pending.items()}
                selected = sorted(scores, key=lambda s: (scores[s], s))[0]
                dispatch = [a for a in acts if a["action"] == "program-dispatch"]
                if (packet["seq"] != selected or len(dispatch) != 1 or dispatch[0]["seq"] != selected
                        or dispatch[0]["fields"] != fields(pending[selected]) or dispatch[0]["score"] != scores[selected]):
                    errors.append("independent program consumption")
            arrival = arrivals.get((t, packet["seq"]))
            if arrival and arrival["ack"]:
                pending.pop(packet["seq"], None)
        if int(row["pending_records"]) != len(pending) or int(row["retained_records"]) != len(memory):
            errors.append("memory/pending state")
        previous_powered = bool(int(row["powered"]))
    if len(rows) != round(task["duration_s"] / task["dt_s"]):
        errors.append("trace horizon")
    if {r["seq"] for r in run["final_history"]} != set(memory):
        errors.append("final durable record set")
    for r in run["final_history"]:
        original = memory.get(r["seq"])
        expected_ack = any(a["seq"] == r["seq"] and a["ack"] for a in run["receiver"])
        if (original is None or {k: v for k, v in r.items() if k != "acked"} != {k: v for k, v in original.items() if k != "acked"}
                or bool(r["acked"]) != expected_ack):
            errors.append("final durable record content")
    if "program" in task and run.get("program_sha256") != world.identity(task["program"]):
        errors.append("program identity")
    return {"verdict": "PASS" if not errors else "FAIL", "errors": sorted(set(errors)),
            "implementation": "independent action debit, pending-state, ESR and postfix program replay"}


def service_reference(task: dict, run: dict) -> dict:
    energy = reference.energy_reference(task, run["trace"], "ar")
    legacy = reference.reference_ar(task, run, energy)
    audit = activity_audit(task, run)
    samples = [r["created_s"] for r in run["records"] if r["kind"] == 0]
    whole = coverage(samples, task["service_start_s"], task["duration_s"], task["required_sample_period_s"])
    dark = [coverage(samples, max(task["service_start_s"], s["start_s"]), s["end_s"], task["required_sample_period_s"])
            for s in task["source_segments"] if s["power_w"] == 0 and s["end_s"] > task["service_start_s"]]
    durable = {r["seq"]: r for r in run["final_history"]}
    written = {r["seq"]: r for r in run["records"]}
    retained, committed = set(durable), set(written)
    corrupted_history = [s for s in retained & committed
                         if {k: v for k, v in durable[s].items() if k != "acked"} != {k: v for k, v in written[s].items() if k != "acked"}]
    accepted = [r for r in run["receiver"] if r["accepted"]]
    delivered_gaps = [reference.decode(r["hex"], "ar") for r in accepted if reference.decode(r["hex"], "ar") and reference.decode(r["hex"], "ar")["kind"] == 2]
    unreported = [interval for interval in whole["missing_intervals_s"]
                  if not any(g["lo_s"] <= interval[0] and g["hi_s"] >= interval[1] for g in delivered_gaps)]
    eligible, late, delays = [], [], []
    for rec in run["records"]:
        t = rec["created_s"]
        if rec["kind"] != 0 or t < task["service_start_s"] or not any(a <= t < b for a, b in task["gateway_windows"]):
            continue
        eligible.append(rec["seq"])
        valid_times = []
        for r in accepted:
            if r["seq"] != rec["seq"]:
                continue
            p = reference.decode(r["hex"], "ar")
            if (p and p["known"] and not p["history"] and 0 <= r["time_s"] - t
                    and -task["max_timestamp_error_s"] <= r["time_s"] - p["lo_s"] <= task["required_sample_period_s"]):
                valid_times.append(r["time_s"])
        delay = min(valid_times) - t if valid_times else None
        delays.append({"seq": rec["seq"], "created_s": t, "fresh_receive_delay_s": delay})
        if delay is None or delay > task["required_live_receive_delay_s"]:
            late.append(rec["seq"])
    verdict = lambda ok: "PASS" if ok else "FAIL"
    gates = {}

    def add(name, result, applies=True, **facts):
        gates[name] = {"status": result if applies else "NOT_APPLICABLE", "applicable": applies, **facts}

    add("independent_energy", energy["verdict"], step_count=energy["step_count"])
    add("independent_receiver", legacy["verdicts"]["independent_receiver"], errors=legacy["receiver_errors"])
    add("independent_activity_program", audit["verdict"], errors=audit["errors"])
    add("first_fresh_receive", legacy["verdicts"]["first_receive"], first_receive_s=legacy["first_receive_s"], deadline_s=task["required_first_receive_s"])
    add("continuous_new_sampling", verdict(not whole["missing_intervals_s"]), **whole)
    add("dark_new_sampling", verdict(not any(x["missing_intervals_s"] for x in dark)), bool(dark), intervals=dark)
    add("history_retention", verdict(committed <= retained and not corrupted_history), bool(committed), committed_records=len(committed), retained_records=len(retained), missing_sequences=sorted(committed - retained), corrupted_sequences=sorted(corrupted_history))
    add("gap_reporting", verdict(not unreported), bool(whole["missing_intervals_s"]), missing_intervals=whole["missing_intervals_s"], unreported_intervals=unreported, received_gap_intervals=delivered_gaps)
    add("absolute_time", legacy["verdicts"]["absolute_time"], bool(samples), max_known_error_s=legacy["max_known_timestamp_error_s"], time_error_limit_s=task["max_timestamp_error_s"], unknown_sample_count=sum(r["kind"] == 0 and not r["time_known"] for r in run["records"]))
    add("recovery_upload", legacy["verdicts"]["recovery_upload"], task["recovery_at_s"] is not None and legacy["backlog_at_recovery"] > 0,
        recovery_at_s=task["recovery_at_s"], deadline_delay_s=120, backlog_records=legacy["backlog_at_recovery"], late_sequences=legacy["unacknowledged_at_recovery_deadline"])
    add("deduplication", legacy["verdicts"]["deduplication"], legacy["duplicate_arrivals"] > 0, duplicate_arrivals=legacy["duplicate_arrivals"], duplicate_accepts=legacy["duplicate_accepts"])
    add("fresh_receive_delay", verdict(not late), bool(eligible), eligible_new_samples=len(eligible), limit_s=task["required_live_receive_delay_s"], late_sequences=late,
        maximum_delivered_delay_s=max((x["fresh_receive_delay_s"] for x in delays if x["fresh_receive_delay_s"] is not None), default=None))
    add("temperature_accuracy", legacy["verdicts"]["temperature_accuracy"], bool(samples), maximum_error_c=legacy["max_temperature_error_c"])
    add("temperature_events", legacy["verdicts"]["temperature_event_coverage"], legacy["temperature_events_required"] > 0, required=legacy["temperature_events_required"], missed=legacy["temperature_events_missed"])
    add("physical_qualification", "UNKNOWN", scope="No hardware or calibrated source/PMIC/RF model")
    integrity = all(gates[n]["status"] == "PASS" for n in ("independent_energy", "independent_receiver", "independent_activity_program"))
    service = all(g["status"] == "PASS" for n, g in gates.items() if g["applicable"] and n != "physical_qualification")
    return {"schema_version": "bf-ar-service-matrix-v2", "checker_id": CHECKER_ID,
            "execution_integrity": verdict(integrity), "all_applicable_computational_services": verdict(service),
            "gates": gates, "sample_count": len(samples), "first_boot_s": run["first_boot_s"],
            "brownout_times_s": [a["time_s"] for a in run["activity"] if a["action"] == "brownout"],
            "live_delays": delays, "energy": energy, "activity_audit": audit,
            "legacy_v1_comparison": {"verdicts": legacy["verdicts"], "missing_sample_windows": len(legacy["missing_sample_windows"]),
                                     "dark_missing_windows": len(legacy["dark_missing_windows"]), "late_live_sequences": legacy["late_live_sequences"]},
            "scope": "Public-development nominal computation; no aggregate progress score or physical acceptance"}


def compact(result: dict) -> dict:
    return {"checker_id": result["checker_id"], "execution_integrity": result["execution_integrity"],
            "all_applicable_computational_services": result["all_applicable_computational_services"],
            "gates": {k: {"status": v["status"], "applicable": v["applicable"]} for k, v in result["gates"].items()},
            "sample_count": result["sample_count"], "first_boot_s": result["first_boot_s"],
            "first_fresh_receive_s": result["gates"]["first_fresh_receive"]["first_receive_s"],
            "brownouts": len(result["brownout_times_s"]), "late_fresh_sequences": result["gates"]["fresh_receive_delay"]["late_sequences"][:20],
            "backlog_at_recovery": result["gates"]["recovery_upload"]["backlog_records"],
            "late_recovery_records": len(result["gates"]["recovery_upload"]["late_sequences"]),
            "known_timestamp_error_s": result["gates"]["absolute_time"]["max_known_error_s"]}


def verify_historical() -> dict:
    c = load_contract()
    root = Path(c["historical_raw"]["path"])
    if sha(root / "seal.json") != c["historical_raw"]["seal_sha256"]:
        raise ValueError("HISTORICAL_SEAL_DRIFT")
    checked = reference.verify_saved(root)
    if checked["verdict"] != "PASS":
        raise ValueError("HISTORICAL_READBACK:" + json.dumps(checked))
    cases = {}
    for name, frozen in c["tasks"].items():
        task, run = load_case(root / "cases" / name)
        if task != frozen:
            raise ValueError("HISTORICAL_INPUT_DRIFT:" + name)
        cases[name] = service_reference(task, run)
    return {"schema_version": "bf-ar-historical-readback-v2", "raw_root": str(root),
            "seal_sha256": sha(root / "seal.json"), "old_independent_readback": checked,
            "phase1_independent_readback": cases, "new_simulations": 0, "paid_requests": 0, "native_calls": 0,
            "old_failure_root_preserved": str(root.parent / "verification-001/stale-failure")}


def load_case(path: Path) -> tuple[dict, dict]:
    task = read_json(path / "input.json")
    if (path / "observations.json.gz").exists():
        with gzip.open(path / "observations.json.gz", "rt") as f:
            run = json.load(f)
        with gzip.open(path / "trace.csv.gz", "rt", newline="") as f:
            run["trace"] = list(csv.DictReader(f))
    else:
        run = read_json(path / "observations.json")
        with (path / "trace.csv").open(newline="") as f:
            run["trace"] = list(csv.DictReader(f))
    return task, run


class CappedWriter:
    def __init__(self, file, limit): self.file, self.limit, self.count = file, limit, 0
    def write(self, data):
        if self.count + len(data) > self.limit:
            raise RuntimeError("CASE_OUTPUT_CAP")
        written = self.file.write(data)
        self.count += written
        return written
    def flush(self): return self.file.flush()


def save_raw(path: Path, raw: dict) -> None:
    caps = load_contract()["resource_caps"]
    for name in ("trace.csv.gz", "observations.json.gz"):
        budget = min(caps["maximum_case_output_bytes"] - tree_bytes(path),
                     caps["retained_output_cap_bytes"] - tree_bytes(RUNTIME) - 1048576)
        with (path / name).open("xb") as binary:
            capped = CappedWriter(binary, budget)
            with gzip.GzipFile(filename="", mode="wb", fileobj=capped, mtime=0) as zipped:
                with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                    if name.startswith("trace"):
                        writer = csv.DictWriter(text, fieldnames=list(raw["trace"][0]))
                        writer.writeheader(); writer.writerows(raw["trace"])
                    else:
                        encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
                        for block in encoder.iterencode({k: v for k, v in raw.items() if k != "trace"}):
                            text.write(block)


def seal_bundle(path: Path) -> dict:
    files = []
    for p in sorted(path.rglob("*")):
        if p.is_symlink():
            raise ValueError("BUNDLE_SYMLINK")
        if p.is_file(): files.append({"path": str(p.relative_to(path)), "sha256": sha(p), "bytes": p.stat().st_size})
    seal = {"schema_version": "bf-ar-bundle-seal-v1", "contract_sha256": CONTRACT_SHA256, "files": files,
            "total_bytes_before_seal": sum(p["bytes"] for p in files)}
    dump(path / "seal.json", seal)
    return seal


def verify_seal(path: Path) -> dict:
    seal = read_json(path / "seal.json")
    if seal["contract_sha256"] != CONTRACT_SHA256:
        raise ValueError("BUNDLE_CONTRACT_DRIFT")
    expected = set()
    for row in seal["files"]:
        p = Path(row["path"])
        if p.is_absolute() or ".." in p.parts or str(p) in expected:
            raise ValueError("BUNDLE_PATH")
        expected.add(str(p))
        target = path / p
        if target != target.resolve() or not target.is_file() or target.stat().st_size != row["bytes"] or sha(target) != row["sha256"]:
            raise ValueError("BUNDLE_FILE_DRIFT:" + str(p))
    actual = {str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()}
    if actual != expected | {"seal.json"}:
        raise ValueError("UNSEALED_BUNDLE_FILE")
    if sum(r["bytes"] for r in seal["files"]) > load_contract()["resource_caps"]["retained_output_cap_bytes"]:
        raise ValueError("BUNDLE_SIZE")
    return seal


def execute_candidate(candidate: dict, output: Path, *, author: dict) -> dict:
    world.validate_candidate(candidate)
    c = load_contract()
    resource = output_guard(output)
    if output.exists():
        raise FileExistsError("IMMUTABLE_OUTPUT_EXISTS")
    output.mkdir(parents=True)
    started = time.monotonic()
    try:
        dump(output / "candidate.json", candidate)
        dump(output / "author.json", author)
        dump(output / "resource-before.json", resource)
        manifest = []
        for rel in SOURCE_PATHS:
            dest = output / "source" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as f: f.write((ROOT / rel).read_bytes())
            manifest.append({"path": rel, "sha256": sha(dest)})
        dump(output / "source-manifest.json", manifest)
        reuse = world.identity(candidate) == world.identity(original_candidate())
        if reuse:
            historical = verify_historical()
        facts = {}
        for name, frozen in c["tasks"].items():
            path = output / "cases" / name
            path.mkdir(parents=True)
            if reuse:
                dump(path / "historical-ref.json", {"case": name, "raw_root": c["historical_raw"]["path"],
                     "seal_sha256": c["historical_raw"]["seal_sha256"], "input_sha256": sha(Path(c["historical_raw"]["path"]) / "cases" / name / "input.json"),
                     "reuse_identity": "exact-original-candidate; v1 raw, v2 external consumer; no new simulation"})
                result = historical["phase1_independent_readback"][name]
            else:
                task = world.apply_candidate(frozen, candidate)
                dump(path / "input.json", task)
                raw = world.simulate_ar(task)
                save_raw(path, raw)
                del raw
                task, raw = load_case(path)
                result = service_reference(task, raw)
                del raw
            dump(path / "public-facts.json", result)
            facts[name] = compact(result)
            if time.monotonic() - started > 300:
                raise RuntimeError("LOCAL_EVALUATION_WALL_CAP")
        summary = {"schema_version": "bf-ar-public-candidate-result-v1", "contract_sha256": CONTRACT_SHA256,
                   "candidate_sha256": world.identity(candidate), "world_id": world.MODEL_ID,
                   "raw_world_id": "ar-light-behavior-v1" if reuse else world.MODEL_ID,
                   "reused_historical_cases": len(facts) if reuse else 0,
                   "new_simulations": 0 if reuse else len(facts), "cases": facts,
                   "final_acceptance": "EXTERNAL_CHECK_REQUIRED", "paid_requests_in_this_tool": 0, "native_calls": 0,
                   "wall_s": time.monotonic() - started}
        dump(output / "public-result.json", summary)
        seal_bundle(output)
        return {"artifact": str(output), "seal_sha256": sha(output / "seal.json"), **summary}
    except Exception as exc:
        dump(output / "FAILED.json", {"error": type(exc).__name__, "reason": str(exc)[:2000],
                                      "wall_s": time.monotonic() - started, "preserved_partial_output": True})
        raise


def independent_check(bundle: Path, receipt: Path | None = None, *, expected_seal_sha256: str | None = None) -> dict:
    """External-only readback; never imports producer summaries as verdicts."""
    c = load_contract()
    if expected_seal_sha256 is not None and sha(bundle / "seal.json") != expected_seal_sha256:
        raise ValueError("HOST_BOUND_SEAL_DRIFT")
    seal = verify_seal(bundle)
    manifest = read_json(bundle / "source-manifest.json")
    if len(manifest) != len(SOURCE_PATHS) or {r["path"] for r in manifest} != set(SOURCE_PATHS):
        raise ValueError("SOURCE_MANIFEST_PATHS")
    for row in manifest:
        if sha(ROOT / row["path"]) != row["sha256"] or sha(bundle / "source" / row["path"]) != row["sha256"]:
            raise ValueError("CHECKER_OR_PRODUCER_SOURCE_DRIFT:" + row["path"])
    candidate = read_json(bundle / "candidate.json")
    world.validate_candidate(candidate)
    summary = read_json(bundle / "public-result.json")
    if set(summary["cases"]) != set(c["tasks"]) or {p.name for p in (bundle / "cases").iterdir()} != set(c["tasks"]):
        raise ValueError("FIXED_CASE_LIST_DRIFT")
    reuse = world.identity(candidate) == world.identity(original_candidate())
    historical = verify_historical() if reuse else None
    facts, disagreement = {}, []
    for name, frozen in c["tasks"].items():
        case = bundle / "cases" / name
        if reuse:
            ref = read_json(case / "historical-ref.json")
            raw_input = Path(c["historical_raw"]["path"]) / "cases" / name / "input.json"
            if ref["case"] != name or ref["raw_root"] != c["historical_raw"]["path"] or ref["seal_sha256"] != c["historical_raw"]["seal_sha256"] or ref["input_sha256"] != sha(raw_input):
                raise ValueError("HISTORICAL_REFERENCE_DRIFT")
            result = historical["phase1_independent_readback"][name]
        else:
            task, raw = load_case(case)
            if task != expected_task(frozen, candidate):
                raise ValueError("TASK_OR_FIXED_PARAMETER_DRIFT:" + name)
            result = service_reference(task, raw)
            del raw
        if read_json(case / "public-facts.json") != result or summary["cases"][name] != compact(result):
            disagreement.append(name)
        facts[name] = result
    if summary["candidate_sha256"] != world.identity(candidate) or summary["contract_sha256"] != CONTRACT_SHA256:
        raise ValueError("CANDIDATE_IDENTITY_DRIFT")
    integrity = not disagreement and all(r["execution_integrity"] == "PASS" for r in facts.values())
    result = {"schema_version": "bf-ar-external-check-v1", "checker_id": CHECKER_ID,
              "checker_sha256": sha(Path(__file__)), "contract_sha256": CONTRACT_SHA256,
              "candidate_sha256": world.identity(candidate), "bundle": str(bundle), "seal_sha256": sha(bundle / "seal.json"),
              "sealed_files": len(seal["files"]), "execution_integrity": "PASS" if integrity else "FAIL",
              "public_consumer_disagreements": disagreement, "cases": facts,
              "all_applicable_computational_services": "PASS" if integrity and all(r["all_applicable_computational_services"] == "PASS" for r in facts.values()) else "FAIL",
              "author": read_json(bundle / "author.json"), "new_simulations_in_readback": 0,
              "physical_qualification": "UNKNOWN", "method_benefit": "NOT_TESTED", "rsi": "NOT_TESTED"}
    if receipt is not None:
        if receipt.is_relative_to(bundle):
            raise ValueError("INDEPENDENT_RECEIPT_MUST_BE_SEPARATE")
        output_guard(receipt)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        dump(receipt, result)
    return result


def tool_definition() -> dict:
    schema = world.candidate_schema()
    definitions = schema.pop("$defs")
    definitions["candidate"] = schema
    return {"name": "bf_ar_service", "description": "Inspect frozen public A/R facts, execute a legal device/program candidate, or submit a proposal. Facts only; submission is not final acceptance. No native or arbitrary file/shell access.",
            "parameters": {"type": "object", "additionalProperties": False, "required": ["action"],
                           "properties": {"action": {"enum": ["inspect", "check", "submit"]},
                                          "topic": {"enum": ["contract", "schema", "history", "bounds"]},
                                          "candidate": {"$ref": "#/$defs/candidate"},
                                          "rationale": {"type": "string", "maxLength": 6000},
                                          "conclusion": {"enum": ["candidate", "no-go"]}}, "$defs": definitions}}


class ServiceTool:
    """Host-only context. A participant cannot set the lease, paths or limits.

    S0 owns actual provider accounting, dispatch slots and lease validation.
    This additional local guard bounds tool invocations/candidate artifacts; it
    does not assert that a JSON lease proves a model request or bill settlement.
    """
    def __init__(self, output_root: Path, *, lease: dict | None = None):
        self.root = output_root
        self.lease = copy.deepcopy(lease)
        self.started = time.monotonic()
        self.calls = 0
        self.candidates = {}
        self.submitted = False
        c = load_contract()
        if lease is not None:
            required = ("episode_id", "model", "backend", "provider_ledger", "slot_receipt", "baseline", "maximum_requests", "maximum_candidates", "maximum_wall_s")
            if any(k not in lease for k in required) or lease["baseline"] != c["baseline"]:
                raise ValueError("S0_LEASE_IDENTITY_REQUIRED")
            if any(not isinstance(lease[k], str) or not lease[k] for k in required[:5]):
                raise ValueError("S0_LEASE_IDENTITY_REQUIRED")
            for key, maximum in (("maximum_requests", 60), ("maximum_candidates", 3), ("maximum_wall_s", 3600)):
                if type(lease[key]) is not int or not 0 < lease[key] <= maximum:
                    raise ValueError("S0_LEASE_FINITE_CAP")
        output_guard(output_root)
        if output_root.exists():
            raise FileExistsError("FRESH_EPISODE_REQUIRED")
        output_root.mkdir(parents=True)
        dump(output_root / "host-context.json", {"lease": self.lease, "contract_sha256": CONTRACT_SHA256,
             "capabilities": "local public simulation only; model/native dispatch not implemented here",
             "attribution": "BF/Pi authorship requires independent S0 transport/model/usage evidence"})

    def handle(self, args: dict) -> dict:
        try:
            result = self._handle(args)
        except Exception as exc:
            if self.calls <= 60:
                try:
                    logged_args = args if isinstance(args, dict) and len(world.canonical(args)) <= 24000 else None
                except (ValueError, TypeError):
                    logged_args = None
                dump(self.root / ("call-%03d.json" % self.calls), {"args": logged_args,
                     "status": "ERROR", "error": type(exc).__name__, "reason": str(exc)[:2000], "wall_s": time.monotonic() - self.started})
            raise
        dump(self.root / ("call-%03d.json" % self.calls), {"args": args, "status": "RETURNED", "result": result,
             "wall_s": time.monotonic() - self.started})
        return result

    def _handle(self, args: dict) -> dict:
        self.calls += 1
        maximum = self.lease["maximum_requests"] if self.lease else 60
        wall = self.lease["maximum_wall_s"] if self.lease else 3600
        if self.calls > maximum or time.monotonic() - self.started > wall:
            raise RuntimeError("EPISODE_CAP_EXHAUSTED")
        if not isinstance(args, dict) or len(world.canonical(args)) > 24000:
            raise ValueError("TOOL_ARGUMENT_CAP")
        action = args.get("action")
        permitted = {"inspect": {"action", "topic"}, "check": {"action", "candidate", "rationale"},
                     "submit": {"action", "candidate", "rationale", "conclusion"}}
        if action not in permitted or set(args) - permitted[action]:
            raise ValueError("TOOL_ARGUMENT_SCHEMA")
        if self.submitted:
            raise ValueError("EPISODE_ALREADY_SUBMITTED")
        if action == "inspect":
            topic = args.get("topic", "contract")
            if topic == "contract": value = load_contract()
            elif topic == "schema": value = {"candidate_schema": world.candidate_schema(), "original_candidate": original_candidate()}
            elif topic == "history":
                full = verify_historical()
                value = {"seal_sha256": full["seal_sha256"], "old_independent_readback": full["old_independent_readback"],
                         "cases": {k: compact(v) for k, v in full["phase1_independent_readback"].items()}}
            elif topic == "bounds": value = energy_bounds()
            else: raise ValueError("INSPECT_TOPIC")
            return {"kind": "public-facts", "topic": topic, "facts": value, "final_acceptance": "EXTERNAL_CHECK_REQUIRED"}
        if self.lease is None:
            raise RuntimeError("S0_PI_LEASE_REQUIRED")
        rationale = args.get("rationale", "")
        if not isinstance(rationale, str) or len(rationale) > 6000:
            raise ValueError("RATIONALE_SCHEMA")
        candidate = args.get("candidate")
        result = None
        if candidate is not None:
            key = world.identity(candidate)
            if key not in self.candidates:
                if len(self.candidates) >= self.lease["maximum_candidates"]:
                    raise RuntimeError("CANDIDATE_CAP_EXHAUSTED")
                # Every proposed JSON, including a rejected illegal one, consumes a revision.
                attempt = self.root / ("attempt-%03d.json" % (len(self.candidates) + 1))
                dump(attempt, {"candidate": candidate, "candidate_sha256": key, "rationale": rationale})
                self.candidates[key] = {"status": "REJECTED_OR_INTERRUPTED", "attempt": str(attempt)}
                result = execute_candidate(candidate, self.root / ("candidate-%03d" % len(self.candidates)),
                         author={"kind": "S0-dispatched-participant-proposal", "host_lease": self.lease,
                                 "rationale": rationale, "authorship": "requires S0 transcript/model/request/usage binding"})
                self.candidates[key] = result
            else:
                result = self.candidates[key]
        elif action == "check":
            raise ValueError("CHECK_CANDIDATE_REQUIRED")
        if action == "submit":
            if not rationale or args.get("conclusion") not in ("candidate", "no-go") or (args["conclusion"] == "candidate" and candidate is None):
                raise ValueError("SUBMISSION_REASON_REQUIRED")
            submission = {"schema_version": "bf-ar-participant-submission-v1", "conclusion": args["conclusion"],
                          "rationale": rationale, "candidate_sha256": world.identity(candidate) if candidate is not None else None,
                          "candidate_artifact": result.get("artifact") if result else None, "host_lease": self.lease,
                          "tool_calls": self.calls, "unique_revisions": len(self.candidates), "wall_s": time.monotonic() - self.started,
                          "final_acceptance": "EXTERNAL_CHECK_REQUIRED", "bounds": energy_bounds() if args["conclusion"] == "no-go" else None}
            dump(self.root / "submission.json", submission)
            self.submitted = True
            return {"kind": "proposal-saved", "submission": str(self.root / "submission.json"), **submission}
        return {"kind": "public-execution-facts", "result": result, "final_acceptance": "EXTERNAL_CHECK_REQUIRED"}


def create_handler(output_root: str | Path, *, lease: dict | None = None):
    return ServiceTool(Path(output_root), lease=lease).handle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe", help="Print frozen public contract and single tool schema")
    sub.add_parser("bounds", help="Print necessary energy inequalities, without choosing a D")
    sub.add_parser("history", help="Read-only verify all 81 old files and 17 old outcomes; no simulations")
    validate = sub.add_parser("validate", help="Validate a candidate JSON against the frozen legal space")
    validate.add_argument("candidate", type=Path)
    prepare = sub.add_parser("prepare", help="Zero-paid original-only readback and separate external receipt")
    prepare.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify", help="External independent consumer; never changes a bundle")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--receipt", type=Path, required=True)
    check.add_argument("--expected-seal", help="S0 binds the tool-returned hash before final readback")
    serve = sub.add_parser("serve", help="Persistent trusted-host JSON-lines bridge for the one tool")
    serve.add_argument("--output", type=Path, required=True)
    serve.add_argument("--lease", type=Path, help="Trusted host only; absent means inspect only")
    serve.add_argument("--lease-sha256", help="Required when a trusted host supplies a lease")
    args = parser.parse_args()
    if args.command == "describe": result = {"contract": load_contract(), "tool": tool_definition(), "profile": validate_profile()}
    elif args.command == "bounds": result = energy_bounds()
    elif args.command == "history":
        full = verify_historical()
        result = {"old_independent_readback": full["old_independent_readback"], "seal_sha256": full["seal_sha256"],
                  "cases": {k: compact(v) for k, v in full["phase1_independent_readback"].items()}}
    elif args.command == "validate":
        candidate = read_json(args.candidate); world.validate_candidate(candidate)
        result = {"validation": "PASS", "candidate_sha256": world.identity(candidate), "contract_sha256": CONTRACT_SHA256}
    elif args.command == "prepare":
        profile = validate_profile()
        # This readback belongs to the phase admitted before implementation
        # (baseline-audit.json records >10 GB+900 MB). S0 owns phase admission;
        # this owner must retain its full 10 GB+300 MB execution headroom.
        output_guard(args.output)
        result = execute_candidate(original_candidate(), args.output / "original-readback", author={"kind": "Codex-preparation-only", "profile": profile, "new_D_choices": 0, "paid_requests": 0})
        checked = independent_check(args.output / "original-readback", args.output / "external-original-check.json")
        dump(args.output / "necessary-bounds.json", energy_bounds())
        result = {"artifact": str(args.output), "execution_integrity": checked["execution_integrity"],
                  "cases": result["cases"], "new_simulations": 0, "paid_requests": 0, "native_calls": 0}
    elif args.command == "serve":
        validate_profile()
        if args.lease is not None and (not args.lease_sha256 or sha(args.lease) != args.lease_sha256):
            raise ValueError("S0_LEASE_HASH_REQUIRED")
        handler = create_handler(args.output, lease=read_json(args.lease) if args.lease is not None else None)
        while True:
            line = sys.stdin.readline(24001)
            if not line:
                break
            if len(line) > 24000 or not line.endswith("\n"):
                raise ValueError("JSON_LINE_CAP")
            try:
                value = handler(json.loads(line))
                print(json.dumps({"ok": True, "value": value}, ensure_ascii=False, allow_nan=False), flush=True)
            except Exception as exc:
                print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)[:2000]}, ensure_ascii=False), flush=True)
        return 0
    else:
        checked = independent_check(args.bundle, args.receipt, expected_seal_sha256=args.expected_seal)
        result = {"receipt": str(args.receipt), "execution_integrity": checked["execution_integrity"],
                  "all_applicable_computational_services": checked["all_applicable_computational_services"],
                  "cases": {k: compact(v) for k, v in checked["cases"].items()}}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
