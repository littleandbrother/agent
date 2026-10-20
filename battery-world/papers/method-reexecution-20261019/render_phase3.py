#!/usr/bin/env python3
"""Build the separate phase3 research paper from seven pinned S0 data files.

Only paper readback, TeX compilation and PDF inspection run here. No provider,
Agent, simulator, SDK smoke, test suite or native scientific tool is invoked.
"""
from __future__ import annotations

import argparse
from collections import Counter
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
WORLD = PAPER.parents[1]
FINAL = WORLD / "docs/research/phase3-20261020/methods/paper-final"
SCRATCH = FINAL / ".build-phase3"
BINDING = PAPER / "phase3-binding.json"
METHODS = ("complete-raw", "ordinary_reflection", "proposed_method")
LABELS = {"complete-raw": "Fixed $H$ (complete raw)",
          "ordinary_reflection": "Ordinary reflection", "proposed_method": "Proposed procedure"}


def read(path):
    return json.loads(path.read_text())


def meta(path):
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def verify(root, entries):
    for name, expected in entries.items():
        assert meta(root / name)["sha256"] == expected["sha256"], name


def command(args, env=None):
    proc = subprocess.run(args, cwd=PAPER, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, (args, proc.stdout[-3000:], proc.stderr[-3000:])
    return proc.stdout + proc.stderr


TEXT = r"""% Generated from the seven pinned S0 phase3 files; no experiment is run.
\section{Question and experimental object}
The scientific question is whether a proposed design procedure adds service
success once its own construction cost is included. Correctly classifying an
edit or passing a tool contract does not answer that question. We separate a
device program $D$, a method $H$ that chooses and checks $D$, and an improver
$G$ that proposes and selects methods. A different successful $D$ is not
automatically a better $H$; generating a task-specific $H$ does not establish an
improved $G$. The present study evaluates method conditions while retaining
negative and no-update outcomes.

The apparatus is a fixed ideal battery-free model with source arrivals,
storage, state-dependent controller actions, event capture and a receiver.
Three task IDs are \texttt{b-pulse-fast}, \texttt{b-volatile-reset}, and
\texttt{b-latched-reset}. The fourth,
\texttt{clite-query-window-derived-v1}, is a synthetic DC single-query derivative.
The legal capacitance and transmit-floor ranges and service contract are fixed
for each task. They cannot be edited by a method. These are four fixed digital
tasks, not four physical devices or four independent environment families.
The single-query mapping does not establish nonce security or multiple-query
operation. Physical and RF qualification remain UNKNOWN.

\begin{table}[htbp]
\centering
\begin{tabular}{@{}lrrrrr@{}}
\toprule
Stage & Tasks & Repeats/task & Groups & Episodes & Requests \\
\midrule
Pilot & 1 & 2 & 16 & 20 & @PILOT_REQUESTS@ \\
Formal & 4 & 3 & 96 & 120 & @FORMAL_REQUESTS@ \\
Total (distinct tasks) & 4 & --- & 112 & 140 & @ALL_REQUESTS@ \\
\bottomrule
\end{tabular}
\caption{The full registered eight-condition matrix. A group is one
task/condition/repetition, including a proposal episode when present. The pilot
task is already among the four formal tasks; counts of tasks are not additive.}
\label{tab:inventory}
\end{table}

The paper's main comparison uses three of the eight conditions. Its fixed-$H$
cell is the same observed \texttt{complete-raw} cell used by the interface
comparison; it is counted once. Likewise, \texttt{rich-static} also supplies
the E4 JSON cell, while E4 table is a separate condition. The method subset
does not create additional baseline groups or provider episodes. Table
\ref{tab:inventory} counts the complete matrix once, and the main result below
uses 36 of its 96 formal groups.

\section{Conditions and prospective comparison}
All three method conditions use the complete-raw information setting. Every
supplied record and the full fixed model definition are available; complete
raw physical traces are retained by the host for audit. Task, source and tool
access are matched within a task/repetition. The fixed-$H$ condition requests
one complete design attempt. Ordinary reflection first reviews the supplied
observations and proposes a repeatable procedural revision, or no update.
The proposed procedure additionally asks for a typed $D/H$ distinction,
dependency-correct evidence scope, explicit event order, and a distinction
between necessary constraints and sufficient design heuristics. It supplies
no winning device values. Both proposing conditions must produce an actual
model-authored hypothesis, falsifier and procedural method text, or abstain.

Every group has the same ceiling of 24 provider requests, 1,200 seconds and
two distinct $D$ candidates. A proposal subcap of eight requests and 400 seconds
is included in that total. Acquisition, failed actions, the proposal, fresh
design and confirmation all count. Using the entire proposal subcap leaves
at most 16 requests and 800 seconds for the rest of the group. Equality here
means equal registered ceilings and accounting scope, not equal realized
spending. A no-update outcome keeps its proposal costs and uses the base $H$
for any admitted fresh design.

A changed $H$ is consumed at a fresh task entry with a new decision context.
An unchanged lower-level physical response may still be reused under exact
consumed-input identity. These are distinct operations. Every arm begins with
the same immutable cache manifest: 12 phase2 exact-input responses plus one
registered derived baseline. Job overlays are isolated; later physical
deduplication does not expose another arm's result before its query or enlarge
its two-design allowance. All 28 matched proposal groups, including pilot
groups, have passing recorded information, tool, model-alias, cache and total
budget parity checks. These checks establish comparison eligibility, not
method benefit. The provider reports \texttt{deepseek-flash}; the weights are
not independently pinned.

\subsection{Pilot and fixed repetition count}
The two pilots use one task and reverse condition order in the second repeat.
The registered rule chooses two formal repetitions only if complete-service
and design signatures are stable in every matched arm; otherwise it chooses
three. Pilot signatures are not stable across all arms, so the repetition
count is frozen once at three before the formal comparison. No original
failure is replaced and there is no outcome-dependent stopping after this
freeze. Formal task and group order are fixed by the protocol.

\begin{table}[htbp]
\centering
\begin{tabular}{@{}lcrr@{}}
\toprule
Pilot method condition & Service PASS/groups & Requests & Mean/group \\
\midrule
@PILOT_ROWS@
\bottomrule
\end{tabular}
\caption{The six method-subset pilot groups, shown separately from the formal
denominators. The full pilot has 16 groups and 112 requests. Both proposal
conditions propose an update in each pilot group.}
\label{tab:pilot}
\end{table}

\section{Formal result: no added service success at higher cost}
Each method condition passes all 12 formal complete-service evaluations
(Table~\ref{tab:main}). Across the four fixed task IDs, the success vector
is $(3,3,3,3)$ for fixed $H$, ordinary reflection and the proposed procedure.
The 12 observations per condition are repetitions of four tasks. They are not
12 new tasks and do not support a general population success-rate claim.
Complete service is determined independently under the same task-specific
receiver, energy, transient and duplicate-handling criteria.

\begin{table}[htbp]
\centering
\small
\begin{tabular}{@{}lccrrr@{}}
\toprule
Condition & PASS/groups & H update/no-update & Requests & Mean & USD upper \\
\midrule
@MAIN_ROWS@
\bottomrule
\end{tabular}
\caption{Main formal comparison: four fixed tasks times three repetitions.
Requests and cost include proposal and fresh $D$ work. USD values are settled
provider upper estimates, not invoices. A dash denotes no proposal stage.}
\label{tab:main}
\end{table}

Ordinary reflection proposes ten updates and returns no-update twice; the
proposed procedure proposes in all 12 formal groups. The no-update groups stay
in the denominator and retain their costs. The method subset uses 308 requests
in total, including the 64 requests of the one shared fixed-$H$ baseline. The
proposing conditions use 117 and 127 requests versus 64 for the fixed method.
Their means are 9.750 and 10.583 requests per group versus 5.333. Differences
in device choice or intermediate reasoning do not create additional complete
service successes.

The registered selection requires strictly more task-level complete-service
success than both the fixed method and reflection, no lost task, and no higher
mean request count. The proposed procedure has the same task-success vector
and a higher mean request count. The decision is
\textbf{KEEP\_UNCHANGED\_BASE\_H}. It is an actual negative selection result
under the registered objective. It does not show that reflection or structured
reasoning can never be useful; this finite task set has a complete-service
ceiling for the strong baseline.

\subsection{Accounting and shared cells}
Across the entire matrix, all 771 requests settle and no usage remains UNKNOWN.
The 16 pilot groups use 112 requests and USD 0.7345845 upper; the 96 formal
groups use 659 requests and USD 4.7132760. The combined provider upper estimate
is USD 5.4478605. The matrix has 140 actual episodes: 112 design episodes and
28 proposal episodes, not 140 physical experiments. These whole-matrix totals
also include the other interface conditions; they must not be charged again
as a separate method batch. All proposal and fresh design costs are retained,
including abstention and failure. There is no invoice audit. Codex assistance
is unpriced and nonzero, so full end-to-end cost remains UNKNOWN.

\section{Validity controls and event-order interpretation}
Recomputation correctness and method benefit have separate evidential roles.
The deterministic comparison annotates 107 existing admitted group responses;
five groups have no admitted final response. Of the 107, 91 change $D$ and
16 are exact unchanged-input controls. The four strategies in
Table~\ref{tab:scope} are evaluated against those existing response identities,
not four new paid trial arms. Additional scientific executions for this
comparison are zero.

\begin{table}[htbp]
\centering
\begin{tabular}{@{}lp{10.6cm}@{}}
\toprule
Strategy & Recorded meaning for the coupled device change \\
\midrule
Frozen trajectory & Invalid after changed input; retained as a negative control.
Exact unchanged-input records remain positive controls. \\
Dependency recomputation & Conservatively expands to the same complete feedback
response used by the full strategy. \\
Scope recomputation & Conservatively expands to that same complete feedback
response; no valid suffix or smaller region is demonstrated. \\
Full feedback & Uses the actual complete response for the candidate and its
consumed input identity. \\
\bottomrule
\end{tabular}
\caption{Correctness comparison on retained actual responses. The three valid
strategies share one execution key within every admitted record. There is no
local-recomputation speed benefit or extra scientific execution.}
\label{tab:scope}
\end{table}

The coupled device affects controller actions and later physical state; an old
trajectory cannot stand in for the changed load's service. For an $H$ change,
dependency, scope and full policies all require fresh Agent decisions from
task entry. A physical exact-input cache hit does not restore validity to old
Agent decisions. These are validity constraints and a null computational
saving, not an observed method improvement.

\subsection{Four choices, one historical reset-retention response}
The ordered audit finds four formal groups with a pending event delivered
across reset: two fixed-$H$ selections, one proposed-procedure selection, and
one E4 table selection (Table~\ref{tab:ordered}). All select the same historical
\texttt{b-latched-reset} response at $10\,\mu$F and a $45$ ms transmit floor.
Capture actions run from 3.7 through 7.9 ms, brownout occurs at 12.1 ms, and
the same event is received at 46.9 ms. The audit binds event identity to the
single-event ideal state machine. Physical qualification is UNKNOWN.

\begin{table}[htbp]
\centering
\begin{tabular}{@{}lrr@{}}
\toprule
Condition & Formal selected groups & Repetition IDs \\
\midrule
Fixed $H$ / complete raw & 2 & 2, 3 \\
Proposed procedure & 1 & 2 \\
E4 table & 1 & 3 \\
\midrule
All selected groups & 4 & One distinct response key \\
\bottomrule
\end{tabular}
\caption{Four fresh Agent choices, all reusing one historical physical execution
key. The mechanism is the fixed model's ideal passive latch; no new memory
mechanism or new physical experiment is demonstrated.}
\label{tab:ordered}
\end{table}

The remaining 83 successful formal groups deliver before any reset. The
initial controls separately include a successful before-reset response, a
volatile-latch response without valid delivery, and the historical latched
cross-reset response. Relabeling these existing traces adds no experiment.
A reset after delivery is not evidence that pending state survived reset;
the legacy success-and-any-reset label is insufficient without event identity
and capture--reset--delivery order.

\section{Discussion and limits of the negative result}
The apparatus makes two different questions observable. The validity controls
show why changing a coupled input invalidates an old trajectory and why
changing $H$ invalidates its earlier decision span. The formal comparison then
asks whether paying for an actual method proposal adds service success. The
first question has a conservative correctness answer; the second has a
negative result on the registered tasks. Passing an interface or hash check
cannot substitute for an improvement in the second question.

The baseline already completes every formal task/repetition. The structured
procedure does not create another success and costs more requests. This is a
useful counterexample to treating more explicit reasoning or more submitted
method updates as an automatic research gain. It does not identify which
instruction caused a particular device choice, nor isolate the value of each
reasoning step. No component ablation or significance test is claimed. Four
fixed digital tasks and three repetitions provide a finite development
comparison, not broad generalization over battery-free products.

\subsection{Task-local methods and historical boundaries}
The actual $H$ texts are instantiated separately within each task/repetition.
They are not one selected global $H$ transported unchanged across new tasks.
The proposing procedure $G$ is not changed or compared through independent
method lineages. Consequently, the result establishes neither global method
transfer nor recursive self-improvement. More method text, a changed device,
and a selected historical latch response are distinct objects and claims.

The prospective phase3 protocol does not erase phase2's failure. Its original
nine-request proposal episode remains blocked at the host action/budget
contract; recovering actual model-authored text was explicitly posthoc, and
that phase's initial-cache parity was not established. Phase3 matches the
initial cache and uses prospective role separation, but cannot retroactively
make that earlier episode successful. Prior A/R fixed-space NO\_GO, strict
FIFO FAIL and product NOT\_ACCEPTED also remain intact. Physical validation
and product acceptance are separate from every service PASS reported here.

\subsection{Frozen next step and reproducibility}
The selection for the next phase retains the base $H$. Two frozen parameter
derivatives, one with a stretched BF supply window and one with a C-Lite query
at half power, are candidates for within-model digital generalization only.
They have no participant exposure or scientific
execution in the supplied freeze. They are not a new physical family or an
executed transfer result. The historical \texttt{b-esr-fail} and
\texttt{b-no-energy} controls have already been used and cannot be called
unseen. The freeze's explicit historical-control classification takes
precedence over the older holdout wording retained in the selection-rule
string. A separately admitted execution would be required for the new tasks.

\texttt{phase3-binding.json} pins the seven primary S0 files, this manuscript's
sources, the unchanged shared style and official English vector logo, and the
compiled PDF. \texttt{render\_phase3.py build} reads those files and recomputes
only tables and counts before two TeX passes; it never runs the scientific
apparatus, model, SDK smoke or tests. Small build, all-page visual and cleanup
receipts are retained under
\path{docs/research/phase3-20261020/methods/paper-final/}.
The current writing adds zero provider requests, scientific executions or
native calls. Earlier manuscripts, code, configurations, tests and handoffs
are preserved. No fresh-clone or independent-host rebuild is claimed.
"""


def readback(data):
    main = data["main-tables.json"]
    comparison = data["actual-comparison.json"]
    protocol = data["protocol.json"]
    formal = {x["condition"]: x for x in main["formal"]}
    pilot = {x["condition"]: x for x in main["pilot"]}
    assert main["formal_task_count"] == 4 and main["formal_repetitions_per_task"] == 3
    assert sum(x["run_count"] for x in main["formal"]) == 96
    assert sum(x["run_count"] for x in main["pilot"]) == 16
    assert main["group_count"] == 112 and main["actual_episode_count"] == 140
    assert main["accounting"]["requests"] == 771 and main["accounting"]["unknown_usage"] == []
    assert comparison["accounting"] == main["accounting"]
    assert protocol["group_limits"]["provider_requests"] == 24
    assert protocol["group_limits"]["wall_seconds"] == 1200
    assert protocol["group_limits"]["H_proposal_requests"] == 8
    assert protocol["group_limits"]["H_proposal_wall_s"] == 400
    assert data["formal-repeat-freeze.json"]["formal_repetitions"] == 3
    assert data["formal-repeat-freeze.json"]["adapt_after_this_freeze"] is False
    assert main["selection"]["condition_decision"] == "KEEP_UNCHANGED_BASE_H"
    assert not main["selection"]["default_H_changed"]
    assert main["selection"]["task_success_vectors"] == {x: [3, 3, 3, 3] for x in METHODS}
    groups = list(comparison["groups"].values())
    assert len(groups) == 112 and sum(len(x["episodes"]) for x in groups) == 140
    for condition, expected in zip(METHODS, [64, 117, 127]):
        row = formal[condition]
        subset = [x for x in groups if x["condition"] == condition and x["stage"] == "formal"]
        assert len(subset) == 12 and row["service_counts"] == {"PASS": 12}
        assert row["requests"] == sum(x["requests"] for x in subset) == expected
        assert all(x["fresh_task_entry"] and not x["unknown_usage"] for x in subset)
        assert all(x["initial_cache_sha256"] == protocol["initial_cache_sha256"] for x in subset)
        assert all(x["requests"] <= 24 and x["wall_s"] <= 1200 for x in subset)
        decisions = Counter(x["H_proposal"]["decision"] for x in subset if "H_proposal" in x)
        assert dict(decisions) == row["H_proposal_counts"]
    assert formal["ordinary_reflection"]["H_proposal_counts"] == {"propose": 10, "no-update": 2}
    assert formal["proposed_method"]["H_proposal_counts"] == {"propose": 12}
    assert len(comparison["matched_methods"]) == 28
    assert all(all(x["parity"].values()) for x in comparison["matched_methods"])
    deterministic = comparison["deterministic_controls"]
    assert len(deterministic) == 107
    assert Counter(x["changed_D"] for x in deterministic) == {True: 91, False: 16}
    assert sum(x["new_scientific_executions_for_comparison"] for x in deterministic) == 0
    for record in deterministic:
        assert record["source_bound_identity"] == "PASS"
        if record["changed_D"]:
            assert record["strategies"][0]["disposition"] == "INVALID_FOR_CHANGED_INPUT"
        valid = record["strategies"][1:]
        assert {x["scope"] for x in valid} == {"full-feedback-response"}
        assert len({x["actual_execution_key"] for x in valid}) == 1
    witnesses = data["ordered-selected-witnesses.json"]
    assert witnesses["selected_groups"] == 4 and witnesses["distinct_physical_execution_keys"] == 1
    assert witnesses["new_scientific_executions_for_audit"] == 0
    assert Counter(x["condition"] for x in witnesses["witnesses"]) == {
        "complete-raw": 2, "proposed_method": 1, "e4-rich-static-table": 1}
    for witness in witnesses["witnesses"]:
        state = witness["ordered_state"]
        assert witness["physical_response_reused"] and witness["world"] == "b-latched-reset"
        assert witness["design"] == {"capacitance_f": 1e-5, "tx_not_before_s": .045}
        reset = state["resets_before_first_delivery"][0]["time_s"]
        assert abs(witness["capture_last_s"] - .0079) < 1e-12
        assert witness["capture_last_s"] < reset < state["first_valid_receive_s"]
        assert abs(reset - .0121) < 1e-12 and abs(state["first_valid_receive_s"] - .0469) < 1e-12
        assert state["event_origin"]["receiver_event_id_matches"]
        assert state["physical_qualification"] == "UNKNOWN"
    assert sum(x["ordered_event_counts"].get("DELIVERED_BEFORE_ANY_RESET", 0) for x in main["formal"]) == 83
    initial = data["ordered-initial-controls.json"]
    assert initial["new_scientific_executions"] == initial["provider_requests"] == 0
    stage4 = data["stage4-selection-freeze.json"]
    assert stage4["historical_controls_not_counted_as_unseen"] == ["b-esr-fail", "b-no-energy"]
    assert all(x["participant_exposures"] == x["scientific_executions"] == 0 for x in stage4["new_unexposed_tasks"])
    return main, formal, pilot


def paper_text(data):
    main, formal, pilot = readback(data)
    formal_rows, pilot_rows = [], []
    for condition in METHODS:
        row = formal[condition]
        counts = row["H_proposal_counts"]
        proposals = f"{counts.get('propose', 0)} / {counts.get('no-update', 0)}" if counts else "---"
        formal_rows.append(f"{LABELS[condition]} & 12/12 & {proposals} & {row['requests']}"
                           f" & {row['requests']/12:.3f} & {Decimal(str(row['settled_upper_usd'])):.7f} " + r"\\")
        row = pilot[condition]
        pilot_rows.append(f"{LABELS[condition]} & 2/2 & {row['requests']} & {row['requests']/2:.3f} " + r"\\")
    values = {"PILOT_REQUESTS": sum(x["requests"] for x in main["pilot"]),
              "FORMAL_REQUESTS": sum(x["requests"] for x in main["formal"]),
              "ALL_REQUESTS": main["accounting"]["requests"],
              "PILOT_ROWS": "\n".join(pilot_rows), "MAIN_ROWS": "\n".join(formal_rows)}
    text = TEXT
    for key, value in values.items():
        text = text.replace("@" + key + "@", str(value))
    assert not re.search(r"@[A-Z0-9_]+@", text)
    return text


def clean():
    visual = read(FINAL / "visual-review.json")
    assert visual["status"] == "PASS_ALL_PAGES"
    assert visual["pdf_sha256"] == meta(PAPER / "phase3.pdf")["sha256"]
    removed = {}
    for raster in FINAL.glob("phase3-page-*.png"):
        assert visual["page_rasters"][raster.name] == meta(raster)
        removed[raster.name] = meta(raster)
        raster.unlink()
    if SCRATCH.exists():
        assert SCRATCH.resolve().parent == FINAL.resolve()
        for path in SCRATCH.rglob("*"):
            if path.is_file():
                removed[str(path.relative_to(FINAL))] = meta(path)
        shutil.rmtree(SCRATCH)
    receipt = {"status": "CLEANED_ONLY_THIS_PHASE3_BUILD_AND_REVIEWED_PAGE_RASTERS",
               "at_utc": datetime.now(timezone.utc).isoformat(), "removed_files": removed,
               "removed_logical_bytes": sum(x["bytes"] for x in removed.values()),
               "pdf": meta(PAPER / "phase3.pdf"), "visual_receipt": meta(FINAL / "visual-review.json")}
    save(FINAL / "cleanup.json", receipt)
    print(json.dumps({"status": receipt["status"], "removed_logical_bytes": receipt["removed_logical_bytes"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "clean"), nargs="?", default="build")
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    binding = read(BINDING)
    root = args.data_root or Path(binding["primary_data_root"])
    verify(root, binding["primary_inputs"])
    verify(PAPER, binding["shared_style_inputs"])
    admission = read(PAPER / binding["admission"])
    verify(WORLD, admission["protected_critical_files_only"])
    if args.action == "clean":
        clean()
        return
    assert shutil.disk_usage(PAPER).free >= admission["minimum_reserve_plus_phase_peak_bytes"]
    if binding["paper_inputs"]:
        verify(PAPER, binding["paper_inputs"])
    data = {name: read(root / name) for name in binding["primary_inputs"]}
    (PAPER / "phase3-methods.tex").write_text(paper_text(data))
    SCRATCH.mkdir(exist_ok=True)
    binding.setdefault("pdf_source_date_epoch", int(datetime.now(timezone.utc).timestamp()))
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(binding["pdf_source_date_epoch"]),
               FORCE_SOURCE_DATE="1", TZ="UTC")
    latex = shutil.which("pdflatex") or "/Library/TeX/texbin/pdflatex"
    args = [latex, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", "-recorder",
            "-jobname=phase3", "-output-directory=" + str(SCRATCH), "phase3-manuscript.tex"]
    for iteration in (1, 2):
        (FINAL / f"build-pass{iteration}.stdout.log").write_text(command(args, env))
    log = (SCRATCH / "phase3.log").read_text()
    assert "Overfull" not in log, "Repair overfull box before accepting the PDF"
    assert "undefined references" not in log, "Unresolved reference after two TeX passes"
    shutil.copyfile(SCRATCH / "phase3.log", FINAL / "phase3-compile.log")
    shutil.copyfile(SCRATCH / "phase3.fls", FINAL / "phase3-inputs.fls")
    shutil.copyfile(SCRATCH / "phase3.pdf", PAPER / "phase3.pdf")
    info = command(["pdfinfo", str(PAPER / "phase3.pdf")])
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE).group(1))
    assert 1 <= pages <= 7
    (FINAL / "pdfinfo.txt").write_text(info)
    command(["pdftotext", "-layout", str(PAPER / "phase3.pdf"), str(FINAL / "phase3.txt")])
    text = (FINAL / "phase3.txt").read_text()
    for expected in ["64", "117", "127", "12/12", "5.4478605", "KEEP_UNCHANGED_BASE_H"]:
        assert expected in text, expected
    command(["pdftoppm", "-scale-to", "1500", "-png", str(PAPER / "phase3.pdf"), str(FINAL / "phase3-page")])
    rasters = {p.name: meta(p) for p in sorted(FINAL.glob("phase3-page-*.png"))}
    assert len(rasters) == pages
    fonts = command(["pdffonts", str(PAPER / "phase3.pdf")])
    (FINAL / "pdffonts.txt").write_text(fonts)
    assert all(line.split()[-5] == "yes" for line in fonts.splitlines()[2:] if line.strip())
    binding["paper_inputs"] = {name: meta(PAPER / name) for name in
                               ["phase3-methods.tex", "phase3-manuscript.tex", "render_phase3.py"]}
    binding["outputs"] = {"phase3.pdf": meta(PAPER / "phase3.pdf"), "pages": pages,
                          "compile_status": "SUCCESS_TWO_PASSES_NO_OVERFULL_OR_UNDEFINED_REFERENCES",
                          "visual_status": "PENDING_ALL_PAGE_REVIEW"}
    binding["rebuild"] = {"command": "python -B render_phase3.py build", "cwd": str(PAPER),
                          "data_override": "--data-root /path/to/the/same/seven/pinned/files",
                          "environment": {k: env[k] for k in ["SOURCE_DATE_EPOCH", "FORCE_SOURCE_DATE", "TZ"]},
                          "scope": "Counts/tables and this new paper only; no scientific or test execution"}
    save(BINDING, binding)
    receipt = {"schema_version": "bf-phase3-method-paper-build-v1",
               "at_utc": datetime.now(timezone.utc).isoformat(), "status": "COMPILED_REQUIRES_ALL_PAGE_VISUAL_REVIEW",
               "pdf": meta(PAPER / "phase3.pdf"), "binding": meta(BINDING), "pages": pages,
               "latex_command": args, "passes": 2, "page_rasters": rasters,
               "latex_version": command([latex, "--version"]).splitlines()[0],
               "overfull_boxes": 0, "undefined_references": 0, "all_fonts_embedded": True,
               "protected_critical_file_count": len(admission["protected_critical_files_only"]),
               "new_provider_requests": 0, "new_scientific_executions": 0,
               "native_dispatches": 0, "test_runs": 0, "SDK_smoke_runs": 0, "full_init_runs": 0}
    save(FINAL / "build.json", receipt)
    print(json.dumps({"status": receipt["status"], "pages": pages, "pdf": receipt["pdf"],
                      "page_rasters": list(rasters)}))


if __name__ == "__main__":
    main()
