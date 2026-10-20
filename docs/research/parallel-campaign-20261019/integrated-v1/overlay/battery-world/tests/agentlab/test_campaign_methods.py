import unittest
from bfworld.agentlab.campaign20261019.common import require_matched, usage_summary
from bfworld.agentlab.campaign20261019.reexecution import qualify, invalidation


class MethodQualification(unittest.TestCase):
    def test_feedback_counterexample_and_exact_cache(self):
        value = qualify()
        self.assertTrue(value['qualification'])
        rows = {r['case']:r for r in value['rows']}
        self.assertTrue(rows['unchanged']['cache_hit'])
        self.assertFalse(rows['less-energy']['fixed_matches_full'])
        self.assertFalse(rows['less-energy']['fixed_trajectory']['admissible'])
        self.assertTrue(rows['less-energy']['full']['admissible'])
        self.assertTrue(all(r['correct_methods_match'] for r in rows.values()))

    def test_typed_restart_and_conservative_boundary(self):
        self.assertEqual(invalidation('H', ['prompt']), 'task-entry')
        self.assertEqual(invalidation('G', ['selection']), 'method-lineage-root')
        self.assertEqual(invalidation('D', ['capacity']), 'full-feedback-response')
        self.assertEqual(invalidation('D', []), 'reuse-exact-input')

    def test_mismatched_cache_and_missing_usage_stop(self):
        left = dict.fromkeys(('task','checker','backend','information','cache_start','limits'), 'same')
        right = {**left, 'cache_start':'warmer'}
        with self.assertRaisesRegex(ValueError, 'cache_start'):
            require_matched(left, right)
        rows = [{'id':'u', 'status':'UNKNOWN', 'reserved':.2},
                {'id':'s', 'status':'SETTLED', 'charged':.1, 'usage':None}]
        self.assertEqual(usage_summary(rows)['unknown_or_missing_usage'], ['u','s'])


if __name__=='__main__':
    unittest.main()
