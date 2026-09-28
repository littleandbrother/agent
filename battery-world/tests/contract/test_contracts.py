from __future__ import annotations

import json
import unittest

from bfworld.contracts.validation import load_schema, validate_document
from bfworld.worlds.rotary.model import compile_world_ir
from tests.helpers import MISSION


class ContractTests(unittest.TestCase):
    def test_all_contract_schemas_are_valid(self) -> None:
        for name in (
            "world.schema.json",
            "event.schema.json",
            "run-manifest.schema.json",
            "evidence.schema.json",
            "views.schema.json",
        ):
            schema = load_schema(name)
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_compiled_world_validates_and_is_load_dependent(self) -> None:
        mission = json.loads(MISSION.read_text(encoding="utf-8"))
        world = compile_world_ir(mission)
        validate_document("world.schema.json", world)
        self.assertTrue(world["provider"]["terminal_voltage_dependent"])
        self.assertEqual(world["provider"]["fidelity"], "F1-simplified")
        self.assertFalse(world["provider"]["hardware_result"])


if __name__ == "__main__":
    unittest.main()

