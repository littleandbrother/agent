"""Normal v2 output capture, no extra tests or full execution."""
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import json
import time

from semantic_search import build_state, digest
from semantic_closure import ClosureFactory, VERSION
from bfworld.agentlab.pqe20261024debt import task as door_task
from bfworld.agentlab.pqe20261024debt.facts import design_facts

ROOT = Path(__file__).resolve().parent


def freeze():
    out = ROOT / "closure-v2"
    out.mkdir(exist_ok=False)
    start = time.monotonic()
    costs = {"new_B_cheap_cap": 10, "geometry_misses": 0, "geometry_cache_hits": 0,
             "structural_validator_calls": 0, "actual_design_facts_calls": 0,
             "fact_and_validation_wall_s": 0., "full_consumers": 0, "provider_calls": 0,
             "new_software_tests": 0}
    cells, reports = [], []
    index = json.loads((ROOT.parent / "shared/prefixes/index.json").read_text())
    old = json.loads((ROOT / "frozen-prefixes/candidates.json").read_text())["cells"]

    def measure(fn, design, kind):
        before = set(door_task._STATIC_GEOMETRY_CACHE)
        costs[kind] += 1
        t = time.monotonic()
        try:
            return fn(design)
        finally:
            added = len(set(door_task._STATIC_GEOMETRY_CACHE) - before)
            costs["geometry_misses"] += added
            if not added:
                from bfworld.agentlab.pqe20261022 import door_model
                payload = json.dumps({"mechanism": design["mechanism"], "defaults": door_model.DEFAULT_MECHANISM,
                                      "domain": door_model.DOMAIN}, sort_keys=True, separators=(",", ":"), allow_nan=False)
                key = (door_model.source_step, getattr(door_model.source_step, "__code__", None), payload)
                costs["geometry_cache_hits"] += int(key in before)
            costs["fact_and_validation_wall_s"] += time.monotonic() - t
            if costs["geometry_misses"] > 10:
                raise RuntimeError("B_REMAINING_CHEAP_CAP_EXCEEDED")

    for row, seed in zip(index["prefixes"], (314159, 271828)):
        p = Path(row["path"])
        if hashlib.sha256(p.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("PREFIX_HASH_CHANGED")
        with gzip.open(p, "rt") as stream:
            v = json.load(stream)
        contract, result = v["public_contract"], v["family_result"]
        def validate(d):
            for task in contract["tasks"]:
                measure(lambda actual, task=task: door_task.validate_design(task, actual), d, "structural_validator_calls")
        def facts_fn(d):
            return measure(lambda actual: design_facts(actual, contract["tasks"][0]), d, "actual_design_facts_calls")
        state = build_state(result, v["prior_result"], contract)
        f = ClosureFactory(contract, result["design"], validate_fn=validate, design_facts_fn=facts_fn)
        pair = []
        for enabled in (False, True):
            g = f.generate(result["design"], state, seed=seed, round_index=0, relations_enabled=enabled)
            selected = f.select(g, seen_keys=[f.semantic_key(result["design"])], parent_id=v["node_id"])
            label = "on" if enabled else "off"
            cell = {"prefix_id": v["prefix_id"], "switch": label, "seed": seed,
                    "source_prefix": row, "state": state, "generation": g, "selected": selected,
                    "full_consequences": "NOT_READ_NOT_EXECUTED_BY_B"}
            dest = out / (v["prefix_id"] + "-" + label + ".json.gz")
            with dest.open("xb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
                    stream.write(json.dumps(cell, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode())
            previous = next(x for x in old if x["prefix_id"] == v["prefix_id"] and x["switch"] == label)
            cells.append({"prefix_id": v["prefix_id"], "switch": label, "design": selected["design"],
                          "design_patch": selected["design_patch"], "selection": selected["selection"],
                          "same_as_v1_selected_design": selected["design"] == previous["design"],
                          "path": str(dest), "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
            pair.append(cell)
        chains = pair[1]["generation"]["closure_chains"]
        producer_chains = [c for c in chains if c["intent"]["kind"] == "INTRODUCE_PUBLIC_PRODUCER"]
        chains_summary = []
        for chain in producer_chains:
            byid = {n["id"]: n for n in chain["nodes"]}
            trails = []
            for nid in chain["static_closed_node_ids"]:
                n, trail = byid[nid], []
                while n:
                    trail.append({"node_id": n["id"], "design": n["inspection"]["design"],
                                  "transition": n["transition"],
                                  "actual_facts_sha256": n["inspection"]["facts_sha256"],
                                  "unmet": [{"id": o["id"], "kind": o["check"]["kind"],
                                             "source_fact_ids": o["check"]["predicate"].get("from_fact_ids", [])}
                                            for o in n["inspection"]["obligations"] if o["status"] == "UNMET_STATIC_COMPANION"],
                                  "remaining_dynamic_unknowns": [o["check"]["kind"] for o in n["inspection"]["obligations"] if o["status"].startswith("UNKNOWN")],
                                  "full_service": "UNKNOWN"})
                    n = byid.get(n["parent_id"])
                trails.append(list(reversed(trail)))
            chains_summary.append({"intent": chain["intent"], "nodes": len(chain["nodes"]), "closed_trails": trails})
        selected_intents = pair[1]["selected"]["selection"].get("consumed_derivations", [])
        reports.append({"prefix_id": v["prefix_id"],
                        "common_raw_pool_identical_on_off": pair[0]["generation"]["common_raw_proposals"] == pair[1]["generation"]["common_raw_proposals"],
                        "new_pool_sizes": [len(c["generation"]["candidates"]) for c in pair],
                        "on_off_selected_design_changed": pair[0]["selected"]["design"] != pair[1]["selected"]["design"],
                        "selected_intent_kinds": [x["intent"]["kind"] for x in selected_intents],
                        "selected_introduces_component_duty": any(x["introduced_component_duty"] for x in selected_intents),
                        "selected_claims_coverage_satisfied": any(x["coverage_satisfied"] for x in selected_intents),
                        "actual_component_closure_trails": chains_summary,
                        "interpretation": "Actual contract-to-companion generation exists in alternatives; selected simple/charge probes must not be reported as executed component-closure chains."})
    sources = {str(ROOT / n): hashlib.sha256((ROOT / n).read_bytes()).hexdigest()
               for n in ("semantic_search.py", "semantic_closure.py", "freeze_closure.py")}
    receipt = {"at": datetime.now(timezone.utc).isoformat(), "schema": VERSION + ":freeze",
               "source_manifest": sources, "cells": cells, "prefix_reports": reports, "costs": costs,
               "B_total_cheap": 6 + costs["geometry_misses"], "B_total_cheap_cap": 16,
               "B_software_cases_total": 10, "old_software_receipt_preserved": True,
               "wall_s": time.monotonic() - start,
               "source_scope": "New v2 only; original frozen v1 and four cells unchanged. No S0 stage2 consequences or new A tasks/results read.",
               "claim_boundary": "Static source-contract expansion capability and conditional probes only; complete physical service UNKNOWN; actual selected designs compared explicitly to frozen v1."}
    with (out / "freeze-receipt.json").open("x") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"costs": costs, "B_total_cheap": receipt["B_total_cheap"], "sources": sources,
                      "selected": [{k: x[k] for k in ("prefix_id", "switch", "design_patch", "same_as_v1_selected_design")} for x in cells],
                      "producer_chain_counts": [len(x["actual_component_closure_trails"]) for x in reports],
                      "wall_s": receipt["wall_s"]}, ensure_ascii=False))


if __name__ == "__main__":
    freeze()
