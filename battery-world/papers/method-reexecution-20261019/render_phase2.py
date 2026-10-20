#!/usr/bin/env python3
"""Read pinned phase2 evidence and build only the separate phase2 manuscript.

No provider, Agent, simulator, or native-execution imports or dispatches exist
here. `build` performs evidence readback, two TeX passes, PDF text extraction and
rasterization. `clean` requires a matching manual visual receipt before removing
only this script's TeX scratch directory and page rasters.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


PAPER = Path(__file__).resolve().parent
BATTERY_WORLD = PAPER.parents[1]
DOCS = BATTERY_WORLD / "docs/research/phase2-20261020/methods"
RECEIPTS = DOCS / "paper-final"
SCRATCH = RECEIPTS / ".build-phase2"
BINDING = PAPER / "phase2-binding.json"
EPISODES = (
    "p2-e5-001", "p2-h-proposal-001", "p2-h0-design-001",
    "p2-hprime-design-001",
)


def read(path):
    return json.loads(path.read_text())


def metadata(path):
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def verify_files(root, entries):
    for name, expected in entries.items():
        assert metadata(root / name)["sha256"] == expected["sha256"], name


def run(args, *, env=None):
    result = subprocess.run(args, cwd=PAPER, env=env, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, (args, result.stdout[-3000:], result.stderr[-3000:])
    return result.stdout + result.stderr


def costs_from_usage(root):
    costs = []
    for episode in EPISODES:
        obj = read(root / episode / "provider-costs.json")
        assert obj["unknown_or_missing_usage"] == []
        assert obj["unsettled_reserved_usd"] == 0
        upper = Decimal(0)
        cache = Decimal(0)
        for row in obj["rows"]:
            assert row["status"] == "SETTLED" and row["error"] is None
            usage = json.loads(row["usage"])
            assert usage["prompt_tokens"] == (usage["prompt_cache_hit_tokens"]
                                               + usage["prompt_cache_miss_tokens"])
            upper += (Decimal(usage["prompt_tokens"]) * Decimal(".30")
                      + Decimal(usage["completion_tokens"]) * Decimal("1.20")) / 1_000_000
            cache += (Decimal(usage["prompt_cache_hit_tokens"]) * Decimal(".006")
                      + Decimal(usage["prompt_cache_miss_tokens"]) * Decimal(".30")
                      + Decimal(usage["completion_tokens"]) * Decimal("1.20")) / 1_000_000
        assert abs(upper - Decimal(str(obj["settled_charge_upper_bound_usd"]))) < Decimal("1e-15")
        assert abs(cache - Decimal(str(obj["cache_aware_rate_estimate_usd"]))) < Decimal("1e-15")
        costs.append({"episode": episode, "requests": len(obj["rows"]),
                      "upper_usd": str(upper.normalize()),
                      "cache_aware_rate_estimate_usd": str(cache.normalize()),
                      "usage_status": "SETTLED"})
    return costs


TEXT = r"""% Generated from pinned actual receipts by render_phase2.py; no experiments run.
\section{Question, apparatus, and intervention boundary}
This finite study asks whether an actual proposed design method should replace
the baseline method. Device changes $D$ and design-method changes $H$ have
different validation scopes. Here $D$ contains two device parameters: capacitance
and the earliest allowed transmit time. $H$ contains instructions for observing
sources, forming energy and timing constraints, selecting a candidate, and
checking it. A changed $D$ requires its complete feedback response; a global
change to $H$ requires fresh design decisions from task entry. Changing the
procedure that proposes methods, $G$, would require a separate lineage study.
No such $G$ comparison is reported.

The fixed public development task is \texttt{b-volatile-reset}. One event at
$t=0$ must deliver exactly one valid eight-byte application frame by $100$ ms,
without duplicates. Legal capacitance is $4$--$22\,\mu$F; the legal transmit floor
is $0$--$45$ ms. Supply, initial state, event, all other device fields, and the
evaluator remain fixed. Harvest segments occur at $0$--$6$ and $30$--$60$ ms.
The event latch is volatile. Passing means passing the complete frozen
computational service, including independent energy and receiver checks and
transient-voltage and deduplication checks. Physical calibration remains
\texttt{UNKNOWN}; this is not a hardware or official benchmark result.

A registered device-response negative control distinguishes replay from valid
reuse: the retained $10\,\mu$F / $45$ ms design fails, whereas
$10\,\mu$F / $0$ ms passes on the same world. Reusing the former response for the
changed input would give the wrong answer. The control read exact-input cached
full responses and added no new execution. It was prepared by the host and is
not an observation generated by the method proposer. The qualification-grid
construction cost remains in the phase accounting.

\clearpage
\section{Original failure and posthoc method recovery}
The actual proposer used nine provider requests. Its live episode ended
\texttt{INCOMPLETE\_OR\_STOPPED}: a host action was wrongly exposed and a device
check payload consumed a method-proposal slot. No original method submission
or adoption succeeded. A zero process exit code does not change that result.
The host-action and budget-contract failure, trace, and all nine requests remain
recorded.

A posthoc host adapter recovered an actual model-authored method from the
retained rejected call. It added no paid proposal request or new model decision.
The resulting artifact is eligible for experimental re-execution; it is neither
a researcher-authored replacement nor a successful original proposal episode.
Its method-text identity is bound as a canonical JSON string, with the hash
encoding recorded in \texttt{phase2-binding.json}. This recovery is explicitly
posthoc and does not repair the original prospective protocol.

The proposed $H$ instructs the agent to acquire all listed sources, construct
an energy and timing ledger, avoid losing the volatile latch before transmission,
and check one selected design. It also makes device-specific exclusions:
it presents $7.4$--$14\,\mu$F as a feasible band, rejects waiting across the
dark gap or using a late transmit floor, and recommends $10\,\mu$F / $2$ ms.
These exclusions are scientific claims to test, rather than consequences of
passing the method schema. Its declared falsifier includes failure of the
selected design and an edge-design clause fixing a $2$ ms floor and requiring
selected-design failure. An outside-band success at a different floor does
not, by itself, satisfy that exact conjunctive clause.

\subsection{Fresh entries and comparison limits}
The baseline $H_0$ and revised $H'$ each ran from task entry with a distinct
owner and context, zero initial decision messages, and a limit of two candidates,
24 provider requests, and 1,200 seconds. Each actually checked and submitted
one candidate. The revised protocol appends the recovered method body verbatim
to the common instruction. Its actual choice, $9\,\mu$F / $3.7$ ms, differs
from the method's $10\,\mu$F / $2$ ms recommendation; this is a fresh decision,
not a literal copy of that device recommendation.

The external registry reports matching task, source, information, model
configuration, tool, and evaluator identities. Both use the provider-reported
alias \texttt{deepseek-flash}; the weights are not independently pinned.
Crucially, the physical exact-input cache evolved and its initial snapshot was
not frozen equally for the two entries. The confirmation gate rejects with
\texttt{PARITY\_INITIAL\_CACHE\_SHA256}. Valid response reuse for a particular
input does not establish equal starting caches. These runs therefore provide
descriptive case outcomes, not a causal comparison of the methods.

\clearpage
\section{Complete-service results and ordered state}
Both designs pass the complete frozen computational service
(Table~\ref{tab:designs}). The external evaluator reads qualified complete
responses whose input identities match the actual agent checks. The response
receipts say \texttt{reused=true} and
\texttt{origin=new-full-feedback-response}: reuse during external readback does
not mean that the agent inherited an old decision trace, or that readback ran a
new simulation. Both agent entries are fresh; cache construction is accounted
separately.

\begin{table}[h]
\centering
\begin{tabular}{@{}lrrrrc@{}}
\toprule
Condition & $C$ ($\mu$F) & TX floor (ms) & First RX (ms) & Frames & Service \\
\midrule
$H_0$ & @H0_C@ & @H0_FLOOR@ & @H0_RX@ & 1 & PASS \\
$H'$ & @HP_C@ & @HP_FLOOR@ & @HP_RX@ & 1 & PASS \\
\bottomrule
\end{tabular}
\caption{One observed design per condition on the exposed fixed task. Physical
qualification is UNKNOWN for both. These values do not estimate a success rate
or a general method speedup.}
\label{tab:designs}
\end{table}

The ordered-state audit resolves the reset interpretation. $H_0$ receives at
@H0_RX@ ms and has no reset before delivery or before the deadline. $H'$ receives
at @HP_RX@ ms and resets at @HP_RESET@ ms, after delivery. Both have zero resets
before first delivery, and both event latches remain volatile. The baseline
avoids a pre-delivery reset; the revised design finishes delivery before reset.
Neither successful run demonstrates that pending state survived a reset.

The frozen checker's legacy \texttt{event\_preserved\_after\_reset} label is
FAIL for $H_0$ and PASS for $H'$. Its implementation combines successful
delivery with the occurrence of any reset; it does not test whether a still
pending event crossed a reset. We retain those labels while interpreting the
actual temporal order. In particular, the participant's broad ``no brownout''
description is unsupported over the full deadline: the post-delivery
@HP_RESET@ ms reset remains in the audit. The checker was not changed.

\subsection{Counterexample and retention decision}
The passing $22\,\mu$F / $45$ ms baseline is a counterexample to the proposed
necessary $7.4$--$14\,\mu$F band and its rejection of waiting through the gap
or using a late floor. It is not a counterexample to the separate claim that
transmission must fit within one contiguous harvest segment: this baseline
transmits during the second segment. Nor does it test the proposal's particular
$22\,\mu$F / $2$ ms edge case or the recommended $10\,\mu$F / $2$ ms design.
The revised design's success does not validate every rule in the method text.

The external decision is \textbf{reject promotion; retain the experimental
artifact}. The default $H$ is unchanged. This decision preserves the original
host failure and posthoc boundary, the already successful baseline, the missing
initial-cache parity, the cost of the proposal, and the over-restrictive method
claims. The earlier reception under $H'$ is an observed outcome; with one
case per condition and unequal cache provenance, it does not establish a
general or causal method advantage.

\clearpage
\section{All requests, construction costs, and claim boundaries}
Table~\ref{tab:costs} retains the four phase2 episodes, including the separate
E5 consumer attempt and both original incomplete episodes. All @TOTAL_REQUESTS@
requests have settled usage; no usage is unresolved and no reservation remains
unsettled. Amounts are token-based estimates at the existing pinned rates,
not invoices. The upper calculation charges all prompt tokens at USD 0.30 per
million and completion tokens at USD 1.20; the cache-aware calculation charges
cache-hit prompt tokens at USD 0.006 and misses at USD 0.30 per million.

\begin{table}[h]
\centering
\begin{tabular}{@{}lrrr@{}}
\toprule
Episode & Requests & Upper (USD) & Cache-aware estimate (USD) \\
\midrule
@COST_ROWS@
\midrule
All phase2 episodes & @TOTAL_REQUESTS@ & @TOTAL_UPPER@ & @TOTAL_CACHE@ \\
\bottomrule
\end{tabular}
\caption{Actual usage readback. The E5 scientific interpretation is outside this
method report; its cost remains in the whole-phase total.}
\label{tab:costs}
\end{table}

The H proposal and the two design episodes together use 19 requests:
USD 0.1122807 upper and USD 0.065353596 cache-aware estimate. Proposal plus $H'$
uses 14 requests and USD 0.0729432 / 0.040090464, compared with $H_0$'s five
requests and USD 0.0393375 / 0.025263132. Although the $H'$ design episode alone
has a lower estimated cost, omitting the nine proposal requests would hide the
method-development cost. No advantage under the same total budget is established.
Codex assistance is unpriced and nonzero; total end-to-end cost remains UNKNOWN.

The entire finite phase records seven new local computational cases: four
qualification-grid cases and three consumer/design cases. Native calls are zero.
The ordered-state audit and this manuscript build add no model request,
scientific execution, or native dispatch. The already recorded 22 MOCK tests
verify the structural method API; they are reused here without a test or full
verification rerun. They do not establish scientific method benefit.

\subsection{Evidence and reproducibility}
\texttt{phase2-binding.json} binds the original failed proposal, recovered method,
fresh-entry protocols and actual tool traces, external service results,
ordered-state audit, retention decision, and every cost ledger. It also binds
this manuscript, the shared style and official English university logo, and
the resulting PDF. Source hashes distinguish raw UTF-8 method text from its
canonical JSON-string identity. \texttt{render\_phase2.py build} validates those
inputs and rebuilds only this separate paper in two TeX passes; it does not
execute the scientific apparatus. Build and visual receipts are retained in
\path{docs/research/phase2-20261020/methods/paper-final/}.

All observations concern an exposed public development task under a fixed
ideal model. No heldout transfer, repeated-sampling estimate, independent
method lineage, recursive self-improvement, hardware acceptance, or overall
product acceptance is established. The prior A/R fixed-space NO\_GO, strict FIFO
failure, and NOT\_ACCEPTED are preserved. The prior manuscript and PDF are
preserved as separate artifacts.
"""


def render_text(root, costs):
    baseline = read(root / EPISODES[2] / "external/result.json")
    revised = read(root / EPISODES[3] / "external/result.json")
    ordered = read(root / "ordered-state-audit.json")
    decision = read(root / "method-retain-or-reject.json")
    assert baseline["execution"]["complete_service"] == revised["execution"]["complete_service"] == "PASS"
    assert not decision["retained"] and not decision["default_H_changed"]
    assert decision["gate"]["failures"] == ["PARITY_INITIAL_CACHE_SHA256"]
    assert ordered["frozen_checker_changed"] is False
    for episode in EPISODES[2:]:
        case = ordered["cases"][episode]
        assert case["event_latch_unchanged"] == "volatile"
        assert case["resets_before_first_delivery"] == []
    total_upper = sum(Decimal(c["upper_usd"]) for c in costs)
    total_cache = sum(Decimal(c["cache_aware_rate_estimate_usd"]) for c in costs)
    labels = ("E5 attempt (incomplete)", "H proposal (incomplete)", "$H_0$ design", "$H'$ design")
    rows = []
    for label, cost in zip(labels, costs):
        rows.append(f"{label} & {cost['requests']} & {Decimal(cost['upper_usd']):.7f}"
                    f" & {Decimal(cost['cache_aware_rate_estimate_usd']):.9f} " + r"\\")
    values = {"COST_ROWS": "\n".join(rows),
              "TOTAL_REQUESTS": str(sum(c["requests"] for c in costs)),
              "TOTAL_UPPER": f"{total_upper:.7f}",
              "TOTAL_CACHE": f"{total_cache:.9f}",
              "HP_RESET": f"{ordered['cases'][EPISODES[3]]['resets_after_delivery_before_deadline'][0]['time_s'] * 1000:.1f}"}
    for prefix, result in [("H0", baseline), ("HP", revised)]:
        values[prefix + "_C"] = f"{result['candidate']['capacitance_f'] * 1e6:g}"
        values[prefix + "_FLOOR"] = f"{result['candidate']['tx_not_before_s'] * 1000:g}"
        values[prefix + "_RX"] = f"{result['execution']['reference']['first_receive_s'] * 1000:.1f}"
    rendered = TEXT
    for key, value in values.items():
        rendered = rendered.replace("@" + key + "@", value)
    assert not re.search(r"@[A-Z0-9_]+@", rendered)
    return rendered


def clean(binding):
    visual = read(RECEIPTS / "visual-review.json")
    assert visual["status"] == "PASS_ALL_PAGES"
    assert visual["pdf_sha256"] == metadata(PAPER / "phase2.pdf")["sha256"]
    removed = {}
    for raster in RECEIPTS.glob("phase2-page-*.png"):
        assert visual["page_rasters"][raster.name]["sha256"] == metadata(raster)["sha256"]
        removed[str(raster.relative_to(RECEIPTS))] = metadata(raster)
        raster.unlink()
    if SCRATCH.exists():
        assert SCRATCH.resolve().parent == RECEIPTS.resolve()
        for path in SCRATCH.rglob("*"):
            if path.is_file():
                removed[str(path.relative_to(RECEIPTS))] = metadata(path)
        shutil.rmtree(SCRATCH)
    save(RECEIPTS / "cleanup.json", {"at_utc": datetime.now(timezone.utc).isoformat(),
         "status": "REMOVED_ONLY_NEW_PHASE2_TEX_SCRATCH_AND_REVIEWED_RASTERS",
         "removed_files": removed, "removed_bytes": sum(x["bytes"] for x in removed.values()),
         "pdf": metadata(PAPER / "phase2.pdf"), "visual_receipt": metadata(RECEIPTS / "visual-review.json"),
         "available_bytes_after": shutil.disk_usage(PAPER).free})
    print(json.dumps({"status": "CLEANED", "files_removed": len(removed), "pdf": metadata(PAPER / "phase2.pdf")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "clean"), nargs="?", default="build")
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    binding = read(BINDING)
    root = args.evidence_root or Path(binding["evidence_root"])
    verify_files(root, binding["evidence_files"])
    verify_files(PAPER, binding["analysis_inputs"])
    verify_files(PAPER, binding["support_inputs"])
    admission = read(PAPER / binding["admission"])
    verify_files(BATTERY_WORLD, admission["protected_files"])
    if args.action == "clean":
        clean(binding)
        return
    assert shutil.disk_usage(PAPER).free >= admission["minimum_phase_reserve_plus_peak_bytes"]
    if binding["paper_inputs"]:
        verify_files(PAPER, binding["paper_inputs"])
    costs = costs_from_usage(root)
    assert costs == binding["costs"]
    methods = render_text(root, costs)
    (PAPER / "phase2-methods.tex").write_text(methods)
    SCRATCH.mkdir(exist_ok=True)
    env = dict(os.environ, SOURCE_DATE_EPOCH="1792436786", FORCE_SOURCE_DATE="1", TZ="UTC")
    latex = shutil.which("pdflatex") or "/Library/TeX/texbin/pdflatex"
    command = [latex, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
               "-recorder", "-jobname=phase2", "-output-directory=" + str(SCRATCH),
               "phase2-manuscript.tex"]
    for iteration in (1, 2):
        output = run(command, env=env)
        (RECEIPTS / f"build-pass{iteration}.stdout.log").write_text(output)
    log = (SCRATCH / "phase2.log").read_text()
    assert "Overfull" not in log, "Inspect and repair an overfull TeX box"
    assert "undefined references" not in log, "Unresolved reference after the final pass"
    shutil.copyfile(SCRATCH / "phase2.log", RECEIPTS / "phase2-compile.log")
    shutil.copyfile(SCRATCH / "phase2.fls", RECEIPTS / "phase2-inputs.fls")
    shutil.copyfile(SCRATCH / "phase2.pdf", PAPER / "phase2.pdf")
    info = run(["pdfinfo", str(PAPER / "phase2.pdf")])
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE).group(1))
    assert 1 <= pages <= 6, pages
    (RECEIPTS / "pdfinfo.txt").write_text(info)
    run(["pdftotext", "-layout", str(PAPER / "phase2.pdf"), str(RECEIPTS / "phase2.txt")])
    extracted = (RECEIPTS / "phase2.txt").read_text()
    for expected in ["46.9", "5.6", "12.1", "0.1766922", "0.101240040", "PARITY_INITIAL_CACHE_SHA256"]:
        assert expected in extracted, expected
    run(["pdftoppm", "-scale-to", "1500", "-png", str(PAPER / "phase2.pdf"), str(RECEIPTS / "phase2-page")])
    rasters = {x.name: metadata(x) for x in sorted(RECEIPTS.glob("phase2-page-*.png"))}
    assert len(rasters) == pages
    fonts = run(["pdffonts", str(PAPER / "phase2.pdf")])
    (RECEIPTS / "pdffonts.txt").write_text(fonts)
    for line in fonts.splitlines()[2:]:
        if line.strip():
            assert line.split()[-5] == "yes", line
    binding["paper_inputs"] = {name: metadata(PAPER / name) for name in
                                ["phase2-manuscript.tex", "phase2-methods.tex", "render_phase2.py"]}
    binding["outputs"] = {"phase2.pdf": metadata(PAPER / "phase2.pdf"), "pages": pages,
                          "compile_status": "SUCCESS_TWO_PASSES_NO_OVERFULL_OR_UNDEFINED_REFERENCES",
                          "visual_status": "PENDING_MANUAL_ALL_PAGE_REVIEW"}
    binding["rebuild"] = {"cwd": str(PAPER), "command": "python -B render_phase2.py build",
                          "evidence_override": "--evidence-root /path/to/pinned/evidence",
                          "environment": {k: env[k] for k in ["SOURCE_DATE_EPOCH", "FORCE_SOURCE_DATE", "TZ"]},
                          "scientific_execution": False}
    save(BINDING, binding)
    receipt = {"schema_version": "bf-phase2-paper-build-v1", "at_utc": datetime.now(timezone.utc).isoformat(),
               "status": "COMPILED_REQUIRES_VISUAL_REVIEW", "pages": pages,
               "pdf": metadata(PAPER / "phase2.pdf"), "binding": metadata(BINDING),
               "latex_command": command, "latex_passes": 2,
               "latex_version": run([latex, "--version"]).splitlines()[0],
               "no_overfull_or_undefined_references": True, "all_fonts_embedded": True,
               "page_rasters": rasters, "new_provider_requests": 0,
               "new_scientific_executions": 0, "native_dispatches": 0,
               "tests": "Reuse previously recorded 22 MOCK tests; no tests or full verification run",
               "protected_files_verified": len(admission["protected_files"]),
               "peak_cap_bytes": admission["paper_peak_cap_bytes"],
               "retained_cap_bytes": admission["paper_retained_cap_bytes"]}
    save(RECEIPTS / "build.json", receipt)
    print(json.dumps({"status": receipt["status"], "pages": pages, "pdf": receipt["pdf"],
                      "page_rasters": list(rasters), "scientific_executions": 0}))


if __name__ == "__main__":
    main()
