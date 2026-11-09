"""Five bounded implementation cases. All outcomes are synthetic software fixtures.
No scientific consumer, numerical oracle, model or provider is invoked.
"""
from copy import deepcopy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("partial_ancestor_frozen_controllers", BASE / "controllers.py")
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)
CONDITIONS = ["software-fixture-c0", "software-fixture-c1", "software-fixture-c2"]
SCOPE = {"family_id": "SYNTHETIC_SOFTWARE_FIXTURE_ONLY", "conditions": CONDITIONS}
INITIAL = {"holding_component": "off", "holding_capacity": 1,
           "holding_overflow": "drop_new", "read_source": "contact_only", "clear_after": "never",
           "persistent_queue": False, "fixture_knob": 0, "fixture_switch": False}
DOMAIN = {"holding_component": {"values": ["off", "fixture_on"]},
          "holding_capacity": {"kind": "int", "min": 1, "max": 3},
          "holding_overflow": {"values": ["drop_new", "drop_old"]},
          "read_source": {"values": ["contact_only", "holding_then_contact"]},
          "clear_after": {"values": ["never", "after_ack"]},
          "persistent_queue": {"kind": "bool"},
          "fixture_knob": {"kind": "int", "min": 0, "max": 3},
          "fixture_switch": {"kind": "bool"}}
CONTRACT = {"design_domain": DOMAIN, "active_variables": list(DOMAIN)}


def factory():
    return c.CandidateFactory(CONTRACT, INITIAL)


def family(design, *, partial=False, passed=False, unknown=False, request=None):
    result = {"design": deepcopy(design), "results": [], "fixture_only": True}
    if request:result["request_id"] = request
    for condition in CONDITIONS:
        ref = "software-fixture-" + c.digest([design, condition, partial, passed, unknown])
        relations = []
        if partial or passed:
            for stage in ["produced", "read"]:
                relations.append({"stage": stage, "record_key": "fixture-device/record-1",
                    "holds": True, "evidence_kind": "execution", "refs": [ref],
                    "condition_id": condition, "design_sha256": c.digest(design), "result_sha256": ref})
            relations.append({"stage": "ack", "record_key": "fixture-device/record-1",
                "relation_id": "fixture-read-before-ack", "holds": not partial,
                "evidence_kind": "runtime", "refs": [ref], "condition_id": condition,
                "depends_on": ["read_source", "clear_after", "persistent_queue"],
                "design_sha256": c.digest(design), "result_sha256": ref})
        result["results"].append({"design": deepcopy(design), "condition_id": condition,
            "execution_status": "TOOL_ERROR" if unknown else "COMPLETE", "model_valid": not unknown,
            "public_check": {"verdict": "UNKNOWN" if unknown else ("PASS" if passed else "FAIL"),
                             "received_count": 3 if passed else 0},
            "result_sha256": ref, "relationship_view": {"relations": relations}})
    return result


def make(kind="R", *, seed=314159, initial=None):
    f = factory()
    return c.DeterministicController(kind, f, initial or family(f.initial_design), scope=SCOPE, seed=seed)


def expect_error(fn, text):
    try:fn()
    except ValueError as exc:
        assert text in str(exc), (text, str(exc))
    else:raise AssertionError("expected ValueError: " + text)


def normalization_and_slot_cost():
    f = factory()
    raw = {**INITIAL, "holding_capacity": 3, "holding_overflow": "drop_old",
           "read_source": "holding_then_contact", "clear_after": "after_ack"}
    n = f.normalize(raw)
    assert n["inactive_only"] and not n["design_patch"] and n["design"] == f.initial_design
    assert n["raw_proposal"] == raw and len(n["normalized_inactive_fields"]) == 4
    assert n["semantic_key"] == f.semantic_key(INITIAL) and n["empirical_status"] == "UNKNOWN"
    enabled = f.normalize({**raw, "holding_component": "fixture_on"})
    assert enabled["design"]["holding_capacity"] == 3 and enabled["design"]["clear_after"] == "after_ack"
    g = c.FreeJointInterface(f, family(f.initial_design), scope=SCOPE, seed=314159)
    action = g.submit(raw)
    assert action["slot"] == 2 and action["semantic_reuse_of"] == g.root_id
    g.update(family(action["design"], request=action["request_id"]))
    assert len(g.nodes) == 1 and g.slots == 2 and g.stop()["status"] == "FINAL_SELECTION_REQUIRED"
    bad = g.submit({**INITIAL, "fixture_knob": 99})
    assert bad["status"] == "STATIC_REJECTED" and g.slots == 3
    assert g.finalize(INITIAL)["final_submission_kind"] == "ORIGINAL_PARENT_RETAINED"
    return {"inactive_fields_canonicalized": 4, "duplicate_and_invalid_each_consumed_slot": True,
            "enabled_parameters_preserved": True, "slots": g.slots}


def shared_seeded_joint_factory_and_free_G():
    f = factory()
    pools = [f.generate(f.initial_design, seed=seed, round_index=0) for seed in c.SEEDS]
    assert pools[0] == f.generate(f.initial_design, seed=c.SEEDS[0], round_index=0)
    assert len({c.digest(p["generation_records"]) for p in pools}) == 3
    assert all(0 < p["raw_proposals"] <= 32 for p in pools)
    assert all(any(len(x["design_patch"]) >= 2 for x in p["candidates"]) for p in pools)
    assert all(any(x["origin"] == "FULL_DOMAIN_RESTART" for x in p["candidates"]) for p in pools)
    for kind in ("D", "R", "A"):
        ctrl = make(kind)
        ctrl.step()
        expansion = next(e for e in ctrl.events if e["event"] == "EXPAND_PARENT")
        assert expansion["pool"] == pools[0]
    g = c.FreeJointInterface(f, family(f.initial_design), scope=SCOPE, seed=314159)
    free = {**INITIAL, "holding_component": "fixture_on", "holding_capacity": 2,
            "holding_overflow": "drop_old", "fixture_knob": 2, "persistent_queue": True}
    action = g.submit(free)
    assert action["status"] == "ACTION" and action["design"] == free
    g.update(family(free, request=action["request_id"]))
    assert g.stop()["status"] == "FINAL_SELECTION_REQUIRED"
    final = g.finalize(free)
    assert final["final_design"] == free and final["eligible_for_holdout"]
    return {"actual_seed_orderings": 3, "common_factory_same_parent": True,
            "joint_and_full_width_enabled": True, "G_arbitrary_full_design_and_model_final": True}


def actual_failed_ancestor_gate_and_lineage():
    r, a = make("R"), make("A")
    first_r, first_a = r.step(), a.step()
    assert first_r["design"] == first_a["design"]
    for ctrl, action in [(r, first_r), (a, first_a)]:
        result = family(action["design"], partial=True, request=action["request_id"])
        update = ctrl.update(result)
        assert update["low_score"] and update["useful_failed"]
    failed_id = r.by_semantic[r.factory.semantic_key(first_r["design"])]
    second_r, second_a = r.step(), a.step()
    assert second_r["parent_id"] == failed_id
    assert second_a["parent_id"] == a.root_id
    assert all(e["parent"] != failed_id for e in a.events if e["event"] == "EXPAND_PARENT")
    assert r.nodes[failed_id].summary["condition_pass_count"] == 0
    assert all(x["empirical_status"] == "UNKNOWN" for e in r.events if e["event"] == "EXPAND_PARENT" for x in e["pool"]["candidates"])
    r.update(family(second_r["design"], passed=True, request=second_r["request_id"]))
    chain = r.ancestor_chains()[-1]
    assert chain["all_pass"] and chain["lineage"][1]["node"] == failed_id
    assert chain["lineage"][1]["useful_failed"] and chain["lineage"][1]["result_refs"]
    return {"fixture_actual_expansion_parent": failed_id,
            "R_expands_evidenced_failed_parent": True, "A_blocks_before_generation": True,
            "lineage_has_evaluated_parent_child_results": True,
            "scientific_evidence": False}


def unknown_scope_private_identity_and_no_inheritance():
    ctrl = make()
    action = ctrl.step()
    wrong = family(action["design"], request="wrong-request")
    expect_error(lambda:ctrl.update(wrong), "RESULT_REQUEST_BINDING")
    missing = family(action["design"], request=action["request_id"])
    missing["results"].pop()
    expect_error(lambda:ctrl.update(missing), "COMPLETE_UNCHANGED_CONDITION_FAMILY_REQUIRED")
    malformed = {"results": []}
    expect_error(lambda:c.summarize(malformed, action["design"], CONDITIONS, ctrl.factory), "WHOLE_DESIGN_RESULT_BINDING")
    private = family(action["design"], partial=True, request=action["request_id"])
    private["results"][0]["relationship_view"]["relations"][0]["record_key"] = {"observer_epoch": 3}
    expect_error(lambda:ctrl.update(private), "PRIVATE_OBSERVER_IDENTITY_FORBIDDEN")
    unknown_fact = family(action["design"], partial=True, request=action["request_id"])
    for member in unknown_fact["results"]:
        for relation in member["relationship_view"]["relations"]:relation["holds"] = None
    summary = c.summarize(unknown_fact, action["design"], CONDITIONS, ctrl.factory)
    assert summary["capabilities"] == [0] * len(c.STAGES) and not c.targets(summary)
    out = ctrl.update(family(action["design"], unknown=True, request=action["request_id"]))
    assert out["summary"]["statuses"] == ["UNKNOWN"] * 3 and not out["low_score"]
    assert ctrl.termination == "TOOL_OR_DOMAIN_UNKNOWN" and not ctrl.nodes[out["node_id"]].useful_failed
    return {"request_family_design_private_guards": True, "UNKNOWN_not_failure_or_capability": True,
            "TOOL_ERROR_typed_stop": ctrl.termination}


def diverse_archive_restart_final_quota():
    d = make("D")
    parent_ids = []
    for _ in range(5):
        action = d.step()
        assert action["status"] == "ACTION"
        parent_ids.append(action["parent_id"])
        d.update(family(action["design"], partial=True, request=action["request_id"]))
    assert d.slots == 6 and len(d.archive) >= 3
    assert len(d.archive) == len(d.nodes) and any(n.low_score for n in d.nodes.values())
    expansions = [e for e in d.events if e["event"] == "EXPAND_PARENT"]
    assert [e["round"] for e in expansions if e["pool"]["restart"]] == [0, 3]
    assert expansions[0]["parent"] == d.root_id and expansions[3]["parent"] == d.root_id
    assert d.step()["reason"] == "SLOT_CAP" and d.slots == 6
    final = d.stop()
    assert final["final_submission_kind"] == "ORIGINAL_PARENT_RETAINED" and not final["eligible_for_holdout"]
    assert not final["adopted"] and not final["all_condition_PASS"]
    snap = d.snapshot()
    assert len(snap["ancestor_chains"]) == 5 and len(snap["nodes"]) == 6
    return {"retained_failed_alternatives": len(d.archive)-1, "restart_rounds": [0, 3],
            "actual_slots": d.slots, "unchanged_parent_not_new_success": True}


if __name__ == "__main__":
    tests = [normalization_and_slot_cost, shared_seeded_joint_factory_and_free_G,
             actual_failed_ancestor_gate_and_lineage, unknown_scope_private_identity_and_no_inheritance,
             diverse_archive_restart_final_quota]
    rows = []
    before = os.statvfs(BASE).f_bavail * os.statvfs(BASE).f_frsize
    for test in tests:
        row = {"case": test.__name__, "fixture_only": True}
        try:row.update(status="PASS", details=test())
        except Exception as exc:
            row.update(status="FAIL", error=type(exc).__name__+": "+str(exc), traceback=traceback.format_exc())
        rows.append(row)
    receipt = {"schema": "partial-ancestor-B-software-checks-v1", "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "source_sha256": hashlib.sha256((BASE/"controllers.py").read_bytes()).hexdigest(),
       "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       "software_cases": len(rows), "passed": sum(x["status"] == "PASS" for x in rows), "cases": rows,
       "cheap_numeric": 0, "full_inputs": 0, "provider_requests": 0,
       "private_A_qualification_exposure": False, "free_bytes_before": before,
       "free_bytes_after": os.statvfs(BASE).f_bavail * os.statvfs(BASE).f_frsize,
       "claim_boundary": "Synthetic software behavior only; no actual scientific ancestor comparison or advantage."}
    (BASE/"software-checks.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    sys.exit(0 if receipt["passed"] == 5 else 1)
