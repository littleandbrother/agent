"""Bind the single authorized finite package; no provider or scientific calls."""
from copy import deepcopy
from pathlib import Path
import ast
import json

import runtime as r
from bfworld.agentlab.pqe20261023bold.contracts import compact_feedback
from bfworld.agentlab.pqe20261024lc.projection import project_public_result


def freeze():
    if r.PROTOCOL.exists() or (r.HERE / "run-started.json").exists():
        raise ValueError("ALREADY_FROZEN_NO_REPLACEMENT")
    oldroot = r.BASE / "bold-interventions"
    old = r.read(oldroot / "shared/protocol.json")
    areceipt = r.read(r.OUT / "a/FINAL-A-RECEIPT.json")
    engineering = r.checked(areceipt["engineering"])
    isolated = r.read(r.OUT / "a/host/TASK-FREEZE.json")
    direct = r.read(r.HERE / "direct-path-check.json")
    if direct["status"] != "PASS" or areceipt["new_full_inputs"] != 8:
        raise ValueError("REQUIRED_EXISTING_RECEIPT")
    catalog = deepcopy(r.checked(old["public_bindings"]["catalog"]))
    history = deepcopy(r.checked(old["public_bindings"]["history"]))
    for incident in history:
        source = incident["record_ref"][0]
        full = r.checked(catalog[source])
        incident.update(source_id=source, typed_view=project_public_result(full, source, world_kind="DOOR"))

    def add(source, ref, decision=None):
        full = r.checked(ref)
        catalog[source] = deepcopy(ref)
        world = "LC_PV" if full.get("world_kind") == "LC-PV" or "LC-PV" in full["task_id"] else "DOOR"
        history.append(dict(incident_id="LC-DEV-" + source.upper(), source_id=source,
            allowed_for_learning=True, provenance="PUBLIC_EXECUTION", record_ref=[source],
            visible_before={"task_id": full["task_id"], "task_sha256": full["task_sha256"],
                            "design": deepcopy(full["design"]), "problem": deepcopy(full["problem"])},
            decision=deepcopy(decision or {"source": "PREVIOUS_PUBLIC_EXECUTION"}),
            result=compact_feedback(full, source), typed_view=project_public_result(full, source, world_kind=world)))

    training = deepcopy(old["tasks"])
    for entry in training:
        add("seen-" + entry["role"] + "-initial", entry["initial_public_result"])
    for number, attempt in enumerate(r.read(oldroot / "s0/resource-ledger.json")["attempts"]):
        if attempt.get("category") == "t2-h1":
            add("seen-lc-parent-" + str(number), attempt["public_result"], attempt["decision"])
    for cell in engineering["cells"]:
        add("lc-engineering-" + cell["id"], cell["files"]["public-result.json"],
            {"source": "PRE_FROZEN_WHOLE_DESIGN_ENGINEERING", "design": cell["design"]})
    for number, ref in enumerate(engineering["public_training_index"]):
        envelope = r.checked(ref)
        catalog["lc-engineering-public-envelope-" + str(number)] = deepcopy(ref)
        catalog["lc-engineering-public-task-" + str(number)] = envelope["public_task"]
    r.save(r.OUT / "shared/common-history.json", history)
    r.save(r.OUT / "shared/public-source-catalog.json", catalog)

    descriptors = []
    for entry in training:
        t, initial = r.task(entry), r.checked(entry["initial_public_result"])
        previous = r.read(oldroot / "s0/episodes" / (entry["role"] + "-h1") / "episode-result.json")
        descriptors.append(dict(task_id=t["task_id"], world=entry["world"], public_task=deepcopy(t),
            initial_verdict=initial["public_check"]["verdict"],
            parent_final_verdict=previous["last_public_check"]["verdict"],
            parent_correct_stop=initial["model_valid"] is True and initial["public_check"]["verdict"] == "PASS"
                and previous["candidate_evaluations"] == 0 and previous["termination"]["reason"] == "STOPPED",
            parent_basis="Previously retained original BOLD executable-parent solve; no new baseline execution."))

    tasks = []
    for entry in isolated["entries"]:
        item = {key: deepcopy(entry[key]) for key in ("role", "world", "task")}
        item["initial_public_result"] = deepcopy(entry["initial"]["public-result.json"])
        if item["world"] == "LC-PV":
            item.update(lc_public=deepcopy(entry["context"]["public"]), lc_host_task=deepcopy(entry["context"]["host_task"]))
        tasks.append(item)

    cache = {}
    possible = [entry["initial_public_result"] for entry in training + tasks]
    possible += [row["public_result"] for row in r.read(oldroot / "s0/resource-ledger.json")["attempts"] if "public_result" in row]
    possible += [cell["files"]["public-result.json"] for cell in engineering["cells"]]
    for ref in possible:
        full = r.checked(ref)
        for entry in training + tasks:
            if full.get("task_sha256") == r.identity(r.task(entry)):
                folder = Path(ref["path"]).parent
                if (folder / "raw.json").is_file() and (folder / "assessment.json").is_file():
                    cache[r.cache_key(entry, full["design"])] = str(folder)
    r.save(r.OUT / "shared/cache-seed.json", cache)

    source_bindings = deepcopy(old["source_bindings"])
    for path in list(source_bindings):
        if r.bind(path)["sha256"] != source_bindings[path]:
            raise ValueError("ORIGINAL_DIRECT_SOURCE_CHANGED:" + path)
    paths = list(r.PKG.glob("*.py")) + [r.HERE / name for name in ("runtime.py", "run_lc_learning.py", "freeze_lc_learning.py")]
    for path in paths:
        ast.parse(path.read_text(), filename=str(path))
        source_bindings[str(path.resolve())] = r.bind(path)["sha256"]
    source_bindings[str(Path(old["model_contract"]["sdk_entry"]))] = r.bind(old["model_contract"]["sdk_entry"])["sha256"]
    source_bindings[old["model_contract"]["profile_source"]["path"]] = old["model_contract"]["profile_source"]["sha256"]
    model = deepcopy(old["model_contract"])
    model.update(package=r.PACKAGE, at=r.now(), total_usd=50, requests_total_max=120,
        formation_limits=r.FORMATION, solve_limits=r.SOLVE, episodes_max=8)
    snapshot = r.host.provider_snapshot()
    if snapshot["historical_unknown_sha256"] != old["provider_before"]["historical_unknown_sha256"]:
        raise ValueError("R11_ORIGINAL_ROW_CHANGED")
    protocol = dict(package=r.PACKAGE, frozen_at=r.now(), model_contract=model,
        formation_limits=r.FORMATION, solve_limits=r.SOLVE, total_caps=r.TOTAL,
        tasks=tasks, training_tasks=training, training_task_descriptors=descriptors,
        source_bindings=source_bindings, apparatus_source=r.adapter.source_identity(),
        methods_sha256=r.bind(r.PKG.parent / "pqe20261022/methods.py")["sha256"],
        public_bindings={"parent": r.bind(oldroot / "b/parent-program.json"),
            "history": r.bind(r.OUT / "shared/common-history.json"),
            "catalog": r.bind(r.OUT / "shared/public-source-catalog.json")},
        provider_before=snapshot, storage=r.capacity(), direct_path_check=r.bind(r.HERE / "direct-path-check.json"),
        engineering=r.bind(r.OUT / "a/ENGINEERING-RESULTS.json"), isolated_freeze=r.bind(r.OUT / "a/host/TASK-FREEZE.json"),
        rules=dict(formation_original_proposals_per_group=2, autonomous_revisions_per_proposal=1,
            training_rounds_per_group=2, training_chosen_actions_per_task_round=2,
            training_full_per_group=8, test_chosen_actions_per_cell=4, low_cost_total=96,
            update_before_every_next_decision=True, legal_nonexecution_terminates_without_new_assessment=True,
            same_parent_history_rights_model_budgets=True, no_test_exposure_during_formation=True,
            merged_training_history_for_all_test_conditions=True, no_human_patch_rescue=True,
            local_adoption_requires_both_isolated_full_pass_and_no_parent_pass_regression=True,
            unused_engineering_quota_retired=2, no_extra_matrices_or_replacement_episodes=True,
            retained_cap_metric="allocated_upper_bound; logical bytes separately reported",
            new_backups_environments_worktrees=0, original_r11_exception_only=True),
        pre_dispatch_common_revisions=dict(count=2, maximum=2,
            first="Saved-payload direct path and typed public-view integration.",
            second="Single pre-run review: legal history provenance; allocated storage guards; legal nonexecution accounting; fatal binding propagation."))
    ledger = dict(package=r.PACKAGE, at=r.now(), full_dynamic_inputs=areceipt["new_full_inputs"],
        full_dynamic_wall_s=areceipt["full_wall_s"], candidate_evaluations=0,
        cache_reuses=areceipt["reused_prior_full"], cheap_checks=areceipt["cheap_checks_total"] + 1,
        cheap_screen_reserved=32, attempts=[], engineering_import=r.bind(r.OUT / "a/FINAL-A-RECEIPT.json"))
    r.save(r.HERE / "resource-ledger.json", ledger)
    r.save(r.PROTOCOL, protocol)
    r.configure(protocol)
    r.validate(protocol)
    print(json.dumps(dict(status="FROZEN", history=len(history), sources=len(catalog), cache_entries=len(cache),
        provider_before=snapshot, storage=r.capacity(), new_model_or_science_calls=0)))


if __name__ == "__main__":
    freeze()
