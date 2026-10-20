#!/usr/bin/env python3
"""Seal one actual formation after S0 reviews its original submitted prose."""
from decimal import Decimal, localcontext
from pathlib import Path
import runpy

d = runpy.run_path(str(Path(__file__).with_name("execute.py")))
OUT, m, r = d["OUT"], d["m"], d["r"]
load, seal, digest, file_hash = d["load"], d["seal"], d["digest"], d["file_hash"]
result = d["get"]("G1-formation")
if result is None:
    raise ValueError("NO_ACTUAL_FORMATION_RESULT")
account = result["accounting"]
if account["unknown_or_missing_usage"]:
    raise ValueError("NEW_UNKNOWN_USAGE_STOP")
q, wall, usd = account["requests"], result["wall_seconds_total"], account["settled_charge_upper_bound_usd"]
with localcontext() as ctx:
    ctx.prec = 40
    w, u = Decimal(str(wall)), Decimal(str(usd))
    shares = [{"lineage": i + 1, "requests": q // 3 + int(i < q % 3),
               "wall_s": float(w / 3 if i < 2 else w - w / 3 - w / 3),
               "settled_upper_usd": float(u / 3 if i < 2 else u - u / 3 - u / 3)} for i in range(3)]
seal(OUT / "G1-formation-accounting.json", {"actual_event_count": 1, "event_id": "G1-formation",
     "requests": q, "wall_s": wall, "usd": usd, "allocations": shares,
     "all_actual_cost_charged_once_globally": True, "full_end_to_end_cost": "UNKNOWN"})
value = {"eligible": False, "status": result["status"], "actual_formation_event_count": 1,
         "default_H0_changed": False, "provider_requests": q,
         "accounting_path": str(OUT / "G1-formation-accounting.json")}
if result["status"] == "ACTUAL_PROSPECTIVE_SUBMITTED":
    reviewed = d["semantic"]("G1-formation")
    raw = result["external_result"]["raw_proposal"]
    costs = load(OUT / "episodes/G1-formation/provider-costs.json")
    parents = m.frozen_parent_methods()
    receipt = {"evidence_kind": "ACTUAL_PROVIDER", "author": "participant-model",
        "semantic_component": "proposal_procedure_only", "usage_status": "SETTLED",
        "automatic_retry": False, "reported_models": result["reported_models"], "unknown_usage": [],
        "formation_event_count": 1, "formation_event_id": "G1-formation", "registered_formation_event_id": "G1-formation",
        "provider_request_ids": [x["id"] for x in costs["rows"]], "requests": q, "wall_s": wall, "usd": usd,
        "model_configuration_sha256": digest({"profile": file_hash(d["PROFILE"]),
            "runtime_configuration": file_hash(d["p"]["configuration"]),
            "SDK": file_hash(r.HARNESS / "dist/phase1/episode.js")}),
        "proposal_sha256": m.digest(raw), "history_sha256": m.HISTORY_SHA256,
        "model_history_sha256": m.MODEL_HISTORY_SHA256,
        "H0_sha256": parents["H0"]["method_sha256"], "G0_sha256": parents["G0"]["procedure_sha256"]}
    seal(OUT / "G1-actual-formation-receipt.json", receipt)
    try:
        gate = m.formation_gate(raw, receipt=receipt)
        seal(OUT / "G1-structural-gate.json", gate)
        valid = reviewed["eligible"] and gate["status"] == "ELIGIBLE_FOR_S0_FREEZE"
        value.update(eligible=valid, status=gate["status"] if reviewed["eligible"] else "SEMANTIC_REJECTION")
        if valid:
            value["proposal_procedure"] = gate["normalized"]["proposal_procedure"]
            value["procedure_sha256"] = digest(value["proposal_procedure"])
    except ValueError as error:
        value.update(status="FORMATION_GATE_REJECTED", reason=str(error))
seal(OUT / "G1-freeze.json", value)
print({k: v for k, v in value.items() if k != "proposal_procedure"})
