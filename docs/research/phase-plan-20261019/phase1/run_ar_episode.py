"""One preregistered phase-one episode; no automatic retry or new environment."""
from pathlib import Path
import argparse
import datetime
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
PLAN = ROOT / "docs/research/phase-plan-20261019/phase1"
PROFILE = Path("/Users/depengsu/.local/share/bf-campaign-20261019-s0/profile.json")
OUT = Path("/Users/depengsu/.local/share/bf-phase1-20261020/a/ar-service/pi-episode-001")
EPISODE = "method-study-phase1-ar-20261020-001"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--continue-pre-dispatch", action="store_true")
    args = parser.parse_args()
    continuation = OUT.exists()
    if continuation and not args.continue_pre_dispatch:
        raise FileExistsError("ORIGINAL_EPISODE_EXISTS_INSPECT_DO_NOT_RESAMPLE")
    if continuation and any((OUT / name).exists() for name in ["protocol.json", "gateway", "scientific", "episode-result.json"]):
        raise ValueError("ONLY_ZERO_REQUEST_PRE_DISPATCH_REPAIR_ALLOWED")
    free = shutil.disk_usage(ROOT).free
    if free < 10_900_000_000:
        raise RuntimeError("WHOLE_PHASE_STORAGE_HEADROOM_REQUIRED")
    slots = json.loads((PLAN / "idle-slot-receipt.json").read_text())
    if time.time() - slots["observed_unix"] > 300 or any(slots[k]["status"] != "idle" for k in ("A", "B")):
        raise ValueError("FRESH_IDLE_WORKER_SNAPSHOT_REQUIRED")
    profile = json.loads(PROFILE.read_text())
    for key, value in profile["paths"].items():
        os.environ["BF_" + key] = value
    os.environ.update(BF_RUNTIME_ROOT=profile["runtime_root"], BF_RUNTIME_CONFIG=profile["configuration"],
        BF_DEVELOPMENT_PROFILE=str(PROFILE), PI_CODING_AGENT_DIR=str(Path(profile["home"]) / "pi-config"),
        PYTHONDONTWRITEBYTECODE="1")
    sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
    from bfworld.agentlab.campaign20261019.phase1 import digest, encoded, file_hash, seal, tool_definition

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    runner = load("bf_phase1_runner", APP / "scripts/campaign_phase1.py")
    host = load("bf_phase1_frozen_ar", APP / "scripts/campaign_ar_service.py")
    contract = host.load_contract()
    if continuation:
        harness = OUT / "harness"
        built = json.loads((harness / "manifest.json").read_text())
        if file_hash(harness / "dist/phase1/episode.js") != built["compiled_sha256"]:
            raise ValueError("PRE_DISPATCH_HARNESS_DRIFT")
    else:
        harness, built = runner.build(OUT)
    database = Path(profile["home"]) / "state/workbench.sqlite"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        prior = {row["id"]: digest(dict(row)) for row in db.execute("SELECT * FROM model_requests ORDER BY created,rowid")}
    if continuation:
        original = json.loads((OUT / "preserved-ledger-before.json").read_text())
        if prior != original["rows"]:
            raise ValueError("PRE_DISPATCH_LEDGER_CHANGED")
    else:
        seal(OUT / "preserved-ledger-before.json", {"rows": prior, "count": len(prior)})
    service = "http://127.0.0.1:8980"
    operator = (Path(profile["home"]) / "state/operator.token").read_text().strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(path, body):
        request = urllib.request.Request(service + path, data=encoded(body),
            headers={"Authorization": "Bearer " + operator, "Content-Type": "application/json"})
        with opener.open(request, timeout=30) as response:
            return json.load(response)

    goal = (
        "在冻结的 A/R 无电池服务合同内，自行选择合法的储能/电压阈值及可执行程序，"
        "实际检验冷启动、周期采样、暗区新采样、历史保持、断档/时钟、事件、恢复上传、去重与新鲜度。"
        "先读取公开合同、候选语法和旧结果；至少选择并 check 一个由你提出的合法 candidate，"
        "再 submit 最终候选或有依据的 no-go，可同时保存部分修复候选。"
        "所有固定条件、物理参数、初始能量、服务期限和独立检查器保持不变。"
        "若合法空间不能兼顾要求，保留失败并说明所需的人类取舍，不擅自放宽需求。"
    )
    instruction = (
        "这是 public-development 的一个新 episode。你决定新的 D/program，Codex 只搭建语法、工具及检查器。"
        "唯一工具 bf_ar_service 返回结构化公开事实；inspect 的 contract/schema/history/bounds 可读取。"
        "bounds 是 Codex 辅助构造的必要界，不是你的自主发现或完整最终验收。"
        "最多 60 个供应商请求（含失败）、3 个不同候选（含被拒绝的候选）、累计 3600 秒；"
        "同一候选可复用结果。没有 bash、文件工具、原生工具或自动重试。"
        "必须以 submit 保存公开理由和 candidate 或 no-go 决策。submit 不是通过；独立验收由外部执行。"
        "保留所有失败、用量和费用，不宣称硬件合格、方法优势、未见迁移或 RSI。"
    )
    if continuation:
        record = json.loads((OUT / "owner.json").read_text())
        if record["episode"] != EPISODE:
            raise ValueError("ORIGINAL_EPISODE_IDENTITY_REQUIRED")
        owner = record["owner"]
        from bfworld.agentlab.campaign20261019.phase1 import ledger
        if ledger(database, owner)["requests"]:
            raise ValueError("PRE_DISPATCH_REPAIR_MUST_HAVE_ZERO_PROVIDER_ROWS")
    else:
        conversation = api("/api/conversations", {"text": goal, "operation_id": EPISODE, "defer_dispatch": True})
        owner = conversation["id"]
        seal(OUT / "owner.json", {"episode": EPISODE, "owner": owner, "new_original_episode": True,
            "old_owner_replacement": False, "conversation_model_dispatch": False})
    authority = api("/api/design-lab", {"action": "method_authorize", "session_id": owner,
        "task_id": EPISODE, "wall_authorization_text": "持续运行 不设置时间限制",
        "model_profile": "engineering-reasoning-compact-v2"})
    token = authority.pop("participant_token")
    seal(OUT / "authority.json", authority)
    bound = {str(APP / relative): file_hash(APP / relative) for relative in host.SOURCE_PATHS}
    for path in [APP / "scripts/campaign_phase1.py",
        APP / "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase1.py",
        APP / "packages/python/bfworld/src/bfworld/agentlab/provider.py",
        APP / "packages/python/bfworld/src/bfworld/agentlab/model_profile.py",
        APP / "configs/studies/phase1-20261020/shared/apparatus.v1.json",
        PLAN / "baseline-v2/manifest.json", PROFILE, Path(__file__),
        harness / "dist/phase1/episode.js", harness / "src/phase1/episode.ts",
        APP.parent / "pi-bf-aiot/package-lock.json",
        Path(contract["historical_raw"]["path"]) / "seal.json"]:
        bound[str(path)] = file_hash(path)
    bound.update(built["sdk_runtime_files"])
    protocol = {"schema_version": "bf-phase1-actual-ar-episode-v1", "id": EPISODE,
        "mode": "public-development", "baseline": contract["baseline"], "owner": owner,
        "goal": goal, "instruction": instruction, "tool": tool_definition(**host.tool_definition()),
        "ar_tool_script": str(APP / "scripts/campaign_ar_service.py"), "harness": str(harness),
        "output_root": str(OUT), "provider_service": service, "provider_database": str(database),
        "model_alias": "deepseek-flash", "allowed_reported_models": ["deepseek-flash"],
        "identity_scope": "Provider-reported alias only; no independently pinned weights/version",
        "bound_files": bound, "candidate_fields": ["candidate"], "candidate_actions": ["check", "submit"],
        "limits": {"model_requests": 60, "candidates": 3, "wall_seconds": 3600,
            "reserve_bytes": 10_000_000_000, "peak_remaining_bytes": 300_000_000,
            "output_bytes": 180_000_000, "tool_calls": 60, "tool_response_bytes": 96_000,
            "model_request_bytes": 2_000_000, "model_response_bytes": 2_000_000, "max_output_tokens": 32768},
        "storage_policy": {"whole_phase_peak_bytes": 900_000_000, "owner_retained_cap_bytes": 220_000_000,
            "gateway_stop_threshold_bytes": 180_000_000, "remaining_headroom_for_inflight_outputs_bytes": 40_000_000},
        "exposure": "All current tasks, prior failures and Codex apparatus/bounds are exposed public development; no heldout claim.",
        "assistance": {"Codex_grammar_tool_checker_bounds": "UNPRICED_NONZERO", "guidance_scope": "Goal and tool semantics; no D/program or decisive answer supplied in prompt"},
        "independent_final_evaluation": "Outside participant after submit; rehash raw/source, replay all fixed cases and separately assess any no-go bound.",
        "profile_scope": "Trusted S0 integration host calls frozen A API; A's CLI preparation profile is preserved and is not impersonated.",
        "automatic_retry": False, "native_dispatches": 0}
    protocol_path = OUT / "protocol.json"
    seal(protocol_path, protocol)
    lease = OUT / "slot-lease.json"
    seal(lease, {"status": "GRANTED", "episode": EPISODE, "expires": time.time() + 3600,
        "holders": ["S0", "Pi"], "other_executor_status": "idle", "worker_snapshot": slots})
    seal(OUT / "start.json", {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "protocol_sha256": digest(protocol), "free_bytes": shutil.disk_usage(ROOT).free,
        "before_provider_requests": 0, "no_new_environment": True, "no_native": True})
    runner.verify(protocol_path)
    sys.stdin = io.StringIO(token + "\n")
    try:
        result = runner.run_episode(protocol_path, lease)
    finally:
        sys.stdin = sys.__stdin__
        token = None
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        current = {row["id"]: digest(dict(row)) for row in db.execute("SELECT * FROM model_requests")}
    unchanged = all(current.get(key) == value for key, value in prior.items())
    seal(OUT / "preserved-ledger-after.json", {"original_count": len(prior), "original_rows_unchanged": unchanged,
        "new_rows": len(current) - len(prior), "free_bytes": shutil.disk_usage(ROOT).free})
    if not unchanged:
        raise ValueError("ORIGINAL_LEDGER_DRIFT")
    return 0 if result["status"] == "PARTICIPANT_SUBMITTED_REQUIRES_EXTERNAL_EVALUATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
