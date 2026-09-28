import copy
import json
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from pathlib import Path
from http.server import ThreadingHTTPServer

from bfworld.agentlab.server import Workbench, handler
from bfworld.agentlab.developer import read_json
from bfworld.agentlab import launcher


class DeveloperStudio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Workbench(Path(self.tmp.name) / "state")
        self.dev = self.app.developer
        self.token = (self.app.store.root / "operator.token").read_text()
        self.app.store.grant("alice", ["dev-01"], 1, time.time() + 60)
        self.alice = self.app.store.issue("alice")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        self.app.stop.set(); self.app.thread.join(3); self.app.lock.close()
        self.tmp.cleanup()

    def req(self, path, body=None, token=None, origin=None):
        headers = {"Authorization": "Bearer " + (token or self.token), "Content-Type": "application/json"}
        if origin: headers["Origin"] = origin
        request = urllib.request.Request("http://127.0.0.1:" + str(self.server.server_port) + path,
                    data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(request) as response: return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def draft(self):
        payload = self.dev.seed()["payload"]
        payload["name"] = "contract-test"
        payload["memory"] = {"hypotheses": ["test hypothesis"], "plan": ["inspect evidence"], "notes": "operator-memory-sentinel"}
        payload["prompts"]["solver_append"] = "prompt-activation-sentinel"
        return payload

    def test_operator_only_read_write_origin_and_paths(self):
        for path in ["/api/developer", "/api/developer/seed", "/api/developer/revision?id=bad"]:
            self.assertEqual(403, self.req(path, token=self.alice)[0])
        for path, body in [("/api/developer/revisions", self.draft()), ("/api/developer/validate", {"revision": "bad"}),
                           ("/api/developer/activate", {"revision": None, "expected_generation": 0})]:
            self.assertEqual(403, self.req(path, body, token=self.alice)[0])
        self.assertEqual(403, self.req("/api/developer/revisions", self.draft(), origin="http://foreign.test")[0])
        self.assertEqual(400, self.req("/api/developer/revision?id=../../secrets")[0])
        self.assertEqual(403, self.req("/api/developer?session=pi-../../secrets")[0])
        draft=self.draft(); draft["memory"]["facts"]=[{"passed": True}]
        self.assertEqual(400, self.req("/api/developer/revisions", draft)[0])
        draft=self.draft(); draft["sources"]["../../escape.ts"]=""
        self.assertEqual(400, self.req("/api/developer/revisions", draft)[0])

    def test_immutable_revisions_parent_diff_and_selection_conflict(self):
        draft=self.draft()
        _, first=self.req("/api/developer/revisions", draft)
        again=self.dev.save(draft)
        self.assertEqual(first, again)
        self.assertEqual(self.dev.sources(),first["payload"]["base"]["sources"])
        with patch.object(self.dev, "sources", return_value={"solver.ts":"later checkout", "improver.ts":"later checkout"}):
            self.assertNotIn("later checkout",self.dev.diff(first["id"])["solver.ts"])
        original=(self.dev.root/"revisions"/(first["id"]+".json")).read_bytes()
        second=copy.deepcopy(draft); second["parent"]=first["id"]; second["memory"]["notes"]="changed"
        _, changed=self.req("/api/developer/revisions", second)
        self.assertNotEqual(first["id"],changed["id"])
        self.assertIn("changed",self.dev.diff(changed["id"])["memory"])
        self.assertEqual(original,(self.dev.root/"revisions"/(first["id"]+".json")).read_bytes())
        self.assertEqual(400,self.req("/api/developer/activate",{"revision":first["id"],"expected_generation":0})[0])
        self.assertEqual(200,self.req("/api/developer/activate",{"revision":None,"expected_generation":0})[0])
        self.assertEqual(400,self.req("/api/developer/activate",{"revision":None,"expected_generation":0})[0])

    def test_real_build_memory_prompt_activation_tamper_and_no_paid_call(self):
        draft=self.draft()
        import re
        draft["sources"]["solver.ts"], count = re.subn(r"current\s*:\s*null", "current: {developer_test:true}", draft["sources"]["solver.ts"], count=1)
        self.assertEqual(1, count, "test mutation must change an actual initial state field")
        record=self.dev.save(draft); key=record["id"]
        status, report=self.req("/api/developer/validate",{"revision":key})
        self.assertEqual(200,status);self.assertEqual("VALIDATED",report["status"],report)
        harness=self.dev.resolve(key)
        source=(harness/"src/solver.ts").read_text()
        self.assertIn("operator-memory-sentinel",source)
        self.assertIn("prompt-activation-sentinel",source)
        self.assertEqual(report,self.dev.validate(key))
        self.dev.activate(key,0)
        self.assertEqual(key,self.dev.active()["revision"])
        self.assertEqual(4,len(read_json(harness/"manifest.json")["loaded_files"]))
        with patch.object(launcher, "HOME_ROOT", self.app.store.root.parent):
            receipt=launcher.launch(harness, label="pi-editor-dry-run", store_root=self.app.store.root,
                                    dry_run=True, service_port=self.server.server_port)
        trace=(self.app.store.root.parent/"sessions/pi-editor-dry-run/trace.jsonl").read_text()
        stderr=(self.app.store.root.parent/"sessions/pi-editor-dry-run/stderr.log").read_text()
        self.assertEqual(0,receipt["exit_code"],stderr)
        self.assertIn("prompt-activation-sentinel",trace)
        self.assertIn("operator-memory-sentinel",trace)
        self.assertIn(key,trace)
        state=read_json(self.app.store.root.parent/"participants/pi-editor-dry-run/state.json")
        self.assertEqual(["test hypothesis"],state["hypotheses"])
        self.assertEqual([],state["facts"])
        self.assertEqual({"developer_test":True},state["current"])
        (self.app.store.root.parent/"paid-window-closed.json").write_text('{"reason":"closed"}')
        self.assertEqual("PAID_WINDOW_CLOSED",self.req("/api/solve",{"task_id":"dev-01"})[1]["error"])
        with self.app.store.connect() as db:
            self.assertEqual(0,db.execute("SELECT count(*) FROM model_requests").fetchone()[0])
        (harness/"dist/solver-base.js").write_text("tampered")
        with self.assertRaisesRegex(ValueError,"HARNESS_BUILD_TAMPER"): self.dev.resolve(key)

    def test_invalid_source_and_sandbox_read_are_rejected(self):
        draft=self.draft();draft["sources"]["solver.ts"]="not typescript ???"
        key=self.dev.save(draft)["id"]
        self.assertEqual("REJECTED",self.dev.validate(key)["status"])
        with self.assertRaisesRegex(ValueError,"REVISION_NOT_VALIDATED"):self.dev.activate(key,0)
        draft=self.draft()
        draft["sources"]["solver.ts"]+='\nimport fs from "node:fs"; fs.readFileSync("/Users/depengsu/Documents/bf-agent-workbench/secrets/deepseek.key");'
        key=self.dev.save(draft)["id"]
        result=self.dev.validate(key)
        self.assertEqual("REJECTED",result["status"])
        self.assertIn("EPERM",result.get("error",""))

    def test_projection_uses_bound_source_and_labels_missing_prompt(self):
        owner="pi-test-observation"; base=self.app.store.root.parent
        participant=base/"participants"/owner;participant.mkdir(parents=True)
        (participant/"state.json").write_text('{"facts":[{"run_id":"original"}],"hypotheses":[],"plan":[]}')
        (participant/"task.json").write_text('{"task_id":"dev-01"}')
        session=base/"sessions"/owner;session.mkdir(parents=True)
        manifest={"identity":"bound","label":"test","tools":["read","bf_job"]}
        (session/"receipt.json").write_text(json.dumps({"owner":owner,"mode":"solve","status":"COMPLETED","started":time.time(),"task_id":"dev-01","harness":manifest}))
        (session/"stderr.log").write_text("")
        (session/"trace.jsonl").write_text(json.dumps({"type":"tool_execution_start","toolName":"read","args":{"path":"task.json"}})+"\n"+json.dumps({"type":"message","message":{"role":"toolResult","toolName":"read","content":[{"type":"text","text":"public"}],"isError":False}})+"\n")
        status, value=self.req("/api/developer?session="+owner)
        self.assertEqual(200,status);self.assertEqual([],value["session"]["contexts"])
        self.assertIsNone(value["session"]["sources"])
        self.assertEqual("original",value["session"]["state"]["facts"][0]["run_id"])
        self.assertEqual("public",value["session"]["calls"][0]["result"][0]["text"])
        self.assertNotIn("token",json.dumps(value))


if __name__ == "__main__": unittest.main()
