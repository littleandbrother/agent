#!/usr/bin/env python3
"""Run or independently read back the finite BFA-045 public reference list.

Only stdlib is required. No model provider, native simulator, daemon, hardware,
or original run root is opened. Never overwrite an existing output directory.
"""
from __future__ import annotations

import argparse
import copy
import csv
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/studies/parallel-20261019/reference/conditions.v1.json"
CODE = ["packages/python/bfworld/src/bfworld/agentlab/campaign20261019/ar.py",
        "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/b.py",
        "scripts/campaign_reference.py"]
MODEL_SCOPE = "nominal public-development computation; calibration and hardware UNKNOWN"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")


def merge(base: dict, patch: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def crc_reference(body: bytes) -> int:
    """Bit-level CCITT-FALSE; producer uses C-library crc_hqx instead."""
    remainder = 65535
    for byte in body:
        remainder ^= byte << 8
        for _ in range(8):
            remainder = ((remainder << 1) ^ (0x1021 if remainder & 0x8000 else 0)) & 65535
    return remainder


def decode(raw_hex: str, family: str) -> dict | None:
    raw = bytes.fromhex(raw_hex)
    size = 22 if family == "ar" else 10
    if len(raw) != size or crc_reference(raw[:-2]) != int.from_bytes(raw[-2:], "big"):
        return None
    if family == "ar":
        # Explicit slices: no import of producer frame serializer or receiver.
        return {"id": int.from_bytes(raw[0:4], "big"), "seq": int.from_bytes(raw[4:8], "big"),
                "lo_s": int.from_bytes(raw[8:12], "big", signed=True) / 1000,
                "hi_s": int.from_bytes(raw[12:16], "big", signed=True) / 1000,
                "temp_c": int.from_bytes(raw[16:18], "big", signed=True) / 100,
                "kind": raw[18], "known": bool(raw[19] & 1), "history": bool(raw[19] & 2)}
    return {"id": int.from_bytes(raw[:2], "big"), "seq": int.from_bytes(raw[2:4], "big"),
            "key": raw[4], "event": raw[5], "tag": int.from_bytes(raw[6:8], "big")}


def energy_reference(task: dict, rows: list[dict], family: str) -> dict:
    """Decimal replay plus analytic source integration from input, not totals."""
    d = task["device"]
    D = lambda x: Decimal(str(x))
    previous = D(d["capacitance_f"]) * D(d["cap_initial_voltage_v"]) ** 2 / 2
    max_j = D(d["capacitance_f"]) * D(d["cap_voltage_max_v"]) ** 2 / 2
    debits = ["background_j", "boot_j", "tx_j", "spill_j"] + (["sense_j", "write_j"] if family == "ar" else ["shunt_j"])
    totals = {k: Decimal(0) for k in ["source_j", "harvest_j", "conversion_j", *debits]}
    balance_error = voltage_error = source_error = port_error = 0.0
    bad_steps = []
    for index, row in enumerate(rows):
        t, dt = float(row["time_s"]), float(row["dt_s"])
        a, b = t - dt, t
        expected_source = sum(max(0.0, min(b, s["end_s"]) - max(a, s["start_s"])) * s["power_w"] for s in task["source_segments"])
        source_error = max(source_error, abs(float(row["source_j"]) - expected_source))
        harvest_expected = expected_source * d["harvest_efficiency"]
        if family == "ar":
            src = next(s for s in task["source_segments"] if s["start_s"] <= a + 1e-7 < s["end_s"])
            if src["voc_v"] * src["mpp_ratio"] < d["cold_start_voltage_v"] or src["power_w"] < d["cold_start_power_w"]:
                harvest_expected = 0
            port_error = max(port_error, abs(float(row["source_v"]) * float(row["source_a"]) * dt - expected_source))
        source_error = max(source_error, abs(float(row["harvest_j"]) - harvest_expected),
                           abs(float(row["conversion_j"]) - (expected_source - harvest_expected)))
        predicted = previous + D(row["harvest_j"]) - sum((D(row[k]) for k in debits), Decimal(0))
        end = D(row["stored_j"])
        error = max(abs(predicted - end), abs(previous - D(row["start_j"])))
        balance_error = max(balance_error, float(error))
        v = math.sqrt(max(0.0, 2 * float(end) / d["capacitance_f"]))
        voltage_error = max(voltage_error, abs(v - float(row["voltage_v"])))
        if error > D("1e-10") or end < D("-1e-12") or end > max_j + D("1e-10") or any(D(row[k]) < 0 for k in totals):
            bad_steps.append(index)
        for k in totals:
            totals[k] += D(row[k])
        previous = end
    source_integral = sum((D(s["end_s"]) - D(s["start_s"])) * D(s["power_w"]) for s in task["source_segments"])
    source_total_error = abs(float(totals["source_j"] - source_integral))
    passed = not bad_steps and balance_error < 1e-10 and voltage_error < 1e-9 and source_error < 1e-10 and port_error < 1e-10 and source_total_error < 1e-8
    return {"verdict": "PASS" if passed else "FAIL", "implementation": "independent Decimal ledger and piecewise input integral",
            "max_balance_error_j": balance_error, "max_voltage_error_v": voltage_error,
            "max_source_step_error_j": source_error, "source_total_error_j": source_total_error,
            "max_port_vi_error_j": port_error, "bad_steps": bad_steps[:20],
            "source_integral_j": float(source_integral), "totals_j": {k: float(v) for k, v in totals.items()},
            "final_storage_j": float(previous), "step_count": len(rows),
            "time_resolution_s": task["dt_s"], "physical_calibration": "UNKNOWN"}


def _missed(samples: list, start: float, end: float, period: float) -> list:
    result = []
    a = start
    while a + period <= end + 1e-8:
        if not any(a <= t < a + period for t in samples):
            result.append([a, a + period])
        a += period
    return result


def reference_ar(task: dict, run: dict, energy: dict) -> dict:
    records = {r["seq"]: r for r in run["records"]}
    final = {r["seq"] for r in run["final_history"]}
    samples = [r["created_s"] for r in records.values() if r["kind"] == 0]
    seen, accepted, errors, stale = set(), [], [], []
    ack_left = task["device"]["ack_drop_first_n"]
    for row in run["receiver"]:
        p = decode(row["hex"], "ar")
        record = records.get(row["seq"])
        valid = bool(p and record and p["id"] == task["device"]["id"] and p["seq"] == row["seq"])
        if valid:
            if p["kind"] == 2:
                valid = p["hi_s"] >= p["lo_s"]
            elif p["known"] and not p["history"] and row["time_s"] - p["lo_s"] > task["required_sample_period_s"]:
                valid = False
                stale.append(row["seq"])
            upper = record["time_interval_s"][1]
            if (p["kind"] != record["kind"] or p["known"] != record["time_known"]
                    or abs(p["temp_c"] - record["temperature_c"]) > .0051
                    or abs(p["lo_s"] - record["time_interval_s"][0]) > .00051
                    or abs(p["hi_s"] - (upper if upper is not None else -.001)) > .00051
                    or p["history"] != (row["time_s"] - record["created_s"] > task["required_sample_period_s"])):
                errors.append("payload-record mismatch")
        duplicate = row["seq"] in seen
        accept = valid and (not duplicate or not task["device"]["receiver_dedup"])
        expected_ack = valid and ack_left == 0
        if valid:
            seen.add(row["seq"])
            if ack_left:
                ack_left -= 1
        if bool(row["valid"]) != valid or bool(row["accepted"]) != accept or bool(row["ack"]) != expected_ack:
            errors.append("independent receiver/ACK disagreement")
        if accept:
            accepted.append({**row, "decoded": p, "record": record})
    expected_arrivals = [p for p in run["packets"] if any(a <= p["time_s"] < b for a, b in task["gateway_windows"])]
    if [(p["time_s"], p["hex"]) for p in expected_arrivals] != [(p["time_s"], p["hex"]) for p in run["receiver"]]:
        errors.append("gateway packet/receiver mismatch")
    accepted_samples = [r for r in accepted if r["record"]["kind"] == 0]
    fresh_samples = [r for r in accepted_samples if r["decoded"]["known"] and not r["decoded"]["history"]
                     and -task["max_timestamp_error_s"] <= r["time_s"] - r["decoded"]["lo_s"] <= task["required_sample_period_s"]]
    first = min((r["time_s"] for r in fresh_samples), default=None)
    missing = _missed(samples, task["service_start_s"], task["duration_s"], task["required_sample_period_s"])
    dark_missing = []
    for s in task["source_segments"]:
        if s["power_w"] == 0:
            dark_missing.extend(_missed(samples, max(task["service_start_s"], s["start_s"]), s["end_s"], task["required_sample_period_s"]))
    late_live, temp_errors, timestamp_errors = [], [], []
    for record in records.values():
        if record["kind"] != 0:
            continue
        t = record["created_s"]
        truth = next(s[2] for s in task["temperature_segments"] if s[0] <= t < s[1])
        temp_errors.append(abs(record["temperature_c"] - truth))
        if record["time_known"]:
            timestamp_errors.append(abs(t - record["time_interval_s"][0]))
        if any(a <= t < b for a, b in task["gateway_windows"]) and t >= task["service_start_s"]:
            arrivals = [r["time_s"] for r in accepted_samples if r["seq"] == record["seq"]]
            if not arrivals or min(arrivals) - t > task["required_live_receive_delay_s"]:
                late_live.append(record["seq"])
    delivered_gaps = [r["decoded"] for r in accepted if r["record"]["kind"] == 2]
    uncovered = [m for m in missing if not any(g["lo_s"] <= m[0] and g["hi_s"] >= m[1] for g in delivered_gaps)]
    resets = [a for a in run["activity"] if a["action"] == "brownout"]
    duplicate_accepts = len(accepted) - len({r["seq"] for r in accepted})
    recovery = task["recovery_at_s"]
    backlog, not_uploaded = [], []
    if recovery is not None:
        for seq, rec in records.items():
            if rec["created_s"] < recovery and not any(r["seq"] == seq and r["ack"] and r["time_s"] < recovery for r in run["receiver"]):
                backlog.append(seq)
                if not any(r["seq"] == seq and r["ack"] and recovery <= r["time_s"] <= recovery + 120 for r in run["receiver"]):
                    not_uploaded.append(seq)
    event = task["temperature_event"]
    events = [s for s in task["temperature_segments"] if event["enabled"] and s[2] > event["threshold_c"] and s[1] - s[0] >= event["minimum_duration_s"]]
    missing_events = [s for s in events if not any(r["kind"] == 1 and s[0] + event["minimum_duration_s"] <= r["created_s"] <= s[1] + task["required_sample_period_s"] for r in records.values())]
    v = lambda ok: "PASS" if ok else "FAIL"
    verdicts = {"independent_energy": energy["verdict"], "independent_receiver": v(not errors),
                "first_receive": v(first is not None and first <= task["required_first_receive_s"]),
                "freshness": v(not stale), "temperature_accuracy": v(max(temp_errors, default=math.inf) <= task["required_temperature_error_c"]),
                "continuous_new_sampling": v(not missing), "dark_new_sampling": v(not dark_missing),
                "live_service": v(not missing and not late_live and not stale and first is not None),
                "history_retention": v(set(records) <= final), "gap_reporting": v(not uncovered),
                "deduplication": v(duplicate_accepts == 0), "recovery_upload": v(not not_uploaded),
                "absolute_time": "UNKNOWN" if (resets and not task["device"]["clock_persistent"]) or any(not r["time_known"] and r["kind"] != 2 for r in records.values()) else v(max(timestamp_errors, default=0) <= task["max_timestamp_error_s"]),
                "temperature_event_coverage": v(not missing_events), "physical_qualification": "UNKNOWN"}
    return {"verdicts": verdicts, "first_receive_s": first, "first_boot_s": run["first_boot_s"],
            "committed_records": len(records), "retained_records": len(final), "sample_count": len(samples),
            "accepted_unique_records": len({r["seq"] for r in accepted}), "duplicate_arrivals": sum(r["duplicate"] for r in run["receiver"]),
            "duplicate_accepts": duplicate_accepts, "brownouts": len(resets), "backlog_at_recovery": len(backlog),
            "unacknowledged_at_recovery_deadline": not_uploaded, "missing_sample_windows": missing,
            "dark_missing_windows": dark_missing, "unreported_missing_windows": uncovered, "late_live_sequences": late_live,
            "missing_retained_sequences": sorted(set(records) - final), "temperature_events_required": len(events),
            "temperature_events_missed": len(missing_events), "delivered_gap_intervals": delivered_gaps,
            "max_temperature_error_c": max(temp_errors, default=None), "max_known_timestamp_error_s": max(timestamp_errors, default=None),
            "receiver_errors": errors, "gate_applicability": {"dark_new_sampling": bool(dark_missing or any(s["power_w"] == 0 for s in task["source_segments"])), "recovery_upload": recovery is not None, "temperature_event_coverage": event["enabled"]},
            "vacuous_checks": "An empty dark/event/recovery set has PASS as a logical check only; gate_applicability marks whether it was exercised."}


def reference_b(task: dict, run: dict, energy: dict) -> dict:
    valid, errors = [], []
    for row in run["packets"]:
        p = decode(row["hex"], "b")
        if p and p == {"id": task["device"]["id"], "seq": 1, "key": 1, "event": 1, "tag": 0xB026}:
            valid.append(row)
        else:
            errors.append("invalid event/CRC/identity")
    on_time = [p for p in valid if task["event_s"] <= p["time_s"] <= task["event_s"] + task["deadline_s"]]
    resets = [a for a in run["activity"] if a["action"] == "brownout" and a["time_s"] < task["deadline_s"]]
    transient_failures = [r for r in run["trace"] if float(r["tx_j"]) > 0 and (float(r["loaded_v"]) < task["device"]["output_v"] or float(r["stored_j"]) < task["device"]["capacitance_f"] * task["device"]["off_v"] ** 2 / 2)]
    # Independent ESR equation at each attempted transmit, not only successful frames.
    esr_error = max((abs(float(r["loaded_v"]) - (math.sqrt(2 * (float(r["stored_j"]) + float(r["tx_j"])) / task["device"]["capacitance_f"]) - task["device"]["esr_ohm"] * task["device"]["tx_current_a"])) for r in run["trace"] if float(r["tx_j"]) > 0), default=0)
    if esr_error > 1e-9:
        errors.append("independent ESR equation mismatch")
    success = bool(on_time) and len(valid) == 1
    return {"verdicts": {"independent_energy": energy["verdict"], "independent_receiver": "PASS" if not errors else "FAIL",
                         "event_receive": "PASS" if success else "FAIL", "deduplication": "PASS" if len(valid) <= 1 else "FAIL",
                         "transient_voltage": "PASS" if not transient_failures else "FAIL",
                         "event_preserved_after_reset": "PASS" if success and resets else "FAIL",
                         "physical_qualification": "UNKNOWN"},
            "first_receive_s": min((p["time_s"] for p in valid), default=None), "first_boot_s": run["first_boot_s"],
            "brownouts_before_deadline": len(resets), "captured_before_reset": any(a["event_was_captured"] for a in resets),
            "transient_failed_steps": len(transient_failures), "max_esr_equation_error_v": esr_error,
            "received_frames": len(valid), "receiver_errors": errors,
            "datasheet_range_check": "PASS" if 120e-6 - 1e-12 <= energy["source_integral_j"] <= 210e-6 + 1e-12 else "OUTSIDE_RANGE",
            "datasheet_scope": "Range consistency only. Synthetic port waveform and efficiency are uncalibrated; no ECO260 load-response qualification."}


def read_case(path: Path) -> tuple[dict, dict, dict]:
    task = json.loads((path / "input.json").read_text())
    run = json.loads((path / "observations.json").read_text())
    with (path / "trace.csv").open(newline="") as f:
        run["trace"] = list(csv.DictReader(f))
    family = "ar" if task["model_id"].startswith("ar-") else "b"
    energy = energy_reference(task, run["trace"], family)
    result = (reference_ar if family == "ar" else reference_b)(task, run, energy)
    return task, result, energy


def verify_saved(output: Path) -> dict:
    seal = json.loads((output / "seal.json").read_text())
    mismatches = [e["path"] for e in seal["files"] if not (output / e["path"]).is_file() or sha(output / e["path"]) != e["sha256"]]
    if mismatches:
        return {"verdict": "FAIL", "reason": "sealed-file mismatch", "paths": mismatches}
    summary = json.loads((output / "results.json").read_text())
    for row in summary["cases"]:
        _, result, energy = read_case(output / "cases" / row["id"])
        saved = json.loads((output / "cases" / row["id"] / "result.json").read_text())
        if result != saved["reference"] or energy != saved["energy"]:
            return {"verdict": "FAIL", "reason": "independent saved readback disagreement", "case": row["id"]}
    return {"verdict": "PASS", "sealed_files": len(seal["files"]), "cases": len(summary["cases"]), "new_simulations": 0, "paid_model_requests": 0, "native_calls": 0}


def run_reference(output: Path, config_path: Path = CONFIG) -> dict:
    from bfworld.agentlab.campaign20261019.ar import simulate_ar
    from bfworld.agentlab.campaign20261019.b import simulate_b
    started = time.monotonic()
    protocol = json.loads(config_path.read_text())
    if not output.is_absolute():
        raise ValueError("output must be an absolute new directory")
    if output.exists():
        raise FileExistsError("immutable outputs cannot be overwritten")
    if shutil.disk_usage(output.parent).free < protocol["resource_caps"]["minimum_free_bytes"]:
        raise RuntimeError("free-space gate")
    output.mkdir()
    dump(output / "protocol.json", protocol)
    candidates = output / "candidate"
    candidates.mkdir()
    source_paths = [*CODE, str(config_path.relative_to(ROOT))]
    for p in (ROOT / "configs/studies/parallel-20261019/reference/candidate").glob("*"):
        if p.is_file():
            source_paths.append(str(p.relative_to(ROOT)))
    source_paths += [str(p.relative_to(ROOT)) for p in (ROOT / "docs/research/parallel-20261019/reference/sources").glob("*") if p.is_file()]
    source_manifest = []
    for rel in source_paths:
        dest = candidates / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dest)
        source_manifest.append({"path": rel, "sha256": sha(dest), "bytes": dest.stat().st_size})
    dump(output / "candidate-manifest.json", source_manifest)
    identity = hashlib.sha256(json.dumps(source_manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    results = []
    for family in ("ar", "b"):
        for condition in protocol[f"{family}_cases"]:
            if time.monotonic() - started > protocol["resource_caps"]["runner_wall_seconds"]:
                raise TimeoutError("finite runner wall-clock gate")
            task = merge(protocol[f"{family}_base"], condition["patch"])
            task.update(id=condition["id"], task_id=condition["task_id"], source_baseline=protocol["baseline"])
            path = output / "cases" / condition["id"]
            path.mkdir(parents=True)
            dump(path / "input.json", task)
            raw = (simulate_ar if family == "ar" else simulate_b)(task)
            trace = raw.pop("trace")
            with (path / "trace.csv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(trace[0]))
                writer.writeheader()
                writer.writerows(trace)
            dump(path / "observations.json", raw)
            _, result, energy = read_case(path)
            expect = {k: {"expected": v, "actual": result["verdicts"][k], "matched": v == result["verdicts"][k]} for k, v in condition["expected"].items()}
            control = "PASS" if all(r["matched"] for r in expect.values()) else "FAIL"
            saved = {"schema_version": "campaign-result-v1", "id": condition["id"], "task_id": condition["task_id"],
                     "candidate_id": "CR-" + identity, "input_sha256": sha(path / "input.json"),
                     "energy": energy, "reference": result, "predeclared_control": control, "expectations": expect,
                     "scope": MODEL_SCOPE}
            dump(path / "result.json", saved)
            results.append({"id": condition["id"], "task_id": condition["task_id"], "predeclared_control": control,
                            "verdicts": result["verdicts"], "first_receive_s": result["first_receive_s"], "source_j": energy["source_integral_j"]})
            if energy["verdict"] != "PASS" or result["verdicts"]["independent_receiver"] != "PASS":
                dump(output / "STOP.json", {"case": condition["id"], "reason": "independent reference disagreement", "result": saved})
                raise RuntimeError("independent reference gate; raw failure retained")
    elapsed = time.monotonic() - started
    summary = {"schema_version": "campaign-result-v1", "baseline": protocol["baseline"], "candidate_id": "CR-" + identity,
               "protocol_sha256": sha(config_path), "task_count": protocol["task_count"], "case_count": len(results), "cases": results,
               "predeclared_controls": "PASS" if all(c["predeclared_control"] == "PASS" for c in results) else "FAIL",
               "qualification": protocol["qualification"], "resources": {"elapsed_s": elapsed, "paid_model_requests": 0,
               "native_eda_calls": 0, "hardware_writes": 0, "original_owner_resume": False}, "scope": MODEL_SCOPE}
    dump(output / "results.json", summary)
    with (output / "results.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "task_id", "gate", "verdict"])
        for case in results:
            for gate, value in case["verdicts"].items():
                w.writerow([case["id"], case["task_id"], gate, value])
    files = [{"path": str(p.relative_to(output)), "sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(output.rglob("*")) if p.is_file()]
    total = sum(p["bytes"] for p in files)
    if total > protocol["resource_caps"]["output_bytes"]:
        raise RuntimeError("output-size gate")
    dump(output / "seal.json", {"schema_version": "campaign-reference-seal-v1", "files": files, "bytes_before_seal": total,
                                "candidate_id": summary["candidate_id"], "new_paid_requests": 0, "new_native_calls": 0})
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    p.add_argument("--verify-run", type=Path)
    args = p.parse_args()
    if bool(args.output) == bool(args.verify_run):
        p.error("choose exactly one of --output and --verify-run")
    if args.verify_run:
        result = verify_saved(args.verify_run)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["verdict"] == "PASS" else 1
    summary = run_reference(args.output)
    print(json.dumps({k: summary[k] for k in ("candidate_id", "case_count", "predeclared_controls", "resources", "scope")}, ensure_ascii=False))
    return 0 if summary["predeclared_controls"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
