"""Invoke real new G/S/U on <=3 saved public states. No scientific execution."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys

BDIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(BASE / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022.decision_methods import DecisionEpisodeDriver, DecisionHarness, VERSION
from bfworld.agentlab.pqe20261022.methods import digest
from bfworld.agentlab.pqe20261022.decision_facts import candidate_facts

FROZEN = "260da9338be02a906070e78ca8ee4dc97c13839a524b9627835cdd87d07d5750"


def read(path):
    return json.loads(Path(path).read_text())


def load_cases():
    refs = read(BDIR.parent / "a/relations.json")["public_bindings"]
    docs = {}
    for name, ref in refs.items():
        raw = Path(ref["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("SAVED_PUBLIC_BINDING_CHANGED")
        docs[name] = json.loads(raw)
    r1, r2, local = docs["r1"], docs["r2"], docs["local"]
    if r1["initial_state"] != r2["initial_state"]:
        raise ValueError("INITIAL_STATES_DIFFER")
    steps = lambda t:[s for s in t["steps"] if s.get("result")]
    a, b, control = steps(r1), steps(r2), steps(local)
    return [
        {"name":"common_initial_r1_pool", "state_key":"common_initial", "state":r1["initial_state"], "step":a[0]},
        {"name":"common_initial_r2_pool", "state_key":"common_initial", "state":r2["initial_state"], "step":b[0]},
        {"name":"after_r2_first_failure", "state_key":"after_r2_first_failure", "state":b[1]["state_before"], "step":b[1]},
        {"name":"local_repair_control", "state_key":"local_repair_control", "state":control[0]["state_before"], "step":control[0]},
    ], refs


def replay_case(case, condition):
    step = case["step"]
    requests = []
    gen = {"status":"OK", "candidates":deepcopy(step["generate"]["candidates"])}
    old_selected = step["select"]["selected_id"]
    def saved(request):
        requests.append(deepcopy(request))
        if request["site"] == "H-GEN":
            payload = gen
        elif request["site"] == "H-RANK":
            payload = {"selected_id":old_selected, "selection_basis":"Replay the saved historical selection unchanged; no new model inference.", "expected_discrimination_or_gain":"UNKNOWN"}
        else:
            raise ValueError("UNEXPECTED_OFFLINE_SITE")
        return {"payload":deepcopy(payload), "usage":{"status":"SOFTWARE_FIXTURE", "output_tokens":0, "cost":0}}
    driver = DecisionEpisodeDriver(condition, saved, episode_id="offline-saved-state", initial_state=case["state"], model_identity="SOFTWARE_FIXTURE", request_reserve_usd=0.1, fixture_mode=True, expected_methods_sha256=FROZEN)
    output = driver.next()
    return driver, output, requests


def behavior():
    cases, refs = load_cases()
    rows = []
    for case in cases:
        old, old_out, old_asks = replay_case(case, "full_h")
        new, new_out, new_asks = replay_case(case, "improved_full_h")
        before = old_out.get("decision")
        after = new_out.get("decision")
        rows.append({
            "case":case["name"], "state_key":case["state_key"], "public_state_sha256":digest(case["state"]),
            "old_actual_input":before["actual_input"] if before else None,
            "new_actual_input":after["actual_input"] if after else None,
            "old_status":old_out["status"], "new_status":new_out["status"],
            "action_changed":bool(before and after and before["actual_input"] != after["actual_input"]),
            "relation_consumption":new.harness.decisions,
            "loaded_hook_calls":new.harness.program.calls,
            "new_candidate":after.get("selected_candidate") if after else None,
            "offline_ask_sites":{"old":[r["site"] for r in old_asks],"new":[r["site"] for r in new_asks]},
            "subsequent_dynamic_service":"NOT_EXECUTED; offline facts/selection do not establish new design service.",
        })
    # Replay the first old r2 action and its actual old public result through
    # typed Update. Do not feed its result to a different new pending design.
    initial = next(c for c in cases if c["name"] == "common_initial_r2_pool")
    h = DecisionHarness("improved_full_h", fixture_mode=True)
    typed = h.update(initial["state"], initial["step"]["select"], initial["step"]["result"])
    next_case = next(c for c in cases if c["name"] == "after_r2_first_failure")
    next_case = {**next_case, "state":typed}
    next_driver, next_action, next_requests = replay_case(next_case, "improved_full_h")
    # Negative control on the existing local state, not a model response or a
    # fourth public state: the already executed valid FAIL of its unchanged
    # design must block repeat verification, while preserving the local repair.
    local = next(c for c in cases if c["name"] == "local_repair_control")
    verification = {"id":"software-repeat-verification", "operation":"verify", "target":"design",
                    "reason":"Explicit software negative control, not model generation.",
                    "expected_state_change":"No design change", "prediction_or_unknown":"UNKNOWN",
                    "actual_input":{"operation":"verify","design_patch":{},"problem_patch":{}}}
    initial_result = local["state"]["last_result"]
    if initial_result["design"] != local["state"]["design"]:
        raise ValueError("LOCAL_RESULT_INPUT_MISMATCH")
    control_h = DecisionHarness("improved_full_h", fixture_mode=True)
    control_h.quota = {"remaining_actions":1}
    before_memory = control_h._select({"state":local["state"],"candidates":[verification]})
    update_control = control_h.update(local["state"], {"actual_input":verification["actual_input"],"selected_candidate":verification}, initial_result)
    after_memory = control_h._select({"state":update_control,"candidates":[verification]})
    repair = deepcopy(local["step"]["generate"]["candidates"][0])
    repair_after_memory = control_h._select({"state":update_control,"candidates":[repair]})
    value = {"schema":"pqe-decision-behavior-delta-v1", "dispatch":"BF-PQE-S3-DECISION-20261023-001", "method_version":VERSION,
             "source_bindings":[{"path":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
                                for p in [BASE / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022" / name
                                          for name in ("decision_methods.py","decision_facts.py","methods.py","episode_methods.py")]],
             "public_state_count":3, "common_initial_has_two_saved_candidate_pools":True,
             "source_public_bindings":refs, "rows":rows,
             "typed_update_replay":{"old_consumed_actual_input":initial["step"]["select"]["actual_input"],
                                    "update_status":typed.get("update_status"), "memory":typed.get("strategy", {}).get("decision_memory", []),
                                    "next_generate_consumed_strategy":next_requests[0]["context"]["state"].get("strategy") if next_requests else None,
                                    "next_status":next_action["status"],"next_actual_input":next_action.get("decision", {}).get("actual_input") if next_action.get("decision") else None},
             "update_consumption_negative_control":{
                 "evidence_class":"SOFTWARE_NEGATIVE_CONTROL_ON_EXISTING_LOCAL_STATE",
                 "no_model_output_or_scientific_result_created":True,
                 "recorded_current_result_sha256":initial_result["result_sha256"],
                 "facts_unchanged":candidate_facts(local["state"],verification["actual_input"]) == candidate_facts(update_control,verification["actual_input"]),
                 "without_update_memory":before_memory,"with_update_memory":after_memory,
                 "different_local_repair_with_same_memory":repair_after_memory,
                 "consumed_relations":control_h.decisions,
                 "memory":update_control["strategy"]["decision_memory"],
             },
             "provider_requests":0,"new_scientific_inputs":0,"new_model_outputs":0,
             "boundary":"Real fixed-method calls with offline saved planner payloads. No joint simulation, new provider output, model efficacy or complete service claim."}
    return value


if __name__ == "__main__":
    result = behavior()
    BDIR.mkdir(parents=True, exist_ok=True)
    path = BDIR / "behavior-delta.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"rows":[{k:r[k] for k in ("case","old_status","new_status","action_changed")} for r in result["rows"]]},ensure_ascii=False))
