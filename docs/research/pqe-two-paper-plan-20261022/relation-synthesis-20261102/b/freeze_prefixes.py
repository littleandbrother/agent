"""Freeze four normal generation outputs; does not execute scientific designs."""
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import json
import os
import time

from semantic_search import SemanticFactory, build_state, digest, VERSION
from bfworld.agentlab.pqe20261024debt import task as door_task

ROOT = Path(__file__).resolve().parent


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def freeze():
    destination = ROOT / "frozen-prefixes"
    destination.mkdir(exist_ok=False)
    start = time.monotonic()
    static = {"validator_calls": 0, "geometry_cache_misses": 0, "geometry_cache_hits": 0,
              "pure_static_rejections": 0, "validation_wall_s": 0., "cheap_cap": 16}
    index = json.loads((ROOT.parent / "shared/prefixes/index.json").read_text())
    summaries, candidates = [], []
    for row, seed in zip(index["prefixes"], (314159, 271828)):
        path = Path(row["path"])
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha != row["sha256"]:
            raise ValueError("PUBLIC_PREFIX_FILE_HASH_MISMATCH")
        with gzip.open(path, "rt") as stream:
            prefix = json.load(stream)
        contract, result, prior = prefix["public_contract"], prefix["family_result"], prefix["prior_result"]
        tasks = contract["tasks"]

        def validate(design):
            for task in tasks:
                before = set(door_task._STATIC_GEOMETRY_CACHE)
                at = time.monotonic()
                static["validator_calls"] += 1
                try:
                    door_task.validate_design(task, design)
                except Exception:
                    static["pure_static_rejections"] += 1
                    raise
                finally:
                    added = len(set(door_task._STATIC_GEOMETRY_CACHE) - before)
                    static["geometry_cache_misses"] += added
                    if not added:
                        # A domain rejection before geometry is not a cache hit.
                        from bfworld.agentlab.pqe20261022 import door_model
                        payload = json.dumps({"mechanism": design["mechanism"],
                                              "defaults": door_model.DEFAULT_MECHANISM,
                                              "domain": door_model.DOMAIN}, sort_keys=True,
                                             separators=(",", ":"), allow_nan=False)
                        key = (door_model.source_step, getattr(door_model.source_step, "__code__", None), payload)
                        if key in before:
                            static["geometry_cache_hits"] += 1
                    static["validation_wall_s"] += time.monotonic() - at
                    if static["geometry_cache_misses"] > 16:
                        raise RuntimeError("B_CHEAP_CAP_EXCEEDED_STOP")

        state = build_state(result, prior, contract)
        factory = SemanticFactory(contract, result["design"], validate_fn=validate)
        cells = []
        for enabled in (False, True):
            label = "on" if enabled else "off"
            generation = factory.generate(result["design"], state, seed=seed, round_index=0,
                                          relations_enabled=enabled)
            selected = factory.select(generation, seen_keys=[factory.semantic_key(result["design"])],
                                      parent_id=prefix["node_id"])
            cell = {"prefix_id": prefix["prefix_id"], "switch": label,
                    "relations_enabled": enabled, "seed": seed, "round_index": 0,
                    "state": state, "generation": generation, "selected": selected,
                    "source_public_prefix": {"path": str(path), "sha256": actual_sha},
                    "original_condition_ids": state["condition_ids"],
                    "full_result_status": "NOT_EXECUTED_BY_B", "source_version": VERSION}
            name = prefix["prefix_id"] + "-" + label + ".json.gz"
            # Exclusive raw file prevents overwriting any historical generation.
            with (destination / name).open("xb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
                    stream.write(json.dumps(cell, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode())
            cells.append(cell)
            candidates.append({"prefix_id": prefix["prefix_id"], "switch": label,
                               "seed": seed, "parent_id": prefix["node_id"],
                               "design": selected["design"] if selected else None,
                               "design_patch": selected["design_patch"] if selected else None,
                               "selection": selected["selection"] if selected else None,
                               "derivations": selected.get("derivations", []) if selected else [],
                               "cell_path": str(destination / name),
                               "cell_sha256": hashlib.sha256((destination / name).read_bytes()).hexdigest(),
                               "prefix_source_path": str(path), "prefix_source_sha256": actual_sha,
                               "original_condition_ids": state["condition_ids"]})
        off, on = cells
        off_keys = {c["semantic_key"] for c in off["generation"]["candidates"]}
        on_keys = {c["semantic_key"] for c in on["generation"]["candidates"]}
        same_selected = bool(on["selected"] and off["selected"] and on["selected"]["design"] == off["selected"]["design"])
        consumed = bool(on["generation"]["rules_consumed"])
        diagnostic = ("RELATION_TO_ACTION_CHANGED" if not same_selected and consumed else
                      "NO_RELATION_CONSUMPTION" if not consumed else
                      "GENERATION_CHANGED_SELECT_SAME" if on_keys != off_keys else
                      "SAME_POOL_SELECT_SAME")
        summaries.append({"prefix_id": prefix["prefix_id"], "counts": state["stage_counts"],
                          "progress": state["progress"], "pending_kinds": sorted({p["kind"] for p in state["pending_service"]}),
                          "same_common_raw_pool": on["generation"]["common_raw_proposals"] == off["generation"]["common_raw_proposals"],
                          "same_rng_before": on["generation"]["common_rng_before_sha256"] == off["generation"]["common_rng_before_sha256"],
                          "same_rng_after": on["generation"]["common_rng_after_sha256"] == off["generation"]["common_rng_after_sha256"],
                          "same_raw_facts": on["generation"]["raw_public_facts_sha256"] == off["generation"]["raw_public_facts_sha256"],
                          "off_pool_size": len(off_keys), "on_pool_size": len(on_keys),
                          "additional_semantic_designs": sorted(on_keys - off_keys),
                          "selected_design_changed": not same_selected,
                          "diagnostic": diagnostic, "full_consequence": "S0_PENDING"})
    save(destination / "candidates.json", {"schema": VERSION + ":four-candidates", "cells": candidates})
    source_files = [ROOT / name for name in ("semantic_search.py", "check_direct.py", "freeze_prefixes.py", "PREREGISTRATION.md")]
    manifest = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    receipt = {"at": datetime.now(timezone.utc).isoformat(), "schema": VERSION + ":freeze",
               "source_manifest": manifest, "paired_prefixes": summaries,
               "software_receipt": str(ROOT / "direct-checks.json"),
               "software_first_run": {"cases": 10, "PASS": 7, "FAIL": 3, "rerun": False},
               "static_cost": static, "cheap_scientific_calls": static["geometry_cache_misses"],
               "full_consumers": 0, "provider_requests": 0,
               "wall_s": time.monotonic() - start,
               "available_bytes_after": os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize,
               "B_retained_bytes": sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file()),
               "historical_exposure": "Seen prefixes; old public success successors seen in earlier work, not read or embedded by this implementation. New A tasks/results not read.",
               "claim": "Frozen actual generation/selection. Full consequences and scientific benefit UNKNOWN until S0 original consumers."}
    save(destination / "freeze-receipt.json", receipt)
    print(json.dumps({"prefixes": summaries, "static_cost": static, "source_manifest": manifest,
                      "wall_s": receipt["wall_s"], "available_bytes_after": receipt["available_bytes_after"]}, ensure_ascii=False))


if __name__ == "__main__":
    freeze()
