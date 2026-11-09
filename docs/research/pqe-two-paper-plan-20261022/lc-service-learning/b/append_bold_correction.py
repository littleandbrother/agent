"""Append the BOLD view correction without changing either sealed prefix."""
from __future__ import annotations

import hashlib
from pathlib import Path


PAPERS = Path(__file__).resolve().parents[5] / "workbench/bf-campaign-s0-20261019/battery-world/papers/pqe20261022"
ROWS = {
    "paper1-stage3-decision-increment.md": (
        "1bf0d5c2c5b0dc9078e8fb26f9101a3ac1f9d877b788c1b47960a714957c0e64",
        "\n\n**BOLD formation-view correction (24 October 2026).** The saved compact engineering history contained activity counts and public-result references, but the actual H4 formation request showed a different, original trace/activity-style paged view without those fields. An earlier readback incorrectly treated saved history as the model-visible view. This changes the interpretation of H4's field observation, not the eight engineering outcomes, the original consumer, or either new-task service result. The claim that runtime H-UPDATE lacked those fields remains unproved. See `bold-interventions/b/CORRECTION-20261024.md` and `bold-interventions/s0/CORRECTION-20261024.md`.\n",
    ),
    "paper2-stage3-decision-increment.md": (
        "5d665ee2525b87482c04490b99ee396e719c979fb667a984a9a3dac7f3f98ec3",
        "\n\n**BOLD input-view correction (24 October 2026).** Direct readback of the sent H4 request shows that all eight incident summaries lacked inline `activity_counts` and `detail_catalog`: projection by original `result_sha256` silently substituted a paged raw-result view for the compact saved history. H4's description of its visible fields was supported, though the extrapolation to live H-UPDATE was not tested. H2's sent proposal context paged the eligible incident list while inlining separate lowercase source IDs; its use of those IDs as `source_incidents` still violated the original contract, but the representation ambiguity contributed to the failure and no feedback turn followed. The original H2 rejection, H4 empty proposal, absent descendants and parent task outcomes remain unchanged. See `bold-interventions/b/CORRECTION-20261024.md` and `lc-service-learning/s0/bold-view-correction.json`.\n",
    ),
}


def main():
    original = {}
    for name, (expected, _) in ROWS.items():
        body = (PAPERS / name).read_bytes()
        if hashlib.sha256(body).hexdigest() != expected:
            raise RuntimeError("SEALED_PAPER_PREFIX_CHANGED:" + name)
        original[name] = body
    for name, (_, text) in ROWS.items():
        path = PAPERS / name
        path.write_bytes(original[name] + text.encode())
        body = path.read_bytes()
        if not body.startswith(original[name]):
            raise RuntimeError("PAPER_PREFIX_NOT_PRESERVED:" + name)
        print(name, len(original[name]), len(body), hashlib.sha256(body).hexdigest())


if __name__ == "__main__":
    main()
