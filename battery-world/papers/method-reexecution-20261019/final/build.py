#!/usr/bin/env python3
"""Compile the saved manuscript only. Requires a local TeX installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tex-engine",default="pdflatex")
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--log-dir",type=Path,required=True)
    ap.add_argument("--attempt",required=True)
    ap.add_argument("--command-prefix",default="")
    args=ap.parse_args()
    paper=Path(__file__).resolve().parent
    out,logs=args.output_dir.resolve(),args.log_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    logs.mkdir(parents=True,exist_ok=True)
    assert shutil.disk_usage(paper).free>10_000_000_000
    receipt=logs/("build-attempt-"+args.attempt+".json")
    assert not receipt.exists(), "retain previous build attempts"
    env=dict(os.environ,SOURCE_DATE_EPOCH="1792459200",FORCE_SOURCE_DATE="1",TZ="UTC")
    cmd=shlex.split(args.command_prefix)+[args.tex_engine,"-interaction=nonstopmode",
        "-halt-on-error","-file-line-error","-no-shell-escape","-recorder",
        "-output-directory="+str(out),"main.tex"]
    passes=[]
    for n in (1,2):
        r=subprocess.run(cmd,cwd=paper,env=env,capture_output=True,text=True)
        target=logs/f"build-{args.attempt}-pass{n}.stdout.log"
        target.write_text(r.stdout+r.stderr)
        passes.append(dict(pass_number=n,returncode=r.returncode,stdout=str(target)))
        if r.returncode:
            break
    log=(out/"main.log").read_text(errors="replace") if (out/"main.log").exists() else ""
    findings=[line for line in log.splitlines() if re.search(r"Overfull|undefined|multiply defined|LaTeX Error",line)]
    success=len(passes)==2 and all(p["returncode"]==0 for p in passes) and not findings
    result=dict(status="PASS" if success else "REPAIR_REQUIRED",command=cmd,passes=passes,
                findings=findings,provider_requests=0,scientific_executions=0)
    for leaf in ("main.log","main.fls"):
        if (out/leaf).exists():
            shutil.copyfile(out/leaf,logs/("build-"+args.attempt+"-"+leaf))
    if (out/"main.pdf").exists() and all(p["returncode"]==0 for p in passes):
        shutil.copyfile(out/"main.pdf",paper/"main.pdf")
        b=(paper/"main.pdf").read_bytes()
        result.update(pdf_sha256=hashlib.sha256(b).hexdigest(),pdf_bytes=len(b))
    receipt.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    return 0 if success else 1


if __name__=="__main__":
    sys.exit(main())
