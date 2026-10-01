# Existing-pipeline handoff (additive, separately manifested)

The frozen parent core is unchanged. This adapter emits the actual
closed-simulation-spec-v1 candidate consumed by the installed
bfworld.agentlab.simulation_chain.pipeline.submit_candidate.
It does not import or execute COMSOL/LTspice/native.py during preparation.

## What works now

- Exact pinned source checks against installed contracts/native/solver/program
- Actual installed Python/C implementation map is bound into source identity
- Solver settings come from the very candidate passed to the pipeline
- Canonical-native provider check refuses substitution of the generic causal fixture
- Fresh tool and implementation recheck helper; scientific-identity cache namespace
- Exact existing callable kwargs, no production source or cache edits
- Camera no-op, changed capacitance invalidation, legacy continuation rejection
- Nine offline tests, including AST inspection of the real submit_candidate signature

## Minimal integration at the future authorized execution boundary

1. Obtain actual pipeline.tool_identity() and pipeline.implementation() in the
   intended native runtime. Missing tools/model files must fail, not become placeholders.
2. prepare_request(candidate, source_bound_native_model_contract, actual_tools)
3. Immediately before execution, verify_runtime(request, pipeline.tool_identity(),
   pipeline.implementation()). Do not bypass this with saved attestations.
4. Call pipeline.submit_candidate(**pipeline_kwargs(request, NEW_RUN_PATH,
   ISOLATED_CACHE_PARENT)). The latter returns candidate/output/cache_root/confirm.
5. Preserve its entire result and raw artifacts. Write a companion containing
   request.identity, request SHA, actual runtime identities and result-file SHA.
   The current pipeline need not understand extra candidate fields. Do not inject
   unknown fields into its strict candidate schema.
6. Before evaluating or pooling records, require world/task/input/source/model/solver
   identity matching. Neither the native pipeline's received-group proxy nor this
   companion grants attributed event, physical qualification or formal admission.

This is the smallest remaining wrapper integration, not a production code patch.
The preparation output is usable by that exact pipeline, but no native call is
made in this package. The independently frozen core's 43 tests and these 9 tests
must not be described as a complete native or application run.

DEV-COUPLING-01 is refused until a new canonical checkpoint exists. Recipe-only
initial-state identity is explicitly planning evidence, not proof of actual reset
or initial energy. The original world/mission remain fixed; no precharge,
external power, shortened opening or lower success requirements are admitted.

Example preparation (no solving):
python -B prepare_request.py --candidate candidate.json --model model-contract.json \
  --tools actual-tool-identities.json --output /tmp/NEW-request.json

Test:
python -B -m unittest -v test_handoff

The mock tools in test_handoff.py are explicitly synthetic nonexecuting inputs,
not native runtime or feasibility evidence.
