#!/usr/bin/env python3
"""Rebuild E-series tables from sealed saved data; Python standard library only.

No network, model, simulator, qualifier, consumer, or archived Python is invoked.
Absolute paths inside historical records are provenance strings, never read targets.
"""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


class SavedData:
    def __init__(self, root):
        self.root = Path(root).resolve()
        manifest_bytes = (self.root / "manifest.json").read_bytes()
        self.manifest_sha256 = digest(manifest_bytes)
        self.manifest = json.loads(manifest_bytes)
        self.files = {}
        self.bytes_verified = 0
        for item in self.manifest["files"]:
            identity, relative = item["id"], Path(item["path"])
            require(identity not in self.files, "Duplicate saved-data identity: " + identity)
            require(not relative.is_absolute() and ".." not in relative.parts, "Nonportable manifest path")
            path = (self.root / relative).resolve()
            require(path.is_relative_to(self.root), "Saved input escapes --data-root")
            raw = path.read_bytes()  # Missing files fail; no historical-path fallback.
            require(len(raw) == item["bytes"] and digest(raw) == item["sha256"], "Saved input hash mismatch: " + identity)
            self.files[identity] = {**item, "resolved": path}
            self.bytes_verified += len(raw)

    def read(self, identity):
        return json.loads(self.files[identity]["resolved"].read_text())

    def sha(self, identity):
        return self.files[identity]["sha256"]


def status(row):
    return row.get("service") or "INCOMPLETE"


def close(a, b, label):
    require(math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-10), label)


def analyze(data):
    structural = data.read("structural-results")
    witness_rows = []
    for pair in structural["pairs"]:
        require(pair["current_same"] and pair["current_both_pass"] and pair["jointly_legal"] and pair["intervention_diverges"], "Structural witness boundary")
        cases = pair["cases"]
        require(len(cases) == 2 and cases[0]["current_representation"] == cases[1]["current_representation"], "Current representations differ")
        require({r["intervention"]["verdict"] for r in cases} == {"PASS", "FAIL"}, "No intervention separation")
        for case in cases:
            witness_rows.append({"pair": pair["pair"], "world": case["world"], "current": case["current"]["verdict"],
                                 "intervention": case["intervention"]["verdict"], "margin_uj": case["intervention"].get("service_margin_uj"),
                                 "delivered": case["intervention"]["delivered_count"]})
    require(len(structural["reference_checks"]) == 16, "Reference/resolution check count")
    require(all(r["primary"]["verdict"] == r["reference"]["verdict"] for r in structural["reference_checks"]), "Saved numerical agreement")
    require(len(structural["static_sufficient_rows"]) == 28 and all(r["prediction"] == r["reference_verdict"] for r in structural["static_sufficient_rows"]), "Strong static grid")
    require(len(structural["additive_static_rows"]) == 5 and all(r["static"] == r["reference"] for r in structural["additive_static_rows"]), "Additive negative control")
    require(all(structural["negative_controls"].values()), "Saved structural negative control")
    observations = structural["observation_summary"]
    by_obs = {r["arm"]: r for r in observations}
    require(by_obs["selected"]["read_bytes"] == by_obs["mechanism-spec"]["read_bytes"] == 103, "Selector/minimal-static tie")
    reference_rows = []
    for case in data.read("p1-mechanisms")["b_reference"]["saved_outcomes"]:
        raw = data.read("reference-" + case["id"])
        ref = raw["reference"]
        require(case["verdicts"] == ref["verdicts"], "Reference mapping mismatch")
        require(ref["verdicts"]["physical_qualification"] == "UNKNOWN", "Reference physical scope")
        reference_rows.append({"case": case["id"], "source_uj": raw["energy"]["source_integral_j"] * 1e6,
                               "first_receive_ms": None if ref["first_receive_s"] is None else ref["first_receive_s"] * 1000,
                               "service": ref["verdicts"]["event_receive"], "rail": ref["verdicts"]["transient_voltage"]})

    original = data.read("p2-original_result")
    require(not original["qualified_observation"] and not original["real_consumer_executed"], "Original E5 failure was replaced")
    require(original["accounting"]["requests"] == 6, "Original failed E5 costs")
    consumer, service = data.read("p2-consumer"), data.read("p2-service")
    require(consumer["observation"]["qualification_kind"] == "POSTHOC_HOST_ADAPTER_REEVALUATION", "Post-hoc scope missing")
    require(consumer["before"]["judgment"] == "UNKNOWN" and consumer["after"]["used_observation"], "Typed consumer change")
    require([service[k]["complete_service"] for k in ("original", "selected", "static_complete")] == ["FAIL", "PASS", "PASS"], "Post-hoc/static results")

    actual, tables = data.read("p3-actual-comparison"), data.read("p3-main-tables")
    require(tables["source_bindings"], "Missing matrix provenance")
    groups = list(actual["groups"].values())
    require(len(groups) == 112 and sum(len(g["episodes"]) for g in groups) == 140, "Group/episode units")
    require(sum(g["requests"] for g in groups) == tables["accounting"]["requests"] == 771, "Matrix request accounting")
    close(sum(g["settled_upper_usd"] for g in groups), 5.4478605, "Matrix dollars")
    require(all(not g["unknown_usage"] and g["fresh_task_entry"] for g in groups), "Usage/fresh-entry boundary")
    require({tuple(g["reported_models"]) for g in groups} == {("deepseek-flash",)}, "Ambiguous reported model alias")
    require(len({g["initial_cache_sha256"] for g in groups}) == 1, "Initial cache mismatch")
    formal_groups = [g for g in groups if g["stage"] == "formal"]
    require(len(formal_groups) == 96 and len({g["world"] for g in formal_groups}) == 4, "Formal task denominator")
    formal = []
    displayed = ["average-energy", "rich-static", "complete-raw", "executable-response", "live-e5", "e4-rich-static-table"]
    saved = {r["condition"]: r for r in tables["formal"]}
    for condition in displayed:
        rows = [g for g in formal_groups if g["condition"] == condition]
        counts = Counter(g["complete_service"] for g in rows)
        require(len(rows) == 12 and dict(counts) == saved[condition]["service_counts"], "Formal arm counts: " + condition)
        require(sum(g["requests"] for g in rows) == saved[condition]["requests"], "Formal arm requests")
        formal.append({"condition": condition, "PASS": counts["PASS"], "FAIL": counts["FAIL"], "INCOMPLETE": counts["INCOMPLETE"],
                       "requests": sum(g["requests"] for g in rows), "usd": sum(g["settled_upper_usd"] for g in rows), "wall_s": sum(g["wall_s"] for g in rows)})
    require([r["PASS"] for r in formal] == [8, 12, 12, 12, 7, 12], "Main outcome vector")
    e5 = [r for r in tables["e5_audit"] if r["stage"] == "formal"]
    passed, incomplete = [r for r in e5 if r["complete_service"] == "PASS"], [r for r in e5 if r["complete_service"] == "INCOMPLETE"]
    require(len(e5) == 12 and len(passed) == 7 and len(incomplete) == 5, "E5 complete denominator")
    require(Counter(r["mode"] for r in passed) == {"selection": 6, "construction": 1}, "E5 discovery-mode counts")
    require(all(r["typed_observation_consumed"] and r["qualification"]["status"] == "EXTERNAL_PASS" for r in passed), "Prospective consumer chain")
    require(sum(r["design_changed"] for r in passed) == 6 and not any(r["new_physical_measurement"] for r in e5), "E5 change/measurement scope")
    unit_bad = [r for r in incomplete if any("SOURCE_UNIT_UNAVAILABLE" in a for a in r["failed_actions"])]
    typed_bad = [r for r in incomplete if any("NO_TYPED_CONSUMER_MATCH" in a for a in r["failed_actions"])]
    require(len(unit_bad) == 4 and len(typed_bad) == 1, "E5 group failure categories")
    e4 = [r for r in tables["e4_pairs"] if r["stage"] == "formal"]
    require(len(e4) == 12 and all(r["identical_decoded_initial_packet"] and r["identical_tool"] for r in e4), "Saved equal-information receipts")
    require(sum(r["json_requests"] for r in e4) == sum(r["table_requests"] for r in e4) == 65, "E4 request tie")
    ordered = data.read("p3-ordered-selected-witnesses")
    require(ordered["comparison_sha256"] == data.sha("p3-actual-comparison"), "Ordered witness source hash")
    require(len(ordered["witnesses"]) == 4 and len({r["execution_key"] for r in ordered["witnesses"]}) == 1, "Four selections/one response")

    o0 = []
    for name in ["candidate", "fixed-periodic", "rich-state"]:
        raw = data.read("o0-O0-" + name)
        ex = raw["external_result"]["execution"]
        o0.append({"arm": name, "poll_s": ex["design"]["sample_period_s"], "matched": ex["matched_event_count"],
                   "service": ex["complete_service"], "self_judgment": raw["external_result"]["service_judgment"],
                   "requests": raw["accounting"]["requests"], "packets": ex["accepted_packets"], "execution_key": ex["execution_key"]})
    require(o0[0]["execution_key"] == o0[2]["execution_key"] and o0[0]["self_judgment"] == "UNKNOWN", "O0 shared response and scoped judgment")
    require(sum(r["requests"] for r in o0) == 18 and [r["service"] for r in o0] == ["PASS", "FAIL", "PASS"], "O0 totals")

    a4, f4 = data.read("p4-actual-results"), data.read("p4-final-details")
    require(f4["actual_results_sha256"] == data.sha("p4-actual-results"), "Final details source hash")
    require(len(a4["rows"]) == 77 and a4["effective_canonical_cells"] == 73, "Actual/logical denominator")
    require(sum(r["usage"]["requests"] for r in a4["rows"]) == 367 and all(r["usage"]["status"] == "SETTLED" for r in a4["rows"]), "Full actual accounting")
    close(sum(r["usage"]["usd"] for r in a4["rows"]), 3.1767228, "Actual dollars")
    require(a4["G1_formation_events"] == 1 and not a4["default_H0_changed"], "One formation/unchanged H0")
    freeze = data.read("p4-final-selection-freeze")
    require(freeze["all_final_episodes_not_started"] and not freeze["final_results_consulted"], "Selection/final exposure boundary")
    require(canonical(data.read("p4-selected-methods")) == freeze["selected_methods_sha256"], "Frozen methods canonical hash")
    final_rows = f4["rows"]
    require(len(final_rows) == 27 and len({r["episode"] for r in final_rows}) == 27, "Final cell count")
    final_arms = []
    for arm, expected in [("H0", (7, 1, 1)), ("G0", (6, 1, 2)), ("G1", (8, 0, 1))]:
        counts = Counter(status(r) for r in final_rows if r["arm"] == arm)
        require(tuple(counts[k] for k in ["PASS", "FAIL", "INCOMPLETE"]) == expected, "Final arm result")
        final_arms.append({"arm": arm, **{k: counts[k] for k in ["PASS", "FAIL", "INCOMPLETE"]}})
    o_rows = [r for r in final_rows if r["task"] == "p4-o-unexposed-waveform-v1"]
    require(len(o_rows) == 9 and all(status(r) == "PASS" for r in final_rows if r not in o_rows), "O versus 18 digital cells")
    missing = [r for r in o_rows if r["design"] is None]
    require(len(missing) == 4, "Censoring denominator")
    for row in missing:
        meta = row["last_assistant_metadata"]
        require(meta["stop_reason"] == "length" and meta["usage"]["output"] == meta["usage"]["reasoning"] == 32768, "Token-censoring metadata")
    o_results, timing = [], []
    for row in o_rows:
        design, events = row["design"], row.get("O_events")
        item = {"lineage": row["lineage"], "arm": row["arm"], "episode": row["episode"], "poll_s": None, "retry_s": None,
                "event_passes": None, "max_error_s": None, "service": status(row)}
        if design:
            require(events["matched"] == events["expected"] == 8 and events["accepted_packets"] == 18 and row["energy"] == "PASS", "Event matching/energy invariant")
            item.update(poll_s=design["sample_period_s"], retry_s=design["retry_s"], event_passes=events["pass_count"],
                        max_error_s=max(e["absolute_stamp_error_s"] for e in events["per_event"]))
            for event in events["per_event"]:
                close(abs(event["encoded_stamp_s"]-event["time_s"]), event["absolute_stamp_error_s"], "Encoded timestamp arithmetic")
                if event["verdict"] == "FAIL":
                    require(event["kind"] == "stop" and event["receive_s"]-event["time_s"] < 1, "Receipt versus encoded-time boundary")
                    timing.append({"episode": row["episode"], **{k: event[k] for k in ["time_s", "receive_s", "encoded_stamp_s", "absolute_stamp_error_s"]}})
        o_results.append(item)
    require(len(timing) == 4 and {round(e["absolute_stamp_error_s"], 3) for e in timing} == {1.004, 1.103}, "Two stop failures per failed design")
    require([r["poll_s"] for r in o_results if r["service"] == "PASS"] == [0.75, 0.75, 0.75], "Saved sampling association")
    ar = data.read("ar-preserved-result")
    require(ar["product_acceptance"] == "NOT_ACCEPTED" and ar["strict_FIFO"] == "FAIL", "Historical product failures")
    return {"scope": "Saved-data arithmetic/readback only; zero new scientific, provider or native execution", "structural_witnesses": witness_rows,
            "reference_controls": reference_rows, "observation_costs": observations, "formal": formal,
            "per_task": {c: saved[c]["per_task_counts"] for c in displayed}, "pilot": tables["pilot"], "e5": e5,
            "e5_failure_groups": {"source_unit": [r["group"] for r in unit_bad], "typed_consumer": [r["group"] for r in typed_bad]},
            "ordered_selections": 4, "ordered_distinct_responses": 1, "O0": o0, "O_final": o_results, "O_failed_times": timing,
            "final_arms": final_arms, "incomplete_O_episodes": [r["episode"] for r in missing],
            "accounting": {"original_failed_E5": original["accounting"], "controlled_matrix": tables["accounting"], "O_and_procedure_campaign": a4["accounting"],
                           "no_sum_across_subsets": "O0 is included in the 367-request campaign; E4 JSON is the rich-static shared cell. Campaign totals include conditions outside displayed interface rows."},
            "physical_qualification": "UNKNOWN", "product_acceptance": "NOT_ACCEPTED", "default_H0_changed": False,
            "new_provider_requests": 0, "new_scientific_executions": 0, "new_native_mutations": 0}


LABELS = {"average-energy": "Average energy", "rich-static": "Rich static / E4 JSON", "complete-raw": "Complete input", "executable-response": "Executable response",
          "live-e5": "Live observation (E5)", "e4-rich-static-table": "E4 typed table"}


def table(path, caption, label, columns, header, rows):
    text = ["% Generated from hash-verified saved data; no scientific execution.", "\\begin{table}[htbp]", "\\centering\\small", "\\caption{" + caption + "}",
            "\\label{tab:" + label + "}", "\\begin{tabular}{@{}" + columns + "@{}}\\toprule", " & ".join(header) + r" \\\midrule"]
    text.extend(" & ".join(map(str, row)) + r" \\" for row in rows)
    text += [r"\bottomrule\end{tabular}", r"\end{table}", ""]
    path.write_text("\n".join(text))


def write_outputs(summary, output):
    output.mkdir(parents=True, exist_ok=True)
    tables = output / "tables"
    tables.mkdir(exist_ok=True)
    for name, rows in [("E2-E3-witnesses", summary["structural_witnesses"]), ("E4-formal", summary["formal"]),
                       ("E5-observation-costs", summary["observation_costs"]), ("O-final", summary["O_final"]), ("O-failed-timestamps", summary["O_failed_times"])]:
        with (output / (name + ".csv")).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    names = {"b-pulse-fast": "Fast pulse", "b-pulse-slow": "Slow pulse", "b-esr-fail": "High ESR", "b-no-energy": "No energy",
             "b-late-energy": "Late pulse", "b-latched-reset": "Latched reset", "b-volatile-reset": "Volatile reset"}
    table(tables/"reference.tex", "Seven saved digital BF reference controls. First reception after 100 ms fails the deadline; a passing rail gate without a received event is insufficient. Physical qualification is UNKNOWN throughout.",
          "reference", "lrrcc", ["Control", r"Input ($\mu$J)", "RX (ms)", "Service", "Rail"],
          [[names[r["case"]], f'{r["source_uj"]:.0f}', "--" if r["first_receive_ms"] is None else f'{r["first_receive_ms"]:.1f}', r["service"], r["rail"]] for r in summary["reference_controls"]])
    table(tables/"witnesses.tex", "E2--E3 structural witnesses: both worlds pass before a common legal intervention, then separate. These are two exposed ideal pairs, not statistical repetitions.",
          "witnesses", "llccr", ["Mechanism", "World", "Current", "Changed", "Changed events"],
          [["Clamp" if r["pair"] == "clamp-capacitance" else "Reset memory", r["world"], r["current"], r["intervention"], r["delivered"]] for r in summary["structural_witnesses"]])
    table(tables/"acquisition.tex", "Finite observation selection on four exposed cases. Read and audit bytes are Python payloads, not disk I/O. Host timings are single historical measurements, not latency benchmarks; selected and mechanism-spec contain the same facts.",
          "acquisition", "lrrrrr", ["Observation", "Correct", "Read B", "Audit B", "Wall ms", "Model runs"],
          [[r["arm"], str(r["correct"])+"/4", r["read_bytes"], r["audit_read_bytes"], f'{(r["observation_wall_ns"]+r["audit_wall_ns"]+r["selector_wall_ns"])/1e6:.3f}', r["model_runs"]] for r in summary["observation_costs"]])
    table(tables/"formal.tex", "Formal matched interface comparison: four fixed tasks, three repetitions per task, twelve groups per arm. P/F/I are PASS, submitted FAIL and INCOMPLETE. Every incomplete group and its requests remain included.",
          "formal", "lrrrrr", ["Condition", "P", "F", "I", "Requests", "Requests/group"],
          [[LABELS[r["condition"]], r["PASS"], r["FAIL"], r["INCOMPLETE"], r["requests"], f'{r["requests"]/12:.4f}'] for r in summary["formal"]])
    task_names = {"b-pulse-fast": "Pulse-fast", "b-volatile-reset": "Volatile reset", "b-latched-reset": "Latched reset", "clite-query-window-derived-v1": "C-lite query derivative"}
    def pfi(r): return "/".join(str(r.get(k, 0)) for k in ("PASS", "FAIL", "INCOMPLETE"))
    table(tables/"per-task.tex", "Formal P/F/I out of three per task. Each strong arm separately denotes rich static, complete input, executable response and E4 table; none has an omitted failure.",
          "tasks", "lccc", ["Fixed task", "Average energy", "Live E5", "Each strong arm"],
          [[label, pfi(summary["per_task"]["average-energy"][task]), pfi(summary["per_task"]["live-e5"][task]), "3/0/0"] for task, label in task_names.items()])
    table(tables/"e5.tex", "Disposition of all twelve formal E5 groups. Repeated rejected actions are not additional groups; absent executions are retained as INCOMPLETE.",
          "e5", "lrc", ["Disposition", "Groups", "Final service"], [["Qualified selection, consumed", 6, "PASS"], ["Qualified construction, consumed", 1, "PASS"], ["Source-unit binding rejected", 4, "INCOMPLETE"], ["No typed consumer match", 1, "INCOMPLETE"]])
    e4 = [r for r in summary["formal"] if r["condition"] in ("rich-static", "e4-rich-static-table")]
    table(tables/"format.tex", "E4 equal-information initial serialization. Later acquisitions use common JSON. Cost and summed group wall time are descriptive; neither establishes a format advantage.",
          "format", "lrrrr", ["Initial packet", "PASS", "Requests", "USD", "Wall (s)"],
          [["JSON" if r["condition"] == "rich-static" else "Typed table", "12/12", r["requests"], f'{r["usd"]:.7f}', f'{r["wall_s"]:.1f}'] for r in e4])
    table(tables/"O0.tex", "Original O0 development task. Candidate and rich-state control share one exact design and response. Self-judgment is scoped separately from the host O event predicate.",
          "o0", "lrrccr", ["Arm", "Poll (s)", "Matched/8", "Host O", "Self-judgment", "Requests"],
          [[r["arm"], f'{r["poll_s"]:g}', str(r["matched"])+"/8", r["service"], r["self_judgment"], r["requests"]] for r in summary["O0"]])
    table(tables/"O-final.tex", "All nine new-O final cells. Every submitted row matches eight events, receives 18 packets and passes energy. Events P/8 counts individually passing events. Dashes denote no submission.",
          "ofinal", "lrrrrc", ["Lineage/arm", "Poll (s)", "Retry (s)", "Events P/8", "Max error (s)", "Service"],
          [["L"+str(r["lineage"])+"-"+r["arm"], "--" if r["poll_s"] is None else f'{r["poll_s"]:g}', "--" if r["retry_s"] is None else f'{r["retry_s"]:g}', "--" if r["event_passes"] is None else str(r["event_passes"])+"/8", "--" if r["max_error_s"] is None else f'{r["max_error_s"]:.3f}', r["service"]] for r in summary["O_final"]])
    unique = {r["time_s"]: r for r in summary["O_failed_times"]}
    table(tables/"timing.tex", "The same two failed stop times occur in both one-second submissions. Error uses encoded event time, not receive time. Their distinct execution keys and different retry values remain preserved.",
          "timing", "rrrr", ["Confirmation (s)", "Reception (s)", "Encoded (s)", "Error (s)"],
          [[f'{r[k]:.3f}' for k in ["time_s", "receive_s", "encoded_stamp_s", "absolute_stamp_error_s"]] for r in unique.values()])
    table(tables/"final-arms.tex", "Complete 27-cell transfer denominator. Both reserved digital tasks pass in all 18 cells; O contributes the submitted failures and four incomplete episodes.",
          "finalarms", "lrrr", ["Procedure arm", "PASS", "Submitted FAIL", "INCOMPLETE"], [[r["arm"], r["PASS"], r["FAIL"], r["INCOMPLETE"]] for r in summary["final_arms"]])
    (output/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument("--data-root", type=Path, default=here/"data")
    parser.add_argument("--output", type=Path, default=here/"generated")
    args = parser.parse_args()
    data = SavedData(args.data_root)
    require(not args.output.resolve().is_relative_to(data.root), "Output cannot overwrite sealed saved data")
    result = analyze(data)
    write_outputs(result, args.output)
    checks = {"status": "PASS", "scope": result["scope"], "data_manifest_sha256": data.manifest_sha256,
              "script_sha256": digest(Path(__file__).read_bytes()), "saved_files_verified": len(data.files), "saved_bytes_verified": data.bytes_verified,
              "formal_E5": {"PASS": 7, "INCOMPLETE": 5, "denominator": 12}, "rich_static": {"PASS": 12, "denominator": 12},
              "O_final_denominator": 9, "O_token_censored": 4, "physical_qualification": "UNKNOWN", "product_acceptance": "NOT_ACCEPTED",
              "default_H0_changed": False, "new_provider_requests": 0, "new_scientific_executions": 0, "archived_code_executed": False}
    (args.output/"checks.json").write_text(json.dumps(checks, indent=2)+"\n")
    print(json.dumps(checks))


if __name__ == "__main__":
    main()
