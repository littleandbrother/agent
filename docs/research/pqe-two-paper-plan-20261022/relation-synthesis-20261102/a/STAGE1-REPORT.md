# 第一步：两个精确反事实

六次原完整消费者执行全部完成、模型域有效。低门限且关闭持久化的固定设计三工况全部 FAIL；旧 G callback 12 原样设计三工况全部 PASS。

低门限设计与旧 R314159 成功终态逐字段相比，仅 `persistent_queue` 从 true 变为 false；与原 common parent 相比，仅 `startup_v` 从 3.2 改为 1.9。holder 原本为 off。

| 固定设计 | 工况 | verdict | capture/SAVE/TX/RX/ACK | missed/late | duplicate wire | brownout | load J |
|---|---|---|---|---:|---:|---:|---:|
| startup19_no_persistence_holder_off | capture-recover | FAIL | 2/2/2/1/2 | 2 | 1 | 2 | 0.008256048 |
| startup19_no_persistence_holder_off | reuse-train | FAIL | 6/6/6/5/6 | 2 | 1 | 2 | 0.009628002 |
| startup19_no_persistence_holder_off | radio-gap | FAIL | 2/2/8/1/2 | 2 | 1 | 2 | 0.009984205 |
| saved_G_callback12_untouched | capture-recover | PASS | 3/3/3/3/3 | 0 | 0 | 2 | 0.009822940 |
| saved_G_callback12_untouched | reuse-train | PASS | 7/7/7/7/7 | 0 | 0 | 2 | 0.011225534 |
| saved_G_callback12_untouched | radio-gap | PASS | 3/3/7/3/3 | 0 | 0 | 2 | 0.010997395 |

低门限设计 failures：["MISSED_OR_LATE_EVENT"]。stage 计数不能替代完整服务门或身份连续性；seq/direction 是公共观测键，不是跨重启全局记录身份。

旧 G 提案通过原 `adapter.prepare/validate_design`，未修改参数、类型或设计；其与旧 complete-reference 的数值/枚举差异：{}。本次执行单列为新反事实；旧工具配额耗尽、零新完整执行和没有最终提交的原 episode 结论保持原样。

原 parent、persistent-only、holder-only、never、complete 和旧 R 成功终态均按 SHA 引用，见 `FIXED-NEIGHBORHOOD-MATRIX.json`。矩阵只支持固定设计邻域中的交互，不能推成全域组件必要性、物理资格或方法优势。低门限空间保持原合法范围。

资源：新 full=6，实际累计 6.740417581983s；cheap=1（静态几何真实缓存 miss）；software=2（原输入/源码绑定与逐件压缩产物读回），模型请求=0。每次上限120s；余量充足，输出A约1679246 bytes，执行后可用23257579520 bytes。未运行 init/全套测试。

原消费者/评价器/门限/域 SHA 与旧 R 成功成员精确相同；六份输入在 full 之前冻结。原始 raw/assessment 保留为单份 gzip，完整读回；public result、白名单公共关系与详细 summary 均可重审。机械力门和两能量闭合门原样通过；physical UNKNOWN、population-loss NOT_ESTABLISHED。

复现命令（此包不可直接重跑；应新授权、新输出身份，避免覆盖或隐性重试）：

```text
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B docs/research/pqe-two-paper-plan-20261022/relation-synthesis-20261102/a/run_stage1.py
```

下一步：S0 使用此里程碑；A 仅冻结 DOOR/LC 事前任务，不追加初态执行，不向 B 提供比较任务。
