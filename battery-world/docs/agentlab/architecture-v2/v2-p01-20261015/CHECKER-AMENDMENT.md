# P01 V2 验收更正记录

对象：原 SC1/SC2，提交身份和输入保持；重新解释已有输出。

旧版本 `p01-system-independent-review-v1` 的紧凑表判定、缺失电荷字段判定及改名字段解析已由 v2 更正。SC1 v3 使用 netlist SHA/点数绑定，原误报移除。SC2 v5 从数值窗口独立重建，664／672 点及 Iload 电荷差异保留。供电低于 1.8 V 和人工接通负电压仍失败。

原生 EDA/CAD 检查按冻结输入及原独立回执精确复用：PCB 52 Clearance / 50 Connection；原理图、装配保留缺失资料项。新证据覆盖八项门并进入当前资格。

旧回执/包留存。新 RV/REL 与完整摘要见 [delivery-final.json](delivery-final.json)；包内新检查记录、资格及不可变 SC 回读见 [delivery-validation-readback.json](delivery-validation-readback.json)。只读重现：[compact-timeline-checker-reproduction.json](compact-timeline-checker-reproduction.json)。离线实际输入校准：[checker-load-calibration-002.json](checker-load-calibration-002.json)。

维护：Codex；新证据的调用、设计决定及两版 release：原 BF Lead。0 参与者工程改写、0 新构建、0 新求解。
