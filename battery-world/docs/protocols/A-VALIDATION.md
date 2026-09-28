# A World Kernel validation record

Validation date: 2026-09-04 (Asia/Shanghai)

Authoritative command:

```bash
./init.sh
```

## Result

- Environment gate: Python 3.11.9, PyArrow 22.0.0, jsonschema 4.23.0,
  PyYAML 6.0.2.
- Python gates: 12/12 passed across contract, dependency, integration, replay,
  recovery, and tamper tests.
- TypeScript wire-contract gate: passed with the locked workspace toolchain.
- Fresh reproduction: byte-identical bundle seal and equal bundle identity.
- Model calls: 0.
- Hardware result: false.

## Frozen identity

```text
run_id          run-9b86a46b1f0cbcd204c70ef580a019845e3c7a6d3bcda89c7df74e38dbda7cca
event_head      sha256:80ac2e7c35fd6479742126e842a795a9c81466e411f6c268fb6e4f4540bf6180
scientific_hash sha256:5c5a9374104130aa3d8d8de38dc28dc7ed50324cdb3bf33f9b0300498b7ab986
bundle_hash     sha256:6fa761099b10c9b10060a3636380e5d83221cd95272ee6ac9efa96955ad97059
```

## Scientific checks

| Phase | dt (s) | Peak (V) | Overvoltage samples | Brownout samples | Inferences | Verdict |
|---|---:|---:|---:|---:|---:|---|
| baseline | 0.005 | 3.817598129045 | 83 | 0 | 5/5 | expected failure |
| revised | 0.005 | 3.481747021842 | 0 | 0 | 5/5 | pass |
| fine validation | 0.001 | 3.480835962989 | 0 | 0 | 5/5 | pass |

The coarse/fine peak difference is 0.000911058853 V, below the frozen 0.02 V
tolerance.

## Recovery and evidence checks

The chaos gate terminates the process immediately after the durable baseline
checkpoint, resumes from that checkpoint, and requires the recovered run to
produce the same scientific hash and event bytes as a clean run. A modified
checkpoint artifact blocks resume. Bundle-byte and event-chain tampering are
also rejected.

Studio, the future-Agent observation adapter, and the independent verifier all
read through `RunBundleReader` and bind the same `run_id` and `event_head`.
`replay.html` is a static projection of the bundle; it computes neither physics
nor verdicts.

## Claim boundary

This closes A only as a deterministic, load-dependent, F1-simplified numerical
apparatus. It does not establish physical Rotary-TENG fidelity, measured
hardware behavior, Agent efficacy, DeepSeek Harness benefit, or RSI.
