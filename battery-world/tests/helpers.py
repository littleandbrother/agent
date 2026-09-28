from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MISSION = REPO / "configs" / "missions" / "rotary-overvoltage-v1.json"


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

