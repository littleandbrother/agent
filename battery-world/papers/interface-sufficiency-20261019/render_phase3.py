#!/usr/bin/env python3
"""Render the Phase 3 paper from existing receipts; never run a scientific tool.

Uses the Python standard library. The renderer reads seven authoritative JSONs,
five original failed-group gateway logs, and small frozen provenance files. It
only writes phase3-methods.tex and phase3-binding.json. PDF compilation and human
visual review are bound by --finalize; neither is a scientific verification run.
"""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import signal

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
RECEIPTS = PROJECT / "docs/research/phase3-20261020/interfaces/paper-final"
SOURCE_DEFAULT = Path("/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/phase-plan-20261019/phase3")
EPISODES_DEFAULT = Path("/Users/depengsu/.local/share/bf-phase3-20261020/episodes")
FILES = (
    "main-tables.json", "actual-comparison.json", "protocol.json",
    "formal-repeat-freeze.json", "ordered-selected-witnesses.json",
    "ordered-initial-controls.json", "stage4-selection-freeze.json",
)
ARMS = (
    "average-energy", "rich-static", "complete-raw", "executable-response",
    "live-e5", "e4-rich-static-table",
)
LABELS = {
    "average-energy": "Average-energy",
    "rich-static": "Rich-static / E4 JSON",
    "complete-raw": "Complete-input (complete-raw)",
    "executable-response": "Executable-response",
    "live-e5": "Live observation (E5)",
    "e4-rich-static-table": "E4 table",
}
TASK_LABELS = {
    "b-pulse-fast": "Pulse-fast",
    "b-volatile-reset": "Volatile-reset",
    "b-latched-reset": "Latched-reset",
    "clite-query-window-derived-v1": "C-lite query derivative",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound(path, role):
    return {"path": str(path.resolve()), "sha256": digest(path),
            "bytes": path.stat().st_size, "role": role}


def load(path):
    return json.loads(path.read_text())


def close(left, right):
    assert math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-9), (left, right)


def summarize_groups(groups, rows, stage):
    for row in rows:
        selected = [g for g in groups if g["stage"] == stage and g["condition"] == row["condition"]]
        assert len(selected) == row["run_count"]
        assert len({g["world"] for g in selected}) == row["task_count"]
        assert dict(Counter(g["complete_service"] for g in selected)) == row["service_counts"]
        assert sum(g["requests"] for g in selected) == row["requests"]
        close(sum(g["settled_upper_usd"] for g in selected), row["settled_upper_usd"])
        close(sum(g["wall_s"] for g in selected), row["wall_s"])
        close(row["requests"] / len(selected), row["mean_group_requests"])
        for task, counts in row["per_task_counts"].items():
            assert dict(Counter(g["complete_service"] for g in selected if g["world"] == task)) == counts
        ordered = Counter(g.get("ordered_event_state", {}).get("classification", "NO_ADMITTED_EXECUTION") for g in selected)
        assert dict(ordered) == row["ordered_event_counts"]


def ast_fields(node):
    if isinstance(node, dict):
        return ([node["field"]] if "field" in node else []) + [f for value in node.values() for f in ast_fields(value)]
    if isinstance(node, list):
        return [f for value in node for f in ast_fields(value)]
    return []


def failed_binding_diagnostics(e5_rows, episode_root):
    diagnostics, sources = [], []
    for row in e5_rows:
        if row["complete_service"] != "INCOMPLETE":
            continue
        path = episode_root / (row["group"] + "-e5") / "gateway/gateway-events.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()]
        starts, acquired = {}, {}
        meaningful = []
        for event in events:
            data = event["data"]
            if event["kind"] == "tool_started":
                starts[data["number"]] = data["input"]
            elif event["kind"] == "tool_completed" and "source_id" in data["output"]:
                source = data["output"]
                acquired[source["source_id"]] = source
            elif event["kind"] == "tool_failed" and any(code in data["error"] for code in ("SOURCE_UNIT_UNAVAILABLE", "NO_TYPED_CONSUMER_MATCH")):
                meaningful.append((data, starts[data["number"]]))
        assert meaningful
        data, action = meaningful[0]
        spec = action["spec"]
        units = acquired[spec["source_id"]]["field_units"]
        fields = ([spec["field"]] if "field" in spec else ast_fields(spec.get("ast", {})))
        constraints = [c["field"] for c in spec["domain"]["constraints"]]
        diagnostic = {
            "group": row["group"], "source_id": spec["source_id"], "mode": spec["mode"],
            "first_relevant_error": data["error"], "tool_number": data["number"],
            "selected_or_ast_fields": fields,
            "mapped_selected_or_ast_fields": [field for field in fields if field in units],
            "unmapped_selected_or_ast_fields": [field for field in fields if field not in units],
            "unmapped_domain_fields": [field for field in constraints if field not in units],
        }
        if "SOURCE_UNIT_UNAVAILABLE" in data["error"]:
            assert diagnostic["unmapped_domain_fields"] or diagnostic["unmapped_selected_or_ast_fields"]
            diagnostic["interpretation"] = "Source-local field/domain unit binding fails; the error alone does not establish absence of a physical quantity or isolate the first rejected term."
        else:
            assert spec["ast"]["op"] == "eq"
            assert all(isinstance(p["equals"], (int, float)) and not isinstance(p["equals"], bool) for p in action["policy"])
            diagnostic["relation_output_type_from_syntax"] = "boolean"
            diagnostic["policy_equals_values"] = [p["equals"] for p in action["policy"]]
            diagnostic["interpretation"] = "The submitted equality relation has Boolean output, while the submitted consumer branches match numeric durations; no qualifier/consumer was rerun."
        diagnostics.append(diagnostic)
        sources.append(bound(path, "Read-only original submitted proposal, acquisition mapping and failure; no compressed provider archive opened"))
    assert len(diagnostics) == 5
    assert sum("SOURCE_UNIT_UNAVAILABLE" in d["first_relevant_error"] for d in diagnostics) == 4
    assert sum("NO_TYPED_CONSUMER_MATCH" in d["first_relevant_error"] for d in diagnostics) == 1
    return diagnostics, sources


METHODS = r"""% Generated by render_phase3.py from the existing, immutable receipts.
% Presentation only: no model, simulator, qualifier, consumer or evaluator call.
\section{Frozen apparatus and matched protocol}
\subsection{Four fixed tasks and a complete-service outcome}
The first three tasks use the same versioned digital transient apparatus:
\path{b-pulse-fast}, \path{b-volatile-reset} and \path{b-latched-reset}.
Their design variables are capacitance and the earliest allowed transmission
time, within task-specific legal ranges. Pulse-fast is a static-sufficient
control. The reset cases expose the timing of capture, energy loss and later
delivery under volatile or ideal passive-latch state. A complete-service PASS
uses the registered independent receiver and event-order check. FAIL means an
admitted final execution failed that check. INCOMPLETE means no admitted final
execution; it is retained as a third outcome, never removed or replaced.

The fourth task, \path{clite-query-window-derived-v1}, is a preregistered
single-window derivative of proposed C-lite requirements~\cite{interfaces}.
It prescribes 20~$\mu$W DC input over 30~s, 1~$\mu$W idle power,
zero initial energy and a 50~$\mu$J reply. A query arrives at 2~s;
the reply deadline is 7~s and maximum data age is 5~s. Capacitance is limited
to 25--100~$\mu$F, corresponding to at most 200~$\mu$J at the ideal
2~V ceiling. Zero ESR, unit harvest efficiency and zero boot energy/delay
are explicit digital assumptions. They are not measured component properties.
The registered gates require query issuance, capture, the matching token,
causal ordering, deadline and freshness. Fixed sequence/key/event value 1
represents one virtual query token. It establishes neither a multi-query nonce
protocol nor security, RF behavior or qualified hardware.

\subsection{Conditions and information boundaries}
All arms receive the same task, legal design space, declared assumptions and
units. Average-energy starts with the coarse source integral and average power.
Rich-static and complete-raw both include every supplied input record and the
full model definition. Their equality in available facts is an admissible
negative control; ``complete-raw'' is the registered arm name, not a claim
that the model received the full coupled raw physical trace. That trace remains
host-side for audit. We call this arm complete-input in the tables to keep
the boundary visible.

Executable-response receives the same complete inputs plus candidate-specific
public energy ledgers, activity and packets. Live E5 instead starts coarse and
actually acquires sources through a generic interface. It can select a supplied
field or construct a bounded expression, declare its domain and units, submit
a typed consumer policy, and obtain independent qualification before final
service checking. No target expression or answer-bearing field relevance is
prefilled. Qualification checks the declared source relation; it does not by
itself prove service, novelty or the causal necessity of that observation.

E4 compares the rich-static packet in JSON with a typed JSON-Pointer table.
All @@E4_PAIRS@@ formal pairs have identical decoded initial packets and identical tools.
The table preserves containers, types, empty values and nested structure,
without adding summaries or answers. Later source-acquisition responses use
common JSON in both arms. Thus E4 isolates initial serialization only, rather
than the representation of an entire interactive trajectory.

\subsection{Accounting unit, freeze and cache}
The complete eight-condition matrix has @@GROUPS@@ unique groups and @@EPISODES@@ actual episodes:
@@FORMAL_GROUPS@@ formal groups (four tasks $\times$ three repetitions $\times$ eight conditions;
@@FORMAL_EPISODES@@ episodes) and @@PILOT_GROUPS@@ pilot groups (one task $\times$ two repetitions
$\times$ eight conditions; @@PILOT_EPISODES@@ episodes). A group includes every charged parent
method-proposal episode when one is present. This paper's six displayed interface
arms contain 72 formal and 12 pilot groups. Complete-raw is also the method
study's fixed-$H$ cell; rich-static is also E4 JSON. Each shared cell is counted
once, not redispatched or added again to the global totals.

The two pilots on volatile-reset precede the formal comparison. Under the
registered one-time rule, instability of designs/outcomes selects three formal
repetitions, rather than two. The repeat freeze records exactly one selection
event and forbids adaptation afterward~\cite{freeze}. A failed group is not
automatically retried or replaced; the fixed registered repetitions are separate
groups. Receipts report the model as \path{deepseek-flash} throughout this matrix.
These repetitions describe behavior on four used inputs, not independent samples
of new task families or a statistical acceptance test.

Every group has a total allowance of 24 provider requests, 40 tool calls,
1,200~s and at most two distinct design exposures, including checks, response
queries and confirmation. E5 acquisition, qualification and consumption receive
no extra design or total budget. Where used, a parent $H$ proposal has an
eight-request, 400~s sublimit within the group accounting. The campaign caps are
3,000 requests, USD~200 in settled conservative provider estimates and
134,400 summed episode seconds. Paid/new dispatch is closed for paper preparation.

Every arm starts from the same hash-bound immutable cache: twelve Phase 2
exact-input responses and one registered derivative baseline. Private overlays
isolate group outputs. A physical cache hit consumes logical exposure and
does not reveal another arm's output before a query or enlarge the design cap.
Here ``physical response'' is the cache accounting term for an underlying
digital execution, not evidence of laboratory hardware. Public development
feedback and the independent final check retain their registered boundaries.

\section{Formal results and separate pilot evidence}
\subsection{Strong static controls saturate complete service}
Table~\ref{tab:formal} retains all twelve formal groups per arm. Average-energy
has @@AVG_PASS@@ PASS and @@AVG_FAIL@@ FAIL. Rich-static, complete-input, executable-response
and E4 table each pass all twelve. E5 has @@E5_PASS@@ PASS and @@E5_INCOMPLETE@@ INCOMPLETE;
there is no admitted service FAIL in that arm. Those five incomplete groups
cannot be interpreted as five simulated physical failures or omitted to report
a conditional 7/7 success rate.

\begin{table}[htbp]
\centering\small
\caption{Formal interface results. Each row is four fixed tasks with three
repetitions each; P/F/I denote PASS/FAIL/INCOMPLETE. Requests include failures.}
\label{tab:formal}
\begin{tabular}{@{}lrrrrr@{}}\toprule
Condition & P & F & I & Requests & Mean/group \\\midrule
@@FORMAL_ROWS@@
\bottomrule\end{tabular}
\end{table}

The task breakdown in Table~\ref{tab:tasks} locates the coarse arm's observed
deficit in the two reset tasks: each has one PASS and two FAIL, while pulse-fast
and the C-lite derivative each have three PASS. The four strong arms each pass
all three repetitions on every task. This finite contrast is consistent with
the value of detailed timing/state information beyond the coarse summary.
It provides no service advantage for executable-response over the complete
static baseline, and no evidence that live E5 surpasses that baseline. Saturation
on four public tasks also prevents a conclusion that the strong interfaces
would be equivalent on harder or unseen tasks.

\begin{table}[htbp]
\centering\small
\caption{Per-task formal counts. Each entry is P/F/I out of three; the strong
column applies separately to rich-static, complete-input, executable-response
and E4 table. Repetitions do not enlarge the four-task denominator.}
\label{tab:tasks}
\begin{tabular}{@{}lccc@{}}\toprule
Fixed task & Average-energy & Live E5 & Each strong arm \\\midrule
@@TASK_ROWS@@
\bottomrule\end{tabular}
\end{table}

\subsection{Pilots are development evidence}
Table~\ref{tab:pilot} reports the two pilot repetitions on volatile-reset
separately. Average-energy has one PASS and one FAIL; every other displayed arm
has two PASS. The two E5 pilot successes include one construction and one
selection. These observations helped determine the frozen repeat count; they
are not pooled into the formal twelve-run denominator or treated as extra tasks.

\begin{table}[htbp]
\centering\small
\caption{Separate pilot results: one fixed task and two repetitions per arm.
The full eight-arm pilot contains sixteen groups and twenty actual episodes.}
\label{tab:pilot}
\begin{tabular}{@{}lrrrr@{}}\toprule
Condition & P & F & I & Requests \\\midrule
@@PILOT_ROWS@@
\bottomrule\end{tabular}
\end{table}

\section{What the prospective E5 chains establish}
All seven formal successes have an actual prospective submitted observation,
external source qualification and recorded typed consumer use. Six select
already supplied fields; one constructs a relation. Five use a component record
and two an excitation record. Six change the initial design and one leaves it
unchanged. Every successful final design passes the independent service check,
but typed consumption and design change do not establish that the observation
was necessary or unavailable to the complete static arm. All seven are based
on supplied data; new physical measurements number zero.

\begin{table}[htbp]
\centering\small
\caption{Disposition of all twelve formal E5 groups. Failure categories count
groups, not repeated rejected tool actions. Every row remains in the denominator.}
\label{tab:e5}
\begin{tabular}{@{}p{0.48\linewidth}rp{0.35\linewidth}@{}}\toprule
Disposition & Groups & Final service status \\\midrule
Qualified selection, consumed & 6 & PASS \\
Qualified construction, consumed & 1 & PASS \\
Source-unit binding rejected & 4 & INCOMPLETE; no admitted final execution \\
No typed consumer match & 1 & INCOMPLETE; no admitted final execution \\
\bottomrule\end{tabular}
\end{table}

Four groups record \texttt{SOURCE\_UNIT\_UNAVAILABLE} in the original
gateway events~\cite{gateways}. This code concerns the
submitted source/field/domain unit binding; it does not establish that a physical
quantity does not exist. For example, the pulse-fast proposal selects
\path{/packets/0/application_bytes}, which \emph{is} unit-mapped in its acquired
saved-activity record, while domain constraints reference deadline, TX-duration
and readiness fields absent from that same source's unit map. A latched-reset
proposal instead selects a packet field from the model-law source, whose mapped
fields are model identity and Python definition. These original submissions
show source-local binding mismatches. The generic error does not identify the
first rejected term, and no repaired proposal is evaluated here.

The remaining incomplete C-lite group records \path{NO_TYPED_CONSUMER_MATCH}.
Its submitted equality expression has Boolean output, while its consumer
branches match the numeric durations 0.002 and 0.001. This syntax-level
diagnosis uses the original proposal and log; it is not a qualifier or consumer
rerun. Other syntax and valid-proposal-cap errors in these groups remain charged
history, rather than additional independent failures or free rescue attempts.

The earlier Phase 2 actual episode remains a failed live E5 attempt. Its
separately labeled post-hoc adapter chain reused an already generated corrected
call; it is neither a prospective Phase 3 success nor a replacement for that
failure~\cite{phase2}. The seven formal chains reported here are actual
prospective submissions under the later registered protocol. This separation
preserves the distinction between an engineering repair demonstration and
prospective operational reliability.

\section{Equal-information serialization and ordered witnesses}
\subsection{E4 gives no observed service or request advantage}
Both E4 arms achieve 12/12 formal PASS and exactly 65 provider requests,
or 5.4167 per group. Equality of decoded initial packets and tools holds for
all twelve formal pairs. Table~\ref{tab:e4} gives provider cost and wall time
only as descriptive receipts. Equal service and request totals do not prove
general equivalence; the cost and wall differences do not establish a format
advantage. The study neither isolates all determinants of latency/cost nor
tests a representation change in later common-JSON acquisitions.

\begin{table}[htbp]
\centering\small
\caption{E4 formal descriptive accounting. Dollars are provider-reported
settled conservative estimates, not an invoice audit. Wall time is summed
group time; no causal format-speed or format-cost claim is made.}
\label{tab:e4}
\begin{tabular}{@{}lrrrr@{}}\toprule
Initial representation & PASS & Requests & USD & Wall (s) \\\midrule
@@E4_ROWS@@
\bottomrule\end{tabular}
\end{table}

\subsection{Four fresh selections reuse one historical response}
Complete-service delivery and state retention across a reset are distinct
observations. A retention witness requires capture of the same event before
a brownout and its first valid delivery afterward. A reset after delivery,
or a PASS Boolean alone, is insufficient. The source-bound initial controls
are classified as delivery before any reset (pulse-fast), no valid event
delivery (volatile-reset), and pending-event retention across reset
(latched-reset)~\cite{ordered}. These labels analyze existing responses without
a new scientific execution.

Four formal Agent groups select the across-reset outcome: two complete-input
(fixed-$H$) groups, one proposed-method group, and one E4 table group.
They are four fresh Agent choices but share one distinct historical digital
execution key. All choose $C=10~\mu$F and an earliest TX time of 45~ms.
Table~\ref{tab:order} records their common ordered witness. The fixed ideal
passive-mechanical latch supplies the retention mechanism; these choices
neither invent a memory mechanism nor qualify a physical implementation.
All four have physical qualification UNKNOWN. The witness audit creates
zero new scientific executions.

\begin{table}[htbp]
\centering\small
\caption{One historical digital response reused by four formal selections.
Capture ends before brownout, and first valid reception follows brownout.}
\label{tab:order}
\begin{tabular}{@{}lrp{0.53\linewidth}@{}}\toprule
Event & Time (ms) & Source-bound interpretation \\\midrule
Capture interval & 3.7--7.9 & Same task event 1 captured before reset \\
Brownout & 12.1 & Pending captured event retained by the ideal latch \\
Earliest allowed TX & 45.0 & Selected design parameter \\
First valid receive & 46.9 & Same event first delivered after reset \\
\bottomrule\end{tabular}
\end{table}

Most other formal successes deliver before any reset. All twelve rich-static,
all twelve executable-response and all seven successful E5 groups are in that
category. Such service successes do not demonstrate survival of pending state
across a reset. Four selected groups and one underlying execution key must not
be reported as four new physical experiments or four independent retention
mechanisms.

\section{Accounting, interpretation and next gate}
The full eight-condition campaign records @@REQUESTS@@ provider requests, all SETTLED,
with no new UNKNOWN usage. Its settled conservative estimate is
USD~@@COST@@ and summed episode wall time is @@WALL@@~s. This accounting includes
the two method-proposal arms and their parent episodes, not only the six
interface rows. It is provider-reported accounting without an invoice audit;
Codex assistance and full end-to-end cost remain UNKNOWN. The current paper
rendering adds no provider request, scientific execution or native dispatch.

The observed coarse-information deficit is task dependent. Strong static
inputs already provide enough information to reach complete service on all
four fixed tasks. An executable interface may still provide useful audit
structure, but this study does not demonstrate an additional service benefit.
E5's seven successful chains establish that acquired source data can be admitted,
qualified and consumed prospectively. The five incomplete chains expose the
operational cost of that route under the same total allowance. Its six field
selections and one construction do not establish autonomous discovery of an
unseen physical relation.

The fixed tasks, small repeat count, one reported model, development exposure
and saturated controls limit generalization. Synthetic DC input does not supply
RF field measurements, conversion/load-response waveforms, calibrated startup
or leakage, clock uncertainty or actual PHY reliability. A full host-side trace
and an independently checked digital PASS therefore remain separate from
physical qualification.

The preregistered Phase 4 selection rule promotes a proposed procedure only
with more task-level complete-service passes than both fixed-$H$ and reflection,
no lost task and no higher mean group request count~\cite{selection}.
All three formal task-success vectors are $(3,3,3,3)$; proposed-method requests
average 10.5833 per group, versus 5.3333 for fixed-$H$ and 9.7500 for reflection.
The recorded decision is to retain unchanged base $H$. The two reserved
within-model parameter-generalization tasks remain unexecuted here and require
separate admission. Historical controls do not become unseen tasks. Nothing
in Phase 3 establishes global transfer of $H$ or recursive improvement.

\subsection{Reproducible manuscript binding}
\path{render_phase3.py} reads the seven authoritative Phase 3 JSONs and verifies
their group, outcome, accounting and hash relationships before generating this
methods/results fragment. It also reads the five original failed-group gateway
logs for the bounded diagnostics above, without opening compressed provider
archives. It invokes no simulator, model, qualifier, consumer or service checker.
\path{phase3-binding.json} binds exact source bytes, both TeX sources, the renderer,
shared layout/logo and final PDF. The paper-final receipts record compilation,
per-page visual inspection and cleanup of this build's temporary files.
This validates the manuscript's presentation and source binding; it is not a
new scientific replication or a full audit of the historical campaign.
"""


def render(main, protocol, counts):
    formal = {r["condition"]: r for r in main["formal"]}
    pilot = {r["condition"]: r for r in main["pilot"]}

    def outcome(row):
        return [row["service_counts"].get(k, 0) for k in ("PASS", "FAIL", "INCOMPLETE")]

    formal_rows = []
    pilot_rows = []
    for arm in ARMS:
        row = formal[arm]
        formal_rows.append(" & ".join([LABELS[arm], *map(str, outcome(row)), str(row["requests"]), f'{row["mean_group_requests"]:.4f}']) + r" \\")
        row = pilot[arm]
        pilot_rows.append(" & ".join([LABELS[arm], *map(str, outcome(row)), str(row["requests"])]) + r" \\")
    task_rows = []
    for task in protocol["tasks"]:
        assert isinstance(task, str)
        cells = ["/".join(str(formal[arm]["per_task_counts"][task].get(k, 0)) for k in ("PASS", "FAIL", "INCOMPLETE")) for arm in ("average-energy", "live-e5", "rich-static")]
        task_rows.append(" & ".join([TASK_LABELS[task], *cells]) + r" \\")
    e4_rows = []
    for arm, label in (("rich-static", "JSON (rich-static)"), ("e4-rich-static-table", "Typed table")):
        row = formal[arm]
        e4_rows.append(f'{label} & {row["service_counts"]["PASS"]}/12 & {row["requests"]} & {row["settled_upper_usd"]:.7f} & {row["wall_s"]:.1f}' + r" \\")
    replacements = {
        "FORMAL_ROWS": "\n".join(formal_rows), "PILOT_ROWS": "\n".join(pilot_rows),
        "TASK_ROWS": "\n".join(task_rows), "E4_ROWS": "\n".join(e4_rows),
        "E4_PAIRS": len([p for p in main["e4_pairs"] if p["stage"] == "formal"]),
        "GROUPS": main["group_count"], "EPISODES": main["actual_episode_count"],
        "FORMAL_GROUPS": counts["formal_groups"], "PILOT_GROUPS": counts["pilot_groups"],
        "FORMAL_EPISODES": counts["formal_episodes"], "PILOT_EPISODES": counts["pilot_episodes"],
        "AVG_PASS": formal["average-energy"]["service_counts"]["PASS"],
        "AVG_FAIL": formal["average-energy"]["service_counts"]["FAIL"],
        "E5_PASS": formal["live-e5"]["service_counts"]["PASS"],
        "E5_INCOMPLETE": formal["live-e5"]["service_counts"]["INCOMPLETE"],
        "REQUESTS": main["accounting"]["requests"], "COST": f'{main["accounting"]["settled_upper_usd"]:.7f}',
        "WALL": f'{main["accounting"]["wall_s"]:.1f}',
    }
    text = METHODS
    for key, value in replacements.items():
        text = text.replace("@@" + key + "@@", str(value))
    assert "@@" not in text
    return text


def run(args):
    signal.alarm(60)
    sources = [bound(args.source_dir / name, "Authoritative closed Phase 3 matrix receipt") for name in FILES]
    documents = {name: load(args.source_dir / name) for name in FILES}
    main = documents["main-tables.json"]
    comparison = documents["actual-comparison.json"]
    protocol = documents["protocol.json"]
    freeze = documents["formal-repeat-freeze.json"]
    witnesses = documents["ordered-selected-witnesses.json"]
    controls = documents["ordered-initial-controls.json"]
    selection_freeze = documents["stage4-selection-freeze.json"]
    assert main["source_bindings"]["comparison"] == digest(args.source_dir / "actual-comparison.json")
    assert main["source_bindings"]["protocol"] == digest(args.source_dir / "protocol.json")
    assert witnesses["comparison_sha256"] == main["source_bindings"]["comparison"]
    groups = list(comparison["groups"].values())
    assert len(groups) == main["group_count"] == 112
    assert len(protocol["episodes"]) == main["actual_episode_count"] == 140
    assert len({g["id"] for g in groups}) == 112
    assert sum(len(g["episodes"]) for g in groups) == 140
    assert {e["id"] for g in groups for e in g["episodes"]} == {e["id"] for e in protocol["episodes"]}
    assert len(protocol["tasks"]) == main["formal_task_count"] == 4
    assert len(protocol["conditions"]) == 8
    assert main["formal_repetitions_per_task"] == freeze["formal_repetitions"] == 3
    assert freeze["repeat_selection_events"] == 1 and freeze["stable_across_two_pilots"] is False
    assert freeze["adapt_after_this_freeze"] is False and freeze["no_original_failure_replaced"] is True
    counts = {stage + "_groups": sum(g["stage"] == stage for g in groups) for stage in ("formal", "pilot")}
    counts.update({stage + "_episodes": sum(e["stage"] == stage for e in protocol["episodes"]) for stage in ("formal", "pilot")})
    assert counts == {"formal_groups": 96, "pilot_groups": 16, "formal_episodes": 120, "pilot_episodes": 20}
    assert len({(g["world"], g["condition"], g["replicate"]) for g in groups if g["stage"] == "formal"}) == 96
    assert all(g["fresh_task_entry"] is True for g in groups)
    assert all(g["initial_cache_sha256"] == protocol["initial_cache_sha256"] for g in groups)
    assert all(g["reported_models"] == ["deepseek-flash"] for g in groups)
    assert all(not g["unknown_usage"] for g in groups) and not main["accounting"]["unknown_usage"]
    assert sum(g["requests"] for g in groups) == main["accounting"]["requests"] == 771
    close(sum(g["settled_upper_usd"] for g in groups), main["accounting"]["settled_upper_usd"])
    close(sum(g["wall_s"] for g in groups), main["accounting"]["wall_s"])
    summarize_groups(groups, main["formal"], "formal")
    summarize_groups(groups, main["pilot"], "pilot")
    expected = {"average-energy": (8, 4, 0), "live-e5": (7, 0, 5)}
    formal = {r["condition"]: r for r in main["formal"]}
    for arm in ARMS:
        assert tuple(formal[arm]["service_counts"].get(k, 0) for k in ("PASS", "FAIL", "INCOMPLETE")) == expected.get(arm, (12, 0, 0))
    assert len(main["e4_pairs"]) == 14
    assert all(p["identical_decoded_initial_packet"] and p["identical_tool"] for p in main["e4_pairs"])
    pairs = [p for p in main["e4_pairs"] if p["stage"] == "formal"]
    assert len(pairs) == 12
    assert sum(p["json_requests"] for p in pairs) == sum(p["table_requests"] for p in pairs) == 65
    e5 = [r for r in main["e5_audit"] if r["stage"] == "formal"]
    successes = [r for r in e5 if r["complete_service"] == "PASS"]
    assert len(e5) == 12 and len(successes) == 7
    assert Counter(r["mode"] for r in successes) == {"selection": 6, "construction": 1}
    assert Counter(r["source_id"] for r in successes) == {"component_record": 5, "excitation_record": 2}
    assert sum(r["design_changed"] for r in successes) == 6
    assert all(r["typed_observation_consumed"] and r["qualification"]["prospective"] and r["qualification"]["independent_scalar_value_agrees"] and r["qualification"]["status"] == "EXTERNAL_PASS" for r in successes)
    assert all(r["new_physical_measurement"] is False for r in main["e5_audit"])
    diagnostics, gateway_sources = failed_binding_diagnostics(e5, args.episode_dir)
    sources.extend(gateway_sources)
    assert witnesses["selected_groups"] == len(witnesses["witnesses"]) == 4
    assert witnesses["distinct_physical_execution_keys"] == len({w["execution_key"] for w in witnesses["witnesses"]}) == 1
    assert witnesses["new_scientific_executions_for_audit"] == 0
    assert Counter(w["condition"] for w in witnesses["witnesses"]) == {"complete-raw": 2, "proposed_method": 1, "e4-rich-static-table": 1}
    for witness in witnesses["witnesses"]:
        assert witness["physical_response_reused"] and witness["stage"] == "formal" and witness["service"] == "PASS"
        assert witness["ordered_state"]["classification"] == "PENDING_EVENT_RETAINED_ACROSS_RESET"
        assert witness["ordered_state"]["physical_qualification"] == "UNKNOWN"
        close(witness["design"]["capacitance_f"], 1e-5)
        close(witness["design"]["tx_not_before_s"], .045)
        close(witness["capture_first_s"], .0037)
        close(witness["capture_last_s"], .0079)
        close(witness["ordered_state"]["resets_before_first_delivery"][0]["time_s"], .0121)
        close(witness["ordered_state"]["first_valid_receive_s"], .0469)
    assert controls["new_scientific_executions"] == controls["provider_requests"] == 0
    assert {r["case"]: r["ordered_evaluation"]["classification"] for r in controls["controls"]} == {
        "b-pulse-fast": "DELIVERED_BEFORE_ANY_RESET", "b-volatile-reset": "NO_VALID_EVENT_DELIVERY",
        "b-latched-reset": "PENDING_EVENT_RETAINED_ACROSS_RESET"}
    assert selection_freeze["frozen_before_formal_comparison"] is True
    assert selection_freeze["provider_requests"] == selection_freeze["new_environments"] == 0
    assert len(selection_freeze["new_unexposed_tasks"]) == 2
    assert all(t["scientific_executions"] == t["participant_exposures"] == 0 for t in selection_freeze["new_unexposed_tasks"])
    assert main["selection"]["condition_decision"] == "KEEP_UNCHANGED_BASE_H"
    assert main["selection"]["default_H_changed"] is False and main["selection"]["global_transferable_H_proven"] is False
    assert all(v == [3, 3, 3, 3] for v in main["selection"]["task_success_vectors"].values())
    derived_path = PROJECT / "configs/studies/phase3-20261020/interfaces/derived-case.json"
    derived = load(derived_path)
    assert derived["id"] == "clite-query-window-derived-v1" and not derived["measured_physical_data"]
    assert derived["task"]["query"]["issued_s"] == 2 and derived["task"]["receiver"]["deadline_s"] == 7
    assert derived["task"]["receiver"]["max_data_age_s"] == 5
    sources.append(bound(derived_path, "Frozen synthetic derivative preparation/ancestry; historical not-executed status is superseded by actual matrix receipts"))
    sources.append(bound(PROJECT / "configs/studies/phase3-20261020/interfaces/conditions.json", "Frozen information/serialization preparation"))
    catalog = Path(derived["source"]["path"])
    assert digest(catalog) == derived["source"]["sha256"]
    sources.append(bound(catalog, "Proposal-only C-lite requirements ancestry; not measured capabilities"))
    prior = HERE / "phase2-binding.json"
    assert load(prior)["original_live_E5_success"] is False
    sources.append(bound(prior, "Frozen Phase 2 original failure versus separately labeled post-hoc validation boundary"))
    before = load(RECEIPTS / "scope-before.json")
    assert all(bound(PROJECT / relative, "guard")["sha256"] == receipt["sha256"] for relative, receipt in before["files"].items())
    methods = render(main, protocol, counts)
    methods_path = HERE / "phase3-methods.tex"
    methods_path.write_text(methods)
    artifacts = [bound(path, role) for path, role in (
        (HERE / "phase3-manuscript.tex", "Manuscript source"), (methods_path, "Receipt-rendered methods/results source"),
        (Path(__file__), "Presentation-only renderer"), (PROJECT / "papers/shared/hkustgz-paper.sty", "Unchanged shared layout"),
        (PROJECT / "papers/shared/assets/hkustgz-english.pdf", "Unchanged official vector logo"))]
    result = {
        "schema_version": "bf-phase3-paper-binding-v1", "mode": "ACTUAL_CLOSED_MATRIX_PAPER_FINALIZATION",
        "source_dir": str(args.source_dir.resolve()), "sources": sources, "paper_sources_and_style": artifacts,
        "source_relationship_checks": "PASS", "counts": counts, "actual_episode_count": 140,
        "distinct_fixed_tasks": 4, "formal_repeats_per_task": 3, "global_accounting": main["accounting"],
        "displayed_arms": list(ARMS), "formal": [formal[a] for a in ARMS],
        "e5_group_failure_diagnostics": diagnostics,
        "e5_formal": {"PASS": 7, "FAIL": 0, "INCOMPLETE": 5, "denominator": 12, "selection": 6, "construction": 1, "new_physical_measurements": 0},
        "e4_formal": {"matched_pairs": 12, "decoded_initial_packet_and_tools_identical": True,
                      "json_pass": 12, "table_pass": 12, "json_requests": 65, "table_requests": 65,
                      "scope": "Initial serialization only; later acquisitions common JSON. Cost/wall descriptive, no format advantage."},
        "ordered_witness": {"fresh_selected_formal_groups": 4, "distinct_historical_digital_execution_keys": 1,
                            "new_scientific_executions": 0, "physical_qualification": "UNKNOWN",
                            "execution_key": witnesses["witnesses"][0]["execution_key"]},
        "stage4_decision": main["selection"]["condition_decision"],
        "authoring_execution": {"provider_requests": 0, "scientific_executions": 0, "qualifier_or_consumer_reruns": 0,
                                "native_dispatches": 0, "tests_or_CI_or_init": 0, "full_tree_hash_audit": False},
        "frozen_selected_guards_verified": True,
        "claim_boundary": "Four fixed public digital tasks, three formal repeats. Strong static controls all PASS; no superiority, autonomous new physical relation, hardware/RF qualification, global H transfer or RSI. Phase 2 failed and post-hoc records remain separate.",
        "self_binding": "This JSON is hashed by paper-final/HANDOFF.json; it deliberately excludes its own digest.",
        "build_status": "PENDING",
    }
    if args.finalize:
        verification = load(args.finalize)
        assert verification["compile"]["status"] == "PASS" and verification["compile"]["passes"] == 2
        assert not verification["compile"]["warnings"]
        assert verification["pdf_info"]["all_fonts_embedded"] is True
        assert all(verification["semantic_pdf_readback_checks"].values())
        assert verification["visual_review"]["status"] == "PASS"
        assert len(verification["visual_review"]["pages"]) == verification["pdf_info"]["pages"]
        assert all(p["status"] == "PASS" for p in verification["visual_review"]["pages"])
        for name, sha in verification["compile_input_sha256"].items():
            assert digest(HERE / name) == sha, name
        for name, sha in verification["source_sha256"].items():
            assert digest(args.source_dir / name) == sha, name
        pdf = HERE / "phase3.pdf"
        assert digest(pdf) == verification["pdf"]["sha256"]
        result.update({"build_status": "PASS", "pdf": bound(pdf, "Compiled final manuscript; no scientific execution"),
                       "verification_receipt": bound(args.finalize, "Two-pass compile, PDF/font/text readback and every-page visual review"),
                       "build": verification["compile"], "pdf_info": verification["pdf_info"],
                       "semantic_pdf_readback_checks": verification["semantic_pdf_readback_checks"],
                       "visual_review": verification["visual_review"]})
    (HERE / "phase3-binding.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "PASS", "paper_binding": result["build_status"], "counts": counts,
                      "e5": result["e5_formal"], "e4": result["e4_formal"], "sources_bound": len(sources)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--episode-dir", type=Path, default=EPISODES_DEFAULT)
    parser.add_argument("--finalize", type=Path)
    run(parser.parse_args())
