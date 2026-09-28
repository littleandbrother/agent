from __future__ import annotations

import copy
import unittest

from scripts.validate_project_state import (
    ProjectStateError,
    read_repository_state,
    validate_loaded,
)


class ProjectStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = read_repository_state()

    def test_current_repository_state_is_consistent(self) -> None:
        report = validate_loaded(self.state)
        self.assertEqual(report["research_milestones_complete"], len(self.state['roadmap']['current']['research_milestones_completed']))
        self.assertEqual(report["research_milestones_total"], 6)
        self.assertEqual(report["next_feature"], self.state['roadmap']['current']['next_feature'])

    def test_duplicate_milestone_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["roadmap"]["milestones"].append(copy.deepcopy(state["roadmap"]["milestones"][0]))
        with self.assertRaisesRegex(ProjectStateError, "milestone sequence or identity|duplicate milestone"):
            validate_loaded(state)

    def test_false_completion_with_pending_gates_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["roadmap"]["milestones"][0]["status"] = "complete"
        state["roadmap"]["milestones"][0]["exit_gates"][0]["status"] = "pending"
        state["roadmap"]["current"]["research_milestones_completed"] = ["A1"]
        with self.assertRaisesRegex(ProjectStateError, "completed with open gate"):
            validate_loaded(state)

    def test_stale_a_identity_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["roadmap"]["evidence_anchors"]["A-001"]["bundle_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ProjectStateError, "A-001 roadmap evidence identity"):
            validate_loaded(state)

    def test_stale_b0_identity_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["roadmap"]["evidence_anchors"]["B0-000"]["manifest_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ProjectStateError, "B0-000 roadmap evidence identity"):
            validate_loaded(state)

    def test_missing_next_feature_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        del state["features"][state['roadmap']['current']['next_feature']]
        with self.assertRaisesRegex(ProjectStateError, "next feature missing|active feature is missing"):
            validate_loaded(state)


if __name__ == "__main__":
    unittest.main()
