# Launch correction — 2026-09-07

The user continued on 2026-09-07. The first launch stopped before dispatch:
zero model calls, zero tokens, CNY 0. `stop.json` preserves that event.
Preparation had incorrectly started the engineering wall timer and included
the overnight user pause. The timer now starts at first paid dispatch; once
any call is reserved, process restarts cannot reset it. No monetary cap,
protocol task, arm, qualification gate or scientific equation changed.
