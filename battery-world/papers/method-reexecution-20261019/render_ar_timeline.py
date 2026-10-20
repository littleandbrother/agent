#!/usr/bin/env python3
"""Render a source-bound A/R timeline after an external service check.

Only saved raw observations are plotted. The original candidate resolves to
the canonical sealed reference rather than copied traces or new simulations.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("ar_timeline_consumer", ROOT / "scripts/campaign_ar_service.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)
os.environ.setdefault("MPLCONFIGDIR", str(service.RUNTIME / "plot-cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "phase1-figures")
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().parent != HERE:
        raise ValueError("NEW_OWNED_FIGURE_DIRECTORY_REQUIRED")
    saved = json.loads(args.receipt.read_text())
    checked = service.independent_check(Path(saved["bundle"]), expected_seal_sha256=saved["seal_sha256"])
    if saved != checked or checked["execution_integrity"] != "PASS":
        raise ValueError("EXTERNAL_RECEIPT_DISAGREEMENT")
    service.output_guard(service.RUNTIME / "plot-admission")
    args.output.mkdir()
    plt.rcParams.update({"font.family": ["DejaVu Sans", "Arial", "Helvetica", "sans-serif"], "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 1.2,
                         "legend.frameon": False, "svg.fonttype": "none", "pdf.fonttype": 42})
    blue, green, red, gray = "#0F4D92", "#4A8748", "#B64342", "#767676"
    cases = [("ar-light-dark", "Six-hour nominal positive"),
             ("ar-history-nvm", "Twelve-hour dark service"),
             ("ar-upload-dedup", "Gateway recovery and fresh samples")]
    fig, axes = plt.subplots(3, 3, figsize=(15, 8.8), sharex="col")
    evidence = []
    for col, (name, title) in enumerate(cases):
        case = Path(saved["bundle"]) / "cases" / name
        if (case / "historical-ref.json").exists():
            source = Path(service.load_contract()["historical_raw"]["path"]) / "cases" / name
        else:
            source = case
        task, raw = service.load_case(source)
        result = checked["cases"][name]
        rows = raw["trace"]
        times = [float(r["time_s"]) / 3600 for r in rows]
        top, events, history = axes[:, col]
        top.set_title(title, fontsize=13, fontweight="bold", pad=9)
        top.plot(times, [float(r["voltage_v"]) for r in rows], color=blue, lw=1.7)
        top.axhline(task["device"]["off_v"], color=red, lw=1, ls=":")
        top.set_ylim(0, 3.6); top.set_ylabel("Capacitor (V)")
        power = top.twinx()
        power.step(times, [float(r["source_j"]) / float(r["dt_s"]) * 1e6 for r in rows],
                   color=gray, lw=1, alpha=.7)
        power.set_ylim(0, 110); power.set_ylabel("Assumed PV (µW)", color=gray)
        power.tick_params(axis="y", colors=gray); power.spines["top"].set_visible(False)
        for segment in task["source_segments"]:
            if segment["power_w"] == 0:
                for ax in (top, events, history):
                    ax.axvspan(segment["start_s"] / 3600, segment["end_s"] / 3600, color="#CFCECE", alpha=.27, zorder=0)
        new = [r["created_s"] / 3600 for r in raw["records"] if r["kind"] == 0]
        fresh = []
        unique_times, count, seen = [], [], set()
        for r in raw["receiver"]:
            if r["accepted"] and r["seq"] not in seen:
                seen.add(r["seq"]); unique_times.append(r["time_s"] / 3600); count.append(len(seen))
            p = service.reference.decode(r["hex"], "ar")
            if r["accepted"] and p and p["kind"] == 0 and p["known"] and not p["history"]:
                fresh.append(r["time_s"] / 3600)
        events.scatter(new, [2] * len(new), marker="|", color=blue, s=24, linewidths=.8)
        events.scatter(fresh, [1] * len(fresh), marker="|", color=green, s=24, linewidths=.8)
        for gap in result["gates"]["gap_reporting"]["received_gap_intervals"]:
            events.plot([gap["lo_s"] / 3600, gap["hi_s"] / 3600], [0, 0], color=red, lw=3, ls="--")
        events.set_yticks([0, 1, 2], ["Gap bracket", "Fresh receive", "New sample"])
        events.set_ylim(-.55, 2.65)
        history.plot(times, [int(r["retained_records"]) for r in rows], color=blue, lw=1.6)
        history.step(unique_times, count, color=green, lw=1.6, where="post", ls="--")
        history.plot(times, [int(r["pending_records"]) for r in rows], color=red, lw=1, ls=":")
        history.set_ylabel("Record count"); history.set_xlabel("Elapsed time (h)")
        for t in result["brownout_times_s"]:
            for ax in (top, events, history): ax.axvline(t / 3600, color=red, lw=.9, ls=":")
        summary = service.compact(result)
        annotation = "New: %s · history: %s\nRecovery: %s · fresh ≤10 s: %s" % tuple(
            result["gates"][k]["status"].replace("NOT_APPLICABLE", "N/A")
            for k in ("continuous_new_sampling", "history_retention", "recovery_upload", "fresh_receive_delay"))
        events.text(.02, .94, annotation, transform=events.transAxes, va="top", fontsize=9,
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": .9, "pad": 1.5})
        if result["gates"]["absolute_time"]["status"] == "UNKNOWN":
            history.text(.4, .84, "Absolute time UNKNOWN\nafter reset", transform=history.transAxes, color=red, fontsize=9)
        for ax in (top, events, history):
            ax.set_xlim(0, task["duration_s"] / 3600); ax.tick_params(labelsize=10)
        evidence.append({"case": name, "source": str(source), "input_sha256": service.sha(source / "input.json"),
                         "raw_rows_plotted": len(rows), "summary": summary})
    fig.suptitle("A/R sealed reference: energy, new information and receiving service", fontsize=17, x=.5, y=.98)
    handles = [Line2D([0], [0], color=blue, lw=2, label="Durable records"),
               Line2D([0], [0], color=green, lw=2, ls="--", label="Accepted unique records"),
               Line2D([0], [0], color=red, lw=1.5, ls=":", label="Pending records / reset markers")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .033), ncol=3, fontsize=11)
    fig.text(.5, .012, "Nominal uncalibrated model · original candidate only · dark shading = zero source · gap bars are reported brackets, not exact outage edges", ha="center", fontsize=10, color="#4D4D4D")
    fig.tight_layout(pad=1.4, rect=(0, .09, 1, .95))
    for suffix in ("pdf", "svg", "png"):
        fig.savefig(args.output / ("ar-reference-timeline." + suffix), dpi=300, facecolor="white")
    plt.close(fig)
    receipt = {"schema_version": "bf-ar-timeline-render-v1", "external_receipt": str(args.receipt),
               "external_receipt_sha256": service.sha(args.receipt), "candidate_sha256": checked["candidate_sha256"],
               "renderer_sha256": service.sha(Path(__file__)), "cases": evidence, "new_simulations": 0,
               "paid_requests": 0, "native_calls": 0, "physical_qualification": "UNKNOWN",
               "outputs": [{"path": p.name, "sha256": service.sha(p), "bytes": p.stat().st_size} for p in sorted(args.output.iterdir())]}
    service.dump(args.output / "render-receipt.json", receipt)
    print(json.dumps({"output": str(args.output), "raw_simulations": 0, "rendered_files": 3}))


if __name__ == "__main__": main()
