"""Close a LiveRun into an immutable, self-describing RunBundle."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from bfworld.bundle.format import PHASES, scientific_hash
from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json
from bfworld.runtime.live import LiveRun
from bfworld.bundle.projection import render_replay


CHANNEL_SCHEMA = pa.schema(
    [
        ("phase", pa.string()),
        ("step", pa.int64()),
        ("time_s", pa.float64()),
        ("rpm", pa.float64()),
        ("source_current_a", pa.float64()),
        ("harvest_current_a", pa.float64()),
        ("load_current_a", pa.float64()),
        ("leak_current_a", pa.float64()),
        ("shunt_current_a", pa.float64()),
        ("capacitor_voltage_v", pa.float64()),
        ("storage_energy_j", pa.float64()),
        ("inference_active", pa.bool_()),
        ("brownout", pa.bool_()),
        ("overvoltage", pa.bool_()),
    ]
)


def _inventory(root: Path, *, exclude: set[str]) -> list[dict[str, Any]]:
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in exclude:
            continue
        records.append({"path": relative, "sha256": file_hash(path), "bytes": path.stat().st_size})
    return records


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_run_bundle(
    live: LiveRun,
    mission: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"bundle output already exists: {output}")
    final_output = output
    staging = output.with_name(output.name + ".staging")
    if staging.exists():
        raise FileExistsError(f"bundle staging output already exists: {staging}")
    output = staging
    output.mkdir(parents=True)

    shutil.copyfile(live.artifacts / "world.ir.json", output / "world.ir.json")
    shutil.copyfile(live.events.path, output / "events.jsonl")
    shutil.copyfile(live.audit.path, output / "runtime-audit.jsonl")

    rows: list[dict[str, Any]] = []
    phases: dict[str, Any] = {}
    for phase in PHASES:
        rows.extend(_read_json(live.artifacts / f"{phase}-rows.json"))
        phases[phase] = _read_json(live.artifacts / f"{phase}-summary.json")
    table = pa.Table.from_pylist(rows, schema=CHANNEL_SCHEMA)
    pq.write_table(
        table,
        output / "channels.parquet",
        compression="NONE",
        version="2.6",
        write_statistics=True,
    )

    world_ir = _read_json(output / "world.ir.json")
    event_head = live.events.head
    if event_head is None:
        raise ValueError("cannot bundle an empty event journal")
    result_hash = scientific_hash(world_ir["canonical_hash"], event_head, phases)
    convergence = _read_json(live.artifacts / "convergence.json")

    evidence = {
        "schema_version": "bfworld-evidence-v1",
        "run_id": live.run_id,
        "claims": [
            {
                "claim_id": "baseline-overvoltage-observed",
                "verdict": phases["baseline"]["overvoltage_count"] > 0,
                "scope": "frozen public numerical mission",
            },
            {
                "claim_id": "revised-design-passes",
                "verdict": phases["revised"]["passed"],
                "scope": "coarse F1-simplified simulation",
            },
            {
                "claim_id": "fine-validation-passes",
                "verdict": phases["fine_validation"]["passed"] and convergence["passed"],
                "scope": "finer-step F1-simplified simulation",
            },
        ],
        "artifact_bindings": {
            "world.ir.json": file_hash(output / "world.ir.json"),
            "events.jsonl": file_hash(output / "events.jsonl"),
            "channels.parquet": file_hash(output / "channels.parquet"),
        },
        "fidelity": "F1-simplified",
        "hardware_result": False,
        "limitations": [
            "No measured TENG terminal waveforms are used.",
            "Fine validation changes numerical resolution, not physical fidelity class.",
            "No Agent, DSH, hidden evaluator, radio, MCU, or hardware result is included.",
        ],
    }
    write_canonical_json(output / "evidence.json", evidence)

    views = {
        "schema_version": "bfworld-views-v1",
        "run_id": live.run_id,
        "event_head": event_head,
        "views": [
            {
                "id": "voltage-timeline",
                "type": "line",
                "source": "channels.parquet",
                "x": "time_s",
                "y": "capacitor_voltage_v",
                "facet": "phase",
                "unit": "V",
            },
            {
                "id": "failure-lens",
                "type": "events",
                "source": "events.jsonl",
                "filter": ["constraint_violated", "design_revision_applied"],
            },
            {
                "id": "evidence-matrix",
                "type": "claims",
                "source": "evidence.json",
            },
        ],
    }
    write_canonical_json(output / "views.json", views)
    render_replay(output, rows, evidence, views, result_hash)

    pre_manifest_inventory = _inventory(output, exclude={"run-manifest.json", "bundle-seal.json"})
    manifest = {
        "schema_version": "bfworld-run-manifest-v1",
        "run_id": live.run_id,
        "world_hash": world_ir["canonical_hash"],
        "event_head": event_head,
        "scientific_hash": result_hash,
        "phases": phases,
        "recovery_count": live.recovery_count,
        "inventory": pre_manifest_inventory,
        "claim_boundary": (
            "Deterministic F1-simplified computational apparatus only; no hardware, "
            "Agent, DSH-benefit, or RSI claim."
        ),
    }
    write_canonical_json(output / "run-manifest.json", manifest)

    sealed_inventory = _inventory(output, exclude={"bundle-seal.json"})
    bundle_hash = canonical_hash(
        {"schema_version": "bfworld-bundle-inventory-v1", "files": sealed_inventory}
    )
    seal = {
        "schema_version": "bfworld-bundle-seal-v1",
        "run_id": live.run_id,
        "bundle_hash": bundle_hash,
        "files": sealed_inventory,
    }
    write_canonical_json(output / "bundle-seal.json", seal)
    directory_fd = os.open(output, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    output.replace(final_output)
    parent_fd = os.open(final_output.parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return {
        "run_id": live.run_id,
        "scientific_hash": result_hash,
        "bundle_hash": bundle_hash,
        "output": str(final_output),
    }
