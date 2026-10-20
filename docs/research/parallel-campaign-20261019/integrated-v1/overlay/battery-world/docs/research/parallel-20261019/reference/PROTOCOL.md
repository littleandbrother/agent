# BFA-045 finite reference protocol

Owner campaign-a. Common source baseline
CB-6f1c798155bb7ca2352d362d57a7e2032dc79379450a723ea3cff2751ce5318c,
HEAD 317d40fef0137d3c1ad1873e53c3e9968b31200a. Before implementation,
5,543 baseline files matched by SHA-256. PROJECT.yaml has the single S0-owned
overlay `active_feature: null -> BFA-045-ar-b-reference`; its hash is frozen in
conditions.v1.json. No other baseline source drift was observed.

Hypothesis: one explicit single-light A/R service chain and an independent B
transient/event mechanism can produce reproducible nominal positive/negative
controls before an Agent is connected. Paper claim: a finite public reference
and qualification boundary. Falsifier: independent source/energy or receiver
disagreement, retained history counted as new sensing, concealed dark failures,
unqualified lux-to-watt conversion, or nominal output called measured hardware.

The configuration was written before implementation and before any calculation.
Its SHA-256 is 19757a1c9aa8a889dbb7258276121d3621c0faa7d468aa47ff95ac9a1a201fdb.
It defines all six registered public-development tasks and 17 fixed conditions
(10 A/R, 7 B). Expected positive/negative control outcomes were declared there.
The 90/20 uW light-source points are **assumed watts inputs**, not results of
converting 200/50 lux or reading off a calibrated IV curve. Lux is metadata.
Source/input models, capacitor, background and activity loads are versioned
behavioral assumptions. Independent integration verifies equations and saved
evidence, not the physical fidelity of these assumptions.

Schema: campaign-task-v1 and campaign-result-v1 are local feature artifacts,
not changes to shared scientific contracts. The three executable source files,
configuration, candidate installation/BOM and retrieved source documents are
copied into each new candidate tree and hashed. The A/R numerical step is 1 s;
its load impulses do not resolve switching transients. B uses 0.1 ms steps and
an explicit ESR guard. Both receive an independent source-energy integral and
Decimal ledger replay. The checker parses wire bytes with a bitwise CRC while
the sender/endpoint use crc_hqx. No results are imported from old Pi runs.

Negative controls: no energy; cold start too late; stale sample; insufficient
dark storage; volatile history; duplicate acceptance; B ESR transient; late
energy; captured volatile event lost after an injected brownout. A/R history
uses 12 h darkness and separate retention/sampling/gap/time/upload gates. It is
a limited development profile, not the full 24 h R0 temperature-and-shock
lifecycle. The main A/R-1 light/dark profile retains the six-hour proposal.
There is no second energy source. No service requirement may be reduced after
observing a failure. Formal selection and final test sets do not yet exist.

Resources: zero paid model requests, zero native EDA/simulator/hardware calls,
no original owner resumption. Runner wall time <=120 s; verification <=300 s;
output <=500 MB; stop below 5 GB free. Stop on unexpected baseline drift,
reference disagreement, hidden evaluator exposure, unsupported model scope,
unknown native state, or required source edit outside owned_paths. Expected
negative controls are saved as failures, not repaired by changing semantics.
Computations use only stdlib and immutable local input. The output directory
must be new; readback uses --verify-run and performs zero new simulations.

Definition of done: targeted tests; one complete new raw-output run; independent
readback and seal; architecture-v2-ci init; input/result JSON and CSV; candidate
file-tree manifest; sources, actual conclusions, limitations and S0 handoff.
Root/PROJECT/feature/state updates belong exclusively to S0. No commit or push.

v0.2 differences: A and R are one installed product line; B is public
qualification, never unseen evaluation; F1a physical recalculation differs from
F1b fresh design decisions; F4 begins early under S0; interface discovery stays
a research object rather than a receipt-format exercise. This work supplies
reference facts for those methods and does not itself claim Agent benefit.
