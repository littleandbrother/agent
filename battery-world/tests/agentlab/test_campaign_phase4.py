"""Small adversarial software fixtures for new admission/feedback boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from bfworld.agentlab.campaign20261019.phase1 import digest, encoded, seal
from bfworld.agentlab.campaign20261019.phase4 import (
    ProposalHost, ResponseStore, bounded_allowance, executor_admission,
    require_final_freeze, used_totals,
)


class CoupledFixture:
    """Injected digital fixture, not a BF simulation or benchmark result."""
    def __init__(self):
        self.calls, self.changed = 0, False

    def check_sources(self):
        if self.changed:
            raise ValueError("FIXTURE_SOURCE_CHANGED")

    def normalize(self, world, value):
        if set(value) != {"load"} or type(value["load"]) is not int:
            raise ValueError("FIXTURE_DESIGN")
        return dict(value)

    def key(self, world, value):
        return digest({"world": world, "source": "fixed", "candidate": value})

    def execution_input(self, world, value):
        return {"world": world, "source": "fixed", "candidate": value}

    def simulate(self, world, value):
        self.calls += 1
        return {"delivered": value["load"] < 3, "remaining_energy": 3 - value["load"]}

    def assess(self, world, value, raw):
        return {"complete_service": "PASS" if raw["delivered"] else "FAIL"}

    def raw(self, world, original):
        return json.loads(zlib.decompress(Path(original["raw_path"]).read_bytes()))

    def public_response(self, world, value, raw, result):
        return {"remaining_energy": raw["remaining_energy"]}


class Phase4AdmissionTests(unittest.TestCase):
    def setup_store(self, directory, engine=None, group="a"):
        root = Path(directory)
        initial = root / "initial.json"
        if not initial.exists():
            seal(initial, {})
        return ResponseStore(root / "results", initial, group, engine or CoupledFixture())

    def test_changed_load_requires_new_full_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.setup_store(directory)
            first, _ = store.execute("fixture", {"load": 1})
            second, _ = store.execute("fixture", {"load": 4})
            self.assertNotEqual(first["execution_key"], second["execution_key"])
            self.assertEqual((first["complete_service"], second["complete_service"]), ("PASS", "FAIL"))
            self.assertEqual(store.engine.calls, 2)

    def test_exact_reuse_still_consumes_isolated_logical_exposure(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = CoupledFixture()
            first = self.setup_store(directory, engine)
            first.execute("fixture", {"load": 1})
            second = self.setup_store(directory, engine, "b")
            reused, _ = second.execute("fixture", {"load": 1})
            self.assertTrue(reused["reused"])
            self.assertTrue(reused["job_accounting"]["new_logical_D_exposure"])
            second.execute("fixture", {"load": 4})
            second.execute("fixture", {"load": 4})
            with self.assertRaisesRegex(ValueError, "TWO_DISTINCT"):
                second.execute("fixture", {"load": 2})
            self.assertEqual(engine.calls, 2)

    def test_tampered_cached_response_rejected_without_resimulation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.setup_store(directory)
            value, _ = store.execute("fixture", {"load": 1})
            Path(value["raw_path"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "FROZEN_SOURCE_CHANGED"):
                store.execute("fixture", {"load": 1})
            self.assertEqual(store.engine.calls, 1)

    def test_started_unsealed_execution_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.setup_store(directory)
            key = store.key("fixture", {"load": 1})
            store.index[key] = {"origin": "phase4-new-full-response", "status": "STARTED"}
            with self.assertRaisesRegex(ValueError, "NO_RETRY"):
                store.execute("fixture", {"load": 1})
            self.assertEqual(store.engine.calls, 0)

    def test_source_change_blocks_even_exact_cached_input(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.setup_store(directory)
            store.execute("fixture", {"load": 1})
            store.engine.changed = True
            with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED"):
                store.execute("fixture", {"load": 1})

    def test_final_input_requires_all_selected_methods_and_exact_freeze(self):
        spec = {"stage": "final"}
        chosen = {str(i): "H" + str(i) for i in range(6)}
        with self.assertRaises(ValueError):
            require_final_freeze(spec, None, chosen)
        frozen = {"status": "ALL_SIX_ARMS_FROZEN", "selected_methods_sha256": digest(chosen)}
        require_final_freeze(spec, frozen, chosen)
        with self.assertRaises(ValueError):
            require_final_freeze(spec, frozen, {**chosen, "0": "changed_after_test"})

    def test_formation_and_parent_usage_are_not_free(self):
        row = {"spec": {"arm_id": "L1-G1"}, "accounting": {
            "requests": 118, "settled_charge_upper_bound_usd": 1,
            "unknown_or_missing_usage": []}, "wall_seconds_total": 100}
        spec = {"kind": "D", "stage": "selection", "arm_id": "L1-G1"}
        self.assertEqual(bounded_allowance(spec, [row])[0], 2)
        with self.assertRaisesRegex(ValueError, "EXHAUSTED"):
            bounded_allowance(spec, [row], {"requests": 2, "wall_s": 0, "settled_upper_usd": 0})
        row["accounting"]["unknown_or_missing_usage"] = ["unsettled"]
        with self.assertRaisesRegex(ValueError, "UNRESOLVED_USAGE"):
            used_totals([row])

    def test_pi_requires_a_free_slot_and_recent_status(self):
        slots = {"status": "OBSERVED", "observed_unix": 100, "A": "idle", "B": "running"}
        self.assertEqual(executor_admission(slots, 101), ["S0", "Pi", "B"])
        with self.assertRaises(ValueError):
            executor_admission({**slots, "A": "running"}, 101)
        with self.assertRaises(ValueError):
            executor_admission(slots, 4000)

    def test_proposal_role_cannot_check_design_or_replace_valid_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            host = ProposalHost(directory, "G", {"history": "seen only"}, {}, lambda x: x)
            with self.assertRaisesRegex(ValueError, "NO_DESIGN_ACTION"):
                host({"action": "check", "candidate": {"load": 1}})
            host({"action": "propose", "proposal": {"procedure": "one"}})
            with self.assertRaisesRegex(ValueError, "ONE_VALID"):
                host({"action": "submit", "proposal": {"procedure": "two"}})


if __name__ == "__main__":
    unittest.main()
