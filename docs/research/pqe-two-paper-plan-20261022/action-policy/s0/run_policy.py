"""One ordered parent-development, automatic-edit, and sealed-case package."""
from copy import deepcopy
from pathlib import Path
import argparse
import importlib.util
import json

import runtime as r

spec=importlib.util.spec_from_file_location("sealed_training_runner",r.BASE/"training-execution/s0/run_training.py")
saved=importlib.util.module_from_spec(spec)
spec.loader.exec_module(saved)
solve_program,close_episode=saved.solve_program,saved.close_episode


def objects_for(ep,catalog):
    from bfworld.agentlab.pqe20261024policy.projection import PublicObjects
    ep.objects=PublicObjects(ep.root/"public-objects")
    ep.public_catalog=[]
    for source_id,ref in catalog.items():
        value=r.checked(ref)
        oid=ep.objects.register(value,path=ref["path"])
        ep.public_catalog.append(dict(source_id=source_id,views=[dict(original_pointer="",object_id=oid)]))
    ep.objects.save_index()


def initialize():
    if (r.HERE/"initials-started.json").exists():
        raise ValueError("INITIALS_STARTED_NO_RETRY_OR_REPLACEMENT")
    manifest=r.read(r.OUT/"a/host/MANIFEST.json")
    sealed=r.read(r.BASE/"training-execution/shared/protocol.json")
    if r.adapter.source_identity()!=sealed["apparatus_source"]:
        raise ValueError("ORIGINAL_SCIENTIFIC_CONSUMER_CHANGED")
    if r.bind(r.OUT/"a/host/MANIFEST.json")["sha256"]!="ad1345c0ddf423955fbe72caee3868d3bc39aeb6007bd8c57eba3f961d94c217":
        # The exact expected digest is supplied by A; fail before science on mismatch.
        raise ValueError("A_MANIFEST_SHA_REQUIRED")
    entries=[]
    r.save(r.HERE/"initials-started.json",dict(at=r.now(),manifest=r.bind(r.OUT/"a/host/MANIFEST.json"),no_replacements=True))
    cache=r.read(r.BASE/"lc-service-learning/shared/cache-seed.json")
    for row in r.read(r.BASE/"training-execution/s0/resource-ledger.json")["attempts"]:
        if row["category"].startswith("form-") and row.get("public_result"):
            old_public=r.checked(row["public_result"])
            for training in r.read(r.BASE/"lc-service-learning/shared/protocol.json")["training_tasks"]:
                if old_public["task_sha256"]==r.identity(r.task(training)):
                    cache[r.cache_key(training,old_public["design"])]=str(Path(row["public_result"]["path"]).parent)
    r.save(r.OUT/"shared/cache-seed.json",cache)
    r.save(r.HERE/"resource-ledger.json",dict(package=r.PACKAGE,full_dynamic_inputs=0,full_dynamic_wall_s=0,
        candidate_evaluations=0,cache_reuses=0,cheap_checks=5,cheap_screen_reserved=16,
        attempts=[],new_engineering_inputs=0,new_test_initials=0))
    for original in manifest["entries"]:
        entry=deepcopy(original)
        t=r.task(entry)
        design,problem=r.checked(entry["initial_design"]),r.checked(entry["initial_problem"])
        if t["initial_design"]!=design or t["initial_problem"]!=problem:
            raise ValueError("A_INITIAL_BINDING_DISAGREEMENT")
        folder=r.HERE/"episodes"/("initial-"+entry["role"])
        try:
            public,receipt,source=r.full_execute(entry,dict(task=t,design=design,problem=problem),
                dict(actual_input=dict(operation="edit",design_patch={},problem_patch={})),
                folder,cache,"initial-"+entry["role"])
            entry.update(status="READY",initial_public_result=r.bind(source/"public-result.json"),
                initial_verdict=public["public_check"]["verdict"],initial_model_valid=public["model_valid"])
        except Exception as exc:
            entry.update(status="INITIAL_UNRESOLVED_NO_REPLACEMENT",initial_error=type(exc).__name__+":"+str(exc))
        entries.append(entry)
        resource=r.read(r.HERE/"resource-ledger.json")
        resource["new_test_initials"]=sum(x.get("new_full_dynamic_inputs",0) for x in resource["attempts"] if x["category"].startswith("initial-"))
        r.save(r.HERE/"resource-ledger.json",resource)
        r.save(r.HERE/"host/test-bindings.json",dict(at=r.now(),tasks=entries,manifest=r.bind(r.OUT/"a/host/MANIFEST.json")))
        print(json.dumps(dict(event="SEALED_INITIAL_COMPLETE",role=entry["role"],status=entry["status"],verdict=entry.get("initial_verdict"))),flush=True)
    r.save(r.OUT/"shared/cache-seed.json",cache)


def solve_episode(ident,role,condition,entry,program,history,catalog,protocol,cache,actions_max):
    ep=r.PolicyEpisode(ident,r.task(entry),condition,protocol,cache,role)
    objects_for(ep,catalog)
    error,result=None,None
    try:
        ep.start_server()
        result,_=solve_program(ep,program,entry,history,ep.root/"solve",actions_max=actions_max)
    except Exception as exc:
        error=type(exc).__name__+":"+str(exc)
        if any(x in str(exc) for x in ("SOURCE_CHANGED","ROW_CHANGED","BINDING_STOP","COMPACTION_READBACK","UNKNOWN_STOP")):
            ep.fatal=error
    row=close_episode(ep,error,dict(result=result,common_history_sha256=r.identity(history),
        program_sha256=r.identity(program),nested_solve_count=len(ep.nested_solves)))
    if ep.fatal:
        raise ValueError(ep.fatal)
    return row


def add_public_history(history,catalog,category_prefix):
    from bfworld.agentlab.pqe20261023bold.contracts import compact_feedback
    from bfworld.agentlab.pqe20261024lc.projection import project_public_result
    history,catalog=deepcopy(history),deepcopy(catalog)
    for number,row in enumerate(r.read(r.HERE/"resource-ledger.json")["attempts"]):
        if not any(row["category"].startswith(p) for p in category_prefix) or not row.get("public_result"):
            continue
        public=r.checked(row["public_result"])
        if public.get("execution_status")=="NO_EXECUTION":
            continue
        sid="action-policy-public-"+row["category"]+"-"+str(number)
        iid="ACTION-POLICY-PUBLIC-"+row["category"].upper()+"-"+str(number)
        catalog[sid]=row["public_result"]
        world="LC_PV" if "LC-PV" in public["task_id"] else "DOOR"
        history.append(dict(incident_id=iid,source_id=sid,allowed_for_learning=True,
            provenance="PUBLIC_EXECUTION",phase="development-or-training",decision=deepcopy(row["decision"]),
            record_ref=[sid],result=compact_feedback(public,sid),typed_view=project_public_result(public,sid,world_kind=world)))
    return history,catalog


def add_parent_development_outcomes(history,catalog,rows,entries):
    from bfworld.agentlab.pqe20261023bold.contracts import compact_feedback
    from bfworld.agentlab.pqe20261024lc.projection import project_public_result
    for index,(row,entry) in enumerate(zip(rows,entries),1):
        result=row.get("result")
        if result is None:
            raise ValueError("ACTUAL_PARENT_DEVELOPMENT_REFERENCE_MISSING_NO_FORMATION")
        reference=(result["actions"][-1]["receipt"]["public_result"] if result["actions"] else entry["initial_public_result"])
        public=r.checked(reference)
        sid=f"action-policy-parent-development-{index}"
        trajectory=dict(episode=row["episode"],task_id=result["task_id"],program_sha256=row["program_sha256"],
            initial_verdict=result["initial_verdict"],final_verdict=result["final_verdict"],model_valid=result["model_valid"],
            correct_stop=result["correct_stop"],action_signature=result["action_signature"],
            actual_inputs=[x["actual_input"] for x in result["actions"]],accounting=row["accounting"],
            public_result=reference,provenance="ACTUAL_COMMON_PARENT_DEVELOPMENT")
        path=r.OUT/"shared"/(sid+".json")
        r.save(path,trajectory)
        catalog[sid]=reference
        catalog[sid+"-trajectory"]=r.bind(path)
        history.append(dict(incident_id=sid.upper(),source_id=sid,allowed_for_learning=True,
            provenance="PUBLIC_EXECUTION",phase="common-parent-development",record_ref=[sid,sid+"-trajectory"],
            decision=trajectory,result=compact_feedback(public,sid),
            typed_view=project_public_result(public,sid,world_kind="LC_PV" if entry["world"]=="LC-PV" else "DOOR")))
    return history,catalog


def train_program(ep,protocol,history,program,version,remaining_full,round_no):
    before=ep.numerical
    budget_before=ep.budget()
    if version.get("revision_index",0)>0:
        ep.revision_pending=False
        ep.training_slots_remaining=2
    rows,refs=[],[]
    for number,entry in enumerate(protocol["training_tasks"]):
        row,local=solve_program(ep,program,entry,history,
            ep.root/"training"/f"round-{round_no:02d}"/f"task-{number+1:02d}",actions_max=2)
        rows.append(row)
        refs+=local
    after=ep.budget()
    feedback=dict(status="COMPLETE",full_inputs=ep.numerical-before,task_results=rows,execution_refs=refs,
        owner_budget_after=ep.snapshot(),round=round_no,version=deepcopy(version),
        cost_summary=dict(all_in_cost_usd=after["spent_usd"],total_rate_estimate_usd=after["spent_usd"],
            scope="Formation owner cumulative proposal, any rejected/previous version, training and revision costs through this version; pinned-rate estimate, not invoice",
            formation_owner_cumulative_requests=after["model_requests"],
            training_round_rate_estimate_usd=after["spent_usd"]-budget_before["spent_usd"],
            training_round_requests=after["model_requests"]-budget_before["model_requests"],
            formation_owner_cumulative_output_tokens=after["output_tokens"],
            all_prior_proposal_training_rejection_cost_included=True,invoice_claim=False))
    if feedback["full_inputs"]>min(4,remaining_full) or ep.evaluations>8:
        raise ValueError("TRAINING_FULL_CAP_DISAGREEMENT")
    ep.audit(ep.root/"training"/f"round-{round_no:02d}"/"feedback.json",feedback)
    return feedback


def formation_episode(ident,condition,protocol,cache):
    from bfworld.agentlab.pqe20261024policy.training import PolicyFormationDriver
    parent=r.checked(protocol["public_bindings"]["parent"])
    history=r.checked(protocol["public_bindings"]["history"])
    catalog=r.checked(protocol["public_bindings"]["catalog"])
    ep=r.PolicyEpisode(ident,dict(task_id="PUBLIC_DEVELOPMENT_TRAINING_ONLY",initial_design={},initial_problem={}),condition,protocol,cache,"formation")
    objects_for(ep,catalog)
    error,formation,round_count=None,None,0

    def train(program,version,remaining_full):
        nonlocal round_count
        if round_count>=2:
            raise ValueError("ONE_ROUND_PER_ORIGINAL_AND_REVISION_ONLY")
        round_count+=1
        return train_program(ep,protocol,history,program,version,remaining_full,round_count)

    try:
        ep.start_server()
        driver=PolicyFormationDriver(condition=condition,planner_callback=ep.planner,parent=parent,history=history,
            source_catalog=catalog,training_tasks=protocol["training_task_descriptors"],training_execute=train,
            episode_id=ident,model_identity=r.p.MODEL_IDENTITY,request_reserve_usd=.19,
            limits=dict(provider_requests=30,tool_calls=60,new_numerical_inputs=8,wall_s=2400,
                output_tokens_per_request=65536,output_tokens_total=393216,reserve_usd=15))
        ep.driver=driver
        formation=driver.run()
        ep.audit(ep.root/"formation.json",formation)
        r.save(ep.root/"selected-program.json",formation["selected_program"])
    except Exception as exc:
        error=type(exc).__name__+":"+str(exc)
        if any(x in str(exc) for x in ("SOURCE_CHANGED","ROW_CHANGED","BINDING_STOP","COMPACTION_READBACK","UNKNOWN_STOP")):
            ep.fatal=error
        if ep.driver is not None:
            ep.audit(ep.root/"retained-driver-error.json",ep.driver.transcript())
    finally:
        used=formation.get("cheap_checks_consumed",0) if formation else getattr(ep.driver,"cheap_checks_consumed",0)
        resource=r.read(r.HERE/"resource-ledger.json")
        resource["cheap_checks"]+=used
        resource["cheap_screen_reserved"]-=8
        if not 0<=used<=8 or resource["cheap_screen_reserved"]<0 or resource["cheap_checks"]>120:
            raise ValueError("FINITE_SCREEN_RESERVATION_DISAGREEMENT")
        r.save(r.HERE/"resource-ledger.json",resource)
    row=close_episode(ep,error,dict(selected_descendant=bool(formation and formation.get("selected_candidate")),
        training_rounds=round_count,nested_solve_count=len(ep.nested_solves)))
    if ep.fatal:
        raise ValueError(ep.fatal)
    return row,formation


def run():
    protocol=r.read(r.PROTOCOL)
    r.configure(protocol)
    r.validate(protocol)
    if (r.HERE/"run-started.json").exists():
        raise ValueError("FINITE_PACKAGE_STARTED_NO_REPLACEMENT")
    r.save(r.HERE/"run-started.json",dict(at=r.now(),package=r.PACKAGE))
    cache=r.read(r.OUT/"shared/cache-seed.json")
    parent=r.checked(protocol["public_bindings"]["parent"])
    history=r.checked(protocol["public_bindings"]["history"])
    catalog=r.checked(protocol["public_bindings"]["catalog"])
    rows,formed=[],{}
    with r.runtime_scope():
        for number,entry in enumerate(protocol["training_tasks"]):
            rows.append(solve_episode(f"dev{number+1}","development","H1",entry,parent,history,catalog,protocol,cache,2))
            r.save(r.HERE/"batch-result.json",dict(package=r.PACKAGE,rows=rows,complete=False))
        history,catalog=add_public_history(history,catalog,["dev"])
        history,catalog=add_parent_development_outcomes(history,catalog,rows,protocol["training_tasks"])
        r.save(r.OUT/"shared/formation-history.json",history)
        r.save(r.OUT/"shared/formation-catalog.json",catalog)
        formation_protocol=deepcopy(protocol)
        formation_protocol["public_bindings"]["history"]=r.bind(r.OUT/"shared/formation-history.json")
        formation_protocol["public_bindings"]["catalog"]=r.bind(r.OUT/"shared/formation-catalog.json")
        for desc,row in zip(formation_protocol["training_task_descriptors"],rows):
            result=row.get("result") or {}
            desc.update(parent_final_verdict=result.get("final_verdict","UNKNOWN"),
                parent_correct_stop=result.get("correct_stop",False),parent_model_valid=result.get("model_valid",False),
                parent_result_sha256=result.get("result_sha256"),parent_total_cost=row["accounting"].get("cache_aware_rate_estimate_usd"),
                parent_basis="Actual common model-decision parent development solve in this package; all groups receive same record.")
        r.save(r.OUT/"shared/formation-inputs.json",formation_protocol)
        r.save(r.HERE/"baseline-milestone-ready.json",dict(at=r.now(),package=r.PACKAGE,
            actual_parent_development_complete=True,episodes=[r.bind(r.HERE/"episodes"/f"dev{i}"/"episode-result.json") for i in (1,2)],
            shared_formation_inputs=r.bind(r.OUT/"shared/formation-inputs.json")))
        print(json.dumps(dict(event="BASELINE_MILESTONE_READY",continue_without_approval=True)),flush=True)
        for ident,condition in (("form-h2","H2"),("form-h4","H4")):
            r.validate(formation_protocol)
            row,formation=formation_episode(ident,condition,formation_protocol,cache)
            rows.append(row)
            formed[condition]=formation
            r.save(r.HERE/"batch-result.json",dict(package=r.PACKAGE,rows=rows,complete=False))
        history,catalog=add_public_history(history,catalog,["form-"])
        r.save(r.OUT/"shared/merged-test-history.json",history)
        r.save(r.OUT/"shared/merged-test-catalog.json",catalog)
        r.save(r.HERE/"formed-program-freeze.json",dict(at=r.now(),test_feedback_seen=False,
            merged_history=r.bind(r.OUT/"shared/merged-test-history.json"),merged_catalog=r.bind(r.OUT/"shared/merged-test-catalog.json"),
            conditions={c:dict(diagnostic_candidate=bool(v and v.get("selected_candidate")),
                program=r.bind(r.HERE/"episodes"/("form-"+c.lower())/"selected-program.json") if v else None) for c,v in formed.items()}))
        for entry in protocol["tasks"]:
            for condition in ("H1","H2","H4"):
                ident=entry["role"]+"-"+condition.lower()
                if entry["status"]!="READY" or (condition!="H1" and not (formed.get(condition) or {}).get("selected_candidate")):
                    row=dict(episode=ident,role=entry["role"],condition=condition,status="NOT_EXECUTED_INITIAL_UNRESOLVED" if entry["status"]!="READY" else "NOT_EXECUTED_NO_DIAGNOSTIC_DESCENDANT",provider_requests=0,candidate_evaluations=0)
                    r.save(r.HERE/"skipped"/(ident+".json"),row)
                else:
                    program=parent if condition=="H1" else formed[condition]["selected_program"]
                    row=solve_episode(ident,entry["role"],condition,entry,program,history,catalog,protocol,cache,3)
                rows.append(row)
                r.save(r.HERE/"batch-result.json",dict(package=r.PACKAGE,rows=rows,complete=False))
                r.validate(protocol)
    r.save(r.HERE/"batch-result.json",dict(package=r.PACKAGE,at=r.now(),rows=rows,complete=True,
        provider_after=r.host.provider_snapshot(),storage=r.capacity()))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("phase",choices=["initials","run","_execute"])
    parser.add_argument("input",nargs="?")
    args=parser.parse_args()
    if args.phase=="_execute":
        r.execute_child(args.input)
    elif args.phase=="initials":
        initialize()
    else:
        run()


if __name__=="__main__":
    main()
