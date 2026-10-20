# Bounded storage during development

Storage is a dispatch prerequisite. A development batch is one feature change,
its targeted verification, generated-output review, cleanup, and measured
readback. Complete this loop before another batch starts.

1. Record filesystem free bytes, estimated peak *additional* bytes, output
   directory, and retained-output cap in the active feature. Reserve at least
   **10 GB plus the estimated peak**. Missing estimates or insufficient capacity
   defer expensive work. The native adapter also reserves **2 GB per miss**
   before its dispatch marker; this is a provisional guard, not a measured
   upper bound for every future mission. Longer or changed jobs need their own
   larger estimate. Streaming readback stops before consuming the reserve.
2. Use the registered source tree and dependency environment. Reuse exact-input
   caches without changing input identity, numerical semantics, or historical
   costs. Avoid new source/runtime copies, reinstallations, and repeated
   previews for routine review.
3. Use `agentlab.storage.copy_artifact` for large immutable copies and completed
   trace snapshots. New APFS destinations have separate inodes with shared
   blocks, full hash readback, atomic publication, and no overwrite of a
   different file. A non-APFS fallback reserves its complete size before copy.
   Never make shared writable hard links to another artifact. COW trace
   snapshots let unchanged prefixes share blocks while future appends remain
   isolated. Byte-preserving streaming zlib compression retains the existing
   encoding and verifies restoration before raw removal.
4. Run targeted checks with `PYTHONDONTWRITEBYTECODE=1`; inspect the diff and
   generated files. Temporary decompression and failed copies use scoped
   temporary directories that clean up on errors. Keep a final preview only
   when it is needed for delivery review. Keep small commands and receipts,
   rather than copying complete logs into multiple reports.
5. Remove confirmed rebuildable scratch and clean disposable review clones
   after recording exact commit/dependency restore information. Keep original
   experimental failures, bills, UNKNOWN, evaluator inputs, raw evidence and
   sealed receipts. Idle resident files can be transparently compressed after
   open-handle checks, original/final SHA-256 checks and metadata validation.
   Do not touch cloud placeholders or active databases. Cleanup is never an
   excuse to overwrite a sealed artifact or silently change a result.
6. Record final available bytes, retained growth, removed scratch, checks and
   limitations in the feature receipt. Review any unexplained growth before
   continuing. `du` and summed `st_blocks` overcount shared APFS blocks;
   **filesystem free-space changes** establish actual reclamation.

## Commands

From this Battery World source tree:

```sh
rtk proxy python3 -B scripts/storage_maintenance.py audit
rtk proxy env PYTHONDONTWRITEBYTECODE=1 BFWORLD_VERIFY_PROFILE=architecture-v2-ci ./init.sh
```

Use the registered development profile for verification. A maintenance operation
may use a **2 GB emergency reserve** with a conservative single-file peak
reservation; that exception never authorizes new experiments. The compaction
command accepts explicit idle runtime files only and requires a receipt path.
Applesauce 0.5.30 is a separately pinned 4.6 MB maintenance executable; it is not
a new product or experiment dependency. macOS reads the compressed files at
their original names and original byte contents.

## Boundaries of the 2026-10-19 first batch

The changes live in the S0 development tree. The original V2 source, published
Baseline, prior experiment definitions and historical receipts remain frozen.
The closed four-attempt H0/H1 batch stays closed. Maintenance creates a new
source/environment identity for future work; it does not retroactively qualify
old runs under new source hashes or authorize a new paid/native batch.

The first cleanup removes a clean temporary review clone and rebuildable
bytecode, and compresses historical probe waveforms, cumulative trace snapshots
and the historical request-evidence database without changing any bytes.
See the root `docs/storage-slimming-20261019/REPORT.md` for measurements and the
remaining review queue. This is staged maintenance, not a claim that all
historical artifacts are unused or that the entire system has been minimized.
