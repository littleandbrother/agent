"""Forensic metadata/corrected claims only. No parser repair or dispatch."""
import re
from common import *


def run():
    target=HERE/'comparison-validity.json'
    if target.exists():raise RuntimeError('ONE_FINAL_VALIDITY_CORRECTION_ONLY')
    rejected=[]
    for path in sorted((HERE/'episodes').glob('*/callbacks/*/callback-result.json')):
        value=load(path)
        if value.get('payload',{}).get('error')!='TOOL_NOT_ALLOWED':continue
        rawpath=path.parent/'pi-public.jsonl.gz'
        with gzip.open(rawpath,'rt') as stream:records=[json.loads(x) for x in stream if x.strip()]
        answer=next(x for x in records if x.get('type')=='assistant_public')
        raw=''.join(x['text'] for x in answer['content'])
        try:names=[x['name'] for x in json.loads(raw)['tool_calls']]
        except (ValueError,KeyError):names=re.findall(r'invoke name="([a-z_]+)"',raw)
        rejected.append(dict(episode=path.parents[2].name,callback=path.parent.name,tool_names=names,
            original_raw=ref(rawpath),original_callback=ref(path),raw_response_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            provider_usage=value['usage'],classification='SETTLED_PROVIDER_RESPONSE_REJECTED_BY_LOCAL_TOOL_WHITELIST',
            host_tools_executed_from_this_batch=0))
    assert len(rejected)==4 and sum(r['tool_names'].count('calculate') for r in rejected)==6
    report_path=OUT/'REPORT.md';prior_report=ref(report_path);text=report_path.read_text()
    finding=dict(at=now(),status='BLOCKED_COMMON_CALCULATOR_INTERFACE',package=PACKAGE,
        finite_real_model_execution_completed=12,physical_whole_service_first_design_PASS=12,
        matched_common_calculator_comparison_valid=False,accounting_and_frozen_science_audit='PASS',
        cause='S0 reused the original strict model_format parser whose JSON and DSML whitelist only allows public_object. The new advertised candidate_facts/calculate names never reached the new host handlers.',
        frozen_formatter=ref(BASE/'codebt-zeroapi/s0/model_format.py'),frozen_provider=ref(HERE/'provider.py'),
        rejected_callbacks=rejected,rejected_calculate_calls=6,collaterally_rejected_public_object_calls=1,
        actual_model_candidate_facts_calls=0,actual_model_calculate_calls=0,
        strategy_internal_calculator_access=True,unequal_actual_common_tool_access=True,
        responsibility='S0 direct integration and end-to-end gate omission; not a scientific model failure.',
        withdrawn_claims=['The three actual agents had usable equal public calculator tools.',
            'This completed a valid same-capability test of joint/recursive incremental value.',
            'Equal first-pass results establish no recursive advantage, or fewer C requests show an advantage.'],
        retained_facts=['All12 actual model episodes ended with one design passing the original3 services.',
            'No automatic J or C proposal selected; holder off in all final designs.',
            'Developer-selected actual companion before/after remained FAIL in all3 conditions.',
            'All21 provider requests settled; no change to old2026 rows/UNKNOWN/auth snapshots.'],
        sources_left_frozen=True,experiments_retried=0,additional_paid_requests=0,
        resource_stop='12/12 episode identities and24 direct software cases used. No automatic rescue, quota transfer or old episode restart.',
        concrete_next_scope=['In a separately authorized direct-path correction, add strict JSON/DSML validation for exactly public_object/candidate_facts/calculate with their bounded arguments.',
            'Use these existing saved genuine outputs for zero-API replay through the whole parser-to-dispatch route; prove calculators execute and retain page/token/action budgets.',
            'Only after that gate, a separately scoped fresh comparison can answer the matched research question; current matrix remains immutable and invalid for that inference.'],
        report_before_correction=prior_report)
    save(target,finding)
    text=text.replace('# 同底座联合修改与配套递推：有限开发诊断','# 联合/递推有限包：执行完成，公平比较被接口缺口阻断')
    paragraphs=text.split('\n')
    for i,line in enumerate(paragraphs):
        if line.startswith('包 `'):
            paragraphs[i]=f'包 `{PACKAGE}`。12/12 条真实模型执行结束，均在首设计通过原三工况；计费/冻结科学源审计 PASS。**相同能力的比较未完成：公共计算器接口被本地解析器阻断。**'
        if line.startswith('所有组获得相同原始事实'):
            paragraphs[i]='协议要求所有组获得相同原始事实、条件计算器和合法整套编辑权限，以及同一已暴露历史。实际事实与合法设计权限在场，但模型计算调用被旧解析器拒绝；J/C 内部策略能用计算器，所以共同工具的实际可达性没有实现。以下服务结果保留为执行事实，不能作有效同能力消融。'
        if line.startswith('算参数与联合修改：'):
            paragraphs[i]=line+' 这是开发者/内部工具路径的支持，不能替代真实模型共有计算器的接通验证。'
        if line.startswith('正式轨迹没有选中递推候选'):
            paragraphs[i]='正式轨迹没有选中 J/C 自动候选，未获得真实模型动态机制样本。加上计算器接口阻断，本包不能有效判别递推独立价值，也不能用这些平局证明递推无价值。'
        if 'A只做一次' in line:pass
    text='\n'.join(paragraphs)
    gap='''## B 最终复核发现的实质缺口

S0 复用的 `codebt-zeroapi/s0/model_format.py` 在 JSON 与 DSML 两条路径都只允许 `public_object`。新增宿主虽声明了 `candidate_facts/calculate`，合法模型调用仍在解析阶段被挡住。4次已结算回包合计6次 calculate 和同批1次 public_object 未执行；所有原始文本、FORMAT_ERROR 和费用保留在 `s0/comparison-validity.json` 的绑定记录。

这是 S0 的接入与端到端检查遗漏。不能把本地拒绝算成模型/方法科学失败。最初“同底座比较完成、未见递推增益”的表述在此撤回；现有结果只能说明12个实际模型最终各找到一个原任务成功方案。A 的服务读回支持这些原消费者结果，B 的方法读回指出公平比较缺口，二者范围不同。

当前12个episode身份和24个直接软件case已用完，不修冻源后补跑、不救组、不转配额。下一步具体是严格接通三种公共工具的 JSON/DSML 参数校验，用本批已存真实回包做零API端到端复验，随后才可在另行授权的新范围做有效比较。此次未进行这些新检查或新增实验。

'''
    text=text.replace('## 三层增量',gap+'## 三层观察（不作有效增量归因）')
    text=text.replace('独立 A 服务读回与 B 方法/费用读回将作为最终索引附加。','独立 A 服务读回与 B 方法/费用读回，以及此处接口阻断后的结论更正，见最终索引。')
    report_path.write_text(text)
    finding['report_after_correction']=ref(report_path);save(target,finding)
    table=load(OUT/'trajectory-table.json')
    for row in table:row.update(comparison_validity='BLOCKED_COMMON_CALCULATOR_INTERFACE',incremental_value_claim_allowed=False)
    save(OUT/'trajectory-table.json',table)
    print(json.dumps(dict(event='COMPARISON_VALIDITY_BLOCKED',callbacks=4,calculate=6,public_object_collateral=1,extra_dispatch=0)),flush=True)


if __name__=='__main__':run()
