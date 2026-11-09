"""Exactly ten direct software cases; no consumer or provider calls."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import gzip
import json
import os
import time

from semantic_search import (SemanticFactory, DeterministicController,
                             FreeJointInterface, build_state, digest)

ROOT = Path(__file__).resolve().parent
PREFIX = ROOT.parent / "shared/prefixes"


def load(name):
    with gzip.open(PREFIX / (name + ".json.gz"), "rt") as stream:
        return json.load(stream)


def fixture(design=None, verdict="FAIL"):
    design = deepcopy(design or {"x": .2, "y": .4, "z": .6})
    rows = [{"condition_id": "fixture", "design": design, "execution_status": "COMPLETE",
             "model_valid": True, "facts": {}, "public_check": {"verdict": verdict, "received_count": 0}}]
    return {"design": design, "results": rows}


def run():
    destination = ROOT / "direct-checks.json"
    if destination.exists():
        raise RuntimeError("APPEND_ONLY_CHECK_RECEIPT_ALREADY_EXISTS")
    start = time.monotonic()
    identity, saved = load("identity-progress"), load("saved-undelivered")
    states = {}
    outcomes = []

    def case(name, fn):
        at = time.monotonic()
        try:
            details = fn()
            outcomes.append({"name": name, "status": "PASS", "details": details,
                             "wall_s": time.monotonic() - at})
        except Exception as exc:
            outcomes.append({"name": name, "status": "FAIL", "error": type(exc).__name__ + ": " + str(exc),
                             "wall_s": time.monotonic() - at})

    def identity_progress():
        s = build_state(identity["family_result"], identity["prior_result"], identity["public_contract"])
        p = build_state(identity["prior_result"], public_contract=identity["public_contract"])
        # Raw operation occurrences can decrease when repeated identities vanish;
        # the old controller's distinct-stage signature was equal, not every raw count.
        assert all(s["stage_counts"][k] <= p["stage_counts"][k] for k in s["stage_counts"])
        assert any(x["kind"] == "prior_conflict_no_longer_observed" for x in s["progress"])
        assert all(not x.get("global_repair_proven", False) for x in s["progress"])
        assert any(x["kind"] == "complete_service_coverage" for x in s["pending_service"])
        states["identity"] = s
        return {"counts": s["stage_counts"], "progress": s["progress"]}

    def saved_pending():
        s = build_state(saved["family_result"], saved["prior_result"], saved["public_contract"])
        assert s["stage_counts"]["save"] == 18 and s["stage_counts"]["tx"] == 0
        pending = [x for x in s["pending_service"] if x["kind"] == "saved_to_wire"]
        assert len(pending) == 3 and all(x["cause_status"] == "UNKNOWN" for x in pending)
        assert all(not x["absence_is_physical_failure"] for x in pending)
        states["saved"] = s
        return {"counts": s["stage_counts"], "pending_ids": [x["id"] for x in pending]}

    def absence_domain_private():
        f = fixture()
        f["results"][0]["facts"] = {"activity": [{"action": "brownout", "observer_epoch": 999}], "hidden_truth": [1]}
        s = build_state(f)
        assert not s["refuted_relations"]
        assert s["pending_service"][0]["cause_status"] == "UNKNOWN"
        assert "observer_epoch" not in json.dumps(s) and "999" not in json.dumps(s)
        f["results"][0]["model_valid"] = False
        s = build_state(f)
        assert s["statuses"] == ["UNKNOWN"] and not s["pending_service"]
        return {"invalid_model_status": s["statuses"], "absence_not_refuted": True}

    def inactive_enable():
        c, d = identity["public_contract"], identity["family_result"]["design"]
        f = SemanticFactory(c, d)
        dead = f.normalize({**d, "holding_capacity": 4})
        assert dead["inactive_only"] and not dead["design_patch"]
        active = f.normalize({**d, "holding_component": "lp_fifo", "holding_capacity": 4,
                              "read_source": "holding_then_contact", "clear_after": "save"})
        assert not active["inactive_only"] and active["design"]["holding_capacity"] == 4
        assert len(active["design_patch"]) >= 3
        return {"dead_normalization": dead["normalized_inactive_fields"], "effective_enable_patch": active["design_patch"]}

    def handoff_choices():
        f = SemanticFactory(identity["public_contract"], identity["family_result"]["design"])
        state = build_state(identity["family_result"], identity["prior_result"], identity["public_contract"])
        rules = f._rules(f.initial_design, state)
        handoffs = [r for r in rules if r["rule"].startswith("powered_capture_handoff_")]
        assert {r["patch"]["clear_after"] for r in handoffs} == {"save", "ack"}
        assert next(r for r in handoffs if r["patch"]["clear_after"] == "save")["predicate"]["values"]["persistent_queue"] is True
        assert all(r["side_effects"] and r["expected_observations"] and r["complete_service"] == "UNKNOWN" for r in rules)
        return {"handoff_rules": [r["rule"] for r in handoffs], "ack_only": False}

    def exact_consumption_cut():
        details = []
        for data, label, seed in [(identity, "identity", 314159), (saved, "saved", 271828)]:
            f = SemanticFactory(data["public_contract"], data["family_result"]["design"])
            state = build_state(data["family_result"], data["prior_result"], data["public_contract"])
            on = f.generate(f.initial_design, state, seed=seed, round_index=0, relations_enabled=True)
            off = f.generate(f.initial_design, state, seed=seed, round_index=0, relations_enabled=False)
            assert on["common_raw_proposals"] == off["common_raw_proposals"]
            assert on["common_rng_before_sha256"] == off["common_rng_before_sha256"]
            assert on["common_rng_after_sha256"] == off["common_rng_after_sha256"]
            assert on["raw_public_facts_sha256"] == off["raw_public_facts_sha256"]
            assert on["rules_consumed"] and not off["rules_consumed"]
            a, b = f.select(on), f.select(off)
            assert a["design"] != b["design"]
            assert a["selection"]["satisfied_rules"]
            assert any(r["origin"] == "RELATION_DERIVED" and r["consumption"] for r in on["generation_records"])
            details.append({"prefix": label, "on_patch": a["design_patch"], "off_patch": b["design_patch"],
                            "on_satisfied": a["selection"]["satisfied_rules"]})
        return details

    def common_static_validator():
        calls = []
        def validate(d):
            calls.append(digest(d))
            if d["x"] > .5:
                raise ValueError("COMMON_STATIC_FIXTURE")
        d = fixture()["design"]
        c = {"design_domain": {k: {"kind": "number", "min": 0., "max": 1.} for k in d}}
        f = SemanticFactory(c, d, validate_fn=validate)
        s = build_state(fixture(), public_contract=c)
        g = f.generate(d, s, seed=123, round_index=0)
        assert any(r["status"] == "STATIC_REJECTED" for r in g["generation_records"])
        assert all(r["design"]["x"] <= .5 for r in g["candidates"])
        return {"injected_static_calls": len(calls), "rejections": sum(r["status"] == "STATIC_REJECTED" for r in g["generation_records"])}

    def lc_public_schema_only():
        d = {"area_cm2": 10., "capacitance_f": .01, "esr_ohm": 5., "startup_v": 3., "brownout_v": 2.,
             "sample_period_s": 30., "nvm_capacity_records": 10, "persistent_records": False}
        bounds = {"area_cm2": (10., 50.), "capacitance_f": (.001, 1.), "esr_ohm": (.1, 100.),
                  "startup_v": (2.1, 3.3), "brownout_v": (1.8, 2.), "sample_period_s": (1., 60.),
                  "nvm_capacity_records": (1, 100)}
        c = {"world_kind": "LC-PV", "design_domain": {k: {"kind": "integer" if k == "nvm_capacity_records" else "number", "min": lo, "max": hi} for k, (lo, hi) in bounds.items()},
             "tasks": [{"service": {"required_sample_period_s": 60.}}]}
        c["design_domain"]["persistent_records"] = {"kind": "boolean"}
        result = fixture(d)
        result["results"][0]["facts"] = {"activity": [{"action": "save_commit"}, {"action": "capacity_blocked"}],
                                          "program_state": {"clock_synchronized": False}}
        s = build_state(result, public_contract=c)
        f = SemanticFactory(c, d)
        g = f.generate(d, s, seed=7, round_index=0)
        rules = g["rules_consumed"]
        assert {"lc_sample_energy_service_boundary", "lc_capacity_after_observed_block", "lc_retention_and_supply_probe"} <= {r["rule"] for r in rules}
        assert all(not {"holding_component", "read_source", "clear_after"} & set(r["patch"]) for r in rules)
        assert all(set(r["patch"]) <= set(d) for r in rules)
        return {"fixture_only": True, "rule_names": [r["rule"] for r in rules], "consumer_not_run": True}

    def initial_pass_stop():
        result = fixture(verdict="PASS")
        c = {"design_domain": {k: {"kind": "number", "min": 0., "max": 1.} for k in result["design"]}}
        f = SemanticFactory(c, result["design"])
        ctl = DeterministicController("R", f, result, seed=1)
        assert ctl.step() is None and ctl.slots == 0
        assert ctl.stop()["all_condition_PASS"] and ctl.stop()["initial_evaluations_charged_to_slots"] == 0
        return ctl.stop()

    def six_new_archive_free_submit():
        result = fixture()
        c = {"design_domain": {k: {"kind": "number", "min": 0., "max": 1.} for k in result["design"]}}
        f = SemanticFactory(c, result["design"])
        ctl = DeterministicController("D", f, result, seed=42)
        for slot in range(1, 7):
            action = ctl.step()
            assert action and action["slot"] == slot
            ctl.update(fixture(action["design"]))
        assert ctl.slots == 6 and len(ctl.nodes) == 7 and ctl.step() is None
        assert all(not n["state"]["all_pass"] for n in ctl.nodes.values())
        g = FreeJointInterface(f, result, seed=3)
        action = g.submit({"x": .8, "y": .9, "z": .1})
        assert len(action["design_patch"]) == 3 and action["parent_id"] == g.root_id
        g.update(fixture(action["design"]))
        assert g.slots == 1 and len(g.nodes) == 2
        return {"new_slots": ctl.slots, "retained_nodes_including_failed_initial": len(ctl.nodes),
                "G_free_joint_fields": list(action["design_patch"]), "software_fixture_evaluations_only": True}

    for name, fn in [("identity_progress_without_stage_gain", identity_progress),
                     ("saved18_wire0_pending_unknown", saved_pending),
                     ("absence_domain_and_private_boundary", absence_domain_private),
                     ("inactive_fields_and_reasoned_enable", inactive_enable),
                     ("durable_SAVE_and_ACK_handoff_alternatives", handoff_choices),
                     ("exact_relation_consumption_cut_actual_prefixes", exact_consumption_cut),
                     ("shared_injected_static_validator", common_static_validator),
                     ("LC_public_schema_fixture_only", lc_public_schema_only),
                     ("initial_PASS_stops_at_zero_new_slots", initial_pass_stop),
                     ("six_new_slots_failed_archive_free_joint", six_new_archive_free_submit)]:
        case(name, fn)
    receipt = {"at": datetime.now(timezone.utc).isoformat(), "software_cases": len(outcomes),
               "cases": outcomes, "passed": sum(x["status"] == "PASS" for x in outcomes),
               "failed": sum(x["status"] == "FAIL" for x in outcomes),
               "cheap_scientific_calls": 0, "full_consumers": 0, "provider_requests": 0,
               "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE"),
               "wall_s": time.monotonic() - start, "claim": "Software only; no complete-service result."}
    with destination.open("x") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: receipt[k] for k in ("software_cases", "passed", "failed", "wall_s")}))
    print(json.dumps([{k: c[k] for k in ("name", "status", "error") if k in c} for c in outcomes]))
    if receipt["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
