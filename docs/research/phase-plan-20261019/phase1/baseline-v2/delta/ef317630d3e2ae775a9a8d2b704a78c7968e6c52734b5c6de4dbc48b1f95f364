"""BFA-045: causally distinct controls and independent evidence readback."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

from bfworld.agentlab.campaign20261019.ar import simulate_ar
from bfworld.agentlab.campaign20261019.b import simulate_b

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("campaign_reference", ROOT / "scripts/campaign_reference.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


class CampaignReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads(reference.CONFIG.read_text())
        cls.cases = {}
        for family in ("ar", "b"):
            for condition in cls.protocol[f"{family}_cases"]:
                task = reference.merge(cls.protocol[f"{family}_base"], condition["patch"])
                raw = (simulate_ar if family == "ar" else simulate_b)(task)
                energy = reference.energy_reference(task, raw["trace"], family)
                readback = (reference.reference_ar if family == "ar" else reference.reference_b)(task, raw, energy)
                cls.cases[condition["id"]] = (task, raw, energy, readback, condition)

    def test_independent_energy_and_receiver_all_conditions(self):
        for name, (_, _, energy, readback, _) in self.cases.items():
            with self.subTest(condition=name):
                self.assertEqual("PASS", energy["verdict"])
                self.assertEqual("PASS", readback["verdicts"]["independent_receiver"])

    def test_predeclared_positive_and_negative_outcomes(self):
        for name, (_, _, _, readback, condition) in self.cases.items():
            for gate, expected in condition["expected"].items():
                with self.subTest(condition=name, gate=gate):
                    self.assertEqual(expected, readback["verdicts"][gate])

    def test_lux_is_metadata_not_watts(self):
        task, raw, _, _, _ = self.cases["ar-cold"]
        modified = copy.deepcopy(task)
        modified["source_segments"][0]["illuminance_lux"] = 9999
        changed = simulate_ar(modified)
        self.assertEqual(raw["first_boot_s"], changed["first_boot_s"])
        self.assertEqual(raw["records"], changed["records"])
        self.assertEqual(raw["trace"][-1]["stored_j"], changed["trace"][-1]["stored_j"])

    def test_same_total_energy_different_transient_outcome(self):
        normal, failure = self.cases["b-pulse-fast"], self.cases["b-esr-fail"]
        self.assertEqual(normal[2]["source_integral_j"], failure[2]["source_integral_j"])
        self.assertEqual("PASS", normal[3]["verdicts"]["event_receive"])
        self.assertEqual("FAIL", failure[3]["verdicts"]["event_receive"])
        self.assertGreater(failure[3]["transient_failed_steps"], 0)

    def test_volatile_event_was_observed_then_lost_at_reset(self):
        latched, volatile = self.cases["b-latched-reset"], self.cases["b-volatile-reset"]
        self.assertEqual(latched[2]["source_integral_j"], volatile[2]["source_integral_j"])
        self.assertTrue(volatile[3]["captured_before_reset"])
        self.assertEqual("PASS", latched[3]["verdicts"]["event_preserved_after_reset"])
        self.assertEqual("FAIL", volatile[3]["verdicts"]["event_preserved_after_reset"])

    def test_history_retention_does_not_imply_new_sampling(self):
        gates = self.cases["ar-history-nvm"][3]["verdicts"]
        self.assertEqual("PASS", gates["history_retention"])
        self.assertEqual("FAIL", gates["continuous_new_sampling"])
        self.assertEqual("PASS", gates["gap_reporting"])
        self.assertEqual("UNKNOWN", gates["absolute_time"])

    def test_actual_lost_ack_creates_duplicate_arrivals(self):
        r = self.cases["ar-upload-dedup"][3]
        self.assertGreaterEqual(r["duplicate_arrivals"], 2)
        self.assertEqual(0, r["duplicate_accepts"])
        self.assertGreater(self.cases["ar-upload-naive"][3]["duplicate_accepts"], 0)

    def test_energy_trace_tamper_is_rejected(self):
        task, raw, _, _, _ = self.cases["b-pulse-fast"]
        bad = copy.deepcopy(raw["trace"])
        bad[50]["stored_j"] += 1e-5
        self.assertEqual("FAIL", reference.energy_reference(task, bad, "b")["verdict"])
        bad = copy.deepcopy(raw["trace"])
        bad[50]["source_j"] += 1e-5
        self.assertEqual("FAIL", reference.energy_reference(task, bad, "b")["verdict"])

    def test_corrupt_crc_and_stale_sample_are_rejected(self):
        raw = bytearray.fromhex(self.cases["b-pulse-fast"][1]["packets"][0]["hex"])
        raw[4] ^= 1
        self.assertIsNone(reference.decode(raw.hex(), "b"))
        self.assertEqual("FAIL", self.cases["ar-stale"][3]["verdicts"]["freshness"])
        self.assertIsNone(self.cases["ar-stale"][3]["first_receive_s"])

    def test_correct_crc_does_not_hide_payload_record_mismatch(self):
        import binascii
        task, raw, energy, _, _ = self.cases["ar-cold"]
        altered = copy.deepcopy(raw)
        body = bytearray.fromhex(altered["receiver"][0]["hex"])
        body[17] ^= 4
        body[-2:] = binascii.crc_hqx(body[:-2], 0xFFFF).to_bytes(2, "big")
        altered["receiver"][0]["hex"] = body.hex()
        self.assertEqual("FAIL", reference.reference_ar(task, altered, energy)["verdicts"]["independent_receiver"])

    def test_time_resolution_refinement(self):
        for name, simulate, family, tolerance in [("ar-cold", simulate_ar, "ar", 1.1), ("b-pulse-fast", simulate_b, "b", .0003)]:
            task, _, _, old, _ = self.cases[name]
            finer = copy.deepcopy(task)
            finer["dt_s"] /= 2
            raw = simulate(finer)
            energy = reference.energy_reference(finer, raw["trace"], family)
            new = (reference.reference_ar if family == "ar" else reference.reference_b)(finer, raw, energy)
            self.assertEqual("PASS", energy["verdict"])
            self.assertLess(abs(old["first_receive_s"] - new["first_receive_s"]), tolerance)

    def test_aem10941_invalid_threshold_is_not_silently_extrapolated(self):
        task = copy.deepcopy(self.cases["ar-cold"][0])
        task["device"]["off_v"] = 2.1
        with self.assertRaisesRegex(ValueError, "threshold domain"):
            simulate_ar(task)


if __name__ == "__main__":
    unittest.main()
