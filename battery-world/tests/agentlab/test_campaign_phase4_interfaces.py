"""BFA-062 small adversarial software fixtures; never execute the O0 matrix."""
import binascii
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from bfworld.agentlab.campaign20261019 import phase4_interfaces as o

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/studies/phase4-20261020/interfaces/o0-task.v1.json"


def fixture(horizon=150, windows=((20, 30),), power=9e-5, capacitance=.015, initial_v=3.3):
    """Short/precharged *software* case; no change or solve of original O0."""
    case = json.loads(CONFIG.read_text())
    case["task_id"], case["duration_s"] = "fixture-o-only", horizon
    case["ar_task"]["duration_s"] = horizon
    src = copy.deepcopy(case["ar_task"]["source_segments"][0])
    src.update(start_s=0, end_s=horizon, power_w=power)
    case["ar_task"]["source_segments"] = [src]
    case["ar_task"]["gateway_windows"] = [[0, horizon + 1]]
    case["ar_task"]["temperature_segments"] = [[0, horizon + 1, 22]]
    case["ar_task"]["device"].update(capacitance_f=capacitance, cap_initial_voltage_v=initial_v, boot_delay_s=0)
    case["design_space"]["capacitance_f"] = [capacitance, capacitance]
    waveform, last = [], 0
    for a, b in windows:
        if a > last:
            waveform.append({"start_s": last, "end_s": a, "rms_g": .005})
        waveform.append({"start_s": a, "end_s": b, "rms_g": .08})
        last = b
    if last < horizon:
        waveform.append({"start_s": last, "end_s": horizon, "rms_g": .005})
    case["rms_segments"] = waveform
    return o.bind_case(case)


def seal(response):
    response["response_sha256"] = o.identity({k: v for k, v in response.items() if k != "response_sha256"})
    return response


def replace_wire(response, seq, *, stamp=None, kind=None, state=None):
    record = next(r for r in response["records"] if r["seq"] == seq)
    if stamp is not None:
        record["stamp_s"] = stamp
    if kind is not None:
        record["kind"] = kind
    if state is not None:
        record["state"] = state
    for packet in [*response["packets"], *response["receiver"]]:
        if packet["seq"] == seq:
            raw = bytearray.fromhex(packet["hex"])
            if stamp is not None:
                raw[8:12] = round(stamp * 1000).to_bytes(4, "big", signed=True)
                raw[12:16] = raw[8:12]
            if kind is not None:
                raw[18] = o.KINDS[kind]
            if state is not None:
                raw[16:18] = round(state * 100).to_bytes(2, "big", signed=True)
            raw[-2:] = binascii.crc_hqx(raw[:-2], 65535).to_bytes(2, "big")
            packet["hex"] = raw.hex()
    return seal(response)


class OServiceSmallFixtureTests(unittest.TestCase):
    def run_case(self, case, **overrides):
        self.assertLessEqual(case["duration_s"], 600, "Full O0 execution is forbidden in preparation")
        candidate = o.rich_state(case)["candidate"]
        candidate.update(overrides)
        raw = o.evaluate_candidate(case, candidate)
        return raw, o.evaluate_service(case, raw)

    def test_original_o0_profile_is_preserved_without_execution(self):
        case = json.loads(CONFIG.read_text())
        o.validate_case(case)
        self.assertEqual(21600, case["duration_s"])
        self.assertEqual(0, case["ar_task"]["device"]["cap_initial_voltage_v"])
        self.assertEqual([(4200, 4500), (7800, 8100), (11400, 12000), (16800, 16920)],
                         [(s["start_s"], s["end_s"]) for s in case["rms_segments"] if s["rms_g"] > .05])
        self.assertEqual([200, 0, 50, 200, 0, 50], [s["illuminance_lux"] for s in case["ar_task"]["source_segments"]])
        self.assertEqual(o.fixed_periodic(case)["candidate"]["capacitance_f"], o.rich_state(case)["candidate"]["capacitance_f"])

    def test_small_positive_producer_and_independent_service(self):
        raw, result = self.run_case(fixture())
        self.assertEqual("PASS", result["verdict"], result)
        self.assertEqual([23, 90], [e["time_s"] for e in result["per_event"]])
        self.assertEqual("PASS", result["energy"]["verdict"])
        self.assertEqual("UNKNOWN", result["physical_qualification"])
        self.assertLess(len(raw["energy"]), 10)
        self.assertLess(len(raw["sample_runs"]), 10)

    def test_exact_three_and_sixty_second_edges(self):
        raw, result = self.run_case(fixture(horizon=160, windows=((20, 23), (83, 90))))
        self.assertEqual("PASS", result["verdict"], result)
        self.assertEqual([23, 83, 86, 150], [r["observed_s"] for r in raw["records"] if r["kind"] in ("start", "stop")])

    def test_sub_three_seconds_and_threshold_equality_negative(self):
        case = fixture(windows=((20, 22.999),))
        self.assertEqual([], o.reference_events(case))
        _, result = self.run_case(case)
        self.assertEqual("FAIL", result["verdict"])
        self.assertIn("FALSE_OR_MISTIMED_EVENT", result["reasons"])
        for row in case["rms_segments"]:
            row["rms_g"] = .05
        case = o.bind_case(case)
        self.assertEqual([], o.reference_events(case))
        _, result = self.run_case(case)
        self.assertEqual("PASS", result["verdict"])

    def test_stop_requires_continuous_sixty_not_accumulated_low(self):
        case = fixture(horizon=200, windows=((20, 30), (89, 100)))
        self.assertEqual([23, 160], [e["time_s"] for e in o.reference_events(case)])
        _, result = self.run_case(case)
        self.assertEqual("PASS", result["verdict"], result)

    def test_stop_threshold_equality_is_not_low_confirmation(self):
        case = fixture(horizon=200)
        case["rms_segments"][-1:] = [{"start_s": 30, "end_s": 100, "rms_g": .01},
                                     {"start_s": 100, "end_s": 200, "rms_g": .005}]
        case = o.bind_case(case)
        self.assertEqual([23, 160], [e["time_s"] for e in o.reference_events(case)])
        _, result = self.run_case(case)
        self.assertEqual("PASS", result["verdict"], result)

    def test_all_energy_absent_does_not_capture_or_transmit_dark_event(self):
        raw, result = self.run_case(fixture(power=0, initial_v=0))
        self.assertEqual([], raw["sample_runs"])
        self.assertEqual([], raw["records"])
        self.assertEqual([], raw["packets"])
        self.assertEqual("PASS", result["energy"]["verdict"])
        self.assertEqual("FAIL", result["verdict"])
        self.assertEqual(2, sum(e["verdict"] == "FAIL" for e in result["per_event"]))

    def test_nvm_retention_is_not_new_detection_after_brownout(self):
        case = fixture(horizon=240, windows=((20, 30), (140, 150)), power=0, capacitance=.001)
        raw, result = self.run_case(case, tx_backoff_s=120)
        self.assertTrue(any(a["action"] == "brownout" for a in raw["activity"]))
        self.assertTrue(raw["state"]["pending"])
        self.assertTrue(all(r["observed_s"] < 140 for r in raw["records"]))
        self.assertEqual("FAIL", result["verdict"])
        volatile, _ = self.run_case(case, tx_backoff_s=120, cache="volatile")
        self.assertEqual([], volatile["state"]["pending"])
        self.assertTrue(any(a["action"] == "brownout" and a["pending_lost"] > 0 for a in volatile["activity"]))

    def test_wrong_sequence_and_crc_are_independently_rejected(self):
        raw, _ = self.run_case(fixture())
        bad = copy.deepcopy(raw)
        bad["packets"][0]["seq"] += 99
        self.assertEqual("FAIL", o.evaluate_service(fixture(), seal(bad))["verdict"])
        bad = copy.deepcopy(raw)
        data = bytearray.fromhex(bad["packets"][0]["hex"])
        data[4] ^= 1
        bad["packets"][0]["hex"] = data.hex()
        result = o.evaluate_service(fixture(), seal(bad))
        self.assertEqual("FAIL", result["verdict"])
        self.assertIn("INDEPENDENT_CRC_ID_SEQUENCE_OR_PAYLOAD", result["reasons"])

    def test_correct_crc_does_not_hide_wrong_event_timestamp(self):
        case = fixture()
        raw, _ = self.run_case(case)
        first = raw["records"][0]
        replace_wire(raw, first["seq"], stamp=first["stamp_s"] + 5)
        result = o.evaluate_service(case, raw)
        self.assertEqual("FAIL", result["verdict"])
        self.assertIn("WRONG_EVENT_TIME", result["reasons"])

    def test_late_receive_and_wrong_state_are_failures(self):
        case = fixture()
        raw, _ = self.run_case(case)
        for row in [raw["packets"][0], raw["receiver"][0]]:
            row["time_s"] += 11
            row["receive_s"] += 11
        result = o.evaluate_service(case, seal(raw))
        self.assertIn("LATE_OR_NONCAUSAL_RECEIVE", result["reasons"])
        raw, _ = self.run_case(case)
        replace_wire(raw, raw["records"][0]["seq"], state=0)
        self.assertIn("WRONG_MESSAGE_STATE", o.evaluate_service(case, raw)["reasons"])

    def test_false_keepalive_while_idle_even_with_valid_energy_and_crc(self):
        case = fixture(horizon=200, windows=())
        raw = o.evaluate_candidate(case, o.fixed_periodic(case)["candidate"])
        replace_wire(raw, raw["records"][0]["seq"], kind="keepalive", state=1)
        result = o.evaluate_service(case, raw)
        self.assertEqual("PASS", result["energy"]["verdict"])
        self.assertIn("FALSE_KEEPALIVE_WHILE_IDLE", result["reasons"])

    def test_lost_keepalive_cannot_be_canceled_by_correct_final_stop(self):
        case = fixture(horizon=500, windows=((20, 400),))
        raw, result = self.run_case(case)
        self.assertEqual("PASS", result["verdict"], result)
        seq = next(r["seq"] for r in raw["records"] if r["kind"] == "keepalive")
        for row in [*raw["packets"], *raw["receiver"]]:
            if row["seq"] == seq:
                data = bytearray.fromhex(row["hex"])
                data[-1] ^= 1
                row["hex"] = data.hex()
                if "accepted" in row:
                    row.update(valid=False, accepted=False, ack=False)
        result = o.evaluate_service(case, seal(raw))
        self.assertIn("MISSING_KEEPALIVE", result["reasons"])
        self.assertTrue(any(e["kind"] == "stop" and e["verdict"] == "PASS" for e in result["per_event"]))

    def test_energy_and_changed_source_cannot_reuse_response(self):
        case = fixture()
        raw, _ = self.run_case(case)
        bad = copy.deepcopy(raw)
        bad["energy"][0]["stored_j"] += .001
        self.assertIn("ENERGY_AUDIT", o.evaluate_service(case, seal(bad))["reasons"])
        case["ar_task"]["source_segments"][0]["power_w"] /= 2
        self.assertEqual("UNKNOWN", o.evaluate_service(case, raw)["verdict"])
        case = o.bind_case(case)
        self.assertIn("RESPONSE_SOURCE_OR_DESIGN_BINDING", o.evaluate_service(case, raw)["reasons"])
        changed, _ = self.run_case(case)
        self.assertNotEqual(changed["execution_key"], raw["execution_key"])

    def test_independent_energy_checks_uvlo_and_actual_sample_source(self):
        case = fixture()
        raw, _ = self.run_case(case)
        bad = copy.deepcopy(raw)
        row = next(row for row in bad["energy"] if row["powered"])
        row["minimum_j"] = case["ar_task"]["device"]["capacitance_f"] * 2.3 ** 2 / 2 - .001
        result = o.evaluate_service(case, seal(bad))
        self.assertIn("ENERGY_AUDIT", result["reasons"])
        bad = copy.deepcopy(raw)
        bad["sample_runs"][0]["rms_g"] = .006
        result = o.evaluate_service(case, seal(bad))
        self.assertIn("ENERGY_AUDIT", result["reasons"])
        self.assertIn("sample-source-value", [e[1] for e in result["energy"]["errors"]])

    def test_typed_design_does_not_accept_truth_tables_or_boolean_numbers(self):
        case = fixture()
        candidate = o.rich_state(case)["candidate"]
        candidate["expected_events"] = [{"time_s": 23, "kind": "start"}]
        with self.assertRaisesRegex(ValueError, "NO_EVENT_TABLE"):
            o.evaluate_candidate(case, candidate)
        candidate = o.rich_state(case)["candidate"]
        candidate["sample_period_s"] = True
        with self.assertRaisesRegex(ValueError, "DOMAIN"):
            o.validate_candidate(case, candidate)

    def test_public_sources_complete_hashed_and_no_private_truth_function(self):
        case = fixture()
        raw, _ = self.run_case(case)
        with patch.object(o, "reference_events", side_effect=AssertionError("private evaluator called")):
            view = o.public_view(case, raw)
            o.evaluate_candidate(case, o.rich_state(case)["candidate"])
        self.assertNotIn("expected_events", view)
        self.assertNotIn("complete_service", view)
        source = o.public_view(case, source="photovoltaic_source")
        self.assertEqual(o.identity(source["payload"]), source["sha256"])
        self.assertEqual("W", source["field_units"]["/segments/0/power_w"])
        task = o.public_view(case, source="task")
        self.assertEqual("s", task["field_units"]["/ar_task/gateway_windows/0/0"])
        self.assertEqual("F", task["field_units"]["/design_space/capacitance_f/0"])
        self.assertEqual("degC", task["field_units"]["/ar_task/temperature_segments/0/2"])
        law = o.public_view(case, source="model_law")["payload"]
        self.assertNotIn("def reference_events", law["producer_python"])
        self.assertNotIn("def evaluate_service", law["producer_python"])
        self.assertIn("def validate_candidate", law["producer_dependencies_python"])
        self.assertNotIn("def reference_events", law["producer_dependencies_python"])
        self.assertIn("def simulate_ar", law["ar_python"])
        self.assertLess(len(o.canonical(view)), 100000)

    def test_complete_public_source_json_roundtrip(self):
        case = fixture()
        for item in o.public_view(case)["sources"]:
            source = o.public_view(case, source=item["source_id"])
            self.assertEqual(source, json.loads(json.dumps(source)))


if __name__ == "__main__":
    unittest.main()
