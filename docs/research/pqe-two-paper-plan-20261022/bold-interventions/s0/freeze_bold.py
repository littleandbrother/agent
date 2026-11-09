"""Single offline direct-path check, then freeze this finite accountable batch."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import run_bold as r
from bfworld.agentlab.pqe20261022 import methods, restricted_worker
from bfworld.agentlab.pqe20261023bold import consumer, contracts
from bfworld.agentlab.pqe20261023bold.drivers import BoldEpisodeDriver

S, O, B = r.HERE, r.OUT, r.BASE
parent = r.read(O / "b/parent-program.json")
history = r.read(O / "b/common-history.json")
assert len(history) == 8
freeze = r.read(O / "a/ENGINEERING-FREEZE.json")
engineering = r.read(O / "a/ENGINEERING-RESULTS.json")
assert engineering["full_inputs"] == 8 and len(engineering["rows"]) == 8
assert consumer.source_identity() == freeze["shared_sources"]

# Rehydrate the original failed H3 invocation from its existing audit graph.
# No original artifact is copied, modified or executed.
old_root = B / "f1-conditional-learning/s0/episodes/t1-h3"
index = r.read(old_root / "public-objects/index.json")
objects = index.get("objects", index)

def restore(value):
    if isinstance(value, dict):
        if "audit_public_object" in value:
            return r.read(objects[value["audit_public_object"]]["path"])
        return {k: restore(v) for k, v in value.items()}
    return [restore(v) for v in value] if isinstance(value, list) else value

old = restore(r.read(old_root / "method-transcript.json"))
old_protocol = r.read(B / "f1-conditional-learning/shared/protocol.json")
old_program = r.checked(old_protocol["public_bindings"]["h3"])["program"]
old_state = deepcopy(old["final_state"])
old_state.pop("update_status", None)
old_ctx = {"state": old_state, "decision": old["steps"][-1]["select"],
           "result": old_state["last_result"], "public_assessment": None,
           "site_config": old_program["config"].get("H-UPDATE", {}),
           "site_prompt": old_program["prompts"].get("H-UPDATE", "")}
old_call = old["steps"][-1]["site_calls"][-1]
assert methods.digest(old_ctx) == old_call["context_sha256"]
old_frame = {"site": "H-UPDATE", "source": old_program["code"]["H-UPDATE"], "context": old_ctx}
old_bytes = len(json.dumps(old_frame, allow_nan=False, separators=(",", ":")).encode())
assert old_bytes == 2461796

result_refs = {r.read(meta["path"]).get("result_sha256"): oid
               for oid, meta in objects.items() if isinstance(r.read(meta["path"]), dict)}

def compact(value):
    if isinstance(value, dict):
        if value.get("result_sha256") and "facts" in value:
            return contracts.compact_feedback(value, result_refs[value["result_sha256"]])
        return {k: compact(v) for k, v in value.items()}
    return [compact(v) for v in value] if isinstance(value, list) else value

compact_ctx = compact(old_ctx)
compact_ctx.update(site_config=parent["config"].get("H-UPDATE", {}),
                   site_prompt=parent["prompts"].get("H-UPDATE", ""))
new_frame = {"site": "H-UPDATE", "source": parent["code"]["H-UPDATE"], "context": compact_ctx}
new_bytes = len(restricted_worker._encoded(new_frame)) - 1
loaded = methods.load_program(parent, hook_runner=restricted_worker.run_isolated_hook)

def deny_ask(*args):
    raise AssertionError("OFFLINE_DIRECT_PATH_MUST_NOT_DISPATCH_MODEL")

updated = loaded.invoke("H-UPDATE", compact_ctx, deny_ask, lambda c: {})
assert set(updated) <= methods.UPDATE_FIELDS

# Actual parent Update and Generate on old public engineering data, then actual
# Rank over four already executed whole designs. No new candidate is simulated.
tasks = r.checked(freeze["tasks"])
task = list(tasks.values())[0]
rows = engineering["rows"][::2]
initial = r.checked(rows[0]["binding"]["public-result.json"])
state = r.p.episode_initial_state(task, initial["design"], initial["problem"])
state["last_result"] = initial
limits = {"output_tokens_per_request": 65536, "output_tokens_total": 131072,
          "reserve_usd": 5, "new_numerical_inputs": 4}
driver = BoldEpisodeDriver("strong_generic", deny_ask, episode_id="offline-original-public-replay",
    initial_state=state, initial_public_object_ref="bold-engineering-01-original-parent-t1",
    model_identity=r.p.MODEL_IDENTITY, request_reserve_usd=.19, limits=limits,
    program=parent, common_history=history,
    expected_methods_sha256=r.bind(r.legacy.PKG / "methods.py")["sha256"],
    isolated_program=True, full_evaluator=lambda request: (_ for _ in ()).throw(AssertionError("NO_NEW_SCIENCE")))
budget = dict(provider_requests_remaining=12, tool_calls_remaining=24, new_numerical_inputs_remaining=4,
              reserve_usd_remaining=5, wall_s_remaining=900, output_tokens_remaining=131072)
initial_update = driver.apply_initial_update(budget)
assert initial_update["status"] == "UPDATED" and not driver.callback_records
batch = driver.harness.generate(driver.state, driver._quota())
assert batch["status"] == "READY" and 1 <= len(batch["candidates"]) <= 4 and not batch["rejected"]
known_candidates, known_results = [], []
for row in rows:
    result = r.checked(row["binding"]["public-result.json"])
    actual = {"operation": "edit", "design_patch": result["design"], "problem_patch": {}}
    candidate = {"id": row["cell"], "operation": "edit", "actual_input": actual,
                 "target": "existing-public-replay", "expected_state_change": "existing whole-design result",
                 "prediction_or_unknown": "UNKNOWN", "observation_branches": [],
                 "affected_constraints": [], "cost_bound": 1, "validity_conditions": ["offline replay only"]}
    known_candidates.append(candidate)
    known_results.append({"candidate_id": candidate["id"], "actual_input_digest": methods.digest(actual),
                          "public_result": result, "public_object_ref": "existing-" + row["cell"],
                          "accounting": {"numerical_inputs": 0, "tool_calls": 1, "cache_reuse": True}})
envelope = {"results": known_results, "owner_budget_after": budget}
bounded = contracts.validate_full_candidate_batch(known_candidates, envelope, state=driver.state)
rank_context = {"state": driver.state, "candidates": known_candidates, "quota": driver._quota(),
                "full_candidate_results": bounded}
selected = loaded.invoke("H-RANK", rank_context, deny_ask, lambda c: {})
assert selected["selected_id"] == rows[1]["cell"]

check = {"package": r.PACKAGE, "at": r.now(), "status": "PASS",
         "original_failed_invocation_sha256": methods.digest(old_ctx),
         "original_frame_bytes": old_bytes, "new_compact_frame_bytes": new_bytes,
         "unchanged_frame_limit": restricted_worker.MAX_FRAME,
         "parent_update_on_compacted_original_failure": True,
         "actual_initial_update_status": initial_update["status"],
         "actual_generated_legal_candidates": len(batch["candidates"]),
         "actual_rank_existing_public_results_selected": selected["selected_id"],
         "all_original_public_materials_remain_pageable": True,
         "new_model_full_cheap_calls": 0,
         "pre_dispatch_fixture_correction": "The offline replay fixture initially supplied tool_calls=0, correctly rejected by the new >=1 broker-action contract. Corrected the fixture accounting to1; no scientific/model input occurred and no method was changed.",
         "scope": "One offline implementation check with one fixture-accounting repair; no new task, child or scientific efficacy qualification."}
r.save(S / "direct-path-check.json", check)

# All frozen artifacts below are reviewable bindings, not backup source trees.
r.save(O / "shared/parent.json", {"program": parent, "source": r.bind(O / "b/parent-program.json")})
task_freeze = r.read(O / "a/host/TASK-FREEZE.json")
door_initial = r.read(O / "a/host/DOOR-INITIAL-RECEIPT.json")
door_entry = {"role": "t1", "world": "DOOR", "task": task_freeze["door"], "status": "READY",
              "initial_public_result": r.bind(O / "a/host/door-initial/public-result.json")}
lc_entry = r.read(S / "host/lc-entry.json")
old_model = r.read(B / "f1-conditional-learning/shared/protocol.json")["model_contract"]
model = {**old_model, "package": r.PACKAGE, "at": r.now(), "total_usd": 40, "episodes_max": 8,
         "requests_total_max": 96, "reused_existing_transport_no_paid_probe": True}
source_files = list(r.PKG.glob("*.py")) + [S / "run_bold.py", Path(__file__),
    r.legacy.PKG / "methods.py", r.legacy.PKG / "episode_methods.py",
    r.legacy.PKG / "conditional_learning_methods.py", r.legacy.PKG / "f1first_methods.py",
    r.legacy.PKG / "restricted_worker.py", r.legacy.PKG / "pilot.py",
    B / "f1-conditional-learning/s0/run_learning.py", B / "service-repair-m3/s0/run_m3.py",
    B / "service-repair-m3/s0/public_projection.py",
    B / "f1-conditional-learning/shared/runtime/scripts/pqe_pi_callback.mjs",
    r.APP / "scripts/pqe_pi_callback.mjs"]
source_bindings = {str(p): r.bind(p)["sha256"] for p in source_files}
for path, digest in r.adapter.source_identity()["lc"].items():
    source_bindings[path] = digest
for name, digest in consumer.source_identity().items():
    path = (r.PKG.parent / name) if name.startswith("bold/") else r.legacy.PKG / name
    if name.startswith("bold/"):
        path = r.PKG / name.split("/", 1)[1]
    source_bindings[str(path)] = digest
protocol = {"package": r.PACKAGE, "frozen_at": r.now(), "model_contract": model,
            "limits_per_episode": r.LIMITS, "total_caps": r.TOTAL,
            "tasks": [door_entry, lc_entry], "source_bindings": source_bindings,
            "apparatus_source": r.adapter.source_identity(),
            "public_bindings": {"parent": r.bind(O / "shared/parent.json"),
                                "history": r.bind(O / "b/common-history.json"),
                                "catalog": r.bind(O / "b/public-source-catalog.json")},
            "new_task_selection": r.bind(O / "a/host/TASK-FREEZE.json"),
            "engineering_results": r.bind(O / "a/ENGINEERING-RESULTS.json"),
            "provider_before": r.host.provider_snapshot(), "storage": r.capacity(),
            "rules": {"same_consumer_all_methods": True, "no_new_task_in_formation": True,
                      "automatic_formation_count_each": 1, "max_raw_proposals_each": 2,
                      "no_semantic_repair_or_task_replacement": True,
                      "each_solve_evaluated_candidates_max": 4, "full_dynamic_inputs_max": 34,
                      "full_dynamic_seconds_max": 4080, "full_dynamic_each_seconds_max": 120,
                      "no_backups_environments_worktrees_commits_push": True}}
r.save(r.PROTOCOL, protocol)
resource = r.read(S / "resource-ledger.json")
assert resource["full_dynamic_inputs"] == 1
resource["full_dynamic_inputs"] += 9
resource["full_dynamic_wall_s"] += engineering["wall_s"] + door_initial["wall_s"]
resource["candidate_evaluations"] += 9
resource["engineering_and_door_initial_import"] = {
    "engineering": r.bind(O / "a/ENGINEERING-LEDGER.json"),
    "door_initial": r.bind(O / "a/host/DOOR-INITIAL-RECEIPT.json"),
    "new_full_inputs": 9, "wall_s": engineering["wall_s"] + door_initial["wall_s"]}
r.save(S / "resource-ledger.json", resource)
r.validate(protocol)
print(json.dumps({"event": "BOLD_FROZEN_READY", "direct_check": check,
                  "protocol": r.bind(r.PROTOCOL), "accounted_new_full_inputs": resource["full_dynamic_inputs"]}), flush=True)
