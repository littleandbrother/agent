"""Analyze only S0-indexed sealed public episodes; reuse prior readback."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[5]
BDIR = Path(__file__).resolve().parent
OUT = BDIR.parent
SUCCESS = {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}


def read(path):
    path = Path(path).resolve()
    if any(p in {"private", "lcpv-private"} for p in path.parts):
        raise ValueError("PRIVATE_READ_FORBIDDEN")
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def pass_result(result):
    return result.get("execution_status") in SUCCESS and result.get("model_valid") is True and result.get("public_check", {}).get("verdict") == "PASS"


def result_summary(result):
    keys = ("execution_status", "model_valid", "domain_errors", "design", "problem", "public_check", "usage", "result_sha256", "input_sha256")
    out = {k: result.get(k) for k in keys}
    # Keep public aggregate facts; raw event arrays remain at their bound sources.
    out["facts"] = {k:v for k,v in result.get("facts", {}).items() if k not in {"trace", "activity", "records", "packets", "receiver_records"}}
    return out


def analyze(entry):
    documents = {}
    for ref in entry["files"]:
        path = Path(ref["path"])
        if path.name not in {"episode-result.json", "method-transcript.json", "public-compact.json"}:
            raise ValueError("NOT_APPROVED_PUBLIC_FILENAME")
        value, actual = read(path)
        if actual != ref["sha256"]:
            raise ValueError("SEALED_PUBLIC_FILE_CHANGED")
        documents[str(path)] = value
    episode_path = next(p for p in documents if p.endswith("/episode-result.json"))
    transcript_path = next(p for p in documents if p.endswith("/method-transcript.json"))
    ep, t = documents[episode_path], documents[transcript_path]
    calls = [{"site":r["request"]["site"], "instruction":r["request"].get("instruction"),
              "json_instructions":r["request"].get("json_instructions"),
              "state_history_count":len(r["request"]["context"].get("state", {}).get("history", [])),
              "request_sha256":r["request_sha256"], "response":r.get("response"),
              "consumed_payload":r.get("consumed_payload")} for r in t.get("callback_records", [])]
    steps = []
    initial = t["initial_state"]
    first = None
    evaluations = new_inputs = cache = 0
    for s in t.get("steps", []):
        result = s.get("result")
        selected = s.get("select") or {}
        actual = selected.get("actual_input") or {}
        item = {k:s.get(k) for k in ("step", "generate", "select", "update", "scope_effect", "pre_action_predictions", "contract_feedback")}
        item["state_before"] = {k:s["state_before"].get(k) for k in ("design", "problem", "hypotheses", "invalidated")}
        item["history_count_before"] = len(s["state_before"].get("history", []))
        item["result"] = result_summary(result) if result else None
        if result:
            normal = result.get("execution_status") in SUCCESS
            before_design = s["state_before"].get("design", {})
            after_design = result.get("design", {})
            changed = [k for k in actual.get("design_patch", {}) if before_design.get(k) != after_design.get(k)]
            item["actual_changed_design_keys"] = changed if normal else []
            before_problem, after_problem = s["state_before"].get("problem", {}), result.get("problem", {})
            item["consumed_scope_changed"] = normal and (set(before_problem.get("active_variables", [])) != set(after_problem.get("active_variables", [])) or before_problem.get("fixed_choices", {}) != after_problem.get("fixed_choices", {}))
            item["changed_edit_outside_original_cap_esr_scope"] = sorted(set(changed)-{"capacitance_f", "esr_ohm"}) if normal else []
            evaluation = actual.get("operation") not in {"report", "select"} and not selected.get("selected_candidate", {}).get("target", "").startswith("detail:") and result.get("execution_status") != "NO_EXECUTION"
            evaluations += bool(evaluation)
            new_inputs += result.get("usage", {}).get("numerical_inputs", 0)
            cache += bool(evaluation and result.get("usage", {}).get("reused"))
            if first is None and pass_result(result):
                hist = item["history_count_before"]
                through = [c for c in calls if c["state_history_count"] <= hist]
                usages = [c.get("response", {}).get("usage", {}) for c in through]
                known = all(u.get("status") == "KNOWN" and isinstance(u.get("cost"), (int,float)) for u in usages)
                first = {"step":s["step"], "model_requests":sum(len(u.get("request_ids", [])) for u in usages),
                         "estimated_usd":sum(u["cost"] for u in usages) if known else None,
                         "candidate_evaluations_including_cache":evaluations, "new_scientific_inputs":new_inputs, "exact_reuses":cache}
        steps.append(item)
    return {"episode":entry["episode"], "condition":entry["condition"], "independent_context":entry.get("independent_context"),
            "source_files":entry["files"], "episode_result":ep, "initial_design":initial["design"], "initial_problem":initial["problem"],
            "initial_result":result_summary(initial.get("last_result", {})), "steps":steps, "callback_records":calls,
            "contract_corrections":t.get("contract_corrections"), "e3lc_policy":t.get("e3lc_policy"),
            "termination":t.get("termination"), "model_conclusion":t.get("model_conclusion"),
            "model_identity":t.get("model_identity"), "generated_code_loaded":t.get("generated_code_loaded"),
            "first_feasible":first, "counts":{"candidate_evaluations_including_cache":evaluations,"new_scientific_inputs":new_inputs,"exact_reuses":cache},
            "public_action_results":[{"source":p,"result":result_summary(value)} for p,value in documents.items() if p.endswith("/public-compact.json")]}


def main():
    index_path = Path(sys.argv[1]) if len(sys.argv)>1 else OUT/"s0/public-episode-index.json"
    index, index_hash = read(index_path)
    dest = BDIR/"PUBLIC-READBACK.json"
    old = read(dest)[0] if dest.exists() else {"episodes":[]}
    cached = {r["episode"]:r for r in old["episodes"]}
    fresh = 0
    for entry in index["public_completed_episodes"]:
        if entry["episode"] in cached:
            if cached[entry["episode"]]["source_files"] != entry["files"]:
                raise ValueError("PREVIOUS_READBACK_SOURCE_BINDINGS_CHANGED")
        else:
            cached[entry["episode"]] = analyze(entry)
            fresh += 1
    value = {"package":index["package"], "source_index":{"path":str(index_path),"sha256":index_hash},
             "index_status":index.get("status"), "episodes":list(cached.values()),
             "read_boundary":"Sealed indexed public files only. Cached prior episodes not reread. No raw/assessment/private/LC host reads."}
    dest.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"episodes":len(cached),"new_public_episodes_read":fresh,"bytes":dest.stat().st_size},ensure_ascii=False))


if __name__ == "__main__":
    main()
