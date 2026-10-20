"""Mechanical public-response checks; no BF simulation or provider calls."""
import copy
import unittest

from bfworld.agentlab.campaign20261019.phase1 import digest, encoded
from bfworld.agentlab.campaign20261019.phase4 import public_projection


class ProjectionTests(unittest.TestCase):
    def test_long_sequences_bind_unexposed_middle_and_do_not_mutate_raw(self):
        raw = {"packets": [{"time_s": n, "hex": "00" * 32} for n in range(20000)],
               "energy": {"balance_j": 0, "status": "OBSERVED"}}
        original = copy.deepcopy(raw)
        view = public_projection(raw)
        self.assertEqual(raw, original)
        self.assertEqual(view["packets"]["full_count"], 20000)
        self.assertEqual(view["packets"]["full_value_sha256"], digest(raw["packets"]))
        changed = copy.deepcopy(raw)
        changed["packets"][10000]["hex"] = "ff"
        self.assertNotEqual(public_projection(changed)["packets"]["full_value_sha256"], view["packets"]["full_value_sha256"])
        self.assertLess(len(encoded(view)), 96000)
        self.assertNotIn("complete_service", view)

    def test_short_arrays_and_nested_arrays_follow_one_rule(self):
        raw = {"samples": [0] * 12, "nested": [{"rows": list(range(13))}]}
        view = public_projection(raw)
        self.assertEqual(view["samples"], raw["samples"])
        self.assertEqual(view["nested"][0]["rows"]["full_count"], 13)
        self.assertEqual(view, public_projection(copy.deepcopy(raw)))


if __name__ == "__main__":
    unittest.main()
