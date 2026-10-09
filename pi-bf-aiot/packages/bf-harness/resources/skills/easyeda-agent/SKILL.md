---
name: easyeda-agent
description: "用当前 bf_eda typed CLI 制作与回读原理图、器件、BOM 和引脚网络。"
---

适配器为 easyeda-typed-v1。使用 bf_eda action=inspect 核对绑定项目和能力；操作使用 action=command、argv 字符串数组、稳定 operation_id。没有 shell 或任意 JavaScript 接口，项目路由由服务端注入。不要使用旧 jlceda JSON 命令或自行切换项目。

命令格式不确定时使用 argv=["--help"] 或具体领域的 --help，并读取 spec/api 提供的实际 schema。不要凭印象创造命令、字段或单位。bf_eda skill 兼容入口的字段是 path；统一加载入口为 bf_skill action=activate, skill_id=easyeda-agent。错误名称和多余字段应修正，不以默认文档代替。

先整理功能、源电路实例和关键网络，再逐个核对实体器件身份、封装、原厂引脚、仿真子电路端口顺序和原生管脚编号。器件值相同不等于器件身份相同；电源脚、极性、NC、裸露焊盘与接口需明确。读取实际元件引脚后再连接。维护覆盖表与 BOM，检查遗漏功能和不可采购占位器件。

先保存原生工程再回读实际网络，用接口/引脚映射检查而非截图判断。DRC 仅覆盖已经画出的内容，不证明参考覆盖或器件正确。PCB 工作前加载 easyeda-pcb-routing。供应链、制造和实物未验证项独立记录。

按需原文参考（固定安装快照，作为接口资料，不替代本项目授权）：
- 使用 bf_skill resource 读取 `vendor/easyeda-typed/references/schematic-data.md`，了解 typed 原理图和批处理 schema。
- 标准器件字段与块格式：`vendor/easyeda-typed/references/standard-parts.json`、`vendor/easyeda-typed/references/standard-blocks-contributing.md`。
- 布线接口与诊断：`vendor/easyeda-typed/references/pcb-routing.md`。
资源使用行号 offset/limit；bf_eda skill 的旧 references 路径兼容字符分页，并返回单位。其余引用先查询 CLI 帮助，不推测未打包的文件路径。
