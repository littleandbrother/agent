#!/usr/bin/env python3
"""Render phase-one manuscript facts from the sealed preparation and saved data."""
from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from bfworld.agentlab.campaign20261019 import bf_interfaces as bf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    signal.alarm(30)
    paper = Path(__file__).resolve().parent
    root = paper.parents[1]
    bf.load_protocol(root)
    audit = bf.verify(args.bundle)
    result = bf.read_json(args.bundle / "result.json")
    mechanisms = bf.read_json(args.bundle / "mechanisms.json")
    base = mechanisms["b_reference"]
    rows = {x["id"]: x for x in base["saved_outcomes"]}
    names = [("b-pulse-fast", "Fast pulse"), ("b-pulse-slow", "Slow pulse"),
             ("b-esr-fail", "High ESR"), ("b-no-energy", "No energy"),
             ("b-late-energy", "Late pulse"), ("b-latched-reset", "Latched reset"),
             ("b-volatile-reset", "Volatile reset")]
    table = []
    for key, name in names:
        row = rows[key]
        rx = "---" if row["first_receive_s"] is None else f"{row['first_receive_s'] * 1000:.1f}"
        table.append(f"{name} & {row['source_j'] * 1e6:.0f} & {rx} & "
                     f"{row['verdicts']['event_receive']} & {row['verdicts']['transient_voltage']} \\")
    # append a second literal slash for a TeX table line break
    table = [line + "\\" for line in table]
    mechanism_tex = r"""\section{Battery-free mechanism mapping}
The two structural pairs isolate BF relations that a passing current trace need
not excite: a capacitor's upper energy ceiling and pending-event state across
power loss. Their consumers are a timed service-energy transaction and a
transmit guard. They are deliberately ideal witnesses, not complete nodes.

A separate saved BF reference supplies startup, transient and event examples
(Table~\ref{tab:bf-reference}). The prescribed source first charges a capacitor;
ready/off thresholds and boot cost govern startup. A transmit attempt loads the
rail according to $V_{\rm load}=\sqrt{2E/C}-I_{\rm TX}R_{\rm ESR}$; a failed rail
or energy threshold resets the program. Reset can clear a volatile pending
event. This is load--storage--program feedback. The source is prescribed and
does not respond to load, so these examples do not establish source feedback.

\begin{table}[ht]
\centering\small
\begin{tabular}{lrrrr}
\toprule
Condition & Input ($\mu$J) & First RX (ms) & Event by deadline & Rail gate \\
\midrule
""" + "\n".join(table) + r"""
\bottomrule
\end{tabular}
\caption{Readback of seven saved ideal BF controls; no new simulation. The
deadline is 100 ms. A passing rail gate without a receive event does not mean
service success. Physical qualification is UNKNOWN for every row.}
\label{tab:bf-reference}
\end{table}

Fast and slow pulses both supply 150 $\mu$J and pass, with different startup and
receive times. The same total energy arriving late misses the service deadline.
At 150 $\Omega$ ESR, transient droop prevents reception despite the same input
energy. With 210 $\mu$J input, a common 40 $\mu$J shunt and postponed TX, the
latched and volatile cases differ in event survival. The passive mechanical
latch explicitly captures at zero electrical energy and retains across reset;
this assumes neither free powered NVM writes nor a calibrated commercial latch.
All sources and devices remain uncalibrated. Agreement with a predeclared
negative control is distinct from a passing event-service verdict.
"""
    protocol_tex = r"""\section{Frozen E4 input and resource protocol}
Phase one exports \textbf{64 participant inputs}: four existing cases,
four information levels, two formats and two observation regimes. All
\textbf{32 format pairs} have identical decoded facts, summary, assets, tool
definitions and resource limits. The main factorial uses the current interface
and a BF-rich static model. Complete raw data and executable response are
additional strong baselines. This is an input-integrity result. E4 live
Agent-format trials are NOT\_RUN.

The static model includes actual-world parameters, state rules, service windows,
units, assumptions and legal design domain. It is sufficient for the declared
ideal witnesses: the 28 static-grid and five additive controls are retained
saved results. Complete raw preserves every physical field, law, current output,
alternative world and public grid; only historical identifiers are removed.
The executable baseline includes a standalone export of the unchanged numerical
model bodies. Preparation checks its syntax without running it. No baseline is
reduced to total energy or average power alone.

Each trial has one participant directory. Future-intervention labels and
historical case mappings live in a separate evaluator index. The participant
input gate reads only that trial directory, verifies packet/asset hashes and
rejects unlisted files, private paths and explicit answer/relevance metadata.
Current verdicts and physically informative parameters remain legal facts.
These public examples were already exposed; the directory split does not make
them unseen tests or provide an operating-system sandbox.

In fixed-information use, external observations are prohibited and local
computation on supplied assets is allowed. In active-observation use, the same
initial packet at each information level is combined with a common API for
current trace, full declarative specification, complete raw model and model
response. Newly acquired facts, source digest, units, bytes and wall time are
recorded separately. This phase replays saved responses only; a different design
query abstains rather than launching a new solve. Live trials require fresh
contexts, one-directory mounts, an externally owned cumulative ledger, and
identical per-trial limits. The registered profile disables model, Agent and
native dispatch; no paid/provider lease is admitted here.

\section{E5: Agent discovery to a real BF consumer}
E5-1 asks an Agent to choose a legal observation from a general catalogue.
E5-2 asks it to identify a missing BF relation and propose the observation and
executable implementation itself. The initial interface supplies the task,
current facts, legal interventions and general tool schemas/costs. Relevant-field
labels, target observations and future service labels remain evaluator-only.
The earlier required-field selector and human headroom expression are explicit
construction baselines, not discoveries.

The frozen contract requires six stages: (1) a provenance-bound Agent proposal;
(2) a legal acquisition with units, domain and budget; (3) an immutable observation
bound to source, code, full input and actual cost receipts; (4) qualification by
a separate implementation, with static-rich, uninformative, tampered and
out-of-domain controls; (5) a typed input edge into a kernel-registered BF
consumer, bound to its full input, code, execution and independent service check;
and (6) an outcome-blind next judgment or design decision that retains rejection
or UNKNOWN when appropriate. Provider, model, run and usage identity must come
from external authority. Self-declared Agent ownership, self-reported costs,
echoing an observation or signing one's own consumer receipt is insufficient.

The existing loaded-rail/reset/event program is a candidate consumer; an adapter
connecting a qualified relation to that real program is not registered in this
phase. The validator therefore admits no real E5 experiment without external
kernel authority. Synthetic registry unit fixtures test admission rules only.
Even a valid receipt can record service FAIL; it establishes no improvement.
A benefit claim needs a separate frozen with/without-observation comparison.
Genuine Agent discovery, new independent qualification and real-consumer use
are all NOT\_RUN; transfer and hardware remain untested.

\paragraph{Phase-one binding.}
The preparation bundle is \texttt{BFP-1516e936ff2a3bd8902e}.
Its data and contract are stored under
\path{docs/research/phase1-20261020/interfaces/data/}. Preparation and gates:
\path{scripts/campaign_bf_interfaces.py}. New solver runs, paid model requests
and native dispatches are zero. The two original structural witnesses,
16 packets, numerical checks and historical costs remain unchanged.
"""
    (paper / "phase1-mechanisms.tex").write_text(mechanism_tex)
    (paper / "phase1-protocol.tex").write_text(protocol_tex)
    manuscript = (paper / "manuscript.tex").read_text()
    prior_region = manuscript.split("% BEGIN GENERATED RESULTS", 1)[1].split("% END GENERATED RESULTS", 1)[0]
    source_names = ["result.json", "mechanisms.json", "baselines.json", "e5-contract.json", "seal.json"]
    record = {"schema_version": "bf-interface-phase1-paper-binding-v1",
              "bundle": str(args.bundle.resolve().relative_to(root)), "audit": audit,
              "protocol_sha256": bf.sha((root / bf.PROTOCOL).read_bytes()),
              "manuscript_sha256": bf.sha((paper / "manuscript.tex").read_bytes()),
              "renderer_sha256": bf.sha(Path(__file__).read_bytes()),
              "sources": {name: bf.binding((args.bundle / name).read_bytes()) for name in source_names},
              "legacy_generated_region_sha256": bf.sha(prior_region.encode()),
              "shared_style_sha256": bf.sha((root / "papers/shared/hkustgz-paper.sty").read_bytes()),
              "english_logo_sha256": bf.sha((root / "papers/shared/assets/hkustgz-english.pdf").read_bytes()),
              "rendered": {name: bf.binding((paper / name).read_bytes()) for name in
                           ["phase1-mechanisms.tex", "phase1-protocol.tex"]},
              "new_solver_runs": result["new_solver_runs"], "paid_model_requests": 0, "native_dispatches": 0}
    (paper / "phase1-binding.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "b_reference_rows": len(names),
                      "e4_inputs": result["prepared_e4_inputs"], "equal_format_pairs": result["equal_format_pairs"]}))


if __name__ == "__main__":
    main()
