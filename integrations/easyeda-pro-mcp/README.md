# easyeda-pro-mcp

**EasyEDA Pro (嘉立创EDA专业版) 的非官方 MCP server** — 让 AI agent 直接读写原理图与 PCB。**零外部依赖**,一条命令跑起来。

本项目与嘉立创 / JLCEDA 无隶属关系,也未获其背书。「EasyEDA」「嘉立创EDA」是其各自所有者的商标,此处仅用于说明本项目与什么互操作。

```jsonc
// .mcp.json
{ "mcpServers": { "eda": { "type": "stdio", "command": "node",
                           "args": ["/path/to/easyeda-pro-mcp/src/eda-mcp-server.mjs"] } } }
```

## 它解决什么

EasyEDA Pro 的扩展 [Run API Gateway](https://github.com/easyeda/eext-run-api-gateway) 提供了一条「往 EDA 里塞一段 JS 并拿回结果」的通道。够用,但**不自描述**:调用方必须**已经知道** `eda.*` 那 120+ 个类怎么调,而 agent(尤其是冷启动的子 agent)不知道。

本项目把这条通道包成 MCP,并且**把知识编码进工具描述里**随工具一起下发:

- `eda_api_lookup` — API scheme 发现,写代码前先查签名,别猜(三档粒度,默认档比整篇省 ~13x)
- 19 个工具覆盖定位 / 器件表 / 引脚 / 摆件 / 选型 / 连通性 / 截图 / DFM 预检
- 每条返回都前置 `[EDA] proj=... | board=...` **作用域横幅** —— 一个工程可以有多块板,位号**按板独立编号**,读错板的结果和读对的**长得一模一样**

## 装

需要 **Node >= 20**。没有 `npm install` 这一步。

1. **装扩展**:EasyEDA Pro -> 扩展 -> 导入 -> Run API Gateway([上游](https://github.com/easyeda/eext-run-api-gateway),或本仓库 `eext/` 的改版)。装完在菜单里点一次 `API Gateway -> Reconnect`(扩展的激活挂在启动事件上,装的时候不触发)。
2. **注册 MCP**:如上 `.mcp.json`。
3. 打开 EasyEDA Pro 和你的工程,调 `eda_health` 应看到 `edaConnected: true`。

**不需要单独起 bridge 进程** —— MCP server 会在自己进程内监听(端口 49620-49629 自选)。

### 可选:API 参考文档

`eda_api_lookup` 需要一份生成好的 EasyEDA Pro API 文档。本项目**不分发**它;装官方的 [easyeda-api skill](https://github.com/easyeda/easyeda-api-skill) 后会自动从 `~/.claude/skills/easyeda-api/references` 找到,或用 `EDA_API_REFERENCES_DIR` 指定。没有它,其余 18 个工具照常工作。

## 多窗口

同时开两个 EasyEDA 窗口时,**每个工具都接受可选的 `windowId`**(取自 `eda_windows`):给了就直接打那个窗口、**且不改动"活动窗口"**,两个窗口可以并发操作。

**活动窗口不可依赖。** 它在两处会变:显式 `eda_windows_select`,以及**活动窗口断线**时 —— 后者会把活动权交给另一个窗口,而**原窗口重连也拿不回来**。所以:凡是不能落错板的操作(摆件 / 删除 / 布线 / DFM 预检),**显式带 `windowId`**。

裸脚本同样支持 `--window <id>`(或 env `EDA_WINDOW_ID`)。

**⛔ 页 uuid 本身不选窗口。** `dmt_EditorControl.openDocument(uuid)` 在没有这份文档的窗口里只是按签名返回
`undefined` —— 调用方一路往下走,读到的是**那个窗口里原本开着的文档**。实测(2026-08-05):要 BOARD-A 的
`aaaa1111…`,拿回来的是另一个窗口的 `cccc5555…`,57 个网络全是别的板的位号,**不报错**。

⇒ `eda_netlist` / `eda_sch_netcheck`(以及 `--page <uuid>`)把这件事反过来做:**用页 uuid 去找窗口** ——
扫所有连着的窗口,看哪个窗口的工程里有这一页;找不到 / 找到两个 / 那一页不是当前文档,一律**报错退出(5)**,
绝不退回活动窗口。没给 `--page` / `--window` 时,目标窗口在开跑前**钉死**,中途易主也飘不走(但钉的是谁仍由
bridge 决定,所以两个窗口开着就该显式给)。每份报告的**头尾各一行**作用域横幅:工程 / 板 / 页 + 页 uuid + 窗口。

## 架构

**默认:bridge 跑在 MCP 进程内。**

```
MCP host --stdio JSON-RPC--> eda-mcp-server --HTTP(自环)--> 内嵌 bridge --WS--> EasyEDA(eext)
```

**扫到已有 bridge 时自动退化成客户端**,于是多个 AI 工具可以共享同一批 EDA 窗口:

```
eda-mcp-server --HTTP--> 某个已在跑的 bridge --WS--> EasyEDA
```

扩展只能通过 `eda.sys_WebSocket` 往外连(`sys_*` 里没有任何 HTTP/fetch 能力),所以必须有人监听 WebSocket;而 Node **没有内置 WS 服务端**,于是 `src/ws-server.mjs` 自己实现了 RFC 6455 的必要子集,这也是本项目零依赖的原因。

| 文件 | 作用 |
|---|---|
| `src/eda-mcp-server.mjs` | MCP server(19 工具) |
| `src/bridge-embedded.mjs` | 进程内 bridge:窗口管理 / 超时链 / 大结果分块重组 |
| `src/ws-server.mjs` | 零依赖 WebSocket 服务端(RFC 6455 子集) |
| `src/bridge-client.mjs` | 找桥 / 发 HTTP / 解析 `--window` 的共享底座 |
| `src/eda-target.mjs` | 页 uuid → 窗口的定位 + 作用域横幅(唯一一份;`--self-test` 用两个假窗口跑全流程) |
| `src/sch-netlist.mjs` | 权威连通性(EDA 自编译网表) |
| `src/sch-netcheck.mjs` | 几何法连通性 + 短路检测 |
| `src/pcb-dfm-check.mjs` | PCB 预检:阻焊桥 / 过孔压焊盘 / 器件体撞件 / 铺铜灌注 |
| `src/capture-canvas.mjs` | 画布截图(CLI;被 MCP server `import` 时进程内直调,图随工具结果内联返回) |
| `src/freerouting-mcp-server.mjs` | **可选**的自动布线 MCP(见下) |

## 可选:自动布线(Freerouting)

`src/freerouting-mcp-server.mjs` 是**另一个** MCP server,把本地 Freerouting 命令行包成工具(`fr_autoroute` / `fr_version`)。管线:EDA 导出 Specctra DSN -> 本 server 跑 `java -jar freerouting.jar -de in.dsn -do out.ses` -> SES 回导 EDA。文件进出 EDA 由人手动做。

```jsonc
{ "mcpServers": { "freerouting": { "type": "stdio", "command": "node",
    "args": ["/path/to/easyeda-pro-mcp/src/freerouting-mcp-server.mjs"],
    "env": { "FREEROUTING_JAR": "/path/to/freerouting-2.2.4.jar" } } } }
```

**jar 用户自备,本项目不分发** —— [Freerouting](https://github.com/freerouting/freerouting) 是 **GPL-3.0**,而本仓库是 Apache-2.0。本 server 只是 `spawn` 一个独立进程(不链接、不嵌入),所以包装器本身可以是 Apache-2.0;但把 GPL 二进制打进发行包会给整个仓库拖进 GPL 的分发义务。去 [releases](https://github.com/freerouting/freerouting/releases) 下载后设 `FREEROUTING_JAR`。

**为什么不用官方那个 MCP**:官方 npx MCP 走 `api.freerouting.app` 公有云,**会把你的 `.dsn` 上传到第三方**。本 server 全程本机、无网络、无 API key,并默认关闭遥测上报 + 无头运行。(另:已发布的 jar <= 2.2.4 **不含**内建 MCP —— 官方文档里 `--mcp_server.stdio=true` 那条只在 master 源码里,需自行编译。所以这里包的是稳定的 batch CLI。)

## 测试

不需要 EasyEDA,也不需要板子:

```bash
npm test        # = ws-server / bridge-embedded / eda-target 的 --self-test
```

三套自检共 50 项,覆盖 RFC 6455 的边界(长度档 / 分片跨包 / 掩码 / 控制帧)、bridge 的线协议(多窗口定向 / 超时链 / 分块重组 / 断线时在途请求立即失败),以及**多窗口定位**(用两个假窗口复刻"页 uuid 落到别的板上"那次事故:页 uuid 选窗口 / 找不到就报错 / 不给目标时钉死活动窗口)。

## 已知限制

- **`eda_api_lookup` 需要外部文档**(见上),本项目不分发。
- **铺铜不能通过 API 重灌** —— EasyEDA 的 API 没有"重新灌注"入口(`pcb_PrimitivePoured.create/modify` 是空函数体)。`pcb-dfm-check --only pour` 只能回答「灌没灌过」,**回答不了「是不是最新的」**(没有脏标记/时间戳),所以改完走线后**必须由人在 EDA 里手动重灌**。
- **内电层:读得到,写不了。** 能**验证**「哪个网被指派到哪个内电层」,但要**从网络那一侧**查 —— `pcb_Layer.getAllLayers()` 不返回 net 字段:
  ```js
  const prims = await eda.pcb_Net.getAllPrimitivesByNet('GND');
  const inner = prims.filter(p => p.pcbItemPrimitiveType === 'Inner');  // 再按 p.layerId 分组
  ```
  注意字段是 `layerId` 不是 `layer`(返回纯数据对象,无 `getState_*`);过孔的 `layerId` 是 `undefined`(跨层)。**必须做对照**:还要验其它电源网在同样两层上是 0 个,否则只证明了"有东西",没证明"没指派错"。创建 / 分割 / 指派内电层**没有写接口**,只能在层管理器里点。
- **`dmt_EditorControl.zoomToRegion()` 在这个网关下是空操作**(恒返回 true 但视口不动)。截图取景走 `zoomTo()` / `zoomToSelectedPrimitives()`。
- **库存/价格不在 EDA API 里** —— `lib_*` 的 `jlcInventory` / `lcscInventory` / `jlcPrice` 恒为 undefined。补这个缺口的两个工具查的是**两个不同的池子**:`eda_smt_stock` = JLC **贴装库**(能不能贴、基础库/扩展库、贴装库存),`eda_datasheet` = **LCSC 商城**(价格阶梯 + datasheet)。**商城有货 ≠ 贴得了** —— 要贴装的 BOM 以 `eda_smt_stock` 为准。
- **MCP 重启 = 所有 EDA 窗口重连**(内嵌 bridge 随进程走)。重连全自动、约 15s,但重连后活动窗口按顺序重定,所以更要显式带 `windowId`。

## 许可

[Apache-2.0](LICENSE)。归属与上游关系见 [NOTICE](NOTICE)。

`eext/` 若存在,是 [easyeda/eext-run-api-gateway](https://github.com/easyeda/eext-run-api-gateway)(Apache-2.0, © 2024 JLCEDA)的**修改版**,改动列在 `eext/CHANGES.md`。其余全部为原创实现。
