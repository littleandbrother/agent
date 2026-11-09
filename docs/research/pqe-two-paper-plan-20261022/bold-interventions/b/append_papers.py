"""Append the two bounded BOLD result paragraphs while preserving F1 bytes."""
from __future__ import annotations

import hashlib
from pathlib import Path


PAPERS = Path(__file__).resolve().parents[5] / "workbench" / "bf-campaign-s0-20261019" / "battery-world" / "papers" / "pqe20261022"
ROWS = {
    "paper1-stage3-decision-increment.md": (
        "96626b914bd00bc0fad55390d30430f946ef10a9f650b5e8df11700cde01373b",
        """\n\n**Frozen joint-design comparison and new-condition consequence (BOLD, 23 October 2026).** Four designs fixed before execution were each run through the same complete consumer on two public M2 conditions. The original parent failed both (received 0/6 and 5/6, the latter only three timely); the bundled source, storage and TX-gate design passed both with six timely deliveries each. Save-first and persistent adaptive designs passed only the gate/recovery condition. On the start/TX condition, adaptive delivery received all six but only five were timely, so receipt count alone did not satisfy service. These eight runs compare complete design packages and cannot assign the gain to one parameter or to automatic H learning. On the prespecified new DOOR condition the common initial design already passed 6/6; the executable parent consumed that result and stopped without an edit. On the new LC-PV condition, all four original complete candidate executions were model-valid but failed service. Its selected candidate increased received records from 1,155 to 1,288 while six service checks still failed. This is an observed limited-method consequence, not two-task repair or hardware evidence. Evidence: `bold-interventions/a/ENGINEERING-RESULTS.json`, `bold-interventions/b/FINAL-REVIEW.md`, and `bold-interventions/s0/batch-result.json`.\n""",
    ),
    "paper2-stage3-decision-increment.md": (
        "e89eafa33633e86470baafbcf97c1a36bf29bbfa6c03ffd061bf57c1dc375206",
        """\n\n**Executable parent, automatic formation and actual selection (BOLD, 23 October 2026).** The developer-written G/S/U parent was frozen against eight shared public engineering incidents before two automatic formations. H2 emitted one genuine H-UPDATE code proposal, but cited lowercase public-source IDs instead of the eligible incident IDs; the unchanged `PATCH_SOURCE_INCIDENTS` contract rejected it before a screen or child run. H4 compared competing explanations and returned a legal empty patch list. Its claim that the incidents lacked activity counts and full-public references is contradicted by the frozen shared history, so it is not a verified H-UPDATE input defect. No H2/H4 descendant was formed or substituted for the parent. The common-history parent correctly stopped after a real initial Update on a new DOOR task that already passed. On the failing new LC-PV task it executed Update→Generate four joint edits→four original complete evaluations→Rank→exact selected-result reuse→Update. All four candidates remained service FAIL; Rank chose the model-valid 1,288-receipt candidate for partial delivery versus 1,155 initially, while six service checks failed. LC-PV activity used `phase_begin` rather than the parent's DOOR-specific `boot`, producing an unsupported `STARTUP_OR_SOURCE` Update branch. The package used 14 full inputs including engineering and initial qualifications, and three settled formation-model requests. It establishes actual hook reachability and a concrete generalization failure, not learned-H adoption, two-task improvement or RSI. Evidence: `bold-interventions/b/FINAL-REVIEW.md` and `bold-interventions/s0/episodes/{form-h2,form-h4,t1-h1,t2-h1}/`.\n""",
    ),
}


def main():
    originals = {}
    for name, (expected, paragraph) in ROWS.items():
        path = PAPERS / name
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != expected:
            raise RuntimeError("PAPER_PREFIX_CHANGED:" + name)
        originals[name] = body
    for name, (_, paragraph) in ROWS.items():
        path = PAPERS / name
        path.write_bytes(originals[name] + paragraph.encode())
        final = path.read_bytes()
        if not final.startswith(originals[name]):
            raise RuntimeError("PAPER_PREFIX_NOT_PRESERVED:" + name)
        print(name, len(originals[name]), len(final), hashlib.sha256(final).hexdigest())


if __name__ == "__main__":
    main()
