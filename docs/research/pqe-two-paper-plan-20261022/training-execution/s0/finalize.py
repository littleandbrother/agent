"""Seal the completed finite package; no dispatch, replay, backup or Git operation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os

R = Path(__file__).resolve().parents[5]
BASE = R / "docs/research/pqe-two-paper-plan-20261022"
OUT = BASE / "training-execution"
HERE = OUT / "s0"
APP = R / "workbench/bf-campaign-s0-20261019/battery-world"
PACKAGE = "BF-PQE-TRAINING-EXECUTION-20261024-001"


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def ref(path):
    data = path.read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))


def seal():
    assert not (HERE / "final-readback.json").exists(), "ALREADY_SEALED_NO_REPEAT"
    v = read(HERE / "verification.json")
    a = read(OUT / "a/FINAL-READBACK.json")
    b = read(OUT / "b/FINAL-READBACK.json")
    papers = read(OUT / "b/PAPER-PREFIX-READBACK.json")
    batch = read(HERE / "batch-result.json")
    assert v["status"] == "TARGETED_FINITE_RUN_VERIFIED" and batch["complete"]
    assert a["status"] == "PASS_INDEPENDENT_SAVED_SERVICE_READBACK"
    assert b["status"] == "PASS_INDEPENDENT_METHOD_READBACK_NO_QUALIFIED_DESCENDANT"
    assert v["scope_restoration_values"]["status"] == "PRIOR_ABSENT_SCOPE_RESTORED_VERIFIED"
    assert len(b["skipped_child_cells"]) == 4 and v["actual_full_inputs"] == 2
    # Bind the newly appended paper segments only; do not rescan historical prefixes.
    increments = []
    for item in papers["papers"]:
        assert item["prefix_preserved"]
        path = R / item["path"]
        with path.open("rb") as stream:
            stream.seek(item["prior_prefix_bytes"])
            segment = stream.read()
        assert path.stat().st_size == item["final_bytes"]
        assert b"24 October 2026" in segment and len(segment) < 5000
        increments.append(dict(path=str(path), offset=item["prior_prefix_bytes"],
            bytes=len(segment), sha256=hashlib.sha256(segment).hexdigest(),
            historical_prefix_review="B receipt accepted; not rescanned by S0"))
    at = datetime.now(timezone.utc).isoformat()
    summary = dict(execution_closed=True, actual_training_chain_completed=True,
        qualified_descendants=0, child_isolated_cells_executed=0,
        child_isolated_cells_unexecuted=4, adoption="RETAIN_ORIGINAL_PARENT",
        outer_episodes=4, training_rounds=4, nested_training_solves=8,
        parent_control_solves=2, raw_proposals=4, autonomous_revisions=4,
        materialized_or_rejected_versions=8,
        actual_full_inputs=v["actual_full_inputs"], full_wall_s=v["full_wall_s"],
        full_result_evaluations=v["full_result_evaluations"], exact_reuses=v["exact_reuses"],
        cheap_checks_including_software_direct_path=v["low_cost_checks"],
        independent_saved_result_reviews=7, provider_requests=v["provider_requests"],
        input_tokens=v["input_tokens"], output_tokens=v["output_tokens"],
        rate_estimate_usd=v["rate_estimate_usd"], invoice_claim=False,
        new_billing_unknown=0, original_r11_unchanged=True,
        active_credentials_grants_inflight=0, scope_restored=True,
        research_reclaimed_bytes=0, new_backups_environments_worktrees=0,
        root_init_run=False, commit_or_push=0, whole_project_complete=False)
    report = """# 实际训练执行贯通续包：有限执行完成

BF-PQE-TRAINING-EXECUTION-20261024-001 / BFA-095。两组实际走通模型自动改代码→原完整开发结果→Update→反馈→自主修订，但都没有形成满足采用规则的后代。四个后代隔离续评格未执行，保留原父。完成的是本次有限工单；整个研究项目、自动方法收益与完整 LC 服务尚未完成。

共同接入在正式形成前做了两次有据修订：嵌套 solve 继承同一 owner 的真实余额与绝对截止时间，额度取原单次上限和形成剩余额度之较小值，并保留一次反馈修订机会；公共工具/目录加入后再投影最终请求。一次保存故障的软件替身检查实际穿过 host 的 train/solve/初始 Update/结果 Update/反馈/修订/下一轮，真实模型与科学调用均0。首次替身 provenance 被既有门禁拒绝的错误保留，未改正式历史。正式运行冻结后没有源码救援或实验重试。

两组使用同一原始父、22条公开历史、38个公共来源、原开发任务与预算。形成公开 registry/pages/7份实际请求中未发现原隔离输入、结果或退出摘要；最终请求为69,712–78,920字节，低于原220,000字节上限。续评沿用此前固定、对学习器隔离的任务；协调者已见旧结果，因此不称新盲测。

| 条件 | 实际训练与行为 | 采用结果 |
|---|---|---|
| H2 普通自动编辑 | 2原提案+2自主修订，4版本；前2版完整训练，后2版达到预定训练轮数上限。Update写入失败/活动/来源，但原可执行Generate只消费failure_branch；LC两轮均选择joint-source→joint-reserve，完整服务仍FAIL。DOOR初态PASS后正确停止。 | 无完整服务增益，无合格后代。 |
| H4 归因自动编辑 | 2原提案+2自主修订，4版本。首版Update改变记录但LC行动相同；首修订在训练前被原HOOK_PRIVATE_NAME合同拒绝。第二原提案修改H-STOP，在原父PASS的DOOR上继续行动：第1新输入域有效PASS6，第2收到6但违反cam压力角模型域，结果UNKNOWN(MODEL_DOMAIN)，Update为DOMAIN_UNKNOWN。末修订通过软件筛选但达到轮数上限。 | 原采用规则REGRESSION_ON_PARENT_PASS拒绝；域外结果不能称有效服务FAIL/PASS，也不是费用UNKNOWN。 |

两组各2实际训练轮/4嵌套solve。形成结束冻结后合并两组公共训练历史，原父据此重新决策：DOOR初态Update后正确Stop/PASS6、0行动；LC四评价精确复用422→380→422→380，原cold-start/continuous/dark/freshness四门仍FAIL。无后代格不以父代替，不据此声称后代迁移失败或稳定相对优势。开发者先前整体LC工程PASS仅作工程证据。

全包2新完整动态输入、9.229476792秒数值墙钟；14次完整结果评价含12次精确复用。50次便宜检查含软件贯通与筛选；A退出另7次保存结果只读审查（6唯一结果，首份因review包装器键错误多读1次，错误保留），无新增科学运行。7请求全部SETTLED，输入120,736/输出108,763 token，固定费率估算USD0.1667364，非账单。0新费用UNKNOWN、0在途，旧R11原UNKNOWN/null usage/完整预留整行未变。

A独立核验原服务、事件、CRC、期限、次序与能量闭合；B独立核验实际代码/状态消费、候选合同、采用原因和两稿新增短段。58项冻结源码绑定不变。owner凭据和有效grant清零、study过期。runtime-closeout的scope_restored=null是原设置不存在这一原值：runtime-open.prior_scope=null，退出后数据库该设置行确实不存在；scope-readback.json已明确记录，并非未确认布尔值。

原环境与源树复用，无新备份/环境/工作树/commit/push/全仓init。当前包存储与生成物见postflight.json和generated-file-inventory.json；保留上限150MB按分配上限计。本研究包主动回收0B，不把后台空间差值或此前第17批248.488MB处理窗口收益再计一次。第17批维护复核仍未证明有可整删的GB级闲置树，独有overlay/当前依赖/原证据继续保留。

定向验证已完成：verification.json；独立出口：../a/FINAL-READBACK.json、../b/FINAL-READBACK.json；实际轨迹：batch-result.json、episodes/*/formation.json、resource-ledger.json。没有从本次有限负结果推出硬件、一般学习失败、RSI或整个项目完成结论。首次真实训练反馈里程碑已单次送达；最终完成信号另行单次发送授权审查。
"""
    (HERE / "REPORT.md").write_text(report)
    feature_path = R / "feature_list.json"
    features = read(feature_path)
    feature = features["bf_pqe_training_execution_20261024"]
    assert feature["status"] == "in-progress"
    feature.update(status="complete", completed_at=at, result=summary,
        next_handoff="Finite package complete, no qualified descendant and four child cells unexecuted. Send one distinct completion signal to authorized reviewer; no automatic new matrix or old quota.",
        evidence=[str(x.relative_to(R)) for x in [HERE/"REPORT.md", HERE/"verification.json", HERE/"scope-readback.json", HERE/"batch-result.json", HERE/"resource-ledger.json", OUT/"a/FINAL-READBACK.json", OUT/"b/FINAL-READBACK.json", HERE/"final-readback.json"]])
    save(feature_path, features)
    save(APP / "project/features/BFA-095-pqe-training-execution/feature.yaml", feature)
    state = read(BASE / "execution-state.json")
    assert state["package"] == PACKAGE
    state.update(status="CLOSED_FINITE_PACKAGE_NO_QUALIFIED_DESCENDANT", completed_at=at,
        result=summary, next_action=feature["next_handoff"], report=str(HERE/"REPORT.md"))
    save(BASE / "execution-state.json", state)
    project = APP / "PROJECT.yaml"
    text = project.read_text()
    assert "active_feature: BFA-095-pqe-training-execution\nactive_feature_status: in-progress" in text
    text = text.replace("active_feature: BFA-095-pqe-training-execution\nactive_feature_status: in-progress", "active_feature: BFA-095-pqe-training-execution\nactive_feature_status: complete", 1)
    text = text.replace("next_milestone: PQE-training-execution", "next_milestone: PQE-training-execution-exit-review", 1)
    project.write_text(text)
    handoff = """\n\n## 2026-10-24 — 实际训练与自主修订贯通，有限采用负结果完成

BFA-095/BF-PQE-TRAINING-EXECUTION-20261024-001完成。两组真实自动代码→原完整结果→Update→反馈→修订；每组2提案+2修订/2训练轮/4嵌套solve。H2两训练版LC相同行动且无服务增益；H4首版无增益、首修订HOOK_PRIVATE_NAME拒绝，第二raw修改H-STOP后在原父PASS DOOR继续行动，第1域有效PASS6、第2MODEL_DOMAIN/UNKNOWN，按REGRESSION_ON_PARENT_PASS拒绝，末修订达到轮数上限。无合格后代、4子隔离格未执行；合并训练历史后父实际重新决策，DOOR正确Stop/PASS6，LC4精确复用仍四门FAIL。未把域UNKNOWN当有效服务失败/费用UNKNOWN，也不称新盲测或一般学习失败。

2new完整/9.229476792s、14评价含12精确复用、50cheap（含软件贯通）及A退出7次保存结果只读审查；7SETTLED、120736in/108763out、费率估算USD0.1667364，0新费用UNKNOWN/在途。58冻结源码、旧R11整行不变；owner凭据/grant清零/study过期；scope原无设置行，null原值已恢复并现场确认。A/B独立出口与两稿实际短段齐备。原环境源树、无备份/工作树/commit/push/全init，本研究主动回收0B；第17批248.488MB不重计，当前维护复核无新已证可整删GB树。

报告training-execution/s0/REPORT.md与verification/final-readback/postflight。有限工单complete，整个项目未完成，无合格后代/LC完整服务仍未解。首次训练里程碑已送一次，最终另发本包唯一BF_COMPLETE；不自动补组/重形成/扩大矩阵或复用旧配额，授权reviewer独立衔接后续。
"""
    for path in [R/"progress.md", R/"session-handoff.md", APP/"docs/PROGRESS.md", APP/"docs/SESSION-HANDOFF.md"]:
        with path.open("a") as stream:
            stream.write(handoff)
    inventory = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            stat = path.stat()
            inventory.append(dict(path=str(path.relative_to(OUT)), logical_bytes=stat.st_size,
                allocated_upper_bound_bytes=max(4096, stat.st_blocks*512)))
    save(HERE / "generated-file-inventory.json", dict(at=at, scope="current package only; metadata, not a content copy", files=inventory, new_backups_environments_worktrees=0))
    fs = os.statvfs(R)
    post = dict(at=datetime.now(timezone.utc).isoformat(), available_bytes=fs.f_bavail*fs.f_frsize,
        retained_logical_bytes=sum(x["logical_bytes"] for x in inventory),
        retained_allocated_upper_bound_bytes=sum(x["allocated_upper_bound_bytes"] for x in inventory),
        snapshot_excludes_inventory_and_final_receipt_overhead=True,
        retained_cap_bytes=150000000, estimated_peak_bytes=1000000000,
        required_available_bytes=11000000000, research_reclaimed_bytes=0,
        prior_storage_batch17_not_recounted=True)
    assert post["available_bytes"] >= post["required_available_bytes"]
    assert post["retained_allocated_upper_bound_bytes"] < post["retained_cap_bytes"]-1000000
    save(HERE / "postflight.json", post)
    receipt = dict(package=PACKAGE, at=at, status="COMPLETE_INDEPENDENT_EXIT_REVIEW",
        result=summary, storage=post, paper_increments=increments,
        evidence=[ref(path) for path in [HERE/"REPORT.md", HERE/"verification.json", HERE/"scope-readback.json", HERE/"batch-result.json", HERE/"resource-ledger.json", OUT/"a/FINAL-READBACK.json", OUT/"b/FINAL-READBACK.json", OUT/"b/PAPER-PREFIX-READBACK.json", HERE/"postflight.json", HERE/"generated-file-inventory.json"]])
    save(HERE / "final-readback.json", receipt)
    print(json.dumps(dict(status=receipt["status"], result=summary, storage=post), ensure_ascii=False))


if __name__ == "__main__":
    seal()
