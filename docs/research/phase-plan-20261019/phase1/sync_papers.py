"""Synchronize the two authorized Overleaf checkouts with bounded TeX scratch.

Only manuscript sources, their figure assets, and the shared style/logo are
published. Existing unrelated template files are retained. No source repository
is committed, no new checkout/environment is created, and no credentials are
written. A normal authenticated Git credential helper is reused.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
CHECKOUTS = Path.home() / ".local/share/bf-agent-manuscripts/overleaf"
SPECS = {
    "interface": ("interface-sufficiency-20261019", "manuscript.tex",
                  "interface-sufficiency-phase1.pdf", "6ad5fbda856b284d5d917ffd"),
    "rsi": ("method-reexecution-20261019", "main.tex", "main.pdf",
            "6ad5fb6e87c3ac6782d05b2c"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, cwd=None, timeout=60):
    result = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout,
                            env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if result.returncode:
        # Git diagnostics may include a configured URL; never print those.
        message = result.stdout.decode(errors="replace")[-2500:] if args[0] == "pdflatex" else ""
        raise RuntimeError(f"{args[0]} {args[1]} failed ({result.returncode})\n{message}")
    return result.stdout


def seal(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def words(pdf):
    xml = ET.fromstring(run(["pdftotext", "-bbox-layout", str(pdf), "-"]))
    pages = []
    for page in xml.iter():
        if page.tag.rsplit("}", 1)[-1] == "page":
            pages.append({"dimensions": dict(page.attrib), "words": [
                [dict(word.attrib), word.text] for word in page.iter()
                if word.tag.rsplit("}", 1)[-1] == "word"]})
    return pages


def prepare(key):
    folder, entry, reference_name, project = SPECS[key]
    out = HERE / "publication" / key / "prepare.json"
    if out.exists():
        raise FileExistsError("REVIEW_EXISTING_PREPARATION_RECEIPT")
    if shutil.disk_usage(ROOT).free < 10_900_000_000:
        raise RuntimeError("PHASE_STORAGE_RESERVE")
    local, checkout = APP / "papers" / folder, CHECKOUTS / project
    if run(["git", "status", "--porcelain=v1"], checkout).strip():
        raise ValueError("EXISTING_OVERLEAF_CHANGES_REQUIRE_REVIEW")
    before = run(["git", "rev-parse", "HEAD"], checkout).decode().strip()
    remote = run(["git", "ls-remote", "origin", "HEAD"], checkout).decode().split()[0]
    if before != remote:
        raise ValueError("REMOTE_CHANGED_RECONCILE_BEFORE_WRITING")
    selected = {"main.tex": local / entry}
    selected.update({path.name: path for path in local.glob("*.tex") if path.name != entry})
    # Only the named paper figure directory is eligible; no runtime or data tree.
    figures = local / "phase1-figures"
    if figures.exists():
        selected.update({str(path.relative_to(local)): path for path in figures.iterdir()
                         if path.is_file() and path.suffix in {".pdf", ".png", ".svg"}})
    selected["hkustgz-paper.sty"] = APP / "papers/shared/hkustgz-paper.sty"
    for extension in ["pdf", "svg"]:
        selected[f"assets/hkustgz-english.{extension}"] = APP / f"papers/shared/assets/hkustgz-english.{extension}"
    if sum(path.stat().st_size for path in selected.values()) > 8_000_000:
        raise ValueError("PAPER_PACKAGE_CAP")
    bindings = {relative: {"source": str(path), "sha256": sha(path), "bytes": path.stat().st_size}
                for relative, path in selected.items()}
    free_before = shutil.disk_usage(ROOT).free
    for relative, source in selected.items():
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or sha(target) != bindings[relative]["sha256"]:
            shutil.copyfile(source, target)
    wrapper = "% Compatibility entry for the existing Overleaf main-document setting.\n\\input{main.tex}\n"
    (checkout / "example_paper.tex").write_text(wrapper)
    package = {"schema_version": "bf-phase1-overleaf-manuscript-binding-v1",
               "project": project, "source_baseline": "CB2-61f3ff75e94647915c87b3746c3bc5e12a374409efe0642e6d3e3980fa2a672a",
               "files": {name: {k: value for k, value in item.items() if k != "source"}
                         for name, item in bindings.items()},
               "scope": "Manuscript source synchronization; raw scientific data remains in sealed local receipts, not a portable data release.",
               "cloud_compile": "NOT_RUN"}
    (checkout / "phase1-publication.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n")
    with tempfile.TemporaryDirectory(prefix="bf-paper-build-") as scratch_text:
        scratch = Path(scratch_text)
        passes = []
        for _ in range(2):
            run(["pdflatex", "-recorder", "-interaction=nonstopmode", "-halt-on-error",
                 "-output-directory=" + str(scratch), "example_paper.tex"], checkout)
            passes.append(0)
        log = (scratch / "example_paper.log").read_text(errors="replace")
        warnings = [line for line in log.splitlines()
                    if re.search(r"Warning|Overfull|Underfull|Missing character", line)]
        if warnings:
            raise ValueError("PORTABLE_TEX_WARNINGS:" + repr(warnings))
        built = scratch / "example_paper.pdf"
        reference = local / reference_name
        reference_words, built_words = words(reference), words(built)
        if reference_words != built_words:
            raise ValueError("PORTABLE_LAYOUT_DIFFERS_FROM_REVIEWED_PDF")
        font_lines = run(["pdffonts", str(built)]).decode().splitlines()[2:]
        if any(len(line.split()) < 8 or line.split()[-5] != "yes" for line in font_lines):
            raise ValueError("UNEMBEDDED_PORTABLE_FONT")
        shutil.copyfile(built, checkout / "example_paper.pdf")
    files = {name: sha(checkout / name) for name in [*selected, "example_paper.tex", "example_paper.pdf", "phase1-publication.json"]}
    run(["git", "diff", "--check"], checkout)
    receipt = {"schema_version": "bf-phase1-overleaf-build-v1", "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "status": "PASS", "key": key, "project": project, "checkout": str(checkout),
               "previous_head": before, "source_bindings": bindings, "files": files,
               "reviewed_reference_pdf": {"path": str(reference), "sha256": sha(reference)},
               "pages": len(built_words), "passes": passes, "warnings": warnings,
               "portable_word_positions_and_page_dimensions_equal": True,
               "embedded_fonts": len(font_lines), "all_fonts_embedded": True,
               "shared_style_and_logo_byte_exact": True, "temporary_build_removed": True,
               "free_bytes_before": free_before, "free_bytes_after": shutil.disk_usage(ROOT).free,
               "published": False, "cloud_compile_verified": False}
    seal(out, receipt)
    print(json.dumps({"paper": key, "status": "PASS", "pages": len(built_words), "files": len(files), "receipt": str(out)}))


def publish(key):
    out = HERE / "publication" / key / "published.json"
    if out.exists():
        raise FileExistsError("REVIEW_EXISTING_PUBLICATION_RECEIPT")
    receipt = json.loads((out.parent / "prepare.json").read_text())
    checkout = Path(receipt["checkout"])
    for name, binding in receipt["source_bindings"].items():
        if sha(Path(binding["source"])) != binding["sha256"]:
            raise ValueError("SOURCE_CHANGED_AFTER_REVIEW:" + name)
    for name, expected in receipt["files"].items():
        if sha(checkout / name) != expected:
            raise ValueError("PACKAGE_CHANGED_AFTER_BUILD:" + name)
    remote = run(["git", "ls-remote", "origin", "HEAD"], checkout).decode().split()[0]
    if remote != receipt["previous_head"] or run(["git", "rev-parse", "HEAD"], checkout).decode().strip() != remote:
        raise ValueError("PUBLICATION_HEAD_CHANGED")
    # Parse NUL-delimited porcelain so every changed path must be in the package.
    changes = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], checkout).split(b"\0")
    for change in filter(None, changes):
        if change[3:].decode() not in receipt["files"] or b"R" in change[:2] or b"D" in change[:2]:
            raise ValueError("UNRELATED_OVERLEAF_CHANGE")
    run(["git", "diff", "--check"], checkout)
    run(["git", "add", "--", *receipt["files"]], checkout)
    summary = "Record phase-one A/R repair limits and complete accounting" if key == "rsi" else "Add BF mechanism evidence and frozen E4/E5 protocols"
    run(["git", "commit", "-m", summary], checkout)
    head = run(["git", "rev-parse", "HEAD"], checkout).decode().strip()
    branch = run(["git", "branch", "--show-current"], checkout).decode().strip()
    if not branch:
        raise ValueError("DETACHED_OVERLEAF_HEAD")
    run(["git", "push", "origin", "HEAD:refs/heads/" + branch], checkout, timeout=120)
    run(["git", "fetch", "origin", "refs/heads/" + branch], checkout, timeout=120)
    fetched = run(["git", "rev-parse", "FETCH_HEAD"], checkout).decode().strip()
    if fetched != head:
        raise ValueError("REMOTE_READBACK_HEAD_MISMATCH")
    for name, expected in receipt["files"].items():
        actual = hashlib.sha256(run(["git", "show", fetched + ":" + name], checkout)).hexdigest()
        if actual != expected:
            raise ValueError("REMOTE_FILE_READBACK_MISMATCH:" + name)
    if run(["git", "status", "--porcelain=v1"], checkout).strip():
        raise ValueError("OVERLEAF_CHECKOUT_NOT_CLEAN")
    result = {"status": "PASS", "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "project": receipt["project"], "url": "https://www.overleaf.com/project/" + receipt["project"],
              "previous_head": receipt["previous_head"], "head": head, "fetched_head": fetched,
              "fetched_source_hashes": receipt["files"], "checkout_clean": True,
              "local_portable_build_verified": True, "cloud_compile_verified": False,
              "root_or_s0_commit": False}
    seal(out, result)
    print(json.dumps({"paper": key, "published": True, "head": head, "files_verified": len(receipt["files"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "publish"])
    parser.add_argument("paper", choices=SPECS)
    args = parser.parse_args()
    (prepare if args.mode == "prepare" else publish)(args.paper)
