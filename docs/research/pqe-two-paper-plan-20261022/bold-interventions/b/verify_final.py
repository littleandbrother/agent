"""Independent, read-only BOLD B exit assertions over retained public evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bfworld.agentlab.pqe20261022.methods import digest


HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
S0 = PACKAGE / "s0"
EPISODES = S0 / "episodes"
ROOT = HERE.parents[4]
PAPERS = ROOT / "workbench/bf-campaign-s0-20261019/battery-world/papers/pqe20261022"
SOURCE = ROOT / "workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src/bfworld/agentlab/pqe20261023bold"
PREFIXES = {
    "paper1-stage3-decision-increment.md": (16436, "96626b914bd00bc0fad55390d30430f946ef10a9f650b5e8df11700cde01373b"),
    "paper2-stage3-decision-increment.md": (15736, "e89eafa33633e86470baafbcf97c1a36bf29bbfa6c03ffd061bf57c1dc375206"),
}


def read(path):
    return json.loads(path.read_text())


def bind(path):
    body = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parent = read(HERE / "parent-program.json")
    history = read(HERE / "common-history.json")
    freeze = read(HERE / "FREEZE-RECEIPT.json")
    check(digest(parent) == freeze["parent_program_digest"], "PARENT_DIGEST")
    check(digest(history) == freeze["common_history_digest"], "HISTORY_DIGEST")
    check(len(history) == 8 and all(h["allowed_for_learning"] is True for h in history), "COMMON_HISTORY")
    check(all({"activity_counts", "detail_catalog"} <= set(h["result"]["facts"])
              and h["result"]["facts"]["detail_catalog"].get("full_public_object_ref")
              for h in history), "H4_SCHEMA_CLAIM_CONTRADICTED")

    h2 = read(EPISODES / "form-h2/formation.json")
    h4 = read(EPISODES / "form-h4/formation.json")
    check(h2["parent_sha256"] == freeze["parent_program_digest"] == h4["parent_sha256"], "FORMATION_PARENT")
    raw_h2 = h2["raw_proposals"][0]["payload"]["patches"]
    eligible = {h["incident_id"] for h in history}
    check(h2["raw_proposal_count"] == 1 and len(raw_h2) == 1
          and set(raw_h2[0]["source_incidents"]).isdisjoint(eligible)
          and [r["reason"] for r in h2["proposals"]["rejected"]] == ["PATCH_SOURCE_INCIDENTS"]
          and not h2["local_evaluations"] and h2["allocation"]["status"] == "RETAIN_PARENT", "H2_REJECTION")
    check(h4["raw_proposal_count"] == 0 and h4["raw_proposals"][-1]["payload"]["patches"] == []
          and h4["proposals"]["rejected"] == [] and h4["allocation"]["status"] == "RETAIN_PARENT", "H4_EMPTY")

    t1 = read(EPISODES / "t1-h1/method-transcript.json")
    t2 = read(EPISODES / "t2-h1/method-transcript.json")
    t1_result = read(EPISODES / "t1-h1/episode-result.json")
    t2_result = read(EPISODES / "t2-h1/episode-result.json")
    check(all(x["loaded_program_sha256"] == freeze["parent_program_digest"]
              and x["common_history_sha256"] == freeze["common_history_digest"] for x in (t1, t2)), "SOLVE_PROGRAM_BINDING")
    check(t1["initial_update"]["status"] == "UPDATED" and t1["initial_update"]["initial_verdict"] == "PASS"
          and t1["counts"]["new_numerical_inputs"] == 0 and t1["full_candidates_evaluated"] == 0
          and t1_result["last_public_check"]["verdict"] == "PASS" and not t1_result["actions"], "DOOR_CORRECT_STOP")
    batch = t2["full_candidate_evaluations"]
    rows = [r for item in batch for r in item["result_bindings"]]
    received = [r["public_check"]["received_count"] for r in rows]
    check(t2["initial_update"]["status"] == "UPDATED" and t2["initial_update"]["initial_verdict"] == "FAIL"
          and t2["full_candidates_evaluated"] == 4 and len(rows) == 4
          and received == [455, 405, 618, 1288]
          and all(r["model_valid"] is True and r["public_check"]["verdict"] == "FAIL" for r in rows)
          and t2["counts"]["new_numerical_inputs"] == 4, "LC_FOUR_COMPLETE_FAILURES")
    selected = t2["steps"][0]["select"]
    action = t2_result["actions"][0]
    check(selected["selected_id"] == action["selected_id"] == "joint-contrast"
          and selected["pre_evaluation"]["result_sha256"] == rows[3]["result_sha256"]
          and selected["pre_evaluation"]["public_object_ref"] == rows[3]["public_object_ref"]
          and action["new_full_dynamic_inputs"] == 0
          and t2_result["last_public_check"]["verdict"] == "FAIL", "SELECTED_EXACT_REUSE")
    check(t2["final_state"]["strategy"]["bold_gsu"]["failure_branch"] == "STARTUP_OR_SOURCE", "LC_UPDATE_BRANCH")
    index = read(EPISODES / "t2-h1/public-objects/index.json")
    initial_ref = t2["final_state"]["strategy"]["bold_gsu"]["recent_outcomes"][0]["public_object_ref"]
    initial_public = read(Path(index["objects"][initial_ref]["path"]))
    activity = [r.get("action") for r in initial_public["facts"]["activity"]]
    check(initial_public["public_check"]["received_count"] == 1155
          and "phase_begin" in activity and "boot" not in activity, "LC_ACTIVITY_VOCABULARY")

    ledger = read(S0 / "resource-ledger.json")
    check(ledger["full_dynamic_inputs"] == 14 and ledger["candidate_evaluations"] == 14
          and ledger["cache_reuses"] == 0 and 57.12 < ledger["full_dynamic_wall_s"] < 57.13,
          "PACKAGE_RESOURCE_LEDGER")
    check(sum(read(EPISODES / (name + "/episode-result.json"))["accounting"]["requests"]
              for name in ("form-h2", "form-h4")) == 3,
          "THREE_FORMATION_REQUESTS")
    batch_result = read(S0 / "batch-result.json")
    rows_by_episode = {row["episode"]: row for row in batch_result["rows"]}
    for name in ("t1-h2", "t1-h4", "t2-h2", "t2-h4"):
        check(rows_by_episode[name]["status"] == "NOT_EXECUTED_NO_QUALIFIED_DESCENDANT",
              "DESCENDANT_CELL:" + name)

    papers = {}
    for name, (prefix_size, prefix_hash) in PREFIXES.items():
        path = PAPERS / name
        body = path.read_bytes()
        check(hashlib.sha256(body[:prefix_size]).hexdigest() == prefix_hash, "PAPER_PREFIX:" + name)
        check(body[prefix_size:].count(b"**Executable parent") +
              body[prefix_size:].count(b"**Frozen joint-design") == 1, "ONE_APPEND_PARAGRAPH:" + name)
        papers[name] = {**bind(path), "preserved_prefix_bytes": prefix_size,
                        "preserved_prefix_sha256": prefix_hash}

    source_paths = {
        "A_engineering_results": PACKAGE / "a/ENGINEERING-RESULTS.json",
        "B_parent": HERE / "parent-program.json", "B_history": HERE / "common-history.json",
        "B_catalog": HERE / "public-source-catalog.json", "B_freeze": HERE / "FREEZE-RECEIPT.json",
        "H2_formation": EPISODES / "form-h2/formation.json",
        "H4_formation": EPISODES / "form-h4/formation.json",
        "DOOR_H1_transcript": EPISODES / "t1-h1/method-transcript.json",
        "LC_H1_transcript": EPISODES / "t2-h1/method-transcript.json",
        "LC_initial_public": Path(index["objects"][initial_ref]["path"]),
        "LC_selected_public": EPISODES / "t2-h1/candidates/04/public-result.json",
        "S0_batch": S0 / "batch-result.json", "S0_resources": S0 / "resource-ledger.json",
        "B_review": HERE / "FINAL-REVIEW.md",
        "B_parent_source": SOURCE / "parent.py", "B_contract_source": SOURCE / "contracts.py",
        "B_driver_source": SOURCE / "drivers.py",
    }
    receipt = {
        "schema": "bold-B-final-review-receipt-v1",
        "package": "BF-PQE-BOLD-INTERVENTIONS-20261023-001",
        "status": "INDEPENDENT_PUBLIC_READBACK_PASS",
        "checks": ["frozen_parent_history", "H2_invalid_source_incident_ids",
                   "H4_legal_empty_and_schema_misread", "DOOR_initial_PASS_correct_stop",
                   "LC_four_model_valid_service_FAIL", "selected_exact_reuse",
                   "LC_activity_vocabulary_mismatch", "four_descendant_cells_not_executed",
                   "ledger_14_full_three_settled_formation_requests", "two_manuscript_prefixes_preserved"],
        "outcome": {"parent_program_digest": freeze["parent_program_digest"],
                    "common_history_digest": freeze["common_history_digest"],
                    "H2": "ONE_RAW_PROPOSAL_REJECTED_PATCH_SOURCE_INCIDENTS",
                    "H4": "LEGAL_EMPTY_PATCHES", "new_DOOR_H1": "INITIAL_PASS_CORRECT_STOP_NO_ACTION",
                    "new_LC_H1": "FOUR_MODEL_VALID_CANDIDATES_ALL_SERVICE_FAIL",
                    "qualified_descendants": 0},
        "resources": {"full_dynamic_inputs_total": 14,
                      "full_dynamic_wall_s": ledger["full_dynamic_wall_s"],
                      "settled_formation_model_requests": 3,
                      "B_added_model_requests": 0, "B_added_numerical_inputs": 0,
                      "B_added_cheap_scores": 0},
        "source_bindings": {key: bind(path) for key, path in source_paths.items()},
        "papers": papers,
        "claim_boundary": "Manual engineering PASSes and parent hook execution are separate from automatic H learning. No child or two-task child benefit was observed.",
    }
    output = HERE / "FINAL-RECEIPT.json"
    body = (json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    if output.exists() and output.read_bytes() != body:
        raise RuntimeError("FINAL_RECEIPT_DIFFERS")
    if not output.exists():
        output.write_bytes(body)
    print(json.dumps({"status": receipt["status"], "receipt": bind(output),
                      "paper_sha256": {k:v["sha256"] for k,v in papers.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
