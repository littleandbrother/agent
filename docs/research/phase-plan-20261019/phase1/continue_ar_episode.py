"""Explicit transport repair; preserve original owner, context, costs and deadline.

The censored episode and its gateway are never reopened. Qualify the continuation
with a mock provider, then freeze a separate continuation before a paid request.
"""
from pathlib import Path
import argparse
import http.server
import importlib.util
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
PLAN = ROOT / "docs/research/phase-plan-20261019/phase1"
BASE = Path("/Users/depengsu/.local/share/bf-phase1-20261020/a/ar-service/pi-episode-001")
QUAL = BASE.parent / "sdk-resume-qualification-001"
OUT = BASE / "continuation-001"
PROFILE = Path("/Users/depengsu/.local/share/bf-campaign-20261019-s0/profile.json")
profile = json.loads(PROFILE.read_text())
os.environ.update({"BF_" + key: value for key, value in profile["paths"].items()})
os.environ.update(BF_RUNTIME_ROOT=profile["runtime_root"], BF_RUNTIME_CONFIG=profile["configuration"],
    BF_DEVELOPMENT_PROFILE=str(PROFILE), PI_CODING_AGENT_DIR=str(Path(profile["home"]) / "pi-config"),
    PYTHONDONTWRITEBYTECODE="1")
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.campaign20261019.phase1 import BFPhaseGateway, digest, encoded, file_hash, ledger, seal
from bfworld.agentlab import launcher


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load("bf_phase1_original_runner", APP / "scripts/campaign_phase1.py")
host = load("bf_phase1_original_host", APP / "scripts/campaign_ar_service.py")
original = json.loads((BASE / "protocol.json").read_text())
session_source = Path((BASE / "participant/.pi/phase1-session-path").read_text().strip())


def build(root):
    if root.exists():
        raise FileExistsError("CONTINUATION_IDENTITY_ALREADY_EXISTS")
    root.mkdir(parents=True)
    harness = root / "harness"
    dest = harness / "dist/phase1/episode.js"
    dest.parent.mkdir(parents=True)
    pi = APP.parent / "pi-bf-aiot"
    source = pi / "packages/bf-agent/src/phase1/continuation.ts"
    with tempfile.TemporaryDirectory(prefix="continuation-build-", dir=root) as tmp:
        result = subprocess.run([str(pi / "node_modules/.bin/tsgo"), "-p",
            str(pi / "packages/bf-agent/tsconfig.json"), "--outDir", tmp],
            cwd=pi, capture_output=True, text=True, timeout=60)
        if result.returncode:
            seal(root / "build-failure.json", {"stdout": result.stdout[-3000:], "stderr": result.stderr[-1000:]})
            raise ValueError("CONTINUATION_TYPECHECK_FAILED")
        dest.write_bytes((Path(tmp) / "phase1/continuation.js").read_bytes())
    frozen = harness / "src/phase1/continuation.ts"
    frozen.parent.mkdir(parents=True)
    frozen.write_bytes(source.read_bytes())
    (harness / "node_modules").symlink_to(pi / "node_modules", target_is_directory=True)
    old = json.loads((BASE / "harness/manifest.json").read_text())
    for path, expected in old["sdk_runtime_files"].items():
        if file_hash(path) != expected:
            raise ValueError("ORIGINAL_SDK_DRIFT")
    receipt = {"sdk_version": old["sdk_version"], "sdk_runtime_files": old["sdk_runtime_files"],
        "compiled_sha256": file_hash(dest), "source_sha256": file_hash(frozen),
        "installed_dependencies_reused": True, "original_episode_source_unchanged": True}
    seal(harness / "manifest.json", receipt)
    return harness


def stage_context(root):
    workspace = root / "participant"
    directory = workspace / ".pi/phase1-sessions"
    directory.mkdir(parents=True)
    destination = directory / session_source.name
    subprocess.run(["/bin/cp", "-c", str(session_source), str(destination)], check=True)
    if file_hash(destination) != file_hash(session_source) or destination.stat().st_ino == session_source.stat().st_ino:
        raise ValueError("ORIGINAL_SESSION_CLONE_FAILED")
    return workspace, {"path": str(destination), "sha256": file_hash(session_source)}


def invoke(root, harness, config, timeout):
    workspace = Path(config["workspace"])
    (workspace / ".tmp").mkdir()
    seatbelt = launcher.seatbelt(workspace, harness, int(config["service"].rsplit(":", 1)[1]))
    started = time.monotonic()
    with (root / "pi-public-trace.jsonl").open("x") as stdout, (root / "pi-stderr.log").open("x") as stderr:
        process = subprocess.Popen(["/usr/bin/sandbox-exec", "-p", seatbelt, profile["paths"]["NODE"],
            str(harness / "dist/phase1/episode.js")], cwd=workspace,
            env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin", "TMPDIR": str(workspace / ".tmp"), "LANG": "en_US.UTF-8"},
            stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
        timed_out = False
        try:
            process.communicate(encoded(config) + b"\n", timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
    prefix = Path(config["resumeSession"]["path"]).read_bytes()[:session_source.stat().st_size]
    if runner.hashlib_sha(prefix) != config["resumeSession"]["sha256"]:
        raise ValueError("ORIGINAL_CONTEXT_PREFIX_CHANGED")
    return {"exit_code": process.returncode, "wall_seconds": time.monotonic() - started,
        "timed_out": timed_out, "original_context_prefix_unchanged": True,
        "sandbox_sha256": runner.hashlib_sha(seatbelt.encode())}


def qualify():
    harness = build(QUAL)
    workspace, resume = stage_context(QUAL)
    database = QUAL / "fixture-ledger.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE model_requests(id TEXT,owner TEXT,created REAL,status TEXT,reserved REAL,charged REAL,usage TEXT,response_hash TEXT,error TEXT)")
    requests = []

    class FakeProvider(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(value)
            usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
            with sqlite3.connect(database) as db:
                db.execute("INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?)",
                    ("fixture-only", original["owner"], time.time(), "SETTLED", 0, 0, json.dumps(usage), "fixture", None))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for delta, reason in [({"role": "assistant", "content": "CONTINUATION_SOFTWARE_QUALIFIED"}, None), ({}, "stop")]:
                item = {"id": "fixture", "model": "deepseek-flash", "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": reason}], "usage": usage}
                self.wfile.write(b"data: " + encoded(item) + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")

    mock = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
    thread = threading.Thread(target=mock.serve_forever, daemon=True)
    thread.start()
    p = {**original, "mode": "fixture", "output_root": str(QUAL), "provider_database": str(database),
        "provider_service": "http://127.0.0.1:" + str(mock.server_port), "bound_files": {},
        "limits": {**original["limits"], "reserve_bytes": 0, "peak_remaining_bytes": 0, "wall_seconds": 60,
            "model_response_bytes": 64 * 1024 * 1024}}
    lease = QUAL / "fixture-lease.json"
    seal(lease, {"status": "GRANTED", "episode": p["id"], "holders": ["S0", "Pi"],
        "expires": time.time() + 60, "other_executor_status": "idle"})
    gateway = BFPhaseGateway(p, QUAL / "gateway", lambda body: {}, provider_token="fixture-only", lease_path=lease)
    try:
        result = invoke(QUAL, harness, {"workspace": str(workspace), "resumeSession": resume,
            "service": gateway.start(), "token": gateway.token, "owner": original["owner"],
            "goal": "软件恢复演练：已有上下文保持，只回复演练完成，不执行科学工具。", "instruction": original["instruction"],
            "episodeId": original["id"], "tool": original["tool"]}, 45)
    finally:
        gateway.close()
        mock.shutdown()
        mock.server_close()
        thread.join(timeout=2)
    events = [json.loads(line) for line in (QUAL / "pi-public-trace.jsonl").read_text().splitlines()]
    context = next(e for e in events if e.get("type") == "bf_continuation_context")
    old_results = [m for m in requests[0]["messages"] if m.get("role") == "tool"] if len(requests) == 1 else []
    result.update(status="PASS" if result["exit_code"] == 0 and len(old_results) == 4 and context["messages"] > 0 else "FAIL",
        original_session_id=context["session_id"], original_messages=context["messages"],
        old_tool_results_in_actual_next_request=len(old_results), actual_sdk_requests=len(requests),
        paid_requests=0, native_dispatches=0, scientific_tool_calls=0,
        scope="Actual installed SDK resumes original session prefix; mock provider only")
    seal(QUAL / "result.json", result)
    print(json.dumps(result), flush=True)
    if result["status"] != "PASS":
        raise ValueError("ORIGINAL_CONTEXT_CONSUMPTION_NOT_QUALIFIED")


def run():
    if json.loads((QUAL / "result.json").read_text())["status"] != "PASS":
        raise ValueError("CONTINUATION_QUALIFICATION_REQUIRED")
    if OUT.exists():
        raise FileExistsError("NO_AUTOMATIC_CONTINUATION_RETRY")
    runner.verify(BASE / "protocol.json")
    old_result = json.loads((BASE / "episode-result.json").read_text())
    if old_result["status"] != "INCOMPLETE_OR_STOPPED" or old_result["trace_audit"]["model_submitted"]:
        raise ValueError("WRONG_PREDECESSOR_STATE")
    events = [json.loads(line) for line in (BASE / "gateway/gateway-events.jsonl").read_text().splitlines()]
    if not any(e["kind"] == "model_forward_failed" and "MODEL_RESPONSE_BYTE_LIMIT" in e["data"]["error"] for e in events):
        raise ValueError("ONLY_DECLARED_TRANSPORT_REPAIR_ALLOWED")
    account = ledger(original["provider_database"], original["owner"])
    if account["unknown_or_missing_usage"] or account["requests"] != 2:
        raise ValueError("SETTLED_PREDECESSOR_USAGE_REQUIRED")
    if list((BASE / "scientific").glob("candidate-*")) or (BASE / "scientific/submission.json").exists():
        raise ValueError("PREDECESSOR_HAS_DESIGN_STATE_REQUIRES_SEPARATE_REVIEW")
    slots = json.loads((PLAN / "continuation-idle-slot-receipt.json").read_text())
    if time.time() - slots["observed_unix"] > 300 or any(slots[key]["status"] != "idle" for key in ("A", "B")):
        raise ValueError("FRESH_IDLE_SNAPSHOT_REQUIRED")
    deadline = json.loads((BASE / "slot-lease.json").read_text())["expires"]
    remaining = int(deadline - time.time())
    if remaining < 60 or shutil.disk_usage(ROOT).free < 10_900_000_000:
        raise ValueError("ORIGINAL_DEADLINE_OR_STORAGE_HEADROOM")
    OUT.mkdir()
    harness = OUT / "harness"
    for relative in ["dist/phase1/episode.js", "src/phase1/continuation.ts", "manifest.json"]:
        dest = harness / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["/bin/cp", "-c", str(QUAL / "harness" / relative), str(dest)], check=True)
    (harness / "node_modules").symlink_to(APP.parent / "pi-bf-aiot/node_modules", target_is_directory=True)
    workspace, resume = stage_context(OUT)
    p = {**original, "schema_version": "bf-phase1-explicit-transport-continuation-v1", "output_root": str(OUT),
        "harness": str(harness), "limits": {**original["limits"], "model_response_bytes": 64 * 1024 * 1024,
            "wall_seconds": remaining, "tool_calls": 56},
        "continuation": {"parent_protocol": str(BASE / "protocol.json"), "parent_result": str(BASE / "episode-result.json"),
            "reason": "SSE framing exceeded 2 MB; upstream terminal usage settled after disconnect.",
            "prior_provider_requests": 2, "prior_scientific_candidates": 0, "prior_tool_calls": 4,
            "original_deadline_unix": deadline, "original_session": str(session_source), "resume_prefix_sha256": resume["sha256"],
            "new_owner_or_context_reset": False, "automatic_retry": False,
            "method_comparison": "NOT_TESTED; original censored attempt stays in accounting and attrition"}}
    p["bound_files"] = dict(original["bound_files"])
    for path in [Path(__file__), APP.parent / "pi-bf-aiot/packages/bf-agent/src/phase1/continuation.ts",
        harness / "dist/phase1/episode.js", harness / "src/phase1/continuation.ts", QUAL / "result.json",
        session_source, BASE / "protocol.json", BASE / "episode-result.json", BASE / "settlement-readback.json"]:
        p["bound_files"][str(path)] = file_hash(path)
    protocol_path = OUT / "protocol.json"
    seal(protocol_path, p)
    lease = OUT / "slot-lease.json"
    seal(lease, {"status": "GRANTED", "episode": p["id"], "expires": deadline,
        "holders": ["S0", "Pi"], "other_executor_status": "idle", "worker_snapshot": slots})
    runner.verify(protocol_path)
    operator = (Path(profile["home"]) / "state/operator.token").read_text().strip()
    req = urllib.request.Request(p["provider_service"] + "/api/design-lab", data=encoded({"action": "method_authorize",
        "session_id": p["owner"], "task_id": p["id"], "wall_authorization_text": "持续运行 不设置时间限制",
        "model_profile": "engineering-reasoning-compact-v2"}),
        headers={"Authorization": "Bearer " + operator, "Content-Type": "application/json"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=30) as response:
        authority = json.load(response)
    token = authority.pop("participant_token")
    seal(OUT / "authority.json", authority)
    context = {"episode_id": p["id"], "model": p["model_alias"], "backend": p["provider_service"],
        "provider_ledger": p["provider_database"], "slot_receipt": str(lease), "baseline": p["baseline"],
        "maximum_requests": 60, "maximum_candidates": 3, "maximum_wall_s": remaining}
    gateway = BFPhaseGateway(p, OUT / "gateway", host.create_handler(OUT / "scientific", lease=context),
        provider_token=token, lease_path=lease)
    result = {"status": "START_FAILURE", "episode": p["id"], "owner": p["owner"],
        "original_censored_attempt_retained": True, "automatic_retry": False, "native_dispatches": 0}
    try:
        result.update(invoke(OUT, harness, {"workspace": str(workspace), "resumeSession": resume,
            "service": gateway.start(), "token": gateway.token, "owner": p["owner"],
            "goal": "继续同一任务和已有公开事实。上一回复被传输封装限额截断，已有两次费用保留并计入原始总额。请继续选择合法候选、实际 check 并 submit；仍最多累计 60 请求、3 候选，原始总时限不延长。",
            "instruction": original["instruction"], "episodeId": p["id"], "tool": p["tool"]},
            max(1, deadline - time.time())))
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)[:1800]
    finally:
        gateway.close()
        token = None
        account = ledger(p["provider_database"], p["owner"])
        seal(OUT / "provider-costs.json", account)
    result.update(provider_requests_cumulative=account["requests"], unresolved_usage=account["unknown_or_missing_usage"],
        settled_charge_upper_bound_usd=account["settled_charge_upper_bound_usd"], cache_aware_rate_estimate_usd=account["cache_aware_rate_estimate_usd"])
    try:
        result["trace_audit"] = runner.audit_participant(OUT, p["tool"]["name"])
        submitted = (OUT / "scientific/submission.json").exists() and result["trace_audit"]["model_submitted"]
        result["status"] = "PARTICIPANT_SUBMITTED_REQUIRES_EXTERNAL_EVALUATION" if result.get("exit_code") == 0 and submitted and not account["unknown_or_missing_usage"] and not gateway.stopped else "INCOMPLETE_OR_STOPPED"
    except Exception as error:
        result["status"] = "TRACE_AUDIT_FAILED"
        result["trace_error"] = str(error)[:1800]
    result["scientific_acceptance"] = "EXTERNAL_EVALUATION_REQUIRED"
    seal(OUT / "episode-result.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["status"] == "PARTICIPANT_SUBMITTED_REQUIRES_EXTERNAL_EVALUATION" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["qualify", "run"])
    args = parser.parse_args()
    raise SystemExit(qualify() or 0 if args.mode == "qualify" else run())
