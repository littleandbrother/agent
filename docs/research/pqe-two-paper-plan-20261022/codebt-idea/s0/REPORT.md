# 新 Idea：真实入口已运行，方法比较未完成

BFA-097 / BF-PQE-CODEBT-KILL-20261024-001，出口 2026-10-24T11:22:34.675322+00:00。当前 feature **blocked**，原科学派发已关闭；没有继续扩组或延期。

共同初态的三个原完整数值仿真得到 **FAIL / FAIL / PASS**。两个失败都完成6次捕获、SAVE、TX、ACK；原 assessment 显示复位后重新使用序号，接收器去重后分别只保留2和4条，控制工况保留6条。这支持本构造模型中的跨复位身份问题，不能据此证明需要事件保持组件、存在适应度死亡谷或某方法有优势。未改变任务或根据结果换题。

| 路径 | 实际执行与结果 | 可作出的判断 |
|---|---|---|
| 共同初态，原消费者版本 | 3完成、3 model_valid；收到2/4/6条 | 前两FAIL由序号复用证据解释，控制PASS |
| 强通用 Agent | 2实际SETTLED请求、4公开分页、0合法候选 | 第2实际响应试图用原生DSML继续读取public_object，JSON接入器报JSON_SYNTAX_ERROR；控制器记NO_NEW_LEGAL_MODEL_DESIGN，不是搜索无解或主动放弃 |
| 普通联合搜索，原已选候选 | 原short-cold 120秒工具超时保留；共同补丁版三工况均完成，但3项MODEL_DOMAIN/UNKNOWN | domain_errors均为assembly_envelope_exceeded；不是有效服务FAIL，不是能量闭合已压垮母线的证据 |
| DebtSearch，原已选候选 | 1实际SETTLED请求，提出holding+持久身份+读取联改；原short-cold 120秒超时；共同补丁版short-cold在原绝对截止前约36.8秒仍未完成而终止 | 没有完整工况族，不给通过率或与对照的优劣结论 |
| 机制近邻 | 0；截止后未派发 | 事前规则保留，未用补跑弥补缺口 |

## 接入修正和版本

两次原模型回调在本地因65536超过实际绑定Pi的32768单请求上限而拒绝，实际转发0、无模型结果。按审查明确细化，在原两逻辑episode追加一次 `TRANSPORT_CAP_CONTINUATION`：同owner、原绝对期限（Generic 11:15:49.110 UTC，Debt 11:17:49.675 UTC）、原USD10/24请求/63输入/候选上限，单请求改为min(32768,131072剩余)。没有新建owner/episode、重置时钟或覆盖原terminal/closeout。追加后3请求真实转发且都有用量；没有格式探针，没有修补Generic原输出。

A与审查只读定位到enabled积分的接点屏蔽不一致：begin_step在holder.ready/busy时屏蔽真实接点，idle调度仍用该接点算已到期debounce，使limit=0并以1e-9推进。共同修正仅让两处资格谓词一致；原服务、负载、任务、120秒均未改。旧consumer SHA256 `98c85265ac101687d2630cd3f19d744b693b73d7c6b32c15f63720846a246694`；新 `9bd116f7d28e33953208ac4ef3612977bceab00b4dde971a0ea8e65eb3f5e0bc`。精确diff、旧源反向重建hash和AST见 [A修正回执](../a/SCHEDULER-FIX-RECEIPT.json)。只确认该源码矛盾得到修正；Debt后续仍未完成，不宣称所有调度/数值问题已排除。

按审查11:15 UTC的有限细化，修正版只续评两项**原已选择且无结果**的候选，计作新完整调用、与原工具错误分列；没有重新Generate、改变候选或重跑3个有效初态。所有新调用用同一修正版。旧Debt子进程在A修改磁盘源码时已载入旧模块，随后超时且没有raw/public产物；新版本调用另列06至09，未将磁盘hash误当旧进程的执行身份。

## 费用、存储与出口核对

- 新完整输入**尝试9次**：完成6次（其中3个有效初态、3个域外结果），工具错误3次；总wall **283.737250251秒**。最后一次受原绝对期限截断，不称120秒完整运行。便宜数值check与机制近邻均0。
- 真实模型请求**3 SETTLED**，27136输入/1353输出token，账本计费上界估算 **USD0.0097644**；不是供应商发票。新UNKNOWN/在途0。原1963条模型费用行摘要逐行一致，两个旧UNKNOWN/null usage/完整reserve未改；精确新例外只适用本包。原模型owner凭据/grant已关闭、study过期、scope恢复。
- 产物分配上界约**17.31 MB**，低于100 MB上限；采样可用**38.354 GB**。完整gzip/raw/assessment/public/decision与任务、设计、源码绑定已回读；新增summary的重复完整结果改为经全文核对的canonical引用，没有另建备份。本研究本轮主动释放**0 B**；旧清理保持暂停，文件系统其它变化不算清理成果。
- 4项host语法检查、A单模块AST及精确diff核对；没有重复suite、额外solver、付费probe、native/硬件、全init、commit或push；不声明全仓健康。

[机器出口与逐项证据](science-exit-readback.json)、[原输入账本](science-resource-ledger.json)、[实际模型接续](transport-continuation-summary.json)、[共同补丁续评](scheduler-continuation-summary.json)、[请求上限修正](transport-cap-fix-readback.json)。原两个本地拒绝、Generic DSML原文、两次120秒超时和原期限截断均保留。

**本轮没有完成有效的三组科学比较。** 证书仍None/UNKNOWN；死亡谷、配套义务到真实物理闭合的增益及完整服务优势均未验证。下步审查应直接处理DSML接入、enabled消费者的剩余执行缺口与域资格；当前没有自动新增额度或恢复旧试验。

只读后续线索：解析电压越界时间与固定二分的数值舍入、严格小于复位判据，可能重复调度近零电压事件。本轮没有采集卡点的t/v/mode/limit/栈，不能认定它是Debt超时的实测原因；截止后未修改或重跑。

---

以下为此前离线原型阶段报告，记录的是当时状态。

# 新 Idea 原型：离线贯通，科学执行待准入

BFA-097 / BF-PQE-CODEBT-KILL-20261024-001，2026-10-24T09:40:21.631963+00:00。

**新事件保持/交接机制与义务搜索已实现，并通过直接软件贯通；三组科学比较尚未执行。** 原 UNKNOWN 请求未获得真实 usage 或新的精确历史例外，保留 status、usage=null 和 USD0.1025205 全预留。本包不是旧 ACTION-POLICY、F1 或 BOLD 的恢复。

## 实际实现与证据

- A：新增一个有电压工作域、有限容量/保持期限的事件保持组件；捕获、读取、清除均有时间和负载，回到共同供电方程。当前接点/保持后接点读取、early/SAVE/ACK/never 清除可独立编辑；SAVE 与 ACK 均有合成重入正控制。默认关闭仅以替身验证原函数路由，未重跑旧科学输入。见 [A 源码回执](../a/SOURCE-READY.json)。
- B：真实部分节点保存 design/pending_diff/obligations/evidence/scope/parent；公开生产、读取、交接、复位和负载事实派生 OPEN/SATISFIED/REFUTED/UNKNOWN。Generate 按依赖扩展；Select 保留部分节点；Update 保留合成 0 服务方案。普通搜索含联合突变/重启/保留，三控制器共用 A 的纯静态合法域。见 [B 回执](../b/source-ready.json)。
- S0：直接软件链连接新组件状态机、A 事实、真实 DebtSearch、原动作适配函数及 Update。该链的 raw consumer 和 evaluator 都是明确标记的软件替身。首个实际请求联合修改 holding_component=lp_fifo、persistent_queue=true、read_source=holding_then_contact；没有强制 ACK 清除答案。六个实际评价请求都有半成品祖先。见 [直接链账本](offline-direct-chain.json) 和 [检查结果](offline-readback.json)。
- 剩余输出额度实际传入回调；用量 UNKNOWN 后停止且不重试。真实 provider/owner 的付费接入尚未实例化或验证。新 science 子进程入口同时检查计费准入、公共协议、源码和任务绑定，单输入120秒；当前协议是 FROZEN_OFFLINE_INTERFACE_ONLY，不能作为科学准入。
- 一项新 DOOR 任务/三个工况的选择与原始输入已冻结；初态运行0。最多六个机制近邻输入的事前规则已固定，当前运行0。见 [公共协议](../shared/protocol.json) 与 [机制选择规则](../shared/MECHANISM-SELECTION.json)。

## 验证与原失败

| 层 | 最终检查 | 累计软件检查成本 | 新科学/供应商请求 |
|---|---:|---|---:|
| A | 20 PASS | 4 suite、76 case-executions | 0 / 0 |
| B | 11 PASS | 5 suite、55 case-executions；另4定向诊断 | 0 / 0 |
| S0 | 9 PASS | 一次直接贯通；21 family-member 替身调用、9软件 planner 回调 | 0 / 0 |

B 的 attempt-01 至04均保留：每次9 PASS/2 FAIL。首失败是快照重复引用超过本地体积断言，其依赖消融项未完成；最终改为可校验引用表，原回调请求/响应保留。它们不是数值服务失败。A/B 源绑定已独立读回，没有再跑整套 suite。收口脚本一项 Python 元组/JSON 数组直接相等断言失败，规范 JSON 哈希证实内容相同；原比较错误与修正见 postflight-comparison-correction.json，未修改任务。

只运行受影响路径逻辑与静态检查，未运行 ./init.sh；不声明整个仓库健康。

## 尚不能宣称的结果

新增完整科学输入0、便宜数值边界调用0、真实模型 episode/供应商请求0；三个共同初态、三组参与者、机制近邻均未执行。完整 enabled 消费者的数值能量闭合、波形覆盖、完整服务、物理资格、死亡谷与方法收益均未验证。A 的解析必要界没有获得实际数值 kernel 的误差资格，当前 BF 不可行 certificate=null/UNKNOWN；B 的合成数学证书检查没有物理排除权。义务闭合不等于服务 PASS，也不称自动学习、迁移、RSI或统计优势。

审查边界补记（2026-10-24）：跨复位序号义务含人工保守先验；persistent 方向不能称为自动发现的身份要求，也没有排除其他身份方案。三组继续共用可达事实和合法动作。

当前公共 certificate 始终为 None，尚未证明现职责分工无解，也未建立职责改变前后的必要界变化，数值 kernel 适用性仍 UNKNOWN。因此后续有限判别首先检验配套关系搜索；即便出现收益，也不能归因证书触发，或宣称“证书＋配套闭合”整体核心已经成立。证书机制作为未测核心依赖继续保留，不静默删去或用旧题补数。审查接受软件实现证据，不构成计费放行；原型保持冻结，不新增准备包、重复 suite 或格式探针。

## 存储与下一步

本研究包主动释放 **0B**；当前采样可用 **40.755GB**。源码/产物精确清单和分配字节见 postflight.json；保留上限100MB、额外峰值1GB。没有新环境、工作树、备份、提交或推送，旧研究/清理继续暂停。背景卷占用变化不计作本包释放量。

先取得原请求真实用量结算，或直接人类仅针对 llm-16cd5bfe95e06e92fd6d 的精确历史例外；随后实际绑定同一后端/模型与新 owner 的原账本验证器，才可冻结科学准入并按原63输入/2episode/USD10上限执行。不得重试旧请求、转旧额度或恢复旧包。此处只发一次离线原型里程碑；完整三组与机制判别尚未完成，不发 BF_COMPLETE。
