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
    return ('你是 BF 的任务评估入口。用户只给出简短要求。输出一个 JSON 对象，严格使用下列字段；'
            '先理解用户意图和范围，再定义任务和方案。明确固定条件与设计自由；未知工况保持待定。'
            '接受任务不等于已经具备执行器，不能为了匹配已有案例改变用户目标。无需 Markdown。\n' +
            json.dumps(SCHEMA, ensure_ascii=False, sort_keys=True))


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
