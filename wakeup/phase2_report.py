"""Offline summary of the current Phase-2 journal; never edits raw runs or calls physics."""
import json
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(__file__).with_name("phase2")


def job_id(j):
    return f"{j['stage']}/{j['task']['id']}/{j['condition']}/r{j['rep']}"


def accounting(rows):
    responses = [r for r in rows if r["kind"] == "response"]
    requests = {r["id"]: r for r in rows if r["kind"] == "request"}
    unknown = {r["id"]: r for r in rows if r["kind"] == "UNKNOWN"}
    settled = {r["id"] for r in responses}
    usage = Counter()
    models = Counter()
    for r in responses:
        a = r["response"]; u = a["usage"]
        usage.update({k: u.get(k, 0) for k in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens")})
        usage["reasoning_tokens"] += u.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
        models[(a.get("model"), a.get("system_fingerprint"))] += 1
    return dict(requests=len(requests), settled_responses=len(responses), usage=dict(usage),
        actual_models=[dict(model=m, fingerprint=f, responses=n) for (m, f), n in models.items()],
        estimated_usd=sum(r.get("estimated_usd", 0) for r in responses),
        conservative_usd=sum(r.get("conservative_usd", 0) for r in responses),
        unknown=[dict(id=i, error=r["error"], reservation_usd=r["reservation_usd"]) for i, r in unknown.items()],
        unknown_reservation_usd=sum(r["reservation_usd"] for r in unknown.values()),
        inflight_ids=sorted(set(requests)-settled-set(unknown)),
        inflight_reservation_usd=sum(r["reservation_usd"] for i, r in requests.items() if i not in settled and i not in unknown))


def table(columns, rows):
    return "\n".join(["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"]*len(columns)) + " |"] +
        ["| " + " | ".join(str(v) for v in row) + " |" for row in rows])


def report():
    jobs = json.loads((OUT/"jobs.json").read_text())
    raw = (OUT/"results.jsonl").read_text()
    lines = raw.splitlines() if raw.endswith("\n") else raw.splitlines()[:-1]
    rows = [json.loads(s) for s in lines if s]
    manifest = {job_id(j): j for j in jobs}
    terminal = {r["job"]: r for r in rows if r["kind"] == "terminal"}
    events = defaultdict(list)
    for r in rows:
        if "job" in r: events[r["job"]].append(r)
    groups = []
    for stage, condition, rnd in sorted({(j["stage"], j["condition"], j["round"]) for j in jobs}):
        ids = [i for i, j in manifest.items() if (j["stage"], j["condition"], j["round"]) == (stage, condition, rnd)]
        ts = [terminal[i] for i in ids if i in terminal]
        records = [r for i in ids for r in events[i]]
        groups.append(dict(stage=stage, condition=condition, round=rnd, planned=len(ids), completed=len(ts),
            service_pass=sum(r.get("pass_") is True for r in ts),
            completed_without_service_pass=sum(r.get("pass_") is False and not r.get("error") for r in ts),
            errors=dict(Counter(r["error"] for r in ts if r.get("error"))),
            actions=sum(r.get("actions", 0) for r in ts), invalid_actions=sum(r["kind"] == "invalid_action" for r in records),
            accounting=accounting(records)))
    evaluations = [r for r in rows if r["kind"] == "evaluation"]
    science = {k: sum(r["result"].get("cost", {}).get(k, 0) for r in evaluations) for k in ("full", "numeric")}
    science["numeric"] += sum(r["kind"] == "math_point" for r in rows)
    science["logical_evaluations"] = len(evaluations)
    science["reused_evaluations"] = sum(bool(r["result"].get("reused")) for r in evaluations)
    gd = []
    for i, r in terminal.items():
        j = manifest[i]
        if j["stage"] not in ("G", "CG"): continue
        truth = j["task"]["private"]; diag = r.get("diagnosis") or {}
        acts = [a for a in events[i] if a["kind"] == "action"]
        global_no = diag.get("label") == "INFEASIBLE" and diag.get("scope") == "global"
        gd.append(dict(job=i, stage=j["stage"], condition=j["condition"], round=j["round"], state=truth["state"],
            feasible_truth=truth["truth"], service_pass=r.get("pass_") is True, error=r.get("error"), diagnosis=r.get("diagnosis"),
            false_global_exclusion=global_no and truth["truth"], true_global_exclusion=global_no and not truth["truth"],
            feasible_claim_without_pass=diag.get("label") == "FEASIBLE" and r.get("pass_") is not True,
            false_feasible_claim=diag.get("label") == "FEASIBLE" and not truth["truth"], missing_diagnosis=not bool(r.get("diagnosis")),
            final_modules={k: r.get("design", {}).get(k) for k in ("A", "B", "C", "D")},
            enabled_A=any(a["design"].get("A") for a in acts),
            reversed_A_after_failed_point=any(a["design"].get("A") and not a["result"]["pass_"] and not b["design"].get("A") for a, b in zip(acts, acts[1:])),
            added_modules_with_no_module_witness=truth["state"] == "S1" and any(r.get("design", {}).get(k) for k in ("A", "B", "C", "D")),
            actions=r.get("actions", 0), numeric_evaluations=r.get("numeric_evaluations", 0)))
    gs = []
    for stage, condition, state in sorted({(x["stage"], x["condition"], x["state"]) for x in gd}):
        ds = [x for x in gd if (x["stage"], x["condition"], x["state"]) == (stage, condition, state)]
        gs.append(dict(stage=stage, condition=condition, state=state, completed=len(ds),
            planned=sum(j["stage"] == stage and j["condition"] == condition and j["task"].get("private", {}).get("state") == state for j in jobs),
            **{k: sum(x[k] for x in ds) for k in ("service_pass", "false_global_exclusion", "true_global_exclusion", "feasible_claim_without_pass", "false_feasible_claim", "missing_diagnosis", "enabled_A", "reversed_A_after_failed_point", "added_modules_with_no_module_witness")}))
    a2 = []
    for i, r in terminal.items():
        j = manifest[i]
        if j["stage"] != "A2": continue
        a = r.get("answer") or {}; truth = j["task"]["private"]
        a2.append(dict(job=i, condition=j["condition"], submitted=bool(r.get("answer")), actual_best=truth["actual_best_index"],
            nominal_best=truth["nominal_best_index"], conflict=truth["conflict"], answer=a,
            correct=a.get("index") == truth["actual_best_index"] if a else None, error=r.get("error")))
    a3 = []
    for i, r in terminal.items():
        j = manifest[i]
        if j["stage"] != "A3": continue
        points = [x for x in events[i] if x["kind"] == "math_point"]
        a = r.get("answer") or {}; design = a.get("design", {})
        key = "main_length_mm" if j["task"]["family"].startswith("E") else "aux_length_mm"
        selected = next((x for x in points if abs(x["value"]-design.get(key, -1)) < 1e-9), None)
        best = max(points, key=lambda x:x["amplitude_V"]) if points else None
        a3.append(dict(job=i, condition=j["condition"], numerical_points=len(points), best_observed=best,
            submitted_value=design.get(key), selected_observed_amplitude_V=selected["amplitude_V"] if selected else None,
            selected_is_observed_best=selected["amplitude_V"] >= best["amplitude_V"]-1e-9 if selected else None,
            full_submitted=bool(a.get("result")), full_service_pass=a.get("result", {}).get("pass_"),
            full_terminal=a.get("result", {}).get("terminal"), full_base=a.get("result", {}).get("base"),
            full_slack=a.get("result", {}).get("slack"), reason=a.get("reason"), error=r.get("error")))
    pairs = []
    for task, condition in sorted({(j["task"]["id"], j["condition"]) for j in jobs if j["stage"] == "A1"}):
        rs = [terminal.get(f"A1/{task}/{condition}/r{rep}") for rep in (0, 1)]
        if not all(rs): continue
        pairs.append(dict(task=task, condition=condition, passes=[r.get("pass_") for r in rs],
            same_service_outcome=rs[0].get("pass_") == rs[1].get("pass_"),
            same_final_design=rs[0].get("design") == rs[1].get("design"), errors=[r.get("error") for r in rs],
            evaluable=not any(r.get("error") for r in rs)))
    valid_pairs = [p for p in pairs if p["evaluable"]]
    summary = dict(planned=len(jobs), completed=len(terminal), started=sum(any(r["kind"] == "start" for r in events[i]) for i in manifest),
        groups=groups, accounting=accounting(rows), science=science, G_by_state=gs, G_details=gd,
        A2_details=a2, A2_correct_position_counts=dict(Counter(str(x["actual_best"]) for x in a2)), A3_details=a3, A1_replicate_pairs=pairs,
        A1_replicate_summary=dict(planned_pairs=32, completed_pairs=len(pairs), evaluable_pairs=len(valid_pairs),
            interrupted_pairs=len(pairs)-len(valid_pairs), same_service_outcome=sum(p["same_service_outcome"] for p in valid_pairs),
            same_final_design=sum(p["same_final_design"] for p in valid_pairs)))
    (OUT/"summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    a = summary["accounting"]
    text = ["# 第二阶段实验已完成" if all(i in terminal for i in manifest) else "# 第二阶段实验实时汇总", f"已完成 {len(terminal)}/{len(jobs)} 个会话；汇总仅覆盖已保存记录。",
        "G/CG 全部是唤醒谐波题；S1当前分支可行，S2需A分支，S3全域无解但无公开界，S4全域无解且提供界。S3/S4不以PASS评价正确停止。",
        "A1/CA/J和A3最终提交使用原完整瞬态、真实采样与分类；A3数值代理仅为开路谐波幅值，代理最优不等于完整服务通过。A2只判断两个已测点的排序。",
        table(["阶段", "组", "轮", "完成/计划", "服务PASS", "动作", "错误会话"],
            [(g["stage"], g["condition"], g["round"], f"{g['completed']}/{g['planned']}", g["service_pass"] if g["stage"] != "A2" else "不适用", g["actions"], sum(g["errors"].values())) for g in groups]),
        f"实际已结算响应 {a['settled_responses']}；费率估算 USD {a['estimated_usd']:.8f}，不计缓存优惠 USD {a['conservative_usd']:.8f}；均非账单。UNKNOWN {len(a['unknown'])} 笔，预留 USD {a['unknown_reservation_usd']:.8f}；在途 {len(a['inflight_ids'])} 笔，预留 USD {a['inflight_reservation_usd']:.8f}。",
        "实际模型及token：`" + json.dumps(dict(models=a["actual_models"], usage=a["usage"]), ensure_ascii=False) + "`",
        "本journal新增执行量：`" + json.dumps(science) + "`。事前资格计算不混入此数。工具错误、输出截断和未提交单列，不能当物理失败。",
        table(["阶段", "组", "真值", "完成/计划", "服务PASS", "误称全域无解", "无解标签与真值一致", "声称可行但无通过记录", "无解题误称可行", "无主动诊断", "启用A", "失败后撤A"],
            [(g["stage"], g["condition"], g["state"], f"{g['completed']}/{g['planned']}", g["service_pass"], g["false_global_exclusion"], g["true_global_exclusion"], g["feasible_claim_without_pass"], g["false_feasible_claim"], g["missing_diagnosis"], g["enabled_A"], g["reversed_A_after_failed_point"]) for g in gs]),
        "错误排除只统计主动finish明确声明INFEASIBLE/global；预算用完不是宣称无解；没有diagnosis也不是主动选择UNSURE。FEASIBLE标签不能替代实际PASS，真实S3/S4上的FEASIBLE是错误可行判断。无解标签与真值一致只表示标签命中，不代表已证明；尤其S3必须审核reason是否有覆盖全域的真实推导，才可称有据停止。branch声明不自动评分：必须先核清它指哪个分支。撤A只是动作记录，不自动认定模型已否定整个分支。",
        "p_global/p_branch保留原始值，缺失不补。首轮合同未明确概率语义，不算Brier；后续明确合同也不与首轮混作置信度比较。",
        table(["A2会话", "实际较大点", "名义预测较大点", "回答", "正确", "置信度"],
            [(x["job"], x["actual_best"], x["nominal_best"], x["answer"].get("index"), x["correct"], x["answer"].get("confidence")) for x in a2]),
        "A2位置分布：`" + json.dumps(summary["A2_correct_position_counts"]) + "`。当前测点排序位置未平衡；即使全答对，也不能排除位置偏好，更不能据此宣称消除了名义模型锚定。完整理由保存在summary与原始journal。",
        table(["A3会话", "数学点数", "完整提交", "完整服务PASS", "首事件前储能V", "供电就绪s"],
            [(x["job"], x["numerical_points"], x["full_submitted"], x["full_service_pass"],
              (x["full_base"] or {}).get("storage_before_first_event_V"), (x["full_base"] or {}).get("cold_charge_ready_s")) for x in a3]),
        "A3实验提示本身要求最大化开路谐波幅值；因此结果只能证明该代理不等价于完整服务，不能解释为模型自主选错目标。开路响应近峰仍可能错过冷启动后的首事件；不能把未通过都归为浮点计算困难。",
        "第二轮共同接口明确概率语义，并公开数值优化的全部内部点；CG允许在原12次响应余额内追加finish-only回合，不增加科学点。G与CG按阶段分别报告，不能跨版本把停止率差异归为方法因果或将轮间差异单归于任务泛化；A1物理任务、设计信息和评价预算不变；共同终止字段澄清概率语义后独立重跑，并非所有提示逐字不变。",
        f"A1同任务同条件已完成重复对 {len(pairs)}/32；可评价 {len(valid_pairs)} 对、中断 {len(pairs)-len(valid_pairs)} 对；仅可评价对中服务结果一致 {sum(p['same_service_outcome'] for p in valid_pairs)}，最终设计完全一致 {sum(p['same_final_design'] for p in valid_pairs)}。OUTPUT_LENGTH等中断单列，不当正常未通过或一致结果；原始配对与错误保留。",
        "原始证据：results.jsonl；固定任务与计划：jobs.json；逐会话判断、理由、重复配对和费用明细：summary.json。此脚本只更新当前汇总，不改任何原始记录。"]
    (OUT/"README.md").write_text("\n\n".join(text) + "\n")
    return summary


if __name__ == "__main__":
    s = report()
    print(json.dumps(dict(completed=s["completed"], planned=s["planned"], accounting=s["accounting"], science=s["science"]), ensure_ascii=False))
