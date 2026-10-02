"""Durable LiveRun state, atomic artifacts, and checkpoint recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json
from bfworld.runtime.journal import HashJournal


class LiveRunError(RuntimeError):
    pass


class LiveRun:
    def __init__(self, workspace: Path, run_id: str) -> None:
        self.run_id = run_id
        self.root = workspace / "live-runs" / run_id.replace(":", "-")
        self.artifacts = self.root / "artifacts"
        self.events = HashJournal(self.root / "events.jsonl", run_id)
        self.audit = HashJournal(
            self.root / "runtime-audit.jsonl",
            run_id,
            hash_field="audit_hash",
        )

    @classmethod
    def create(cls, workspace: Path, run_id: str, plan: dict[str, Any]) -> "LiveRun":
        root = workspace / "live-runs" / run_id.replace(":", "-")
        if root.exists():
            raise LiveRunError(f"live run already exists: {root}")
        live = cls(workspace, run_id)
        live.artifacts.mkdir(parents=True)
        write_canonical_json(live.root / "plan.json", plan)
        live.audit.append("process_started", {"mode": "create"})
        return live

    @classmethod
    def resume(cls, workspace: Path, run_id: str, plan: dict[str, Any]) -> "LiveRun":
        live = cls(workspace, run_id)
        if not live.root.exists():
            raise LiveRunError(f"live run does not exist: {live.root}")
        with (live.root / "plan.json").open("r", encoding="utf-8") as handle:
            stored = json.load(handle)
        if canonical_hash(stored) != canonical_hash(plan):
            raise LiveRunError("resume plan identity mismatch")
        live.events.validate()
        live.audit.validate()
        live._validate_checkpoint()
        live.audit.append("process_recovered", {"mode": "resume"})
        return live

    def write_artifact(self, relative: str, value: Any) -> Path:
        path = self.artifacts / relative
        if path.exists():
            raise LiveRunError(f"artifact already exists: {relative}")
        if isinstance(value, bytes):
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            with temporary.open("wb") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        else:
            write_canonical_json(path, value)
        return path

    def read_artifact(self, relative: str) -> Any:
        path = self.artifacts / relative
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def checkpoint(self, phase: str, bound_artifacts: list[str]) -> None:
        bindings = {}
        for relative in sorted(bound_artifacts):
            path = self.artifacts / relative
            if not path.is_file():
                raise LiveRunError(f"checkpoint artifact missing: {relative}")
            bindings[relative] = file_hash(path)
        state = {
            "schema_version": "bfworld-checkpoint-v1",
            "run_id": self.run_id,
            "phase": phase,
            "event_head": self.events.head,
            "artifacts": bindings,
        }
        state["checkpoint_hash"] = canonical_hash(state)
        write_canonical_json(self.root / "checkpoint.json", state)
        self.audit.append("checkpoint_committed", {"phase": phase, "checkpoint_hash": state["checkpoint_hash"]})

    def checkpoint_state(self) -> dict[str, Any] | None:
        path = self.root / "checkpoint.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        unsigned = dict(state)
        claimed = unsigned.pop("checkpoint_hash")
        if canonical_hash(unsigned) != claimed:
            raise LiveRunError("checkpoint hash mismatch")
        return state

    def _validate_checkpoint(self) -> None:
        state = self.checkpoint_state()
        if state is None:
            return
        if state["run_id"] != self.run_id:
            raise LiveRunError("checkpoint run identity mismatch")
        if state["event_head"] != self.events.head:
            raise LiveRunError("checkpoint event head mismatch")
        for relative, expected in state["artifacts"].items():
            path = self.artifacts / relative
            if not path.is_file() or file_hash(path) != expected:
                raise LiveRunError(f"checkpoint artifact drift: {relative}")

    @property
    def recovery_count(self) -> int:
        return sum(1 for record in self.audit.read() if record["type"] == "process_recovered")
