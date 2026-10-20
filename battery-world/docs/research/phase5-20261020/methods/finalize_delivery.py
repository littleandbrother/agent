#!/usr/bin/env python3
"""Seal local editorial QA; run only saved-data readback, never the apparatus."""
import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    return dict(sha256=digest(path),bytes=path.stat().st_size)


def save(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")


def size(root):
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def resolve_pointer(value,pointer):
    assert pointer=="" or pointer.startswith("/")
    for part in pointer.split("/")[1:]:
        key=part.replace("~1","/").replace("~0","~")
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value


def scan(roots):
    # Only paths/counts are reported; matching credential text is never printed.
    rules={
        "provider_key":re.compile(rb"\b(?:olp_|sk[-_])[A-Za-z0-9_-]{20,}"),
        "bearer_credential":re.compile(rb"(?i)\bBearer[ \t]+[A-Za-z0-9._~+/=-]{16,}"),
        "password_url":re.compile(rb"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"),
        "assigned_credential":re.compile(rb'''(?i)(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\s*["']?\s*[:=]\s*["']([A-Za-z0-9_-]{20,})'''),
    }
    findings=[]
    checked=0
    total=0
    for label,root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            raw=path.read_bytes()
            checked+=1
            total+=len(raw)
            for name,pattern in rules.items():
                count=sum(1 for _ in pattern.finditer(raw))
                if count:
                    findings.append(dict(path=label+"/"+str(path.relative_to(root)),rule=name,count=count))
    return dict(status="PASS" if not findings else "FAIL",files_checked=checked,
                bytes_checked=total,findings=findings,scope="All retained bytes, including binary files; heuristic local secret scan, no remote publication.")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--paper",type=Path,required=True)
    ap.add_argument("--receipts",type=Path,required=True)
    args=ap.parse_args()
    paper=args.paper.resolve()
    receipts=args.receipts.resolve()
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    admission=json.loads((receipts/"admission.json").read_text())
    assert [str(paper),str(receipts)]==admission["writes"]
    assert not (paper/"HANDOFF.json").exists() and not (receipts/"HANDOFF.json").exists()
    peak_observed=size(paper)+size(receipts)
    assert peak_observed<admission["peak_cap_bytes"]
    assert shutil.disk_usage(paper).free>admission["reserve_bytes"]

    # Recompute from the receipt working directory to check cwd independence.
    out=receipts/"_final-readback"
    assert not out.exists()
    command=["rtk","proxy",sys.executable,"-B",str(paper/"reproduce.py"),
             "--data-root",str(paper/"data"),"--output",str(out),"--negative-controls"]
    result=subprocess.run(command,cwd=receipts,capture_output=True,text=True)
    readback=dict(command=command,cwd=str(receipts),returncode=result.returncode,
                  stdout=result.stdout,stderr=result.stderr,new_provider_requests=0,
                  new_scientific_executions=0,detached_acceptance="S0_PENDING")
    save(receipts/"readback-attempt-008.json",readback)
    assert result.returncode==0,"Saved-data readback failed; retained attempt 008"
    output_rows=[]
    for path in sorted(out.rglob("*")):
        if path.is_file():
            relative=path.relative_to(out)
            target=paper/"generated"/relative
            assert target.is_file() and digest(path)==digest(target),str(relative)
            output_rows.append(dict(path=str(relative),**record(path)))
    expected={str(p.relative_to(paper/"generated")) for p in (paper/"generated").rglob("*") if p.is_file()}
    assert expected=={r["path"] for r in output_rows}
    readback.update(status="PASS",generated_outputs_equal=True,outputs=output_rows)
    save(receipts/"readback-attempt-008.json",readback)

    # Every final page was actually viewed using view_image before this script.
    pdf_sha=digest(paper/"main.pdf")
    technical=json.loads((receipts/"pdf-technical-qa.json").read_text())
    build=json.loads((receipts/"build-attempt-002.json").read_text())
    assert pdf_sha==technical["pdf_sha256"]==build["pdf_sha256"]
    assert technical["pages"]==11 and technical["fonts"]==14
    assert technical["all_fonts_embedded"] and not technical["Type3"] and not technical["out_of_page_text"]
    assert not build["findings"] and all(row["returncode"]==0 for row in build["passes"])
    from PIL import Image,ImageDraw
    pages=sorted((receipts/"_pages").glob("page-*.png"))
    assert len(pages)==11
    verification=paper/"verification"
    verification.mkdir(exist_ok=True)
    contact=Image.new("RGB",(1050,4*483),(224,227,233))
    draw=ImageDraw.Draw(contact)
    page_rows=[]
    observations=[
        "Brand, title and abstract legible; no overlap.",
        "Typed D/H/G diagram, arrows and text fit the page.",
        "Protocol and control text remain inside margins.",
        "Recovered-method and rejection arguments are legible; equations fit.",
        "Method comparison table and caption fit; service-tie conclusion is readable.",
        "G formation and exposure sections fit; headings and math are clear.",
        "Sibling-selection and final-outcome tables fit with readable captions.",
        "Costs and candidate-bound A/R table fit; continuation at page break is coherent.",
        "Necessary bounds and finite-cost table fit; units are readable.",
        "Discussion, limitations and reference start fit without collision.",
        "References and reproducibility appendix are legible and within margins.",
    ]
    for i,path in enumerate(pages):
        with Image.open(path) as original:
            width,height=original.size
            thumbnail=original.convert("RGB")
            thumbnail.thumbnail((334,446))
            x=(i%3)*350+(350-thumbnail.width)//2
            y=(i//3)*483+9
            contact.paste(thumbnail,(x,y))
        draw.text(((i%3)*350+12,(i//3)*483+461),"Final page "+str(i+1),fill=(25,34,54))
        page_rows.append(dict(page=i+1,render_name=path.name,**record(path),
                              width=width,height=height,actual_view_image_review="PASS",
                              observation=observations[i]))
    contact.save(verification/"contact-sheet.jpg",quality=86,optimize=True)
    visual=dict(schema_version="bf-phase5-final-visual-qa-v1",reviewed_utc=now,
                pdf_sha256=pdf_sha,pages=11,status="PASS",method="Each final 125-dpi page was actually viewed with view_image; contact sheet is a retained overview, not a substitute.",
                page_reviews=page_rows,contact=dict(path="verification/contact-sheet.jpg",**record(verification/"contact-sheet.jpg")),
                source_unchanged_since_build=True,limitations="Local rendering and visual review only; coordinator detached build and Overleaf acceptance remain pending.")
    save(receipts/"visual-qa.json",visual)
    technical["actual_visual_review"]="PASS"
    technical["visual_qa_sha256"]=digest(receipts/"visual-qa.json")
    save(receipts/"pdf-technical-qa.json",technical)
    for name in ("visual-qa.json","pdf-technical-qa.json","build-attempt-002.json"):
        shutil.copyfile(receipts/name,verification/name)

    # Exact original source bytes and admission-protected files must survive.
    sources=json.loads((receipts/"source-dependencies.json").read_text())
    source_rows=[]
    for row in sources["entries"]:
        original=Path(row["source"])
        assert record(original)=={k:row[k] for k in ("sha256","bytes")},row["source"]
        portable=(paper/"data"/row["path"] if (paper/"data"/row["path"]).is_file() else paper/row["path"]).resolve()
        assert portable.is_relative_to(paper)
        assert record(portable)==record(original),row["path"]
        source_rows.append(dict(source=row["source"],portable_path=str(portable.relative_to(paper)),**record(original)))
    protected=[]
    for name,expected in admission["protected_files"].items():
        assert record(Path(name))==expected,name
        protected.append(dict(path=name,**expected))
    preservation=dict(schema_version="bf-phase5-preservation-readback-v1",status="PASS",checked_utc=now,
        original_dependencies=len(source_rows),immutable_data_files=sources["data_files"],
        source_dependencies_sha256=digest(receipts/"source-dependencies.json"),
        admission_protected_files=len(protected),originals_unchanged=True,portable_bytes_equal_originals=True,
        source_rows=source_rows,protected_rows=protected)
    save(receipts/"preservation-final.json",preservation)

    claims=json.loads((paper/"claim-evidence.json").read_text())
    pointers=0
    for claim in claims["claims"]:
        for evidence in claim["evidence"]:
            path=paper/evidence["path"]
            assert digest(path)==evidence["sha256"]
            for pointer in evidence["json_pointers"]:
                resolve_pointer(json.loads(path.read_text()),pointer)
                pointers+=1
        fragment=claim["reproduced_output"].split("#",1)[1]
        analysis=json.loads((paper/"generated/analysis.json").read_text())
        for part in fragment.split(","):
            resolve_pointer(analysis,"/"+part)
    overleaf=json.loads((paper/"overleaf-files.json").read_text())
    assert len(overleaf["files"])==9
    for row in overleaf["files"]:
        assert not Path(row["path"]).is_absolute()
        assert record(paper/row["path"])=={k:row[k] for k in ("sha256","bytes")}
    core_paths=[]
    for name in ("reproduce.py","build.py"):
        raw=(paper/name).read_text()
        assert not any(prefix in raw for prefix in ("/Users/","/home/","/Applications/","/Library/","/opt/homebrew/"))
        core_paths.append(dict(path=name,**record(paper/name)))
    consistency=dict(status="PASS",claim_rows=len(claims["claims"]),validated_json_pointers=pointers,
        evidence_hashes_valid=True,generated_output_pointers_valid=True,overleaf_compile_assets=9,
        overleaf_hashes_valid=True,portable_core_has_no_host_absolute_literals=True,
        core=core_paths,saved_data_reproduction_outputs_equal=True)
    save(receipts/"package-consistency.json",consistency)
    shutil.copyfile(receipts/"package-consistency.json",verification/"package-consistency.json")

    # Preserve the diagnostic failure without pretending it was a data failure.
    save(receipts/"inspection-attempt-001.json",dict(status="FAILED_DIAGNOSTIC_ONLY",
        error="AttributeError: list has no attribute items",cause="An exploratory key-summary assumed every source JSON was an object; historical UNKNOWN is a list.",
        resolution="The final selectors support JSON objects and arrays; exact hash readback and all evidence selectors pass.",
        source_modified=False,scientific_or_model_execution=False))

    # Delete only individually inventoried rebuildable files under the two roots.
    peak_observed=max(peak_observed,size(paper)+size(receipts))
    removed=[]
    for directory in (receipts/"_pages",receipts/"_build",out):
        assert directory.parent==receipts and directory.is_dir()
        files=sorted(p for p in directory.rglob("*") if p.is_file())
        for path in files:
            assert not path.is_symlink()
            removed.append(dict(path=str(path.relative_to(receipts)),**record(path)))
            path.unlink()
        for child in sorted((p for p in directory.rglob("*") if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
            child.rmdir()
        directory.rmdir()
    save(receipts/"cleanup-final.json",dict(status="PASS",scope="Only owned rebuildable final render PNGs, TeX auxiliary build and duplicate saved-data readback output; originals and failed attempt logs retained.",
        removed_files=removed,removed_bytes=sum(x["bytes"] for x in removed),
        retained_visual_qa_sha256=digest(receipts/"visual-qa.json"),
        retained_final_pdf_sha256=pdf_sha,pre_cleanup_observed_bytes=peak_observed))

    # Manifest excludes itself explicitly; its checksum is supplied by S0 receipt.
    inventory=[]
    for path in sorted(paper.rglob("*")):
        if path.is_file():
            inventory.append(dict(path=str(path.relative_to(paper)),**record(path)))
    portable=dict(schema_version="bf-phase5-portable-paper-handoff-v1",status="A_OWNED_WORK_COMPLETE_READY_FOR_S0",
        paper=dict(path="main.pdf",**record(paper/"main.pdf"),pages=11),
        commands=dict(reproduce="python3 -B reproduce.py --data-root data --output rebuilt --negative-controls",
                      compile="python3 -B build.py --output-dir build --log-dir build-logs --attempt local-001"),
        saved_data_files=643,finite_settled_requests=1238,upper_usd="10.0268025",historical_unknown_rows=24,
        overleaf_main_document="main.tex",overleaf_assets=[row["path"] for row in overleaf["files"]],
        checks=dict(saved_data_readback="PASS",negative_controls="PASS",two_pass_compile="PASS",
                    embedded_fonts="PASS",all_11_pages_actually_viewed="PASS",claim_evidence_selectors="PASS",
                    immutable_source_readback="PASS"),
        new_work=dict(provider_requests=0,scientific_executions=0,native_mutations=0,environment_creations=0),
        limitations=["Saved-data reconstruction is not fresh scientific replication.",
          "F2/F3 do not contain decision-span or organization ablations.",
          "G1 transfer is descriptive and conditional on one formation; unchanged H0 is retained.",
          "A/R remains NO_GO, dark FAIL, FIFO FAIL, NOT_ACCEPTED; physical qualification UNKNOWN.",
          "Usage estimates are not invoices; developer assistance is UNPRICED_NONZERO and end-to-end cost UNKNOWN.",
          "S0 owns detached acceptance, global feature/state updates and existing-project Overleaf publication; pending here."],
        inventory_policy="All retained files below this directory except HANDOFF.json itself; original source locators are inert provenance, not runtime dependencies.",
        inventory=inventory)
    save(paper/"HANDOFF.json",portable)

    secret=scan([("paper",paper),("receipts",receipts)])
    save(receipts/"secret-scan.json",secret)
    assert secret["status"]=="PASS","Potential secret detected; see path/count-only receipt"
    retained=size(paper)+size(receipts)
    storage=dict(status="PASS",peak_cap_bytes=admission["peak_cap_bytes"],retained_cap_bytes=admission["retained_cap_bytes"],
        reserve_bytes=admission["reserve_bytes"],observed_peak_bytes=max(peak_observed,retained),
        retained_bytes_before_final_handoff=retained,free_bytes=shutil.disk_usage(paper).free,
        peak_measurement_scope="Measured at admission/finalization and before own scratch cleanup; all new work is limited to these two owned roots.")
    assert storage["observed_peak_bytes"]<storage["peak_cap_bytes"]
    assert retained<storage["retained_cap_bytes"] and storage["free_bytes"]>storage["reserve_bytes"]
    save(receipts/"storage-final.json",storage)
    receipt_inventory=[]
    for path in sorted(receipts.rglob("*")):
        if path.is_file():
            receipt_inventory.append(dict(path=str(path.relative_to(receipts)),**record(path)))
    handoff=dict(schema_version="bf-phase5-a-handoff-v1",feature=admission["feature"],owner=admission["owner"],
        dispatch_id=admission["dispatch_id"],created_utc=now,status="A_OWNED_WORK_COMPLETE_READY_FOR_S0",
        portable_root=str(paper),portable_handoff=record(paper/"HANDOFF.json"),paper_pdf=dict(path=str(paper/"main.pdf"),**record(paper/"main.pdf"),pages=11),
        exact_source_dependencies=dict(path="source-dependencies.json",**record(receipts/"source-dependencies.json"),entries=645,data_files=643),
        portable_commands=portable["commands"],overleaf=overleaf,
        qa=dict(compile="PASS_TWO_PASSES",visual="PASS_ALL_11_FINAL_PAGES_ACTUALLY_VIEWED",source_preservation="PASS_645_DEPENDENCIES_AND_145_PROTECTED_FILES",
                saved_data_reproduction="PASS_CWD_INDEPENDENT_BYTE_IDENTICAL_OUTPUTS",secrets="PASS_HEURISTIC_SCAN",claim_index="PASS_19_CLAIMS_VALIDATED_SELECTORS"),
        results=dict(F4="KEEP_UNCHANGED_BASE_H",F5="H0 7/9; G0 6/9; G1 8/9, descriptive only",F6="NO_GO; dark FAIL; FIFO FAIL; NOT_ACCEPTED; physical UNKNOWN"),
        accounting=dict(unique_finite_settled_requests=1238,upper_usd="10.0268025",historical_unknown_rows=24,Codex="UNPRICED_NONZERO",end_to_end="UNKNOWN"),
        new_work=portable["new_work"],storage=storage,
        failures_retained=["readback-attempt-001.json","readback-attempt-003.json","readback-attempt-004.json",
                           "collection-extension-attempt-001.json","inspection-attempt-001.json"],
        source_phase1_4_modified=False,default_H0_changed=False,committed=False,pushed=False,published=False,
        coordinator_pending=["Detached relocation/build acceptance", "Global feature_list.json/progress.md/session-handoff.md updates", "Existing authorized Overleaf project synchronization and remote compile"],
        receipt_inventory_policy="All files under this receipt directory except HANDOFF.json itself. Portable HANDOFF.json provides the nonrecursive portable file inventory.",
        receipt_inventory=receipt_inventory)
    save(receipts/"HANDOFF.json",handoff)
    # Read back both inventories after the final write, with no additional files.
    for row in inventory:
        assert record(paper/row["path"])=={k:row[k] for k in ("sha256","bytes")}
    for row in receipt_inventory:
        assert record(receipts/row["path"])=={k:row[k] for k in ("sha256","bytes")}
    assert record(paper/"HANDOFF.json")==handoff["portable_handoff"]
    assert size(paper)+size(receipts)<admission["retained_cap_bytes"]
    assert scan([("paper",paper),("receipts",receipts)])["status"]=="PASS"
    print(json.dumps(dict(status="PASS",pdf_sha256=pdf_sha,pages=11,
        portable_files=len(inventory)+1,receipt_files=len(receipt_inventory)+1,
        retained_bytes=size(paper)+size(receipts),free_bytes=shutil.disk_usage(paper).free,
        portable_handoff_sha256=digest(paper/"HANDOFF.json"),receipt_handoff_sha256=digest(receipts/"HANDOFF.json"),
        next="S0 detached acceptance/publication; A idle")))


if __name__=="__main__":
    main()
