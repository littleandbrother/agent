"""Save the one prospective task and A source receipt. No scientific execution."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SRC = ROOT/"workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src"
sys.path.insert(0, str(SRC))
from bfworld.agentlab.pqe20261024debt import task, facts, bounds


def ref(p):
    data = p.read_bytes()
    return {"path": str(p), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def save_once(name, value):
    p = HERE/name
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode()
    if p.exists():
        if p.read_bytes() != data:
            raise ValueError("FROZEN_CONTENT_CHANGED:"+str(p))
    else:
        with p.open("xb") as stream:
            stream.write(data)
    if p.read_bytes() != data:
        raise ValueError("FROZEN_READBACK:"+str(p))
    return ref(p)


if __name__ == "__main__":
    selection = json.loads((HERE/"TASK-SELECTION.json").read_text())
    family = task.make_task_family()
    for rule, item in zip(selection["conditions"], family):
        actual = item["selection_rule"]
        assert rule["id"] == actual["id"] == item["condition_id"]
        assert rule["starts_s"] == actual["starts_s"]
        assert rule["opening_segments"] == [list(x) for x in actual["opening"]]
        assert rule["closing_segments"] == [list(x) for x in actual["closing"]]
        assert rule["hold_s"] == actual["hold_s"]
    tasks_ref = save_once("TASKS.json", {"schema": "codebt-frozen-family-v1",
        "family_id": task.FAMILY_ID, "conditions": family, "initials_run": 0,
        "selection_ref": ref(HERE/"TASK-SELECTION.json")})
    contract_ref = save_once("FACT-CONTRACT.json", facts.describe_contract())
    symbolic_ref = save_once("BOUND-CONTRACT.json", bounds.describe_bounds())
    source = SRC/"bfworld/agentlab/pqe20261024debt"
    paths = [source/(name+".py") for name in ("consumer", "holding", "task", "bounds", "facts")]
    for p in paths:
        ast.parse(p.read_text(), filename=str(p))
    checks = json.loads((HERE/"LOGIC-RESULTS.json").read_text())
    assert checks["status"] == "PASS" and checks["new_full_scientific_inputs"] == 0
    stat = os.statvfs(ROOT)
    generated = [ref(p) for p in HERE.iterdir() if p.is_file() and p.name != "SOURCE-READY.json"]
    receipt = {"schema": "codebt-A-source-ready-v1", "status": "SOURCE-READY",
        "at_utc": datetime.now(timezone.utc).isoformat(), "package": "BF-PQE-CODEBT-KILL-20261024-001",
        "owner": "campaign-a", "source_bindings": [ref(p) for p in paths],
        "tasks": tasks_ref, "contract": contract_ref, "symbolic_bounds": symbolic_ref,
        "logic_checks": ref(HERE/"LOGIC-RESULTS.json"), "final_logic_cases": checks["logic_checks"],
        "logic_suite_history": {"completed_runs": 4, "case_executions": 76,
            "note": "18 initial; 18 after status/event-order hardening; 20 after reset/payload controls; 20 final after factual dependency/voltage metadata changes"},
        "static_AST_modules": 5, "initials_run": 0, "full_scientific_inputs": 0,
        "source_numeric_steps": 0, "boundary_numeric_calls": 0, "provider_requests": 0,
        "engineering_effect": "UNKNOWN", "numeric_energy_closure": "UNKNOWN",
        "available_bytes_after": stat.f_bavail*stat.f_frsize,
        "retained_A_artifact_bytes": sum(x["bytes"] for x in generated),
        "generated_file_inventory": generated,
        "handoff": "S0 thin adapter/static public integration only; accounting gate still blocks science/provider. Do not run or replace initials."}
    p = HERE/"SOURCE-READY.json"
    with p.open("x") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2); stream.write("\n")
    assert json.loads(p.read_text()) == receipt
    print(json.dumps({"status": "SOURCE-READY", "receipt": ref(p), "final_logic_cases": checks["logic_checks"],
                      "science": 0, "provider": 0, "engineering_effect": "UNKNOWN"}))
