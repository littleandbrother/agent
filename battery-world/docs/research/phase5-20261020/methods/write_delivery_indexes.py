#!/usr/bin/env python3
"""Write editorial indexes from the already collected and audited saved data."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--paper",required=True,type=Path)
    args=ap.parse_args()
    paper=args.paper
    manifest=json.loads((paper/"data/manifest.json").read_text())
    entries={e["path"]:e for e in manifest["entries"]}
    a=json.loads((paper/"generated/analysis.json").read_text())

    def j(rel):
        return json.loads((paper/"data"/rel).read_text())

    def save(name,value):
        (paper/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")

    def evidence(rel,pointer):
        result=dict(path="data/"+rel,sha256=entries[rel]["sha256"],field=pointer)
        if not rel.endswith(".json"):
            result["selector_kind"]="whole-file"
            return result
        value=j(rel)
        escape=lambda x:str(x).replace("~","~0").replace("/","~1")
        if isinstance(value,dict) and pointer in value:
            selectors=["/"+escape(pointer)]
        elif pointer in ("all","source identities and rows"):
            selectors=[""]
        elif pointer in ("saved witnesses","host history","saved checks","transfer"):
            selectors=["/"+{"saved witnesses":"witnesses","host history":"episodes",
                              "saved checks":"checks","transfer":"rows"}[pointer]]
        elif pointer in ("H0/G0","rows/canonical_rows","identity_scope and bound_files"):
            selectors=["/"+x for x in {"H0/G0":["H0","G0"],
                "rows/canonical_rows":["rows","canonical_rows"],
                "identity_scope and bound_files":["identity_scope","bound_files"]}[pointer]]
        elif pointer=="six choices":
            selectors=["/"+escape(x) for x in sorted(value)]
        elif pointer=="amendment":
            selectors=["/"+x for x in ("amendment_id","scope","preservation","falsifier","caps")]
        elif pointer=="O-transfer rows":
            selectors=["/rows/"+str(i) for i,row in enumerate(value["rows"]) if row["stage"]=="O-transfer"]
        elif ".*." in pointer:
            parent,child=pointer.split(".*.")
            container=value[parent]
            items=container.items() if isinstance(container,dict) else enumerate(container)
            selectors=["/"+escape(parent)+"/"+escape(k)+"/"+escape(child)
                       for k,row in items if child in row]
        elif pointer=="cases.candidate-002":
            selectors=["/cases/candidate-002"]
        else:
            raise ValueError("Missing exact evidence selector: "+rel+" # "+pointer)
        if not selectors:
            raise ValueError("Empty evidence selector: "+rel+" # "+pointer)
        for selector in selectors:
            current=value
            for part in selector.split("/")[1:]:
                key=part.replace("~1","/").replace("~0","~")
                current=current[int(key)] if isinstance(current,list) else current[key]
        result["selector_kind"]="RFC6901-json-pointers"
        result["json_pointers"]=selectors
        return result

    def claim(cid,section,text,boundary,sources,output):
        return dict(id=cid,manuscript_section=section,claim=text,claim_boundary=boundary,
                    evidence=[evidence(*s) for s in sources],reproduced_output="generated/analysis.json#"+output)

    claims=[
      claim("F1-controls","4.1","Six saved deterministic controls; all valid strategies match full, frozen trajectory differs on five changed cases.",
            "Public qualification only; no simulator speedup",[("early/f1a-controls.json","rows")],"F1"),
      claim("F4-initial","4.1","Three of four original prompt attempts deliver; final H0 is resource censored; 68 requests retained.",
            "Operator-authored prompt, exposed task, no promotion",[("early/paid-audit.json","rows")],"F4"),
      claim("F4-recovery","4.2-4.3","Actual nine-request method proposal fails; posthoc recovered model method remains experimental.",
            "Posthoc use is not a successful original submission",[("p2/p2-h-proposal-001/episode-result.json","status"),
            ("p2/method-retain-or-reject.json","automatic_H_text_source")],"F4"),
      claim("F4-confirmation","4.3","Independent promotion rejects initial-cache parity; base and revised designs both pass.",
            "Descriptive one-pair device outcomes; over-restrictive method not validated",[("p2/method-retain-or-reject.json","gate"),
            ("p2/method-external-registry.json","records")],"F4"),
      claim("F4-ordered","4.3","Revised reception precedes its reset; neither successful entry shows pending state crossing reset.",
            "Legacy labels retained, interpreted by actual time order",[("p2/ordered-state-audit.json","cases")],"F4"),
      claim("F4-prospective","5.1-5.2","Formal fixed H, ordinary reflection and typed procedure each pass 12/12, using 64/117/127 requests.",
            "Four fixed public tasks times three repetitions, not population rates",[("p3/actual-comparison.json","groups"),
            ("p3/formal-repeat-freeze.json","formal_repetitions"),("p3/main-tables.json","selection")],"F4"),
      claim("F1-actual-responses","5.3","107 admitted responses: 91 changed and 16 unchanged; valid strategies share full-feedback key.",
            "Five missing responses retained; no smaller-scope benefit",[("p3/actual-comparison.json","deterministic_controls")],"F1"),
      claim("F4-reset-reuse","5.3","Four fresh cross-reset choices reuse one historical ideal response.",
            "No new memory mechanism, physical replication or hardware qualification",[("p3/actual-comparison.json","groups.*.ordered_event_state"),
            ("p3/ordered-selected-witnesses.json","saved witnesses")],"F4"),
      claim("F5-history","6.1","Both proposers use one exact 75,955-byte packet from four public episodes; O0/final inputs excluded.",
            "Model exposure is not the larger host history",[("p4/config/model-history.json","episodes"),
            ("p4/config/public-history.json","host history"),("p4/config/frozen-parents.json","H0/G0")],"F5"),
      claim("F5-formation","6.1","One actual G1 formation generates twelve descendants through three conditional paired lineages.",
            "One formation, no independent G1 training replications or weight update",[("p4/G1-freeze.json","actual_formation_event_count"),
            ("p4/G1-formation-accounting.json","allocations"),("p4/actual-results.json","rows")],"F5"),
      claim("F5-selection","6.2","All 30 effective selections pass; six choices are frozen before final inputs.",
            "Rank uses effective cells; full costs retain every sibling and incident",[("p4/selection-complete.json","rows"),
            ("p4/final-selection-freeze.json","all_final_episodes_not_started"),("p4/selected-methods.json","six choices")],"F5/choices"),
      claim("F5-amendment","6.2","77 actual attempts resolve 73 cells; four original incidents plus four recoveries remain.",
            "Bounded loader/provenance repair, no semantic tuning",[("p4/actual-results.json","rows/canonical_rows"),
            ("p4/amendment-registration.json","amendment"),("p4/cache-repair-qualification.json","saved checks")],"F5"),
      claim("F5-final","6.3","Final H0 7/9, G0 6/9, G1 8/9; four censored entries retained; digital derivatives 18/18.",
            "Descriptive conditional result; no stable RSI",[("p4/actual-results.json","canonical_rows"),
            ("p4/final-details.json","rows"),("p4/analysis-summary.json","incomplete_final_cells")],"F5/final"),
      claim("F5-O0","6.3","Initial O0 candidate and rich-state control both pass; candidate has wrong nominal UNKNOWN judgment.",
            "No advantage over rich state; nominal O is not full A/R service",[("p4/actual-results.json","O-transfer rows"),
            ("p4/O0-transfer-results.json","transfer")],"F5/O0_transfer"),
      claim("F5-cost","6.4","Full G0/G1 cost includes all proposals, siblings, formation allocation, selection, incidents, recoveries and final entries.",
            "Final-only costs are not improvement cost; estimates not invoices",[("p4/actual-results.json","rows.*.usage"),
            ("p4/G1-formation-accounting.json","allocations")],"F5/arm_costs"),
      claim("F6-AR","7","Selected A/R candidate 002 is dark FAIL, FIFO FAIL, fixed-space NO_GO and NOT_ACCEPTED.",
            "Conditional rank timing repair; physical UNKNOWN; no foreign engineering assets",[("ar/continuation-001/external/result.json","candidates"),
            ("ar/continuation-001/external/ordering-policy-audit.json","cases.candidate-002"),
            ("ar/external-fixed-space-bound.json","numeric_decimal")],"F6"),
      claim("cost-finite","8","1238 unique finite requests, all SETTLED, upper estimate USD10.0268025; shared cells counted once.",
            "Token-rate estimate, not invoice or full end-to-end cost",[("billing/campaign-requests.json","rows")],"costs"),
      claim("cost-unknown","8","24 historical UNKNOWN rows remain outside the finite denominator; Codex assistance is unpriced and nonzero.",
            "No unknown row is assigned zero cost; end-to-end UNKNOWN",[("billing/historical-UNKNOWN.json","source identities and rows")],"costs"),
      claim("F2-F3-boundary","2,10","Fresh task entries are audited; no decision-span or organization ablation was performed.",
            "No local-suffix or multi-Agent speedup",[("p3/actual-comparison.json","matched_methods.*.H_reexecution_controls")],"F2,F3")
    ]
    save("claim-evidence.json",dict(schema_version="bf-methods-claim-evidence-v2",claims=claims,
        selector_policy="field is a human label; json_pointers are validated RFC6901 selectors. Empty pointer selects the complete JSON document. Wildcard labels expand only existing fields, preserving missing-response cases.",
        saved_data_only=True,default_H0_changed=False,stable_RSI=False,physical_qualification="UNKNOWN"))

    history=j("p4/config/model-history.json")
    interventions=[
      dict(id="operator-H1",kind="human/developer method authoring",evidence="data/early/paid-audit.json",scope="Original four prompt attempts; not autonomous G"),
      dict(id="AR-SSE-continuation",kind="explicit continuation and host transport repair",evidence="data/ar/continuation-001/protocol.json",scope="Same session/deadline/cumulative caps; 2MB to64MiB envelope only; original UNKNOWN snapshot retained"),
      dict(id="posthoc-H-adapter",kind="posthoc host recovery",evidence="data/p2/method-retain-or-reject.json",scope="No new paid proposal; original incomplete episode remains failed"),
      dict(id="prospective-role-and-cache",kind="developer apparatus/protocol implementation",evidence="data/p3/protocol.json",scope="Role separation and immutable matched cache; does not repair prior failure"),
      dict(id="mechanical-history-export",kind="developer mechanical projection",evidence="data/p4/config/model-history.json",scope="Identical source-bound projection across both G arms; rejected oversize first draft is recorded in prior receipt"),
      dict(id="cache-loader-amendment",kind="registered developer host repair",evidence="data/p4/amendment-registration.json",scope="CSV loading/provenance only; original faults, scientific semantics and all costs preserved"),
      dict(id="editorial-reproduction",kind="Codex manuscript/index implementation",evidence="README.md",scope="No model/provider/scientific/native execution; assistance UNPRICED_NONZERO; local reader/build fixes retained in coordinator receipts")
    ]
    save("cost-exposure-index.json",dict(schema_version="bf-method-cost-exposure-v1",
        model=dict(provider_reported_alias="deepseek-flash",independently_pinned_weights_version="UNKNOWN",
                   frozen_configuration_scope=j("p4/protocol-v1.1.json")["identity_scope"],
                   protocol_evidence=evidence("p4/protocol-v1.1.json","identity_scope and bound_files"),
                   no_model_weight_update=True),
        exposure=dict(model_packet=evidence("p4/config/model-history.json","episodes"),model_packet_bytes=75955,
                      model_packet_sha256=entries["p4/config/model-history.json"]["sha256"],
                      episodes=[e["episode_id"] for e in history["episodes"]],
                      host_packet=evidence("p4/config/public-history.json","all"),host_packet_bytes=257661,
                      O0_in_formation_or_selection=False,final_inputs_in_formation_or_selection=False,
                      final_D_current_task_facts_available=True,
                      H0_versus_descendant_history_confounded=True,G0_G1_history_matched=True),
        full_costs=a["costs"],lineage_costs=a["F5"]["arm_costs"],stage_costs=a["F5"]["stages"],
        host_incident_cost=a["F5"]["host_incident_cost"],
        formation_allocation=dict(actual_global_events=1,rule="One third per G1 lineage; once globally; not three formations",
                                  evidence=evidence("p4/G1-formation-accounting.json","allocations")),
        developer_interventions=interventions,phase5=dict(provider_requests=0,scientific_executions=0,native_mutations=0,new_environment=0),
        boundaries=["All siblings and incomplete episodes retain costs", "A/R continuation ledger includes original two requests; counted once",
                    "Shared method/interface baseline and full matrix counted once", "Historical UNKNOWN is outside finite campaign denominator",
                    "Usage-rate estimates are not invoices", "Full end-to-end and Codex cost UNKNOWN"]))

    ar=j("ar/continuation-001/external/result.json")
    candidates=[]
    for cid in ("candidate-001","candidate-002","candidate-003"):
        record=ar["candidates"][cid]
        base=f"ar/continuation-001/scientific/{cid}/"
        program=j(base+"candidate.json")
        candidates.append(dict(candidate=cid,selected=cid=="candidate-002",candidate_content_sha256=record["candidate_sha256"],
            files=[evidence(base+n,"all") for n in ("candidate.json","seal.json","source-manifest.json")]+
                  [evidence(f"ar/continuation-001/external/{cid}.json","all")],
            device=program["device"],program=program["program"],
            status=dict(dark_service="FAIL",strict_FIFO="FAIL",physical_qualification="UNKNOWN")))
    fifo=j("ar/continuation-001/external/ordering-policy-audit.json")
    save("AR-HANDOFF.json",dict(schema_version="bf-ar-candidate-bound-engineering-handoff-v1",
        selected_candidate="candidate-002",candidates=candidates,
        status=dict(fixed_space="NO_GO",dark_service="FAIL",strict_FIFO="FAIL",product="NOT_ACCEPTED",physical_qualification="UNKNOWN"),
        frozen_contract=evidence("ar/apparatus/configs/studies/phase1-20261020/ar/service-contract.v1.json","all"),
        frozen_world=evidence("ar/apparatus/packages/python/bfworld/src/bfworld/agentlab/campaign20261019/ar_service.py","all"),
        original_service_driver=evidence("ar/apparatus/scripts/campaign_ar_service.py","all"),
        original_external_service=evidence("ar/continuation-001/external/result.json","all"),
        strict_FIFO_witness=fifo["cases"]["candidate-002"]["ar-upload-dedup"]["first_witness"],
        necessary_bound=evidence("ar/external-fixed-space-bound.json","numeric_decimal"),
        conditional_repair="Fresh delay under newest-first rank improves; cannot satisfy original FIFO or fill absent dark measurements",
        ordering_contract_unchanged=True,readback_only=True,new_simulation=0,
        fabrication_assets_for_this_AR_candidate="NOT_PROVIDED_OR_QUALIFIED",
        identity_boundary="Separate piezo-node native/STEP/HEX assets, older P01 report and O-transfer artifacts cannot qualify this A/R candidate",
        continuation=dict(classification="ONE_CONTINUED_EPISODE",original_messages=8,original_tool_results=4,
                          cumulative_provider_requests=7,initial_two_requests_already_included=True),
        pending=["Any service relaxation or apparatus change needs a new contract and qualification",
                 "Physical source/storage/load/temperature/RF/manufacturing properties remain unqualified",
                 "No new scientific or hardware execution authorized by this saved-data handoff"]))

    refs=[
      ("mokhov2018","Andrey Mokhov; Neil Mitchell; Simon Peyton Jones","Build systems a la carte","ICFP 2018","https://www.microsoft.com/en-us/research/publication/build-systems-la-carte/","Executable dependency/rebuilding decomposition; no performance comparison here"),
      ("agrawal2026","Lakshya A. Agrawal et al.","GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning","arXiv:2507.19457v2 (2026)","https://arxiv.org/abs/2507.19457v2","Reflected execution histories for prompt updates; ordinary-reflection arm is not a GEPA implementation"),
      ("khattab2023","Omar Khattab et al.","DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines","arXiv:2310.03714 (2023)","https://arxiv.org/abs/2310.03714","Declarative LM pipelines and metric optimization; no direct comparison"),
      ("zelikman2024","Eric Zelikman; Eliana Lorch; Lester Mackey; Adam Tauman Kalai","Self-Taught Optimizer (STOP): Recursively Self-Improving Code Generation","COLM 2024; arXiv:2310.02304v3","https://arxiv.org/abs/2310.02304v3","Improving an LM-calling scaffold; distinguish from LM weight change; no direct comparison"),
      ("maeng2017","Kiwan Maeng; Alexei Colin; Brandon Lucia","Alpaca: Intermittent Execution without Checkpoints","PACMPL 1(OOPSLA), Article96 (2017)","https://abstract.ece.cmu.edu/pubs/alpaca.pdf","Task privatization and restart consistency; inherited ideal latch is not a new memory mechanism")
    ]
    save("references-verified.json",dict(verified_date="2026-10-20",method="Primary author/publisher pages and original paper; no external benchmark numbers reused",
        references=[dict(key=k,authors=au,title=t,publication=v,url=u,used_for=scope) for k,au,t,v,u,scope in refs]))
    overleaf=["main.tex","body.tex","hkustgz-paper.sty","assets/hkustgz-english.pdf",
              "generated/methods.tex","generated/choices.tex","generated/final.tex","generated/ar.tex","generated/costs.tex"]
    save("overleaf-files.json",dict(main_document="main.tex",publisher="S0 only, existing authorized project",
        files=[dict(path=p,sha256=hashlib.sha256((paper/p).read_bytes()).hexdigest(),bytes=(paper/p).stat().st_size) for p in overleaf],
        absolute_path_dependencies=False,additional_bibliography_files=False))
    print(json.dumps(dict(claims=len(claims),data_files=len(entries),paper_compile_assets=len(overleaf),index_status="WRITTEN")))


if __name__=="__main__":
    main()
