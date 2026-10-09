---
name: easyeda-pcb-routing
description: "用 typed EasyEDA 完成板框、布局、布线与保存回读后的原生 DRC。"
---

适配器仅为 easyeda-typed-v1；先加载 easyeda-agent。先读取实际原生原理图、网络、封装与 PCB，确认功能覆盖、引脚对应和板框/安装约束。元件尺寸与布线坐标的单位以当前 API 为准。关键电源回路、天线净空、接口和安装禁布区优先。

对已有 PCB 做最小修改，保留布局和工程身份。新布线前查询既有作业及结果。使用 bf_eda action=command 的 typed CLI，先读取 pcb --help 获取本版本参数；router 与窗口路由由服务端选择。长作业通过 job_id 等待，不用新 operation_id 绕过超时或 UNKNOWN。

离线路由成功、生成 SES、导入 SES、原生 PCB 保存以及保存后 DRC 是不同证据。保存并重新读取目标 PCB 后检查连通性、Netlist、间距、板边铜距离以及走线/焊盘规则。按规则类别修复；不降低规则或删网以获得通过。原生命令退出码为零不能覆盖 result.passed=false。

从回读板框与接口位置更新机械输入；尺寸或安装点变化使对应装配检查失效。导出制造文件后核对层、孔、板框和源 PCB 身份。包里包含原生源、制造文件、BOM、检查回执和未通过项；文件存在不代表可制造。
