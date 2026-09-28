/**
 * capture-canvas.mjs — 把 EasyEDA 画布截成一张可以直接看的 PNG。
 *
 * 为什么需要一个脚本、而不是一句 `eda_execute`:
 * `dmt_EditorControl.getCurrentRenderedAreaImage()` 返回的是 **Blob**,而 Blob
 * **过不了 JSON 序列化** —— 经桥传回来会变成 `{}`。所以必须在 **EasyEDA 的浏览器
 * 运行时里**先把字节 base64 成字符串(字符串能序列化),回到这边再解码落盘。
 *
 * 取景(优先级 select > zoom > fit;都不给 = 拍当前视口):
 *   --select A,B,C    选中这些位号 → zoomToSelectedPrimitives()(框住某几个器件)
 *   --zoom x,y,scale  zoomTo(x,y,scale)。x/y 单位:PCB=mil,原理图=0.01inch;
 *                     scale 是缩放百分比,≈15–40 大致框住一颗芯片 + 邻域,越大越紧
 *   --fit             zoomToAllPrimitives()(整页/整板)
 *
 * ⚠ **不要用 `dmt_EditorControl.zoomToRegion()`** —— 实测它在这个网关下是个空操作:
 * 恒返回 true 但视口纹丝不动。`zoomTo()` 与 `zoomToSelectedPrimitives()` 正常,
 * 且截图会跟随它们。
 *
 * 其它:
 *   --window <id>     指定 EDA 窗口(见 GET /eda-windows;env EDA_WINDOW_ID 同效)。
 *                     不给 = bridge 的"活动窗口",而它会在两次调用之间自己飘走。
 *   [outPath]         输出 PNG 路径,默认 ./eda-canvas-<ts>.png
 *
 * 退出码:0 成功 · 1 没找到 bridge · 2 bridge 在但没有 EDA 窗口 · 3 执行失败 · 4 取图失败
 *
 * 两副面孔:直接 `node capture-canvas.mjs` 是上面这个 CLI;被 `import` 时只导出
 * `buildCaptureCode()`(MCP server 的 eda_screenshot 进程内直调,不再 spawn 一个 node)。
 */
import { writeFileSync, realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { findBridge, exec as bridgeExec, parseWindowArg, windowTag } from './bridge-client.mjs';

function parseArgs(argv) {
  const o = { fit: false, select: null, zoom: null, out: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--fit') o.fit = true;
    else if (a === '--select') o.select = String(argv[++i] || '').split(',').map((s) => s.trim()).filter(Boolean);
    else if (a === '--zoom') o.zoom = String(argv[++i] || '').split(',').map(Number);
    else if (!a.startsWith('--') && !o.out) o.out = a;
  }
  return o;
}

/** 取景片段。空字符串 = 不动视口。PCB 与原理图的选择控制器不是同一个,所以要按文档类型分派。 */
function framing(o) {
  if (o.select && o.select.length) {
    return `const _d = await eda.dmt_SelectControl.getCurrentDocumentInfo();
const _SC = (_d && _d.documentType === 3) ? eda.pcb_SelectControl : eda.sch_SelectControl;
await _SC.clearSelected();
await _SC.doCrossProbeSelect(${JSON.stringify(o.select)}, [], [], false, true);
await eda.dmt_EditorControl.zoomToSelectedPrimitives();
await new Promise(r => setTimeout(r, 400));`;
  }
  if (o.zoom && o.zoom.length >= 3 && o.zoom.every(Number.isFinite)) {
    const [x, y, s] = o.zoom;
    return `await eda.dmt_EditorControl.zoomTo(${x}, ${y}, ${s});
await new Promise(r => setTimeout(r, 400));`;
  }
  if (o.fit) {
    return `await eda.dmt_EditorControl.zoomToAllPrimitives();
await new Promise(r => setTimeout(r, 400));`;
  }
  return '';
}

/**
 * 生成「在 EDA 里跑」的那段截图代码。CLI 与 MCP server(进程内直调,不再 spawn)共用这一份。
 *
 * o.scopeJs —— 可选,一段以 `return s;` 收尾的作用域探测代码(见 eda-mcp-server 的 SCOPE_JS)。
 * 给了就把它拼进**同一次 eval**:截图本来就要往返一趟 EDA,作用域顺手带回来,
 * 省掉调用方为了贴横幅而单独发的那一次(实测约 120ms/次)。探测失败不影响出图。
 */
export const buildCaptureCode = (o = {}) => `
${framing(o)}
const blob = await eda.dmt_EditorControl.getCurrentRenderedAreaImage();
if (!blob) return { ok: false, reason: 'no image — is a canvas document open?' };
const bytes = new Uint8Array(await blob.arrayBuffer());
// 分块拼接:String.fromCharCode 一次吃不下几十万个参数(会爆栈)
let s = '';
const CH = 8192;
for (let i = 0; i < bytes.length; i += CH) s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
${o.select && o.select.length
    ? `try {
  const _d2 = await eda.dmt_SelectControl.getCurrentDocumentInfo();
  await ((_d2 && _d2.documentType === 3) ? eda.pcb_SelectControl : eda.sch_SelectControl).clearSelected();
} catch (e) { /* 选择状态清不掉不影响出图 */ }`
    : ''}
${o.scopeJs
    ? `let __scope = null;
try { __scope = await (async () => { ${o.scopeJs} })(); } catch (e) { /* 作用域探测失败不影响出图 */ }`
    : 'const __scope = null;'}
return { ok: true, type: blob.type, size: bytes.length, b64: btoa(s), scope: __scope };
`.trim();

async function main() {
  const { windowId, rest } = parseWindowArg(process.argv.slice(2));
  const o = parseArgs(rest);
  const out = o.out || `./eda-canvas-${Date.now()}.png`;

  const bridge = await findBridge();
  if (!bridge) { console.error('没找到 bridge(49620-49629)。先起 MCP server 或独立 bridge。'); process.exit(1); }
  if (!bridge.health.edaConnected) { console.error('bridge 在,但没有 EDA 窗口连上。'); process.exit(2); }

  let r;
  try {
    r = await bridgeExec(bridge.port, buildCaptureCode(o), { windowId });
  } catch (e) {
    console.error('执行失败:', e && e.message ? e.message : String(e));
    if (e && e.edaStack) console.error(e.edaStack);
    process.exit(3);
  }
  if (!r || !r.ok) { console.error('取图失败:', r && r.reason); process.exit(4); }

  writeFileSync(out, Buffer.from(r.b64, 'base64'));
  console.log(`Saved ${out} (${r.type}, ${r.size} bytes) · bridge :${bridge.port} · window ${windowTag(windowId)}`);
}

// 只有**直接 node 跑**这个文件才走 CLI —— MCP server 是 import 进去拿 buildCaptureCode 的,
// 不加这道闸,import 的瞬间就会去连桥、截图、写文件。
function isDirectRun() {
  try {
    return !!process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
  } catch { return false; }
}

if (isDirectRun()) main().catch((e) => { console.error(e); process.exit(1); });
