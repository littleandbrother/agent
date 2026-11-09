"""New M2 paths only. Predictor/model are mocks; no real numerical/model call."""
from pathlib import Path
from copy import deepcopy
import json
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / "docs/research/pqe-two-paper-plan-20261022"
SRC = ROOT / "workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src"
sys.path.insert(0, str(SRC))
from bfworld.agentlab.pqe20261022 import dynamic_methods as m1
from bfworld.agentlab.pqe20261022 import m2_methods as m2
from bfworld.agentlab.pqe20261022.methods import public_state, ContractError

old = json.loads((BASE / "dynamic-repair-m1/b/ANALYTIC-AFTER-DEFAULT-FIX.json").read_text())
phase = old["artifacts"]["contact"]["phase_facts"]
request = json.loads((BASE / "stage3-decision/s0/episodes/local-c0/callbacks/01/input-public.json").read_text())["request"]
state = request["context"]["state"]
result = request["public_result_registry"][state["last_result"]["public_result_ref"]]
state = deepcopy(state)
state["last_result"] = deepcopy(result)
state["last_result"]["assessment"] = "PRIVATE_SENTINEL_NEVER_EXPORT"
mock_predictions = []
def mock_predict(task, design, phase_facts=None):
    mock_predictions.append({"task":m2.digest(task), "design":m2.digest(design), "phase":m2.digest(phase_facts)})
    return {"prediction_status":"CONDITIONAL", "service_verdict":"UNKNOWN", "score":1.0,
            "necessary_failures":[], "phase_predictions":[], "repair_intervals":{},
            "relations":[], "unknowns":["MOCK_SOFTWARE_PATH_ONLY"]}
def saved_phase(task, design, public):
    assert public.get("design") == design
    assert "assessment" not in public
    return deepcopy(phase)
m1.predict_candidate = mock_predict
m1.extract_phase_facts = saved_phase
m2.extract_phase_facts = saved_phase
quota = {"remaining_actions":24, "remaining_cost":24, "max_candidates":1,
         "analytic_scores_left":24, "public_tool_calls_left":24,
         "model_calls_remaining":12, "model_cost_remaining":5, "model_call_reserve":0.19,
         "output_tokens_left":65536}
checks = {}
u, f = m2.M2Harness(True), m2.M2Harness(False)
u_state = u.update(state, {}, result)
f_state = f.update(state, {}, result)
assert u_state == f_state and u_state["history"] and u_state["last_result"]["facts"]
assert u._phase(u_state)[1] is True and f._phase(f_state)==({},False)
assert u._refuted(u_state,u_state["design"]) and f._refuted(f_state,f_state["design"])
u_batch, f_batch = u.generate(u_state, quota), f.generate(f_state, quota)
assert u_batch["status"] == f_batch["status"] == "READY"
assert set(u_batch["candidates"][0]["actual_input"]["design_patch"]) == {"debounce_s"}
assert not f_batch["candidates"][0]["update_consumed"]
assert u_batch["candidates"][0]["update_consumed"]
assert u.usage_ledger == f.usage_ledger == []
checks.update(single_phase_read_ablation=True, identical_update_history_and_fail_memory=True,
              u_consumes_saved_phase_f_does_not=True, exact_fail_dedup_preserved_both=True)

proposed = {**u_state["design"], "capacitance_f":0.0004}
actual = m1._actual(u_state, proposed)
candidate = {"id":"mock-generic-choice", "target":"fixture current", "operation":actual["operation"],
             "actual_input":actual,"expected_state_change":"MOCK", "prediction_or_unknown":"UNKNOWN",
             "observation_branches":["MOCK"], "affected_constraints":["MOCK"], "cost_bound":1,
             "validity_conditions":["MOCK"]}
model_requests = []
def model_call(req):
    model_requests.append(deepcopy(req))
    if req["site"]=="H-GEN" and not req["context"].get("public_tool_results"):
        payload = {"status":"PUBLIC_TOOLS", "tool_calls":[
            {"id":"p", "name":"phase_facts", "arguments":{}},
            {"id":"a", "name":"predict_candidate", "arguments":{"design":proposed}},
            {"id":"b", "name":"predict_candidate", "arguments":{"design":proposed}},
            {"id":"r", "name":"engineering_relations", "arguments":{}},
            {"id":"d", "name":"public_detail", "arguments":{"list":"activity", "offset":0}}]}
    elif req["site"]=="H-GEN":
        assert len(req["context"]["public_tool_results"])==5
        assert "PRIVATE_SENTINEL_NEVER_EXPORT" not in json.dumps(req)
        payload = {"status":"OK", "candidates":[candidate]}
    else:
        assert req["site"]=="H-RANK"
        payload = {"selected_id":candidate["id"], "selection_basis":"Mock model itself selects supplied candidate"}
    return {"payload":payload, "usage":{"status":"SOFTWARE_FIXTURE", "cost":0, "output_tokens":0}}
g = m2.M2GenericHarness(model_call, fixture_mode=True)
g_state = g.update(state, {}, result)
g_batch = g.generate(g_state, quota)
g_choice = g.select(g_state, g_batch, quota)
assert g_batch["status"] == g_choice["status"] == "READY", (g_batch,g_choice)
assert g.tool_call_count == g.public_tool_call_count == 5
assert g.analytic_score_count == 1 and len(model_requests)==3
assert len(g.usage_ledger)==3
assert g.tool_call_log[1]["analytic_scores_used"]==1 and g.tool_call_log[2]["analytic_scores_used"]==0
pages = model_requests[1]["context"]["public_tool_results"][-1]["result"]
assert pages["total"] == len(result["facts"]["activity"]) and len(pages["rows"])<=64
checks.update(g_model_asks_tools_then_generates_and_selects=True, full_public_page_matches_saved_result=True,
              five_tool_requests_one_mock_prediction=True, duplicate_predict_cache_zero_mock_score=True,
              private_fields_not_exposed=True, original_callback_usage_contract=True)

repeat = deepcopy(candidate)
repeat["id"]="repeat-known-failure"
repeat["operation"]="verify"
repeat["actual_input"]={"operation":"verify", "design_patch":{}, "problem_patch":{}}
old_n=len(model_requests)
blocked=g.select(g_state, {"status":"READY", "candidates":[repeat]},quota)
assert blocked["status"]=="INSUFFICIENT_EVIDENCE" and len(model_requests)==old_n
checks["g_common_exact_fail_dedup_no_extra_model_call"]=True

passed=json.loads((BASE/"stage3-decision/s0/episodes/local-c0/actions/01/public-result.json").read_text())
# Phase extraction is not needed for a zero-action saved PASS control here.
for h in (u,f,g):
    keep=deepcopy(u_state);keep["design"]=deepcopy(passed["design"]);keep["last_result"]=passed
    before=len(mock_predictions),len(model_requests)
    out=h.generate(keep,{**quota,"analytic_scores_left":0})
    assert out["status"]=="STOPPED" and not out["candidates"]
    assert before==(len(mock_predictions),len(model_requests))
checks["common_saved_pass_stop_zero_predict_and_model"]=True
try:m2.M2Harness("False")
except ContractError:checks["nonboolean_ablation_rejected"]=True
else:raise AssertionError("string switch accepted")

error_requests=[]
def bad_tool(req):
    error_requests.append(req)
    return {"payload":{"status":"PUBLIC_TOOLS","tool_calls":[{"id":"bad","name":"public_detail","arguments":{"list":"hidden_assessment","offset":0}}]},
            "usage":{"status":"SOFTWARE_FIXTURE","cost":0,"output_tokens":0}}
error_h=m2.M2GenericHarness(bad_tool,fixture_mode=True)
error_state=error_h.update(state,{},result)
error_out=error_h.generate(error_state,quota)
assert error_out["status"]=="TOOL_ERROR" and len(error_requests)==1 and error_h.analytic_score_count==0
checks["tool_error_retained_without_internal_model_rescue"]=True

p=Path(__file__).with_name("MOCK-PATH-CHECKS.json")
output={"status":"PASS_MOCK_AND_SAVED_FACT_PATHS_ONLY", "worker_actual_cheap_full_model_calls":0,
        "mock_prediction_calls":len(mock_predictions),"mock_model_callbacks":len(model_requests),
        "checks":checks,"u_actual_input":u_batch["candidates"][0]["actual_input"],
        "f_actual_input":f_batch["candidates"][0]["actual_input"],
        "g_selected_input":g_choice["actual_input"],"g_tools":g.tool_call_log,
        "no_new_m2_tasks_or_results_read":True,
        "source_sha256":hashlib.sha256(Path(m2.__file__).read_bytes()).hexdigest()}
p.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({k:output[k] for k in ("status","worker_actual_cheap_full_model_calls","mock_prediction_calls","mock_model_callbacks","checks")}))
