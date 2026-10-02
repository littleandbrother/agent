# Double-RAW RC qualification addendum
Date: 2026-10-01 UTC · prospective and unexecuted

The independent final review requires actual RC smoke that exercises the same dependent-variable precision profile as the PMIC decks. The earlier RC smoke deck did not explicitly request numdgt=15, so a float-only smoke result would be insufficient for this kit's all-double RAW parser gate.

smoke/rc_double_smoke.cir is an additive, separately named copy of our own earlier passive RC installation deck. The only operational change is numdgt=15 on the existing plotwinsize=0 options line; its comment identifies it as an unexecuted double-RAW installation smoke. R, C, source, simulation horizon, maxstep and measurements are unchanged. The original RC and the sealed four-case plan/decks remain unchanged.

Before any PMIC run, a supported authorized runtime must:
1. Execute this RC smoke under the approved installation-smoke scope and retain exact deck/executable identity, process result, native log and complete RAW
2. Successfully read the actual native RAW with src/retained_raw.py; inspect header precision flags and verify the reader used the all-double real profile, not the older mixed float32 profile
3. Check the expected 1 ms passive RC response and the native 1/5/10-time-constant measurements against original full-resolution samples
4. Independently review the real smoke evidence and qualify the actual encoding/layout; synthetic tests do not satisfy this step

This addendum adds no native result, no PMIC case, no automatic launcher and no execution approval. The existing four-case attempt budget applies to the PMIC diagnostic only; installation smoke is separate and must remain within its own authorized scope. This kit does not authorize repeated smoke retries, changes to sandbox/security settings, or substituting an unapproved executor.

