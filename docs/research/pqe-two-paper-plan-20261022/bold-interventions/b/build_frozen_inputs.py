"""Freeze eight PUBLIC engineering cases into one shared BOLD parent/history.

This script reads A's public results only. It does not open raw or assessment
files, and it refuses to replace a differently frozen output.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bfworld.agentlab.pqe20261022.methods import digest
from bfworld.agentlab.pqe20261023bold.contracts import compact_engineering_case, compact_feedback
from bfworld.agentlab.pqe20261023bold.parent import parent_program


HERE = Path(__file__).resolve().parent
A = HERE.parent / "a"
RESULTS = A / "ENGINEERING-RESULTS.json"
FREEZE = A / "ENGINEERING-FREEZE.json"
CONTRACT = A / "CONSUMER-CONTRACT.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_once(name, value):
    path = HERE / name
    body = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    if path.exists():
        if path.read_bytes() != body:
            raise RuntimeError("FROZEN_OUTPUT_DIFFERS:" + name)
    else:
        path.write_bytes(body)
    return {"path": str(path), "sha256": sha(path), "bytes": len(body)}


def main():
    results = json.loads(RESULTS.read_text())
    freeze = json.loads(FREEZE.read_text())
    if (results.get("full_inputs") != 8 or len(results.get("rows", [])) != 8
            or results.get("post_result_revision") != 0 or
            [r["cell"] for r in results["rows"]] != [
                "01-original-parent-t1", "02-original-parent-t2",
                "03-joint-source-supply-t1", "04-joint-source-supply-t2",
                "05-save-first-t1", "06-save-first-t2",
                "07-persistent-adaptive-t1", "08-persistent-adaptive-t2"]):
        raise RuntimeError("ENGINEERING_EIGHT_CELL_FREEZE_MISMATCH")
    by_family = {c["id"]: c for c in freeze["cases"]}
    cases, history, catalog = [], [], {}
    for row in results["rows"]:
        cell = row["cell"]
        family = cell[3:].rsplit("-t", 1)[0]
        binding = row["binding"]["public-result.json"]
        path = Path(binding["path"])
        if (not path.is_file() or path.parent != A / "engineering" / cell
                or sha(path) != binding["sha256"] or path.stat().st_size != binding["bytes"]):
            raise RuntimeError("PUBLIC_RESULT_FILE_BINDING_MISMATCH:" + cell)
        public = json.loads(path.read_text())
        if (public.get("task_id") != row["task_id"] or
                public.get("design") != row["design"] or
                public.get("public_check", {}).get("verdict") != row["verdict"] or
                public.get("model_valid") is not True or
                public.get("execution_status") != "COMPLETE" or
                row["design"] != by_family[family]["design"]):
            raise RuntimeError("PUBLIC_RESULT_CONTENT_MISMATCH:" + cell)
        source_id = "bold-engineering-" + cell
        ref = {"source_id": source_id, "path": str(path), "sha256": binding["sha256"]}
        cases.append(compact_engineering_case(cell, public, ref, family=family))
        summary = compact_feedback(public, ref)
        catalog[source_id] = {
            "path": str(path), "sha256": binding["sha256"], "bytes": binding["bytes"],
            "visibility": "PUBLIC", "allowed_json_pointers": ["/"],
        }
        history.append({
            "incident_id": "BOLD-ENGINEERING-" + cell,
            "allowed_for_learning": True,
            "provenance": "PUBLIC_EXECUTION",
            "record_ref": [source_id],
            "visible_before": {
                "task_id": row["task_id"], "task_sha256": row["task_sha256"],
                "design": row["design"], "problem": public["problem"],
                "design_fixed_before_all_eight_results": True,
            },
            "decision": {
                "source": "DEVELOPER_FROZEN_ENGINEERING_COMPARISON",
                "autonomous_agent_choice": False,
                "design_family": family,
                "actual_input": {"operation": "execute_original_complete_consumer",
                                 "design": row["design"], "problem": public["problem"]},
                "pre_run_hypothesis": by_family[family]["hypothesis"],
            },
            "result": summary,
            "developer_annotation": {
                "author": "DEVELOPER_RETROSPECTIVE",
                "text": "One frozen full public execution; manual engineering comparison, not learned method behavior. The original public result is in the source catalog.",
                "not_an_autonomous_agent_discovery_or_original_prediction": True,
            },
        })
    if len(cases) != 8 or len(history) != 8 or sum(c["public_check"]["verdict"] == "PASS" for c in cases) != 4:
        raise RuntimeError("PUBLIC_EIGHT_CASE_STATUS_MISMATCH")
    program = parent_program(cases)
    outputs = {
        "parent-program.json": save_once("parent-program.json", program),
        "common-history.json": save_once("common-history.json", history),
        "public-source-catalog.json": save_once("public-source-catalog.json", catalog),
    }
    receipt = {
        "schema": "bold-B-frozen-public-inputs-v1",
        "package": "BF-PQE-BOLD-INTERVENTIONS-20261023-001",
        "source": {"engineering_results_sha256": sha(RESULTS),
                   "engineering_freeze_sha256": sha(FREEZE),
                   "consumer_contract_sha256": sha(CONTRACT)},
        "cases": 8, "history_incidents": 8, "engineering_public_pass": 4,
        "parent_program_digest": digest(program),
        "common_history_digest": digest(history),
        "outputs": outputs,
        "limits": {"new_model_requests": 0, "new_full_inputs": 0,
                   "new_cheap_scores": 0, "new_task_or_hidden_material_read": False},
        "claim_boundary": "Developer-written parent bound to public engineering development outcomes; automatic formation and unseen-task method effects remain unmeasured.",
    }
    print(json.dumps(save_once("FREEZE-RECEIPT.json", receipt), ensure_ascii=False))
    print(json.dumps({"parent_program_digest": receipt["parent_program_digest"],
                      "common_history_digest": receipt["common_history_digest"],
                      "cases": len(cases), "history": len(history),
                      "output_bytes": {key: value["bytes"] for key, value in outputs.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
