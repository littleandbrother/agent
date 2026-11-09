"""Read-only finite-package verification; no provider or consumer dispatch."""
import hashlib
import json
import sqlite3
import time

import runtime as r


def verify():
    protocol = r.read(r.PROTOCOL)
    r.configure(protocol)
    r.validate(protocol)
    batch = r.read(r.HERE / "batch-result.json")
    assert batch["complete"] is True
    resource = r.read(r.HERE / "resource-ledger.json")
    close = r.read(r.HERE / "runtime-closeout.json")
    rows = batch["rows"]
    formation = {}
    for condition in ("H2", "H4"):
        path = r.HERE / "episodes" / ("form-" + condition.lower()) / "formation.json"
        result = r.read(path)
        assert not result["selected_candidate"] and result["full_inputs_consumed"] == 0
        formation[condition] = dict(original=r.bind(path), raw_proposals=result["raw_proposal_count"],
            versions=len(result["raw_versions"]), actual_full_training_inputs=0,
            revision_count=len(result["revisions"]), selected_descendant=False)
    h2 = r.read(formation["H2"]["original"]["path"])
    h4 = r.read(formation["H4"]["original"]["path"])
    assert h2["raw_versions"][0]["contract_feedback"]["code"] == "LIMITS_MUST_BE_FINITE_AND_NOT_ENLARGED"
    assert h4["callback_records"][0]["error"]["message"] == "LOCAL_PUBLIC_PROJECTION_BYTES_CAP_PRE_FORWARD"
    formation["H2"].update(classification="ORCHESTRATOR_TRAINING_SUBSOLVE_LIMIT_MISMATCH",
        contract_error="LIMITS_MUST_BE_FINITE_AND_NOT_ENLARGED", evidence_of_method_failure=False)
    formation["H4"].update(classification="LOCAL_PUBLIC_PROJECTION_PRE_FORWARD_CAP",
        new_provider_requests=0, new_billing_unknown=False, evidence_of_method_failure=False)
    assert h2["parent_sha256"] == h4["parent_sha256"]
    assert h2["common_history_sha256"] == h4["common_history_sha256"]
    assert len([row for row in rows if row["status"] == "NOT_EXECUTED_NO_QUALIFIED_DESCENDANT"]) == 4

    executions = []
    for attempt in resource["attempts"]:
        public, raw, assessment = (r.checked(attempt[key]) for key in ("public_result", "raw", "assessment"))
        assert r.identity({k: v for k, v in raw.items() if k != "result_sha256"}) == raw["result_sha256"]
        assert public["result_sha256"] == raw["result_sha256"]
        assert public["public_check"]["verdict"] == assessment["verdict"] == "FAIL"
        assert public["model_valid"] is True
        executions.append(dict(public=attempt["public_result"], reused=attempt["reused"],
            verdict="FAIL", model_valid=True, received_count=public["public_check"]["received_count"]))
    assert len(executions) == 4 and sum(not x["reused"] for x in executions) == 2
    tests = {}
    for name in ("t1-h1", "t2-h1"):
        folder = r.HERE / "episodes" / name / "solve"
        result, transcript = r.read(folder / "solve-result.json"), r.read(folder / "method-transcript.json")
        assert transcript["initial_update"]["status"] == "UPDATED"
        assert all(x["update_status"] == "UPDATED" for x in transcript["evaluated_candidates"])
        tests[name] = dict(result=r.bind(folder / "solve-result.json"), initial_update=True,
            evaluated_candidates=len(transcript["evaluated_candidates"]), final_verdict=result["final_verdict"],
            correct_stop=result["correct_stop"], action_signature=result["action_signature"],
            every_actual_result_updated_before_next_decision=True)
    assert tests["t1-h1"]["correct_stop"] is True
    assert tests["t2-h1"]["final_verdict"] == "FAIL"
    assert len({row["common_history_sha256"] for row in rows if row.get("result")}) == 1

    accounts = []
    tokens_in = tokens_out = 0
    for folder in (r.HERE / "episodes").iterdir():
        costs = r.read(folder / "provider-costs.json")
        assert not costs["unknown_or_missing_usage"] and costs["unsettled_reserved_usd"] == 0
        for row in costs["rows"]:
            assert row["status"] == "SETTLED" and row["usage"] is not None
            usage = json.loads(row["usage"]) if isinstance(row["usage"], str) else row["usage"]
            tokens_in += usage["prompt_tokens"]
            tokens_out += usage["completion_tokens"]
            accounts.append(dict(id=row["id"], status=row["status"], charged=row["charged"],
                                 original=r.bind(folder / "provider-costs.json")))
    assert len(accounts) == 1
    provider = r.host.provider_snapshot()
    assert provider["total"] == protocol["provider_before"]["total"] + 1 and provider["inflight"] == 0
    assert provider["statuses"]["UNKNOWN"] == protocol["provider_before"]["statuses"]["UNKNOWN"]
    with r.p.dbconnect() as db:
        owners = close["owners"]
        for owner in owners:
            assert db.execute("SELECT COUNT(*) FROM principals WHERE owner=?", (owner,)).fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM grants WHERE owner=? AND expires>?", (owner, time.time())).fetchone()[0] == 0
        scope = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        assert (scope[0] if scope else None) == close["scope_restored"]
        assert db.execute("SELECT expires FROM research_model_studies WHERE protocol=?", (r.PACKAGE,)).fetchone()[0] <= time.time()
    baseline = r.read(r.ROOT / "docs/storage-slimming-20261019/batch-17/billing-before.json")["campaign"]
    connection = sqlite3.connect("file:" + baseline["path"] + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    digest = hashlib.sha256()
    original_rows = connection.execute("SELECT * FROM model_requests WHERE created<=? ORDER BY id", (baseline["high_water_created"],)).fetchall()
    for row in original_rows:
        digest.update(json.dumps(dict(row), sort_keys=True).encode() + b"\n")
    assert len(original_rows) == baseline["original_rows"] and digest.hexdigest() == baseline["original_rows_sha256"]
    connection.close()
    result = dict(package=r.PACKAGE, at=r.now(), status="FINITE_EXECUTION_CLOSED_METHOD_COMPARISON_INCOMPLETE",
        targeted_preservation_and_execution_checks="PASS", method_comparison_completed=False,
        original_campaign_billing_rows_unchanged=len(original_rows), original_r11_row_unchanged=True,
        source_bindings_unchanged=len(protocol["source_bindings"]), formation=formation, tests=tests,
        executions=executions, skipped_descendant_cells=4, adopted_program="ORIGINAL_PARENT_RETAINED",
        local_adoption_qualified=False, actual_full_dynamic_inputs=resource["full_dynamic_inputs"],
        actual_full_wall_s=resource["full_dynamic_wall_s"], low_cost_checks=resource["cheap_checks"],
        new_provider_requests=len(accounts), provider_records=accounts,
        input_tokens=tokens_in, output_tokens=tokens_out,
        rate_estimate_usd=sum(x["charged"] for x in accounts), invoice_claim=False,
        new_billing_unknown=0, inflight=0, owner_credentials_and_live_grants=0,
        provider_after=provider, storage=r.capacity(), scientific_reclaimed_bytes=0,
        new_backups_environments_worktrees=0, root_init_run=False, repository_health_claim=False,
        next_dependency="Separately bounded correction of training subsolve limit mapping and G-ATTRIBUTE public projection before any new study; do not reopen this attempt.")
    r.save(r.HERE / "verification.json", result)
    print(json.dumps({k: result[k] for k in ("status", "actual_full_dynamic_inputs", "low_cost_checks", "new_provider_requests", "rate_estimate_usd", "original_campaign_billing_rows_unchanged", "storage")}))


if __name__ == "__main__":
    verify()
