import json
from pathlib import Path
import tempfile
import unittest

from bfworld.agentlab.campaign20261019.abc_shared import slot_holders, check_bindings, totals
from bfworld.agentlab.campaign20261019.phase1 import file_hash


class ABCSharedTest(unittest.TestCase):
    def test_slot_receipt_requires_observed_idle_and_three_maximum(self):
        value = dict(observed_unix=100, holders=['S0','B','Pi'], idle_execution_thread='A',other_executor_status='idle')
        self.assertEqual(slot_holders(value,now=150),['S0','B','Pi'])
        for patch in [dict(observed_unix=0),dict(holders=['S0','A','B','Pi']),dict(idle_execution_thread=None),dict(other_executor_status='active')]:
            with self.assertRaises(ValueError):slot_holders({**value,**patch},now=150)

    def test_source_drift_fails_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source';p.write_text('frozen');bound={str(p):file_hash(p)}
            check_bindings(bound);p.write_text('changed')
            with self.assertRaises(ValueError):check_bindings(bound)
            self.assertEqual(p.read_text(),'changed')

    def test_started_failed_attempt_counts_without_provider_owner(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'episodes/failure';p.mkdir(parents=True)
            (p/'attempt.json').write_text(json.dumps({'started_unix':0}))
            (p/'episode-result.json').write_text(json.dumps({'wall_seconds_total':3}))
            v=totals(d,'unopened-database')
            self.assertEqual((v['attempts'],v['requests'],v['wall_s']),(1,0,3))
