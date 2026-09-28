# Interactive output recovery — BFA-009

The original conversation `pi-chat-48879f0893e33a22` returned only `已` with
`stopReason=length`: 36,727 input tokens and one output token. This was an output
clamp, not a successful answer. Offline replay of the original Pi session prefix
estimates 34,021 context tokens. The incorrect 32,000 context window, minus Pi's
4,096 safety margin, caused `max_tokens=1`.

Both active interactive entry points now advertise a 1,048,576 context window
and a 4,096 output allowance. This matches the
[official DeepSeek Flash integration metadata](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/).
Frozen batch entries and Pi SDK sources are unchanged.

Before paid dispatch, the interactive proxy omits completed tool-call/result
pairs from previous user turns. It retains every user message, system instruction,
public assistant message and current-turn tool exchange. Partial exchanges stay
intact. A context notice explains the omission and directs exact factual checks
to existing files/results. This is deterministic request projection, not model
summarization or rewriting the Pi session. Automatic Pi compaction remains off.
Original/projected hashes, sizes, omitted call IDs and the originating user message
are recorded in `model_request_context` and Developer → Trace exports.

Interactive requests now have a 24-call limit per explicit user message instead
of per conversation lifetime. Duplicate operations/retries do not reset it. The
600-second turn lease, original cumulative USD/token limits and experiment gates
remain enforced. Batch owners retain their lifetime 24-call limit. Model ingress
is bounded at 2 MiB so preserved history can reach projection; the projected
provider request still has the existing 128,000-byte cap. Interactive output
allowances below 1,024 are rejected before a paid dispatch.

`length` now produces a failed/truncated turn, including in the actual Pi process;
the partial text remains visible with an explanation. The UI distinguishes input
and output tokens. Historical records receive the same display correction without
being rewritten. Both open localhost tabs were reloaded to build `e5fe058345b79918`.

## Verification

- Original-session replay: old window gives 1 output token; corrected window gives 4,096.
- 255 isolated full-init tests pass, including 64 agentlab tests; SDK/Studio checks pass.
- Actual browser → original Pi session → DeepSeek acceptance: one settled call,
  401 stream deltas, 14,976 input and 401 output tokens, 638 characters of Chinese
  public answer, normal `stop`, no tools or experiments. Cost upper bound USD 0.004974.
- Acceptance temporarily restricted this owner's additional spend to USD 0.05;
  the previous owner cap was restored. Global limits never changed.
- Actual request projection: 125,623 → 52,872 bytes; 52 → 26 messages; 24 completed
  historical tool calls omitted. Exported raw Trace bytes match the local file.
- All 817 prior model ledger rows, 15 prior user messages, 4,862 prior chat events,
  120 jobs, model limits and owner caps remain identical. Of 1,975 existing history
  files, 1,971 are identical, two conversation logs only appended, and the resumed
  conversation's mutable runtime state/receipt were refreshed normally.
- Targeted Pi TypeScript compilation passes. The required root `npm run check`
  was run in an isolated copy because it formats files; it stops on six existing
  unused-variable warnings in the three BF chat entry files. Its later root check
  stages were not reached. The live source was not broadly reformatted.

Evidence and rerunnable offline replay:
`/Users/depengsu/Documents/bf-agent-workbench/verification/context-recovery/`.
Run `node .../scripts/bfa009-replay.mjs` for the captured-prefix clamp replay; it
intercepts the SDK payload and forbids network dispatch. Run `./init.sh` in the
isolated `verification/battery-world` checkout for full checks.

This validates interactive recovery, not the factual correctness of every generated
sentence, CAD/FEM, hardware or Harness RSI. Extremely long current turns still stop
at the byte/budget limits rather than silently dropping active evidence. No automatic
model retry, budget replenishment or experiment rerun was added. No Git commit.
