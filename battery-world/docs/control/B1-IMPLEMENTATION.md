# B1 control-plane implementation

`scripts/agent_tools.py` provides line-delimited JSON calls: describe, experiment,
read, status, recover, submit. This is a thin adapter surface for a general coding
agent or DSH tool subprocess; it does not depend on DSH's changing internal APIs.
No installed DSH compatibility or actual model-provider campaign is claimed.

`scripts/serve_studio.py` exposes the same broker on loopback. The browser can
change design parameters, record a pre-experiment prediction, run the real local
solver, inspect its receipt, and recover pending work. Offline HTML disables
execution while retaining all sealed visualizations.

Budget is fixed when a state database is created, not by incoming requests.
Idempotency conflicts, reference mutation, non-finite values and oversize inputs
are rejected. Independent scientific replications carry a distinct identity;
they are not treated as executor retries. Same-origin and Host checks protect the
local HTTP mutation endpoints; no CORS allowance is installed.

Subprocess fault injection covers death after reservation and after sealing.
Recovery re-executes deterministic computation where needed and verifies the
same sealed result. Committed experiment reservations are charged once; repeated
execution attempts are reported separately. CPU time lost to a killed process
is unknown, never silently counted as zero.

This is *software completion*, not completion of research milestone B1: a formal
fixed-model pilot, usage accounting, restricted participant filesystem, and
independent mission qualification remain required. The unsandboxed developer
host is not a security isolation mechanism. Submissions are recorded but never
self-promoted to VMS.

Reproduce: `./init.sh`; broker tests are in `tests/control/test_broker.py`.
Run local Studio: `corepack pnpm run studio`.
