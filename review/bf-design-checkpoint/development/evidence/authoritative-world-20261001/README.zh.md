# 权威开发世界 v1

此包冻结的是可执行计算规格，绝不等于物理合格、任务准入或 Agent 实验已获准。

## 已实现

- 主线采用 338d603 的固定梁端／移动门上驱动磁体语义；SI 单位、输入、初始状态配方、共享 C 程序、虚拟接收和任务分别绑定
- 旧云端固定驱动磁体／移动产品保持独立世界；48 mm 名义坐标相同不代表其他 gap、轨迹、固件、PMIC 或任务结果等价
- 世界及语言无关 schema 冻结精确规格；更改语义或未知事实须注册新版本，不能在 v1 中暗改
- run identity 分开绑定 world / design / task / model / solver / program / sources / input / initial-state。绘图视角不进入科学身份，任何其他设计字段均保守失效所有缓存。源文件、求解设置及工具身份改变也全部失效
- no-motion 是不同的 input identity；提供的平衡初态须有来源哈希、残差及机械能，无法把未知辅助电源/复位能量补零。只绑定初态配方时明确标为 recipe_only_not_run_evidence
- BFD2 只去重 capture_id，不声称消除了无线重复、恢复了开关门方向或动作身份。完整 TX 和 deadline 是输入校验，不是物理接收证明
- 历史 DEV-COUPLING-01 的成功/失败资格不迁移；需在新世界重新取得 failure snapshot。两个任务仍不准入

## 可复跑入口

python -B src/authoritative_world.py verify --originals
./init.sh
python -B src/authoritative_world.py geometry --gap-mm 48 --time-s 1

仅需 Python、jsonschema 和主机 cc。测试在临时目录构建共享 C 库，不调用 COMSOL、LTspice、真实 MCU、蓝牙或模型服务。./init.sh 是此独立包的核验入口，绝不是整个 Battery World 上游应用健康证明。上游 ./init.sh 本包未重新运行；此前 Linux Seatbelt/数值失败保持其原有结论。

测试源码、原始日志、源字节副本、authority registry、未知事实、迁移任务和 FREEZE-RECEIPT.json 均在包中。verify --originals 额外确认读取的旧来源未变化；可移植副本无原位置时省略 --originals，只验证此包精确字节。build_contracts.py 是创建记录，已有冻结收据时拒绝重写。不要覆盖现有冻结证据。

## 接口与边界

src/authoritative_world.py 导出 load_world、validate_world、world_id、geometry_at、input_at、bind_initial_state、migrate_upstream_spec、make_run_identity、stage_keys、receive_completed_records 和 validate_comparison。

make_run_identity / stage_keys 接受 input_control='prescribed' 或 'no_motion'，以及可选 initial_state（bind_initial_state 的结果）。预充电、额外电输入、更快/更大的开门、错误 source/world/task/input 绑定会拒绝。此接口是规格/身份层，不是数值求解器、真实工况数据验证器或任务独立验收器。模型、设计/架构、参数和实际工件仍需各自的适用域验证。

source_hash 是身份，不是物理真值。源中固定的数值仅属开发假设；真实安装空间/力限、弱动作、机械初态准备与复位、原生 CAP/VIN2 状态和端口、全磁场/非线性机械、实际二进制功耗/时延、动作接收与独立可行参考仍有未知。完整清单位于 world-v1.json。

不存在任何付费调用、商用求解器执行、权限绕过、Git commit/push 或对旧封存包的改写。当前新增磁性世界科学动态求解次数为 0；共享 C 和代数坐标测试不算原生物理验证。

## 下一步

NEXT-REFERENCE-PLAN.json 是待复审的最小四格开发筛查方案，不是执行许可或可行参考。先绑定独立推导的明确假设 ROM 或真实原生 ROM；禁止拿旧云 ROM/缓存测试夹具冒充。静态数据手册状态合同不能替代瞬态 PMIC。弱动作/真实安装未知不阻塞明确标注的有限开发筛查，但阻塞相应用户/产品/正式主张。
