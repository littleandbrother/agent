常规压电节点 · 名义参考链

在声明的振动、初始储能和 20 秒窗口内完成至少 3 次有效采样与接收；比较机械参数、储能或固件调度的修订。

System: SC-e4cb777644f4a192133f9834cf4ee8cd4834975f5129d5ca041a055fa2187588
Scope: nominal-reference-chain
Result: PASS

第一轮采用版 R6（储能 47 µF，调度 2/6/10/14 s）的报告修订版：本轮不改设计、不改执行与验收，只修正单位与表述。R6 在标准服务调度下五门 PASS。窗口最低电压取自已保存波形（执行 TX-3dd1fb23… 的 storage.dat）：4 个发送窗口最低 2.93087839 V（对 2.2 V 下限余量 0.73088 V），采样窗口最低 3.45887489 V。负载能量按固定 2.5 V 负载轨计：327.552 µC × 2.5 V = 818.88 µJ/20 s，平均 40.944 µW；转换后可用平均功率 152.757 µW，供需比 3.73 倍。储能核算相对残差 1.13480e-7 J / 1.57747e-4 J = 7.19e-4（分子分母同为 J）。以上均为仿真结果，physical=NOT_TESTED。R6 已在第二轮被 R7（68 µF、时序不变）取代。

## 当前执行的数值摘要

| 项目 | 数值 |
|---|---|
| 储能电容 | 47 µF |
| 负载电源轨 | 2.5 V |
| 负载总电荷 | 327.552 µC |
| 负载总能量 | 818.88 µJ |
| 平均负载功率 | 40.944 µW |
| 转换后可用平均功率 | 152.757 µW |
| 可用功率 / 平均负载 | 3.73087 倍 |
| 第 1 帧采样窗口最低储能电压 | 3.45887 V |
| 第 1 帧发送窗口最低储能电压 | 2.93088 V |
| 第 2 帧采样窗口最低储能电压 | 3.45887 V |
| 第 2 帧发送窗口最低储能电压 | 2.93088 V |
| 第 3 帧采样窗口最低储能电压 | 3.45887 V |
| 第 3 帧发送窗口最低储能电压 | 2.93088 V |
| 第 4 帧采样窗口最低储能电压 | 3.45887 V |
| 第 4 帧发送窗口最低储能电压 | 2.93088 V |
| 采样与发送窗口最小电压余量 | 0.730878 V |
| 储能核算绝对残差 | 0.11348 µJ |
| 储能核算相对残差 | 0.0718861 % |

## task_and_model

任务：在固定参考场景下交付能量链候选（机械/源/储能/固件/接收）；本轮为报告核对，不改候选、执行与验收要求。R6 的设计选择：储能 47 µF（E6 值）、4 帧调度 2/6/10/14 s（每帧 sample 10 ms → 1 ms → tx 4 ms）、机械保持参考值。证据范围：容量扫描只变 C，源功率、转换效率、状态电流、窗口最小时长与初始储能都固定，故相关结论只在该范围内成立。

Sources: design.json, firmware/main.c, notes/candidate-r6-storage-schedule.md

## mechanics_and_source

机械保持参考值（L=50 mm、w=10 mm、基板与压电各 0.2 mm、尖端 2.000 g）。仿真源：原生求解 305.51 µW，解析 304.30 µW，误差 0.4003%；f_n = 31.0868 Hz；尖端峰值 1.3289 mm，占 5% L 上限的 53%。EXP-D 把尖端质量调到 f_n≈30 Hz：功率升到 3.03 倍，但位移升到上限的 92.6%，属负收益交易，未采纳。

Sources: notes/exp-d-mechanics-resonance.md, source_model

## firmware_and_receiver

固件按 4 帧调度（2/6/10/14 s）生成事件表，每帧 sample 10 ms + 1 ms 间隔 + tx 4 ms，帧内含 CRC；receiver_service PASS：4 帧全部交付并被接收，无重复、无校验失败。load_binding PASS：负载总电荷 327.552 µC，与事件表的状态电流积分一致；该电荷只取决于状态时长，与储能容量无关。

Sources: firmware/main.c, receiver_service, load_binding

## energy_and_service

以下均为仿真结果。① 负载用固定 2.5 V 轨：327.552 µC × 2.5 V = 818.88 µJ/20 s，平均 40.944 µW；转换后可用 152.757 µW，供需比 3.73 倍，负载不是限制量。② 窗口最低电压直接读自已保存波形（storage.dat 与 events.json）：发送窗口 2.93087839 V（余量 0.73088 V），采样窗口 3.45887489 V；钳位 3.60037 V 与发送窗口最低之差 0.66949 V，折合 47 µF 上 31.5 µC，低于按状态电流直接积分的每帧 42.6 µC —— 因为负载按固定 2.5 V 轨取功率，储能侧电流按 V_rail/V_cap（约 0.75 倍）折算；这也解释了第一轮按 42.6 µC 外推出的 2.80~2.87 V 偏低（实际读数 2.93088 V）。③ 储能核算残差 1.13480e-7 J，分母为储能变化 1.57747e-4 J，比值 7.19e-4（0.0719%），分子分母同为 J。④ 容量扫描（仅变 C）：220 µF 与 33 µF 通过，22 µF 失败（交付 0 帧），三点跌落给出下限约 25~26 µF。该下限在本扫描中由钳位水头与每帧电荷决定；因未做源功率与效率变化扫描，不能推广为“下限与可用功率无关”。

Sources: design.json, notes/exp-a-storage-floor.md, notes/exp-b-capacity-floor.md, notes/exp-c-capacity-floor-22uf.md, power_service

## conclusion_and_files

R6 第一轮采用：五门 PASS、4 帧交付并接收（执行 TX-3dd1fb23ed035f11e5208c0a53cca06f16cb8231ce0001a74de540e809bd358c）。文件：design.json（storage_f 4.7e-5）、firmware/main.c（事件表 sha d78bbe45…）、notes/exp-a~d、notes/candidate-r6-storage-schedule.md。限制：全部为仿真结果（physical=NOT_TESTED）；名义参考模型未做器件标定；容量下限结论只在本扫描范围成立；本轮只修订报告表述，设计与执行均未变。R6 现被第二轮 R7 取代；47 µF 只在“连续两帧、其间几乎没有再充”的自定压力下丢帧（该压力探针记录在取代版本 R7 包内的 EXP-E）。

Sources: design.json, firmware/main.c, delivery_version, notes/candidate-r6-storage-schedule.md
