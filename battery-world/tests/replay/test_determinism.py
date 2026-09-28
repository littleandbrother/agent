from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bfworld.application.rotary import run_rotary_mission
from bfworld.kernel.canonical import file_hash
from bfworld.verification.verifier import verify_bundle
from tests.helpers import MISSION


class DeterminismTests(unittest.TestCase):
    def test_two_clean_runs_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = run_rotary_mission(MISSION, root / "workspace-a", root / "bundle-a")
            second = run_rotary_mission(MISSION, root / "workspace-b", root / "bundle-b")
            self.assertEqual(first["scientific_hash"], second["scientific_hash"])
            self.assertEqual(first["bundle_hash"], second["bundle_hash"])
            self.assertEqual(
                file_hash(root / "bundle-a" / "bundle-seal.json"),
                file_hash(root / "bundle-b" / "bundle-seal.json"),
            )
            self.assertEqual(verify_bundle(root / "bundle-a"), verify_bundle(root / "bundle-b"))


if __name__ == "__main__":
    unittest.main()

