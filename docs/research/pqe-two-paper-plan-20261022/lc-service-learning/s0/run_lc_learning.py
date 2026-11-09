"""Continuous finite formation/training, then frozen equal-history tests."""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import time

import runtime as r


def objects_for(ep, catalog):
    from bfworld.agentlab.pqe20261024lc.projection import PublicObjects
    ep.objects = PublicObjects(ep.root / "public-objects")
    ep.public_catalog = []
    for source_id, ref in catalog.items():
        value = r.checked(ref)
        identifier = ep.objects.register(value, path=ref["path"])
        ep.public_catalog.append({"source_id": source_id, "views": [{"original_pointer": "", "object_id": identifier}]})
    ep.objects.save_index()


def solve_program(ep, program, entry, history, folder, *, actions_max):
    from bfworld.agentlab.pqe20261024lc.driver import SequentialEpisodeDriver
    from bfworld.agentlab.pqe20261022.methods import digest
    t = r.task(entry)
    initial = r.checked(entry["initial_public_result"])
    state = r.p.episode_initial_state(t, t["initial_design"], t["initial_problem"])
    state["last_result"] = deepcopy(initial)
    initial_ref = ep.objects.register(initial, path=entry["initial_public_result"]["path"])
    ep.task, ep.design, ep.problem, ep.last_full = deepcopy(t), deepcopy(t["initial_design"]), deepcopy(t["initial_problem"]), initial
    limits = {"output_tokens_per_request": 65536, "output_tokens_total": ep.limits["generated_tokens"],
              "reserve_usd": ep.limits["usd"], "new_numerical_inputs": actions_max}
    driver = SequentialEpisodeDriver("strong_generic", ep.planner, episode_id=ep.ident + ":" + t["task_id"],
        initial_state=state, initial_public_object_ref=initial_ref, world_kind="LC_PV" if entry["world"] == "LC-PV" else "DOOR",
        model_identity=r.p.MODEL_IDENTITY, request_reserve_usd=.19, limits=limits,
        max_evaluated_candidates=actions_max, program=program, common_history=history,
        expected_methods_sha256=ep.protocol["methods_sha256"], isolated_program=True)
    ep.current_solver = driver
    before_actions = len(ep.actions)
    final, final_ref, execution_refs = initial, initial_ref, []
    try:
        driver.apply_initial_update(ep.snapshot())
        for number in range(actions_max + 1):
            action = driver.next(ep.snapshot())
            if action["status"] != "ACTION":
                break
            if number >= actions_max:
                raise ValueError("HOST_ACTION_CAP_DISAGREEMENT")
            public, reference, receipt = ep.consume_one(entry, driver, folder / "actions" / f"{number + 1:02d}")
            execution_refs.append(receipt["public_result"])
            if public.get("execution_status") == "NO_EXECUTION":
                driver.finish("LEGAL_NONEXECUTION_" + public["operation"].upper())
                break
            final, final_ref = public, reference
            # This actual Update precedes every subsequent decision.
            driver.update(final, public_object_ref=final_ref)
        if driver.termination is None:
            driver.finish("FINITE_SELECTED_CANDIDATE_CAP")
    finally:
        ep.audit(folder / "method-transcript.json", driver.transcript())
        ep.current_solver = None
    new_actions = ep.actions[before_actions:]
    correct_stop = (initial["model_valid"] is True and initial["public_check"]["verdict"] == "PASS"
                    and not new_actions and (driver.termination or {}).get("reason") == "STOPPED")
    row = {"task_id": t["task_id"], "initial_verdict": initial["public_check"]["verdict"],
           "final_verdict": final["public_check"]["verdict"], "model_valid": final["model_valid"] is True,
           "correct_stop": correct_stop, "action_signature": digest([x["actual_input"] for x in new_actions]),
           "result_sha256": final["result_sha256"], "public_object_ref": final_ref,
           "public_check": deepcopy(final["public_check"]), "actions": new_actions,
           "termination": deepcopy(driver.termination), "transcript": r.bind(folder / "method-transcript.json")}
    r.save(folder / "solve-result.json", row)
    return row, execution_refs


def close_episode(ep, error, extra):
    ep.close()
    accounting = r.p.ledger(r.p.DATABASE, ep.owner)
    r.save(ep.root / "provider-costs.json", accounting)
    row = dict(package=r.PACKAGE, episode=ep.ident, role=ep.role, condition=ep.condition, owner=ep.owner,
               status="RETAINED_ERROR" if error or ep.fatal else "FINITE_ATTEMPT_COMPLETE",
               error=error, fatal=ep.fatal, wall_s=time.monotonic() - ep.started,
               accounting={k: v for k, v in accounting.items() if k != "rows"},
               candidate_evaluations=ep.evaluations, new_full_dynamic_inputs=ep.numerical,
               cheap_relation_calls=ep.cheap_calls, explicit_tools=ep.tools, **extra)
    r.save(ep.root / "episode-result.json", row)
    print(json.dumps({"event": "LC_EPISODE_COMPLETE", "episode": ep.ident, "status": row["status"],
                      "error": error, "requests": accounting["requests"], "new_full": ep.numerical,
                      "selected_descendant": row.get("selected_descendant")}), flush=True)
    return row


def formation_episode(ident, condition, protocol, cache):
    from bfworld.agentlab.pqe20261024lc.training import TrainingFormationDriver
    parent = r.checked(protocol["public_bindings"]["parent"])
    history = r.checked(protocol["public_bindings"]["history"])
    catalog = r.checked(protocol["public_bindings"]["catalog"])
    dummy = dict(task_id="PUBLIC_DEVELOPMENT_TRAINING_ONLY", initial_design={}, initial_problem={})
    ep = r.LCEpisode(ident, dummy, condition, protocol, cache, "formation")
    objects_for(ep, catalog)
    error, formation = None, None
    round_count = 0

    def train(program, version, remaining_full):
        nonlocal round_count
        if round_count >= 2 or remaining_full < 0:
            raise ValueError("TWO_TRAINING_ROUNDS_CAP")
        round_count += 1
        before = ep.numerical
        rows, refs = [], []
        for number, entry in enumerate(protocol["training_tasks"]):
            if ep.numerical - before >= remaining_full:
                break
            row, local = solve_program(ep, program, entry, history,
                ep.root / "training" / f"round-{round_count:02d}" / f"task-{number + 1:02d}", actions_max=2)
            rows.append(row)
            refs += local
        feedback = dict(status="COMPLETE" if len(rows) == len(protocol["training_tasks"]) else "PARTIAL",
            full_inputs=ep.numerical - before, task_results=rows, execution_refs=refs,
            owner_budget_after=ep.snapshot(), round=round_count, version=deepcopy(version))
        if feedback["full_inputs"] > min(4, remaining_full) or ep.evaluations > 8:
            raise ValueError("TRAINING_FULL_CAP_DISAGREEMENT")
        ep.audit(ep.root / "training" / f"round-{round_count:02d}" / "feedback.json", feedback)
        return feedback

    try:
        ep.start_server()
        limits = dict(output_tokens_per_request=65536, output_tokens_total=262144,
                      reserve_usd=10, new_numerical_inputs=8)
        driver = TrainingFormationDriver(condition=condition, planner_callback=ep.planner, parent=parent,
            history=history, source_catalog=catalog, training_tasks=protocol["training_task_descriptors"],
            training_execute=train, episode_id=ident, model_identity=r.p.MODEL_IDENTITY,
            request_reserve_usd=.19, limits=limits)
        ep.driver = driver
        formation = driver.run()
        ep.audit(ep.root / "formation.json", formation)
        # The driver, never the host, selects a lawful trained descendant.
        r.save(ep.root / "selected-program.json", formation["selected_program"])
        resource = r.read(r.HERE / "resource-ledger.json")
        resource["cheap_checks"] = resource.get("cheap_checks", 0) + formation.get("cheap_checks_consumed", 0)
        resource["cheap_screen_reserved"] = resource.get("cheap_screen_reserved", 0) - 16
        if not 0 <= formation.get("cheap_checks_consumed", 0) <= 16 or resource["cheap_screen_reserved"] < 0:
            raise ValueError("FINITE_SCREEN_RESERVATION_DISAGREEMENT")
        if resource["cheap_checks"] > 96:
            raise ValueError("GLOBAL_CHEAP_SCREEN_CAP")
        r.save(r.HERE / "resource-ledger.json", resource)
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
        if any(token in str(exc) for token in ("SOURCE_CHANGED", "ROW_CHANGED", "BINDING_STOP", "COMPACTION_READBACK", "UNKNOWN_STOP")):
            ep.fatal = error
        if ep.driver is not None:
            ep.audit(ep.root / "retained-driver-error.json", ep.driver.transcript())
    row = close_episode(ep, error, dict(selected_descendant=bool(formation and formation.get("selected_candidate")),
                                      training_rounds=round_count))
    if ep.fatal:
        raise ValueError(ep.fatal)
    return row, formation


def test_episode(ident, role, condition, protocol, cache, formed, history, catalog):
    if condition in {"H2", "H4"} and not (formed.get(condition) or {}).get("selected_candidate"):
        row = dict(episode=ident, role=role, condition=condition, status="NOT_EXECUTED_NO_QUALIFIED_DESCENDANT",
                   candidate_evaluations=0, new_full_dynamic_inputs=0, provider_requests=0)
        r.save(r.HERE / "skipped" / (ident + ".json"), row)
        return row
    entry = next(x for x in protocol["tasks"] if x["role"] == role)
    program = formed[condition]["selected_program"] if condition in {"H2", "H4"} else r.checked(protocol["public_bindings"]["parent"])
    ep = r.LCEpisode(ident, r.task(entry), condition, protocol, cache, role)
    objects_for(ep, catalog)
    error, result = None, None
    try:
        ep.start_server()
        result, refs = solve_program(ep, program, entry, history, ep.root / "solve", actions_max=4)
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
    row = close_episode(ep, error, dict(result=result, common_history_sha256=r.identity(history),
                                      program_sha256=r.identity(program), selected_descendant=condition in {"H2", "H4"}))
    if ep.fatal:
        raise ValueError(ep.fatal)
    return row


def merged_history(protocol, formed):
    from bfworld.agentlab.pqe20261023bold.contracts import compact_feedback
    from bfworld.agentlab.pqe20261024lc.projection import project_public_result
    history = deepcopy(r.checked(protocol["public_bindings"]["history"]))
    catalog = deepcopy(r.checked(protocol["public_bindings"]["catalog"]))
    for number, row in enumerate(r.read(r.HERE / "resource-ledger.json")["attempts"]):
        if not row["category"].startswith("form-"):
            continue
        source_id = "lc-training-" + row["category"] + "-" + str(number)
        incident_id = "LC-TRAINING-" + row["category"].upper() + "-" + str(number)
        public = r.checked(row["public_result"])
        catalog[source_id] = row["public_result"]
        if public.get("execution_status") == "NO_EXECUTION":
            continue
        world = "LC_PV" if public.get("world_kind") == "LC-PV" or "LC-PV" in public["task_id"] else "DOOR"
        history.append(dict(incident_id=incident_id, source_id=source_id, allowed_for_learning=True,
            provenance="PUBLIC_EXECUTION", phase="training", decision=deepcopy(row["decision"]), record_ref=[source_id],
            result=compact_feedback(public, source_id), typed_view=project_public_result(public, source_id, world_kind=world)))
    r.save(r.OUT / "shared/merged-test-history.json", history)
    r.save(r.OUT / "shared/merged-test-catalog.json", catalog)
    r.save(r.HERE / "formed-program-freeze.json", dict(at=r.now(), test_feedback_seen=False,
        merged_history=r.bind(r.OUT / "shared/merged-test-history.json"), merged_catalog=r.bind(r.OUT / "shared/merged-test-catalog.json"),
        conditions={c: dict(qualified_descendant=bool(v and v.get("selected_candidate")),
                           program=r.bind(r.HERE / "episodes" / ("form-" + c.lower()) / "selected-program.json") if v else None)
                    for c, v in formed.items()}))
    return history, catalog


def run():
    protocol = r.read(r.PROTOCOL)
    r.configure(protocol)
    r.validate(protocol)
    if (r.HERE / "run-started.json").exists():
        raise ValueError("FINITE_PACKAGE_STARTED_NO_REPLACEMENTS")
    r.save(r.HERE / "run-started.json", dict(at=r.now(), package=r.PACKAGE))
    cache = r.read(r.OUT / "shared/cache-seed.json")
    rows, formed = [], {}
    with r.runtime_scope():
        for ident, _, condition in r.PLAN[:2]:
            row, formation = formation_episode(ident, condition, protocol, cache)
            rows.append(row)
            formed[condition] = formation
            r.save(r.HERE / "batch-result.json", dict(package=r.PACKAGE, rows=rows, complete=False))
            r.validate(protocol)
        history, catalog = merged_history(protocol, formed)
        for ident, role, condition in r.PLAN[2:]:
            r.validate(protocol)
            rows.append(test_episode(ident, role, condition, protocol, cache, formed, history, catalog))
            r.save(r.HERE / "batch-result.json", dict(package=r.PACKAGE, rows=rows, complete=False))
    r.save(r.HERE / "batch-result.json", dict(package=r.PACKAGE, at=r.now(), rows=rows, complete=True,
        provider_after=r.host.provider_snapshot(), storage=r.capacity()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["run", "_execute"])
    parser.add_argument("input", nargs="?")
    args = parser.parse_args()
    r.execute_child(args.input) if args.phase == "_execute" else run()
