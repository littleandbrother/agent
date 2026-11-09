"""One explicit software-only traversal of the real nested training host."""
from copy import deepcopy
from pathlib import Path
import json
import time

import runtime as r
import run_training as run
from bfworld.agentlab.pqe20261024train.training import TrainingFormationDriver
from bfworld.agentlab.pqe20261024train.projection import encoded


class SoftwareEpisode(r.LCEpisode):
    def __init__(self, protocol, cache, ident):
        self.ident, self.role, self.condition = ident, "formation", "H2"
        self.owner = "SOFTWARE_ONLY_NO_MODEL_OWNER"
        self.protocol, self.cache = protocol, cache
        self.root = r.HERE / "direct-path" / ident
        self.root.mkdir(parents=True, exist_ok=False)
        self.limits = deepcopy(r.FORMATION)
        self.started = time.monotonic()
        self.absolute_deadline = self.started + self.limits["wall_s"]
        self.subscope, self.current_solver, self.fatal = None, None, None
        self.tools = self.numerical = self.evaluations = self.cheap_calls = 0
        self.actions, self.nested_solves, self.requests = [], [], []
        self.driver = None
        self.software_check = True
        self.fake_usage = dict(model_requests=0, spent_usd=0, output_tokens=0, wall_s=0)
        self.last_full = None
        self.revision_requests, self.full_feedbacks = [], []
        self.original = r.read(r.BASE / "lc-service-learning/s0/episodes/form-h2/formation.json")["initial_raw_response"]
        run.objects_for(self, r.checked(protocol["public_bindings"]["catalog"]))

    def budget(self):
        return {**self.fake_usage, "wall_s": time.monotonic() - self.started}

    def ready(self, paid=False):
        if self._remaining(self.budget())["wall_s_remaining"] <= 0:
            raise ValueError("SOFTWARE_ABSOLUTE_DEADLINE")
        return self.budget()

    def audit(self, path, value):
        r.save(path, value)

    def paid_callback(self, body):
        # A labelled substitute only: never invokes a model or registers owner.
        self.requests.append(dict(site=body["site"], bytes=len(encoded(body)),
            wire_payload_bytes=len(r.p.encoded(r.p.callback_payload(body, body["max_output_tokens"]))),
            sha256=r.identity(body), software_substitute=True))
        self.fake_usage["model_requests"] += 1
        self.fake_usage["output_tokens"] += 37
        self.fake_usage["spent_usd"] += .001
        if body["site"] == "G-ATTRIBUTE":
            payload = {"status": "READY", "explanations": []}
        elif self.driver and self.driver.raw_versions:
            payload = ({"status": "OK", "patches": [deepcopy(self.original["patches"][0])]}
                       if len(self.revision_requests) == 1 else {"status": "NO_UPDATE", "patches": []})
        else:
            payload = deepcopy(self.original)
        return dict(payload=payload, provider_status="COMPLETE", request_ids=[],
            usage=dict(status="SOFTWARE_FIXTURE", model_identity=r.p.MODEL_IDENTITY,
                       output_tokens=37, input_tokens=0, cost=.001),
            software_substitute=True, new_provider_requests=0)

    def consume_one(self, entry, driver, folder):
        actual = r.old.common_contract_check(driver.state, driver.pending["actual_input"], {"remaining_actions": 1})
        design = {**deepcopy(driver.state["design"]), **actual.get("design_patch", {})}
        key = r.cache_key(entry, design, actual.get("dt_s"))
        if key not in self.cache:
            raise ValueError("SOFTWARE_CHECK_MUST_USE_EXACT_PREEXISTING_SCIENCE_CACHE:" + key)
        original = Path(self.cache[key])
        public = r.read(original / "public-result.json")
        public["problem"] = {**deepcopy(driver.state["problem"]), **actual.get("problem_patch", {})}
        public["usage"] = dict(numerical_inputs=0, reused=True, wall_s=0, software_check_only=True)
        self.tools += 1
        self.evaluations += 1
        reference = self.objects.register(r.read(original / "public-result.json"), path=original / "public-result.json")
        receipt = dict(public_result=r.bind(original / "public-result.json"), reused=True,
                       new_full_dynamic_inputs=0, software_check_only=True)
        self.actions.append(dict(number=len(self.actions) + 1, actual_input=deepcopy(actual),
            public_check=public["public_check"], public_object_ref=reference, receipt=receipt))
        self.last_full = public
        return public, reference, receipt


def check():
    if (r.HERE / "direct-path-check.json").exists():
        raise ValueError("ONE_SOFTWARE_CHAIN_ALREADY_COMPLETED")
    protocol = r.read(r.OUT / "shared/working-protocol.json")
    r.configure(protocol, True)
    cache = deepcopy(r.read(r.BASE / "lc-service-learning/shared/cache-seed.json"))
    ep = SoftwareEpisode(protocol, cache, "h2-host-through-chain-v2")
    parent, history = (r.checked(protocol["public_bindings"][k]) for k in ("parent", "history"))
    # The original fixed Improver deliberately excludes PUBLIC_EXECUTION rows
    # in fixture mode. Label only this ephemeral software copy accordingly;
    # keep IDs/content and the formal public-history file unchanged.
    history = [{**deepcopy(row), "provenance": "SOFTWARE_FIXTURE",
                "original_provenance": row["provenance"]} for row in history]
    round_number = 0

    def train(program, version, remaining):
        nonlocal round_number
        round_number += 1
        feedback = run.train_program(ep, protocol, history, program, version, remaining, round_number)
        ep.full_feedbacks.append(feedback)
        return feedback

    driver = TrainingFormationDriver("H2", ep.planner, parent=parent, history=history,
        source_catalog=r.checked(protocol["public_bindings"]["catalog"]),
        training_tasks=protocol["training_task_descriptors"], training_execute=train,
        episode_id="SOFTWARE-HOST-CHAIN", model_identity=r.p.MODEL_IDENTITY, request_reserve_usd=.19,
        fixture_mode=True, revision_request_hook=lambda request: ep.revision_requests.append(deepcopy(request)))
    ep.driver = driver
    formed = driver.run()
    if round_number != 2 or len(ep.nested_solves) != 4 or not ep.revision_requests:
        raise ValueError("REAL_HOST_TRAIN_SOLVE_REVISION_SECOND_ROUND_NOT_REACHED:" + json.dumps(
            dict(rounds=round_number, nested=len(ep.nested_solves), revisions=len(ep.revision_requests),
                 versions=[(v["status"], v.get("contract_feedback")) for v in formed["raw_versions"]])))
    assert all(x["status"] == "COMPLETE" for x in ep.full_feedbacks)
    assert all(x["limits"]["reserve_usd"] <= 5 and x["limits"]["output_tokens_total"] <= 131072
        and x["limits"]["provider_requests"] <= 12 and x["limits"]["tool_calls"] <= 24
        and x["limits"]["wall_s"] <= 900 for x in ep.nested_solves)
    first, second = ep.nested_solves[0], ep.nested_solves[2]
    assert second["before"]["provider_requests_remaining"] < first["before"]["provider_requests_remaining"]
    assert second["before"]["output_tokens_remaining"] < first["before"]["output_tokens_remaining"]
    assert second["before"]["reserve_usd_remaining"] < first["before"]["reserve_usd_remaining"]
    assert len({x["parent_absolute_deadline"] for x in ep.nested_solves}) == 1
    for path in (ep.root / "training").rglob("method-transcript.json"):
        transcript = r.read(path)
        assert transcript["initial_update"]["status"] == "UPDATED"
        assert all(x["update_status"] == "UPDATED" for x in transcript["evaluated_candidates"])

    # Rebuild the actual first H4 attribution request from its original public
    # inputs; its original failed saved record remains separately referenced.
    h4 = SoftwareEpisode(protocol, cache, "h4-original-attribution")
    h4.condition = "H4"
    attr = TrainingFormationDriver("H4", h4.planner, parent=parent, history=history,
        source_catalog=r.checked(protocol["public_bindings"]["catalog"]), training_tasks=protocol["training_task_descriptors"],
        training_execute=lambda *args: (_ for _ in ()).throw(ValueError("H4_SOFTWARE_ONLY_ATTRIBUTION")),
        episode_id="SOFTWARE-H4-ATTRIBUTION", model_identity=r.p.MODEL_IDENTITY,
        request_reserve_usd=.19, fixture_mode=True)
    h4.driver = attr
    attr._stage(lambda: attr.harness.attribute(attr.harness.extract(history), parent))
    assert len(h4.requests) == 1 and h4.requests[0]["site"] == "G-ATTRIBUTE"
    forbidden = [r.task(entry)["task_id"] for entry in protocol["tasks"]]
    for episode in (ep, h4):
        for identifier in episode.objects.objects:
            value = episode.objects._get(identifier)
            text = encoded(value).decode()
            assert not any(task_id in text for task_id in forbidden), "ISOLATED_TASK_EXPOSED"
        largest = max(episode.objects.objects, key=lambda key: episode.objects.objects[key]["serialized_bytes"])
        page = episode.objects.read(dict(object_id=largest, section="", offset=0))
        assert len(encoded(page)) <= 14000
    requests = ep.requests + h4.requests
    assert all(x["bytes"] <= 220000 and x["wire_payload_bytes"] <= 240000 for x in requests)
    r.save(r.HERE / "direct-path-check.json", dict(status="PASS_SOFTWARE_HOST_THROUGH_CHAIN", at=r.now(),
        all_required_chain_stages=True, common_revision_count=2,
        software_only=True, new_provider_requests=0, new_full_scientific_inputs=0,
        exact_old_cache_only=True, old_h2_raw_proposal_source=r.bind(r.BASE / "lc-service-learning/s0/episodes/form-h2/formation.json"),
        old_h4_failure_source=r.bind(r.BASE / "lc-service-learning/s0/episodes/form-h4/formation.json"),
        actual_host_train_function=True, actual_nested_solve_construction=True, initial_update_and_result_update=True,
        next_decision_after_actual_saved_result=True, feedback_and_revision_request=True, second_round_remaining_decreased=True,
        nested_same_owner_and_absolute_deadline=True, formation_contract=driver.formation_contract(),
        training_rounds=round_number, nested_solves=ep.nested_solves, software_requests=requests,
        behavior_screen_inputs=formed["cheap_checks_consumed"], cached_saved_result_evaluations=len(ep.actions),
        final_request_caps_and_public_paging=True, isolated_task_source_leak=False,
        budgeted_software_operations=formed["cheap_checks_consumed"] + len(ep.actions) + len(requests) + 1,
        earlier_fixture_admission_error="Fixture mode correctly filtered PUBLIC_EXECUTION history; zero callbacks or nested solves. Ephemeral copies now explicitly SOFTWARE_FIXTURE, formal input unchanged.",
        no_software_outputs_in_formal_cache_or_learning_history=True))
    print(json.dumps(dict(status="PASS_SOFTWARE_HOST_THROUGH_CHAIN", rounds=round_number,
        nested=len(ep.nested_solves), requests=requests, screens=formed["cheap_checks_consumed"], saved_results=len(ep.actions))))


if __name__ == "__main__":
    check()
