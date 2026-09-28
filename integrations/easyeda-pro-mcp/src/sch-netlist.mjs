/**
 * sch-netlist.mjs — Coordinate-FREE net-to-net connectivity from EDA's OWN
 * compiled netlist (`sch_Netlist.getNetlist`). This is the authoritative source:
 * it resolves coincident pins, net labels, cross-page tags and wire net-names
 * exactly as EDA's compiler does — none of the geometry reconstruction (and none
 * of its blind spots) that `sch-netcheck.mjs` relies on.
 *
 * Why this exists / why it's better than sch-netcheck.mjs:
 *   - sch-netcheck rebuilds connectivity from wire/flag GEOMETRY. That has a
 *     false-FLOATING blind spot: a passive whose pin is placed directly ON an IC
 *     pin (coincident, no wire) is joined by EDA (shared `$…` net) but NOT by a
 *     geometry union that only links via wires/labels. Verified 2026-07-07: it
 *     reported 22 P2 pins floating that EDA's netlist shows fully connected
 *     (RREF/VD12D/RSET/AVDD33/DVDD33/LED/1.05V …).
 *   - This script asks EDA directly, so it is correct by construction.
 *
 * The one obstacle to getNetlist(): a synchronous `return await getNetlist()`
 * exceeds the run-api-gateway's ~25s in-EDA execution cap ("Execution exceeded
 * 25000ms" — that limit is inside EDA, not the bridge's 30s). So we DON'T block:
 * fire it into a globalThis var, then poll with fast calls until it resolves,
 * then pull the string (chunked). Each individual /execute returns in ms.
 *
 * Netlist format = Protel 2.0: component section `[ … ]`, then net blocks
 * `( NetName \n DES-PIN <parttype>-<pinname> <type> \n … )`.
 *
 * Scope: the net→pins map is WHOLE-PROJECT (getNetlist compiles all pages).
 * The unconnected-pin check compares against the ACTIVE page's part roster only
 * (open the page you want to audit first) — the connectivity map itself is global.
 *
 * Usage:
 *   node sch-netlist.mjs                 summary: net count + unconnected pins
 *   node sch-netlist.mjs U10 U6 J2       per-pin net table for those designators
 *   node sch-netlist.mjs --all           per-pin net table for every part
 *   node sch-netlist.mjs --json          raw JSON { nets, pin2net, scope }
 *   node sch-netlist.mjs --net RF_INOUT  pins on one net
 *   node sch-netlist.mjs --page <uuid>   ⭐ target the WINDOW whose project holds
 *                                        that schematic page, and require the page
 *                                        to be the active document. Not found /
 *                                        found twice / not active = hard error —
 *                                        it never silently falls back to the
 *                                        active window (see eda-target.mjs).
 *   node sch-netlist.mjs --window <id>   target a specific EDA window (id from
 *                                        GET /eda-windows or eda_windows); env
 *                                        EDA_WINDOW_ID does the same. Without it
 *                                        (and without --page) the bridge's ACTIVE
 *                                        window is pinned at start-up — pinned so
 *                                        it cannot drift mid-run, but WHICH window
 *                                        that is still depends on the bridge, so
 *                                        with two windows open pass --page/--window.
 *
 * Every report starts AND ends with the scope banner (project / board / page +
 * page uuid + window): designators are numbered per board, so a netlist read off
 * the wrong board looks exactly like a correct one.
 *
 * Exit code: 0 = ok · 1 = unconnected pins found · 5 = target resolution failed
 *            (bad --page/--window) · other >1 = infra error.
 */
// 找桥 / 发 HTTP / 解析 --window 全在这一份共享底座里(此前四个脚本各抄一份)
import { findBridge, exec as bridgeExec, parseWindowArg } from './bridge-client.mjs';
// 页 uuid → 窗口、以及横幅:EDA 语义那一层(bridge-client 只管传输)
import { parsePageArg, assertNoUuidArgs, resolveTarget, targetBanner, TargetError, TARGET_EXIT } from './eda-target.mjs';

// Target window: null = whatever the bridge calls "active" right now.
// Set once in main() and threaded into every /execute so a multi-page run can
// never straddle two windows halfway through.
let WINDOW_ID = null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 每次调用都短(getNetlist 是 fire-and-poll,不是一次阻塞),所以只需要一个宽松的 socket 超时
const exec = (port, code) => bridgeExec(port, code, { windowId: WINDOW_ID, httpTimeoutMs: 35000 });

/** Fire getNetlist async into a global, poll until done, pull the string chunked. */
async function fetchNetlist(port, type = 'Protel2') {
  const DBG = process.env.NL_DEBUG;
  if (DBG) console.error('[nl] firing getNetlist…');
  await exec(port,
    `globalThis.__nlDone=false;globalThis.__nl="";globalThis.__nlErr="";` +
    `(async()=>{try{globalThis.__nl=await eda.sch_Netlist.getNetlist(${JSON.stringify(type)});}` +
    `catch(e){globalThis.__nlErr=String(e&&e.message||e);}finally{globalThis.__nlDone=true;}})();return "started";`);
  if (DBG) console.error('[nl] fired; polling…');
  const deadline = Date.now() + 120000;
  let st;
  do {
    await sleep(1500);
    st = await exec(port, `return {done:globalThis.__nlDone,err:globalThis.__nlErr,len:(globalThis.__nl||"").length};`);
    if (DBG) console.error('[nl] poll:', JSON.stringify(st));
    if (st.err) throw new Error('getNetlist failed in EDA: ' + st.err);
  } while (!st.done && Date.now() < deadline);
  if (DBG) console.error('[nl] done, len=' + st.len + '; fetching chunks…');
  if (!st.done) throw new Error('getNetlist did not resolve within 120s');
  // pull chunked (survive large boards / bridge payload limits)
  const CH = 60000;
  let out = '';
  for (let i = 0; i < st.len; i += CH) {
    out += await exec(port, `return (globalThis.__nl||"").slice(${i},${i + CH});`);
  }
  return out;
}

/** Parse Protel 2.0 netlist → { nets: {name:[DES-PIN…]}, pin2net: {DES-PIN:name} }. */
function parseProtel(nl) {
  const nets = {}; const pin2net = {};
  let inNet = false, name = null, pins = null;
  for (const raw of nl.split('\n')) {
    const s = raw.trim();
    if (s === '(') { inNet = true; name = null; pins = []; }
    else if (s === ')') { if (inNet && name != null) { nets[name] = pins; for (const p of pins) pin2net[p] = name; } inNet = false; }
    else if (inNet) { if (name == null) name = s; else if (s) pins.push(s.split(' ')[0]); }
  }
  return { nets, pin2net };
}

/** Roster of the ACTIVE page's part pins (pinNumber/name only — no coords, no
 * connectivity). Scoped to the active page: getAllPinsByPrimitiveId is reliable
 * there and it keeps the call count small. Per-part guarded so one bad component
 * can't abort the whole roster. Used only to flag pins absent from the netlist. */
async function fetchRoster(port) {
  return exec(port,
    `const ids=await eda.sch_PrimitiveComponent.getAllPrimitiveId("part");const out={};` +
    `for(const id of ids){try{const a=await eda.sch_PrimitiveComponent.get([id]);const c=a&&a[0];if(!c||!c.designator)continue;` +
    `const ps=await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id);` +
    `out[c.designator]=(ps||[]).map(p=>({n:p.pinNumber,nm:p.pinName,nc:!!p.noConnected}));}catch(e){}}return out;`);
}

function num(s) { const m = String(s).match(/\d+/g); return m ? m.map(Number) : [0]; }
function cmpDes(a, b) { const A = num(a), B = num(b); const pa = a.replace(/\d+/g, ''), pb = b.replace(/\d+/g, ''); return pa === pb ? (A[0] - B[0]) : a.localeCompare(b); }

async function main() {
  // parseWindowArg / parsePageArg 摘掉各自的取值,剩下的才轮到本脚本自己的参数解析
  const { windowId, rest: afterWindow } = parseWindowArg(process.argv.slice(2));
  const { pageUuid, rest: args } = parsePageArg(afterWindow);
  const jsonOut = args.includes('--json');
  const all = args.includes('--all');
  const netIdx = args.indexOf('--net');
  const oneNet = netIdx >= 0 ? args[netIdx + 1] : null;
  // --net takes a value; that value is not a designator.
  const desArgs = args.filter((a) => !a.startsWith('--') && a !== oneNet);
  // 位号位置上出现 uuid = 用户想指定页却指定成了一个永不匹配的位号(报告照出、不报错)
  assertNoUuidArgs(desArgs, '想指定原理图页请用 --page <uuid>;想指定窗口用 --window <id>。');
  const desFilter = desArgs.map((s) => s.toUpperCase());

  const b = await findBridge();
  if (!b) { console.error('No easyeda-bridge on 49620-49629. Start the bridge / MCP first.'); process.exit(2); }
  if (!b.health.edaConnected) { console.error('Bridge up but no EDA window connected.'); process.exit(2); }
  const port = b.port;

  // ⭐ 目标窗口在**开跑前钉死**:网表是 fire → poll → 分块取,多次往返;不钉死的话
  //   中途活动窗口易主,前半段和后半段读的是两块板(而且看不出来)。
  const target = await resolveTarget(port, { windowId, pageUuid });
  WINDOW_ID = target.windowId;
  const banner = targetBanner('netlist', target);
  // --json 模式 stdout 必须是纯 JSON(调用方要 parse),横幅走 stderr,同时进 JSON 的 scope 字段
  const say = jsonOut ? console.error : console.log;
  say(banner);
  for (const w of target.warnings) say(w);

  let nl;
  try { nl = await fetchNetlist(port); }
  catch (e) { console.error('Netlist fetch failed: ' + e.message); process.exit(2); }
  // Roster is best-effort: only needed to flag pins ABSENT from the netlist.
  // The connectivity map below never depends on it, so a slow/flaky roster
  // must not hang or fail the tool.
  let roster = {};
  try { roster = await Promise.race([fetchRoster(port), sleep(20000).then(() => { throw new Error('roster timeout'); })]); }
  catch (e) { console.error('(roster unavailable: ' + e.message + ' — skipping unconnected-pin check)'); roster = null; }

  const { nets, pin2net } = parseProtel(nl);

  // 报告尾巴再贴一次横幅:网表输出动辄几百行,开头那行早滚出视野了,而"读错板"恰恰
  // 是在结论处才被采信的。收尾这一行让人和 agent 都能就地核账。
  const done = (code) => { if (!jsonOut) console.log(banner); process.exit(code); };

  if (oneNet) {
    const pins = nets[oneNet];
    if (!pins) { console.log(`net "${oneNet}" not found`); done(1); }
    console.log(`${oneNet}  (${pins.length} pins):`);
    for (const p of pins.slice().sort()) console.log('  ' + p);
    done(0);
  }

  const wantDes = (d) => all || desFilter.length === 0 || desFilter.includes(d);

  // Per-designator pin roster: prefer the live roster (knows every pin, incl.
  // unconnected ones); else fall back to pins that appear in the netlist.
  const desPins = {};
  if (roster) {
    for (const [des, pins] of Object.entries(roster)) desPins[des] = pins;
  } else {
    for (const p of Object.keys(pin2net)) { const i = p.lastIndexOf('-'); const des = p.slice(0, i); (desPins[des] = desPins[des] || []).push({ n: p.slice(i + 1), nm: '', nc: false }); }
  }

  // unconnected = roster pin absent from every net (only computable with roster).
  const unconnected = []; const ncPins = [];
  if (roster) for (const [des, pins] of Object.entries(roster)) for (const p of pins) {
    if (pin2net[`${des}-${p.n}`] === undefined) (p.nc ? ncPins : unconnected).push({ des, ...p });
  }

  if (jsonOut) {
    // scope 进 JSON:机器读的那一份也要能核"这是哪块板",不然只有人眼看得到横幅
    const scope = { ...(target.probe || {}), windowId: WINDOW_ID, banner };
    delete scope.pages; // 页表是解析窗口用的中间产物,不进报告
    console.log(JSON.stringify({ scope, nets, pin2net, unconnected: roster ? unconnected : null, ncPins }, null, 1));
    process.exit(unconnected.length ? 1 : 0);
  }

  if (desFilter.length || all) {
    for (const des of Object.keys(desPins).filter(wantDes).sort(cmpDes)) {
      const pins = desPins[des];
      console.log(`\n=== ${des} (${pins.length} pins) ===`);
      for (const p of pins.sort((a, b) => cmpDes(a.n, b.n))) {
        const net = pin2net[`${des}-${p.n}`];
        const tag = net === undefined ? (p.nc ? '  (no-connect)' : '  <<UNCONNECTED>>') : '';
        console.log(`  ${String(p.n).padEnd(6)} ${String(p.nm).padEnd(18)} ${net || '—'}${tag}`);
      }
    }
  }

  console.log(`\nNets: ${Object.keys(nets).length}  ·  source: EDA compiled netlist (Protel 2.0, whole project)`);
  if (roster) {
    console.log(`Active-page parts: ${Object.keys(roster).length}  ·  UNCONNECTED pins (in no net, not NC): ${unconnected.length}`);
    for (const p of unconnected.sort((a, b) => cmpDes(a.des, b.des))) console.log(`  ${p.des}-${p.n} (${p.nm})`);
    if (ncPins.length) console.log(`(also ${ncPins.length} pins carry an explicit no-connect flag — intentional)`);
  } else {
    console.log(`(roster unavailable — connectivity map above is complete; unconnected-pin check skipped)`);
  }
  done(unconnected.length ? 1 : 0);
}

main().catch((e) => {
  // 目标解析失败(--page 找不到 / 不在活动文档 / --window 不存在)是**用法错**,
  // 报错文本本身就是说明书,别再糊一层 stack 上去。
  if (e instanceof TargetError) { console.error(e.message); process.exit(TARGET_EXIT); }
  console.error(String(e && e.stack || e));
  process.exit(2);
});
