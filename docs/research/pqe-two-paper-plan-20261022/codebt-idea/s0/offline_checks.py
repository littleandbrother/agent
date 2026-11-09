"""Direct new-consumer/new-controller logic checks, with hard solver guards.

The family feedback is an explicitly labelled software fixture. It does not
estimate the new task's service, energy feasibility, fitness valley or benefit.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

from run import FamilyBroker, FinitePlanner, HERE, digest, save, require_scientific_admission
from bfworld.agentlab.pqe20261024debt import adapter, consumer, facts, holding, task
from bfworld.agentlab.pqe20261024debt.obligations import derive_obligations
from bfworld.agentlab.pqe20261024debt.search import DebtSearch
from bfworld.agentlab.pqe20261024debt.baselines import GenericJointAgent, MixedJointSearch


@contextmanager
def no_science():
    blocked = []
    previous = sys.getprofile()

    def guard(frame, event, arg):
        if event != "call":
            return
        filename, name = frame.f_code.co_filename, frame.f_code.co_name
        if ("bfworld/agentlab" in filename and
                (name in {"source_step", "_midpoint_step", "_execute_enabled", "paid_callback"}
                 or name == "execute_design")):
            blocked.append(filename+":"+name)
            raise AssertionError("SCIENTIFIC_OR_PROVIDER_ENTRY_FORBIDDEN:"+blocked[-1])
    sys.setprofile(guard)
    try:
        yield blocked
    finally:
        sys.setprofile(previous)


def fixture_raw(t, design, **unused):
    return {"execution_status": "COMPLETE", "model_valid": True, "domain_errors": [],
            "program_version": "SOFTWARE_FIXTURE_ONLY", "engineering_model_sha256": "fixture-no-model",
            "trace": [], "activity": [], "records": [], "packets": [], "energy": {},
            "peak_handle_force_n": 0., "minimum_tx_terminal_v": None, "program_state": {},
            "result_sha256": "fixture-"+digest({"task": t["task_id"], "design": design})}


def fixture_assessment(t, design, raw):
    return {"verdict": "FAIL", "failures": ["SOFTWARE_FIXTURE_NO_PHYSICAL_VERDICT"],
            "unknown": [], "receiver_records": []}


def fixture_member(t, design, action):
    public, captured = adapter.bind_consumer(fixture_raw, fixture_assessment)(
        t, action["base_design"], t["initial_problem"], action["decision"],
        task_resolver=lambda ident: next(x for x in task.make_task_family() if x["task_id"] == ident))
    if public["design"] != design or "raw" not in captured:
        raise AssertionError("HOST_ACTUAL_INPUT_DID_NOT_REACH_RAW_FIXTURE")
    public["scientific_result"] = False
    public["fixture_kind"] = "No numeric consumer; all feedback is synthetic FAIL."
    return public


def failed_initial(family):
    design = deepcopy(family[0]["initial_design"])
    return {"design": design, "scientific_result": False,
            "results": [{"condition_id": t["condition_id"], "task_id": t["task_id"],
                "design": deepcopy(design), "execution_status": "COMPLETE", "model_valid": True,
                "public_check": {"verdict": "FAIL"}, "result_sha256": "fixture-initial-"+t["condition_id"]}
                for t in family]}


def holder_program_chain():
    h = holding.EventHolding()
    h.prepare(.5, 1)
    h.advance(.1, .5)
    assert not h.records and h.current_a == 0
    h.prepare(2.5, 1)
    h.advance(holding.PROFILE["debounce_s"], 2.5)
    h.prepare(2.5, 1)
    assert h.current_a > holding.PROFILE["monitor_a"]
    h.advance(holding.PROFILE["capture_s"], 2.5)
    d = {**deepcopy(task.DEFAULT_DESIGN), "holding_component": "lp_fifo",
         "read_source": "holding_then_contact", "clear_after": "save", "persistent_queue": True}
    p = consumer.HoldingDoorProgram(d, task.COMPONENTS, h)
    p.begin_step(2.5, 1)
    p.advance(task.COMPONENTS["boot_s"], 2.5)
    p.begin_step(2.5, 1)
    assert p.mode == "HREAD"
    p.advance(holding.PROFILE["read_s"], 2.5)
    p.advance(task.COMPONENTS["write_s"], 2.5)
    assert p.mode == "HCLEAR" and len(p.nvm["queue"]) == 1 and h.peek() is not None
    p.advance(holding.PROFILE["clear_s"], 2.5)
    assert h.peek() is None
    p.reset("SYNTHETIC_MCU_RESET")
    assert len(p.remaining_queue) == 1
    p.begin_step(2.5, 1)
    p.advance(task.COMPONENTS["boot_s"], 2.5)
    assert len(p.queue) == 1 and p.nvm["seq"] == 1
    return {"design": d, "holder_events": h.drain_events(), "program_events": p.drain_events(),
            "final_nvm": deepcopy(p.nvm), "load_definition": deepcopy(holding.PROFILE),
            "energy_feasibility": "UNKNOWN; manual state transitions, no supply solver"}


def run_checks():
    checks, failures = [], []
    ledger = {"schema": "codebt-offline-direct-chain-v1", "scientific_result": False}
    family = task.make_task_family()
    contract = facts.describe_contract()
    conditions = [t["condition_id"] for t in family]
    scope = {"family_id": task.FAMILY_ID, "conditions": conditions,
             "task_sha256": [digest(t) for t in family], "offline_fixture": True}

    def check(name, function):
        try:
            function()
            checks.append({"name": name, "status": "PASS"})
        except Exception as exc:
            checks.append({"name": name, "status": "FAIL", "error": type(exc).__name__+":"+str(exc)})
            failures.append(name)

    with no_science() as blocked:
        def check_holder():
            ledger["actual_component_state_machine"] = holder_program_chain()
        check("powered_capture_paid_read_SAVE_clear_reset_state_chain", check_holder)

        def check_handoffs():
            d = deepcopy(ledger["actual_component_state_machine"]["design"])
            rows = {}
            for placement in ("save", "ack", "early"):
                d["clear_after"] = placement
                obs = derive_obligations(d, facts.design_facts(d, family[0]), scope=scope)
                rows[placement] = [o.to_dict() for o in obs]
                handoff = [o for o in obs if o.type == "RELIABLE_HANDOFF"]
                assert handoff and all(o.status == ("OPEN" if placement == "early" else "SATISFIED") for o in handoff)
                assert any(o.status == "UNKNOWN" for o in obs)
            ledger["independent_handoff_predicates"] = rows
        check("SAVE_and_ACK_both_reliable_early_clear_remains_open_dynamic_unknown", check_handoffs)

        def check_invalidation():
            before = deepcopy(ledger["actual_component_state_machine"]["design"])
            prior = derive_obligations(before, facts.design_facts(before), scope=scope)
            after = {**before, "persistent_queue": False}
            rows = derive_obligations(after, facts.design_facts(after), scope=scope,
                previous=prior, previous_design=before, trigger_diff={"persistent_queue": False})
            assert any(o.invalidations for o in rows)
            assert any(o.type == "RELIABLE_HANDOFF" and o.status == "OPEN" for o in rows)
            ledger["dependency_invalidation"] = [o.to_dict() for o in rows if o.invalidations]
        check("changed_storage_invalidates_prior_closure", check_invalidation)

        def check_task_permissions():
            t = deepcopy(family[0])
            problem = deepcopy(t["initial_problem"])
            problem["active_variables"] = ["retry_s"]
            problem["groups"] = [["retry_s"]]
            try:
                adapter.prepare(t, t["initial_design"], problem,
                    {"actual_input": {"operation": "edit", "design_patch": {"holding_component": "lp_fifo"}}},
                    task_resolver=lambda ident: t)
            except ValueError as exc:
                assert str(exc) == "EDIT_OUTSIDE_ACTIVE_VARIABLES"
            else:
                raise AssertionError("Model domain silently expanded task authority")
        check("model_field_does_not_expand_task_permission", check_task_permissions)

        broker = FamilyBroker(family, fixture_member, offline=True, sources=adapter.source_identity())

        def check_debt_chain():
            callbacks = []
            def planner(request):
                callbacks.append(deepcopy(request))
                # Deliberately incomplete hardware-only proposal. Completion is
                # selected by the actual controller from public counterfactuals.
                candidates = ([{"id": "fixture-incomplete", "design_patch": {"holding_component": "lp_fifo"}}]
                              if len(callbacks) == 1 else [])
                return {"usage": {"status": "SOFTWARE_FIXTURE"}, "payload": {"candidates": candidates}}
            controller = DebtSearch(family[0]["initial_design"], contract,
                lambda d: facts.design_facts(d, family[0]), planner=planner,
                scope=scope, initial_result=failed_initial(family), fixture_mode=True,
                validate_fn=lambda d: task.validate_design(family[0], d))
            actions, updates = [], []
            try:
                for _ in range(6):
                    action = controller.step()
                    if action["status"] != "ACTION":
                        break
                    actions.append(deepcopy(action))
                    result = broker.evaluate("debt_agent", action)
                    updates.append(controller.update(result))
            finally:
                snapshot = controller.snapshot()
                ledger["debt_controller"] = snapshot
                ledger["debt_actions"] = actions
                ledger["debt_updates"] = updates
            retained = {e["node"] for e in snapshot["transitions"] if e["event"] == "SELECT_RETAIN_PARTIAL"}
            expanded = {e["parent"] for e in snapshot["transitions"] if e["event"] == "GENERATE_NODE"}
            incomplete = [n for n in snapshot["nodes"] if n["origin"] == "MODEL_JOINT_PROPOSAL"
                          and n["pending_diff"].get("holding_component") == "lp_fifo"
                          and any(o["type"] == "CONSUMPTION" and o["status"] == "OPEN" for o in n["obligations"])]
            assert incomplete, "Hardware proposal did not produce a factual read obligation"
            assert any(n["id"] in retained and n["id"] in expanded for n in incomplete), "Open partial was retained but never actually extended"
            ancestors = {n["id"]: n for n in snapshot["nodes"]}
            linked = []
            for action in actions:
                line, cursor = [], action["node_id"]
                while cursor:
                    line.append(cursor)
                    cursor = ancestors[cursor]["parent"]
                if any(n["id"] in line for n in incomplete):
                    linked.append({"evaluated_node": action["node_id"], "ancestors": line,
                                   "actual_input": action["decision"]["actual_input"]})
            ledger["modified_obligation_extension_evaluation_chains"] = linked
            assert linked, "No actual full-fixture action descended from the incomplete hardware proposal"
            assert snapshot["evaluations"] == len(actions) and actions
            assert any(e.get("retained_after_zero_service") for e in snapshot["transitions"])
            assert snapshot["certificate"]["status"] == "UNKNOWN"
        check("actual_partial_relation_changes_extension_then_host_feedback_update", check_debt_chain)

        def check_controls():
            d = deepcopy(family[0]["initial_design"])
            def planner(request):
                return {"usage": {"status": "SOFTWARE_FIXTURE"}, "payload": {"selected_id": "joint",
                    "candidates": [{"id": "joint", "design_patch": {"persistent_queue": True, "retry_s": .2}},
                                   {"id": "alternative", "design_patch": {"capacitance_f": .0002, "esr_ohm": 1.}}]}}
            generic = GenericJointAgent(d, contract, planner=planner,
                facts_fn=lambda d0: facts.design_facts(d0, family[0]), fixture_mode=True,
                scope=scope, initial_result=failed_initial(family),
                validate_fn=lambda d0: task.validate_design(family[0], d0))
            action = generic.step()
            assert len(action["decision"]["actual_input"]["design_patch"]) == 2
            generic.update(broker.evaluate("generic_agent", action))
            assert generic.snapshot()["evaluations"] == 1 and generic.alternatives
            mixed = MixedJointSearch(d, contract, scope=scope, initial_result=failed_initial(family),
                validate_fn=lambda d0: task.validate_design(family[0], d0))
            first = mixed.step()
            assert len(first["decision"]["actual_input"]["design_patch"]) >= 2
            # Mixed proposals can violate cross-field facts; the real host
            # validates them. This check uses no consumer and no repair sweep.
            ledger["control_interface"] = {"generic": generic.snapshot(), "mixed_first": first,
                                           "mixed_snapshot": mixed.snapshot()}
        check("strong_control_joint_edit_alternatives_mixed_restart", check_controls)

        def check_shared_family_cache():
            sample = ledger["control_interface"]["generic"]["history"][0]["request"]
            before = broker.fixture_inputs
            result = broker.evaluate("fixture_cache_readback", sample)
            assert all(row["reused"] for row in result["results"])
            assert broker.fixture_inputs == before and len(broker.by_group["fixture_cache_readback"]) == 1
            assert result["scientific_result"] is False and result["usage"]["full_inputs"] == 0
        check("cache_counts_candidate_slot_same_three_conditions_zero_science", check_shared_family_cache)

        def check_callback_caps():
            budget = {"requests_used": 0, "output_tokens_used": 131065, "spent_usd": 0.,
                      "remaining_wall_s": 100., "tool_calls_used": 0}
            bodies = []
            def callback(body):
                bodies.append(deepcopy(body))
                budget["requests_used"] += 1
                budget["output_tokens_used"] += 7
                return {"usage": {"status": "SOFTWARE_FIXTURE", "output_tokens": 7},
                        "payload": {"candidates": []}}
            planner = FinitePlanner(callback, lambda: deepcopy(budget),
                                    model_identity="fixture-only", offline=True)
            planner({"max_output_tokens": 999999, "site": "H-GEN"})
            assert bodies[0]["max_output_tokens"] == 7
            try:
                planner({"site": "H-GEN"})
            except RuntimeError as exc:
                assert str(exc) == "NEW_EPISODE_OUTPUT_EXHAUSTED"
            else:
                raise AssertionError("Spent output quota reached callback")
            assert len(bodies) == 1
            unknown_calls = []
            def unknown(body):
                unknown_calls.append(body)
                return {"usage": {"status": "UNKNOWN"}, "payload": {}}
            pending = FinitePlanner(unknown, lambda: {**budget, "output_tokens_used": 0},
                                    model_identity="fixture-only", offline=True)
            for _ in range(2):
                try:
                    pending({"site": "H-GEN"})
                except RuntimeError as exc:
                    assert str(exc) == "PROVIDER_USAGE_NOT_SETTLED"
                else:
                    raise AssertionError("Missing usage was accepted")
            assert len(unknown_calls) == 1
            ledger["callback_cap_propagation"] = {"capped_calls": planner.calls,
                "unknown_halt": pending.calls, "software_fixture_callbacks": 2,
                "provider_requests": 0}
        check("actual_callback_input_remaining_output_unknown_stops_no_retry", check_callback_caps)

        def check_gate():
            try:
                require_scientific_admission()
            except RuntimeError as exc:
                assert str(exc).startswith("CODEBT_SCIENCE_NOT_ADMITTED:")
            else:
                raise AssertionError("Offline-only package silently admitted science")
        check("live_missing_usage_gate_refuses_science", check_gate)

        ledger["broker_events"] = broker.events
        ledger["blocked_scientific_entries"] = list(blocked)
        assert not blocked
    ledger["checks"] = checks
    save(HERE / "offline-direct-chain.json", ledger)
    return {"schema": "codebt-offline-readback-v1", "status": "PASS" if not failures else "FAIL",
            "logic_checks": len(checks), "failed_checks": failures, "checks": checks,
            "fixture_family_inputs": broker.fixture_inputs,
            "software_planner_callbacks": (ledger.get("debt_controller", {}).get("model_callbacks", 0)
                + ledger.get("control_interface", {}).get("generic", {}).get("model_callbacks", 0)
                + ledger.get("callback_cap_propagation", {}).get("software_fixture_callbacks", 0)),
            "new_full_scientific_inputs": 0, "cheap_numerical_checks": 0, "provider_requests": 0,
            "scientific_result": False, "full_consumer_energy_closure": "UNKNOWN",
            "service_and_relative_method_benefit": "NOT_TESTED",
            "evidence": str(HERE / "offline-direct-chain.json"),
            "claim": "Actual new component state transitions and controller/host software logic only; family feedback is a FAIL fixture, not a new scientific simulation."}
