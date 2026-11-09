"""Four bounded analytic API checks; no dynamic/reference/provider calls.

Run once.  The exclusive ledger prevents accidental repeated score batches.
The proposed reference is derived from the failed point's new analytic bounds,
not a saved successful design.  S0 alone may execute its dynamic consequence.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from bfworld.agentlab.pqe20261022.dynamic_relations import (
    extract_phase_facts, predict_candidate,
)

BASE = Path(__file__).resolve().parents[1]
PLAN = BASE.parent
OUT = Path(__file__).resolve().parent
COMMON = PLAN / "stage3-update-continue/shared/common-input.json"
UPDATE = PLAN / "stage3-update-continue/s0/episodes/update-generic/external-update.json"


def read(path):
    return json.loads(Path(path).read_text())


common, update = read(COMMON), read(UPDATE)
task, design = common["state_before_external"]["task"], update["state_after"]["design"]
compact = update["state_after"]["last_result"]
public = read(common["external_public_result"]["path"])
facts = extract_phase_facts(task, design, compact)
full_facts = extract_phase_facts(task, design, public)
assert facts["service"]["activity_counts"]["tx_begin"] == 64
assert facts["service"]["activity_counts"]["brownout"] == 64
assert facts["failed_phases"] == ["TX"]
assert full_facts["failed_phases"] == facts["failed_phases"]
assert not facts["service"]["truth_or_private_assessment_read"]

ledger = OUT / "ANALYTIC-LEDGER.jsonl"
with ledger.open("x") as f:
    f.write(json.dumps({"kind": "batch_start", "score_cap": 4, "full_dynamic_cap_A": 0})+"\n")
rows = []


def score(label, candidate):
    number = len(rows)+1
    assert number <= 4
    with ledger.open("a") as f:
        f.write(json.dumps({"kind": "score_started", "number": number, "label": label,
                            "design": candidate}, sort_keys=True)+"\n")
    start = time.monotonic()
    result = predict_candidate(task, candidate, facts)
    rows.append({"number": number, "label": label, "design": deepcopy(candidate),
                 "seconds": time.monotonic()-start, "prediction": result})
    with ledger.open("a") as f:
        f.write(json.dumps({"kind": "score_finished", "number": number,
                            "analytic_scores_consumed": result["analytic_scores_consumed"],
                            "status": result["prediction_status"], "score": result["score"]})+"\n")
    assert result["service_verdict"] == "UNKNOWN"
    assert result["predicted_received_count"] is None
    assert result["analytic_scores_consumed"] == 1
    return result


baseline = score("original_public_TX_failure", design)
assert baseline["prediction_status"] == "CONDITIONAL", baseline["unknowns"]
assert any(p["phase"] == "TX" and p.get("terminal_margin_v", 1) < 0
           for p in baseline["phase_predictions"])

# Independent of Task ID and known successful parameter values.  The geometry
# midpoint increases source voltage while respecting pressure/envelope bounds.
joint = deepcopy(design)
geometry = baseline["repair_intervals"]["mechanism"]
lo, hi = geometry["task_stroke_interval_m"]
stroke = (design["mechanism"]["stroke_m"] + min(hi, geometry["joint_geometry_stroke_upper_m"]))/2
blo, bhi = geometry["task_base_radius_interval_m"]
base_lower = max(blo, geometry["minimum_base_radius_per_stroke"]*stroke)
base_upper = min(bhi, geometry["maximum_base_plus_stroke_m"]-stroke)
assert base_lower <= base_upper
joint["mechanism"] = {**design["mechanism"], "stroke_m": stroke,
                       "cam_base_radius_m": min(base_upper, max(base_lower, design["mechanism"]["cam_base_radius_m"]))}
cap_domain = task["design_domain"]["capacitance_f"]
conditional_lower = baseline["repair_intervals"]["capacitance_f"]["conditional_no_source_lower_f"]
assert conditional_lower is not None
joint["capacitance_f"] = min(cap_domain["max"], max(cap_domain["min"], design["capacitance_f"], 1.25*conditional_lower))
reference = score("source_derived_joint_reference", joint)

illegal = deepcopy(design)
illegal["mechanism"] = {**design["mechanism"], "stroke_m": hi, "cam_base_radius_m": bhi}
rejected = score("within_scalar_bounds_but_joint_geometry_invalid", illegal)
assert rejected["prediction_status"] == "REJECT_NECESSARY"
assert "assembly_envelope_exceeded" in rejected["necessary_failures"]
assert not rejected["phase_predictions"]

different_c = deepcopy(joint)
different_c["capacitance_f"] = min(cap_domain["max"], joint["capacitance_f"]*1.5)
feedback = score("same_source_different_capacitance_feedback", different_c)
assert feedback["prediction_status"] == "CONDITIONAL", feedback["unknowns"]
assert feedback["source_feedback"]["recomputed_for_current_design"]
q_reference = sum(p.get("source_charge_c_approx", 0.0) for p in reference["phase_predictions"])
q_feedback = sum(p.get("source_charge_c_approx", 0.0) for p in feedback["phase_predictions"])
assert abs(q_reference-q_feedback) > 1e-12

report = {"package": "BF-PQE-DYNAMIC-REPAIR-M1-20261023-001", "owner": "campaign-a",
          "status": "FOUR_ANALYTIC_CHECKS_PASSED", "analytic_score_count": len(rows),
          "new_full_dynamic_inputs": 0, "new_model_requests": 0,
          "public_observation": facts, "checks": rows,
          "feedback_source_charge_c": [q_reference, q_feedback],
          "reference_is_complete_service_pass": False}
with (OUT / "ANALYTIC-CHECKS.json").open("x") as f:
    json.dump(report, f, indent=2, allow_nan=False)
    f.write("\n")
with (OUT / "CANDIDATE-FOR-S0.json").open("x") as f:
    json.dump({"origin": "DEVELOPER_DERIVED_ENGINEERING_REFERENCE", "task_id": task["task_id"],
        "task_file_sha256": public["task_sha256"], "design": joint,
        "derivation": "Geometry interval midpoint; 1.25 times conditional source-free tail C bound, then current-design prediction.",
        "prediction": reference, "autonomous_agent_success": False,
        "full_dynamic_consequence": "NOT_RUN_BY_A; S0 owns the global 12-input budget"}, f, indent=2, allow_nan=False)
    f.write("\n")
print(json.dumps({"status": report["status"], "analytic_score_count": len(rows),
    "full_dynamic": 0, "models": 0,
    "scores": [{"label": r["label"], "score": r["prediction"]["score"],
                "status": r["prediction"]["prediction_status"]} for r in rows],
    "reference_design": joint, "feedback_source_charge_c": [q_reference, q_feedback],
    "output_sha256": hashlib.sha256((OUT / "ANALYTIC-CHECKS.json").read_bytes()).hexdigest()}, indent=2))
