"""Reuse original finite selection/test flow with corrected common host entry."""
from copy import deepcopy
from pathlib import Path
import argparse
import importlib.util
import json

import runtime as r

spec = importlib.util.spec_from_file_location("sealed_lc_runner", r.BASE / "lc-service-learning/s0/run_lc_learning.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
close_episode, merged_history, test_episode = prior.close_episode, prior.merged_history, prior.test_episode


def objects_for(ep, catalog):
    from bfworld.agentlab.pqe20261024train.projection import PublicObjects
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
    with ep.nested_solve(t["task_id"], actions_max) as limits:
        state = r.p.episode_initial_state(t, t["initial_design"], t["initial_problem"])
        state["last_result"] = deepcopy(initial)
        initial_ref = ep.objects.register(initial, path=entry["initial_public_result"]["path"])
        ep.task, ep.design, ep.problem, ep.last_full = deepcopy(t), deepcopy(t["initial_design"]), deepcopy(t["initial_problem"]), initial
        driver = SequentialEpisodeDriver("strong_generic", ep.planner, episode_id=ep.ident + ":" + t["task_id"],
            initial_state=state, initial_public_object_ref=initial_ref,
            world_kind="LC_PV" if entry["world"] == "LC-PV" else "DOOR", model_identity=r.p.MODEL_IDENTITY,
            request_reserve_usd=.19, limits=limits, max_evaluated_candidates=actions_max,
            program=program, common_history=history, expected_methods_sha256=ep.protocol["methods_sha256"],
            isolated_program=True, fixture_mode=bool(ep.software_check))
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
                driver.update(final, public_object_ref=final_ref)
            if driver.termination is None:
                driver.finish("FINITE_SELECTED_CANDIDATE_CAP")
        finally:
            ep.audit(folder / "method-transcript.json", driver.transcript())
            ep.current_solver = None
        new_actions = ep.actions[before_actions:]
        correct_stop = (initial["model_valid"] is True and initial["public_check"]["verdict"] == "PASS"
                        and not new_actions and (driver.termination or {}).get("reason") == "STOPPED")
        row = dict(task_id=t["task_id"], initial_verdict=initial["public_check"]["verdict"],
            final_verdict=final["public_check"]["verdict"], model_valid=final["model_valid"] is True,
            correct_stop=correct_stop, action_signature=digest([x["actual_input"] for x in new_actions]),
            result_sha256=final["result_sha256"], public_object_ref=final_ref,
            public_check=deepcopy(final["public_check"]), actions=new_actions,
            termination=deepcopy(driver.termination), transcript=r.bind(folder / "method-transcript.json"))
        r.save(folder / "solve-result.json", row)
    return row, execution_refs


def train_program(ep, protocol, history, program, version, remaining_full, round_no):
    before = ep.numerical
    rows, refs = [], []
    for number, entry in enumerate(protocol["training_tasks"]):
        if ep.numerical - before >= remaining_full:
            break
        row, local = solve_program(ep, program, entry, history,
            ep.root / "training" / f"round-{round_no:02d}" / f"task-{number + 1:02d}", actions_max=2)
        rows.append(row)
        refs += local
    feedback = dict(status="COMPLETE" if len(rows) == len(protocol["training_tasks"]) else "PARTIAL",
        full_inputs=ep.numerical - before, task_results=rows, execution_refs=refs,
        owner_budget_after=ep.snapshot(), round=round_no, version=deepcopy(version))
    if feedback["full_inputs"] > min(4, remaining_full) or ep.evaluations > 8:
        raise ValueError("TRAINING_FULL_CAP_DISAGREEMENT")
    ep.audit(ep.root / "training" / f"round-{round_no:02d}" / "feedback.json", feedback)
    return feedback


def formation_episode(ident, condition, protocol, cache):
    from bfworld.agentlab.pqe20261024train.training import TrainingFormationDriver
    parent = r.checked(protocol["public_bindings"]["parent"])
    history = r.checked(protocol["public_bindings"]["history"])
    catalog = r.checked(protocol["public_bindings"]["catalog"])
    ep = r.LCEpisode(ident, dict(task_id="PUBLIC_DEVELOPMENT_TRAINING_ONLY", initial_design={}, initial_problem={}),
                     condition, protocol, cache, "formation")
    objects_for(ep, catalog)
    error, formation, round_count = None, None, 0

    def train(program, version, remaining_full):
        nonlocal round_count
        if round_count >= 2 or remaining_full < 0:
            raise ValueError("TWO_TRAINING_ROUNDS_CAP")
        round_count += 1
        return train_program(ep, protocol, history, program, version, remaining_full, round_count)

    try:
        ep.start_server()
        driver = TrainingFormationDriver(condition=condition, planner_callback=ep.planner, parent=parent,
            history=history, source_catalog=catalog, training_tasks=protocol["training_task_descriptors"],
            training_execute=train, episode_id=ident, model_identity=r.p.MODEL_IDENTITY, request_reserve_usd=.19,
            limits=dict(provider_requests=24, tool_calls=48, new_numerical_inputs=8, wall_s=1800,
                output_tokens_per_request=65536, output_tokens_total=262144, reserve_usd=10))
        ep.driver = driver
        formation = driver.run()
        ep.audit(ep.root / "formation.json", formation)
        r.save(ep.root / "selected-program.json", formation["selected_program"])
        resource = r.read(r.HERE / "resource-ledger.json")
        resource["cheap_checks"] += formation.get("cheap_checks_consumed", 0)
        resource["cheap_screen_reserved"] -= 16
        if not 0 <= formation.get("cheap_checks_consumed", 0) <= 16 or resource["cheap_screen_reserved"] < 0 or resource["cheap_checks"] > 96:
            raise ValueError("FINITE_SCREEN_RESERVATION_DISAGREEMENT")
        r.save(r.HERE / "resource-ledger.json", resource)
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
        if any(token in str(exc) for token in ("SOURCE_CHANGED", "ROW_CHANGED", "BINDING_STOP", "COMPACTION_READBACK", "UNKNOWN_STOP")):
            ep.fatal = error
        if ep.driver is not None:
            ep.audit(ep.root / "retained-driver-error.json", ep.driver.transcript())
    row = close_episode(ep, error, dict(selected_descendant=bool(formation and formation.get("selected_candidate")),
        training_rounds=round_count, nested_solve_count=len(ep.nested_solves)))
    if ep.fatal:
        raise ValueError(ep.fatal)
    return row, formation


prior.objects_for, prior.solve_program, prior.formation_episode = objects_for, solve_program, formation_episode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["run", "_execute"])
    parser.add_argument("input", nargs="?")
    args = parser.parse_args()
    r.execute_child(args.input) if args.phase == "_execute" else prior.run()


if __name__ == "__main__":
    main()
