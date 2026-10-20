#!/usr/bin/env python3
"""F1--F6 saved-data readback. Standard library only; no apparatus imports.

Embedded artifact locators in historical JSON are provenance, never input paths.
Only the relative paths in data/manifest.json are opened. Outputs contain counts,
tables and audits, not new model decisions or scientific responses.
"""
import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


def digest(body):
    return hashlib.sha256(body).hexdigest()


def canonical(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def amount(value):
    return Decimal(str(value))


def near(a, b):
    return abs(amount(a) - amount(b)) < Decimal("0.000000001")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False,
                               allow_nan=False) + "\n")


class SavedData:
    def __init__(self, root):
        self.root = root.resolve()
        self.manifest = json.loads((self.root / "manifest.json").read_text())
        self.entries = {e["path"]: e for e in self.manifest["entries"]}
        require(len(self.entries) == len(self.manifest["entries"]), "duplicate data path")

    def path(self, rel):
        p = PurePosixPath(rel)
        require(not p.is_absolute() and ".." not in p.parts, "nonrelative manifest path")
        target = self.root.joinpath(*p.parts).resolve()
        require(target.is_relative_to(self.root), "data escapes selected root")
        return target

    def verify(self, override=None):
        for rel, rec in self.entries.items():
            b = override(rel) if override else self.path(rel).read_bytes()
            require(b is not None, "MISSING_SAVED_INPUT: " + rel)
            require(len(b) == rec["bytes"] and digest(b) == rec["sha256"],
                    "SAVED_INPUT_HASH_MISMATCH: " + rel)

    def raw(self, rel):
        require(rel in self.entries, "unregistered input: " + rel)
        return self.path(rel).read_bytes()

    def j(self, rel):
        return json.loads(self.raw(rel))


def rows_csv(path, rows):
    if rows:
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def usage_total(rows):
    return dict(episodes=len(rows), requests=sum(r["usage"]["requests"] for r in rows),
                upper_usd=f'{sum((amount(r["usage"]["usd"]) for r in rows), Decimal(0)):.7f}',
                summed_wall_s=sum(r["usage"]["wall_s"] for r in rows))


def ledger_readback(data, prefix, expected_count, master, seen):
    rows = []
    for rel in sorted(data.entries):
        if rel.startswith(prefix) and rel.endswith("/provider-costs.json"):
            ledger = data.j(rel)
            require(not ledger["unknown_or_missing_usage"], "unresolved finite usage")
            require(ledger["unsettled_reserved_usd"] == 0, "unsettled reservation")
            require(len(ledger["rows"]) == ledger["requests"], "ledger request count")
            charge = Decimal(0)
            for row in ledger["rows"]:
                rid = row["id"]
                require(rid not in seen, "double-counted provider request")
                require(rid in master and row["status"] == "SETTLED", "unsettled/missing request")
                require(near(row["charged"], master[rid]["charged"]) and
                        row["response_hash"] == master[rid]["response_hash"], "request identity mismatch")
                seen.add(rid)
                rows.append(row)
                charge += amount(row["charged"])
            require(near(charge, ledger["settled_charge_upper_bound_usd"]), "ledger sum")
    require(len(rows) == expected_count, prefix + " request denominator")
    return rows


def audit(data):
    out, tables = {}, {}
    p3 = data.j("p3/actual-comparison.json")
    groups = list(p3["groups"].values())
    controls = p3["deterministic_controls"]
    early = data.j("early/f1a-controls.json")["rows"]
    for row in early:
        for key in ("dependency", "boundary", "exact_response_cache"):
            require(row[key] == row["full"], "early response control differs from full")
    changed = [r for r in controls if r["changed_D"]]
    for r in controls:
        valid = [s for s in r["strategies"] if s["strategy"] != "frozen-trajectory"]
        require(len({s["actual_execution_key"] for s in valid}) == 1, "execution-key disagreement")
        require(all(s["eligible"] and s["scope"] == "full-feedback-response" for s in valid),
                "unqualified local scope")
        require(not r["new_scientific_executions_for_comparison"], "unexpected new computation")
        frozen = next(s for s in r["strategies"] if s["strategy"] == "frozen-trajectory")
        if r["changed_D"]:
            require(not frozen["eligible"], "stale changed-input trajectory admitted")
    out["F1"] = dict(early_controls=len(early), early_stale_mismatches=sum(not r["fixed_matches_full"] for r in early),
                     actual_response_records=len(controls), changed_D=len(changed),
                     unchanged_D=len(controls)-len(changed), groups_without_admitted_response=len(groups)-len(controls),
                     valid_strategies_share_full_response=True, extra_scientific_executions=0,
                     speedup="NOT_ESTABLISHED")

    matches = p3["matched_methods"]
    require(all(all(r["parity"].values()) for r in matches), "method parity failed")
    require(all(g["fresh_task_entry"] for g in groups), "nonfresh design entry")
    out["F2"] = dict(status="NO_DECISION_SPAN_ABLATION", fresh_design_groups=len(groups),
                     matched_method_groups=len(matches), all_recorded_parity_checks_pass=True,
                     H_change_scope="TASK_ENTRY", local_suffix_advantage="NOT_EVALUATED")
    out["F3"] = dict(status="NO_ORGANIZATION_COMPARISON", organization="single participant Agent per episode",
                     multi_agent_speedup="NOT_EVALUATED", independent_G1_formations=1)

    table = []
    for stage in ("pilot", "formal"):
        for condition in ("complete-raw", "ordinary_reflection", "proposed_method"):
            rows = [g for g in groups if g["stage"] == stage and g["condition"] == condition]
            r = dict(stage=stage, condition=condition, groups=len(rows),
                     passed=sum(g["complete_service"] == "PASS" for g in rows),
                     requests=sum(g["requests"] for g in rows),
                     upper_usd=f'{sum((amount(g["settled_upper_usd"]) for g in rows), Decimal(0)):.7f}',
                     updates=sum((g.get("H_proposal") or {}).get("decision") == "propose" for g in rows),
                     no_updates=sum((g.get("H_proposal") or {}).get("decision") == "no-update" for g in rows))
            table.append(r)
    formal = [r for r in table if r["stage"] == "formal"]
    require([(r["passed"], r["requests"]) for r in formal] == [(12,64),(12,117),(12,127)],
            "formal method result differs")
    selection = data.j("p3/main-tables.json")["selection"]
    p2 = data.j("p2/method-retain-or-reject.json")
    require(not p2["retained"] and not p2["default_H_changed"], "posthoc promotion")
    require("PARITY_INITIAL_CACHE_SHA256" in p2["gate"]["failures"], "lost cache failure")
    audit4 = data.j("early/paid-audit.json")
    ordered = data.j("p3/ordered-selected-witnesses.json")
    witnesses = [g for g in groups if (g.get("ordered_event_state") or {}).get("pending_event_retained_across_reset")]
    require(len(witnesses) == 4 and len({g["execution"]["execution_key"] for g in witnesses}) == 1,
            "cross-reset response double-counting")
    out["F4"] = dict(formal=formal, pilot=[r for r in table if r["stage"] == "pilot"],
                     selected_base_H_unchanged=True, selection=selection,
                     early_actual_attempts=len(audit4["rows"]),
                     early_resource_censored=sum(r["resource_censored"] for r in audit4["rows"]),
                     posthoc_method_status=p2["status"], posthoc_rejection=p2["gate"]["failures"],
                     cross_reset_choices=len(witnesses), distinct_historical_cross_reset_responses=1,
                     formal_scope="Four fixed tasks, three repetitions; task-local H, not global H transfer")
    tables["F4-methods"] = table

    p4 = data.j("p4/actual-results.json")
    parents=data.j("p4/config/frozen-parents.json")
    require(canonical(parents["H0"]["method_text"])==parents["H0"]["method_sha256"] and
            canonical(parents["G0"]["proposal_procedure"])==parents["G0"]["procedure_sha256"],
            "frozen H0/G0 identity")
    packet=data.raw("p4/config/model-history.json")
    require(len(packet)==75955 and digest(packet)=="7e7f379d80746d0572f6ef75214129a4c08292a4dfe8270b4d9f953308318cf9",
            "model exposure packet changed")
    exposed=data.j("p4/config/model-history.json")["episodes"]
    require({e["episode_id"] for e in exposed}=={"p2-h-proposal-001","p3-formal-1-1-complete-raw-d",
            "p3-formal-1-1-ordinary_reflection-h","p3-formal-1-1-ordinary_reflection-d"}, "history exposure changed")
    raw, effective = p4["rows"], p4["canonical_rows"]
    require(len(raw)==77 and len(effective)==73, "phase4 attempt/cell denominator")
    require(sum(r["host_incident_overhead"] for r in raw)==4, "host attempts lost")
    final = [r for r in effective if r["stage"] == "final"]
    arm = lambda r: r.get("arm") or r.get("condition")
    ft, costs = [], []
    for label in ("H0", "G0", "G1"):
        rr = [r for r in final if arm(r)==label]
        passed = sum(r["service"]=="PASS" for r in rr)
        failed = sum(r["service"]=="FAIL" for r in rr)
        incomplete = len(rr)-passed-failed
        ft.append(dict(arm=label, cells=len(rr), passed=passed, submitted_fail=failed, incomplete=incomplete,
                       judgment_disagreements=sum(bool(r["wrong_service_judgment"]) for r in rr)))
        for scope, rs in (("final",rr), ("full", [r for r in raw if arm(r)==label])):
            if scope=="full" and label=="G1":
                rs += [r for r in raw if r["stage"]=="formation"]
            costs.append(dict(arm=label, scope=scope, **usage_total(rs)))
    require([(r["passed"],r["submitted_fail"],r["incomplete"]) for r in ft]==[(7,1,1),(6,1,2),(8,0,1)],
            "final results or incomplete denominators changed")
    final_tasks=[]
    for task in sorted({r["task"] for r in final}):
        for label in ("H0","G0","G1"):
            rr=[r for r in final if r["task"]==task and arm(r)==label]
            final_tasks.append(dict(task=task,arm=label,cells=len(rr),passed=sum(r["service"]=="PASS" for r in rr),
                                    submitted_fail=sum(r["service"]=="FAIL" for r in rr),
                                    incomplete=sum(r["service"] not in ("PASS","FAIL") for r in rr)))
    choices=[]
    selected=data.j("p4/selected-methods.json")
    for lineage in (1,2,3):
        for label in ("G0","G1"):
            key=f"L{lineage}-{label}"
            sel=data.j(f"p4/selections/{key}.json")
            ranked=sorted(sel["candidate_metrics"], key=lambda r:(-r["complete_service_passes"],
                          r["wrong_service_judgments"], r["total_charged_requests"], r["descendant_index"]))
            chosen=sel["selected_descendant_index"]
            require(chosen==ranked[0]["descendant_index"] and not sel["final_results_consulted"],
                    "selection differs or final contamination")
            h=data.j(f"p4/episodes/{key}-h{chosen}-proposal/scientific/submission.json")["proposal"]
            text=selected[key]["selected_H_text"]
            require(text.endswith("\n\n"+h["method_text"]), "selected H not actual authored text")
            prefix=text[:-(len(h["method_text"])+2)]
            require(canonical(prefix)==sel["H0_sha256"] and canonical(text)==sel["selected_H_sha256"],
                    "H0/H composition identity")
            choices.append(dict(lineage=key, selected_child=chosen,
                                h1_requests=sel["candidate_metrics"][0]["total_charged_requests"],
                                h2_requests=sel["candidate_metrics"][1]["total_charged_requests"],
                                consumed_H_sha256=canonical(text)))
            for r in final:
                if r["lineage"]==lineage and arm(r)==label:
                    payload=data.j(f'p4/episodes/{r["episode"]}/participant-payload.json')
                    control=data.j(f"p4/episodes/L{lineage}-H0-{r['slot']}/participant-payload.json")
                    require(control["instruction"].startswith(prefix), "H0 final prefix changed")
                    directive=control["instruction"][len(prefix):]
                    require(payload["instruction"]==text+directive,
                            "final D did not consume selected H plus common D instruction")
    freeze=data.j("p4/final-selection-freeze.json")
    require(freeze["all_final_episodes_not_started"] and not freeze["final_results_consulted"], "freeze timing")
    require(canonical(selected)==freeze["selected_methods_sha256"], "selected method freeze identity")
    form=data.j("p4/G1-freeze.json")
    require(form["actual_formation_event_count"]==1 and canonical(form["proposal_procedure"])==form["procedure_sha256"],
            "G1 formation identity")
    for s in [r for r in effective if r["stage"]=="selection"]:
        require(s["service"]=="PASS", "effective selection result")
    stages=[dict(stage=stage, **usage_total([r for r in raw if r["stage"]==stage]))
            for stage in ("O-transfer","formation","proposal","selection","final")]
    require(sum(r["episodes"] for r in stages)==77 and sum(r["requests"] for r in stages)==367,
            "phase4 stage accounting does not cover every attempt")
    transfer=[dict(episode=r["episode"],service=r["service"],participant_judgment=r["participant_judgment"],
                   wrong_judgment=r["wrong_service_judgment"], **usage_total([r]))
              for r in effective if r["stage"]=="O-transfer"]
    out["F5"]=dict(actual_attempts=len(raw), canonical_cells=len(effective), final=ft, final_tasks=final_tasks,
                    choices=choices, effective_selection_PASS=30, H_siblings=12,
                    G1_formations=1, conditional_lineage_pairs=3, default_H0_changed=False,
                    model_history_bytes=len(packet), model_history_sha256=digest(packet),
                    host_incident_attempts=4, host_incident_cost=usage_total([r for r in raw if r["host_incident_overhead"]]),
                    recovery_attempts=len([r for r in raw if r["recovery_of"]]),
                    all_cost=usage_total(raw), arm_costs=costs, stages=stages, O0_transfer=transfer,
                    inference="Descriptive, conditional on one G1 formation; no stable RSI")
    tables.update({"F5-final":ft,"F5-final-tasks":final_tasks,"F5-selections":choices,"F5-costs":costs,"F5-stages":stages,
                   "F5-O0-transfer":transfer})

    ar=data.j("ar/continuation-001/external/result.json")
    fifo=data.j("ar/continuation-001/external/ordering-policy-audit.json")
    bounds=data.j("ar/external-fixed-space-bound.json")["numeric_decimal"]
    require(amount(bounds["dark_capacitance_lower_bound_f"])>amount(bounds["cold_capacitance_upper_bound_f"]),
            "fixed-space bound changed")
    require(ar["submitted_candidate"]=="candidate-002", "A/R candidate selection changed")
    art=[]
    for cid, result in ar["candidates"].items():
        candidate=data.j(f"ar/continuation-001/scientific/{cid}/candidate.json")
        require(canonical(candidate)==result["candidate_sha256"], "foreign A/R candidate")
        require(fifo["cases"][cid]["ar-upload-dedup"]["strict_fifo"]=="FAIL", "lost FIFO failure")
        require(result["cases"]["ar-history-nvm"]["computational_services"]=="FAIL", "lost dark failure")
        detail=data.j(f"ar/continuation-001/external/{cid}.json")["cases"]["ar-history-nvm"]
        art.append(dict(candidate=cid, selected=cid==ar["submitted_candidate"],
                        retry_s=candidate["program"]["retry_s"],
                        history_samples=result["cases"]["ar-history-nvm"]["sample_count"],
                        late_backlog=len(detail["gates"]["recovery_upload"]["late_sequences"]),
                        missed_events=detail["gates"]["temperature_events"]["missed"],
                        dark_service="FAIL", fresh_delay_under_rank=result["cases"]["ar-upload-dedup"]["gates"]["fresh_receive_delay"],
                        strict_FIFO="FAIL", candidate_content_sha256=canonical(candidate)))
    out["F6"]=dict(fixed_space="NO_GO", dark_service="FAIL", strict_FIFO="FAIL", product="NOT_ACCEPTED",
                    physical_qualification="UNKNOWN", selected_candidate="candidate-002", candidates=art,
                    saved_necessary_bounds=bounds, new_simulations=0,
                    engineering_boundary="Executable ideal A/R program, not a fabricated device or transferable proof for another candidate")
    tables["F6-candidates"]=art

    campaign=data.j("billing/campaign-requests.json")["rows"]
    master={r["id"]:r for r in campaign}
    require(len(master)==len(campaign)==1238, "finite campaign unique denominator")
    upper, aware=Decimal(0),Decimal(0)
    for row in campaign:
        require(row["status"]=="SETTLED" and row["usage"] and not row["error"], "finite request unsettled")
        u=json.loads(row["usage"]) if isinstance(row["usage"],str) else row["usage"]
        p,c=u["prompt_tokens"],u["completion_tokens"]
        hit=u.get("prompt_cache_hit_tokens",0)
        miss=u.get("prompt_cache_miss_tokens",p-hit)
        calculated=(Decimal(p)*Decimal("0.30")+Decimal(c)*Decimal("1.20"))/1_000_000
        require(near(calculated,row["charged"]), "token-based upper charge differs")
        upper+=amount(row["charged"])
        aware+=(Decimal(hit)*Decimal("0.006")+Decimal(miss)*Decimal("0.30")+Decimal(c)*Decimal("1.20"))/1_000_000
    seen=set()
    p2rows=ledger_readback(data,"p2/",25,master,seen)
    p3rows=ledger_readback(data,"p3/episodes/",771,master,seen)
    p4rows=ledger_readback(data,"p4/episodes/",367,master,seen)
    arfinal=data.j("ar/phase1-pi-evidence.json")
    initial_rows=arfinal["later_original_settlement"]["rows"]
    arr=data.j("ar/continuation-001/provider-costs.json")["rows"]
    # This is the cumulative continuation ledger, including the original segment.
    ar_ids={r["id"]:r for r in arr}
    require(all(r["id"] in ar_ids and near(r["charged"],ar_ids[r["id"]]["charged"])
                for r in initial_rows), "continuation lost original settled requests")
    for row in arr:
        require(row["id"] not in seen and row["id"] in master, "A/R request double counted")
        require(near(row["charged"],master[row["id"]]["charged"]), "A/R cost mismatch")
        seen.add(row["id"])
    early_rows=[r for r in campaign if r["id"] not in seen]
    require(len(arr)==7 and len(early_rows)==68, "phase cost partition")
    early_owners={data.j(f"early/{n}-result.json")["owner"] for n in ("H0-r1","H1-r1","H1-r2","H0-r2")}
    require({r["owner"] for r in early_rows}==early_owners, "finite campaign remainder is not original H batch")
    historic=data.j("billing/historical-UNKNOWN.json")
    unknown_counts={g["source_identity"]:len(g["rows"]) for g in historic}
    require(sum(unknown_counts.values())==24 and all(r["status"]=="UNKNOWN" for g in historic for r in g["rows"]),
            "historical UNKNOWN was dropped or settled silently")
    costrows=[]
    for phase,rows in (("Original four H attempts",early_rows),("A/R continued episode",arr),
                       ("Posthoc method and E5",p2rows),("Eight-condition comparison",p3rows),("Transfer and G lineages",p4rows)):
        costrows.append(dict(batch=phase,requests=len(rows),upper_usd=f'{sum((amount(r["charged"]) for r in rows),Decimal(0)):.7f}'))
    require(near(upper,"10.0268025"), "whole finite cost differs")
    out["costs"]=dict(finite_unique_requests=len(campaign), settled_upper_usd=f"{upper:.7f}",
                       cache_aware_rate_estimate_usd=f"{aware:.9f}", batches=costrows,
                       historical_UNKNOWN_by_source=unknown_counts, historical_UNKNOWN_total=24,
                       historical_cost_in_finite_denominator=False, new_UNKNOWN=0,
                       Codex_assistance="UNPRICED_NONZERO", end_to_end_cost="UNKNOWN",
                       scope="Provider usage at frozen rates, not invoices; shared interface cells counted once")
    tables["costs-all-batches"]=costrows
    out["verification"]=dict(input_files=len(data.entries),data_bytes=sum(e["bytes"] for e in data.entries.values()),
                              provider_ledger_rows_independently_checked=25+771+367,
                              phase5_model_requests=0,phase5_scientific_executions=0,phase5_native_dispatches=0)
    return out,tables


def tex_tables(out):
    s=[]
    parts={}
    def table(name, spec, header, rows, caption):
        first=len(s)
        s.append("\\begin{table}[htbp]\n\\centering\\small\n\\begin{tabular}{@{}"+spec+"@{}}\n\\toprule\n"+header+" \\\\\n\\midrule\n")
        s.extend(" & ".join(str(x) for x in row)+" \\\\\n" for row in rows)
        s.append("\\bottomrule\n\\end{tabular}\n\\caption{"+caption+"}\\label{tab:"+name+"}\n\\end{table}\n")
        parts[name]="".join(s[first:])
    f4=out["F4"]["formal"]
    labels={"complete-raw":"Fixed $H_0$", "ordinary_reflection":"Ordinary reflection", "proposed_method":"Typed procedure"}
    table("methods","lrrrr", "Method & PASS/groups & Requests & Updates & USD upper",
          [(labels[r["condition"]],f'{r["passed"]}/{r["groups"]}',r["requests"],r["updates"] if r["condition"]!="complete-raw" else "---",r["upper_usd"]) for r in f4],
          "Fresh method comparison on four fixed digital tasks times three repetitions. All proposal and fresh-design requests are included. The base cell is shared with the interface matrix and counted once.")
    table("final","lrrrrr", "Arm & Cells & PASS & Submitted FAIL & Censored & Wrong judgment",
          [(r["arm"],r["cells"],r["passed"],r["submitted_fail"],r["incomplete"],r["judgment_disagreements"]) for r in out["F5"]["final"]],
          "Final transfer outcomes. Censored attempts stay in the denominator. Three descendant-lineage pairs are conditional on one shared $G_1$ formation.")
    table("choices","lrrrl", "Lineage & $h_1$ requests & $h_2$ requests & Chosen & $H$ hash prefix",
          [(r["lineage"],r["h1_requests"],r["h2_requests"],r["selected_child"],"\\texttt{"+r["consumed_H_sha256"][:12]+"}") for r in out["F5"]["choices"]],
          "Every sibling passes both effective selection tasks with zero judgment errors. Requests include that sibling's proposal and its two effective selection entries. All sibling costs remain in full costs.")
    table("costs","lrr", "Finite batch & Requests & USD upper",
          [(r["batch"],r["requests"],r["upper_usd"]) for r in out["costs"]["batches"]]+[("Total unique finite requests",out["costs"]["finite_unique_requests"],out["costs"]["settled_upper_usd"])],
          "Non-overlapping finite campaign costs. Provider estimates use frozen rates, not invoices. Historical UNKNOWN and unpriced development assistance remain separate.")
    table("ar","lrrrrl", "Candidate & Retry (s) & History samples & Late backlog & Missed events & FIFO",
          [(r["candidate"][-3:]+(" (selected)" if r["selected"] else ""),r["retry_s"],r["history_samples"],
            r["late_backlog"],r["missed_events"],r["strict_FIFO"]) for r in out["F6"]["candidates"]],
          "All A/R alternatives remain in the record. Sample counts cover the whole history profile. Conditional fresh-delay improvement does not satisfy the unchanged dark-service and oldest-first requirements.")
    return "\n".join(s),parts


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parent/"data")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--negative-controls", action="store_true")
    args=ap.parse_args()
    data=SavedData(args.data_root)
    data.verify()
    result,tables=audit(data)
    output=args.output.resolve()
    require(output != data.root and not output.is_relative_to(data.root), "output must be outside immutable data")
    output.mkdir(parents=True,exist_ok=True)
    if args.negative_controls:
        target="p4/actual-results.json"
        controls=[]
        for mode in ("tampered","missing"):
            def override(rel):
                if rel!=target:
                    return data.path(rel).read_bytes()
                return b"tampered" if mode=="tampered" else None
            try:
                data.verify(override)
            except (ValueError,FileNotFoundError):
                controls.append(dict(control=mode,status="REJECTED_AS_REQUIRED",input=target))
            else:
                raise ValueError("negative control unexpectedly passed")
        # Foreign-candidate content cannot satisfy candidate-002's saved identity.
        foreign=data.j("ar/continuation-001/scientific/candidate-001/candidate.json")
        selected=data.j("ar/continuation-001/external/result.json")["candidates"]["candidate-002"]["candidate_sha256"]
        require(canonical(foreign)!=selected,"foreign candidate accepted")
        controls.append(dict(control="foreign_candidate",status="REJECTED_AS_REQUIRED"))
        result["negative_controls"]=controls
    write_json(output/"analysis.json",result)
    (output/"tables").mkdir(exist_ok=True)
    for name,rows in tables.items():
        rows_csv(output/"tables"/(name+".csv"),rows)
    all_tex,parts=tex_tables(result)
    (output/"tables.tex").write_text(all_tex)
    for name,body in parts.items():
        (output/(name+".tex")).write_text(body)
    print(json.dumps(dict(status="PASS",saved_input_files=len(data.entries),
                          finite_requests=result["costs"]["finite_unique_requests"],
                          settled_upper_usd=result["costs"]["settled_upper_usd"],
                          F4="KEEP_UNCHANGED_BASE_H",F5="H0 7/9; G0 6/9; G1 8/9 (descriptive)",
                          F6="NO_GO; dark FAIL; FIFO FAIL; NOT_ACCEPTED; physical UNKNOWN",
                          new_provider_requests=0,new_scientific_executions=0)))


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(status="FAIL",error_type=type(exc).__name__,reason=str(exc))),file=sys.stderr)
        sys.exit(1)
