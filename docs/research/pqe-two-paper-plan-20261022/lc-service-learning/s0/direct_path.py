"""One offline check with the retained failed payload; no provider/science."""
from copy import deepcopy
from pathlib import Path
import json

import runtime as r
from bfworld.agentlab.pqe20261022 import methods, restricted_worker
from bfworld.agentlab.pqe20261023bold.contracts import compact_feedback
from bfworld.agentlab.pqe20261024lc.driver import SequentialEpisodeDriver
from bfworld.agentlab.pqe20261024lc.projection import PublicObjects


def check():
    parent = r.read(r.BASE / "bold-interventions/b/parent-program.json")
    history = r.read(r.BASE / "bold-interventions/b/common-history.json")
    old_root = r.BASE / "f1-conditional-learning/s0/episodes/t1-h3"
    objects = r.read(old_root / "public-objects/index.json")
    objects = objects.get("objects", objects)

    def restore(value):
        if isinstance(value, dict):
            if "audit_public_object" in value:
                return r.read(objects[value["audit_public_object"]]["path"])
            return {k: restore(v) for k, v in value.items()}
        return [restore(x) for x in value] if isinstance(value, list) else value

    old = restore(r.read(old_root / "method-transcript.json"))
    old_program = r.checked(r.read(r.BASE / "f1-conditional-learning/shared/protocol.json")["public_bindings"]["h3"])["program"]
    state = deepcopy(old["final_state"])
    state.pop("update_status", None)
    context = dict(state=state, decision=old["steps"][-1]["select"], result=state["last_result"], public_assessment=None,
                   site_config=old_program["config"].get("H-UPDATE", {}), site_prompt=old_program["prompts"].get("H-UPDATE", ""))
    assert methods.digest(context) == old["steps"][-1]["site_calls"][-1]["context_sha256"]
    old_bytes = len(json.dumps(dict(site="H-UPDATE", source=old_program["code"]["H-UPDATE"], context=context),
                              allow_nan=False, separators=(",", ":")).encode())
    assert old_bytes == 2461796
    registry = PublicObjects(r.HERE / "direct-path-public-objects")
    refs = {}
    for oid, meta in objects.items():
        value = r.read(meta["path"])
        if isinstance(value, dict) and value.get("result_sha256"):
            refs[value["result_sha256"]] = registry.register(value, path=meta["path"])

    def compact(value):
        if isinstance(value, dict):
            if value.get("result_sha256") and "facts" in value:
                return compact_feedback(value, refs[value["result_sha256"]])
            return {k: compact(v) for k, v in value.items()}
        return [compact(x) for x in value] if isinstance(value, list) else value

    current = compact(context)
    current.update(site_config=parent["config"].get("H-UPDATE", {}), site_prompt=parent["prompts"].get("H-UPDATE", ""))
    new_bytes = len(restricted_worker._encoded(dict(site="H-UPDATE", source=parent["code"]["H-UPDATE"], context=current))) - 1
    assert new_bytes < restricted_worker.MAX_FRAME == 2000000

    def no_model(*args):
        raise AssertionError("OFFLINE_CHECK_CANNOT_CALL_PROVIDER")

    loaded = methods.load_program(parent, hook_runner=restricted_worker.run_isolated_hook)
    assert set(loaded.invoke("H-UPDATE", current, no_model, lambda c: {})) <= methods.UPDATE_FIELDS
    projected = registry.project(dict(site="G-ATTRIBUTE", context=dict(result=current["result"])))
    result = projected["context"]["result"]
    if "summary" in result:
        result = result["summary"]
    assert result["facts"]["activity_counts"] == current["result"]["facts"]["activity_counts"]
    assert "detail_catalog" in result["facts"]

    protocol = r.read(r.BASE / "bold-interventions/shared/protocol.json")
    entry = next(x for x in protocol["tasks"] if x["role"] == "t2")
    task, initial = r.task(entry), r.checked(entry["initial_public_result"])
    state = r.p.episode_initial_state(task, task["initial_design"], task["initial_problem"])
    state["last_result"] = initial
    ref = registry.register(initial, path=entry["initial_public_result"]["path"])
    driver = SequentialEpisodeDriver("strong_generic", no_model, episode_id="offline-saved-LC-sequence", initial_state=state,
        initial_public_object_ref=ref, world_kind="LC_PV", max_evaluated_candidates=2,
        model_identity=r.p.MODEL_IDENTITY, request_reserve_usd=.19,
        limits=dict(output_tokens_per_request=65536, output_tokens_total=131072, reserve_usd=5, new_numerical_inputs=2),
        program=parent, common_history=history, expected_methods_sha256=r.bind(r.legacy.PKG / "methods.py")["sha256"], isolated_program=True)
    budget = dict(provider_requests_remaining=12, tool_calls_remaining=24, new_numerical_inputs_remaining=2,
                  reserve_usd_remaining=5, wall_s_remaining=900, output_tokens_remaining=131072)
    assert driver.apply_initial_update(budget)["status"] == "UPDATED"
    action = driver.next(budget)
    assert action["status"] == "ACTION"
    actual_design = {**state["design"], **action["decision"]["actual_input"].get("design_patch", {})}
    old_candidate = r.BASE / "bold-interventions/s0/episodes/t2-h1/candidates/01"
    saved = r.read(old_candidate / "public-result.json")
    assert actual_design == saved["design"], "offline selected input must match the original saved execution"
    saved["usage"] = dict(paid_model_requests=0, numerical_inputs=0, wall_s=0, reused=True)
    saved_ref = registry.register(r.read(old_candidate / "public-result.json"), path=old_candidate / "public-result.json")
    updated = driver.update(saved, public_object_ref=saved_ref)
    assert updated["update_status"] == "UPDATED"
    before = len(driver.harness.program.calls)
    next_action = driver.next(budget)
    assert driver.harness.program.calls[before - 1]["site"] == "H-UPDATE"
    assert not driver.callback_records
    registry.save_index()
    return dict(status="PASS", package=r.PACKAGE, at=r.now(), original_failed_context_sha256=methods.digest(context),
        original_frame_bytes=old_bytes, compact_frame_bytes=new_bytes, unchanged_frame_limit=restricted_worker.MAX_FRAME,
        exact_view_preserved_after_original_registration=True, inline_activity_counts_and_reference=True,
        actual_initial_update=True, actual_generate_rank=True, saved_exact_first_result_update=True,
        next_decision_after_update=next_action["status"], new_provider_requests=0, new_full_dynamic_inputs=0,
        cheap_checks_consumed=1, scope="One saved-payload direct-path implementation check, not scientific efficacy evidence.")


if __name__ == "__main__":
    path = r.HERE / "direct-path-check.json"
    if path.exists():
        raise ValueError("DIRECT_PATH_ALREADY_RECORDED_NO_REPEATED_UNCHANGED_CHECK")
    try:
        result = check()
    except Exception as exc:
        r.save(path, dict(status="RETAINED_LOCAL_CHECK_ERROR", at=r.now(), error=type(exc).__name__ + ":" + str(exc),
                          new_provider_requests=0, new_full_dynamic_inputs=0))
        raise
    r.save(path, result)
    print(json.dumps(result), flush=True)
