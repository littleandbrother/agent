import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bfworld.agentlab.launcher import write_session_receipt


class SessionReceiptPublicationTests(unittest.TestCase):
    def test_observer_sees_complete_old_or_new_receipt_at_the_replacement_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'receipt.json'
            old={'owner':'original','status':'RUNNING','previous_attempts':['preserved']}
            new={**old,'status':'FAILED','error':'preserved failure','large':'内容'*20000}
            write_session_receipt(path,old)
            replace=os.replace
            def observe(source,target):
                self.assertEqual(json.loads(path.read_text()),old)
                self.assertEqual(json.loads(Path(source).read_text()),new)
                replace(source,target)
                self.assertEqual(json.loads(path.read_text()),new)
            with patch('bfworld.agentlab.launcher.os.replace',side_effect=observe) as published:
                write_session_receipt(path,new)
            published.assert_called_once()
            self.assertEqual(list(Path(tmp).iterdir()),[path])

    def test_failed_replacement_retains_previous_receipt_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'receipt.json';old={'status':'RUNNING','historical_unknown':['keep']}
            write_session_receipt(path,old);original=path.read_bytes()
            with patch('bfworld.agentlab.launcher.os.replace',side_effect=OSError('injected publication failure')):
                with self.assertRaises(OSError):write_session_receipt(path,{'status':'COMPLETED'})
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(tmp).iterdir()),[path])
