/**
 * sch-netcheck.mjs — Reconstruct the netlist of the ACTIVE schematic page and
 * report unconnected (floating) pins and multi-net shorts, without a live compile.
 *
 * Why this exists: `sch_Net`/`sch_Netlist` return empty/hang mid-build, so we
 * rebuild connectivity host-side from wires + net flags/ports (see the
 * easyeda-api SKILL "Schematic net check" note). Two hard-won correctness fixes
 * are baked in:
 *   1. FLOATING-POINT COORDS: pins report coords like 659.9999999999999 while
 *      wire vertices are clean integers (660). Exact string-key matching then
 *      calls a pin that is dead-on a wire "floating". We Math.round() every
 *      coordinate before keying. (This once made a fully-wired RJ45 read as 14
 *      floating pins.)
 *   2. MID-SEGMENT taps: a pin can sit on a wire segment without a vertex there,
 *      so we also union pins onto orthogonal segments (point-on-segment test).
 *
 * Connectivity model: net flags (componentType "netflag": +3V3/GND/+5V…) and
 * net ports ("netport": WIFI_DP…) are components carrying a `net` string with a
 * single pin at (x,y); labeled wires carry `wire.net`. Union-find over
 * pin/vertex coordinates; a group's net name comes from any flag/port/label
 * anchor in it. A pin is FLOATING if its group has no anchor AND nothing else
 * shares its coordinate (sz<=1), and it is not marked no-connect.
 *
 * Runs on the CURRENTLY ACTIVE schematic page — open the page you want first.
 * Reads twice and warns if the sheet changed between reads (user editing live).
 *
 * Usage:
 *   node sch-netcheck.mjs                 summary: floating (grouped) + shorts
 *   node sch-netcheck.mjs U10 U6 J2       full per-pin net table for those parts
 *   node sch-netcheck.mjs --all           full per-pin table for every part
 *   node sch-netcheck.mjs --json          raw JSON of every pin
 *   node sch-netcheck.mjs --page <uuid>   ⭐ target the WINDOW whose project holds
 *                                        that page, and require it to be the active
 *                                        document. Not found / found twice / not
 *                                        active = hard error, never a silent
 *                                        fallback to the active window.
 *   node sch-netcheck.mjs --window <id>   target a specific EDA window (id from
 *                                        GET /eda-windows or eda_windows); env
 *                                        EDA_WINDOW_ID does the same. Without it
 *                                        (and without --page) the bridge's ACTIVE
 *                                        window is pinned at start-up — pinned so
 *                                        it cannot drift between the two reads, but
 *                                        WHICH window that is is still the bridge's
 *                                        call, so with two windows open pass it.
 *
 * Exit code: 0 = clean (no floating, no shorts) · 1 = issues found · 5 = target
 *            resolution failed (bad --page/--window) · other >1 = infrastructure
 *            error (no bridge / no EDA / wrong doc type).
 */
// 找桥 / 发 HTTP / 解析 --window 全在这一份共享底座里(此前四个脚本各抄一份)
import { findBridge, execute as bridgeExecute, parseWindowArg, windowTag } from './bridge-client.mjs';
// 页 uuid → 窗口:EDA 语义那一层(bridge-client 只管传输)
import { parsePageArg, assertNoUuidArgs, resolveTarget, targetBanner, TargetError, TARGET_EXIT } from './eda-target.mjs';

// Target window: null = whatever the bridge calls "active" right now.
// Both reads below must land on the SAME window, so it is fixed once in main().
let WINDOW_ID = null;

const execute = (port, code) => bridgeExecute(port, code, { windowId: WINDOW_ID });

const NETCHECK_CODE = `
const R = v => Math.round(v);
const key = (x, y) => R(x) + ',' + R(y);
const parent = new Map();
function find(k){ if(!parent.has(k)){parent.set(k,k);return k;} let r=k; while(parent.get(r)!==r)r=parent.get(r); let c=k; while(parent.get(c)!==c){const n=parent.get(c);parent.set(c,r);c=n;} return r; }
function uni(a,b){ const ra=find(a),rb=find(b); if(ra!==rb)parent.set(ra,rb); }
const ids = await eda.sch_PrimitiveComponent.getAllPrimitiveId();
const anchors = []; const compPins = [];
for (const id of ids){
  const c = await eda.sch_PrimitiveComponent.get(id);
  let d=''; try{ d = c.getState_Designator && c.getState_Designator(); }catch(e){ d=''; }
  const t = c.componentType; const cnet = c.net||'';
  const pins = await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id);
  if (pins && pins.length){ for (const p of pins){ const k=key(p.x,p.y); find(k);
    if (t==='netflag'||t==='netport'){ if(cnet) anchors.push({k,net:cnet}); }
    else if (t==='part'){ compPins.push({des:d||'?',pn:p.pinNumber,name:p.pinName,k,x:R(p.x),y:R(p.y),nc:!!p.noConnected}); } } }
}
const wires = await eda.sch_PrimitiveWire.getAll();
const segs = [];
for (const w of wires){ const ln=w.line||[]; const vs=[];
  for (let i=0;i+1<ln.length;i+=2) vs.push([R(ln[i]),R(ln[i+1])]);
  for (let i=1;i<vs.length;i++) uni(key(vs[0][0],vs[0][1]), key(vs[i][0],vs[i][1]));
  if (w.net && vs.length) anchors.push({k:key(vs[0][0],vs[0][1]), net:w.net});
  for (let i=0;i+1<vs.length;i++) segs.push([vs[i][0],vs[i][1],vs[i+1][0],vs[i+1][1]]); }
function onseg(px,py,ax,ay,bx,by){ if(ax===bx&&px===ax)return py>=Math.min(ay,by)&&py<=Math.max(ay,by); if(ay===by&&py===ay)return px>=Math.min(ax,bx)&&px<=Math.max(ax,bx); return false; }
const anchorPts = anchors.map(a=>{ const s=a.k.split(','); return {k:a.k,x:parseInt(s[0]),y:parseInt(s[1])}; });
for (const pt of compPins.concat(anchorPts)){ for (const s of segs){ if(onseg(pt.x,pt.y,s[0],s[1],s[2],s[3])) uni(pt.k,key(s[0],s[1])); } }
const gNet = new Map();
for (const a of anchors){ const r=find(a.k); if(!gNet.has(r))gNet.set(r,a.net); else if(gNet.get(r)!==a.net){ const cur=gNet.get(r); if(cur.split('|').indexOf(a.net)<0)gNet.set(r,cur+'|'+a.net); } }
const gSize = new Map();
for (const k of parent.keys()){ const r=find(k); gSize.set(r,(gSize.get(r)||0)+1); }
const out = [];
for (const cp of compPins){ const r=find(cp.k); out.push({des:cp.des,pn:cp.pn,name:cp.name,net:gNet.get(r)||'',nc:cp.nc,sz:gSize.get(r)||1}); }
const doc = await eda.dmt_SelectControl.getCurrentDocumentInfo();
let pageName='';
try{ const pages=await eda.dmt_Schematic.getAllSchematicPagesInfo(); const pg=(pages||[]).find(p=>p.uuid===(doc&&doc.uuid)); if(pg)pageName=pg.name||pg.friendlyName||''; }catch(e){}
let projName='',boardName='';
try{ const p=await eda.dmt_Project.getCurrentProjectInfo(); if(p)projName=p.friendlyName||p.name||''; }catch(e){}
try{ const b=await eda.dmt_Board.getCurrentBoardInfo(); if(b)boardName=b.name||''; }catch(e){}
return { pins: out, docType: doc&&doc.documentType, pageUuid: doc&&doc.uuid, pageName, projName, boardName };
`.trim();

function grouped(pins) {
  const by = {};
  for (const p of pins) (by[p.des] = by[p.des] || []).push(p.pn + '/' + p.name);
  return Object.keys(by).sort().map((d) => `  ${d.padEnd(7)}${by[d].join(', ')}`).join('\n');
}

async function readOnce(port) {
  const resp = await execute(port, NETCHECK_CODE);
  if (!resp.success) throw new Error('execute failed: ' + resp.error);
  return resp.result;
}

async function main() {
  // parseWindowArg / parsePageArg 摘掉各自的取值,剩下的裸参数才是位号
  const { windowId, rest: afterWindow } = parseWindowArg(process.argv.slice(2));
  const { pageUuid, rest: args } = parsePageArg(afterWindow);
  const wantJson = args.includes('--json');
  const wantAll = args.includes('--all');
  const filters = args.filter((a) => !a.startsWith('--'));
  // 位号位置上出现 uuid = 想指定页却指定成了一个永不匹配的位号(报告照出、不报错)
  assertNoUuidArgs(filters, '想指定原理图页请用 --page <uuid>;想指定窗口用 --window <id>。');

  const bridge = await findBridge();
  if (!bridge) { console.error('No easyeda-bridge on 49620-49629. Start the bridge / MCP first, and load run-api-gateway in EDA.'); process.exit(2); }
  if (!bridge.health.edaConnected) { console.error('Bridge up but no EDA window connected.'); process.exit(3); }

  // 目标窗口开跑前钉死:下面要读两次比对稳定性,两次必须落在同一个窗口上
  const target = await resolveTarget(bridge.port, { windowId, pageUuid });
  WINDOW_ID = target.windowId;
  for (const w of target.warnings) (wantJson ? console.error : console.log)(w);
  if (wantJson) console.error(targetBanner('netcheck', target)); // json 模式 stdout 只能是 JSON

  const a = await readOnce(bridge.port);
  if (a.docType !== 1) { console.error(`Active document is not a schematic page (documentType=${a.docType}). Open the target page first.`); process.exit(4); }
  const b = await readOnce(bridge.port);
  const sig = (r) => JSON.stringify(r.pins.map((p) => [p.des, p.pn, p.net, p.sz, p.nc]));
  const stable = sig(a) === sig(b);
  const pins = b.pins;

  if (wantJson) { console.log(JSON.stringify(pins, null, 2)); process.exit(0); }

  // ⚠ scope 横幅:designator 在各板独立编号,读错板的报告和读对板的长得一模一样
  // (曾经据此读错过板)。先核这一行再采信下面的结果。
  // 页 uuid 也印出来:页名跨板重名,只有 uuid 能和调用方要的那一页对上账
  console.log(`[netcheck] 读的是: 工程 ${b.projName || '?'} / 板 ${b.boardName || '?'} / 页 ${b.pageName || '(unnamed)'}`
    + ` [${b.pageUuid || '?'}]  ·  窗口 ${windowTag(WINDOW_ID)}${target.windows.length > 1 ? `(共${target.windows.length}个)` : ''}`);
  const hdr = `Page: ${b.pageName || '(unnamed)'}  ·  ${pins.length} part pins  ·  port ${bridge.port}`;
  console.log(hdr);
  if (!stable) console.log('⚠ Sheet CHANGED between two reads — user is editing live. Re-run when stable before trusting results.');

  const floating = pins.filter((p) => p.net === '' && p.sz <= 1 && !p.nc);
  const shorts = pins.filter((p) => p.net.includes('|'));

  if (filters.length || wantAll) {
    const want = wantAll ? null : new Set(filters);
    const sel = pins.filter((p) => !want || want.has(p.des));
    const by = {};
    for (const p of sel) (by[p.des] = by[p.des] || []).push(p);
    for (const des of Object.keys(by).sort()) {
      console.log(`\n=== ${des} (${by[des].length} pins) ===`);
      for (const p of by[des].sort((x, y) => x.pn.length - y.pn.length || (x.pn < y.pn ? -1 : 1))) {
        const tag = p.net.includes('|') ? '  <<SHORT>>' : (p.net === '' && p.sz <= 1 && !p.nc ? '  <<FLOATING>>' : '');
        const net = p.net || (p.nc ? '(none)' : `(local net, sz${p.sz})`);
        console.log(`  ${p.pn.padStart(3)} ${p.name.padEnd(18)} ${net}${p.nc ? ' [NC]' : ''}${tag}`);
      }
    }
    console.log('');
  }

  console.log(`\nFLOATING (unconnected, non-NC): ${floating.length}`);
  if (floating.length) console.log(grouped(floating));
  console.log(`SHORTS (pin on >1 named net): ${shorts.length}`);
  if (shorts.length) for (const p of shorts) console.log(`  ${p.des}.${p.pn} (${p.name}) -> ${p.net}`);

  const clean = floating.length === 0 && shorts.length === 0;
  console.log(`\n${clean ? '✅ CLEAN' : '❌ ISSUES'}${stable ? '' : ' (UNSTABLE READ)'}`);
  process.exit(clean && stable ? 0 : 1);
}

main().catch((e) => {
  // 目标解析失败(--page 找不到 / 不在活动文档 / --window 不存在)是**用法错**:
  // 报错文本本身就是说明书,而且退出码要和"有问题"(1)分开,别让调用方当成检查结论。
  if (e instanceof TargetError) { console.error(e.message); process.exit(TARGET_EXIT); }
  console.error(e);
  process.exit(1);
});
