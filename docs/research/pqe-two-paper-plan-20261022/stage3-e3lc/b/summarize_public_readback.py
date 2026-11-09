"""Summarize cached public facts without importing or running the apparatus."""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import hashlib
import json

BDIR = Path(__file__).resolve().parent
CONDITIONS = (
    "strong_generic", "full_h", "full_h_no_active_reform",
    "strong_generic_scope_matched",
)
NORMAL = {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}


def usd(values):
    return format(sum((Decimal(str(v)) for v in values), Decimal(0)).quantize(Decimal("0.0000001")), ".7f")


def changed_leaves(before, after, prefix=""):
    out = {}
    for key in sorted(set(before) | set(after)):
        name = f"{prefix}.{key}" if prefix else key
        a, b = before.get(key), after.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            out.update(changed_leaves(a, b, name))
        elif a != b:
            out[name] = {"before": a, "after": b}
    return out


def main():
    source = BDIR / "PUBLIC-READBACK.json"
    raw = source.read_bytes()
    data = json.loads(raw)
    rows = []
    for e in data["episodes"]:
        ep = e["episode_result"]
        if e["condition"] not in CONDITIONS:
            raise ValueError("NOT_DOOR_COMPARISON_CONDITION")
        actions = []
        errors = Counter()
        for s in e["steps"]:
            r = s.get("result")
            if not r:
                continue
            normal = r.get("execution_status") in NORMAL
            changes = changed_leaves(s["state_before"]["design"], r.get("design", {})) if normal else {}
            for err in r.get("domain_errors") or []:
                errors[err if isinstance(err, str) else json.dumps(err, sort_keys=True)] += 1
            actions.append({
                "step": s["step"],
                "generated_candidate_count": len((s.get("generate") or {}).get("candidates", [])),
                "selected_id": ((s.get("select") or {}).get("selected_candidate") or {}).get("id"),
                "selected_prediction": [p.get("prediction_or_unknown") for p in s.get("pre_action_predictions") or [] if p.get("candidate_id") == ((s.get("select") or {}).get("selected_candidate") or {}).get("id")],
                "operation": (s.get("select") or {}).get("actual_input", {}).get("operation"),
                "execution_status": r.get("execution_status"),
                "model_valid": r.get("model_valid"),
                "public_check": r.get("public_check"),
                "design_changes": changes,
                "scope_effect": s.get("scope_effect"),
                "consumed_scope_changed": s.get("consumed_scope_changed", False),
                "prediction_update": s.get("update"),
            })
        count = e["counts"]
        if count["new_scientific_inputs"] != ep["actual_new_numerical_inputs"]:
            raise ValueError("SCIENTIFIC_INPUT_ACCOUNTING_MISMATCH")
        accounting = ep["accounting"]
        rows.append({
            "episode": e["episode"], "condition": e["condition"],
            "independent_context": e.get("independent_context"),
            "last_public_service": ep["last_public_service"],
            "first_feasible": e["first_feasible"],
            "total_model_requests": accounting["requests"],
            "estimated_usd": accounting["cache_aware_rate_estimate_usd"],
            "unknown_or_missing_usage": accounting["unknown_or_missing_usage"],
            "unsettled_reserved_usd": accounting["unsettled_reserved_usd"],
            "counts": count, "actual_tools": ep["actual_tools"],
            "domain_errors": dict(errors),
            "contract_corrections": e.get("contract_corrections"),
            "no_active_reform_consumed_deviations": e["e3lc_policy"]["no_active_reform_consumed_deviations"],
            "initial_problem": e["initial_problem"],
            "actions": actions, "termination": e["termination"],
            "model_conclusion": e["model_conclusion"],
        })
    totals = {}
    for c in CONDITIONS:
        selected = [r for r in rows if r["condition"] == c]
        totals[c] = {
            "episodes": len(selected),
            "pass": sum(r["last_public_service"]["verdict"] == "PASS" for r in selected),
            "total_model_requests": sum(r["total_model_requests"] for r in selected),
            "estimated_usd": usd(r["estimated_usd"] for r in selected),
            **{k: sum(r["counts"][k] for r in selected) for k in ("candidate_evaluations_including_cache", "new_scientific_inputs", "exact_reuses")},
            "first_feasible_model_requests": sum(r["first_feasible"]["model_requests"] for r in selected if r["first_feasible"]) if any(r["first_feasible"] for r in selected) else None,
            "first_feasible_estimated_usd": usd(r["first_feasible"]["estimated_usd"] for r in selected if r["first_feasible"]) if any(r["first_feasible"] for r in selected) else None,
            "first_feasible_episode_count": sum(r["first_feasible"] is not None for r in selected),
        }
    result = {
        "source_readback_sha256": hashlib.sha256(raw).hexdigest(),
        "source_index": data["source_index"], "index_status": data["index_status"],
        "episodes": rows, "condition_totals": totals,
        "totals": {
            "episodes": len(rows),
            "model_requests": sum(r["total_model_requests"] for r in rows),
            "estimated_usd": usd(r["estimated_usd"] for r in rows),
            "unknown_or_missing_usage": [u for r in rows for u in r["unknown_or_missing_usage"]],
            "unsettled_reserved_usd": sum(r["unsettled_reserved_usd"] for r in rows),
            "actual_tools": sum(r["actual_tools"] for r in rows),
            **{k: sum(r["counts"][k] for r in rows) for k in ("candidate_evaluations_including_cache", "new_scientific_inputs", "exact_reuses")},
        },
        "interpretation": "One exposed mechanism task, repeated independent model contexts; no population estimate. First-feasible totals are conditional on successful episodes and must be reported with their denominator. All USD figures are pinned-rate estimates, not invoices.",
    }
    dest = BDIR / "DOOR-SUMMARY.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"episodes": len(rows), "condition_totals": totals, "summary_sha256": hashlib.sha256(dest.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
