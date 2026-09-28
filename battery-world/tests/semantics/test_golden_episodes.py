from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bfworld.kernel.canonical import canonical_hash
from bfworld.semantics.golden import (
    A001_BUNDLE_HASH,
    GoldenSemanticError,
    build_golden_episodes,
    validate_episode,
    validate_suite,
    write_golden_suite,
)
from scripts.validate_golden_episodes import validate_directory
from tests.helpers import REPO


FIXTURES = REPO / "fixtures" / "golden-episodes"


def _rehash(value: dict) -> None:
    unsigned = dict(value)
    unsigned.pop("content_hash", None)
    value["content_hash"] = canonical_hash(unsigned)


class GoldenEpisodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.episodes = build_golden_episodes()

    def test_truth_table_and_same_energy_twin(self) -> None:
        report = validate_suite(self.episodes)
        by_id = {item["episode_id"]: item for item in report["episodes"]}
        self.assertTrue(by_id["G0-PASS"]["vms"])
        self.assertFalse(by_id["G1-OVERVOLTAGE"]["pmp"])
        self.assertFalse(by_id["G2-BROWNOUT"]["pmp"])
        self.assertFalse(by_id["G3-WRONG-DIAGNOSIS"]["pmp"])
        self.assertEqual(
            self.episodes[0]["energy_ledger"]["harvester_output_mj"],
            self.episodes[2]["energy_ledger"]["harvester_output_mj"],
        )

    def test_materialization_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            manifest_a = write_golden_suite(Path(first))
            manifest_b = write_golden_suite(Path(second))
            self.assertEqual(manifest_a["content_hash"], manifest_b["content_hash"])
            for entry in manifest_a["files"]:
                self.assertEqual(
                    (Path(first) / entry["path"]).read_bytes(),
                    (Path(second) / entry["path"]).read_bytes(),
                )

    def test_committed_suite_and_a_identity_validate(self) -> None:
        report = validate_directory(FIXTURES, reproduce=True)
        self.assertEqual(report["a001_bundle_hash"], A001_BUNDLE_HASH)
        self.assertTrue(report["byte_identical_rebuild"])

    def test_energy_tamper_is_rejected_after_resealing(self) -> None:
        episode = copy.deepcopy(self.episodes[0])
        episode["energy_ledger"]["sense_mj"] += 0.1
        _rehash(episode)
        with self.assertRaisesRegex(GoldenSemanticError, "energy ledger residual"):
            validate_episode(episode)

    def test_same_time_event_order_tamper_is_rejected_after_resealing(self) -> None:
        episode = copy.deepcopy(self.episodes[0])
        episode["state_transition_table"][1]["priority"] = 5
        _rehash(episode)
        with self.assertRaisesRegex(GoldenSemanticError, "same-time event order"):
            validate_episode(episode)

    def test_visual_provenance_tamper_is_rejected_after_resealing(self) -> None:
        episode = copy.deepcopy(self.episodes[0])
        del episode["expected_ui_projection"]["visual_bindings"][0]["source_channel"]
        _rehash(episode)
        with self.assertRaisesRegex(GoldenSemanticError, "visual binding provenance"):
            validate_episode(episode)

    def test_reality_mutability_tamper_is_rejected_after_resealing(self) -> None:
        episode = copy.deepcopy(self.episodes[0])
        reality = episode["authorities"]["reality_world"]
        reality["mutable_by_agent"] = True
        _rehash(reality)
        _rehash(episode)
        with self.assertRaisesRegex(GoldenSemanticError, "RealityWorld is mutable"):
            validate_episode(episode)

    def test_a_identity_drift_is_rejected_even_with_valid_manifest_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "golden-episodes"
            shutil.copytree(FIXTURES, copied)
            manifest_path = copied / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["a001_bundle_hash"] = "sha256:" + "0" * 64
            _rehash(manifest)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(GoldenSemanticError, "changed A-001 identity"):
                validate_directory(copied, reproduce=False)


if __name__ == "__main__":
    unittest.main()
