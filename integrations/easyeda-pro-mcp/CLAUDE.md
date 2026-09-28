# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

零外部依赖的 Node ESM(`.mjs`),Node >= 20。背景、工具清单、EDA API 本身的坑见 README。

## 命令

```bash
npm test                                  # 三套自检,不需要 EasyEDA、不需要板子
node src/ws-server.mjs --self-test        # RFC 6455 边界
node src/bridge-embedded.mjs --self-test  # 线协议:多窗口/超时链/分块重组/断线
node src/eda-target.mjs --self-test       # 页 uuid → 窗口的定位(两个假窗口)+ 横幅
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | node src/eda-mcp-server.mjs
cd eext && pnpm install && pnpm run build  # 独立 pnpm 工程(TS),另有 pnpm run typecheck / lint / fix
```

没有测试框架:`selfTest()` 是文件内一个函数,跑完一串打勾,**没有单条过滤**。主仓库没有 lint。

自检要判 `isMain`,不能只判 argv —— `bridge-embedded --self-test` 会 import `ws-server`,后者看到同一份 argv 会把自己的自检也跑起来。

## 架构

```
MCP host --stdio JSON-RPC--> eda-mcp-server --HTTP--> bridge --WS--> EasyEDA(eext)
```

`ensureBridge()` 双模:扫 49620-49629,扫到已有 bridge 就当它的 HTTP 客户端(多个 AI 工具共享同一批 EDA 窗口),没扫到就在**自己进程内**起一个。内嵌那份的 HTTP API 与独立 bridge 完全一样(`/health` `/eda-windows` `/eda-windows/select` `/execute`)——这是刻意的,**别动这四个端点的形状**。

`ws-server.mjs` 手写 RFC 6455 子集:eext 只能用 `eda.sys_WebSocket` 往外连,而 Node 没有内置 WS 服务端,引 `ws` 就破了零依赖。

| 文件 | 边界 |
|---|---|
| `eda-mcp-server.mjs` | MCP 协议 + 19 工具;1500 行里绝大部分是工具描述 |
| `bridge-embedded.mjs` | 窗口注册表 / 路由 / 超时 / 分块重组。按线协议实现,不复制 eext 的实现 |
| `ws-server.mjs` | RFC 6455 子集,不做扩展协商 / 子协议 / 客户端模式 |
| `bridge-client.mjs` | **唯一一份**传输底座(找桥 / 发 HTTP / 拆信封 / 解析 `--window`),不碰 EDA 语义 |
| `eda-target.mjs` | **唯一一份**目标判定(`--page` uuid → 哪个窗口)+ 作用域横幅。EDA 语义,所以不在 bridge-client 里;脚本 import 它,自检里的 bridge 走动态 import(裸脚本不该拖进 ws-server) |
| `sch-netlist` `sch-netcheck` `pcb-dfm-check` `capture-canvas` | EDA 语义层;双面:CLI + 被 import 时进程内直调 |
| `freerouting-mcp-server.mjs` | 另一个独立 MCP server,与这条链路无关 |

新脚本一律 import `bridge-client.mjs`,别再抄一份 —— 那四个脚本曾各抄一遍,加一个特性改了五处。线协议定义在 `eext/src/index.ts`,清单在 `bridge-embedded.mjs` 文件头。

## 四条不变量

**超时链外松内紧:`MCP HTTP = t+15s > bridge = t+5s > eext = t`(默认 25s,上限 600s)。** 反了就拿不到 EDA 的真实报错,只拿到 `bridge request timeout`;改一层要看另两层。分块重组期间必须给定时器续期,否则大结果传一半被判超时。

**活动窗口会飘。** 窗口 id 每次连接都是新 `randomUUID()`,认不回原窗口;活动权在 `eda_windows_select` 和**断线自动移交**时易主(原窗口重连也拿不回)。所以工具收可选 `windowId`,脚本收 `--window` / `EDA_WINDOW_ID`。`parseWindowArg()` 的 `rest` 必须摘干净 `--window` 及其取值 —— 脚本把裸参数当位号,不摘干净只在多窗口时才犯。

**⛔ 页 uuid 不是窗口选择器 —— 除非你自己让它是。** `openDocument(uuid)` 在没有这份文档的窗口里按签名返回 `undefined`,调用方不检查就接着读**那个窗口原本开着的文档**(2026-08-05:要 BOARD-A `aaaa1111…`,拿回另一窗口的 `cccc5555…`,57 个别的板的网络,零报错)。凡是接受页 uuid 的入口都必须走 `resolveTarget()`:**用 uuid 反查窗口**,0 个 / >1 个 / 那页不是当前文档 ⇒ 一律 `TargetError` 退出 5(和"读到了但有问题"的 1 分开),**绝不退回活动窗口**;没给目标时把活动窗口 id **钉死**再开跑,多来回的脚本才不会前半段一块板后半段另一块。位号位置上出现 uuid 也要 `assertNoUuidArgs()` 拦下 —— 一个匹配不上的位号 = 空过滤器 = 报告照出、不报错。

**作用域横幅。** 一个工程多块板、位号按板独立编号、页名跨板重名 ⇒ 读错板和读对的长得一样,所以每条返回前置 `[EDA] proj=… | board=… | doc=…`(`SCOPE_JS` + `edaScope()` + `withScope()`)。**加新工具必须同时看 `NO_SCOPE_TOOLS`**(纯本地,不为贴横幅把 bridge 拉起来)**和 `SCOPE_MUTATING_TOOLS`**(会切板切页,横幅要在 handler 跑完之后再探),漏了就报错板。

## 工具描述就是产品

价值不在转发,在于把实测结论(哪个字段恒为 undefined、哪个方法是空操作、旋转基准差在哪)编码进 description 随 `tools/list` 下发。写新工具按这个标准写。

代价是 `tools/list` 每个会话都要付:跨工具的公共规则放 `SERVER_INSTRUCTIONS`(整份只付一次),别复制进 N 个 schema(`WINDOW_ID_PROP` 只留一句就是为此)。改工具名走 `TOOL_ALIASES` —— 旧名仍可调用,但不列进 `tools/list`。

「库存分两个池子」那条结论散在四处,改一处要一起改:`LIB_SEARCH_FACTS`、`eda_datasheet` 与 `eda_smt_stock` 各自的 description、`eda_lib_search` handler 的 `note`,以及 README。

## 硬约束

- **零外部依赖**:装机没有 `npm install` 这一步,裸脚本要能直接 `node xxx.mjs` 跑。
- **stdio**:协议走 stdout(逐行 JSON,不能含内嵌换行),日志全走 stderr。往 stdout `console.log` 一句就打崩会话。
- **不提交 GPL 二进制**:仓库 Apache-2.0,Freerouting 是 GPL-3.0,jar 由用户自备(`FREEROUTING_JAR`)。
- **改 `eext/` 要更新 `eext/CHANGES.md`**(Apache-2.0 §4(b) 的要求);那个目录的代码风格按 `eext/AGENTS.md`。
- `eda_api_lookup` 依赖的 references/ 本仓库不分发,解析顺序见 `resolveReferencesDir()`。
