"""One public development experiment; reuse the frozen complete M3 consumer host.

No model owner, planner, broker callback, predictor, or scientific search is used.
Audit objects are saved whole, with a reference index rather than prompt projection.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import importlib.util
import json
import os
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
BASE = OUT.parent
ROOT = BASE.parents[2]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
PKG = APP / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022"
PACKAGE = "BF-PQE-EXECUTABLE-SELECT-M4-20261023-001"
PROTOCOL = OUT / "shared/protocol.json"
M3 = BASE / "service-repair-m3"
sys.path.insert(0, str(M3 / "s0"))
spec = importlib.util.spec_from_file_location("m4_frozen_consumer_helpers", M3 / "s0/run_m3.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
now, read, bind, checked, save = host.now, host.read, host.bind, host.checked, host.save
p, adapter, identity = host.p, host.adapter, host.identity


def capacity():
    fs = os.statvfs(ROOT)
    available = fs.f_bavail * fs.f_frsize
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    if available < 10400000000 or size >= 40000000:
        raise ValueError("M4_STORAGE_RESOURCE_GATE")
    return {"at": now(), "available_bytes": available, "retained_logical_bytes": size,
            "estimated_peak_additional_bytes": 400000000, "retained_cap_bytes": 40000000,
            "deleted_bytes": 0, "new_backups": 0, "new_environments": 0, "new_worktrees": 0}


# Only the host's existing complete-consumer execution and readback are reused.
# In its subprocess entry, __file__ routes to this file, not to the old M3 run.
host.OUT, host.HERE, host.PROTOCOL, host.PACKAGE = OUT, HERE, PROTOCOL, PACKAGE
host.__file__, host.capacity = str(Path(__file__).resolve()), capacity


def cheap_ledger():
    rows, total = {}, 0
    for owner in ("a", "b"):
        path = OUT / owner / "cheap-ledger.json"
        value = read(path)
        field = "total_calls" if owner == "a" else "consumed"
        count = int(value[field])
        if not 0 <= count <= 4:
            raise ValueError("M4_OWNER_CHEAP_CAP:" + owner)
        rows[owner] = {"binding": bind(path), "source_count_field": field,
                       "new_cheap_relation_calls": count}
        total += count
    if total > 8:
        raise ValueError("M4_TOTAL_CHEAP_CAP")
    return {"total": total, "owners": rows, "S0_new_cheap_relation_calls": 0}


def audit(path, value):
    """Durable audit, intentionally independent of model prompt byte caps."""
    save(path, value)
    if identity(read(path)) != identity(value):
        raise ValueError("M4_AUDIT_FULL_READBACK_FAILED")
    return bind(path)


def audit_saved_chain():
    rows = []
    for path in sorted((M3 / "s0/episodes/m3-u/actions").glob("*/public-result.json")):
        rows.append({"public_result": bind(path), "value": read(path)})
    if len(rows) != 3:
        raise ValueError("EXPECTED_THREE_ORIGINAL_M3_ACTIONS")
    encoded = json.dumps(rows, ensure_ascii=False, allow_nan=False).encode()
    decoded = json.loads(encoded)
    if identity(decoded) != identity(rows) or len(encoded) <= 220000:
        raise ValueError("ORIGINAL_CHAIN_AUDIT_REGRESSION_CHECK")
    return audit(HERE / "audit-regression-readback.json", {
        "status": "PASS", "original_actions": [r["public_result"] for r in rows],
        "full_chain_serialized_bytes": len(encoded), "roundtrip_sha256": identity(decoded),
        "audit_strategy": "Whole JSON objects with content readback; index references bind saved full objects.",
        "prompt_projection_used_for_audit": False, "original_M3_chain_rewritten": False,
        "new_scientific_or_model_execution": 0})


def freeze():
    if PROTOCOL.exists():
        raise ValueError("M4_PROTOCOL_ALREADY_FROZEN_NO_RETRY")
    old = read(M3 / "shared/protocol.json")
    offline = read(OUT / "b/OFFLINE-RECEIPT.json")
    if offline.get("status") != "OFFLINE_SEMANTICS_PASS" or not all(offline.get("checks", {}).values()):
        raise ValueError("M4_OFFLINE_SEMANTICS_REQUIRED")
    if read(HERE / "offline-integration-check.json").get("status") != "PASS":
        raise ValueError("M4_AFFECTED_INTEGRATION_CHECK_REQUIRED")
    parent = read(OUT / "shared/IMPLEMENTATION.json")["parent_choice"]["public_result"]
    checked(parent)
    if adapter.source_identity() != old["apparatus_source"]:
        raise ValueError("M4_ORIGINAL_APPARATUS_CHANGED")
    paths = [PKG / "service_relations.py", PKG / "m3_methods.py",
             PKG / "trajectory_service_facts.py", PKG / "m4_methods.py", Path(__file__)]
    sources = dict(old["source_bindings"])
    sources.update({str(path): bind(path)["sha256"] for path in paths})
    protocol = {k: deepcopy(old[k]) for k in ("tasks", "common_start", "common_before",
        "common_decision", "common_result", "scientific_source", "apparatus_source",
        "sdk_entry", "same_backend", "model_identity")}
    protocol.update(package=PACKAGE, frozen_at=now(), source_bindings=sources,
        provider_before=host.provider_snapshot(), parent_public_result=parent,
        development_proposal=bind(OUT / "a/development-candidate.json"),
        offline_semantics=bind(OUT / "b/OFFLINE-RECEIPT.json"),
        offline_integration=bind(HERE / "offline-integration-check.json"),
        implementation=bind(OUT / "shared/IMPLEMENTATION.json"),
        caps=read(HERE / "preflight.json")["budget"], capacity=capacity(),
        cheap_relations=cheap_ledger(), audit_check=audit_saved_chain(),
        no_model_dispatch_or_runtime_registration=True,
        claim_boundary="Seen-development deterministic method correction and at most one fixed experimental design; no learned H, held-out efficacy, RSI or physical result.")
    save(PROTOCOL, protocol)
    save(HERE / "participant-freeze.json", {"package": PACKAGE, "at": now(),
        "source_bindings": {str(path): bind(path)["sha256"] for path in paths},
        "development_proposal": protocol["development_proposal"],
        "post_result_revisions": 0})
    host.validate(protocol, participant=True)
    audit(HERE / "resource-ledger.json", {"package": PACKAGE, "full_dynamic_inputs": 0,
        "full_dynamic_wall_s": 0, "evaluations_including_reuse": 0, "cache_reuses": 0,
        "attempts": [], "categories": {}, "cheap_scores": protocol["cheap_relations"]["total"],
        "provider_requests": 0, "provider_usd": 0, "native_inputs": 0, "hardware_runs": 0,
        "post_participant_result_revisions": 0})
    return protocol


def exact_cache(protocol):
    cache = host.exact_cache(protocol)
    tasks = {e["task_canonical_sha256"]: host.load_task(e) for e in protocol["tasks"]}
    folders = list((M3 / "s0/engineering").glob("*"))
    folders += list((M3 / "s0/episodes").glob("*/actions/*"))
    for folder in folders:
        if not (folder / "raw.json").exists():
            continue
        public, raw = read(folder / "public-result.json"), read(folder / "raw.json")
        task = tasks.get(public["task_sha256"])
        if task is None or not public.get("model_valid"):
            continue
        if (identity({k: v for k, v in raw.items() if k != "result_sha256"}) != raw["result_sha256"]
                or raw["result_sha256"] != public["result_sha256"]
                or public["sources"] != protocol["apparatus_source"]):
            raise ValueError("M4_PRIOR_CACHE_BINDING_FAILED")
        key = p.execution_cache_key(task, public["design"], raw["dt_s"], protocol["apparatus_source"])
        cache[key] = folder
    return cache


def execute(entry, state, decision, folder, ledger, cache, protocol, category):
    if ledger["categories"].get(category, 0) or category not in {"candidate", "regression"}:
        raise ValueError("M4_ONE_INPUT_PER_ROLE")
    if ledger["full_dynamic_inputs"] >= 2 or ledger["full_dynamic_wall_s"] > 120:
        raise ValueError("M4_TOTAL_NUMERICAL_CAP")
    result = host.execute(entry, state, decision, folder, ledger, cache, protocol, category)
    if ledger["full_dynamic_inputs"] > 2 or ledger["full_dynamic_wall_s"] > 240:
        raise ValueError("M4_TOTAL_NUMERICAL_CAP_EXCEEDED")
    return result


def run():
    if (HERE / "run-started.json").exists():
        raise ValueError("M4_ALREADY_STARTED_NO_RETRY")
    protocol = read(PROTOCOL)
    host.validate(protocol, participant=True)
    from bfworld.agentlab.pqe20261022.m4_methods import M4Harness
    started = time.monotonic()
    save(HERE / "run-started.json", {"package": PACKAGE, "at": now()})
    ledger, cache = read(HERE / "resource-ledger.json"), exact_cache(protocol)
    entry = protocol["tasks"][1]
    task, parent = host.load_task(entry), checked(protocol["parent_public_result"])
    state = p.episode_initial_state(task, parent["design"], parent["problem"])
    state["task"] = checked(entry["public_input"])["task"]
    state["last_result"] = deepcopy(parent)
    proposal = checked(protocol["development_proposal"])
    method = M4Harness(development_candidate=proposal)
    quota = {"remaining_actions": 1, "remaining_cost": 1, "max_candidates": 1,
             "analytic_scores_left": 0, "public_tool_calls_left": 8,
             "model_calls_remaining": 0, "model_cost_remaining": 0}
    method.quota = quota
    external = {"status": "READY",
        "actual_input": {"operation": "verify"}, "purpose": "EXPLICIT_SAVED_PARENT_OBSERVATION"}
    state = method.update(state, external, deepcopy(parent))
    chain = {"package": PACKAGE, "parent_public_result": protocol["parent_public_result"],
             "initial_state": audit(HERE / "chain/initial-state.json", state)}
    batch = method.generate(state, quota)
    decision = method.select(state, batch, quota)
    chain.update(generated=audit(HERE / "chain/generated.json", batch),
                 selected=audit(HERE / "chain/selected.json", decision))
    result, consequence, regression, regression_readback = None, None, None, None
    if decision.get("status") == "READY":
        result, consequence = execute(entry, deepcopy(state), decision,
            HERE / "candidate/01", ledger, cache, protocol, "candidate")
        state = method.update(state, deepcopy(decision), deepcopy(result))
        chain["candidate_state_after"] = audit(HERE / "chain/candidate-state-after.json", state)
        # The original independent evaluator stays host-only. It never enters G/S/U.
        parent_assessment = read(Path(protocol["parent_public_result"]["path"]).parent / "assessment.json")
        improved = consequence["model_valid"] and consequence["timely_matches"] > len(parent_assessment.get("matches", []))
        if improved or host.passed(result):
            regression_state = p.episode_initial_state(host.load_task(protocol["tasks"][0]),
                result["design"], result["problem"])
            regression_state["task"] = checked(protocol["tasks"][0]["public_input"])["task"]
            regression_decision = {"status": "READY", "selected_id": decision["selected_id"] + "-original-task1-regression",
                                   "actual_input": {"operation": "verify"}}
            regression, regression_readback = execute(protocol["tasks"][0], regression_state,
                regression_decision, HERE / "regression/01", ledger, cache, protocol, "regression")
    if hasattr(method, "finalize_adoption"):
        state = method.finalize_adoption(state, regression)
    chain.update(final_state=audit(HERE / "chain/final-state.json", state),
        method_transcript=audit(HERE / "chain/method-transcript.json", {
            "calls": method.program.calls, "decisions": method.decisions,
            "program": method.program.artifact}))
    duration = time.monotonic() - started
    if duration > 900:
        raise ValueError("M4_DETERMINISTIC_RUNTIME_CAP")
    host.validate(protocol, participant=True)
    audit(HERE / "chain/index.json", chain)
    audit(HERE / "result.json", {"package": PACKAGE, "at": now(),
        "status": "FINITE_PACKAGE_EXECUTED" if result else "JUSTIFIED_NO_CANDIDATE_STOP",
        "selected_status": decision.get("status"), "candidate": consequence,
        "regression": regression_readback, "adoption": state.get("strategy", {}).get("executable_select"),
        "method_calls": method.program.calls, "chain": bind(HERE / "chain/index.json"),
        "ledger": bind(HERE / "resource-ledger.json"), "deterministic_runtime_wall_s": duration,
        "provider_after": host.provider_snapshot(), "postflight": capacity(),
        "paid_models": 0, "new_model_episodes": 0, "post_result_revisions": 0})
    print(json.dumps({"status": "FINITE_PACKAGE_EXECUTED" if result else "JUSTIFIED_NO_CANDIDATE_STOP",
        "candidate": consequence and consequence["public_check"],
        "candidate_timely": consequence and consequence["timely_matches"],
        "regression": regression_readback and regression_readback["public_check"],
        "new_full": ledger["full_dynamic_inputs"], "wall_s": duration}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["freeze", "run", "_execute", "auditcheck"])
    parser.add_argument("input", nargs="?")
    args = parser.parse_args()
    if args.phase == "_execute":
        host.child(args.input)
    elif args.phase == "freeze":
        freeze()
    elif args.phase == "auditcheck":
        audit_saved_chain()
    else:
        run()
