# BFA-028 门动作磁耦合工程案例 D2

状态：数字工程交付已归档，完整验收未通过。没有硬件、没有外部模型调用、没有提交或推送。

## 已交付
- 真实尺寸门及磁耦合机构；22 个 STEP/BREP 实体、装配与安装 STEP、22 张 CAD 投影图；加工孔位基准、公差及螺纹明细未完成，不声称制造级完整制图。
- Blender 原生场景、GLB、3 张安装/机构图、4.07 秒开门 MP4；视频完整解码通过；动画是规定门角，不是假造动力学结果。
- COMSOL 6.2 压电梁静载/模态/互易提参、磁场模型、原生 MPH 与应力/位移/磁场 PNG/GLB。
- 受载荷影响的降阶模型、时间步检查、正常/慢速/高阻尼/无动作/无磁体对照、原始 CSV。
- ADI LTC3588-1 厂商 LTspice 模型，真实 RAW/CSV/电路/PWL/日志；单向耦合，未通过冷启动。
- 元器件精确网表原理图，80×30 mm 双层 PCB 实际布线；独立检查0断网/0间距违规，原生 EDA 导入与 ERC/DRC 未验收；Gerber 缺阻焊/钢网，不能下单制造。
- nRF52832/S132 3.0.0 固件 ELF/BIN/HEX、干净重复构建同哈希、烧录 dry-run、协议合成样例解码。未烧录/未接收/未测功耗或时延。
- 36 页中文 PDF 与可编辑 TeX、来源、图表哈希、复算入口、399 项 ZIP。

## 后台与页面
增加 engineering_case_releases SQLite 表和不可变文件快照；发布严格绑定既有会话与 D2 哈希。案例版本独立于历史 Agent 装配 v1，不改旧验收，不冒充 Pi 工作。通用适配可供其它 case 使用。
当前会话 pi-chat-c1152c3ff3c7a5d8 的产品页有8个D2分区、130件文件，HTTP下载逐件哈希通过。新增MP4预览；工程记录入口展示原始回执而非伪造Agent Trace。

## 验证及失败
19项目标测试通过。完整 ./init.sh 的407项Python测试有12失败、9错误；独立复现的一项Pi启动失败为 undici 的 iteratorMixin TypeError（Node22.22.0），没有将其余失败一概归因。未运行根仓库科学 init，未修改冻结实验。
正常开门 VIN最高0.1355317831V，PGOOD不拉高；不能发送。磁场两级最差差异7.65%超过5%门槛。原生EDA导入返回null，没有原生ERC/DRC。没有放宽门槛。

## 后续
1. 恢复原生EDA可操作窗口，导入并检查真实PCB/原理图结构，补齐制造规则及阻焊钢网。
2. 在单独D3版本建立快速机械释放或其它受论据支持的激励方案；先解非线性与磁网格，再比较。不能只靠减小磁间隙把梁推到越界。
3. 建立PMIC电压与梁运动的双向耦合，冻结单次开门冷启动标准；改储能/匹配要重做电路、板图与所有关联哈希。
4. 修复Pi依赖并复跑相关集成测试后，才进行Pi独立调用验收；本轮不计入自主Agent成绩。
5. 当前CAD图纸为样机投影，补功能尺寸/公差/材料及配合后再申请制造释放；实物验证仍待硬件。

文件根目录：/Users/depengsu/Documents/bf-agent-workbench/reference-cases/door-magnetic-v1
运行记录：/Users/depengsu/Documents/bf-agent-workbench/verification/door-engineering-20260929/receipt.json
复核命令：python scripts/door_case/run.py --root /Users/depengsu/Documents/bf-agent-workbench/reference-cases/door-magnetic-v1
