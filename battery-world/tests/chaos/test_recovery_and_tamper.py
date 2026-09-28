from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bfworld.application.rotary import run_rotary_mission
from bfworld.kernel.canonical import file_hash
from bfworld.verification.verifier import VerificationError, verify_bundle
from tests.helpers import MISSION, REPO


PYTHON_SOURCE = REPO / "packages" / "python" / "bfworld" / "src"


class RecoveryAndTamperTests(unittest.TestCase):
    def _env(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(PYTHON_SOURCE)
        return environment

    def test_process_death_resumes_exact_scientific_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "crashed-workspace"
            bundle = root / "recovered-bundle"
            command = [
                sys.executable,
                "-m",
                "bfworld",
                "run",
                "--mission",
                str(MISSION),
                "--workspace",
                str(workspace),
                "--output",
                str(bundle),
                "--crash-after",
                "baseline",
            ]
            crashed = subprocess.run(command, env=self._env(), cwd=REPO, check=False)
            self.assertEqual(crashed.returncode, 91)
            self.assertFalse(bundle.exists())
            resumed = subprocess.run(
                command[:-2] + ["--resume"],
                env=self._env(),
                cwd=REPO,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            recovered = json.loads(resumed.stdout)
            clean = run_rotary_mission(MISSION, root / "clean-workspace", root / "clean-bundle")
            self.assertEqual(recovered["scientific_hash"], clean["scientific_hash"])
            self.assertEqual(
                file_hash(bundle / "events.jsonl"),
                file_hash(root / "clean-bundle" / "events.jsonl"),
            )
            self.assertEqual(verify_bundle(bundle)["status"], "passed")
            manifest = json.loads((bundle / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["recovery_count"], 1)

    def test_bundle_byte_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_rotary_mission(MISSION, root / "workspace", root / "bundle")
            tampered = root / "tampered"
            shutil.copytree(root / "bundle", tampered)
            with (tampered / "world.ir.json").open("ab") as handle:
                handle.write(b" ")
            with self.assertRaises(VerificationError):
                verify_bundle(tampered)

    def test_checkpoint_artifact_drift_blocks_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "crashed-workspace"
            bundle = root / "recovered-bundle"
            command = [
                sys.executable,
                "-m",
                "bfworld",
                "run",
                "--mission",
                str(MISSION),
                "--workspace",
                str(workspace),
                "--output",
                str(bundle),
                "--crash-after",
                "baseline",
            ]
            crashed = subprocess.run(command, env=self._env(), cwd=REPO, check=False)
            self.assertEqual(crashed.returncode, 91)
            live_runs = list((workspace / "live-runs").iterdir())
            self.assertEqual(len(live_runs), 1)
            with (live_runs[0] / "artifacts" / "baseline-rows.json").open("ab") as handle:
                handle.write(b" ")
            resumed = subprocess.run(
                command[:-2] + ["--resume"],
                env=self._env(),
                cwd=REPO,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(resumed.returncode, 0)
            self.assertIn("checkpoint artifact drift", resumed.stderr)
            self.assertFalse(bundle.exists())

    def test_event_hash_chain_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_rotary_mission(MISSION, root / "workspace", root / "bundle")
            tampered = root / "tampered"
            shutil.copytree(root / "bundle", tampered)
            path = tampered / "events.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[2])
            event["payload"]["phase"] = "forged"
            lines[2] = json.dumps(event, sort_keys=True, separators=(",", ":"))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify_bundle(tampered)


if __name__ == "__main__":
    unittest.main()
