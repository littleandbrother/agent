"""Targeted C consumer/interpreter controls; fixtures are not participant trials."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from bfworld.agentlab.campaign20261019 import abc_methods as c


def design(period=20000,origin="detected",offset=0):
    return dict(schema_version=c.DESIGN,sample_period_us=period,sample_phase_us=0,
                timestamp_origin=origin,timestamp_offset_us=offset)


class TimeConsumerTests(unittest.TestCase):
    def test_matching_and_receive_are_not_timestamp_accuracy(self):
        task=c.make_task("C-first")
        result=c.assess(task,c.execute(task,design(750000)))
        self.assertEqual((result["event_matching"],result["timely_receive"]),("PASS","PASS"))
        self.assertEqual(result["timestamp_accuracy"],"FAIL")
        self.assertIn("WRONG_EVENT_TIME",result["reasons"])

    def test_definition_changes_truth_without_changing_detection(self):
        onset=c.make_task("C-definition")
        qualified=copy.deepcopy(onset)
        qualified["event_definition"]="qualified"
        raw=c.execute(onset,design(origin="first_sample"))
        first=c.assess(onset,raw)
        second=c.assess(qualified,c.execute(qualified,design(origin="first_sample")))
        self.assertEqual(first["status"],"PASS")
        self.assertEqual(second["timestamp_accuracy"],"FAIL")
        self.assertEqual(raw["records"][0]["detected_us"],c.execute(qualified,design(origin="first_sample"))["records"][0]["detected_us"])

    def test_nonintegral_confirmation_and_quantization(self):
        task=c.make_task("C-confirm")
        self.assertEqual(c.assess(task,c.execute(task,design()))["status"],"PASS")
        self.assertEqual(c.assess(task,c.execute(task,design(750000)))["status"],"FAIL")

    def test_foreign_and_tampered_response_rejected(self):
        task=c.make_task("C-first")
        raw=c.execute(task,design())
        self.assertEqual(c.assess(c.make_task("C-phase"),raw)["reasons"],["RESPONSE_BINDING"])
        raw["records"][0]["receive_us"]+=1
        self.assertEqual(c.assess(task,raw)["reasons"],["RESPONSE_BINDING"])

    def test_wire_is_decoded_independently(self):
        task=c.make_task("C-first")
        raw=c.execute(task,design())
        wire=bytearray.fromhex(raw["records"][0]["hex"])
        wire[8]^=1
        raw["records"][0]["hex"]=wire.hex()
        raw["response_sha256"]=c.digest({k:v for k,v in raw.items() if k!="response_sha256"})
        result=c.assess(task,raw)
        self.assertEqual(result["timestamp_accuracy"],"FAIL")

    def test_generic_ast_has_no_built_in_time_rule(self):
        proposal=dict(schema_version=c.METHOD,hypothesis="fixture only",falsifier="fixture failure",method_text="Generic interpreter fixture; no scientific rule.",
            checks=[dict(name="number comparison",relation=["le",{"var":"sample_period_s"},2])])
        gate=c.validate_method(proposal)
        self.assertEqual(gate["variables_used"],["sample_period_s"])
        values=c.run_relations(c.make_task("C-first"),design(),proposal)
        self.assertTrue(all(row["result"] for row in values["rows"]))
        proposal["checks"][0]["relation"]={"var":"private_truth"}
        with self.assertRaises(ValueError):c.validate_method(proposal)
        with self.assertRaises(ValueError):c.expression("__import__('os')",{})

    def test_tool_permissions_equal_and_formal_split_guarded(self):
        self.assertEqual(len({c.digest(c.tool_definition(dict(arm=arm))) for arm in c.ARMS}),1)
        with self.assertRaises(ValueError):c.make_task("C-unknown")
        scratch=Path(__file__).resolve().parents[2]/"docs/research/abc-cycle-20261020/methods/_test-scratch"
        scratch.mkdir(parents=True,exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=scratch) as directory:
                root=Path(directory)
                history=root/"history.json"
                c.seal(history,dict(original_only=True))
                spec=dict(stage="formation",arm="proposed",h0_text="H0 fixture",history_path=str(history),history_sha256=c.file_hash(history))
                packet=c.prepare_episode(spec,root)
                self.assertIsNone(packet["participant_input"]["task"])
                self.assertNotIn("C-phase",json.dumps(packet))
                handler=c.create_handler(root,spec)
                with self.assertRaises(ValueError):handler(dict(action="check",candidate=design()))
                result=c.independent_check(root,spec)
                self.assertEqual(result["status"],"NO_SUBMISSION")
            with tempfile.TemporaryDirectory(dir=scratch) as directory:
                root=Path(directory)
                spec=dict(stage="first",arm="H0",h0_text="H0 fixture",task_id="C-first")
                c.prepare_episode(spec,root)
                handler=c.create_handler(root,spec)
                first=handler(dict(action="check",candidate=design(750000)))
                self.assertEqual(first["acquisition"]["new_scientific_executions"],1)
                self.assertNotIn("verdict",first["observed"])
                repeated=handler(dict(action="submit",candidate=design(750000),service_judgment="PASS"))
                self.assertEqual(repeated["acquisition"]["new_scientific_executions"],0)
                result=c.independent_check(root,spec)
                self.assertEqual(result["status"],"FAIL")
                self.assertTrue(result["wrong_service_judgment"])
                handler(dict(action="check",candidate=design(700000)))
                with self.assertRaises(ValueError):handler(dict(action="check",candidate=design(600000)))
        finally:
            scratch.rmdir()


if __name__=="__main__":unittest.main()
