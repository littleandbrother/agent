"""Shared, non-mutating contract for natural-language task assessment.

An assessment is a proposal. Only the existing task-definition action freezes
requirements; an unsupported design request remains visible with its gaps.
"""
from copy import deepcopy
import hashlib
import json

VERSION = 'bf-task-assessment-v1'
INTENTS = ('audit', 'reproduce', 'reconstruct', 'complete', 'optimize', 'new_design')
DOMAINS = ('mechanical', 'power', 'pcb', 'firmware', 'sensing', 'radio', 'receiver', 'assembly')
SCOPES = ('single_module', 'coupled', 'end_to_end')
SCHEMA = {
    'version': VERSION,
    'intent': list(INTENTS), 'scope': list(SCOPES), 'domains': list(DOMAINS),
    'fields': {
        'intent': 'One intent; use audit for diagnosis/review, reproduce for matching published results, reconstruct for missing models, complete for missing parts, optimize for improving existing designs, new_design for a new device.',
        'scope': 'Requested design scope. Supporting checks do not automatically expand it to the whole device.',
        'domains': 'Only engineering domains needed for the requested work.',
        'goal': 'One concise user-facing goal.',
        'requirements': '[{text,source_quote}]; quote must occur verbatim in the user request. Do not convert a suggested solution into a mandatory requirement.',
        'design_variables': '[string]; choices left to BF, excluding fixed user constraints.',
        'missing_inputs': '[{question,blocks_execution:boolean}]; ask only what affects scope or an engineering decision.',
        'assumptions': '[string]; proposed starting conditions, not confirmed requirements.',
        'plan': '[{action,purpose,output,check}]; 3-6 concrete steps including a cheap overall feasibility check for coupled/end-to-end tasks.',
        'acceptance': '[string]; observable checks for the requested goal, no invented numerical targets.',
        'deliverables': '[string]; outputs appropriate to the requested task.',
        'feasibility': 'unknown | plausible | conflict; conflict needs an explicit contradiction in the request.',
    },
    'execution_profiles': {
        'node-reference-v1': 'Nominal piezo modal source + average conversion + host C event load + storage SPICE + digital receiver. Actual PMIC/target MCU/native PCB require additional adapters.',
        'curve-reproduction-v1': 'Comparison of two source-bound tabulated curves.',
        'pcb-completion-v1': 'Review existing native PCB checks; editing is not qualified by this profile.',
        'p01-digital-v1': 'Existing P01 circuit, nRF52832/S132 and eight engineering gates.',
    },
}


def schema():
    return deepcopy(SCHEMA)


def prompt():
    example = {'intent':'audit','scope':'single_module','domains':['power'],'goal':'简短目标',
        'requirements':[{'text':'用户要求','source_quote':'用户原句中的连续片段'}],
        'design_variables':['允许调整的内容'],'missing_inputs':[{'question':'需要确认的条件','blocks_execution':True}],
        'assumptions':[],'plan':[{'action':'动作','purpose':'目的','output':'产物','check':'检查方式'}],
        'acceptance':['可检查的完成条件'],'deliverables':['实际交付物'],'feasibility':'unknown'}
    return ('你是 BF 的任务评估入口。只输出一个完整 JSON 对象。下面的例子仅规定结构，替换所有值。'
            '所有字段直接位于根对象；不输出 fields、execution_profiles、schema 等包装。plan 输出 3 到 6 步。'
            '每题独立评估，不默认继承 P01、无线、MCU、PCB 或压电节点。依据用户请求确定范围，必要的辅助检查另写入 plan。'
            '单模块指一个工程工作目标（例如固件含通信代码）；联合任务明确涉及互相影响的工程对象；整链任务要求设备整体或交付。'
            '只写用户确实要求的硬条件；未知工况在 missing_inputs 中提出，候选方案放 assumptions 或 design_variables。'
            'requirements.source_quote 必须逐字摘自用户原句。用户允许自由选择的器件不能变成硬约束。'
            '不要自行增加数值验收门限。联合/整机方案先安排低成本可行性检查。'
            '意图仅选 audit（审查诊断）、reproduce（复现已给结果）、reconstruct（重建缺失工程）、complete（补全已有）、optimize（优化已有）、new_design（新设计）。'
            '多阶段请求按当前第一阶段分类，后续阶段写进 plan。'
            'scope 仅选 single_module/coupled/end_to_end。domains 从 '+','.join(DOMAINS)+' 中选择。'
            'feasibility 仅选 unknown/plausible/conflict；只有明确相互矛盾的条件才用 conflict。\n'
            '输出结构：'+json.dumps(example,ensure_ascii=False))


def validate(request, value):
    if not isinstance(request, str) or not request.strip():
        raise ValueError('TASK_REQUEST_REQUIRED')
    if not isinstance(value, dict):
        raise ValueError('TASK_ASSESSMENT_OBJECT_REQUIRED')
    for field, options in [('intent', INTENTS), ('scope', SCOPES),
                           ('feasibility', ('unknown', 'plausible', 'conflict'))]:
        if value.get(field) not in options:
            raise ValueError('TASK_ASSESSMENT_ENUM:' + field)
    domains = value.get('domains')
    if not isinstance(domains, list) or not domains or len(set(domains)) != len(domains) or any(d not in DOMAINS for d in domains):
        raise ValueError('TASK_ASSESSMENT_DOMAINS')
    if not isinstance(value.get('goal'), str) or not value['goal'].strip():
        raise ValueError('TASK_ASSESSMENT_GOAL')
    for name in ('design_variables', 'assumptions', 'acceptance', 'deliverables'):
        rows = value.get(name)
        if not isinstance(rows, list) or any(not isinstance(r, str) or not r.strip() for r in rows):
            raise ValueError('TASK_ASSESSMENT_LIST:' + name)
    if not value['acceptance'] or not value['deliverables']:
        raise ValueError('TASK_ASSESSMENT_EXIT_REQUIRED')
    if not isinstance(value.get('requirements'), list) or not value['requirements']:
        raise ValueError('TASK_ASSESSMENT_REQUIREMENTS')
    for r in value['requirements']:
        if not isinstance(r, dict) or not r.get('text') or not isinstance(r.get('source_quote'), str) or not r['source_quote'] or r['source_quote'] not in request:
            raise ValueError('TASK_REQUIREMENT_SOURCE_MISMATCH')
    if not isinstance(value.get('missing_inputs'), list):
        raise ValueError('TASK_ASSESSMENT_MISSING_INPUTS')
    for r in value['missing_inputs']:
        if not isinstance(r, dict) or not r.get('question') or type(r.get('blocks_execution')) is not bool:
            raise ValueError('TASK_ASSESSMENT_QUESTION')
    plan = value.get('plan')
    if not isinstance(plan, list) or not 3 <= len(plan) <= 6 or any(not isinstance(r, dict) or any(not isinstance(r.get(k), str) or not r[k].strip() for k in ('action', 'purpose', 'output', 'check')) for r in plan):
        raise ValueError('TASK_ASSESSMENT_PLAN')
    result = deepcopy(value)
    result['schema_version'] = VERSION
    result['request_sha256'] = hashlib.sha256(request.encode()).hexdigest()
    result['state'] = 'REQUIREMENTS_CONFLICT' if value['feasibility'] == 'conflict' else 'INPUT_REQUIRED' if any(r['blocks_execution'] for r in value['missing_inputs']) else 'READY_FOR_CAPABILITY_MATCH'
    result['requirements_frozen'] = False
    return result
