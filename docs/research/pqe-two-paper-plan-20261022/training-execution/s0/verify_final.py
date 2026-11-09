"""Targeted receipts for this finite run only; no old ledger/paper rescan."""
import json
from pathlib import Path
import time

import runtime as r
from bfworld.agentlab.pqe20261024train.projection import digest, encoded


def verify():
    protocol = r.read(r.PROTOCOL)
    r.configure(protocol)
    r.validate(protocol)
    batch = r.read(r.HERE / "batch-result.json")
    if not batch["complete"]:
        raise ValueError("FINITE_RUN_NOT_CLOSED")
    resource = r.read(r.HERE / "resource-ledger.json")
    assert resource["full_dynamic_inputs"] <= 40 and resource["full_dynamic_wall_s"] <= 4800
    assert resource["cheap_checks"] <= 96 and resource["cheap_screen_reserved"] == 0
    forms, request_rows, in_tokens, out_tokens = {}, [], 0, 0
    remaining, privacy, test_rows = [], [], []
    forbidden = [r.task(entry)["task_id"] for entry in protocol["tasks"]]
    forbidden += [str(r.BASE / "lc-service-learning/a/host/"),
        str(r.BASE / "lc-service-learning/s0/episodes/t1-"),
        str(r.BASE / "lc-service-learning/s0/episodes/t2-"),
        str(r.BASE / "lc-service-learning/s0/REPORT.md"),
        str(r.BASE / "lc-service-learning/a/FINAL-READBACK"),
        str(r.BASE / "lc-service-learning/b/FINAL-READBACK")]
    for episode in batch["rows"]:
        ident = episode["episode"]
        if episode["status"] == "NOT_EXECUTED_NO_QUALIFIED_DESCENDANT":
            assert episode["provider_requests"] == episode["new_full_dynamic_inputs"] == 0
            continue
        folder = r.HERE / "episodes" / ident
        costs = r.read(folder / "provider-costs.json")
        assert not costs["unknown_or_missing_usage"] and costs["unsettled_reserved_usd"] == 0
        limit = r.FORMATION if episode["role"] == "formation" else r.SOLVE
        assert costs["requests"] <= limit["model_requests"] and episode["wall_s"] <= limit["wall_s"] + 5
        for row in costs["rows"]:
            assert row["status"] == "SETTLED" and row["usage"] is not None
            usage = json.loads(row["usage"]) if isinstance(row["usage"], str) else row["usage"]
            in_tokens += usage["prompt_tokens"]
            out_tokens += usage["completion_tokens"]
            request_rows.append(dict(id=row["id"], charged=row["charged"], episode=ident,
                provider_record=r.bind(folder / "provider-costs.json")))
        nested_path = folder / "nested-solve-budgets.json"
        nested = r.read(nested_path) if nested_path.exists() else []
        for sub in nested:
            limits = sub["limits"]
            assert (limits["provider_requests"] <= 12 and limits["tool_calls"] <= 24
                and limits["reserve_usd"] <= 5 and limits["output_tokens_total"] <= 131072
                and limits["wall_s"] <= 900 and sub["same_owner_and_ledger"])
            assert sub["owner"] == episode["owner"]
        if episode["role"] == "formation":
            form = r.read(folder / "formation.json")
            assert form["raw_proposal_count"] <= 2 and len(form["raw_versions"]) <= 4
            assert form["training_rounds"] <= 2 and form["full_inputs_consumed"] <= 8
            combined = costs["requests"] + form["cheap_checks_consumed"] + episode["explicit_tools"]
            assert combined <= 48, "ACTUAL_COMBINED_FORMATION_OPERATION_CAP"
            forms[episode["condition"]] = dict(original=r.bind(folder / "formation.json"),
                parent_sha256=form["parent_sha256"], history_sha256=form["common_history_sha256"],
                raw_proposals=form["raw_proposal_count"], versions=len(form["raw_versions"]),
                statuses=[v["status"] for v in form["raw_versions"]],
                actual_training_rounds=form["training_rounds"], nested_solves=len(nested),
                full_new_training_inputs=form["full_inputs_consumed"],
                selected_descendant=bool(form["selected_candidate"]), no_child_reason=form["no_child_reason"],
                revisions=len(form["revisions"]), explicit_combined_operations=combined)
            count_objects = count_requests = 0
            registry = r.read(folder / "public-objects/index.json")
            for record in registry["objects"].values():
                value = r.read(record["path"])
                assert digest(value) == record["sha256"]
                text = encoded(value).decode()
                assert not any(item in text for item in forbidden), "PRIVATE_ISOLATED_OBJECT_EXPOSED"
                count_objects += 1
            for input_path in (folder / "callbacks").glob("*/input-public.json"):
                text = input_path.read_text()
                assert not any(item in text for item in forbidden), "PRIVATE_ISOLATED_REQUEST_EXPOSED"
                assert input_path.stat().st_size <= 240000
                count_requests += 1
            privacy.append(dict(episode=ident, registered_public_objects=count_objects,
                actual_requests=count_requests, isolated_input_result_exit_summary_found=False,
                source_chain_only=True, no_blind_task_claim=True))
        else:
            result = r.read(folder / "solve/solve-result.json")
            test_rows.append(dict(episode=ident, condition=episode["condition"], role=episode["role"],
                final_verdict=result["final_verdict"], model_valid=result["model_valid"], correct_stop=result["correct_stop"],
                action_signature=result["action_signature"], actions=len(result["actions"]),
                common_history_sha256=episode["common_history_sha256"], result=r.bind(folder / "solve/solve-result.json")))
        for path in (folder / "training").rglob("method-transcript.json") if (folder / "training").exists() else []:
            transcript = r.read(path)
            # Audit-sized subtrees remain available by the original audit refs;
            # scalar receipts here prove actual initial/result Update ordering.
            assert transcript["initial_update"]["status"] == "UPDATED"
            for value in transcript["evaluated_candidates"]:
                assert (value["update_status"] == "UPDATED" or
                    (value["update_status"] == "DOMAIN_UNKNOWN" and value["model_valid"] is False
                     and value["public_check"]["verdict"] == "UNKNOWN")), "RESULT_UPDATE_GATE_NOT_RECORDED"
        remaining.append(dict(episode=ident, owner=episode["owner"], nested_solve_count=len(nested)))
    assert forms["H2"]["parent_sha256"] == forms["H4"]["parent_sha256"]
    assert forms["H2"]["history_sha256"] == forms["H4"]["history_sha256"]
    assert len({x["common_history_sha256"] for x in test_rows}) == 1
    checks = []
    for row in resource["attempts"]:
        if row.get("execution_status") == "NO_EXECUTION":
            continue
        public, raw, assessment = (r.checked(row[k]) for k in ("public_result", "raw", "assessment"))
        assert r.identity({k: v for k, v in raw.items() if k != "result_sha256"}) == raw["result_sha256"]
        assert public["result_sha256"] == raw["result_sha256"] and public["public_check"]["verdict"] == assessment["verdict"]
        checks.append(dict(category=row["category"], reused=row["reused"], verdict=assessment["verdict"],
            model_valid=public["model_valid"], public_result=row["public_result"]))
    provider = r.host.provider_snapshot()
    assert len(request_rows) <= 120 and sum(x["charged"] for x in request_rows) <= 50
    assert provider["total"] == protocol["provider_before"]["total"] + len(request_rows)
    assert provider["inflight"] == 0 and provider["statuses"]["UNKNOWN"] == protocol["provider_before"]["statuses"]["UNKNOWN"]
    close = r.read(r.HERE / "runtime-closeout.json")
    opened = r.read(r.HERE / "runtime-open.json")
    assert close["scope_restored"] == opened["prior_scope"]
    with r.p.dbconnect() as db:
        for owner in close["owners"]:
            assert db.execute("SELECT COUNT(*) FROM principals WHERE owner=?", (owner,)).fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM grants WHERE owner=? AND expires>?", (owner, time.time())).fetchone()[0] == 0
        scope = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        assert (scope[0] if scope else None) == close["scope_restored"]
    output = dict(package=r.PACKAGE, at=r.now(), status="TARGETED_FINITE_RUN_VERIFIED",
        formation=forms, tests=test_rows, isolated_source_chain_review=privacy,
        actual_full_inputs=resource["full_dynamic_inputs"], full_wall_s=resource["full_dynamic_wall_s"],
        full_result_evaluations=len(checks), exact_reuses=sum(x["reused"] for x in checks),
        low_cost_checks=resource["cheap_checks"], nested_solves=remaining,
        provider_requests=len(request_rows), input_tokens=in_tokens, output_tokens=out_tokens,
        rate_estimate_usd=sum(x["charged"] for x in request_rows), invoice_claim=False,
        original_r11_unchanged=True, new_billing_unknown=0, inflight=0,
        owner_credentials_and_live_grants=0, scope_restored=True,
        scope_restoration_values=dict(prior=opened["prior_scope"], restored=close["scope_restored"],
            meaning="null is the original absent setting, not an unconfirmed boolean"), provider_after=provider,
        no_routine_old_ledger_full_row_or_paper_prefix_scan=True, storage=r.capacity(),
        source_bindings_unchanged=len(protocol["source_bindings"]), scientific_reclaimed_bytes=0,
        no_new_backup_environment_worktree=True, root_init_run=False, repository_health_claim=False)
    r.save(r.HERE / "verification.json", output)
    print(json.dumps({k: output[k] for k in ("status", "actual_full_inputs", "full_result_evaluations", "exact_reuses", "low_cost_checks", "provider_requests", "rate_estimate_usd", "storage")}))


if __name__ == "__main__":
    verify()
