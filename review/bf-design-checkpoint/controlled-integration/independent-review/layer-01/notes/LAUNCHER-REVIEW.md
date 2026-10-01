# Independent review: controlled launcher integration

Status: passes the declared **trusted offline real-Pi integration** scope. Live participant launch remains blocked. This review does not qualify a hostile-participant sandbox, scientific evaluator, holdout, native task, participant-authored H1 or future-task benefit.

## Verified implementation path

The overlay invokes the existing `bfworld.agentlab.launcher.freeze` to compile pinned harness sources with the restored TypeScript compiler. Its changed entrypoint is an instrumentation-only copy of the real Pi agent main, with the actual SDK session/resource/tool setup retained. Events follow actual module imports and successful solver/improver function calls. A pre-import `harness_loaded` event alone is not accepted. The entrypoint requires literal `dryRun === true` before harness imports and before model-runtime/session creation; `session.prompt` is skipped.

The Python participant route also unconditionally stops at readiness, before the production launcher can grant capabilities, issue a token or invoke a provider. The only subprocess route permits a finite trusted source-variant allowlist; it is explicitly not an isolation boundary for arbitrary uploaded or participant code. A local fixture service permits only a budget read and has no model/experiment endpoint.

## Independent verification

- The producer's 225 manifested file hashes/sizes and 9 declared symlink targets verify. The code tested in a separate copy matches the final producer code. Its 2,161 input hashes were recomputed, including task/world/evaluator and protocol sources; original input files remain unchanged.
- All 32 tests pass in the isolated reviewer copy. Tests exercise real Pi import/invocation, compiler failure, invocation failure, timeout, stale bytes, replay/recovery, lineage and budget guards. They are trusted engineering controls, not participant episodes or scientific samples.
- A separate reader, without importing the producer's validator, verifies both retained event hash chains, immutable terminal-receipt hashes, trace/stderr hashes, source/build identities, nonce/PID/mode binding, import-before-call ordering and each recorded invocation-output hash. It independently checks the all-assigned registry, 11 attempts per run, a denied extra attempt, the never-started assignment, and zero model messages/service dispatches beyond the known local budget request.
- Each retained run has nine actual trusted Pi processes, with the build-failure and denied-budget cases retained separately. Both runs and all 22 recorded attempts remain in the final receipt. V1 contains the real relative-output-path failure and lacks a historical adapter-source attestation; neither fact was erased or retroactively invented. V2 binds the repaired adapter and passes the intended controls.
- The direct reviewer-owned negative subprocess uses `dryRun:false`. It exits with `CONTROLLED_OVERLAY_TRUSTED_DRY_RUN_ONLY` before harness activation or session completion. This supplements the existing Python dispatch/grant/token denial tests. No model call was made.

## Issues found and disposition

1. **Terminal cache hash check:** the initial inspected `AttemptBook.begin` returned completed cached receipts without checking their journal-pinned hash. The final code shares receipt validation across write, replay and recovery and verifies the pinned hash. An independent no-process tamper fixture confirms `RECEIPT_TAMPER` on both cache replay and recovery.
2. **Invocation-output binding:** initial evidence logged an output hash without validating it. The final trace includes the actual trusted output; validation recomputes the hash and rejects missing or changed output. Actual traces were independently checked.
3. **Generator receipt binding:** initial lineage validation did not establish that the resolver returned the requested receipt content. Final validation defines a canonical JSON digest, checks it against `generator_invocation_receipt_hash`, and retains a wrong-artifact negative test. It still reports that participant authorship has not been independently verified and grants no promotion.
4. **Cost scope/build failures:** process-only timing originally excluded preparation/build work. Final receipts distinguish process costs from attempt-local preparation/build costs; build failure is retained in the same attempt journal. Historical acquisition, scientific qualification, transfer and complete H-loop cost remain explicitly unestablished.
5. **Relative output path:** the producer's first retained CLI run exposed a real path-normalization error. Final code resolves the root, includes a relative-path regression and retains the failed run. Historical relative evidence paths were resolved against the original producer directory during reviewer readback, without modifying any receipt.

No blocking defect remains for this limited trusted-offline deliverable.

## What remains blocked

The world/task/evaluator identity attached to these processes is a prospective target binding; the executed task is the trusted activation fixture. The magnetic experiment service is not registered in the legacy runtime, and old literal model/task/caps cannot become new authorization. Qualified tasks remain 0/2, no independently feasible reference is admitted, the model/budget/analysis/assignment/holdout protocol is unapproved, and this Linux host has no qualified existing Seatbelt participant isolation. The evaluator and holdout checks demonstrate source binding and synthetic boundary logic, not an actual protected scientific confirmation service.

Lineage field/hash consistency is not authenticated participant authorship. Manual H1 is labelled manual, H0 restoration creates no new generation, and rollback retains prior attempts and costs. The npm lock pins dependency versions; it is not a byte attestation of every external dependency. No full monorepo/application-health claim follows from focused tests.

## Identities and artifacts

- Producer file manifest SHA-256: `a258f5f4efea5841095c41b0bde95ec05fbd0656140190253bbb39c4aa1a3850`
- Producer final receipt SHA-256: `14cfba5f0965feb9d543191314987fa06a665b877d77bd163e956ee2591ecfd9`
- Final adapter SHA-256: `6a2cd15be472053d79a158e50ca644edc03ed81896f5639c2e044b8170e98e87`
- `outputs/LAUNCHER-BYTE-VERIFICATION.json`
- `outputs/LAUNCHER-JOURNAL-ACTIVATION-READBACK.json`
- `outputs/launcher-isolated-tests.log`
- `outputs/CACHE-INTEGRITY-REPAIR-READBACK.json`
- `outputs/DIRECT-LIVE-GUARD-READBACK.json`

The review started only fixed trusted offline subprocess controls. No actual participant/model call, native/scientific solve, credential action, commercial software execution, commit or push occurred.
