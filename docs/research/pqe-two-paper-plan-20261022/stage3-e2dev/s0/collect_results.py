"""Read-only replay of the sealed finite packet; no provider or scientific calls."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

OUT = Path(__file__).resolve().parent
PACKAGE = "BF-PQE-S3-E2DEV-20261023-001"


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def delta(before, after):
    return {k: {"before": before.get(k), "after": after.get(k)}
            for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)}


def main():
    batch = read(OUT / "batch-result.json")
    assert batch["package"] == PACKAGE
    assert len(batch["episodes"]) == 12
    assert len({r["episode"] for r in batch["episodes"]}) == 12
    state = read(OUT.parents[1] / "execution-state.json")
    assert sha(state["protocol"]["path"]) == state["protocol"]["sha256"]
    protocol = read(state["protocol"]["path"])
    assert [r["episode"] for r in batch["episodes"]] == [r[0] for r in protocol["cells"]]
    rows = []
    for item in batch["episodes"]:
        root = OUT / "episodes" / item["episode"]
        if not (root / "episode-result.json").exists():
            rows.append({**item, "actual_execution": False})
            continue
        result = read(root / "episode-result.json")
        transcript = read(root / "method-transcript.json")
        initial = transcript["initial_state"]
        actions = []
        previous_problem = initial["problem"]
        for action in result["actions"]:
            directory = Path(action["path"])
            public_path = directory / "public-result.json"
            public = read(public_path)
            reuse = directory / "reused.json"
            consumed = public["execution_status"] not in {"NO_EXECUTION", "TOOL_ERROR"}
            problem_change = delta(previous_problem, public["problem"]) if consumed else {}
            permission_change = consumed and (
                set(previous_problem["active_variables"]) != set(public["problem"]["active_variables"])
                or previous_problem["fixed_choices"] != public["problem"]["fixed_choices"])
            actions.append({
                "number": action["number"], "operation": action["operation"],
                "actual_input": action["actual_input"],
                "execution_status": public["execution_status"],
                "model_valid": public.get("model_valid"),
                "public_check": public["public_check"], "usage": public["usage"],
                "result_sha256": public.get("result_sha256"),
                "consumed_problem_delta": problem_change,
                "scope_permission_changed": permission_change,
                "public_path": str(public_path), "public_file_sha256": sha(public_path),
                "reused_source": read(reuse) if reuse.exists() else None,
                "raw_path": str(directory / "raw.json") if (directory / "raw.json").exists() else None,
            })
            if consumed:
                previous_problem = public["problem"]
        rows.append({
            "episode": result["episode"], "task_id": result["task_id"],
            "condition": result["condition"], "owner": result["owner"],
            "status": result["status"], "error": result["error"], "fatal": result["fatal"],
            "termination": transcript["termination"], "wall_s": result["wall_s"],
            "design_delta": delta(initial["design"], result["last_design"]),
            "problem_delta": delta(initial["problem"], result["last_problem"]),
            "scope_permissions_changed": (
                any(a["scope_permission_changed"] for a in actions)),
            "actual_tools": result["actual_tools"],
            "evaluated_candidates_including_cache": result["distinct_attempted_designs"],
            "new_numerical_inputs": result["actual_new_numerical_inputs"],
            "exact_cache_hits": sum(bool(a["usage"].get("reused")) for a in actions),
            "last_applicable_public_service": result["last_public_service"],
            "literal_last_control_or_scientific_service": actions[-1]["public_check"] if actions else None,
            "domain_unknown_actions": [a["number"] for a in actions if "MODEL_DOMAIN" in a["public_check"].get("unknown", [])],
            "actions": actions, "accounting": result["accounting"],
            "tool_error_artifacts": [{"path": str(p), "sha256": sha(p)}
                                     for p in sorted((root / "tool-errors").glob("*.json"))],
            "correction_feedback_count": len(transcript["contract_corrections"]["feedback"]),
            "hypotheses": transcript["final_state"].get("hypotheses", []),
            "model_self_assessment": result["method_conclusion"],
            "output_tokens": transcript["output_budget"]["used"],
            "model_callback_sites": [c["request"]["site"] for c in transcript["callback_records"]],
            "episode_result": {"path": str(root / "episode-result.json"), "sha256": sha(root / "episode-result.json")},
            "method_transcript": {"path": str(root / "method-transcript.json"), "sha256": sha(root / "method-transcript.json")},
        })
    actual = [r for r in rows if "accounting" in r]
    totals = {
        "cells": len(rows), "actual_episode_attempts": len(actual),
        "unexecuted_cells": len(rows) - len(actual),
        "requests": sum(r["accounting"]["requests"] for r in actual),
        "tools": sum(r["actual_tools"] for r in actual),
        "episode_new_numerical_inputs": sum(r["new_numerical_inputs"] for r in actual),
        "shared_initial_new_numerical_inputs": batch["shared_initial_numerical_inputs"],
        "exact_cache_hits": sum(r["exact_cache_hits"] for r in actual),
        "scope_permission_change_episodes": [r["episode"] for r in actual if r["scope_permissions_changed"]],
        "estimated_usd": round(sum(r["accounting"]["cache_aware_rate_estimate_usd"] for r in actual), 12),
        "correction_feedback_count": sum(r["correction_feedback_count"] for r in actual),
        "domain_unknown_actions": sum(len(r["domain_unknown_actions"]) for r in actual),
        "model_UPDATE_calls": sum(r["model_callback_sites"].count("H-UPDATE") for r in actual),
    }
    assert totals["requests"] == batch["actual_requests"]
    assert totals["episode_new_numerical_inputs"] == batch["actual_new_numerical_inputs"]
    output = OUT / "RESULTS.json"
    assert not output.exists(), "One canonical final result; do not create preview revisions"
    output.write_text(json.dumps({
        "package": PACKAGE, "collected_at": datetime.now(timezone.utc).isoformat(),
        "collector_sha256": sha(__file__), "batch_result_sha256": sha(OUT / "batch-result.json"),
        "totals": totals, "episodes": rows,
        "claim_boundary": "Known development tasks, one attempt per task/condition. Shared exact scientific inputs are not independent physical repetitions. Model self-assessments remain separate from independent A readback. No H/G learning or hardware execution.",
    }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(totals, ensure_ascii=False))


if __name__ == "__main__":
    main()
