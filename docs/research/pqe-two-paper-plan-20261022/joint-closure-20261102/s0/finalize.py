"""Close the finite feature after two independent saved-artifact readbacks."""
from collections import Counter
from common import *


def run():
    marker=HERE/'final-closeout.json'
    if marker.exists():raise RuntimeError('ONE_FINAL_CLOSEOUT_ONLY')
    audit=load(HERE/'postflight-audit.json');assert audit['status']=='PASS'
    matrix=load(HERE/'comparison-result.json');assert matrix['completed']==12 and matrix['unrun_trajectories']==0
    validity=load(HERE/'comparison-validity.json');assert validity['status']=='BLOCKED_COMMON_CALCULATOR_INTERFACE'
    reads={name:ref(path) for name,path in dict(A=OUT/'a/final-service-readback.json',B=OUT/'b/final-method-cost-readback.json').items()}
    review_values={k:load(v['path']) for k,v in reads.items()}
    for k,v in review_values.items():
        assert str(v['status']).startswith('PASS'),(k,v['status'])
    require_sources(load(OUT/'shared/protocol.json'))
    current=capacity();stats=Counter(p.suffix or '<none>' for p in OUT.rglob('*') if p.is_file())
    save(HERE/'generated-file-inventory.json',dict(at=now(),extensions=dict(stats),capacity=current,
        largest=sorted([dict(path=str(p),bytes=p.stat().st_size) for p in OUT.rglob('*') if p.is_file()],key=lambda r:r['bytes'],reverse=True)[:12],
        new_backups=0,new_environments=0,new_worktrees=0,whole_source_or_runtime_copies=0,
        canonical_output_compression='Exact complete byte readback before removing newly owned uncompressed outputs.'))
    rowtable=load(OUT/'trajectory-table.json');recursion=sum(r['recursive_selected'] for r in rowtable)
    resources=audit['resources'];provider=audit['provider']
    evidence=dict(report=str(OUT/'REPORT.md'),final_index=str(OUT/'FINAL-INDEX.md'),protocol=str(OUT/'shared/protocol.json'),
        matrix=str(HERE/'comparison-result.json'),trajectory_table=str(OUT/'trajectory-table.json'),
        audit=str(HERE/'postflight-audit.json'),integration_review=str(HERE/'integration-review.json'),
        actual_companion_consequences=str(HERE/'actual-companion-consequences.json'),
        independent_readbacks=reads,figure=str(OUT/'figures/comparison-summary.pdf'),
        source_amendment=str(HERE/'source-amendment.json'),comparison_validity=str(HERE/'comparison-validity.json'),
        generated_file_inventory=str(HERE/'generated-file-inventory.json'))
    usage=dict(new_full_inputs=resources['full_new'],new_full_wall_s=resources['full_wall_s'],
        logical_inputs=resources['logical_inputs'],logical_phases=resources['phases'],exact_reused_inputs=resources['exact_reuse'],
        cheap_numeric=resources['cheap_numeric_total'],cheap_by_owner=resources['cheap_by_owner'],software_cases=24,
        software_failed_cases=6,pre_case_parse_failures=1,postprocessing_launch_failures=1,independent_readbacks=2,
        provider_episodes=provider['episodes'],provider_requests=provider['requests'],provider_tokens=provider['tokens'],
        settled_charge_upper_bound_usd=provider['settled_charge_upper_bound_usd'],new_unknown=0,
        original_unknown_reserved_usd=audit['old_unknown_reserved_usd'],real_model_selected_recursive_candidates=recursion,
        rejected_calculate_calls=6,local_parser_rejected_paid_callbacks=4,collateral_public_object_rejected=1,
        actual_model_calculator_calls=0,valid_matched_comparison=False)
    root=load(ROOT/'feature_list.json');feature=root['bf_pqe_joint_closure_20261102']
    feature.update(status='blocked',phase='FINITE_EXECUTION_CLOSED_COMMON_CALCULATOR_INTERFACE_BLOCKED',closed_execution_at=now(),
        command=f'rtk proxy env PYTHONDONTWRITEBYTECODE=1 {PYTHON} -B "{HERE / "verify_readonly.py"}"',
        evidence={**feature['evidence'],**evidence},actual_usage=usage,
        limitations=['Previously exposed development history; no blind transfer, independent model seed or statistical claim.',
            'All12 first whole-service PASS design1 is a service fact; calculator parser rejects shared tool calls, so matched comparison is invalid.',
            '6 calculate calls and1 collateral read across4 settled replies were locally rejected; no claim of recursive benefit or lack of value.',
            'A4 and S02 original case failures plus B pre-case parse failure retained; no reruns above24 direct cases.',
            'No whole-repository init/health claim; no commit or push.'],
        blocking_reason='S0 inherited public_object-only JSON/DSML parser; advertised common calculate/candidate_facts handlers were unreachable from actual model requests.',
        next_handoff='Finite execution closed, fair comparison blocked. A separately scoped strict common-tool parser correction and zero-API saved-output replay must pass before any fresh authorized comparison. No old experiment, cleanup, manuscript, automation, hardware or paid continuation.')
    root['updated_at']=now();save(ROOT/'feature_list.json',root)
    save(APP/'project/features/BFA-101-pqe-joint-closure/feature.yaml',feature)
    state=load(HERE/'execution-state.json');state.update(status='FINITE_EXECUTION_CLOSED_COMPARISON_BLOCKED',closed_at=now(),actual_usage=usage,
        evidence=evidence,capacity=current,next_action=feature['next_handoff'],
        execution_gate=dict(provider_ready=False,development_full='COMPLETED_18_LOGICAL_12_NEW',
            comparison='BLOCKED_COMMON_MODEL_CALCULATOR_PARSER_INTERFACE',new_episode_quota=0))
    save(HERE/'execution-state.json',state);save(BASE/'execution-state.json',state)
    text=f'''\n\n## 2026-11-02 — 联合/递推有限执行关闭，研究判别被接口阻断\n\nBFA-101 / {PACKAGE}：原2族×3工况、同一真实 deepseek/deepseek-flash high，12/12实际模型轨迹结束且首评全服务PASS。该服务事实有效，但研究feature保持blocked：S0继承的JSON/DSML解析器只准public_object，4份已结算回包中的6次calculate及同批1次读页被整批拒绝，实际模型公共计算器调用0，J内部策略却能使用。因此公平共同工具前提未实现，撤回“同底座判别完成/无递推增益”结论。正式选中递推候选{recursion}；开发两个旧前缀联合候选PASS，真实配套前后均三FAIL，这些仍只是具体执行事实。\n\n{resources['full_new']}新full/{resources['full_wall_s']:.6f}s，{resources['logical_inputs']}逻辑（{resources['phases']}）、{resources['exact_reuse']}复用、cheap{resources['cheap_numeric_total']}（{resources['cheap_by_owner']}）。24登记软件case保留A4/S02失败，B预case parse1、末端只读表名错误1亦保留；无第25项/后见救组/补跑。{provider['requests']}SETTLED、tokens {provider['tokens']}、费用估计上界USD{provider['settled_charge_upper_bound_usd']:.7f}。原2026计费行/auth哈希及两UNKNOWN/nullusage/预留USD{audit['old_unknown_reserved_usd']:.7f}不变。A服务范围PASS，B带实质接口限制完成唯一读回；不是无条件协议PASS。owner凭据/grant关闭、scope恢复、本包服务停止。\n\n报告 {OUT/'REPORT.md'}；实质缺口 {HERE/'comparison-validity.json'}；只读账目/源核证 {HERE/'verify_readonly.py'}。当前可用{current['available_bytes']}B，保留分配上界{current['allocated_upper_bound_bytes']}B；主动清理释放0B，无备份/新环境/工作树/commit/push/全init或健康声明。有限执行closed、研究判别blocked；待单独范围修三公共工具严格解析并用已有真实输出做零API端到端复验，再决定新比较。旧研究/清理/论文/自动化/硬件均不自动恢复。最终唯一BF_COMPLETE报告BLOCKED出口并停止。\n'''
    for path in (ROOT/'progress.md',ROOT/'session-handoff.md',APP/'progress.md'):
        with path.open('a') as stream:stream.write(text)
    (OUT/'FINAL-INDEX.md').write_text(f'''# BFA-101 最终出口：有限执行已关闭，公平比较 BLOCKED\n\n12/12实际模型轨迹均首设计全服务PASS，但本地解析器拒绝了6次calculate（4份已结算回包），共同公共计算器前提未实现。**不能据此判别递推独立价值。** 原科学结果和费用有效保留，冻结源未热改，未补跑。\n\n- 更正后的完整报告：[REPORT.md](REPORT.md)。\n- 实质缺口、原回包SHA与撤回声明：[comparison-validity.json](s0/comparison-validity.json)。\n- 逐轨迹服务事实、真实设计与费用：[trajectory-table.json](trajectory-table.json)。\n- A唯一服务读回：[final-service-readback.json](a/final-service-readback.json)，{review_values['A']['status']}；仅支持服务范围。\n- B唯一方法/费用读回：[final-method-cost-readback.json](b/final-method-cost-readback.json)，{review_values['B']['status']}；指出计算器实质限制，不能当全面协议PASS。\n- 计费/源/关闭审计：[postflight-audit.json](s0/postflight-audit.json)，PASS仅属这些范围。\n- 实际配套前后完整后果：[actual-companion-consequences.json](s0/actual-companion-consequences.json)。\n- 接口拒绝与执行事实图：[PDF](figures/comparison-summary.pdf)，源数据 [summary-data.json](figures/summary-data.json)。\n\n最终可用{current['available_bytes']/1e9:.2f}GB，保留分配上界{current['allocated_upper_bound_bytes']/1e6:.2f}MB；主动清理释放0B，无新备份/环境/工作树。原实验、失败和费用保留。\n\n有限执行停止，研究feature blocked。后续须在单独范围严格接通三公共工具JSON/DSML并用既有真实输出零API复验，之后才可准入新的授权比较；不自动恢复旧实验、清理、论文、定时或付费任务。\n''')
    save(marker,dict(at=now(),status='FINITE_EXECUTION_CLOSED_COMPARISON_BLOCKED',package=PACKAGE,resources=usage,independent_readbacks=reads,
        evidence=evidence,capacity=current,automatic_continuation=False))
    print(json.dumps(dict(event='FINAL_CLOSED',usage=usage,capacity=current)),flush=True)


if __name__=='__main__':run()
