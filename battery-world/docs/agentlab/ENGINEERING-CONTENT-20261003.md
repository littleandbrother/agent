# 门磁任务的工程内容补齐与读回

本轮工作始于2026-10-03，最终读回于2026-10-04。当前任务是“磁耦合全流程bf aiot设计”（owner `pi-chat-390c76686d6d79a5`）。这是内容恢复、采购电子修订与页面接入；不修改封存的科学实验、Agent装配验收或评价规则。

## 原因与实现

旧D2工程只发布给另一个owner，部分本机文件还是iCloud按需内容。当前会话没有可读取的工程记录，前端还优先选择空的Agent装配。因此问题同时存在于文件可读性、归属和默认成果范围。

- `restore_publication.py`从旧封存归档逐件恢复130个D2文件，校验路径、字节与SHA-256，再显式发布给当前owner。不修改原文件、封存清单和旧owner。
- `StudioModel.preferredScope()`在没有可读取的当前装配成果时，选择最新显式发布案例；已有当前装配成果时仍优先当前装配。不把参考工程充当Agent验收结果。
- 发布独立的`D3.3-electronics`：6组、88件文件，逐件读回通过。中间D3、D3.1、D3.2归档保留。当前会话选择最新版本即可，不需要浏览所有历史记录。
- 原理图、PCB、仿真、BOM和文档都有预览与下载。重复视图区分PNG/SVG/PDF；未执行的检查显示“未检查”。不支持直接解析的原生二进制RAW给出CSV/原生软件入口提示，未生成替代曲线。
- 文本表格保留原始字段，修正0603被解析成603、精确库存被显示格式四舍五入的问题。目录和手册链接只接受列明的HTTPS域名，所有文本继续转义。

## 实际产物与范围

| 部分 | 本轮结果 | 验证边界 |
| --- | --- | --- |
| 原理图 | LTC3588-1 3.3V、E73/nRF52832、压电输入、储能、去耦、PGOOD、SWD；PNG/SVG/PDF与逐引脚网表 | 与PCB的引脚—网络一致；原生ERC未执行 |
| PCB | 80×30×1.6mm；81焊盘、89条实际Freerouting走线、9过孔；双层图、SES/DSN、epro2/epru、草案铜层/钻孔 | 独立二维连通、铜间距、天线禁布检查通过；原生DRC与制造审核未完成 |
| 电源 | 3个工况真实ADI LTspice26.0.2：正常门动作、慢弱动作、无动作 | 三个工况均未冷启动；沿用D2的单向ROM输入，不替代双向closed-simulation或MCU实测 |
| 机械场图 | 原D2 COMSOL应力、位移、磁场PNG/GLB/MPH | 本轮未重算；原磁场网格差7.65%超过5%门槛；不验证新模块装配 |
| BOM | 14装配件、11种嘉立创料号；库存快照、封装、数量、型号、目录与手册 | 查询库存覆盖一块样机；未购买，不证明贴片服务资格 |
| 工程包 | 100个ZIP条目，含图纸、布线、库、波形、网表、宏模型、BOM及来源快照/手册 | 下载SHA和ZIP CRC通过；电子工程草案，不是制造放行包 |

两项缺货料已处理：C685115换为C685122，保持MSOP-10-EP引脚但温度等级不同；C2828282换为C411306（E73-2G4M04S1B），后者是不同的44焊盘封装，实际重建网表、布局和路由，不是简单改一行BOM。PMIC查询库存只有4个，模块为131个；查询时刻以每件凭据为准。

新模块焊盘来自厂家手册，矩形焊盘内侧长度1.2mm，较厂家底部焊盘1.5mm缩短，保留0.65mm宽度。独立检查捕获并修正两处转角铜间距，但这不能替代原生库与焊接工艺审核。最小铜间距0.1669mm，最窄路由neckdown为0.1142mm，不能用0.1524mm标称线宽代表所有走线。

电感采用[SRN4018厂家手册](https://www.bourns.com/docs/product-datasheets/srn4018.pdf)中的180mΩ标称DCR重新求解（D2旧假设400mΩ保留为默认）。输入47µF、输出100µF和14mA条件负载属于本失败基线，未宣称是最优配置。电容DC偏置/ESR、模块内部去耦和实物程序能耗仍未校准。

最终正常工况VIN峰值0.135531783104V，VOUT峰值9.92299078462e-7V；PGOOD未激活，负载能量0。因未启动，此结果也没有验证发送电流或电感运行时损耗。没有外部电源、非零初始储能或人为成功标签。

最终原始点数为104021/230021/92021；CSV预览为256/161/49点，按48个时间顺序分箱保留每个原生通道的极值和端点。独立读回核对原RAW/CSV哈希和四个显示通道的全局极值；原始RAW仍为权威数据。完整预览采样说明在`waveform-provenance.json`。

## 原生EDA状态

连接器健康、4.1.60宿主与工程容器身份可读。`BF-Door-D3-Procurement`容器创建成功，不代表原理图/PCB已经导入。C411306的typed封装读取重复超时，原生导入与ERC/DRC尚未完成。

[EasyEDA技能](https://github.com/zhoushoujianwork/easyeda-agent)本机约束要求“保存或回读失败时停止现场写入并报告数据不可用”，并禁止用GUI或debug JS绕过typed接口。对应本机文件：`/Users/depengsu/.codex/skills/easyeda-agent/SKILL.md`。据此保留离线工程草案，不做现场兜底编辑或虚构native通过。下一步应先修复该typed读回/导入能力，然后核对厂家封装、ERC/DRC、板框和装配、RF与制造层，而不是直接投板。

## 复算与检查

脚本均在`scripts/door_case/`。先复制工作目录到新的输出目录；不要覆写封存版本。需要已安装的本机LTspice、Freerouting以及含NumPy/CairoSVG的工程Python。

```sh
# 从原case的库与来源生成独立电子目录
python scripts/door_case/procurement.py "$case_root" "$revision_root"
python scripts/door_case/board.py "$revision_root" --definition "$revision_root/definition.json" --output "$revision_root/pcb"
python scripts/door_case/schematic_procurement.py "$revision_root/pcb"
# 以board生成的door.dsn运行Freerouting，保存door.ses，再执行：
python scripts/door_case/route_export.py "$revision_root/pcb"
python scripts/door_case/procurement.py "$case_root" "$revision_root" --bom
python scripts/door_case/power.py "$case_root" --output "$revision_root/power" --load-a .014 --inductor-dcr-ohm .18
python scripts/door_case/procurement_views.py "$revision_root"
```

`publish_procurement.py`只读取指定工作case，并要求一个全新的版本号；它冻结manifest、工程包和owner发布。图纸PNG/PDF由SVG离线转换，后端不生成替代数值。

测试结果：

- 17项定向Python、10项JS（含27个工程视图投影断言）通过；包括损坏归档、owner隔离、零库存、型号不符、转角焊盘和BOM文本/库存精度的负向检查。
- 未显式设置Pi实际运行目录的首轮init出现14失败/2错误，原因是沙箱允许的Pi路径与node_modules软链接目标不同；没有放宽沙箱。使用服务同一`BF_PI_ROOT`后488项Python检查通过（313.312秒）。
- plain init随后在pnpm非TTY依赖自动刷新处停止；按已安装依赖执行`corepack pnpm --config.verify-deps-before-run=false`的SDK类型、Studio类型和构建，通过；control及2803样本projection通过。不把plain init写为全程通过。
- 当前用户页面实际验收四栏目、CSV曲线和全部11行BOM，工程包真实下载、SHA/CRC以及所有88文件读取通过。无新增外部模型调用，无购买。

本机最终收据：`bf-agent-workbench/verification/engineering-content-20261003/receipt.json`。最终工程包：`reference-cases/door-magnetic-v1/electronics-D3/electronics-D3-engineering-draft.zip`，SHA-256 `aee0206e0eb6152b46128d5cf95b0ea9855aacb9ee4e21f4c9a9ab03434ae949`。照片/屏幕图与日志随验证收据保存。

本轮内容接入已完成；自供能任务、原生EDA恢复和制造/实物验收仍未完成。BFA-035的物理模型与正式结构实验状态不因此改变。
