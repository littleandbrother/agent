---
name: bf-coupled-mechanical
description: "一次提取机械参数、几何差异和接口，绑定当前候选。"
---

先读 bf_design interfaces，定位实际 PCB 板框、孔位、坐标和 CAD 作业。参数或差异用 bf_workspace 批量读来源文件。

几何集中输出尺寸、实体数、孔位、干涉及 STEP/预览引用；见 [参数与几何](references/geometry.md)。未变的 STEP 和成功作业复用。

机械输入记录位移、频率、单位和参数文件 SHA。C(x)、电荷、损耗、装配变换由 BF 选择并给依据；变化影响的源模型、电路和装配分别重验。

SPICE 先取数值摘要及 RAW 来源，再按节点/区间读取，见 [数值结果](references/spice.md)。模型端口与原生电路引脚逐项对应。
