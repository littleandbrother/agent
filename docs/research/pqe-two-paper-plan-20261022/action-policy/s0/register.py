"""Declare the bounded action-policy package before implementation or dispatch."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os

R = Path(__file__).resolve().parents[5]
APP = R / "workbench/bf-campaign-s0-20261019/battery-world"
BASE = R / "docs/research/pqe-two-paper-plan-20261022"
OUT = BASE / "action-policy"
WORK = BASE / "联合搜索算法改写与前瞻比较_20261024.md"


def main():
    path = R / "feature_list.json"
    data = json.loads(path.read_text())
    key = "bf_pqe_action_policy_20261024"
    assert key not in data, "ALREADY_REGISTERED"
    prior = data["bf_pqe_training_execution_20261024"]
    assert prior["status"] == "complete"
    fs = os.statvfs(R)
    free = fs.f_bavail * fs.f_frsize
    assert free >= 11200000000
    authority = dict(prior["authority"])
    authority["new_workorder"] = dict(path=str(WORK), sha256=hashlib.sha256(WORK.read_bytes()).hexdigest())
    at = datetime.now(timezone.utc).isoformat()
    feature = dict(schema_version="bf-research-feature-v1", id="BFA-096-pqe-action-policy",
        package="BF-PQE-ACTION-POLICY-20261024-001", owner="campaign-s0", status="in-progress", declared_at=at,
        authority=authority,
        hypothesis="With complete decision code visible and a common autonomous joint-search parent, automatic program edits may improve complete service or total cost on four prospectively sealed cases.",
        paper_claim="Actual executable algorithm, consumed state and selected action changes, complete service/correct stop and all formation/training/solve cost within four pre-specified cases.",
        falsifier="No action change, copied seen parameters only, no full-service or total-cost gain, parent-PASS regression, or equally effective strong parent; any outcome closes the finite package.",
        owned_paths=dict(S0=["action-policy/{s0,shared}/", "pqe20261024policy/{__init__,adapter}.py", "root feature/progress/handoff and APP mirrors"],
            A=["action-policy/a/"], B=["action-policy/b/", "pqe20261024policy/{parent,projection,training}.py", "two canonical paper increments and new paper1 full draft/result index"]),
        schema_changes=["Versioned common model-decision parent, direct full decision-code projection and prospective diagnostic admission distinct from final adoption; no scientific, legal-domain, service or execution privilege change."],
        targeted_tests=["Once explicit software-substitute real ask/generate/full-result/update/next-decision host check", "Shared parent two actual public development solves", "Both original and autonomous revised version each one training round", "Four sealed cases x three independent conditions", "One concentrated independent service and algorithm/cost exit readback"],
        negative_controls=["PASS initial correct stop", "No prospective task/input/result in formation or parent development", "Same parent/history/model/tools/rights/budgets", "No no-child fallback", "No new missing usage exception", "No outcome-driven task or source replacement"],
        command="rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B docs/research/pqe-two-paper-plan-20261022/action-policy/s0/run_policy.py run",
        output_artifact=str(OUT),
        cost_cap=dict(new_full_inputs=60, full_each_s=120, full_wall_s=7200, outer_episodes=16,
            provider_requests=228, usd=100, low_cost=120, model_slots=3,
            formation=dict(requests=30, tools=60, wall_s=2400, usd=15, output_tokens=393216),
            solve=dict(requests=12, tools=24, wall_s=900, usd=5, output_tokens=131072),
            parent_development_candidates_each=2, training_candidates_each_task=2,
            test_candidates_each=3, raw_proposals_each=1, autonomous_revisions_each=1,
            pre_formation_common_revisions=2, post_formation_rescue=0,
            new_engineering_scan_native_hardware_environments_worktrees_backups=0),
        storage=dict(available_bytes=free, estimated_peak_additional_bytes=1200000000,
            required_available_bytes=11200000000, retained_allocated_upper_bound_cap_bytes=200000000,
            output_directory=str(OUT)),
        claim_boundary="Constructed nominal simulation; joint-learning cross-condition adaptation only, not zero-LC-feedback transfer, broad superiority, independent G repetitions, RSI or hardware. Shared developer parent change is not learned gain.",
        stop_condition="One finite ordered package; at most one justified direct check and two pre-formation common fixes. No result rescue, task replacement, extra matrix, old quota or missing-usage exception. Final adoption requires all four complete service and no parent-PASS regression; if parent also all-pass, total child cost including learning must be lower.",
        next_handoff="Seal tasks before parent implementation. Run two actual parent development solves, send unique baseline milestone, directly form/train/test. End one independent exit, full paper1 draft/index, distinct final completion.")
    for name in ("a", "b", "shared", "s0"):
        (OUT/name).mkdir(parents=True, exist_ok=True)
    data[key] = feature
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")
    mirror = APP/"project/features/BFA-096-pqe-action-policy/feature.yaml"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(json.dumps(feature, ensure_ascii=False, indent=2)+"\n")
    project = APP/"PROJECT.yaml"
    text = project.read_text().replace("active_feature: BFA-095-pqe-training-execution\nactive_feature_status: complete\nprevious_active_feature: BFA-094-pqe-lc-service-learning\nnext_milestone: PQE-training-execution-exit-review", "active_feature: BFA-096-pqe-action-policy\nactive_feature_status: in-progress\nprevious_active_feature: BFA-095-pqe-training-execution\nnext_milestone: PQE-action-policy", 1)
    assert "active_feature: BFA-096-pqe-action-policy" in text
    project.write_text(text)
    state = dict(package=feature["package"], feature=feature["id"], owner="campaign-s0",
        status="DECLARED_WAITING_PROSPECTIVE_TASK_SEAL", started_at=at, authority=authority,
        output=str(OUT), previous_package=prior["package"], next_action=feature["next_handoff"])
    (BASE/"execution-state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n")
    note = "\n\n## 2026-10-24 — 强通用共同父与前瞻联合算法比较启动\n\nBFA-096/BF-PQE-ACTION-POLICY-20261024-001按既有直接人类持续授权及新有限工单接续。A先事前封存2DOOR+2LC/各最多1初态，不找解换题；B任务封存后复用原强通用实际模型路径为同一可编辑父，完整决策代码内联。S0先父两公开开发solve，再普通/归因各1提案+1自主修订且两版各1训练轮，冻结后三组四题独立续评；诊断准入与最终采用分开。60新完整/7200s、16外层episode/228请求/USD100、120cheap、最多2前形成共同修订；峰值1.2GB/保留200MB，入场"+str(free)+"B>11.2GB。原环境源树无备份/工作树/全init/commit/push；结果后不救组，旧包不重开，LC不称零反馈迁移。先基线里程碑单次发送后直接训练，结束集中A/B读回与完整论文一初稿/结果索引。\n"
    for item in [R/"progress.md", R/"session-handoff.md", APP/"docs/PROGRESS.md", APP/"docs/SESSION-HANDOFF.md"]:
        with item.open("a") as stream:
            stream.write(note)
    (OUT/"shared/OWNERSHIP.json").write_text(json.dumps(dict(package=feature["package"], declared_at=at,
        ownership=feature["owned_paths"], one_active_implementation_per_owner=True,
        no_additional_workers=True, no_new_backup_environment_worktree=True), ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(dict(status=state["status"], available_bytes=free, feature=feature["id"])))


if __name__ == "__main__":
    main()
