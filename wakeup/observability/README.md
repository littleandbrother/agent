# 原题观测剥离：36条新轨迹

[完整报告与五条超时分析](REPORT.md) · [协议](PROTOCOL.md) · [统计](summary.json) · [冻结任务](tasks.json)

9个不同原物理实例，L/A两种计算条件，gateway_only/original_p两档反馈；原直接整流、原五变量、每条6次评价。L为0/9对6/9，A为3/9对5/9；A有5条自主Python耗尽30分钟。453次模型响应和144次设计评价均返回。

`runs/`保留全部36条事件记录与终态，含未通过、超时、模型代码、实际公开反馈、完整物理结果和用量。目录中的私有任务/物理结果供事后研究复核，不是Agent获得的全部信息；实际输入在start/request/tool_result事件中。

本次发布仅在17份事件副本中将已失效的本机science接口令牌替为`LOCAL_SCIENCE_TOKEN_REDACTED`；本地原始记录未改。供应商密钥不在发布文件中。供本轮运行器读取的旧题来源清单改为仓库相对路径；科学任务、设计和结果未变。

只重算保存记录的汇总，无模型或仿真：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B wakeup/observability_run.py --report
```

该命令会重写summary.json，不改原始事件。查看报告无需执行。`--run`是付费实验入口，会拒绝覆盖已有记录，本次发布没有重跑。保留了实际使用的运行器源码，其付费重跑仍需配置本地模型凭据、macOS sandbox-exec及Pi SDK路径；它不是无需配置的跨平台安装包。

旧198条复测的初态、选题清单与详细题目设置位于`../attribution/`，仅为本轮必要依赖；未将旧198条与这36条混合计分。
