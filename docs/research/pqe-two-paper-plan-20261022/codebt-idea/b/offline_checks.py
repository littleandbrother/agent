"""B's bounded software checks; no consumer, source solver or provider calls.

Fixture interval axioms test checker algebra, never physical bounds. Family
verdicts below are synthetic feedback, never results for A's scientific task.
Run with the registered product-cad Python and PYTHONDONTWRITEBYTECODE=1.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback

from bfworld.agentlab.pqe20261024debt.facts import describe_contract, design_facts
from bfworld.agentlab.pqe20261024debt.task import validate_design
from bfworld.agentlab.pqe20261024debt.obligations import (
    digest, derive_obligations, closure_delta)
from bfworld.agentlab.pqe20261024debt.search import DebtSearch, DomainSpace, expand_snapshot_obligation
from bfworld.agentlab.pqe20261024debt.baselines import GenericJointAgent, MixedJointSearch
from bfworld.agentlab.pqe20261024debt.certificates import (
    build_certificate, verify_certificate, covers_design)

HERE = Path(__file__).resolve().parent
CONTRACT = describe_contract()
INITIAL = deepcopy(CONTRACT["defaults"])
SCOPE = {"conditions": ["fixture-a", "fixture-b", "fixture-c"],
         "offline_fixture": True, "service_sha256": "fixture-service"}
CHECKS, DETAILS, BLOCKED = [], {}, []


def static_validate(design):
    validate_design({"design_domain": CONTRACT["design_domain"],
                     "components": CONTRACT["components"]["mcu"]}, design)


def no_science(frame, event, arg):
    if event == "call" and "bfworld/agentlab" in frame.f_code.co_filename:
        if frame.f_code.co_name in {"execute_design", "source_step", "_midpoint_step",
                                   "_execute_enabled", "paid_callback"}:
            BLOCKED.append(frame.f_code.co_filename + ":" + frame.f_code.co_name)
            raise AssertionError("SCIENTIFIC_OR_PROVIDER_CALL_FORBIDDEN")


def family(design, *, verdict="FAIL", request_id=None):
    out = {"design": deepcopy(design), "scientific_result": False,
           "fixture": "Synthetic verdict; no scientific execution or result.",
           "results": [{"condition_id": cid, "execution_status": "COMPLETE",
                        "model_valid": True, "public_check": {"verdict": verdict},
                        "result_sha256": "software-fixture-" + digest([cid, design, verdict])}
                       for cid in SCOPE["conditions"]]}
    if request_id:
        out["request_id"] = request_id
    return out


def planner_factory():
    calls = []
    def planner(request):
        calls.append(deepcopy(request))
        return {"usage": {"status": "SOFTWARE_FIXTURE"},
                "payload": {"candidates": ([{"id": "partial-fixture",
                    "design_patch": {"holding_component": "lp_fifo"}}] if len(calls) == 1 else [])}}
    return planner, calls


def expect_value_error(function, fragment):
    try:
        function()
    except ValueError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError("Expected " + fragment)


def check(name, function):
    try:
        function()
        CHECKS.append({"name": name, "status": "PASS"})
    except Exception as exc:
        CHECKS.append({"name": name, "status": "FAIL",
                       "error": type(exc).__name__ + ":" + str(exc),
                       "traceback": traceback.format_exc(limit=4)})


def rows(design, **kwargs):
    return derive_obligations(design, design_facts(design), scope=SCOPE, **kwargs)


def consumption_and_identity():
    before = rows(INITIAL)
    partial = {**INITIAL, "holding_component": "lp_fifo"}
    missing = rows(partial, previous=before, previous_design=INITIAL,
                   trigger_diff={"holding_component": "lp_fifo"})
    consume = next(o for o in missing if o.type == "CONSUMPTION")
    assert consume.status == "OPEN" and consume.trigger_diff == {"holding_component": "lp_fifo"}
    assert "read_source" in consume.dependencies and consume.predicate["from_fact_ids"]
    read = {**partial, "read_source": "holding_then_contact"}
    extended = rows(read, previous=missing, previous_design=partial,
                    trigger_diff={"read_source": "holding_then_contact"})
    closed = next(o for o in extended if o.id == consume.id)
    assert closed.status == "SATISFIED" and closed.invalidations
    assert consume.id in closure_delta(missing, extended)["satisfied"]
    reverted = rows(INITIAL, previous=missing, previous_design=partial,
                    trigger_diff={"holding_component": "off"})
    assert consume.id not in closure_delta(missing, reverted)["satisfied"]
    stale = [{"obligation_id": consume.id, "holds": True, "refs": ["stale-fixture"],
              "design_sha256": digest(INITIAL)}]
    assert next(o for o in rows(partial, observations=stale) if o.id == consume.id).status == "OPEN"
    DETAILS["consumption"] = {"stable_id": consume.id, "activation": consume.trigger_diff,
                              "extended_fields": ["read_source"], "source_refs": consume.evidence_refs}


def handoffs_and_dynamic_unknown():
    base = {**INITIAL, "holding_component": "lp_fifo", "read_source": "holding_then_contact",
            "persistent_queue": True}
    statuses, ids = {}, []
    for placement in ("early", "save", "ack", "never"):
        obs = rows({**base, "clear_after": placement})
        handoff = next(o for o in obs if o.type == "RELIABLE_HANDOFF")
        statuses[placement] = handoff.status
        ids.append(handoff.id)
        assert any(o.status == "UNKNOWN" for o in obs)
    assert len(set(ids)) == 1
    assert statuses == {"early": "OPEN", "save": "SATISFIED", "ack": "SATISFIED", "never": "SATISFIED"}
    saved = {**base, "clear_after": "save"}
    prior = rows(saved)
    volatile = {**saved, "persistent_queue": False}
    changed = rows(volatile, previous=prior, previous_design=saved,
                   trigger_diff={"persistent_queue": False})
    handoff = next(o for o in changed if o.type == "RELIABLE_HANDOFF")
    assert handoff.status == "OPEN" and handoff.invalidations
    DETAILS["handoffs"] = {"fixture_static_predicates": statuses,
                            "full_service": "UNKNOWN; not executed"}


def real_partial_chain():
    planner, calls = planner_factory()
    controller = DebtSearch(INITIAL, CONTRACT, design_facts, planner=planner,
                            fixture_mode=True, scope=SCOPE, initial_result=family(INITIAL),
                            validate_fn=static_validate)
    actions = []
    for _ in range(6):
        action = controller.step({"remaining_usd": 0, "offline_fixture": True})
        assert action["status"] == "ACTION", action
        assert action["diagnostic"] and action["diagnostic_question"]
        assert action["conditions"] == SCOPE["conditions"]
        actions.append(deepcopy(action))
        controller.update(family(action["design"], request_id=action["request_id"]))
    stopped = controller.step()
    assert stopped["reason"] == "EVALUATED_DESIGN_CAP" and not stopped["adopted"]
    snap = controller.snapshot()
    partial = [n for n in snap["nodes"] if n["origin"] == "MODEL_JOINT_PROPOSAL"
               and n["design"]["holding_component"] == "lp_fifo"
               and any(o["type"] == "CONSUMPTION" and o["status"] == "OPEN" for o in n["obligations"])]
    assert partial
    selected = {e["node"] for e in snap["transitions"] if e["event"] == "SELECT_RETAIN_PARTIAL"}
    expanded = {e["parent"] for e in snap["transitions"] if e["event"] == "GENERATE_NODE"}
    assert any(p["id"] in selected & expanded for p in partial)
    nodes = {n["id"]: n for n in snap["nodes"]}
    cursor, line = actions[0]["node_id"], []
    while cursor:
        line.append(cursor)
        cursor = nodes[cursor]["parent"]
    assert any(p["id"] in line for p in partial)
    assert actions[0]["design"]["read_source"] == "holding_then_contact"
    assert actions[0]["design"]["persistent_queue"] is True
    assert len(line) >= 3 and snap["evaluations"] == 6 and len(calls) == 6
    assert snap["certificate"]["status"] == "UNKNOWN"
    assert all(c["owner_budget"]["offline_fixture"] for c in calls)
    assert any(e.get("retained_after_zero_service") for e in snap["transitions"])
    snapshot_bytes = len(json.dumps(snap, allow_nan=False, separators=(",", ":")).encode())
    assert snapshot_bytes < 8_000_000, snapshot_bytes
    for saved in snap["nodes"]:
        live = controller.nodes[saved["id"]]
        for compact, original in zip(saved["obligations"], live.obligations):
            assert expand_snapshot_obligation(snap, compact) == original.to_dict()
    DETAILS["real_entry_chain"] = {"nodes": len(nodes), "fact_checks": snap["fact_checks"],
        "logic_expansions": snap["logic_expansions"], "fixture_evaluated_designs": 6,
        "snapshot_canonical_json_bytes": snapshot_bytes,
        "fixture_model_callbacks": len(calls), "first_ancestry": line,
        "first_action": actions[0], "later_action_hashes": [digest(a["design"]) for a in actions[1:]],
        "scientific_result": False, "global_infeasibility_claim": False}
    DETAILS["ledger_first_action"] = deepcopy(actions[0]["design"])


def ablation_changes_action():
    planner, calls = planner_factory()
    ablated = DebtSearch(INITIAL, CONTRACT, design_facts, planner=planner,
                         fixture_mode=True, scope=SCOPE, use_obligations=False,
                         validate_fn=static_validate)
    action = ablated.step()
    assert action["status"] == "ACTION" and len(calls) == 1
    assert action["design"]["holding_component"] == "lp_fifo"
    assert action["design"]["read_source"] == INITIAL["read_source"]
    assert action["design"] != DETAILS["ledger_first_action"]
    DETAILS["ledger_ablation"] = {"changed_actual_action": True, "no_ledger_action": action,
                                 "causal_scope": "One software fixture; no method-effectiveness claim"}


def result_bindings_and_reopen():
    planner, _ = planner_factory()
    c = DebtSearch(INITIAL, CONTRACT, design_facts, planner=planner, fixture_mode=True, scope=SCOPE)
    action = c.step()
    expect_value_error(lambda: c.step(), "UPDATE_PENDING")
    expect_value_error(lambda: c.update(family(INITIAL)), "DESIGN_BINDING")
    bad = family(action["design"]); bad["results"].pop()
    expect_value_error(lambda: c.update(bad), "SAME_CONDITION_FAMILY")
    bad = family(action["design"], request_id="wrong")
    expect_value_error(lambda: c.update(bad), "RESULT_REQUEST_BINDING")
    target = next(o for o in c.nodes[action["node_id"]].obligations
                  if o.status == "SATISFIED" and o.predicate["applicable"] is True)
    result = family(action["design"], request_id=action["request_id"])
    result["predicate_observations"] = [{"obligation_id": target.id, "holds": False,
        "design_sha256": digest(action["design"]), "refs": ["software-fixture-negative-readback"]}]
    update = c.update(result)
    assert any(o["id"] == target.id and o["status"] == "OPEN" for o in update["open_obligations"])
    assert target.id in c.nodes[action["node_id"]].delta["opened"]
    assert not c.stop()["adopted"]


def initial_pass_is_noop():
    def forbidden(_):
        raise AssertionError("PLANNER_CALLED_AFTER_INITIAL_PASS")
    for factory in (
        lambda: DebtSearch(INITIAL, CONTRACT, design_facts, planner=forbidden,
                           initial_result=family(INITIAL, verdict="PASS"), scope=SCOPE),
        lambda: GenericJointAgent(INITIAL, CONTRACT, planner=forbidden,
                                  initial_result=family(INITIAL, verdict="PASS"), scope=SCOPE),
        lambda: MixedJointSearch(INITIAL, CONTRACT,
                                 initial_result=family(INITIAL, verdict="PASS"), scope=SCOPE)):
        c = factory()
        assert c.step()["reason"] == "INITIAL_COMPLETE_SERVICE_PASS"
        assert c.evaluations == 0 and c.model_requests == 0


def usage_blocks_without_retry():
    def unknown(_):
        return {"usage": {"status": "UNKNOWN"}, "payload": {"candidates": []}}
    for c in (DebtSearch(INITIAL, CONTRACT, design_facts, planner=unknown, scope=SCOPE),
              GenericJointAgent(INITIAL, CONTRACT, planner=unknown, scope=SCOPE)):
        assert c.step()["reason"] == "MODEL_CALLBACK_BLOCKED"
        assert c.step()["reason"] == "MODEL_CALLBACK_BLOCKED" and c.model_requests == 1


def generic_joint_and_alternatives():
    calls = []
    def planner(request):
        calls.append(request)
        return {"usage": {"status": "SOFTWARE_FIXTURE"}, "payload": {
            "selected_id": "joint", "candidates": ([
                {"id": "joint", "design_patch": {"capacitance_f": .0002, "retry_s": .2}},
                {"id": "alternative", "design_patch": {"esr_ohm": 1., "startup_v": 2.5}}]
                if len(calls) == 1 else [])}}
    c = GenericJointAgent(INITIAL, CONTRACT, planner, facts_fn=design_facts,
                         fixture_mode=True, scope=SCOPE, validate_fn=static_validate)
    first = c.step({"offline_fixture": True})
    assert len(first["decision"]["actual_input"]["design_patch"]) == 2
    c.update(family(first["design"]))
    assert c.alternatives
    second = c.step()
    assert second["decision"]["selected_id"] == "alternative"
    c.update(family(second["design"]))
    assert len(c.retained) == 2 and calls[0]["owner_budget"]["offline_fixture"]
    json.dumps(c.snapshot(), allow_nan=False)


def mixed_seed_joint_restart_retention():
    runs = []
    for _ in range(2):
        c, actions = MixedJointSearch(INITIAL, CONTRACT, seed=20261024, scope=SCOPE,
                                     validate_fn=static_validate), []
        for index in range(6):
            action = c.step()
            assert action["status"] == "ACTION"
            assert len(action["decision"]["actual_input"]["design_patch"]) >= 2
            assert ("RESTART" in action["decision"]["selection_basis"]) == (index % 2 == 0)
            actions.append(action)
            c.update(family(action["design"]))
        assert len(c.retained) == 6 and c.step()["reason"] == "EVALUATED_DESIGN_CAP"
        runs.append(actions)
    assert runs[0] == runs[1]
    DETAILS["mixed"] = {"seed": 20261024, "fixture_design_hashes": [digest(a["design"]) for a in runs[0]]}


def exact_fixture_certificates():
    scope = {"mode": {"mode": "old"}, "domain": {"x": {"min": 0, "max": 1}},
             "conditions": ["fixture"], "service_sha256": "fixture-service",
             "source_sha256": "fixture-axiom-source", "assumptions": ["Software interval axiom only"]}
    fact = {"id": "fixture-necessary-axiom", "variable": "x", "lower": 2,
            "scope_sha256": digest(scope), "necessary": True,
            "evidence_refs": ["software-fixture-axiom"], "derivation": "Fixture axiom x >= 2"}
    def validator(row, bound_scope):
        return bound_scope == scope and row == fact
    assert build_certificate(scope, [fact])["status"] == "UNKNOWN"
    cert = build_certificate(scope, [fact], verify_fact=validator)
    assert cert["status"] == "CERTIFIED_EMPTY" and verify_certificate(cert, verify_fact=validator)
    assert covers_design(cert, {"mode": "old", "x": .5}, conditions=["fixture"])
    assert not covers_design(cert, {"mode": "new", "x": .5}, conditions=["fixture"])
    assert not covers_design(cert, {"mode": "old", "x": .5}, conditions=["other"])
    tampered = deepcopy(cert); tampered["scope"]["source_sha256"] = "stale"
    assert not verify_certificate(tampered, verify_fact=validator)
    bad = {**fact, "necessary": False}
    assert build_certificate(scope, [bad], verify_fact=lambda *args: True)["status"] == "UNKNOWN"
    malformed = {**fact, "lower": 2, "upper": 3, "upper_strict": "bad"}
    assert build_certificate(scope, [malformed], verify_fact=lambda *args: True)["status"] == "UNKNOWN"
    contract = {"design_domain": {"mode": {"kind": "enum", "values": ["old", "new"]},
                                  "x": {"kind": "number", "min": 0, "max": 1}}}
    initial = {"mode": "old", "x": 0}
    def facts(design):
        return {"design_sha256": digest(design), "predicates": [{"id": "fixture-need-dynamic",
            "type": "FIXTURE_UNKNOWN", "holds": None, "refs": ["software-fixture"],
            "dependencies": ["mode", "x"]}]}
    c = DebtSearch(initial, contract, facts, scope={"conditions": ["fixture"]},
                   certificate_scope=scope, certificate_facts=[fact], certificate_checker=validator)
    action = c.step()
    assert action["status"] == "ACTION" and action["design"]["mode"] == "new"
    assert any(e["event"] == "CERTIFICATE_PRUNE" for e in c.transitions)
    DETAILS["certificate"] = {"software_axiom_only": True, "status": cert["status"],
                               "actual_prune_count": sum(e["event"] == "CERTIFICATE_PRUNE" for e in c.transitions),
                               "alternative_mode_action": action}


def domain_authority():
    restricted = DomainSpace(CONTRACT, INITIAL, active_variables=["retry_s"])
    expect_value_error(lambda: restricted.apply(INITIAL, {"holding_component": "lp_fifo"}), "AUTHORIZED_DOMAIN")
    expect_value_error(lambda: restricted.validate({**INITIAL, "holding_capacity": 1.1}), "INTEGER")
    seen = []
    def public_validator(design):
        seen.append(digest(design))
        if design["retry_s"] == .2:
            raise ValueError("FIXTURE_COMMON_RELATIONAL_CONSTRAINT")
    for c in (DebtSearch(INITIAL, CONTRACT, design_facts, validate_fn=public_validator),
              GenericJointAgent(INITIAL, CONTRACT, planner=None, validate_fn=public_validator),
              MixedJointSearch(INITIAL, CONTRACT, validate_fn=public_validator)):
        expect_value_error(lambda: c.space.apply(INITIAL, {"retry_s": .2}), "RELATIONAL_CONSTRAINT")
    assert len(seen) >= 6


def main():
    previous = sys.getprofile()
    sys.setprofile(no_science)
    try:
        for name, function in (
            ("stable_consumption_activation_dependency_invalidation", consumption_and_identity),
            ("SAVE_ACK_never_early_and_dynamic_UNKNOWN", handoffs_and_dynamic_unknown),
            ("real_step_partial_retention_extension_six_fixture_updates", real_partial_chain),
            ("removing_ledger_changes_actual_next_action", ablation_changes_action),
            ("result_identity_scope_and_negative_predicate_reopen", result_bindings_and_reopen),
            ("initial_PASS_stops_three_controllers_without_calls", initial_pass_is_noop),
            ("UNKNOWN_usage_stops_both_model_controllers_without_retry", usage_blocks_without_retry),
            ("generic_joint_edit_retains_executable_alternative", generic_joint_and_alternatives),
            ("mixed_frozen_seed_joint_mutation_restart_retention", mixed_seed_joint_restart_retention),
            ("exact_axiom_certificate_checked_and_used_in_real_step", exact_fixture_certificates),
            ("common_domain_does_not_expand_task_authority", domain_authority)):
            check(name, function)
    finally:
        sys.setprofile(previous)
    report = {"schema": "codebt-b-offline-checks-v1", "scientific_result": False,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "checks": CHECKS, "details": DETAILS,
              "guard_blocked_calls": BLOCKED,
              "provider_calls": 0, "full_consumer_calls": 0, "new_numerical_boundary_calls": 0,
              "passed": sum(c["status"] == "PASS" for c in CHECKS),
              "failed": sum(c["status"] != "PASS" for c in CHECKS)}
    attempts = sorted(HERE.glob("logic-checks-attempt-*.json"))
    path = HERE / ("logic-checks-attempt-%02d.json" % (len(attempts) + 1))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"report": str(path), "passed": report["passed"], "failed": report["failed"],
                      "failures": [c for c in CHECKS if c["status"] != "PASS"]}, ensure_ascii=False))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
