"""One compact source-bound report; no model or scientific execution."""
from common import *
from verify_readonly import verify


def run():
    audit=verify();save(HERE/'postflight-audit.json',audit)
    matrix=load(HERE/'comparison-result.json');trajectories=matrix['trajectories']
    rows=[];chains=[]
    for t in trajectories:
        ledger=t['model_ledger'];model_calls=ledger['requests'] if ledger else 0
        token_rows=[json.loads(r['usage']) for r in ledger['rows'] if r['usage']] if ledger else []
        recursive=[h for h in t['history'] if h.get('closure_chain')]
        choices=[h['origin'] for h in t['history']]
        row=dict(ident=t['ident'],family=t['family'],condition=t['condition'],repeat=t['repeat_identifier'],status=t['status'],
            first_pass=t['first_all_service_PASS_design_slot'],designs=t['logical_evaluated_designs'],
            calls=model_calls,prompt_tokens=sum(x['prompt_tokens'] for x in token_rows),completion_tokens=sum(x['completion_tokens'] for x in token_rows),
            estimated_usd=sum(r['charged'] for r in ledger['rows']) if ledger else 0.,
            recursive_selected=len(recursive),origins=choices,
            final_design=t['final']['design'] if t['final'] else None,
            new_full=t['new_resources']['full_attempts'],reuse=t['new_resources']['cache_reuses'],wall_s=t['wall_s'],
            final_burden=t['history'][-1]['complexity'] if t['history'] else None)
        rows.append(row)
        for h in recursive:chains.append(dict(trajectory=t['ident'],slot=h['slot'],design=h['design'],closure_chain=h['closure_chain'],statuses=h['statuses'],result=h['result']))
    save(OUT/'trajectory-table.json',rows);save(OUT/'selected-companion-chains.json',chains)
    report=['# 同底座联合修改与配套递推：有限开发诊断',
        '',f"包 `{PACKAGE}`。完成 {matrix['completed']}/12 条真实模型轨迹；未运行 {matrix['unrun_trajectories']} 条。审计 {audit['status']}。",'',
        '本包精确保留 DOOR/LC 原任务、各三工况和六个共同初态。三组均由同一 API 模型 `deepseek/deepseek-flash`、high 推理配置实际决策；底层权重未披露。314159/271828 是重复标识与控制器种子，不能称模型可控随机种子。',
        '所有组获得相同原始事实、条件计算器、合法整套编辑权限以及已经暴露的旧开发历史。J 是可拒绝的同父联合候选；C 仅添加候选事实驱动的配套扩展。首个完整三工况通过即停止。',
        '', '## 三层增量', '']
    for condition in ('G','G+J','G+J+C'):
        subset=[r for r in rows if r['condition']==condition]
        report.append(f"- {condition}：{sum(r['first_pass'] is not None for r in subset)}/{len(subset)} 通过；逻辑设计数 {[r['designs'] for r in subset]}；真实请求 {sum(r['calls'] for r in subset)}；选中递推候选 {sum(r['recursive_selected'] for r in subset)}。")
    report.extend(['',
        '算参数与联合修改：两个旧失败前缀的联合候选均通过原三工况，C 的相同候选精确复用。这证明新增联合路径在这些已见前缀上可用，并不证明模型自主学会联合策略。',
        '配套递推：实际生成过 holder 职责变化→CONSUMPTION 义务→读取配套修改→候选重检。开发者选择该既有候选执行时，修改前后仍均为三工况 FAIL。不能以静态链或日志变化宣称完整服务收益。',
        ('正式轨迹没有选中递推候选，因此本包未获得真实模型的动态机制样本；G+J+C 的普通成功不计为递推增益。' if not chains else f'正式轨迹选中 {len(chains)} 个带递推链的候选，逐条后果见 selected-companion-chains.json；因果解释须结合其真实行动与完整结果，不能只看最终标签。'),
        '这是已见任务、已暴露历史上的开发机制诊断。不能作未见迁移、统计优势、不可行证书、最优性、硬件或 RSI 证据。共同历史包含旧合法大电容成功，所有组三方都可复用；首通过指标受这种暴露影响。',
        '', '## 逐轨迹结果', '',
        '| 族 | 条件 | 重复标识 | 首通过设计 | 已评设计 | 请求 | 新 full / 复用 | 递推选中 | 终态 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---|'])
    for r in rows:
        report.append(f"| {r['family']} | {r['condition']} | {r['repeat']} | {r['first_pass'] or '—'} | {r['designs']} | {r['calls']} | {r['new_full']} / {r['reuse']} | {r['recursive_selected']} | {r['status']} |")
    resources=audit['resources'];provider=audit['provider'];tokens=provider['tokens']
    report.extend(['','## 真实设计与部件负担','',
        '完整候选、设计 diff、父状态、生成来源和完整后果保留在 `s0/trajectories/*/history.json`，汇总为 `trajectory-table.json`。以下是最终选定/最后已评方案的实际参数，不作人为总复杂度评分。','',
        '| 轨迹 | C (F) | PV (cm²) | 改字段数 | 新部件 | 生成来源 |','|---|---:|---:|---:|---|---|'])
    for r in rows:
        b=r['final_burden'] or {};report.append(f"| {r['ident']} | {b.get('capacitance_f','—')} | {b.get('pv_area_cm2') or '—'} | {b.get('changed_field_count','—')} | {','.join(b.get('added_components',[])) or '无'} | {','.join(r['origins']) or '无'} |")
    report.extend(['','## 费用、资源与失败','',
        f"新完整执行 {resources['full_new']} 个单工况，实际 {resources['full_wall_s']:.6f}s；逻辑评价 {resources['logical_inputs']}（开发 {resources['phases'].get('development',0)}，正式 {resources['phases'].get('comparison',0)}）；精确复用 {resources['exact_reuse']}。共同初态直接引用，不重跑、不占新设计槽。",
        f"便宜数值输入 {resources['cheap_numeric_total']}/120：A/B/S0={resources['cheap_by_owner']}，真实几何 miss 包含在内；精确 memo 和结构检查单列在各 owner 计量事件。24 个登记软件 case：A 2/6、B 8/8、S0 8/10；另 B 有一次进入 case 前的 parse 启动错误。",
        '120 为包总额，启动登记分配 A24/B24/S072；冻结宿主实际以 S0=72 为更严停止门，未热改或转移额度。',
        'A 旧四项失败来自过小光照分段 guard，修订后由 S0 实际 LC 路径覆盖；S0 两项失败来自错误拼接父 ID 和越域测试值。失败原记录不覆盖，修订原因/独立核证在 integration-review.json。未增加第25项软件检查。',
        f"真实模型请求 {provider['requests']}，全部状态 {provider['statuses']}。prompt/completion/total/reasoning tokens = {tokens.get('prompt_tokens',0)}/{tokens.get('completion_tokens',0)}/{tokens.get('total_tokens',0)}/{tokens.get('reasoning_tokens',0)}；本地结算估计/上界 USD {provider['settled_charge_upper_bound_usd']:.7f}，不冒供应商发票金额。",
        f"启动前的 {audit['old_model_requests']['count']} 条完整请求行和原 authorizations 哈希不变。两条旧 UNKNOWN 的原始行、null usage 与 USD {audit['old_unknown_reserved_usd']:.7f} 全额预留不变；新请求没有缺失 usage。",
        f"新 owner 凭证关闭：{audit['credentials_closed']}；原预算 scope 恢复；本包自启服务停止。新包保留分配占用上界 {audit['capacity']['allocated_upper_bound_bytes']/1e6:.2f}MB，当前可用 {audit['capacity']['available_bytes']/1e9:.2f}GB。未新增环境、worktree 或备份。此次是研究执行包，清理释放 0B；前后磁盘可用量差不能冒充本包回收。",'',
        '## 证据和复核入口','',
        '- 协议：`shared/protocol.json`；登记预算：`shared/registration.json`。',
        '- 实际前后链：`s0/actual-companion-consequences.json`；联合四单元：`s0/development-results.json`。',
        '- 正式结果：`s0/comparison-result.json`；逐轨迹设计/来源/费用：`trajectory-table.json`。',
        '- 完整费用、原行哈希、资源和关闭证据：`s0/postflight-audit.json`。',
        '- 只读核证（零模型/零消费者）：', '',
        '```sh',f'rtk proxy env PYTHONDONTWRITEBYTECODE=1 {PYTHON} -B "{HERE / "verify_readonly.py"}"','```','',
        '本包到此停止；不自动恢复旧学习、第二篇论文、清理、自动化或硬件任务。独立 A 服务读回与 B 方法/费用读回将作为最终索引附加。',''])
    (OUT/'REPORT.md').write_text('\n'.join(report))
    print(json.dumps(dict(event='REPORT',audit=audit['status'],completed=matrix['completed'],requests=provider['requests'],tokens=tokens,usd=provider['settled_charge_upper_bound_usd'],capacity=audit['capacity'])),flush=True)


if __name__=='__main__':run()
