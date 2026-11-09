"""Eight reserved real cheap predictions; no dynamic consumer/model calls."""
from pathlib import Path
from copy import deepcopy
import json
import hashlib
import sys
import datetime

ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / "docs/research/pqe-two-paper-plan-20261022"
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import dynamic_methods as module
from bfworld.agentlab.pqe20261022.methods import public_state, ContractError

PRIOR = json.loads(Path(__file__).with_name("ANALYTIC-CHECKS.json").read_text())
RECEIPT = json.loads(Path(__file__).with_name("IMPLEMENTATION-RECEIPT.json").read_text())
TOTAL_CAP = RECEIPT["budget"]["b_reserved_analytic_scores"]
if TOTAL_CAP <= PRIOR["cheap_analytic_scores_used"]:
    raise RuntimeError("No additional S0 allocation")
OUT = Path(__file__).with_name("ANALYTIC-AFTER-DEFAULT-FIX.json")
if OUT.exists():
    raise RuntimeError("Existing counted check retained; no unallocated repeat")

def read(p):
    return json.loads(p.read_text())

def bind(p):
    return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}

real_predict = module.predict_candidate
used = []
def counted(task, design, phase_facts=None):
    if len(used) + PRIOR["cheap_analytic_scores_used"] >= TOTAL_CAP:
        raise RuntimeError("B reserved eight scores exhausted")
    used.append({"task_sha256": module.digest(task), "design_sha256": module.digest(design)})
    result = real_predict(task, design, phase_facts)
    used[-1].update(prediction_status=result["prediction_status"], score=result["score"],
                    service_verdict=result["service_verdict"], prediction_sha256=module.digest(result))
    return result
module.predict_candidate = counted
checks, artifacts, error = {}, {}, None
try:
    common_path = BASE / "stage3-update-continue/shared/common-input.json"
    common = read(common_path)
    failure_path = Path(common["external_public_result"]["path"])
    failure = read(failure_path)
    method = module.DynamicRepairHarness()
    state = method.update(common["state_before_external"], common["external_decision"], failure)
    assert state["update_status"] == "UPDATED"
    quota = {"remaining_actions": 3, "remaining_cost": 3, "max_candidates": 2,
             "analytic_scores_left": TOTAL_CAP-PRIOR["cheap_analytic_scores_used"]}
    batch = PRIOR["artifacts"]["main"]["generate"]
    checks.update(PRIOR["checks"])
    artifacts["main_previously_verified"] = {"retained_check": bind(Path(__file__).with_name("ANALYTIC-CHECKS.json")),
                                            "basis": "Earlier G/S/U verified, its unrelated local control failure retained; not rerun or recharged."}

    # Real public histories: candidate derivation reads only these initial FAIL
    # records. No successful numeric repair is provided to the algorithm.
    for label, rel, changed in [
        ("contact", "stage3-decision/s0/episodes/local-c0/callbacks/01/input-public.json", "debounce_s"),
        ("retention", "stage3-e2main/s0/episodes/d05-r1-b1/callbacks/01/input-public.json", "persistent_queue")]:
        public_path = BASE / rel
        request = read(public_path)["request"]
        control_state = request["context"]["state"]
        initial_ref = control_state["last_result"]["public_result_ref"]
        public_result = request["public_result_registry"][initial_ref]
        control = module.DynamicRepairHarness()
        control_state = control.update(control_state, {"actual_input": {"operation": "verify", "design_patch": {}, "problem_patch": {}}}, public_result)
        control_quota = {**quota, "max_candidates": 1, "analytic_scores_left": TOTAL_CAP-PRIOR["cheap_analytic_scores_used"]-len(used)}
        control_batch = control.generate(control_state, control_quota)
        assert control_batch["status"] == "READY", (label, control_batch)
        control_choice = control.select(control_state, control_batch, control_quota)
        assert control_choice["status"] == "READY", (label, control_choice)
        patch = control_choice["actual_input"]["design_patch"]
        assert set(patch) == {changed}, (label, patch)
        real_phase = control_state["strategy"]["dynamic_repair"]["phase_facts"]
        without_update = control._simple_repairs(control_state, {})
        with_update = control._simple_repairs(control_state, real_phase)
        assert with_update and not without_update
        assert control.usage_ledger == []
        artifacts[label] = {"input": bind(public_path), "initial_public_result_identity": initial_ref,
                            "phase_facts": real_phase, "generate": control_batch, "select": control_choice,
                            "calls": control.program.calls, "update_ablation_proposal_only": {
                                "without_phase_facts": without_update, "with_phase_facts": with_update,
                                "additional_scores": 0, "boundary": "software actual-consumption check, no dynamic outcome"}}
        checks[label + "_remains_one_field_local"] = True
        checks[label + "_update_changes_actual_proposal"] = True

    invalid = deepcopy(batch["candidates"][-1])
    invalid["id"] = "necessary-domain-negative-control"
    invalid["actual_input"] = module._actual(state, {**state["design"],
        "mechanism": {"stroke_m": 0.008, "cam_base_radius_m": 0.008}})
    invalid["operation"] = invalid["actual_input"]["operation"]
    rejected = method.select(state, {"status": "READY", "candidates": [invalid]},
                             {**quota, "analytic_scores_left": TOTAL_CAP-PRIOR["cheap_analytic_scores_used"]-len(used)})
    assert rejected["status"] == "INSUFFICIENT_EVIDENCE", rejected
    checks["necessary_domain_violation_rejected"] = True
    artifacts["necessary_negative"] = {"candidate": invalid, "select": rejected}

    pass_path = BASE / "stage3-update-continue/s0/episodes/update-generic/actions/02/public-result.json"
    passed = read(pass_path)
    keeper = module.DynamicRepairHarness()
    kept = keeper.update(state, {"actual_input": {"operation": "verify", "design_patch": {}, "problem_patch": {}}}, passed)
    stopped = keeper.generate(kept, {**quota, "analytic_scores_left": 0})
    assert stopped["status"] == "STOPPED" and not stopped["candidates"]
    assert keeper.analytic_score_count == 0 and keeper.usage_ledger == []
    checks["saved_pass_retained_zero_scores"] = True
    artifacts["pass"] = {"input": bind(pass_path), "generate": stopped}

    empty = module.DynamicRepairHarness()
    depleted = empty.generate(state, {**quota, "analytic_scores_left": 0})
    assert depleted["status"] == "INSUFFICIENT_EVIDENCE" and empty.analytic_score_count == 0
    try:
        empty.generate(state, {k: v for k, v in quota.items() if k != "analytic_scores_left"})
    except ContractError:
        checks["missing_analytic_quota_rejected"] = True
    else:
        raise AssertionError("Missing quota silently accepted")
    checks["zero_quota_dispatch_blocked"] = True
    checks["total_real_predictions_within_reallocated_cap"] = len(used) + PRIOR["cheap_analytic_scores_used"] <= TOTAL_CAP
except Exception as exc:
    error = repr(exc)
finally:
    payload = {"schema": "pqe-dynamic-repair-b-checks-v1", "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "status": "PASS" if error is None else "FAILED_RETAINED", "error": error,
               "cheap_analytic_scores_used": len(used), "prior_counted_scores": PRIOR["cheap_analytic_scores_used"],
               "cumulative_b_scores": len(used) + PRIOR["cheap_analytic_scores_used"], "reserved_scores": TOTAL_CAP,
               "full_dynamic_inputs": 0, "model_calls": 0, "checks": checks,
               "source": bind(Path(module.__file__)), "relations_source": bind(Path(module.__file__).with_name("dynamic_relations.py")),
               "score_calls": used, "artifacts": artifacts}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({k: payload[k] for k in ("status", "error", "cheap_analytic_scores_used", "checks")}))
if error:
    raise SystemExit(1)
