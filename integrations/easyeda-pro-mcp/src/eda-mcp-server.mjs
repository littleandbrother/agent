#!/usr/bin/env node
/**
 * EasyEDA MCP Server (local stdio)
 *
 * 把「EasyEDA 桥接」封装成一个真正的 MCP server,让任何 MCP 客户端(Claude Code 主
 * agent / 子 agent、队友的其他 AI 工具)都能直接看到**调用 API 的 scheme**——
 * 不再依赖装了 easyeda-api skill 才知道怎么调。
 *
 * 架构(search + execute 模式,官方 build-mcp-server 对「大 API 面」的推荐):
 *
 *   ┌──────────┐  stdio JSON-RPC  ┌──────────────┐  HTTP  ┌──────────────┐  WS  ┌──────────┐
 *   │ MCP host │ ◄──────────────► │  这个 server  │ ◄────► │ 内嵌 bridge   │ ◄──► │  EasyEDA  │
 *   │ (agent)  │   (MCP tools)    │ (thin adapter)│ /exec  │  (49620-9)    │      │  (eext)   │
 *   └──────────┘                  └──────────────┘        └──────────────┘      └──────────┘
 *
 * bridge 默认跑在**本进程内**(见下 ensureBridge:扫到别人的就当客户端,没扫到就自己当)。
 *
 * 它本身是**无外部依赖**的薄适配层:
 *   - eda_api_lookup —— 直接读磁盘上的 references/,不需要 bridge / EDA。是 scheme 发现工具。
 *   - eda_execute / eda_health / eda_windows[_select] —— 转发到后台 bridge(不在则自动拉起)。
 *
 * stdio 约定:协议消息走 stdout(逐行 JSON,不能含内嵌换行);所有日志走 stderr。
 */

import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { basename, dirname, join } from 'node:path';
import { homedir, tmpdir } from 'node:os';
import { createInterface } from 'node:readline';
// ⭐ 找桥 / 发 HTTP 的那一份共享底座(裸脚本也用同一个,见 ./bridge-client.mjs)
import { httpGetJson, httpPostJson, findBridge, execute as bridgeExecute } from './bridge-client.mjs';
import { resolveTarget } from './eda-target.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ─── Config ─────────────────────────────────────────────────────────
const SERVER_NAME = 'easyeda';
// 版本号跟 package.json 走(首次公开发行 = 0.1.0)。
// 下面 1.1.0 ~ 1.7.0 是公开前的内部迭代号,只留作特性时间线,不再往上加:
// 1.7.0: eda_screenshot 直接把图内联返回(省掉 agent 再 Read 一次 = 一整个回合);
//        改进程内直调 capture-canvas.mjs(不再 spawn),作用域探测并进同一次 eval(省一次往返);
//        新增 eda_smt_stock(JLC 贴装库:能不能贴 / 基础库还是扩展库 / 贴装库存)——
//        与 eda_datasheet 的 LCSC 商城库存是【两个池子】,商城有货 ≠ 贴得了
// 1.6.0: eda_netlist 加 "Nets: 0 不可信" 告警(实测整页接好仍报全部未连);
//        eda_place_components 记三条引脚几何实测(间距按器件/pin1 侧按器件/create 与 modify 的旋转基准不同)
// 1.5.0: 新增 eda_datasheet(LCSC 详情:datasheet 下载 + 库存 + 价格 —— EDA API 给不了的那三样)
// 1.4.0: eda_place_components 加 expectBoard 板名闸门;eda_lib_search 返回 jlcClass(基础/扩展库)
// 1.3.0: 新增 eda_lib_search / eda_delete / eda_wire(布线需显式指令)
// 1.2.0: eda_api_lookup 默认只吐方法清单(+member/full 钻取);新增 eda_place_components
// 1.1.0: 每个工具返回值前置 [EDA] 作用域横幅(多板工程防摆错板)
const SERVER_VERSION = '0.1.0';
const AUTOSTART_BRIDGE = process.env.EDA_MCP_NO_AUTOSTART !== '1';

// references/ 目录:env 覆盖 → 仓库根的 references/(本仓库**不分发**,自己放才有)→ skill(兜底)
function resolveReferencesDir() {
  const candidates = [
    process.env.EDA_API_REFERENCES_DIR,
    join(__dirname, '..', 'references'),
    join(homedir(), '.claude', 'skills', 'easyeda-api', 'references'),
  ].filter(Boolean);
  return candidates.find((p) => existsSync(join(p, '_quick-reference.md'))) || null;
}

function log(...args) {
  process.stderr.write(`[eda-mcp] ${args.join(' ')}\n`);
}

let bridgeStarting = null;
// ⭐ 双模(2026-08-05):
//   扫到已有 bridge  → 当它的 HTTP 客户端(老行为)⇒ **多个 AI 工具共享同一批 EDA 窗口**
//   没扫到           → **自己当 bridge**(进程内监听,见 ../bridge-embedded.mjs)
// 内嵌那份对外暴露完全一样的 HTTP API,所以:① 下面 19 个工具一行都不用改;
// ② 后起的第二个 MCP server 会扫到我们、自动退化成客户端 —— 共享特性不会因为"合进一个进程"而丢。
// 这也顺手去掉了"再 spawn 一个子进程"这条路:少一个进程、少一次端口竞争。
let embedded = null;
async function ensureBridge() {
  const found = await findBridge();
  if (found) return found;
  if (embedded) return { port: embedded.port, embedded: true };
  if (!AUTOSTART_BRIDGE) return null;

  if (!bridgeStarting) {
    bridgeStarting = (async () => {
      try {
        const { startEmbeddedBridge } = await import('./bridge-embedded.mjs');
        embedded = await startEmbeddedBridge({ log: (m) => log(`[embedded] ${m}`) });
        log(`embedded bridge listening on 127.0.0.1:${embedded.port} (in-process, no child)`);
        return { port: embedded.port, embedded: true };
      } catch (e) {
        log(`embedded bridge failed to start: ${e && e.message ? e.message : e}`);
        return null;
      }
    })();
  }
  const res = await bridgeStarting;
  bridgeStarting = null;
  return res;
}

// 在 EDA 里跑一段 JS,拿回结果或抛错(固化工具的公共底座)
// timeoutMs 省略 = 沿用 bridge 默认;给了就一路传下去,并让外层 HTTP 比它更松
// (否则 EDA 的报错还没回来这里就先超时,拿到的是 'bridge request timeout' 而非真因)。
async function runOnEda(code, windowId, timeoutMs) {
  const bridge = await ensureBridge();
  if (!bridge) throw new Error('No EDA bridge and the in-process one failed to start (all ports 49620-49629 busy?). Check stderr for [eda-mcp].');
  const resp = await bridgeExecute(bridge.port, code, { windowId, timeoutMs });
  if (resp && resp.success) return resp.result;
  throw new Error(resp ? resp.error : 'no response from bridge');
}

// 找辅助脚本(网检/网表/预检):env → 同目录 → skill scripts/
// 截图不在此列:它已改成 import ./capture-canvas.mjs 进程内直调,同目录那份才与本 server 版本对齐。
const SCRIPT_ENV = {
  'sch-netcheck.mjs': 'EDA_SCH_NETCHECK', 'sch-netlist.mjs': 'EDA_SCH_NETLIST',
  'pcb-dfm-check.mjs': 'EDA_PCB_DFM_CHECK',
};
function findScript(basename) {
  const candidates = [
    process.env[SCRIPT_ENV[basename] || ''],
    join(__dirname, basename),
    join(homedir(), '.claude', 'skills', 'easyeda-api', 'scripts', basename),
  ].filter(Boolean);
  return candidates.find(existsSync) || null;
}

// 跑一个 node 脚本,收集 stdout/stderr + 退出码
function spawnScript(scriptPath, args = [], timeoutMs = 60000) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [scriptPath, ...args], { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    const timer = setTimeout(() => { child.kill('SIGKILL'); }, timeoutMs);
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (err += d));
    child.on('close', (code) => { clearTimeout(timer); resolve({ code, stdout: out, stderr: err }); });
    child.on('error', (e) => { clearTimeout(timer); resolve({ code: -1, stdout: out, stderr: String(e) }); });
  });
}

// EDMT_EditorDocumentType 常见值 → 人类可读
const DOC_TYPE = {
  '-1': 'home', '0': 'blank', '1': 'schematic-page', '2': 'symbol', '3': 'pcb',
  '4': 'footprint', '12': 'pcb-2d-preview', '15': 'pcb-3d-preview', '26': 'panel',
};

// ─── 作用域横幅(每个 EDA 工具的返回值都带上「在哪块板 / 哪一页」)──────────
// 起因:一个工程可以有多块板子(DMT_Board.createBoard),base 与拓展卡同工程并存。
// 「当前板子搞错 → 元件摆到另一块板上」是最容易犯且最难发现的错。
// 与其靠调用方每次先 eda_context,不如让**每次工具返回都自带**当前板/页,想忽略都难。
const SCOPE_JS = "let s={},b=null;"
  + "try{const p=await eda.dmt_Project.getCurrentProjectInfo();s.project=p?(p.friendlyName||p.name||''):'';}catch(e){}"
  + "try{b=await eda.dmt_Board.getCurrentBoardInfo();if(b){s.board=b.name||'';s.boardPcb=b.pcb?b.pcb.name:'';}}catch(e){}"
  + "try{const all=await eda.dmt_Board.getAllBoardsInfo();if(all){s.boardCount=all.length;s.boards=all.map(x=>x.name);}}catch(e){}"
  + "try{const d=await eda.dmt_SelectControl.getCurrentDocumentInfo();if(d){s.documentType=d.documentType;"
  + "if(d.documentType===1){const pg=(await eda.dmt_Schematic.getAllSchematicPagesInfo()||[]).find(x=>x.uuid===d.uuid);s.page=pg?(pg.name||pg.friendlyName||''):'';}"
  + "else if(d.documentType===3){s.page=s.boardPcb||'';}}}catch(e){}"
  + "return s;";

// 短 TTL 的 promise 缓存:一串连续调用只探一次,不给每个工具都加一次往返。
const SCOPE_TTL_MS = 1500;
const scopeCache = new Map(); // windowId|'' -> {at, promise}

async function edaScope(windowId) {
  const key = windowId || '';
  const hit = scopeCache.get(key);
  if (hit && Date.now() - hit.at < SCOPE_TTL_MS) return hit.promise;
  const promise = runOnEda(SCOPE_JS, windowId).catch(() => null);
  scopeCache.set(key, { at: Date.now(), promise });
  return promise;
}

// 一行横幅。板子 >1 时加 ⚠ + 全部板名 —— 摆错板的代价太高,值得每次都刺一下眼。
function scopeBanner(s) {
  if (!s || (!s.project && !s.board)) return null;
  const parts = [];
  if (s.project) parts.push(`proj=${s.project}`);
  if (s.board) {
    const multi = s.boardCount > 1;
    const list = multi && Array.isArray(s.boards) ? ` ⚠共${s.boardCount}块板: ${s.boards.join(' / ')}` : '';
    parts.push(`board=${s.board}${list}`);
  }
  const dt = DOC_TYPE[String(s.documentType)] || (s.documentType != null ? 'type#' + s.documentType : '');
  if (dt) parts.push(`doc=${dt}${s.page ? ':' + s.page : ''}`);
  return `[EDA] ${parts.join(' | ')}`;
}

/**
 * `page`(页 uuid)是**窗口选择器**:脚本自己会解析它,但**横幅**必须跟着落到同一个窗口 ——
 * 否则正文说 BOARD-A、横幅说 proj-b,而横幅正是给人核账的那一行,它一撒谎这套机制就白做了。
 * 顺手把解析出的窗口写回 args.windowId:横幅、作用域缓存的键、传给脚本的 `--window` 这三处
 * 必须是同一个窗口。解析失败就返回 null,让脚本去报错(它的诊断信息更全)。
 */
async function scopeForPage(args) {
  if (!args.page) return null;
  try {
    const bridge = await ensureBridge();
    if (!bridge) return null;
    const t = await resolveTarget(bridge.port, { windowId: args.windowId, pageUuid: String(args.page) });
    args.windowId = t.windowId;
    return t.probe ? { ...t.probe, documentType: t.probe.docType, pages: undefined } : null;
  } catch { return null; }
}

// 不需要横幅的工具:纯本地、不碰 EDA。
// 不碰 EDA 的工具:不探作用域,也就不会为了贴个横幅去把 bridge 拉起来
const NO_SCOPE_TOOLS = new Set(['eda_api_lookup', 'eda_datasheet', 'eda_smt_stock']);

// 会**改变**作用域的工具:横幅必须在 handler 跑完之后再探,否则报的是切换前的板/页。
// (eda_execute 是任意 JS,可能切板切页;截图/网表脚本也可能切页。)
const SCOPE_MUTATING_TOOLS = new Set([
  'eda_open_document', 'eda_activate_page', 'eda_windows_select', 'eda_execute', 'eda_screenshot',
  'eda_netlist', 'eda_sch_netcheck',
]);

// ─── References lookup (the "scheme" discovery tool) ─────────────────
let quickRefCache = null;
function loadQuickRef(refsDir) {
  if (quickRefCache) return quickRefCache;
  quickRefCache = readFileSync(join(refsDir, '_quick-reference.md'), 'utf8');
  return quickRefCache;
}

// _quick-reference.md 用 "## ClassName" 分节;把它切成 {name, text} 段
function splitSections(md) {
  const out = [];
  const lines = md.split('\n');
  let cur = null;
  for (const line of lines) {
    const m = /^## (.+?)\s*$/.exec(line);
    if (m) {
      if (cur) out.push(cur);
      cur = { name: m[1].trim(), text: line + '\n' };
    } else if (cur) {
      cur.text += line + '\n';
    }
  }
  if (cur) out.push(cur);
  return out;
}

function findRefFileByName(refsDir, query) {
  const q = query.toLowerCase().replace(/\.md$/, '');
  for (const sub of ['classes', 'enums', 'interfaces', 'types']) {
    const dir = join(refsDir, sub);
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir)) {
      if (f.toLowerCase().replace(/\.md$/, '') === q) return join(dir, f);
    }
  }
  return null;
}

// ── 类文档的三档粒度 ────────────────────────────────────────────────
// 起因(2026-08-02 实测):查 SCH_PrimitiveComponent 只为拿 create() 一个签名,
// 却吐回整类 20 个方法的完整参数表(上万 token)。而本项目把「写 eda.* 前先
// api_lookup」定成硬规矩 ⇒ 这笔钱**每写一段 EDA 代码就付一次**。
// 所以默认只给「方法清单 + 参数名」,要类型细节再按方法钻取,整篇留给 full:true。

// 参考文档全是 HTML 表格(一格一段)。把 "## <标题>" 那张表拆成 [单元格...] 的行数组。
function tableRows(content, heading) {
  const start = content.indexOf(`\n## ${heading}`);
  if (start < 0) return null;
  let end = content.indexOf('\n---', start);
  if (end < 0) end = content.length;
  const body = content.slice(start, end);
  const tbody = body.indexOf('<tbody>');            // 跳过表头那一行
  const rows = [];
  for (const chunk of body.slice(tbody < 0 ? 0 : tbody).split('<tr>').slice(1)) {
    const cells = chunk.split('</td><td>').map((c) => c
      .replace(/<\/?t[dr]>/g, '')
      .split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('<'))
      .join(' ').replace(/\\/g, '').replace(/\s+/g, ' ').trim());
    if (cells.some((c) => c)) rows.push(cells);
  }
  return rows.length ? rows : null;
}

const nameFromLink = (cell) => (cell.match(/\[([^\]]+)\]\(\.\//) || [, cell])[1].trim();

// 一行一个成员的压缩清单;返回 null = 这份文档没有该表,交给整篇兜底
function summarize(content) {
  let rows = tableRows(content, 'Methods');
  if (rows) {
    return { kind: 'Methods', lines: rows.map((c) => {
      const sig = nameFromLink(c[0] || '');
      const desc = (c[2] || c[1] || '').replace(/^\*\*_\(BETA\)_\*\*\s*/, '');
      return desc ? `- ${sig} — ${desc}` : `- ${sig}`;
    }) };
  }
  rows = tableRows(content, 'Enumeration Members');
  if (rows) {
    return { kind: 'Enumeration Members', lines: rows.map((c) =>
      `- ${c[0]}${c[1] ? ' = ' + c[1].replace(/`/g, '') : ''}${c[2] ? ' — ' + c[2] : ''}`) };
  }
  rows = tableRows(content, 'Properties');
  if (rows) {
    // 属性表列数不固定(有的有 Modifiers 列)——类型取倒数第二格,描述取最后一格
    return { kind: 'Properties', lines: rows.map((c) => {
      const name = nameFromLink(c[0] || '');
      const type = c.length >= 3 ? c[c.length - 2] : '';
      const desc = (c[c.length - 1] || '').replace(/^_\(Optional\)_\s*/, '');
      return `- ${name}${type ? ': ' + type : ''}${desc && desc !== type ? ' — ' + desc : ''}`;
    }) };
  }
  return null;
}

// 详情节标题是小写化的成员名,重载带 _1/_2 后缀(getbylcscids / getbylcscids_1)
function sectionNames(content) {
  const out = [];
  for (const part of content.split(/\n### /).slice(1)) {
    const head = part.slice(0, part.indexOf('\n')).trim().replace(/_\d+$/, '');
    if (head && !out.includes(head)) out.push(head);
  }
  return out;
}

// 取一个成员的全部重载节
function extractMemberDetail(content, member) {
  const want = String(member).toLowerCase().trim().replace(/\(\)$/, '');
  const hits = [];
  for (const part of content.split(/\n### /).slice(1)) {
    const head = part.slice(0, part.indexOf('\n')).trim();
    if (head.replace(/_\d+$/, '').toLowerCase() === want) hits.push('### ' + part.trimEnd());
  }
  return hits;
}

function apiLookup(query, member, full) {
  const refsDir = resolveReferencesDir();
  if (!refsDir) {
    return 'EasyEDA API references not found. Set EDA_API_REFERENCES_DIR to the easyeda-api skill\'s '
      + 'references/ directory (e.g. ~/.claude/skills/easyeda-api/references), or install the '
      + 'easyeda-api skill. Without it, look up signatures in the skill docs directly.';
  }
  query = String(query || '').trim();
  if (!query) return 'Provide a query: a class name (e.g. "DMT_Project") or a keyword (e.g. "createBoard", "wire", "layer").';

  // 精确类名 → 默认给方法清单;member 钻取单个成员;full 才吐整篇
  const exact = findRefFileByName(refsDir, query);
  if (exact) {
    let content = readFileSync(exact, 'utf8');
    const file = basename(exact, '.md');

    if (member) {
      const hits = extractMemberDetail(content, member);
      if (hits.length) {
        return `# ${file}.${member}${hits.length > 1 ? `  (${hits.length} overloads)` : ''}\n\n${hits.join('\n\n')}`;
      }
      const names = sectionNames(content);
      return `No member "${member}" in ${file}.\n\nMembers (${names.length}): ${names.join(', ')}\n\n`
        + `(Omit "member" for the summary list, or pass full:true for the whole doc.)`;
    }

    if (!full) {
      const sum = summarize(content);
      if (sum) {
        const lines = [...new Set(sum.lines)];   // 同名重载在汇总表里是重复行
        const header = content.slice(0, content.indexOf(`\n## ${sum.kind}`)).trim();
        const first = (lines[0].match(/- ([\w$]+)/) || [, 'name'])[1];
        return `${header}\n\n## ${sum.kind} (${lines.length}) — summary\n${lines.join('\n')}\n\n`
          + `→ Full detail (parameter TYPES, return type, remarks, every overload) for one of them:\n`
          + `   eda_api_lookup {query:"${file}", member:"${first}"}\n`
          + `→ Whole doc (long — only when you need several at once): {query:"${file}", full:true}`;
      }
      // 没有任何汇总表(类型别名等)——本来就短,整篇给
    }

    const CAP = 28000;
    if (content.length > CAP) {
      let cut = content.slice(0, CAP);
      // back off to the last method/section heading so we never truncate mid-method
      const b = Math.max(cut.lastIndexOf('\n### '), cut.lastIndexOf('\n## '));
      if (b > CAP * 0.5) cut = cut.slice(0, b);
      content = cut + `\n\n… [truncated at a section boundary; the method summary table above is complete — full doc at ${exact}]`;
    }
    return `# Full doc: ${exact}\n\n${content}`;
  }

  // 否则在 quick-reference 里搜 类名 + 方法签名
  const md = loadQuickRef(refsDir);
  const sections = splitSections(md);
  const q = query.toLowerCase();
  const classHits = [];
  const methodHits = [];
  for (const sec of sections) {
    if (sec.name.toLowerCase().includes(q)) {
      classHits.push(sec);
      continue;
    }
    const matched = sec.text.split('\n').filter((l) => l.trimStart().startsWith('- **') && l.toLowerCase().includes(q));
    if (matched.length) methodHits.push({ name: sec.name, lines: matched });
  }

  const parts = [];
  const CAP = 10000;
  if (classHits.length) {
    parts.push(`## Matching classes (${classHits.length})`);
    for (const sec of classHits.slice(0, 6)) parts.push(sec.text.trim());
  }
  if (methodHits.length) {
    parts.push(`## Matching methods (${methodHits.length} classes)`);
    for (const h of methodHits.slice(0, 25)) {
      parts.push(`**${h.name}**\n${h.lines.slice(0, 12).join('\n')}`);
    }
  }
  // 文件名部分匹配(便于 drill-down)
  const fileMatches = [];
  for (const sub of ['classes', 'enums', 'interfaces', 'types']) {
    const dir = join(refsDir, sub);
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir)) {
      if (f.toLowerCase().includes(q)) fileMatches.push(`${sub}/${f.replace(/\.md$/, '')}`);
    }
  }
  if (fileMatches.length) {
    parts.push(`## Reference docs you can look up by exact name (${fileMatches.length})`);
    parts.push(fileMatches.slice(0, 40).join(', '));
  }

  if (!parts.length) {
    return `No matches for "${query}". Try a class prefix (DMT_/PCB_/SCH_/LIB_/SYS_), a method name, or a broader keyword. `
      + `references/ is at ${refsDir}.`;
  }
  let text = parts.join('\n\n');
  if (text.length > CAP) text = text.slice(0, CAP) + '\n\n… [truncated; narrow the query or ask for an exact class name for its full doc]';
  text += `\n\n(Tip: call eda_api_lookup again with an exact class name — e.g. "${(classHits[0] || methodHits[0] || { name: 'DMT_Project' }).name}" — for its full signatures.)`;
  return text;
}

// ─── LCSC:datasheet / 库存 / 价格 ────────────────────────────────────
// 这条路不经 EasyEDA,也不经 bridge —— 直接打 LCSC 的商品详情接口。
// 存在的理由:datasheet 链接、**库存**、价格阶梯这三样 EasyEDA 的 lib_* API 一个都给不了
// (见 LIB_SEARCH_FACTS),而选型时恰恰最需要它们。
// ⚠ 只有「按 C 编号查详情」这一个口子能用:关键字搜索接口(/ftps/wm/search/global)在 WAF 后面,
//   实测 403。所以关键字检索仍然走 eda_lib_search,本工具接在它后面。
const LCSC_DETAIL = 'https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=';
const LCSC_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36';

// ⭐ JLCPCB **贴装库**(SMT assembly)查询 —— 和 LCSC 商城是**两个不同的池子**。
// 商城有货 ≠ 能贴装:贴装看的是这个接口的 componentLibraryType(base/expand)+ stockCount。
// 实测 2026-08-05:POST、无鉴权、200;keyword 支持**关键字**(含中文)与 C 编号 ——
// 这也顺带补上了 eda_datasheet 那条「LCSC 搜索接口 403 ⇒ 没有关键字搜索」的缺口。
const JLC_SMT_SEARCH = 'https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList';

async function jlcSmtSearch({ keyword, page = 1, pageSize = 10, library = '' }) {
  const res = await fetch(JLC_SMT_SEARCH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'User-Agent': LCSC_UA, Accept: 'application/json' },
    body: JSON.stringify({
      keyword: String(keyword),
      currentPage: Math.max(1, Math.round(page)),
      pageSize: Math.min(50, Math.max(1, Math.round(pageSize))),
      componentLibraryType: library, // '' = 两个库都要 · 'base' = 基础库 · 'expand' = 扩展库
    }),
    signal: AbortSignal.timeout(25_000),
  });
  if (!res.ok) throw new Error(`JLC SMT HTTP ${res.status}`);
  const body = await res.json();
  if (body && body.code !== 200 && body.code !== undefined && body.code !== null) {
    throw new Error(`JLC SMT code=${body.code}${body.msg ? ' ' + body.msg : ''}`);
  }
  const pi = (body && body.data && body.data.componentPageInfo) || {};
  const rows = (pi.list || []).map((r) => ({
    lcsc: r.componentCode,
    // ⭐ 这个字段才是"能不能贴、贵不贵"的决定项:base=基础库(不收上机费) · expand=扩展库(按料号收一次性上机费)
    library: r.componentLibraryType,
    stockSmt: r.stockCount,
    mpn: r.componentModelEn || '',
    brand: r.componentBrandEn || '',
    package: r.componentSpecificationEn || '',
    desc: r.erpComponentName || r.componentNameEn || '',
    price: (r.componentPrices || []).slice(0, 4).map((p) => ({ qty: p.startNumber, usd: p.productPrice })),
    datasheetUrl: r.dataManualUrl || r.dataManualOfficialLink || null,
  }));
  return { total: pi.total, page: pi.pageNum || page, rows };
}

function resolveManualsDir() {
  const candidates = [
    process.env.EDA_MANUALS_DIR,
    join(__dirname, '..', 'manuals'),
  ].filter(Boolean);
  return candidates.find((p) => existsSync(p)) || null;
}

// 文件名只留安全字符;MPN 里的括号是项目既有习惯(TYPE-C_16PIN_2MD(073).pdf),保留
function safeFileName(s) {
  return String(s).trim().replace(/[^\w.()+\-]+/g, '_').replace(/^_+|_+$/g, '') || 'datasheet';
}

async function lcscPart(lcsc, opt) {
  const res = await fetch(LCSC_DETAIL + encodeURIComponent(lcsc), {
    headers: { 'User-Agent': LCSC_UA, Accept: 'application/json' },
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) throw new Error(`LCSC detail HTTP ${res.status}`);
  const body = await res.json();
  const d = body && body.result;
  // HTTP 200 + result:null = 商城里没有这个料。实测常见于 **JLC-only** 料(EasyEDA 库里有、
  // JLCPCB 有基础/扩展库分类,LCSC 商城不单卖)—— 这条路就到头了,别再重试。
  if (!d) {
    throw new Error(`LCSC has no storefront entry for ${lcsc}`
      + (body && body.msg ? ` (${body.msg})` : ' (HTTP 200, result:null)')
      + ' — common for JLC-only parts; eda_lib_search may still know it, but the datasheet has to come from the vendor site.');
  }

  const params = {};
  for (const p of d.paramVOList || []) params[p.paramNameEn || p.paramName] = p.paramValueEn || p.paramValue;
  const out = {
    lcsc: d.productCode,
    mpn: d.productModel || '',
    brand: d.brandNameEn || '',
    desc: d.productIntroEn || d.productDescEn || '',
    package: d.encapStandard || '',
    catalog: d.catalogName || '',
    // ⚠ 这是 **LCSC 商城池** 的库存,**不是 JLCPCB 贴装库**的。两者是不同的池子:
    // 商城有货 ≠ 能贴装(贴装要查 JLC 的 selectSmtComponentList,基础/扩展库各有自己的备货)。
    // 字段名带上 lcscMall 前缀,免得下游把它当成"能不能下 SMT 单"的依据。
    stockLcscMall: d.stockNumber,
    stockNote: 'LCSC 商城池库存;SMT 贴装能否下单要另查 JLCPCB 贴装库(基础/扩展库),两者不通用',
    minBuy: d.minBuyNumber,
    price: (d.productPriceList || []).slice(0, 4).map((p) => ({ qty: p.ladder, usd: p.usdPrice })),
    params,
    datasheetUrl: d.pdfUrl || null,
  };
  if (!opt.download) return out;

  if (!out.datasheetUrl) { out.saved = { skipped: true, reason: 'LCSC has no datasheet for this part' }; return out; }
  const file = safeFileName(opt.name || out.mpn || out.lcsc).replace(/(\.pdf)?$/i, '.pdf');
  const path = join(opt.dir, file);
  if (existsSync(path) && !opt.overwrite) {
    out.saved = { skipped: true, path, reason: 'file already exists — pass overwrite:true to replace' };
    return out;
  }
  const pdf = await fetch(out.datasheetUrl, {
    headers: { 'User-Agent': LCSC_UA }, redirect: 'follow', signal: AbortSignal.timeout(60_000),
  });
  if (!pdf.ok) throw new Error(`datasheet HTTP ${pdf.status} for ${lcsc}`);
  const buf = Buffer.from(await pdf.arrayBuffer());
  // LCSC 出错时会回一页 HTML;不验就会存成一个叫 .pdf 的网页,而且要到有人打开才发现
  if (buf.slice(0, 5).toString('latin1') !== '%PDF-') {
    throw new Error(`downloaded ${buf.length} B for ${lcsc} but it is not a PDF (starts with `
      + `${JSON.stringify(buf.slice(0, 24).toString('latin1'))}) — nothing was written`);
  }
  writeFileSync(path, buf);
  out.saved = { path, bytes: buf.length };
  return out;
}

// ─── Tool definitions ───────────────────────────────────────────────
const CALLING_SCHEME =
  'Code runs as the body of `async function(eda){ ... }` in EasyEDA\'s browser runtime. '
  + 'RULES: (1) You MUST `return` the value — console.log is NOT captured. '
  + '(2) Almost every eda.* method is async — `await` it. '
  + '(3) `eda` exposes all modules: eda.dmt_* (projects/boards/docs), eda.sch_* (schematic), '
  + 'eda.pcb_* (PCB), eda.lib_* (libraries), eda.sys_* (system/UI/dialogs). '
  + '(4) Use enum MEMBERS (e.g. EPCB_LayerId.TOP), never raw numbers. '
  + '(5) Units differ: PCB = 1mil, Schematic = 0.01inch (10mil). '
  + '(6) Browser context — no Node APIs (fs/path). '
  + '(7) Errors thrown by eda.* are NOT Error instances and have no .message — String(e) gives '
  + '"[object Object]". Use JSON.stringify(e) in catch blocks. '
  + 'ALWAYS call eda_api_lookup to confirm a method\'s exact signature/enum before using it — never guess.';

// 库检索的实测事实(2026-08-02,选 CAN 共模扼流那轮)。写在这里是因为它是**否定结论**:
// 不写下来,下一个 agent 会照着 ILIB_DeviceSearchItem 的字段名去要库存,拿到 undefined 再重新试一遍。
const LIB_SEARCH_FACTS =
  'LIBRARY SEARCH — measured behaviour, not the doc\'s promise: '
  + 'eda.lib_Device.search(key,...) returns name / manufacturerId (MPN) / supplierId (LCSC C-number) / '
  + 'description (the electrical parameters live here), but jlcInventory, lcscInventory, jlcPrice and '
  + 'footprint come back UNDEFINED. eda.lib_Device.getByLcscIds([...]) adds manufacturer + footprintUuid + '
  + 'libraryUuid but still NO stock or price. eda.lib_Footprint.get(fpUuid, libraryUuid) gives the footprint '
  + 'NAME (libraryUuid is REQUIRED — omitting it throws) but only metadata, no pad geometry. '
  + '⇒ Stock/price cannot be read through the EDA API at all. Two tools here DO return them, but from '
  + 'TWO DIFFERENT POOLS: eda_smt_stock = the JLCPCB ASSEMBLY (贴装) library, which decides whether a part '
  + 'can be PLACED at all (stockSmt + 基础库/扩展库); eda_datasheet = the LCSC MALL, i.e. buying loose parts '
  + '(stockLcscMall + price ladder + datasheet PDF). In stock at the mall does NOT mean it can be assembled. '
  + '⇒ For a BOM that will be assembled the chain is eda_smt_stock (keyword → C-number + library + assembly '
  + 'stock) → eda_datasheet (that C-number → datasheet + mall price); eda_lib_search is the right entry only '
  + 'when you just need to place the symbol and do not care about assembly.';

// ⭐ 多窗口:每个工具都能显式指定打哪个 EasyEDA 窗口。
// ⚠ 这段描述会被复制进【每一个】工具的 schema,而 tools/list 是每个会话都要付的常驻成本
// (实测:原来 422B 的版本 ×13 份 = 5.5KB,占整个 tools/list 的 19%)。
// ⇒ 这里只留一句话,完整语义(活动窗口为什么会飘、什么时候必须显式给)放进
//   initialize 的 `instructions` —— 那个**整份只付一次**。
const WINDOW_ID_PROP = {
  type: 'string',
  description: 'Target EasyEDA window (windowId from eda_windows); omit = the active window. See server instructions.',
};

// MCP initialize 的 `instructions`:跨工具的公共规则放这里,**整份只付一次**,
// 而不是复制进 N 个工具的 schema。只放"每个工具都适用"的东西,单个工具的坑留在它自己的 description 里。
const SERVER_INSTRUCTIONS = `EasyEDA Pro bridge. Two cross-cutting rules:

1) MULTI-WINDOW. Every eda_* tool takes an optional windowId (from eda_windows). Passing it targets that
window directly and does NOT change the "active" window, so two EDA windows can be worked on concurrently.
⛔ The active window is NOT stable: it changes on an explicit eda_windows_select AND whenever the active
window's connection blips — the bridge then hands the active flag to the other window and never hands it
back. A run that silently switches boards halfway is a failure mode this has actually caused.
⇒ With two windows open, pass windowId explicitly on anything that must not land on the wrong board
(placing, deleting, wiring, DFM checks).
⛔ A page/document uuid does NOT select a window: openDocument(uuid) just returns undefined in a window whose
project does not hold it, and the caller then reads whatever was already open. Only eda_netlist and
eda_sch_netcheck take a "page" argument and RESOLVE the window from that uuid (hard error if it is not found
or not active); for every other tool the uuid is scoped to the window you targeted.

2) SCOPE BANNER. Every reply is prefixed with "[EDA] proj=… | board=… | doc=…" describing where the call
actually landed. A project can hold several boards, designators are numbered PER BOARD (two boards both
have U1/R1/C1), and page names repeat across boards — so a result read off the wrong board looks exactly
like a correct one. Check the banner before believing a result.`;

const TOOLS = [
  {
    name: 'eda_api_lookup',
    description:
      'Look up the EasyEDA Pro API scheme (class/method signatures, enums, interfaces) so you know '
      + 'exactly how to call eda.* BEFORE writing code for eda_execute. The API has 123 classes / 62 '
      + 'enums — use this whenever unsure of a method name, parameter order/types, return type, or enum '
      + 'value. Never guess a signature.\n'
      + 'THREE GRANULARITIES — start narrow, a full class doc can be 10k+ tokens:\n'
      + '  • {query:"SCH_PrimitiveComponent"} → that class\'s method list (names + parameter names). '
      + 'This is the default and usually all you need to pick a method.\n'
      + '  • {query:"SCH_PrimitiveComponent", member:"create"} → ONE member\'s full signature with '
      + 'parameter TYPES, return type and remarks (all overloads). Use this before writing the call.\n'
      + '  • {query:"...", full:true} → the whole class doc. Only when you need several members at once.\n'
      + 'A keyword instead of an exact name (e.g. "createBoard", "schematic wire", "layer") searches all '
      + 'signatures. Enums/interfaces have no method table, so they always come back whole (they are short).',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Exact class/enum/interface name, or a keyword to search signatures.' },
        member: { type: 'string', description: 'Method/property name on that class — returns its full signature '
          + '(types + remarks + every overload) instead of the summary list. Requires query to be an exact name.' },
        full: { type: 'boolean', description: 'Return the entire class doc instead of the method summary. Expensive; '
          + 'prefer member for a single call site.' },
      },
      required: ['query'],
    },
    handler: async (args) => apiLookup(args.query, args.member, args.full),
  },
  {
    name: 'eda_execute',
    description:
      'Execute JavaScript inside the running EasyEDA Pro client and return the result. ' + CALLING_SCHEME
      + ' Requires the bridge + EasyEDA extension connected (call eda_health if it fails). '
      + 'Example: {"code":"return await eda.dmt_Project.getCurrentProjectInfo();"}\n' + LIB_SEARCH_FACTS,
    inputSchema: {
      type: 'object',
      properties: {
        code: { type: 'string', description: 'JS to run as the body of async function(eda){...}. Must `return` a value.' },
        windowId: WINDOW_ID_PROP,
        timeoutMs: { type: 'number', description: 'Optional execution timeout override in ms (default 25000, max 600000). '
          + 'Raise it for bulk dump/apply scripts that loop over every component.' },
      },
      required: ['code'],
    },
    handler: async (args) => {
      const bridge = await ensureBridge();
      if (!bridge) {
        return { isError: true, text: 'No EDA bridge: this server hosts one in-process, and starting it failed '
          + '(all ports 49620-49629 busy?). See stderr for [eda-mcp] lines.' };
      }
      // 超时链(外松内紧)在 bridge-client.execute 里统一算,这里不再各算一份
      const resp = await bridgeExecute(bridge.port, args.code, {
        windowId: args.windowId, timeoutMs: args.timeoutMs,
      });
      if (resp && resp.success) return { text: JSON.stringify(resp.result, null, 2) };
      const detail = resp && resp.stack ? `\n--- in-EDA stack ---\n${resp.stack}` : '';
      return { isError: true, text: `EDA execute failed: ${resp ? resp.error : 'no response'}${detail}` };
    },
  },
  {
    name: 'eda_health',
    description: 'Check the EDA bridge + EasyEDA client status (bridge port, whether an EDA window is connected, '
      + 'active window/label). Call this first when eda_execute reports a connection error.',
    inputSchema: { type: 'object', properties: {} },
    handler: async () => {
      const bridge = await ensureBridge();
      if (!bridge) return { isError: true, text: 'No bridge running (autostart failed or disabled).' };
      const health = await httpGetJson(bridge.port, '/health');
      return { text: JSON.stringify({ bridgePort: bridge.port, ...health }, null, 2) };
    },
  },
  {
    name: 'eda_windows',
    description: 'List all connected EasyEDA windows (windowId, project label, active flag). Use to disambiguate '
      + 'when multiple EDA windows are open, then either pass that windowId to any eda_* tool (targets it directly, '
      + 'leaves the active window alone — this is the way to work on two windows at once) or eda_windows_select it '
      + 'as the new default. ⚠ label is captured at registration and does NOT follow the user switching projects '
      + 'inside that window; the [EDA] banner on every reply is the live truth.',
    inputSchema: { type: 'object', properties: {} },
    handler: async () => {
      const bridge = await ensureBridge();
      if (!bridge) return { isError: true, text: 'No bridge running.' };
      const res = await httpGetJson(bridge.port, '/eda-windows');
      return { text: JSON.stringify(res, null, 2) };
    },
  },
  {
    name: 'eda_windows_select',
    description: 'Set the DEFAULT EasyEDA window that eda_* tools target when they are called without windowId. '
      + 'Params: windowId (from eda_windows). ⚠ This default is not sticky: if that window\'s connection blips, the '
      + 'bridge hands the active flag to the other window and never hands it back. For anything that must not land '
      + 'on the wrong board, pass windowId per call instead of relying on this.',
    inputSchema: {
      type: 'object',
      properties: { windowId: { type: 'string', description: 'windowId from eda_windows.' } },
      required: ['windowId'],
    },
    handler: async (args) => {
      const bridge = await ensureBridge();
      if (!bridge) return { isError: true, text: 'No bridge running.' };
      const res = await httpPostJson(bridge.port, '/eda-windows/select', { windowId: args.windowId }, 5000);
      return { text: JSON.stringify(res, null, 2) };
    },
  },

  // ─── Hardened (固化) common operations — no hand-written JS needed ──
  {
    name: 'eda_context',
    description: 'Orient yourself, and the ONE place to see what documents exist. Returns: the current EasyEDA project, '
      + 'the CURRENT BOARD (a project can hold several — e.g. a base board plus expansion cards), the ACTIVE document, '
      + 'and every board with its PCB (name+uuid) and its schematic PAGES (name+uuid+active). Call it before opening '
      + 'anything with eda_open_document. Page names repeat across boards, so a per-board listing is the only one that '
      + 'can be acted on safely — that is why there is no separate flat page-list tool.',
    inputSchema: { type: 'object', properties: { windowId: WINDOW_ID_PROP } },
    handler: async (args) => {
      const code = "const proj=await eda.dmt_Project.getCurrentProjectInfo();"
        + "const doc=await eda.dmt_SelectControl.getCurrentDocumentInfo();"
        + "let activePage='';if(doc&&doc.documentType===1){try{const pages=await eda.dmt_Schematic.getAllSchematicPagesInfo();const pg=(pages||[]).find(p=>p.uuid===doc.uuid);activePage=pg?(pg.name||pg.friendlyName||''):'';}catch(e){}}"
        + "let currentBoard=null,boards=[];"
        + "try{const b=await eda.dmt_Board.getCurrentBoardInfo();if(b)currentBoard={name:b.name,uuid:b.uuid,pcb:b.pcb?b.pcb.name:null,schematic:b.schematic?b.schematic.name:null};}catch(e){}"
        // 页给到 uuid + active(而不是只有名字)—— 这样本工具就完全覆盖了原 eda_pages,
        // 且多一层板归属:页名在各板之间会重名,只有名字的扁平表反而会误导。
        + "try{boards=(await eda.dmt_Board.getAllBoardsInfo()||[]).map(b=>({name:b.name,uuid:b.uuid,"
        + "pcb:b.pcb?{name:b.pcb.name,uuid:b.pcb.uuid}:null,"
        + "pages:(b.schematic&&b.schematic.page?b.schematic.page.map(p=>({name:p.name,uuid:p.uuid,active:!!(doc&&p.uuid===doc.uuid)})):[])}));}catch(e){}"
        + "return{project:proj?{name:proj.friendlyName,uuid:proj.uuid}:null,currentBoard,boardCount:boards.length,boards,documentType:doc?doc.documentType:null,tabId:doc?doc.tabId:null,activePage};";
      const r = await runOnEda(code, args.windowId);
      if (r) {
        r.documentTypeName = DOC_TYPE[String(r.documentType)] || ('type#' + r.documentType);
        if (r.boardCount > 1) {
          r._warning = `This project holds ${r.boardCount} boards; every eda_* call acts on the CURRENT one `
            + `("${r.currentBoard ? r.currentBoard.name : '?'}") only. Confirm the board before placing, `
            + 'exporting or wiring — designators are numbered PER BOARD, so both boards have U1/R1/C1.';
        }
      }
      return { text: JSON.stringify(r, null, 2) };
    },
  },
  {
    name: 'eda_list_components',
    description: 'List components on the ACTIVE document (schematic page or PCB): designator, device (library part), value '
      + '(24kΩ/1µF…), lcsc (立创/LCSC C-number), mfrId (MPN), x, y, rotation, type — ideal for BOM / as-built write-back. '
      + 'On a schematic each row also has net; on a PCB each row instead has layer (top/bottom) — a PCB part has no single '
      + 'net so that field is omitted there. Parts only by default; includeFlags=true also lists net flags/ports. Filter '
      + 'with designators[]. Coords are rounded (schematic unit = 0.01inch, PCB = 1mil).',
    inputSchema: {
      type: 'object',
      properties: {
        designators: { type: 'array', items: { type: 'string' }, description: 'Optional filter, e.g. ["U10","J2"].' },
        includeFlags: { type: 'boolean', description: 'Include netflag/netport pseudo-components (default false).' },
        windowId: WINDOW_ID_PROP,
      },
    },
    handler: async (args) => {
      const want = Array.isArray(args.designators) && args.designators.length ? JSON.stringify(args.designators) : 'null';
      const inc = args.includeFlags ? 'true' : 'false';
      const code = "const INC=" + inc + ";const WANT=" + want + ";const LYR={1:'top',2:'bottom'};const doc=await eda.dmt_SelectControl.getCurrentDocumentInfo();const isPcb=doc&&doc.documentType===3;const M=isPcb?eda.pcb_PrimitiveComponent:eda.sch_PrimitiveComponent;const ids=await M.getAllPrimitiveId();const rows=[];for(const id of ids){const c=await M.get(id);if(!c)continue;const ct=c.componentType;if(!INC&&ct&&ct!=='part')continue;const d=c.designator||'';if(WANT&&WANT.indexOf(d)<0)continue;const op=c.otherProperty||{};const row={designator:d,device:(c.component&&c.component.name)||'',value:op.Value||op.value||'',lcsc:c.supplierId||'',mfrId:c.manufacturerId||'',x:Math.round(c.x),y:Math.round(c.y),rotation:c.rotation,type:ct||'part'};if(isPcb){row.layer=LYR[c.layer]||c.layer;}else{row.net=c.net||'';}rows.push(row);}rows.sort((a,b)=>String(a.designator).localeCompare(String(b.designator),undefined,{numeric:true}));return{documentType:doc&&doc.documentType,count:rows.length,components:rows};";
      const r = await runOnEda(code, args.windowId);
      return { text: JSON.stringify(r, null, 2) };
    },
  },
  {
    name: 'eda_component_pins',
    description: 'Get the pins of schematic components by designator: pinNumber, pinName, absolute x/y (the exact wire '
      + 'endpoints), and noConnect flag. Use before wiring, or to inspect a part. Active document must be a schematic page.',
    inputSchema: {
      type: 'object',
      properties: {
        designators: { type: 'array', items: { type: 'string' }, description: 'e.g. ["U10","U6"].' },
        windowId: WINDOW_ID_PROP,
      },
      required: ['designators'],
    },
    handler: async (args) => {
      const want = JSON.stringify(Array.isArray(args.designators) ? args.designators : []);
      const code = "const WANT=new Set(" + want + ");const M=eda.sch_PrimitiveComponent;const ids=await M.getAllPrimitiveId();const out={};for(const id of ids){const c=await M.get(id);if(!c||!WANT.has(c.designator))continue;const pins=await M.getAllPinsByPrimitiveId(id);out[c.designator]=(pins||[]).map(p=>({pinNumber:p.pinNumber,pinName:p.pinName,x:Math.round(p.x),y:Math.round(p.y),noConnect:!!p.noConnected}));}return out;";
      const r = await runOnEda(code, args.windowId);
      return { text: JSON.stringify(r, null, 2) };
    },
  },
  {
    name: 'eda_place_components',
    description:
      'Place components on the ACTIVE schematic page from a list — the counterpart of eda_list_components. '
      + 'Folds the three hand-written steps (lib_Device.getByLcscIds → sch_PrimitiveComponent.create → '
      + 'modify to set the designator/value) into one call, and refuses duplicate designators before placing '
      + 'anything. Identify each part by lcsc (C-number, preferred) or by deviceUuid+libraryUuid.\n'
      + '⚠ COORDINATES ARE SCHEMATIC UNITS = 0.01 inch (10 mil), same as eda_list_components returns — NOT mil, '
      + 'NOT mm. Snap to the 10-unit (0.1 inch) grid so pins land on wire endpoints.\n'
      + '⚠ Placement lands on whatever board+page is active (a project can hold several boards) — the [EDA] '
      + 'banner on every reply tells you which; switch with eda_open_document({page,board}) first.\n'
      + 'Designators: pass one per item. Prefix by PHYSICAL CLASS, not by whatever the library defaults to '
      + '(J=connector incl. card-edge/header/terminal, U=IC, H=mounting hole only). Omit to let EasyEDA '
      + 'auto-number. Use dryRun:true to resolve the parts and check for collisions without touching the canvas.\n'
      + '🔴 NEVER ASSUME PIN GEOMETRY — read it back with eda_component_pins after placing. Three behaviours '
      + 'verified 2026-08-03:\n'
      + '  (1) Symbol pin PITCH is per-DEVICE, not per-package: among 0402 caps, C1546(100pF) is 30 units and '
      + 'C1525(100nF) is 40; among 0603 caps, C1653(22pF) is 40 and C318667(240pF) is 30. So a same-package '
      + 'part swap can silently pull pins off already-drawn wires.\n'
      + '  (2) Which end is pin 1 is also per-device: C25102(300R) and C25120(49.9R) land pin 1 on opposite '
      + 'sides at the same rotation.\n'
      + '  (3) 🔴 rotation passed to create() and rotation set later via modify() do NOT give the same '
      + 'orientation — creating at 270 put pin 1 at the bottom, modify({rotation:270}) on that same part put '
      + 'pin 1 at the top. Treat the create-time angle as unreliable: place, then modify the rotation, then '
      + 'read the pins back.',
    inputSchema: {
      type: 'object',
      properties: {
        components: {
          type: 'array',
          description: 'Parts to place, in order.',
          items: {
            type: 'object',
            properties: {
              lcsc: { type: 'string', description: 'LCSC C-number, e.g. "C76584". Preferred identifier.' },
              deviceUuid: { type: 'string', description: 'Library device uuid (use with libraryUuid) when there is no C-number.' },
              libraryUuid: { type: 'string', description: 'Library uuid that holds deviceUuid.' },
              designator: { type: 'string', description: 'e.g. "L1". Omit to let EasyEDA auto-number.' },
              value: { type: 'string', description: 'Value property, e.g. "51uH" / "0Ω" / "4.7nF".' },
              x: { type: 'number', description: 'X in 0.01 inch units.' },
              y: { type: 'number', description: 'Y in 0.01 inch units.' },
              rotation: { type: 'number', description: 'Degrees, default 0.' },
              mirror: { type: 'boolean', description: 'Mirror the symbol, default false.' },
              addIntoPcb: { type: 'boolean', description: 'Push to PCB, default true. Set false for schematic-only parts.' },
            },
            required: ['x', 'y'],
          },
        },
        dryRun: { type: 'boolean', description: 'Resolve parts + check designator collisions, place nothing.' },
        expectBoard: { type: 'string', description: 'STRONGLY RECOMMENDED on any multi-board project: the board name you '
          + 'intend to place on (from eda_context, e.g. "ExpansionCard"). Refuses and places nothing if the active board differs. '
          + 'The active tab can be changed by the USER in EasyEDA between your calls — documentType alone does not catch '
          + '"right kind of document, wrong board", which is the expensive mistake.' },
        windowId: WINDOW_ID_PROP,
      },
      required: ['components'],
    },
    handler: async (args) => {
      const items = Array.isArray(args.components) ? args.components : [];
      if (!items.length) return { isError: true, text: 'components[] is empty.' };
      const code = "const ITEMS=" + JSON.stringify(items) + ";const DRY=" + (args.dryRun ? 'true' : 'false') + ";"
        + "const E=e=>{try{return JSON.stringify(e);}catch(_){return String(e);}};"
        + "const doc=await eda.dmt_SelectControl.getCurrentDocumentInfo();"
        + "if(!doc||doc.documentType!==1)return{ok:false,error:'active document is not a schematic page (documentType='+(doc?doc.documentType:'none')+'). Open the target page with eda_open_document first.'};"
        // ⭐ 板名闸门:一个工程可以有多块板,活动标签页会被**用户在 EDA 里点来点去**地改掉
        // (2026-08-02 实测:两次连续调用分别落到了 BoardA/PCB1 和 BoardA/P4)。
        // documentType 只挡住了"不是原理图",挡不住"是另一块板的原理图" —— 那才是最贵的错。
        + "const EXPECT=" + JSON.stringify(String(args.expectBoard || '')) + ";"
        + "if(EXPECT){const bi=await eda.dmt_Board.getCurrentBoardInfo();const cur=(bi&&bi.name)||'';"
        + "if(cur!==EXPECT)return{ok:false,error:'BOARD MISMATCH — expected \"'+EXPECT+'\" but the active board is \"'+cur+'\". Nothing was placed. Switch with eda_open_document({page,board}) — pass board, because page names repeat across boards.'};}"
        // 位号唯一性:先全查再决定,避免"摆了一半才发现撞号"
        + "const want=ITEMS.filter(i=>i.designator).map(i=>i.designator);"
        + "if(want.length){const seen={};const dupIn=[];for(const d of want){if(seen[d])dupIn.push(d);seen[d]=1;}"
        + "if(dupIn.length)return{ok:false,error:'duplicate designators within this request: '+dupIn.join(', ')};"
        // ⚠ 不要传 allSchematicPages=true:实测(2026-08-02)它**并不会**跨页返回(只给活动页),
        // 却明显更慢 —— 花了钱没买到东西。⇒ 位号唯一性检查的作用域 = **活动页**,别的页要靠人。
        + "const exist=new Set();for(const id of (await eda.sch_PrimitiveComponent.getAllPrimitiveId())){const c=await eda.sch_PrimitiveComponent.get(id);if(c&&c.designator)exist.add(c.designator);}"
        + "const clash=want.filter(d=>exist.has(d));"
        + "if(clash.length)return{ok:false,error:'designator already used on this board: '+clash.join(', ')+' (designators are per-board; check you are on the right board)'};}"
        + "const ids=[...new Set(ITEMS.filter(i=>i.lcsc).map(i=>i.lcsc))];const byLcsc={};"
        + "if(ids.length){let devs=[];try{devs=await eda.lib_Device.getByLcscIds(ids)||[];}catch(e){return{ok:false,error:'getByLcscIds failed: '+E(e)};}"
        + "for(const d of devs)byLcsc[d.supplierId]=d;}"
        + "const out=[];"
        + "for(const it of ITEMS){const r={designator:it.designator||null,lcsc:it.lcsc||null,x:it.x,y:it.y};let dev=null;"
        + "if(it.lcsc){dev=byLcsc[it.lcsc];if(!dev){r.ok=false;r.error='LCSC not found in the library';out.push(r);continue;}}"
        // ⚠⚠ create() 拿到无效器件引用会**静默挂死**(不抛错、不返回),实测单次 >115s 被 bridge 掐掉。
        // 最容易踩的:把画布实例 c.component 里的 16 位内部引用当成库器件 uuid —— 库器件 uuid 是 32 位。
        // 所以这里先 lib_Device.get() 验一次,解析不到就立刻报错,别让调用方去等超时。
        + "else if(it.deviceUuid&&it.libraryUuid){let d=null;try{d=await eda.lib_Device.get(it.deviceUuid,it.libraryUuid);}catch(e){}"
        + "if(!d){r.ok=false;r.error='deviceUuid does not resolve to a library device (library uuids are 32 hex chars; a 16-char id from a placed instance\\'s .component is NOT one). create() would hang silently on this.';out.push(r);continue;}dev=d;}"
        + "else{r.ok=false;r.error='need lcsc, or deviceUuid+libraryUuid';out.push(r);continue;}"
        + "r.mfrId=dev.manufacturerId||null;"
        + "if(DRY){r.ok=true;r.dryRun=true;out.push(r);continue;}"
        + "let prim=null;try{prim=await eda.sch_PrimitiveComponent.create(dev,it.x,it.y,undefined,it.rotation||0,!!it.mirror,true,it.addIntoPcb===false?false:true);}"
        + "catch(e){r.ok=false;r.error='create failed: '+E(e);out.push(r);continue;}"
        + "if(!prim){r.ok=false;r.error='create returned undefined';out.push(r);continue;}"
        + "r.primitiveId=prim.primitiveId||prim.id||null;"
        // ⚠ create() 不把库器件的 supplierId 带过去 —— 实测放完 supplierId 变成 "<器件名>.1",
        // 而 BOM 通常是从 EDA 实读回写的 ⇒ 不补这一步就会往 BOM 里灌错料号。
        + "const mod={};if(it.designator)mod.designator=it.designator;if(it.value!=null&&it.value!=='')mod.otherProperty={Value:String(it.value)};"
        + "if(dev.supplierId){mod.supplierId=dev.supplierId;mod.supplier=dev.supplier||'LCSC';}"
        + "if(dev.manufacturerId){mod.manufacturerId=dev.manufacturerId;if(dev.manufacturer)mod.manufacturer=dev.manufacturer;}"
        + "if(Object.keys(mod).length){try{const m2=await eda.sch_PrimitiveComponent.modify(prim,mod);if(!m2)r.modifyWarning='modify returned falsy';}catch(e){r.modifyError=E(e);}}"
        + "r.ok=true;out.push(r);}"
        + "return{ok:out.every(r=>r.ok),dryRun:DRY,placed:out.filter(r=>r.ok&&!r.dryRun).length,total:ITEMS.length,results:out};";
      const r = await runOnEda(code, args.windowId, 120_000);
      return { text: JSON.stringify(r, null, 2), isError: !!(r && r.ok === false) };
    },
  },
  {
    name: 'eda_lib_search',
    description:
      'Search the EasyEDA component library and return one flat row per part: name, mpn (manufacturerId), '
      + 'lcsc (C-number), manufacturer, and params (the description string — this is where the electrical '
      + 'parameters live: inductance / impedance / DCR / voltage …). Use this for part selection instead of '
      + 'hand-writing eda.lib_Device.search in eda_execute.\n'
      + 'Pass query for a keyword search (Chinese names dominate the library: try 共模电感 / 共模扼流 as well as '
      + 'the MPN family, e.g. ACT45B, DLW), or lcsc[] to look up known C-numbers directly. '
      + 'withFootprint:true resolves each part\'s footprint NAME (one extra round trip per distinct footprint).\n'
      + '⚠ ' + LIB_SEARCH_FACTS,
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Keyword, e.g. "共模电感" or "ACT45B". Omit when using lcsc[].' },
        lcsc: { type: 'array', items: { type: 'string' }, description: 'Look up these C-numbers directly, e.g. ["C76584","C88056"].' },
        limit: { type: 'number', description: 'Max rows for a keyword search (default 40).' },
        withFootprint: { type: 'boolean', description: 'Also resolve the footprint name for each row (costs one call per distinct footprint).' },
        windowId: WINDOW_ID_PROP,
      },
    },
    handler: async (args) => {
      const q = String(args.query || '').trim();
      const ids = Array.isArray(args.lcsc) ? args.lcsc.filter(Boolean) : [];
      if (!q && !ids.length) return { isError: true, text: 'Provide query (keyword) or lcsc[] (C-numbers).' };
      const code = "const Q=" + JSON.stringify(q) + ";const IDS=" + JSON.stringify(ids) + ";"
        + "const LIM=" + (Math.max(1, Math.round(args.limit || 40))) + ";const FP=" + (args.withFootprint ? 'true' : 'false') + ";"
        + "const E=e=>{try{return JSON.stringify(e);}catch(_){return String(e);}};let devs=[];"
        + "try{if(IDS.length){devs=await eda.lib_Device.getByLcscIds(IDS)||[];}else{devs=await eda.lib_Device.search(Q,undefined,undefined,undefined,LIM,1)||[];}}"
        + "catch(e){return{ok:false,error:'library search failed: '+E(e)};}"
        // ⭐ jlcClass 只在 otherProperty 里,search() 不给 —— 关键字检索时补一次 getByLcscIds 取回。
        // 「优先基础库」是本项目的常驻偏好(扩展库件按料号收一次性上机费),不给这个字段等于每次都要人再查一遍。
        + "if(!IDS.length&&devs.length){try{const full=await eda.lib_Device.getByLcscIds(devs.map(d=>d.supplierId).filter(Boolean));"
        + "const byId={};for(const f of (full||[]))byId[f.supplierId]=f;"
        + "devs=devs.map(d=>byId[d.supplierId]?Object.assign({},d,{otherProperty:byId[d.supplierId].otherProperty,manufacturer:byId[d.supplierId].manufacturer,footprintUuid:byId[d.supplierId].footprintUuid,libraryUuid:byId[d.supplierId].libraryUuid,footprint:byId[d.supplierId].footprint}):d);}catch(e){}}"
        + "const fpCache={};const rows=[];"
        + "for(const d of devs){const op=d.otherProperty||{};"
        + "const r={name:d.name||'',mpn:d.manufacturerId||'',lcsc:d.supplierId||'',manufacturer:d.manufacturer||'',"
        + "jlcClass:op['JLCPCB Part Class']||'',params:d.description||''};"
        + "if(FP&&d.footprintUuid){const lib=(d.footprint&&d.footprint.libraryUuid)||d.libraryUuid;const k=d.footprintUuid+'|'+lib;"
        + "if(!(k in fpCache)){try{const f=await eda.lib_Footprint.get(d.footprintUuid,lib);fpCache[k]=f?(f.name||''):'';}catch(e){fpCache[k]='?';}}"
        + "r.footprint=fpCache[k];}rows.push(r);}"
        // 库存/价格这里恒为 undefined(见工具描述),不列成字段免得读的人以为是"这次没查到"。
        // note 里必须指路,否则读的人会自己去 lcsc.com 查商城库存 —— 那是另一个池子,贴装的答案在 eda_smt_stock。
        + "return{ok:true,mode:IDS.length?'lcsc':'keyword',count:rows.length,note:'stock/price are not in the EDA API. Assembly (贴装) stock + 基础库/扩展库: eda_smt_stock. LCSC mall price + datasheet: eda_datasheet. They are different pools.',results:rows};";
      const r = await runOnEda(code, args.windowId, 90_000);
      return { text: JSON.stringify(r, null, 2), isError: !!(r && r.ok === false) };
    },
  },
  {
    name: 'eda_datasheet',
    description:
      'Look a part up on LCSC by C-number and (optionally) DOWNLOAD its datasheet PDF into manuals/.\n'
      + 'Returns what the EasyEDA API cannot give: the datasheet URL, the price ladder, the manufacturer part '
      + 'number/brand, package, and the parametric table.\n'
      + '⚠ STOCK IS THE **LCSC MALL POOL** (field stockLcscMall) — NOT the JLCPCB assembly (贴装) library. '
      + 'They are different pools: in stock at the mall does NOT mean you can order it placed. Whether a part '
      + 'can be assembled, and how many JLC has, is exactly what **eda_smt_stock** answers (stockSmt + '
      + '基础库/扩展库). For anything that will be assembled, that tool is the authority, not this one.\n'
      + '⚠ This tool has NO keyword search — LCSC\'s search endpoint is behind a WAF (403). So reach a '
      + 'C-number with eda_smt_stock (it takes keywords too, and is the right entry for an assembled BOM) or '
      + 'eda_lib_search, then come here for the datasheet + mall price.\n'
      + 'download:true saves to manuals/<MPN>.pdf. It refuses to overwrite an existing file unless overwrite:true, '
      + 'and it verifies the %PDF magic so an HTML error page never lands as a .pdf.\n'
      + 'After downloading, the manuals/ pipeline still needs its two manual steps: add a METADATA row in '
      + 'manuals/process_datasheets.py, then run it to extract text/ and regenerate INDEX.md.',
    inputSchema: {
      type: 'object',
      properties: {
        lcsc: { type: 'array', items: { type: 'string' }, description: 'C-numbers, e.g. ["C496552","C720477"]. Required.' },
        download: { type: 'boolean', description: 'Also fetch the PDF (default false = metadata only).' },
        dir: { type: 'string', description: 'Target directory (default: the repo\'s manuals/).' },
        name: { type: 'string', description: 'File name override (single part only); ".pdf" is appended if missing.' },
        overwrite: { type: 'boolean', description: 'Allow replacing an existing file (default false).' },
      },
      required: ['lcsc'],
    },
    handler: async (args) => {
      const ids = (Array.isArray(args.lcsc) ? args.lcsc : [args.lcsc])
        .filter(Boolean).map((s) => String(s).trim().replace(/^c/i, 'C'))
        .map((s) => (/^C\d+$/.test(s) ? s : (/^\d+$/.test(s) ? 'C' + s : s)));
      if (!ids.length) return { isError: true, text: 'Provide lcsc[] — one or more C-numbers.' };
      const bad = ids.filter((s) => !/^C\d+$/.test(s));
      if (bad.length) return { isError: true, text: `Not C-numbers: ${bad.join(', ')}. This tool takes LCSC codes only; use eda_lib_search for keywords.` };

      let outDir = args.dir ? String(args.dir) : resolveManualsDir();
      if (args.download && !outDir) return { isError: true, text: 'manuals/ not found next to this server — pass dir explicitly.' };
      if (args.download && !existsSync(outDir)) return { isError: true, text: `Directory does not exist: ${outDir}` };
      if (args.name && ids.length > 1) return { isError: true, text: 'name is only allowed with a single lcsc entry.' };

      const rows = [];
      for (const id of ids) {
        try {
          rows.push(await lcscPart(id, {
            download: !!args.download, dir: outDir,
            name: args.name ? String(args.name) : null, overwrite: !!args.overwrite,
          }));
        } catch (e) {
          // undici 的 'fetch failed' 本身不说明任何事,真正的原因在 cause 里(DNS / TLS / 代理)
          const cause = e && e.cause && e.cause.message ? ` (${e.cause.message})` : '';
          rows.push({ lcsc: id, error: (e && e.message ? e.message : String(e)) + cause });
        }
      }
      const saved = rows.filter((r) => r.saved && !r.saved.skipped);
      const note = saved.length
        ? 'Downloaded. manuals/ pipeline is not finished yet: add a METADATA row in manuals/process_datasheets.py '
          + '(MPN / LCSC / designator / what it is / which doc section), then run '
          + '`python3 manuals/process_datasheets.py` to extract text/ and regenerate INDEX.md.'
        : undefined;
      return {
        text: JSON.stringify({ ok: !rows.some((r) => r.error), count: rows.length, note, results: rows }, null, 2),
        isError: rows.every((r) => r.error),
      };
    },
  },
  {
    name: 'eda_smt_stock',
    description:
      'Query the JLCPCB **ASSEMBLY (贴装) parts library** — the pool that decides whether a part can actually be '
      + 'PLACED on your board, and what it costs to place it. THIS IS NOT THE SAME POOL AS eda_datasheet: that one '
      + 'reports LCSC mall stock (buying loose parts). In stock at the mall does NOT mean JLC can assemble it. '
      + 'For any BOM that will be assembled, this tool is the authority.\n'
      + 'Per row: lcsc (C-number) · library ("base" = 基础库, no per-part setup fee / "expand" = 扩展库, one-off '
      + 'setup fee per part number) · stockSmt (assembly-library stock) · mpn · brand · package · price ladder · '
      + 'datasheet URL.\n'
      + '⭐ It takes a KEYWORD (English or Chinese: "CC1101", "共模电感") as well as a C-number — so unlike '
      + 'eda_datasheet it CAN search by text. Chain for a part that must be assembled: eda_smt_stock (keyword → '
      + 'C-number + library + assembly stock) → eda_datasheet (that C-number → datasheet PDF + mall price).\n'
      + 'library:"base" filters to the basic library — worth doing first, since 基础库 parts avoid the per-part '
      + 'setup fee, so prefer them when a basic-library part will do.\n'
      + 'Goes straight to JLCPCB (no EDA, no bridge, no auth needed).',
    inputSchema: {
      type: 'object',
      properties: {
        keyword: { type: 'string', description: 'C-number ("C25804") or free text ("CC1101", "共模电感", "0603 10k 1%").' },
        library: { type: 'string', description: '"" (default, both) | "base" (基础库) | "expand" (扩展库).' },
        limit: { type: 'number', description: 'Rows to return, 1-50 (default 10).' },
        page: { type: 'number', description: 'Page number, 1-based (default 1).' },
      },
      required: ['keyword'],
    },
    handler: async (args) => {
      const keyword = String(args.keyword || '').trim();
      if (!keyword) return { isError: true, text: 'keyword is required (C-number or free text).' };
      const library = ['base', 'expand'].includes(String(args.library)) ? String(args.library) : '';
      try {
        const r = await jlcSmtSearch({ keyword, page: args.page || 1, pageSize: args.limit || 10, library });
        const zero = r.rows.filter((x) => !x.stockSmt).length;
        return {
          text: JSON.stringify({
            ok: true, keyword, library: library || '(both)', total: r.total, count: r.rows.length,
            note: 'stockSmt = JLC ASSEMBLY library stock (not LCSC mall). library=base 无上机费 / expand 每个料号一次性上机费。'
              + (zero ? ` ⚠ ${zero}/${r.rows.length} 条贴装库存为 0 —— 这些料买得到也贴不了。` : ''),
            results: r.rows,
          }, null, 2),
        };
      } catch (e) {
        // undici 的 'fetch failed' 本身不说明任何事,真因在 cause 里
        const cause = e && e.cause && e.cause.message ? ` (${e.cause.message})` : '';
        return { isError: true, text: `JLC SMT query failed: ${(e && e.message) || String(e)}${cause}` };
      }
    },
  },
  {
    name: 'eda_delete',
    description:
      'Delete things from the ACTIVE schematic page: components by designator, and/or any primitive (wire, …) '
      + 'by primitiveId. The undo companion to eda_place_components / eda_wire — the EasyEDA API has NO undo, '
      + 'so a misplaced part or a wrong wire can only be removed this way.\n'
      + 'Reports every target as deleted / not-found (a designator that does not exist is reported, never silently '
      + 'treated as success). Use dryRun:true to see exactly what would go before it goes.',
    inputSchema: {
      type: 'object',
      properties: {
        designators: { type: 'array', items: { type: 'string' }, description: 'Components to delete, e.g. ["R98","L3"].' },
        primitiveIds: { type: 'array', items: { type: 'string' }, description: 'Raw primitive ids (wires from eda_wire, etc.).' },
        dryRun: { type: 'boolean', description: 'Resolve targets and report, delete nothing.' },
        windowId: WINDOW_ID_PROP,
      },
    },
    handler: async (args) => {
      const des = Array.isArray(args.designators) ? args.designators.filter(Boolean) : [];
      const pids = Array.isArray(args.primitiveIds) ? args.primitiveIds.filter(Boolean) : [];
      if (!des.length && !pids.length) return { isError: true, text: 'Provide designators[] and/or primitiveIds[].' };
      const code = "const DES=" + JSON.stringify(des) + ";const PIDS=" + JSON.stringify(pids) + ";const DRY=" + (args.dryRun ? 'true' : 'false') + ";"
        + "const E=e=>{try{return JSON.stringify(e);}catch(_){return String(e);}};const M=eda.sch_PrimitiveComponent;const out=[];"
        + "if(DES.length){const want=new Set(DES);const found={};"
        + "for(const id of await M.getAllPrimitiveId()){const c=await M.get(id);if(c&&want.has(c.designator))found[c.designator]=id;}"
        + "for(const d of DES){const id=found[d];if(!id){out.push({target:d,kind:'component',status:'not-found'});continue;}"
        + "if(DRY){out.push({target:d,kind:'component',primitiveId:id,status:'would-delete'});continue;}"
        + "try{const ok=await M.delete(id);out.push({target:d,kind:'component',primitiveId:id,status:ok?'deleted':'delete-returned-false'});}"
        + "catch(e){out.push({target:d,kind:'component',primitiveId:id,status:'error',error:E(e)});}}}"
        + "for(const p of PIDS){if(DRY){out.push({target:p,kind:'primitive',status:'would-delete'});continue;}"
        + "let ok=false,err=null;"
        + "try{ok=await eda.sch_PrimitiveWire.delete(p);}catch(e){err=E(e);}"
        + "if(!ok){try{ok=await M.delete(p);}catch(e){err=err||E(e);}}"
        + "out.push({target:p,kind:'primitive',status:ok?'deleted':'not-found-or-error',error:ok?undefined:err});}"
        + "const bad=out.filter(r=>r.status!=='deleted'&&r.status!=='would-delete');"
        + "return{ok:bad.length===0,dryRun:DRY,deleted:out.filter(r=>r.status==='deleted').length,total:out.length,results:out};";
      const r = await runOnEda(code, args.windowId, 120_000);
      return { text: JSON.stringify(r, null, 2), isError: !!(r && r.ok === false) };
    },
  },
  {
    name: 'eda_wire',
    description:
      '⚠ DIVISION OF LABOUR: in this project net-to-net wiring belongs to the USER, component placement to the '
      + 'agent. This tool is the documented exception and REQUIRES AN EXPLICIT PER-REQUEST '
      + 'INSTRUCTION: only call it when the user has just told you to draw these specific connections. Never '
      + 'call it on your own initiative — not to "finish" a placement, not to fix a netcheck failure, not '
      + 'because a datasheet implies a connection. If you believe wiring is needed, say so and wait.\n'
      + 'The `instruction` field is required and must quote the user\'s actual words asking for this wiring; it '
      + 'exists so the call cannot be made casually.\n'
      + 'Draws wires on the ACTIVE schematic page. Two forms per item: {from:"U1.5", to:"U2.3"} connects two pins '
      + '(resolved to their exact endpoints), or {points:[[x,y],[x,y],…]} for an explicit polyline. Coordinates '
      + 'are schematic units = 0.01 inch.\n'
      + '⚠ Pin-to-pin draws a NAIVE two-segment elbow (default horizontal-then-vertical; elbow:"vh" flips it). It '
      + 'does NOT avoid obstacles — it can run straight across other symbols and can touch pins it was not meant '
      + 'to touch, which silently creates nets. Prefer dryRun:true first and check the returned polyline, or pass '
      + 'explicit points.\n'
      + '⚠ There is NO undo. eda_wire returns each wire\'s primitiveId — feed those to eda_delete to back out.\n'
      + 'Optional net names the wire; per the EasyEDA API, if an endpoint already sits on a primitive with an '
      + 'explicitly assigned net, creation FAILS rather than merging (reported per item).',
    inputSchema: {
      type: 'object',
      properties: {
        instruction: { type: 'string', description: 'REQUIRED. The user\'s explicit request for this wiring, in their own words. '
          + 'If you cannot point at such a request in the current conversation, do not call this tool.' },
        wires: {
          type: 'array',
          description: 'Connections to draw.',
          items: {
            type: 'object',
            properties: {
              from: { type: 'string', description: 'Source pin as "<designator>.<pinNumber>", e.g. "U4.7".' },
              to: { type: 'string', description: 'Target pin as "<designator>.<pinNumber>", e.g. "L1.1".' },
              points: { type: 'array', items: { type: 'array', items: { type: 'number' } },
                description: 'Explicit polyline [[x1,y1],[x2,y2],…] in 0.01 inch units. Overrides from/to.' },
              net: { type: 'string', description: 'Optional net name to assign, e.g. "CANH".' },
              elbow: { type: 'string', description: '"hv" (default) or "vh" — which leg of the pin-to-pin elbow comes first.' },
            },
          },
        },
        dryRun: { type: 'boolean', description: 'Resolve pins and return the polylines that WOULD be drawn, drawing nothing. Use this first.' },
        windowId: WINDOW_ID_PROP,
      },
      required: ['instruction', 'wires'],
    },
    handler: async (args) => {
      const instruction = String(args.instruction || '').trim();
      if (instruction.length < 4) {
        return { isError: true, text: 'eda_wire requires `instruction` — the user\'s explicit request for this specific '
          + 'wiring. Wiring is the user\'s half of the division of labour; do not call this tool on your own initiative.' };
      }
      const wires = Array.isArray(args.wires) ? args.wires : [];
      if (!wires.length) return { isError: true, text: 'wires[] is empty.' };
      const code = "const W=" + JSON.stringify(wires) + ";const DRY=" + (args.dryRun ? 'true' : 'false') + ";"
        + "const E=e=>{try{return JSON.stringify(e);}catch(_){return String(e);}};"
        + "const doc=await eda.dmt_SelectControl.getCurrentDocumentInfo();"
        + "if(!doc||doc.documentType!==1)return{ok:false,error:'active document is not a schematic page (documentType='+(doc?doc.documentType:'none')+')'};"
        // 只在真要按脚名连线时才扫全页取引脚坐标
        + "const needPins=W.some(w=>!w.points&&(w.from||w.to));const pinAt={};"
        + "if(needPins){const M=eda.sch_PrimitiveComponent;for(const id of await M.getAllPrimitiveId()){const c=await M.get(id);if(!c||!c.designator)continue;"
        + "const pins=await M.getAllPinsByPrimitiveId(id)||[];for(const p of pins)pinAt[c.designator+'.'+p.pinNumber]=[p.x,p.y];}}"
        + "const out=[];"
        + "for(const w of W){const r={from:w.from||null,to:w.to||null,net:w.net||null};let pts=null;"
        + "if(Array.isArray(w.points)&&w.points.length>=2){pts=w.points.map(p=>[p[0],p[1]]);}"
        + "else if(w.from&&w.to){const a=pinAt[w.from],b=pinAt[w.to];"
        + "if(!a){r.ok=false;r.error='pin not found: '+w.from;out.push(r);continue;}"
        + "if(!b){r.ok=false;r.error='pin not found: '+w.to;out.push(r);continue;}"
        + "if(a[0]===b[0]||a[1]===b[1]){pts=[a,b];}"
        + "else{pts=(w.elbow==='vh')?[a,[a[0],b[1]],b]:[a,[b[0],a[1]],b];}}"
        + "else{r.ok=false;r.error='need points[], or both from and to';out.push(r);continue;}"
        + "r.polyline=pts;"
        + "if(DRY){r.ok=true;r.dryRun=true;out.push(r);continue;}"
        + "const flat=[];for(const p of pts){flat.push(p[0],p[1]);}"
        + "try{const wire=await eda.sch_PrimitiveWire.create(flat,w.net||undefined);"
        + "if(!wire){r.ok=false;r.error='create returned undefined (net conflict? endpoints not on any primitive?)';}"
        + "else{r.ok=true;r.primitiveId=wire.primitiveId||wire.id||null;}}"
        + "catch(e){r.ok=false;r.error='create failed: '+E(e);}"
        + "out.push(r);}"
        + "return{ok:out.every(r=>r.ok),dryRun:DRY,drawn:out.filter(r=>r.ok&&!r.dryRun).length,total:W.length,"
        + "hint:'no undo — pass the returned primitiveIds to eda_delete to back out',results:out};";
      const r = await runOnEda(code, args.windowId, 120_000);
      return { text: JSON.stringify(r, null, 2), isError: !!(r && r.ok === false) };
    },
  },
  {
    name: 'eda_open_document',
    description: 'Open/activate a document in EasyEDA so the other tools act on it — a SCHEMATIC PAGE, a PCB, or any '
      + 'document by uuid. Non-destructive: it only switches the active tab.\n'
      + '  • {page:"P2"} → that schematic page (name or uuid)\n'
      + '  • {pcb:"PCB1"} or {pcb:"ExpansionCard"} → that PCB (accepts the PCB name OR the BOARD name — you rarely '
      + 'remember which PCB doc belongs to which board, so either works)\n'
      + '  • {uuid:"…"} → any document uuid (schematic / page / pcb / panel), when you already have it\n'
      + '⚠ PAGE NAMES REPEAT ACROSS BOARDS (a project can hold several boards and each tends to have a "p1"). '
      + 'If the name you pass exists on more than one board this REFUSES and lists the candidates — pass '
      + 'board:"<board name>" to disambiguate. It never silently picks one, because "right kind of document, '
      + 'wrong board" is the expensive mistake.\n'
      + 'Old name eda_activate_page still works (alias). Use eda_context / eda_pages to see what exists.',
    inputSchema: {
      type: 'object',
      properties: {
        page: { type: 'string', description: 'Schematic page name (e.g. "P2") or uuid.' },
        pcb: { type: 'string', description: 'PCB doc name (e.g. "PCB1") or the board name whose PCB to open (e.g. "ExpansionCard").' },
        board: { type: 'string', description: 'Disambiguates `page` when several boards have a page with that name.' },
        uuid: { type: 'string', description: 'Open any document directly by uuid (page / schematic / pcb / panel).' },
        windowId: WINDOW_ID_PROP,
      },
    },
    handler: async (args) => {
      const T = {
        uuid: String(args.uuid || ''), page: String(args.page || ''),
        pcb: String(args.pcb || ''), board: String(args.board || ''),
      };
      if (!T.uuid && !T.page && !T.pcb) return { isError: true, text: 'Give one of: page / pcb / uuid.' };
      // 板子信息是唯一同时给出「板名 ↔ PCB ↔ 页」三者归属的来源;
      // getAllSchematicPagesInfo 拿不到板归属,而页名在各板之间会重名(实测某工程的
      // 两块板都有一页叫 "p1")⇒ 只按页名开 = 有一半概率开到另一块板上。
      const code = "const T=" + JSON.stringify(T) + ";"
        + "let boards=[];try{boards=await eda.dmt_Board.getAllBoardsInfo()||[];}catch(e){}"
        + "const roster=boards.map(b=>({board:b.name,pcb:b.pcb?b.pcb.name:null,pages:(b.schematic&&b.schematic.page?b.schematic.page.map(p=>p.name):[])}));"
        + "const open=async(u,info)=>{const tabId=await eda.dmt_EditorControl.openDocument(u);"
        + "if(!tabId)return{ok:false,error:'openDocument returned undefined — open failed',target:info,uuid:u};"
        + "return{ok:true,opened:info,uuid:u,tabId};};"
        + "if(T.uuid)return await open(T.uuid,{kind:'uuid'});"
        + "if(T.pcb){const m=boards.filter(b=>b.pcb&&(b.pcb.name===T.pcb||b.name===T.pcb||b.pcb.uuid===T.pcb));"
        + "if(!m.length)return{ok:false,error:'no PCB matches \"'+T.pcb+'\" — pass a PCB name or a board name',roster};"
        + "if(m.length>1)return{ok:false,error:'ambiguous PCB \"'+T.pcb+'\": '+m.map(b=>b.name+'/'+b.pcb.name).join(', '),roster};"
        + "return await open(m[0].pcb.uuid,{kind:'pcb',board:m[0].name,name:m[0].pcb.name});}"
        + "const cand=[];"
        + "for(const b of boards){if(T.board&&b.name!==T.board)continue;"
        + "for(const p of ((b.schematic&&b.schematic.page)||[])){"
        + "if(p.uuid===T.page||p.name===T.page||p.friendlyName===T.page)cand.push({kind:'schematic-page',board:b.name,name:p.name,uuid:p.uuid});}}"
        // 兜底:板子信息拿不到时(旧工程/异常),退回全局页表 —— 此时没有板归属可判,只能开第一个
        + "if(!cand.length&&!boards.length){const pgs=await eda.dmt_Schematic.getAllSchematicPagesInfo()||[];"
        + "const pg=pgs.find(p=>p.uuid===T.page||p.name===T.page||p.friendlyName===T.page);"
        + "if(pg)return await open(pg.uuid,{kind:'schematic-page',board:null,name:pg.name,note:'board info unavailable — page resolved globally'});"
        + "return{ok:false,error:'page not found: '+T.page,available:pgs.map(p=>p.name)};}"
        + "if(!cand.length)return{ok:false,error:'page not found: '+T.page+(T.board?' on board '+T.board:''),roster};"
        + "if(cand.length>1)return{ok:false,error:'page \"'+T.page+'\" exists on '+cand.length+' boards ('+cand.map(c=>c.board).join(', ')+') — pass board:\"…\" to say which. Nothing was opened.',candidates:cand};"
        + "return await open(cand[0].uuid,cand[0]);";
      const r = await runOnEda(code, args.windowId);
      return { text: JSON.stringify(r, null, 2), isError: !!(r && r.ok === false) };
    },
  },
  {
    name: 'eda_screenshot',
    description: 'Capture the EasyEDA canvas to a PNG file you can then Read (visual verification). FRAMING (precedence '
      + 'select > zoom > fit; if none given, captures whatever is currently on screen — which you usually cannot control '
      + 'headless, so pass one): select=["U8","U10"] frames just those parts (selects them + zoom-to-fit) — best for '
      + 'inspecting a chip and its neighbours; zoom={x,y,scale} frames an arbitrary spot (x/y in PCB mil / SCH 0.01inch, '
      + 'scale is a zoom % where ~15-40 frames one chip + neighbours, larger = tighter); fit=true frames the whole '
      + 'sheet/board (dense boards become unreadable — prefer '
      + 'select/zoom for detail). RETURNS THE IMAGE ITSELF plus the file path — do not follow up with a Read on that '
      + 'path, you already have the picture (pass inline=false if you only want the file). (Shares capture-canvas.mjs; '
      + 'avoids the gateway\'s broken zoomToRegion, uses zoomToSelectedPrimitives/zoomTo which are verified to work.)',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Output PNG path. Defaults to a temp file.' },
        fit: { type: 'boolean', description: 'zoomToAllPrimitives() first to frame everything (default false). Lowest precedence.' },
        select: { type: 'array', items: { type: 'string' }, description: 'Designators to frame, e.g. ["U8","U10"] — selects them and zooms to fit. Highest precedence.' },
        zoom: {
          type: 'object',
          description: 'Frame an arbitrary point: {x, y, scale}. scale is a zoom % (~15-40 frames a chip + neighbours; larger = tighter). Used only if select is absent.',
          properties: { x: { type: 'number' }, y: { type: 'number' }, scale: { type: 'number' } },
        },
        inline: { type: 'boolean', description: 'Return the image itself in the result (default true). false = path only, for batch captures you do not want to look at.' },
        windowId: WINDOW_ID_PROP,
      },
    },
    // 进程内直调,不 spawn 子进程:少一次 node 启动(~50ms)+ 少一次端口扫描,
    // 而且 timeoutMs 能一路传下去 —— 原来的 spawn 到点是 SIGKILL,exit 码成 null、stderr 全丢,
    // 报出来的是「exit null」而不是 EDA 的真因(违反 bridge-client.mjs:79 那条外松内紧)。
    handler: async (args) => {
      let buildCaptureCode;
      try { ({ buildCaptureCode } = await import('./capture-canvas.mjs')); }
      catch (e) { return { isError: true, text: `capture-canvas.mjs 加载失败(应与本 server 同目录): ${e && e.message ? e.message : e}` }; }

      const z = args.zoom || {};
      const o = { scopeJs: SCOPE_JS }; // 作用域拼进同一次 eval,省掉贴横幅那次单独往返
      if (Array.isArray(args.select) && args.select.length) o.select = args.select;
      else if (Number.isFinite(z.x) && Number.isFinite(z.y) && Number.isFinite(z.scale)) o.zoom = [z.x, z.y, z.scale];
      else if (args.fit) o.fit = true;

      // 取图本身实测 55ms–1s(视口空白时会撞上 EDA 内部约 1s 的等待),取景再加 400ms;
      // 给到 60s 是留给「整版 fit + 大图」的余量,HTTP 侧会自动比它松 15s。
      const r = await runOnEda(buildCaptureCode(o), args.windowId, 60_000);
      if (!r || !r.ok) return { isError: true, text: `screenshot failed: ${(r && r.reason) || 'no result from EDA'}` };

      const out = args.path || join(tmpdir(), 'eda-canvas-' + Date.now() + '.png');
      writeFileSync(out, Buffer.from(r.b64, 'base64'));
      const inline = args.inline !== false;
      return {
        text: `Saved screenshot: ${out} (${r.size} bytes, ${r.type || 'image/png'})`
          + (inline ? ' — the image is attached below; do NOT Read the file, you already have it.' : ' — Read this file to view.'),
        image: inline ? { data: r.b64, mimeType: r.type || 'image/png' } : undefined,
        scope: r.scope || undefined,
      };
    },
  },
  {
    name: 'eda_sch_netcheck',
    description: 'GEOMETRY-based connectivity check on the ACTIVE schematic page: rebuilds the netlist host-side from '
      + 'wires + net flags/ports and reports floating (unconnected) pins + multi-net shorts (rounded coords, mid-segment taps). '
      + 'exit 0=CLEAN, 1=ISSUES, >1=infra error. designators[] → per-pin net table; json=true → raw JSON. Open the target page '
      + 'first (eda_open_document). ⚠ BLIND SPOT: a passive whose pin sits directly ON an IC pin (coincident, no wire) is joined '
      + 'by EDA but NOT by this geometry check → reported as false-FLOATING. For authoritative connectivity prefer eda_netlist '
      + '(EDA\'s own compiled netlist). Use this when you need short detection or EDA can\'t compile. '
      + '`page` (a page UUID) doubles as a window selector: it picks the window whose project holds that page and errors '
      + 'if the page is not the active document, instead of silently checking whatever page the active window happens to show.',
    inputSchema: {
      type: 'object',
      properties: {
        designators: { type: 'array', items: { type: 'string' }, description: 'Per-pin net table for these parts, e.g. ["U10","U6"].' },
        page: { type: 'string', description: 'Schematic page UUID (from eda_context) — picks the window holding it and requires it to be the active document.' },
        json: { type: 'boolean', description: 'Emit raw JSON of every pin.' },
        windowId: WINDOW_ID_PROP,
      },
    },
    handler: async (args) => {
      const script = findScript('sch-netcheck.mjs');
      if (!script) return { isError: true, text: 'sch-netcheck.mjs not found (expected next to the server).' };
      const scope = await scopeForPage(args); // 先定窗口,横幅才不会指向另一块板
      const sargs = []; if (args.json) sargs.push('--json');
      if (args.windowId) sargs.push('--window', String(args.windowId));
      if (args.page) sargs.push('--page', String(args.page));
      if (Array.isArray(args.designators)) sargs.push(...args.designators);
      const { code, stdout, stderr } = await spawnScript(script, sargs, 60000);
      const verdict = code === 0 ? 'CLEAN (no floating, no shorts)' : code === 1 ? 'ISSUES found (floating and/or shorts)'
        : code === 5 ? 'TARGET NOT RESOLVED — nothing was checked (fix page/windowId, see below)' : `infra error (exit ${code})`;
      return { isError: code > 1, text: `netcheck exit=${code} → ${verdict}\n\n${(stdout || stderr).trim()}`, scope: scope || undefined };
    },
  },
  {
    name: 'eda_netlist',
    description: 'THE connectivity tool — start here. Uses EDA\'s OWN compiled netlist (sch_Netlist.getNetlist, whole '
      + 'project): coordinate-FREE, so it correctly resolves coincident pins, net labels, cross-page tags and wire net-names, '
      + 'with none of a geometry check\'s blind spots. designators[] → per-pin net table (unconnected pins flagged against the '
      + 'ACTIVE page roster); net → pins on one net; json=true → raw {nets,pin2net}.\n'
      + 'The compile sometimes returns NOTHING on a fully wired schematic (observed 2026-08-03), which looks identical to a '
      + 'completely unwired board — this tool DETECTS that itself and automatically re-runs the geometry check, labelling '
      + 'which engine each result came from. You do not have to remember the rule.\n'
      + '⚠ TARGETING: `page` is a page UUID and acts as a WINDOW SELECTOR — the tool finds the window whose project holds '
      + 'that page and errors if it is not the active document; it NEVER falls back to the bridge\'s active window. '
      + '(Measured 2026-08-05 on the older CLI: asked for page aaaa1111…, got cccc5555… from the OTHER window — 57 unrelated '
      + 'nets, no error.) With two windows open pass `page` or `windowId`. The report starts AND ends with the scope banner.\n'
      + 'Use eda_sch_netcheck directly only when you specifically want the geometry engine (e.g. multi-net SHORT detection, '
      + 'which the compiled netlist cannot express).',
    inputSchema: {
      type: 'object',
      properties: {
        designators: { type: 'array', items: { type: 'string' }, description: 'Per-pin net table for these parts, e.g. ["U10","U6"].' },
        net: { type: 'string', description: 'List all pins on a single net, e.g. "RF_INOUT".' },
        page: { type: 'string', description: 'Schematic page UUID (from eda_context) — picks the window holding it and requires it to be the active document.' },
        json: { type: 'boolean', description: 'Emit raw JSON { scope, nets, pin2net }.' },
        windowId: WINDOW_ID_PROP,
      },
    },
    handler: async (args) => {
      const script = findScript('sch-netlist.mjs');
      if (!script) return { isError: true, text: 'sch-netlist.mjs not found (expected next to the server).' };
      const scope = await scopeForPage(args); // 先定窗口,横幅才不会指向另一块板
      const sargs = []; if (args.json) sargs.push('--json'); if (args.net) sargs.push('--net', String(args.net));
      if (args.windowId) sargs.push('--window', String(args.windowId));
      if (args.page) sargs.push('--page', String(args.page));
      if (Array.isArray(args.designators)) sargs.push(...args.designators);
      const { code, stdout, stderr } = await spawnScript(script, sargs, 150000);
      // exit 5 = 目标没解析出来(page/window 不对),**什么都没读**。必须和"读了但有问题"分开报,
      // 否则一句 "infra error" 会被当成"网表读到了、只是基础设施抖了一下"。
      const verdict = code === 0 ? 'ok' : code === 1 ? 'unconnected pins found'
        : code === 5 ? 'TARGET NOT RESOLVED — nothing was read (fix page/windowId, see below)' : `infra error (exit ${code})`;
      const out = (stdout || stderr).trim();
      const head = `netlist exit=${code} → ${verdict}\n\n${out}`;

      // ⭐ 空编译自动回退(2026-08-05):`Nets: 0` 不是"这块板没接线",而是编译返回了空
      // —— 两者的输出**长得一模一样**,此前只能靠工具描述里一段散文提醒 agent 别信、改跑几何法。
      // 规则做进工具里:少一段每会话都要付的散文,也少一次"agent 没照做"的可能。
      if (!/^Nets:\s*0\b/m.test(out)) return { isError: code > 1, text: head, scope: scope || undefined };
      const nc = findScript('sch-netcheck.mjs');
      if (!nc) return { isError: code > 1, text: `${head}\n\n⚠ "Nets: 0" = 编译返回空(不可信),但找不到 sch-netcheck.mjs 无法回退。`, scope: scope || undefined };
      const ncArgs = [];
      if (args.windowId) ncArgs.push('--window', String(args.windowId));
      if (args.page) ncArgs.push('--page', String(args.page)); // 回退也必须落在同一页/同一窗口上
      if (Array.isArray(args.designators)) ncArgs.push(...args.designators);
      const fb = await spawnScript(nc, ncArgs, 60000);
      const fbVerdict = fb.code === 0 ? 'CLEAN' : fb.code === 1 ? 'ISSUES' : `infra error (exit ${fb.code})`;
      return {
        isError: fb.code > 1,
        text: `${head}\n\n${'─'.repeat(60)}\n`
          + '🔴 The compiled netlist came back with **Nets: 0**. That is getNetlist returning nothing — NOT '
          + '"this board has no wiring". The two are indistinguishable in the output above.\n'
          + '⇒ Automatically re-ran the GEOMETRY check instead. **Trust the section below; discard the one above.**\n'
          + '⚠ The geometry engine has its own blind spot: a passive whose pin sits directly ON an IC pin '
          + '(coincident, no wire) is reported as falsely FLOATING.\n\n'
          + `netcheck exit=${fb.code} → ${fbVerdict}\n\n${(fb.stdout || fb.stderr).trim()}`,
        scope: scope || undefined,
      };
    },
  },
  {
    name: 'eda_dfm_check',
    description:
      'PCB pre-check on the ACTIVE PCB, covering four things EasyEDA\'s DRC structurally cannot report:\n'
      + '  • mask — solder-mask dam width (copper gap − 2× mask expansion). ⭐ INCLUDES SAME-NET pairs, which is '
      + 'the point: DRC\'s clearance rules only look at different nets, and the three real bridges found in '
      + 'production QC were all same-net. Same-net findings get "neighbour-gap triage": how many pads out until '
      + 'a DIFFERENT net is reached, because solder does not stop neatly at one gap.\n'
      + '  • via — via inside / too close to a pad opening (⭐ incl. same net). Tenting does NOT save a via-in-pad: '
      + 'the pad\'s own mask opening exposes it anyway.\n'
      + '  • body — 3D component-body envelope overlap. Gerber has no component bodies and CPL has no sizes, so '
      + 'this can only be computed in the EDA domain.\n'
      + '  • pour — copper pour frames vs poured fills: catches "a pour was drawn but never actually poured". '
      + '⚠ It answers "was it poured", NOT "is it up to date" — there is no dirty flag and NO re-pour API at all, '
      + 'so re-pouring after edits remains a HUMAN step.\n'
      + '⛔ NOT a replacement for jlc-dfm.com. That is the Gerber-domain gate maintained by the fab; this runs '
      + 'while you are still drawing and adds the two things Gerber cannot express (net semantics + body sizes). '
      + 'Run both.\n'
      + '🔴 CHECK THE FIRST LINE OF THE OUTPUT — it prints which project/board was actually read. Designators are '
      + 'numbered PER BOARD, so a report from the wrong board looks exactly like a correct one. With two EDA '
      + 'windows open, pass windowId.\n'
      + 'exit 0 = no findings, 1 = findings, >1 = infra error (no bridge / active doc is not a PCB).',
    inputSchema: {
      type: 'object',
      properties: {
        only: { type: 'array', items: { type: 'string' }, description: 'Subset of ["mask","via","body","pour"] (default: all four).' },
        maskMinMm: { type: 'number', description: 'Solder-mask dam floor in mm (default 0.1 — measured, not official; see the script header).' },
        viaMarginMm: { type: 'number', description: 'Via-to-pad-edge floor in mm (default 0.05).' },
        bodyMinMm: { type: 'number', description: 'Component-body clearance floor in mm (default 0 = report real overlaps only).' },
        triageSpanMm: { type: 'number', description: 'How far the same-net neighbour-gap triage looks outward, mm (default 0.3).' },
        json: { type: 'boolean', description: 'Machine-readable JSON instead of the human report.' },
        windowId: WINDOW_ID_PROP,
      },
    },
    handler: async (args) => {
      const script = findScript('pcb-dfm-check.mjs');
      if (!script) return { isError: true, text: 'pcb-dfm-check.mjs not found (expected next to the server).' };
      const sargs = [];
      if (Array.isArray(args.only) && args.only.length) sargs.push('--only', args.only.join(','));
      for (const [flag, v] of [['--mask-min', args.maskMinMm], ['--via-margin', args.viaMarginMm],
        ['--body-min', args.bodyMinMm], ['--triage-span', args.triageSpanMm]]) {
        if (Number.isFinite(v)) sargs.push(flag, String(v));
      }
      if (args.json) sargs.push('--json');
      if (args.windowId) sargs.push('--window', String(args.windowId));
      // 整板分析(834 焊盘 / 412 过孔 / 212 器件)实测秒级,但 O(n²) 的对比在更大的板上会更久
      const { code, stdout, stderr } = await spawnScript(script, sargs, 180_000);
      const verdict = code === 0 ? '无告警' : code === 1 ? '有告警(逐条判)' : `环境错误 (exit ${code})`;
      return { isError: code > 1, text: `dfm-check exit=${code} → ${verdict}\n\n${(stdout || stderr).trim()}` };
    },
  },
];

const TOOL_MAP = new Map(TOOLS.map((t) => [t.name, t]));

// 改过名的工具:旧名仍可调用,但**不列进 tools/list** —— 老会话/老文档里的调用不会断,
// 新会话看到的又只有一个名字(两个同义工具并列只会让 agent 犹豫该用哪个)。
const TOOL_ALIASES = {
  eda_activate_page: 'eda_open_document', // 2026-08-05 改名(旧名只认原理图页)
  // eda_pages 的扁平页表【没有板归属】,而页名跨板重名 ⇒ 它给出的清单无法安全据以行动。
  // eda_context 现在把页按板列出(带 uuid + active),严格覆盖它 ⇒ 老调用转到 context。
  eda_pages: 'eda_context',
};
for (const [alias, real] of Object.entries(TOOL_ALIASES)) {
  const t = TOOL_MAP.get(real);
  if (t) TOOL_MAP.set(alias, t);
}

// ─── MCP stdio JSON-RPC loop ────────────────────────────────────────
function send(msg) {
  process.stdout.write(JSON.stringify(msg) + '\n');
}

function sendResult(id, result) { send({ jsonrpc: '2.0', id, result }); }
function sendError(id, code, message) { send({ jsonrpc: '2.0', id, error: { code, message } }); }

function toolResult(payload) {
  // payload: string | {text, isError, image:{data,mimeType}}
  if (typeof payload === 'string') return { content: [{ type: 'text', text: payload }] };
  const content = [{ type: 'text', text: payload.text }];
  // 图**内联**成 MCP image content。截图工具原来只回一个路径,agent 必须再调一次 Read 才看得见 ——
  // 那是一整个模型回合,比这条链路上所有毫秒加起来都贵。
  if (payload.image && payload.image.data) {
    content.push({ type: 'image', data: payload.image.data, mimeType: payload.image.mimeType || 'image/png' });
  }
  return { content, isError: !!payload.isError };
}

// 把作用域横幅贴到工具返回值最前面。探测失败(桥没起/EDA 没连)就静默跳过 ——
// 横幅是辅助信息,绝不能让它把工具本身的结果或错误吃掉。
async function withScope(payload, scopePromise) {
  let banner = null;
  try { banner = scopeBanner(await scopePromise); } catch { /* 探测失败不影响工具结果 */ }
  if (!banner) return payload;
  if (typeof payload === 'string') return `${banner}\n${payload}`;
  return { ...payload, text: `${banner}\n${payload.text}` };
}

async function handleMessage(msg) {
  const { id, method, params } = msg;
  const isNotification = id === undefined || id === null;

  switch (method) {
    case 'initialize':
      sendResult(id, {
        protocolVersion: (params && params.protocolVersion) || '2025-06-18',
        capabilities: { tools: {} },
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
        instructions: SERVER_INSTRUCTIONS,
      });
      return;
    case 'notifications/initialized':
    case 'initialized':
      return; // notification, no response
    case 'ping':
      if (!isNotification) sendResult(id, {});
      return;
    case 'tools/list':
      sendResult(id, {
        tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
      });
      return;
    case 'tools/call': {
      const name = params && params.name;
      const tool = TOOL_MAP.get(name);
      if (!tool) { sendError(id, -32602, `Unknown tool: ${name}`); return; }
      const args = (params && params.arguments) || {};
      const mutates = SCOPE_MUTATING_TOOLS.has(name);
      // 只读工具:横幅与 handler 并发探,不加延迟。
      // 会改作用域的工具:必须等 handler 跑完再探(否则报的是切换前的板/页)。
      const scopeP = NO_SCOPE_TOOLS.has(name) || mutates ? Promise.resolve(null) : edaScope(args.windowId);
      const after = async (payload) => {
        // handler 自带作用域(截图那类:它本来就要在 EDA 里跑一次 eval,把 SCOPE_JS 拼进同一次往返)
        // ⇒ 这里就不必再单独探一次。顺手用它把缓存刷成最新的,后面的只读工具也蹭得上。
        if (payload && typeof payload === 'object' && payload.scope) {
          const { scope, ...rest } = payload;
          scopeCache.clear();
          scopeCache.set(args.windowId || '', { at: Date.now(), promise: Promise.resolve(scope) });
          return withScope(rest, Promise.resolve(scope));
        }
        if (!mutates) return withScope(payload, scopeP);
        scopeCache.clear(); // 作用域已变,缓存作废
        return withScope(payload, edaScope(args.windowId));
      };
      try {
        sendResult(id, toolResult(await after(await tool.handler(args))));
      } catch (err) {
        const text = `Tool "${name}" error: ${err && err.message ? err.message : String(err)}`;
        sendResult(id, toolResult(await after({ isError: true, text })));
      }
      return;
    }
    default:
      if (!isNotification) sendError(id, -32601, `Method not found: ${method}`);
      return;
  }
}

function main() {
  log(`starting (bridge=in-process (falls back to an existing one on 49620-49629), refs=${resolveReferencesDir() || 'NOT FOUND'})`);
  const rl = createInterface({ input: process.stdin });
  rl.on('line', (line) => {
    const s = line.trim();
    if (!s) return;
    let msg;
    try { msg = JSON.parse(s); } catch { log(`ignoring non-JSON line: ${s.slice(0, 120)}`); return; }
    handleMessage(msg).catch((e) => log(`handler crash: ${e && e.stack ? e.stack : e}`));
  });
  rl.on('close', () => process.exit(0));
}

main();
