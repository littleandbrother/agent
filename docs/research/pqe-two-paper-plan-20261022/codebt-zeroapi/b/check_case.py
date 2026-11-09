"""Seven bounded software cases; saved public evidence, no scientific solve.

Each requested case consumes one of B's seven attempts before executing. This
does not run the old suite or a model. Rebound feedback is explicitly synthetic.
"""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

from bfworld.agentlab.pqe20261024debt import facts, task
from bfworld.agentlab.pqe20261024debt.search import DebtSearch, family_result
from bfworld.agentlab.pqe20261024debt.baselines import GenericJointAgent, MixedJointSearch
from bfworld.agentlab.pqe20261024debt.obligations import digest, derive_obligations

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
OLD = HERE.parents[1] / "codebt-idea/s0"
NEW = HERE.parent
bridge_path = NEW / "s0/public_predicates.py"
spec = importlib.util.spec_from_file_location("codebt_shared_public_predicates", bridge_path)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
CONTRACT = facts.describe_contract()
INITIAL = deepcopy(CONTRACT["defaults"])
PUBLIC_FILES = sorted((OLD / "science").glob("0[123]-initial-*/result/public-result.json.gz"))
PUBLIC = [json.loads(gzip.decompress(p.read_bytes())) for p in PUBLIC_FILES]
CONDITIONS = [p["condition_id"] for p in PUBLIC]
SCOPE = {"conditions": CONDITIONS, "package": "BF-PQE-CODEBT-ZEROAPI-CHECK-20261024-001"}
original_input = json.loads((PUBLIC_FILES[0].parents[1] / "input.json").read_text())
TASK = original_input["task"]
DETAILS = {}
ACTIVE = [key for key in CONTRACT["design_domain"] if key != "mechanism"]
COUNTERS = {"cheap_numeric": 0, "static_geometry_calls": 0}


def guard(frame, event, arg):
    if event == "call" and "bfworld/agentlab" in frame.f_code.co_filename:
        name = frame.f_code.co_name
        if name in {"execute_design", "_midpoint_step", "_execute_enabled", "paid_callback"}:
            raise AssertionError("FORBIDDEN_SCIENTIFIC_OR_PROVIDER_ENTRY:" + name)
        if name == "source_step":
            caller = frame.f_back
            assert caller and caller.f_code.co_name == "static_geometry_facts", "Dynamic source call forbidden"
            assert (frame.f_locals.get("theta_deg"), frame.f_locals.get("omega_deg_s"),
                    frame.f_locals.get("v_bus_v")) == (0., 0., 0.)
            COUNTERS["cheap_numeric"] += 1
            assert COUNTERS["cheap_numeric"] <= 3, "B_SHARED_CHEAP_REMAINDER_EXHAUSTED"
        if name == "static_geometry_facts":COUNTERS["static_geometry_calls"] += 1


def validate(design):
    task.validate_design(TASK, design)


def requirement_data():
    path = NEW / "shared/public-observation-contract.json"
    contract = json.loads(path.read_text())
    # The test consumes S0's explicit public declaration, never evaluator truth.
    requirements = contract.get("expected_requirements", contract.get("requirements"))
    if isinstance(requirements, list):
        requirements = {r["condition_id"]: r for r in requirements}
    assert isinstance(requirements, dict), contract
    requirements = deepcopy(requirements)
    for cid, value in requirements.items():
        value["ref"] = {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "pointer": "/requirements/" + cid}
    return requirements


def saved_family():
    raw = {"design": deepcopy(INITIAL), "results": deepcopy(PUBLIC)}
    refs = {r["condition_id"]: {"path": str(p.relative_to(ROOT)),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p, r in zip(PUBLIC_FILES, PUBLIC)}
    return bridge.attach_family_result(raw, refs, requirement_data())


def controller(initial_result=None):
    return DebtSearch(INITIAL, CONTRACT, facts.design_facts, initial_result=initial_result,
                      scope=SCOPE, validate_fn=validate, planner=None, active_variables=ACTIVE)


def public_rows(node):
    return [o for o in node.obligations if o.type.startswith("PUBLIC_")]


def fixture_feedback(action, *, deficit=False):
    # New values represent a software scenario, not replayed physical results.
    results = []
    for cid in CONDITIONS:
        activity, records = [], []
        count = 4 if deficit else 6
        for i in range(count):
            direction = 1 - i % 2
            record = {"seq": i + 1, "direction": direction}
            activity += [{"action": "capture", "direction": direction},
                         {"action": "save_commit", "record": record}]
            records.append(record)
        results.append({"condition_id": cid, "design": deepcopy(action["design"]),
            "execution_status": "COMPLETE", "model_valid": True,
            "public_check": {"verdict": "FAIL"},
            "result_sha256": "software-fixture-" + digest([cid, action["design"], deficit]),
            "facts": {"activity": activity, "records": records, "packets": []},
            "scientific_result": False})
    raw = {"design": deepcopy(action["design"]), "request_id": action["request_id"],
           "results": results, "scientific_result": False}
    refs = {r["condition_id"]: {"software_fixture": True, "object_sha256": digest(r)} for r in results}
    return bridge.attach_family_result(raw, refs, requirement_data())


def case1():
    """Original public identity loss selects a minimal real controller action."""
    result = saved_family()
    c = controller(result)
    initial = public_rows(c.nodes[c.root_id])
    assert [o.status for o in initial if o.type == "PUBLIC_CAPTURE_COVERAGE"] == ["SATISFIED"] * 3
    identities = [o.status for o in initial if o.type == "PUBLIC_SEQUENCE_IDENTITY"]
    assert identities.count("OPEN") == 2 and identities.count("SATISFIED") == 1, identities
    action = c.step()
    assert action["status"] == "ACTION" and action["diagnostic"]
    assert action["decision"]["actual_input"]["design_patch"] == {"persistent_queue": True}, action
    assert action["design"]["holding_component"] == "off" and c.model_requests == 0
    candidate = c.nodes[action["node_id"]]
    assert all(o.status == "UNKNOWN" for o in public_rows(candidate)), "Parent result leaked into unexecuted child"
    assert len(action["decision"]["selection_basis"]["public_experiments"]) == 2
    DETAILS.update(original_public_predicates=[o.to_dict() for o in initial],
                   action=action, counters={"fact_checks": c.fact_checks, "nodes": len(c.nodes)},
                   attribution="Public complete capture counts plus capture-to-SAVE seq reuse; no delivered-count rule.")
    # Consume A's already saved P1 public results, never its private assessment.
    files = sorted((NEW / "a").glob("0[123]-P1-*/result/public-result.json"))
    p1 = [json.loads(p.read_text()) for p in files]
    condition_by_task = {row["task_id"]: row["condition_id"] for row in PUBLIC}
    for member in p1:
        # Family metadata is derived from the same public task binding; the
        # original saved files are neither edited nor assigned a new outcome.
        member["condition_id"] = condition_by_task[member["task_id"]]
    assert len(p1) == 3 and all(row["design"] == action["design"] for row in p1)
    refs = {row["condition_id"]: {"path": str(p.relative_to(ROOT)),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p, row in zip(files, p1)}
    result = bridge.attach_family_result({"design": action["design"], "request_id": action["request_id"],
                                         "results": p1}, refs, requirement_data())
    update = c.update(result)
    assert update["service"]["all_pass"] and c.step()["reason"] == "COMPLETE_SERVICE_PASS"
    assert all(o.status == "SATISFIED" for o in public_rows(c.nodes[action["node_id"]]))
    DETAILS.update(saved_P1_update=update, new_scientific_execution=False)


def case2():
    """Actual Update changes the next causal trial to a capture investigation."""
    c = controller(saved_family())
    first = c.step()
    result = fixture_feedback(first, deficit=True)
    update = c.update(result)
    current = public_rows(c.nodes[first["node_id"]])
    assert all(o.status == "OPEN" for o in current if o.type == "PUBLIC_CAPTURE_COVERAGE")
    assert all(o.status == "SATISFIED" for o in current if o.type == "PUBLIC_SEQUENCE_IDENTITY")
    second = c.step()
    assert second["status"] == "ACTION" and second["diagnostic"]
    target_ids = set(second["decision"]["selection_basis"]["public_experiments"])
    capture_ids = {o.id for o in current if o.type == "PUBLIC_CAPTURE_COVERAGE"}
    assert target_ids and target_ids <= capture_ids
    assert second["design"]["holding_component"] == "off", "Capture deficit forced holder"
    assert len(second["decision"]["actual_input"]["design_patch"]) == 1
    DETAILS.update(first_action=first, synthetic_update=update, second_action=second,
                   scientific_result=False, scope="Software feedback reopens a capture question; no physical outcome claimed.")


def case3():
    """Missing fields, invalid domain and unfinished tools remain UNKNOWN."""
    raw = {"design": deepcopy(INITIAL), "results": deepcopy(PUBLIC)}
    raw["results"][0]["facts"].pop("activity")
    raw["results"][1].update(model_valid=False, domain_errors=["fixture-domain-error"])
    raw["results"][2]["execution_status"] = "TOOL_ERROR"
    refs = {cid: {"software_fixture": True} for cid in CONDITIONS}
    result = bridge.attach_family_result(raw, refs, requirement_data())
    # Even a forged boolean cannot turn incomplete/invalid execution into a gap.
    for row in result["predicate_observations"]:
        if row["condition_id"] in CONDITIONS[1:]:row["holds"] = False
    for member in result["results"][1:]:
        for row in member["predicate_observations"]:row["holds"] = False
    c = controller(result)
    obs = public_rows(c.nodes[c.root_id])
    assert len(obs) == 6 and all(o.status == "UNKNOWN" for o in obs)
    action = c.step()
    assert action["status"] in {"ACTION", "STOPPED"}
    if action["status"] == "ACTION":
        assert action["decision"]["selection_basis"]["public_experiments"] == []
    DETAILS.update(obligations=[o.to_dict() for o in obs], action=action)


def case4():
    """Both controllers stop the same saved format failure without a provider."""
    saved = json.loads((OLD / "episodes/debt_agent/callbacks/02/callback-result.json").read_text())
    calls = []
    def callback(request):
        calls.append(request["condition"])
        return {"payload": deepcopy(saved["payload"]), "usage": {"status": "SOFTWARE_FIXTURE"}}
    d = DebtSearch(INITIAL, CONTRACT, facts.design_facts, planner=callback,
                   fixture_mode=True, scope=SCOPE, validate_fn=validate)
    g = GenericJointAgent(INITIAL, CONTRACT, callback, fixture_mode=True,
                          scope=SCOPE, validate_fn=validate, facts_fn=facts.design_facts)
    stops = [d.step(), g.step()]
    assert [r["reason"] for r in stops] == ["MODEL_FORMAT_ERROR"] * 2
    assert d.model_requests == g.model_requests == 1 and len(calls) == 2
    assert not d.pending and not g.pending
    DETAILS.update(stops=stops, saved_payload_status=saved["payload"].get("status"),
                   callback_kind="Pure saved-payload software callback; provider/model episode count zero")


def case5():
    """Hardware responsibilities and nonunique handoffs remain explicit."""
    base = {**INITIAL, "holding_component": "lp_fifo"}
    obs = derive_obligations(base, facts.design_facts(base), scope=SCOPE,
                             trigger_diff={"holding_component": "lp_fifo"})
    assert any(o.type == "CONSUMPTION" and o.status == "OPEN" for o in obs)
    assert any(o.type == "RESET_IDENTITY" and o.status == "OPEN" for o in obs)
    statuses = {}
    for placement in ("early", "save", "ack", "never"):
        design = {**base, "read_source": "holding_then_contact", "persistent_queue": True,
                  "clear_after": placement}
        rows = derive_obligations(design, facts.design_facts(design), scope=SCOPE)
        statuses[placement] = next(o.status for o in rows if o.type == "RELIABLE_HANDOFF")
        assert any(o.type == "PAID_LOAD" for o in rows) and any(o.status == "UNKNOWN" for o in rows)
    assert statuses == {"early": "OPEN", "save": "SATISFIED", "ack": "SATISFIED", "never": "SATISFIED"}
    c = controller(saved_family());action = c.step()
    events = [e for e in c.transitions if e["event"].startswith("SELECT_RETAIN")]
    assert events and all(e["selection_basis"]["opened_and_self_closure_are_not_progress"] for e in events)
    assert action["design"]["holding_component"] == "off"
    DETAILS.update(new_responsibilities=[o.to_dict() for o in obs], handoffs=statuses,
                   selected_without_self_reward=action)


def case6():
    """All three controls consume A's same-source static domain prefilter."""
    path = OLD / "science/06-mixed_joint-scheduler-fixed-short-cold/result/public-result.json.gz"
    bad = json.loads(gzip.decompress(path.read_bytes()))["design"]
    p1 = {**INITIAL, "persistent_queue": True}
    p2 = {**p1, "holding_component": "lp_fifo", "read_source": "holding_then_contact"}
    errors = []
    for c in (controller(), GenericJointAgent(INITIAL, CONTRACT, planner=None,
                  scope=SCOPE, validate_fn=validate),
              MixedJointSearch(INITIAL, CONTRACT, scope=SCOPE, validate_fn=validate)):
        for design in (INITIAL, p1, p2):c.space.validate(design)
        try:c.space.validate(bad)
        except ValueError as exc:errors.append(str(exc))
        else:raise AssertionError("Old mixed envelope violation admitted")
    assert len(set(errors)) == 1 and "assembly_envelope_exceeded" in errors[0], errors
    DETAILS.update(common_error=errors[0], original_bad_ref=str(path.relative_to(ROOT)),
                   validators="A.task.validate_design identical callable; formula/domain not copied or changed")


def case7():
    """Repeated wire attempts alone and stale result bindings do not imply loss."""
    action = {"design": deepcopy(INITIAL), "request_id": "fixture-retransmit"}
    raw = fixture_feedback(action)
    for member in raw["results"]:
        member["facts"]["packets"] = [{"hex": "same-retransmitted-frame"}] * 30
    refs = {cid: {"software_fixture": True} for cid in CONDITIONS}
    result = bridge.attach_family_result(raw, refs, requirement_data())
    assert all(row["holds"] is True for row in result["predicate_observations"])
    for row in result["predicate_observations"]:row["result_sha256"] = "stale-result"
    for member in result["results"]:
        for row in member["predicate_observations"]:row["design_sha256"] = "stale-design"
    summary = family_result(result, INITIAL, CONDITIONS)
    assert summary["observations"] == []
    c = controller(result)
    assert not public_rows(c.nodes[c.root_id])
    DETAILS.update(stale_observations_rejected=True, retransmissions_are_not_new_captures=True)


def run_case(case):
    assert 1 <= case <= 7
    usage_path = HERE / "case-budget.json"
    usage = json.loads(usage_path.read_text()) if usage_path.exists() else {"cap": 7, "attempts": []}
    assert len(usage["attempts"]) < usage["cap"], "B_SOFTWARE_CASE_CAP"
    assert not any(row["case"] == case for row in usage["attempts"]), "CASE_ALREADY_EXECUTED"
    row = {"case": case, "started_at": datetime.now(timezone.utc).isoformat(), "status": "RUNNING"}
    usage["attempts"].append(row);usage_path.write_text(json.dumps(usage,indent=2)+'\n')
    previous = sys.getprofile();sys.setprofile(guard)
    before = deepcopy(COUNTERS)
    DETAILS.clear()
    try:
        globals()["case" + str(case)]()
        row["status"] = "PASS"
    except Exception as exc:
        row.update(status="FAIL", error=type(exc).__name__ + ":" + str(exc),
                   traceback=traceback.format_exc(limit=5))
    finally:sys.setprofile(previous)
    row.update(completed_at=datetime.now(timezone.utc).isoformat(), details=DETAILS,
               scientific_result=False, provider_calls=0, model_episodes=0,
               full_inputs=0, cheap_numeric=COUNTERS["cheap_numeric"] - before["cheap_numeric"],
               static_geometry_calls=COUNTERS["static_geometry_calls"] - before["static_geometry_calls"],
               geometry_cache_reuses=(COUNTERS["static_geometry_calls"] - before["static_geometry_calls"]
                                      - COUNTERS["cheap_numeric"] + before["cheap_numeric"]),
               static_geometry="A same-source memoized algebra, actual evaluations conservatively counted as cheap numeric")
    (HERE / ("case-%02d.json" % case)).write_text(json.dumps(row,indent=2,ensure_ascii=False)+'\n')
    usage["attempts"][-1] = {k:v for k,v in row.items() if k != "details"}
    usage_path.write_text(json.dumps(usage,indent=2)+'\n')
    print(json.dumps({k:v for k,v in row.items() if k != "details"},ensure_ascii=False))
    return 1 if row["status"] != "PASS" else 0


if __name__ == "__main__":
    status = 0
    for arg in sys.argv[1:]:status |= run_case(int(arg))
    raise SystemExit(status)
