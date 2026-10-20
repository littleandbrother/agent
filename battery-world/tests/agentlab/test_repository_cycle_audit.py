"""Offline controls for selecting a continuous actual-consumption lineage."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from verify_v2_cycle import continuous_chain


def proof(sid, parent, **overrides):
    return {'system_commit': sid, 'parent': parent,
            'actual_changed_sources': {'main.c': {'before': 'a', 'after': 'b'}},
            'releases': ['review'], 'validation_ids': ['independent'],
            'decisions': ['BF'], **overrides}


class CycleAuditTests(unittest.TestCase):
    def test_old_base_review_fork_does_not_replace_requested_root(self):
        records = [proof('old-review', 'old-root'), proof('first', 'requested'),
                   proof('second', 'first')]
        self.assertEqual(continuous_chain(records, 'requested'), ['first', 'second'])

    def test_declaration_only_second_candidate_is_not_design_revision(self):
        records = [proof('first', 'requested'),
                   proof('declaration', 'first', actual_changed_sources={})]
        self.assertEqual(continuous_chain(records, 'requested'), ['first'])

    def test_wrong_root_and_missing_independent_result_are_rejected(self):
        self.assertEqual(continuous_chain([proof('first', 'old-root')], 'requested'), [])
        self.assertEqual(continuous_chain([proof('first', 'requested', validation_ids=[])], 'requested'), [])

    def test_missing_decision_or_same_version_release_is_rejected(self):
        for field in ('releases', 'decisions'):
            self.assertEqual(continuous_chain([proof('first', 'requested', **{field: []})], 'requested'), [])


if __name__ == '__main__':
    unittest.main()
