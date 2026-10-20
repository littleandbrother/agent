#!/usr/bin/env python3
"""Bind existing episode receipts to paper data; no apparatus/tool execution."""
from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path

PAPER = Path(__file__).resolve().parent
WORLD = PAPER.parent.parent
DOCS = WORLD / "docs/research/phase1-20261020/ar/final-pi-20261020"
ROOT = Path("/Users/depengsu/.local/share/bf-phase1-20261020/a/ar-service/pi-episode-001")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main():
    sources = {}

    def read(path):
        path = Path(path)
        sources[str(path)] = {"sha256": sha(path), "bytes": path.stat().st_size}
        return json.loads(path.read_text())

    original = read(ROOT / "episode-result.json")
    protocol = read(ROOT / "protocol.json")
    continuation = read(ROOT / "continuation-001/protocol.json")
    episode = read(ROOT / "continuation-001/episode-result.json")
    settlement = read(ROOT / "settlement-readback.json")
    costs = read(ROOT / "continuation-001/provider-costs.json")
    submission = read(ROOT / "continuation-001/scientific/submission.json")
    external = read(ROOT / "continuation-001/external/result.json")
    bound = read(ROOT / "external-fixed-space-bound.json")
    ordering = read(ROOT / "continuation-001/external/ordering-policy-audit.json")
    qualification = read(ROOT.parent / "sdk-resume-qualification-001/result.json")
    continuation_meta = continuation["continuation"]
    original_session = Path(continuation_meta["original_session"])
    resumed_session = Path((ROOT / "continuation-001/participant/.pi/phase1-session-path").read_text().strip())
    trace_path = ROOT / "continuation-001/pi-public-trace.jsonl"
    for path in (original_session, resumed_session, trace_path):
        sources[str(path)] = {"sha256": sha(path), "bytes": path.stat().st_size}
    old_entries = [json.loads(line) for line in original_session.read_text().splitlines()]
    new_entries = [json.loads(line) for line in resumed_session.read_text().splitlines()]
    old_messages = [x["message"] for x in old_entries if x.get("type") == "message"]
    new_messages = [x["message"] for x in new_entries if x.get("type") == "message"]
    assert sha(original_session) == continuation_meta["resume_prefix_sha256"]
    assert len(old_messages) == 8
    assert new_messages[:8] == old_messages
    assert sum(x.get("role") == "toolResult" for x in old_messages) == 4
    assert qualification["status"] == "PASS"
    assert qualification["original_messages"] == 8
    assert qualification["old_tool_results_in_actual_next_request"] == 4
    assert not continuation_meta["automatic_retry"]
    assert not continuation_meta["new_owner_or_context_reset"]
    assert protocol["owner"] == continuation["owner"] == episode["owner"] == external["owner"]
    assert continuation["limits"]["model_requests"] == protocol["limits"]["model_requests"] == 60
    assert continuation["limits"]["candidates"] == protocol["limits"]["candidates"] == 3
    assert protocol["limits"]["wall_seconds"] == 3600
    assert continuation["model_alias"] == protocol["model_alias"] == "deepseek-flash"

    # Bind the current candidate execution to the actual frozen sources, without importing them.
    current_files = {}
    for relative in (
        "configs/studies/phase1-20261020/ar/service-contract.v1.json",
        "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/ar_service.py",
        "scripts/campaign_ar_service.py",
    ):
        path = WORLD / relative
        current_files[relative] = {"sha256": sha(path), "bytes": path.stat().st_size}
    checker_sha = current_files["scripts/campaign_ar_service.py"]["sha256"]
    contract_sha = current_files["configs/studies/phase1-20261020/ar/service-contract.v1.json"]["sha256"]
    world_sha = current_files["packages/python/bfworld/src/bfworld/agentlab/campaign20261019/ar_service.py"]["sha256"]
    for config in (protocol, continuation):
        for relative, identity in current_files.items():
            matches = [v for k, v in config["bound_files"].items() if k.endswith("/battery-world/" + relative)]
            assert matches == [identity["sha256"]]
        for name, expected_sha in config["bound_files"].items():
            assert sha(Path(name)) == expected_sha, name
    assert bound["contract_sha256"] == contract_sha
    assert bound["world_sha256"] == world_sha
    assert bound["protocol_sha256"] == sha(ROOT / "protocol.json")
    feasibility_path = WORLD.parent.parent.parent / "docs/research/phase-plan-20261019/phase1/independent_feasibility.py"
    assert sha(feasibility_path) == bound["checker_sha256"]
    sources[str(feasibility_path)] = {"sha256": sha(feasibility_path), "bytes": feasibility_path.stat().st_size}
    assert original["protocol_sha256"] == canonical(protocol)

    trace = [json.loads(line) for line in trace_path.read_text().splitlines()]
    model_calls = [c for x in trace if x["type"] == "assistant_public"
                   for c in x["content"] if c["type"] == "toolCall"]
    facts = [x for x in trace if x["type"] == "bf_tool_fact"]
    assert len(model_calls) == len(facts) == 4
    assert [x["arguments"] for x in model_calls] == [x["input"] for x in facts]
    assert [x["arguments"]["action"] for x in model_calls] == ["check", "check", "check", "submit"]
    assert external["candidate_count"] == 3 and external["new_simulations"] == 12
    assert external["independent_new_simulations"] == 0
    assert external["product_acceptance"] == "NOT_ACCEPTED"
    assert not external["native_dispatches"] and not episode["native_dispatches"]

    candidate_data = []
    source_gate_rows = []
    sealed_total = 0
    for index in range(1, 4):
        name = f"candidate-{index:03}"
        bundle = ROOT / f"continuation-001/scientific/{name}"
        candidate = read(bundle / "candidate.json")
        seal = read(bundle / "seal.json")
        source_manifest = read(bundle / "source-manifest.json")
        receipt_path = ROOT / f"continuation-001/external/{name}.json"
        receipt = read(receipt_path)
        record = external["candidates"][name]
        assert sha(receipt_path) == record["receipt_sha256"]
        assert canonical(candidate) == record["candidate_sha256"] == receipt["candidate_sha256"]
        assert sha(bundle / "seal.json") == receipt["seal_sha256"]
        assert receipt["checker_sha256"] == checker_sha
        assert receipt["contract_sha256"] == contract_sha
        assert receipt["execution_integrity"] == "PASS"
        assert candidate == model_calls[index - 1]["arguments"]["candidate"]
        assert not receipt["public_consumer_disagreements"]
        assert not receipt["new_simulations_in_readback"]
        for item in seal["files"]:
            path = bundle / item["path"]
            assert path.stat().st_size == item["bytes"] and sha(path) == item["sha256"]
            sealed_total += 1
        for item in source_manifest:
            assert sha(WORLD / item["path"]) == item["sha256"]
        cases = {}
        for case_name, case in receipt["cases"].items():
            assert case["execution_integrity"] == "PASS"
            assert case["energy"]["verdict"] == case["activity_audit"]["verdict"] == "PASS"
            assert case["gates"]["independent_receiver"]["status"] == "PASS"
            for gate_name, gate in case["gates"].items():
                assert record["cases"][case_name]["gates"][gate_name] == gate["status"]
                source_gate_rows.append({"candidate": name, "case": case_name,
                                         "gate": gate_name, "status": gate["status"]})
            cases[case_name] = {
                "samples": case["sample_count"],
                "computational_services_under_rank_hook": case["all_applicable_computational_services"],
                "gates": {k: v["status"] for k, v in case["gates"].items()},
                "history_retention": case["gates"]["history_retention"],
                "recovery_upload": case["gates"]["recovery_upload"],
                "fresh_receive_delay": case["gates"]["fresh_receive_delay"],
                "temperature_events": case["gates"]["temperature_events"],
                "strict_fifo": ordering["cases"][name][case_name],
            }
        history = cases["ar-history-nvm"]
        for gate in ("continuous_new_sampling", "dark_new_sampling", "recovery_upload", "temperature_events"):
            assert history["gates"][gate] == "FAIL"
        assert history["gates"]["absolute_time"] == "UNKNOWN"
        assert cases["ar-upload-dedup"]["strict_fifo"]["strict_fifo"] == "FAIL"
        candidate_data.append({"name": name, "candidate_sha256": canonical(candidate),
                               "candidate": candidate, "model_tool_call_id": model_calls[index - 1]["id"],
                               "selected": name == external["submitted_candidate"], "cases": cases})
    assert submission["candidate_sha256"] == candidate_data[1]["candidate_sha256"]
    assert model_calls[3]["arguments"]["candidate"] == candidate_data[1]["candidate"]
    matrix_path = ROOT / "continuation-001/external/service-matrix.csv"
    sources[str(matrix_path)] = {"sha256": sha(matrix_path), "bytes": matrix_path.stat().st_size}
    matrix = list(csv.DictReader(matrix_path.open()))
    sort_key = lambda row: (row["candidate"], row["case"], row["gate"])
    assert sorted(matrix, key=sort_key) == sorted(source_gate_rows, key=sort_key)
    assert len(matrix) == external["matrix_rows"] == 180
    witness = ordering["cases"]["candidate-002"]["ar-upload-dedup"]["first_witness"]
    assert witness == {"time_s": 833, "selected_seq": 2, "oldest_pending_seq": 1, "pending_count": 2}

    # All seven ledger rows count; SDK zero usage on the censored call is not authoritative.
    assert costs["requests"] == episode["provider_requests_cumulative"] == len(costs["rows"]) == 7
    assert not costs["unknown_or_missing_usage"] and not costs["unsettled_reserved_usd"]
    cost_rows = []
    upper_total = Decimal(0)
    cache_total = Decimal(0)
    for row in costs["rows"]:
        assert row["status"] == "SETTLED"
        usage = json.loads(row["usage"])
        assert usage["prompt_tokens"] == usage["prompt_cache_hit_tokens"] + usage["prompt_cache_miss_tokens"]
        upper = (Decimal(usage["prompt_tokens"]) * Decimal(".30") + Decimal(usage["completion_tokens"]) * Decimal("1.20")) / 1_000_000
        cache = (Decimal(usage["prompt_cache_hit_tokens"]) * Decimal(".006") + Decimal(usage["prompt_cache_miss_tokens"]) * Decimal(".30") + Decimal(usage["completion_tokens"]) * Decimal("1.20")) / 1_000_000
        assert abs(Decimal(str(row["charged"])) - upper) < Decimal("1e-16")
        upper_total += upper
        cache_total += cache
        cost_rows.append({"request_id": row["id"], "status": row["status"],
                          "prompt_tokens": usage["prompt_tokens"], "completion_tokens": usage["completion_tokens"],
                          "cache_hit_tokens": usage["prompt_cache_hit_tokens"],
                          "cache_miss_tokens": usage["prompt_cache_miss_tokens"],
                          "charge_upper_usd": str(upper), "cache_aware_estimate_usd": str(cache),
                          "response_sha256": row["response_hash"]})
    assert upper_total == Decimal(str(costs["settled_charge_upper_bound_usd"])) == Decimal(".082605")
    assert cache_total == Decimal(str(costs["cache_aware_rate_estimate_usd"])) == Decimal(".058482888")
    assert [x["id"] for x in settlement["account"]["rows"]] == [x["id"] for x in costs["rows"][:2]]
    assistant_rows = [x for x in new_messages[8:] if x.get("role") == "assistant"]
    assert len(assistant_rows) == 5
    request_links = []
    for message in assistant_rows:
        usage = message["usage"]
        matches = [row for row in cost_rows if row["prompt_tokens"] == usage["input"] + usage["cacheRead"]
                   and row["completion_tokens"] == usage["output"]
                   and row["cache_hit_tokens"] == usage["cacheRead"]]
        assert len(matches) == 1
        request_links.append({"provider_request_id": matches[0]["request_id"],
                              "sdk_response_id": message["responseId"],
                              "model_tool_call_ids": [c["id"] for c in message["content"] if c["type"] == "toolCall"],
                              "linkage": "unique complete usage tuple in settled ledger; exact tool arguments bound to trace and candidate"})

    with localcontext() as ctx:
        ctx.prec = 40
        n = bound["numeric_decimal"]
        cold = 2 * Decimal(n["cold_optimistic_available_j"]) / Decimal("2.2") ** 2
        dark = Decimal(n["powered_duration_lower_bound_s"]) * Decimal(".000005") / Decimal(n["usable_energy_per_f"])
        assert abs(cold - Decimal(n["cold_capacitance_upper_bound_f"])) < Decimal("1e-38")
        assert abs(dark - Decimal(n["dark_capacitance_lower_bound_f"])) < Decimal("1e-38")
        assert Decimal(n["dark_duration_s"]) - Decimal(n["edge_slack_s"]) == Decimal(n["powered_duration_lower_bound_s"])
        assert cold < dark

    resolved_comparisons = [
        {"initial_comparison": "Analytical receipt checker_sha256 versus service checker file bytes appeared unequal",
         "resolution": "Different checker identities: the analytical receipt binds independent_feasibility.py; candidate receipts bind campaign_ar_service.py. Both match their actual paths.",
         "analytical_checker": {"path": str(feasibility_path), "sha256": sha(feasibility_path)},
         "service_checker": {"path": str(WORLD / "scripts/campaign_ar_service.py"), "sha256": checker_sha},
         "status": "RESOLVED_NO_SOURCE_DRIFT"},
        {"initial_comparison": "Original episode-result protocol_sha256 versus protocol.json file bytes appeared unequal",
         "resolution": "Original episode-result uses canonical JSON content hash, not file byte hash. Current file matches both declared encodings. No original result was changed.",
         "canonical_encoding": "JSON ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False; UTF-8",
         "original_protocol_canonical_sha256": canonical(protocol),
         "original_protocol_file_sha256": sha(ROOT / "protocol.json"),
         "continuation_protocol_canonical_sha256": canonical(continuation),
         "continuation_protocol_file_sha256": sha(ROOT / "continuation-001/protocol.json"),
         "status": "RESOLVED_NO_SOURCE_DRIFT"},
    ]
    data = {
        "schema_version": "bf-ar-paper-actual-pi-evidence-v1", "baseline": protocol["baseline"],
        "episode": episode["episode"], "owner": episode["owner"],
        "episode_classification": "ONE_EXPLICIT_CONTINUED_PUBLIC_DEVELOPMENT_EPISODE_NOT_INDEPENDENT_RESAMPLING",
        "model_alias": protocol["model_alias"], "model_identity_scope": protocol["identity_scope"],
        "continuation": {"original_session_id": qualification["original_session_id"],
                         "original_messages": 8, "original_tool_results": 4,
                         "original_prefix_sha256": sha(original_session), "prefix_verified": True,
                         "original_deadline_unix": continuation_meta["original_deadline_unix"],
                         "maximum_cumulative_requests": 60, "maximum_candidates": 3,
                         "maximum_cumulative_wall_s": 3600, "automatic_retry": False,
                         "transport_response_bytes_original": protocol["limits"]["model_response_bytes"],
                         "transport_response_bytes_continuation": continuation["limits"]["model_response_bytes"]},
        "original_stop": original, "later_original_settlement": settlement["account"],
        "provider_request_links": request_links, "costs": {"requests": 7, "settled": 7,
            "charge_upper_usd": str(upper_total), "cache_aware_rate_estimate_usd": str(cache_total),
            "invoice": False, "unknown_or_missing_usage": [], "unsettled_reserved_usd": 0,
            "assistance": "Codex construction/repair: UNPRICED_NONZERO; total end-to-end cost unknown"},
        "candidates": candidate_data, "case_simulations_in_episode": 12,
        "new_simulations_in_this_editorial_readback": 0, "new_model_requests_in_this_editorial_readback": 0,
        "native_dispatches": 0, "external_status": external["status"],
        "product_acceptance": "NOT_ACCEPTED", "physical_qualification": "UNKNOWN",
        "method_benefit": "NOT_TESTED", "rsi": "NOT_TESTED", "heldout_transfer": "NOT_TESTED",
        "necessary_bound_external_receipt": bound,
        "bound_scope": "Fixed ideal single-capacitor/fixed-sleep legal space only; not physical impossibility",
        "matrix_rows_verified": 180, "sealed_files_rehashed": sealed_total,
        "frozen_sources": current_files, "source_bindings": sources,
        "provenance_status": "SOURCE_BINDING_READBACK_PASS_WITH_EXPLICIT_HASH_ENCODINGS_AND_CHECKER_PATHS",
        "resolved_hash_comparisons": resolved_comparisons,
    }
    write_json(PAPER / "phase1-pi-evidence.json", data)
    with (PAPER / "phase1-pi-costs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cost_rows[0])); writer.writeheader(); writer.writerows(cost_rows)
    summary_rows = []
    for item in candidate_data:
        history = item["cases"]["ar-history-nvm"]
        summary_rows.append({"candidate": item["name"], "selected": item["selected"],
                             "retry_s": item["candidate"]["program"]["retry_s"],
                             "history_samples_whole_profile": history["samples"],
                             "history_late_backlog": len(history["recovery_upload"]["late_sequences"]),
                             "history_missed_events": history["temperature_events"]["missed"],
                             "upload_fresh_gate_under_rank_hook": item["cases"]["ar-upload-dedup"]["gates"]["fresh_receive_delay"],
                             "strict_fifo_upload": item["cases"]["ar-upload-dedup"]["strict_fifo"]["strict_fifo"]})
    with (PAPER / "phase1-pi-candidates.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary_rows[0])); writer.writeheader(); writer.writerows(summary_rows)
    table_rows = []
    for item in summary_rows:
        label = item["candidate"].removeprefix("candidate-") + ("*" if item["selected"] else "")
        table_rows.append(f"{label} & {item['retry_s']} & {item['history_samples_whole_profile']} & {item['history_late_backlog']} & {item['history_missed_events']} " + r"\\")
    (PAPER / "phase1-pi-results.tex").write_text(
        "% Generated by bind_pi_evidence.py from external receipts; no simulation.\n"
        + r"\begin{table}[ht]" + "\n" + r"\centering\small" + "\n"
        + r"\setlength{\tabcolsep}{7pt}" + "\n"
        + r"\begin{tabular}{lrrrr}" + "\n" + r"\toprule" + "\n"
        + r"Candidate & Retry (s) & History samples & Late backlog & Missed events\\" + "\n"
        + r"\midrule" + "\n" + "\n".join(table_rows) + "\n"
        + r"\bottomrule" + "\n" + r"\end{tabular}" + "\n"
        + r"\caption{Three adaptive device revisions in one continued Pi episode; * marks the submitted candidate. Samples count the entire history profile, including its light periods, rather than only the dark interval. Every listed backlog record misses the 120~s recovery deadline. The four history service failures persist for every candidate.}" + "\n"
        + r"\label{tab:phase1-pi}" + "\n" + r"\end{table}" + "\n")
    write_json(DOCS / "source-data-binding.json", {"schema_version": "bf-ar-editorial-source-binding-v1",
               "generator": str(Path(__file__).resolve()), "generator_sha256": sha(Path(__file__)),
               "upstream_files": sources, "frozen_sources": current_files,
               "checks": {"candidate_seals_and_source_manifests": "PASS", "sealed_files_rehashed": sealed_total,
                          "model_tool_arguments_to_candidate_json": "PASS", "continuation_session_prefix": "PASS",
                          "ledger_arithmetic_and_original_cost_inclusion": "PASS", "service_matrix_180_rows": "PASS",
                          "necessary_bound_decimal_readback": "PASS", "protocol_bound_files": {"original": len(protocol["bound_files"]), "continuation": len(continuation["bound_files"]), "status": "PASS"},
                          "original_protocol_canonical_identity": "PASS", "analytical_checker_file_identity": "PASS"},
               "resolved_hash_comparisons": resolved_comparisons, "paper_outputs": {path.name: sha(path) for path in
                   (PAPER / "phase1-pi-evidence.json", PAPER / "phase1-pi-costs.csv", PAPER / "phase1-pi-candidates.csv", PAPER / "phase1-pi-results.tex")},
               "new_simulations": 0, "new_model_requests": 0, "native_dispatches": 0})
    write_json(DOCS / "hash-comparison-notes.json", {"schema_version": "bf-ar-hash-comparison-resolution-v1",
               "comparisons": resolved_comparisons, "upstream_files_modified": False,
               "scope": "Preserves initial wrong-identity comparisons and their source-verified resolution; no trace/hash audit failure remains from these comparisons."})
    print(json.dumps({"sealed_files_rehashed": sealed_total, "matrix_rows_verified": len(matrix),
                      "candidates": len(candidate_data), "settled_requests": 7,
                      "charge_upper_usd": str(upper_total), "cache_aware_estimate_usd": str(cache_total),
                      "resolved_initial_hash_comparisons": len(resolved_comparisons), "new_simulations": 0}))


if __name__ == "__main__":
    main()
