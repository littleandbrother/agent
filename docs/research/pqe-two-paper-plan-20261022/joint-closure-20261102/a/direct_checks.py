"""Exactly six preregistered checks of the new public interfaces; no science."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
SRC = ROOT / "workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src"
sys.path.insert(0, str(SRC))
spec = importlib.util.spec_from_file_location("bfa101_a_facts", HERE / "shared_facts.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main():
    started = time.monotonic()
    available = shutil.disk_usage(HERE).free
    if available < 11_000_000_000:
        raise RuntimeError("STORAGE_GATE")
    output = HERE / ("checks-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".json")
    manifest = json.loads((HERE.parents[1] / "relation-synthesis-20261102/a/stage3-host/MANIFEST.json").read_text())
    contracts = {}
    for family in ("LC", "DOOR"):
        tasks = [json.loads(Path(e["task"]["path"]).read_text()) for e in manifest["entries"] if e["family"] == family]
        contracts[family] = {"family_id": "BFA101-"+family, "world_kind": family,
                             "tasks": tasks, "design_domain": tasks[0]["design_domain"],
                             "initial_design": tasks[0]["initial_design"],
                             "initial_problem": tasks[0]["initial_problem"],
                             "component_contract": {"scope": "original public task components/profile"}}
    lc_contract, dc = contracts["LC"], contracts["DOOR"]
    ld, dd = deepcopy(lc_contract["initial_design"]), deepcopy(dc["initial_design"])
    events, cases, full_attempts = [], [], []
    counts = {}

    def meter(kind, key, details=None):
        if kind in ("cheap_numeric", "geometry_miss") and sum(counts.get(k, 0) for k in ("cheap_numeric", "geometry_miss")) >= 24:
            raise RuntimeError("CHEAP_CAP")
        counts[kind] = counts.get(kind, 0)+1
        events.append({"kind": kind, "key": key, "details": details})

    def forbidden(*args, **kwargs):
        full_attempts.append("forbidden full consumer")
        raise AssertionError("FULL_EXECUTION_FORBIDDEN")

    # Guard original full entry points, retaining the actual source primitives.
    from bfworld.agentlab.pqe20261024debt import adapter, consumer
    from bfworld.agentlab.pqe20261023bold import lc_adapter
    mod.lc.simulate = forbidden
    adapter.execute = consumer.execute_design = lc_adapter.execute = forbidden

    def facts_map(value):
        return {x["id"]: x["value"] for x in value["facts"]}

    def run(name, fn):
        before = dict(counts)
        t = time.monotonic()
        row = {"name": name, "before": before}
        try:
            row["evidence"] = fn()
            row["status"] = "PASS"
        except Exception:
            row["status"] = "FAIL"
            row["error"] = traceback.format_exc()
        row.update(after=dict(counts), wall_s=time.monotonic()-t)
        cases.append(row)

    def case1():
        f = mod.candidate_facts(lc_contract, ld, meter=meter)
        m = facts_map(f)
        assert set(f["active_fields"]) == set(ld)
        assert "tx_gate_v" not in f["active_fields"]
        assert m["clock.continuation"]["requires_continuous_power"]
        assert not m["clock.continuation"]["persistent_records_supply_clock"]
        assert m["queue.handoff"]["survives_mcu_reset"]
        assert not m["queue.capacity"]["ack_frees_memory_slot"]
        assert m["receiver.handoff"]["pending_removal_after"] == "paid_ack_commit"
        assert m["darkness.coverage"]["complete_service"] == "UNKNOWN"
        return {"facts": len(f["facts"]), "active_fields": f["active_fields"], "no_door_gate_required": True}

    def case2():
        a = mod.calculate(lc_contract, ld, meter=meter)
        changed = {**ld, "capacitance_f": .024, "area_cm2": 50.}
        b = mod.calculate(lc_contract, changed, meter=meter)
        assert a["memo_key"] != b["memo_key"]
        assert a["design_sha256"] != b["design_sha256"]
        for x, y in zip(a["tasks"], b["tasks"]):
            assert abs(y["storage"]["maximum_to_brownout_j"]-2*x["storage"]["maximum_to_brownout_j"]) < 1e-12
            pa, pb = (v["source"]["declared_scenario_points"][0]["points"][0] for v in (x, y))
            assert pb["bus_power_w"] > pa["bus_power_w"] > 0
            assert not x["source"]["point_samples_are_energy_upper_bound"] if "point_samples_are_energy_upper_bound" in x["source"] else True
        # Independent bounded primitive readback, explicitly metered.
        meter("cheap_numeric", "check2-original-pv-readback", {"reference_bundle": True, "points": 2})
        task = lc_contract["tasks"][0]
        profile = task["public_inputs"]["Profile"]
        p = mod.lc.pv_point({"optical_environment": task["public_inputs"]["optical_environment"]}, profile, changed, 0, changed["startup_v"], True)
        assert p == {k: v for k, v in b["tasks"][0]["source"]["declared_scenario_points"][0]["points"][2].items() if k not in ("storage_v", "powered")}
        q = mod.lc.pv_point({"optical_environment": task["public_inputs"]["optical_environment"]}, profile, changed, 0, profile["pmic"]["maximum_voltage_v"], True)
        assert p["input_v"] != q["input_v"] and p["bus_power_w"] != q["bus_power_w"]
        return {"initial_key": a["memo_key"], "changed_key": b["memo_key"], "pv_loaded_voltage_dependence": True}

    def case3():
        a = mod.calculate(lc_contract, ld, meter=meter)
        for row in a["tasks"]:
            e = row["energy"]
            assert abs(e["background_only_required_j"]-.0864) < 1e-12
            assert abs(e["background_only_capacitance_lower_f"]-.0135) < 1e-12
            assert e["minimum_interior_samples_with_endpoint_coverage"] == 719
            assert e["background_only_margin_j"] < 0
            assert e["cold_start"]["service_certificate"] is None
            assert not row["loads"]["background_divide_by_efficiency"]
        # Three exact startup load guards vs the unmodified original primitive.
        meter("cheap_numeric", "check3-original-phase-readback", {"reference_bundle": True, "points": 3})
        load = lc_contract["tasks"][0]["public_inputs"]["Profile"]["load"]
        for phase in ("sense", "save", "tx"):
            row = next(r for r in a["tasks"][0]["loads"]["phase_points"] if r["phase"] == phase and r["storage_v"] == ld["startup_v"])
            i = mod.lc.input_current(ld["startup_v"], load[phase+"_j"]/load[phase+"_s"], ld["esr_ohm"], load["efficiency"])
            assert row["input_current_a"] == i
            assert row["terminal_v"] == ld["startup_v"]-i*ld["esr_ohm"]
        return {"background_j": .0864, "necessary_c_f": .0135, "minimum_interior_samples": 719, "service": "UNKNOWN"}

    def case4():
        changed = {**ld, "persistent_records": False, "sample_period_s": 30., "nvm_capacity_records": 1}
        f = facts_map(mod.candidate_facts(lc_contract, changed, meter=meter))
        a = mod.calculate(lc_contract, changed, meter=meter)
        assert not f["queue.handoff"]["survives_mcu_reset"]
        assert not f["clock.continuation"]["survives"]
        for row in a["tasks"]:
            assert row["recovery"]["nominal_image_headroom_records"] < 0
            assert not row["recovery"]["ack_reclaims_memory"]
            assert row["clock"]["actual_sync_at"] == "UNKNOWN"
            assert row["clock"]["after_reset_interval"][1] is None
            assert row["full_service"] == row["recovery"]["full_service"] == "UNKNOWN"
        return {"volatile_reset_loses_image": True, "ack_does_not_reclaim_memory": True, "reset_clock": "UNKNOWN"}

    def case5():
        off = mod.candidate_facts(dc, dd, meter=meter)
        changed = {**dd, "holding_component": "lp_fifo", "read_source": "holding_then_contact", "clear_after": "save", "persistent_queue": True}
        on = mod.candidate_facts(dc, changed, meter=meter)
        assert not facts_map(off)["holder.production"]["enabled"]
        assert facts_map(on)["holder.production"]["enabled"]
        assert facts_map(on)["holder.clear"]["trigger"] == "save_commit"
        assert facts_map(on)["queue.handoff"]["survives_mcu_reset"]
        calc = mod.calculate(dc, changed, meter=meter)
        assert counts.get("geometry_miss") == 1
        assert counts.get("geometry_hit", 0) >= 2
        for row in calc["tasks"]:
            assert row["bounds"]["certificate"] is None
            for segment in row["source"]["declared_midpoint_source_points"]:
                for point in segment["points"]:
                    assert abs(point["bus_power_w"]-point["storage_v"]*point["current_a"]) < 1e-15
            assert row["full_service"] == "UNKNOWN"
        return {"holder_off_retained": True, "holder_on_shared_loads": len(on["loads"]), "geometry_misses": counts["geometry_miss"]}

    def case6():
        a = mod.calculate(lc_contract, ld, meter=meter)
        b = mod.calculate(lc_contract, ld, public_result={"hidden_truth": "sentinel", "facts": {"observer_epoch": "secret"}}, meter=meter)
        assert b["memo"] == "HIT" and a["memo_key"] == b["memo_key"]
        assert a["tasks"] == b["tasks"] and "secret" not in json.dumps(b)
        assert b["public_result_sha256"] is not None
        assert mod.identity(lc_contract) == b["contract_sha256"]
        assert mod.source_identity() == b["source_sha256"]
        n = len(events)
        try:
            mod.calculate(lc_contract, {**ld, "area_cm2": 1.}, meter=meter)
            raise AssertionError("invalid domain accepted")
        except ValueError:
            pass
        assert not any(e["kind"] in ("cheap_numeric", "geometry_miss") for e in events[n:])
        assert mod.calculate(lc_contract, ld, "future_service_oracle", meter=meter)["status"] == "UNKNOWN"
        rejected = []
        class CapStop(Exception):
            pass
        def no_budget(kind, key, details=None):
            if kind == "cheap_numeric":
                rejected.append(key)
                raise CapStop()
        before = len(mod._MEMO)
        try:
            mod.calculate(lc_contract, {**ld, "capacitance_f": .023}, meter=no_budget)
            raise AssertionError("meter ignored")
        except CapStop:
            pass
        assert rejected and len(mod._MEMO) == before
        assert not full_attempts
        return {"memo_binding": True, "invalid_domain_precharge_rejected": True,
                "budget_callback_prevents_computation": True, "hidden_fields_not_projected": True,
                "full_attempts": len(full_attempts)}

    for name, fn in (("1 LC facts", case1), ("2 active C and PV", case2),
                     ("3 necessary bounds and load guards", case3), ("4 clock queue recovery", case4),
                     ("5 DOOR common component facts", case5), ("6 binding metering and noninterference", case6)):
        run(name, fn)
    receipt = {"schema": "BFA101-A-six-direct-checks-v1", "at": datetime.now(timezone.utc).isoformat(),
               "status": "PASS" if all(r["status"] == "PASS" for r in cases) else "FAIL",
               "cases": cases, "software_cases": len(cases), "event_counts": counts, "events": events,
               "cheap_total": sum(counts.get(k, 0) for k in ("cheap_numeric", "geometry_miss")),
               "full": 0, "model": 0, "full_attempts": full_attempts,
               "source_sha256": mod.source_identity(), "wall_s": time.monotonic()-started,
               "available_before_bytes": available, "available_after_bytes": shutil.disk_usage(HERE).free,
               "peak_estimate_bytes": 20_000_000, "retained_cap_bytes": 5_000_000}
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"path": str(output), **{k: receipt[k] for k in ("status", "software_cases", "event_counts", "cheap_total", "full", "model", "wall_s")}}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
