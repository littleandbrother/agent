"""BFA-052: short injected apparatus controls and old evidence readback.

Toy queue expressions below qualify program consumption. They are never
supplied as a proposed D for the fixed product task or attributed to BF/Pi.
"""
import copy
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bfworld.agentlab.campaign20261019 import ar, ar_service as world
from campaign_fixtures import archived_ar_reference, published_path, RECORDED_WORKSPACE

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("campaign_ar_service_test", ROOT / "scripts/campaign_ar_service.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


def toy():
    candidate = service.original_candidate()
    candidate["program"]["sample_period_s"] = 5
    task = copy.deepcopy(service.load_contract()["tasks"]["ar-cold"])
    task.update(id="qualification-only", duration_s=180, service_start_s=10,
                required_first_receive_s=10, required_sample_period_s=5, recovery_at_s=80,
                source_segments=[{"start_s": 0, "end_s": 180, "power_w": .02, "illuminance_lux": 0,
                                  "voc_v": 3.2, "mpp_ratio": .75}],
                gateway_windows=[[0, 20], [80, 181]], temperature_segments=[[0, 181, 22.]])
    return task, candidate


class ARServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = ExitStack()
        cls.addClassCleanup(cls.resources.close)
        original_sha = service.sha

        def mounted_sha(path):
            path = Path(path)
            if (path.is_relative_to(RECORDED_WORKSPACE)
                    and not path.is_relative_to(ROOT.parent)):
                path = published_path(path)
            return original_sha(path)

        # Frozen metadata keeps the recorded path; its exact bytes are checked
        # against the published artifact, even when the old home still exists.
        cls.resources.enter_context(patch.object(service, "sha", side_effect=mounted_sha))
        historical = copy.deepcopy(service.load_contract())
        historical["historical_raw"]["path"] = str(
            cls.resources.enter_context(archived_ar_reference()))
        with patch.object(service, "load_contract", return_value=historical):
            cls.historical = service.verify_historical()
        task, cls.candidate = toy()
        cls.task = world.apply_candidate(task, cls.candidate)
        cls.raw = world.simulate_ar(cls.task)

    def test_six_hour_positive_and_all_old_failures_read_without_simulation(self):
        h = self.historical
        self.assertEqual({"verdict": "PASS", "sealed_files": 81, "cases": 17, "new_simulations": 0,
                          "paid_model_requests": 0, "native_calls": 0}, h["old_independent_readback"])
        r = h["phase1_independent_readback"]["ar-light-dark"]
        self.assertEqual((348, 773, "PASS"), (r["sample_count"], r["gates"]["first_fresh_receive"]["first_receive_s"], r["execution_integrity"]))
        self.assertEqual("PASS", r["all_applicable_computational_services"])
        self.assertTrue(Path(h["old_failure_root_preserved"]).is_dir())

    def test_retention_and_honest_gap_do_not_replace_dark_samples_or_clock(self):
        g = self.historical["phase1_independent_readback"]["ar-history-nvm"]["gates"]
        self.assertEqual(["PASS", "PASS", "FAIL", "UNKNOWN", "FAIL", "FAIL"],
                         [g[k]["status"] for k in ("history_retention", "gap_reporting", "dark_new_sampling",
                                                   "absolute_time", "recovery_upload", "temperature_events")])

    def test_120_second_upload_pass_is_separate_from_10_second_freshness(self):
        g = self.historical["phase1_independent_readback"]["ar-upload-dedup"]["gates"]
        self.assertEqual("PASS", g["recovery_upload"]["status"])
        self.assertEqual("PASS", g["deduplication"]["status"])
        self.assertEqual("FAIL", g["fresh_receive_delay"]["status"])
        self.assertEqual([109], g["fresh_receive_delay"]["late_sequences"])

    def test_legal_space_rejects_power_precharge_clock_and_task_changes(self):
        for section, key, value in (("device", "cap_initial_voltage_v", 3.3), ("device", "harvest_efficiency", 1.),
                                    ("device", "clock_persistent", True), ("device", "cap_voltage_max_v", 4.5),
                                    ("program", "sample_period_s", 61), ("device", "capacitance_f", True)):
            bad = copy.deepcopy(self.candidate)
            bad[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): world.validate_candidate(bad)
        bad = copy.deepcopy(self.candidate); bad["required_live_receive_delay_s"] = 30
        with self.assertRaises(ValueError): world.validate_candidate(bad)

    def test_program_has_no_hidden_truth_arbitrary_code_or_unbounded_ast(self):
        for expression in ({"field": "created_s"}, {"field": "future_source"}, {"python": "open('x')"},
                           {"op": "if", "args": [{"const": 1}, {"const": 0}]}, {"const": float("nan")}):
            bad = copy.deepcopy(self.candidate); bad["program"]["rank"] = expression
            with self.subTest(expression=expression), self.assertRaises(ValueError): world.validate_candidate(bad)
        expression = {"field": "seq"}
        for _ in range(9): expression = {"op": "+", "args": [expression, {"const": 0}]}
        bad = copy.deepcopy(self.candidate); bad["program"]["rank"] = expression
        with self.assertRaises(ValueError): world.validate_candidate(bad)

    def test_v2_original_program_preserves_v1_loop_in_short_outage_fixture(self):
        old_task = copy.deepcopy(self.task)
        old_task["model_id"] = ar.MODEL_ID
        old_task.pop("program")
        old = ar.simulate_ar(old_task)
        for key in ("trace", "records", "packets", "receiver", "final_history", "gaps", "evictions", "first_boot_s"):
            with self.subTest(key=key): self.assertEqual(old[key], self.raw[key])
        self.assertEqual(old["activity"], [a for a in self.raw["activity"] if a["action"] != "program-dispatch"])
        self.assertEqual("PASS", service.service_reference(self.task, self.raw)["execution_integrity"])

    def test_participant_expression_and_retry_enter_actual_consumer(self):
        changed = copy.deepcopy(self.candidate)
        changed["program"]["rank"] = {"op": "-", "args": [{"const": 0}, {"field": "seq"}]}
        changed["program"]["retry_s"] = 3
        task = world.apply_candidate(toy()[0], changed)
        raw = world.simulate_ar(task)
        self.assertNotEqual(self.raw["packets"], raw["packets"])
        self.assertEqual("PASS", service.service_reference(task, raw)["execution_integrity"])
        ignored = copy.deepcopy(self.raw)
        ignored["program_sha256"] = world.identity(task["program"])
        self.assertIn("independent program consumption", service.activity_audit(task, ignored)["errors"])

    def test_controller_cannot_access_true_age_after_clock_loss(self):
        rec = {"seq": 17, "kind": 0, "created_s": 100, "time_known": True, "time_interval_s": [100, 100]}
        self.assertEqual({"seq": 17, "kind": 0, "age_known": 0, "age_s": 0.}, world.visible_fields(rec, 9999, None, 20))

    def test_exact_spacing_detects_failure_hidden_by_fixed_bins(self):
        samples = [1, 119, 121, 239]
        self.assertEqual([], service.reference._missed(samples, 0, 240, 60))
        checked = service.coverage(samples, 0, 240, 60)
        self.assertEqual(118, checked["maximum_spacing_s"])
        self.assertEqual([[61, 119], [181, 239]], checked["missing_intervals_s"])

    def test_balanced_but_wrong_energy_debit_and_invalid_crc_are_rejected(self):
        raw = copy.deepcopy(self.raw)
        row = next(r for r in raw["trace"] if r["tx_j"])
        row["tx_j"] -= 1e-5; row["background_j"] += 1e-5
        self.assertEqual("PASS", service.reference.energy_reference(self.task, raw["trace"], "ar")["verdict"])
        self.assertEqual("FAIL", service.activity_audit(self.task, raw)["verdict"])
        raw = copy.deepcopy(self.raw)
        packet = bytearray.fromhex(raw["receiver"][0]["hex"]); packet[3] ^= 1
        raw["receiver"][0]["hex"] = packet.hex()
        self.assertEqual("FAIL", service.service_reference(self.task, raw)["gates"]["independent_receiver"]["status"])

    def test_false_clock_claim_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw["records"][0]["time_known"] = False
        self.assertIn("independent clock basis", service.activity_audit(self.task, raw)["errors"])

    def test_history_payload_corruption_is_not_counted_as_retention(self):
        raw = copy.deepcopy(self.raw)
        raw["final_history"][0]["temperature_c"] += 3
        result = service.service_reference(self.task, raw)
        self.assertEqual("FAIL", result["gates"]["history_retention"]["status"])
        self.assertIn("final durable record content", result["activity_audit"]["errors"])

    def test_no_source_is_failure_and_empty_checks_are_not_promoted(self):
        task = copy.deepcopy(self.task)
        task["source_segments"][0].update(power_w=0, voc_v=0)
        checked = service.service_reference(task, world.simulate_ar(task))
        self.assertEqual("FAIL", checked["gates"]["first_fresh_receive"]["status"])
        self.assertEqual("FAIL", checked["gates"]["dark_new_sampling"]["status"])
        for gate in ("deduplication", "history_retention", "absolute_time", "recovery_upload", "fresh_receive_delay"):
            with self.subTest(gate=gate): self.assertEqual("NOT_APPLICABLE", checked["gates"][gate]["status"])

    def test_old_negative_volatile_stale_and_duplicate_controls_remain_failures(self):
        root = Path(self.historical["raw_root"]) / "cases"
        for name, gate, expected in (("ar-history-volatile", "history_retention", "FAIL"),
                                      ("ar-startup-late", "first_fresh_receive", "FAIL"),
                                      ("ar-stale", "first_fresh_receive", "FAIL"),
                                      ("ar-upload-naive", "deduplication", "FAIL")):
            task, raw = service.load_case(root / name)
            with self.subTest(name=name): self.assertEqual(expected, service.service_reference(task, raw)["gates"][gate]["status"])

    def test_necessary_bounds_are_conservative_and_do_not_choose_device(self):
        bounds = service.energy_bounds()
        self.assertFalse(bounds["bounds_overlap"])
        self.assertAlmostEqual(.1278, bounds["startup"]["optimistic_net_charge_j"])
        self.assertEqual(719, bounds["dark_intervals"][0]["interior_new_samples_lower_bound"])
        self.assertGreater(bounds["dark_intervals"][0]["capacitance_lower_bound_f"], bounds["startup"]["capacitance_upper_bound_f"])
        self.assertNotIn("candidate", bounds)
        # A different task would need its own frozen contract. This tests the inequality,
        # it never relaxes or overwrites the actual service task.
        fixture = service.load_contract()
        fixture["tasks"]["ar-history-nvm"]["source_segments"][1]["end_s"] = 4200
        self.assertTrue(service.energy_bounds(fixture)["bounds_overlap"])

    def test_schema_and_tool_have_one_definition_and_no_accept_action(self):
        definition = service.tool_definition()
        self.assertEqual(["inspect", "check", "submit"], definition["parameters"]["properties"]["action"]["enum"])
        self.assertNotIn("path", definition["parameters"]["properties"])
        try:
            import jsonschema
        except ImportError:
            return
        jsonschema.Draft202012Validator.check_schema(definition["parameters"])
        jsonschema.validate({"action": "check", "candidate": self.candidate}, definition["parameters"])

    def test_saved_new_program_reaches_external_consumer_and_tamper_rejects(self):
        service.RUNTIME.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="unit-consumer-", dir=service.RUNTIME) as tmp:
            root = Path(tmp)
            fixture = service.load_contract()
            fixture["tasks"] = {"qualification-only": toy()[0]}
            with patch.object(service, "load_contract", return_value=fixture):
                bundle = root / "bundle"
                service.execute_candidate(self.candidate, bundle, author={"kind": "Codex-short-unit-fixture", "product_claim": False})
                expected = service.sha(bundle / "seal.json")
                checked = service.independent_check(bundle, root / "external.json", expected_seal_sha256=expected)
                self.assertEqual("PASS", checked["execution_integrity"])
                with self.assertRaises(FileExistsError): service.execute_candidate(self.candidate, bundle, author={})
                with self.assertRaisesRegex(ValueError, "HOST_BOUND_SEAL_DRIFT"):
                    service.independent_check(bundle, expected_seal_sha256="0" * 64)
                input_path = bundle / "cases/qualification-only/input.json"
                original_input = input_path.read_bytes()
                changed_task = json.loads(original_input)
                changed_task["source_segments"][0]["power_w"] *= 2
                input_path.write_text(json.dumps(changed_task))
                (bundle / "seal.json").unlink(); service.seal_bundle(bundle)
                with self.assertRaisesRegex(ValueError, "TASK_OR_FIXED_PARAMETER_DRIFT"):
                    service.independent_check(bundle)
                input_path.write_bytes(original_input)
                (bundle / "seal.json").unlink(); service.seal_bundle(bundle)
                with (bundle / "candidate.json").open("a") as f: f.write(" ")
                with self.assertRaisesRegex(ValueError, "BUNDLE_FILE_DRIFT"): service.independent_check(bundle)

    def test_host_lease_required_and_participant_cannot_self_accept(self):
        service.RUNTIME.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="unit-host-", dir=service.RUNTIME) as tmp:
            handler = service.create_handler(Path(tmp) / "episode")
            self.assertEqual("public-facts", handler({"action": "inspect", "topic": "schema"})["kind"])
            with self.assertRaisesRegex(RuntimeError, "S0_PI_LEASE_REQUIRED"):
                handler({"action": "check", "candidate": self.candidate})
            with self.assertRaisesRegex(ValueError, "TOOL_ARGUMENT_SCHEMA"):
                handler({"action": "accept", "verdict": "PASS"})
            with self.assertRaisesRegex(ValueError, "ISOLATED_OUTPUT_SCOPE"):
                service.output_guard(Path("/tmp/participant-selected-output"))

    def test_storage_exhaustion_stops_before_artifact_creation(self):
        free = type("Usage", (), {"free": 10000000000})()
        with patch.object(service.shutil, "disk_usage", return_value=free):
            with self.assertRaisesRegex(RuntimeError, "STORAGE_HEADROOM_REQUIRED"):
                service.output_guard(service.RUNTIME / "must-not-create")

    def test_rejected_candidates_count_and_submission_does_not_self_accept(self):
        lease = {"episode_id": "UNIT-NOT-A-PI-LEASE", "model": "unit", "backend": "unit", "provider_ledger": "unit",
                 "slot_receipt": "unit", "baseline": service.load_contract()["baseline"],
                 "maximum_requests": 60, "maximum_candidates": 3, "maximum_wall_s": 3600}
        service.RUNTIME.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="unit-caps-", dir=service.RUNTIME) as tmp:
            handler = service.create_handler(Path(tmp) / "episode", lease=lease)
            bad = copy.deepcopy(self.candidate); bad["device"]["cap_initial_voltage_v"] = 3.3
            with self.assertRaises(ValueError): handler({"action": "check", "candidate": bad})
            self.assertEqual(1, len(handler.__self__.candidates))
            with patch.object(service, "execute_candidate", return_value={"artifact": "unit-stub-not-a-model-run"}):
                for value in (.016, .017):
                    c = copy.deepcopy(self.candidate); c["device"]["capacitance_f"] = value
                    handler({"action": "check", "candidate": c})
                c = copy.deepcopy(self.candidate); c["device"]["capacitance_f"] = .018
                with self.assertRaisesRegex(RuntimeError, "CANDIDATE_CAP_EXHAUSTED"):
                    handler({"action": "check", "candidate": c})
            submitted = handler({"action": "submit", "conclusion": "no-go", "rationale": "UNIT protocol control only"})
            self.assertEqual("EXTERNAL_CHECK_REQUIRED", submitted["final_acceptance"])
            with self.assertRaisesRegex(ValueError, "EPISODE_ALREADY_SUBMITTED"):
                handler({"action": "inspect"})

    def test_metadata_cannot_grow_past_retained_output_cap(self):
        with patch.object(service, "tree_bytes", return_value=219999999):
            with self.assertRaisesRegex(RuntimeError, "RETAINED_OUTPUT_CAP"):
                service.dump(service.RUNTIME / "must-not-create.json", {"metadata": "bounded"})


if __name__ == "__main__": unittest.main()
