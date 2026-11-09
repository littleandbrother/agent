# BFA-087 B final readback

Status: B work complete for `BF-PQE-S3-UPDATE-CONTINUE-20261023-001`.

Both original continuations consumed their own real Update output after the same externally executed public failure, generated and selected engineering actions, and reached a valid public PASS with six delivered packets. This establishes an executed failure-to-Update-to-action-to-consequence chain in both conditions. The shared external action was not autonomously chosen and was charged only in the previous package.

| Condition | Candidate evaluations / new numerical inputs | Model requests | Estimated USD | Final public outcome |
|---|---:|---:|---:|---|
| Strong generic | 2 / 2 | 5 | 0.0845871 | Valid PASS, 6 packets |
| Fixed H | 1 / 1 | 1 | 0.0456315 | Valid PASS, 6 packets |

The generic first action used 270 µF, 8 mm stroke and 8 mm cam base radius. Its cam diameter exceeded the 35 mm envelope, so its public service verdict was UNKNOWN/MODEL_DOMAIN; its tentative six packets are not valid service evidence. Its next action reduced stroke to 7.5 mm and passed. Fixed H proposed 300 µF, 7.5 mm stroke and 6.5 mm base radius and passed on its first action. Both retained startup 1.9 V and TX gate 1.85 V. Final minimum TX terminal voltages were 2.230695 V and 2.185206 V respectively. Their remaining three brownouts each occurred during IDLE with empty queues after deliveries, not during TX.

The generic Update used the seed/default path without typed memory. Fixed H executed the frozen deterministic H-UPDATE and passed 13 typed records to its actual next Generate: complete_service REFUTED, two geometric constraints SUPPORTED and ten other relations NOT_DISCRIMINATED. These records establish actual memory consumption, not a uniquely identified failure cause. The repaired numerical parameters came from the model payload and reached the submitted input unchanged. All submitted generated pools contained one candidate, no experiment candidate, and prediction UNKNOWN. The fixed-H exclusions list was empty: no geometry projection or exact-point rejection caused this selected repair.

The 5-versus-1 request difference includes two generic ranking calls and one generic success-confirmation Generate, versus deterministic fixed-H selection and stopping. The remaining extra Generate accompanied the invalid first iteration. This one pair does not isolate a benefit of Update memory from fixed prompts, model generation variance, control overhead or ordinary failure feedback. Both conditions repaired successfully; no learned H/G, stable superiority, unseen transfer, hardware qualification or statistical advantage is established. The task remained exposed development material even though the causal prefix excluded later successful configurations.

Static interface readback found that a non-OK H-RANK/Select response stops the existing episode. It does not reject the current batch and return to Generate. An OK selection with an invalid selected ID can retry ranking the same batch. H-GEN contract correction can regenerate malformed actions, but the coupled geometric envelope is not such an editable-field contract violation. The generic rank acknowledged the invalid geometry and submitted its sole candidate; it had a reject-and-stop outlet, not a valid reject-and-regenerate route. No interface change or probe was made for this package.

One fixed-H model explanation called radius plus stroke an assembly-depth constraint. The frozen model uses this quantity for cam diameter/lateral envelope; axial depth is fixed. This wording is not accepted as validated physical causality.

`CHAIN-READBACK.json` binds the actual Update states, consumed structured model candidates, selected inputs, public results and cost records. `PAPER-APPEND-BINDINGS.json` proves one appended paragraph per paper with unchanged original byte prefixes. B made zero model calls, scientific executions or tests and did not read private assessments or raw execution artifacts. S0's `runtime-closeout.json` reports six new SETTLED requests, zero inflight, and retention of the historical R11 UNKNOWN/null-usage/full-reserve row; B did not independently re-audit the private billing ledger. The combined new estimated model cost is USD 0.1302186, not an invoice.

B changed only its report directory and the two authorized paper appendices. S0 owns root feature/progress/handoff integration and the original runtime closeout. No commits, backups, environments, worktrees or new workers were created.
