"""Bind minimal continuation inputs, reusing sealed sources and public history."""
from copy import deepcopy
import argparse
import ast
import json

import runtime as r


def build():
    original = r.read(r.BASE / "lc-service-learning/shared/protocol.json")
    inputs = r.read(r.OUT / "a/INPUT-BINDINGS.json")
    code = deepcopy(original["source_bindings"])
    for path, expected in code.items():
        if r.bind(path)["sha256"] != expected:
            raise ValueError("SEALED_DIRECT_SOURCE_CHANGED:" + path)
    for path in list(r.PKG.glob("*.py")) + list(r.HERE.glob("*.py")):
        ast.parse(path.read_text(), filename=str(path))
        code[str(path)] = r.bind(path)["sha256"]
    model = deepcopy(original["model_contract"])
    model.update(package=r.PACKAGE, at=r.now(), total_usd=50, requests_total_max=120)
    protocol = dict(package=r.PACKAGE, frozen_at=r.now(), model_contract=model,
        source_bindings=code, methods_sha256=original["methods_sha256"],
        apparatus_source=deepcopy(original["apparatus_source"]),
        public_bindings=deepcopy(original["public_bindings"]),
        training_tasks=deepcopy(original["training_tasks"]),
        training_task_descriptors=deepcopy(original["training_task_descriptors"]),
        tasks=deepcopy(original["tasks"]), provider_before=r.host.provider_snapshot(),
        inputs_host_only=r.bind(r.OUT / "a/INPUT-BINDINGS.json"),
        public_allowlist=r.bind(r.OUT / "a/FORMATION-ALLOWLIST.json"),
        storage=r.capacity(), formation_limits=r.FORMATION, solve_limits=r.SOLVE, total_caps=r.TOTAL,
        rules=dict(new_engineering_initials_scan=0, formation_groups_same_parent_and_public_history=True,
            original_pre_specified_learner_isolated_continuation=True, coordinator_has_seen_previous_parent_results=True,
            no_new_blind_task_claim=True, old_patch_offline_only=True, nested_owner_ledger_and_absolute_deadline_shared=True,
            nested_limits_min_original_solve_ceiling_parent_remaining=True, reserve_revision_opportunity=True,
            final_shared_catalog_and_tools_projected_before_byte_gate=True, public_request_bytes_cap=220000,
            new_full_inputs=40, total_full_wall_s=4800, low_cost_cap=96, original_r11_exception_only=True,
            no_human_patch_rescue_or_hidden_information=True, merge_public_training_only_after_both_formations=True,
            parent_must_redecide_same_merged_history=True, no_backup_environment_worktree=True))
    return protocol


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["working", "freeze"])
    args = parser.parse_args()
    if r.PROTOCOL.exists() or (r.HERE / "run-started.json").exists():
        raise ValueError("FROZEN_PACKAGE_NO_REPLACEMENT")
    protocol = build()
    r.configure(protocol)
    if args.phase == "working":
        r.save(r.OUT / "shared/working-protocol.json", protocol)
        print("working host config ready; no provider or science")
        return
    direct = r.read(r.HERE / "direct-path-check.json")
    if direct["status"] != "PASS_SOFTWARE_HOST_THROUGH_CHAIN" or not direct["all_required_chain_stages"]:
        raise ValueError("REAL_HOST_SOFTWARE_CHAIN_REQUIRED")
    cache = deepcopy(r.read(r.BASE / "lc-service-learning/shared/cache-seed.json"))
    for row in r.read(r.BASE / "lc-service-learning/s0/resource-ledger.json")["attempts"]:
        if row.get("public_result"):
            public = r.checked(row["public_result"])
            for entry in protocol["tasks"] + protocol["training_tasks"]:
                if public.get("task_sha256") == r.identity(r.task(entry)):
                    cache[r.cache_key(entry, public["design"])] = str(r.Path(row["public_result"]["path"]).parent)
    r.save(r.OUT / "shared/cache-seed.json", cache)
    protocol["direct_path_check"] = r.bind(r.HERE / "direct-path-check.json")
    protocol["pre_formation_common_revisions"] = direct["common_revision_count"]
    r.save(r.HERE / "resource-ledger.json", dict(package=r.PACKAGE, full_dynamic_inputs=0, full_dynamic_wall_s=0,
        candidate_evaluations=0, cache_reuses=0, cheap_checks=direct["budgeted_software_operations"] + 1,
        cheap_screen_reserved=32, attempts=[], new_engineering_initials=0))
    r.save(r.PROTOCOL, protocol)
    r.validate(protocol)
    print(json.dumps(dict(status="FROZEN", cache_entries=len(cache), provider=protocol["provider_before"],
        storage=r.capacity(), software_operations_seed=direct["budgeted_software_operations"] + 1)))


if __name__ == "__main__":
    main()
