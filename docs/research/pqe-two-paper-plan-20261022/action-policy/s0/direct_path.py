"""One explicit no-provider/no-science actual ask/host-through-chain check."""
from copy import deepcopy
from pathlib import Path
import json
import time

import runtime as r
import run_policy as run
from bfworld.agentlab.pqe20261024policy.training import PolicyFormationDriver
from bfworld.agentlab.pqe20261024policy.projection import encoded


class SoftwareEpisode(r.PolicyEpisode):
    def __init__(self,protocol,cache,ident):
        self.ident,self.role,self.condition=ident,"formation","H2"
        self.owner="SOFTWARE_ONLY_NO_PROVIDER_OWNER"
        self.protocol,self.cache=protocol,cache
        self.root=r.HERE/"direct-path"/ident
        self.root.mkdir(parents=True,exist_ok=False)
        self.limits=deepcopy(r.FORMATION)
        self.started=time.monotonic()
        self.absolute_deadline=self.started+self.limits["wall_s"]
        self.subscope,self.current_solver,self.fatal=None,None,None
        self.tools=self.numerical=self.evaluations=self.cheap_calls=0
        self.actions,self.nested_solves,self.requests=[],[],[]
        self.driver=None
        self.software_check=True
        self.training_slots_remaining,self.revision_pending=4,True
        self.fake_usage=dict(model_requests=0,spent_usd=0,output_tokens=0,wall_s=0)
        self.last_full=None
        self.revision_requests,self.full_feedbacks=[],[]
        old=r.read(r.BASE/"training-execution/s0/episodes/form-h2/training/round-01/task-02/method-transcript.json")
        self.fixture_candidates=deepcopy(old["steps"][0]["generate"]["candidates"])
        run.objects_for(self,r.checked(protocol["public_bindings"]["catalog"]))

    def budget(self):
        return {**self.fake_usage,"wall_s":time.monotonic()-self.started}

    def ready(self,paid=False):
        if self._remaining(self.budget())["wall_s_remaining"]<=0:
            raise ValueError("SOFTWARE_ABSOLUTE_DEADLINE")
        return self.budget()

    def audit(self,path,value):
        r.save(path,value)

    def paid_callback(self,body):
        # Deliberate software substitutes; never register an owner or forward.
        parent=r.checked(self.protocol["public_bindings"]["parent"])
        assert body["policy_parent_inline"]["code"]==parent["code"]
        assert body["policy_execution_contract"]["full_parent_code"]==parent["code"]
        self.requests.append(dict(site=body["site"],bytes=len(encoded(body)),
            wire_payload_bytes=len(r.p.encoded(r.p.callback_payload(body,body["max_output_tokens"]))),
            sha256=r.identity(body),all_six_parent_functions_inline=True,software_substitute=True))
        self.fake_usage["model_requests"]+=1
        self.fake_usage["output_tokens"]+=37
        self.fake_usage["spent_usd"]+=.001
        if body["site"]=="G-ATTRIBUTE":
            payload=dict(status="READY",explanations=[dict(kind="H_OR_G_DEFECT",support=[self.incident_id],
                refutation=["software substitute only"],missing_discrimination=["not a research inference"],target_sites=["H-GEN"])])
        elif body["site"]=="G-PROPOSE":
            payload=dict(status="OK",patches=[deepcopy(self.fixture_patch)])
        elif body["site"]=="H-GEN":
            index=min(len(self.current_solver.evaluated_candidates),1)
            payload=dict(status="OK",candidates=[deepcopy(self.fixture_candidates[index])])
        elif body["site"]=="H-RANK":
            index=min(len(self.current_solver.evaluated_candidates),1)
            payload=dict(selected_id=self.fixture_candidates[index]["id"],selection_basis="explicit software substitute",expected_discrimination_or_gain="UNKNOWN")
        else:
            raise ValueError("UNEXPECTED_SOFTWARE_CALLBACK_SITE:"+str(body["site"]))
        return dict(payload=payload,provider_status="COMPLETE",request_ids=[],software_substitute=True,
            new_provider_requests=0,usage=dict(status="SOFTWARE_FIXTURE",model_identity=r.p.MODEL_IDENTITY,
                input_tokens=0,output_tokens=37,cost=.001))

    def consume_one(self,entry,driver,folder):
        actual=r.lc.common_contract_check(driver.state,driver.pending["actual_input"],dict(remaining_actions=1))
        design={**deepcopy(driver.state["design"]),**actual.get("design_patch",{})}
        key=r.cache_key(entry,design,actual.get("dt_s"))
        if key not in self.cache:
            raise ValueError("SOFTWARE_REQUIRES_PREEXISTING_EXACT_SCIENCE_CACHE:"+key)
        original=Path(self.cache[key])
        public=r.read(original/"public-result.json")
        public["problem"]={**deepcopy(driver.state["problem"]),**actual.get("problem_patch",{})}
        public["usage"]=dict(numerical_inputs=0,reused=True,wall_s=0,software_check_only=True)
        self.tools+=1
        self.evaluations+=1
        reference=self.objects.register(r.read(original/"public-result.json"),path=original/"public-result.json")
        receipt=dict(public_result=r.bind(original/"public-result.json"),reused=True,new_full_dynamic_inputs=0,software_check_only=True)
        self.actions.append(dict(number=len(self.actions)+1,actual_input=deepcopy(actual),public_check=public["public_check"],public_object_ref=reference,receipt=receipt))
        self.last_full=public
        return public,reference,receipt


def check():
    if (r.HERE/"direct-path-check.json").exists() or (r.HERE/"direct-path").exists():
        raise ValueError("ONE_DIRECT_PATH_NO_UNRECORDED_RETRY")
    protocol=r.read(r.OUT/"shared/working-protocol.json")
    r.configure(protocol,True)
    cache=r.read(r.OUT/"shared/cache-seed.json")
    parent,history=(r.checked(protocol["public_bindings"][k]) for k in ("parent","history"))
    history=[{**deepcopy(x),"provenance":"SOFTWARE_FIXTURE","original_provenance":x["provenance"]} for x in history]
    ep=SoftwareEpisode(protocol,cache,"actual-policy-ask-host")
    ep.incident_id=history[0]["incident_id"]
    ep.fixture_patch=dict(parent_program=parent["program_id"],parent_sha256=r.identity(parent),
        target_sites=["H-GEN"],source_incidents=[ep.incident_id],applicability={},non_trigger_conditions={},
        change=dict(code={"H-GEN":parent["code"]["H-GEN"]+"\n"}),
        predicted_behavior_change=["Software substitute only; same actual ask path remains reachable"],
        side_effects=["No scientific change"],behavior_tests=["Original restricted fixture"],
        full_task_test_plan=["Saved original result replay only"],falsifier=["No actual ask or result Update reached"])
    round_number=0

    def train(program,version,remaining):
        nonlocal round_number
        round_number+=1
        feedback=run.train_program(ep,protocol,history,program,version,remaining,round_number)
        ep.full_feedbacks.append(feedback)
        return feedback

    driver=PolicyFormationDriver("H2",ep.planner,parent=parent,history=history,
        source_catalog=r.checked(protocol["public_bindings"]["catalog"]),training_tasks=protocol["training_task_descriptors"],
        training_execute=train,episode_id="SOFTWARE-ACTION-POLICY-CHAIN",model_identity=r.p.MODEL_IDENTITY,
        request_reserve_usd=.19,fixture_mode=True,revision_request_hook=lambda request:ep.revision_requests.append(deepcopy(request)))
    ep.driver=driver
    formed=driver.run()
    if round_number!=2 or len(ep.nested_solves)!=4 or len(ep.revision_requests)!=1:
        raise ValueError("ACTUAL_ASK_TRAIN_UPDATE_REVISION_CHAIN_NOT_REACHED:"+json.dumps(
            dict(rounds=round_number,nested=len(ep.nested_solves),revisions=len(ep.revision_requests),
                versions=[(v["status"],v.get("contract_feedback")) for v in formed["raw_versions"]])))
    assert all(x["status"]=="COMPLETE" for x in ep.full_feedbacks)
    assert all(x["limits"]["reserve_usd"]<=5 and x["limits"]["output_tokens_total"]<=131072
        and x["limits"]["provider_requests"]<=12 and x["limits"]["tool_calls"]<=24 and x["limits"]["wall_s"]<=900 for x in ep.nested_solves)
    assert len({x["parent_absolute_deadline"] for x in ep.nested_solves})==1
    assert ep.nested_solves[2]["before"]["provider_requests_remaining"]<ep.nested_solves[0]["before"]["provider_requests_remaining"]
    assert ep.nested_solves[2]["before"]["output_tokens_remaining"]<ep.nested_solves[0]["before"]["output_tokens_remaining"]
    assert ep.nested_solves[0]["remaining_training_slots"]==4 and ep.nested_solves[2]["remaining_training_slots"]==2
    for path in (ep.root/"training").rglob("method-transcript.json"):
        transcript=r.read(path)
        assert transcript["initial_update"]["status"]=="UPDATED"
        assert all(x["update_status"]=="UPDATED" for x in transcript["evaluated_candidates"])
    h4=SoftwareEpisode(protocol,cache,"attribution-final-request")
    h4.condition="H4"
    h4.incident_id=ep.incident_id
    attr=PolicyFormationDriver("H4",h4.planner,parent=parent,history=history,
        source_catalog=r.checked(protocol["public_bindings"]["catalog"]),training_tasks=protocol["training_task_descriptors"],
        training_execute=lambda *args:(_ for _ in ()).throw(ValueError("ATTRIBUTION_REQUEST_ONLY")),
        episode_id="SOFTWARE-ACTION-POLICY-ATTRIBUTION",model_identity=r.p.MODEL_IDENTITY,request_reserve_usd=.19,fixture_mode=True)
    h4.driver=attr
    attr._stage(lambda:attr.harness.attribute(attr.harness.extract(history),parent))
    assert len(h4.requests)==1 and h4.requests[0]["site"]=="G-ATTRIBUTE"
    forbidden=[r.task(entry)["task_id"] for entry in protocol["tasks"]]
    for episode in (ep,h4):
        for oid in episode.objects.objects:
            content=encoded(episode.objects._get(oid)).decode()
            assert not any(x in content for x in forbidden),"SEALED_TASK_EXPOSED"
        largest=max(episode.objects.objects,key=lambda x:episode.objects.objects[x]["serialized_bytes"])
        assert len(encoded(episode.objects.read(dict(object_id=largest,section="",offset=0))))<=14000
    requests=ep.requests+h4.requests
    assert {x["site"] for x in requests}>={"H-GEN","H-RANK","G-PROPOSE","G-ATTRIBUTE"}
    assert all(x["bytes"]<=220000 and x["wire_payload_bytes"]<=240000 for x in requests)
    r.save(r.HERE/"direct-path-check.json",dict(status="PASS_SOFTWARE_HOST_THROUGH_CHAIN",at=r.now(),software_only=True,
        all_required_chain_stages=True,new_provider_requests=0,new_full_scientific_inputs=0,
        actual_ask_and_sequential_host=True,all_six_parent_sources_inline=True,
        initial_update_and_full_result_update=True,next_decision_after_saved_result=True,
        feedback_and_one_autonomous_revision_request=True,training_rounds=round_number,
        nested_same_owner_and_absolute_deadline=True,fair_remaining_slots_reserved=True,
        nested_solves=ep.nested_solves,software_requests=requests,
        behavior_screen_inputs=formed["cheap_checks_consumed"],saved_result_evaluations=len(ep.actions),
        budgeted_software_operations=formed["cheap_checks_consumed"]+len(ep.actions)+len(requests)+1,
        no_software_output_in_formal_cache_history_or_result=True))
    print(json.dumps(dict(status="PASS_SOFTWARE_HOST_THROUGH_CHAIN",rounds=round_number,nested=len(ep.nested_solves),
        requests=len(requests),screens=formed["cheap_checks_consumed"],saved_results=len(ep.actions))))


if __name__=="__main__":
    check()
