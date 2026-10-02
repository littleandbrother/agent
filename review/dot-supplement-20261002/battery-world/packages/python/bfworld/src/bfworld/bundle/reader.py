"""The shared read-only projection boundary for Agent, Studio, and Verifier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


class RunBundleReader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def json(self, name: str) -> dict[str, Any]:
        with (self.root / name).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @property
    def manifest(self) -> dict[str, Any]:
        return self.json("run-manifest.json")

    @property
    def evidence(self) -> dict[str, Any]:
        return self.json("evidence.json")

    @property
    def views(self) -> dict[str, Any]:
        return self.json("views.json")

    def events(self) -> list[dict[str, Any]]:
        with (self.root / "events.jsonl").open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle]

    def channels(self) -> list[dict[str, Any]]:
        return pq.read_table(self.root / "channels.parquet").to_pylist()

