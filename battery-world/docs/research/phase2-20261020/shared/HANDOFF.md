# 阶段二真实执行交付

权威报告：`/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/phase-plan-20261019/phase2/RESULTS.md`。

权威实际记录：`/Users/depengsu/.local/share/bf-phase2-20261020/actual-results.json`。只读复核命令：

```sh
rtk proxy python3 -B '/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/phase-plan-20261019/phase2/verify_results.py'
```

E5 原 episode 失败，事后实际消费者将 10 µF / 45 ms 改成 15 µF / 45 ms，服务 FAIL→PASS；强静态信息方案也通过。H 原提案受宿主操作/额度错误阻断，事后保留其实际模型文本；H0 与 H′ 分别得到 22 µF / 45 ms、9 µF / 3.7 ms 的通过设计。H′ 拒绝推广，默认方法不变。两者在任何复位前交付，不能解释为易失待发送状态跨复位保持。

四次实际 episode、原始失败、来源、实际 tool trace、设备输入、完整反馈和账本均封存，不自动重跑。25 次请求全部 SETTLED，计费上界估计 0.1766922 USD；Codex 介入非零且未计价。7 次新科学执行，零原生调度、零新环境、零新工作树。原 A/R 产品仍 NO_GO / FIFO FAIL / NOT_ACCEPTED。

新版本接口修复在根报告目录的 `dispatch_adapter_v2.py`，仅通过两个原故障的定向回归，未改原运行身份。下一批须新注册、冻结相同初始缓存并按同总预算/强静态基线比较。两篇 `phase2.pdf` 为本地结果稿，旧主稿、PDF、共享版式与校徽保持原样，本批未推送。
