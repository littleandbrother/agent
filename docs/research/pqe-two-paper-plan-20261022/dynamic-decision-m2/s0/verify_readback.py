"""Offline M2 receipt readback. No calculator, solver or model calls."""
from pathlib import Path
from collections import Counter
import hashlib
import importlib.util
import json
import sqlite3
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("m2_frozen_entry_readback", HERE / "run_m2.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def verify():
    protocol = m.read(m.PROTOCOL)
    m.validate(protocol)
    batch = m.read(HERE / "batch-result.json")
    ledger = m.read(HERE / "resource-ledger.json")
    assert len(batch["tracks"]) == 6 and not (HERE / "active.lock").exists()
    current_provider = m.provider_snapshot()
    assert current_provider["total"] >= batch["provider_after"]["total"]
    assert current_provider["historical_unknown_sha256"] == batch["provider_after"]["historical_unknown_sha256"]
    assert batch["provider_before"]["total"] == 1920 and batch["provider_after"]["total"] == 1923
    assert batch["provider_after"]["inflight"] == 0
    assert batch["provider_after"]["statuses"]["UNKNOWN"] == batch["provider_before"]["statuses"]["UNKNOWN"] == 1
    assert ledger["full_dynamic_inputs"] == 6 and ledger["initial_inputs"] == 2
    assert ledger["evaluations_including_reuse"] == 8 and ledger["cache_reuses"] == 4
    assert ledger["cheap_scores"] == 50 and sum(x["cheap_scores"] for x in ledger["tracks"].values()) == 50
    assert ledger["algorithm_revisions"] == ledger["native_inputs"] == ledger["hardware_runs"] == 0
    assert ledger["full_dynamic_wall_s"] < 1800 and all(x["wall_s"] < 120 for x in ledger["attempts"])
    pairs, inputs, evidence = [], [], []
    for entry in protocol["tasks"]:
        task = m.load_task(entry)
        initial_dir = HERE / "initial" / entry["id"]
        public = m.read(initial_dir / "public-result.json")
        assert public["task_sha256"] == m.identity(task) and public["model_valid"] is True
        assert public["public_check"]["verdict"] == "FAIL" and public["public_check"]["received_count"] == 0
        assert m.read(initial_dir / "readback.json")["at"] >= protocol["frozen_at"]
        inputs.append({"id": entry["id"], "task_canonical_sha256": m.identity(task),
                       "initial_public_result": m.bind(initial_dir / "public-result.json")})
        f = m.read(HERE / "episodes" / (entry["id"] + "-f") / "chain.json")
        u = m.read(HERE / "episodes" / (entry["id"] + "-u") / "chain.json")
        assert len(f["rows"]) == len(u["rows"]) == (1 if entry["id"] == "m2-01" else 3)
        for index, (fr, ur) in enumerate(zip(f["rows"], u["rows"]), 1):
            # Real cache usage/history provenance differs after the first point;
            # never erase it to manufacture identical full states or cost gains.
            fs, us = fr["state_before"], ur["state_before"]
            assert all(fs[key] == us[key] for key in ["task", "design", "problem"])
            assert fs["last_result"]["facts"] == us["last_result"]["facts"]
            assert fs["last_result"]["public_check"] == us["last_result"]["public_check"]
            assert fs["strategy"]["dynamic_repair"]["phase_facts"] == us["strategy"]["dynamic_repair"]["phase_facts"]
            assert fr["select"]["actual_input"] == ur["select"]["actual_input"]
            assert fr["generate"]["candidates"] != ur["generate"]["candidates"]  # consumption annotations differ
            assert [c["actual_input"] for c in fr["generate"]["candidates"]] == [c["actual_input"] for c in ur["generate"]["candidates"]]
            assert fr["result"]["result_sha256"] == ur["result"]["result_sha256"]
            assert fr["select"]["selected_candidate"]["update_consumed"] is False
            assert ur["select"]["selected_candidate"]["update_consumed"] is True
            for arm, row in [("F", fr), ("U", ur)]:
                assert row["result"]["model_valid"] is True
                assert row["state_after"]["last_result"] == row["result"]
                phase = row["state_before"]["strategy"]["dynamic_repair"]["phase_facts"]
                assert phase["failed_phases"] == []
                pred = row["select"]["selected_candidate"]["dynamic_prediction"]
                assert pred["service_verdict"] == "UNKNOWN" and pred["predicted_received_count"] is None
            pred = fr["select"]["selected_candidate"]["dynamic_prediction"]
            predicted_tx = min(p["minimum_terminal_v"] for p in pred["phase_predictions"]
                               if p.get("phase") == "TX" and p.get("minimum_terminal_v") is not None)
            pairs.append({"task": entry["id"], "step": index,
                "same_Task_Design_Problem_public_facts_and_phase_memory": True,
                "accounting_and_history_provenance_differences_preserved": True,
                "same_candidate_actual_inputs": True,
                "same_selected_actual_input": True, "same_independent_raw_result": True,
                "F_consumed": False, "U_consumed": True,
                "failed_phases": [], "predicted_service": "UNKNOWN",
                "predicted_minimum_tx_terminal_v": predicted_tx,
                "actual_minimum_tx_terminal_v": fr["result"]["facts"]["minimum_tx_terminal_v"],
                "public_check": fr["result"]["public_check"],
                "actual_input": fr["select"]["actual_input"]})
            for row in [fr, ur]:
                consequence = row["consequence"]
                raw = m.checked(consequence["raw"])
                assessment = m.checked(consequence["assessment"])
                assert m.identity({k: v for k, v in raw.items() if k != "result_sha256"}) == raw["result_sha256"]
                assert raw["result_sha256"] == row["result"]["result_sha256"]
                assert assessment["verdict"] == row["result"]["public_check"]["verdict"]
                evidence.append({"public": consequence["public_result"], "raw": consequence["raw"],
                                 "assessment": consequence["assessment"]})
    account = m.read(HERE / "episodes/m2-01-g/provider-costs.json")
    assert account["requests"] == 3 and not account["unknown_or_missing_usage"]
    assert all(row["status"] == "SETTLED" and row["usage"] for row in account["rows"])
    usage = [json.loads(row["usage"]) for row in account["rows"]]
    assert sum(u["prompt_tokens"] for u in usage) == 205435
    assert sum(u["completion_tokens"] for u in usage) == 24378
    fourth = HERE / "episodes/m2-01-g/callbacks/04"
    callback = m.read(fourth / "callback-result.json")
    assert callback["request_ids"] == [] and callback["usage"]["status"] == "UNKNOWN"
    assert not (fourth / "wire-public.json").exists()
    assert "BODY_CAP" in (fourth / "stderr.log").read_text()
    assert batch["tracks"][3]["status"] == "NOT_EXECUTED_NEW_USAGE_STOP"
    with m.p.dbconnect() as db:
        # Legitimate later batches may append rows or install their own scope.
        # Validate the M2 rows, not a permanently frozen global database size.
        for row in account["rows"]:
            current = dict(db.execute("SELECT * FROM model_requests WHERE id=?", (row["id"],)).fetchone())
            assert all(current.get(key) == value for key, value in row.items())
        owners = [r[0] for r in db.execute("SELECT owner FROM research_model_owners WHERE protocol=?", (m.PACKAGE,))]
        assert len(owners) == 1
        principals = sum(db.execute("SELECT count(*) FROM principals WHERE owner=?", (o,)).fetchone()[0] for o in owners)
        grants = sum(db.execute("SELECT count(*) FROM grants WHERE owner=? AND expires>?", (o, time.time())).fetchone()[0] for o in owners)
        assert principals == grants == 0
        assert db.execute("SELECT count(*) FROM research_model_studies WHERE protocol=? AND expires>?", (m.PACKAGE, time.time())).fetchone()[0] == 0
        closeout = m.read(HERE / "runtime-closeout.json")
        assert closeout["scope_restored_to"] is None
    return {"package": m.PACKAGE, "status": "PASS_OFFLINE_READBACK_WITH_TOOL_CENSORED_G_COMPARISON",
            "at": m.now(), "frozen_protocol": m.bind(m.PROTOCOL),
            "source_bindings_unchanged": len(protocol["source_bindings"]),
            "inputs": inputs, "F_U_pairs": pairs, "independent_artifacts": evidence,
            "ledger": m.bind(HERE / "resource-ledger.json"),
            "resources": {k: v for k, v in ledger.items() if k not in {"attempts", "tracks"}},
            "accounting": {"new_settled_requests": 3, "new_unknown_billing_rows": 0,
               "input_tokens": 205435, "output_tokens": 24378,
               "rate_estimate_usd": account["cache_aware_rate_estimate_usd"],
               "not_invoice": True, "R11_full_row_unchanged": True},
            "transport_classification": {"fourth_callback": m.bind(fourth / "callback-result.json"),
               "stderr": m.bind(fourth / "stderr.log"), "kind": "LOCAL_BODY_CAP_PRE_PROVIDER_FORWARD",
               "provider_requests_for_fourth_callback": 0, "new_unknown_billing_row": False,
               "original_unknown_placeholder_preserved": True,
               "G2_conservative_dispatch_stop_preserved": True,
               "G_not_a_scientific_failure_or_inferiority_result": True},
            "runtime_closeout": {"owners": owners, "active_principals": principals,
               "effective_grants": grants, "study_expired": True, "scope_restored_absent": True,
               "global_inflight": 0},
            "claim_boundary": "F/U isolated action and outcome parity in two finite mechanisms; generic comparison censored by transport and conservative stop. No stable efficacy, transfer, learned H or hardware claim.",
            "new_science_predictor_model_calls_for_verification": 0}


if __name__ == "__main__":
    result = verify()
    target = HERE / "final-readback.json"
    if not target.exists():
        m.save(target, result)
    print(json.dumps({"status": result["status"], "F_U_action_pairs": len(result["F_U_pairs"]),
                      "accounting": result["accounting"], "receipt": m.bind(target)}))
