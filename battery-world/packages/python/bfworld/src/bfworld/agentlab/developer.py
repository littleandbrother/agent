"""Operator-only projections and immutable, locally validated future-run profiles."""
import difflib
import fcntl
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from .store import canonical, identity
from . import launcher
from .trace_review import tool_calls

EMPTY_MEMORY = {"hypotheses": [], "plan": [], "notes": ""}
EMPTY_PROMPTS = {"solver_append": "", "improver_append": ""}
FILES = ("solver.ts", "improver.ts")


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def safe_file(root, name):
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise PermissionError("PATH_DENIED")
    return path


def write_once(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()


class Developer:
    def __init__(self, workbench):
        self.app = workbench
        self.home = workbench.store.root.parent
        self.root = self.home / "developer"
        self.root.mkdir(exist_ok=True)

    def revision(self, key):
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("REVISION_ID_INVALID")
        record = read_json(safe_file(self.root, "revisions/" + key + ".json"))
        if not record or identity(record["payload"]) != key:
            raise ValueError("REVISION_MISSING_OR_TAMPERED")
        return record

    def active(self):
        return read_json(self.root / "active.json", {"revision": None, "generation": 0})

    def status(self):
        records = []
        for path in sorted((self.root / "revisions").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            record = self.revision(path.stem)
            validation = read_json(self.root / "validations" / (path.stem + ".json"))
            records.append({"id": path.stem, "name": record["payload"]["name"],
                            "created": record["created"], "parent": record["payload"]["parent"],
                            "validation": validation})
        return {"active": self.active(), "revisions": records}

    def sources(self, manifest=None):
        if manifest:
            for base in [self.home / "harnesses", self.root / "harnesses"]:
                for path in base.glob("*/manifest.json"):
                    if read_json(path).get("identity") == manifest["identity"]:
                        return {name: safe_file(path.parent, "src/" + name).read_text() for name in FILES}
            return None
        return {name: (launcher.PI / "packages/bf-harness/src" / name).read_text() for name in FILES}

    def harness_detail(self, key):
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("HARNESS_ID_INVALID")
        manifest = None
        for base in [self.home / "harnesses", self.root / "harnesses"]:
            for path in base.glob("*/manifest.json"):
                candidate = read_json(path)
                if candidate["identity"] == key:
                    manifest = candidate
                    break
        if not manifest:
            raise ValueError("HARNESS_NOT_FOUND")
        sources = self.sources(manifest)
        candidate = next((c for c in self.app.study_summary()["candidates"] if c.get("identity") == key), None)
        parent = self.sources({"identity": candidate["parent"]}) if candidate else None
        diff = {name: "".join(difflib.unified_diff(parent[name].splitlines(True), sources[name].splitlines(True),
                     fromfile="parent/"+name, tofile="candidate/"+name)) for name in FILES} if parent else None
        return {"manifest": manifest, "sources": sources, "candidate": candidate, "parent_diff": diff}

    def seed(self, session=None, revision=None):
        if revision:
            return self.revision(revision)
        source, memory, origin = self.sources(), dict(EMPTY_MEMORY), None
        if session:
            try:
                detail = self.app.session_detail(session)
            except FileNotFoundError:
                # A queued conversation has no frozen runtime yet. Start a default draft.
                self.app.conversations.get(session)
                return self.seed()
            origin = detail["result"]["receipt"]["harness"]["identity"]
            source = self.sources(detail["result"]["receipt"]["harness"])
            if not source:
                raise ValueError("FROZEN_SOURCE_UNAVAILABLE")
            state = read_json(safe_file(self.home / "participants", session + "/state.json"), {})
            memory = {"hypotheses": state.get("hypotheses", []), "plan": state.get("plan", []), "notes": ""}
            # Developer releases wrap source modules; seed from their original draft.
            for item in self.status()["revisions"]:
                validation = item["validation"]
                if validation and validation.get("harness_identity") == origin:
                    return self.revision(item["id"])
        return {"id": None, "payload": {"name": "新的运行配置", "parent": None,
                "source_session": session, "source_identity": origin,
                "memory": memory, "prompts": dict(EMPTY_PROMPTS), "sources": source}}

    def save(self, body):
        payload = {k: body.get(k) for k in ["name", "parent", "source_session", "source_identity", "memory", "prompts", "sources"]}
        if not isinstance(payload["name"], str) or not 1 <= len(payload["name"].strip()) <= 80:
            raise ValueError("NAME_REQUIRED_MAX_80")
        if payload["parent"]:
            self.revision(payload["parent"])
        if payload["source_session"]:
            receipt = self.app.session_detail(payload["source_session"], False)["result"]["receipt"]
            if receipt["harness"]["identity"] != payload["source_identity"]:
                raise ValueError("SOURCE_IDENTITY_MISMATCH")
        memory = payload["memory"]
        if not isinstance(memory, dict) or set(memory) != set(EMPTY_MEMORY):
            raise ValueError("MEMORY_ONLY_HYPOTHESES_PLAN_NOTES")
        for name in ["hypotheses", "plan"]:
            if not isinstance(memory[name], list) or len(memory[name]) > 100 or any(not isinstance(v, str) or len(v) > 2000 for v in memory[name]):
                raise ValueError("MEMORY_LIST_INVALID")
        if not isinstance(memory["notes"], str) or len(memory["notes"]) > 16000:
            raise ValueError("MEMORY_NOTES_TOO_LONG")
        for field, keys, limit in [("prompts", EMPTY_PROMPTS, 16000), ("sources", FILES, 40000)]:
            value = payload[field]
            if not isinstance(value, dict) or set(value) != set(keys) or any(not isinstance(v, str) or len(v) > limit for v in value.values()):
                raise ValueError(field.upper() + "_INVALID")
        if len(canonical(payload).encode()) > 120000:
            raise ValueError("REVISION_TOO_LARGE")
        if not payload["parent"]:
            seed = self.seed(payload["source_session"])["payload"]
            # Bind the initial comparison to the bytes observed at save time.
            # Later edits to the default Pi checkout cannot rewrite this diff.
            payload["base"] = {k: seed[k] for k in ["memory", "prompts", "sources"]}
        key = identity(payload)
        record = {"schema_version": "bf-agent-developer-revision-v1", "id": key, "created": time.time(), "payload": payload}
        try:
            write_once(self.root / "revisions" / (key + ".json"), record)
        except FileExistsError:
            return self.revision(key)
        return record

    def diff(self, key):
        record = self.revision(key)["payload"]
        parent = self.revision(record["parent"])["payload"] if record["parent"] else record.get("base")
        if parent is None:  # First local UI revision predates bound baselines.
            parent = self.seed(record["source_session"])["payload"]
        out = {}
        for name in ["memory", "prompts"]:
            out[name] = "".join(difflib.unified_diff(json.dumps(parent[name], ensure_ascii=False, indent=2).splitlines(True),
                              json.dumps(record[name], ensure_ascii=False, indent=2).splitlines(True), fromfile="before/" + name, tofile="after/" + name))
        for name in FILES:
            out[name] = "".join(difflib.unified_diff(parent["sources"][name].splitlines(True), record["sources"][name].splitlines(True), fromfile="before/" + name, tofile="after/" + name))
        return out

    def validate(self, key):
        record = self.revision(key)
        path = self.root / "validations" / (key + ".json")
        # Serialize compilation and selection. A receipt never changes after creation.
        with (self.root / "edit.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            previous = read_json(path)
            if previous:
                if previous["status"] == "VALIDATED":
                    self.resolve(key)
                return previous
            report = {"schema_version": "bf-agent-developer-validation-v1", "revision": key,
                      "created": time.time(), "status": "REJECTED", "model_calls": 0}
            payload = record["payload"]
            source = self.root / "build-inputs" / key
            (source / "src").mkdir(parents=True, exist_ok=True)
            for name, text in payload["sources"].items():
                (source / "src" / (name[:-3] + "-base.ts")).write_text(text)
            for kind in ["solver", "improver"]:
                function = "solverPrompt" if kind == "solver" else "improvementPrompt"
                signature = "task: any, state: any" if kind == "solver" else "context: any"
                args = "task, state" if kind == "solver" else "context"
                suffix = payload["prompts"][kind + "_append"]
                memory = canonical(payload["memory"])
                wrapper = f'import * as base from "./{kind}-base.js";\nexport * from "./{kind}-base.js";\n'
                if kind == "solver":
                    wrapper += f'export function initialState() {{ return {{...base.initialState(), hypotheses: {canonical(payload["memory"]["hypotheses"])}, plan: {canonical(payload["memory"]["plan"])}, developerMemory: {memory}}}; }}\n'
                extra = "\nOperator instructions:\n" + suffix
                if kind == "solver":
                    extra += "\nOperator memory (unverified hypotheses and notes, not experimental facts):\n" + memory
                wrapper += f'export function {function}({signature}): string {{ const prompt = base.{function}({args}) + {json.dumps(extra, ensure_ascii=False)}; console.log(JSON.stringify({{type:"context_snapshot", revision:{json.dumps(key)}, kind:{json.dumps(kind)}, prompt, memory:{memory}}})); return prompt; }}\n'
                (source / "src" / (kind + ".ts")).write_text(wrapper)
            try:
                harness = launcher.freeze(source, "DEV-" + key[:12], home_root=self.root)
                smoke = source / "smoke.mjs"
                smoke.write_text('''import {pathToFileURL} from "node:url";
const root=process.argv[2];
const s=await import(pathToFileURL(root+"/dist/solver.js"));
const u=await import(pathToFileURL(root+"/dist/improver.js"));
const state=s.initialState();
if(!state || !state.pending || !Array.isArray(state.facts)) throw Error("STATE_CONTRACT");
if(typeof s.solverPrompt({},state)!=="string" || typeof u.improvementPrompt({})!=="string") throw Error("PROMPT_CONTRACT");
const next=s.observeExperiment(state,{run_id:"smoke",snapshot_id:"smoke",checks:{electrical_safe:true},summary:{}});
if(!next || !Array.isArray(next.facts)) throw Error("OBSERVATION_CONTRACT");
console.log("CONTRACT_SMOKE_PASS");
''')
                profile = launcher.seatbelt(source, harness) + "\n(deny network*)"
                result = subprocess.run(["/usr/bin/sandbox-exec", "-p", profile, launcher.NODE, str(smoke), str(harness)],
                                        cwd=source, env={"PATH": "/usr/bin:/bin", "TMPDIR": str(source)}, capture_output=True, text=True, timeout=8)
                if result.returncode or "CONTRACT_SMOKE_PASS" not in result.stdout:
                    raise ValueError("CONTRACT_SMOKE_FAILED: " + result.stderr[-2000:])
                manifest = read_json(harness / "manifest.json")
                report.update(status="VALIDATED", harness=str(harness.relative_to(self.root)),
                              harness_identity=manifest["identity"], checks=["typescript", "sandboxed-contract", "source-build-binding"],
                              app_build_hash=manifest["app_build_hash"], source_hash=manifest["source_hash"])
            except (ValueError, subprocess.TimeoutExpired) as exc:
                report["error"] = str(exc)[:3000]
            write_once(path, report)
            return report

    def resolve(self, key):
        self.revision(key)
        report = read_json(self.root / "validations" / (key + ".json"))
        if not report or report["status"] != "VALIDATED":
            raise ValueError("REVISION_NOT_VALIDATED")
        harness = safe_file(self.root, report["harness"])
        manifest = read_json(harness / "manifest.json")
        if manifest["identity"] != report["harness_identity"] or identity({k:v for k,v in manifest.items() if k != "identity"}) != manifest["identity"]:
            raise ValueError("HARNESS_MANIFEST_TAMPER")
        for name, digest in manifest["source_files"].items():
            if launcher.filehash(safe_file(harness, name)) != digest:
                raise ValueError("HARNESS_SOURCE_TAMPER")
        for name, digest in manifest["loaded_files"].items():
            if launcher.filehash(safe_file(harness, "dist/" + name)) != digest:
                raise ValueError("HARNESS_BUILD_TAMPER")
        if launcher.filehash(launcher.PI / "packages/bf-agent/dist/main.js") != manifest["app_build_hash"]:
            raise ValueError("APP_BUILD_CHANGED_SINCE_VALIDATION")
        if launcher.filehash(launcher.PI / "package-lock.json") != manifest["pi_lock_hash"] or launcher.world_binding() != manifest["world_binding"]:
            raise ValueError("RUNTIME_CHANGED_SINCE_VALIDATION")
        return harness

    def activate(self, key, expected):
        with (self.root / "edit.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = self.active()
            if expected != current["generation"]:
                raise ValueError("ACTIVE_SELECTION_CHANGED_REFRESH")
            if key:
                self.resolve(key)
            value = {"revision": key, "generation": current["generation"] + 1, "selected_at": time.time()}
            write_once(self.root / "selections" / (str(value["generation"]) + ".json"), value)
            temp = self.root / "active.tmp"
            temp.write_text(canonical(value)); temp.replace(self.root / "active.json")
            return value

    def projection(self, session=None):
        out = {**self.status(), "session": None, "study": self.app.study_summary()}
        if not session or not session.startswith("pi-"):
            out["note"] = "选中 Pi 运行可查看其记忆、工具与上下文；固定参考不调用 Agent。"
            return out
        try:detail = self.app.session_detail(session)
        except FileNotFoundError:
            out['note'] = '当前会话尚未启动 Pi，可先准备下一次运行配置。'
            return out
        receipt = detail["result"]["receipt"]
        workspace = self.home / "participants" / session
        manifest = receipt["harness"]
        state = read_json(safe_file(workspace, "state.json"))
        contexts, calls, messages, loaded, shared = [], [], [], None, None
        calls, call_issues = tool_calls([event for event in detail['events'] if 'seq' in event])
        for event in detail["events"]:
            data = event["data"]
            if data.get("type") == "harness_loaded":
                loaded = data
            elif data.get("type") in ("context_snapshot", "shared_context_loaded"):
                contexts.append(data)
                if data["type"] == "shared_context_loaded":
                    shared = data
            elif data.get("type") == "message":
                msg = data["message"]
                if msg.get("role") in ["assistant", "user"]:
                    messages.append({"seq": event["seq"], "role": msg["role"], "content": [c for c in msg.get("content", []) if isinstance(c, dict) and c.get("type") == "text"]})
        with self.app.store.connect() as db:
            jobs = [self.app.store.project(row) for row in db.execute("SELECT * FROM jobs WHERE owner=? ORDER BY created", (session,))]
        jobs = [{"id": j["id"], "status": j["status"], "request": j["request"], "result": {k:j["result"].get(k) for k in ["run_id", "snapshot_id", "design_status", "checks", "summary", "artifacts"]} if j["result"] else None} for j in jobs]
        out["session"] = {"id": session, "mode": receipt["mode"], "harness": manifest, "loaded": loaded,
            "sources": self.sources(manifest), "state": state, "shared_context": shared,
            "notes": safe_file(workspace, "notes.md").read_text()[:24000] if safe_file(workspace, "notes.md").is_file() else None,
            "task": read_json(safe_file(workspace, "task.json")),
            "public_history": read_json(safe_file(workspace, "public-history.json")),
            "experience": read_json(safe_file(workspace, "experience.json")),
            "memory_in_prompt": receipt.get("memory_in_prompt", False), "contexts": contexts,
            "calls": calls, "call_issues": call_issues, "messages": messages, "jobs": jobs,
            "cost": detail["result"]["cost_upper_bound_usd"], "model_calls": detail["result"]["model_calls"]}
        return out
