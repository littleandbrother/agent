"""Append-only deterministic event journals."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from bfworld.kernel.canonical import canonical_bytes, canonical_hash


class JournalError(RuntimeError):
    pass


class HashJournal:
    def __init__(self, path: Path, run_id: str, *, hash_field: str = "event_hash") -> None:
        self.path = path
        self.run_id = run_id
        self.hash_field = hash_field
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.path.open("rb") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.endswith(b"\n"):
                    raise JournalError(f"unterminated journal frame at line {line_number}")
                try:
                    records.append(json.loads(raw))
                except json.JSONDecodeError as exc:
                    raise JournalError(f"invalid journal JSON at line {line_number}") from exc
        self.validate(records)
        return records

    def validate(self, records: list[dict[str, Any]] | None = None) -> None:
        if records is None:
            records = self.read()
            return
        previous: str | None = None
        for expected_index, record in enumerate(records):
            if record.get("run_id") != self.run_id:
                raise JournalError("journal run identity mismatch")
            if record.get("index") != expected_index:
                raise JournalError("journal index mismatch")
            if record.get("previous_hash") != previous:
                raise JournalError("journal previous hash mismatch")
            claimed = record.get(self.hash_field)
            unsigned = dict(record)
            unsigned.pop(self.hash_field, None)
            actual = canonical_hash(unsigned)
            if claimed != actual:
                raise JournalError("journal event hash mismatch")
            previous = actual

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        records = self.read()
        record: dict[str, Any] = {
            "schema_version": "bfworld-event-v1" if self.hash_field == "event_hash" else "bfworld-runtime-audit-v1",
            "run_id": self.run_id,
            "index": len(records),
            "logical_time": len(records),
            "type": event_type,
            "payload": payload,
            "previous_hash": records[-1][self.hash_field] if records else None,
        }
        record[self.hash_field] = canonical_hash(record)
        with self.path.open("ab") as handle:
            handle.write(canonical_bytes(record))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    @property
    def head(self) -> str | None:
        records = self.read()
        return records[-1][self.hash_field] if records else None

