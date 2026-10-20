#!/usr/bin/env python3
"""Two-pass local TeX build and document checks; no scientific execution."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parent


def run(args):
    started=time.monotonic()
    result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
    if result.returncode:
        raise RuntimeError("BUILD_COMMAND_FAILED: "+" ".join(args)+"\n"+(result.stdout+result.stderr)[-7000:])
    return result.stdout+result.stderr,time.monotonic()-started


def main(render=False):
    build=ROOT/".build";build.mkdir(exist_ok=True)
    commands=[]
    argv=["pdflatex","-interaction=nonstopmode","-halt-on-error","-file-line-error","-recorder","-output-directory=.build","main.tex"]
    for number in (1,2):
        _,seconds=run(argv)
        commands.append({"pass":number,"argv":argv,"exit_code":0,"wall_s":seconds})
    final=ROOT/"interface-sufficiency-abc.pdf"
    shutil.copyfile(build/"main.pdf",final)
    info,_=run(["pdfinfo",str(final)])
    fonts,_=run(["pdffonts",str(final)])
    run(["pdftotext","-layout",str(final),str(build/"manuscript.txt")])
    run(["pdftotext","-bbox-layout",str(final),str(build/"bbox.html")])
    log=(build/"main.log").read_text(errors="replace")
    warnings=[line for line in log.splitlines() if any(s in line for s in ("Warning:","Overfull ","Underfull ","Missing character:"))]
    pages=int(re.search(r"^Pages:\s+(\d+)",info,re.M)[1])
    if render:
        (build/"pages").mkdir(exist_ok=True)
        for old in (build/"pages").glob("page-*.png"):
            old.unlink()
        run(["pdftoppm","-r","105","-png",str(final),str(build/"pages/page")])
    receipt={"schema_version":"abc-B-paper-build-v1","at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "commands":commands,"pages":pages,"warnings":warnings,"font_report":fonts,
        "pdf_sha256":hashlib.sha256(final.read_bytes()).hexdigest(),"pdf_bytes":final.stat().st_size,
        "visual_inspection":"PENDING","rendered_pages":pages if render else 0,
        "new_model_requests":0,"new_scientific_executions":0,"new_native_jobs":0,
        "scope":"Actual local document build; no scientific reevaluation, hardware or venue-compliance acceptance."}
    (ROOT/"build-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({k:receipt[k] for k in ("pages","warnings","pdf_sha256","pdf_bytes","rendered_pages")}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--render",action="store_true")
    main(p.parse_args().render)
