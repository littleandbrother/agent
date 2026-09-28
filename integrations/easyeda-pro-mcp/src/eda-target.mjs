/**
 * eda-target.mjs — 「这次调用到底打在哪块板 / 哪一页上」的**唯一一份**判定 + 横幅。
 *
 * 起因(2026-08-05 实测):给 `sch-netlist.mjs` 传 BOARD-A 的页 uuid `aaaa1111…`,
 * 它回的是 `cccc5555…`(另一个窗口 proj-b 那块板)的 57 个网络,全是 U1/U2/U3/X1,
 * **一声不吭**。原因:页 uuid 只是 `dmt_EditorControl.openDocument()` 的入参,而
 * openDocument 打在 **bridge 的活动窗口**上;那个窗口里没有这一页 ⇒ 按签名返回
 * `undefined`,脚本 `if (tab)` 一跳过,就接着把**当前活动文档**当成结果读了。
 *
 * ⇒ 本模块把这条教训做成三件事,谁都不用再记:
 *   1. **页 uuid 是窗口选择器**,不是打开命令 —— 先扫所有连着的窗口,找出**哪个窗口**
 *      的工程里有这一页;找不到 / 找到多个 ⇒ 报错(而不是退回活动窗口)。
 *   2. **窗口在开跑前钉死。** 活动窗口会在断线时易主,一次多来回的脚本(网表要 fire →
 *      poll → 分块取)中途飘走的话,前半段和后半段读的是两块板。钉死 = 中途飘不动。
 *   3. **横幅**:每份报告都带 `工程 / 板 / 页 + 页 uuid + 窗口`。位号按板独立编号,
 *      读错板的报告和读对的长得一模一样 —— 只有横幅能把这两者分开。
 *
 * 分工:`bridge-client.mjs` 只管传输(找桥 / 发 HTTP / `--window`),**不碰 EDA 语义**;
 * 「什么是页、哪块板」这些在这里。新脚本要么 import 这两份,要么别用页 uuid。
 */
import { pathToFileURL } from 'node:url';
import { listWindows, exec as bridgeExec, windowTag } from './bridge-client.mjs';

/** 目标解析失败(找不到页 / 页不在活动文档上 / 窗口不对)统一用这个退出码,与 infra 错误区分。 */
export const TARGET_EXIT = 5;

export class TargetError extends Error {
  constructor(message) { super(message); this.name = 'TargetError'; this.exitCode = TARGET_EXIT; }
}

// EDA 的文档 uuid 是 16 位十六进制(aaaa1111bbbb2222);窗口 id 是 randomUUID() 的 36 位带杠形式。
// 位号(U1/R29/TP3)不可能长这样 —— 所以这条正则足够把「用户把 uuid 当位号传进来」认出来。
export const UUID_RE = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,})$/i;
export const looksLikeUuid = (s) => UUID_RE.test(String(s ?? '').trim());

/**
 * 解析 `--page <uuid>`(页 uuid = 目标页,同时**用来定位窗口**)。
 * 与 `parseWindowArg` 一样,返回的 `rest` 已摘掉 `--page` 及其取值。
 * 故意不设环境变量兜底:一个忘了 unset 的 env 会静默地把结果锁在别的板上。
 */
export function parsePageArg(argv) {
  const i = argv.indexOf('--page');
  const value = i >= 0 ? (argv[i + 1] || null) : null;
  const rest = i >= 0 ? argv.filter((_, k) => k !== i && k !== i + 1) : argv.slice();
  return { pageUuid: value || null, rest };
}

/**
 * 裸参数守卫:这些脚本把「不以 -- 开头的参数」当**位号**,而 uuid 混进去只会被当成
 * 一个永远匹配不上的位号 —— 过滤器全空,报告照常输出,**不报错**。正是本项目反复踩的坑。
 */
export function assertNoUuidArgs(rest, hint = 'use --page <uuid> to name a schematic page') {
  const bad = rest.filter((a) => !a.startsWith('--') && looksLikeUuid(a));
  if (bad.length) {
    throw new TargetError(
      `参数 ${bad.join(' ')} 看着是 uuid,但这个位置只收**位号**(U10 / R29 / TP3)。\n`
      + `  一个不存在的位号 = 过滤器为空 = 报告照出、不报错 —— 所以这里直接拦下。\n`
      + `  ⇒ ${hint}`);
  }
}

// 一次往返读齐「在哪」:工程 / 板(含同工程的其它板)/ 当前文档 / 本工程的全部原理图页。
// 页表是用来**按 uuid 找窗口**的,所以哪怕当前文档是 PCB 也要取。
const PROBE_JS =
  "const s={};"
  + "try{const p=await eda.dmt_Project.getCurrentProjectInfo();s.project=p?(p.friendlyName||p.name||''):'';}catch(e){}"
  + "try{const b=await eda.dmt_Board.getCurrentBoardInfo();if(b){s.board=b.name||'';s.boardPcb=b.pcb?b.pcb.name:'';}}catch(e){}"
  + "try{const all=await eda.dmt_Board.getAllBoardsInfo();if(all){s.boardCount=all.length;s.boards=all.map(x=>x.name);}}catch(e){}"
  + "try{const d=await eda.dmt_SelectControl.getCurrentDocumentInfo();if(d){s.docType=d.documentType;s.docUuid=d.uuid;}}catch(e){}"
  + "try{const pg=await eda.dmt_Schematic.getAllSchematicPagesInfo();s.pages=(pg||[]).map(x=>({uuid:x.uuid,name:x.name||x.friendlyName||''}));}catch(e){}"
  + "if(s.docType===1&&s.pages){const hit=s.pages.find(x=>x.uuid===s.docUuid);s.page=hit?hit.name:'';}"
  + "else if(s.docType===3)s.page=s.boardPcb||'';"
  + "return s;";

/** 探一个窗口的作用域。失败(窗口刚断/超时)返回 null,由调用方决定要不要致命。 */
export async function probeWindow(port, windowId) {
  try { return await bridgeExec(port, PROBE_JS, { windowId, timeoutMs: 8000 }); }
  catch { return null; }
}

const shortUuid = (u) => (u ? String(u).slice(0, 16) : '?');
const winLabel = (w) => `${windowTag(w.windowId)}${w.label ? ` [${w.label}]` : ''}${w.active ? ' (活动)' : ''}`;

function describeWindow(w, probe) {
  if (!probe) return `  ${winLabel(w)}  (探测失败)`;
  const pages = (probe.pages || []).map((p) => `${p.name || '(unnamed)'}=${shortUuid(p.uuid)}`).join(' · ');
  return `  ${winLabel(w)}  工程 ${probe.project || '?'} / 板 ${probe.board || '?'}`
    + ` / 当前文档 ${shortUuid(probe.docUuid)}${probe.page ? `(${probe.page})` : ''}`
    + (pages ? `\n      本工程的页: ${pages}` : '');
}

/**
 * 把 `--window` / `--page` 解析成一个**钉死的** windowId,并顺带把作用域探回来。
 *
 * 语义:
 *   - 给了 `pageUuid`:按 uuid 找**哪个窗口的工程里有这一页**。0 个 ⇒ 报错(绝不退回活动
 *     窗口);>1 个 ⇒ 报错要 `--window` 消歧;找到的窗口里这一页**不是当前文档** ⇒ 也报错
 *     (网表虽是全工程编译,但「未连接引脚」是拿当前页的元件册对的账,页不对 = 结论不对)。
 *   - 没给 `pageUuid`:钉死当前活动窗口的 id(而不是每次都发"打活动窗口"),这样中途易主
 *     也飘不走;窗口 >1 且没显式指定时,`warnings` 里带一条,由调用方印进横幅。
 *
 * @returns {{windowId:string, probe:object|null, windows:Array, warnings:string[]}}
 */
export async function resolveTarget(port, { windowId = null, pageUuid = null } = {}) {
  const list = await listWindows(port);
  const windows = ((list && list.windows) || []).filter((w) => w.connected);
  const activeWindowId = (list && list.activeWindowId) || null;
  const warnings = [];

  if (!windows.length) throw new TargetError('bridge 在跑,但没有连着的 EDA 窗口(EasyEDA 里加载 eext 扩展)。');
  if (windowId && !windows.some((w) => w.windowId === windowId)) {
    throw new TargetError(`--window ${windowId} 不在连着的窗口里:\n${windows.map((w) => `  ${winLabel(w)}`).join('\n')}`);
  }

  if (pageUuid) {
    const cands = windowId ? windows.filter((w) => w.windowId === windowId) : windows;
    const probes = [];
    for (const w of cands) probes.push({ w, probe: await probeWindow(port, w.windowId) });
    const hits = probes.filter(({ probe }) => (probe?.pages || []).some((p) => p.uuid === pageUuid));

    if (!hits.length) {
      throw new TargetError(
        `页 uuid ${pageUuid} 不在${windowId ? '指定窗口' : `连着的 ${cands.length} 个窗口`}的工程里:\n`
        + probes.map(({ w, probe }) => describeWindow(w, probe)).join('\n')
        + '\n  ⇒ 页 uuid 认不出窗口时**不会**退回活动窗口(那正是"结果落在别的板上却看起来正常")。'
        + '\n     先在目标窗口打开该工程,或用 eda_windows 查 windowId 后显式 --window。');
    }
    if (hits.length > 1) {
      throw new TargetError(
        `页 uuid ${pageUuid} 在多个窗口里都有(同一工程开了两次?),无法确定打哪个:\n`
        + hits.map(({ w, probe }) => describeWindow(w, probe)).join('\n')
        + '\n  ⇒ 加 --window <id> 消歧。');
    }
    const { w, probe } = hits[0];
    if (probe.docUuid !== pageUuid) {
      const want = (probe.pages || []).find((p) => p.uuid === pageUuid);
      throw new TargetError(
        `页 ${want?.name || '(unnamed)'} (${pageUuid}) 在窗口 ${winLabel(w)} 里,但**当前文档不是它**:\n`
        + describeWindow(w, probe)
        + '\n  ⇒ 先按 uuid 打开该页(eda_open_document / dmt_EditorControl.openDocument),再跑。'
        + '\n     (页名跨板重名,按名字切页会切到另一块板的同名页。)');
    }
    return { windowId: w.windowId, probe, windows, warnings };
  }

  const pinned = windowId || activeWindowId;
  if (!pinned) throw new TargetError('bridge 没有活动窗口可用,显式给 --window <id>(eda_windows 里查)。');
  if (!windowId && windows.length > 1) {
    warnings.push(
      `⚠ ${windows.length} 个 EDA 窗口连着,没给 --window/--page —— 钉的是**此刻**的活动窗口。`
      + '活动窗口在断线时会易主且不还,横幅里的板名先核一眼再采信结果。');
  }
  return { windowId: pinned, probe: await probeWindow(port, pinned), windows, warnings };
}

/**
 * 一行横幅:每份报告的**第一行**都该是它。带页 uuid —— 传了 uuid 的人要能一眼对上账。
 * 同工程多块板时加 ⚠ + 板名清单(摆错板 / 读错板的代价太高,值得每次都刺一下眼)。
 */
export function targetBanner(tool, target) {
  const { windowId, probe, windows } = target;
  const multiBoard = probe && probe.boardCount > 1 ? ` ⚠共${probe.boardCount}块板: ${(probe.boards || []).join(' / ')}` : '';
  const win = `窗口 ${windowTag(windowId)}${windows && windows.length > 1 ? `(共${windows.length}个)` : ''}`;
  if (!probe) return `[${tool}] 读的是: (作用域探测失败) · ${win}`;
  return `[${tool}] 读的是: 工程 ${probe.project || '?'} / 板 ${probe.board || '?'}${multiBoard}`
    + ` / 页 ${probe.page || '(unnamed)'} [${shortUuid(probe.docUuid)}] · ${win}`;
}

// ─── 自检:纯函数 + 两个【假 eext 窗口】的定位全流程 ─────────────────────────
// 假的是 EDA 的应答,走的是真 bridge + 真 HTTP —— 不需要 EasyEDA、不需要板子。
// ⚠ 只在【本文件是入口】时跑 —— 别的模块 import 本文件时 argv 里也可能有 --self-test。
// bridge 那两份用 **动态 import**:裸脚本 import 本模块时不该把 bridge/ws-server 也拖进来。
async function selfTest() {
  let pass = 0, fail = 0;
  const ok = (name, cond, extra = '') => { (cond ? pass++ : fail++); console.log(`${cond ? '✅' : '❌'} ${name}${extra ? '  ' + extra : ''}`); };

  ok('16 位十六进制页 uuid 认得出', looksLikeUuid('aaaa1111bbbb2222'));
  ok('randomUUID 形式认得出', looksLikeUuid('3f1a2b4c-5d6e-4f70-8901-abcdef123456'));
  ok('位号不误判', !looksLikeUuid('U10') && !looksLikeUuid('R29') && !looksLikeUuid('TP3') && !looksLikeUuid('C1'));
  ok('十六进制样的短位号不误判', !looksLikeUuid('D1') && !looksLikeUuid('BEEF'));

  const p1 = parsePageArg(['--page', 'aaaa1111bbbb2222', 'U10']);
  ok('--page 摘干净取值', p1.pageUuid === 'aaaa1111bbbb2222' && p1.rest.join(',') === 'U10', JSON.stringify(p1));
  const p2 = parsePageArg(['U10', '--json']);
  ok('没有 --page 时原样返回', p2.pageUuid === null && p2.rest.join(',') === 'U10,--json');

  let threw = null;
  try { assertNoUuidArgs(['U10', 'aaaa1111bbbb2222']); } catch (e) { threw = e; }
  ok('裸 uuid 当位号 → 拦下', threw instanceof TargetError && threw.exitCode === TARGET_EXIT);
  threw = null;
  try { assertNoUuidArgs(['U10', 'R29']); } catch (e) { threw = e; }
  ok('正常位号放行', threw === null);

  const banner = targetBanner('t', {
    windowId: 'aabbccdd-1111-2222-3333-444455556666',
    probe: { project: 'proj-a', board: 'BOARD-A', boardCount: 2, boards: ['BOARD-A', 'BOARD-B'], docUuid: 'aaaa1111bbbb2222', page: 'P1' },
    windows: [{}, {}],
  });
  ok('横幅带板名/页/uuid/窗口', /BOARD-A/.test(banner) && /共2块板/.test(banner) && /aaaa1111bbbb2222/.test(banner) && /aabbccdd/.test(banner), banner);
  ok('探测失败也出横幅', /探测失败/.test(targetBanner('t', { windowId: null, probe: null, windows: [] })));

  // ── 两个假窗口:复刻 2026-08-05 那次事故的现场 ──────────────────────────
  // 活动窗口 = proj-b,而要读的页在另一个窗口(proj-a/BOARD-A)里。
  const { startEmbeddedBridge } = await import('./bridge-embedded.mjs');
  const { randomUUID } = await import('node:crypto');
  const PAGE_A1 = 'aaaa1111bbbb2222', PAGE_A4 = 'aaaa3333bbbb4444', PAGE_X1 = 'cccc5555dddd6666';
  const br = await startEmbeddedBridge({ portStart: 49710, portEnd: 49719, log: () => {} });

  /** 假 eext:握手 → register → 任何 execute 都回这个窗口的作用域 */
  const fakeEext = (label, scope) => new Promise((resolve) => {
    const ws = new WebSocket(`ws://127.0.0.1:${br.port}/eda`);
    const windowId = randomUUID();
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'handshake') {
        ws.send(JSON.stringify({ type: 'register', windowId, label, timestamp: Date.now() }));
        setTimeout(() => resolve({ ws, windowId }), 60);
      } else if (msg.type === 'execute') {
        ws.send(JSON.stringify({ type: 'result', id: msg.id, result: scope }));
      }
    });
  });

  const catchErr = async (p) => { try { await p; return null; } catch (e) { return e; } };
  try {
    // 注册顺序 = 活动窗口顺序:proj-b 先连 ⇒ 它是活动窗口(正是事故现场)
    const sig = await fakeEext('proj-b', {
      project: 'proj-b', board: 'BOARD-X', boardCount: 1, boards: ['BOARD-X'],
      docType: 1, docUuid: PAGE_X1, page: 'P1', pages: [{ uuid: PAGE_X1, name: 'P1' }],
    });
    const rt = await fakeEext('proj-a', {
      project: 'proj-a', board: 'BOARD-A', boardCount: 2, boards: ['BOARD-A', 'BOARD-B'],
      docType: 1, docUuid: PAGE_A1, page: 'P1',
      pages: [{ uuid: PAGE_A1, name: 'P1' }, { uuid: PAGE_A4, name: 'P4' }],
    });

    const t1 = await resolveTarget(br.port, { pageUuid: PAGE_A1 });
    ok('⭐ 页 uuid 把调用从活动窗口(proj-b)拽到了对的窗口', t1.windowId === rt.windowId, targetBanner('netlist', t1));

    const e1 = await catchErr(resolveTarget(br.port, { pageUuid: 'deadbeefdeadbeef' }));
    ok('页 uuid 找不到 → 报错,不退回活动窗口',
      e1 instanceof TargetError && /不在连着的 2 个窗口/.test(e1.message) && /proj-b/.test(e1.message) && /proj-a/.test(e1.message));

    const e2 = await catchErr(resolveTarget(br.port, { pageUuid: PAGE_A4 }));
    ok('页在但不是当前文档 → 报错(元件册会对错页)', e2 instanceof TargetError && /当前文档不是它/.test(e2.message));

    const e3 = await catchErr(resolveTarget(br.port, { pageUuid: PAGE_A1, windowId: sig.windowId }));
    ok('--window 与 --page 打架 → 报错', e3 instanceof TargetError && /不在指定窗口/.test(e3.message));

    const e4 = await catchErr(resolveTarget(br.port, { windowId: 'not-a-window' }));
    ok('--window 不存在 → 报错', e4 instanceof TargetError && /不在连着的窗口里/.test(e4.message));

    const t2 = await resolveTarget(br.port, {});
    ok('不给目标 → 钉死此刻的活动窗口(而不是每次现问)', t2.windowId === sig.windowId);
    ok('多窗口且没指定 → 横幅带 ⚠ 警告', t2.warnings.length === 1 && /会易主/.test(t2.warnings[0]), t2.warnings[0]);

    sig.ws.close(); rt.ws.close();
    await new Promise((r) => setTimeout(r, 80));
    const e5 = await catchErr(resolveTarget(br.port, { pageUuid: PAGE_A1 }));
    ok('窗口全断开 → 明说没窗口', e5 instanceof TargetError && /没有连着的 EDA 窗口/.test(e5.message));
  } finally {
    await br.close();
  }

  console.log(`\n${fail ? '❌' : '✅'} eda-target: ${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain && process.argv.includes('--self-test')) selfTest();
