#!/usr/bin/env python3
"""Compile and render this standalone paper with installed TeX and Poppler.

Run E_reproduce.py first. This helper performs document operations only.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path


def bound(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument("--output", type=Path, default=here/"build")
    parser.add_argument("--pdf", type=Path, default=here/"interface-sufficiency.pdf")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--tex-engine", default="pdflatex")
    args = parser.parse_args()
    output, pdf = args.output.resolve(), args.pdf.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt = args.receipt.resolve() if args.receipt else output/"build-receipt.json"
    require = lambda condition, msg: condition or (_ for _ in ()).throw(ValueError(msg))
    require((here/"generated/checks.json").is_file(), "Run E_reproduce.py before building")
    commands = []
    start = time.monotonic()

    def run(argv):
        program = shutil.which(str(argv[0]))
        require(program is not None, "Required installed document tool is missing: " + str(argv[0]))
        argv = [program] + [str(a) for a in argv[1:]]
        result = subprocess.run(argv, cwd=here, text=True, capture_output=True, timeout=90)
        commands.append({"argv": argv, "returncode": result.returncode,
                         "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
                         "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest()})
        require(result.returncode == 0, (result.stdout+result.stderr)[-3500:])
        return result.stdout+result.stderr

    try:
        for number in (1, 2):
            text = run([args.tex_engine, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
                        "-output-directory="+str(output), "main.tex"])
            (output/f"pass-{number}.stdout.txt").write_text(text)
        log = (output/"main.log").read_text()
        warnings = [line for line in log.splitlines() if any(term in line for term in ("Warning:", "Overfull", "Underfull", "undefined references", "Missing character"))]
        notices = [line for line in warnings if line == "Package epstopdf Warning: Shell escape feature is not enabled."]
        unexpected = [line for line in warnings if line not in notices]
        require(not unexpected, "Document warnings: "+repr(unexpected))
        shutil.copyfile(output/"main.pdf", pdf)
        info, fonts = run(["pdfinfo", pdf]), run(["pdffonts", pdf])
        require("Type 3" not in fonts, "Unexpected Type 3 font")
        font_rows = [r for r in fonts.splitlines()[2:] if r.strip()]
        require(bool(font_rows), "No fonts found")
        for row in font_rows:
            flags = re.search(r"\s+(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", row)
            require(flags is not None and flags.group(1) == "yes", "Unembedded font")
        pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
        text_path = output/"extracted.txt"
        run(["pdftotext", "-layout", pdf, text_path])
        text = text_path.read_text()
        page_text = [p for p in text.split("\f") if p.strip()]
        require(len(page_text) == pages and "??" not in text, "Page/reference extraction failed")
        required = ["7/12", "12/12", "1.004", "1.103", "32,768", "UNKNOWN", "NOT_ACCEPTED", "E_reproduce.py", "3.1767228"]
        require(all(term in text for term in required), "Required content missing: "+repr([s for s in required if s not in text]))
        replaced = [bound(p) for p in sorted(output.glob("page-*.png"))]
        for item in replaced:
            Path(item["path"]).unlink()
        run(["pdftoppm", "-r", "100", "-png", pdf, output/"page"])
        images = sorted(output.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        require(len(images) == pages, "Render page count mismatch")
        source_paths = list(here.glob("*.tex"))+list((here/"sections").glob("*.tex"))+list((here/"generated/tables").glob("*.tex"))
        source_paths += [here/"hkustgz-paper.sty", here/"assets/hkustgz-english.pdf", here/"E_reproduce.py", here/"build_paper.py", here/"data/manifest.json", here/"generated/checks.json"]
        result = {"status": "COMPILED_PENDING_DIRECT_ALL_PAGE_VISUAL_REVIEW", "page_count": pages, "pdf": bound(pdf), "passes": 2,
                  "document_commands": commands, "elapsed_s": time.monotonic()-start, "last_pass_warnings": unexpected,
                  "document_tool_notices": notices, "notice_scope": "Shell escape is deliberately disabled; included artwork is PDF, so no EPS conversion is required.",
                  "all_fonts_embedded": True, "font_count": len(font_rows), "pdfinfo": info, "pdffonts": fonts,
                  "required_text_checks": required, "page_text_lengths": [len(p.strip()) for p in page_text],
                  "sources": [bound(p) for p in sorted(source_paths)], "page_images": [bound(p) for p in images], "replaced_previous_page_images": replaced,
                  "new_provider_requests": 0, "new_scientific_executions": 0}
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps({"status": result["status"], "pages": pages, "fonts": len(font_rows), "pdf": result["pdf"], "warnings": unexpected}))
    except Exception as exc:
        failure = {"status": "DOCUMENT_BUILD_FAILED", "error": str(exc), "document_commands": commands, "elapsed_s": time.monotonic()-start,
                   "scope": "Document-only attempt; no SDK/model/scientific call"}
        (output/"build-failure.json").write_text(json.dumps(failure, indent=2)+"\n")
        print(json.dumps(failure))
        raise


if __name__ == "__main__":
    main()
