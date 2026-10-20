"""Meaningful protocol, information and evidence-boundary regression controls."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bfworld.agentlab.campaign20261019 import bf_interfaces as bf
from campaign_fixtures import interface_registration


ROOT = Path(__file__).resolve().parents[2]
PROFILE: Path


def synthetic_discovery() -> tuple[dict, dict]:
    """Trusted registry is an explicit test fixture, never live scientific evidence."""
    payload = {"headroom": -14.0}
    proposal = {"actor": "agent", "mode": "construction", "run_id": "synthetic-agent",
                "visible_inputs_sha256": "1" * 64, "bf_relation": "energy-headroom",
                "units": "uJ", "domain": {"capacitance_uf": [4.0, 12.0]},
                "acquisition": "synthetic source", "code_sha256": "2" * 64,
                "budget": {"wall_s": 1, "payload_bytes": 1000, "solver_runs": 1, "model_requests": 1}}
    observation = {"payload": payload, "sha256": bf.sha(bf.canonical(payload)),
                   "units": "uJ", "domain": proposal["domain"],
                   "input_sha256": "7" * 64, "source_sha256": "8" * 64,
                   "code_sha256": proposal["code_sha256"],
                   "costs": {"wall_s": .01, "payload_bytes": len(bf.canonical(payload)),
                             "solver_runs": 0, "model_requests": 0}}
    full_input = {"observation_sha256": observation["sha256"], "candidate_sha256": "3" * 64}
    consumer = {"consumer_id": "synthetic-bf-consumer", "execution_id": "synthetic-execution",
                "code_sha256": "4" * 64, "full_input": full_input,
                "input_sha256": bf.sha(bf.canonical(full_input))}
    submission = {"proposal": proposal, "observation": observation, "qualification_id": "q-synthetic",
                  "consumer": consumer}
    authority = {
        "agent_runs": {"synthetic-agent": {"usage_available": True, "provider": "synthetic",
                                          "model": "synthetic", "proposal_sha256": bf.sha(bf.canonical(proposal)),
                                          "visible_inputs_sha256": proposal["visible_inputs_sha256"]}},
        "qualifications": {"q-synthetic": {"observation_sha256": observation["sha256"], "status": "PASS",
                                           "domain": proposal["domain"], "reference_code_sha256": "5" * 64,
                                           "controls": {x: "PASS" for x in ["uninformative", "tampered", "out_of_domain", "static_rich"]}}},
        "observations": {observation["sha256"]: {"receipt_sha256": bf.sha(bf.canonical(observation))}},
        "consumers": {"synthetic-bf-consumer": {"purpose": "bf-service", "code_sha256": consumer["code_sha256"],
                                               "accepted_relations": [proposal["bf_relation"]], "units": "uJ"}},
        "executions": {"synthetic-execution": {"consumer_id": consumer["consumer_id"], "code_sha256": consumer["code_sha256"],
                                               "input_sha256": consumer["input_sha256"], "observation_sha256": observation["sha256"],
                                               "relation_input_edge": proposal["bf_relation"],
                                               "independent_service_sha256": "6" * 64,
                                               "decision_sha256": "9" * 64,
                                               "service_verdict": "FAIL", "decision_mode": "outcome-blind"}}}
    return submission, authority


class BFInterfaceProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global ROOT, PROFILE
        cls.fixture = tempfile.TemporaryDirectory(prefix="bf-e4-unit-")
        cls.addClassCleanup(cls.fixture.cleanup)
        ROOT, PROFILE = interface_registration(Path(cls.fixture.name), bf)
        # A separate disabled unit-test owner exercises the unchanged gate.
        cls.scratch = tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT / bf.OUTPUT)
        cls.output = Path(cls.scratch.name) / "bundle"
        # A single preparation cannot silently re-run any historical model.
        names = ["evaluate", "analytic_clamp", "numeric_clamp", "event_memory", "numeric_memory",
                 "numeric_additive", "construct_observation", "run_suite"]
        mocks = [patch.object(bf.old, name, side_effect=AssertionError("old solve called")) for name in names]
        for mock in mocks:
            mock.start()
        try:
            cls.report = bf.prepare(ROOT, PROFILE, cls.output)
        finally:
            for mock in reversed(mocks):
                mock.stop()
        cls.rows = bf.read_json(cls.output / "evaluator/index.json")["trials"]

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_readback_uses_existing_solutions_only(self):
        self.assertEqual(self.report["new_solver_runs"], 0)
        self.assertEqual(self.report["legacy"]["packet_files"], 16)
        self.assertEqual(self.report["legacy"]["format_parity_pairs"], 8)
        self.assertEqual(self.report["legacy"]["saved_reference_checks"], 16)

    def test_sealed_factorial_and_equal_formats(self):
        result = bf.verify(self.output)
        self.assertEqual((result["trials"], result["format_pairs"]), (64, 32))
        for row in self.rows:
            self.assertRegex(row["trial_id"], r"^t-[a-f0-9]{24}$")
            manifest = bf.read_json(self.output / row["participant_dir"] / "manifest.json")
            self.assertNotIn("expected_verdict", manifest)
            self.assertEqual(manifest["tools"], bf.TOOLS)

    def test_current_alias_and_static_sufficient_controls(self):
        base = bf.read_json(self.output / "baselines.json")
        self.assertEqual(base["rich_static"]["saved_sufficient_grid_checks"], 28)
        self.assertEqual(base["rich_static"]["saved_additive_checks"], 5)
        self.assertEqual(base["e4_fixed_parser"]["current_unknown"], 16)
        self.assertEqual(base["e4_fixed_parser"]["rich_static_correct"], 16)

    def test_complete_raw_preserves_all_scientific_fields(self):
        for row in self.rows:
            if row["information"] != "complete-raw":
                continue
            original = bf.read_json(ROOT / bf.LEGACY / "observation-inputs" / row["pair"] / row["world"] / "raw.json")
            exported = bf.read_json(self.output / row["participant_dir"] / "raw.json")
            restored = copy.deepcopy(exported)
            restored["pair"]["id"] = original["pair"]["id"]
            restored["world"]["name"] = original["world"]["name"]
            for old_world, new_world in zip(original["pair"]["worlds"], restored["pair"]["worlds"]):
                new_world["name"] = old_world["name"]
            self.assertEqual(restored, original)

    def test_executable_baseline_is_standalone_without_execution(self):
        row = next(r for r in self.rows if r["information"] == "executable-response")
        source = (self.output / row["participant_dir"] / "model.py").read_bytes()
        self.assertIn(b"def predict(raw, patch):", source)
        self.assertNotIn(b"from bfworld", source)
        compile(source, "model.py", "exec")

    def test_participant_input_gate_reads_no_evaluator(self):
        row = self.rows[0]
        trial = self.output / row["participant_dir"]
        original = bf.read_json
        def participant_only(path):
            self.assertTrue(path.resolve().is_relative_to(trial.resolve()))
            return original(path)
        with patch.object(bf, "read_json", side_effect=participant_only):
            self.assertEqual(bf.verify_trial(trial)["status"], "PASS")

    def test_unlisted_file_cannot_enter_participant_mount(self):
        trial = self.output / self.rows[0]["participant_dir"]
        injected = trial / "notes.json"
        try:
            injected.write_text('{"expected": "PASS"}')
            with self.assertRaisesRegex(bf.ProtocolError, "Unlisted"):
                bf.verify_trial(trial)
        finally:
            injected.unlink()

    def test_bf_mechanisms_bound_to_retained_reference_data(self):
        data = bf.read_json(self.output / "mechanisms.json")
        rows = {r["id"]: r for r in data["b_reference"]["saved_outcomes"]}
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows["b-pulse-fast"]["source_j"], rows["b-late-energy"]["source_j"])
        self.assertEqual(rows["b-late-energy"]["verdicts"]["event_receive"], "FAIL")
        self.assertEqual(rows["b-no-energy"]["verdicts"]["transient_voltage"], "PASS")
        self.assertEqual(rows["b-no-energy"]["verdicts"]["event_receive"], "FAIL")
        self.assertIn("no source-response feedback", data["b_reference"]["feedback_scope"])

    def test_fixed_information_rejects_observation(self):
        row = next(r for r in self.rows if r["regime"] == "fixed")
        with self.assertRaisesRegex(bf.ProtocolError, "Fixed-information"):
            bf.replay_observation(self.output, row["trial_id"], "read_spec")

    def test_active_observation_records_new_facts_and_costs(self):
        row = next(r for r in self.rows if r["regime"] == "active" and r["information"] == "current")
        uninformative = bf.replay_observation(self.output, row["trial_id"], "read_current")
        rich = bf.replay_observation(self.output, row["trial_id"], "read_spec")
        self.assertEqual(bf.old.judge_facts(uninformative["facts"]), "UNKNOWN")
        self.assertEqual(bf.old.judge_facts(rich["facts"]), row["expected_verdict"])
        self.assertEqual(rich["facts_sha256"], bf.sha(bf.canonical(rich["facts"])))
        self.assertGreater(rich["costs"]["payload_bytes"], 0)
        self.assertEqual(rich["costs"]["new_solver_runs"], 0)

    def test_cached_query_no_new_solver_and_cache_miss_abstains(self):
        row = next(r for r in self.rows if r["regime"] == "active")
        receipt = bf.replay_observation(self.output, row["trial_id"], "query_model", row["legal_patch"])
        self.assertEqual(receipt["facts"]["verdict"], row["expected_verdict"])
        with self.assertRaisesRegex(bf.ProtocolError, "No saved response"):
            bf.replay_observation(self.output, row["trial_id"], "query_model", {"capacitance_uf": -1})
        with self.assertRaisesRegex(bf.ProtocolError, "Unsupported"):
            bf.replay_observation(self.output, row["trial_id"], "invented")

    def test_target_labels_and_relevance_metadata_rejected(self):
        for payload in [{"x": {"expected": "PASS"}}, {"target_observation": "clamp_v"},
                        {"required_fields": ["clamp_v"]}, {"source": "../evaluator/index.json"}]:
            with self.assertRaises(bf.ProtocolError):
                bf.assert_public(payload)
        bf.assert_public({"clamp_v": 3, "current_verdict": "PASS"})

    def test_tampered_packet_rejected(self):
        row = self.rows[0]
        trial = self.output / row["participant_dir"]
        manifest = bf.read_json(trial / "manifest.json")
        packet = trial / manifest["packet"]["path"]
        saved = packet.read_bytes()
        try:
            packet.write_bytes(saved + b"tampered")
            with self.assertRaisesRegex(bf.ProtocolError, "Sealed artifact changed"):
                bf.verify(self.output)
        finally:
            packet.write_bytes(saved)

    def test_path_escape_and_symlink_rejected(self):
        for name in ["../evaluator/index.json", "/tmp/absolute"]:
            with self.assertRaises(bf.ProtocolError):
                bf.safe_path(self.output, name)
        link = Path(self.scratch.name) / "link"
        link.symlink_to(self.output, target_is_directory=True)
        with self.assertRaisesRegex(bf.ProtocolError, "Symlink"):
            bf.safe_path(Path(self.scratch.name), "link/result.json")

    def test_dispatch_and_insufficient_storage_rejected_before_execution(self):
        for action in ["model", "agent", "native", "paid-trial"]:
            with self.assertRaisesRegex(bf.ProtocolError, "Dispatch blocked"):
                bf.resource_gate(ROOT, PROFILE, action, free_bytes=20_000_000_000)
        with self.assertRaisesRegex(bf.ProtocolError, "Storage gate"):
            bf.resource_gate(ROOT, PROFILE, "prepare", free_bytes=10_899_999_999)

    def test_modified_profile_cannot_enable_capability(self):
        data = bf.read_json(PROFILE)
        data["capabilities"]["agent"] = True
        path = Path(self.scratch.name) / "unregistered-profile.json"
        bf.write_json(path, data)
        with self.assertRaisesRegex(bf.ProtocolError, "profile changed"):
            bf.resource_gate(ROOT, path, "prepare", free_bytes=20_000_000_000)

    def test_e5_missing_external_consumer_authority_stays_not_run(self):
        submission, _ = synthetic_discovery()
        with self.assertRaisesRegex(bf.ProtocolError, "NOT_REGISTERED"):
            bf.validate_discovery(submission)
        contract = bf.e5_contract()
        self.assertEqual(contract["status_by_claim"]["genuine_agent_discovery"], "NOT_RUN")

    def test_e5_synthetic_contract_accepts_failure_without_claiming_gain(self):
        submission, authority = synthetic_discovery()
        result = bf.validate_discovery(submission, authority)
        self.assertEqual(result["status"], "CONTRACT_VALID")
        self.assertEqual(result["service_verdict"], "FAIL")
        self.assertEqual(result["discovery_benefit"], "NOT_ESTABLISHED")

    def test_e5_human_formula_cannot_be_agent_discovery(self):
        submission, authority = synthetic_discovery()
        submission["proposal"]["actor"] = "researcher"
        with self.assertRaisesRegex(bf.ProtocolError, "baseline"):
            bf.validate_discovery(submission, authority)

    def test_e5_unavailable_usage_and_proposal_tamper_rejected(self):
        submission, authority = synthetic_discovery()
        authority["agent_runs"]["synthetic-agent"]["usage_available"] = False
        with self.assertRaisesRegex(bf.ProtocolError, "usage identity"):
            bf.validate_discovery(submission, authority)
        submission, authority = synthetic_discovery()
        submission["proposal"]["bf_relation"] = "different relation"
        with self.assertRaisesRegex(bf.ProtocolError, "provenance"):
            bf.validate_discovery(submission, authority)

    def test_e5_observation_hash_unit_domain_and_budget_controls(self):
        for key, value in [("sha256", "0" * 64), ("units", "J"), ("domain", {"capacitance_uf": [-1, 1000]})]:
            submission, authority = synthetic_discovery()
            submission["observation"][key] = value
            authority["observations"][submission["observation"]["sha256"]] = {
                "receipt_sha256": bf.sha(bf.canonical(submission["observation"]))}
            with self.assertRaises(bf.ProtocolError):
                bf.validate_discovery(submission, authority)
        submission, authority = synthetic_discovery()
        submission["observation"]["costs"]["wall_s"] = 10
        authority["observations"][submission["observation"]["sha256"]]["receipt_sha256"] = bf.sha(bf.canonical(submission["observation"]))
        with self.assertRaisesRegex(bf.ProtocolError, "budget"):
            bf.validate_discovery(submission, authority)

    def test_e5_self_reported_acquisition_costs_are_not_trusted(self):
        submission, authority = synthetic_discovery()
        authority["observations"] = {}
        with self.assertRaisesRegex(bf.ProtocolError, "Trusted acquisition"):
            bf.validate_discovery(submission, authority)

    def test_e5_independent_qualification_and_negative_controls_required(self):
        for field, value in [("reference_code_sha256", "2" * 64), ("controls", {})]:
            submission, authority = synthetic_discovery()
            authority["qualifications"]["q-synthetic"][field] = value
            with self.assertRaisesRegex(bf.ProtocolError, "qualification"):
                bf.validate_discovery(submission, authority)

    def test_e5_echo_self_signed_and_disconnected_consumers_rejected(self):
        for field, value in [("consumers", {}), ("executions", {})]:
            submission, authority = synthetic_discovery()
            authority[field] = value
            with self.assertRaisesRegex(bf.ProtocolError, "Real consumer"):
                bf.validate_discovery(submission, authority)
        submission, authority = synthetic_discovery()
        submission["consumer"]["full_input"]["observation_sha256"] = "0" * 64
        with self.assertRaisesRegex(bf.ProtocolError, "Real consumer"):
            bf.validate_discovery(submission, authority)

    def test_no_existing_output_overwrite(self):
        with self.assertRaises(FileExistsError):
            bf.prepare(ROOT, PROFILE, self.output)


if __name__ == "__main__":
    unittest.main()
