"""Read completed finite outputs only; never dispatch a model or scientific run."""
from collections import Counter
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import decision as d


def collect():
    protocol = d.read(d.PROTOCOL)
    registry = d.configure(protocol)
    batch = d.read(d.OUT / "s0/batch-result.json")
    if batch["status"] != "FINITE_DECISION_COMPLETE" or len(batch["episodes"]) != 6:
        raise ValueError("SIX_FINITE_EPISODES_NOT_COMPLETE")
    shared = d.read(d.STUDY / "shared/common-history.json")
    result = {"package": d.PACKAGE, "status": "FINITE_COMPARISON_COMPLETE",
              "protocol": d.binding(d.PROTOCOL), "episodes": [],
              "shared_initial_new_inputs": registry["new_initial_inputs"]}
    for row in batch["episodes"]:
        root = d.OUT / "s0/episodes" / row["episode"]
        transcript = d.read(root / "method-transcript.json")
        if transcript["initial_state"]["history"][:len(shared)] != shared:
            raise ValueError("COMMON_PUBLIC_HISTORY_CHANGED")
        candidates, first_pass = [], None
        for action in row["actions"]:
            public = d.read(Path(action["path"]) / "public-result.json")
            if action["candidate_evaluation"]:
                candidates.append({"number": len(candidates) + 1,
                    "actual_input": action["actual_input"], "model_valid": public["model_valid"],
                    "domain_errors": public.get("domain_errors", []),
                    "service": public["public_check"], "usage": action["usage"],
                    "public_result": d.binding(Path(action["path"]) / "public-result.json")})
                if first_pass is None and public["model_valid"] is True and public["public_check"]["verdict"] == "PASS":
                    first_pass = len(candidates)
        costs = d.read(root / "provider-costs.json")
        tokens = Counter()
        for entry in costs["rows"]:
            if entry["status"] != "SETTLED" or not entry["usage"]:
                raise ValueError("NEW_UNSETTLED_OR_MISSING_USAGE")
            usage = json.loads(entry["usage"])
            tokens.update({"input": usage["prompt_tokens"], "output": usage["completion_tokens"]})
        sites = Counter(c["request"]["site"] for c in transcript["callback_records"])
        last = candidates[-1] if candidates else None
        false_adoption = bool(row.get("method_conclusion", {}).get("verdict") == "PASS" and
            (not last or last["model_valid"] is not True or last["service"]["verdict"] != "PASS"))
        result["episodes"].append({"episode": row["episode"], "condition": row["condition"],
            "task_id": row["task_id"], "candidates": candidates,
            "evaluated_candidates_including_cache": len(candidates), "first_feasible_evaluation": first_pass,
            "new_scientific_inputs": row["actual_new_numerical_inputs"],
            "exact_result_reuses": sum(bool(a["usage"].get("reused")) for a in row["actions"]),
            "invalid_domain_evaluations": sum(c["model_valid"] is not True for c in candidates),
            "false_adoption": false_adoption, "last_service": row["last_public_service"],
            "requests": costs["requests"], "cost_estimate_usd": costs["cache_aware_rate_estimate_usd"],
            "tokens": dict(tokens), "callback_sites": dict(sites), "wall_s": row["wall_s"],
            "termination": row["termination"], "actual_tools": row["actual_tools"],
            "method_version": transcript["decision_method_version"],
            "consumed_rules": transcript["decision_consumption"],
            "output": d.binding(root / "episode-result.json")})
    episodes = result["episodes"]
    result["totals"] = {
        "episodes": len(episodes), "requests": sum(e["requests"] for e in episodes),
        "evaluated_candidates_including_cache": sum(len(e["candidates"]) for e in episodes),
        "new_scientific_inputs": registry["new_initial_inputs"] + sum(e["new_scientific_inputs"] for e in episodes),
        "exact_result_reuses": sum(e["exact_result_reuses"] for e in episodes),
        "invalid_domain_evaluations": sum(e["invalid_domain_evaluations"] for e in episodes),
        "false_adoption": sum(e["false_adoption"] for e in episodes),
        "cost_estimate_usd": sum(e["cost_estimate_usd"] for e in episodes),
        "input_tokens": sum(e["tokens"]["input"] for e in episodes),
        "output_tokens": sum(e["tokens"]["output"] for e in episodes),
        "provider_usage": "All new requests KNOWN and SETTLED; rate estimates are not invoices."}
    result["interpretation"] = "All groups share completed exposed development history and new public cheap facts. Separate saved-state engineering-action deltas, shared-information effects, deterministic rank/stop overhead, and exact-cache order. No learning, unseen transfer or statistical claim."
    return result


if __name__ == "__main__":
    summary = collect()
    d.p.save(d.OUT / "s0/FINITE-SUMMARY.json", summary)
    print(json.dumps(summary["totals"], ensure_ascii=False))
