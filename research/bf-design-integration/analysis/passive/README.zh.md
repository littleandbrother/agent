# 原被动轨迹的只读数值复核

## 结果

- 47 µF 保持对照，10 µF 保持一个条件比较候选。细步末端储能分别为 0.476288565 µJ、1.751368211 µJ，10−47 差为 +1.275079646 µJ
- 四格最大能量收支残差约 3.679×10⁻¹¹ J；18 项原粗／细门槛及两项原效果规则通过。能量差对照的是 5×原观察粗／细差值之和 = 6.195688784×10⁻¹² J；这是经验数值分辨率规则，不是统计显著性、置信区间或严格误差界
- 从保存的三次插值系数重建状态，从保存的力／力矩和运动导数重建功率，再逐接受区间独立作 Simpson 积分。2 s 的左右单侧功率分别保留，没有跨跳变连线积分。四格 2–4 s 储能增量及驱动功均为零，机械衰减仍有损耗
- 两组相同的是指定驱动角度／时间轨迹及初态。10 µF 的外部磁驱动总功多 0.381739504 µJ，机械和电阻损耗分别少约 0.577785908、0.315555596 µJ；储能差属于耦合能量分配，不能解释成等输入功效率提升
- 初始梁弹性能 +1485.586152 µJ、互磁势能 −7711.207266 µJ 明确保留；初态准备、驱动机构惯性／摩擦与复位成本并未验证

原版仍是 1 条实际中断、3 个未运行槽位；另封版修订版为 4 条完成。跨版本共 5 次实际尝试，不把修订结果回填原版。

## 本地重跑

已有 Python 3.9+ 与 NumPy 即可，无需 SciPy、求解器或网络。三个原归档保留原名，放在同一个只读输入目录，不必解压：

- BF_Conditional_Passive_20261001_core.zip
- BF_Conditional_Passive_20261001_raw47.tar.xz
- BF_Conditional_Passive_20261001_raw10.tar.xz

从本工作区运行：

```sh
python -B analysis-passive-20261001/analyze_passive.py \
  --archive-dir passive-delivery-archives \
  --recovery-index scientific-input-recovery-20261001/RECOVERY-INDEX.json \
  --out analysis-passive-20261001/RESULTS.local.json
```

其他机器只需修改路径。--recovery-index 可省略；三个归档及 PACKAGE-MANIFEST 的固定 SHA 仍必须匹配。成功退出码为 0；缺文件、字节身份不符或读回计算矛盾时退出码为 1，并写 BLOCKED_OR_FAILED；输出必须是尚不存在的新路径。任何已有文件、目录、符号链接（包括断链）或硬链接均被拒绝（退出码 2），最终使用独占创建模式 x 防止检查后的竞态覆盖。指向归档目录或恢复索引也会被拒绝。每次重跑请选择新的输出文件名；不要指向原科学文件。

## 输入映射与检查范围

RESULTS.json 的 input_integrity 记录三个归档 SHA、原清单 SHA、冻结计划和恢复索引身份；input_mapping 给出实际读用的 38 个成员的归档名、成员路径、字节数与 SHA。全部 268 项包清单已重新逐字节验证，嵌套原计划封口与五个历史运行封口另作核对。

- 原冻结规则：core 中 passive-source-storage-jacobian-20261001/PLAN.json；与原版 PLAN.json 对照，物理参数、初态、驱动、预算、能量与收敛门槛均未改变
- 四格主数组：两个 raw 归档中对应 outputs/cin47-或cin10-粗细目录的 raw.npz；sample、accepted、quadrature、ledger、domain 数组
- 独立状态重建：同目录 DENSE-SEGMENTS.json；全过程保存的多项式求值不是新时间积分
- 身份／读回：同目录 RUN-SEAL、STARTED、SUMMARY、REJECTED-EVALUATION、JACOBIAN-CHECKS
- 原中断身份与未运行名单：core 中原版 STOPPED-STUDY-RECEIPT、cin47-coarse 原输出；未运行槽位没有制造输出

脚本重算储能、完整有符号能量收支、原语功率、最终独立积分、三次轨迹电压／位移界、保存 Jacobian 的 h/h2 差分、6/10 阶保存值的原门槛、18 项时间细化和两项效果规则。它不重新计算磁几何间隙下界，只校验原始文件身份并明确标记该保留值；也不复现求解器内部行为或把保存的磁力值变成独立磁模型。极少量浮点运算重排差值与原科学门槛分开报告。

## 边界与文件

这仅支持固定材料分支、q-only ROM、未标定 ζ=0.02、理想桥和 100 kΩ 串联电阻模型的条件储能敏感性。不支持最优电容、真实整流器上界、PMIC 启动、原生等价、硬件／任务可行性或 Agent 收益；没有新扫描。

analyze_passive.py 是完整独立分析入口；RESULTS.json 是本次机器结果；SELF-TEST.json 记录确定性重跑、缺文件、单字节篡改、覆写归档拒绝和原归档未改动、已有文件／符号链接／断链／硬链接及原提取文件保护等自检；DELIVERY-MANIFEST.json 绑定交付文件。本目录不含任何大体积 raw、第三方模型、求解器或库安装包。

本版修复交付脚本的输出覆盖保护；科学公式与输入保持不变。前版生成结果保留于同级 analysis-passive-20261001-v1，不作为当前交付。self_test.py 可重现本版的安全与确定性检查。
