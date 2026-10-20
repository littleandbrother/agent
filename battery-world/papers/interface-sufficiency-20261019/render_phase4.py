#!/usr/bin/env python3
"""Render the complete Phase 4 paper from existing closed receipts.

Standard library only. No scientific imports, provider, simulator, evaluator,
scientific native tool. Never opens heldout input payloads or dispatches a job.
Reads the closed final-result tables. --build invokes only document tools;
--finalize requires hash-bound actual page-by-page visual review.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
DOC = PROJECT / "docs/research/phase4-20261020/interfaces/paper-final"
SOURCE = Path("/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/phase-plan-20261019/phase4")
EPISODES = Path("/Users/depengsu/.local/share/bf-phase4-20261020/episodes")
FILES = ("O0-transfer-results.json", "first-O0-result.json", "host-error-hold.json",
         "amendment-registration.json", "cache-repair-qualification.json", "protocol-v1.1.json")

METHODS = r"""% Generated from the closed Phase 4 receipts by render_phase4.py.
% Document rendering only; no model or scientific execution.
\section{Original O service and matched digital apparatus}
\subsection{Unchanged external task and service predicate}
All three O0 episodes use the original 21,600 s A0 supply schedule and zero
initial capacitor voltage. The photovoltaic area is 15 cm$^2$ and capacitance
is fixed at 15 mF. The six light intervals are 200, 0, 50, 200, 0 and 50 lux,
at boundaries 0, 120, 150, 180, 300, 330 and 360 minutes. Their assumed
electrical port powers are respectively 90, 0, 20, 90, 0 and 20 $\mu$W.
The 3500 K light specification is metadata; lux is never converted to watts.
Calibrated spectral irradiance and photovoltaic IV data are unavailable.

External RMS vibration is 0.08 g during 70--75, 130--135, 190--200 and
280--282 minutes and 0.005 g otherwise. Start requires continuously greater
than 0.05 g for 3 s; stop requires continuously below 0.01 g for 60 s.
The corresponding threshold equality resets confirmation. The event time is
the confirmation instant. Every start and stop must reach the receiver within
10 s and have a timestamp error at most 1 s. Received active-state messages
must cover each confirmed active interval with gaps at most 120 s. Darkness
is included; idle false messages fail. A correct final state cannot cancel
an earlier missing event or keepalive~\cite{case}.

The four confirmed active intervals end at 4560, 8160, 12060 and 16980 s.
They are service intervals, not a daily occupancy summary. In particular, the
130--135 minute activity window occurs within the first dark supply interval.
The event predicate neither replaces event history with an hourly state nor
accepts a retained NVM value as a newly observed event.

\subsection{Inherited energy law and proposed RMS costs}
The apparatus retains the A/R assumed source/cold-start/PMIC/capacitor and
digital receiver parameters. Harvest efficiency is 0.8, with 0.38 V and
3 $\mu$W cold-start gates. Ready/off voltages are 2.7/2.3 V; maximum capacitor
voltage is 3.3 V, rating 5.5 V and ESR 0.3 ohm. The managed output is 1.8 V
with 0.3 V dropout. Off/sleep power is 1/5 $\mu$W; boot and storage-side TX
costs are 100 and 130 $\mu$J. Transmission uses the existing ideal atomic
wire/CRC and receiver abstraction, not a qualified RF link.

The O addition declares 0.5 $\mu$W powered standby, 1 $\mu$J per wake,
20 $\mu$J per successful RMS sample and 5 $\mu$J per committed write.
The 20 $\mu$J value borrows the numerical A/R temperature-sample cost; it does
not qualify a vibration sensor. A write is charged when a record is committed,
not at every poll. NVM preserves committed state and the pending queue but
provides no sensing energy. Powered samples use a declared zero-order hold;
failed samples and brownouts reset continuous-confirmation timers.
Energy integration is piecewise and observations are compressed into sampling
runs. These are explicit digital assumptions with physical qualification
UNKNOWN~\cite{case}.

\subsection{Candidate, controls and public observations}
All three episodes share the same source, initial state, components, link,
service predicate and hardware. The legal candidate contains only typed
capacitance, sample period, thresholds, cache, retry/backoff and program
choices. The fixed periodic control takes one RMS snapshot every 60 s and
uploads it without an event confirmation state machine. The rich-state control
uses a one-second sampled start/stop state machine, 120 s active keepalive,
NVM queue, one-second retry and zero TX backoff. Each fixed control is its
episode's sole legal design; the candidate may check at most two distinct
designs under the same registered total allowance.

Every initial O0 episode has a ceiling of 24 provider requests, 40 tool calls,
1200 s and two distinct design exposures. Participants must actually inspect,
check, judge and submit. Source records carry hashes and unit maps. The common
public-response projection replaces every array longer than twelve entries
with its full count, canonical full-value hash, first six and last six entries.
The complete raw digital response remains host-sealed, and public feedback
contains no reference truth or host service label. Thus an evaluator's use of
the full response is separate from what the participant could inspect~\cite{protocol}.
All three episode receipts report the \path{deepseek-flash} provider alias;
the protocol leaves pinned weight identity UNKNOWN.

\section{Frozen procedures, selection and final information}
H0 is the unchanged base design procedure: read the fixed task and available
sources, choose a legal D, actually check it, then submit a source-bound design
and judgment while retaining failures and UNKNOWN. G0 is the fixed parent
improver. A single actual proposal episode forms G1 from the frozen parent
material and retained public history. These are changes to instructional
procedures; no model weights, scientific semantics or device parameters are
trained by the G-formation step.

G1's recorded proposal calls for source-parameterized H text, capability and
budget checks before spending an attempt, separation of achieved delivery from
post-terminal decay, and retrospective rehearsal of quantitative predictions
on their own source episode. It distinguishes arithmetic/transcription errors
from substantive design failures and retains no-update as an option. This
describes the proposed procedure; it does not establish that every consumer
follows it or that any rule is a novel or necessary mechanism~\cite{parents}.

Three lineages each generate two H proposals under G0 and two under the same
shared G1, for twelve actual H proposals. Each admitted descendant is consumed
on the fixed pulse-fast and volatile-reset selection tasks. H0 supplies the
corresponding control in each lineage. Thus selection contains 24 descendant
cells and six H0 cells. The registered ranking prefers more complete-service
passes, then fewer nominal judgment disagreements, then fewer charged requests,
then the lower descendant index. Proposal costs and both selection attempts
enter the request criterion; unselected sibling costs remain in the pipeline.
All 30 effective selection cells pass with no nominal judgment disagreement.
All six choices are frozen before final exposure~\cite{selection}.

Each selected descendant and H0 is then consumed by fresh design episodes on
three frozen final inputs: a stretched-port-window transient task, a half-power
C-lite query derivative, and a new O waveform. The C-lite branch is the
existing single-query digital abstraction, not a new RF or physical environment.
The final designer can inspect the complete current task and acquire its
sources, including the new O waveform. Formation and selection do not see these
final inputs, and final feedback cannot trigger reselection. O0 is excluded
from G/H formation and selection. Array projection is the same in all arms.

Later D episodes have at most 12 provider requests, 40 tool calls, 800 s and
two distinct designs. Each H proposal has an eight-request/400 s ceiling.
The one G1 formation has an eight-request/400 s ceiling; its actual three
requests are charged once and included in G1 pipeline cost. The nine final
cells per arm represent three fixed tasks consumed in three descendant-lineage
contexts, not nine independent task families~\cite{protocol,analysis}.

\section{Observed O0 behavior}
\subsection{Event success is shared with the rich-state control}
@@O0_TABLE@@

Candidate and rich-state submit identical designs: 15 mF, one-second sampling,
thresholds 0.05/0.01 g, NVM, one-second retry, zero backoff and the confirmed-event
program. They share the same execution key and response hash. The external
event evaluator passes all eight transitions, energy and receiver checks,
with no missing keepalive or idle false event. The shared response contains
18 accepted packets. Two fresh model submissions of one shared digital
response do not supply two independent realizations~\cite{episodes}.

The periodic control's energy and receiver checks also pass, with 348 accepted
packets. Its messages are periodic snapshots, which provide neither the
required start/stop records nor active-state keepalive coverage. It matches
zero of the eight transitions and fails event service. The contrast shows that
energy feasibility and accepted packet count do not by themselves satisfy this
event contract. Because the fixed rich-state control already passes, O0
establishes no additional event-service benefit for the candidate interface.
The candidate also uses eight provider requests, versus five for each control;
these single-episode counts supply no efficiency advantage or statistical
comparison~\cite{o0}.

\subsection{Retained checked alternative and timing sensitivity}
The actual candidate checks one-second sampling first, then 1.5-second
sampling, and finally submits the one-second design. Both checked responses
are retained in its exposure and cost history. In the 1.5-second check, the
first start record is observed at @@ALT_OBSERVED@@ s and stamped
@@ALT_STAMP@@ s, against the external confirmation time 4203 s. Its timestamp
error is @@ALT_ERROR@@ s, exceeding the frozen 1 s tolerance even though
energy and delivery observations alone can appear adequate. This observed
timing violation explains retention of the one-second design; it is a checked
alternative within the same episode, not another model repetition or a later
repair to the accepted design~\cite{episodes}.

\subsection{Participant UNKNOWN and the host event PASS remain distinct}
The candidate's submitted service judgment is UNKNOWN. Its original explanation
identifies unobserved dark intervals after brownout, the absence of an O gap
message to bracket those intervals, inherited A/R first-receive and dark-report
metadata, and unavailable source/hardware calibration. Specifically, the
inherited metadata request reception by 1800 s and dark reporting every 600 s;
the first confirmed O event occurs much later. The participant therefore
declines broader acceptance. Its complete original explanation is preserved
verbatim in the manuscript binding as participant testimony, including its
own numerical interpretations~\cite{first,episodes}.

The registered O evaluator instead asks whether the required start, active
keepalive and stop history was delivered under the nominal energy/receiver
model. It returns PASS, and the receipt retains a nominal predicate-disagreement
flag. The participant's physical and broader-reporting UNKNOWN is not a
physical self-judgment error. Both scopes are retained.
Neither this disagreement nor the event PASS resolves the inherited broader
reporting contract. Earlier A/R dark NO\_GO and FIFO FAIL remain historical
failures; O0 supplies no whole-product acceptance.

The one-second observations include dark-period brownouts near 8766.18 and
19587.64 s. The required active intervals do not overlap the subsequent
unobserved gaps. Successful O0 event coverage therefore does not establish
uninterrupted six-hour sensing or successful detection in every possible dark
window. The next waveform must be evaluated as a separate frozen task rather
than inferred from the O0 final state. Physical qualification remains UNKNOWN
for all three arms.

\section{Final results with every cell retained}
\subsection{Two digital tasks saturate; the new O task separates outcomes}
@@FINAL_ARM_TABLE@@

Both reserved digital inputs have three PASS per arm, for 18/18 final cells
across those two inputs. All final submitted designs pass their energy gate.
On the new O waveform, H0 has one PASS, one submitted FAIL and one INCOMPLETE;
G0 has zero, one and two; G1 has two, zero and one. The complete 27-cell totals
are H0 7/1/1, G0 6/1/2 and G1 8/0/1. Removing incomplete episodes would change
the question and inflate the apparent completion rate~\cite{details,analysis}.

The final per-lineage pass vectors, in lineage order, are H0 $(2,3,2)$,
G0 $(2,2,2)$ and G1 $(3,2,3)$. G1's 8/9 is a descriptive result from three
descendant-lineage contexts conditional on one shared formation. There is no
independent replication of G1 training, no large task sample, and no promotion
of the default H0 or improver. Strong selection performance on two tasks also
does not establish transfer to a different event-time alignment.

\subsection{Encoded event time is stricter than event matching}
@@O_FINAL_TABLE@@

All five O submissions match eight events, receive 18 accepted packets and
pass energy checks. Only three pass complete event service. These three use
0.75 s sampling; the two one-second submissions each pass six individual event
checks and fail two stops with \path{WRONG_EVENT_TIME}. The three successful
designs include H0 as well as G1. Retry periods also differ, so this is an
observed design association, not a controlled one-factor sampling ablation or
an exclusive G1 mechanism~\cite{details}.

@@STAMP_TABLE@@

Both failed stop receptions occur less than one second after the external
confirmation instant. Nevertheless, their encoded timestamps exceed the one-second
error bound by 0.004 and 0.103 s. Sampling phase and the modeled clock's timestamp
accumulation therefore have to be checked together. Correct matching, prompt
reception, an empty pending queue and energy feasibility cannot substitute for
the encoded-time predicate. The 0.75 s submissions have maximum encoded-time
error 0.728 s on this waveform. Their observed success is specific to the
frozen digital input and its timing, not a physical robustness guarantee.

The two submitted final O failures each self-report PASS; their nominal
event-service disagreements are retained. These differ from the original O0
candidate's broader UNKNOWN: in the final failures the host identifies a
specific encoded event-time violation within the submitted nominal contract.
Missing submissions supply no service self-judgment at all.

\subsection{Four token-censored episodes remain in the denominator}
The incomplete final episodes are L1-G0, L2-G0, L2-G1 and L3-H0 on O.
Each last SDK assistant response has stop reason \path{length}, with 32,768
output tokens and 32,768 reported reasoning tokens, and no final submission.
This is a response-level metadata observation; it is not a six-hour device
failure, an energy FAIL, or evidence that the whole episode used only that
many tokens. The four episodes are not retried. Their requests and costs
remain charged, and the outcome remains INCOMPLETE rather than a conditional
success or an omitted row~\cite{details,analysis}.

\section{Host cache incident and explicit protocol continuation}
The later selection stage encounters a host representation error: historical
\path{observations.json} is loaded without its separately sealed
\path{trace.csv}, while assessment requires the trajectory. Three selection
attempts raise \path{KeyError: 'trace'}; a fourth attempt is truncated by the
hold. These attempts are apparatus failures or censoring, not negative G0/G1
method outcomes. The frozen hold preserves all four records and their costs:
@@INCIDENT_REQUESTS@@ provider requests and USD~@@INCIDENT_COST@@ in settled
upper-bound estimates~\cite{hold}.

The explicit amendment limits repair to reconstructing the already sealed
historical trace and linking four named one-off recovery attempts. Qualification
passes exact-input historical assessment, preservation of compressed raw and
all five previously valid selection results, and rejection of missing trace,
wrong trace hash, wrong input and wrong world. These checks use existing
responses with zero new provider requests or simulations; they establish a
cache decoding boundary, not method success~\cite{qualification}.

Version 1.1 retains the original methods, tasks, scoring and request/time/dollar
budgets, while
preserving every original attempt. Formal selection accounting uses the original
proposal and two effective selection attempts; incident overhead remains
separately itemized and included in full arm/global pipeline cost. The protocol
retains 73 logical slots with a ceiling of 77 actual episodes after four named
recoveries. Request, summed episode-time and settled upper-bound cost ceilings
remain 860, 54,400 s and USD~100. These are ceilings, not observed final totals.
The amendment preserves the five valid selection responses and twelve H
proposals rather than silently replacing them~\cite{amendment,protocol}.
The four named authorized recovery attempts all close with PASS. They resolve
the four canonical slots without rebuilding G/H or erasing the incident
history~\cite{recovery}. Effective selection consequently has 30 cells, while
its full accounting contains 34 actual attempts.

\section{Complete accounting and interpretation}
@@COST_TABLE@@

The full pipeline records 367 requests, all SETTLED, with no new UNKNOWN usage,
USD~3.1767228 in fixed-rate settled upper-bound estimates and 5951.639484 s of
summed episode wall time. This includes the one G1 formation, all twelve H
proposals, eliminated siblings, selection, final episodes, four original host
incidents, four recoveries and token-censored responses. The incident subset
is 21 requests, USD~0.1318473 and 216.654733 s; it is already in the totals
and must not be added again~\cite{analysis}.

Full G0 pipeline cost is 135 requests and USD~1.2585825; full G1 cost is
138 requests and USD~1.2447618, including its formation. H0 selection plus
final consumption costs 76 requests and USD~0.5154765, and O0 costs 18 requests
and USD~0.1579020. These four buckets sum to the global total. G0 and G1 pipeline
costs include both proposed descendants rather than only the selected child.
Provider aliases and registered fixed rates bound an estimate, not a provider
invoice or the full end-to-end research cost. Codex assistance and historical
acquisition remain unpriced.

O0's scope is one development input and an explicitly assumed digital apparatus.
The results do not qualify a photovoltaic device, PMIC transient model,
vibration sensor, physical clock, NVM implementation or RF receiver. They also
do not erase prior A/R reporting failures. A/R NO\_GO, dark FAIL, strict FIFO
FAIL and product NOT\_ACCEPTED remain preserved. The independent O event gate
does not cover every inherited A/R metadata, reporting or dark-observation
requirement. Physical qualification remains UNKNOWN throughout.

The study establishes a finite separation: original O0 can be served by the
same design as a strong fixed control; a different waveform exposes encoded-time
violations despite successful energy and event matching; and procedural
completion can fail through response truncation. It supplies neither evidence
of an interface advantage beyond rich-state nor a stable recursive-improvement
mechanism. The unchanged H0's own successful 0.75 s submission and the single
shared G1 formation constrain that interpretation.

\section{Reproducible manuscript and evidence limits}
\path{render_phase4.py} verifies the authoritative closed handoff and its
finite source list, cross-checks actual and final rows, frozen choices,
accounting and per-event timestamp arithmetic, then generates this fragment.
It also preserves the original O0 participant explanation verbatim in
\path{phase4-binding.json}. It runs no model, scientific simulator or service
evaluator. The source-preservation receipt records all six choices frozen
before final exposure, unchanged historical prefixes and preserved old UNKNOWN
billing records~\cite{preservation}.

The paper-final receipts bind both TeX sources, renderer, shared layout/logo,
compiled PDF, fonts, extracted text and actual page-by-page visual review.
Build and rendering validate presentation and source binding; they do not
replicate the scientific batch, establish hardware acceptance or replace the
coordinator's registered repository verification. No scientific code, task,
result, old manuscript, shared style or logo is changed for this paper.
"""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def bound(path, role):
    data = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "role": role}


def load(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def table_tex(caption, label, columns, header, rows):
    return ("\\begin{table}[htbp]\n\\centering\\small\n\\caption{" + caption + "}\n"
            "\\label{" + label + "}\n\\begin{tabular}{@{}" + columns + "@{}}\\toprule\n"
            + header + " \\\\\\midrule\n" + "\n".join(" & ".join(row) + " \\\\" for row in rows)
            + "\n\\bottomrule\\end{tabular}\n\\end{table}")


def closed_results(source):
    handoff_path = source / "paper-handoff.json"
    assert bound(handoff_path, "handoff")["sha256"] == "690e0aaf76d92c6f8756c9976872bb94406397e30f2e622d9f70a85924477a56"
    handoff = load(handoff_path)
    inputs = [bound(handoff_path, "Authoritative closed paper handoff")]
    objects = {}
    for item in handoff["sources"]:
        path = Path(item["path"])
        record = bound(path, "Authoritative closed result/freeze; read only")
        assert record["sha256"] == item["sha256"] and record["bytes"] == item["bytes"], path
        inputs.append(record)
        objects[path.name] = load(path)
    actual, details, analysis = (objects[n] for n in ("actual-results.json", "final-details.json", "analysis-summary.json"))
    assert len(actual["rows"]) == actual["actual_episodes"] == 77
    assert len(actual["canonical_rows"]) == actual["effective_canonical_cells"] == 73
    assert actual["new_unknown_usage"] == [] and actual["native_dispatches"] == 0
    assert actual["new_scientific_executions"] == 25 and actual["G1_formation_events"] == 1
    assert all(r["usage"]["status"] == "SETTLED" for r in actual["rows"])
    assert sum(r["usage"]["requests"] for r in actual["rows"]) == analysis["all_accounting"]["requests"] == 367
    dollars = sum((Decimal(str(r["usage"]["usd"])) for r in actual["rows"]), Decimal(0))
    assert abs(dollars - Decimal(str(analysis["all_accounting"]["settled_upper_usd"]))) < Decimal("1e-12")
    assert abs(sum(r["usage"]["wall_s"] for r in actual["rows"]) - analysis["all_accounting"]["wall_s"]) < 1e-6
    assert analysis["actual_results_sha256"] == bound(source / "actual-results.json", "cross-check")["sha256"]
    assert analysis["final_details_sha256"] == bound(source / "final-details.json", "cross-check")["sha256"]
    selected = objects["selected-methods.json"]
    freeze = objects["final-selection-freeze.json"]
    selection = objects["selection-complete.json"]
    assert identity(selected) == freeze["selected_methods_sha256"] == selection["selected_methods_sha256"]
    assert freeze["all_final_episodes_not_started"] is True and freeze["final_results_consulted"] is False
    assert selection["final_results_consulted"] is False and len(selection["rows"]) == 30
    effective_selection = [r for r in actual["canonical_rows"] if r["stage"] == "selection"]
    assert len(effective_selection) == 30 and all(r["service"] == "PASS" for r in effective_selection)
    assert sum(r["stage"] == "selection" for r in actual["rows"]) == 34
    assert len(objects["parent-freeze.json"]["rows"]) == 12
    assert objects["G1-freeze.json"]["actual_formation_event_count"] == 1
    for name in selection["selection_files"]:
        path = Path(name)
        obj = load(path)
        inputs.append(bound(path, "Frozen selected H and original two-sibling metrics"))
        arm = path.stem
        eligible = [r for r in obj["candidate_metrics"] if r["eligible"]]
        best = min(eligible, key=lambda r: (-r["complete_service_passes"], r["wrong_service_judgments"], r["total_charged_requests"], r["descendant_index"]))
        assert best["descendant_index"] == obj["selected_descendant_index"] == selected[arm]["selected_descendant_index"]
        assert obj["selected_H_sha256"] == selected[arm]["selected_H_sha256"] and not obj["final_results_consulted"]
    preservation = objects["preservation-final.json"]
    assert preservation["status"] == "PASS" and preservation["all_six_selections_frozen_before_final"]
    assert preservation["prior_S0_prefix_unchanged"] and preservation["old_unknown_records_preserved"] == 24
    assert actual["default_H0_changed"] is False and analysis["default_H0_changed"] is False
    finals = details["rows"]
    assert len(finals) == 27
    actual_final = {r["episode"]: r for r in actual["canonical_rows"] if r["stage"] == "final"}
    def counts(rows):
        return (sum(r["service"] == "PASS" for r in rows), sum(r["service"] == "FAIL" for r in rows), sum(r["service"] not in ("PASS", "FAIL") for r in rows))
    for r in finals:
        assert r["result_sha256"] == actual_final[r["episode"]]["result_sha256"]
    arm_rows = []
    for arm in ("H0", "G0", "G1"):
        rows = [r for r in finals if r["arm"] == arm]
        assert len(rows) == 9
        c = counts(rows)
        assert c == tuple(analysis["final_arms"][arm][k] for k in ("PASS", "submitted_FAIL", "incomplete"))
        digital = [r for r in rows if r["task"] != "p4-o-unexposed-waveform-v1"]
        orows = [r for r in rows if r["task"] == "p4-o-unexposed-waveform-v1"]
        assert counts(digital) == (6, 0, 0)
        arm_rows.append([arm, "/".join(map(str, counts(digital))), "/".join(map(str, counts(orows))), "/".join(map(str, c))])
    incomplete = [r for r in finals if r["service"] not in ("PASS", "FAIL")]
    assert len(incomplete) == 4
    for r in incomplete:
        metadata = r["last_assistant_metadata"]
        assert metadata["stop_reason"] == "length" and metadata["usage"]["output"] == metadata["usage"]["reasoning"] == 32768
        assert r["design"] is None and r["participant_judgment"] is None
    orows = [r for r in finals if r["task"] == "p4-o-unexposed-waveform-v1"]
    assert len(orows) == 9
    o_table_rows, o_facts = [], []
    for r in orows:
        group = f"L{r['lineage']}-{r['arm']}"
        if r["service"] in ("PASS", "FAIL"):
            ev = r["O_events"]
            assert r["energy"] == "PASS" and ev["matched"] == ev["expected"] == 8 and ev["accepted_packets"] == 18
            period = r["design"]["sample_period_s"]
            assert period == (.75 if r["service"] == "PASS" else 1)
            for e in ev["per_event"]:
                assert abs(abs(e["encoded_stamp_s"] - e["time_s"]) - e["absolute_stamp_error_s"]) < 1e-8
            maximum = max(e["absolute_stamp_error_s"] for e in ev["per_event"])
            o_table_rows.append([group, f"{period:g}", f"{r['design']['retry_s']:g}", str(ev["pass_count"]) + "/8", f"{maximum:.3f}", r["service"]])
            o_facts.append({k: r[k] for k in ("episode", "design", "energy", "execution_key", "service", "O_events", "participant_judgment", "wrong_service_judgment")})
        else:
            o_table_rows.append([group, "--", "--", "--", "--", "INCOMPLETE"])
    assert len(o_facts) == 5 and sum(r["service"] == "PASS" for r in o_facts) == 3
    failed = [r for r in o_facts if r["service"] == "FAIL"]
    assert all("WRONG_EVENT_TIME" in e["reasons"] for r in failed for e in r["O_events"]["per_event"] if e["verdict"] == "FAIL")
    bad = [e for e in failed[0]["O_events"]["per_event"] if e["verdict"] == "FAIL"]
    assert len(bad) == 2
    stage_rows = []
    labels = {"O-transfer": "O0 development", "formation": "G1 formation", "proposal": "All H proposals", "selection": "Selection, all attempts", "final": "All final cells"}
    for stage in labels:
        r = analysis["stages_all_actual"][stage]
        chosen = [x for x in actual["rows"] if x["stage"] == stage]
        assert len(chosen) == r["episodes"] and sum(x["usage"]["requests"] for x in chosen) == r["requests"]
        stage_rows.append([labels[stage], str(r["episodes"]), str(r["requests"]), f"{Decimal(r['settled_upper_usd']):.7f}", f"{r['summed_wall_s']:.1f}"])
    stage_rows.append(["Total", "77", "367", "3.1767228", "5951.6"])
    tables = {
        "@@FINAL_ARM_TABLE@@": table_tex("Final P/F/I counts: PASS, submitted FAIL and INCOMPLETE. The denominator is six digital cells plus three O cells per arm; all 27 remain included.", "tab:final", "lccc", "Arm & Two digital tasks & New O waveform & Total", arm_rows),
        "@@O_FINAL_TABLE@@": table_tex("All nine new-O final cells. Every submitted row has energy PASS, eight matched events and 18 accepted packets. Events P/8 counts individually passing events, not matches. Dash denotes no submission.", "tab:o-final", "lrrrrl", "Lineage-arm & Poll (s) & Retry (s) & Events P/8 & Max error (s) & Service", o_table_rows),
        "@@STAMP_TABLE@@": table_tex("The two failed stops in each one-second submission. These same times occur in both failed designs, whose retry values and execution keys differ. The error is computed from encoded timestamp, not reception time.", "tab:stamp", "rrrr", "Confirmation (s) & Reception (s) & Encoded time (s) & Error (s)", [[f"{e['time_s']:.3f}", f"{e['receive_s']:.3f}", f"{e['encoded_stamp_s']:.3f}", f"{e['absolute_stamp_error_s']:.3f}"] for e in bad]),
        "@@COST_TABLE@@": table_tex("Full pipeline accounting from the authoritative analysis. Selection includes the four original host incidents and four recoveries. USD denotes fixed-rate provider upper-bound estimates; wall is summed episode time.", "tab:cost", "lrrrr", "Stage & Attempts & Requests & USD & Wall (s)", stage_rows),
    }
    return objects, inputs, tables, o_facts


def prepare(source, episodes):
    complete, complete_sources, complete_tables, final_o = closed_results(source)
    preflight = load(DOC / "PREFLIGHT.json")
    for record in preflight["protected_read_only_files"]:
        assert bound(Path(record["path"]), "guard")["sha256"] == record["sha256"], record["path"]
    sources = [bound(source / name, "Authoritative pre-final preparation evidence") for name in FILES]
    data = {name: load(source / name) for name in FILES}
    table, first, hold, amendment, qualification, protocol = (data[name] for name in FILES)
    assert table["status"] == "THREE_REGISTERED_ACTUAL_O0_EPISODES_CLOSED"
    assert table["G_H_history_exposure"] is False and table["whole_product_acceptance"] == "NOT_ESTABLISHED"
    original_rows = {r["episode"]: r for r in table["rows"]}
    expected_names = ("O0-candidate", "O0-fixed-periodic", "O0-rich-state")
    assert set(original_rows) == set(expected_names)
    results = {}
    for name in expected_names:
        path = episodes / name / "episode-result.json"
        record = bound(path, "Original actual O0 episode; no replay")
        assert record["sha256"] == original_rows[name]["result_sha256"]
        sources.append(record)
        obj = results[name] = load(path)
        assert obj["accounting"]["unknown_or_missing_usage"] == []
        assert obj["accounting"]["requests"] == original_rows[name]["requests"]
        assert obj["native_dispatches"] == 0
        assert obj["reported_models"] == ["deepseek-flash"]
        assert obj["external_result"]["execution"]["complete_service"] == original_rows[name]["complete_O_event_service"]
    requests = sum(r["accounting"]["requests"] for r in results.values())
    cost = sum((Decimal(str(r["accounting"]["settled_charge_upper_bound_usd"])) for r in results.values()), Decimal(0))
    assert requests == table["total_requests"] == 18
    assert abs(cost - Decimal(str(table["total_settled_upper_usd"]))) < Decimal("1e-12")
    candidate = results["O0-candidate"]["external_result"]
    rich = results["O0-rich-state"]["external_result"]
    periodic = results["O0-fixed-periodic"]["external_result"]
    assert candidate["candidate"] == rich["candidate"] and candidate["candidate"]["sample_period_s"] == 1
    for key in ("execution_key", "response_sha256", "case_sha256", "evaluator_sha256", "per_event"):
        assert candidate["execution"][key] == rich["execution"][key]
    assert candidate["execution"]["matched_event_count"] == rich["execution"]["matched_event_count"] == 8
    assert periodic["execution"]["matched_event_count"] == 0
    assert first["matched_events"] == first["expected_events"] == 8
    assert candidate["service_judgment"] == "UNKNOWN" and candidate["wrong_service_judgment"] is True
    assert first["episode_sha256"] == original_rows["O0-candidate"]["result_sha256"]
    case_path = Path(protocol["O_tasks"]["o0-original-service-development-v1"]["input_path"])
    case_record = bound(case_path, "Actual O0 input only; no heldout payload read")
    assert case_record["sha256"] == protocol["O_tasks"]["o0-original-service-development-v1"]["input_sha256"]
    sources.append(case_record)
    case = load(case_path)
    assert identity(case) == candidate["execution"]["case_sha256"]
    d = case["ar_task"]["device"]
    assert (case["duration_s"], d["cap_initial_voltage_v"], d["capacitance_f"], case["photovoltaic_area_cm2"]) == (21600, 0, .015, 15)
    assert [(r["start_s"], r["end_s"]) for r in case["rms_segments"] if r["rms_g"] > .05] == [(4200, 4500), (7800, 8100), (11400, 12000), (16800, 16920)]
    evaluator = case_path.parents[4] / "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase4_interfaces.py"
    evaluator_record = bound(evaluator, "Actual O0 evaluator source; hashed only, never imported")
    assert evaluator_record["sha256"] == candidate["execution"]["evaluator_sha256"]
    sources.append(evaluator_record)
    method_source = evaluator.with_name("phase4_methods.py")
    method_record = bound(method_source, "Frozen method semantics and selection ranking; hashed only")
    assert method_record["sha256"] == protocol["bound_files"][str(method_source)]
    sources.append(method_record)
    gateway = episodes / "O0-candidate/gateway/gateway-events.jsonl"
    sources.append(bound(gateway, "Existing O0 candidate checked alternatives; no provider archive read"))
    starts, checks = {}, []
    for line in gateway.read_text().splitlines():
        event = json.loads(line)
        payload = event.get("data", {})
        if event.get("kind") == "tool_started":
            starts[payload["number"]] = payload["input"]
        if event.get("kind") == "tool_completed" and starts.get(payload.get("number"), {}).get("action") == "check":
            observed = payload["output"]["observed"]
            records = observed["records"]
            if isinstance(records, dict):
                records = records["first_six"]
            checks.append({"tool_number": payload["number"], "candidate": starts[payload["number"]]["candidate"],
                           "response_sha256": observed["response_sha256"], "first_record": records[0]})
    assert [c["candidate"]["sample_period_s"] for c in checks] == [1, 1.5]
    assert checks[0]["candidate"] == candidate["candidate"]
    alt = checks[1]["first_record"]
    alt_error = alt["stamp_s"] - candidate["execution"]["per_event"][0]["time_s"]
    assert alt_error > case["service"]["event_time_error_s"]
    incidents = hold["failed_or_censored_episodes"]
    assert len(incidents) == 4 and sum(bool(r["errors"]) for r in incidents) == 3
    assert all(any("KeyError: 'trace'" in e["error"] for e in r["errors"]) for r in incidents if r["errors"])
    incident_requests = sum(r["requests"] for r in incidents)
    incident_cost = sum((Decimal(str(r["settled_upper_usd"])) for r in incidents), Decimal(0))
    assert set(amendment["restore_originals"]) == {r["episode"] for r in incidents}
    assert qualification["status"] == "PASS" and all(c["status"] == "PASS" for c in qualification["checks"])
    assert qualification["new_provider_requests"] == qualification["new_simulations"] == 0
    assert protocol["schema_version"] == "bf-phase4-finite-protocol-v1.1"
    assert protocol["canonical_cell_count"] == 73 and protocol["budgets"]["max_actual_episodes"] == 77
    assert protocol["budgets"]["max_provider_requests"] == 860 and protocol["budgets"]["max_summed_episode_wall_s"] == 54400
    assert bound(source / "amendment-registration.json", "cross-binding")["sha256"] == protocol["amendment_registration"]["sha256"]
    assert bound(source / "cache-repair-qualification.json", "cross-binding")["sha256"] == protocol["qualification"]["sha256"]
    labels = {"O0-candidate": "Candidate", "O0-fixed-periodic": "Fixed periodic", "O0-rich-state": "Rich-state"}
    rows = []
    for name in expected_names:
        r = results[name]; ext = r["external_result"]; ev = ext["execution"]
        rows.append(f"{labels[name]} & {ext['candidate']['sample_period_s']:g} & {ev['matched_event_count']}/8 & {ev['complete_service']} & {ext['service_judgment']} & {r['accounting']['requests']} \\\\")
    o0_table = r"""\begin{table}[htbp]
\centering\small
\caption{Three actual O0 development episodes. Matched counts concern eight
transitions on one task. Candidate and rich-state share one digital response.}
\label{tab:o0}
\begin{tabular}{@{}lrlccr@{}}\toprule
Arm & Poll (s) & Matched & Host O & Self-judgment & Requests \\\midrule
""" + "\n".join(rows) + r"""
\bottomrule\end{tabular}
\end{table}"""
    event_rows = [f"{r['kind'].capitalize()} & {r['time_s']:.0f} & {r['receive_s']:.3f} & PASS \\\\" for r in candidate["execution"]["per_event"]]
    event_table = r"""\begin{table}[htbp]
\centering\small
\caption{Eight host-checked transitions in the shared candidate/rich-state
response. Reception time is distinct from the encoded event timestamp.}
\label{tab:events}
\begin{tabular}{@{}lrrc@{}}\toprule
Event & Confirmation (s) & Reception (s) & O event \\\midrule
""" + "\n".join(event_rows) + r"""
\bottomrule\end{tabular}
\end{table}"""
    replacements = {"@@O0_TABLE@@": o0_table, "@@EVENT_TABLE@@": event_table,
                    "@@ALT_OBSERVED@@": f"{alt['observed_s']:.6f}", "@@ALT_STAMP@@": f"{alt['stamp_s']:.6f}",
                    "@@ALT_ERROR@@": f"{alt_error:.6f}", "@@INCIDENT_REQUESTS@@": str(incident_requests),
                    "@@INCIDENT_COST@@": f"{incident_cost:.7f}"}
    replacements.update(complete_tables)
    methods = METHODS
    for key, value in replacements.items():
        methods = methods.replace(key, value)
    assert "@@" not in methods
    (HERE / "phase4-methods.tex").write_text(methods)
    manuscript = (HERE / "phase4-manuscript.tex").read_text()
    all_text = manuscript + methods
    cited = {key for group in re.findall(r"\\cite\{([^}]+)\}", all_text) for key in group.split(",")}
    bibliography = set(re.findall(r"\\bibitem\{([^}]+)\}", manuscript))
    assert cited <= bibliography, cited - bibliography
    assert all_text.count(r"\begin{table}") == all_text.count(r"\end{table}") == 5
    assert all_text.count(r"\input{phase4-methods.tex}") == 1
    for record in preflight["protected_read_only_files"]:
        assert bound(Path(record["path"]), "guard")["sha256"] == record["sha256"], record["path"]
    evidence = {"O0_task_count": 1, "O0_actual_episodes": 3, "O0_requests": requests,
                "model_identity_scope": protocol["identity_scope"],
                "O0_settled_upper_usd": str(cost), "shared_candidate_rich_response": candidate["execution"]["response_sha256"],
                "shared_candidate_rich_execution_key": candidate["execution"]["execution_key"],
                "rows": table["rows"], "checked_alternatives": checks,
                "alternative_first_timestamp_error_s": alt_error,
                "participant_reason_verbatim": candidate["reason"],
                "participant_reason_scope": "Original model testimony; numerical claims are not silently promoted to author-verified physics.",
                "host_incident": {"failed": 3, "censored": 1, "requests": incident_requests,
                                  "settled_upper_usd": str(incident_cost), "attempts": incidents},
                "closed_analysis": complete["analysis-summary.json"],
                "final_O_submissions": final_o,
                "O0_disagreement_scope": "Nominal O-event predicate only; broader reporting/physical UNKNOWN is not a physical self-judgment error.",
                "selected_methods_file_sha256": next(r["sha256"] for r in complete_sources if Path(r["path"]).name == "selected-methods.json"),
                "selected_methods_canonical_sha256": identity(complete["selected-methods.json"])}
    write(DOC / "evidence-map.json", evidence)
    static = {"status": "PASS", "scope": "Source/hash/count/accounting/identity and TeX reference structure only",
              "protected_files_unchanged": len(preflight["protected_read_only_files"]),
              "citations_resolved": sorted(cited), "tables": 5, "compiled": False, "visual_review": "NOT_RUN",
              "new_provider_requests": 0, "new_scientific_executions": 0, "native_dispatches": 0}
    write(DOC / "static-checks.json", static)
    combined = {r["path"]: r for r in [*sources, *complete_sources]}
    binding = {"schema_version": "bf-phase4-paper-binding-v1", "status": "CLOSED_RESULTS_SOURCE_READY_PENDING_PDF_QA",
               "feature": "BFA-062-phase4-service-transfer", "inputs": list(combined.values()),
               "paper_files": [bound(HERE / name, "Owned Phase 4 preparation source") for name in ("phase4-methods.tex", "phase4-manuscript.tex", "render_phase4.py")],
               "shared_layout_and_logo": [bound(PROJECT / "papers/shared/hkustgz-paper.sty", "Frozen shared layout"), bound(PROJECT / "papers/shared/assets/hkustgz-english.pdf", "Frozen logo")],
               "evidence": evidence, "static_checks": static,
               "pdf": {"path": str(HERE / "phase4.pdf"), "exists": (HERE / "phase4.pdf").exists(), "compile_status": "PENDING_CURRENT_SOURCE_BUILD", "page_count": None, "full_page_visual_check": "NOT_RUN"},
               "heldout_payloads_read": False, "final_results_read": True,
               "whole_product_acceptance": "NOT_ESTABLISHED", "physical_qualification": "UNKNOWN",
               "registered_final_init": "PENDING_SINGLE_S0_RUN_AFTER_IMPORT",
               "next_owner": "B performs document-only build and all-page QA; S0 owns import and registered repository verification."}
    write(HERE / "phase4-binding.json", binding)
    print(json.dumps({"status": binding["status"], "O0_episodes": 3, "O0_requests": requests,
                      "O0_settled_upper_usd": str(cost), "host_incident_requests": incident_requests,
                      "protected_files_unchanged": static["protected_files_unchanged"], "PDF_compiled": False,
                      "new_scientific_executions": 0, "new_provider_requests": 0}))


def main():
    signal.alarm(240)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE)
    parser.add_argument("--episode-root", type=Path, default=EPISODES)
    parser.add_argument("--build", action="store_true", help="Generate sources, compile twice and render all pages; no science")
    parser.add_argument("--finalize", action="store_true", help="Bind existing build and actual visual review, then remove this build")
    args = parser.parse_args()
    if args.finalize:
        finalize()
    else:
        prepare(args.source_root, args.episode_root)
        if args.build:
            build_pdf()


def doc_tool(argv, timeout=90):
    result = subprocess.run(["rtk", "proxy", *map(str, argv)], cwd=HERE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=timeout, check=False)
    if result.returncode:
        (DOC / "build-error.txt").write_text(result.stdout)
        raise RuntimeError(f"DOCUMENT_TOOL_FAILED:{argv[0]}:{result.returncode}")
    return result.stdout


def build_pdf():
    build = DOC / "build"
    build.mkdir(exist_ok=True)
    logs = []
    start = time.monotonic()
    for number in (1, 2):
        text = doc_tool(["/Library/TeX/texbin/pdflatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
                         "-file-line-error", "-output-directory=" + str(build), "phase4-manuscript.tex"])
        (build / f"pass-{number}.stdout.txt").write_text(text)
        logs.append({"pass": number, "exit_code": 0, "stdout_sha256": hashlib.sha256(text.encode()).hexdigest(), "tail": text[-600:]})
    log = (build / "phase4-manuscript.log").read_text()
    warnings = [line for line in log.splitlines() if any(term in line for term in ("Warning:", "Overfull", "Underfull", "undefined references", "Missing character"))]
    notices = [line for line in warnings if line == "Package epstopdf Warning: Shell escape feature is not enabled."]
    unexpected = [line for line in warnings if line not in notices]
    assert not unexpected, unexpected
    shutil.copyfile(build / "phase4-manuscript.pdf", HERE / "phase4.pdf")
    pdf = HERE / "phase4.pdf"
    info = doc_tool(["pdfinfo", pdf])
    fonts = doc_tool(["pdffonts", pdf])
    assert "Type 3" not in fonts
    font_lines = [line for line in fonts.splitlines()[2:] if line.strip()]
    assert font_lines
    for line in font_lines:
        flags = re.search(r"\s+(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", line)
        assert flags and flags.group(1) == "yes", line
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
    doc_tool(["pdftotext", "-layout", pdf, DOC / "phase4-extracted.txt"])
    text = (DOC / "phase4-extracted.txt").read_text()
    page_text = [part for part in text.split("\f") if part.strip()]
    assert len(page_text) == pages and "??" not in text
    assert all(len(part.strip()) > 80 for part in page_text)
    needles = ("367", "3.1767228", "32,768", "INCOMPLETE", "0.728", "UNKNOWN", "1.004", "1.103", "25")
    assert all(needle in text for needle in needles), [needle for needle in needles if needle not in text]
    replaced_images = [bound(path, "Prior temporary page image replaced during this document rebuild")
                       for path in sorted(build.glob("page-*.png"))]
    for old in replaced_images:
        Path(old["path"]).unlink()
    doc_tool(["pdftoppm", "-r", "100", "-png", pdf, build / "page"])
    images = sorted(build.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    assert len(images) == pages
    receipt = {"status": "COMPILED_PENDING_VISUAL_REVIEW", "passes": logs, "page_count": pages,
               "build_elapsed_s": time.monotonic() - start, "pdf": bound(pdf, "Two-pass compiled current manuscript"),
               "last_pass_warnings": unexpected, "document_tool_notices": notices,
               "notice_scope": "Shell escape deliberately disabled; only PDF vector artwork is included, with no EPS conversion required.",
               "all_fonts_embedded": True, "font_count": len(font_lines),
               "pdffonts": fonts, "pdfinfo": info, "required_text_checks": list(needles),
               "all_page_text_lengths": [len(part.strip()) for part in page_text],
               "replaced_previous_page_images": replaced_images,
               "page_images": [bound(path, "Full-page 100 dpi visual review image; temporary") for path in images],
               "new_provider_requests": 0, "new_scientific_executions": 0}
    write(DOC / "build-receipt.json", receipt)
    print(json.dumps({"document_build": "PASS", "pages": pages, "embedded_fonts": len(font_lines), "layout_reference_font_warnings": unexpected, "document_tool_notices": notices,
                      "PDF_sha256": receipt["pdf"]["sha256"], "page_images": [str(path) for path in images]}))


def finalize():
    binding = load(HERE / "phase4-binding.json")
    build = load(DOC / "build-receipt.json")
    visual = load(DOC / "visual-review.json")
    current = bound(HERE / "phase4.pdf", "Final compiled and visually checked manuscript")
    assert current["sha256"] == build["pdf"]["sha256"] == visual["pdf_sha256"]
    assert visual["status"] == "PASS" and visual["reviewed_pages"] == list(range(1, build["page_count"] + 1))
    assert all(r["status"] == "PASS" for r in visual["pages"])
    assert not build["last_pass_warnings"] and build["all_fonts_embedded"]
    for item in binding["inputs"] + binding["paper_files"] + binding["shared_layout_and_logo"] + load(DOC / "PREFLIGHT.json")["protected_read_only_files"]:
        assert bound(Path(item["path"]), "readback")["sha256"] == item["sha256"], item["path"]
    binding.update(status="FINAL_LOCAL_PDF_AND_ALL_PAGE_QA_PASS", pdf={**current, "page_count": build["page_count"],
                   "compile_status": "SUCCESS_TWO_PASSES", "full_page_visual_check": "PASS", "all_fonts_embedded": True},
                   document_build=build, visual_review=visual,
                   next_owner="B idle; S0 imports this finite paper delivery and performs its single registered init.")
    binding["static_checks"].update(compiled=True, visual_review="PASS", final_source_readback="PASS")
    write(HERE / "phase4-binding.json", binding)
    write(DOC / "static-checks.json", binding["static_checks"])
    folder = DOC / "build"
    temporary = [bound(p, "Derived temporary document build/render file") for p in sorted(folder.iterdir()) if p.is_file()]
    shutil.rmtree(folder)
    write(DOC / "cleanup.json", {"status": "PASS", "removed_files": temporary, "removed_logical_bytes": sum(p["bytes"] for p in temporary),
                                 "build_directory_exists": folder.exists(), "final_PDF_retained": current,
                                 "scope": "Only this paper's build and full-size page PNGs; no scientific or historical files"})
    print(json.dumps({"status": binding["status"], "pages": build["page_count"], "PDF_sha256": current["sha256"],
                      "all_page_visual_review": "PASS", "build_removed": not folder.exists(), "S0_registered_init": "PENDING"}))


if __name__ == "__main__":
    main()
