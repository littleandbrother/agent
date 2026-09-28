from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bfworld.agent.observation import public_observation
from bfworld.application.rotary import run_rotary_mission
from bfworld.bundle.reader import RunBundleReader
from bfworld.studio.snapshot import studio_snapshot
from bfworld.verification.verifier import verify_bundle
from tests.helpers import MISSION


class AVerticalSliceTests(unittest.TestCase):
    def test_complete_a_world_kernel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_rotary_mission(MISSION, root / "workspace", root / "bundle")
            report = verify_bundle(root / "bundle")
            self.assertEqual(result["bundle_hash"], report["bundle_hash"])
            self.assertTrue(report["baseline_overvoltage_observed"])
            self.assertTrue(report["revision_passed"])
            self.assertTrue(report["fine_validation_passed"])
            self.assertFalse(report["hardware_result"])
            self.assertEqual(report["model_calls"], 0)

    def test_agent_studio_and_verifier_bind_same_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_rotary_mission(MISSION, root / "workspace", root / "bundle")
            reader = RunBundleReader(root / "bundle")
            agent = public_observation(reader)
            studio = studio_snapshot(reader)
            verifier = verify_bundle(root / "bundle")
            self.assertEqual(agent["event_head"], studio["event_head"])
            self.assertEqual(agent["event_head"], verifier["event_head"])
            self.assertEqual(agent["run_id"], studio["run_id"])
            self.assertEqual(agent["run_id"], verifier["run_id"])


if __name__ == "__main__":
    unittest.main()

