"""Synthetic component/program events only. Never invoke a scientific solver."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
SRC = ROOT / "workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src"
sys.path.insert(0, str(SRC))
from bfworld.agentlab.pqe20261024debt import consumer, holding, task, facts, bounds


def capture(h, direction):
    h.prepare(2.5, direction)
    h.advance(holding.PROFILE["debounce_s"], 2.5)
    h.prepare(2.5, direction)
    h.advance(holding.PROFILE["capture_s"], 2.5)


def program(placement="save", persistent=True, holder=None):
    h = holder or holding.EventHolding()
    if not h.records:
        capture(h, 1)
    d = {**deepcopy(task.DEFAULT_DESIGN), "holding_component": "lp_fifo",
         "read_source": "holding_then_contact", "clear_after": placement,
         "persistent_queue": persistent}
    p = consumer.HoldingDoorProgram(d, task.COMPONENTS, h)
    p.begin_step(2.5, 1)
    p.advance(task.COMPONENTS["boot_s"], 2.5)
    return p, h


def read(p):
    p.begin_step(2.5, 1)
    assert p.mode == "HREAD"
    p.advance(holding.PROFILE["read_s"], 2.5)


def reboot(p):
    p.reset("SYNTHETIC_MCU_ONLY")
    p.begin_step(2.5, 1)
    p.advance(task.COMPONENTS["boot_s"], 2.5)


class LogicChecks(unittest.TestCase):
    def test_no_capture_without_voltage(self):
        h = holding.EventHolding()
        h.prepare(.8, 1); h.advance(.2, .8)
        self.assertEqual(h.records, [])
        self.assertEqual(h.current_a, 0)

    def test_capture_is_timed_and_loaded(self):
        h = holding.EventHolding()
        h.prepare(2.5, 1); h.advance(.06, 2.5); h.prepare(2.5, 1)
        self.assertGreater(h.current_a, holding.PROFILE["monitor_a"])
        h.advance(.001, 2.5); self.assertEqual(h.records, [])
        h.advance(.001, 2.5); self.assertEqual(len(h.records), 1)

    def test_capture_interruption_discards(self):
        h = holding.EventHolding()
        h.prepare(2.5, 1); h.advance(.06, 2.5); h.prepare(2.5, 1)
        h.advance(.001, .9)
        self.assertEqual(h.records, [])
        self.assertFalse(h.powered)

    def test_capacity_drop_and_overwrite_are_distinct(self):
        drop = holding.EventHolding(1, "drop_new")
        overwrite = holding.EventHolding(1, "overwrite_oldest")
        for h in (drop, overwrite):
            capture(h, 1); capture(h, 0)
        self.assertEqual(drop.peek()["direction"], 1)
        self.assertEqual(overwrite.peek()["direction"], 0)

    def test_expiry_and_voltage_reset(self):
        h = holding.EventHolding(); capture(h, 1)
        h.advance(60., 2.5); self.assertIsNone(h.peek())
        capture(h, 0); self.assertIsNotNone(h.peek())
        h.prepare(.9, 0); self.assertEqual(h.records, [])

    def test_read_claim_commits_after_paid_duration(self):
        p, h = program()
        p.begin_step(2.5, 1); p.advance(.001, 2.5)
        self.assertIsNone(h.peek()["assigned_seq"])
        self.assertIsNone(p.pending)
        p.advance(.001, 2.5)
        self.assertEqual(h.peek()["assigned_seq"], 1)
        self.assertEqual(p.pending, {"seq": 1, "direction": 1})
        self.assertNotIn("observer_epoch", h.peek())
        self.assertNotIn("captured_at_s", h.peek())

    def test_save_handoff_is_an_independent_valid_state_path(self):
        p, h = program("save"); read(p)
        p.advance(.002, 2.5)
        self.assertEqual(p.mode, "HCLEAR")
        self.assertEqual(p.nvm["queue"], [{"seq": 1, "direction": 1}])
        p.advance(.001, 2.5); self.assertIsNotNone(h.peek())
        p.advance(.001, 2.5); self.assertIsNone(h.peek())
        reboot(p)
        self.assertEqual(p.queue, [{"seq": 1, "direction": 1}])

    def test_ack_handoff_is_an_independent_valid_state_path(self):
        p, h = program("ack"); read(p); p.advance(.002, 2.5)
        self.assertIsNotNone(h.peek())
        p.begin_step(2.5, 1); self.assertEqual(p.mode, "TX")
        p.advance(.006, 2.5, True); self.assertEqual(p.mode, "ACK")
        p.advance(.002, 2.5); self.assertEqual(p.mode, "HCLEAR")
        self.assertEqual(p.nvm["queue"], [])
        p.advance(.002, 2.5); self.assertIsNone(h.peek())

    def test_early_clear_has_a_real_loss_window(self):
        p, h = program("early"); read(p)
        self.assertEqual(p.mode, "HCLEAR")
        p.advance(.002, 2.5)
        self.assertEqual(p.mode, "SAVE")
        self.assertIsNone(h.peek())
        reboot(p)
        self.assertEqual(p.nvm["seq"], 0)
        self.assertEqual(p.nvm["queue"], [])

    def test_save_without_persistence_is_not_reset_durable(self):
        p, h = program("save", persistent=False); read(p)
        p.advance(.002, 2.5); p.advance(.002, 2.5)
        self.assertIsNone(h.peek())
        self.assertEqual(len(p.queue), 1)
        reboot(p)
        self.assertEqual(p.queue, [])
        self.assertEqual(p.ram["seq"], 0)

    def test_record_payload_is_not_read_before_paid_read(self):
        p, h = program("save")
        with patch.object(h, "peek", side_effect=AssertionError("OBSERVER_PAYLOAD_NOT_DEVICE_STATUS")):
            p.begin_step(2.5, 1)
            self.assertEqual(p.mode, "HREAD")
            self.assertIsNone(p.pending)
            p.advance(.002, 2.5)
            self.assertEqual(p.pending["direction"], 1)

    def test_read_then_reset_before_save_reuses_claim(self):
        p, h = program("save"); read(p)
        reboot(p); read(p); p.advance(.002, 2.5)
        self.assertEqual(p.nvm["seq"], 1)
        self.assertEqual(len(p.nvm["queue"]), 1)

    def test_saved_reentry_does_not_duplicate_import(self):
        p, h = program("save"); read(p); p.advance(.002, 2.5)
        reboot(p); read(p)
        self.assertEqual(p.mode, "HCLEAR")
        p.advance(.002, 2.5)
        self.assertEqual(p.nvm["seq"], 1)
        self.assertEqual(len(p.nvm["queue"]), 1)
        self.assertIsNone(h.peek())

    def test_acked_reentry_can_finish_clear(self):
        p, h = program("ack"); read(p); p.advance(.002, 2.5)
        p.begin_step(2.5, 1); p.advance(.006, 2.5, True); p.advance(.002, 2.5)
        reboot(p); read(p)
        self.assertEqual(p.mode, "HCLEAR")
        p.advance(.002, 2.5)
        self.assertEqual(p.nvm["queue"], [])
        self.assertEqual(p.nvm["seq"], 1)
        self.assertIsNone(h.peek())

    def test_holder_reset_new_record_does_not_reuse_durable_seq(self):
        p, h = program("save"); read(p); p.advance(.002, 2.5); p.advance(.002, 2.5)
        h.prepare(.9, 0)
        capture(h, 1)
        reboot(p); read(p)
        self.assertEqual(p.pending["seq"], 2)
        self.assertEqual(h.peek()["token"], 1)
        self.assertEqual(h.peek()["assigned_seq"], 2)

    def test_never_clear_retains_capacity_without_reimport(self):
        h = holding.EventHolding(1, "drop_new")
        p, h = program("never", holder=h); read(p); p.advance(.002, 2.5)
        capture(h, 0)
        self.assertEqual(h.peek()["direction"], 1)
        reboot(p); read(p)
        self.assertEqual(p.mode, "IDLE")
        self.assertEqual(p.nvm["seq"], 1)
        self.assertEqual(len(h.records), 1)

    def test_busy_holder_blocks_direct_capture_race(self):
        h = holding.EventHolding(); h.prepare(2.5, 1)
        p, _ = program("save", holder=h)
        # program() populated holder; use a fresh uncommitted monitor state.
        fresh = holding.EventHolding(); fresh.prepare(2.5, 1)
        p.holder = fresh
        p.begin_step(2.5, 1)
        self.assertEqual(p.mode, "IDLE")
        self.assertIsNone(p.pending)

    def test_off_route_is_exact_original_function_dispatch(self):
        t = task.make_task_family()[0]
        payload = {"program_version": "fixture-original", "packets": [{"hex": "fixture"}],
                   "activity": [], "records": [], "energy": {"load_j": 123.}, "result_sha256": "fixture"}
        calls = []
        def original_fixture(t0, d0, **kwargs):
            calls.append((t0, d0, kwargs))
            return deepcopy(payload)
        with patch.object(consumer.bold, "execute_design", original_fixture):
            r = consumer.execute_design(t, t["initial_design"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], task.base_design(t["initial_design"]))
        self.assertEqual(r["energy"], payload["energy"])
        self.assertEqual(r["packets"], payload["packets"])
        self.assertEqual(r["holding_route"], "OFF_EXACT_ORIGINAL_FUNCTION")

    def test_contract_and_counterfactual_facts_are_not_service_answers(self):
        d = deepcopy(task.DEFAULT_DESIGN)
        d.update(holding_component="lp_fifo", read_source="holding_then_contact", persistent_queue=True)
        for placement in ("save", "ack"):
            d["clear_after"] = placement
            f = facts.design_facts(d)
            by_id = {x["id"]: x for x in f["facts"]}
            self.assertTrue(by_id["queue.handoff"]["value"]["survives_mcu_reset"])
            self.assertTrue(by_id["receiver.handoff"]["value"]["survives_mcu_reset"])
            self.assertIsNone(by_id["dynamic.coverage"]["value"]["complete_service"])
            self.assertEqual(by_id["holder.clear"]["value"]["placement"], placement)
        self.assertEqual(set(facts.describe_contract()["operations"]), {"capture", "read", "save", "tx", "ack", "clear"})
        self.assertIsNone(bounds.necessary_bounds(d)["certificate"])

    def test_frozen_family_has_three_new_distinct_static_stimuli(self):
        family = task.make_task_family()
        self.assertEqual([t["condition_id"] for t in family], ["short-cold", "reset-link", "simple-control"])
        self.assertEqual(len({consumer.identity(t["motion"]) for t in family}), 3)
        for t in family:
            self.assertEqual(t["initial"]["capacitor_v"], 0)
            self.assertEqual(t["duration_s"], 86400)
            self.assertEqual(t["service"], task.SERVICE)
            self.assertFalse(t["initial_design"]["persistent_queue"])
            self.assertEqual(t["initial_design"]["holding_component"], "off")
            for seg in t["motion"]:
                self.assertLessEqual(abs(seg["end_deg"]-seg["start_deg"])/(seg["end_s"]-seg["start_s"]), 120.+1e-7)


def run():
    # A hard guard against accidental source solves, full consumer execution or
    # boundary numerics, even if a future logic check accidentally calls one.
    with patch.object(consumer, "_execute_enabled", side_effect=AssertionError("FORBIDDEN_FULL_CONSUMER")), \
         patch.object(consumer, "_midpoint_step", side_effect=AssertionError("FORBIDDEN_NUMERICAL_STEP")), \
         patch.object(consumer.original, "source_step", side_effect=AssertionError("FORBIDDEN_SOURCE_SOLVE")):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(LogicChecks)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result


if __name__ == "__main__":
    result = run()
    receipt = {"schema": "codebt-A-offline-logic-v1", "status": "PASS" if result.wasSuccessful() else "FAIL",
        "logic_checks": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "new_full_scientific_inputs": 0, "source_numeric_steps": 0, "provider_requests": 0,
        "method": "Synthetic holder/program events, static contract and off-route fixture; full/source solvers guarded.",
        "engineering_effect": "UNKNOWN", "energy_closure_in_full_consumer": "UNKNOWN"}
    Path(__file__).with_name("LOGIC-RESULTS.json").write_text(json.dumps(receipt, indent=2)+"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
