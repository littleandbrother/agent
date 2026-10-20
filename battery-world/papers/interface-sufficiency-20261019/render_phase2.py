#!/usr/bin/env python3
"""Render source-bound phase-two text; never run a model or scientific solver."""
from __future__ import annotations

import argparse
import hashlib
import json
import signal
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EPISODE = Path("/Users/depengsu/.local/share/bf-phase2-20261020/p2-e5-001")
PLAN = Path("/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/phase-plan-20261019/phase2")
GUARDS = {
    "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase2_discovery.py": "a1a3247803b0fa912c7ceffb7de58698c81682202424609da9e590969d693314",
    "papers/shared/hkustgz-paper.sty": "473994c5eb69167576ae0427ed4696e6542d5aadd10497868e38304e7c850872",
    "papers/shared/assets/hkustgz-english.pdf": "25f016add579c729d3447b4fca72b66fa98bd309cc82a9a4971bd61d8837f12e",
    "papers/interface-sufficiency-20261019/manuscript.tex": "d03b00a935e312b65d674225d1712430155b9b643e115e9c679a7d850d1d138f",
    "papers/interface-sufficiency-20261019/interface-sufficiency-phase1.pdf": "aa4d29d003d0caf7d3b15cca424cf2ec315d0b178375a123eaf127937832c785",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def record(path):
    raw = path.read_bytes()
    return {"path": str(path), "sha256": sha(raw), "bytes": len(raw)}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, default=EPISODE)
    parser.add_argument("--plan", type=Path, default=PLAN)
    args = parser.parse_args()
    signal.alarm(30)
    paper = Path(__file__).resolve().parent
    e = args.episode.resolve(); p = args.plan.resolve()
    paths = {
        "original_result": e / "external/result.json",
        "episode_result": e / "episode-result.json",
        "provider_costs": e / "provider-costs.json",
        "original_protocol": e / "protocol.json",
        "original_trace": e / "pi-public-trace.jsonl",
        "posthoc_result": e / "posthoc-adapter-001/result.json",
        "qualification": e / "posthoc-adapter-001/qualification.json",
        "consumer": e / "posthoc-adapter-001/consumer.json",
        "service": e / "posthoc-adapter-001/service.json",
        "posthoc_plan": p / "posthoc-interface-validation-plan.json",
        "adapter_regression": p / "adapter-v2/regression-result.json",
        "adapter_e5_schema": p / "adapter-v2/e5-schema.json",
        "ordered_state_audit": e.parent / "ordered-state-audit.json",
    }
    sources = {name: record(path) for name, path in paths.items()}
    data = {name: json.loads(path.read_bytes()) for name, path in paths.items() if path.suffix == ".json"}
    original = data["original_result"]; episode = data["episode_result"]
    result = data["posthoc_result"]; q = data["qualification"]
    consumer = data["consumer"]; service = data["service"]; costs = data["provider_costs"]
    regression = data["adapter_regression"]
    for name, expected in GUARDS.items():
        require(record(ROOT / name)["sha256"] == expected, "FROZEN_SOURCE_DRIFT:" + name)
    require(original["status"] == "ACTUAL_E5_ATTEMPT_REJECTED_AT_PROPOSAL_SYNTAX", "ORIGINAL_STATUS_CHANGED")
    require(original["rejection"] == "JSON_POINTER_REQUIRED" and original["revision_limit"] == 1, "ORIGINAL_GATE_CHANGED")
    require(not original["qualified_observation"] and not original["real_consumer_executed"], "ORIGINAL_FAILURE_PROMOTION")
    require(original["trace_sha256"] == sources["original_trace"]["sha256"], "TRACE_BINDING")
    require(original["protocol_sha256"] == sources["original_protocol"]["sha256"], "PROTOCOL_BINDING")
    require(episode["status"] == "INCOMPLETE_OR_STOPPED", "OWNER_OUTCOME_CHANGED")
    require(costs["requests"] == 6 and len(costs["rows"]) == 6 and all(row["status"] == "SETTLED" and row["usage"] for row in costs["rows"]), "USAGE_NOT_SETTLED")
    require(not costs["unknown_or_missing_usage"] and costs["unsettled_reserved_usd"] == 0, "UNKNOWN_COSTS")
    require(result["label"] == q["label"] == "POSTHOC_HOST_ADAPTER_REEVALUATION", "POSTHOC_LABEL")
    for alias in ["qualification", "consumer", "service"]:
        require(result[alias + "_sha256"] == sources[alias]["sha256"], "POSTHOC_BINDING:" + alias)
    require(result["original_failed_attempt_unchanged"] and not result["original_live_E5_success"] and not result["superiority_claim"], "CLAIM_BOUNDARY")
    require(result["new_provider_requests"] == q["new_provider_requests"] == q["new_model_proposals"] == 0, "POSTHOC_RESAMPLE")
    require(q["relation_value"] is True and q["unit_status"] == "CHECKED_AGAINST_SUPPLIED_MAPPING" and q["domain_status"] == "CHECKED_ON_SOURCE", "QUALIFICATION_CHANGED")
    call = q["actual_generated_corrected_call"]
    require(call["spec"]["mode"] == "construction" and call["spec"]["ast"]["op"] == "gt", "ACTUAL_MODE_CHANGED")
    require(consumer["policy"] == call["policy"] and consumer["after"]["used_observation"] and not consumer["before"]["used_observation"], "CONSUMER_EDGE")
    require(consumer["observation"]["value"] is True and consumer["observation"]["source_sha256"] == q["source"]["source_sha256"], "OBSERVATION_BINDING")
    require(consumer["after"]["design"] == service["selected"]["design"] and consumer["actual_executed_input_sha256"] == service["selected"]["input_sha256"], "EXECUTED_DESIGN_BINDING")
    require([service[k]["complete_service"] for k in ["original", "selected", "static_complete"]] == ["FAIL", "PASS", "PASS"], "SERVICE_CHANGED")
    require(all(service[k]["physical_qualification"] == "UNKNOWN" for k in ["original", "selected", "static_complete"]), "PHYSICAL_PROMOTION")
    require(regression["status"] == "PASS" and regression["targeted_regressions"] == 2 and regression["old_protocols_and_original_failure_results_unchanged"], "REGRESSION_CHANGED")
    # Presentation arithmetic on receipt values only; this is not a new AST,
    # qualification, service execution or proposed observation.
    source = q["source"]["payload"]
    dec = lambda k: Decimal(str(source[k]))
    tx_uj = dec("tx_current_a") * dec("tx_duration_s") * dec("output_v") * Decimal(1000000)
    reserve_uj = Decimal("0.5") * dec("capacitance_f") * (dec("ready_v") ** 2 - dec("off_v") ** 2) * Decimal(1000000)
    require(tx_uj == Decimal("28.8") and reserve_uj == Decimal("23"), "RECEIPT_NUMBERS_CHANGED")
    rows = []
    for name, label in [("original", "Original design"), ("selected", "Post-hoc selected"), ("static_complete", "Static complete information")]:
        row = service[name]; design = row["design"]; reference = row["reference"]
        receive = reference["first_receive_s"]
        rx = "--" if receive is None else f"{receive * 1000:.1f}"
        rows.append(f"{label} & {design['capacitance_f'] * 1e6:.0f} & {design['tx_not_before_s'] * 1000:.0f} & {rx} & {row['complete_service']} \\\\")
    upper = f"{costs['settled_charge_upper_bound_usd']:.7f}"
    estimate = f"{costs['cache_aware_rate_estimate_usd']:.9f}"
    methods = r"""% Generated only from retained actual episode/post-hoc receipts.
\section{Bounded proposal and external authority}
The host exposes source listing, acquisition, proposal and submission. A
proposal declares a hypothesis, source identifier, units and domain. Selection
names an existing JSON field. Construction supplies a bounded JSON abstract
syntax tree (AST) over fields, constants and permitted operators. A construction
must contain a source field and an operator; this mode label establishes no
novelty. The initial schema supplies no answer expression, required-field list
or target relation. The expression below reports actual model output
retrospectively.

The frozen B interpreter accepts at most 64 AST nodes and depth eight, an
8~MB JSON source and 32,768 vector elements. JSON Pointer paths identify data;
arbitrary Python and filesystem access are unavailable through the AST. Unit
dimensions must agree across operations, output units must match the root and
declared numeric domain bounds are checked on source values. Missing values,
invalid arithmetic or an unsupported domain yield UNKNOWN or a retained
rejection. These gates address bounded interpretation, not physical validity.

The two-argument evaluator accepts the corresponding raw JSON payload. With no
external field-unit map it reports declared units only. An S0-supplied map can
check unit consistency, while source authenticity and independent qualification
remain outside the proposer. The host separately binds original source bytes,
the model call, actual cost and consumer input. An OBSERVED value from the B
interpreter cannot certify its own source or service outcome.

The model also proposes a conditional design table with at most three branches.
Each branch contains a strictly typed equality value and a legal capacitance
and earliest-transmission design. The generic consumer starts with UNKNOWN
when no qualified observation exists. After external qualification it matches
the observed value to the original table and passes the selected full input to
the BF service. No expected service label is needed by the matching rule.

\section{The original actual episode failed}
The model acquired \texttt{component\_record},
\texttt{excitation\_record} and \texttt{saved\_activity}. These supplied the
device record, input/event/disturbance record and saved actions. It then
attempted a construction over those acquired facts. Its first proposal omitted
the leading slash required by JSON Pointer. The host rejected it with
\texttt{JSON\_POINTER\_REQUIRED}; that attempt consumed the registered
one-proposal allowance. The model subsequently generated corrected paths, but
the correction was rejected at the frozen proposal cap~\cite{attempt}.

The original outcome remains INCOMPLETE\_OR\_STOPPED at the episode level.
It produced no qualified observation, executed no real consumer and performed
no scientific execution for a proposed design. A process exit code of zero
therefore does not mean a successful E5 chain. The corrected call remains
actual model output in the retained trace, rather than a researcher-written
replacement.

All six actual provider requests have SETTLED usage records and no missing
usage or unsettled reservation. The retained ledger records a charge upper
bound of \$UPPER and a cache-aware rate estimate of \$ESTIMATE.
These are pinned-rate accounting values, not provider invoice amounts. They
belong to the original failed episode; the later adapter evaluation made zero
additional provider requests. Host and authoring assistance are outside this
episode's provider-usage total.

\section{Separately authorized post-hoc qualification}
The label \path{POSTHOC_HOST_ADAPTER_REEVALUATION} identifies a later engineering
evaluation of the already generated corrected call. It introduces no new
model proposal, new episode or proposer rerun. The review also replaces an
over-specific paired-world-only condition with source dependence across legal
design values; this changed qualification criterion is post hoc. The original
protocol and failed outcome remain intact~\cite{adapter}.

The corrected AST compares single-frame transmission energy with the current
capacitor's ideal energy reserve between ready and off thresholds:
\begin{align}
 E_{\mathrm{TX}} &= I_{\mathrm{TX}}\Delta t_{\mathrm{TX}}V_{\mathrm{out}}
                  = 28.8~\mu\mathrm{J},\\
 E_{\mathrm{reserve}} &= \tfrac12 C(V_{\mathrm{ready}}^2-V_{\mathrm{off}}^2)
                  = 23.0~\mu\mathrm{J},\\
 b &= [E_{\mathrm{TX}}>E_{\mathrm{reserve}}]=\mathrm{true}.
\end{align}
The retained source uses $I_{\mathrm{TX}}=8$~mA,
$\Delta t_{\mathrm{TX}}=2$~ms, $V_{\mathrm{out}}=1.8$~V,
$C=10$~$\mu$F, $V_{\mathrm{ready}}=2.8$~V and
$V_{\mathrm{off}}=1.8$~V. Both sides have energy dimensions; the output is a
dimensionless Boolean. The source-bound applicability constraints limit
capacitance to $[4,22]$~$\mu$F, earliest transmission to $[0,45]$~ms and
transmission current to the record's 8~mA. Other device and waveform
assumptions remain those of the frozen, uncalibrated ideal world.

S0 binds the acquired source hash and independently supplied unit map, then
checks the expression with a separate Decimal AST interpreter. The value is
true at 4~$\mu$F and false at 22~$\mu$F, rejecting a constant observation.
The two transmission-time probes leave it true, as expected because the
expression contains no time-scheduling field. Missing, self-signed and
out-of-domain observations remain UNKNOWN; source hash binding
passes~\cite{qualification}. These checks establish this source-dependent
engineering relation under the stated assumptions. They do not calibrate
the hardware.

The information added to the consumer is a derived relation among fields
already acquired from the component record. It is construction, rather than
selection of a predeclared observation. It is neither a new hardware
measurement nor evidence that the model autonomously discovered a previously
unseen physical relation. The energy comparison also omits startup work,
losses and event ordering; its truth alone is not a complete service verdict.

\section{Real consumer use and the strong static baseline}
Without an admitted observation the consumer retains UNKNOWN and the original
10~$\mu$F, 45~ms design. After post-hoc qualification, Boolean true selects
the model's original true branch: 15~$\mu$F with earliest transmission still
45~ms. The unused false branch proposes 10~$\mu$F and 30~ms; the receipts do
not establish its service outcome. The consumer receipt binds the observation,
unchanged model policy and complete executed input~\cite{consumer}.

\begin{table}[ht]
\centering\small
\begin{tabular}{lrrrr}
\toprule
Design condition & $C$ ($\mu$F) & Earliest TX (ms) & First RX (ms) & Service \\
\midrule
ROWS
\bottomrule
\end{tabular}
\caption{One public nominal BF task. The original exact-input result is reused;
the selected design adds one full service execution. The strong static result
is reused from its already executed input. All three have physical
qualification UNKNOWN. A missing reception is shown as --.}
\label{tab:actual-service}
\end{table}

The full service uses the unchanged BF feedback model and independent energy
and receiver checks. The selected design receives one frame at 46.9~ms and
passes complete service, whereas the original has no received frame and
fails. Its independent energy ledger passes in both designs; energy-check
success alone therefore cannot substitute for service success. The selected
trajectory has zero brownouts before the deadline. The comparison is an
executed post-hoc engineering consequence, not a prospectively admitted E5
benefit~\cite{service}.

The strong static complete-information design also passes, using the original
10~$\mu$F capacitance and earliest transmission at 0~ms; its first reception is
5.6~ms. Thus this evidence neither requires capacitance growth nor demonstrates
an advantage over complete static information. It also shows why the scalar
energy flag cannot determine service independently of scheduling. The device
record remains volatile. Reception before a reset, avoiding a reset and
retaining pending state across a reset are different properties; the legacy
\texttt{event\_preserved\_after\_reset} label is not used here to claim the last.

\section{Adapter repair, limits and reproducibility}
The separate adapter-v2 regression receipt records two targeted regressions.
For E5 it rejects the original malformed pointer before incrementing the valid
proposal counter and admits the already generated corrected call as one valid
proposal. It caps syntax rejections at two and retains the valid-proposal cap
of one. The other regression concerns the H action contract and is outside
this BF result. These are new-version, post-hoc qualification checks with no
new model requests or scientific executions. They do not replace the original
episode or establish a successful fresh live run~\cite{adapter}.

The original episode and the adapter result answer different questions. The
first demonstrates an actual failed attempt to use the interface. The second
demonstrates that existing model output can be qualified, consumed and linked
to a nominal service change under revised host admission. There is one exposed
development task, no randomized comparison, no held-out transfer evidence and
no physical qualification. The strong static passing result precludes a
superiority claim from this comparison. H proposal and design episodes are
separate evidence and are not aggregated into this manuscript's outcome.

The accompanying \texttt{phase2-binding.json} records exact source paths,
SHA-256 hashes, the frozen B interpreter, shared style, official vector English
logo and generated TeX. \texttt{render\_phase2.py} reads retained receipts and
performs presentation arithmetic only; it invokes no provider, scientific
solver or qualification interpreter. Building this manuscript adds no
experimental evidence. The original failed episode, corrected model call,
post-hoc plan, qualification, consumer, service and adapter regression records
remain separately addressable. This is a local development manuscript, not
a venue-compliance or hardware-acceptance result.
"""
    methods = methods.replace("UPPER", upper).replace("ESTIMATE", estimate).replace("ROWS", "\n".join(rows))
    (paper / "phase2-methods.tex").write_text(methods)
    binding = {
        "schema_version": "phase2-interface-actual-paper-binding-v1",
        "episode": "p2-e5-001", "original_outcome": original["status"],
        "posthoc_label": result["label"], "original_live_E5_success": False,
        "mode": "construction", "superiority_claim": False,
        "physical_qualification": "UNKNOWN", "sources": sources,
        "read_only_guards": GUARDS,
        "paper_sources": {name: record(paper / name) for name in ["phase2-manuscript.tex", "phase2-methods.tex", "render_phase2.py"]},
        "reported_numbers": {"tx_energy_uj": str(tx_uj), "ready_off_reserve_uj": str(reserve_uj),
                             "actual_original_provider_requests": costs["requests"], "all_original_requests_settled": True,
                             "posthoc_provider_requests": result["new_provider_requests"],
                             "posthoc_selected_new_scientific_executions": result["new_scientific_executions"]},
        "authoring_execution": {"new_provider_requests": 0, "new_scientific_executions": 0, "native_dispatches": 0},
        "claim_boundary": "Original actual E5 failed. Separate post-hoc engineering relation/consumer/service chain only; static complete information also passes. No autonomous unseen-relation discovery, superiority, transfer or physical qualification.",
    }
    (paper / "phase2-binding.json").write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "receipt_sources": len(sources), "original_live_E5_success": False,
                      "posthoc_service": "PASS", "static_complete_service": "PASS", "new_authoring_scientific_executions": 0}))


if __name__ == "__main__":
    main()
