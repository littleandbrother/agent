"""Read saved original outcomes and ledgers; never dispatch or simulate."""
from pathlib import Path
import json
import run_bold as r
from bfworld.agentlab.pqe20261022.methods import digest

protocol = r.read(r.PROTOCOL)
r.configure(protocol)
r.validate(protocol)
batch = r.read(r.HERE / "batch-result.json")
assert batch["complete"]
resource = r.read(r.HERE / "resource-ledger.json")
engineering = r.checked(protocol["engineering_results"])
rows = batch["rows"]
forms = {}
for name in ("form-h2", "form-h4"):
    root = r.HERE / "episodes" / name
    f = r.read(root / "formation.json")
    assert f["parent_sha256"] == digest(r.checked(protocol["public_bindings"]["parent"])["program"])
    assert f["common_history_sha256"] == digest(r.checked(protocol["public_bindings"]["history"]))
    forms[name] = {k: f.get(k) for k in ("condition", "raw_proposal_count", "selected_candidate", "parent_retained", "allocation")}
    forms[name].update(rejected=f["proposals"].get("rejected", []),
                       local_screen_count=len(f["local_evaluations"]),
                       raw_callback_paths=[str(p) for p in sorted((root / "callbacks").glob("*/callback-result.json"))])
assert forms["form-h2"]["raw_proposal_count"] == 1
assert forms["form-h2"]["rejected"][0]["reason"] == "PATCH_SOURCE_INCIDENTS"
assert forms["form-h4"]["raw_proposal_count"] == 0 and not forms["form-h4"]["rejected"]

costs, requests, wires = [], [], []
for row in rows:
    if not row.get("owner"):
        assert row["status"] == "NOT_EXECUTED_NO_QUALIFIED_DESCENDANT"
        continue
    ledger = r.p.ledger(r.p.DATABASE, row["owner"])
    assert not ledger["unknown_or_missing_usage"] and not ledger["unsettled_reserved_usd"]
    costs.append({"episode": row["episode"], **{k: v for k, v in ledger.items() if k != "rows"}})
    for req in ledger["rows"]:
        assert req["status"] == "SETTLED" and req["usage"] and not req["error"]
        usage = json.loads(req["usage"])
        requests.append({"id": req["id"], "episode": row["episode"], "status": req["status"],
                         "usage": usage, "cache_aware_rate_estimate_usd": req["charged"]})
    for path in sorted((r.HERE / "episodes" / row["episode"] / "callbacks").glob("*/wire-public.json")):
        wire = r.read(path)
        r.legacy.validate_wire(wire)
        result = r.read(path.parent / "callback-result.json")
        loaded = [json.loads(line) for line in (path.parent / "pi-public.jsonl").read_text().splitlines()
                  if line.strip() and json.loads(line).get("type") == "pqe_pi_loaded"]
        assert len(loaded) == 1 and not loaded[0]["tools"] and not loaded[0]["history_messages"]
        wires.append({"wire": r.bind(path), "grant": wire["max_tokens"],
                      "provider_status": result["provider_status"], "tool_free": True, "empty_sdk_history": True})

parent = {}
for role in ("t1", "t2"):
    entry = next(t for t in protocol["tasks"] if t["role"] == role)
    row = next(x for x in rows if x["episode"] == role + "-h1")
    transcript = r.read(r.HERE / "episodes" / row["episode"] / "method-transcript.json")
    assert transcript["initial_update"]["status"] == "UPDATED"
    assert transcript["initial_update"]["parent_design_preserved"]
    parent[role] = {"world": entry["world"], "initial_public_check": r.checked(entry["initial_public_result"])["public_check"],
                    "final_public_check": row["last_public_check"], "service_origin": row["service_origin"],
                    "actual_initial_update": transcript["initial_update"],
                    "full_candidate_evaluations": transcript["full_candidate_evaluations"],
                    "selected_actions": row["actions"], "termination": row["termination"],
                    "loaded_program_sha256": transcript["loaded_program_sha256"], "provider_requests": row["accounting"]["requests"]}
    if role == "t1":
        assert not row["actions"] and row["candidate_evaluations"] == 0 and row["last_public_check"]["verdict"] == "PASS"
    else:
        assert row["candidate_evaluations"] == row["new_full_dynamic_inputs"] == 4
        assert len(row["actions"]) == 1 and row["actions"][0]["new_full_dynamic_inputs"] == 0
        bindings = transcript["full_candidate_evaluations"][0]["result_bindings"]
        assert all(x["model_valid"] and x["public_check"]["verdict"] == "FAIL" for x in bindings)
        parent[role]["diagnosis"] = (
            "Four whole candidates executed; Rank chose largest model-valid received_count1288, despite6 public service failures. "
            "The initial result had1155 records and4 service failures. More records are not conjunctive service improvement. "
            "Update's door-named boot/tx_begin rules do not establish LC phase_begin boot/tx absence; its STARTUP_OR_SOURCE label is a method hypothesis, not an independent cause.")

provider = r.host.provider_snapshot()
assert provider["historical_unknown_sha256"] == protocol["provider_before"]["historical_unknown_sha256"]
assert provider["inflight"] == 0
owners = [x["owner"] for x in rows if x.get("owner")]
with r.p.dbconnect() as db:
    for owner in owners:
        assert not db.execute("SELECT 1 FROM principals WHERE owner=?", (owner,)).fetchone()
        assert not db.execute("SELECT 1 FROM grants WHERE owner=? AND expires>strftime('%s','now')", (owner,)).fetchone()
    scope = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
    scope = scope[0] if scope else None
assert scope == r.read(r.HERE / "runtime-open.json")["prior_scope"]
assert resource["full_dynamic_inputs"] == 14 and resource["full_dynamic_wall_s"] <= 4080
assert len(requests) == 3
rate = sum(x["cache_aware_rate_estimate_usd"] for x in requests)
accounting = {"provider_requests": len(requests), "all_settled_complete_usage": True,
              "rate_estimate_usd": rate, "invoice_amount_known": False,
              "input_tokens": sum(x["usage"]["prompt_tokens"] for x in requests),
              "output_tokens": sum(x["usage"]["completion_tokens"] for x in requests),
              "new_billing_unknown": 0, "original_r11_unchanged": True,
              "full_dynamic_inputs": resource["full_dynamic_inputs"], "full_dynamic_wall_s": resource["full_dynamic_wall_s"],
              "engineering_inputs": 8, "common_initial_inputs": 2, "method_full_candidate_inputs": 4,
              "selected_exact_replay_inputs": 0, "selected_exact_replays": 1,
              "cheap_native_hardware_g_self_modification": 0, "episode_costs": costs, "requests": requests}
adoption = {"package": r.PACKAGE, "decision": "NO_AUTOMATIC_DESCENDANT_ADOPTION_RETAIN_PARENT_ARTIFACT",
            "engineering": "Joint source/supply whole design passes both original M2 development conditions. Adaptive whole design misses one cold-start deadline; no cross-condition adoption.",
            "method": "H2 proposal rejected on exact incident references; H4 valid no-update. Four descendant cells unexecuted; no automatic learning effect tested.",
            "parent": "Correct stop on pre-frozen already-PASS DOOR; four model-valid but service-FAIL LC candidates. No two-case complete-service qualification.",
            "cost_advantage": "NOT_ESTABLISHED; formation expenditure remains charged; no child to compare.",
            "claim_boundary": "Constructed finite development/adoption tests only; no stable transfer, population advantage, physical qualification or RSI."}
result = {"package": r.PACKAGE, "at": r.now(), "finite_execution_complete": True,
          "engineering": engineering, "formations": forms, "same_history_parent": parent,
          "skipped_descendant_cells": [x for x in rows if x["status"].startswith("NOT_EXECUTED")],
          "accounting": accounting, "adoption": adoption,
          "independent_reviews": {"A": "PENDING", "B": "PENDING"}}
r.save(r.HERE / "RESULTS.json", result)
r.save(r.HERE / "adoption.json", adoption)
r.save(r.HERE / "verification.json", {"at": r.now(), "direct_frozen_sources_match": True,
     "two_formations_one_each_no_replacement": True, "raw_proposal_rejection_retained": True,
     "new_tasks_frozen_before_engineering_and_absent_formation": True,
     "initial_PASS_kept_and_really_updated": True, "initial_LC_FAIL_kept": True,
     "four_counted_full_candidates_selected_exact_reuse": True,
     "provider_wire_checks": wires, "resources": accounting,
     "temporary_principals_active_grants": 0, "scope_restored": scope,
     "provider_after": provider, "original_r11_unchanged": True,
     "no_new_backup_environment_worktree_commit_push_full_init": True,
     "new_execution_for_verification": 0, "full_repository_health_claim": False})
r.save(r.HERE / "postflight.json", r.capacity())
print(json.dumps({"event": "BOLD_HOST_CLOSEOUT_VERIFIED", "accounting": {k:v for k,v in accounting.items() if k not in {"episode_costs","requests"}},
                  "provider": provider, "storage": r.capacity(), "independent_reviews": "pending"}), flush=True)
