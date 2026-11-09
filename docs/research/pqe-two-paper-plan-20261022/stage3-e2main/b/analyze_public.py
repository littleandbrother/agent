"""Read saved public E2MAIN facts; no runtime imports or experiment dispatch."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[5]
PLAN = ROOT / "docs/research/pqe-two-paper-plan-20261022"
OUT = PLAN / "stage3-e2main"
BDIR = OUT / "b"
BASE = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
COND = BASE / "studies/pqe20261022/e2main/shared/conditions.json"


def read(path):
    path = Path(path).resolve()
    if any(part in {"private", "lcpv-private"} for part in path.parts):
        raise ValueError("B_PRIVATE_READ_FORBIDDEN")
    return json.loads(path.read_text())


def binding(path):
    path = Path(path)
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def valid_pass(result):
    return (result.get("execution_status") in {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}
            and result.get("model_valid") is True
            and result.get("public_check", {}).get("verdict") == "PASS")


def numeric_resources(results):
    return {"candidate_evaluations_including_cache": sum(
                x.get("_b_evaluation", False) and x.get("execution_status") != "NO_EXECUTION" for x in results),
            "new_scientific_inputs": sum(x.get("usage", {}).get("numerical_inputs", 0) for x in results),
            "exact_result_reuses": sum(x.get("_b_evaluation", False) and bool(x.get("usage", {}).get("reused")) for x in results),
            "all_broker_reuses_including_detail": sum(bool(x.get("usage", {}).get("reused")) for x in results)}


def analyze(row, condition):
    ident = row["episode"]
    folder = OUT / "s0/episodes" / ident
    tp = folder / "method-transcript.json"
    if not tp.exists():
        return {**{k: row.get(k) for k in ("episode", "role", "condition", "independent_context", "status", "reason")},
                "executed": False, "source": binding(OUT / "s0/batch-result.json")}
    t = read(tp)
    initial = t["initial_state"].get("last_result", {})
    initial_pass = valid_pass(initial)
    results, actions = [], []
    first_step = None
    for s in t.get("steps", []):
        r = s.get("result")
        if not r:
            continue
        selected = (s.get("select") or {}).get("selected_candidate", {})
        actual = (s.get("select") or {}).get("actual_input", {})
        results.append({**r, "_b_step": s["step"], "_b_evaluation": actual.get("operation") not in {"report", "select"} and not selected.get("target", "").startswith("detail:")})
        actions.append({"step": s["step"], "selected_id": (s.get("select") or {}).get("selected_id"),
                        "actual_input": (s.get("select") or {}).get("actual_input"),
                        "service": r.get("public_check"), "execution_status": r.get("execution_status"),
                        "model_valid": r.get("model_valid"), "usage": r.get("usage"),
                        "scope_effect": s.get("scope_effect"), "prediction": selected.get("prediction_or_unknown"),
                        "observation_branches": selected.get("observation_branches"), "target": selected.get("target"),
                        "update": s.get("update"), "generated_candidates": (s.get("generate") or {}).get("candidates", [])})
        if first_step is None and valid_pass(r):
            first_step = s
    first = None
    if initial_pass:
        first = {"origin": "INITIAL_ALREADY_PASS", "model_requests": 0, "estimated_usd": 0,
                 "candidate_evaluations_including_cache": 0, "new_scientific_inputs": 0, "exact_result_reuses": 0}
    elif first_step is not None:
        h = len(first_step["state_before"].get("history", []))
        # Default programs have no model UPDATE. Each completed action adds one
        # history record. Include syntax/contract corrections before this result.
        callbacks = [c for c in t.get("callback_records", [])
                     if len(c["request"]["context"].get("state", {}).get("history", [])) <= h]
        if any(c["request"]["site"] == "H-UPDATE" for c in callbacks):
            raise ValueError("DEFAULT_UPDATE_MODEL_CALL_UNEXPECTED")
        usage = [c.get("response", {}).get("usage", {}) for c in callbacks]
        known = all(u.get("status") == "KNOWN" and isinstance(u.get("cost"), (int, float)) for u in usage)
        consumed = [r for r in results if r["_b_step"] <= first_step["step"]]
        first = {"origin": "CONSUMER_CONFIRMED_ACTION", "step": first_step["step"],
                 "model_requests": sum(len(u.get("request_ids", [])) for u in usage),
                 "estimated_usd": sum(u["cost"] for u in usage) if known else None,
                 "cost_boundary": "All callback usage through the first passing consumer result, including corrections; no later stop request.",
                 **numeric_resources(consumed)}
    callbacks = t.get("callback_records", [])
    expected = condition["planner_instruction"]
    consumed_instructions = [c["request"].get("instruction") == expected for c in callbacks]
    final_service = row.get("last_public_service") or (t.get("final_state", {}).get("last_result") or {}).get("public_check")
    conclusion = t.get("model_conclusion") or {}
    return {"episode": ident, "role": row.get("role"), "independent_context": row.get("independent_context"),
            "condition": row["condition"], "executed": True, "status": row.get("status"),
            "initial_service": initial.get("public_check"), "initial_pass": initial_pass,
            "first_feasible": first, "final_service": final_service,
            "full_service_pass": (final_service or {}).get("verdict") == "PASS",
            "termination": t.get("termination"), "error": row.get("error"), "fatal": row.get("fatal"),
            "model_conclusion": conclusion,
            "false_pass_adoption": conclusion.get("verdict") == "PASS" and (final_service or {}).get("verdict") != "PASS",
            "global_exclusion_manual_review": conclusion.get("verdict") == "FAIL",
            "accounting": row.get("accounting"), "resources": numeric_resources(results),
            "count_boundary": "Result-level evaluations include repeated cached results; detail/report/select and NO_EXECUTION excluded. Host reserved attempts and tool errors remain separate.",
            "host_counts": {k: row.get(k) for k in ("actual_tools", "actual_new_numerical_inputs", "distinct_attempted_designs", "candidate_evaluations")},
            "request_sites": {site: sum(c["request"]["site"] == site for c in callbacks) for site in sorted({c["request"]["site"] for c in callbacks})},
            "frozen_instruction_consumed_all_requests": bool(callbacks) and all(consumed_instructions),
            "formed_program_loaded": t.get("generated_code_loaded"), "h_g_formation": t.get("h_g_formation"),
            "actions": actions, "source": binding(tp)}


def main():
    first_block = "--first-block" in sys.argv
    batch_path = OUT / ("s0/first-task-block.json" if first_block else "s0/batch-result.json")
    if not batch_path.exists():
        raise SystemExit("No saved E2MAIN batch-result yet; no analysis result written.")
    batch, cond = read(batch_path), read(COND)
    cached_path = BDIR / "FIRST-BLOCK-READBACK.json"
    cached = {} if first_block or not cached_path.exists() else {r["episode"]: r for r in read(cached_path)["episodes"]}
    rows = []
    for r in batch["episodes"]:
        prior = cached.get(r["episode"])
        if prior is not None:
            if (prior["final_service"] != r.get("last_public_service") or prior["accounting"] != r.get("accounting")
                    or prior["termination"] != r.get("termination")):
                raise ValueError("FIRST_BLOCK_CACHE_DIFFERS_FROM_FINAL_BATCH")
            rows.append(prior)
        else:
            rows.append(analyze(r, cond["conditions"][r["condition"]]))

    out = {"package": cond["package"], "batch_status": batch.get("status"),
           "source_batch": binding(batch_path), "conditions": binding(COND), "episodes": rows,
           "totals": batch.get("totals"),
           "claim_boundary": "Saved public artifacts only; partial matrices remain partial. D16 and initial-pass controls separate. No new science or H/G learning."}
    aggregate = {}
    for name, spec in cond["conditions"].items():
        rs = [r for r in rows if r.get("executed") and r["condition"] == name]
        repair = [r for r in rs if r["initial_service"].get("verdict") == "FAIL"]
        control = [r for r in rs if r["initial_pass"]]
        aggregate[spec["label"]] = {"condition": name, "episodes": len(rs),
            "initial_failure_repairs_passed": sum(r["full_service_pass"] for r in repair),
            "initial_failure_episodes": len(repair),
            "initial_pass_controls_retained": sum(r["full_service_pass"] for r in control),
            "initial_pass_episodes": len(control),
            "requests": sum((r.get("accounting") or {}).get("requests", 0) for r in rs),
            "estimated_usd": sum((r.get("accounting") or {}).get("settled_charge_upper_bound_usd", 0) for r in rs),
            "candidate_evaluations_including_cache": sum(r["resources"]["candidate_evaluations_including_cache"] for r in rs),
            "new_scientific_inputs": sum(r["resources"]["new_scientific_inputs"] for r in rs),
            "exact_result_reuses": sum(r["resources"]["exact_result_reuses"] for r in rs),
            "false_pass_adoptions": sum(r["false_pass_adoption"] for r in rs),
            "global_fail_conclusions_for_manual_review": sum(r["global_exclusion_manual_review"] for r in rs)}
    out["condition_aggregates"] = aggregate
    out["prior_first_block_readback_reused"] = binding(cached_path) if cached else None
    dest = BDIR / ("FIRST-BLOCK-READBACK.json" if first_block else "PUBLIC-READBACK.json")
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    table = ["# Saved public E2MAIN paired cells", "", "Partial matrices remain partial; D10/D16 initial-pass controls are separate from repairs.", "",
             "|Cell|Initial|Final|First feasible requests / USD|Evaluations / new / cache|Total requests / USD|Stop|",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r.get("executed"):
            table.append(f"|{r['episode']}|—|{r.get('status')}|—|—|—|—|")
            continue
        first, a, n = r["first_feasible"], r.get("accounting") or {}, r["resources"]
        fv = "—" if first is None else f"{first['model_requests']} / {first['estimated_usd']:.7f}" if first["estimated_usd"] is not None else "usage unknown"
        table.append(f"|{r['episode']}|{r['initial_service'].get('verdict')}|{(r['final_service'] or {}).get('verdict')}|{fv}|{n['candidate_evaluations_including_cache']} / {n['new_scientific_inputs']} / {n['exact_result_reuses']}|{a.get('requests', 0)} / {a.get('settled_charge_upper_bound_usd', 0):.7f}|{(r['termination'] or {}).get('reason')}|")
    (BDIR / ("FIRST-BLOCK-TABLE.md" if first_block else "PAIRED-CELLS.md")).write_text("\n".join(table) + "\n")
    print(json.dumps({"result": str(dest), "episodes": len(rows), "executed": sum(r["executed"] for r in rows), "batch_status": out["batch_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
