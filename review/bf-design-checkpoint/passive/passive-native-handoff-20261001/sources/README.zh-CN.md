# 338d603 原生证据最小采集器

目标：先收集可核对的小文件，避免先搬运整份约 1.4 GB 工程归档。仅在本机生成新证据包；不联网、不上传、不运行 COMSOL/LTspice/编译器，不修改原始证据。

当前只测试了人工合成夹具。这个工具包不含用户的原生运行数据，不能证明已重新做过原生仿真。

## 1. 先收集小包

需要 macOS 或 Linux、Python 3.10 及以上，仅用标准库，无需安装依赖。请先停止向同一证据目录写文件的运行，避免采集到变化中的文件。解压本工具包，在工具目录打开终端：

**尚未核实你本机的实际工作区根目录。下方 `--workbench-root` 是明确的路径占位符，请替换为你自己的 bf-agent-workbench 根目录绝对路径，不能原样执行。** 随包保留的原始证据请求中的绝对路径也仅是来源记录，不代表已验证你的本机位置；固定的相对证据路径保持不变。

```bash
python3 collect_native_evidence.py \
  --workbench-root "/替换为你的实际绝对路径/bf-agent-workbench" \
  --output "$HOME/Desktop/native-evidence-small"

python3 verify_native_bundle.py \
  --bundle "$HOME/Desktop/native-evidence-small"
```

- `--workbench-root` 是 **bf-agent-workbench 根目录**，不是 battery-world 仓库，也不是 acceptance-v2
- 采集器只从该根目录下 `verification/closed-simulation-20260930/` 读取
- `--output` 必须是工作区之外、尚不存在的绝对目录；其父目录需要已存在
- 不支持目录或文件的符号链接，也不读取硬链接。macOS 如果路径经过 `/tmp` 等系统链接，请使用实际物理路径（例如 `/private/tmp`）
- 命令只生成本地文件。确认内容后再自行决定是否分享；日志、源码及JSON可能带有本地路径等信息，采集器不做破坏原始哈希的内容改写

生成文件：

- `manifest.json`：相对路径、文件与分块 SHA-256、大小、选择范围、缺失列表；最后才写入，缺少它表示采集未完成
- `evidence-001.zip` 等：默认每卷不超过 10 MiB；可用 `--part-mib` 明确调整上限（需要大于 `--chunk-mib`，默认分块为 8 MiB）。10 MiB 只是保守的文件划分选择，不保证所有聊天客户端都接受此大小。使用不压缩的标准 ZIP，超大文件按块跨卷保存
- `collection-report.json`：采集时的版本/绑定/缺失检查；收到包后仍应独立运行校验器

这些文件共同组成一个包。只给出其中一卷无法完成全包校验。各卷中的 `.bin` 是原文件的逐字节分块，不是可执行程序；校验器不解压到磁盘，也拒绝顶层额外文件/子目录、ZIP注释及额外头尾数据。不要把其他文件或校验输出报告放进证据包目录；接收校验输出可另存在目录外。

## 2. 有需要时再带基线 RAW

```bash
python3 collect_native_evidence.py \
  --workbench-root "/替换为你的实际绝对路径/bf-agent-workbench" \
  --output "$HOME/Desktop/native-evidence-baseline-raw" \
  --include-raw baseline

python3 verify_native_bundle.py \
  --bundle "$HOME/Desktop/native-evidence-baseline-raw"
```

`baseline` 仅增加 baseline Result 引用的 joint、numerical 阶段各一份最终 `system.raw`，不收集迭代全档。小文件仍覆盖 baseline 与 positive-module。

需要两组共四份 RAW 时，用 `--include-raw all` 和新的输出目录。默认单份 RAW 上限 512 MiB、总载荷上限 1024 MiB；超限会记录为缺失，不自动扩大范围。确认确有必要后可显式调整 `--max-raw-mib`、`--max-total-mib`，同时给校验器相应的 `--max-file-mib`、`--max-total-mib`。参数上限均有限制。

`--include-passive` 可增加 passive-100000 和 passive-1000000 的 solve.json、waveform.csv、system.cir、system.log；其 RAW 还需要额外的 `--include-passive-raw`。默认不收集这些可选对照。

## 可选模型接口说明（新增，非原版已有文件）

只有操作人明确提供了新说明文件，才使用 `--include-model-interface`。固定位置是：

`bf-agent-workbench/verification/closed-simulation-20260930/native-model-interface.json`

格式见 `native-model-interface.schema.json`：原模型 SHA-256、原始单行 `.SUBCKT` 接口声明、原顺序端口、操作人抄录来源说明，以及可选的现有 XU1 行/节点/映射。不能包含模型正文、模型文件路径、许可证或凭据字段。若原声明有续行，当前格式直接拒绝，不展平或猜测。

采集器不计算厂商模型文件的摘要，也不越出固定目录读取模型；只接收操作人已提供的声明。它会核对接口令牌、端口顺序与可选映射，并将声明摘要与 Result 的 `tools.pmic_model` 比较。报告仍固定标注 `operator-supplied-unverified` / `not_independently_verified`：互相一致的声明不是模型真实性认证。

没有说明文件时仍报告 missing，不自动生成占位值或补造端口。该新sidecar不会改变、替代或冒充 338d603 原版证据。

## 3. 固定白名单

原始请求保留在 `MINIMAL-NATIVE-EVIDENCE-REQUEST.json`，实际允许范围硬编码在 `evidence_contract.py`。修改请求 JSON 不会扩大采集范围。

- 根回执与 acceptance-v2 的 receipt.json、cases.json、uncertainty.json、schema-validation.json
- baseline、positive-module 中明确列出的 Result、design-spec、收敛、能量、接收、程序/波形 CSV、日志追踪及生成源码/电路文件
- 只从这两份 `result.json` 的 `stages.<stage>.key` 解析 64 位小写十六进制键，读取 beam、force、firmware、joint、numerical、magnetic-confirmation 的指定文件
- checkpoint 中的文件列表只用于比对，不被当作额外采集指令；不会沿其路径去找文件
- 不递归扫描工作区、用户目录或其他缓存；不读取环境变量中的凭据
- 不收集 `.mph`、商业二进制、许可证文件、加密 PMIC 模型、SQLite 数据库、`.env`、完整 engineering-evidence.zip 或旧运行集
- 不导入/执行采来的 Python、C、Java、电路文件；也不加载 NPZ 中的数组或 pickle

单个普通文件默认上限 16 MiB；JSON 固定上限 8 MiB。缺失文件保留缺失状态，不从旧归档或别的运行偷偷补齐。

## 4. 如何理解校验结果

- `transport_integrity=pass`：所有清单中的字节、分块、ZIP结构及白名单已独立检查
- `source_binding=pass`：已收集且需核对的版本、输入/阶段/摘要关系一致，不表示求解器真的执行过
- `source_binding=incomplete`：关键输入、Result或阶段证据不够
- `source_binding=fail`：版本/哈希/绑定不一致、非法JSON或不安全路径；需要检查报告
- `evidence_completeness=partial`：本次白名单中至少有文件缺失、超限或阶段键无法解析，不能当成全部材料齐全
- `scientific_validation=not_performed`、`authentication=not_provided`：始终保留；普通哈希没有数字签名或运行真实性证明

报告会将 implementation 与提交 `338d60384d5805abf1e02252a4513860066a2c39` 的八个已核实源码摘要比较，并核对 acceptance runner、Result↔cases/receipt、完整 design-spec、physics_hash、阶段键/输入、缓存文件摘要、返回值副本和阶段间依赖。也检查 Result 的 energy_ledger 与采集文件是否一致。

原源码未定义可用于此处的顶层 `task_id`/`run_id`。工具不会发明这两个字段，也不根据目录名假定某一次运行真实完成。若已有来自独立来源的 Result SHA-256，可在采集和接收校验时分别加上：

```bash
--expect-result-sha256 "baseline=已独立确认的64位小写SHA256"
```

校验器只信任本次命令显式传入的预期值，不将包内自行宣称的预期摘要当成独立证明。

版本不同（包括另行修复的 cache-v2 实现）会报告不匹配。请保留它作为另一版证据，不要改名伪装成 338d603 的原版运行。

退出码：0 表示打包或传输校验完成且没有已检出的绑定失败；2 表示失败或安全/格式/绑定错误。默认允许带缺失的小包；校验器加 `--require-complete` 后，材料不齐返回 3。退出 0 也不是科学验收通过。

## 5. 明确的证据边界

- JSON/CSV/log 能核对报告值与关联，不能独立复算原生瞬态极值、机械/压电能量账或采样网格间的掉电行为
- 收到 RAW 仍需要后续独立解析和数值检查；本工具只保存/校验字节，未解析 RAW
- 已发布电路的 `.save` 没有保存所有辅助电源轨观察量。原始 RAW 的存在也不能证明 VIN2/CAP 辅助轨充放电已被验证；补观察量须另建明确版本的新测试电路，不能回写或冒充旧运行
- COMSOL 场收敛、完整轨迹 FEM、实际硬件和商业工具原生重跑都未被本工具证明
- 最小包故意省略大量文件，因此不宣称所有缓存文件或整个工程归档已验证
- 采集前与接收校验时还会扫描有界的常见凭据标记（如私钥、API token、Authorization/password字段）。疑似含凭据时整文件拒收，不回显值、不静默脱敏；可分享ZIP写入前完成扫描。NPZ/RAW 等二进制只做字节标记扫描，不解密或解包其中内容；扫描并不能识别任意编码或未知格式的凭据，固定白名单也不是对文件内容绝无敏感信息的保证。请在分享前检查原始日志/输入中的信息

## 6. 本工具测试

```bash
python3 -m unittest discover -s tests -v
```

测试只创建临时合成数据：普通/RAW范围、大小限制、路径穿越、链接/FIFO、缺失、内容篡改、缓存值不一致、版本/运行哈希、ZIP篡改、重复/额外成员、分卷复组、只读原件与权限。`example-manifest.json` 也是合成示例，不是实际原生运行的清单。
