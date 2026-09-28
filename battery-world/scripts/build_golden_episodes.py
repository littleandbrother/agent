#!/usr/bin/env python3
"""Materialize the B0-000 semantic golden episodes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_SOURCE = REPO / "packages" / "python" / "bfworld" / "src"
sys.path.insert(0, str(PYTHON_SOURCE))

from bfworld.semantics.golden import write_golden_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO / "fixtures" / "golden-episodes",
        help="Output directory for the deterministic suite.",
    )
    args = parser.parse_args()
    manifest = write_golden_suite(args.output)
    print(
        json.dumps(
            {
                "status": "materialized",
                "output": str(args.output.resolve()),
                "content_hash": manifest["content_hash"],
                "episode_count": len(manifest["files"]),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
