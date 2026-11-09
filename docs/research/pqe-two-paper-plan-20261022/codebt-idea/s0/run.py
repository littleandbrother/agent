#!/usr/bin/env python3
"""New-idea host entrypoint. Offline means no provider and no full solver.

No old study, quota or episode is resumed. Scientific admission is explicit and
checked again before every full input. Compact originals are kept in place.
"""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import hashlib
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
BASE = OUT.parent
ROOT = BASE.parents[2]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
DB = Path("/Users/depengsu/.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite")
PYTHON = Path("/Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python")
PACKAGE = "BF-PQE-CODEBT-KILL-20261024-001"
BLOCKING_REQUEST = "llm-16cd5bfe95e06e92fd6d"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def accounting_gate():
    """Read-only. No estimate, saved SDK zero, or new owner settles a liability."""
    from bfworld.agentlab import historical_usage
    db = sqlite3.connect(DB.as_uri()+"?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        exceptions = historical_usage.verified_exceptions(db, PACKAGE)
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM model_requests WHERE status='UNKNOWN' OR (status='SETTLED' AND usage IS NULL)")]
        blockers = [{"id": row["id"], "owner": row["owner"], "status": row["status"],
                     "usage": row["usage"], "reserved_usd": row["reserved"],
                     "original_row_sha256": historical_usage.identity(row)}
                    for row in rows if exceptions.get(row["id"]) != historical_usage.identity(row)]
        counts = dict(db.execute("SELECT status,count(*) FROM model_requests GROUP BY status"))
    finally:
        db.close()
    state = json.loads((BASE / "execution-state.json").read_text())
    admitted = state.get("package") == PACKAGE and state.get("execution_gate", {}).get("status") == "ADMITTED_NEW_IDEA"
    return {"schema": "codebt-accounting-gate-v1", "package": PACKAGE,
            "status": "ADMITTED" if not blockers and admitted else "OFFLINE_IMPLEMENTATION_ONLY",
            "unexcepted_missing_usage": blockers, "ledger_status_counts": counts,
            "recognized_exact_historical_exceptions": sorted(exceptions),
            "explicit_new_package_admission": admitted,
            "ledger_access": "read_only",
            "rule": "Only the two immutable specifically authorized historical liabilities may be carried; the later exception applies to this package only. Any new missing usage stops dependent dispatch."}


def require_scientific_admission():
    gate = accounting_gate()
    if gate["status"] != "ADMITTED":
        raise RuntimeError("CODEBT_SCIENCE_NOT_ADMITTED:"+json.dumps(gate["unexcepted_missing_usage"]))
    if not (OUT / "shared/protocol.json").exists():
        raise RuntimeError("CODEBT_SHARED_PROTOCOL_NOT_FROZEN")
    protocol = json.loads((OUT / "shared/protocol.json").read_text())
    if protocol.get("status") != "FROZEN_FOR_NEW_SCIENCE":
        raise RuntimeError("CODEBT_ACTUAL_MODEL_AND_OWNER_BINDING_REQUIRED")
    return gate


def scientific_member(task, design, action, folder):
    """One new full input in a bounded child; never called by offline checks."""
    import os
    require_scientific_admission()
    if not folder.resolve().is_relative_to(HERE / "science"):
        raise ValueError("SCIENTIFIC_OUTPUT_OUTSIDE_NEW_PACKAGE")
    fs = os.statvfs(ROOT)
    retained = sum(p.stat().st_blocks*512 for p in OUT.rglob("*") if p.is_file())
    if fs.f_bavail*fs.f_frsize < 11_000_000_000 or retained > 100_000_000:
        raise RuntimeError("STORAGE_CAP_OR_HEADROOM")
    folder.mkdir(parents=True, exist_ok=False)
    request = {"package": PACKAGE, "task": task, "design": design, "action": action}
    save(folder / "input.json", request)
    # One child per input, no new environment, no persistent service, 120s cap.
    with (folder / "child.stdout").open("w") as stdout, (folder / "child.stderr").open("w") as stderr:
        completed = subprocess.run([str(PYTHON), "-B", str(HERE / "run.py"), "child", str(folder / "input.json")],
            cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=stdout, stderr=stderr, timeout=120, check=False)
    if completed.returncode:
        raise RuntimeError("NEW_FULL_CHILD_FAILED:"+str(completed.returncode))
    with gzip.open(folder / "result/public-result.json.gz", "rt") as stream:
        return json.load(stream)


def child(input_path):
    require_scientific_admission()
    from bfworld.agentlab.pqe20261024debt import adapter
    protocol = json.loads((OUT / "shared/protocol.json").read_text())
    if protocol["sources"] != adapter.source_identity():
        raise RuntimeError("FROZEN_SCIENTIFIC_SOURCE_CHANGED")
    family_ref = protocol["family_ref"]
    frozen_bytes = Path(family_ref["path"]).read_bytes()
    if hashlib.sha256(frozen_bytes).hexdigest() != family_ref["sha256"]:
        raise RuntimeError("FROZEN_TASK_ARTIFACT_CHANGED")
    family = {t["task_id"]: t for t in json.loads(frozen_bytes)["conditions"]}
    request = json.loads(input_path.read_text())
    task = request["task"]
    if request["package"] != PACKAGE or family.get(task["task_id"]) != task:
        raise RuntimeError("NEW_FROZEN_TASK_BINDING")
    action = request["action"]
    base = action.get("base_design", request["design"])
    updated, _, _ = adapter.prepare(task, base, task["initial_problem"], action["decision"],
                                     task_resolver=family.__getitem__)
    if updated != request["design"]:
        raise RuntimeError("ACTION_DESIGN_BINDING")
    public = adapter.execute(task, base, task["initial_problem"], action["decision"],
        input_path.parent / "result", task_resolver=family.__getitem__)
    public["condition_id"] = task["condition_id"]
    public_path = input_path.parent / "result/public-result.json.gz"
    adapter._write_gzip(public_path, public)
    # The verified compressed public object is canonical, not another preview.
    (input_path.parent / "result/public-result.json").unlink()
    return {"status": "COMPLETED", "result": str(public_path)}


class FinitePlanner:
    """Budget propagation around one existing accounted model callback.

    Production needs the actual owner ledger and settlement verifier. This
    adapter cannot issue credentials, settle usage, revive an owner or retry.
    """
    def __init__(self, callback, budget_reader, *, model_identity, settlement_check=None,
                 offline=False):
        self.callback, self.budget_reader = callback, budget_reader
        self.model_identity, self.settlement_check = model_identity, settlement_check
        self.offline = offline
        self.requests = 0
        self.halted = None
        self.calls = []

    def __call__(self, request):
        if self.halted:
            raise RuntimeError(self.halted)
        if not self.offline:
            require_scientific_admission()
            if self.settlement_check is None:
                raise RuntimeError("ACTUAL_OWNER_SETTLEMENT_VERIFIER_REQUIRED")
        budget = self.budget_reader()
        # Values originate in the trusted owner ledger, never participant quota.
        needed = {"requests_used", "output_tokens_used", "spent_usd", "remaining_wall_s", "tool_calls_used"}
        if not needed <= set(budget):
            raise RuntimeError("COMPLETE_OWNER_BUDGET_REQUIRED")
        if (self.requests >= 12 or budget["requests_used"] >= 12 or budget["spent_usd"] >= 5
                or budget["remaining_wall_s"] <= 0 or budget["tool_calls_used"] >= 24):
            raise RuntimeError("NEW_EPISODE_BUDGET_EXHAUSTED")
        # The bound Pi callback admits at most 32768 tokens per request.
        # The episode's 131072-token total is a separate, unchanged limit.
        grant = min(32768, 131072-budget["output_tokens_used"])
        if grant < 1:
            raise RuntimeError("NEW_EPISODE_OUTPUT_EXHAUSTED")
        body = {**deepcopy(request), "max_output_tokens": grant, "owner_budget": deepcopy(budget)}
        self.requests += 1
        record = {"request_sha256": digest(body), "max_output_tokens": grant,
                  "software_fixture": self.offline}
        self.calls.append(record)
        try:
            response = self.callback(body)
            usage = response.get("usage", {})
            expected = {"SOFTWARE_FIXTURE"} if self.offline else {"KNOWN", "SETTLED"}
            if usage.get("status") not in expected:
                raise RuntimeError("PROVIDER_USAGE_NOT_SETTLED")
            if not self.offline and (usage.get("model_identity") != self.model_identity or
                    self.settlement_check(response) is not True):
                raise RuntimeError("ACTUAL_OWNER_USAGE_OR_MODEL_BINDING")
            after = self.budget_reader()
            if (after["requests_used"] > 12 or after["output_tokens_used"] > 131072
                    or after["spent_usd"] > 5 or after["remaining_wall_s"] < 0
                    or after["tool_calls_used"] > 24
                    or usage.get("output_tokens", 0) > grant):
                raise RuntimeError("NEW_EPISODE_ACTUAL_BUDGET_EXCEEDED")
            record["usage_status"] = usage["status"]
            return response
        except Exception as exc:
            self.halted = str(exc)
            record["error"] = self.halted
            raise


class FamilyBroker:
    """Common family evaluator. Fixture feedback is never scientific evidence."""
    def __init__(self, family, evaluate_fn, *, offline=False, sources=None):
        self.family = deepcopy(family)
        self.evaluate_fn = evaluate_fn
        self.offline = offline
        self.sources = deepcopy(sources or {})
        self.by_group = {}
        self.cache = {}
        self.full_inputs = 0
        self.fixture_inputs = 0
        self.full_wall_s = 0.
        self.events = []

    def evaluate(self, group, action):
        if action.get("status") != "ACTION":
            raise ValueError("ACTION_REQUIRED")
        design = deepcopy(action["design"])
        key = digest(design)
        slots = self.by_group.setdefault(group, [])
        if key in slots:
            raise ValueError("DUPLICATE_DESIGN_ALREADY_EVALUATED_BY_GROUP")
        if len(slots) >= 6:
            raise RuntimeError("GROUP_SIX_DESIGN_CAP")
        if not self.offline:
            require_scientific_admission()
            if self.full_inputs + len(self.family) > 63 or self.full_wall_s + 120*len(self.family) > 7560:
                raise RuntimeError("PACKAGE_FULL_INPUT_OR_WALL_CAP")
        # Admission/claim before any callback; failures also consume this slot.
        slots.append(key)
        results = []
        for task in self.family:
            if not self.offline:
                require_scientific_admission()
            cache_key = digest({"task": task, "design": design, "sources": self.sources})
            reused = cache_key in self.cache
            if reused:
                result = deepcopy(self.cache[cache_key])
            else:
                if self.offline:
                    self.fixture_inputs += 1
                else:
                    self.full_inputs += 1
                started = time.monotonic()
                try:
                    result = self.evaluate_fn(task, design, action)
                except Exception as exc:
                    self.events.append({"group": group, "request_id": action.get("request_id"),
                        "condition": task.get("condition_id"), "error": str(exc),
                        "scientific": not self.offline, "design_sha256": key})
                    raise
                elapsed = time.monotonic() - started
                if not self.offline:
                    self.full_wall_s += elapsed
                    if elapsed > 120 or self.full_wall_s > 7560:
                        raise RuntimeError("FULL_WALL_CAP_EXCEEDED")
                self.cache[cache_key] = deepcopy(result)
            if result.get("design") != design or result.get("task_id") != task["task_id"]:
                raise ValueError("CONSUMER_TASK_DESIGN_BINDING")
            result["condition_id"] = task["condition_id"]
            result["reused"] = reused
            results.append(result)
        passed = all(r.get("model_valid") is True and r.get("public_check", {}).get("verdict") == "PASS"
                     for r in results)
        unknown = any(r.get("model_valid") is not True or r.get("execution_status") not in
                      {"OK", "COMPLETE", "COMPLETED", "SUCCESS"} or
                      r.get("public_check", {}).get("verdict") not in {"PASS", "FAIL"} for r in results)
        result = {"request_id": action.get("request_id"), "node_id": action.get("node_id"),
                  "design": design, "design_sha256": key, "results": results,
                  "scientific_result": not self.offline,
                  "execution_status": "OFFLINE_FIXTURE" if self.offline else "COMPLETED",
                  "model_valid": all(r.get("model_valid") is True for r in results),
                  "public_check": {"verdict": "UNKNOWN" if unknown else "PASS" if passed else "FAIL"},
                  "score": sum(r.get("public_check", {}).get("verdict") == "PASS" for r in results),
                  "usage": {"full_inputs": sum(not r["reused"] for r in results) if not self.offline else 0,
                            "fixture_inputs": sum(not r["reused"] for r in results) if self.offline else 0}}
        self.events.append({"group": group, "request_id": action.get("request_id"),
            "design_sha256": key, "conditions": [t.get("condition_id") for t in self.family],
            "scientific": not self.offline, "reused": [r["reused"] for r in results]})
        return result


def offline():
    # Implemented below once A/B source APIs are ready. Importing this module or
    # checking the gate never enters a scientific consumer or provider scope.
    from offline_checks import run_checks
    report = run_checks()
    report["gate"] = accounting_gate()
    report["recorded_at"] = datetime.now(timezone.utc).isoformat()
    report["available_bytes"] = __import__("os").statvfs(ROOT).f_bavail*__import__("os").statvfs(ROOT).f_frsize
    save(HERE / "offline-readback.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("offline", "gate", "child"))
    parser.add_argument("input", type=Path, nargs="?")
    args = parser.parse_args()
    if args.command == "child":
        if args.input is None:
            parser.error("child requires one host input path")
        result = child(args.input)
    else:
        result = accounting_gate() if args.command == "gate" else offline()
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
