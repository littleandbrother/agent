import unittest

from bfworld.agentlab.launcher import previous_attempt_summary


class LauncherRecoveryTests(unittest.TestCase):
    def test_unclean_running_receipt_keeps_unknown_terminal_fields(self):
        previous = {'started': 123.0, 'status': 'RUNNING', 'pid': 42}
        summary = previous_attempt_summary(previous)
        self.assertEqual('INTERRUPTED', summary['status'])
        self.assertEqual('RUNNING', summary['recorded_status'])
        self.assertIsNone(summary['ended'])
        self.assertIsNone(summary['trace_hash'])
        self.assertTrue(summary['terminal_receipt_missing'])
        self.assertEqual({'started': 123.0, 'status': 'RUNNING', 'pid': 42}, previous)

    def test_completed_receipt_preserves_measured_values(self):
        previous = {'started': 123.0, 'ended': 124.0, 'status': 'FAILED', 'trace_hash': 'abc'}
        self.assertEqual(previous, previous_attempt_summary(previous))


if __name__ == '__main__':
    unittest.main()
