---
name: bf-engineering-report
description: 用同版工程、网表、源码与原始结果编写八页简版和详版 PDF；核对真实回路连线、跨参与者时序、图表与验收结论。
---

# 同版工程报告

固定版式与必检项见 `references/layout.json`。

先读取指定 report_id 的 `report_read` 与本专业 `report_schema`。输入是冻结工程与现有检查，沿原 owner 编写报告。

1. `skill(skill_id="bf-engineering-report")` 激活本技能；专业步骤再按需加载 EasyEDA 或 MCU 技能。
2. `report_schema(scope="power"|"firmware"|"lead")` 返回准确 JSON 示例与必填规则。
3. `report_read(report_id,path="facts.json",offset?,limit?)` 读取当前事实；原文件路径为 `input/sources/candidate/<工程路径>`。每次最多24000字符，按返回的 next_offset 继续。
4. `report_status(report_id)` 返回已提交作者摘要与 SHA。首次提交 expected_sha256=null；修订使用当前 SHA。
5. `report_write(report_id,scope,content="JSON全文",expected_sha256,operation_id)` 提交本专业内容。工程文件与任务基线保持原身份。
6. Lead 汇总三位作者后使用 `report_build(report_id,operation_id)` 生成并检查双 PDF。提交只追加报告，不派发原生仿真。检查通过后，Lead 用 `release(system_id,report_id,rationale,operation_id)` 发布同版审查包。

## 原理图

Power 先加载 easyeda-agent。按实际信号/能量流划分功能回路，每个冻结器件归属一组；组内器件用实际导线连接，跨组使用有名称的接口，公共电源/地使用规范符号。保留全部引脚、NC与真实网络。原生符号、元件身份和引脚网络来自同版 readback，报告绘图只重排版面。

说明关键路径、实际缺线、器件与模型差异。不能为画得完整而添加不存在的电气连接。PCB 标注引用真实器件编号，区域从本版坐标生成。

## 固件时序

用参与者之间的时序描述人工接通、初始化、广播、连接、CDC配置/采样、通知、PC解码，以及错误、断线与恢复。每条消息给出当前源码 path + symbol。区分实际配置、策略周期和声明的负载电流。序列至少12条，并覆盖 start/sample/notify/error/disconnect。

## 八页内容

1 整机结论与组成；2 CAD尺寸与接口；3 装配与爆炸图；4 电气架构与PCB；5 已连线的关键电路；6 固件时序；7 供能/负载/储能结果；8 需求验收与交付。

Lead 为每页填写直接结论与说明，需求表覆盖所有工程门。图表消费同版原始数据，单位和输入条件明确；未知尺寸列出具体缺项。使用简洁中文。保留失败与异常样本，不编造物理验证。

系统检查：器件/引脚网络完整、图中导线一致、时序源码定位、八页内容齐全、RAW/图表绑定、双PDF与候选绑定、输出哈希。新 release 必须附带通过该检查的报告。
