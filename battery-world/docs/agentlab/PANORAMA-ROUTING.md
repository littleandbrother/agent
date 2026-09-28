# 全景连线整理

2026-09-24 · BFA-020-panorama-routing

全景原先把所有关系画成端点间的直线，跨行关系会穿过卡片，多条线在同一端口叠加。现在沿卡片间隙绘制带圆角的正交折线，为每条关系分配独立端口；路径选择同时考虑长度、转弯、已有线路占用和交叉。选中模块的关系高亮并绘制在上层，交叉处使用背景描边，便于跟随箭头辨别连接。

只修改 `apps/agent-studio/panorama.js` 和 `panorama.css` 的展示逻辑。现有 13 个模块、21 条关系、方向及说明保留，服务端架构声明和研究数据不变。节点仍可拖动，路线随位置重新计算；位置保存、重置、搜索、版本对比、控制台跳转保持。选择模块不改变路径，避免图形跳动；同一布局的路径缓存，拖动更新合并到动画帧。

浏览器验收使用本机 Chrome headless 访问实际 `127.0.0.1:8768` 服务：

- 13 个节点、21 条连线，没有遗漏。
- 沿 SVG 实际绘制路径每 2 个画布单位取样，默认布局、拖动布局、刷新恢复及窄窗口均未发现线进入卡片内部。
- 选择运行时模块时 5 条关联高亮，路径保持；端点方向沿用声明关系。
- 拖动研究节点后自动重新排线，刷新恢复、重置、搜索、版本对比、900 px 显示及模式跳转通过。
- 页面脚本错误为空；JavaScript 语法检查通过。

这是展示层路由，关系本身仍为架构声明。并不保证任意人工堆叠的卡片都能获得可见连接：无法找到通道时保留关系记录并显示“部分卡片过近”提示，可拖开卡片或重置布局。完整关系清单仍在右侧模块详情中。

验证目录：`/Users/depengsu/Documents/bf-agent-workbench/verification/panorama-routing-20260924/`，包含修改前源码、几何读回、浏览器脚本/回执、总览及选中状态截图、完整 `init.log` 和最终 `receipt.json`。

复核命令（在 battery-world 目录执行）：

```sh
rtk proxy node --check apps/agent-studio/panorama.js
rtk proxy node /Users/depengsu/Documents/bf-agent-workbench/verification/panorama-routing-20260924/browser-check.cjs
rtk proxy ./init.sh
```

完整 `./init.sh` 通过 352 项 Python 测试（173.026 秒），SDK/Studio 类型、构建及复现通过。

现有已打开标签页若仍保留旧脚本，点击页面“更新界面”即可重载新版并保留草稿。没有发起模型调用或工程任务；没有 Git 提交。
