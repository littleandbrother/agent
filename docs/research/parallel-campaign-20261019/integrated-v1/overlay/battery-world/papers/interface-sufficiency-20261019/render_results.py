#!/usr/bin/env python3
"""Render a paper fragment and CSV directly from the sealed public result."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    raw = args.data.read_bytes()
    result = json.loads(raw)
    here = Path(__file__).resolve().parent
    run_id = result["run_id"]
    error = result["reference_max_error_uj"]
    observations = result["observation_summary"]
    construction = result["construction"]
    packet_rows = []
    for level in ["current", "sufficient"]:
        for form in ["free-text", "structured"]:
            rows = [r for r in result["packets"] if r["information"] == level and r["format"] == form]
            packet_rows.append({"information": level, "format": form,
                                "correct": sum(r["correct"] for r in rows),
                                "unknown": sum(r["prediction"] == "UNKNOWN" for r in rows),
                                "cases": len(rows)})
    with (here / "observation-costs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(observations[0]))
        writer.writeheader()
        writer.writerows(observations)
    with (here / "packet-checks.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(packet_rows[0]))
        writer.writeheader()
        writer.writerows(packet_rows)
    packet_table = "\n".join(f"{r['information']} & {r['format']} & {r['correct']}/{r['cases']} & {r['unknown']}/{r['cases']} \\\\" for r in packet_rows)
    obs_table = "\n".join(
        f"{r['arm']} & {r['correct']}/{r['cases']} & {r['read_bytes']} & {r['audit_read_bytes']} & "
        f"{(r['observation_wall_ns'] + r['audit_wall_ns'] + r['selector_wall_ns']) / 1e6:.3f} & {r['model_runs']} \\\\"
        for r in observations)
    fresh_ms = sum(r["wall_ns"] for r in construction["fresh_process_executions"]) / 1e6
    fragment = r"""\subsection{E2--E3: two unexcited mechanisms}
Run \texttt{RUNID} contains two public development pairs, not statistical replications or unseen tests. Each pair has identical current observed event/rail traces and two passing current tasks. The identical legal D change then yields FAIL/PASS.

For the clamp pair, a fixed 20 $\mu$W source supplies 40 $\mu$J before a 30 $\mu$J service transaction at 2.5 s, with a 1 V service reserve. Both systems use 10 $\mu$F initially. Their ideal clamps are 3 V and 5 V. The initial maximum rail voltage is $\sqrt{8}=2.828$ V, so neither clamp activates and the entire current trajectory coincides. Changing only capacitance to 4 $\mu$F is legal in the common $[4,12]$ $\mu$F domain. The 3 V clamp now spills 22 $\mu$J and makes only 16 $\mu$J available above reserve; it fails the fixed service. The 5 V clamp spills zero and delivers 30 $\mu$J; it passes. The post-change margins are $-14$ and $8$ $\mu$J. These are ideal energy transactions, not measured PMIC startup or MCU current.

For the reset pair, an event is captured at 1 s and must be transmitted once at 4 s, by a 5 s deadline. The external event and transmission time stay fixed. Without a power reset, volatile and retained pending memories both deliver the event. A common D change inserts an outage from 2 to 3 s: volatile pending memory is cleared and delivers zero events; retained pending memory delivers one. This changes a state transition rather than rescaling an old energy/window template.

The analytic clamp implementation agrees with projected time integration; the ordered memory machine agrees with a separate event-program parser and tick interpreter. Both 1 ms and 0.5 ms settings agree on all eight current/intervention cases. Maximum energy discrepancy is MAXERROR $\mu$J. These implementations share ideal assumptions, so agreement is numerical/software evidence only.

Deleting the unexcited clamp threshold or reset-retention information restores aliasing in this encoding. It does not establish universal necessity of a field name or complete device-level E3 validation. Indeed an enriched \emph{static} model is sufficient on the declared ideal domain. It passes all 28 exposed legal-grid checks (20 clamp, eight memory), and a purely additive static control agrees with independent packet accounting on five service-cost values, including passing and failing designs. The clamp statistic is
\[
 M(C)=\min(E_0+P_{\mathrm{in}}t_{\mathrm{in}},CV_{\max}^2/2)-CV_{\min}^2/2-E_{\mathrm{service}}.
\]
Its sufficiency follows here from all input preceding service, an ideal cap, and no leakage or intervening workload. Those assumptions bound the claim.

\subsection{E4: executable equal-information preparation}
At each information level the prose and JSON packets contain identical facts and an identical summary (eight parity checks across 16 packet files). In fixed-information use no additional tool or read is legal. In active-observation use all arms start with the same current packet and share the same legal observations. Table~\ref{tab:packets} reports deterministic parse-and-judge checks on the proposed intervention. Abstentions are not counted as errors. This constrained prose serialization is preparation, not a test of model comprehension or unconstrained writing.

\begin{table}[ht]
\centering
\begin{tabular}{llrr}
\toprule
Information & Format & Correct & Unknown \\
\midrule
PACKETTABLE
\bottomrule
\end{tabular}
\caption{Fixed-information parser/decision checks; no model calls. Model-format benefit is NOT\_RUN.}
\label{tab:packets}
\end{table}

\subsection{E5-1: measured finite observation selection}
The selector receives researcher-supplied required-field metadata, not outcomes, and chooses the smallest eligible source by actual file-size estimate. Table~\ref{tab:costs} totals four public cases. Bytes are payload bytes returned to Python, separately counting source readback for audit; they are not storage-device I/O or monetary fees. Wall time includes acquisition, source audit, and selector where used. Source-export setup is retained in the raw data. These are single host measurements with uncontrolled OS cache, not a latency benchmark.

\begin{table}[ht]
\centering\small
\begin{tabular}{lrrrrr}
\toprule
Observation & Correct & Read B & Audit B & Wall ms & Model runs \\
\midrule
OBSTABLE
\bottomrule
\end{tabular}
\caption{Observation acquisition and audit costs. Uninformative returns UNKNOWN on all four.}
\label{tab:costs}
\end{table}

Fixed-rich, complete raw information, and an executable dynamic response all judge four of four correctly. The selected observation reads exactly the same facts and bytes as the fixed minimal mechanism-spec baseline. This batch supplies no independent algorithmic selection gain and does not weaken those strong baselines. A zero-byte acquisition budget abstains; three illegal changes and a tampered source binding are rejected.

\subsection{E5-2: executable construction preparation}
A deterministic compiler turns a researcher-specified headroom expression into a new standalone Python observation, with source hash, input schema and applicability domain. Its values $-14$ and $8$ $\mu$J agree with independent integration on all 20 exposed clamp-grid points and in two fresh-process executions. Construction took CONSTRUCTMS ms; reference qualification took QUALIFYMS ms (20 model runs); the two fresh processes took FRESHMS ms combined. The equation and relevant inputs were manually supplied. This validates executable construction and audit machinery, not autonomous discovery or held-out usefulness.

\paragraph{Evidence binding.}
The frozen protocol, raw result, packet files, generated program and costs accompany \texttt{RUNID}. Data source: \path{docs/research/parallel-20261019/interfaces/data/RUNID/result.json}. Entry point: \path{scripts/campaign_interfaces.py}; manuscript tables: \path{papers/interface-sufficiency-20261019/render_results.py}. Paid model requests and native dispatches are zero. Historical successful product solves were not rerun. The old three scaled families and the refinement/fixed-rich tie remain separate development negatives.
"""
    mantissa, exponent = f"{error:.2e}".split("e")
    replacements = {
        "RUNID": run_id, "MAXERROR": "$" + mantissa + r"\times 10^{" + str(int(exponent)) + "}$", "PACKETTABLE": packet_table,
        "OBSTABLE": obs_table, "CONSTRUCTMS": f"{construction['construction_wall_ns']/1e6:.3f}",
        "QUALIFYMS": f"{construction['qualification_wall_ns']/1e6:.3f}", "FRESHMS": f"{fresh_ms:.3f}",
    }
    for key, value in replacements.items():
        fragment = fragment.replace(key, value)
    (here / "results.tex").write_text(fragment)
    manuscript = (here / "manuscript.tex").read_text()
    begin, end = "% BEGIN GENERATED RESULTS", "% END GENERATED RESULTS"
    if begin in manuscript:
        before, middle = manuscript.split(begin, 1)
        _, after = middle.split(end, 1)
        manuscript = before + begin + "\n" + fragment + end + after
    else:
        manuscript = manuscript.replace(r"\section{E2--E3: structural development witnesses}",
                                        r"\section{E2--E5: public development results}")
        manuscript = manuscript.replace(r"\input{results.tex}", begin + "\n" + fragment + end)
    (here / "manuscript.tex").write_text(manuscript)
    (here / "paper-data-binding.json").write_text(json.dumps({
        "run_id": run_id, "result_sha256": hashlib.sha256(raw).hexdigest(),
        "source_data": str(args.data.resolve()), "packet_rows": packet_rows,
        "observation_rows": observations, "status": "actual data only; no model benefit predictions"
    }, indent=2) + "\n")
    print(json.dumps({"run_id": run_id, "manuscript": str(here / "manuscript.tex"),
                      "data_sha256": hashlib.sha256(raw).hexdigest()}))


if __name__ == "__main__":
    main()
