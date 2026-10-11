#!/usr/bin/env python3
"""Package public, source-bound review evidence; no model/native dispatch."""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

APP = Path(__file__).resolve().parents[2]
STAGE = APP.parent
ROOT = STAGE.parents[1]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.contracts import sha, sealed

OUT = APP / 'docs/agentlab/refactor-r3-r5-20261012'
OLD = APP / 'docs/agentlab/refactor-r0-r2-20261011'
DEST = ROOT / 'workbench/review-packages/BF_Agent_R3-R5_System_Review_20261012-v3.zip'
PLAN = ROOT / 'workbench/review-packages/BF_Agent_Refactor_Implementation_Plan_20261011.md'
AUDIT = OUT / 'system-audit-1791740938815627000'
CONTENT = {}


def add(path, name):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError('REVIEW_FILE_NOT_REGULAR:' + str(path))
    data = path.read_bytes()
    if name in CONTENT and CONTENT[name] != data:
        raise ValueError('REVIEW_COLLISION:' + name)
    CONTENT[name] = data


def tree(directory, prefix):
    for path in sorted(directory.rglob('*')):
        if path.is_file() and not path.is_symlink() and not {'node_modules', '.pi', '__pycache__', '.git'} & set(path.parts):
            add(path, prefix + '/' + str(path.relative_to(directory)))


def json_key_audit(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in ('api_key', 'apikey', 'operator_token', 'participant_token', 'tooltoken', 'tool_token', 'reasoning_content'):
                raise ValueError('PRIVATE_FIELD_IN_REVIEW:' + key)
            json_key_audit(child)
    elif isinstance(value, list):
        for child in value:
            json_key_audit(child)


def main():
    closeout = json.loads((OUT / 'closeout.json').read_text())
    assert closeout['R3']['full_exit'] == 'NOT_MET'
    assert closeout['R4']['fresh_confirmation_verdict'] == 'REJECT'
    assert not closeout['R5']['complete']
    add(APP / 'docs/agentlab/DESIGN-LAB-R3-R5-20261012.md', '01_IMPLEMENTATION.md')
    add(APP / 'docs/agentlab/SYSTEM-REVIEW-20261012.md', '02_SYSTEM_REVIEW.md')
    add(PLAN, '03_APPROVED_PLAN.md')
    add(APP / 'docs/agentlab/DESIGN-LAB-R0-R2-20261011.md', 'reference/PRIOR_R0_R2.md')
    for filename in ('closeout.json', 'validity-amendments.json', 'R5-descendant-blocked.json',
                     'deferred-placeholders-1791740844349903000.json', 'current-targeted-tests.log'):
        add(OUT / filename, 'evidence/' + filename)
    for directory in ('environment-1791740435574814000',
        'method-study-77a587a1bb6ee37dd97726d8', 'method-study-followup-d98c5124f7b02b89f532eea5',
        'method-study-finite-A-a080ab993be83df898c4', 'method-study-finite-A-03e829fdf3861737fe38',
        'method-study-finite-B-134a541e8fa66a1c754c', 'physical-readiness-1791738323981611000',
        'system-audit-1791740938815627000', 'deliveries'):
        tree(OUT / directory, 'evidence/' + directory)
    for filename in ('preservation-final-1791742252986032000.json', 'live-readback-1791742227101316000.json'):
        add(OLD / filename, 'evidence/preservation/' + filename)
    tree(OLD / 'verification/native-environment-1791741319469001000', 'evidence/application-init')
    add(OLD / 'trial/C-digital-design.zip', 'deliveries/C-prior-F0-digital-design.zip')
    # Historical withdrawn PASS/failed records are provided alongside amendment;
    # they are neither current authority nor silently removed.
    for directory in ('environment-1791738019954513000', 'environment-1791738066130701000',
            'environment-1791739329751894000', 'environment-1791740348895775000',
            'system-audit-1791739639072070000'):
        for name in ('qualification.json', 'report.json'):
            path = OUT / directory / name
            if path.is_file():
                add(path, 'evidence/historical-amended/' + directory + '/' + name)

    sources = list((APP / 'packages/python/bfworld/src/bfworld/agentlab/design_lab').glob('*.py'))
    sources += list((APP / 'scripts/design_lab').glob('*.py'))
    sources += list((APP / 'tests/agentlab').glob('test_design_lab*.py'))
    sources += [APP / 'tests/agentlab/test_design_execution.py']
    base = APP / 'packages/python/bfworld/src/bfworld/agentlab'
    for name in ('context.py', 'model_profile.py', 'budget_policy.py', 'launcher.py',
            'harness.py', 'chat.py', 'store.py', 'literature_acceptance.py', 'runtime_config.py',
            'runtime_resources.py', 'resource_manifest.py'):
        if (base / name).is_file(): sources.append(base / name)
    sources += [STAGE / 'pi-bf-aiot/packages/bf-agent/src' / name for name in
        ('design-task.ts', 'method-task.ts', 'extensions/bf-design.ts', 'chat-product.ts')]
    sources += [APP / 'project/features/BFA-035-dot-integration-pilot/design-lab-r3-r5.json']
    if (APP / 'configs/reference_cases/design-lab').is_dir():
        sources += [p for p in (APP / 'configs/reference_cases/design-lab').rglob('*') if p.is_file()]
    index = []
    for path in sorted(set(sources)):
        name = 'source/' + str(path.relative_to(STAGE))
        add(path, name)
        functions = []
        if path.suffix == '.py':
            node = ast.parse(path.read_text())
            functions = [{'name': n.name, 'line': n.lineno, 'kind': type(n).__name__}
                         for n in ast.walk(node) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        index.append({'original_path': str(path), 'archive_path': name, 'sha256': sha(path), 'definitions': functions})
    CONTENT['SOURCE_INDEX.json'] = (json.dumps(index, ensure_ascii=False, indent=2) + '\n').encode()

    CONTENT['00_READ_FIRST.md'] = '''# BF Agent 最新实施与系统审查包

日期：2026-10-12。本包可以上传到 Gemini、DeepSeek 或其他网页版进行明确源码审查。

先读 01_IMPLEMENTATION.md，再读 02_SYSTEM_REVIEW.md；03_APPROVED_PLAN.md 是原计划，不是完成证明。
04_REVIEW_PROMPT.md 给出独立审查要求。SOURCE_INDEX.json 记录当前源码绝对路径、函数行号和 SHA。
source/ 为当前源码；evidence/*/frozen-controller/ 为实验实际版本，不能把当前版本反向当作旧运行版本。

有限 C/A/B 数字链成立；完整 R3 未完成；R4 真实候选追加确认 REJECT；R5 后代受前提阻止，物理 NOT_TESTED。
十原论文阶段文件包 10/10，完整数字产品 0/10；不是十次完整整机试验都失败。

每份 A/B 工程包有自身 manifest、源、编译、执行、独立检查和公开理由；旧 C 包同时提供。
公共材料包含已结束实验的独立序列，后续不能再将这些序列称为未见测试。
historical-amended/ 中旧错误/过时结论保留，读取 validity-amendments.json 后才能解释。

包含本轮公开轨迹、测试日志和费用事实；不包含私人密钥、SDK 私人会话、隐藏思维链、全仓库、全部论文 PDF、供应商账单或外部依赖二进制。
复制本包不等于可以在任意机器立即运行；工具链、SDK、macOS sandbox、授权及源数据外部路径见协议/报告。
不要为文件检查重发模型或重跑旧原生作业。README/报告中所有 PASS 均有声明范围。
MANIFEST.json 提供成员摘要；读取核对回执 PACKAGE_READBACK-v3.json 在原输出目录。该外置回执记录最终 ZIP 摘要，避免循环哈希。
'''.encode()
    CONTENT['04_REVIEW_PROMPT.md'] = '''# 独立架构与研究审查要求

请依据包中真实源码和实验回执进行审查。01、02 是待审主张，03 是计划。不要直接接受作者总结；优先核对具体协议、输入/程序/构建/执行/检查/采用/交付和 SHA。

1. 从使用者角度评价当前真正可执行的任务、原 UI/产物入口、状态表达、人工前提及阶段交付。
2. 逐层检查 Prompt、Skills、插件、MCP/CLI/HTTP 工具、状态/Memory、上下文投影和主控。区分安装、可调用、实际使用、功能通过。
3. 核查 C 主控与 A/B/方法 CLI 的控制器一致性、operation 身份、CAS、UNKNOWN、恢复/重试/重复派发风险。21 个占位撤回只解决了什么？哪些恢复保证尚缺故障注入？
4. 核查有限源与真实编译逻辑：标签泄漏、免费电流、状态/电压反馈、样本覆盖、请求/RX、时间网格、数值回执和历史撤回。数值账本是否被误称为独立物理模型？
5. 审查目标编译与共享主机逻辑边界：ARM .o、ELF/HEX、真实外设、功耗、RF、BOM/PCB/装配分别有什么证据？不要把某层通过提升为其他层。
6. 从费用/上下文数据判断可优化原因；保守费用、缓存估算、供应商实付分别处理。统计不足时不要宣称压缩因果收益。
7. 审查 Pi 方法候选与 5 对/追加 3 对：预注册采用规则、正确性收益 0、顺序/cache、小样本、获取费。追加 REJECT 后不能事后混合改变判定。实际 skill 注入是否等于产品发布？
8. 审查十论文逐篇模型域与有效功能门；区分更新后旧绑定失效、尚未检查、不可评价、实际失败及文件 PASS。请指出最有价值且可执行的下一工作。
9. 从论文角度列出当前能支持与不能支持的主张、数据污染/新任务需求、模型后台 pin 局限、外部介入及成本缺口。不得凭架构新名字授予新颖性或 RSI。
10. 输出按严重性排序的具体问题，给出文件、函数、行号、可重现反例、影响范围、最小修复和验收条件；无法确认时列明缺少的证据。

不要推荐大幅重做 UI、另建平台或全量重算。禁止清费账、清 UNKNOWN、换 owner、把未测试填成 PASS，或要求更改冻结科学语义来过门。允许候选被拒绝。
请分别评价使用体验、工程成熟度、科学有效性、Agent 自主性、方法收益和物理验证；不合成一个总体完成百分比。
'''.encode()

    private_token = Path('/Users/depengsu/.local/share/bf-agent-runtime/workbench/state/operator.token').read_bytes().strip()
    for name, data in CONTENT.items():
        if private_token and private_token in data:
            raise ValueError('PRIVATE_TOKEN_IN_REVIEW:' + name)
        if name.endswith('.json'):
            json_key_audit(json.loads(data))
        elif name.endswith('.jsonl'):
            for line in data.decode().splitlines():
                if line: json_key_audit(json.loads(line))
    manifest = {'schema_version': 'bf-public-review-package-v1',
        'source_worktree': str(STAGE), 'scope': closeout['claim'],
        'members': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for name, data in sorted(CONTENT.items())},
        'private_runtime_included': False, 'hidden_reasoning_included': False,
        'models_dispatched': 0, 'native_solves': 0}
    CONTENT['MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    if DEST.exists(): raise ValueError('REVIEW_ARCHIVE_ALREADY_EXISTS; inspect rather than overwrite')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(DEST, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(CONTENT.items()): archive.writestr(name, data)
    with zipfile.ZipFile(DEST) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(CONTENT)
        for name, data in CONTENT.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == hashlib.sha256(data).hexdigest()
    receipt = {'schema_version': 'bf-public-package-readback-v1', 'path': str(DEST),
        'zip_sha256': sha(DEST), 'zip_bytes': DEST.stat().st_size, 'members_checked': len(CONTENT),
        'crc_passed': True, 'all_member_sha256_passed': True,
        'private_runtime_included': False, 'hidden_reasoning_included': False,
        'models_dispatched': 0, 'native_solves': 0}
    sealed(OUT / 'PACKAGE_READBACK-v3.json', receipt)
    # The receipt is external, so it can hash the actual ZIP without a circular hash.
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
