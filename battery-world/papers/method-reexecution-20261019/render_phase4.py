#!/usr/bin/env python3
"""Finite phase-4 source readback and local TeX build; no experiment dispatch.

check recomputes the bound counts/costs/selection and verifies table text.
build additionally compiles twice and renders temporary page images.
clean removes only named paper scratch after recorded every-page visual QA.
The earlier reader failure remains in paper-preparation/readback-attempt-001.json.
No SDK, science, test or CI module is imported or invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PAPER = Path(__file__).resolve().parent
ROOT = PAPER.parents[1]
FINAL = ROOT / "docs/research/phase4-20261020/methods/paper-final"
BINDING = PAPER / "phase4-binding.json"
TASKS = ["p4-bf-stretched-port-window-v1", "p4-clite-half-power-query-v1", "p4-o-unexposed-waveform-v1"]
ZERO = Decimal(0)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def meta(path):
    raw = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def read(path):
    return json.loads(Path(path).read_text(), parse_float=Decimal)


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def close(actual, expected, name):
    require(abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal("0.000000001"), name)


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, default=lambda d: format(d, "f")) + "\n")


def money(value):
    return f"{Decimal(str(value)):.7f}"


def total(rows):
    return {"requests": sum(r["usage"]["requests"] for r in rows), "usd": sum((r["usage"]["usd"] for r in rows), ZERO), "wall_s": sum((r["usage"]["wall_s"] for r in rows), ZERO)}


def table(spec, header, rows, caption, label, size="small"):
    return ("\\begin{table}[htbp]\n\\centering\n\\" + size + "\n\\begin{tabular}{" + spec + "}\n\\toprule\n" + header + " \\\\\n\\midrule\n" + "\n".join(row + " \\\\" for row in rows) + "\n\\bottomrule\n\\end{tabular}\n\\caption{" + caption + "}\n\\label{" + label + "}\n\\end{table}")


def tables(data):
    summary, actual, details = data["analysis"], data["actual"], data["details"]
    out = {}
    out["formation"] = table("lrrr", "Component & Episodes & Requests & Upper USD", [
        "Shared $G_1$ formation & 1 & 3 & 0.0269157",
        "$G_0$ descendants & 6 & 20 & 0.1832424",
        "$G_1$ descendants & 6 & 23 & 0.2658975",
        "Formation and proposals & 13 & 46 & 0.4760556"],
        "Actual formation and proposal costs only; selection, final execution, controls and host incidents are additional.", "tab:formation")
    selection_rows = []
    for arm in sorted(data["selected"]):
        metrics = data["selections"][arm]["candidate_metrics"]
        chosen = data["selected"][arm]
        selection_rows.append(arm.replace("G0", "$G_0$").replace("G1", "$G_1$") + f" & {metrics[0]['total_charged_requests']} & {metrics[1]['total_charged_requests']} & {chosen['selected_descendant_index']} & \\texttt{{{chosen['selected_H_sha256'][:12]}}}")
    out["selection"] = table("lrrrl", "Arm & $q(h_1)$ & $q(h_2)$ & Selected & Consumed $H$ hash", selection_rows,
        "All twelve siblings pass both selection tasks, with zero wrong service judgments; all six $H_0$ controls also pass (30/30 effective cells). Requests include each child's proposal and two effective selections. Tied request counts use stable child index, not USD. Consumed $H$ is unchanged $H_0$ followed by the original proposed text; hashes refer to this composite.", "tab:selection")
    arms = summary["final_arms"]
    out["outcomes"] = table("lrrrrr", "Arm & Cells & PASS & Submitted FAIL & Censored & Disagreements", [
        f"${a[0]}_{a[1]}$ & {arms[a]['cells']} & {arms[a]['PASS']} & {arms[a]['submitted_FAIL']} & {arms[a]['incomplete']} & {arms[a]['nominal_service_judgment_disagreements']}" for a in ["H0", "G0", "G1"]],
        "All 27 registered final cells, including four token-censored non-submissions. Disagreements compare a submitted participant judgment with the host service result; censored cells have no submitted judgment.", "tab:outcomes", "footnotesize")
    cost_rows = []
    for arm in ["G0", "G1"]:
        a = arms[arm];f=a["full_pipeline_cost_including_incident_and_formation"];e=a["effective_pipeline_cost_excluding_only_four_host_incidents"]
        cost_rows.append(f"${arm[0]}_{arm[1]}$ & {f['requests']} & {money(f['settled_upper_usd'])} & {e['requests']} & {money(e['settled_upper_usd'])}")
    h=arms["H0"]["selection_plus_final_cost"]
    cost_rows.append(f"$H_0$ controls & {h['requests']} & {money(h['settled_upper_usd'])} & {h['requests']} & {money(h['settled_upper_usd'])}")
    out["costs"] = table("lrrrr", "Scope & Full $q$ & Full upper USD & Effective $q$ & Effective upper USD", cost_rows,
        "Full arm pipelines include both siblings, proposal/selection/final calls, retained failures, and allocated $G_1$ formation. Effective pipelines remove only the four original host incidents, retaining all four charged recoveries. $H_0$ has selection/final controls but no proposal or formation stage.", "tab:costs", "footnotesize")
    stage_rows = []
    labels={"O-transfer":"Original-service development", "formation":"$G_1$ formation", "proposal":"Twelve $H$ proposals", "selection":"Selection, including incidents", "final":"Final evaluation"}
    for stage in ["O-transfer", "formation", "proposal", "selection", "final"]:
        c=summary["stages_all_actual"][stage]
        stage_rows.append(f"{labels[stage]} & {c['episodes']} & {c['requests']} & {money(c['settled_upper_usd'])} & {float(c['summed_wall_s']):.3f}")
    stage_rows.append("Total & 77 & 367 & 3.1767228 & 5951.639")
    out["stages"] = table("lrrrr", "Stage & Attempts & Requests & Upper USD & Summed wall s", stage_rows,
        "Conserved campaign accounting. The 34 selection attempts comprise 30 effective cells and four original incidents. Summed episode wall time is not elapsed campaign time. Rates and ledger upper estimates are not invoices.", "tab:stages", "footnotesize")
    o_rows=[]
    for r in data["O0"]["rows"]:
        o_rows.append(f"{r['episode'].removeprefix('O0-')} & {r['complete_O_event_service']} & {r['participant_judgment']} & {r['requests']} & {money(r['upper_usd'])}")
    out["O0"] = table("lllrr", "Condition & Host service & Participant & Requests & Upper USD", o_rows,
        "The separate O0 development transfer. UNKNOWN disagrees with the candidate's host PASS under the nominal judgment metric. O0 contributes no history to $G/H$ formation or selection.", "tab:O0")
    cell_rows=[]
    for task in TASKS:
        for lineage in [1,2,3]:
            for arm in ["H0","G0","G1"]:
                r=next(r for r in details["rows"] if r["task"]==task and r["lineage"]==lineage and r["arm"]==arm)
                d=r["design"];state="C" if d is None else ("P" if r["service"]=="PASS" else "F")
                if d is None: design="---"
                elif task==TASKS[2]: design=f"{float(d['sample_period_s']):g} / {float(d['retry_s']):g}"
                else: design=f"{float(d['capacitance_f'])*1e6:g} / {float(d['tx_not_before_s']):g}"
                cell_rows.append(f"{TASKS.index(task)+1} & {lineage} & ${arm[0]}_{arm[1]}$ & {state} & {design} & {r['usage']['requests']} & {money(r['usage']['usd'])}")
    out["final_cells"] = table("rrlclrr", "Task & L & Arm & Result & Design parameters & $q$ & Upper USD", cell_rows,
        "Every final cell. P: submitted PASS; F: submitted FAIL; C: token-censored, no submission. Tasks 1/2 report capacitance ($\\mu$F) / transmit gate (s); task 3 reports sample period (s) / retry (s). All submitted task-3 designs use 15 mF, nonvolatile cache and confirmed-events; other fields and complete JSON artifacts remain bound in final-details. Disagreements are task 3, L1-$H_0$ and L3-$G_0$, both judged PASS by the participant but FAIL by the host.", "tab:final-cells", "footnotesize")
    lineage_rows=[]
    for arm,c in sorted(actual["arms"].items()):
        lineage_rows.append(f"{arm} & {c['final_passes']}/3 & {c['full_requests']} & {money(c['full_usd'])} & {c['effective_requests']} & {money(c['effective_usd'])}")
    out["lineage_costs"] = table("lrrrrr", "Lineage arm & PASS & Full $q$ & Full USD & Effective $q$ & Effective USD", lineage_rows,
        "Per-lineage full and effective costs. Formation is one event with three allocated shares, not three independent formations. Full/effective definitions are identical to Table~\\ref{tab:costs}.", "tab:lineage-costs", "footnotesize")
    return out


def load_and_check(verify_paper=True):
    b=read(BINDING)
    require(b["authorization"]["handoff_sha256"]=="690e0aaf76d92c6f8756c9976872bb94406397e30f2e622d9f70a85924477a56", "Wrong final handoff")
    for path,want in b["closed_sources"].items():
        require(meta(path)=={k:want[k] for k in ["sha256","bytes"]}, "Closed source mismatch: "+path)
    for rel,want in b["protected_local_files"].items():
        require(meta(ROOT/rel)==want, "Frozen local file changed: "+rel)
    if verify_paper:
        for rel,want in b["paper_inputs"].items():
            require(meta(ROOT/rel)==want, "New paper input mismatch: "+rel)
    data={key:read(path) for key,path in b["primary_inputs"].items()}
    data["selections"]={Path(path).stem:read(path) for path in data["selection"]["selection_files"]}
    actual,details,summary=data["actual"],data["details"],data["analysis"]
    rows=actual["rows"]
    require(len(rows)==77 and len(actual["canonical_rows"])==73 and not actual["not_dispatched_cells"], "Attempt/cell counts")
    require(summary["actual_results_sha256"]==meta(b["primary_inputs"]["actual"])["sha256"] and details["actual_results_sha256"]==summary["actual_results_sha256"], "Result cross-binding")
    require(summary["final_details_sha256"]==meta(b["primary_inputs"]["details"])["sha256"], "Detail cross-binding")
    ids=set()
    for row in rows:
        path=Path(row["result_path"]);r=read(path);c=read(path.parent/"provider-costs.json")
        require(meta(path)["sha256"]==row["result_sha256"], "Result row binding: "+row["episode"])
        require(r["reported_models"]==["deepseek-flash"] and r["native_dispatches"]==0 and r["fresh_task_entry"], "Actual identity/freshness/native")
        require(not r["trace_audit"]["unmatched_executed_inputs"], "Trace unmatched input")
        require(len(c["rows"])==c["requests"]==row["usage"]["requests"] and not c["unknown_or_missing_usage"] and c["unsettled_reserved_usd"]==0, "Usage boundary")
        close(sum((x["charged"] for x in c["rows"]),ZERO),row["usage"]["usd"], "Provider row sum")
        close(r["wall_seconds_total"],row["usage"]["wall_s"], "Episode wall")
        for charge in c["rows"]:
            require(charge["status"]=="SETTLED" and charge["usage"] and not charge["error"] and charge["id"] not in ids, "Request status/duplication")
            ids.add(charge["id"])
    totals=total(rows);require(totals["requests"]==len(ids)==367, "367 unique charged requests")
    close(totals["usd"],"3.1767228","All USD");close(totals["wall_s"],"5951.6394840371795","All wall")
    require(actual["native_dispatches"]==0 and actual["new_unknown_usage"]==[] and actual["new_scientific_executions"]==25, "Execution/UNKNOWN boundary")
    require(data["preservation"]["all_six_selections_frozen_before_final"] and data["preservation"]["actual_H_and_final_payload_derivation"]=="PASS", "S0 source/selection audit")
    require(data["freeze"]["all_final_episodes_not_started"] and not data["freeze"]["final_results_consulted"] and data["freeze"]["status"]=="ALL_SIX_ARMS_FROZEN", "Freeze boundary")
    require(canonical_digest(data["selected"])==data["freeze"]["selected_methods_sha256"], "Frozen selected methods canonical digest")
    require(len(data["selection"]["rows"])==30 and all(r["service"]=="PASS" and not r["wrong_service_judgment"] for r in data["selection"]["rows"]), "30/30 effective selections")
    canonical={r["canonical_episode"]:r for r in actual["canonical_rows"]}
    base=read(ROOT/"configs/studies/phase4-20261020/methods/frozen-parents.json")["H0"]["method_text"]
    for arm,s in data["selected"].items():
        metrics=data["selections"][arm]["candidate_metrics"]
        for m in metrics:
            child=m["descendant_index"];subset=[r for r in actual["canonical_rows"] if r["arm"]==arm[-2:] and r["lineage"]==int(arm[1]) and r["child"]==child and r["stage"] in ["proposal","selection"]]
            require(total(subset)["requests"]==m["total_charged_requests"] and m["complete_service_passes"]==2 and m["wrong_service_judgments"]==0 and m["eligible"], "Selection ranking components")
        chosen=min(metrics,key=lambda m:(-m["complete_service_passes"],m["wrong_service_judgments"],m["total_charged_requests"],m["descendant_index"]))["descendant_index"]
        require(chosen==s["selected_descendant_index"] and s["status"]=="SELECTED_DESCENDANT", "Frozen selection does not follow ranking")
        p=read(Path(canonical[f"{arm}-h{chosen}-proposal"]["result_path"]).parent/"scientific/submission.json")["proposal"]
        require(s["selected_H_text"]==base+"\n\n"+p["method_text"] and canonical_digest(s["selected_H_text"])==s["selected_H_sha256"], "Unchanged base plus original proposed H")
    require(len(details["rows"])==27, "Final cell count")
    outcomes={}
    for arm,expect in [("H0",(7,1,1)),("G0",(6,1,2)),("G1",(8,0,1))]:
        rs=[r for r in details["rows"] if r["arm"]==arm]
        counts=(sum(r["service"]=="PASS" for r in rs),sum(r["service"]=="FAIL" for r in rs),sum(r["design"] is None for r in rs))
        require(len(rs)==9 and counts==expect, "Final counts: "+arm);outcomes[arm]=counts
    require(all(r["service"]=="PASS" for r in details["rows"] if r["task"]!=TASKS[2]), "18/18 digital tasks")
    for item in summary["incomplete_final_cells"]:
        a=item["last_assistant_metadata"]
        require(item["response_token_censored"] and a["stop_reason"]=="length" and a["usage"]["output"]==a["usage"]["reasoning"]==32768, "Token censor metadata")
        require(not read(next(r["result_path"] for r in rows if r["episode"]==item["episode"]))["trace_audit"]["model_submitted"], "Censored submission")
    for arm,requests,usd,e_requests,e_usd in [("G0",135,"1.2585825",123,"1.1843580"),("G1",138,"1.2447618",129,"1.1871390")]:
        rs=[r for r in rows if r["arm"]==arm];c=total(rs);share=summary["G1_formation_cost"] if arm=="G1" else {"requests":0,"settled_upper_usd":0}
        require(c["requests"]+share["requests"]==requests, "Full arm requests")
        close(c["usd"]+Decimal(str(share["settled_upper_usd"])),usd,"Full arm USD")
        eff=total([r for r in rs if not r["host_incident_overhead"]])
        require(eff["requests"]+share["requests"]==e_requests,"Effective arm requests")
        close(eff["usd"]+Decimal(str(share["settled_upper_usd"])),e_usd,"Effective arm USD")
    h0=total([r for r in rows if r["condition"]=="H0"])
    require(h0["requests"]==76,"H0 requests")
    close(h0["usd"],"0.5154765","H0 selection/final USD")
    require(not actual["default_H0_changed"] and actual["G1_formation_events"]==1, "Default H0/one G1")
    require(sum(1 for r in rows if r["host_incident_overhead"])==4,"Retained four incidents")
    if verify_paper:
        text=(PAPER/"phase4-methods.tex").read_text()
        for name,value in tables(data).items():
            m=re.search(r"% BEGIN AUTO "+name+r"\n(.*?)\n% END AUTO "+name,text,re.S)
            require(m and m.group(1)==value,"Bound table mismatch: "+name)
    receipt={"status":"PASS_FINITE_SOURCE_AND_ACCOUNTING_READBACK", "at_utc":datetime.now(timezone.utc).isoformat(),"source_files":len(b["closed_sources"]),"protected_local_files":len(b["protected_local_files"]),"actual_episodes":77,"canonical_cells":73,"selection_cells_PASS":30,"final_cells":27,"final_outcomes_PASS_FAIL_censored":outcomes,"provider_unique_requests":len(ids),"settled_upper_usd":totals["usd"],"summed_episode_wall_s":totals["wall_s"],"scope":"Independent finite readback of source hashes, 77 result/cost files, selected H composition, ranking, accounting and table text. S0 sealed receipt supplies freeze-before-exposure and original-token metadata audit; no scientific or SDK rerun.","new_provider_SDK_science_native_test_init_CI_calls":0,"registered_final_CI":"PENDING_S0_SINGLE_RUN_AFTER_IMPORT"}
    return b,data,receipt


def command(args,env=None):
    result=subprocess.run(["rtk","proxy",*map(str,args)],cwd=PAPER,env=env,capture_output=True,text=True,timeout=60)
    if result.returncode:
        raise RuntimeError(result.stdout+result.stderr)
    return result.stdout+result.stderr


def build():
    b,data,receipt=load_and_check()
    save(FINAL/"source-readback.json",receipt)
    number=1
    while (FINAL/f"build-attempt-{number:03d}.json").exists():number+=1
    scratch=FINAL/"build-temp";raster=FINAL/"raster-temp"
    scratch.mkdir(exist_ok=True);raster.mkdir(exist_ok=True)
    env=dict(os.environ,SOURCE_DATE_EPOCH=str(b["build_environment"]["SOURCE_DATE_EPOCH"]),FORCE_SOURCE_DATE="1",TZ="UTC")
    args=["/Library/TeX/texbin/pdflatex","-interaction=nonstopmode","-halt-on-error","-file-line-error","-no-shell-escape","-recorder","-jobname=phase4","-output-directory="+str(scratch),"phase4-manuscript.tex"]
    attempt={"attempt":number,"at_utc":datetime.now(timezone.utc).isoformat(),"command":["rtk","proxy",*args],"environment":b["build_environment"],"status":"STARTED"}
    try:
        for i in (1,2):(FINAL/f"build-{number:03d}-pass{i}.stdout.log").write_text(command(args,env))
        log=(scratch/"phase4.log").read_text()
        require("Overfull" not in log and "undefined references" not in log and "Citation" not in log and "multiply defined" not in log,"TeX overflow/reference warning; inspect log")
        shutil.copyfile(scratch/"phase4.pdf",PAPER/"phase4.pdf")
        shutil.copyfile(scratch/"phase4.log",FINAL/"phase4-compile.log")
        shutil.copyfile(scratch/"phase4.fls",FINAL/"phase4-inputs.fls")
        info=command(["/opt/homebrew/bin/pdfinfo",PAPER/"phase4.pdf"]);(FINAL/"pdfinfo.txt").write_text(info)
        pages=int(re.search(r"^Pages:\s+(\d+)",info,re.M).group(1));require(1<=pages<=14,"Unexpected paper length")
        fonts=command(["/opt/homebrew/bin/pdffonts",PAPER/"phase4.pdf"]);(FINAL/"pdffonts.txt").write_text(fonts)
        font_rows=[line.split() for line in fonts.splitlines()[2:] if line.strip()]
        require(font_rows and all(line[-5]=="yes" for line in font_rows),"Unembedded font")
        require(not any("Type 3" in line for line in fonts.splitlines()),"Type3 font")
        command(["/opt/homebrew/bin/pdftotext","-layout",PAPER/"phase4.pdf",FINAL/"phase4-text.txt"])
        text=(FINAL/"phase4-text.txt").read_text();require("??" not in text,"Unresolved PDF reference")
        for token in ["367","3.1767228","1.2447618","1.2585825","1.1871390","1.1843580","0.5154765","32,768","0.75"]:require(token in text,"Missing PDF token: "+token)
        # A shorter rebuilt PDF must not inherit a previous render's last page.
        for old in raster.glob("page-*.png"):
            require(old.parent==raster and not old.is_symlink(),"Raster scratch path")
            old.unlink()
        command(["/opt/homebrew/bin/pdftoppm","-r","125","-png",PAPER/"phase4.pdf",raster/"page"])
        images=sorted(raster.glob("page-*.png"));require(len(images)==pages,"Rendered page count")
        from PIL import Image,ImageDraw
        thumbs=[]
        for n,p in enumerate(images,1):
            with Image.open(p) as im:
                im.thumbnail((550,750));thumb=Image.new("RGB",(580,790),"#e8e8e8");thumb.paste(im,((580-im.width)//2,28));ImageDraw.Draw(thumb).text((15,8),f"Page {n}",fill="black");thumbs.append(thumb)
        cols=3;contact=Image.new("RGB",(cols*580,((pages+cols-1)//cols)*790),"white")
        for i,im in enumerate(thumbs):contact.paste(im,((i%cols)*580,(i//cols)*790))
        contact.save(FINAL/"phase4-contact.jpg",quality=85)
        b["outputs"]={"phase4.pdf":meta(PAPER/"phase4.pdf"),"pages":pages,"compile_status":"PASS_TWO_PASSES_NO_OVERFULL_OR_UNDEFINED_REFERENCES","font_status":"ALL_EMBEDDED_NO_TYPE3","visual_status":"PENDING_ACTUAL_EVERY_PAGE_REVIEW"}
        b["status"]="COMPILED_PENDING_EVERY_PAGE_VISUAL_REVIEW";save(BINDING,b)
        attempt.update(status="COMPILED_PENDING_EVERY_PAGE_VISUAL_REVIEW",pages=pages,pdf=meta(PAPER/"phase4.pdf"),raster_files={str(p.relative_to(ROOT)):meta(p) for p in images})
    except Exception as exc:
        attempt.update(status="FAILED_RETAINED",error=str(exc));save(FINAL/f"build-attempt-{number:03d}.json",attempt);raise
    save(FINAL/f"build-attempt-{number:03d}.json",attempt)
    print(json.dumps({"status":attempt["status"],"pages":pages,"pdf":str(PAPER/"phase4.pdf"),"rasters":str(raster)}))


def clean():
    qa=read(FINAL/"visual-qa.json");b=read(BINDING)
    require(qa["status"]=="PASS_ACTUAL_EVERY_PAGE_REVIEW" and qa["pdf"]==meta(PAPER/"phase4.pdf"),"Visual review missing/stale")
    require(b["outputs"]["visual_status"]=="PASS_ACTUAL_EVERY_PAGE_REVIEW","Binding visual status")
    removed={}
    for name in ["build-temp","raster-temp"]:
        p=FINAL/name
        if p.exists():
            require(p.parent==FINAL and not p.is_symlink(),"Scratch path")
            files=[f for f in p.rglob("*") if f.is_file()];removed[name]={"files":len(files),"bytes":sum(f.stat().st_size for f in files)};shutil.rmtree(p)
    save(FINAL/"cleanup.json",{"status":"REMOVED_ONLY_NAMED_PAPER_SCRATCH","removed":removed,"retained":"Final PDF, small contact preview, compile/source/font/text/visual receipts; no high-resolution page images or TeX scratch."})
    print(json.dumps({"status":"CLEANED_AFTER_VISUAL_QA","removed":removed}))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("action",choices=["check","build","clean"],nargs="?",default="check");args=parser.parse_args()
    if args.action=="build":build()
    elif args.action=="clean":clean()
    else:
        _,_,receipt=load_and_check();save(FINAL/"source-readback.json",receipt);print(json.dumps({k:receipt[k] for k in ["status","source_files","actual_episodes","provider_unique_requests"]}))


if __name__=="__main__":main()
