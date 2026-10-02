# Studio 液态玻璃增强 · BFA-034

2026-10-02，前端视觉范围。

## 实现

- 以浅蓝与中性色背景提供可透出的底层颜色，导航和左右侧栏使用透明材质、背景模糊、饱和度和内侧高光。
- 输入框增加连续圆角、双层边缘和柔和悬浮阴影；输入焦点有清晰描边。发送与导出按钮使用带高光的蓝色材质。
- 产品预览的选中标签、大图按钮、范围选择器和弹出菜单统一为玻璃控件。
- 交付用途选择、选中反馈与导出操作区增加层次，文件清单、失败信息和设计结论保持可读内容底色。
- 悬停抬升 2px、按压反馈与原有标签滑动衔接；没有后台指针监听、持续装饰动画或新依赖。不可用的报告选项不产生悬停抬升。

## Apple HIG 的应用

使用本机 apple-hig 的 materials 等参考。材料指导为：

> Use Liquid Glass for controls and navigation (such as tab bars and sidebars) floating above content. Let content scroll and peek through while preserving control and navigation legibility.

同一指导还明确不要将 Liquid Glass 用于内容层（短暂激活的交互控件除外）。因此主要玻璃效果集中于控件、导航和浮层；产品正文与验证结果使用普通内容材质。这里是网页 CSS 的视觉表达，不宣称原生 Apple Liquid Glass 或物理折射。

## 验证

`./init.sh` 完成：436 项 Python 测试通过，SDK/World Studio 类型检查、构建与 2803 样本复现通过。没有新增付费模型或 COMSOL/LTspice 运行。

真实浏览器检查：1280×720 与 390×844；新项目输入焦点，左右侧栏，产品展示，交付资料选择，键盘焦点与交付区滚动（scrollTop=453），Studio/Lab 切换。未发现横向溢出，浏览器错误日志为空。最终恢复默认窗口尺寸。

深色、减少透明度、增强对比度和减少动态包含回退规则；本轮通过源代码审查，未切换操作系统设置验证。无 CSS backdrop-filter 支持时使用实色回退。

证据：`/Users/depengsu/Documents/bf-agent-workbench/verification/studio-glass-20261002/`。首页、产品、交付、手机端与右侧面板截图均已保存。

只修改 `apps/agent-studio/studio.css` 和配套工程状态/验收文档，不改后端、模型预算、实验条件或工程验收结果。未提交或推送 GitHub。
