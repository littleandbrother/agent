# Current handoff: completed methods manuscript

The new 16-page manuscript and vector C24 evidence figure are complete.
See `PAPER-HANDOFF.json`, `paper-qa.json`, and `PAPER-CLAIMS.json` here.
Entry: `papers/method-reexecution-20261019/abc-20261020/main.tex` in campaign-a.
The old preparation `HANDOFF.json`, pack, protocol, module and tests remain
byte-identical; the instructions below are the historical preparation record.
No additional Pi/model/scientific/native execution is authorized or needed.
A-owned paper work is complete and idle for S0 integration acceptance.

---

# ABC C: first-chain handoff

The participant has not formed a new H and no paid/Pi study has run in this checkout. This package supplies the task mechanism, generic interpreter, real design consumer, independent evaluator and frozen finite queue. S0 alone imports the named paths, binds its exact backend/usage receipt, and starts Pi after one original execution chat is idle.

The API is in `bfworld.agentlab.campaign20261019.abc_methods`:

```python
prepared = prepare_episode(spec, episode_root)
# Send prepared["participant_input"] as the participant's actual task/context.
tool = tool_definition(spec)  # name, description, parameters; wrap with phase1.tool_definition
handler = create_handler(episode_root, spec)
# Existing BFPhaseGateway and SDK dispatch remain S0-owned.
result = independent_check(episode_root, spec)  # host only, after the episode
```

All module-owned runtime outputs are confined to `episode_root/methods/`. The public tool returns raw sampling runs, records, encoded receiver frames, relation-execution facts and acquisition counts. It never returns the independent new-task verdict or reference event table. Source/response/candidate hashes bind the final submission. A repeated check/submit of the same input reuses its response; no more than two different designs are admitted. The participant cannot change waveform, confirmation, event definition, clock, quantization or scoring.

Start with `pack/specs/C-formation-proposed.json`. Its exact 172,012-byte original-history packet contains all nine old O final cells: five submissions and four truncations. The two original `WRONG_EVENT_TIME` failures, full submissions, actual timestamp/receiver observations and costs remain; no new task or target formula is in that packet. `prepare_episode` exposes **no task** during formation. The schema and generic AST syntax are visible to both formation arms; Codex supplies no learned formula or winning design.

After S0 authenticates the raw model submission against the provider/usage receipt, freeze its byte hash. Do not hand-edit it. Resolve `C-validation-proposed.template.json` by adding `method_path` and `method_sha256` pointing to those exact model-authored bytes. Then run the distinct `C-first-proposed` task and call the independent checker. An absent/invalid proposal uses an explicit `frozen_no_update_receipt`; it does not trigger another formation. Preserve the original failed/absent proposal and costs. The ordinary arm has the same single formation, independent validation and operating budget. A valid method is carried forward unchanged even if validation fails; validation is reported, not used for final-result cherry-picking.

The first task and validation are separate from the 24 formal attempts. The finite C ceiling is two formation episodes, two validation episodes, one first-use episode and 24 formal episodes: 29 model episodes. Each has the same ceiling of 12 requests, 900 s, 40 tools, two designs and 65,536 output tokens. S0 must freeze the actual backend/configuration and common payload controls before paid admission. No failures, truncations or missing submissions are replaced.

Formal groups are H0, H0 plus history, ordinary reflection, and the proposed executable method, on three task conditions with two repetitions. The latter three receive the identical history bytes and tool permissions. H0 has the original H0 text and current task; its history difference is measured by H0+history. The task IDs, parameters, order and denominator are in `pack/protocol.json`; the second repetition reverses arm order. Templates are immutable planning inputs; S0 records resolved runtime specs separately.

The new tasks vary waveform phase, nonintegral confirmation durations, quantization/tolerance and whether event time means continuous qualification or excursion onset. The producer uses held RMS observations on a sampling grid, confirms at polls, selects a timestamp origin/offset, applies the fixed clock and quantization, and encodes the existing AR wire. Continuous interval truth is calculated independently. Event matching, receive deadline and decoded timestamp accuracy have distinct fields; a correct match cannot certify timestamp accuracy.

This is an additive **ideal continuously powered O timing component**. It reuses the existing AR wire, not the old energy kernel or a new platform. It does not qualify original O keepalive/energy, an A/R product, RF, hardware or RSI. The old contracts and five-stage delivery are untouched. The old method's 12/12 tie with more requests, four token-censored final cells, unchanged default H0 and A/R failures remain.

Targeted verification only:

```bash
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/python/bfworld/src /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B -m unittest discover -s tests/agentlab -p test_abc_methods.py -v
```

Seven tests cover the independent time gates, changed time definition, nonintegral confirmation/quantization, foreign/tampered response, independent CRC decoding, AST restrictions, split isolation, unchanged tool permissions, independent self-judgment error, exact-input reuse and the two-design cap. These are apparatus controls, not new participant results. No broad regression or repository-health claim is made.
