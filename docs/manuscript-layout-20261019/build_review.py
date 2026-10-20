#!/usr/bin/env python3
"""Build the two manuscripts with bounded, automatically removed TeX scratch."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
SPECS = {
    "interface": ("interface-sufficiency-20261019", "manuscript.tex", "6ad5fbda856b284d5d917ffd"),
    "rsi": ("method-reexecution-20261019", "main.tex", "6ad5fb6e87c3ac6782d05b2c"),
}


def run(args, cwd=None, timeout=60):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--overleaf", action="store_true")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    before = json.loads((OUT / "source-before.json").read_text())
    results = {}
    for key, (folder, name, project) in SPECS.items():
        local = APP / "papers" / folder / name
        text = local.read_text()
        body = text[text.index("\\begin{abstract}"):].encode()
        assert hashlib.sha256(body).hexdigest() == before[key]["body_sha256"], key
        wd = Path.home() / ".local/share/bf-agent-manuscripts/overleaf" / project if args.overleaf else local.parent
        entry = "example_paper.tex" if args.overleaf else name
        stem = Path(entry).stem
        with tempfile.TemporaryDirectory(prefix="hkustgz-layout-build-") as scratch:
            passes = []
            for _ in range(2):
                result = run(["pdflatex", "-recorder", "-interaction=nonstopmode", "-halt-on-error", "-output-directory=" + scratch, entry], wd)
                passes.append(result.returncode)
                if result.returncode:
                    raise RuntimeError(key + " build failed:\n" + result.stdout[-3500:])
            scratch = Path(scratch)
            log = (scratch / (stem + ".log")).read_text(errors="replace")
            warnings = [line for line in log.splitlines() if re.search(r"Warning|Overfull|Underfull|Missing character", line)]
            assert not warnings, (key, warnings)
            pdf = scratch / (stem + ".pdf")
            info = run(["pdfinfo", str(pdf)]).stdout
            pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
            assert "612 x 792 pts (letter)" in info
            dest = local.parent / "build" / (local.stem + ".pdf")
            if not args.overleaf:
                dest.parent.mkdir(exist_ok=True)
                shutil.copyfile(pdf, dest)
            final_text = run(["pdftotext", "-layout", str(pdf), "-"]).stdout
            (OUT / (key + "-final-text.txt")).write_text(final_text)
            bbox = run(["pdftotext", "-f", "1", "-l", "1", "-bbox-layout", str(pdf), "-"]).stdout
            (OUT / (key + "-bbox.html")).write_text(bbox)
            if args.render:
                images = OUT / (key + "-pages")
                images.mkdir(exist_ok=True)
                rendered = run(["pdftoppm", "-scale-to", "1500", "-png", str(pdf), str(images / "page")])
                assert rendered.returncode == 0, rendered.stderr
            results[key] = {
                "pdf": str(dest), "pages": pages, "passes": passes, "warnings": warnings,
                "body_sha256": hashlib.sha256(body).hexdigest(), "body_byte_exact": True,
                "bytes": pdf.stat().st_size, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                "page_size_pt": [612, 792], "entry_point": entry,
                "text_sha256": hashlib.sha256(final_text.encode()).hexdigest(),
            }
        print(key, pages, "pages; body byte exact; no TeX warnings", flush=True)
    label = "overleaf-build" if args.overleaf else "build"
    (OUT / (label + ".json")).write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
