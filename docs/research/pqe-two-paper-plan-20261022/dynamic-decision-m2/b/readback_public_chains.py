"""Read saved M2 public artifacts only; never import or execute the apparatus.

Run with the registered Python and PYTHONDONTWRITEBYTECODE=1. Writes one
compact derived receipt next to this file; private/raw/assessment paths are
never opened. No model, calculator, consumer, provider DB or network access.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
M2 = HERE.parent
S0 = M2 / "s0"
EPISODES = S0 / "episodes"
PACKAGE = "BF-PQE-DYNAMIC-DECISION-M2-20261023-001"


def read(path):
    path = Path(path)
    assert path.name not in {"raw.json", "assessment.json"}
    assert "private" not in path.parts
    return json.loads(path.read_text())


def bind(path):
    path = Path(path)
    assert path.name not in {"raw.json", "assessment.json"}
    assert "private" not in path.parts
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def diff_paths(a, b, prefix=""):
    if type(a) is not type(b):
        return [prefix]
    if isinstance(a, dict):
        return [p for key in sorted(a.keys() | b.keys())
                for p in diff_paths(a.get(key), b.get(key), prefix + "/" + key)]
    if isinstance(a, list):
        if len(a) != len(b):
            return [prefix + "/length"]
        return [p for i, (x, y) in enumerate(zip(a, b))
                for p in diff_paths(x, y, prefix + "/" + str(i))]
    return [] if a == b else [prefix]


def phase_summary(state):
    memory = state["strategy"]["dynamic_repair"]
    phase = memory["phase_facts"]
    return {"memory_canonical_sha256": canonical(memory),
            "phase_canonical_sha256": canonical(phase),
            "failed_phases": phase["failed_phases"],
            "activity_counts": phase["service"]["activity_counts"],
            "public_check": phase["service"]["public_check"],
            "executed_failures": len(memory["executed_failures"]),
            "competing_explanations": phase["competing_explanations"]}


interface = read(HERE / "INTERFACE-RECEIPT.json")
frozen = []
for original in [interface["source"], *interface["frozen_dependencies"],
                 *interface["frozen_scientific_sources"], *interface["bindings"]]:
    current = bind(original["path"])
    assert current == original, ("FROZEN_BINDING_CHANGED", current["path"])
    frozen.append(current)

batch = read(S0 / "batch-result.json")
ledger = read(S0 / "resource-ledger.json")
assert batch["package"] == PACKAGE and batch["error"] is None
assert ledger["full_dynamic_inputs"] == 6 and ledger["initial_inputs"] == 2
assert ledger["cheap_scores"] == 50 and ledger["cache_reuses"] == 4
assert ledger["evaluations_including_reuse"] == 8
assert ledger["algorithm_revisions"] == ledger["native_inputs"] == ledger["hardware_runs"] == 0

comparisons = []
for task, expected_n in [("m2-01", 1), ("m2-02", 3)]:
    paths = [EPISODES / (task + "-" + arm) / "chain.json" for arm in ["f", "u"]]
    fchain, uchain = [read(path) for path in paths]
    assert len(fchain["rows"]) == len(uchain["rows"]) == expected_n
    f_ranks = [d["ranking"] for d in fchain["method_decisions"] if d["site"] == "Select"]
    u_ranks = [d["ranking"] for d in uchain["method_decisions"] if d["site"] == "Select"]
    assert f_ranks == u_ranks
    rows = []
    for i, (fr, ur) in enumerate(zip(fchain["rows"], uchain["rows"]), 1):
        fc, uc = [r["generate"]["candidates"] for r in [fr, ur]]
        assert [c["actual_input"] for c in fc] == [c["actual_input"] for c in uc]
        assert fr["select"]["actual_input"] == ur["select"]["actual_input"]
        assert fr["select"]["selected_id"] == ur["select"]["selected_id"]
        assert [c["rank_components"] for c in fc] == [c["rank_components"] for c in uc]
        assert [c["dynamic_prediction"] for c in fc] == [c["dynamic_prediction"] for c in uc]
        differences = diff_paths(fc, uc)
        assert all(p.endswith("/update_consumed") or p.endswith("/update_phase_facts_sha256")
                   for p in differences)
        assert all(c["update_consumed"] is False for c in fc)
        assert all(c["update_consumed"] is True for c in uc)
        for side in ["state_before", "state_after"]:
            assert fr[side]["strategy"]["dynamic_repair"] == ur[side]["strategy"]["dynamic_repair"]
            assert fr[side]["strategy"]["dynamic_repair"]["phase_facts"]["failed_phases"] == []
        result_paths = [EPISODES / (task + "-" + arm) / "actions" / f"{i:02d}" /
                        "public-result.json" for arm in ["f", "u"]]
        results = [read(p) for p in result_paths]
        result_refs = [bind(p) for p in result_paths]
        for r, ref, result in zip([fr, ur], result_refs, results):
            assert ref == r["consequence"]["public_result"]
            # The chain stores S0's public transcript projection, while the
            # canonical public file keeps the full trace. Check its exact
            # counts and sampled rows rather than demanding byte identity.
            projected = r["result"]
            assert set(diff_paths(result, projected)) <= {
                "/facts/activity_counts", "/facts/detail_catalog",
                "/facts/projection", "/facts/trace/length", "/facts/activity/length"}
            for key, catalog in projected["facts"]["detail_catalog"].items():
                assert catalog["count"] == len(result["facts"][key])
                full_rows = {canonical(v) for v in result["facts"][key]}
                assert all(canonical(v) in full_rows for v in projected["facts"][key])
            counts = Counter((e["action"] + ":" + e["during"])
                             if e["action"] == "brownout" else e["action"]
                             for e in result["facts"]["activity"])
            assert dict(counts) == projected["facts"]["activity_counts"]
            assert result["design"] == {**r["state_before"]["design"],
                                        **r["select"]["actual_input"]["design_patch"]}
        result_differences = diff_paths(*results)
        assert set(result_differences) == {"/usage/numerical_inputs", "/usage/reused", "/usage/wall_s"}
        assert results[0]["facts"] == results[1]["facts"]
        assert not fr["consequence"]["reused"] and ur["consequence"]["reused"]
        result = results[0]
        facts = result["facts"]
        selected = fr["select"]["selected_candidate"]
        windows = fr["state_after"]["strategy"]["dynamic_repair"]["phase_facts"]["service"]["public_contact_windows"]
        public_matches = []
        for seq, window in enumerate(windows, 1):
            records = [e for e in facts["receiver_records"]
                       if e["seq"] == seq and e["direction"] == window["direction"]]
            on_time = [e for e in records if window["stable_contact_s"] <= e["time_s"]
                       <= window["public_deadline_s"]]
            public_matches.append({"seq": seq, "direction": window["direction"],
                "stable_contact_s": window["stable_contact_s"],
                "public_deadline_s": window["public_deadline_s"],
                "received_times_s": [e["time_s"] for e in records],
                "within_public_window": bool(on_time)})
        expected_matches = 6 if task == "m2-01" else (0 if i == 1 else 3)
        assert sum(x["within_public_window"] for x in public_matches) == expected_matches
        receiver_sequences = [e["seq"] for e in facts["receiver_records"]]
        assert len(receiver_sequences) == len(set(receiver_sequences))
        rows.append({"generation": i, "same_candidate_inputs_order_predictions_and_ranks": True,
            "pool_size": len(fc), "candidate_metadata_difference_paths": differences,
            "selected_id": fr["select"]["selected_id"],
            "selected_actual_input": fr["select"]["actual_input"],
            "selected_full_design": result["design"],
            "selection_rank": fr["select"]["expected_discrimination_or_gain"]["rank"],
            "selected_prediction_score": selected["dynamic_prediction"]["score"],
            "selected_prediction_service_verdict": selected["dynamic_prediction"]["service_verdict"],
            "F_U_generate_score_increments": [fr["generate"]["analytic_scores_used"],
                                               ur["generate"]["analytic_scores_used"]],
            "same_written_Update_memory": True,
            "before": phase_summary(fr["state_before"]),
            "after": phase_summary(fr["state_after"]),
            "public_results": result_refs,
            "transcript_projection_counts_and_trace_subset_verified": True,
            "F_U_reuse": [False, True],
            "public_result_difference_paths": result_differences,
            "model_valid": result["model_valid"], "public_check": result["public_check"],
            "minimum_tx_terminal_v": facts["minimum_tx_terminal_v"],
            "receiver_records": facts["receiver_records"],
            "public_identity_deadline_matches": public_matches,
            "matched_events_within_public_windows": expected_matches,
            "receiver_sequence_IDs_unique": True,
            "activity_counts": dict(Counter(e["action"] for e in facts["activity"])),
            "brownouts": [{k: e.get(k) for k in ["during", "queue_length", "reason"]}
                          for e in facts["activity"] if e["action"] == "brownout"]})
    score_summary = []
    for arm, chain in zip(["F", "U"], [fchain, uchain]):
        scores = chain["analytic_score_log"]
        score_summary.append({"arm": arm, "scores": len(scores),
            "unique_designs": len({s["design_sha256"] for s in scores}),
            "unique_predictions": len({s["prediction_sha256"] for s in scores}),
            "scores_by_phase_hash": dict(Counter(s["phase_facts_sha256"] for s in scores))})
    comparisons.append({"task": task, "chains": [bind(p) for p in paths],
        "same_initial_full_state_sha256": fchain["rows"][0]["full_state_before_sha256"] ==
                                         uchain["rows"][0]["full_state_before_sha256"],
        "all_saved_Select_rankings_equal": True, "scores": score_summary, "rows": rows})

gpath = EPISODES / "m2-01-g"
gchain = read(gpath / "chain.json")
tools = gchain["public_tool_call_log"]
assert len(tools) == len(gchain["analytic_score_log"]) == 14
assert {t["request"]["name"] for t in tools} == {"predict_candidate"}
assert all(t["status"] == "OK" and t["analytic_scores_used"] == 1 for t in tools)
assert len(gchain["rows"]) == 0
cost = read(gpath / "provider-costs.json")
assert cost["requests"] == 3 and cost["unknown_or_missing_usage"] == []
assert all(r["status"] == "SETTLED" for r in cost["rows"])
assert abs(cost["settled_charge_upper_bound_usd"] - .0908841) < 1e-12
callbacks = []
for i, expected_tools in enumerate([0, 4, 9, 14], 1):
    folder = gpath / "callbacks" / f"{i:02d}"
    reply = read(folder / "callback-result.json")
    request = read(folder / "input-public.json")
    n_tools = len(request["request"]["context"].get("public_tool_results", []))
    assert n_tools == expected_tools
    stderr = (folder / "stderr.log").read_text()
    wire = folder / "wire-public.json"
    if i < 4:
        assert wire.exists() and len(reply["request_ids"]) == 1
        assert reply["payload"]["status"] == "PUBLIC_TOOLS"
    else:
        assert not wire.exists() and reply["request_ids"] == []
        assert "ValueError:BODY_CAP" in stderr
        assert reply["usage"]["status"] == "UNKNOWN"
    callbacks.append({"index": i, "input": bind(folder / "input-public.json"),
        "reply": bind(folder / "callback-result.json"),
        "stderr": bind(folder / "stderr.log"),
        "accumulated_tool_results": n_tools, "wire_exists": wire.exists(),
        "request_ids": reply["request_ids"], "usage_status": reply["usage"]["status"],
        "provider_status": reply["provider_status"],
        "error": reply["error"], "BODY_CAP_in_stderr": "ValueError:BODY_CAP" in stderr,
        "output_budget_before": reply["output_budget_before"],
        "output_budget_after": reply["output_budget_after"]})

before, after = batch["provider_before"], batch["provider_after"]
assert after["total"] - before["total"] == 3
assert after["statuses"]["SETTLED"] - before["statuses"]["SETTLED"] == 3
assert after["statuses"]["UNKNOWN"] == before["statuses"]["UNKNOWN"] == 1
assert after["historical_unknown_sha256"] == before["historical_unknown_sha256"]

out = {"package": PACKAGE, "status": "PUBLIC_CHAIN_READBACK_COMPLETE",
    "audit_boundary": {"new_model_calls": 0, "new_cheap_scores": 0, "new_dynamic_inputs": 0,
        "private_or_raw_or_assessment_reads": 0, "provider_DB_reads": 0,
        "method_or_apparatus_imports": 0, "source_changes": 0,
        "scope": "Saved public chains plus S0 accounting summaries; no new experiment."},
    "frozen_interface_receipt": bind(HERE / "INTERFACE-RECEIPT.json"),
    "verified_frozen_bindings": frozen,
    "S0_inputs": [bind(S0 / "batch-result.json"), bind(S0 / "resource-ledger.json"),
                  bind(M2 / "shared/protocol.json"), bind(M2 / "shared/methods.json")],
    "F_U": comparisons,
    "generic": {"chain": bind(gpath / "chain.json"), "evaluated_candidates": 0,
        "explicit_public_tool_calls": 14, "new_cheap_scores": 14,
        "tool_types": dict(Counter(t["request"]["name"] for t in tools)),
        "query_designs": [t["request"]["arguments"]["design"] for t in tools],
        "callbacks": callbacks, "cost_receipt": bind(gpath / "provider-costs.json"),
        "settled_requests": 3, "estimated_USD_not_invoice": cost["settled_charge_upper_bound_usd"],
        "local_body_limit_bytes": 400000,
        "fourth_callback": "Local broker BODY_CAP before ready/provider dispatch; no request IDs or wire artifact. UNKNOWN is retained callback placeholder, not a new ledger UNKNOWN.",
        "second_task": "NOT_EXECUTED_NEW_USAGE_STOP; conservative stop after legacy fatal label.",
        "comparison": "CENSORED_BY_TOOL_TRANSPORT; no scientific FAIL or generic inferiority conclusion."},
    "accounting_from_S0": {"provider_before": before, "provider_after": after,
        "new_ledger_UNKNOWN": 0, "full_dynamic_inputs": ledger["full_dynamic_inputs"],
        "initial_inputs": ledger["initial_inputs"], "unique_candidate_inputs": 4,
        "evaluations_including_reuse": ledger["evaluations_including_reuse"],
        "cache_reuses": ledger["cache_reuses"], "cheap_scores": ledger["cheap_scores"],
        "algorithm_revisions": 0, "native_inputs": 0, "hardware_runs": 0},
    "conclusion": "No observed engineering benefit from phase-feedback consumption over the same frozen calculator on these two development tasks. All F/U candidate inputs, order, predictions, ranking, executed designs and scientific public consequences match; task2 U recomputes 8 extra identical predictions as the phase-facts cache key changes. The full G/F/U comparison did not complete.",
    "limitations": ["F keeps identical Update writes, raw public history, exact failed-point memory, current-design calculation and common regeneration; only phase consumption is disabled.",
        "failed_phases is empty throughout; IDLE resets with pending queues and observed retry patterns did not activate distinct phase-repair proposals.",
        "The approximation models one powered observation and one SAVE/TX/ACK per contact window, no reset/retry loop or complete queue/contact semantics, and checks gateway only at first approximate TX completion.",
        "Two prospectively fixed development tasks; manually implemented H, no auto-H learning, held-out transfer, statistical efficacy, native or hardware claim."]}
target = HERE / "FINAL-CHAIN-READBACK.json"
target.write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
print(json.dumps({"status": out["status"], "receipt": bind(target),
    "F_U_selected_designs_equal": True, "task2_F_U_scores": [7, 15],
    "G_predict_calls": 14, "new_audit_model_cheap_dynamic_calls": 0}, ensure_ascii=False))
